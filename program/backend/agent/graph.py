"""LangGraph Agent系统 - 简化版

只保存聊天历史和用户偏好信息。
执行操作需要用户确认。
"""

import json
import os
import random
import time
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.tools import tool
from langgraph.prebuilt import ToolExecutor
from .state import AgentState
from tools import QueryTools, ExecuteTools
from utils import logger, agent_logger
import asyncio

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/prompts.json")
LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/llm_config.json")

logger.info("加载配置文件...")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    prompts = json.load(f)

with open(LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
    llm_config_list = json.load(f)

logger.info("初始化工具...")
query_tools = QueryTools()
execute_tools = ExecuteTools()

class LLMManager:
    """LLM管理器 - 实现多LLM配置轮询策略和自动重试"""

    def __init__(self, configs: list):
        self.configs = configs
        self.current_index = 0
        self.retry_count = 3
        self.retry_delay = 2
        self.llms = []
        self._init_llms()

    def _init_llms(self):
        """初始化所有LLM实例"""
        from langchain_openai import ChatOpenAI
        
        for i, config in enumerate(self.configs):
            api_key = config.get("api_key")
            
            if not api_key or api_key.strip() == "":
                logger.warning(f"LLM配置 #{i+1} ({config.get('name', 'unknown')}) API密钥未配置，跳过")
                continue
            
            try:
                llm = ChatOpenAI(
                    model=config.get("model", "gpt-4o"),
                    base_url=config.get("base_url"),
                    api_key=api_key,
                    temperature=config.get("temperature", 0.7),
                    max_tokens=config.get("max_tokens", 2048),
                    streaming=True,
                    max_retries=0
                )
                self.llms.append({
                    "llm": llm,
                    "config": config
                })
                logger.info(f"LLM #{i+1} 初始化成功 | name={config.get('name')} | model={config.get('model')}")
            except Exception as e:
                logger.error(f"LLM #{i+1} 初始化失败 | error={str(e)}")

        if not self.llms:
            logger.error("没有可用的LLM配置！请检查llm_config.json文件")

    def _get_next_llm(self):
        """获取下一个LLM（轮询策略）"""
        if not self.llms:
            return None, None
        
        llm_info = self.llms[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.llms)
        return llm_info["llm"], llm_info["config"]

    async def invoke(self, messages: list):
        """调用LLM，带自动重试和轮询"""
        if not self.llms:
            raise ValueError("没有可用的LLM配置！请在llm_config.json中配置API密钥")

        last_error = None
        
        for attempt in range(self.retry_count):
            llm, config = self._get_next_llm()
            
            if llm is None:
                raise ValueError("没有可用的LLM配置")
            
            try:
                logger.info(f"调用LLM [{config.get('name')}] | attempt={attempt+1}")
                response = await llm.ainvoke(messages)
                logger.info(f"LLM [{config.get('name')}] 调用成功")
                return response
            
            except Exception as e:
                error_msg = f"LLM [{config.get('name')}] 调用失败 | error={str(e)}"
                logger.error(error_msg)
                last_error = e
                
                if attempt < self.retry_count - 1:
                    logger.info(f"等待 {self.retry_delay} 秒后重试...")
                    await asyncio.sleep(self.retry_delay)
                    self.retry_delay *= 1.5

        raise Exception(f"所有LLM调用均失败，最后错误: {str(last_error)}")

    def has_llms(self):
        """检查是否有可用的LLM"""
        return len(self.llms) > 0

logger.info("初始化LLM管理器...")
llm_manager = LLMManager(llm_config_list)

if not llm_manager.has_llms():
    logger.error("警告：没有可用的LLM配置！请在llm_config.json中正确配置API密钥")

INTENT_TYPE = Literal["preferences", "activity_plan", "booking", "general"]

def analyze_intent(state: AgentState) -> AgentState:
    """分析用户意图"""
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    conversation_id = state.get("conversation_id", "unknown")

    if not isinstance(last_message, HumanMessage):
        return state

    user_input = last_message.content
    agent_logger.intent_analyzing(conversation_id, user_input)

    intent_type: INTENT_TYPE = "general"
    current_skill = None

    preference_keywords = ["喜欢", "偏好", "爱好", "我的情况", "我家", "孩子", "老婆", "老公", "家庭"]
    plan_keywords = ["出去玩", "安排", "规划", "推荐", "去哪", "吃什么", "约会", "聚会"]
    booking_keywords = ["预订", "订", "下单", "购票", "预约"]

    if any(keyword in user_input.lower() for keyword in preference_keywords):
        intent_type = "preferences"
        logger.info(f"检测到偏好设置意图 | conversation_id={conversation_id}")
        
        family_info = {}
        friends_info = {}
        
        if "孩子" in user_input:
            family_info["has_children"] = True
            import re
            ages = re.findall(r'(\d+)岁', user_input)
            if ages:
                family_info["children_ages"] = [int(a) for a in ages]
        
        if "老婆" in user_input or "减肥" in user_input:
            family_info["spouse_diet"] = "减肥中" if "减肥" in user_input else ""
        
        if "朋友" in user_input:
            counts = re.findall(r'(\d+)个', user_input)
            if counts:
                friends_info["total_count"] = int(counts[0])
        
        if family_info or friends_info:
            state["context"]["family_info"] = family_info
            state["context"]["friends_info"] = friends_info

    elif any(keyword in user_input.lower() for keyword in plan_keywords):
        intent_type = "activity_plan"
        
        if any(keyword in user_input.lower() for keyword in ["孩子", "亲子", "带娃", "家庭"]):
            current_skill = "Parent-ChildTravelPlanning"
        elif any(keyword in user_input.lower() for keyword in ["朋友", "聚会", "多人"]):
            current_skill = "FriendsOuting"
        elif any(keyword in user_input.lower() for keyword in ["约会", "对象", "浪漫"]):
            current_skill = "PersonalTravelPlanning"
        
        logger.info(f"检测到活动规划意图 | conversation_id={conversation_id} | skill={current_skill}")

    elif any(keyword in user_input.lower() for keyword in booking_keywords):
        intent_type = "booking"
        logger.info(f"检测到预订意图 | conversation_id={conversation_id}")

    agent_logger.intent_analyzed(conversation_id, current_skill)

    return {
        **state,
        "intent_type": intent_type,
        "current_skill": current_skill,
        "context": state.get("context", {})
    }

async def handle_preferences(state: AgentState):
    """处理偏好设置"""
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""
    conversation_id = state.get("conversation_id", "unknown")

    family_info = state.get("context", {}).get("family_info")
    friends_info = state.get("context", {}).get("friends_info")

    try:
        result = execute_tools.save_preferences(
            user_id="default_user",
            preferences=user_input,
            family_info=family_info,
            friends_info=friends_info
        )
        
        response_text = f"✅ 已为您保存偏好设置！\n\n您的偏好：{user_input[:50]}..."
        if family_info:
            response_text += f"\n\n家庭信息已更新：{family_info}"
        if friends_info:
            response_text += f"\n\n朋友信息已更新：{friends_info}"
        response_text += "\n\n下次规划时我会考虑这些信息！"

        return {
            "messages": [AIMessage(content=response_text)],
            "intent_type": "preferences",
            "conversation_id": conversation_id
        }
    except Exception as e:
        logger.error(f"保存偏好失败 | conversation_id={conversation_id} | error={str(e)}")
        return {
            "messages": [AIMessage(content=f"保存偏好时出错：{str(e)}")],
            "conversation_id": conversation_id
        }

async def agent_node(state: AgentState):
    """Agent主节点"""
    messages = state["messages"]
    preferences = state.get("preferences", "")
    intent_type = state.get("intent_type")
    current_skill = state.get("current_skill")
    conversation_id = state.get("conversation_id", "unknown")

    chat_history = []
    for msg in messages[:-1]:
        if isinstance(msg, HumanMessage):
            chat_history.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage):
            chat_history.append(f"助手: {msg.content}")

    system_msg = prompts["system_prompt"]
    system_msg += "\n\n你是一个专业的活动规划助手，名为'小团'。"

    if preferences:
        system_msg += "\n" + prompts["preference_prompt"].format(preferences=preferences)

    if chat_history:
        system_msg += "\n\n对话历史:\n" + "\n".join(chat_history[-6:])

    system_msg += "\n\n请根据用户的需求和上下文，提供专业的活动规划建议。"

    user_message = messages[-1].content if messages else ""

    try:
        if not llm_manager.has_llms():
            error_msg = """
抱歉，当前系统没有配置可用的LLM服务！

请检查 `backend/config/llm_config.json` 文件，确保已正确配置至少一个LLM的API密钥：

示例配置：
{
  "name": "xiaomi",
  "model": "mimo-v2.5-pro",
  "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
  "api_key": "your-api-key-here",
  "temperature": 0.7
}

配置完成后，请重启后端服务。
"""
            return {
                "messages": [AIMessage(content=error_msg)],
                "conversation_id": conversation_id
            }

        logger.info(f"调用LLM | conversation_id={conversation_id}")
        agent_logger.llm_invoking(conversation_id)

        response = await llm_manager.invoke(
            [SystemMessage(content=system_msg), HumanMessage(content=user_message)]
        )

        agent_logger.llm_response(conversation_id, len(response.content))
        logger.info(f"LLM响应完成 | conversation_id={conversation_id} | length={len(response.content)}")

        return {
            "messages": [response],
            "intent_type": intent_type,
            "current_skill": current_skill,
            "conversation_id": conversation_id
        }
    except Exception as e:
        error_msg = f"抱歉，处理时出现错误: {str(e)}\n\n请检查LLM配置是否正确。"
        logger.error(f"Agent节点错误 | conversation_id={conversation_id} | error={str(e)}")
        return {
            "messages": [AIMessage(content=error_msg)],
            "conversation_id": conversation_id
        }

def should_handle_preferences(state: AgentState) -> Literal["handle_preferences", "agent"]:
    """判断是否需要处理偏好设置"""
    if state.get("intent_type") == "preferences":
        return "handle_preferences"
    return "agent"

def should_execute_skill(state: AgentState) -> Literal["execute_skill", END]:
    """决定是否执行skill"""
    if state.get("current_skill"):
        return "execute_skill"
    return END

def execute_skill_node(state: AgentState):
    """执行skill节点 - 查询数据并生成方案"""
    current_skill = state.get("current_skill")
    conversation_id = state.get("conversation_id", "unknown")

    if not current_skill:
        return {"messages": []}

    logger.info(f"开始执行Skill | conversation_id={conversation_id} | skill={current_skill}")

    try:
        if "Parent-Child" in current_skill:
            scenario = "family"
        elif "Friends" in current_skill:
            scenario = "friends"
        elif "Personal" in current_skill:
            scenario = "couple"
        else:
            scenario = None

        if scenario:
            result = query_tools.recommend_by_scenario(scenario)
            plan_id = f"plan_{hash(conversation_id) % 1000:03d}"
            
            response_text = f"\n\n📍 **方案推荐完成**\n\n场景: {result.get('scenario', '')}\n\n"
            
            attractions = result.get('attractions', [])[:2]
            restaurants = result.get('restaurants', [])[:2]
            
            for i, attr in enumerate(attractions, 1):
                response_text += f"{i}. 🎯 {attr.get('name', '')}\n"
                response_text += f"   类型: {attr.get('type', '')}\n"
                response_text += f"   地址: {attr.get('address', '')[:20]}...\n"
                response_text += f"   评分: {attr.get('rating', '')}\n\n"
            
            for i, rest in enumerate(restaurants, 1):
                response_text += f"{i}. 🍽️ {rest.get('name', '')}\n"
                response_text += f"   菜系: {rest.get('cuisine', '')}\n"
                response_text += f"   人均: {rest.get('price_per_person', '')}元\n\n"
            
            response_text += f"方案ID: {plan_id}\n"
            response_text += "\n需要我帮您预订吗？\n\n⚠️ 所有预订操作都需要您亲自确认。"
            
            return {
                "messages": [AIMessage(content=response_text)],
                "plan_id": plan_id
            }
        else:
            return {"messages": []}

    except Exception as e:
        logger.error(f"Skill执行错误 | conversation_id={conversation_id} | error={str(e)}")
        return {"messages": [AIMessage(content=f"执行时出错: {str(e)}")]}

def build_graph():
    """构建Agent图"""
    logger.info("开始构建Agent图...")

    workflow = StateGraph(AgentState)

    workflow.add_node("analyze_intent", analyze_intent)
    workflow.add_node("handle_preferences", handle_preferences)
    workflow.add_node("agent", agent_node)
    workflow.add_node("execute_skill", execute_skill_node)

    workflow.set_entry_point("analyze_intent")
    workflow.add_conditional_edges(
        "analyze_intent",
        should_handle_preferences,
        {
            "handle_preferences": "handle_preferences",
            "agent": "agent"
        }
    )
    workflow.add_edge("handle_preferences", END)
    workflow.add_conditional_edges(
        "agent",
        should_execute_skill,
        {
            "execute_skill": "execute_skill",
            END: END
        }
    )
    workflow.add_edge("execute_skill", END)

    checkpointer = MemorySaver()
    compiled_graph = workflow.compile(checkpointer=checkpointer)

    logger.info("Agent图构建完成")
    logger.info("节点流程: analyze_intent -> [handle_preferences | agent] -> [execute_skill | end]")

    return compiled_graph

__all__ = ["build_graph", "llm_manager"]
