"""Agent模块 — 核心组件

此模块提供：
- AgentState: Agent 核心状态定义
- build_graph: LangGraph 图构建函数
- nodes: 各个处理节点（意图分析、偏好提取、查询、规划、重规划）
"""

from .state import AgentState
from .graph import build_graph, llm_manager

__all__ = ["AgentState", "build_graph", "llm_manager"]
