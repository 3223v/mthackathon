"""
执行工具集 — 执行预订、下单等操作（需要用户确认）

所有操作通过 mockfunction 层进行，预订结果写入运行时存储。
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from mockfunction import (
    book_restaurant,
    book_ticket,
    order_delivery,
    save_user_preferences,
    get_user_preferences,
)
from utils import logger


class ExecuteTools:
    """执行工具集 — 预订、下单、偏好保存"""

    def __init__(self):
        self.pending_orders = {}

    # ==================== 预订 ====================

    def book_restaurant(
        self,
        restaurant_id: str,
        date: str,
        time: str,
        people: int,
        customer_name: str = "用户",
        phone: str = "",
        plan_id: str = "",
    ) -> Dict[str, Any]:
        """
        预订餐厅桌位

        Args:
            restaurant_id: 餐厅ID
            date: 日期 (YYYY-MM-DD)
            time: 时间 (HH:MM)
            people: 用餐人数
            customer_name: 客户姓名
            phone: 联系电话
            plan_id: 关联方案ID

        Returns:
            预订结果
        """
        logger.info(f"预订餐厅 | restaurant_id={restaurant_id} | date={date} | time={time} | people={people}")
        result = book_restaurant(restaurant_id, date, time, people, customer_name, phone)

        if result.get("code") == 0:
            booking_id = result["data"]["booking_id"]
            self.pending_orders[booking_id] = {
                **result["data"],
                "plan_id": plan_id,
                "type": "restaurant",
            }

        return result

    def book_ticket(
        self,
        attraction_id: str,
        ticket_type: str,
        quantity: int,
        date: str,
        customer_name: str = "用户",
        plan_id: str = "",
    ) -> Dict[str, Any]:
        """
        购买门票

        Args:
            attraction_id: 景点ID
            ticket_type: 票种
            quantity: 数量
            date: 日期
            customer_name: 客户姓名
            plan_id: 关联方案ID

        Returns:
            购票结果
        """
        logger.info(f"购买门票 | attraction_id={attraction_id} | type={ticket_type} | qty={quantity}")
        result = book_ticket(attraction_id, ticket_type, quantity, date, customer_name)

        if result.get("code") == 0:
            order_id = result["data"]["order_id"]
            self.pending_orders[order_id] = {
                **result["data"],
                "plan_id": plan_id,
                "type": "ticket",
            }

        return result

    def order_delivery(
        self,
        item_type: str,
        item_id: str,
        address: str,
        scheduled_time: str,
        note: str = "",
        plan_id: str = "",
    ) -> Dict[str, Any]:
        """
        订购配送服务（蛋糕/鲜花）

        Args:
            item_type: 商品类型 (cake/flower)
            item_id: 商品ID
            address: 配送地址
            scheduled_time: 预计送达时间
            note: 备注
            plan_id: 关联方案ID

        Returns:
            下单结果
        """
        logger.info(f"订购配送 | type={item_type} | item_id={item_id} | address={address}")
        result = order_delivery(item_type, item_id, address, scheduled_time, note)

        if result.get("code") == 0:
            delivery_id = result["data"]["delivery_id"]
            self.pending_orders[delivery_id] = {
                **result["data"],
                "plan_id": plan_id,
                "type": "delivery",
            }

        return result

    # ==================== 订单管理 ====================

    def confirm_order(self, order_id: str) -> Dict[str, Any]:
        """确认订单"""
        if order_id not in self.pending_orders:
            return {"status": "error", "message": f"未找到订单: {order_id}"}

        self.pending_orders[order_id]["status"] = "confirmed"
        return {
            "status": "success",
            "message": f"订单已确认: {order_id}",
            "order": self.pending_orders[order_id],
        }

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """取消订单"""
        if order_id not in self.pending_orders:
            return {"status": "error", "message": f"未找到订单: {order_id}"}

        del self.pending_orders[order_id]
        return {"status": "success", "message": f"订单已取消: {order_id}"}

    def get_pending_orders(self, plan_id: str = None) -> List[Dict[str, Any]]:
        """获取待确认订单列表"""
        orders = list(self.pending_orders.values())
        if plan_id:
            orders = [o for o in orders if o.get("plan_id") == plan_id]
        return orders

    def confirm_plan(self, plan_id: str) -> bool:
        """确认方案"""
        # 确认方案下所有订单
        for order_id, order in self.pending_orders.items():
            if order.get("plan_id") == plan_id:
                order["status"] = "confirmed"
        return True

    # ==================== 用户偏好 ====================

    def save_preferences(
        self,
        user_id: str,
        preferences: str,
        family_info: Optional[Dict[str, Any]] = None,
        friends_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        保存用户偏好设置

        Args:
            user_id: 用户ID
            preferences: 偏好描述文本
            family_info: 家庭信息
            friends_info: 朋友信息

        Returns:
            保存结果
        """
        logger.info(f"保存偏好 | user_id={user_id}")
        return save_user_preferences(
            user_id=user_id,
            preferences=preferences,
            family_info=family_info,
            friends_info=friends_info,
        )

    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """获取用户偏好"""
        return get_user_preferences(user_id)

    def update_family_info(self, user_id: str, family_info: Dict[str, Any]) -> Dict[str, Any]:
        """更新家庭信息"""
        return self.save_preferences(user_id, "", family_info=family_info)

    def update_friends_info(self, user_id: str, friends_info: Dict[str, Any]) -> Dict[str, Any]:
        """更新朋友信息"""
        return self.save_preferences(user_id, "", friends_info=friends_info)
