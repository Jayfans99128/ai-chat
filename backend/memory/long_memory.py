"""
AI-Girlfriend-Agent — 长期记忆

持久化保存用户画像：
- 用户兴趣/爱好
- 学习/工作方向
- 重要经历
- 目标/愿望
- 性格特征

为每个 user_id 存储独立的 JSON 文件。
"""

import json
import os
import logging

logger = logging.getLogger("long_memory")

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "profiles")


class LongMemory:
    """长期记忆管理器"""

    def __init__(self, base_dir: str = MEMORY_DIR):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _file_path(self, user_id: str) -> str:
        # 安全处理 user_id（防止路径穿越）
        safe_id = user_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return os.path.join(self.base_dir, f"{safe_id}.json")

    def get(self, user_id: str) -> dict:
        """读取用户的长期记忆"""
        path = self._file_path(user_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self, user_id: str, data: dict):
        """保存用户的长期记忆"""
        path = self._file_path(user_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("保存长期记忆失败: %s", e)

    def update(self, user_id: str, key: str, value: list):
        """追加更新某个字段"""
        memory = self.get(user_id)
        existing = memory.setdefault(key, [])
        for item in value:
            if item not in existing:
                existing.append(item)
        self.save(user_id, memory)

    def delete(self, user_id: str):
        """删除用户的长期记忆"""
        path = self._file_path(user_id)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass