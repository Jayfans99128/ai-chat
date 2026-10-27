"""
AI-Girlfriend-Agent — 日常聊天技能

负责日常闲聊、问候、关心日常生活等场景。
"""

import logging
import random
import datetime

logger = logging.getLogger("skill_chat")

# 每日不同时段的问候语
GREETINGS = {
    "morning": [
        "早上好呀~今天有什么计划吗？",
        "早安~昨晚睡得好吗？",
        "新的一天又开始啦，今天也要加油哦！",
    ],
    "afternoon": [
        "下午好~今天过得怎么样？",
        "午饭吃了吗？要好好吃饭哦！",
        "下午容易犯困，要不要起来活动一下？",
    ],
    "evening": [
        "晚上好~今天辛苦啦！",
        "天黑啦，回家路上注意安全哦~",
        "晚饭吃了什么好吃的呀？",
    ],
    "night": [
        "夜深了，早点休息哦~",
        "还不睡呀？熬夜对身体不好呢！",
        "晚安啦，做个好梦~明天见！",
    ],
}

# 关心问候
CARE_MESSAGES = [
    "今天有没有好好吃饭呀？",
    "最近天气变化大，要注意保暖哦~",
    "工作/学习再忙也要记得休息一下！",
    "喝杯水放松一下吧~",
    "你最近好像很忙，要注意身体哦！",
]


def get_greeting() -> str:
    """根据当前时间返回合适的问候语"""
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        period = "morning"
    elif 12 <= hour < 18:
        period = "afternoon"
    elif 18 <= hour < 22:
        period = "evening"
    else:
        period = "night"
    return random.choice(GREETINGS[period])


def get_care_message() -> str:
    """随机返回一条关心消息"""
    return random.choice(CARE_MESSAGES)