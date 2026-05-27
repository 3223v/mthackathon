"""预订/下单工具层 - 模拟美团下单流程

所有下单函数生成订单记录并持久化到 data/orders.json。
每个订单有唯一的自增订单号（MT10001 格式）。

当前为 mock 实现，实际对接美团 API 时替换函数体即可。
"""
import json
import os
from datetime import datetime


# 订单数据文件路径
ORDERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "orders.json")


def _ensure_data_dir():
    """确保 data/ 目录存在"""
    os.makedirs(os.path.dirname(ORDERS_FILE), exist_ok=True)


def _load_orders() -> dict:
    """加载订单数据，首次使用返回空结构"""
    _ensure_data_dir()
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"orders": [], "next_id": 10001}


def _save_orders(data: dict):
    """保存订单数据到文件"""
    _ensure_data_dir()
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _generate_order_id() -> str:
    """生成唯一订单号，格式 MT{自增数字}

    Returns:
        如 "MT10001", "MT10002"
    """
    data = _load_orders()
    order_id = f"MT{data['next_id']}"
    data["next_id"] += 1
    _save_orders(data)
    return order_id


def book_restaurant(
    restaurant_id: str,
    restaurant_name: str,
    date: str,
    time: str,
    party_size: int,
    need_kids_chair: bool = False,
    special_requests: str = ""
) -> dict:
    """餐厅预约

    Args:
        restaurant_id: 餐厅 ID（对应 mock 数据中的 id）
        restaurant_name: 餐厅名称
        date: 预约日期（如 "2026-05-27"）
        time: 预约时间（如 "18:00"）
        party_size: 就餐人数
        need_kids_chair: 是否需要儿童椅
        special_requests: 特殊需求备注

    Returns:
        包含 order_id, status 等的订单字典
    """
    order_id = _generate_order_id()
    order = {
        "order_id": order_id,
        "type": "餐厅预约",
        "restaurant_id": restaurant_id,
        "restaurant_name": restaurant_name,
        "date": date,
        "time": time,
        "party_size": party_size,
        "need_kids_chair": need_kids_chair,
        "special_requests": special_requests,
        "status": "已预约",
        "created_at": datetime.now().isoformat()
    }
    data = _load_orders()
    data["orders"].append(order)
    _save_orders(data)
    return order


def book_ticket(
    attraction_id: str,
    attraction_name: str,
    adult_count: int,
    child_count: int = 0,
    date: str = ""
) -> dict:
    """景点门票购买

    Args:
        attraction_id: 景点 ID
        attraction_name: 景点名称
        adult_count: 成人票数量
        child_count: 儿童票数量
        date: 游玩日期

    Returns:
        订单字典
    """
    order_id = _generate_order_id()
    order = {
        "order_id": order_id,
        "type": "门票购买",
        "attraction_id": attraction_id,
        "attraction_name": attraction_name,
        "adult_count": adult_count,
        "child_count": child_count,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "status": "已出票",
        "created_at": datetime.now().isoformat()
    }
    data = _load_orders()
    data["orders"].append(order)
    _save_orders(data)
    return order


def book_activity(
    activity_id: str,
    activity_name: str,
    time: str,
    participants: int,
    date: str = ""
) -> dict:
    """活动预约（密室逃脱、手工体验、桌游等）

    Args:
        activity_id: 活动 ID
        activity_name: 活动名称
        time: 预约时间
        participants: 参与人数
        date: 活动日期

    Returns:
        订单字典
    """
    order_id = _generate_order_id()
    order = {
        "order_id": order_id,
        "type": "活动预约",
        "activity_id": activity_id,
        "activity_name": activity_name,
        "time": time,
        "participants": participants,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "status": "已预约",
        "created_at": datetime.now().isoformat()
    }
    data = _load_orders()
    data["orders"].append(order)
    _save_orders(data)
    return order


def book_movie(
    movie_name: str,
    cinema: str,
    showtime: str,
    seat_count: int,
    date: str = ""
) -> dict:
    """电影票购买

    Args:
        movie_name: 电影名称
        cinema: 影院名称/地址
        showtime: 场次时间
        seat_count: 座位数
        date: 观影日期

    Returns:
        订单字典
    """
    order_id = _generate_order_id()
    order = {
        "order_id": order_id,
        "type": "电影票",
        "movie_name": movie_name,
        "cinema": cinema,
        "showtime": showtime,
        "seat_count": seat_count,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "status": "已出票",
        "created_at": datetime.now().isoformat()
    }
    data = _load_orders()
    data["orders"].append(order)
    _save_orders(data)
    return order


def order_cake(
    cake_name: str,
    delivery_address: str,
    delivery_time: str,
    message_card: str = ""
) -> dict:
    """蛋糕配送下单

    蛋糕会配送到指定地址（通常是用餐的餐厅）。

    Args:
        cake_name: 蛋糕名称
        delivery_address: 配送地址
        delivery_time: 期望送达时间
        message_card: 卡片留言

    Returns:
        订单字典
    """
    order_id = _generate_order_id()
    order = {
        "order_id": order_id,
        "type": "蛋糕配送",
        "cake_name": cake_name,
        "delivery_address": delivery_address,
        "delivery_time": delivery_time,
        "message_card": message_card,
        "status": "已下单",
        "created_at": datetime.now().isoformat()
    }
    data = _load_orders()
    data["orders"].append(order)
    _save_orders(data)
    return order


def order_flower(
    flower_name: str,
    delivery_address: str,
    delivery_time: str,
    message_card: str = ""
) -> dict:
    """鲜花配送下单

    鲜花会配送到指定地址（通常是用餐的餐厅或活动地点）。

    Args:
        flower_name: 鲜花名称
        delivery_address: 配送地址
        delivery_time: 期望送达时间
        message_card: 卡片留言

    Returns:
        订单字典
    """
    order_id = _generate_order_id()
    order = {
        "order_id": order_id,
        "type": "鲜花配送",
        "flower_name": flower_name,
        "delivery_address": delivery_address,
        "delivery_time": delivery_time,
        "message_card": message_card,
        "status": "已下单",
        "created_at": datetime.now().isoformat()
    }
    data = _load_orders()
    data["orders"].append(order)
    _save_orders(data)
    return order


def get_all_orders() -> list[dict]:
    """获取所有历史订单

    Returns:
        订单列表，按创建时间正序
    """
    data = _load_orders()
    return data["orders"]
