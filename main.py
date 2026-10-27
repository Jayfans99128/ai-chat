"""
AI-Girlfriend-Agent — CLI 交互入口

直接在终端中与 AI 女友对话。
"""
import sys
import os

# 确保能 import backend 包
sys.path.insert(0, os.path.dirname(__file__))

from backend.config import client, MODEL
from backend.agent.girlfriend_agent import GirlfriendAgent

agent = GirlfriendAgent(client, MODEL)

print("荧已上线！旅行者，和我说说话吧~ (输入 exit 退出)\n")

while True:
    try:
        user_input = input("你: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\n拜拜~下次再聊！")
        break

    if not user_input:
        continue
    if user_input.lower() in ("exit", "quit", "退出"):
        print("荧: 好的~下次再找你玩哦！拜拜！")
        break

    reply = agent.chat("cli_user", user_input)
    print(f"荧: {reply}")
    print()