import logging
import os
from datetime import datetime
from typing import Optional

class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""

    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[35m',
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

def setup_logger(
    name: str = "agent",
    level: int = logging.DEBUG,
    log_file: Optional[str] = None
) -> logging.Logger:
    """设置日志记录器 — 控制台INFO级别（简洁），文件DEBUG级别（全量）"""

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # logger 本身设为 DEBUG，由 handler 控制输出级别

    if logger.handlers:
        return logger

    # 控制台 handler：INFO 级别，截取展示
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = ColoredFormatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # 文件 handler：DEBUG 级别，全量保存
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger

def get_logger(name: str = "agent") -> logging.Logger:
    """获取日志记录器"""
    return logging.getLogger(name)

class WebSocketLogger:
    """WebSocket专用日志记录器"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or get_logger("websocket")

    def connection_opened(self, conversation_id: str):
        self.logger.info(f"WebSocket连接已建立 | conversation_id={conversation_id}")

    def connection_closed(self, conversation_id: str):
        self.logger.info(f"WebSocket连接已关闭 | conversation_id={conversation_id}")

    def message_received(self, conversation_id: str, message_type: str, content: str):
        self.logger.info(
            f"收到消息 | conversation_id={conversation_id} | "
            f"type={message_type} | content={content[:100]}"
        )

    def message_sent(self, conversation_id: str, message_type: str):
        self.logger.debug(
            f"发送消息 | conversation_id={conversation_id} | type={message_type}"
        )

    def agent_processing(self, conversation_id: str, step: str):
        self.logger.info(
            f"Agent处理中 | conversation_id={conversation_id} | step={step}"
        )

    def skill_detected(self, conversation_id: str, skill_name: str):
        self.logger.info(
            f"技能匹配 | conversation_id={conversation_id} | skill={skill_name}"
        )

    def skill_executed(self, conversation_id: str, skill_name: str, result: str):
        self.logger.info(
            f"技能执行完成 | conversation_id={conversation_id} | "
            f"skill={skill_name} | result={result[:100]}"
        )

    def error(self, conversation_id: str, error: str):
        self.logger.error(
            f"WebSocket错误 | conversation_id={conversation_id} | error={error}"
        )

class AgentLogger:
    """Agent专用日志记录器"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or get_logger("agent")

    def intent_analyzing(self, conversation_id: str, user_input: str):
        self.logger.info(
            f"分析意图 | conversation_id={conversation_id} | "
            f"input={user_input[:100]}"
        )

    def intent_analyzed(self, conversation_id: str, detected_skill: str):
        self.logger.info(
            f"意图分析完成 | conversation_id={conversation_id} | "
            f"skill={detected_skill or 'None'}"
        )

    def llm_invoking(self, conversation_id: str):
        self.logger.info(
            f"调用LLM | conversation_id={conversation_id}"
        )

    def llm_response(self, conversation_id: str, response_length: int):
        self.logger.info(
            f"LLM响应完成 | conversation_id={conversation_id} | "
            f"length={response_length}"
        )

    def state_updated(self, conversation_id: str, state_updates: dict):
        self.logger.debug(
            f"状态更新 | conversation_id={conversation_id} | "
            f"updates={state_updates}"
        )

    def error(self, conversation_id: str, error: str, traceback: str = ""):
        self.logger.error(
            f"Agent错误 | conversation_id={conversation_id} | error={error}"
        )
        if traceback:
            self.logger.debug(f"详细错误: {traceback}")

class APILogger:
    """API接口专用日志记录器"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or get_logger("api")

    def request(self, method: str, path: str, params: dict = None):
        self.logger.info(
            f"API请求 | method={method} | path={path} | "
            f"params={params or {}}"
        )

    def response(self, method: str, path: str, status_code: int, duration: float):
        self.logger.info(
            f"API响应 | method={method} | path={path} | "
            f"status={status_code} | duration={duration:.3f}s"
        )

    def error(self, method: str, path: str, error: str):
        self.logger.error(
            f"API错误 | method={method} | path={path} | error={error}"
        )

LOG_DIR = os.path.join(os.path.dirname(__file__), "../logs")
LOG_FILE = os.path.join(LOG_DIR, f"agent_{datetime.now().strftime('%Y%m%d')}.log")

logger = setup_logger("agent", logging.DEBUG, LOG_FILE)
ws_logger = WebSocketLogger()
agent_logger = AgentLogger()
api_logger = APILogger()


def truncate_for_console(text: str, max_len: int = 200) -> str:
    """截取文本用于控制台展示"""
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [截断，完整内容见日志文件，总长{len(text)}]"


def log_node_io(logger_instance, node_name: str, input_summary: str, output_summary: str,
                full_input: str = "", full_output: str = ""):
    """
    记录节点输入输出：控制台截取，文件全量

    Args:
        logger_instance: logger 实例
        node_name: 节点名称
        input_summary: 输入摘要（控制台展示）
        output_summary: 输出摘要（控制台展示）
        full_input: 完整输入（写入文件）
        full_output: 完整输出（写入文件）
    """
    logger_instance.info(f"[{node_name}] IN  → {truncate_for_console(input_summary)}")
    logger_instance.info(f"[{node_name}] OUT ← {truncate_for_console(output_summary)}")
    if full_input:
        logger_instance.debug(f"[{node_name}] 完整输入:\n{full_input}")
    if full_output:
        logger_instance.debug(f"[{node_name}] 完整输出:\n{full_output}")


__all__ = [
    "setup_logger",
    "get_logger",
    "WebSocketLogger",
    "AgentLogger",
    "APILogger",
    "logger",
    "ws_logger",
    "agent_logger",
    "api_logger",
    "truncate_for_console",
    "log_node_io",
]
