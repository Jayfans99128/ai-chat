"""
数据库初始化脚本

运行此脚本来创建数据库和表结构
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
load_dotenv('.env.db')

# 添加backend到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from flask import Flask
from backend.database import db, init_db

def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    init_db(app)
    return app

def init_database():
    """初始化数据库"""
    print("=" * 50)
    print("AI Girlfriend Agent - 数据库初始化")
    print("=" * 50)

    # 检查数据库配置
    db_user = os.getenv('DB_USER', 'root')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '3306')
    db_name = os.getenv('DB_NAME', 'ai_girlfriend')

    print(f"\n数据库配置:")
    print(f"  用户: {db_user}")
    print(f"  主机: {db_host}")
    print(f"  端口: {db_port}")
    print(f"  数据库: {db_name}")

    # 检查密码
    db_password = os.getenv('DB_PASSWORD', '')
    if not db_password:
        print("\n[警告] 未设置数据库密码，将使用空密码连接")
        print("  请在 .env.db 文件中设置 DB_PASSWORD")

    print("\n正在连接数据库...")

    try:
        app = create_app()
        with app.app_context():
            print("\n[成功] 数据库连接成功！")
            print("\n正在创建表结构...")

            # 显示创建的表
            from backend.database import User, Message, UserProfile, MessageLog
            print(f"  - {User.__tablename__}: 用户表")
            print(f"  - {Message.__tablename__}: 消息表")
            print(f"  - {UserProfile.__tablename__}: 用户画像表")
            print(f"  - {MessageLog.__tablename__}: 消息日志表")

            print("\n[成功] 数据库初始化完成！")

    except Exception as e:
        print(f"\n[错误] 数据库初始化失败: {e}")
        print("\n请检查:")
        print("1. MySQL服务是否正在运行")
        print("2. 数据库连接信息是否正确")
        print("3. 数据库用户是否有创建表的权限")
        print("\n数据库配置文件: .env.db")
        return False

    return True

if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
