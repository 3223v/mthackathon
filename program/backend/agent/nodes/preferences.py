"""
偏好提取节点

从用户消息中提取结构化个人信息和偏好，保存到 data/preferences.json。

支持提取：
- 个人信息：姓名、年龄、居住/工作位置
- 偏好：饮食、交通、活动类型、预算
- 社会关系：配偶、孩子（各自有独立偏好）
- 朋友群组：典型人数、共同活动

此节点是"无感"的 — 用户不需要显式触发，任何包含个人信息的消息都会被处理。
"""

import re
from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage
from agent.state import AgentState
from mockfunction import save_user_preferences, get_user_preferences
from utils import logger


def extract_preferences(state: AgentState) -> Dict[str, Any]:
    """从用户输入中提取偏好信息并持久化"""
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    conversation_id = state.get("conversation_id", "unknown")

    if not isinstance(last_message, HumanMessage):
        return {}

    user_input = last_message.content

    # 提取结构化信息
    extracted = _extract_from_text(user_input)

    if not extracted["has_any"]:
        logger.debug(f"未提取到偏好 | cid={conversation_id}")
        return {"user_profile": state.get("user_profile", {})}

    user_id = "default_user"
    existing = get_user_preferences(user_id)
    existing_data = existing.get("data", {}) if existing.get("code") == 0 else {}

    # 合并社会关系
    merged_relationships = _merge_relationships(
        existing_data.get("social_relationships", []),
        extracted["social_relationships"],
    )

    # 保存到文件
    save_user_preferences(
        user_id=user_id,
        personal_info=extracted["personal_info"],
        diet_prefs=extracted["diet_preferences"],
        transport_prefs=extracted["transport_preferences"],
        activity_prefs=extracted.get("activity_preferences", []),
        budget_range=extracted.get("budget_range", ""),
        social_relationships=merged_relationships,
        friends_group=extracted.get("friends_group"),
    )

    logger.info(
        f"偏好已持久化 | cid={conversation_id} | "
        f"family={bool(extracted['social_relationships'])} | "
        f"diet={extracted['diet_preferences']} | "
        f"budget={extracted.get('budget_range', '')}"
    )

    # 通知用户
    changed = _build_change_notice(extracted)
    notice = f"📝 {changed}" if changed else "📝 已记录您的偏好信息"

    return {
        "user_profile": _build_user_profile(extracted, existing_data),
        "messages": [AIMessage(content=notice)],
    }


def _extract_from_text(text: str) -> Dict[str, Any]:
    """从文本中提取结构化偏好"""
    result = {
        "has_any": False,
        "personal_info": {},
        "diet_preferences": [],
        "transport_preferences": [],
        "activity_preferences": [],
        "budget_range": "",
        "social_relationships": [],
        "friends_group": None,
    }

    # --- 个人信息 ---
    # 位置（居住地）
    loc_match = re.search(r'(?:住在|家住|我家在|在)\s*(\S+(?:区|街道|路|城|庄|园))', text)
    if loc_match:
        result["personal_info"]["home_location"] = {"address": loc_match.group(1)}
        result["has_any"] = True

    # 姓名
    name_match = re.search(r'(?:我叫|我是|叫我)\s*(\S{1,4})', text)
    if name_match:
        result["personal_info"]["name"] = name_match.group(1)
        result["has_any"] = True

    # --- 孩子信息（社会关系） ---
    child_match = re.search(r'(\d+)\s*岁\s*(?:的)?\s*(?:孩子|宝宝|小孩|儿子|女儿|娃)', text)
    if child_match:
        result["social_relationships"].append({
            "relation": "child",
            "age": int(child_match.group(1)),
            "preferences": {},
        })
        result["has_any"] = True
    elif re.search(r'孩子|宝宝|小孩|儿童|娃|亲子', text):
        ages = re.findall(r'(\d+)\s*岁', text)
        child_rel = {"relation": "child", "preferences": {}}
        if ages:
            child_rel["age"] = int(ages[0])
        result["social_relationships"].append(child_rel)
        result["has_any"] = True

    # --- 配偶信息 ---
    if re.search(r'老婆|老公|伴侣|对象|女朋友|男朋友', text):
        spouse_rel = {"relation": "spouse", "preferences": {}}
        if re.search(r'减肥|健身|控制体重', text):
            spouse_rel["preferences"]["diet"] = ["低卡路里", "健康餐"]
        result["social_relationships"].append(spouse_rel)
        result["has_any"] = True

    # --- 父母/长辈 ---
    if re.search(r'爸爸|妈妈|父母|老人|长辈|爸妈', text):
        result["social_relationships"].append({
            "relation": "parent",
            "preferences": {"activity_types": ["轻松", "休闲"]},
        })
        result["has_any"] = True

    # --- 饮食偏好 ---
    if re.search(r'不吃|忌口|过敏|不能吃', text):
        diet_match = re.findall(r'(?:不吃|忌口|过敏|不能吃)\s*[：:]?\s*(\S+)', text)
        result["diet_preferences"].extend(diet_match)
        result["has_any"] = True

    taste_map = {
        '辣': '辣味', '麻辣': '麻辣', '清淡': '清淡', '甜': '甜食',
        '咸': '咸味', '素食': '素食', '清真': '清真', '海鲜': '海鲜',
        '烧烤': '烧烤', '火锅': '火锅', '日料': '日料', '西餐': '西餐',
    }
    for keyword, label in taste_map.items():
        if keyword in text and label not in result["diet_preferences"]:
            result["diet_preferences"].append(label)
            result["has_any"] = True

    # --- 交通偏好 ---
    if re.search(r'开车|自驾|自己开', text):
        result["transport_preferences"].append("driving")
        result["has_any"] = True
    if re.search(r'打车|叫车|滴滴', text):
        result["transport_preferences"].append("taxi")
        result["has_any"] = True
    if re.search(r'地铁|公交|公共交通', text):
        result["transport_preferences"].append("public_transit")
        result["has_any"] = True
    if re.search(r'走路|步行|走着', text):
        result["transport_preferences"].append("walking")
        result["has_any"] = True

    # --- 活动偏好 ---
    activity_map = {
        '户外': '户外活动', '爬山': '登山', '徒步': '徒步',
        '博物馆': '博物馆', '展览': '展览', '密室': '密室逃脱',
        '剧本杀': '剧本杀', '电影': '电影', '购物': '购物',
        '拍照': '拍照打卡', '泡温泉': '温泉',
    }
    for keyword, label in activity_map.items():
        if keyword in text and label not in result["activity_preferences"]:
            result["activity_preferences"].append(label)
            result["has_any"] = True

    # --- 预算 ---
    budget_match = re.search(r'预算\s*[：:]?\s*(\d+)\s*[-~到]\s*(\d+)', text)
    if budget_match:
        result["budget_range"] = f"{budget_match.group(1)}-{budget_match.group(2)}元"
        result["has_any"] = True
    else:
        budget_match = re.search(r'人均\s*[：:]?\s*(\d+)', text)
        if budget_match:
            result["budget_range"] = f"人均{budget_match.group(1)}元"
            result["has_any"] = True

    # --- 朋友群组 ---
    friend_match = re.search(r'(\d+)\s*个?\s*(?:人|朋友|兄弟|闺蜜|同学|同事)', text)
    if friend_match:
        result["friends_group"] = {"typical_size": int(friend_match.group(1))}
        result["has_any"] = True

    if re.search(r'男.*女|女.*男', text) and result["friends_group"]:
        result["friends_group"]["mixed_gender"] = True

    return result


def _merge_relationships(existing: list, new: list) -> list:
    """合并社会关系：按 relation 去重，新的覆盖旧的"""
    merged = {r.get("relation"): r for r in existing}
    for rel in new:
        key = rel.get("relation", "")
        if key in merged:
            merged[key] = {**merged[key], **rel}
            if "preferences" in rel and "preferences" in merged[key]:
                merged[key]["preferences"] = {**merged[key]["preferences"], **rel["preferences"]}
        else:
            merged[key] = rel
    return list(merged.values())


def _build_change_notice(extracted: dict) -> str:
    """构建变更通知"""
    items = []
    if extracted.get("personal_info"):
        items.append("个人信息")
    if extracted.get("social_relationships"):
        rels = [r.get("relation") for r in extracted["social_relationships"]]
        items.append(f"社会关系({', '.join(rels)})")
    if extracted.get("diet_preferences"):
        items.append("饮食偏好")
    if extracted.get("transport_preferences"):
        items.append("交通偏好")
    if extracted.get("activity_preferences"):
        items.append("活动偏好")
    if extracted.get("budget_range"):
        items.append("预算范围")
    if extracted.get("friends_group"):
        items.append("朋友群组")

    return f"已更新您的信息：{', '.join(items)}" if items else ""


def _build_user_profile(extracted: dict, existing: dict) -> Dict:
    """构建结构化的用户画像"""
    return {
        "personal_info": {**existing.get("personal_info", {}), **extracted.get("personal_info", {})},
        "diet_preferences": extracted.get("diet_preferences", []),
        "transport_preferences": extracted.get("transport_preferences", []),
        "activity_preferences": extracted.get("activity_preferences", []),
        "budget_range": extracted.get("budget_range", ""),
        "social_relationships": extracted.get("social_relationships", []),
        "friends_group": extracted.get("friends_group"),
    }
