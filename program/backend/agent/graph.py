"""
Agent 图定义 — LangGraph 工作流 v2

新增能力：
- 真实 LLM token 级流式输出
- 增强日志：记录每个节点的输入/输出和数据流转
- WebSocket 回调注入（通过 config.configurable）

节点流程：
analyze_intent → [general_response | extract_preferences | query_data | replan_*]
extract_preferences → [query_data | END]
query_data → planner → END
replace_activity → END
partial_replan → END
full_replan → query_data → planner → END
"""

import json
import os
import asyncio
from typing import Literal, Optional, Callable, Awaitable, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_openai import ChatOpenAI

from agent.state import AgentState
from agent.nodes import (
    analyze_intent,
    general_response,
    extract_preferences,
    query_data,
    generate_plan,
    replace_activity,
    partial_replan,
    full_replan,
)
from core.skill_loader import skill_loader
from utils import logger, agent_logger

# ==================== 配置路径 ====================
LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/llm_config.json")

# 流式回调类型
StreamCallback = Optional[Callable[[str], Awaitable[None]]]


# ==================== LLM 管理器（支持流式） ====================
class LLMManager:
    """LLM管理器 — 多LLM轮询 + 自动重试 + token级流式输出"""

    def __init__(self, configs: list):
        self.configs = configs
        self.current_index = 0
        self.retry_count = 3
        self.retry_delay = 2
        self.llms = []
        self._init_llms()

    def _init_llms(self):
        for i, config in enumerate(self.configs):
            api_key = config.get("api_key")
            if not api_key or api_key.strip() == "":
                logger.warning(f"LLM #{i+1} ({config.get('name', '?')}) API密钥未配置，跳过")
                continue
            try:
                llm = ChatOpenAI(
                    model=config.get("model", "gpt-4o"),
                    base_url=config.get("base_url"),
                    api_key=api_key,
                    temperature=config.get("temperature", 0.7),
                    max_tokens=config.get("max_tokens", 4096),
                    streaming=True,
                    max_retries=0,
                )
                self.llms.append({"llm": llm, "config": config})
                logger.info(f"LLM #{i+1} 初始化成功 | name={config.get('name')} | model={config.get('model')}")
            except Exception as e:
                logger.error(f"LLM #{i+1} 初始化失败 | error={str(e)}")

        if not self.llms:
            logger.error("没有可用的LLM配置！")

    def _get_next_llm(self):
        if not self.llms:
            return None, None
        llm_info = self.llms[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.llms)
        return llm_info["llm"], llm_info["config"]

    async def invoke(self, messages: list, stream_callback: StreamCallback = None) -> str:
        """
        调用LLM，支持流式输出

        Args:
            messages: 消息列表
            stream_callback: 流式回调 async fn(token: str) -> None

        Returns:
            完整的响应文本
        """
        if not self.llms:
            raise ValueError("没有可用的LLM配置！")

        last_error = None

        for attempt in range(self.retry_count):
            llm, config = self._get_next_llm()
            if llm is None:
                raise ValueError("没有可用的LLM配置")

            try:
                llm_name = config.get("name", "?")
                logger.info(f"LLM调用 [{llm_name}] | attempt={attempt+1} | streaming={stream_callback is not None}")
                agent_logger.llm_invoking("stream")

                if stream_callback:
                    # 流式模式：逐 token 输出
                    full_text = ""
                    async for chunk in llm.astream(messages):
                        if chunk.content:
                            full_text += chunk.content
                            await stream_callback(chunk.content)
                    logger.info(f"LLM [{llm_name}] 流式完成 | length={len(full_text)}")
                    return full_text
                else:
                    # 非流式模式
                    response = await llm.ainvoke(messages)
                    content = response.content if hasattr(response, 'content') else str(response)
                    logger.info(f"LLM [{llm_name}] 调用成功 | length={len(content)}")
                    return content

            except Exception as e:
                logger.error(f"LLM [{config.get('name', '?')}] 失败 | error={str(e)}")
                last_error = e
                if attempt < self.retry_count - 1:
                    logger.info(f"等待 {self.retry_delay}s 后重试...")
                    await asyncio.sleep(self.retry_delay)
                    self.retry_delay *= 1.5

        raise Exception(f"所有LLM调用均失败: {str(last_error)}")

    async def invoke_with_logging(
        self,
        system_prompt: str,
        user_prompt: str,
        stream_callback: StreamCallback = None,
        log_prefix: str = "",
    ) -> str:
        """
        带日志的 LLM 调用，记录完整的 system/user prompt 和响应
        """
        logger.info(f"{'='*40}")
        logger.info(f"{log_prefix} | LLM调用开始")
        logger.info(f"System prompt length: {len(system_prompt)} chars")
        logger.info(f"User prompt length: {len(user_prompt)} chars")
        logger.debug(f"System prompt preview: {system_prompt[:500]}...")
        logger.debug(f"User prompt preview: {user_prompt[:500]}...")

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        result = await self.invoke(messages, stream_callback=stream_callback)

        logger.info(f"{log_prefix} | LLM响应 length={len(result)}")
        logger.debug(f"Response preview: {result[:500]}...")
        logger.info(f"{'='*40}")

        return result

    def has_llms(self):
        return len(self.llms) > 0


# ==================== 初始化 ====================
logger.info("=" * 60)
logger.info("Agent 系统 v2 初始化中...")
logger.info("=" * 60)

logger.info("加载 LLM 配置...")
with open(LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
    llm_config_list = json.load(f)

logger.info("初始化 LLM 管理器...")
llm_manager = LLMManager(llm_config_list)

if not llm_manager.has_llms():
    logger.error("警告：没有可用的LLM配置！")

logger.info("加载 Skills...")
skills = skill_loader.load_all()
logger.info(f"Skills 加载完成: {len(skills)} 个 ({[s['id'] for s in skills]})")


# ==================== 节点包装（带流式回调 + 增强日志） ====================

def _get_stream_callback(config: RunnableConfig) -> StreamCallback:
    """从 config 中提取 WebSocket 流式回调"""
    if config and "configurable" in config:
        return config["configurable"].get("stream_callback")
    return None


async def node_analyze_intent(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    logger.info(f"[节点: analyze_intent] 输入: messages_count={len(state.get('messages', []))}")
    result = analyze_intent(state)
    logger.info(f"[节点: analyze_intent] 输出: intent={result.get('intent_type')} | skill={result.get('skill_context', {}).get('id', 'None') if result.get('skill_context') else 'None'}")
    return result


async def node_general_response(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    logger.info(f"[节点: general_response] 输入: intent={state.get('intent_type')}")
    result = general_response(state)
    logger.info(f"[节点: general_response] 输出: response_length={len(result.get('messages', [{}])[0].content) if result.get('messages') else 0}")
    return result


async def node_extract_preferences(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    logger.info(f"[节点: extract_preferences] 输入: has_profile={bool(state.get('user_profile'))}")
    result = extract_preferences(state)
    profile = result.get("user_profile", {})
    logger.info(f"[节点: extract_preferences] 输出: diet={profile.get('diet_preferences')} | budget={profile.get('budget_range')} | relationships={len(profile.get('social_relationships', []))}")
    return result


async def node_query_data(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    logger.info(f"[节点: query_data] 输入: skill={state.get('skill_context', {}).get('id', 'None') if state.get('skill_context') else 'None'} | filters_ready={bool(state.get('skill_context'))}")
    result = query_data(state)
    qr = result.get("query_results", {})
    total = sum(len(v) for v in qr.values())
    logger.info(f"[节点: query_data] 输出: total_items={total} | attractions={len(qr.get('attractions', []))} | restaurants={len(qr.get('restaurants', []))} | activities={len(qr.get('activities', []))}")
    return result


async def node_planner(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """规划生成 — 流式输出到前端"""
    logger.info(f"[节点: planner] 输入: plan_empty={not state.get('plan')} | query_items={sum(len(v) for v in state.get('query_results', {}).values())}")

    if not llm_manager.has_llms():
        return {"messages": [AIMessage(content="抱歉，当前没有可用的 LLM 服务。")]}

    stream_cb = _get_stream_callback(config)
    result = await generate_plan(state, llm_manager, stream_callback=stream_cb)

    plan = result.get("plan", [])
    logger.info(f"[节点: planner] 输出: plan_length={len(plan)} | plan_id={result.get('plan_id')} | activities={[a.get('name', '?') for a in plan]}")
    if plan:
        logger.debug(f"[节点: planner] Plan JSON:\n{json.dumps(plan, ensure_ascii=False, indent=2)}")
    return result


async def node_replace_activity(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """替换单活动"""
    target = state.get("replan_target", {})
    plan = state.get("plan", [])
    logger.info(f"[节点: replace_activity] 输入: plan_length={len(plan)} | target={target.get('target_description', '?')[:50]}")

    if not llm_manager.has_llms():
        return {"messages": [AIMessage(content="抱歉，当前没有可用的 LLM 服务。")]}

    stream_cb = _get_stream_callback(config)
    result = await replace_activity(state, llm_manager, stream_callback=stream_cb)

    new_plan = result.get("plan", [])
    logger.info(f"[节点: replace_activity] 输出: new_plan_length={len(new_plan)}")
    return result


async def node_partial_replan(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """部分重规划"""
    target = state.get("replan_target", {})
    logger.info(f"[节点: partial_replan] 输入: plan_length={len(state.get('plan', []))} | start_after_index={target.get('start_after_index')}")

    if not llm_manager.has_llms():
        return {"messages": [AIMessage(content="抱歉，当前没有可用的 LLM 服务。")]}

    stream_cb = _get_stream_callback(config)
    result = await partial_replan(state, llm_manager, stream_callback=stream_cb)

    new_plan = result.get("plan", [])
    logger.info(f"[节点: partial_replan] 输出: new_plan_length={len(new_plan)}")
    return result


async def node_full_replan(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """全量重规划"""
    logger.info(f"[节点: full_replan] 输入: old_plan_length={len(state.get('plan', []))}")
    result = await full_replan(state, llm_manager)
    logger.info(f"[节点: full_replan] 输出: intent={result.get('intent_type')} | plan_cleared={not result.get('plan')}")
    return result


# ==================== 路由函数 ====================

def route_after_intent(state: AgentState) -> Literal[
    "general_response", "extract_preferences", "query_data",
    "replace_activity", "partial_replan", "full_replan",
]:
    intent_type = state.get("intent_type", "general")
    routes = {
        "general": "general_response",
        "preferences": "extract_preferences",
        "planning": "extract_preferences",
        "replan_full": "query_data",
        "replan_replace": "replace_activity",
        "replan_partial": "partial_replan",
    }
    target = routes.get(intent_type, "general_response")
    logger.info(f"[路由] analyze_intent → {target} (intent={intent_type})")
    return target


def route_after_preferences(state: AgentState) -> Literal["query_data", "END"]:
    intent_type = state.get("intent_type", "general")
    if intent_type == "planning":
        logger.info(f"[路由] extract_preferences → query_data")
        return "query_data"
    logger.info(f"[路由] extract_preferences → END")
    return END


def route_after_full_replan(state: AgentState) -> Literal["query_data", "END"]:
    if state.get("intent_type") == "planning":
        logger.info(f"[路由] full_replan → query_data")
        return "query_data"
    return END


# ==================== 图构建 ====================

def build_graph():
    """构建 Agent 图 v2"""
    logger.info("开始构建 Agent 图 v2...")

    workflow = StateGraph(AgentState)

    # 注册所有节点
    nodes = [
        ("analyze_intent", node_analyze_intent),
        ("general_response", node_general_response),
        ("extract_preferences", node_extract_preferences),
        ("query_data", node_query_data),
        ("planner", node_planner),
        ("replace_activity", node_replace_activity),
        ("partial_replan", node_partial_replan),
        ("full_replan", node_full_replan),
    ]
    for name, func in nodes:
        workflow.add_node(name, func)

    # 入口
    workflow.set_entry_point("analyze_intent")

    # 路由
    workflow.add_conditional_edges("analyze_intent", route_after_intent, {
        "general_response": "general_response",
        "extract_preferences": "extract_preferences",
        "query_data": "query_data",
        "replace_activity": "replace_activity",
        "partial_replan": "partial_replan",
        "full_replan": "full_replan",
    })
    workflow.add_edge("general_response", END)
    workflow.add_conditional_edges("extract_preferences", route_after_preferences, {
        "query_data": "query_data", END: END,
    })
    workflow.add_edge("query_data", "planner")
    workflow.add_edge("planner", END)
    workflow.add_edge("replace_activity", END)
    workflow.add_edge("partial_replan", END)
    workflow.add_conditional_edges("full_replan", route_after_full_replan, {
        "query_data": "query_data", END: END,
    })

    checkpointer = MemorySaver()
    compiled_graph = workflow.compile(checkpointer=checkpointer)

    logger.info("Agent 图 v2 构建完成（8节点 + 流式LLM + 增强日志）")
    return compiled_graph


__all__ = ["build_graph", "llm_manager", "LLMManager"]
