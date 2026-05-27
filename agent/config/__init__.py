"""配置加载模块 - LLM 配置与提示词管理"""
import json
import os
from dotenv import load_dotenv

load_dotenv()

# 配置文件所在目录
_CONFIG_DIR = os.path.dirname(__file__)

# 提示词缓存（启动时一次性加载）
_prompts_cache: dict | None = None


def get_llm_config(config_name: str = "primary") -> dict:
    """获取指定名称的 LLM 配置，支持 ${ENV_VAR} 环境变量替换

    Args:
        config_name: 配置名称，默认 "primary"，对应 llm_config.json 中的 name 字段

    Returns:
        包含 model, base_url, api_key, temperature 的配置字典
    """
    config_path = os.path.join(_CONFIG_DIR, "llm_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        configs = json.load(f)

    # 按名称查找配置，找不到则使用第一个
    config = next((c for c in configs if c["name"] == config_name), configs[0])

    # 替换环境变量，格式 ${OPENAI_API_KEY} → 读取实际的环境变量值
    api_key = config["api_key"]
    if api_key.startswith("${") and api_key.endswith("}"):
        env_var = api_key[2:-1]
        api_key = os.getenv(env_var, "")
        config["api_key"] = api_key

    return config


def load_prompts() -> dict:
    """加载 config/prompts.json 中的提示词模板

    Returns:
        提示词字典，key 为节点名称，value 为 {"system": "...", "user": "..."} 格式
    """
    global _prompts_cache
    if _prompts_cache is None:
        prompts_path = os.path.join(_CONFIG_DIR, "prompts.json")
        with open(prompts_path, "r", encoding="utf-8") as f:
            _prompts_cache = json.load(f)
    return _prompts_cache


def get_prompt(node_name: str) -> dict:
    """获取指定节点的提示词模板

    Args:
        node_name: 节点名称，如 "analyze_input", "generate_plan"

    Returns:
        {"system": "系统提示词", "user": "用户提示词"}
    """
    prompts = load_prompts()
    if node_name not in prompts:
        raise KeyError(f"提示词节点 '{node_name}' 不存在于 config/prompts.json 中")
    return prompts[node_name]
