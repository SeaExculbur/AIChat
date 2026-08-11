from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_jwt_extended import jwt_required, get_jwt_identity
from openai import OpenAI
from models import db, ChatHistory, Conversation
import os
import logger

chat_bp = Blueprint("chat", __name__)

# 数据库分页
def paginate_query(query):
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    return query.paginate(page=page, per_page=per_page, error_out=False)
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)

# 聊天业务主接口
@chat_bp.route("/api/chat", methods=["POST"])
@jwt_required()
def chat():
    current_user_id = int(get_jwt_identity())
    data = request.get_json()
    user_message = data.get("message", "")
    conversation_id = data.get("conversation_id")

    if not user_message.strip():
        return jsonify({"error": "消息不能为空"}), 400

    # 创建新会话
    if conversation_id is None:
        title = user_message[:20]
        conv = Conversation(user_id=current_user_id, title=title)
        db.session.add(conv)
        db.session.commit()
        conversation_id = conv.id

    # 查该用户最近 20 条历史消息
    history = ChatHistory.query.filter_by(user_id=current_user_id, conversation_id=conversation_id) \
        .order_by(ChatHistory.created_at.desc()).limit(20).all()
    history.reverse()

    messages = [{"role": msg.role, "content": msg.content} for msg in history]
    messages.append({"role": "user", "content": user_message})

    # 存用户消息
    user_msg_record = ChatHistory(user_id=current_user_id, conversation_id=conversation_id, role="user", content=user_message)
    db.session.add(user_msg_record)
    db.session.commit()
    logger.info("user_id=%s 发了一条消息", current_user_id)

    def generate():
        yield f"data: {{\"conversation_id\": {conversation_id}}}\n\n"
        ai_words = []
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            stream=True,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}}
        )
        for chunk in response:
            try:
                word = chunk.choices[0].delta.content
                if word is not None:
                    ai_words.append(word)
                    yield f"data: {word}\n\n"
            except Exception as e:
                logger.error("SSE chunk 解析失败：%s", e)
                yield "data: [ERROR]\n\n"

        reply_text = "".join(ai_words)
        if reply_text:
            try:
                if reply_text:
                    ai_message = ChatHistory(user_id=current_user_id, conversation_id=conversation_id, role="assistant", content=reply_text)
                    db.session.add(ai_message)
                    db.session.commit()
                    logger.info("user_id=%s AI 回复已存库，长度=%s", current_user_id, len(reply_text))
            except Exception as e:
                logger.error("user_id=%s AI 消息存库失败: %s", current_user_id, e)
                yield "data: [DB_ERROR]\n\n"

        yield "data: [DONE]\n\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream")

# 聊天历史查询
@chat_bp.route("/api/history", methods=["GET"])
@jwt_required()
def history():
    current_user_id = int(get_jwt_identity())
    pagination = paginate_query(
    ChatHistory.query.filter_by(user_id=current_user_id)
    .order_by(ChatHistory.created_at.desc())
    )

    return jsonify({
        "messages": [{"role": m.role, "content": m.content, "time": m.created_at.isoformat()} for m in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total
    }), 200

# 会话列表(左侧栏)
@chat_bp.route("/api/conversations", methods=["GET"])
@jwt_required()
def list_conversation():
    current_user_id = int(get_jwt_identity())
    convs = Conversation.query.filter_by(user_id=current_user_id) \
    .order_by(Conversation.updated_at.desc()).all()

    return jsonify([
        {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}
        for c in convs
    ]), 200

# 某会话聊天记录(右侧聊天框)
@chat_bp.route("/api/conversations/<int:conv_id>", methods=["GET"])
@jwt_required()
def get_conversation(conv_id):
    current_user_id = int(get_jwt_identity())

    # 验证会话是否属于当前用户
    conv = Conversation.query.filter_by(id=conv_id, user_id=current_user_id).first()
    if conv is None:
        return jsonify({"error": "会话不存在"}), 404

    pagination = paginate_query(
    ChatHistory.query.filter_by(conversation_id=conv_id)
    .order_by(ChatHistory.created_at.asc())
    )

    return jsonify({
        "id": conv.id,
        "title": conv.title,
        "messages": [{"role": m.role, "content": m.content, "time": m.created_at.isoformat()}
                     for m in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total
    }), 200

# 删除会话
@chat_bp.route("/api/conversations/<int:conv_id>", methods=["DELETE"])
@jwt_required()
def delete_conversation(conv_id):
    current_user_id = int(get_jwt_identity())

    conv = Conversation.query.filter_by(id=conv_id, user_id=current_user_id).first()
    if not conv:
        return jsonify({"error": "会话不存在"}) , 404

    ChatHistory.query.filter_by(conversation_id=conv_id).delete()
    db.session.delete(conv)
    db.session.commit()

    return jsonify({"message": "已删除"}), 200