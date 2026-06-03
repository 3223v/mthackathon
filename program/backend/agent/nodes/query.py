"""
数据查询节点

功能：
1. 根据 Skill 的过滤规则查询数据
2. 调用 mockfunction 获取候选景点、餐厅、活动等
3. 收集并结构化查询结果

所有数据访问通过 mockfunction 进行。
"""

from typing import Dict, Any, List
from agent.state import AgentState
from tools.query_tools import QueryTools
from core.skill_loader import skill_loader
from utils import logger

# 全局查询工具实例
query_tools = QueryTools()


def query_data(state: AgentState) -> Dict[str, Any]:
    """
    根据意图和 Skill 查询相关数据

    查询策略：
    1. 有 Skill → 使用 Skill 定义的过滤规则
    2. 无 Skill → 使用默认过滤规则（全场景查询）
    3. 从用户偏好中提取位置信息（如果有）

    Returns:
        更新 state.query_results
    """
    conversation_id = state.get("conversation_id", "unknown")
    skill_context = state.get("skill_context")
    user_profile = state.get("user_profile", {})
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""

    logger.info(f"开始查询数据 | conversation_id={conversation_id} | skill={skill_context['id'] if skill_context else 'None'}")

    # 默认坐标（北京天安门）
    lat = 39.9042
    lng = 116.4074

    # 从用户画像中提取位置偏好
    if user_profile:
        location = _extract_location(user_input, user_profile)
        if location:
            lat, lng = location

    # 获取查询过滤器
    if skill_context:
        filters = skill_loader.get_query_filters(skill_context)
    else:
        filters = _default_filters()

    logger.info(f"查询过滤器 | suitable_for_attractions={filters['attractions'].get('suitable_for')}")

    # 执行查询
    try:
        results = query_tools.query_by_filters(lat=lat, lng=lng, filters=filters)
    except Exception as e:
        logger.error(f"数据查询失败 | error={str(e)}")
        results = {"attractions": [], "restaurants": [], "activities": [], "cafes": []}

    # 日志输出
    total = sum(len(v) for v in results.values())
    logger.info(
        f"数据查询完成 | total={total} | "
        f"attractions={len(results.get('attractions', []))} | "
        f"restaurants={len(results.get('restaurants', []))} | "
        f"activities={len(results.get('activities', []))} | "
        f"cafes={len(results.get('cafes', []))}"
    )

    return {
        "query_results": results,
    }


def _extract_location(user_input: str, user_profile: Dict) -> Any:
    """从用户输入或画像中提取坐标"""
    # 目前使用默认坐标，未来可扩展为地理编码
    return None


def _default_filters() -> Dict[str, Any]:
    """默认查询过滤器（无 Skill 时不限制 suitable_for，让所有数据通过）"""
    return {
        "attractions": {"suitable_for": None},
        "restaurants": {"suitable_for": None},
        "activities": {"suitable_for": None},
        "cafes": {"suitable_for": None},
    }


def format_data_for_prompt(query_results: Dict[str, Any]) -> str:
    """
    将查询结果格式化为可注入 LLM prompt 的文本

    每个地点包含：ID、名称、类型、坐标、评分、价格、标签等关键信息
    """
    lines = []

    for category, items in query_results.items():
        if not items:
            continue

        category_names = {
            "attractions": "🏛️ 景点",
            "restaurants": "🍽️ 餐厅",
            "activities": "🎯 活动",
            "cafes": "☕ 饮品店",
        }

        lines.append(f"\n## {category_names.get(category, category)}")
        lines.append("-" * 40)

        for item in items[:20]:  # 展示更多候选项
            name = item.get("name", "未知")
            item_id = item.get("id", "")
            item_type = item.get("type", item.get("sub_type", ""))
            location = item.get("location", {})
            address = item.get("address", "")
            rating = item.get("rating", "")
            price = item.get("price", item.get("price_per_person", ""))
            tags = item.get("tags", [])
            suitable = item.get("suitable_for", [])
            duration = item.get("duration_hours", item.get("visit_duration_hours", ""))

            line = f"- [{item_id}] {name}"
            if item_type:
                line += f" | 类型: {item_type}"
            if rating:
                line += f" | ⭐{rating}"
            if price:
                line += f" | 💰{price}元"
            if location:
                line += f" | 📍({location.get('lat', '')}, {location.get('lng', '')})"
            if address:
                line += f" | {address[:30]}"
            if duration:
                line += f" | ⏱️{duration}h"
            if tags:
                line += f" | 标签: {', '.join(tags[:3])}"

            lines.append(line)

        # 如果该类别有更多项
        if len(items) > 5:
            lines.append(f"  ... 还有 {len(items) - 5} 个更多选择")

    return "\n".join(lines)
