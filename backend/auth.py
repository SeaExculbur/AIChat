from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User ,ChatHistory
from flask_jwt_extended import jwt_required, get_jwt_identity

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password)
    )
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "注册成功", "access_token": token}), 201


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "用户名或密码错误"}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "登录成功", "access_token": token}), 200


@auth_bp.route("/api/auth/delete-account", methods=["DELETE"])
@jwt_required()
def delete_account():
    current_user_id = int(get_jwt_identity())   # token 里拿 id
    user = User.query.get(current_user_id)       # 只能删自己

    # 先删该用户的聊天记录
    ChatHistory.query.filter_by(user_id=current_user_id).delete()

    db.session.delete(user)
    db.session.commit()

    return jsonify({"message": "账号已删除"}), 200


@auth_bp.route("/api/auth/change-password" ,methods = ["POST"])
@jwt_required()
def change_password():
    data = request.get_json()
    changed_password = data.get("new_password")
    oldpassword = data.get("old_password")
    user_id = int(get_jwt_identity())
    user = User.query.filter_by(id=user_id).first()

    if not check_password_hash(user.password_hash, oldpassword):
        return jsonify({"error" : "密码错误"}), 401
    
    user.password_hash = generate_password_hash(changed_password)
    db.session.commit()
    return jsonify({"message" : "密码已修改！"}), 200

