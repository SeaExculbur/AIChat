# Alembic 数据库迁移系统

> 项目：AIChat v1.0
> 日期：2026-07-26
> 覆盖：Alembic 初始化、autogenerate diff 机制、revision vs upgrade、版本管理流程、secrets 密钥生成、.env.example 规范

---

## 一、为什么需要 Alembic——`db.create_all()` 的致命缺陷

### 没它时

```python
# app.py
with app.app_context():
    db.create_all()   # CREATE TABLE IF NOT EXISTS
```

`db.create_all()` 的职责只有一条：**"表不存在就建"**。它检查的是整张表的存在性，不是逐列比对。一旦项目有了真实用户数据，在 models.py 里加新列或改类型时，`db.create_all()` 不会更新已有表——因为表已经存在了。

```
第一次跑：建了 users 表（id, username, password_hash, created_at）
加了一列 avatar_url → 再跑一次
  → 数据库一看：users 表已存在，跳过
  → 老表还是 4 列，avatar_url 永远不会被加进去
```

不是 SQLite 的问题——是 `db.create_all()` 的定位：只负责第一次建表，不管建好之后的任何结构变更。像 `mkdir` 命令——目录存在就跳过，不会进去帮你新增子文件夹。

### 有它后

Alembic = 数据库结构的 Git。每次表结构变更写成带版本号的迁移脚本文件，可追踪、可回滚、可重现。

```
迁移脚本目录 versions/
├── d982e2ee7cc7_initial.py      ← 首次基准版本
├── a1b2c3_add_avatar_url.py     ← 给 User 加 avatar_url 列
└── e4f5g6_add_settings_table.py ← 新增 settings 表

alembic_version 表存着当前执行到了哪个版本号。
```

---

## 二、核心工作流

```
1. 修改 models.py（加列/改类型/加表）

2. alembic revision --autogenerate -m "描述"
   → 对比 models.py（应该长什么样）和数据库（现在长什么样）
   → 自动生成 diff 脚本到 versions/ 目录
   → 只写文件，不碰数据库

3. 检查生成的脚本——autogenerate 不完美，有些变更检测不到

4. alembic upgrade head
   → 执行未应用的迁移脚本
   → 创建/更新 alembic_version 表
   → 写入新版本号

5. 迁移脚本提交到 Git——其他人 pull 后跑 upgrade head 同步
```

### revision（写剧本）vs upgrade（演剧本）

**revision**：对比 models.py 和数据库 → 生成差异脚本到 `versions/` 目录 → 只写磁盘，不碰数据库。

**upgrade**：读 `versions/` 目录下未执行的脚本 → 执行 `upgrade()` 函数 → 在 `alembic_version` 表里写入版本号。同一个版本号串联两个阶段——revision 在文件里创版本，upgrade 读版本文件、执行、记录。

### 回滚

```bash
alembic downgrade -1    # 回退一个版本
```

`downgrade()` 函数是 `upgrade()` 的反操作——autogenerate 会自动生成对应的反向 SQL。

---

## 三、autogenerate 的 diff 机制——到底做了什么

`revision --autogenerate` 做的事：拿着 `db.metadata`（models.py 定义的表结构）和数据库实际表结构，逐表逐列做 diff。

```
目标（从 db.metadata 读到）      实际（从数据库读到）
──────────────────────          ────────────────────
User 表：                        users 表：
  id: Integer, pk                  id: INTEGER, PK
  username: String(80), unique     username: VARCHAR(80), UNIQUE
  ...                             ...

差异 = 目标多一列 avatar_url
  → upgrade() 自动写入：op.add_column('users', sa.Column('avatar_url', sa.String(500)))
  → downgrade() 自动写入：op.drop_column('users', 'avatar_url')
```

首次执行时数据库与 models.py 完全一致 → 生成空迁移（只有 `pass`）→ 但版本号被写入 `alembic_version`，建立了 diff 的基准点。

### 为什么需要 `env.py` 里的配置

默认的 `env.py` 不知道你的项目结构和模型在哪。需要手动指定：

```python
# alembic/env.py
sys.path.insert(0, ...)              # 把 backend/ 加入导入路径
from models import db                # 导入模型元数据
from app import create_app
app = create_app()
app.app_context().push()             # 手动建立应用上下文
target_metadata = db.metadata        # 告诉 autogenerate "对比这个元数据"
```

---

## 四、版本追踪——`alembic_version` 表

`upgrade head` 执行后数据库里多了一张特殊表：

```
alembic_version
───────────────
version_num
───────────────
d982e2ee7cc7
```

就一行一列——存着当前数据库结构对应的版本号。之后每次 upgrade 更新这个值，downgrade 回退时也更新。revision 生成新版本时用它判断"上次从哪里开始的"。

### upgrade 输出含义

```
Running upgrade  -> d982e2ee7cc7, initial      ← 从无到有，第一个版本
Running upgrade d982e2ee7cc7 -> a1b2c3, add x  ← 从旧版推进到新版
```

`->` 左边是起点（空 = 从头开始），右边是终点版本号 + 描述。

---

## 五、secrets 模块——生成安全密钥

### 和 random 模块的区别

| | `random` | `secrets` |
|------|------|------|
| 随机源 | 伪随机——基于当前时间戳 | 真随机——操作系统硬件熵源（CPU 热噪声等） |
| 安全性 | 低——攻击者知道时间就能缩小候选范围 | 高——物理真随机，不可预测 |
| 用途 | 游戏、模拟、非安全场景 | 密钥生成、token 生成、密码学 |

**为什么 32 字节（256 位）**：和 JWT HS256 签名算法同一级别。`secrets.token_hex(32)` 生成 64 个十六进制字符作为密钥。

```bash
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))"
```

### 为什么安全——熵空间的物理含义

256 位 = 2^256 种可能。这个数字约 1.16 × 10^77——每秒试 10 亿次，试完需要的时间远超宇宙年龄。不是"很难攻破"——是数学上不可能。

---

## 六、.env.example——新人上手约定

### .env vs .env.example

| | `.env` | `.env.example` |
|------|------|------|
| 存储 | 真实密钥 | 只有键名，值为占位符 |
| 进 Git | ❌ `.gitignore` 排除 | ✅ 提交 |
| 用途 | 应用读这个文件获取密钥 | 新人 clone 后复制一份改成自己的值 |

README 里写的 `cp .env.example .env` 才成立的前提——必须有 `.env.example` 文件存在。没有它，新人不知道要填什么环境变量。

### 模板内容

```
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DATABASE_URL=sqlite:///aichat.db
```

---

## 七、和 Docker 部署的关系

迁移脚本文件（`versions/` 目录）和代码一起打包进 Docker 镜像。容器启动后手动执行：

```bash
docker compose exec flask alembic upgrade head
```

或者将来在 Dockerfile 的 CMD 之前自动执行（多副本需注意并发冲突）。开发阶段保持手动——先知道工具在做什么，再谈自动化。
