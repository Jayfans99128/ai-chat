"""
AI-Girlfriend-Agent — 主动行为 Agent

从"定时自动发消息"升级为"主动行为 Agent"：
- 状态感知：最近对话 + 长期记忆 + 时间 + 用户状态
- 主动决策：LLM 判断是否主动、行为类型、原因
- 消息生成：结合人格和上下文生成自然消息
- 冷却机制：避免机械打扰
"""

import time
import random
import logging
from datetime import datetime

logger = logging.getLogger("proactive_agent")


class ProactiveBehaviorAgent:
    """主动行为 Agent — 智能判断是否主动联系用户"""

    def __init__(self, client, model, agent):
        self.client = client
        self.model = model
        self.agent = agent  # GirlfriendAgent 实例

        self.MIN_INACTIVE = 600          # 10分钟不活跃后才检查
        self.MIN_PROACTIVE_INTERVAL = 1800  # 主动消息至少间隔30分钟

        # 状态记录
        self.last_activity: dict[str, float] = {}
        self.last_proactive: dict[str, float] = {}
        self.proactive_logs: dict[str, list] = {}  # user_id -> [logs]

    def update_activity(self, user_id: str):
        """更新用户最后活动时间"""
        self.last_activity[user_id] = time.time()

    def check(self, user_id: str) -> bool:
        """检查是否满足主动检查条件"""
        now = time.time()

        # 条件1：用户不活跃时间 >= MIN_INACTIVE
        last_active = self.last_activity.get(user_id, 0)
        if now - last_active < self.MIN_INACTIVE:
            return False

        # 条件2：距离上次主动消息 >= MIN_PROACTIVE_INTERVAL
        last_pro = self.last_proactive.get(user_id, 0)
        if now - last_pro < self.MIN_PROACTIVE_INTERVAL:
            return False

        return True

    def perceive(self, user_id: str) -> dict:
        """状态感知：收集上下文信息"""
        # 获取最近对话
        history = self.agent.get_history(user_id)
        recent_messages = history[-10:] if history else []

        # 获取长期记忆
        long_term = self.agent.long_memory.get(user_id)

        # 获取当前时间
        now = datetime.now()
        hour = now.hour
        time_period = self._get_time_period(hour)

        # 计算不活跃时长
        last_active = self.last_activity.get(user_id, 0)
        inactive_minutes = int((time.time() - last_active) / 60)

        # 提取用户最后说的话
        user_msgs = [m for m in recent_messages if m.get("role") == "user"]
        last_user_msg = user_msgs[-1].get("content", "") if user_msgs else ""

        # 识别关键词标签
        tags = self._extract_tags(last_user_msg)

        return {
            "user_id": user_id,
            "recent_messages": recent_messages,
            "long_term": long_term,
            "time_period": time_period,
            "hour": hour,
            "inactive_minutes": inactive_minutes,
            "last_user_msg": last_user_msg,
            "tags": tags,
        }

    def decide(self, context: dict) -> dict:
        """主动决策：LLM 判断是否主动、行为类型、原因"""
        user_id = context["user_id"]
        recent = context["recent_messages"]
        long_term = context["long_term"]
        time_period = context["time_period"]
        inactive_minutes = context["inactive_minutes"]
        last_user_msg = context["last_user_msg"]
        tags = context["tags"]

        # 构建决策 prompt
        recent_text = ""
        for m in recent[-6:]:
            role = "用户" if m.get("role") == "user" else "荧"
            content = m.get("content", "")[:100]
            recent_text += f"{role}: {content}\n"

        long_term_text = ""
        if long_term:
            if long_term.get("interests"):
                long_term_text += f"用户兴趣: {', '.join(long_term['interests'][:3])}\n"
            if long_term.get("goals"):
                long_term_text += f"用户目标: {', '.join(long_term['goals'][:3])}\n"

        prompt = f"""你是荧，用户（旅行者）的女朋友。现在你需要判断是否应该主动联系用户。

【当前状态】
- 时间段: {time_period}（{context['hour']}点）
- 用户已沉默: {inactive_minutes}分钟
- 用户最后说的话: {last_user_msg}
- 关键词标签: {', '.join(tags) if tags else '无'}

【最近对话】
{recent_text if recent_text else '无历史对话'}

【长期记忆】
{long_term_text if long_term_text else '无'}

【判断规则】
1. 用户刚说要睡觉/休息 → 不要打扰
2. 用户刚说要开会/忙 → 不要打扰
3. 用户刚才在倾诉烦恼 → 可以关心
4. 有未结束的话题 → 可以延续
5. 没有明确理由 → 可以简单表达想念
6. 不要机械使用"在干嘛""吃饭了吗"

请输出 JSON 格式：
{{
  "should_send": true/false,
  "reason": "判断原因",
  "action_type": "care/continue/share/tease/miss/accompany/remind/joke"
}}

action_type 说明：
- care: 关心用户
- continue: 延续未结束的话题
- share: 主动分享
- tease: 轻松调侃
- miss: 表达想念
- accompany: 单纯陪伴
- remind: 提醒
- joke: 开玩笑"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                extra_body={"thinking": {"type": "disabled"}},
            )
            result_text = response.choices[0].message.content or ""

            # 解析 JSON
            import json
            # 提取 JSON 部分
            json_match = result_text.replace("```json", "").replace("```", "").strip()
            decision = json.loads(json_match)

            logger.info("主动决策: user=%s, should=%s, type=%s, reason=%s",
                       user_id, decision.get("should_send"),
                       decision.get("action_type"), decision.get("reason"))

            return decision

        except Exception as e:
            logger.error("主动决策失败: %s", e)
            return {"should_send": False, "reason": "决策失败", "action_type": "miss"}

    def generate(self, context: dict, decision: dict) -> str:
        """根据人格和上下文生成主动消息"""
        if not decision.get("should_send"):
            return ""

        user_id = context["user_id"]
        action_type = decision.get("action_type", "miss")
        reason = decision.get("reason", "")
        recent = context["recent_messages"]
        long_term = context["long_term"]
        time_period = context["time_period"]

        # 构建生成 prompt
        recent_text = ""
        for m in recent[-6:]:
            role = "用户" if m.get("role") == "user" else "荧"
            content = m.get("content", "")[:100]
            recent_text += f"{role}: {content}\n"

        # 获取角色人格
        character_prompt = self.agent.character.build_system_prompt()

        # 行为类型说明
        action_desc = {
            "care": "关心用户，表达担忧或体贴",
            "continue": "延续之前没有结束的话题",
            "share": "主动分享想到的事情",
            "tease": "轻松调侃用户",
            "miss": "表达想念用户",
            "accompany": "单纯陪伴，找人聊天",
            "remind": "提醒用户某件事",
            "joke": "开玩笑，活跃气氛",
        }

        prompt = f"""{character_prompt}

【主动行为任务】
你现在要主动找用户聊天，不是回答问题。

行为类型: {action_type} - {action_desc.get(action_type, '')}
决策原因: {reason}
时间段: {time_period}

【最近对话】
{recent_text if recent_text else '无历史对话'}

【要求】
1. 1~3句话，简短自然
2. 必须包含括号动作描写
3. 不要机械使用"在干嘛""吃饭了吗"
4. 符合角色人格（温柔、偶尔嘴硬）
5. 不要求每条都以问题结尾
6. 可以只是突然想找用户聊天

请生成主动消息："""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                extra_body={"thinking": {"type": "disabled"}},
            )
            message = response.choices[0].message.content or ""
            message = message.strip()

            # 确保有括号动作
            if "（" not in message:
                actions = ["（歪了歪头）", "（眨了眨眼）", "（轻轻笑了笑）", "（小声说）"]
                message = random.choice(actions) + message

            logger.info("生成主动消息: user=%s, type=%s, msg=%s", user_id, action_type, message[:50])
            return message

        except Exception as e:
            logger.error("生成主动消息失败: %s", e)
            return ""

    def record(self, user_id: str, decision: dict, message: str):
        """记录主动行为"""
        if user_id not in self.proactive_logs:
            self.proactive_logs[user_id] = []

        log_entry = {
            "timestamp": time.time(),
            "action_type": decision.get("action_type", "unknown"),
            "reason": decision.get("reason", ""),
            "message": message,
            "user_replied": False,
        }
        self.proactive_logs[user_id].append(log_entry)

        # 只保留最近50条
        if len(self.proactive_logs[user_id]) > 50:
            self.proactive_logs[user_id] = self.proactive_logs[user_id][-50:]

    def check_and_generate(self, user_id: str) -> str | None:
        """完整流程：检查 → 感知 → 决策 → 生成"""
        # 检查条件
        if not self.check(user_id):
            return None

        self.last_proactive[user_id] = time.time()

        # 状态感知
        context = self.perceive(user_id)

        # 主动决策
        decision = self.decide(context)

        # 生成消息
        message = self.generate(context, decision)

        if message:
            # 更新状态
            self.last_proactive[user_id] = time.time()
            self.update_activity(user_id)  # 重置计时器

            # 记录
            self.record(user_id, decision, message)

        return message

    def _get_time_period(self, hour: int) -> str:
        """根据小时判断时间段"""
        if 6 <= hour < 9:
            return "早上"
        elif 9 <= hour < 12:
            return "上午"
        elif 12 <= hour < 14:
            return "中午"
        elif 14 <= hour < 18:
            return "下午"
        elif 18 <= hour < 22:
            return "晚上"
        else:
            return "深夜"

    def _extract_tags(self, text: str) -> list:
        """从文本中提取关键词标签"""
        tags = []
        keywords = {
            "工作": ["工作", "上班", "加班", "忙"],
            "吃饭": ["吃", "饭", "饿", "餐"],
            "学习": ["学", "作业", "考试", "复习"],
            "娱乐": ["看", "电影", "剧", "玩"],
            "运动": ["运动", "健身", "跑步"],
            "睡觉": ["睡", "困", "累", "休息"],
        }
        for tag, words in keywords.items():
            if any(w in text for w in words):
                tags.append(tag)
        return tags
