"""
规划生成节点（核心节点）v2

新增：
- 真实 LLM token 级流式输出
- 增强日志：记录完整 Prompt 和响应
- 使用 mockfunction.get_user_preferences_for_planning() 注入偏好
"""

import json
import re
import os
import hashlib
from typing import Dict, Any, List, Optional, Callable, Awaitable
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from agent.state import AgentState
from agent.nodes.query import format_data_for_prompt
from core.travel import calculate_route
from mockfunction import get_user_preferences_for_planning
from utils import logger, agent_logger

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../config/prompts.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    prompts = json.load(f)

StreamCallback = Optional[Callable[[str], Awaitable[None]]]


async def generate_plan(
    state: AgentState,
    llm_manager,
    stream_callback: StreamCallback = None,
) -> Dict[str, Any]:
    """
    生成活动规划方案（带流式输出）

    Args:
        state: Agent 状态
        llm_manager: LLM 管理器实例
        stream_callback: 流式回调 async fn(token) -> None
    """
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""
    conversation_id = state.get("conversation_id", "unknown")
    skill_context = state.get("skill_context")
    query_results = state.get("query_results", {})
    context = state.get("context", {})

    # 提取时间约束（硬性条件）
    time_constraint = context.get("time_constraint", {})
    time_constraint_text = ""
    if time_constraint and time_constraint.get("has_constraint"):
        time_constraint_text = f"\n## ⚠️ 硬性时间约束（必须严格遵守，不可改动）\n{time_constraint.get('constraint_text', '')}"
        if time_constraint.get("earliest_start"):
            time_constraint_text += f"\n- 最早开始时间: {time_constraint['earliest_start']}"
        if time_constraint.get("latest_end"):
            time_constraint_text += f"\n- 最晚结束时间: {time_constraint['latest_end']}"

    # 从持久化偏好中获取格式化文本
    preferences_text = get_user_preferences_for_planning()

    logger.info(f"规划开始 | cid={conversation_id} | skill={skill_context.get('id', 'none') if skill_context else 'none'}")

    # 1. System Prompt
    system_prompt = prompts["planning_system_prompt"]
    if skill_context:
        system_prompt += "\n\n## 场景专项指导\n" + _build_scenario_description(skill_context)

    # 2. User Prompt
    available_data = format_data_for_prompt(query_results)
    if not available_data.strip():
        available_data = "（暂无可用数据，请基于常识推荐北京地区热门景点和餐厅）"

    scenario = skill_context.get("name", "通用出行") if skill_context else "通用出行"

    user_prompt = prompts["planning_user_prompt"].format(
        user_request=user_input,
        preferences=preferences_text,
        available_data=available_data,
        scenario_description=f"场景类型: {scenario}",
    )
    # 追加时间硬性约束
    if time_constraint_text:
        user_prompt += time_constraint_text

    # 3. 调用 LLM（流式）
    try:
        response_text = await llm_manager.invoke_with_logging(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            stream_callback=stream_callback,
            log_prefix="Planner",
        )
    except Exception as e:
        logger.error(f"规划生成失败 | cid={conversation_id} | error={str(e)}")
        return {
            "messages": [AIMessage(content=f"抱歉，规划生成失败：{str(e)}")],
            "plan": [],
            "plan_id": "",
        }

    # 4. 解析 JSON
    plan = _parse_plan_json(response_text)
    if not plan:
        logger.warning(f"JSON解析失败，返回原始文本 | cid={conversation_id}")
        return {
            "messages": [AIMessage(content=response_text)],
            "plan": [],
            "plan_id": "",
        }

    # 5. 后处理：插入交通活动 + 补全信息
    plan = _insert_transport_activities(plan)
    plan_id = f"plan_{hashlib.md5(str(plan).encode()).hexdigest()[:8]}"
    display_text = _format_plan_display(plan, plan_id, skill_context)

    logger.info(f"规划完成 | cid={conversation_id} | plan_id={plan_id} | items={len(plan)}")

    return {
        "plan": plan,
        "plan_id": plan_id,
        "messages": [AIMessage(content=display_text)],
    }


def _build_scenario_description(skill: Dict) -> str:
    parts = []
    if skill.get("flow"):
        parts.append(f"### 业务流程\n{skill['flow']}")
    if skill.get("notes"):
        parts.append(f"### 注意事项\n{skill['notes']}")
    if skill.get("output_template"):
        parts.append(f"### 输出风格参考\n{skill['output_template']}")
    return "\n\n".join(parts)


def _parse_plan_json(text: str) -> List[Dict]:
    """从 LLM 输出中解析 plan JSON"""
    code_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    try:
        plan = json.loads(text)
        if isinstance(plan, list):
            return plan
    except json.JSONDecodeError:
        pass

    array_match = re.search(r'\[.*\]', text, re.DOTALL)
    if array_match:
        try:
            plan = json.loads(array_match.group(0))
            if isinstance(plan, list):
                return plan
        except json.JSONDecodeError:
            pass

    logger.warning(f"无法解析 plan JSON | preview={text[:200]}")
    return []


def _insert_transport_activities(plan: List[Dict]) -> List[Dict]:
    """
    在活动之间插入交通活动，将交通提升为一等公民

    输入: [活动A, 活动B, 活动C]
    输出: [活动A, 交通A→B, 活动B, 交通B→C, 活动C]

    每个交通活动包含完整的结构化数据：
    - activity_type: "transport"
    - from_location / to_location
    - mode, duration, distance
    """
    if not plan or len(plan) < 2:
        return plan

    enriched = []
    for i, activity in enumerate(plan):
        # 清理旧的 transport_from_prev 字段
        activity.pop("transport_from_prev", None)

        if i > 0:
            prev_activity = enriched[-1]  # 上一个实际活动
            prev_loc = prev_activity.get("location", {})
            curr_loc = activity.get("location", {})

            if prev_loc and curr_loc:
                try:
                    route = calculate_route(
                        origin_lat=prev_loc.get("lat", 0),
                        origin_lng=prev_loc.get("lng", 0),
                        dest_lat=curr_loc.get("lat", 0),
                        dest_lng=curr_loc.get("lng", 0),
                    )
                    # 交通活动
                    transport = {
                        "order": len(enriched) + 1,
                        "time_slot": {
                            "start": prev_activity.get("time_slot", {}).get("end", ""),
                            "end": _add_minutes(prev_activity.get("time_slot", {}).get("end", ""), route["duration_minutes"]),
                        },
                        "activity_type": "transport",
                        "name": f"{route['mode_label']}前往{activity.get('name', '下一站')}",
                        "item_id": f"TRANSPORT_{i}",
                        "from_location": {
                            "lat": prev_loc.get("lat"), "lng": prev_loc.get("lng"),
                            "address": prev_activity.get("location", {}).get("address", ""),
                            "name": prev_activity.get("name", ""),
                        },
                        "to_location": {
                            "lat": curr_loc.get("lat"), "lng": curr_loc.get("lng"),
                            "address": activity.get("location", {}).get("address", ""),
                            "name": activity.get("name", ""),
                        },
                        "duration_minutes": route["duration_minutes"],
                        "distance_m": route["distance_m"],
                        "mode": route["mode"],
                        "mode_label": route["mode_label"],
                        "mode_icon": route["mode_icon"],
                        "details": {
                            "description": f"从「{prev_activity.get('name', '')}」{route['mode_label']}{route['duration_minutes']}分钟（{route['distance_m']:.0f}m）到「{activity.get('name', '')}」",
                        },
                        "pre_book": {"need": False},
                        "delivery_sync": None,
                        "notes": "",
                    }
                    enriched.append(transport)
                except Exception as e:
                    logger.debug(f"交通计算失败 | from={prev_activity.get('name')} to={activity.get('name')} | error={e}")

        enriched.append(activity)

    # 重新编号
    for i, act in enumerate(enriched):
        act["order"] = i + 1

    return enriched


def _add_minutes(time_str: str, minutes: int) -> str:
    """时间字符串加分钟数"""
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        total = h * 60 + m + minutes
        return f"{total // 60:02d}:{total % 60:02d}"
    except (ValueError, IndexError):
        return time_str


def _format_plan_display(plan: List[Dict], plan_id: str, skill_context: Dict = None) -> str:
    """格式化展示文本"""
    if not plan:
        return "未能生成有效的规划方案。"

    skill_name = skill_context.get("name", "出行") if skill_context else "出行"
    emoji = {"family": "👨‍👩‍👧", "friends": "👥", "couple": "💑"}.get(
        skill_context.get("scenario", "") if skill_context else "", "📋"
    )

    lines = [
        f"{emoji} **{skill_name}方案**",
        f"",
        f"方案ID: `{plan_id}`",
        f"",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    total_cost = 0
    type_icons = {
        "attraction": "🎯", "restaurant": "🍽️", "activity": "🎪",
        "cafe": "☕", "free_time": "🕐", "transport": "🚶",
    }

    for activity in plan:
        ts = activity.get("time_slot", {})
        start = ts.get("start", "")
        end = ts.get("end", "")
        name = activity.get("name", "未知")
        act_type = activity.get("activity_type", "")
        details = activity.get("details", {})
        notes = activity.get("notes", "")
        pre_book = activity.get("pre_book")

        # 交通活动紧凑显示
        if act_type == "transport":
            icon = activity.get("mode_icon", "🚶")
            dur = activity.get("duration_minutes", 0)
            dist = activity.get("distance_m", 0)
            lines.append(f"  {icon} **{activity.get('mode_label', '')}** {dur}分钟 ({dist:.0f}m)")
            lines.append(f"     {details.get('description', '')}")
            continue

        icon = type_icons.get(act_type, "📍")
        lines.append(f"**{start} - {end}** | {icon} {name}")

        if details:
            price = details.get("price", "")
            rating = details.get("rating", "")
            if price:
                if isinstance(price, (int, float)):
                    total_cost += price
                lines.append(f"  💰 {price}元" + (f" | ⭐{rating}" if rating else ""))

        if pre_book and isinstance(pre_book, dict) and pre_book.get("need"):
            lines.append(f"  🔖 需预订: {pre_book.get('item', '')}")

        if notes:
            lines.append(f"  💡 {notes}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if total_cost > 0:
        lines.append(f"💰 预计总花费: **{total_cost}元**")
    lines.append("")
    lines.append("💬 操作提示：")
    lines.append("- 替换活动: \"换掉XX\"")
    lines.append("- 全部重来: \"重新规划\"")
    lines.append("- 部分调整: \"从XX之后重新规划\"")
    lines.append("- 一键下单: 发送 执行 到 后台")
    lines.append("")
    lines.append("⚠️ 所有预订需您亲自确认。")

    return "\n".join(lines)
