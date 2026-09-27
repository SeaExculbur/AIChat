from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User ,ChatHistory
from datetime import timedelta
from flask_jwt_extended import jwt_required, get_jwt_identity
import logger

auth_bp = Blueprint("auth", __name__)

# 注册接口
@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        logger.warning("注册失败——用户名或密码为空")
        return jsonify({"error": "用户名和密码不能为空"}), 400

    if not (3 <= len(username) <= 20):
        logger.warning("注册失败——用户名长度不合法")
        return jsonify({"error": "用户名长度需为 3~20 个字符"}), 400

    if not (8 <= len(password) <= 128):
        logger.warning("注册失败——密码长度不合法")
        return jsonify({"error": "密码长度需为 8~128 个字符"}), 400

    if User.query.filter_by(username=username).first():
        logger.warning("注册失败——用户名 %s 已存在", username)
        return jsonify({"error": "用户名已存在"}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password)
    )
    db.session.add(user)
    db.session.commit()

    logger.info("用户 %s 注册成功，等待放行，user_id=%s", username, user.id)
    return jsonify({"message": "注册成功，请等待管理员放行"}), 201

# 登录接口
@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        logger.warning("登录失败——用户名或密码为空")
        return jsonify({"error": "用户名和密码不能为空"}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        logger.warning("用户 %s 登录失败——密码错误", username)
        return jsonify({"error": "用户名或密码错误"}), 401

    if not user.is_active:
        logger.warning("user_id=%s 登录失败--账号尚未放行", user.id)
        return jsonify({"error" : "账号待审核，请等待管理员放行"}), 403
    
    logger.info("用户 %s 登录成功", username)
    token = create_access_token(identity=str(user.id), expires_delta=timedelta(hours=2))
    return jsonify({"message": "登录成功", "access_token": token}), 200

# 删除账号接口
@auth_bp.route("/api/auth/delete-account", methods=["DELETE"])
@jwt_required()
def delete_account():
    current_user_id = int(get_jwt_identity())   # token 里拿 id
    user = User.query.get(current_user_id)       # 只能删自己

    # 先删该用户的聊天记录
    ChatHistory.query.filter_by(user_id=current_user_id).delete()

    db.session.delete(user)
    db.session.commit()

    logger.info("user_id=%s 已删除账号及所有聊天记录", current_user_id)
    return jsonify({"message": "账号已删除"}), 200

# 改密码接口
@auth_bp.route("/api/auth/change-password", methods=["POST"])
@jwt_required()
def change_password():
    current_user_id = int(get_jwt_identity())
    data = request.get_json()
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if not old_password or not new_password:
        logger.warning("user_id=%s 改密码失败——密码为空", current_user_id)
        return jsonify({"error": "新旧密码都不能为空"}), 400

    if not (8 <= len(new_password) <= 128):
        logger.warning("user_id=%s 改密码失败——新密码长度不合法", current_user_id)
        return jsonify({"error": "新密码长度需为 8~128 个字符"}), 400

    user = User.query.filter_by(id=current_user_id).first()
    if user is None:
        return jsonify({"error": "用户不存在"}), 404

    if not check_password_hash(user.password_hash, old_password):
        logger.warning("user_id=%s 改密码失败——旧密码错误", current_user_id)
        return jsonify({"error": "密码错误"}), 401

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    logger.info("user_id=%s 密码修改成功", current_user_id)
    return jsonify({"message": "密码已修改！"}), 200
