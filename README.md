# AIChat

AI 聊天网站，基于 **Vue 3 + Flask + DeepSeek API** 的全栈智能对话平台。

## 功能

- 流式对话 — 打字机逐字输出
- 多轮记忆 — 上下文连贯，对话不失忆
- 用户系统 — 注册、登录、JWT 鉴权
- 历史记录 — 刷新不丢失，可回顾过往对话
- 响应式界面 — 适配手机和桌面端

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 (Composition API) + Vite + Naive UI + Pinia + Vue Router |
| 后端 | Python Flask + Flask-CORS + Flask-JWT-Extended |
| 数据库 | SQLAlchemy + SQLite (开发) / PostgreSQL (生产) |
| AI | DeepSeek API（OpenAI 兼容接口） |
| 部署 | Docker Compose (Gunicorn + Nginx 反向代理) |

## 项目结构

```
AIChat_v1.0/
├── backend/                # Flask 后端
│   ├── app.py             # 入口
│   ├── config.py          # 配置
│   ├── models.py          # 数据模型
│   ├── auth.py            # 用户认证
│   ├── chat.py            # 聊天接口（SSE 流式）
│   ├── logger.py          # 日志系统
│   ├── requirements.txt
│   ├── gunicorn_config.py # Gunicorn 生产配置
│   ├── Dockerfile         # Flask 容器镜像
│   ├── alembic.ini        # 数据库迁移配置
│   └── alembic/           # 迁移脚本
├── frontend/              # Vue 3 前端
│   ├── Dockerfile         # Vue 多阶段构建（预留）
│   └── src/
│       ├── views/         # 页面
│       ├── router/        # 路由
│       └── App.vue        # 根组件
├── nginx/
│   └── nginx.conf         # 反向代理 + 静态文件
├── docker-compose.yml     # 容器编排
├── Plan/                  # 项目文档
└── README.md
```

## 本地开发

### 环境要求

- Python 3.13+
- Node.js 18+
- Git

### 后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env    # 编辑 .env 填入 DEEPSEEK_API_KEY
python app.py           # 默认 http://localhost:5000
```

### 前端

```bash
cd frontend
npm install
npm run dev             # 默认 http://localhost:5173
```

前端已配置 Vite 代理，`/api` 请求自动转发到后端 `localhost:5000`。

### 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `JWT_SECRET_KEY` | JWT 签名密钥（随机字符串） |
| `DATABASE_URL` | 数据库连接地址（默认 SQLite） |

## 部署（Docker）

```bash
# 构建前端
cd frontend && npm run build

# 一键启动（Flask + Nginx）
cd ..
docker compose up -d --build

# 访问
# http://localhost（前端 + API 代理）
```

### 生产环境迁移

```bash
# 首次部署
git pull && docker compose up -d --build

# 数据库迁移
docker compose exec flask alembic upgrade head

# 更新代码
git pull && docker compose up -d --build
```

## License

MIT
