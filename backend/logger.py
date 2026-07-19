import logging
import os
import uuid
from flask import request, has_request_context

_logger = logging.getLogger("aichat")

# 生产环境读环境变量，开发环境默认 INFO
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def init_app(app):
    """在 create_app() 里调用——注册钩子，配置日志格式"""
    _logger.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
    _logger.handlers.clear()    # 防止测试实例都注册到了_logger里，多条日志混合到一起

    # 控制台输出（Vercel/Render 自动收集标准输出，JSON 格式便于检索）
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _logger.addHandler(handler)

    # 每个请求进来分配一个唯一追踪 ID
    @app.before_request
    def _inject_request_id():
        request.request_id = str(uuid.uuid4())[:8]

    # 请求进来时打点
    @app.before_request
    def _log_request():
        _logger.info("→ %s %s | req=%s | ip=%s",
            request.method, request.path,
            getattr(request, "request_id", "-"),
            request.remote_addr)

    # 响应出去时打点
    @app.after_request
    def _log_response(response):
        _logger.info("← %s %s %s | req=%s",
            response.status_code, request.method, request.path,
            getattr(request, "request_id", "-"))
        return response


# ----- 业务函数——auth.py / chat.py 里调这些 -----

def info(msg, *args):
    """普通信息日志"""
    _logger.info(_with_req(msg, *args))

def warning(msg, *args):
    """警告日志"""
    _logger.warning(_with_req(msg, *args))

def error(msg, *args):
    """错误日志"""
    _logger.error(_with_req(msg, *args))

def exception(msg, *args):
    """异常日志——自动带堆栈追踪"""
    _logger.exception(_with_req(msg, *args))


def _with_req(msg, *args):
    """把当前的 request_id 拼进日志消息"""
    rid = getattr(request, "request_id", "-") if has_request_context() else "-"
    return f"[req={rid}] {msg}" % args if args else f"[req={rid}] {msg}"
