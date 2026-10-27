"""
AI-Girlfriend-Agent — 短期记忆

会话持久化 + 到期压缩：
- 每次对话后自动保存到磁盘（data/conversations/）
- 启动时自动加载上次会话
- 会话超过 10 天未更新 → 自动压缩旧消息为摘要（调用 LLM）

短期记忆由 GirlfriendAgent 通过 session 管理，本模块提供辅助函数。
"""
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("short_memory")

MAX_ROUNDS = 20  # 保留最近 20 轮对话
SESSION_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "conversations")


class ShortMemory:
    """短期记忆管理器（支持持久化 + 自动压缩）"""

    def __init__(self, max_rounds: int = MAX_ROUNDS):
        self.max_rounds = max_rounds
        os.makedirs(SESSION_DIR, exist_ok=True)

    # ── 持久化 ─────────────────────────────────────────

    def save(self, user_id: str, messages: list) -> None:
        """将会话保存到磁盘"""
        path = self._file_path(user_id)
        now = time.time()
        # 读取已有数据保留 created_at
        existing = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        data = {
            "messages": messages,
            "updated_at": now,
            "created_at": existing.get("created_at", now),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("保存会话失败 (%s): %s", user_id, e)

    def load(self, user_id: str) -> Optional[dict]:
        """从磁盘加载会话，返回 {messages, created_at, updated_at} 或 None"""
        path = self._file_path(user_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def should_compress(self, created_at: float) -> bool:
        """检查会话是否超过 10 天需要压缩"""
        if not created_at:
            return False
        return (time.time() - created_at) > 10 * 86400  # 10 天

    def compress(self, user_id: str, messages: list, summary: str) -> list:
        """
        压缩会话：仅保留 system prompt + 摘要 + 最近 N 轮
        summary 由外部（GirlfriendAgent）通过 LLM 生成
        """
        system = [m for m in messages if m.get("role") == "system"]
        recent = [m for m in messages if m.get("role") != "system"][-self.max_rounds:]

        if summary:
            summary_msg = {
                "role": "system",
                "content": f"[历史会话摘要]\n{summary}",
            }
        else:
            summary_msg = {
                "role": "system",
                "content": "[历史会话摘要]\n无可用摘要。",
            }

        compressed = system + [summary_msg] + recent
        logger.info("会话压缩完成 (%s): %d → %d 条", user_id, len(messages), len(compressed))
        return compressed

    # ── 常规操作 ───────────────────────────────────────

    def trim(self, history: list) -> list:
        """裁剪历史，保留最近 N 轮（不含 system prompt）"""
        if len(history) <= 2:  # system + 第一轮
            return history

        system = [h for h in history if h.get("role") == "system"]
        messages = [h for h in history if h.get("role") != "system"]

        if len(messages) > self.max_rounds:
            messages = messages[-self.max_rounds:]

        return system + messages

    def summarize(self, history: list) -> str:
        """提取当前对话摘要"""
        messages = [h for h in history if h.get("role") != "system"]
        if not messages:
            return "空对话"

        rounds = len([m for m in messages if m["role"] == "user"])
        return f"当前对话共 {rounds} 轮，最近消息: {messages[-1].get('content', '')[:50]}..."

    # ── 内部工具 ───────────────────────────────────────

    def _file_path(self, user_id: str) -> str:
        safe_id = user_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return os.path.join(SESSION_DIR, f"{safe_id}.json")