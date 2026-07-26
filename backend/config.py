import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1 MB
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///instance/aichat.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False