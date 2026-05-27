"""Mock数据操作模块

此模块提供mock数据的查询接口，供tools层调用。
"""

import json
import os
from typing import List, Dict, Any, Optional

DATA_PATH = os.path.join(os.path.dirname(__file__), "../mockdata/mock_data.json")

class MockDataAccessor:
    """Mock数据访问器"""

    def __init__(self):
        self.data = self._load_data()

    def _load_data(self) -> dict:
        """加载mock数据"""
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"警告：未找到mock数据文件: {DATA_PATH}")
            return {"attractions": [], "restaurants": [], "delivery": {"cakes": [], "flowers": []}}

    def get_attractions(self, **filters) -> List[Dict[str, Any]]:
        """查询景点"""
        attractions = self.data.get("attractions", [])
        
        if "family_friendly" in filters:
            attractions = [a for a in attractions if a.get("family_friendly") == filters["family_friendly"]]
        if "kids_friendly" in filters:
            attractions = [a for a in attractions if a.get("kids_friendly") == filters["kids_friendly"]]
        if "group_friendly" in filters:
            attractions = [a for a in attractions if a.get("group_friendly") == filters["group_friendly"]]
        if "romantic" in filters:
            attractions = [a for a in attractions if a.get("romantic") == filters["romantic"]]

        return attractions

    def get_attraction_by_id(self, attraction_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取景点"""
        attractions = self.data.get("attractions", [])
        return next((a for a in attractions if a.get("id") == attraction_id), None)

    def get_restaurants(self, **filters) -> List[Dict[str, Any]]:
        """查询餐厅"""
        restaurants = self.data.get("restaurants", [])
        
        if "family_friendly" in filters:
            restaurants = [r for r in restaurants if r.get("family_friendly") == filters["family_friendly"]]
        if "kids_friendly" in filters:
            restaurants = [r for r in restaurants if r.get("kids_friendly") == filters["kids_friendly"]]
        if "group_friendly" in filters:
            restaurants = [r for r in restaurants if r.get("group_friendly") == filters["group_friendly"]]
        if "romantic" in filters:
            restaurants = [r for r in restaurants if r.get("romantic") == filters["romantic"]]

        return restaurants

    def get_restaurant_by_id(self, restaurant_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取餐厅"""
        restaurants = self.data.get("restaurants", [])
        return next((r for r in restaurants if r.get("id") == restaurant_id), None)

    def get_cakes(self) -> List[Dict[str, Any]]:
        """获取蛋糕列表"""
        return self.data.get("delivery", {}).get("cakes", [])

    def get_flowers(self) -> List[Dict[str, Any]]:
        """获取鲜花列表"""
        return self.data.get("delivery", {}).get("flowers", [])

    def get_family_friendly_places(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取亲子友好的景点和餐厅"""
        return {
            "attractions": self.get_attractions(family_friendly=True),
            "restaurants": self.get_restaurants(family_friendly=True),
            "scenario": "亲子出行"
        }

    def get_group_friendly_places(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取团体友好的景点和餐厅"""
        return {
            "attractions": self.get_attractions(group_friendly=True),
            "restaurants": self.get_restaurants(group_friendly=True),
            "scenario": "朋友聚会"
        }

    def get_romantic_places(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取浪漫的景点和餐厅"""
        return {
            "attractions": self.get_attractions(romantic=True),
            "restaurants": self.get_restaurants(romantic=True),
            "scenario": "情侣约会"
        }

    def recommend_by_scenario(self, scenario: str) -> Dict[str, Any]:
        """根据场景推荐"""
        if scenario == "family":
            return self.get_family_friendly_places()
        elif scenario == "friends":
            return self.get_group_friendly_places()
        elif scenario == "couple":
            return self.get_romantic_places()
        return {"error": f"未知场景: {scenario}"}

mock_accessor = MockDataAccessor()

__all__ = ["MockDataAccessor", "mock_accessor"]
