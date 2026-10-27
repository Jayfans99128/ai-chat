"""
AI-Girlfriend-Agent — 数据库配置和模型

使用 MySQL + SQLAlchemy 进行数据持久化
"""

import os
import logging
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

logger = logging.getLogger("database")

# 数据库实例（在app.py中初始化）
db = SQLAlchemy()
bcrypt = Bcrypt()


# ── 用户模型 ──────────────────────────────────────────────
class User(db.Model):
    """用户表"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nickname = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # 关系
    messages = db.relationship('Message', backref='user', lazy='dynamic')
    profile = db.relationship('UserProfile', backref='user', uselist=False)

    def set_password(self, password):
        """设置密码哈希"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """验证密码"""
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
        }


# ── 对话消息模型 ──────────────────────────────────────────
class Message(db.Model):
    """对话消息表"""
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    role = db.Column(db.Enum('user', 'assistant', 'system'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    emotion = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'role': self.role,
            'content': self.content,
            'emotion': self.emotion,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ── 用户画像模型 ──────────────────────────────────────────
class UserProfile(db.Model):
    """用户画像表（长期记忆）"""
    __tablename__ = 'user_profiles'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    interests = db.Column(db.JSON)  # 兴趣爱好
    goals = db.Column(db.JSON)      # 目标/计划
    personality = db.Column(db.JSON) # 从对话中提取的性格特征
    last_chat_time = db.Column(db.DateTime)  # 最后聊天时间
    active_hours = db.Column(db.JSON)  # 活跃时段 [hour1, hour2, ...]
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'interests': self.interests or [],
            'goals': self.goals or [],
            'personality': self.personality or {},
            'last_chat_time': self.last_chat_time.isoformat() if self.last_chat_time else None,
            'active_hours': self.active_hours or [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ── 消息日志模型（用于分析用户习惯）────────────────────────
class MessageLog(db.Model):
    """消息日志表"""
    __tablename__ = 'message_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    message_type = db.Column(db.Enum('user', 'assistant'), nullable=False)
    content = db.Column(db.Text)
    hour_of_day = db.Column(db.Integer)  # 0-23，用于分析活跃时段
    day_of_week = db.Column(db.Integer)  # 0-6 (周一-周日)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


def init_db(app):
    """初始化数据库"""
    from urllib.parse import quote_plus
    # 数据库连接配置
    db_user = os.getenv('DB_USER', 'root')
    db_password = os.getenv('DB_PASSWORD', '')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '3306')
    db_name = os.getenv('DB_NAME', 'ai_girlfriend')

    # URL编码密码，处理特殊字符如 @ .
    encoded_password = quote_plus(db_password)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}?charset=utf8mb4'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }

    # JWT配置
    jwt_secret_key = os.getenv('JWT_SECRET_KEY')
    if not jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY must be configured in the environment or .env.db file")
    app.config['JWT_SECRET_KEY'] = jwt_secret_key
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 86400  # 24小时

    db.init_app(app)
    bcrypt.init_app(app)

    # 创建所有表
    with app.app_context():
        db.create_all()
        logger.info("数据库表已创建/更新")

    return db
