"""
数据迁移脚本

将现有的JSON数据迁移到MySQL数据库
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
load_dotenv('.env.db')

# 添加backend到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from flask import Flask
from backend.database import db, init_db, User, Message, UserProfile

def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    init_db(app)
    return app

def migrate_conversations(app):
    """迁移对话历史"""
    sessions_dir = os.path.join(os.path.dirname(__file__), 'backend', 'data', 'conversations')

    if not os.path.exists(sessions_dir):
        print("  未找到对话历史目录，跳过")
        return 0

    count = 0
    with app.app_context():
        for filename in os.listdir(sessions_dir):
            if not filename.endswith('.json'):
                continue

            user_id_str = filename[:-5]  # 去掉.json后缀
            filepath = os.path.join(sessions_dir, filename)

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                messages = data.get('messages', [])
                if not messages:
                    continue

                # 检查用户是否存在（使用用户名作为user_id）
                username = f"user_{user_id_str}" if not user_id_str.startswith('user_') else user_id_str
                user = User.query.filter_by(username=username).first()

                if not user:
                    # 创建用户
                    user = User(username=username, nickname=username)
                    user.set_password('migrated_password')  # 迁移的用户需要重置密码
                    profile = UserProfile(user=user)
                    db.session.add(user)
                    db.session.add(profile)
                    db.session.flush()

                # 迁移消息
                for msg in messages:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')

                    if role == 'system':
                        continue  # 跳过system消息

                    message = Message(
                        user_id=user.id,
                        role=role,
                        content=content,
                        created_at=datetime.utcnow()
                    )
                    db.session.add(message)
                    count += 1

                print(f"  迁移用户 {username}: {len(messages)} 条消息")

            except Exception as e:
                print(f"  迁移文件 {filename} 失败: {e}")

        db.session.commit()

    return count

def migrate_profiles(app):
    """迁移用户画像"""
    profiles_dir = os.path.join(os.path.dirname(__file__), 'backend', 'data', 'profiles')

    if not os.path.exists(profiles_dir):
        print("  未找到用户画像目录，跳过")
        return 0

    count = 0
    with app.app_context():
        for filename in os.listdir(profiles_dir):
            if not filename.endswith('.json'):
                continue

            user_id_str = filename[:-5]
            filepath = os.path.join(profiles_dir, filename)

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                username = f"user_{user_id_str}" if not user_id_str.startswith('user_') else user_id_str
                user = User.query.filter_by(username=username).first()

                if user and user.profile:
                    # 更新用户画像
                    user.profile.interests = data.get('interests', [])
                    user.profile.goals = data.get('goals', [])
                    user.profile.personality = data.get('personality', {})
                    count += 1
                    print(f"  更新用户画像: {username}")

            except Exception as e:
                print(f"  迁移画像 {filename} 失败: {e}")

        db.session.commit()

    return count

def main():
    """主函数"""
    print("=" * 50)
    print("AI Girlfriend Agent - 数据迁移")
    print("=" * 50)

    app = create_app()

    print("\n1. 迁移对话历史...")
    msg_count = migrate_conversations(app)
    print(f"   完成: 迁移 {msg_count} 条消息")

    print("\n2. 迁移用户画像...")
    profile_count = migrate_profiles(app)
    print(f"   完成: 更新 {profile_count} 个用户画像")

    print("\n" + "=" * 50)
    print("数据迁移完成！")
    print("=" * 50)
    print("\n注意: 迁移的用户密码为 'migrated_password'，请提醒用户修改密码。")

if __name__ == "__main__":
    main()
