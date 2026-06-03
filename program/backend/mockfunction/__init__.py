# backend/mockfunction/__init__.py
"""
Mock数据操作模块

此模块提供mock数据的查询接口，供tools层调用。
数据源为拆分后的7个JSON文件：
- attractions.json      景点/乐园/公园
- restaurants.json      餐厅（含availability和delivery_items）
- activities.json       额外活动（展览/密室等）
- cafes.json            饮品店
- shops.json            商超（便利店/商场）
- groceries.json        生鲜（水果/蔬菜）
- others.json           公共服务（公厕/药店/加油站）

订单和用户偏好不在mock数据中维护，仅作为运行时存储。
"""

import json
import os
import math
import random
from datetime import datetime
from typing import List, Dict, Any, Optional, Union

# ==================== 路径配置 ====================
MOCKDATA_DIR = os.path.join(os.path.dirname(__file__), "../mockdata")
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
PREFERENCES_FILE = os.path.join(DATA_DIR, "preferences.json")

# 数据文件映射
DATA_FILES = {
    "attractions": "attractions.json",
    "restaurants": "restaurants.json",
    "activities": "activities.json",
    "cafes": "cafes.json",
    "shops": "shops.json",
    "groceries": "groceries.json",
    "others": "others.json"
}

# 运行时存储（订单运行时存储，偏好持久化到文件）
_orders = []
_user_preferences = {}

# ==================== 偏好持久化 ====================
def _load_preferences_from_file() -> dict:
    """从 data/preferences.json 加载用户偏好"""
    try:
        if os.path.exists(PREFERENCES_FILE):
            with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("user_id"):
                    _user_preferences[data["user_id"]] = data
                    return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"警告：加载偏好文件失败: {e}")
    return {}

def _save_preferences_to_file(user_id: str) -> bool:
    """将用户偏好写入 data/preferences.json"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        data = _user_preferences.get(user_id, {})
        with open(PREFERENCES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        print(f"错误：保存偏好文件失败: {e}")
        return False

# 启动时加载已有偏好
_loaded_prefs = _load_preferences_from_file()
if _loaded_prefs:
    print(f"已加载用户偏好: {_loaded_prefs.get('user_id', 'unknown')}")


# ==================== 数据加载辅助 ====================
def _load_json(filename: str) -> list:
    """加载JSON文件，返回列表，文件不存在则返回空列表"""
    filepath = os.path.join(MOCKDATA_DIR, filename)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                print(f"警告：{filename} 应为JSON数组，实际为{type(data)}")
                return []
    except FileNotFoundError:
        print(f"警告：未找到mock数据文件: {filepath}")
        return []
    except json.JSONDecodeError as e:
        print(f"错误：{filepath} JSON解析失败: {e}")
        return []


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间距离（米），使用Haversine公式"""
    R = 6371000  # 地球半径（米）
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _filter_by_distance(items: list, lat: float, lng: float, radius: int) -> list:
    """过滤出距离小于半径的项目，并附加distance字段"""
    result = []
    for item in items:
        loc = item.get("location", {})
        if "lat" in loc and "lng" in loc:
            dist = _haversine_distance(lat, lng, loc["lat"], loc["lng"])
            if dist <= radius:
                copy = item.copy()
                copy["distance"] = round(dist, 0)
                result.append(copy)
    return result


def _filter_by_tags(items: list, tags: List[str] = None, suitable_for: List[str] = None) -> list:
    """根据标签或适用人群过滤"""
    if tags:
        items = [i for i in items if any(tag in i.get("tags", []) for tag in tags)]
    if suitable_for:
        items = [i for i in items if any(s in i.get("suitable_for", []) for s in suitable_for)]
    return items


# ==================== 通用查询接口 ====================
def get_nearby_attractions(lat: float, lng: float, radius: int = 3000,
                           tags: List[str] = None, suitable_for: List[str] = None) -> Dict[str, Any]:
    """获取附近景点，按距离排序"""
    attractions = _load_json(DATA_FILES["attractions"])
    filtered = _filter_by_distance(attractions, lat, lng, radius)
    filtered = _filter_by_tags(filtered, tags, suitable_for)
    filtered.sort(key=lambda x: x["distance"])
    return {"code": 0, "message": "success", "data": filtered[:10]}


def get_nearby_restaurants(lat: float, lng: float, radius: int = 2000,
                           cuisine: str = None, suitable_for: List[str] = None) -> Dict[str, Any]:
    """获取附近餐厅"""
    restaurants = _load_json(DATA_FILES["restaurants"])
    filtered = _filter_by_distance(restaurants, lat, lng, radius)
    if cuisine:
        filtered = [r for r in filtered if r.get("cuisine") == cuisine]
    filtered = _filter_by_tags(filtered, suitable_for=suitable_for)
    filtered.sort(key=lambda x: x["distance"])
    return {"code": 0, "message": "success", "data": filtered[:10]}


def get_nearby_activities(lat: float, lng: float, radius: int = 3000,
                          suitable_for: List[str] = None) -> Dict[str, Any]:
    """获取附近额外活动"""
    activities = _load_json(DATA_FILES["activities"])
    filtered = _filter_by_distance(activities, lat, lng, radius)
    filtered = _filter_by_tags(filtered, suitable_for=suitable_for)
    filtered.sort(key=lambda x: x["distance"])
    return {"code": 0, "message": "success", "data": filtered[:10]}


def get_nearby_cafes(lat: float, lng: float, radius: int = 1500,
                     suitable_for: List[str] = None) -> Dict[str, Any]:
    """获取附近饮品店"""
    cafes = _load_json(DATA_FILES["cafes"])
    filtered = _filter_by_distance(cafes, lat, lng, radius)
    filtered = _filter_by_tags(filtered, suitable_for=suitable_for)
    filtered.sort(key=lambda x: x["distance"])
    return {"code": 0, "message": "success", "data": filtered[:10]}


def get_nearby_shops(lat: float, lng: float, radius: int = 2000,
                     shop_type: str = None, suitable_for: List[str] = None) -> Dict[str, Any]:
    """获取附近商超"""
    shops = _load_json(DATA_FILES["shops"])
    filtered = _filter_by_distance(shops, lat, lng, radius)
    if shop_type:
        filtered = [s for s in filtered if s.get("type") == shop_type]
    filtered = _filter_by_tags(filtered, suitable_for=suitable_for)
    filtered.sort(key=lambda x: x["distance"])
    return {"code": 0, "message": "success", "data": filtered[:10]}


def get_nearby_groceries(lat: float, lng: float, radius: int = 2000,
                         suitable_for: List[str] = None) -> Dict[str, Any]:
    """获取附近生鲜店"""
    groceries = _load_json(DATA_FILES["groceries"])
    filtered = _filter_by_distance(groceries, lat, lng, radius)
    filtered = _filter_by_tags(filtered, suitable_for=suitable_for)
    filtered.sort(key=lambda x: x["distance"])
    return {"code": 0, "message": "success", "data": filtered[:10]}


def get_nearby_others(lat: float, lng: float, radius: int = 5000,
                      other_type: str = None) -> Dict[str, Any]:
    """获取附近公共服务（公厕/药店/加油站）"""
    others = _load_json(DATA_FILES["others"])
    filtered = _filter_by_distance(others, lat, lng, radius)
    if other_type:
        filtered = [o for o in filtered if o.get("type") == other_type]
    filtered.sort(key=lambda x: x["distance"])
    return {"code": 0, "message": "success", "data": filtered[:10]}


# ==================== 可用性查询 ====================
def check_restaurant_availability(restaurant_id: str, date: str, time: str, people: int) -> Dict[str, Any]:
    """
    查询餐厅餐位可用性
    返回格式：
    {
        "available": bool,
        "available_seats": int,
        "queue_count": int,
        "estimated_wait": str
    }
    """
    restaurants = _load_json(DATA_FILES["restaurants"])
    restaurant = next((r for r in restaurants if r.get("id") == restaurant_id), None)
    if not restaurant:
        return {"code": 404, "message": "餐厅不存在", "data": {}}

    availability = restaurant.get("availability", {})
    day_slots = availability.get(date, {})
    slot = day_slots.get(time, {})

    if slot:
        available = slot.get("available_seats", 0) >= people
        data = {
            "available": available,
            "available_seats": slot.get("available_seats", 0),
            "queue_count": slot.get("queue_count", 0),
            "estimated_wait": slot.get("estimated_wait", "0")
        }
    else:
        # 动态模拟
        available = random.choice([True, False])
        data = {
            "available": available,
            "available_seats": random.randint(0, 10) if available else 0,
            "queue_count": random.randint(0, 20) if not available else 0,
            "estimated_wait": f"{random.randint(10, 60)}分钟" if not available else "0"
        }
    return {"code": 0, "message": "success", "data": data}


def check_activity_availability(activity_id: str, date: str, time: str) -> Dict[str, Any]:
    """查询活动场次可用性（如密室逃脱）"""
    activities = _load_json(DATA_FILES["activities"])
    activity = next((a for a in activities if a.get("id") == activity_id), None)
    if not activity or not activity.get("need_booking"):
        return {"code": 200, "message": "无需预订", "data": {"available": True}}

    availability = activity.get("availability", {})
    day_slots = availability.get(date, {})
    slot = day_slots.get(time, {})
    if slot:
        available = slot.get("available_slots", 0) > 0
        data = {"available": available, "available_slots": slot.get("available_slots", 0)}
    else:
        available = random.choice([True, False])
        data = {"available": available, "available_slots": random.randint(0, 3) if available else 0}
    return {"code": 0, "message": "success", "data": data}


# ==================== 菜单与配送商品 ====================
def get_restaurant_menu(restaurant_id: str, suitable_for: List[str] = None) -> Dict[str, Any]:
    """获取餐厅菜单，可按适用人群过滤（child/diet/normal）"""
    restaurants = _load_json(DATA_FILES["restaurants"])
    restaurant = next((r for r in restaurants if r.get("id") == restaurant_id), None)
    if not restaurant:
        return {"code": 404, "message": "餐厅不存在", "data": []}
    menu = restaurant.get("menu", [])
    if suitable_for:
        menu = [item for item in menu if any(s in item.get("suitable_for", []) for s in suitable_for)]
    return {"code": 0, "message": "success", "data": menu}


def get_delivery_items(restaurant_id: str) -> Dict[str, Any]:
    """获取餐厅可配送商品（蛋糕/鲜花）"""
    restaurants = _load_json(DATA_FILES["restaurants"])
    restaurant = next((r for r in restaurants if r.get("id") == restaurant_id), None)
    if not restaurant:
        return {"code": 404, "message": "餐厅不存在", "data": []}
    items = restaurant.get("delivery_items", [])
    return {"code": 0, "message": "success", "data": items}


# ==================== 预订执行 ====================
def book_restaurant(restaurant_id: str, date: str, time: str, people: int,
                    customer_name: str, phone: str) -> Dict[str, Any]:
    """预订餐厅桌位，生成订单号并存储到运行时orders列表"""
    booking_id = f"BOOK_{restaurant_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    order = {
        "order_id": booking_id,
        "type": "restaurant_booking",
        "restaurant_id": restaurant_id,
        "date": date,
        "time": time,
        "people": people,
        "customer_name": customer_name,
        "phone": phone,
        "status": "confirmed",
        "created_at": datetime.now().isoformat()
    }
    _orders.append(order)
    return {"code": 0, "message": "预订成功", "data": {"booking_id": booking_id, "status": "confirmed"}}


def book_ticket(attraction_id: str, ticket_type: str, quantity: int,
                date: str, customer_name: str) -> Dict[str, Any]:
    """购买门票"""
    order_id = f"TICKET_{attraction_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    order = {
        "order_id": order_id,
        "type": "ticket",
        "attraction_id": attraction_id,
        "ticket_type": ticket_type,
        "quantity": quantity,
        "date": date,
        "customer_name": customer_name,
        "status": "paid",
        "created_at": datetime.now().isoformat()
    }
    _orders.append(order)
    return {"code": 0, "message": "购票成功", "data": {"order_id": order_id, "qr_code_url": "https://mock.com/qrcode/123"}}


def order_delivery(item_type: str, item_id: str, address: str,
                   scheduled_time: str, note: str = "") -> Dict[str, Any]:
    """订购配送服务（蛋糕/鲜花）"""
    delivery_id = f"DEL_{item_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    order = {
        "order_id": delivery_id,
        "type": "delivery",
        "item_type": item_type,
        "item_id": item_id,
        "address": address,
        "scheduled_time": scheduled_time,
        "note": note,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    _orders.append(order)
    return {"code": 0, "message": "下单成功", "data": {"delivery_id": delivery_id, "estimated_arrival": scheduled_time}}


# ==================== 用户偏好 ====================
def save_user_preferences(
    user_id: str,
    preferences: str = "",
    personal_info: dict = None,
    diet_prefs: list = None,
    transport_prefs: list = None,
    activity_prefs: list = None,
    budget_range: str = "",
    social_relationships: list = None,
    friends_group: dict = None,
) -> Dict[str, Any]:
    """
    保存用户偏好，持久化到 data/preferences.json

    结构化的偏好存储，包含：
    - personal_info: 个人信息（姓名、年龄、位置等）
    - preferences: 偏好（饮食、交通、活动类型、预算等）
    - social_relationships: 社会关系（配偶、孩子等，各自有独立偏好）
    - friends_group: 朋友群组信息
    """
    now = datetime.now().isoformat()

    # 获取已有数据并合并
    existing = _user_preferences.get(user_id, {})
    if not existing:
        # 从文件或默认结构初始化
        existing = {
            "user_id": user_id,
            "personal_info": {},
            "preferences": {
                "diet": [],
                "transport": [],
                "activity_types": [],
                "budget_range": "",
                "travel_style": "",
                "other": "",
            },
            "social_relationships": [],
            "friends_group": {
                "typical_size": 4,
                "common_activities": [],
                "members": [],
            },
            "created_at": now,
        }

    existing["updated_at"] = now

    # 合并个人信息
    if personal_info:
        existing["personal_info"] = {**existing.get("personal_info", {}), **personal_info}

    # 合并偏好
    prefs = existing.setdefault("preferences", {})
    if diet_prefs:
        existing_diet = set(prefs.get("diet", []))
        existing_diet.update(diet_prefs)
        prefs["diet"] = list(existing_diet)
    if transport_prefs:
        existing_transport = set(prefs.get("transport", []))
        existing_transport.update(transport_prefs)
        prefs["transport"] = list(existing_transport)
    if activity_prefs:
        existing_activity = set(prefs.get("activity_types", []))
        existing_activity.update(activity_prefs)
        prefs["activity_types"] = list(existing_activity)
    if budget_range:
        prefs["budget_range"] = budget_range
    if preferences:
        prefs["other"] = preferences

    # 合并社会关系（有 ID 的更新，无 ID 的新增）
    if social_relationships:
        existing_rels = {r.get("relation"): r for r in existing.get("social_relationships", [])}
        for rel in social_relationships:
            key = rel.get("relation", "")
            if key in existing_rels:
                existing_rels[key] = {**existing_rels[key], **rel}
            else:
                existing_rels[key] = rel
        existing["social_relationships"] = list(existing_rels.values())

    # 合并朋友群组
    if friends_group:
        existing["friends_group"] = {**existing.get("friends_group", {}), **friends_group}

    _user_preferences[user_id] = existing

    # 持久化到文件
    _save_preferences_to_file(user_id)

    return {"code": 0, "message": "保存成功", "data": {"user_id": user_id}}


def get_user_preferences(user_id: str) -> Dict[str, Any]:
    """获取用户偏好，优先从运行时读取，否则从文件加载"""
    if user_id in _user_preferences:
        data = _user_preferences[user_id]
    else:
        data = _load_preferences_from_file()
        if not data or data.get("user_id") != user_id:
            data = {}

    return {"code": 0, "message": "success", "data": data}


def get_user_preferences_for_planning(user_id: str = "default_user") -> str:
    """
    获取格式化的偏好文本，用于注入规划 Prompt
    """
    prefs = get_user_preferences(user_id)
    data = prefs.get("data", {})

    if not data:
        return "暂无偏好信息"

    lines = []

    # 个人信息
    personal = data.get("personal_info", {})
    if personal.get("home_location", {}).get("address"):
        lines.append(f"- 居住地: {personal['home_location']['address']}")

    # 偏好
    prefs_data = data.get("preferences", {})
    if prefs_data.get("diet"):
        lines.append(f"- 饮食偏好: {', '.join(prefs_data['diet'])}")
    if prefs_data.get("transport"):
        lines.append(f"- 交通偏好: {', '.join(prefs_data['transport'])}")
    if prefs_data.get("activity_types"):
        lines.append(f"- 活动偏好: {', '.join(prefs_data['activity_types'])}")
    if prefs_data.get("budget_range"):
        lines.append(f"- 预算范围: {prefs_data['budget_range']}")
    if prefs_data.get("other"):
        lines.append(f"- 其他: {prefs_data['other']}")

    # 社会关系
    relationships = data.get("social_relationships", [])
    for rel in relationships:
        relation_name = rel.get("relation", "")
        rel_prefs = rel.get("preferences", {})
        parts = [f"- {relation_name}:"]
        if rel.get("age"):
            parts.append(f"年龄{rel['age']}岁")
        if rel_prefs.get("diet"):
            parts.append(f"饮食: {', '.join(rel_prefs['diet'])}")
        if rel_prefs.get("activity_types"):
            parts.append(f"喜欢: {', '.join(rel_prefs['activity_types'])}")
        lines.append(" ".join(parts))

    # 朋友群组
    friends = data.get("friends_group", {})
    if friends.get("typical_size"):
        lines.append(f"- 通常{friends['typical_size']}人出行")

    return "\n".join(lines) if lines else "暂无偏好信息"


# ==================== 场景推荐（兼容旧接口） ====================
def get_family_friendly_places(lat: float = 39.9042, lng: float = 116.4074) -> Dict[str, Any]:
    """获取亲子友好场所（景点+餐厅）"""
    # 默认使用北京天安门坐标
    attrs = get_nearby_attractions(lat, lng, suitable_for=["family", "child"])
    rests = get_nearby_restaurants(lat, lng, suitable_for=["family"])
    return {
        "attractions": attrs.get("data", []),
        "restaurants": rests.get("data", []),
        "scenario": "亲子出行"
    }


def get_group_friendly_places(lat: float = 39.9042, lng: float = 116.4074) -> Dict[str, Any]:
    """获取团体友好场所（朋友聚会）"""
    attrs = get_nearby_attractions(lat, lng, suitable_for=["friends"])
    rests = get_nearby_restaurants(lat, lng, suitable_for=["friends"])
    return {
        "attractions": attrs.get("data", []),
        "restaurants": rests.get("data", []),
        "scenario": "朋友聚会"
    }


def get_romantic_places(lat: float = 39.9042, lng: float = 116.4074) -> Dict[str, Any]:
    """获取浪漫场所（情侣约会）"""
    attrs = get_nearby_attractions(lat, lng, suitable_for=["couple"])
    rests = get_nearby_restaurants(lat, lng, suitable_for=["couple"])
    return {
        "attractions": attrs.get("data", []),
        "restaurants": rests.get("data", []),
        "scenario": "情侣约会"
    }


def recommend_by_scenario(scenario: str, lat: float = 39.9042, lng: float = 116.4074) -> Dict[str, Any]:
    """根据场景推荐（供原有execute_skill_node调用）"""
    if scenario == "family":
        return get_family_friendly_places(lat, lng)
    elif scenario == "friends":
        return get_group_friendly_places(lat, lng)
    elif scenario == "couple":
        return get_romantic_places(lat, lng)
    else:
        return {"error": f"未知场景: {scenario}", "attractions": [], "restaurants": []}


# ==================== 导出公共接口 ====================
__all__ = [
    # 查询
    "get_nearby_attractions",
    "get_nearby_restaurants",
    "get_nearby_activities",
    "get_nearby_cafes",
    "get_nearby_shops",
    "get_nearby_groceries",
    "get_nearby_others",
    "check_restaurant_availability",
    "check_activity_availability",
    "get_restaurant_menu",
    "get_delivery_items",
    # 预订
    "book_restaurant",
    "book_ticket",
    "order_delivery",
    # 用户偏好
    "save_user_preferences",
    "get_user_preferences",
    # 场景推荐
    "recommend_by_scenario",
    "get_family_friendly_places",
    "get_group_friendly_places",
    "get_romantic_places",
]