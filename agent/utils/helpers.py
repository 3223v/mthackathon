"""通用工具函数

提供 JSON 文件读写、金额格式化、数据过滤等基础能力，
供 tools/ 和 agent/ 层调用。
"""
import json
import os
from typing import Optional


def load_json(filepath: str) -> dict | list:
    """从项目根目录加载 JSON 文件

    Args:
        filepath: 相对于项目根目录的文件路径，如 "mock/attractions.json"

    Returns:
        解析后的 dict 或 list
    """
    full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), filepath)
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: str, data):
    """保存数据为 JSON 文件到项目根目录

    自动创建不存在的目录。

    Args:
        filepath: 相对于项目根目录的文件路径
        data: 要保存的数据（dict 或 list）
    """
    full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_money(amount: float) -> str:
    """格式化金额为 ¥xxx 格式

    Args:
        amount: 金额数值

    Returns:
        如 "¥260"
    """
    return f"¥{amount:.0f}"


def calculate_total_cost(items: list[dict]) -> float:
    """计算一组项目的总费用

    每个 item 需包含 price 和 count 字段，count 默认为 1。

    Args:
        items: 项目列表

    Returns:
        总费用
    """
    return sum(item.get("price", 0) * item.get("count", 1) for item in items)


def match_tags(item: dict, required_tags: list[str]) -> bool:
    """检查项目是否匹配任意一个标签要求

    同时检查 tags 和 suitable_for 两个字段。

    Args:
        item: 数据项（景点/餐厅/活动）
        required_tags: 需要匹配的标签列表

    Returns:
        是否匹配
    """
    if not required_tags:
        return True
    item_tags = item.get("tags", [])
    item_types = item.get("suitable_for", [])
    all_tags = item_tags + item_types
    return any(tag in all_tags for tag in required_tags)


def filter_by_distance(items: list[dict], max_distance: Optional[float] = None) -> list[dict]:
    """按距离过滤数据

    Args:
        items: 数据列表
        max_distance: 最大距离（km），None 表示不限

    Returns:
        过滤后的列表
    """
    if max_distance is None:
        return items
    return [item for item in items if item.get("distance_km", 0) <= max_distance]


def filter_by_budget(items: list[dict], max_budget: Optional[float] = None) -> list[dict]:
    """按人均预算过滤数据

    优先使用 price_per_person 字段，其次使用 ticket_price。

    Args:
        items: 数据列表
        max_budget: 人均预算上限，None 表示不限

    Returns:
        过滤后的列表
    """
    if max_budget is None:
        return items
    return [item for item in items if item.get("price_per_person", item.get("ticket_price", 0)) <= max_budget]
