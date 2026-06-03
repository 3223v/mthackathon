"""
移动时间计算模块

功能：
1. Haversine 距离计算（两点间球面距离）
2. 四种交通模式的移动时间估算
3. 根据距离推荐合理交通方式
4. 完整的路由信息计算

交通模式速度设定：
- 步行: 5 km/h（考虑城市步行实际速度）
- 公共交通: 25 km/h（含平均等车/换乘时间）
- 打车: 35 km/h（城市道路平均速度）
- 自驾: 30 km/h（含停车时间）
"""

import math
from typing import Dict, Literal, Optional

# ==================== 交通模式定义 ====================
TransportMode = Literal["walking", "public_transit", "taxi", "driving"]

TRANSPORT_MODES: Dict[str, Dict] = {
    "walking": {
        "speed_kmh": 5.0,
        "label": "步行",
        "icon": "🚶",
        "suitable_distance_m": (0, 1500),       # 适合1.5km以内
        "description": "适用于短距离移动，环保健康",
    },
    "public_transit": {
        "speed_kmh": 25.0,
        "label": "公共交通",
        "icon": "🚌",
        "suitable_distance_m": (1000, 30000),    # 适合1km-30km
        "description": "经济实惠，适合城市内中长距离",
    },
    "taxi": {
        "speed_kmh": 35.0,
        "label": "打车",
        "icon": "🚕",
        "suitable_distance_m": (1500, 50000),    # 适合1.5km-50km
        "description": "快捷方便，点到点直达",
    },
    "driving": {
        "speed_kmh": 30.0,
        "label": "自驾",
        "icon": "🚗",
        "suitable_distance_m": (2000, 100000),   # 适合2km-100km
        "description": "灵活自由，适合家庭/团体出行",
    },
}


# ==================== 距离计算 ====================
def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    使用 Haversine 公式计算两点间的球面距离

    Args:
        lat1: 起点纬度
        lng1: 起点经度
        lat2: 终点纬度
        lng2: 终点经度

    Returns:
        距离（米）
    """
    R = 6371000  # 地球半径（米）

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ==================== 时间计算 ====================
def travel_time_minutes(distance_m: float, mode: TransportMode) -> int:
    """
    根据距离和交通方式计算预计移动时间

    Args:
        distance_m: 距离（米）
        mode: 交通方式

    Returns:
        预计时间（分钟），至少返回 1 分钟
    """
    if mode not in TRANSPORT_MODES:
        raise ValueError(f"不支持的交通方式: {mode}，可选值: {list(TRANSPORT_MODES.keys())}")

    speed_kmh = TRANSPORT_MODES[mode]["speed_kmh"]
    distance_km = distance_m / 1000.0
    time_hours = distance_km / speed_kmh
    time_minutes = time_hours * 60

    # 步行少于 100 米算 1 分钟；其他方式最少 3 分钟（含准备时间）
    if mode == "walking":
        return max(1, round(time_minutes))
    else:
        # 加固定开销：取车/等车/停车时间
        overhead = {
            "public_transit": 8,   # 走到车站+等车
            "taxi": 5,             # 等车时间
            "driving": 8,          # 取车+停车
        }
        base_time = max(3, round(time_minutes))
        return base_time + overhead.get(mode, 0)


# ==================== 交通推荐 ====================
def recommend_transport_mode(
    distance_m: float,
    prefer_modes: Optional[list] = None,
    has_children: bool = False,
    group_size: int = 1,
) -> str:
    """
    根据距离、偏好和情境推荐最合适的交通方式

    推荐策略：
    - < 800m: 步行
    - 800m-2km: 步行/打车
    - 2km-10km: 打车/自驾（有小孩或多人优先自驾）
    - 10km-30km: 公共交通/自驾
    - > 30km: 自驾

    Args:
        distance_m: 距离（米）
        prefer_modes: 用户偏好的交通方式列表
        has_children: 是否有小孩
        group_size: 团体人数

    Returns:
        推荐的交通方式 key
    """
    # 如果用户有明确偏好，优先使用
    if prefer_modes and len(prefer_modes) > 0:
        preferred = prefer_modes[0]
        if preferred in TRANSPORT_MODES:
            return preferred

    # 有小孩或多人出行 → 优先自驾/打车
    if has_children or group_size >= 3:
        if distance_m <= 500:
            return "walking"
        elif distance_m <= 2000:
            return "taxi"
        else:
            return "driving"

    # 单人/双人出行
    if distance_m <= 800:
        return "walking"
    elif distance_m <= 2000:
        return "walking"
    elif distance_m <= 10000:
        return "taxi"
    elif distance_m <= 30000:
        return "public_transit"
    else:
        return "driving"


# ==================== 完整路由计算 ====================
def calculate_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    mode: Optional[TransportMode] = None,
    prefer_modes: Optional[list] = None,
    has_children: bool = False,
    group_size: int = 1,
) -> Dict:
    """
    计算两点间完整路由信息

    Args:
        origin_lat: 起点纬度
        origin_lng: 起点经度
        dest_lat: 终点纬度
        dest_lng: 终点经度
        mode: 指定交通方式（可选，不指定则自动推荐）
        prefer_modes: 用户偏好交通方式
        has_children: 是否有小孩
        group_size: 团体人数

    Returns:
        {
            "distance_m": float,          # 距离（米）
            "distance_km": float,         # 距离（公里）
            "mode": str,                  # 交通方式 key
            "mode_label": str,            # 交通方式中文名
            "mode_icon": str,             # 交通方式图标
            "duration_minutes": int,      # 预计时间（分钟）
            "duration_display": str,      # 时间展示（如 "15分钟"）
        }
    """
    distance_m = haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)

    if mode is None:
        mode = recommend_transport_mode(
            distance_m,
            prefer_modes=prefer_modes,
            has_children=has_children,
            group_size=group_size,
        )

    duration = travel_time_minutes(distance_m, mode)
    mode_info = TRANSPORT_MODES[mode]

    # 格式化展示
    if duration < 60:
        duration_display = f"{duration}分钟"
    else:
        hours = duration // 60
        mins = duration % 60
        duration_display = f"{hours}小时{mins}分钟" if mins > 0 else f"{hours}小时"

    return {
        "distance_m": round(distance_m, 0),
        "distance_km": round(distance_m / 1000, 2),
        "mode": mode,
        "mode_label": mode_info["label"],
        "mode_icon": mode_info["icon"],
        "duration_minutes": duration,
        "duration_display": duration_display,
    }


# ==================== 便捷函数 ====================
def calculate_all_routes(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> Dict[str, Dict]:
    """
    计算所有交通方式的路线信息，用于对比

    Returns:
        {mode: route_info, ...}
    """
    results = {}
    for mode in TRANSPORT_MODES:
        results[mode] = calculate_route(
            origin_lat, origin_lng,
            dest_lat, dest_lng,
            mode=mode,
        )
    return results
