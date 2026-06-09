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
| 前端 | Vue 3 (Composition API) + Vite + Naive UI + Tailwind CSS + Pinia + Vue Router |
| 后端 | Python Flask + Flask-CORS + Flask-JWT-Extended |
| 数据库 | SQLAlchemy + SQLite (开发) / PostgreSQL (生产) |
| AI | DeepSeek API（OpenAI 兼容接口） |
| 部署 | Gunicorn + Nginx / Vercel + Railway |

## 项目结构

```
AIChat_v1.0/
├── backend/                # Flask 后端
│   ├── app.py             # 入口
│   ├── config.py          # 配置
│   ├── models.py          # 数据模型
│   ├── auth.py            # 用户认证
│   ├── chat.py            # 聊天接口（SSE 流式）
│   └── requirements.txt
├── frontend/              # Vue 3 前端
│   └── src/
│       ├── views/         # 页面
│       ├── components/    # 组件
│       ├── api/           # Axios 封装
│       ├── router/        # 路由
│       └── store/         # Pinia 状态
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

## 部署

- 后端 → [Railway](https://railway.app) / [Render](https://render.com)
- 前端 → [Vercel](https://vercel.com) / [Netlify](https://netlify.com)

## License

MIT
