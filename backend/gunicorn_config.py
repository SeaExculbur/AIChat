# Gunicorn 生产配置
# 启动命令：gunicorn -c gunicorn_config.py "app:create_app()"

workers = 4
worker_class = "sync"
threads = 1
bind = "0.0.0.0:5000"
accesslog = "-"
errorlog = "-"
loglevel = "info"
timeout = 120
graceful_timeout = 30
proc_name = "aichat"
