"""
AI-Girlfriend-Agent 核心 Agent

整合人格系统、记忆系统、情绪系统、技能系统，实现带情感感知的 AI 陪伴对话。

功能：
- 根据用户输入判断情绪 → 调整回复语气
- 短期记忆（会话持久化 + 10 天到期压缩）
- 长期记忆（用户画像）
- 固定人格角色设定（从 character.py 加载）
- 技能系统（聊天、安慰、讲故事等）
"""

import logging
import json
import re
import sys
import os
from logging.handlers import TimedRotatingFileHandler

# ── 不使用相对 import（避免 importlib 方式加载时包解析失败）──
_gf_agent_dir = os.path.dirname(__file__)          # backend/agent/
_gf_backend_dir = os.path.dirname(_gf_agent_dir)    # backend/
if _gf_backend_dir not in sys.path:
    sys.path.insert(0, _gf_backend_dir)

from personality.character import Character
from memory.short_memory import ShortMemory
from memory.long_memory import LongMemory
from emotion.emotion import EmotionSystem

logger = logging.getLogger("girlfriend_agent")

# ── 聊天专用日志（7 天滚转） ──────────────────────────
_CHAT_LOG_DIR = os.path.join(_gf_backend_dir, "logs")
os.makedirs(_CHAT_LOG_DIR, exist_ok=True)

_chat_handler = TimedRotatingFileHandler(
    os.path.join(_CHAT_LOG_DIR, "chat.log"),
    when="D", interval=1, backupCount=6,  # 保留 7 天
    encoding="utf-8",
)
_chat_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
chat_logger = logging.getLogger("chat_log")
if not chat_logger.handlers:
    chat_logger.addHandler(_chat_handler)
    chat_logger.setLevel(logging.INFO)
    chat_logger.propagate = False

MAX_TOOL_ROUNDS = 3
MAX_TOKENS = 2048
STREAM_CHUNK_SIZE = 12
STREAM_DELAY = 0.025


def _clean_output(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"\[当前用户情绪:[^\]]+\]\s*", "", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = text.strip("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def _strip_internal_context(text: str) -> str:
    return re.sub(
        r"^\[当前用户情绪:[^\]\r\n]+\](?:\r?\n\[用户画像:.*\])?\r?\n",
        "",
        text,
        count=1,
    )


def _ensure_bracket_action(text: str) -> str:
    """确保回复包含括号动作描写，没有就补上"""
    if not text:
        return text
    # 检查是否已有括号动作
    if '（' in text and '）' in text:
        return text
    # 没有括号动作，补一个
    import random
    actions = [
        "（歪了歪头）",
        "（眨了眨眼）",
        "（轻轻笑了笑）",
        "（点了点头）",
        "（托着下巴）",
    ]
    # 找到情绪标记后的位置插入
    match = re.match(r'\*[^*]+\*\s*', text)
    if match:
        pos = match.end()
        return text[:pos] + random.choice(actions) + text[pos:]
    # 没有情绪标记，在开头插入
    return random.choice(actions) + text


class GirlfriendAgent:
    """AI 女友 Agent — 带人格/记忆/情绪的全功能对话引擎"""

    def __init__(self, client, model, use_db=False):
        self.client = client
        self.model = model
        self.character = Character()
        self.short_memory = ShortMemory()
        self.long_memory = LongMemory()
        self.emotion = EmotionSystem()
        self.use_db = use_db  # 是否使用数据库（禁用JSON文件保存）

        # 按用户 ID 隔离对话历史（启动时从磁盘加载）
        self.sessions: dict[str, list] = {}

    def _get_or_create_history(self, user_id: str) -> list:
        """获取或创建用户会话（自动从磁盘加载，到期压缩）"""
        if user_id in self.sessions:
            return self.sessions[user_id]

        # 尝试从磁盘加载
        saved = self.short_memory.load(user_id)
        if saved:
            messages = saved.get("messages", [])
            for message in messages:
                if message.get("role") == "user" and isinstance(message.get("content"), str):
                    message["content"] = _strip_internal_context(message["content"])

            system_prompt = self.character.build_system_prompt()
            base_prompt_index = next(
                (
                    index
                    for index, message in enumerate(messages)
                    if message.get("role") == "system"
                    and not (
                        isinstance(message.get("content"), str)
                        and message["content"].startswith("[历史会话摘要]")
                    )
                ),
                None,
            )
            if base_prompt_index is None:
                messages.insert(0, {"role": "system", "content": system_prompt})
            else:
                messages[base_prompt_index]["content"] = system_prompt

            created_at = saved.get("created_at", 0)
            updated_at = saved.get("updated_at", 0)

            # 超过 10 天 → 压缩
            if self.short_memory.should_compress(created_at):
                logger.info("会话过期 (>10天)，准备压缩 (%s)", user_id)
                # 分离旧消息（需要压缩的部分）
                system_msgs = [m for m in messages if m.get("role") == "system"]
                content_msgs = [m for m in messages if m.get("role") != "system"]
                # 保留最后 4 轮作为最近上下文，其余压缩
                if len(content_msgs) > 8:
                    old_msgs = content_msgs[:-8]
                    recent_msgs = content_msgs[-8:]
                    summary = self._summarize(user_id, old_msgs)
                    compressed = self.short_memory.compress(
                        user_id, system_msgs + old_msgs + recent_msgs, summary
                    )
                    messages = compressed

            self.sessions[user_id] = messages
            logger.info("已加载会话 (%s): %d 条消息", user_id, len(messages))
        else:
            # 新会话
            system_prompt = self.character.build_system_prompt()
            self.sessions[user_id] = [
                {"role": "system", "content": system_prompt}
            ]
            logger.info("创建新会话 (%s)", user_id)

        return self.sessions[user_id]

    def _save_session(self, user_id: str):
        """持久化当前会话到磁盘（使用数据库时跳过）"""
        if self.use_db:
            return  # 使用数据库时，由app.py负责保存
        if user_id in self.sessions:
            self.short_memory.save(user_id, self.sessions[user_id])

    def _summarize(self, user_id: str, messages: list) -> str:
        """调用 LLM 压缩生成对话摘要"""
        if not messages:
            return "无历史对话内容。"

        # 提取对话文本（去掉 system prompt 和太长内容）
        lines = []
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if role == "system":
                continue
            # 截断过长的消息
            if len(content) > 300:
                content = content[:300] + "..."
            label = "用户" if role == "user" else "荧"
            lines.append(f"{label}: {content}")

        text = "\n".join(lines)
        prompt = (
            f"请总结以下我和女友荧之间的对话历史，提取重要信息：\n"
            f"1. 用户提到了哪些兴趣爱好、经历、目标？\n"
            f"2. 用户的情绪变化？\n"
            f"3. 聊过的重要话题？\n"
            f"用简洁的 2-3 句中文概括。\n\n"
            f"---\n{text}\n---"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                extra_body={"thinking": {"type": "disabled"}},
            )
            summary = response.choices[0].message.content or ""
            summary = _clean_output(summary)
            logger.info("会话摘要已生成 (%s): %s", user_id, summary[:100])
            return summary
        except Exception as e:
            logger.warning("生成摘要失败 (%s): %s", user_id, e)
            return "对话历史摘要生成失败。"

    # ── 对话 ───────────────────────────────────────────

    def chat(self, user_id: str, message: str) -> str:
        """非流式对话"""
        history = self._get_or_create_history(user_id)

        # 情绪检测
        emotion = self.emotion.set(user_id, message)

        # 加载长期记忆
        long_term = self.long_memory.get(user_id)

        # 注入情绪和记忆上下文
        context = f"[当前用户情绪: {emotion}，仅供内部参考，请勿在回复中复述]"
        if long_term:
            context += f"\n[用户画像: {json.dumps(long_term, ensure_ascii=False)}]"

        history.append({"role": "user", "content": message})
        request_history = history[:-1] + [
            {"role": "user", "content": context + "\n" + message}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                messages=request_history,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except Exception as e:
            logger.error("API 调用失败: %s", e)
            return "抱歉，我现在有点累，能再说一遍吗？"

        reply = response.choices[0].message.content or ""
        reply = _clean_output(reply)
        reply = _ensure_bracket_action(reply)

        history.append({"role": "assistant", "content": reply})
        # 裁剪历史，防止无限增长
        self.short_memory.trim(history)
        logger.info("👤 %s | 😊 %s | 🤖 %s", user_id, emotion, reply[:200])

        # 记录聊天日志：荧的回复 + 状态码 + 工具调用
        tools_used = "无"
        http_resp = getattr(response, "_response", None)
        status_code = http_resp.status_code if http_resp is not None else 200
        chat_logger.info(
            "USER=%(user)s | EMOTION=%(emotion)s | STATUS=%(status)d | TOOLS=%(tools)s | 荧: %(reply)s",
            {
                "user": user_id,
                "emotion": emotion,
                "status": status_code,
                "tools": tools_used,
                "reply": reply[:300].replace("\n", " "),
            }
        )

        # 持久化会话
        self._save_session(user_id)

        # 异步更新长期记忆
        self._update_long_term(user_id, message, reply)

        return reply

    def stream_chat(self, user_id: str, message: str):
        """流式对话 — 逐块 yield"""
        history = self._get_or_create_history(user_id)
        emotion = self.emotion.set(user_id, message)

        long_term = self.long_memory.get(user_id)
        context = f"[当前用户情绪: {emotion}，仅供内部参考，请勿在回复中复述]"
        if long_term:
            context += f"\n[用户画像: {json.dumps(long_term, ensure_ascii=False)}]"

        history.append({"role": "user", "content": message})
        request_history = history[:-1] + [
            {"role": "user", "content": context + "\n" + message}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                messages=request_history,
                stream=True,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except Exception as e:
            chat_logger.info(
                "USER=%(user)s | EMOTION=%(emotion)s | STATUS=ERROR | TOOLS=无 | 荧: (API失败) %(error)s",
                {"user": user_id, "emotion": emotion, "error": str(e)[:100]},
            )
            yield "抱歉，我现在有点累，能再说一遍吗？"
            return

        # 真正的流式：逐块 yield 内容
        content_chunks = []
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                content_chunks.append(delta.content)
                yield delta.content

        full = _clean_output("".join(content_chunks))
        # 检查是否有括号动作，没有就补上
        if full and '（' not in full:
            import random
            actions = ["（歪了歪头）", "（眨了眨眼）", "（轻轻笑了笑）", "（点了点头）", "（托着下巴）"]
            action = random.choice(actions)
            yield action
            full = full + action
        if not full:
            full = "嗯，我在听，你继续说~"
            yield full

        history.append({"role": "assistant", "content": full})
        # 裁剪历史，防止无限增长
        self.short_memory.trim(history)

        # 记录聊天日志
        chat_logger.info(
            "USER=%(user)s | EMOTION=%(emotion)s | STATUS=200 | TOOLS=无 | 荧: %(reply)s",
            {"user": user_id, "emotion": emotion, "reply": full[:300].replace("\n", " ")},
        )

        # 持久化
        self._save_session(user_id)

        self._update_long_term(user_id, message, full)

    def _update_long_term(self, user_id: str, message: str, reply: str):
        """从对话中提取关键信息更新长期记忆"""
        # 更精确的正则表达式，避免错误提取
        # 兴趣：喜欢XX、爱好XX、对XX感兴趣（排除太短或太长的）
        interests = re.findall(r"(?:喜欢|爱好|对)\s*([一-龥]{2,8}?)(?:[，。！？\s]|$)", message)
        # 目标：想做XX、打算XX、计划XX（排除"想"单独使用的情况）
        goals = re.findall(r"(?:目标是|想要|打算|计划)\s*(.{3,15}?)(?:[，。！？\n]|$)", message)

        # 过滤掉无效内容
        invalid_patterns = ["活了", "着什么", "什么", "好的", "嗯", "啊", "吧", "呢"]
        interests = [i for i in interests if i not in invalid_patterns and len(i) >= 2]
        goals = [g for g in goals if g not in invalid_patterns and len(g) >= 3]

        if interests or goals:
            memory = self.long_memory.get(user_id) or {}
            if interests:
                existing = memory.setdefault("interests", [])
                for i in interests:
                    if i not in existing:
                        existing.append(i)
            if goals:
                existing = memory.setdefault("goals", [])
                for g in goals:
                    if g not in existing:
                        existing.append(g)
            self.long_memory.save(user_id, memory)

    def get_history(self, user_id: str) -> list:
        return self._get_or_create_history(user_id)[1:]  # 排除 system prompt

    def clear_history(self, user_id: str):
        if user_id in self.sessions:
            del self.sessions[user_id]
        # 同时删除磁盘文件
        path = os.path.join(
            os.path.dirname(__file__), "..", "data", "conversations", f"{user_id}.json"
        )
        try:
            os.remove(path)
        except FileNotFoundError:
            pass