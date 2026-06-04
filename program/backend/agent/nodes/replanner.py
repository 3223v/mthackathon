"""
重规划节点 v3

三种重规划 + 流式LLM输出 + 结构化输出保底

1. replace_activity — 约束求解替换单活动
2. partial_replan — 保留前N个，重新规划后续（三层结构化输出）
3. full_replan — 清空方案，触发完整重规划
"""

import json
import re
import os
from typing import Dict, Any, List, Optional, Callable, Awaitable
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from agent.state import AgentState
from agent.nodes.query import format_data_for_prompt
from agent.nodes.planner import _parse_plan_json
from agent.schemas import PartialReplanOutput
from core.travel import calculate_route
from tools.query_tools import QueryTools
from utils import logger

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../config/prompts.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    prompts = json.load(f)

query_tools = QueryTools()
StreamCallback = Optional[Callable[[str], Awaitable[None]]]


# ==================== 替换单活动 ====================

async def replace_activity(
    state: AgentState,
    llm_manager,
    stream_callback: StreamCallback = None,
) -> Dict[str, Any]:
    """替换单活动 — 约束求解"""
    plan = state.get("plan", [])
    replan_target = state.get("replan_target", {})
    query_results = state.get("query_results", {})
    cid = state.get("conversation_id", "unknown")

    if not plan:
        logger.warning(f"替换失败：无现有规划 | cid={cid}")
        return _no_plan_response()

    target_index = _find_target_activity(plan, replan_target)

    # LLM 兜底：关键词无法定位时，用 LLM 识别用户想替换的活动
    if target_index is None and replan_target.get("target_description"):
        logger.info(f"关键词匹配失败，使用LLM识别目标活动 | cid={cid}")
        target_index = await _llm_find_target(
            plan, replan_target.get("target_description", ""), llm_manager
        )

    if target_index is None:
        logger.warning(f"无法定位目标活动 | cid={cid} | target={replan_target}")
        return _not_found_response(replan_target.get("target_description", "该活动"))

    target_activity = plan[target_index]
    logger.info(f"替换活动 | cid={cid} | idx={target_index} | name={target_activity.get('name')}")

    constraints = _calculate_constraints(plan, target_index)
    logger.debug(f"约束条件 | max_duration={constraints['max_duration_hours']}h | available={constraints.get('available_minutes')}min")

    alternatives = _query_alternatives(target_activity, constraints, query_results)
    logger.info(f"候选替代 | count={len(alternatives)}")

    if not alternatives:
        return _no_alternatives_response(target_activity.get("name", "该活动"))

    best = _select_best_alternative(alternatives, target_activity, constraints)
    new_activity = _build_replacement_activity(target_activity, best, constraints)
    new_plan = list(plan)
    new_plan[target_index] = new_activity
    new_plan = _recalculate_affected_transport(new_plan, target_index)

    response_text = (
        f"✅ 已将「{target_activity.get('name', '该活动')}」替换为「{new_activity.get('name')}」\n\n"
        f"时间安排不变，前后活动不受影响。"
    )

    logger.info(f"替换完成 | old={target_activity.get('name')} | new={new_activity.get('name')}")

    return {
        "plan": new_plan,
        "messages": [AIMessage(content=response_text)],
    }


# ==================== 部分重规划 ====================

async def partial_replan(
    state: AgentState,
    llm_manager,
    stream_callback: StreamCallback = None,
) -> Dict[str, Any]:
    """部分重规划 — 保留前N个，重新规划后续"""
    plan = state.get("plan", [])
    replan_target = state.get("replan_target", {})
    query_results = state.get("query_results", {})
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""
    cid = state.get("conversation_id", "unknown")

    if not plan:
        return _no_plan_response()

    split_index = replan_target.get("start_after_index")
    # 如果是 None（关键词没提取到序号），尝试从 plan 中按名称匹配
    if split_index is None:
        user_input_lower = replan_target.get("start_after", messages[-1].content if messages else "")
        split_index = _find_activity_by_name(plan, user_input_lower)
    # 仍然找不到，默认保留一半
    if split_index is None:
        split_index = max(0, len(plan) // 2 - 1)

    split_index = min(split_index, len(plan) - 1)

    kept = plan[:split_index + 1]
    last_kept = kept[-1]
    logger.info(f"部分重规划 | cid={cid} | keep=0..{split_index} | replan={split_index+1}..")

    start_time = last_kept.get("time_slot", {}).get("end", "12:00")
    start_location = last_kept.get("location", {})

    system_prompt = prompts["planning_system_prompt"]
    user_prompt = prompts["replan_partial_prompt"].format(
        kept_activities=json.dumps(kept, ensure_ascii=False, indent=2),
        start_time=start_time,
        start_location=json.dumps(start_location, ensure_ascii=False),
        user_request=user_input,
        available_data=format_data_for_prompt(query_results),
    )

    # 三层保底：结构化输出优先 → 文本解析 → 重试
    new_part = []
    max_retries = 2

    msg_list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    for retry_attempt in range(max_retries + 1):
        # Layer 1+2: 结构化输出
        if retry_attempt == 0:
            try:
                structured = await llm_manager.invoke_structured(msg_list, PartialReplanOutput)
                if structured and hasattr(structured, 'activities'):
                    new_part = [a.model_dump() if hasattr(a, 'model_dump') else a for a in structured.activities]
                    logger.info(f"PartialReplan 结构化输出成功 | activities={len(new_part)}")
                    break
            except Exception as e:
                logger.warning(f"PartialReplan 结构化输出失败 | error={str(e)[:100]}")

        # Layer 3: 文本解析
        try:
            retry_suffix = "\n\n⚠️ 上次输出JSON格式有误，请务必只输出纯JSON数组。" if retry_attempt > 0 else ""
            response_text = await llm_manager.invoke_with_logging(
                system_prompt=system_prompt,
                user_prompt=user_prompt + retry_suffix,
                stream_callback=stream_callback,
                log_prefix=f"PartialReplan(attempt{retry_attempt+1})",
            )
            new_part = _parse_plan_json(response_text)
            if new_part:
                logger.info(f"PartialReplan JSON解析成功 | activities={len(new_part)} | attempt={retry_attempt+1}")
                break
            else:
                logger.warning(f"PartialReplan JSON解析失败 | attempt={retry_attempt+1}")
        except Exception as e:
            logger.error(f"PartialReplan LLM调用失败 | attempt={retry_attempt+1} | error={str(e)}")
            if retry_attempt >= max_retries:
                return {"messages": [AIMessage(content=f"部分重规划失败：{str(e)}")]}

    if not new_part:
        logger.error(f"部分重规划完全失败（{max_retries+1}次尝试）")
        return {"messages": [AIMessage(content="部分重规划多次尝试均失败，请尝试全量重规划或简化需求。")]}

    full_plan = kept + new_part
    for i, act in enumerate(full_plan):
        act["order"] = i + 1

    logger.info(f"部分重规划完成 | total_items={len(full_plan)}")

    return {
        "plan": full_plan,
        "messages": [AIMessage(content=f"✅ 已从第{split_index+1}个活动之后重新规划，共{len(full_plan)}个活动。")],
    }


# ==================== 全量重规划 ====================

async def full_replan(state: AgentState, llm_manager) -> Dict[str, Any]:
    """全量重规划 — 清空方案"""
    cid = state.get("conversation_id", "unknown")
    logger.info(f"全量重规划 | cid={cid} | clearing_plan={len(state.get('plan', []))} items")

    return {
        "plan": [],
        "plan_id": "",
        "query_results": {},
        "intent_type": "planning",
        "messages": [AIMessage(content="🔄 好的，我来为你重新规划整个方案...")],
    }


# ==================== 辅助函数 ====================

async def _llm_find_target(plan: List[Dict], user_input: str, llm_manager) -> Optional[int]:
    """LLM 兜底：识别用户想要替换的活动"""
    plan_summary = "\n".join(
        f"{i}. [{a.get('activity_type', '?')}] {a.get('name', '?')} "
        f"({a.get('time_slot', {}).get('start', '')} - {a.get('time_slot', {}).get('end', '')})"
        for i, a in enumerate(plan)
    )
    prompt = (
        f"用户说：\"{user_input}\"\n\n"
        f"当前规划方案中的活动列表：\n{plan_summary}\n\n"
        f"请判断用户想替换的是哪一个活动。只返回活动序号（一个整数，从0开始），不要其他内容。"
        f"如果无法判断，返回 -1。"
    )
    try:
        response = await llm_manager.invoke([
            SystemMessage(content="你是一个精准的活动匹配助手。只返回一个整数。"),
            HumanMessage(content=prompt),
        ])
        idx = int(response.strip())
        if 0 <= idx < len(plan):
            logger.info(f"LLM识别目标活动成功 | idx={idx} | name={plan[idx].get('name')}")
            return idx
    except Exception as e:
        logger.warning(f"LLM识别目标活动失败 | error={e}")
    return None


def _find_activity_by_name(plan: List[Dict], user_input: str) -> Optional[int]:
    """从 plan 中按名称模糊匹配，找到用户提到的活动索引"""
    if not plan or not user_input:
        return None
    # 去掉常见的前缀/后缀分隔词，提取核心关键词
    cleaned = user_input
    for word in ["重新规划", "后面", "之后", "往后", "从", "开始", "规划", "重新", "的"]:
        cleaned = cleaned.replace(word, " ")
    # 提取所有2字以上的候选词
    candidates = [w.strip() for w in cleaned.split() if len(w.strip()) >= 2]
    for candidate in candidates:
        for i, a in enumerate(plan):
            if candidate in a.get("name", ""):
                logger.info(f"名称匹配: '{candidate}' -> plan[{i}] {a.get('name')}")
                return i
    return None


def _find_target_activity(plan: List[Dict], replan_target: Dict) -> Optional[int]:
    """定位目标活动（跳过 transport 节点）"""
    target_index = replan_target.get("target_index")
    target_name = replan_target.get("target_name")
    target_desc = replan_target.get("target_description", "")

    # 直接索引
    if target_index is not None and 0 <= target_index < len(plan):
        return target_index

    # 按名称搜索（跳过 transport）
    if target_name:
        for i, activity in enumerate(plan):
            if activity.get("activity_type") == "transport":
                continue
            if target_name in activity.get("name", ""):
                return i

    # 类型搜索（跳过 transport）
    type_map = {"餐厅": "restaurant", "饭店": "restaurant", "景点": "attraction", "活动": "activity"}
    for keyword, act_type in type_map.items():
        if keyword in target_desc:
            for i, a in enumerate(plan):
                if a.get("activity_type") == "transport":
                    continue
                if a.get("activity_type") == act_type:
                    return i
    return None


def _calculate_constraints(plan: List[Dict], idx: int) -> Dict:
    constraints = {
        "max_duration_hours": plan[idx].get("duration_hours", 2),
        "time_slot": plan[idx].get("time_slot", {}),
        "activity_type": plan[idx].get("activity_type", ""),
        "prev_location": None,
        "next_location": None,
        "available_minutes": None,
    }
    if idx > 0:
        constraints["prev_location"] = plan[idx - 1].get("location", {})
        constraints["prev_end_time"] = plan[idx - 1].get("time_slot", {}).get("end", "")
    if idx < len(plan) - 1:
        constraints["next_location"] = plan[idx + 1].get("location", {})
        constraints["next_start_time"] = plan[idx + 1].get("time_slot", {}).get("start", "")

    pe = constraints.get("prev_end_time")
    ns = constraints.get("next_start_time")
    if pe and ns:
        try:
            ph, pm = map(int, pe.split(":"))
            nh, nm = map(int, ns.split(":"))
            constraints["available_minutes"] = (nh * 60 + nm) - (ph * 60 + pm)
        except (ValueError, AttributeError):
            pass
    return constraints


def _query_alternatives(target: Dict, constraints: Dict, existing: Dict) -> List[Dict]:
    loc = target.get("location", {})
    lat = loc.get("lat", 39.9042)
    lng = loc.get("lng", 116.4074)
    act_type = target.get("activity_type", "")

    query_map = {
        "restaurant": ("query_nearby_restaurants", {}),
        "attraction": ("query_nearby_attractions", {}),
        "activity": ("query_nearby_activities", {}),
        "cafe": ("query_nearby_cafes", {}),
    }
    func_name, _ = query_map.get(act_type, ("query_nearby_attractions", {}))
    func = getattr(query_tools, func_name, None)
    if not func:
        return []

    result = func(lat=lat, lng=lng, radius=5000)
    alternatives = result.get("data", [])

    target_name = target.get("name", "")
    target_id = target.get("item_id", "")
    alternatives = [a for a in alternatives if a.get("name") != target_name and a.get("id") != target_id]

    # 约束过滤
    if constraints.get("prev_location") and constraints.get("next_location"):
        prev_loc = constraints["prev_location"]
        next_loc = constraints["next_location"]
        available = constraints.get("available_minutes")
        filtered = []
        for alt in alternatives:
            alt_loc = alt.get("location", {})
            if not alt_loc:
                continue
            from_prev = calculate_route(
                prev_loc.get("lat", 0), prev_loc.get("lng", 0),
                alt_loc.get("lat", 0), alt_loc.get("lng", 0),
            )
            to_next = calculate_route(
                alt_loc.get("lat", 0), alt_loc.get("lng", 0),
                next_loc.get("lat", 0), next_loc.get("lng", 0),
            )
            total = from_prev["duration_minutes"] + to_next["duration_minutes"]
            if available:
                alt_dur = alt.get("duration_hours", alt.get("visit_duration_hours", 1))
                alt_dur_min = (alt_dur * 60) if isinstance(alt_dur, (int, float)) else 60
                if total + alt_dur_min <= available:
                    filtered.append(alt)
            else:
                filtered.append(alt)
        if filtered:
            alternatives = filtered

    return alternatives[:5]


def _select_best_alternative(alternatives: List[Dict], target: Dict, constraints: Dict) -> Dict:
    if not alternatives:
        return {}
    def score(a):
        s = 0
        r = a.get("rating", 0)
        if isinstance(r, (int, float)):
            s += r * 10
        d = a.get("distance", 9999)
        if isinstance(d, (int, float)):
            s -= d / 1000
        return s
    scored = [(score(a), a) for a in alternatives]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _build_replacement_activity(original: Dict, alternative: Dict, constraints: Dict) -> Dict:
    loc = alternative.get("location", {})
    dur = alternative.get("duration_hours", alternative.get("visit_duration_hours", 1))
    return {
        "order": original.get("order"),
        "time_slot": original.get("time_slot"),
        "activity_type": original.get("activity_type"),
        "name": alternative.get("name", "未知"),
        "item_id": alternative.get("id", ""),
        "location": {"lat": loc.get("lat", 0), "lng": loc.get("lng", 0), "address": alternative.get("address", "")},
        "duration_hours": dur if isinstance(dur, (int, float)) else 1,
        "details": {
            "rating": alternative.get("rating", ""),
            "price": alternative.get("price", alternative.get("price_per_person", "")),
            "tags": alternative.get("tags", []),
            "description": f"替代「{original.get('name')}」",
        },
        "transport_from_prev": original.get("transport_from_prev"),
        "pre_book": {"need": alternative.get("need_ticket", alternative.get("need_booking", False))},
        "delivery_sync": None,
        "notes": f"替代「{original.get('name')}」",
    }


def _recalculate_affected_transport(plan: List[Dict], idx: int) -> List[Dict]:
    for i in [idx, idx + 1]:
        if i <= 0 or i >= len(plan):
            continue
        prev_loc = plan[i - 1].get("location", {})
        curr_loc = plan[i].get("location", {})
        if prev_loc and curr_loc:
            try:
                route = calculate_route(
                    prev_loc.get("lat", 0), prev_loc.get("lng", 0),
                    curr_loc.get("lat", 0), curr_loc.get("lng", 0),
                )
                plan[i]["transport_from_prev"] = {
                    "mode": route["mode"], "mode_label": route["mode_label"],
                    "mode_icon": route["mode_icon"], "duration_min": route["duration_minutes"],
                    "distance_m": route["distance_m"],
                }
            except Exception:
                pass
    return plan


def _no_plan_response():
    return {"messages": [AIMessage(content="当前还没有规划方案，请先告诉我你的出行需求。")]}


def _not_found_response(target_desc: str):
    return {"messages": [AIMessage(content=f"未找到「{target_desc}」。请用序号（如\"换掉第一个\"）或名称来指定。")]}


def _no_alternatives_response(name: str):
    return {"messages": [AIMessage(content=f"附近没有找到「{name}」的合适替代，请尝试扩大范围或换一种类型。")]}
