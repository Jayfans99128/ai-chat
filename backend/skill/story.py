"""
AI-Girlfriend-Agent — 讲故事技能

提供简短温暖的小故事、睡前故事、治愈系故事等。
"""

import logging
import random

logger = logging.getLogger("skill_story")

STORIES = [
    {
        "title": "小星星的旅行",
        "content": (
            "有一颗小星星觉得在天上太无聊了，于是它偷偷溜到地球上玩。"
            "它变成了一只萤火虫，在森林里飞来飞去。"
            "它遇到了一只迷路的小兔子，就用自己的光帮小兔子找到了回家的路。"
            "小兔子的妈妈为了感谢它，做了最甜的胡萝卜蛋糕。"
            "小星星想：原来帮助别人，自己也会感到温暖呀。"
            "后来它回到天上，每次看到地上的萤火虫都会想起那个香甜的夜晚。"
        ),
        "mood": "calm",
    },
    {
        "title": "慢吞吞的小乌龟",
        "content": (
            "小乌龟总是被朋友们说太慢了。"
            "有一天森林里发大水，朋友们都慌慌张张地跑。"
            "小乌龟不慌不忙地带着大家爬上了一块大石头。"
            "它对大家说：'慢一点也没关系，重要的是方向是对的。'"
            "从那以后，朋友们再也不嫌它慢了。"
            "有时候慢一点，反而能看得更清楚呢。"
        ),
        "mood": "encouraging",
    },
    {
        "title": "云朵棉花糖",
        "content": (
            "小狐狸看到天上的云朵，觉得那一定是棉花糖。"
            "它爬上山坡，跳起来想抓一朵。"
            "但怎么也够不着。"
            "这时风来了，一朵小小的云飘到了它面前。"
            "小狐狸尝了一口——真的是甜的！"
            "原来呀，当你真心想要一样东西的时候，全世界都会来帮你。"
        ),
        "mood": "sweet",
    },
]


def get_story(mood: str = None) -> dict:
    """根据心情获取一个故事"""
    if mood:
        matching = [s for s in STORIES if s["mood"] == mood]
        if matching:
            return random.choice(matching)
    return random.choice(STORIES)


def get_random_story() -> str:
    """获取一个随机故事的内容"""
    story = get_story()
    return f"{story['title']}\\n\\n{story['content']}"


def get_bedtime_story() -> str:
    """获取一个适合睡前听的故事"""
    calm_stories = [s for s in STORIES if s["mood"] == "calm"]
    if not calm_stories:
        calm_stories = STORIES
    story = random.choice(calm_stories)
    return f"🌙 睡前故事：{story['title']}\\n\\n{story['content']}\\n\\n晚安，好梦~"