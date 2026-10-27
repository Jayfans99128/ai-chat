"""
AI-Girlfriend-Agent — 用户认证模块

提供用户注册、登录、token验证功能
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
)
from .database import db, User, UserProfile

logger = logging.getLogger("auth")

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')
    nickname = data.get('nickname', '').strip() or username

    # 参数验证
    if not username or len(username) < 3:
        return jsonify({"error": "用户名至少3个字符"}), 400
    if not password or len(password) < 6:
        return jsonify({"error": "密码至少6个字符"}), 400

    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 409

    # 创建用户
    user = User(username=username, nickname=nickname)
    user.set_password(password)

    # 创建用户画像
    profile = UserProfile(user=user)

    db.session.add(user)
    db.session.add(profile)
    db.session.commit()

    # 生成token
    access_token = create_access_token(identity=str(user.id))

    logger.info("用户注册成功: %s (ID: %d)", username, user.id)

    return jsonify({
        "message": "注册成功",
        "user": user.to_dict(),
        "token": access_token,
    }), 201


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "请输入用户名和密码"}), 400

    # 查找用户
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "用户名或密码错误"}), 401

    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    db.session.commit()

    # 生成token
    access_token = create_access_token(identity=str(user.id))

    logger.info("用户登录成功: %s (ID: %d)", username, user.id)

    return jsonify({
        "message": "登录成功",
        "user": user.to_dict(),
        "token": access_token,
    })


@auth_bp.route('/api/auth/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """获取当前用户信息"""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    return jsonify({
        "user": user.to_dict(),
        "profile": user.profile.to_dict() if user.profile else {},
    })


@auth_bp.route('/api/auth/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """更新用户信息"""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    data = request.get_json(silent=True) or {}

    # 更新昵称
    if 'nickname' in data:
        user.nickname = data['nickname'].strip() or user.nickname

    # 更新用户画像
    if user.profile:
        if 'interests' in data:
            user.profile.interests = data['interests']
        if 'goals' in data:
            user.profile.goals = data['goals']

    db.session.commit()

    return jsonify({
        "message": "更新成功",
        "user": user.to_dict(),
        "profile": user.profile.to_dict() if user.profile else {},
    })
