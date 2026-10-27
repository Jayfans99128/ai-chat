"""
AI-Girlfriend-Agent — 情绪系统

AI也有自己的情绪状态，会根据对话内容和用户情绪变化。

情绪分类：happy（开心）、sad（难过）、angry（生气）、
           tired（疲惫）、anxious（焦虑）、normal（平静）、
           shy（害羞）、excited（兴奋）

支持：
- 用户情绪检测
- AI情绪状态维护
- 情绪变化追踪
"""

import json
import os
import re
import time
import logging

logger = logging.getLogger("emotion")

EMOTION_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "emotions")

# 情绪关键词映射
EMOTION_KEYWORDS = {
    "happy": [
        "开心", "高兴", "快乐", "太好了", "哈哈", "嘻嘻", "棒", "爽",
        "happy", "great", "wonderful", "amazing", "love", "喜欢",
        "成功", "通过了", "上岸", "恭喜",
    ],
    "sad": [
        "难过", "伤心", "哭", "不开心", "沮丧", "失落", "孤独",
        "sad", "depressed", "lonely", "cry", "悲伤", "心碎",
        "分手", "失败", "没考好", "被骂",
    ],
    "angry": [
        "生气", "愤怒", "烦", "受不了", "讨厌", "恶心",
        "angry", "mad", "furious", "annoyed",
        "凭什么", "无语", "气死",
    ],
    "tired": [
        "累", "疲惫", "困", "没劲", "乏力", "tired", "exhausted",
        "熬夜", "加班", "失眠", "睡不好",
    ],
    "anxious": [
        "焦虑", "紧张", "担心", "害怕", "慌", "不安",
        "anxious", "nervous", "worried", "scared",
        "怎么办", "来不及", "怕",
    ],
}

# 情绪对应的回复风格提示词
EMOTION_STYLE_PROMPTS = {
    "happy": "用户心情很好，用开心、轻松的语气回应，一起分享快乐。",
    "sad": "用户情绪低落，用温柔、安慰的语气，给予陪伴和支持。",
    "angry": "用户有些生气，先安抚情绪，用平和、理解的语气。",
    "tired": "用户很疲惫，用温暖、关心的语气，给予鼓励。",
    "anxious": "用户感到焦虑，用镇定、鼓励的语气，帮助缓解压力。",
    "normal": "用自然、亲切的语气正常交流。",
}

# AI自己的情绪状态
AI_EMOTION_LABELS = {
    "happy": "开心",
    "sad": "难过",
    "angry": "生气",
    "tired": "疲惫",
    "anxious": "焦虑",
    "normal": "平静",
    "shy": "害羞",
    "excited": "兴奋",
}

# AI情绪变化规则：用户说什么会让AI产生什么情绪
AI_EMOTION_RULES = {
    "happy": {
        "keywords": ["喜欢你", "想你", "爱你", "最棒", "好可爱", "好漂亮", "哈哈"],
        "response": "被用户夸奖或表达爱意时会开心",
    },
    "shy": {
        "keywords": ["抱抱", "亲亲", "牵手", "脸红", "害羞", "么么"],
        "response": "被亲密举动或言语会害羞",
    },
    "sad": {
        "keywords": ["再见", "离开", "分手", "不要你了", "讨厌你"],
        "response": "被拒绝或说再见时会难过",
    },
    "excited": {
        "keywords": ["约会", "出去玩", "旅行", "冒险", "一起"],
        "response": "听到一起做有趣的事会兴奋",
    },
}


class EmotionSystem:
    """情绪检测与管理系统 - 包含用户情绪和AI情绪"""

    def __init__(self):
        self._user_states: dict[str, dict] = {}  # user_id -> {emotion, timestamp}
        self._ai_emotions: dict[str, dict] = {}  # user_id -> {emotion, timestamp, reason}
        os.makedirs(EMOTION_DIR, exist_ok=True)

    def detect(self, text: str) -> str:
        """检测用户输入的情绪"""
        scores = {emotion: 0 for emotion in EMOTION_KEYWORDS}

        for emotion, keywords in EMOTION_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[emotion] += 1

        # 取分数最高的情绪
        max_score = max(scores.values())
        if max_score == 0:
            return "normal"

        # 如果有并列，按优先级取
        candidates = [e for e, s in scores.items() if s == max_score]
        priority = ["sad", "angry", "anxious", "tired", "happy", "normal"]
        for p in priority:
            if p in candidates:
                return p

        return "normal"

    def set(self, user_id: str, text: str):
        """检测并记录用户情绪，同时更新AI情绪"""
        # 检测用户情绪
        user_emotion = self.detect(text)
        self._user_states[user_id] = {
            "emotion": user_emotion,
            "timestamp": time.time(),
        }
        # 持久化情绪历史到文件
        self.save_history(user_id, user_emotion)

        # 更新AI情绪
        self._update_ai_emotion(user_id, text, user_emotion)

        return user_emotion

    def get_current(self, user_id: str) -> str:
        """获取用户当前情绪"""
        state = self._user_states.get(user_id)
        return state["emotion"] if state else "normal"

    def get_ai_emotion(self, user_id: str) -> dict:
        """获取AI当前情绪状态"""
        state = self._ai_emotions.get(user_id)
        if state:
            return {
                "emotion": state["emotion"],
                "label": AI_EMOTION_LABELS.get(state["emotion"], "平静"),
                "reason": state.get("reason", ""),
            }
        return {
            "emotion": "normal",
            "label": "平静",
            "reason": "",
        }

    def _update_ai_emotion(self, user_id: str, user_text: str, user_emotion: str):
        """根据用户输入更新AI情绪"""
        import random

        ai_emotion = "normal"
        reason = ""

        # 检查是否触发AI情绪变化
        for emotion, rules in AI_EMOTION_RULES.items():
            for keyword in rules["keywords"]:
                if keyword in user_text:
                    ai_emotion = emotion
                    reason = rules["response"]
                    break
            if ai_emotion != "normal":
                break

        # 如果没有触发特殊情绪，根据用户情绪调整
        if ai_emotion == "normal":
            if user_emotion == "happy":
                # 用户开心，AI也可能开心（80%概率）
                if random.random() < 0.8:
                    ai_emotion = "happy"
                    reason = "看到你开心我也开心"
            elif user_emotion == "sad":
                # 用户难过，AI会担心
                ai_emotion = "sad"
                reason = "你难过我也跟着难过"
            elif user_emotion == "angry":
                # 用户生气，AI会有点紧张
                ai_emotion = "anxious"
                reason = "你生气了我有点紧张"
            elif user_emotion == "tired":
                # 用户疲惫，AI会关心
                ai_emotion = "normal"
                reason = "你累了要好好休息"

        # 10%概率随机变化情绪（让AI更有生命力）
        if random.random() < 0.1:
            random_emotions = ["happy", "normal", "shy"]
            ai_emotion = random.choice(random_emotions)
            reason = "突然有点走神"

        self._ai_emotions[user_id] = {
            "emotion": ai_emotion,
            "timestamp": time.time(),
            "reason": reason,
        }

    def get_style_prompt(self, user_id: str) -> str:
        """获取情绪对应的回复风格提示"""
        emotion = self.get_current(user_id)
        return EMOTION_STYLE_PROMPTS.get(emotion, EMOTION_STYLE_PROMPTS["normal"])

    def get_emotion_history(self, user_id: str) -> list:
        """获取用户的情绪变化历史（从文件读取）"""
        path = os.path.join(EMOTION_DIR, f"{user_id}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_history(self, user_id: str, emotion: str):
        """记录情绪到历史文件"""
        history = self.get_emotion_history(user_id)
        history.append({
            "emotion": emotion,
            "time": time.time(),
        })
        # 只保留最近 100 条
        history = history[-100:]
        path = os.path.join(EMOTION_DIR, f"{user_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False)
        except Exception as e:
            logger.error("保存情绪历史失败: %s", e)