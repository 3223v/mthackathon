"""
意图分析节点 v3

核心改进：
- 注入对话历史（最近3-5轮）做上下文感知的意图识别
- 关键词分类后，对模糊案例使用 LLM + 历史确认
- 解决"海洋馆也不适合"无法联系到上文"刚替换了海洋馆"的问题
"""

import re
import json
from typing import Dict, Any, Optional, Tuple, List
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from agent.state import AgentState
from core.skill_loader import skill_loader
from utils import logger, agent_logger

# ==================== 关键词 ====================
REPLAN_FULL_KEYWORDS = [
    "全部重来", "全部重新规划", "完全重新规划", "整套方案重来",
    "整体重新规划", "全量重规划", "全部重新设计", "整个重新",
    "彻底重来", "全部都换", "全部重新来过",
    "重新规划一下", "重新规划吧",
]

REPLAN_PARTIAL_KEYWORDS = [
    "之后重新", "后面重新", "往后重新", "后.*重新规划",
    "从.*开始重新", "接着.*重新", "第.*之后重新",
    "重新规划后面", "后面再重新",
]

REPLAN_REPLACE_KEYWORDS = [
    "不喜欢", "换一个", "替换", "不要这个", "换成", "换掉",
    "改成", "改为", "改一下", "换下", "不想去", "不想吃",
    "换一家", "不好吃", "不好玩", "换换", "换个别的",
]

# 配合上下文才算替换的关键词（单独出现可能是通用表达）
CONTEXT_DEPENDENT_REPLACE = [
    "不适合", "不合适", "不行", "不好", "不去了",
    "也不要", "也不适合", "不想要", "去掉", "取消",
]

PREFERENCE_KEYWORDS = [
    "喜欢", "偏好", "爱好", "我的情况", "我家", "我住在",
    "预算", "忌口", "不吃", "过敏", "我叫", "我家有",
]

PLAN_KEYWORDS = [
    "出去玩", "安排", "规划", "推荐", "去哪", "吃什么",
    "约会", "聚会", "一日游", "周末", "出行", "旅游",
    "带我", "帮我", "想去", "逛逛", "走走", "一日",
    "半天", "玩", "逛", "游", "行程",
]

NON_PLAN_KEYWORDS = [
    "天气", "新闻", "股票", "汇率", "计算", "翻译",
    "几点了", "今天几号", "讲个笑话", "写代码", "写文章",
    "你是谁", "你叫什么", "你是什么",
]


def analyze_intent(state: AgentState) -> Dict[str, Any]:
    """分析用户意图（带历史上下文）"""
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    cid = state.get("conversation_id", "unknown")

    if not isinstance(last_message, HumanMessage):
        return {}

    user_input = last_message.content.strip()
    agent_logger.intent_analyzing(cid, user_input)

    # 提取对话历史（最近6条消息，约3轮对话）
    history = _extract_history(messages)
    if history:
        logger.debug(f"注入历史上下文 | cid={cid} | history_rounds={len(history)//2}")
        logger.debug(f"历史摘要: {history[-1][:100] if history else 'none'}")

    # 分类（关键词 + 历史上下文感知）
    intent_type, replan_target = _classify_intent(user_input, state, history)

    skill_context = None
    if intent_type == "planning":
        skill_context = skill_loader.match_skill(user_input)

    agent_logger.intent_analyzed(cid, skill_context["id"] if skill_context else None)
    logger.info(f"意图分析 | cid={cid} | intent={intent_type} | skill={skill_context.get('id', 'none') if skill_context else 'none'}")

    # 提取时间约束
    time_constraint = _extract_time_constraint(user_input)

    return {
        "intent_type": intent_type,
        "skill_context": skill_context,
        "replan_target": replan_target or {},
        "context": {**state.get("context", {}), "time_constraint": time_constraint},
    }


def _extract_history(messages: List[BaseMessage]) -> str:
    """提取最近N条消息作为上下文（格式化为文本）"""
    recent = messages[-6:]  # 最近6条
    lines = []
    for msg in recent[:-1]:  # 排除最后一条（当前输入）
        if isinstance(msg, HumanMessage):
            lines.append(f"用户: {msg.content[:100]}")
        elif isinstance(msg, AIMessage):
            lines.append(f"助手: {msg.content[:150]}")
    return "\n".join(lines) if lines else ""


def _classify_intent(user_input: str, state: AgentState, history: str = "") -> Tuple[str, Optional[Dict]]:
    """分类用户意图（关键词优先 + 历史上下文感知）"""
    has_plan = bool(state.get("plan"))

    # 0. 明确非规划类
    if _is_clearly_non_planning(user_input):
        return "general", None

    if has_plan:
        # 1a. 部分重规划（最优先）
        for kw in REPLAN_PARTIAL_KEYWORDS:
            if re.search(kw, user_input):
                return "replan_partial", {"type": "partial", **_extract_partial_target(user_input, state)}

        # 1b. 替换关键词明确命中
        if any(kw in user_input for kw in REPLAN_REPLACE_KEYWORDS):
            return "replan_replace", {"type": "replace", **_extract_replace_target(user_input, state)}

        # 1c. 上下文依赖的替换词 + 历史中有相关讨论
        if any(kw in user_input for kw in CONTEXT_DEPENDENT_REPLACE):
            if history and _history_mentions_activity(history):
                logger.info(f"历史上下文感知: '{user_input}' → 判定为替换意图（历史中有活动讨论）")
                return "replan_replace", {"type": "replace", **_extract_replace_target(user_input, state)}

        # 1d. 全量重规划
        if any(kw in user_input for kw in REPLAN_FULL_KEYWORDS):
            return "replan_full", {"type": "full"}
        if "重新规划" in user_input and not any(re.search(kw, user_input) for kw in REPLAN_PARTIAL_KEYWORDS):
            return "replan_full", {"type": "full"}

    # 2. 纯偏好设置
    has_pref = any(kw in user_input for kw in PREFERENCE_KEYWORDS)
    has_plan_kw = any(kw in user_input for kw in PLAN_KEYWORDS)
    if has_pref and not has_plan_kw:
        if _is_pure_preference(user_input):
            return "preferences", None

    # 3. 活动规划
    if has_plan_kw:
        return "planning", None

    # 4. 模糊但有历史上下文 → 检查是否与最近规划/替换相关
    if has_plan and history and not has_plan_kw and not has_pref:
        if _history_mentions_activity(history):
            logger.info(f"模糊输入 + 历史中有活动上下文 → 尝试判定为替换意图")
            return "replan_replace", {"type": "replace", **_extract_replace_target(user_input, state)}

    # 5. 有一定长度的输入 → 尝试规划
    if len(user_input) > 10 and not has_pref:
        return "planning", None

    return "general", None


def _history_mentions_activity(history: str) -> bool:
    """检查历史上下文中是否提到了活动/替换相关的内容"""
    activity_signals = [
        "替换", "换成", "改为", "方案", "规划", "建议", "推荐",
        "动物园", "海洋馆", "博物馆", "餐厅", "景点", "活动",
        "火锅", "烤肉", "烤鸭",
    ]
    return any(sig in history for sig in activity_signals)


def _is_clearly_non_planning(text: str) -> bool:
    pure_greetings = ["你好", "hi", "hello", "嗨", "在吗", "在不在"]
    if text.lower().strip() in [g.lower() for g in pure_greetings]:
        return True
    if len(text) <= 2:
        return True
    if any(kw in text for kw in NON_PLAN_KEYWORDS):
        return True
    if re.match(r'^[？?！!。.]+$', text):
        return True
    return False


def _is_pure_preference(text: str) -> bool:
    for pat in [r'我(?:家|住|是|叫|有|喜欢|的|不)', r'孩子.*岁', r'预算.*\d+']:
        if re.search(pat, text):
            if not any(kw in text for kw in ["帮", "规划", "安排", "推荐", "去哪"]):
                return True
    return False


def _extract_replace_target(user_input: str, state: AgentState) -> Dict:
    target = {"target_description": user_input, "target_index": None, "target_name": None}
    ordinal_map = {
        "第一": 0, "第二": 1, "第三": 2, "第四": 3, "第五": 4,
        "第1": 0, "第2": 1, "第3": 2, "第4": 3, "第5": 4,
        "第一个": 0, "第二个": 1, "第三个": 2, "头一个": 0,
    }
    for word, idx in ordinal_map.items():
        if word in user_input:
            target["target_index"] = idx
            return target

    # 模糊名称匹配
    plan = state.get("plan", [])
    replace_words = ["换掉", "不喜欢", "换成", "替换", "不要", "改掉", "不好吃", "不好玩", "不想去", "不想吃", "不适合", "不合适", "也不要"]
    name_candidate = user_input
    for w in replace_words:
        if w in name_candidate:
            name_candidate = name_candidate.split(w)[0].strip()
            break

    if name_candidate and len(name_candidate) >= 2:
        best_match, best_score = None, 0
        for i, activity in enumerate(plan):
            act_name = activity.get("name", "")
            common = sum(1 for c in name_candidate if c in act_name)
            score = common / max(len(name_candidate), 1)
            if score > best_score and score > 0.3:
                best_score = score
                best_match = i
        if best_match is not None:
            target["target_index"] = best_match
            target["target_name"] = plan[best_match].get("name", "")
            return target

    # 类型推断
    type_hints = {"餐厅": "restaurant", "饭店": "restaurant", "景点": "attraction", "咖啡": "cafe"}
    for hint, act_type in type_hints.items():
        if hint in user_input:
            for i, a in enumerate(plan):
                if a.get("activity_type") == act_type:
                    target["target_index"] = i
                    target["target_name"] = a.get("name", "")
                    return target
    return target


def _extract_partial_target(user_input: str, state: AgentState) -> Dict:
    target = {"start_after": user_input, "start_after_index": None}
    ordinal_map = {"第一": 0, "第二": 1, "第三": 2, "第1": 0, "第2": 1, "第3": 2}
    for word, idx in ordinal_map.items():
        if word in user_input and ("之后" in user_input or "开始" in user_input):
            target["start_after_index"] = idx
            break
    if "下午" in user_input:
        target["start_after"] = "下午"
    elif "中午" in user_input:
        target["start_after"] = "中午"
    return target


def _extract_time_constraint(user_input: str) -> Dict[str, Any]:
    constraint = {"has_constraint": False, "period": None, "earliest_start": None, "latest_end": None, "constraint_text": ""}

    if re.search(r'下午|午后', user_input):
        constraint.update(has_constraint=True, period="afternoon", earliest_start="13:00", latest_end="18:00",
            constraint_text="用户明确要求「下午」出行。第一个活动的开始时间必须不早于13:00。这是硬性时间约束，不允许改为上午。")
    elif re.search(r'上午|早上|早晨', user_input):
        constraint.update(has_constraint=True, period="morning", earliest_start="08:00", latest_end="12:00",
            constraint_text="用户明确要求「上午」出行。第一个活动从8:00-9:00开始。")
    elif re.search(r'晚上|傍晚', user_input):
        constraint.update(has_constraint=True, period="evening", earliest_start="17:00", latest_end="22:00",
            constraint_text="用户明确要求「晚上」出行。第一个活动从17:00之后开始。")

    time_match = re.search(r'(\d{1,2})\s*[点:：]\s*(\d{0,2})?\s*(?:半|分)?', user_input)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            constraint["has_constraint"] = True
            constraint["earliest_start"] = f"{hour:02d}:{minute:02d}"
            constraint["constraint_text"] = f"用户明确指定了开始时间「{constraint['earliest_start']}」。这是硬性时间约束。"

    duration_match = re.search(r'(\d+)\s*个?\s*(?:小时|钟头)', user_input)
    if duration_match:
        constraint["constraint_text"] += f" 用户预计总共{duration_match.group(1)}小时的活动时间。"

    return constraint


def general_response(state: AgentState) -> Dict[str, Any]:
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""
    cid = state.get("conversation_id", "unknown")
    logger.info(f"通用响应 | cid={cid}")

    response_text = (
        "👋 你好！我是**小团**，你的专属活动规划助手。\n\n"
        "我可以帮你：\n"
        "🎯 **规划出行**：一日游、周末游玩、亲子活动\n"
        "🍽️ **推荐餐厅**：根据口味和场景推荐合适的餐厅\n"
        "🎪 **安排活动**：密室逃脱、展览、演出等\n"
        "🎂 **惊喜预定**：蛋糕、鲜花配送到指定地点\n\n"
        "你可以这样跟我说：\n"
        "- \"帮我规划周末带5岁孩子的一日游\"\n"
        "- \"和朋友4个人聚会，有什么推荐？\"\n"
        "- \"约会推荐，浪漫一点的地方\"\n\n"
        "请告诉我你的需求，我来帮你安排！ 😊"
    )

    return {"messages": [AIMessage(content=response_text)], "intent_type": "general", "conversation_id": cid}
