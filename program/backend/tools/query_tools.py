"""LangGraph工具 - 查询层

此模块包含用于查询各种数据的工具函数，供Agent在对话中调用。
查询操作不需要用户审批，可以直接调用mock数据。
"""

from typing import List, Dict, Any, Optional
from mock import mock_accessor

class QueryTools:
    """查询工具集 - 用于查询景点、餐厅、配送服务等数据"""

    def query_attractions(self, 
                        family_friendly: Optional[bool] = None,
                        kids_friendly: Optional[bool] = None,
                        group_friendly: Optional[bool] = None,
                        romantic: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        查询景点列表
        
        Args:
            family_friendly: 是否适合亲子
            kids_friendly: 是否适合儿童
            group_friendly: 是否适合团体
            romantic: 是否适合约会
        
        Returns:
            景点列表
        """
        filters = {}
        if family_friendly is not None:
            filters["family_friendly"] = family_friendly
        if kids_friendly is not None:
            filters["kids_friendly"] = kids_friendly
        if group_friendly is not None:
            filters["group_friendly"] = group_friendly
        if romantic is not None:
            filters["romantic"] = romantic
        
        return mock_accessor.get_attractions(**filters)

    def query_restaurants(self,
                        family_friendly: Optional[bool] = None,
                        kids_friendly: Optional[bool] = None,
                        group_friendly: Optional[bool] = None,
                        romantic: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        查询餐厅列表
        
        Args:
            family_friendly: 是否适合亲子
            kids_friendly: 是否适合儿童
            group_friendly: 是否适合聚餐
            romantic: 是否适合约会
        
        Returns:
            餐厅列表
        """
        filters = {}
        if family_friendly is not None:
            filters["family_friendly"] = family_friendly
        if kids_friendly is not None:
            filters["kids_friendly"] = kids_friendly
        if group_friendly is not None:
            filters["group_friendly"] = group_friendly
        if romantic is not None:
            filters["romantic"] = romantic
        
        return mock_accessor.get_restaurants(**filters)

    def query_family_friendly(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        查询亲子友好的景点和餐厅
        
        Returns:
            包含景点和餐厅的字典
        """
        return mock_accessor.get_family_friendly_places()

    def query_group_friendly(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        查询团体友好的景点和餐厅
        
        Returns:
            包含景点和餐厅的字典
        """
        return mock_accessor.get_group_friendly_places()

    def query_romantic(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        查询浪漫的景点和餐厅
        
        Returns:
            包含景点和餐厅的字典
        """
        return mock_accessor.get_romantic_places()

    def get_attraction_by_id(self, attraction_id: str) -> Dict[str, Any]:
        """
        根据ID获取景点详情
        
        Args:
            attraction_id: 景点ID
        
        Returns:
            景点详情
        """
        return mock_accessor.get_attraction_by_id(attraction_id)

    def get_restaurant_by_id(self, restaurant_id: str) -> Dict[str, Any]:
        """
        根据ID获取餐厅详情
        
        Args:
            restaurant_id: 餐厅ID
        
        Returns:
            餐厅详情
        """
        return mock_accessor.get_restaurant_by_id(restaurant_id)

    def get_cakes(self) -> List[Dict[str, Any]]:
        """
        获取可用蛋糕列表
        
        Returns:
            蛋糕列表
        """
        return mock_accessor.get_cakes()

    def get_flowers(self) -> List[Dict[str, Any]]:
        """
        获取可用鲜花列表
        
        Returns:
            鲜花列表
        """
        return mock_accessor.get_flowers()

    def recommend_by_scenario(self, scenario: str) -> Dict[str, Any]:
        """
        根据场景推荐景点和餐厅
        
        Args:
            scenario: 场景类型 (family/friends/couple)
        
        Returns:
            推荐结果
        """
        return mock_accessor.recommend_by_scenario(scenario)
