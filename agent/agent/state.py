"""Agent 状态定义 - LangGraph 状态图中流转的数据结构

每个节点读取和更新这个状态，状态在节点之间传递，
最终在 Agent 类中跨轮次持久化。
"""
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """LangGraph Agent 的核心状态定义

    所有字段在节点间共享，节点通过返回 dict 的部分字段来更新状态。
    LangGraph 会自动合并更新。
    """

    # ========== 对话相关 ==========
    # 消息历史：记录 Agent 与用户的对话（add_messages 自动追加）
    messages: Annotated[list[BaseMessage], add_messages]

    # 用户当前轮次的原始输入文本
    user_input: str

    # ========== 用户数据 ==========
    # 用户长期偏好（从 data/preferences.json 加载）
    user_preferences: dict

    # ========== 场景与 Skill ==========
    # 场景类型：family(亲子) / friends(朋友) / couple(情侣) / solo(个人)
    scenario: str

    # 当前使用的 Skill 名称，如 "Parent-ChildTravelPlanning"
    skill_used: str

    # ========== 分析结果 ==========
    # analyze_input 节点的 LLM 分析输出
    # 包含 intent, scenario, extracted_info, defaults_applied, confidence
    analysis: dict

    # 应用的智能默认值（人数、预算、位置等）
    defaults_applied: dict

    # ========== 方案与执行 ==========
    # 生成的完整出行方案（包含 timeline、费用、建议等）
    plan: dict

    # 执行节点的下单/预约结果列表
    execution_results: list[dict]

    # ========== 流程控制 ==========
    # 当前流程步骤标识
    # 可能的值：init → analyze → skill_selected → gather_info → plan_generated → wait_confirmation → executed → done
    step: str

    # 总步数计数器（用于限制最大步数，防止死循环）
    step_count: int

    # 是否需要用户确认（方案生成后设为 True，用户确认后设为 False）
    needs_confirmation: bool

    # 是否被打断（用户在方案讨论中加入新信息时设为 True）
    interrupted: bool

    # 打断时用户新加入的信息内容
    new_info: str
