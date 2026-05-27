"""查询工具层 - 封装 mock 数据的查询接口

所有查询函数从 mock/ 目录读取 JSON 数据，支持多维度过滤。
上层（agent/core.py 的 generate_plan 节点）调用这些函数获取候选数据，
再由 LLM 从中选择最合适的组合成方案。
"""
from typing import Optional
from utils.helpers import load_json


def query_attractions(
    scenario: Optional[str] = None,
    max_distance: Optional[float] = None,
    child_age: Optional[int] = None,
    tags: Optional[list[str]] = None
) -> list[dict]:
    """查询景点列表，支持场景/距离/年龄/标签过滤

    Args:
        scenario: 场景标签过滤（"亲子"/"朋友"/"情侣"）
        max_distance: 最大距离限制（km），None 表示不限
        child_age: 孩子年龄，用于排除不适合低龄的景点（如密室逃脱）
        tags: 标签列表，匹配 tags 和 suitable_for 字段

    Returns:
        按评分降序排列的景点列表
    """
    data = load_json("mock/attractions.json")
    results = data["attractions"]

    # 场景过滤：只保留包含该场景标签的景点
    if scenario:
        results = [a for a in results if scenario in a.get("suitable_for", [])]

    # 距离过滤
    if max_distance is not None:
        results = [a for a in results if a["distance_km"] <= max_distance]

    # 年龄过滤：5岁以下排除密室逃脱等不适合的活动
    if child_age is not None:
        if child_age <= 5:
            results = [a for a in results if a["type"] not in ("密室逃脱",)]

    # 标签匹配
    if tags:
        results = [a for a in results if any(
            t in a.get("tags", []) + a.get("suitable_for", []) for t in tags
        )]

    # 按评分降序排列
    return sorted(results, key=lambda x: x["rating"], reverse=True)


def query_restaurants(
    scenario: Optional[str] = None,
    max_distance: Optional[float] = None,
    max_budget_per_person: Optional[float] = None,
    cuisine: Optional[str] = None,
    need_kids_friendly: bool = False,
    min_capacity: Optional[int] = None
) -> list[dict]:
    """查询餐厅列表，支持场景/距离/预算/菜系/儿童设施/容量过滤

    Args:
        scenario: 场景标签过滤
        max_distance: 最大距离限制（km）
        max_budget_per_person: 人均预算上限
        cuisine: 菜系关键词（模糊匹配 cuisine 字段和 tags）
        need_kids_friendly: 是否需要儿童椅或儿童餐
        min_capacity: 最少容纳人数

    Returns:
        按评分降序排列的餐厅列表
    """
    data = load_json("mock/restaurants.json")
    results = data["restaurants"]

    if scenario:
        results = [r for r in results if scenario in r.get("suitable_for", [])]

    if max_distance is not None:
        results = [r for r in results if r["distance_km"] <= max_distance]

    if max_budget_per_person is not None:
        results = [r for r in results if r["price_per_person"] <= max_budget_per_person]

    if cuisine:
        results = [r for r in results if cuisine in r.get("cuisine", "") or cuisine in str(r.get("tags", []))]

    # 亲子场景必须有儿童椅或儿童餐
    if need_kids_friendly:
        results = [r for r in results if r.get("has_kids_chair") or r.get("has_kids_menu")]

    if min_capacity is not None:
        results = [r for r in results if min_capacity <= _parse_capacity(r.get("capacity", "2-4人"))]

    return sorted(results, key=lambda x: x["rating"], reverse=True)


def query_activities(
    scenario: Optional[str] = None,
    max_distance: Optional[float] = None,
    child_age: Optional[int] = None,
    tags: Optional[list[str]] = None
) -> list[dict]:
    """查询活动列表，支持场景/距离/年龄/标签过滤

    Args:
        scenario: 场景标签过滤
        max_distance: 最大距离限制（km）
        child_age: 孩子年龄，过滤年龄限制（只保留 min_age <= child_age 的活动）
        tags: 标签列表

    Returns:
        按评分降序排列的活动列表
    """
    data = load_json("mock/activities.json")
    results = data["activities"]

    if scenario:
        results = [a for a in results if scenario in a.get("suitable_for", [])]

    if max_distance is not None:
        results = [a for a in results if a["distance_km"] <= max_distance]

    # 年龄过滤：只保留孩子年龄 >= min_age 的活动
    if child_age is not None:
        results = [a for a in results if a.get("min_age", 0) <= child_age]

    if tags:
        results = [a for a in results if any(t in a.get("tags", []) for t in tags)]

    return sorted(results, key=lambda x: x["rating"], reverse=True)


def query_cakes(scenario: Optional[str] = None) -> list[dict]:
    """查询可配送的蛋糕

    Args:
        scenario: 场景过滤（"亲子"/"朋友"/"情侣"）

    Returns:
        蛋糕列表
    """
    data = load_json("mock/cakes_flowers.json")
    results = data["cakes"]
    if scenario:
        results = [c for c in results if scenario in c.get("suitable_for", [])]
    return results


def query_flowers(scenario: Optional[str] = None) -> list[dict]:
    """查询可配送的鲜花

    Args:
        scenario: 场景过滤

    Returns:
        鲜花列表
    """
    data = load_json("mock/cakes_flowers.json")
    results = data["flowers"]
    if scenario:
        results = [f for f in results if scenario in f.get("suitable_for", [])]
    return results


def _parse_capacity(cap_str: str) -> int:
    """解析容量字符串中的最大人数

    如 "2-10人" → 10, "不限" → 999

    Args:
        cap_str: 容量描述字符串

    Returns:
        最大容纳人数
    """
    import re
    nums = re.findall(r"\d+", cap_str)
    return int(nums[-1]) if nums else 4
