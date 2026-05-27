"""数据存储模块 - 简化版

只保存：
1. 聊天历史记录
2. 用户信息（偏好、家庭构成）
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PREFERENCES_FILE = os.path.join(DATA_DIR, "preferences.json")
CONVERSATIONS_FILE = os.path.join(DATA_DIR, "conversations.json")

class DataStore:
    """简化的数据存储类"""

    def __init__(self):
        self._ensure_dir()

    def _ensure_dir(self):
        """确保数据目录存在"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    def _load_json(self, filepath: str, default: Any = None) -> Any:
        """加载JSON文件"""
        if not os.path.exists(filepath):
            return default or []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default or []

    def _save_json(self, filepath: str, data: Any):
        """保存JSON文件"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_preferences(self, user_id: str = "default_user") -> Optional[Dict[str, Any]]:
        """获取用户偏好"""
        prefs_data = self._load_json(PREFERENCES_FILE, {})
        
        if isinstance(prefs_data, dict):
            prefs = prefs_data.get("preferences", {})
            if prefs.get("user_id") == user_id:
                return prefs
            return None
        elif isinstance(prefs_data, list):
            return next((p for p in prefs_data if p.get("user_id") == user_id), None)
        return None

    def save_preferences(self, preferences: Dict[str, Any]):
        """保存用户偏好"""
        prefs_data = self._load_json(PREFERENCES_FILE, {"preferences": {}})
        
        if isinstance(prefs_data, dict):
            prefs_data["preferences"] = preferences
            self._save_json(PREFERENCES_FILE, prefs_data)
        elif isinstance(prefs_data, list):
            existing_index = next((i for i, p in enumerate(prefs_data) if p.get("user_id") == preferences.get("user_id")), None)
            if existing_index is not None:
                prefs_data[existing_index] = preferences
            else:
                prefs_data.append(preferences)
            self._save_json(PREFERENCES_FILE, prefs_data)

    def create_conversation(self, user_id: str, skill_type: str) -> Dict[str, Any]:
        """创建新对话"""
        conversation = {
            "id": f"conv_{int(datetime.now().timestamp())}",
            "user_id": user_id,
            "skill_type": skill_type,
            "messages": [],
            "created_at": str(datetime.now()),
            "updated_at": str(datetime.now()),
            "status": "active"
        }
        
        conv_data = self._load_json(CONVERSATIONS_FILE, {"conversations": [], "next_id": 1})
        
        if isinstance(conv_data, dict):
            conv_list = conv_data.get("conversations", [])
        else:
            conv_list = conv_data
        
        conv_list.append(conversation)
        
        if isinstance(conv_data, dict):
            conv_data["conversations"] = conv_list
            conv_data["next_id"] = conv_data.get("next_id", 1) + 1
            self._save_json(CONVERSATIONS_FILE, conv_data)
        else:
            self._save_json(CONVERSATIONS_FILE, conv_list)
        
        return conversation

    def add_message(self, conversation_id: str, role: str, content: str):
        """添加消息到对话"""
        conv_data = self._load_json(CONVERSATIONS_FILE, {"conversations": [], "next_id": 1})
        
        if isinstance(conv_data, dict):
            conv_list = conv_data.get("conversations", [])
        else:
            conv_list = conv_data
        
        for conv in conv_list:
            if conv.get("id") == conversation_id:
                conv["messages"].append({
                    "id": f"msg_{int(datetime.now().timestamp())}",
                    "role": role,
                    "content": content,
                    "timestamp": str(datetime.now())
                })
                conv["updated_at"] = str(datetime.now())
                break
        
        if isinstance(conv_data, dict):
            conv_data["conversations"] = conv_list
            self._save_json(CONVERSATIONS_FILE, conv_data)
        else:
            self._save_json(CONVERSATIONS_FILE, conv_list)

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """获取对话详情"""
        conv_data = self._load_json(CONVERSATIONS_FILE, {"conversations": [], "next_id": 1})
        
        if isinstance(conv_data, dict):
            conv_list = conv_data.get("conversations", [])
        else:
            conv_list = conv_data
        
        return next((c for c in conv_list if c.get("id") == conversation_id), None)

    def get_conversations(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        """获取用户所有对话"""
        conv_data = self._load_json(CONVERSATIONS_FILE, {"conversations": [], "next_id": 1})
        
        if isinstance(conv_data, dict):
            conv_list = conv_data.get("conversations", [])
        else:
            conv_list = conv_data
        
        return [c for c in conv_list if c.get("user_id") == user_id]

    def close_conversation(self, conversation_id: str):
        """关闭对话"""
        conv_data = self._load_json(CONVERSATIONS_FILE, {"conversations": [], "next_id": 1})
        
        if isinstance(conv_data, dict):
            conv_list = conv_data.get("conversations", [])
        else:
            conv_list = conv_data
        
        for conv in conv_list:
            if conv.get("id") == conversation_id:
                conv["status"] = "completed"
                conv["updated_at"] = str(datetime.now())
                break
        
        if isinstance(conv_data, dict):
            conv_data["conversations"] = conv_list
            self._save_json(CONVERSATIONS_FILE, conv_data)
        else:
            self._save_json(CONVERSATIONS_FILE, conv_list)

    def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取对话消息"""
        conv = self.get_conversation(conversation_id)
        return conv.get("messages", []) if conv else []

data_store = DataStore()

__all__ = ["DataStore", "data_store"]
