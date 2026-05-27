"""用户偏好管理 - 偏好的加载、保存和查询

偏好持久化到 data/preferences.json，跨会话保留。
Agent 在规划时会自动参考用户偏好（如饮食限制、最远距离等）。
"""
import json
import os
from typing import Optional


# 偏好文件路径（项目根目录下的 data/preferences.json）
PREFERENCES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "preferences.json")


def _ensure_data_dir():
    """确保 data/ 目录存在，不存在则自动创建"""
    os.makedirs(os.path.dirname(PREFERENCES_FILE), exist_ok=True)


def load_preferences() -> dict:
    """加载用户偏好

    首次使用时返回默认偏好结构，后续从 data/preferences.json 读取。

    Returns:
        偏好字典，包含：
        - dietary_restrictions: 饮食限制（如 ["不吃辣", "素食"]）
        - preferred_cuisines: 喜欢的菜系（如 ["火锅", "日料"]）
        - disliked_cuisines: 不喜欢的菜系
        - activity_types: 喜欢的活动类型
        - budget_range: 预算范围描述
        - max_distance_km: 最远距离限制
        - companions: 常用同行人列表
        - home_location: 家的位置
        - notes: 自由备注列表
    """
    _ensure_data_dir()
    if os.path.exists(PREFERENCES_FILE):
        with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return _default_preferences()


def save_preferences(prefs: dict):
    """保存用户偏好到 data/preferences.json"""
    _ensure_data_dir()
    with open(PREFERENCES_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


def _default_preferences() -> dict:
    """返回默认偏好结构（所有字段为空）"""
    return {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "disliked_cuisines": [],
        "activity_types": [],
        "budget_range": None,
        "max_distance_km": None,
        "companions": [],
        "home_location": None,
        "notes": []
    }


def update_preference(key: str, value) -> dict:
    """更新单条偏好字段

    Args:
        key: 偏好字段名
        value: 新值

    Returns:
        更新后的完整偏好字典
    """
    prefs = load_preferences()
    prefs[key] = value
    save_preferences(prefs)
    return prefs


def add_companion(name: str, age: Optional[int] = None, relation: Optional[str] = None) -> dict:
    """添加或更新同行人信息

    如果同名同行人已存在，会先删除旧记录再添加新的（去重）。

    Args:
        name: 同行人姓名
        age: 年龄（可选，用于判断是否是孩子）
        relation: 关系（如 "老婆"、"朋友"、"孩子"）

    Returns:
        更新后的完整偏好字典
    """
    prefs = load_preferences()
    companions = prefs.get("companions", [])
    # 按姓名去重
    companions = [c for c in companions if c.get("name") != name]
    companions.append({"name": name, "age": age, "relation": relation})
    prefs["companions"] = companions
    save_preferences(prefs)
    return prefs


def add_note(note: str) -> dict:
    """添加偏好备注（自由文本，如"在减肥"、"不喜欢排队"等）

    Args:
        note: 备注内容

    Returns:
        更新后的完整偏好字典
    """
    prefs = load_preferences()
    prefs.setdefault("notes", []).append(note)
    save_preferences(prefs)
    return prefs


def get_scenario_from_preferences(prefs: dict) -> str:
    """根据同行人信息推断场景类型

    判断逻辑：
    - 有 12 岁以下的孩子 → family（亲子）
    - 3 人以上 → friends（朋友）
    - 1 人且关系为伴侣类 → couple（情侣）
    - 其他 → friends

    Args:
        prefs: 用户偏好字典

    Returns:
        场景类型字符串
    """
    companions = prefs.get("companions", [])
    if not companions:
        return "solo"

    has_child = any(c.get("age") and c["age"] <= 12 for c in companions)
    if has_child:
        return "family"

    if len(companions) >= 3:
        return "friends"

    if len(companions) == 1:
        relation = companions[0].get("relation", "")
        if relation in ("老婆", "老公", "女朋友", "男朋友", "对象", "伴侣"):
            return "couple"

    return "friends"


def format_preferences_summary(prefs: dict) -> str:
    """将偏好字典格式化为可读的文本摘要

    用于 LLM 提示词中，让模型了解用户的长期偏好。

    Args:
        prefs: 用户偏好字典

    Returns:
        格式化的文本摘要，每行一个偏好类别
    """
    lines = []
    if prefs.get("preferred_cuisines"):
        lines.append(f"  喜欢的菜系: {', '.join(prefs['preferred_cuisines'])}")
    if prefs.get("disliked_cuisines"):
        lines.append(f"  不喜欢的菜系: {', '.join(prefs['disliked_cuisines'])}")
    if prefs.get("dietary_restrictions"):
        lines.append(f"  饮食限制: {', '.join(prefs['dietary_restrictions'])}")
    if prefs.get("activity_types"):
        lines.append(f"  喜欢的活动: {', '.join(prefs['activity_types'])}")
    if prefs.get("max_distance_km"):
        lines.append(f"  最远距离: {prefs['max_distance_km']}km")
    if prefs.get("budget_range"):
        lines.append(f"  预算范围: {prefs['budget_range']}")
    if prefs.get("companions"):
        comp_strs = []
        for c in prefs["companions"]:
            s = c["name"]
            if c.get("age"):
                s += f"({c['age']}岁)"
            if c.get("relation"):
                s += f"({c['relation']})"
            comp_strs.append(s)
        lines.append(f"  常用同行人: {', '.join(comp_strs)}")
    if prefs.get("notes"):
        lines.append(f"  备注: {'; '.join(prefs['notes'])}")

    if not lines:
        return "  暂无偏好设置"
    return "\n".join(lines)
