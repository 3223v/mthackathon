"""Agent 核心模块 - 基于 LangGraph 构建活动规划 Agent

本模块实现 Agent 的状态图定义、各节点逻辑、路由条件，
以及对外暴露的 Agent 类供 CLI 调用。
"""
import json
import os
from typing import Literal
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END, START

from agent.state import AgentState
from agent.preferences import (
    load_preferences, save_preferences, get_scenario_from_preferences,
    format_preferences_summary, update_preference, add_companion, add_note
)
from tools.query import query_attractions, query_restaurants, query_activities, query_cakes, query_flowers
from tools.book import book_restaurant, book_ticket, book_activity, order_cake, order_flower
from config import get_llm_config, get_prompt

# Skill 文件所在目录
SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")


# ==================== 工具函数 ====================

def _load_skill_content(skill_name: str) -> str:
    """读取指定 skill 的 Markdown 定义文件内容

    Args:
        skill_name: skill 目录名，如 "Parent-ChildTravelPlanning"

    Returns:
        skill 文件的完整文本内容，文件不存在时返回空字符串
    """
    skill_path = os.path.join(SKILLS_DIR, skill_name, f"{skill_name}.md")
    if os.path.exists(skill_path):
        with open(skill_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _get_llm():
    """根据配置创建 ChatOpenAI 实例

    支持任何兼容 OpenAI 格式的 API（OpenAI、DeepSeek、Qwen 等），
    配置从 config/llm_config.json 读取，API Key 从 .env 读取。
    """
    config = get_llm_config()
    return ChatOpenAI(
        model=config["model"],
        base_url=config["base_url"],
        api_key=config["api_key"],
        temperature=config["temperature"]
    )


def _parse_llm_json(response_text: str, fallback: dict) -> dict:
    """安全解析 LLM 返回的 JSON 字符串

    LLM 可能返回纯 JSON，也可能包裹在 ```json ... ``` 代码块中。
    解析失败时返回 fallback 默认值，保证流程不中断。

    Args:
        response_text: LLM 原始返回文本
        fallback: 解析失败时的兜底值

    Returns:
        解析后的字典
    """
    content = response_text
    # 尝试提取 ```json ... ``` 代码块
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    try:
        return json.loads(content.strip())
    except (json.JSONDecodeError, IndexError):
        return fallback


def scenario_tag(scenario: str) -> str:
    """将英文场景标识转为中文标签，用于查询过滤

    family → 亲子, friends → 朋友, couple → 情侣, solo → 朋友
    """
    return {"family": "亲子", "friends": "朋友", "couple": "情侣", "solo": "朋友"}.get(scenario, "朋友")


# ==================== LangGraph 节点函数 ====================

def analyze_input(state: AgentState) -> AgentState:
    """节点：意图分析

    调用 LLM 分析用户输入，提取以下信息：
    - intent: 用户意图（规划/偏好/确认/打断等）
    - scenario: 场景类型（亲子/朋友/情侣/个人）
    - extracted_info: 从输入中提取的结构化信息（人数、年龄、预算等）
    - defaults_applied: 应用的智能默认值

    【核心变更】不再设置 missing_info，永远不反问，
    而是使用智能默认值填充缺失信息。
    """
    llm = _get_llm()
    prefs = load_preferences()
    prefs_summary = format_preferences_summary(prefs)
    user_input = state["user_input"]
    messages_history = state.get("messages", [])

    context = ""
    if messages_history:
        context = "\n".join([
            f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {m.content}"
            for m in messages_history[-6:]
        ])

    prompt = get_prompt("analyze_input")
    system_prompt = prompt["system"].format(
        prefs_summary=prefs_summary,
        context=context
    )

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ])

    analysis = _parse_llm_json(response.content, fallback={
        "intent": "plan",
        "scenario": "friends",
        "extracted_info": {},
        "defaults_applied": {
            "group_size": "智能默认：4人",
            "budget": "智能默认：100-150元/人",
            "location": "智能默认：市区内"
        }
    })

    return {
        **state,
        "analysis": analysis,
        "scenario": analysis.get("scenario", "friends"),
        "defaults_applied": analysis.get("defaults_applied", {}),
        "step": "analyze",
        "step_count": state.get("step_count", 0) + 1
    }


def select_skill(state: AgentState) -> AgentState:
    """节点：选择 Skill

    根据场景类型自动匹配对应的 Skill 定义：
    - family → Parent-ChildTravelPlanning（亲子出行）
    - friends → FriendsOuting（朋友聚会）
    - couple/solo → PersonalTravelPlanning（情侣/个人）

    Skill 定义文件为 Markdown 格式，位于 skills/ 目录下。
    """
    scenario = state["scenario"]

    # 场景 → Skill 目录名的映射
    skill_map = {
        "family": "Parent-ChildTravelPlanning",
        "friends": "FriendsOuting",
        "couple": "PersonalTravelPlanning",
        "solo": "PersonalTravelPlanning"
    }

    skill_name = skill_map.get(scenario, "FriendsOuting")
    skill_content = _load_skill_content(skill_name)

    return {
        **state,
        "skill_used": skill_name,
        "step": "skill_selected",
        "step_count": state.get("step_count", 0) + 1
    }


def generate_plan(state: AgentState) -> AgentState:
    """节点：生成出行方案

    【核心变更】不再等待追问，直接生成完整方案。
    使用智能默认值填充缺失信息。

    综合以下信息由 LLM 生成完整的时间线方案：
    1. 用户输入中提取的信息（人数、年龄、预算等）
    2. 用户历史偏好
    3. 用户打断时加入的新要求
    4. 从 mock 数据查询到的景点/餐厅/活动
    5. 智能默认值（人数、预算、位置等）

    方案输出为结构化 JSON，包含 timeline、费用、额外建议和贴士。
    生成后进入等待确认状态，用户确认后才执行下单。
    """
    llm = _get_llm()
    prefs = load_preferences()
    scenario = state["scenario"]
    analysis = state["analysis"]
    extracted = analysis.get("extracted_info", {})
    defaults = state.get("defaults_applied", {})

    group_size = extracted.get("group_size") or (
        4 if scenario == "friends" else (3 if scenario == "family" else 2)
    )
    child_age = extracted.get("child_age")
    max_distance = extracted.get("location_preference")
    duration = extracted.get("duration_hours") or 5

    tag = scenario_tag(scenario)
    max_dist = prefs.get("max_distance_km")

    attractions = query_attractions(scenario=tag, max_distance=max_dist, child_age=child_age)[:5]
    restaurants = query_restaurants(
        scenario=tag,
        max_distance=max_dist,
        need_kids_friendly=(scenario == "family")
    )[:5]
    activities = query_activities(scenario=tag, max_distance=max_dist, child_age=child_age)[:5]

    interrupt_context = ""
    if state.get("interrupted") and state.get("new_info"):
        interrupt_context = f"\n\n用户额外要求（请务必考虑）：{state['new_info']}"

    special_reqs = extracted.get("special_requirements", [])
    if prefs.get("dietary_restrictions"):
        special_reqs.extend(prefs["dietary_restrictions"])

    child_age_line = f'孩子年龄：{child_age}岁' if child_age else ''
    family_rule = '优先选择有儿童设施的场所' if scenario == 'family' else ''
    friends_rule = '活动要适合多人参与' if scenario == 'friends' else ''

    defaults_line = f"\n智能默认值：\n- 人数：{defaults.get('group_size', '默认4人')}\n- 预算：{defaults.get('budget', '默认100-150元/人')}\n- 位置：{defaults.get('location', '默认市区内')}"

    prompt = get_prompt("generate_plan")
    system_prompt = prompt["system"].format(
        duration=duration,
        scenario=scenario,
        group_size=group_size,
        child_age_line=child_age_line,
        prefs_summary=format_preferences_summary(prefs),
        special_reqs=json.dumps(special_reqs, ensure_ascii=False),
        interrupt_context=interrupt_context,
        defaults_applied=defaults_line,
        attractions_json=json.dumps([{
            'id': a['id'], 'name': a['name'], 'type': a['type'],
            'rating': a['rating'], 'price': a['ticket_price'],
            'distance': a['distance_km'], 'duration_h': a['duration_hours'],
            'desc': a['description']
        } for a in attractions], ensure_ascii=False, indent=2),
        restaurants_json=json.dumps([{
            'id': r['id'], 'name': r['name'], 'cuisine': r['cuisine'],
            'rating': r['rating'], 'price_pp': r['price_per_person'],
            'distance': r['distance_km'], 'wait': r['wait_time_minutes'],
            'seats': r['available_seats'], 'kids_chair': r['has_kids_chair'],
            'desc': r['description']
        } for r in restaurants], ensure_ascii=False, indent=2),
        activities_json=json.dumps([{
            'id': a['id'], 'name': a['name'], 'type': a['type'],
            'rating': a['rating'], 'price_pp': a['price_per_person'],
            'distance': a['distance_km'], 'duration_min': a['duration_minutes'],
            'desc': a['description']
        } for a in activities], ensure_ascii=False, indent=2),
        family_rule=family_rule,
        friends_rule=friends_rule
    )

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="请生成完整方案")
    ])

    plan = _parse_llm_json(response.content, fallback={
        "title": "活动方案",
        "time_period": "evening",
        "timeline": [],
        "total_cost": 0,
        "cost_per_person": 0,
        "extra_suggestions": [],
        "tips": ["请查看方案详情"]
    })

    return {
        **state,
        "plan": plan,
        "step": "plan_generated",
        "step_count": state.get("step_count", 0) + 1,
        "needs_confirmation": True,
        "interrupted": False,
        "new_info": ""
    }


def execute_plan(state: AgentState) -> AgentState:
    """节点：执行方案

    用户确认方案后，自动遍历 timeline 中的每一项并调用对应的 booking 工具：
    - activity 类型 → book_activity()（电影则额外调用 book_movie()）
    - meal 类型 → book_restaurant()
    - extra_suggestions 中的蛋糕/鲜花 → order_cake() / order_flower()

    所有订单记录持久化到 data/orders.json。
    """
    plan = state["plan"]
    scenario = state["scenario"]
    analysis = state["analysis"]
    extracted = analysis.get("extracted_info", {})
    group_size = extracted.get("group_size") or (
        3 if scenario == "family" else (4 if scenario == "friends" else 2)
    )
    child_age = extracted.get("child_age")
    today = datetime.now().strftime("%Y-%m-%d")
    results = []

    # 遍历方案时间线，逐项下单
    for item in plan.get("timeline", []):
        item_type = item.get("type")
        item_id = item.get("id", "")
        item_name = item.get("name", "")
        item_time = item.get("time", "")

        if item_type == "activity":
            all_activities = query_activities()
            act = next((a for a in all_activities if a["id"] == item_id), None)
            if act:
                # 预约活动
                result = book_activity(
                    activity_id=item_id,
                    activity_name=item_name,
                    time=item_time,
                    participants=group_size,
                    date=today
                )
                results.append({"type": "活动预约", "name": item_name, "order": result})

                # 电影类型额外生成电影票订单
                if act["type"] == "电影":
                    from tools.book import book_movie
                    result = book_movie(
                        movie_name=item_name,
                        cinema=act.get("address", ""),
                        showtime=item_time,
                        seat_count=group_size,
                        date=today
                    )
                    results.append({"type": "电影票", "name": item_name, "order": result})

        elif item_type == "meal":
            all_restaurants = query_restaurants()
            rest = next((r for r in all_restaurants if r["id"] == item_id), None)
            if rest:
                # 预约餐厅，亲子场景自动加儿童椅
                result = book_restaurant(
                    restaurant_id=item_id,
                    restaurant_name=item_name,
                    date=today,
                    time=item_time,
                    party_size=group_size,
                    need_kids_chair=(scenario == "family"),
                    special_requests=f"{scenario}出行" + (
                        f"，有{child_age}岁孩子" if child_age else ""
                    )
                )
                results.append({"type": "餐厅预约", "name": item_name, "order": result})

    # 处理额外建议（蛋糕/鲜花配送到餐厅）
    for extra in plan.get("extra_suggestions", []):
        meal_items = [i for i in plan.get("timeline", []) if i.get("type") == "meal"]
        delivery_addr = meal_items[0].get("address", "待定") if meal_items else "待定"
        delivery_time = meal_items[0].get("time", "18:00") if meal_items else "18:00"

        if extra.get("type") == "cake":
            cakes = query_cakes(scenario=scenario_tag(scenario))
            if cakes:
                result = order_cake(
                    cake_name=cakes[0]["name"],
                    delivery_address=delivery_addr,
                    delivery_time=delivery_time,
                    message_card="祝大家玩得开心！"
                )
                results.append({"type": "蛋糕配送", "name": cakes[0]["name"], "order": result})

        elif extra.get("type") == "flower":
            flowers = query_flowers(scenario=scenario_tag(scenario))
            if flowers:
                result = order_flower(
                    flower_name=flowers[0]["name"],
                    delivery_address=delivery_addr,
                    delivery_time=delivery_time,
                    message_card="祝大家玩得开心！"
                )
                results.append({"type": "鲜花配送", "name": flowers[0]["name"], "order": result})

    return {
        **state,
        "execution_results": results,
        "step": "executed",
        "step_count": state.get("step_count", 0) + 1
    }


def format_result(state: AgentState) -> AgentState:
    """节点：格式化最终输出

    将方案和执行结果格式化为用户友好的文本展示，
    包含时间线、费用汇总、已完成的订单号等信息。
    """
    plan = state["plan"]
    results = state["execution_results"]
    scenario = state["scenario"]

    scenario_emoji = {"family": "👨‍👩‍👧", "friends": "👥", "couple": "💑", "solo": "🧑"}
    emoji = scenario_emoji.get(scenario, "📋")

    lines = [f"\n{'='*50}"]
    lines.append(f"{emoji} {plan.get('title', '出行方案')}")
    lines.append(f"{'='*50}\n")

    # 时间线
    for item in plan.get("timeline", []):
        icon = "🍽️" if item["type"] == "meal" else "🎯"
        lines.append(f"🕐 {item['time']}-{item.get('end_time', '')} | {icon} {item['name']}")
        lines.append(f"   📍 {item.get('address', '')}")
        if item.get("description"):
            lines.append(f"   📝 {item['description']}")
        if item.get("reasons"):
            lines.append(f"   💡 {item['reasons']}")
        if item.get("cost"):
            lines.append(f"   💰 预计费用: ¥{item['cost']}")
        lines.append("")

    # 费用汇总
    lines.append(f"{'─'*50}")
    lines.append(f"💰 总费用: ¥{plan.get('total_cost', 0)}")
    lines.append(f"💰 人均: ¥{plan.get('cost_per_person', 0)}")
    lines.append("")

    # 额外建议
    if plan.get("extra_suggestions"):
        lines.append("🎁 额外惊喜建议：")
        for extra in plan["extra_suggestions"]:
            lines.append(f"   - {extra.get('name', '')}: {extra.get('reason', '')}")
        lines.append("")

    # 执行结果（订单号列表）
    lines.append(f"{'─'*50}")
    lines.append("✅ 已完成操作：")
    for r in results:
        order = r.get("order", {})
        lines.append(f"   - [{r['type']}] {r['name']} → 订单号: {order.get('order_id', 'N/A')} ✅")
    lines.append("")

    # 小贴士
    if plan.get("tips"):
        lines.append("📌 小贴士：")
        for tip in plan["tips"]:
            lines.append(f"   - {tip}")

    lines.append(f"\n{'='*50}")
    result_text = "\n".join(lines)

    return {
        **state,
        "step": "done",
        "step_count": state.get("step_count", 0) + 1,
        "messages": state.get("messages", []) + [AIMessage(content=result_text)]
    }


def handle_interrupt(state: AgentState) -> AgentState:
    """节点：处理用户打断

    当用户在方案讨论中加入新信息（如"对了，我老婆在减肥"）时触发。
    调用 LLM 分析新信息对已有方案的影响程度（low/medium/high），
    并更新分析结果，后续会重新生成方案。

    同时自动提取打断信息中的偏好内容（如减肥→记录饮食限制）。
    """
    llm = _get_llm()
    new_info = state.get("new_info", "")
    prev_analysis = state.get("analysis", {})
    prev_plan = state.get("plan", {})

    prompt = get_prompt("handle_interrupt")
    system_prompt = prompt["system"].format(
        prev_analysis=json.dumps(prev_analysis, ensure_ascii=False),
        prev_plan_summary=json.dumps(
            {k: v for k, v in prev_plan.items() if k != 'timeline'},
            ensure_ascii=False
        ),
        new_info=new_info
    )

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=new_info)
    ])

    # 解析打断分析结果
    interrupt_analysis = _parse_llm_json(response.content, fallback={
        "updated_extracted_info": prev_analysis.get("extracted_info", {}),
        "updated_missing_info": [],
        "impact": "medium",
        "suggestion": "已收到新信息，正在调整方案"
    })

    # 合并更新分析结果
    updated_analysis = {**prev_analysis}
    if interrupt_analysis.get("updated_extracted_info"):
        updated_analysis.setdefault("extracted_info", {}).update(
            interrupt_analysis["updated_extracted_info"]
        )

    # 从打断信息中提取偏好（如"减肥"→饮食清淡）
    _update_prefs_from_info(new_info)

    return {
        **state,
        "analysis": updated_analysis,
        "missing_info": interrupt_analysis.get("updated_missing_info", []),
        "interrupted": True,
        "step": "interrupt_handled",
        "step_count": state.get("step_count", 0) + 1
    }


def _update_prefs_from_info(info: str):
    """从用户打断信息中自动提取并更新偏好

    当前支持识别：
    - 减肥/瘦身/减脂/控制饮食 → 添加饮食限制备注
    """
    prefs = load_preferences()

    if any(w in info for w in ["减肥", "瘦身", "减脂", "控制饮食"]):
        notes = prefs.get("notes", [])
        if "在减肥，饮食要清淡健康" not in notes:
            notes.append("在减肥，饮食要清淡健康")
            prefs["notes"] = notes
            save_preferences(prefs)


def handle_preference(state: AgentState) -> AgentState:
    """节点：处理用户偏好设置

    调用 LLM 从用户输入中提取结构化偏好信息（喜欢的菜系、不吃的、预算等），
    并持久化到 data/preferences.json。
    """
    llm = _get_llm()
    user_input = state["user_input"]

    prompt = get_prompt("handle_preference")
    system_prompt = prompt["system"].format(user_input=user_input)

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ])

    pref_result = _parse_llm_json(response.content, fallback={
        "action": "set",
        "preferences": {},
        "message": "好的，已收到你的偏好设置"
    })

    # 执行偏好更新
    if pref_result["action"] in ("set", "add"):
        new_prefs = pref_result.get("preferences", {})
        prefs = load_preferences()
        for key, value in new_prefs.items():
            if value is not None:
                if key == "companions":
                    for comp in value:
                        if comp.get("name"):
                            add_companion(comp["name"], comp.get("age"), comp.get("relation"))
                elif key == "notes":
                    for note in value:
                        add_note(note)
                elif isinstance(value, list):
                    existing = prefs.get(key, [])
                    existing.extend([v for v in value if v not in existing])
                    prefs[key] = existing
                else:
                    prefs[key] = value
        save_preferences(prefs)

    # 返回确认消息 + 当前偏好摘要
    message = pref_result.get("message", "偏好已更新")
    prefs = load_preferences()
    message += f"\n\n当前偏好：\n{format_preferences_summary(prefs)}"

    return {
        **state,
        "step": "preference_set",
        "step_count": state.get("step_count", 0) + 1,
        "messages": state.get("messages", []) + [AIMessage(content=message)]
    }


# ==================== 路由函数 ====================
# 路由函数是条件边的判断逻辑，决定下一步走向哪个节点

def route_after_analyze(state: AgentState) -> str:
    """分析节点后的路由分支

    根据 intent 类型决定下一步：
    - preference → handle_preference（用户设置偏好）
    - confirm → execute_plan（用户确认执行方案）
    - interrupt → handle_interrupt（用户打断加入新信息）
    - 其他 → select_skill（选择 skill 进入规划）

    【核心变更】永远不追问，直接进入规划流程。
    """
    analysis = state["analysis"]
    intent = analysis.get("intent", "plan")

    if intent == "preference":
        return "handle_preference"
    elif intent == "confirm":
        return "execute_plan"
    elif intent == "interrupt":
        return "handle_interrupt"
    else:
        return "select_skill"


def route_after_skill(state: AgentState) -> str:
    """Skill 选择后的路由：直接生成方案，不再追问"""
    return "generate_plan"


def route_after_interrupt(state: AgentState) -> str:
    """打断处理后的路由：直接重新生成方案"""
    return "generate_plan"


# ==================== 构建 LangGraph 状态图 ====================

def build_graph() -> StateGraph:
    """构建 Agent 的 LangGraph 状态图

    节点：
        analyze_input    - 意图分析
        select_skill     - 选择 Skill
        generate_plan    - 生成方案
        execute_plan     - 执行下单
        format_result    - 格式化输出
        handle_interrupt - 处理打断
        handle_preference- 处理偏好

    【核心变更】移除 gather_info 节点，永远不追问。

    数据流：
        START → analyze_input → [条件路由]
            ├→ handle_preference → END
            ├→ execute_plan → format_result → END
            ├→ handle_interrupt → generate_plan → wait_confirmation → END
            └→ select_skill → generate_plan → wait_confirmation → END
    """
    graph = StateGraph(AgentState)

    graph.add_node("analyze_input", analyze_input)
    graph.add_node("select_skill", select_skill)
    graph.add_node("generate_plan", generate_plan)
    graph.add_node("execute_plan", execute_plan)
    graph.add_node("format_result", format_result)
    graph.add_node("handle_interrupt", handle_interrupt)
    graph.add_node("handle_preference", handle_preference)
    graph.add_node("wait_confirmation", lambda state: state)

    graph.add_edge(START, "analyze_input")

    graph.add_conditional_edges("analyze_input", route_after_analyze, {
        "handle_preference": "handle_preference",
        "execute_plan": "execute_plan",
        "handle_interrupt": "handle_interrupt",
        "select_skill": "select_skill"
    })

    graph.add_edge("select_skill", "generate_plan")

    graph.add_edge("generate_plan", "wait_confirmation")
    graph.add_edge("wait_confirmation", END)

    graph.add_edge("execute_plan", "format_result")
    graph.add_edge("format_result", END)

    graph.add_conditional_edges("handle_interrupt", route_after_interrupt, {
        "generate_plan": "generate_plan"
    })

    graph.add_edge("handle_preference", END)

    return graph


# ==================== 对外接口 ====================

class Agent:
    """本地活动规划 Agent

    对外暴露的核心类，封装了 LangGraph 状态图的编译和多轮对话管理。
    CLI 通过 Agent.chat() 方法交互，Agent 维护跨轮次的状态。

    典型流程：
        agent = Agent()
        response = agent.chat("今天下午带5岁的孩子出去玩")  # 分析+生成方案
        response = agent.chat("对了，我老婆在减肥")           # 打断，重新调整
        response = agent.chat("确认")                         # 执行下单
    """

    def __init__(self, config_name: str = "primary"):
        """初始化 Agent

        Args:
            config_name: LLM 配置名称，对应 config/llm_config.json 中的 name
        """
        self.config_name = config_name
        graph = build_graph()
        self.app = graph.compile()
        self.state = self._init_state()

    def _init_state(self) -> AgentState:
        """创建初始状态"""
        return {
            "messages": [],
            "user_input": "",
            "user_preferences": load_preferences(),
            "scenario": "",
            "skill_used": "",
            "analysis": {},
            "defaults_applied": {},
            "plan": {},
            "execution_results": [],
            "step": "init",
            "step_count": 0,
            "needs_confirmation": False,
            "interrupted": False,
            "new_info": ""
        }

    def chat(self, user_input: str) -> str:
        """处理用户输入，返回 Agent 回复

        内部根据当前状态判断行为：
        - 普通输入 → 走 LangGraph 正常流程
        - 等待确认时收到确认词 → 触发执行节点
        - 等待确认时收到非确认词 → 视为打断，重新调整方案

        Args:
            user_input: 用户消息文本

        Returns:
            Agent 的回复文本
        """
        prev_step = self.state.get("step", "init")
        prev_plan = self.state.get("plan", {})

        # 情况 1：等待确认阶段收到确认 → 执行下单
        if prev_step == "wait_confirmation" and self._is_confirmation(user_input):
            self.state["user_input"] = user_input
            self.state["analysis"] = {"intent": "confirm"}
            result = self.app.invoke(self.state)
            self.state = result
            last_msg = result["messages"][-1] if result["messages"] else None
            return last_msg.content if last_msg else "方案已执行完成！"

        # 情况 2：等待确认阶段收到新信息 → 视为打断
        if prev_step == "wait_confirmation" and prev_plan and not self._is_confirmation(user_input):
            self.state["user_input"] = user_input
            self.state["new_info"] = user_input
            self.state["analysis"] = {"intent": "interrupt"}
            # 先处理打断（分析影响）
            self.state = handle_interrupt(self.state)
            # 再重新生成方案
            self.state = generate_plan(self.state)
            return self._format_plan_for_user()

        # 情况 3：正常输入 → 走完整的 LangGraph 流程
        self.state["user_input"] = user_input
        result = self.app.invoke(self.state)
        self.state = result

        last_msg = result["messages"][-1] if result["messages"] else None
        if last_msg:
            return last_msg.content

        # 如果生成了方案但需要确认，展示方案
        if result.get("step") in ("plan_generated", "wait_confirmation") and result.get("plan"):
            return self._format_plan_for_user()

        return "请告诉我更多信息，我来帮你规划。"

    def _is_confirmation(self, text: str) -> bool:
        """判断用户输入是否为确认/同意"""
        confirm_words = [
            "好的", "行", "可以", "确认", "就这么定", "同意",
            "ok", "OK", "没问题", "就这么办", "执行", "下单", "安排", "搞定了"
        ]
        return any(w in text for w in confirm_words)

    def _format_plan_for_user(self) -> str:
        """将方案格式化为友好的展示文本，等待用户确认"""
        plan = self.state.get("plan", {})
        defaults = self.state.get("defaults_applied", {})
        if not plan:
            return "方案生成中..."

        time_period_map = {
            "morning": "🌅 上午",
            "afternoon": "☀️ 下午",
            "evening": "🌙 晚间",
            "full_day": "📅 全天"
        }
        time_period = time_period_map.get(plan.get("time_period", "evening"), "📅 活动")

        lines = [f"\n📋 {plan.get('title', '出行方案')}"]
        lines.append(f"{time_period}")
        lines.append("=" * 50)

        if defaults:
            defaults_info = []
            if defaults.get('group_size'):
                defaults_info.append(f"人数：{defaults['group_size']}")
            if defaults.get('budget'):
                defaults_info.append(f"预算：{defaults['budget']}")
            if defaults.get('location'):
                defaults_info.append(f"位置：{defaults['location']}")
            if defaults_info:
                lines.append(f"📌 基于您的偏好和智能默认设置生成")
                lines.append(f"   {' | '.join(defaults_info)}")
                lines.append("")

        for item in plan.get("timeline", []):
            icon = "🍽️" if item["type"] == "meal" else "🎯"
            lines.append(f"\n🕐 {item['time']}-{item.get('end_time', '')} | {icon} {item['name']}")
            lines.append(f"   📍 {item.get('address', '')}")
            if item.get("description"):
                lines.append(f"   📝 {item['description']}")
            if item.get("reasons"):
                lines.append(f"   💡 {item['reasons']}")
            if item.get("cost_per_person"):
                lines.append(f"   💰 人均: ¥{item['cost_per_person']}")

        lines.append(f"\n{'─'*50}")
        lines.append(f"💰 总费用: ¥{plan.get('total_cost', 0)} | 人均: ¥{plan.get('cost_per_person', 0)}")

        if plan.get("extra_suggestions"):
            lines.append("\n🎁 额外惊喜建议：")
            for extra in plan["extra_suggestions"]:
                lines.append(f"   - {extra.get('name', '')}: {extra.get('reason', '')}")

        if plan.get("tips"):
            lines.append("\n📌 小贴士：")
            for tip in plan["tips"]:
                lines.append(f"   - {tip}")

        lines.append(f"\n{'─'*50}")
        lines.append("👆 对这个方案满意吗？回复「确认」执行下单，或告诉我需要调整的地方。")

        return "\n".join(lines)

    def get_preferences(self) -> str:
        """获取当前用户偏好的格式化摘要"""
        prefs = load_preferences()
        return format_preferences_summary(prefs)

    def reset(self):
        """重置对话状态，开始新一轮规划"""
        self.state = self._init_state()
