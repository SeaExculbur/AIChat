# AIChat

AI 聊天网站，基于 **Vue 3 + Flask + DeepSeek API** 的全栈智能对话平台。

线上地址：<https://seaexculbur.com>

## 功能

- 流式对话 — 打字机逐字输出
- 多轮记忆 — 上下文连贯，对话不失忆
- 用户系统 — 注册、登录、JWT 鉴权
- 管理员放行 — 新用户注册后需在服务器执行 `admin.py approve` 才能登录
- 历史记录 — 刷新不丢失，可回顾过往对话
- 响应式界面 — 适配手机和桌面端

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 (Composition API) + Vite + Naive UI + Pinia + Vue Router |
| 后端 | Python Flask + Flask-CORS + Flask-JWT-Extended |
| 数据库 | SQLAlchemy + SQLite (开发) / PostgreSQL (生产) |
| AI | DeepSeek API（OpenAI 兼容接口） |
| 部署 | Docker Compose (PostgreSQL + Gunicorn/Flask + Nginx + Let's Encrypt) |

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
│   ├── admin.py           # 管理员放行 CLI
│   ├── requirements.txt
│   ├── gunicorn_config.py # Gunicorn 生产配置
│   ├── Dockerfile         # Flask 容器镜像
│   ├── alembic.ini        # 数据库迁移配置
│   └── alembic/           # 迁移脚本
├── frontend/              # Vue 3 前端
│   ├── Dockerfile         # Node 构建 → Nginx 托管（多阶段）
│   ├── .dockerignore      # 排除 node_modules / dist
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
- Node.js 22+
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
| `SECRET_KEY` | Flask 会话签名密钥（随机字符串） |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `JWT_SECRET_KEY` | JWT 签名密钥（随机字符串） |
| `DATABASE_URL` | 数据库连接地址（开发默认 SQLite，生产指向 PostgreSQL） |

## 部署（Docker）

当前生产环境：阿里云 ECS + Docker Compose（PostgreSQL 18 + Gunicorn/Flask + Nginx），HTTPS 由 Let's Encrypt 提供。

### 首次部署

```bash
# 构建（2G 内存建议分两次，避免并行构建 OOM）
docker compose build flask
docker compose build nginx

# 启动
docker compose up -d

# 建表
docker compose exec flask alembic upgrade head

# 放行用户
docker compose exec flask python admin.py list
docker compose exec flask python admin.py approve <用户名>
```

> 源码上传：如果服务器不能访问 GitHub，用 `tar | ssh` 传源码，不要 `git clone`。完整步骤见 `Plan/部署与运维/公网上线实录——从本地Docker到HTTPS.md`。

### 域名与 HTTPS

- 域名 A 记录指向服务器公网 IP
- 安全组放行 80 / 443
- certbot 用 webroot 方式签发 Let's Encrypt 证书
- 80 端口除 `/.well-known/acme-challenge/` 外全部 301 到 HTTPS
- 续期后自动 reload nginx：`/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`

详见 `Plan/部署与运维/HTTPS证书与TLS握手.md`。

### 更新代码

```bash
# 只改后端
docker compose build flask
docker compose up -d --no-deps flask

# 只改前端
docker compose build nginx
docker compose up -d --no-deps nginx

# 改了表结构
docker compose exec flask alembic upgrade head
```

生产环境变量使用 `backend/.env.production`（不入库），compose 通过 `env_file` 注入；模板见 `backend/.env.example`。

> PostgreSQL 密码通过项目根目录的 `.env` 提供给 Compose 插值（`${POSTGRES_PASSWORD}`），必须与 `backend/.env.production` 里 `DATABASE_URL` 的密码一致。根目录 `.env` 和 `backend/.env.production` 都不入库。完整链路见 `Plan/部署与运维/环境变量与密钥注入.md`。

## License

MIT
