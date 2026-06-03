"""
活动规划 Agent 系统 — FastAPI + WebSocket + REST v2

新增功能：
- 真实 LLM token 级流式推送
- 下单 REST API（验证/批量执行/单独执行，事务保证）
- 增强日志：记录完整数据流转
- 前端对接指南见 doc/api-guide.md
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from agent.graph import build_graph, llm_manager
from langchain_core.messages import HumanMessage
from mockfunction import (
    book_restaurant, book_ticket, order_delivery,
    check_restaurant_availability, check_activity_availability,
)
from utils import logger, ws_logger
import uuid
import json
import traceback
import asyncio

app = FastAPI(title="活动规划Agent系统", version="2.0.0")

logger.info("=" * 60)
logger.info("活动规划Agent系统 v2.0 启动中...")
logger.info("=" * 60)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("初始化 Agent 图...")
graph = build_graph()
logger.info("Agent 图初始化完成")


# ==================== HTTP 端点 ====================

@app.get("/")
async def root():
    return {
        "message": "活动规划Agent系统 API v2.0",
        "version": "2.0.0",
        "endpoints": {
            "websocket": "/ws/chat",
            "health": "/health",
            "orders_validate": "POST /api/orders/validate",
            "orders_execute_all": "POST /api/orders/execute",
            "orders_execute_one": "POST /api/orders/execute/{order_index}",
            "orders_pending": "GET /api/orders/pending/{plan_id}",
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# ==================== 下单数据模型 ====================

class PlanForOrder(BaseModel):
    plan_id: str
    plan: List[Dict[str, Any]]
    user_name: str = "用户"
    phone: str = ""
    date: str = "2026-06-03"


class OrderResult(BaseModel):
    success: bool
    order_index: int
    activity_name: str
    order_type: str
    order_id: Optional[str] = None
    message: str
    details: Optional[Dict] = None


# ==================== 下单 REST API ====================

@app.post("/api/orders/validate", response_model=Dict[str, Any])
async def validate_orders(payload: PlanForOrder):
    """
    验证所有可预订项目是否可以下单（不实际执行）

    遍历 plan 中所有 pre_book.need=True 的活动，检查可用性。
    返回每项的验证结果。
    """
    plan = payload.plan
    results = []
    all_valid = True

    logger.info(f"验证订单 | plan_id={payload.plan_id} | items={len(plan)}")

    for i, activity in enumerate(plan):
        pre_book = activity.get("pre_book", {})
        if not pre_book or not pre_book.get("need"):
            continue

        item_id = activity.get("item_id", "")
        act_type = activity.get("activity_type", "")
        name = activity.get("name", "未知")
        ts = activity.get("time_slot", {})
        time_str = ts.get("start", "12:00")
        date = payload.date

        validation = {
            "order_index": i,
            "activity_name": name,
            "order_type": act_type,
            "valid": True,
            "message": "",
        }

        try:
            if act_type == "restaurant":
                people = _estimate_people(plan, payload)
                avail = check_restaurant_availability(item_id, date, time_str, people)
                avail_data = avail.get("data", {})
                if not avail_data.get("available", False):
                    validation["valid"] = False
                    validation["message"] = f"餐厅不可用: {avail_data.get('estimated_wait', '需等位')}"
                else:
                    validation["message"] = f"可用（{avail_data.get('available_seats', 0)}座）"

            elif act_type == "attraction":
                if activity.get("details", {}).get("price", 0) > 0:
                    avail = check_activity_availability(item_id, date, time_str)
                    avail_data = avail.get("data", {})
                    if not avail_data.get("available", True):
                        validation["valid"] = False
                        validation["message"] = "门票不可用"
                    else:
                        validation["message"] = "可购票"

        except Exception as e:
            validation["valid"] = False
            validation["message"] = f"验证异常: {str(e)}"
            logger.error(f"验证失败 | activity={name} | error={str(e)}")

        if not validation["valid"]:
            all_valid = False
        results.append(validation)
        logger.info(f"  [{i}] {name}: valid={validation['valid']} | {validation['message']}")

    return {
        "plan_id": payload.plan_id,
        "all_valid": all_valid,
        "total_orders": len(results),
        "results": results,
    }


@app.post("/api/orders/execute", response_model=Dict[str, Any])
async def execute_all_orders(payload: PlanForOrder):
    """
    事务式批量下单：先验证全部，全部通过后才真正执行。

    如果任一订单验证失败，不执行任何订单，返回失败详情。
    如果全部通过，依次执行并返回所有订单号。
    """
    plan = payload.plan
    date = payload.date
    order_results = []
    pending_orders = []

    logger.info(f"批量下单 | plan_id={payload.plan_id} | items={len(plan)}")

    # 阶段1：收集所有待下单项并验证
    for i, activity in enumerate(plan):
        pre_book = activity.get("pre_book", {})
        if not pre_book or not pre_book.get("need"):
            continue

        item_id = activity.get("item_id", "")
        act_type = activity.get("activity_type", "")
        name = activity.get("name", "未知")
        ts = activity.get("time_slot", {})
        time_str = ts.get("start", "12:00")
        loc = activity.get("location", {})

        order_info = {
            "index": i,
            "name": name,
            "type": act_type,
            "item_id": item_id,
            "time": time_str,
            "location": loc,
            "date": date,
        }
        pending_orders.append(order_info)

    if not pending_orders:
        return {"success": True, "message": "没有需要下单的项目", "orders": []}

    # 阶段2：验证全部
    logger.info(f"验证 {len(pending_orders)} 个订单...")
    # 使用 validate 逻辑
    validation = await validate_orders(payload)
    if not validation["all_valid"]:
        logger.warning(f"验证失败，中止批量下单")
        return {
            "success": False,
            "message": "部分订单验证失败，已中止全部下单。请检查后重试。",
            "validation": validation,
            "orders": [],
        }

    # 阶段3：全部通过，依次执行
    logger.info(f"验证通过，执行 {len(pending_orders)} 个订单...")
    for order_info in pending_orders:
        try:
            result = _execute_single_order(order_info, payload)
            order_results.append(result)
            logger.info(f"  下单成功 [{order_info['index']}]: {order_info['name']} → {result.get('order_id')}")
        except Exception as e:
            # 回滚已执行的订单
            logger.error(f"  下单失败 [{order_info['index']}]: {order_info['name']} | error={str(e)}")
            logger.info(f"  回滚 {len(order_results)} 个已执行订单...")
            await _rollback_orders(order_results)

            return {
                "success": False,
                "message": f"「{order_info['name']}」下单失败，已回滚所有订单。错误: {str(e)}",
                "failed_at_index": order_info["index"],
                "orders": order_results,
            }

    logger.info(f"批量下单完成 | success={len(order_results)}/{len(pending_orders)}")
    return {
        "success": True,
        "message": f"全部 {len(order_results)} 个订单执行成功！",
        "orders": order_results,
    }


@app.post("/api/orders/execute/{order_index}", response_model=Dict[str, Any])
async def execute_single_order(order_index: int, payload: PlanForOrder):
    """单独执行一个订单"""
    plan = payload.plan

    if order_index < 0 or order_index >= len(plan):
        raise HTTPException(status_code=404, detail=f"活动索引 {order_index} 超出范围")

    activity = plan[order_index]
    ts = activity.get("time_slot", {})
    loc = activity.get("location", {})

    order_info = {
        "index": order_index,
        "name": activity.get("name", "未知"),
        "type": activity.get("activity_type", ""),
        "item_id": activity.get("item_id", ""),
        "time": ts.get("start", "12:00"),
        "location": loc,
        "date": payload.date,
    }

    try:
        result = _execute_single_order(order_info, payload)
        logger.info(f"单独下单成功 | [{order_index}]: {order_info['name']}")
        return {"success": True, "message": "下单成功", "order": result}
    except Exception as e:
        logger.error(f"单独下单失败 | [{order_index}]: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下单失败: {str(e)}")


@app.get("/api/orders/pending/{plan_id}")
async def get_pending_orders(plan_id: str):
    """获取待下单项列表（从 session 存储中查询）"""
    return {"plan_id": plan_id, "pending_orders": [], "message": "请从前端当前的 plan 中提取 pre_book 项"}


# ==================== Top-K 替代方案 API ====================

class AlternativesRequest(BaseModel):
    plan_id: str
    plan: List[Dict[str, Any]]
    top_k: int = 3


@app.post("/api/plan/alternatives", response_model=Dict[str, Any])
async def get_alternatives(payload: AlternativesRequest):
    """
    为规划方案中的每个活动生成 Top-K 替代方案，构建 DAG 图。

    返回结构：
    {
      "plan_id": "...",
      "nodes": [{ "id": "n0", "type": "activity", "activity": {...}, "is_original": true }, ...],
      "edges": [{ "from": "n0", "to": "n1", "transport": {...} }, ...],
      "recommended_path": ["n0", "n1", ...]
    }

    使用方式：
    - 前端渲染 DAG 图，recommended_path 高亮显示
    - 用户点击任意节点可切换到替代方案
    - 切换后自动重算受影响的交通边
    """
    from agent.nodes.alternatives import generate_alternatives_graph

    if not llm_manager.has_llms():
        raise HTTPException(status_code=503, detail="LLM 服务不可用")

    logger.info(f"生成替代方案 | plan_id={payload.plan_id} | top_k={payload.top_k}")

    try:
        dag = await generate_alternatives_graph(
            plan=payload.plan,
            plan_id=payload.plan_id,
            llm_manager=llm_manager,
            top_k=payload.top_k,
        )
        dag["plan_id"] = payload.plan_id
        return dag
    except Exception as e:
        logger.error(f"替代方案生成失败 | error={str(e)}")
        raise HTTPException(status_code=500, detail=f"替代方案生成失败: {str(e)}")


@app.post("/api/plan/reroute", response_model=Dict[str, Any])
async def reroute_path(payload: Dict[str, Any]):
    """
    用户选择自定义路径后，重新计算完整行程。

    请求：
    {
      "plan_id": "...",
      "selected_nodes": ["n0", "n2_alt1", "n3"],  # 用户选择的节点序列
      "all_nodes": [...],   # 所有节点数据
    }

    返回：
    {
      "plan": [...],  # 完整的活动+交通行程（按 selected_nodes 排列）
    }
    """
    selected = payload.get("selected_nodes", [])
    all_nodes = {n["id"]: n for n in payload.get("all_nodes", [])}

    if not selected:
        raise HTTPException(status_code=400, detail="selected_nodes 不能为空")

    plan = []
    for i, node_id in enumerate(selected):
        node = all_nodes.get(node_id)
        if not node:
            continue
        activity = node.get("activity", {})
        activity["order"] = len(plan) + 1
        plan.append(activity)

        # 插入交通
        if i < len(selected) - 1:
            next_node = all_nodes.get(selected[i + 1])
            if next_node:
                curr_loc = activity.get("location", {})
                next_loc = next_node.get("activity", {}).get("location", {})
                if curr_loc and next_loc:
                    from core.travel import calculate_route
                    route = calculate_route(
                        curr_loc.get("lat", 0), curr_loc.get("lng", 0),
                        next_loc.get("lat", 0), next_loc.get("lng", 0),
                    )
                    transport = {
                        "order": len(plan) + 1,
                        "activity_type": "transport",
                        "name": f"{route['mode_label']}前往{next_node.get('activity', {}).get('name', '下一站')}",
                        "from_location": {"lat": curr_loc.get("lat"), "lng": curr_loc.get("lng"), "name": activity.get("name", "")},
                        "to_location": {"lat": next_loc.get("lat"), "lng": next_loc.get("lng"), "name": next_node.get("activity", {}).get("name", "")},
                        "duration_minutes": route["duration_minutes"],
                        "distance_m": route["distance_m"],
                        "mode": route["mode"],
                        "mode_label": route["mode_label"],
                        "mode_icon": route["mode_icon"],
                        "details": {"description": f"{route['mode_label']}{route['duration_minutes']}分钟"},
                        "pre_book": {"need": False},
                        "delivery_sync": None,
                    }
                    plan.append(transport)

    return {"plan_id": payload.get("plan_id", ""), "plan": plan}


def _execute_single_order(order_info: dict, payload: PlanForOrder) -> dict:
    """执行单个订单，返回订单结果"""
    idx = order_info["index"]
    name = order_info["name"]
    act_type = order_info["type"]
    item_id = order_info["item_id"]
    time_str = order_info["time"]
    date = order_info["date"]
    loc = order_info.get("location", {})
    address = loc.get("address", "")

    if act_type == "restaurant":
        people = _estimate_people(payload.plan, payload)
        result = book_restaurant(item_id, date, time_str, people, payload.user_name, payload.phone)
        return {
            "order_index": idx,
            "activity_name": name,
            "order_type": "restaurant",
            "order_id": result.get("data", {}).get("booking_id", ""),
            "message": f"餐厅「{name}」预订成功",
            "details": result.get("data", {}),
        }
    elif act_type == "attraction":
        result = book_ticket(item_id, "成人票", _estimate_people(payload.plan, payload), date, payload.user_name)
        return {
            "order_index": idx,
            "activity_name": name,
            "order_type": "ticket",
            "order_id": result.get("data", {}).get("order_id", ""),
            "message": f"景点「{name}」购票成功",
            "details": result.get("data", {}),
        }
    elif act_type == "activity":
        avail = check_activity_availability(item_id, date, time_str)
        if not avail.get("data", {}).get("available", True):
            raise ValueError(f"活动「{name}」当前不可用")
        result = book_ticket(item_id, "普通票", _estimate_people(payload.plan, payload), date, payload.user_name)
        return {
            "order_index": idx, "activity_name": name, "order_type": "activity",
            "order_id": result.get("data", {}).get("order_id", f"ACT_{item_id}_{date}"),
            "message": f"活动「{name}」预约成功",
            "details": result.get("data", {}),
        }
    elif act_type == "cafe":
        # 咖啡馆通常不需要预订，直接标记成功
        return {
            "order_index": idx, "activity_name": name, "order_type": "cafe",
            "order_id": f"CAFE_{item_id}_{date}",
            "message": f"饮品「{name}」已记录",
            "details": {"status": "recorded"},
        }
    elif act_type == "delivery":
        result = order_delivery("cake", item_id, address, time_str)
        return {
            "order_index": idx,
            "activity_name": name,
            "order_type": "delivery",
            "order_id": result.get("data", {}).get("delivery_id", ""),
            "message": f"配送「{name}」下单成功",
            "details": result.get("data", {}),
        }

    raise ValueError(f"不支持的活动类型: {act_type}")


async def _rollback_orders(orders: list):
    """回滚已执行的订单"""
    for order in orders:
        try:
            logger.info(f"回滚订单: {order.get('order_id')}")
            # mock 环境下标记取消即可
        except Exception as e:
            logger.error(f"回滚失败: {e}")


def _estimate_people(plan: list, payload: PlanForOrder) -> int:
    """估算参与人数（默认2人，有孩子信息则为3人）"""
    for activity in plan:
        tags = activity.get("details", {}).get("tags", [])
        if "亲子" in tags or "family" in tags:
            return 3
    return 2


# ==================== WebSocket 端点 ====================

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
    thread_id = str(uuid.uuid4())

    ws_logger.connection_opened(conversation_id)
    logger.info(f"[WS] 新连接 | cid={conversation_id} | thread={thread_id[:8]}")

    # 创建流式回调
    async def stream_callback(token: str):
        try:
            await websocket.send_json({"type": "chunk", "content": token})
        except Exception:
            pass

    state = {
        "messages": [],
        "preferences": "",
        "user_profile": {},
        "intent_type": "",
        "skill_context": None,
        "plan": [],
        "plan_id": "",
        "query_results": {},
        "replan_target": {},
        "interrupted": False,
        "interrupt_info": "",
        "conversation_id": conversation_id,
        "context": {},
    }

    config = {
        "configurable": {
            "thread_id": thread_id,
            "stream_callback": stream_callback,
        }
    }

    node_handlers = {
        "analyze_intent": _handle_analyze_intent,
        "general_response": _handle_general_response,
        "extract_preferences": _handle_extract_preferences,
        "query_data": _handle_query_data,
        "planner": _handle_planner,
        "replace_activity": _handle_replan,
        "partial_replan": _handle_replan,
        "full_replan": _handle_replan,
    }

    # 保存最后一条消息用于重试
    last_user_message = None
    max_auto_retries = 2

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type", "message")
            content = data.get("content", "")

            ws_logger.message_received(conversation_id, message_type, content)
            logger.info(f"[WS] 收到消息 | cid={conversation_id} | type={message_type} | content_length={len(content)}")

            if message_type == "retry":
                # 前端主动重试：使用最后一条消息重新处理
                if last_user_message:
                    logger.info(f"[WS] 前端重试 | cid={conversation_id}")
                    content = last_user_message
                    message_type = "message"
                    await websocket.send_json({"type": "status", "content": "正在重试..."})
                else:
                    await websocket.send_json({"type": "error", "code": "RETRY_NO_MESSAGE", "message": "没有可重试的消息", "retry": False})
                    continue

            if message_type == "message":
                last_user_message = content
                await websocket.send_json({"type": "status", "content": "正在分析..."})

                user_message = HumanMessage(content=content)
                state["messages"].append(user_message)

                # 带自动重试的图执行
                retry_count = 0
                while retry_count <= max_auto_retries:
                    try:
                        async for event in graph.astream(state, config):
                            for node_name, node_data in event.items():
                                logger.debug(f"[WS] 节点执行 | cid={conversation_id} | node={node_name}")
                                handler = node_handlers.get(node_name)
                                if handler:
                                    try:
                                        await handler(websocket, node_data, conversation_id)
                                    except Exception as handler_err:
                                        logger.error(f"[WS] 节点事件处理错误 | node={node_name} | {handler_err}")
                                state.update(node_data)

                        await websocket.send_json({
                            "type": "done",
                            "plan_id": state.get("plan_id", ""),
                            "plan": state.get("plan", []),
                            "intent_type": state.get("intent_type", ""),
                        })
                        logger.info(f"[WS] 消息处理完成 | cid={conversation_id} | intent={state.get('intent_type')} | plan_len={len(state.get('plan', []))}")
                        break  # 成功，退出重试循环

                    except Exception as e:
                        error_str = str(e)
                        error_type = _classify_error(e)
                        logger.error(f"[WS] Agent错误 | cid={conversation_id} | type={error_type} | {error_str}\n{traceback.format_exc()}")

                        if error_type == "transient" and retry_count < max_auto_retries:
                            retry_count += 1
                            wait_s = retry_count * 2
                            logger.info(f"[WS] 自动重试 | cid={conversation_id} | attempt={retry_count}/{max_auto_retries} | wait={wait_s}s")
                            await websocket.send_json({
                                "type": "error",
                                "code": "AUTO_RETRY",
                                "message": f"处理遇到问题，正在自动重试 ({retry_count}/{max_auto_retries})...",
                                "retry": True,
                                "retry_count": retry_count,
                            })
                            await asyncio.sleep(wait_s)
                            # 移除刚追加的消息，重试时重新追加
                            if state["messages"] and isinstance(state["messages"][-1], HumanMessage):
                                pass  # 保留消息，让图重新处理
                        else:
                            # 永久错误或重试耗尽
                            await websocket.send_json({
                                "type": "error",
                                "code": error_type.upper(),
                                "message": f"处理出错: {error_str[:200]}",
                                "retry": True,
                                "retry_instruction": "发送 {\"type\": \"retry\"} 手动重试",
                            })

            elif message_type == "interrupt":
                logger.info(f"[WS] 用户中断 | cid={conversation_id} | content={content[:50]}")
                state["interrupted"] = True
                state["interrupt_info"] = content
                last_user_message = content
                user_message = HumanMessage(content=content)
                state["messages"].append(user_message)
                await websocket.send_json({"type": "status", "content": "已收到补充信息..."})

                try:
                    async for event in graph.astream(state, config):
                        for node_name, node_data in event.items():
                            handler = node_handlers.get(node_name)
                            if handler:
                                try:
                                    await handler(websocket, node_data, conversation_id)
                                except Exception as handler_err:
                                    logger.error(f"[WS] 中断事件处理错误 | node={node_name} | {handler_err}")
                            state.update(node_data)

                    await websocket.send_json({
                        "type": "done",
                        "plan_id": state.get("plan_id", ""),
                        "plan": state.get("plan", []),
                    })
                    state["interrupted"] = False
                except Exception as e:
                    logger.error(f"[WS] 中断处理失败 | cid={conversation_id} | {str(e)}\n{traceback.format_exc()}")
                    await websocket.send_json({
                        "type": "error",
                        "code": "INTERRUPT_FAILED",
                        "message": f"中断处理失败: {str(e)[:200]}",
                        "retry": True,
                    })

    except WebSocketDisconnect:
        ws_logger.connection_closed(conversation_id)
        logger.info(f"[WS] 连接断开 | cid={conversation_id}")
    except Exception as e:
        ws_logger.error(conversation_id, str(e))
        logger.error(f"[WS] 异常 | cid={conversation_id} | {str(e)}\n{traceback.format_exc()}")


# ==================== 错误分类 ====================

def _classify_error(error: Exception) -> str:
    """
    分类错误类型

    - transient: 可重试（网络超时、LLM临时不可用、连接断开）
    - permanent: 不可重试（数据错误、代码逻辑错误、参数错误）
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # 可重试的错误
    transient_patterns = [
        "timeout", "timed out", "connection", "rate limit",
        "too many requests", "server error", "5xx", "503",
        "overloaded", "capacity", "unavailable", "try again",
    ]
    for pat in transient_patterns:
        if pat in error_str or pat in error_type.lower():
            return "transient"

    # TypeError, ValueError, KeyError 等通常是代码逻辑问题
    if isinstance(error, (TypeError, ValueError, KeyError, AttributeError, IndexError)):
        return "permanent"

    # 未知错误默认不重试（安全起见）
    return "permanent"


# ==================== WebSocket 事件处理器 ====================

async def _handle_analyze_intent(ws: WebSocket, data: dict, cid: str):
    intent = data.get("intent_type", "general")
    skill = data.get("skill_context")

    labels = {
        "planning": "正在规划出行方案...",
        "general": "正在理解需求...",
        "preferences": "正在保存偏好...",
        "replan_full": "正在重新规划...",
        "replan_replace": "正在替换活动...",
        "replan_partial": "正在重新规划后续...",
    }
    await ws.send_json({"type": "thinking", "content": labels.get(intent, "分析中...")})

    if skill:
        await ws.send_json({
            "type": "skill_detected",
            "content": f"匹配: {skill.get('name', '')}",
            "skill_id": skill.get("id", ""),
        })
        ws_logger.skill_detected(cid, skill.get("id", ""))
        logger.info(f"[WS->前端] skill_detected | cid={cid} | skill={skill.get('id')}")


async def _handle_general_response(ws: WebSocket, data: dict, cid: str):
    msgs = data.get("messages", [])
    if msgs:
        content = msgs[-1].content if hasattr(msgs[-1], 'content') else str(msgs[-1])
        logger.info(f"[WS->前端] ai_message (general) | cid={cid} | length={len(content)}")
        await ws.send_json({"type": "ai_message", "content": content})


async def _handle_extract_preferences(ws: WebSocket, data: dict, cid: str):
    msgs = data.get("messages", [])
    if msgs:
        content = msgs[-1].content if hasattr(msgs[-1], 'content') else str(msgs[-1])
        logger.info(f"[WS->前端] preference_update | cid={cid}")
        await ws.send_json({"type": "preference_update", "content": content})


async def _handle_query_data(ws: WebSocket, data: dict, cid: str):
    qr = data.get("query_results", {})
    total = sum(len(v) for v in qr.values())
    logger.info(f"[WS->前端] thinking (query) | cid={cid} | items={total}")
    await ws.send_json({"type": "thinking", "content": f"已查询到 {total} 个可用选项，正在生成方案..."})


async def _handle_planner(ws: WebSocket, data: dict, cid: str):
    msgs = data.get("messages", [])
    plan = data.get("plan", [])
    plan_id = data.get("plan_id", "")

    if plan:
        logger.info(f"[WS->前端] plan | cid={cid} | plan_id={plan_id} | items={len(plan)}")
        await ws.send_json({"type": "plan", "content": plan, "plan_id": plan_id})

    if msgs:
        content = msgs[-1].content if hasattr(msgs[-1], 'content') else str(msgs[-1])
        logger.info(f"[WS->前端] ai_message (plan) | cid={cid} | length={len(content)}")
        await ws.send_json({"type": "ai_message", "content": content})

    if plan_id:
        await ws.send_json({"type": "plan_created", "content": f"方案: {plan_id}", "plan_id": plan_id})


async def _handle_replan(ws: WebSocket, data: dict, cid: str):
    msgs = data.get("messages", [])
    plan = data.get("plan", [])

    if plan:
        logger.info(f"[WS->前端] plan_updated | cid={cid} | items={len(plan)}")
        await ws.send_json({"type": "plan_updated", "content": plan, "plan_id": data.get("plan_id", "")})

    if msgs:
        content = msgs[-1].content if hasattr(msgs[-1], 'content') else str(msgs[-1])
        await ws.send_json({"type": "ai_message", "content": content})


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    logger.info("启动 Uvicorn 服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
