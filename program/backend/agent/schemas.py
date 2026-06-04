"""
结构化输出 Schema 定义

为 LLM 调用提供精确的输出结构约束，支持：
- Layer 1: Native json_schema + strict=True（OpenAI 原生结构化输出）
- Layer 2: Function Calling + tool_choice="required"
- Layer 3: 文本解析 + 重试保底
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ==================== 规划输出 Schema ====================

class TimeSlot(BaseModel):
    start: str = Field(description="开始时间，格式 HH:MM，如 09:00")
    end: str = Field(description="结束时间，格式 HH:MM，如 11:00")


class Location(BaseModel):
    lat: float = Field(description="纬度")
    lng: float = Field(description="经度")
    address: Optional[str] = Field(default="", description="地址描述")


class ActivityDetails(BaseModel):
    rating: Optional[float] = Field(default=None, description="评分")
    price: Optional[float] = Field(default=None, description="价格（元）")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    description: Optional[str] = Field(default="", description="一句话描述")


class PreBook(BaseModel):
    need: bool = Field(default=False, description="是否需要预订")
    type: Optional[str] = Field(default="", description="预订类型: ticket/restaurant/activity")
    item: Optional[str] = Field(default="", description="预订项描述")


class DeliverySync(BaseModel):
    item: str = Field(default="", description="配送品名")
    to_address: str = Field(default="", description="配送地址")
    order_ahead_min: int = Field(default=60, description="提前下单分钟数")


class TransportFromPrev(BaseModel):
    mode: str = Field(default="", description="交通方式: walking/taxi/public_transit/driving")
    mode_label: str = Field(default="", description="交通方式中文")
    duration_min: int = Field(default=0, description="预计耗时（分钟）")
    distance_m: float = Field(default=0, description="距离（米）")


class PlanActivity(BaseModel):
    """单个活动/交通节点的输出结构"""
    order: int = Field(description="序号，从1开始")
    time_slot: TimeSlot = Field(description="时间段")
    activity_type: str = Field(description="活动类型: attraction/restaurant/activity/cafe/free_time")
    name: str = Field(description="活动名称（必须从可用数据中选取）")
    item_id: str = Field(description="数据中的ID")
    location: Location = Field(description="位置信息")
    duration_hours: float = Field(default=1.0, description="预计时长（小时）")
    details: ActivityDetails = Field(default_factory=ActivityDetails, description="详情")
    transport_from_prev: Optional[TransportFromPrev] = Field(default=None, description="从上一个活动的交通信息")
    pre_book: PreBook = Field(default_factory=PreBook, description="预订信息")
    delivery_sync: Optional[DeliverySync] = Field(default=None, description="配送同步信息")
    notes: Optional[str] = Field(default="", description="备注建议")


class PlanOutput(BaseModel):
    """规划方案完整输出"""
    activities: List[PlanActivity] = Field(description="活动列表")


# ==================== 重规划部分输出 Schema ====================

class PartialReplanOutput(BaseModel):
    """部分重规划输出（只输出新增部分）"""
    activities: List[PlanActivity] = Field(description="新规划的活动列表（不包括保留的）")


# ==================== 意图识别输出 Schema ====================

class IntentOutput(BaseModel):
    """意图识别输出"""
    intent_type: str = Field(description="意图类型: general/planning/preferences/replan_full/replan_replace/replan_partial")
    confidence: float = Field(default=0.8, description="置信度 0-1")
    reason: str = Field(default="", description="判断理由")
    target_index: Optional[int] = Field(default=None, description="重规划目标索引")
    target_description: Optional[str] = Field(default=None, description="重规划目标描述")


# ==================== 替代方案排序输出 ====================

class RankedIndices(BaseModel):
    """替代方案排序输出"""
    indices: List[int] = Field(description="按适配度从高到低排列的序号列表")
