from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
from openai import OpenAI
from models import db, ChatHistory
import os

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/api/chat", methods=["POST"])
@jwt_required()
def chat():
    current_user_id = int(get_jwt_identity())
    data = request.get_json()
    user_message = data.get("message", "")

    if not user_message.strip():
        return jsonify({"error": "消息不能为空"}), 400

    # 查该用户最近 20 条历史消息
    history = ChatHistory.query.filter_by(user_id=current_user_id) \
        .order_by(ChatHistory.created_at.desc()).limit(20).all()
    history.reverse()

    messages = [{"role": msg.role, "content": msg.content} for msg in history]
    messages.append({"role": "user", "content": user_message})

    # 存用户消息
    user_msg_record = ChatHistory(user_id=current_user_id, role="user", content=user_message)
    db.session.add(user_msg_record)
    db.session.commit()

    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1"
    )

    def generate():
        ai_words = []
        response = client.chat.completions.create(
        model="deepseek-v4-pro",
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
            except:
                yield "data: [ERROR]\n\n"
        yield "data: [DONE]\n\n"

        reply_text = "".join(ai_words)
        ai_message = ChatHistory(user_id=current_user_id, role="assistant", content=reply_text)
        db.session.add(ai_message)
        db.session.commit()
        
        
    return Response(generate(), mimetype="text/event-stream")


@chat_bp.route("/api/history", methods=["GET"])
@jwt_required()
def history():
    current_user_id = int(get_jwt_identity())
    page = request.args.get("page", 1 ,type=int)
    per_page = request.args.get("per_page", 20 ,type=int)
    pagination = ChatHistory.query.filter_by(user_id=current_user_id) \
        .order_by(ChatHistory.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "messages": [{"role": m.role, "content": m.content, "time": m.created_at.isoformat()} for m in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total
    }), 200
