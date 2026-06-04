"""
Agent 状态定义

AgentState 是 LangGraph 图中流转的核心状态对象。
每个节点函数接收 state 并返回部分更新（partial update），
LangGraph 自动合并。

关键字段说明：
- messages: 对话消息历史（operator.add 自动追加）
- intent_type: 意图分类结果，决定路由
- skill_context: 匹配到的 Skill 完整内容
- plan: 当前规划方案（JSON 数组）
- replan_target: 重规划目标信息
- user_profile: 从对话中提取的结构化用户画像
"""

from typing import TypedDict, Annotated, Sequence, Dict, Any, List, Optional
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """Agent 核心状态"""

    # === 对话 ===
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # === 用户画像 ===
    preferences: str                                   # 用户偏好文本（原始）
    user_profile: Dict[str, Any]                       # 结构化用户画像

    # === 意图与技能 ===
    intent_type: str                                   # 意图类型
    skill_context: Optional[Dict[str, Any]]            # 匹配到的 Skill 完整内容

    # === 规划方案 ===
    plan: List[Dict[str, Any]]                         # 当前规划（JSON 数组）
    plan_id: str                                       # 方案 ID
    query_results: Dict[str, Any]                      # 查询到的候选数据

    # === 重规划 ===
    replan_target: Dict[str, Any]                      # 重规划目标

    # === 中断 ===
    interrupted: bool                                  # 是否被中断
    interrupt_info: str                                # 中断补充信息

    # === 会话 ===
    conversation_id: str                               # 会话 ID
    context: Dict[str, Any]                            # 额外上下文

    # === 校验与重试 ===
    planner_parse_failed: bool                         # planner JSON 解析是否失败
    planner_raw_response: str                          # planner 原始响应文本（用于重试时注入提示）
