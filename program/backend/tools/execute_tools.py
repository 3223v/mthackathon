"""LangGraph工具 - 执行层

此模块包含用于执行下单、预订等操作的工具函数。
执行操作需要发送给前端，让用户亲自确认执行。
"""

from typing import Dict, Any, Optional, List

class ExecuteTools:
    """执行工具集 - 用于执行下单、预订等操作"""

    def __init__(self):
        self.pending_orders = {}

    def book_attraction(self,
                       plan_id: str,
                       attraction_name: str,
                       quantity: int = 2,
                       unit_price: float = 0.0) -> Dict[str, Any]:
        """
        创建景点预订请求（需要用户确认）
        
        Args:
            plan_id: 方案ID
            attraction_name: 景点名称
            quantity: 人数
            unit_price: 单价
        
        Returns:
            待确认的订单信息
        """
        order_id = f"order_{plan_id}_{attraction_name[:10]}"
        total_price = quantity * unit_price if unit_price > 0 else "待确认"
        
        pending_order = {
            "order_id": order_id,
            "type": "attraction",
            "plan_id": plan_id,
            "attraction_name": attraction_name,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price,
            "status": "pending",
            "message": f"请确认预订 {attraction_name}，人数: {quantity}人"
        }
        
        self.pending_orders[order_id] = pending_order
        
        return {
            "status": "pending",
            "message": f"需要您确认预订",
            "order": pending_order
        }

    def book_restaurant(self,
                       plan_id: str,
                       restaurant_name: str,
                       party_size: int = 2,
                       scheduled_time: str = "12:00",
                       notes: str = "") -> Dict[str, Any]:
        """
        创建餐厅预订请求（需要用户确认）
        
        Args:
            plan_id: 方案ID
            restaurant_name: 餐厅名称
            party_size: 用餐人数
            scheduled_time: 预订时间
            notes: 备注信息
        
        Returns:
            待确认的预订信息
        """
        order_id = f"order_{plan_id}_{restaurant_name[:10]}"
        
        pending_order = {
            "order_id": order_id,
            "type": "restaurant",
            "plan_id": plan_id,
            "restaurant_name": restaurant_name,
            "party_size": party_size,
            "scheduled_time": scheduled_time,
            "notes": notes,
            "status": "pending",
            "message": f"请确认预订 {restaurant_name}，{party_size}人，时间: {scheduled_time}"
        }
        
        self.pending_orders[order_id] = pending_order
        
        return {
            "status": "pending",
            "message": f"需要您确认预订",
            "order": pending_order
        }

    def order_cake(self,
                  plan_id: str,
                  cake_name: str,
                  delivery_address: str,
                  delivery_time: str,
                  price: float = 0.0) -> Dict[str, Any]:
        """
        创建蛋糕订购请求（需要用户确认）
        
        Args:
            plan_id: 方案ID
            cake_name: 蛋糕名称
            delivery_address: 配送地址
            delivery_time: 配送时间
            price: 价格
        
        Returns:
            待确认的订单信息
        """
        order_id = f"order_{plan_id}_cake_{cake_name[:10]}"
        
        pending_order = {
            "order_id": order_id,
            "type": "cake",
            "plan_id": plan_id,
            "cake_name": cake_name,
            "delivery_address": delivery_address,
            "delivery_time": delivery_time,
            "price": price,
            "status": "pending",
            "message": f"请确认订购 {cake_name}，配送至: {delivery_address}，时间: {delivery_time}"
        }
        
        self.pending_orders[order_id] = pending_order
        
        return {
            "status": "pending",
            "message": f"需要您确认订购",
            "order": pending_order
        }

    def order_flower(self,
                    plan_id: str,
                    flower_name: str,
                    delivery_address: str,
                    delivery_time: str,
                    price: float = 0.0) -> Dict[str, Any]:
        """
        创建鲜花订购请求（需要用户确认）
        
        Args:
            plan_id: 方案ID
            flower_name: 鲜花名称
            delivery_address: 配送地址
            delivery_time: 配送时间
            price: 价格
        
        Returns:
            待确认的订单信息
        """
        order_id = f"order_{plan_id}_flower_{flower_name[:10]}"
        
        pending_order = {
            "order_id": order_id,
            "type": "flower",
            "plan_id": plan_id,
            "flower_name": flower_name,
            "delivery_address": delivery_address,
            "delivery_time": delivery_time,
            "price": price,
            "status": "pending",
            "message": f"请确认订购 {flower_name}，配送至: {delivery_address}，时间: {delivery_time}"
        }
        
        self.pending_orders[order_id] = pending_order
        
        return {
            "status": "pending",
            "message": f"需要您确认订购",
            "order": pending_order
        }

    def confirm_order(self, order_id: str) -> Dict[str, Any]:
        """
        确认订单（用户确认后调用）
        
        Args:
            order_id: 订单ID
        
        Returns:
            订单确认结果
        """
        if order_id not in self.pending_orders:
            return {"status": "error", "message": f"未找到订单: {order_id}"}
        
        order = self.pending_orders[order_id]
        order["status"] = "confirmed"
        
        return {
            "status": "success",
            "message": f"订单已确认: {order.get('message', '')}",
            "order": order
        }

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        取消订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            取消结果
        """
        if order_id not in self.pending_orders:
            return {"status": "error", "message": f"未找到订单: {order_id}"}
        
        del self.pending_orders[order_id]
        
        return {
            "status": "success",
            "message": f"订单已取消: {order_id}"
        }

    def get_pending_orders(self, plan_id: str = None) -> List[Dict[str, Any]]:
        """
        获取待确认订单列表
        
        Args:
            plan_id: 方案ID（可选）
        
        Returns:
            待确认订单列表
        """
        orders = list(self.pending_orders.values())
        if plan_id:
            orders = [o for o in orders if o.get("plan_id") == plan_id]
        return orders

    def confirm_plan(self, plan_id: str) -> bool:
        """
        确认方案（标记方案为已确认）
        
        Args:
            plan_id: 方案ID
        
        Returns:
            是否确认成功
        """
        return True

    def save_preferences(self,
                        user_id: str,
                        preferences: str,
                        family_info: Optional[Dict[str, Any]] = None,
                        friends_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        保存用户偏好设置
        
        Args:
            user_id: 用户ID
            preferences: 偏好描述
            family_info: 家庭信息
            friends_info: 朋友信息
        
        Returns:
            保存结果
        """
        from data_store import DataStore
        store = DataStore()
        
        prefs = store.get_preferences(user_id)
        if not prefs:
            prefs = {
                "user_id": user_id,
                "preferences": preferences,
                "family_info": family_info or {},
                "friends_info": friends_info or {},
                "created_at": str(datetime.now()),
                "updated_at": str(datetime.now())
            }
        else:
            prefs["preferences"] = preferences
            if family_info:
                prefs["family_info"] = family_info
            if friends_info:
                prefs["friends_info"] = friends_info
            prefs["updated_at"] = str(datetime.now())
        
        store.save_preferences(prefs)
        return prefs

    def update_family_info(self, user_id: str, family_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新家庭信息
        
        Args:
            user_id: 用户ID
            family_info: 家庭信息
        
        Returns:
            更新后的偏好信息
        """
        return self.save_preferences(user_id, "", family_info=family_info)

    def update_friends_info(self, user_id: str, friends_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新朋友信息
        
        Args:
            user_id: 用户ID
            friends_info: 朋友信息
        
        Returns:
            更新后的偏好信息
        """
        return self.save_preferences(user_id, "", friends_info=friends_info)
