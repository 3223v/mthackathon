"""
查询工具集 — 通过 mockfunction 层查询景点、餐厅、活动等数据

所有数据访问必须通过 mockfunction 模块，不直接读取 JSON 文件。
"""

from typing import List, Dict, Any, Optional
from mockfunction import (
    get_nearby_attractions,
    get_nearby_restaurants,
    get_nearby_activities,
    get_nearby_cafes,
    get_nearby_shops,
    get_nearby_groceries,
    get_nearby_others,
    check_restaurant_availability,
    check_activity_availability,
    get_restaurant_menu,
    get_delivery_items,
    recommend_by_scenario,
    get_family_friendly_places,
    get_group_friendly_places,
    get_romantic_places,
)


class QueryTools:
    """查询工具集 — 查询景点、餐厅、配送服务等数据"""

    # ==================== 附近查询 ====================

    def query_nearby_attractions(
        self,
        lat: float = 39.9042,
        lng: float = 116.4074,
        radius: int = 5000,
        tags: List[str] = None,
        suitable_for: List[str] = None,
    ) -> Dict[str, Any]:
        """查询附近景点"""
        return get_nearby_attractions(
            lat=lat, lng=lng, radius=radius,
            tags=tags, suitable_for=suitable_for,
        )

    def query_nearby_restaurants(
        self,
        lat: float = 39.9042,
        lng: float = 116.4074,
        radius: int = 3000,
        cuisine: str = None,
        suitable_for: List[str] = None,
    ) -> Dict[str, Any]:
        """查询附近餐厅"""
        return get_nearby_restaurants(
            lat=lat, lng=lng, radius=radius,
            cuisine=cuisine, suitable_for=suitable_for,
        )

    def query_nearby_activities(
        self,
        lat: float = 39.9042,
        lng: float = 116.4074,
        radius: int = 5000,
        suitable_for: List[str] = None,
    ) -> Dict[str, Any]:
        """查询附近额外活动（密室、展览等）"""
        return get_nearby_activities(
            lat=lat, lng=lng, radius=radius,
            suitable_for=suitable_for,
        )

    def query_nearby_cafes(
        self,
        lat: float = 39.9042,
        lng: float = 116.4074,
        radius: int = 2000,
        suitable_for: List[str] = None,
    ) -> Dict[str, Any]:
        """查询附近饮品店"""
        return get_nearby_cafes(
            lat=lat, lng=lng, radius=radius,
            suitable_for=suitable_for,
        )

    # ==================== 场景推荐 ====================

    def query_family_friendly(self, lat: float = 39.9042, lng: float = 116.4074) -> Dict[str, Any]:
        """查询亲子友好场所"""
        return get_family_friendly_places(lat=lat, lng=lng)

    def query_group_friendly(self, lat: float = 39.9042, lng: float = 116.4074) -> Dict[str, Any]:
        """查询团体友好场所"""
        return get_group_friendly_places(lat=lat, lng=lng)

    def query_romantic(self, lat: float = 39.9042, lng: float = 116.4074) -> Dict[str, Any]:
        """查询浪漫场所"""
        return get_romantic_places(lat=lat, lng=lng)

    def recommend_by_scenario(self, scenario: str, lat: float = 39.9042, lng: float = 116.4074) -> Dict[str, Any]:
        """根据场景推荐"""
        return recommend_by_scenario(scenario, lat=lat, lng=lng)

    # ==================== 综合查询 ====================

    def query_by_filters(
        self,
        lat: float = 39.9042,
        lng: float = 116.4074,
        filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        根据过滤器综合查询所有相关数据

        Args:
            lat: 纬度
            lng: 经度
            filters: {
                "attractions": {"suitable_for": [...], "tags": [...]},
                "restaurants": {"suitable_for": [...], "cuisine": "..."},
                "activities": {"suitable_for": [...]},
                "cafes": {"suitable_for": [...]},
            }

        Returns:
            {
                "attractions": [...],
                "restaurants": [...],
                "activities": [...],
                "cafes": [...],
            }
        """
        if filters is None:
            filters = {}

        result = {}

        # 景点（半径20km覆盖北京主城区）
        attr_filter = filters.get("attractions", {})
        attr_result = get_nearby_attractions(
            lat=lat, lng=lng, radius=20000,
            suitable_for=attr_filter.get("suitable_for"),
            tags=attr_filter.get("tags"),
        )
        result["attractions"] = attr_result.get("data", [])

        # 餐厅（半径15km）
        rest_filter = filters.get("restaurants", {})
        rest_result = get_nearby_restaurants(
            lat=lat, lng=lng, radius=15000,
            suitable_for=rest_filter.get("suitable_for"),
            cuisine=rest_filter.get("cuisine"),
        )
        result["restaurants"] = rest_result.get("data", [])

        # 活动（半径15km）
        act_filter = filters.get("activities", {})
        act_result = get_nearby_activities(
            lat=lat, lng=lng, radius=15000,
            suitable_for=act_filter.get("suitable_for"),
        )
        result["activities"] = act_result.get("data", [])

        # 饮品（半径10km）
        cafe_filter = filters.get("cafes", {})
        cafe_result = get_nearby_cafes(
            lat=lat, lng=lng, radius=10000,
            suitable_for=cafe_filter.get("suitable_for"),
        )
        result["cafes"] = cafe_result.get("data", [])

        return result

    # ==================== 可用性查询 ====================

    def check_restaurant_available(
        self, restaurant_id: str, date: str, time: str, people: int
    ) -> Dict[str, Any]:
        """检查餐厅可用性"""
        return check_restaurant_availability(restaurant_id, date, time, people)

    def check_activity_available(
        self, activity_id: str, date: str, time: str
    ) -> Dict[str, Any]:
        """检查活动可用性"""
        return check_activity_availability(activity_id, date, time)

    # ==================== 详情查询 ====================

    def get_menu(self, restaurant_id: str, suitable_for: List[str] = None) -> Dict[str, Any]:
        """获取餐厅菜单"""
        return get_restaurant_menu(restaurant_id, suitable_for=suitable_for)

    def get_delivery(self, restaurant_id: str) -> Dict[str, Any]:
        """获取可配送商品"""
        return get_delivery_items(restaurant_id)
