from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db
from logger import init_app as init_logger


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    CORS(app)
    JWTManager(app)
    init_logger(app)

    # 注册蓝图
    from auth import auth_bp
    app.register_blueprint(auth_bp)
    from chat import chat_bp
    app.register_blueprint(chat_bp)

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
