"""活动规划Agent系统 - 简化版

前端只需要一个对话接口和一些状态展示。
后端存储数据只保存：
1. 聊天历史记录
2. 用户信息（偏好、家庭构成）

执行操作需要发送给前端，让用户亲自确认执行。
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from agent.graph import build_graph
from data_store import data_store
from langchain_core.messages import HumanMessage
from utils import logger, ws_logger
import uuid
import traceback

app = FastAPI(title="活动规划Agent系统", version="1.0.0")

logger.info("=" * 60)
logger.info("活动规划Agent系统启动中...")
logger.info("=" * 60)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("初始化Agent图...")
graph = build_graph()
logger.info("Agent图初始化完成")

@app.get("/")
async def root():
    logger.info("访问根路径")
    return {
        "message": "活动规划Agent系统 API",
        "version": "1.0.0",
        "endpoints": {
            "websocket": "/ws/chat",
            "health": "/health",
            "preferences": "/api/preferences",
            "conversations": "/api/conversations"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/preferences")
async def get_preferences(user_id: str = "default_user"):
    return data_store.get_preferences(user_id)

@app.get("/api/conversations")
async def get_conversations(user_id: str = "default_user"):
    return data_store.get_conversations(user_id)

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    conversation = data_store.create_conversation("default_user", "unknown")
    conversation_id = conversation["id"]
    thread_id = str(uuid.uuid4())

    ws_logger.connection_opened(conversation_id)
    logger.info(f"新建WebSocket连接 | conversation_id={conversation_id} | thread_id={thread_id}")

    state = {
        "messages": [],
        "preferences": data_store.get_preferences().get("preferences", "") if data_store.get_preferences() else "",
        "interrupted": False,
        "interrupt_info": "",
        "conversation_id": conversation_id,
        "current_skill": None,
        "plan_id": None,
        "context": {}
    }

    config = {"configurable": {"thread_id": thread_id}}

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type", "message")
            content = data.get("content", "")

            ws_logger.message_received(conversation_id, message_type, content)

            if message_type == "message":
                await websocket.send_json({
                    "type": "status",
                    "content": "正在接收消息..."
                })

                user_message = HumanMessage(content=content)
                state["messages"].append(user_message)
                data_store.add_message(conversation_id, "user", content)

                logger.info(f"用户消息已记录 | conversation_id={conversation_id} | content_length={len(content)}")

                await websocket.send_json({
                    "type": "thinking",
                    "content": "正在分析您的需求..."
                })

                ws_logger.agent_processing(conversation_id, "analyze_intent")

                try:
                    async for event in graph.astream(
                        state,
                        config
                    ):
                        for node_name, node_data in event.items():
                            logger.debug(f"Agent节点执行 | conversation_id={conversation_id} | node={node_name}")

                            if node_name == "analyze_intent":
                                await websocket.send_json({
                                    "type": "thinking",
                                    "content": f"意图分析: 检测到相关活动类型"
                                })

                                ws_logger.agent_processing(conversation_id, "analyze_intent")

                                if node_data.get("current_skill"):
                                    await websocket.send_json({
                                        "type": "skill_detected",
                                        "content": f"匹配技能: {node_data['current_skill']}"
                                    })
                                    ws_logger.skill_detected(conversation_id, node_data['current_skill'])

                                state.update(node_data)

                            elif node_name == "agent":
                                if node_data.get("messages"):
                                    ai_message = node_data["messages"][-1]
                                    content_text = ai_message.content

                                    logger.info(f"Agent生成响应 | conversation_id={conversation_id} | response_length={len(content_text)}")

                                    for char in content_text:
                                        await websocket.send_json({
                                            "type": "chunk",
                                            "content": char
                                        })

                                    await websocket.send_json({
                                        "type": "ai_message",
                                        "content": content_text
                                    })

                                    data_store.add_message(conversation_id, "assistant", content_text)
                                    state.update(node_data)

                            elif node_name == "execute_skill":
                                ws_logger.agent_processing(conversation_id, "execute_skill")

                                if node_data.get("messages"):
                                    skill_result = node_data["messages"][-1]
                                    if skill_result.content:
                                        await websocket.send_json({
                                            "type": "skill_result",
                                            "content": skill_result.content
                                        })

                                if node_data.get("plan_id"):
                                    await websocket.send_json({
                                        "type": "plan_created",
                                        "content": f"方案已创建: {node_data['plan_id']}"
                                    })
                                    state["plan_id"] = node_data["plan_id"]
                                    logger.info(f"方案已创建 | conversation_id={conversation_id} | plan_id={node_data['plan_id']}")

                    await websocket.send_json({
                        "type": "done",
                        "plan_id": state.get("plan_id")
                    })

                    logger.info(f"消息处理完成 | conversation_id={conversation_id} | plan_id={state.get('plan_id')}")

                except Exception as e:
                    error_msg = f"Agent处理出错: {str(e)}"
                    logger.error(f"{error_msg} | conversation_id={conversation_id}")
                    logger.debug(f"详细错误: {traceback.format_exc()}")

                    await websocket.send_json({
                        "type": "error",
                        "content": error_msg
                    })

    except WebSocketDisconnect:
        ws_logger.connection_closed(conversation_id)
        data_store.close_conversation(conversation_id)
        logger.info(f"WebSocket连接断开 | conversation_id={conversation_id}")
    except Exception as e:
        ws_logger.error(conversation_id, str(e))
        logger.error(f"WebSocket未捕获异常 | conversation_id={conversation_id} | error={str(e)}")
        logger.debug(f"详细错误: {traceback.format_exc()}")

if __name__ == "__main__":
    import uvicorn
    logger.info("启动Uvicorn服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
