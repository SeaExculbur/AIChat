# Alembic 迁移踩坑记录

> 项目：AIChat v1.0  
> 日期：2026-08-13  
> 状态：裸 alembic 迁移系统搭建完成，本地三张表建表成功

---

## 一、今天问题的起因

给数据库加了 `Conversation` 表 + `ChatHistory.conversation_id` 列后，接口报错：

```
sqlite3.OperationalError: no such column: chat_history.conversation_id
```

**根因**：`db.create_all()` 只检查"表是否存在"，不检查"列是否齐全"——`chat_history` 旧表存在，新列永远不会被加进去。

---

## 二、空壳脚本：一切的根源

部署阶段的迁移脚本是**空壳**：

```python
def upgrade() -> None:
    pass    # 什么都没做
```

### 空壳脚本的骗局

| 阶段 | Alembic 的行为 | 结果 |
|------|--------------|------|
| autogenerate（生成脚本） | 通过脚本历史推算数据库状态：pass = 啥都没建 = 空库 | 对比模型（3 表）vs 空库 → 生成建表脚本 ✅（它以为没问题） |
| upgrade（执行脚本） | 执行 `CREATE TABLE users` → **实际库里已有 users** | `table users already exists` → 崩 💥 |

**核心原理**：Alembic 的"对比"信任**脚本历史**胜于信任**数据库实况**。空壳脚本让它在生成阶段误判库是空的，执行阶段撞上真实存在的表才暴露。

### 为什么 Alembic 不直接查库对比

1. `IF NOT EXISTS` 只防"表重复"，防不了"表存在但结构不完整"——后者正是迁移要解决的
2. Alembic 的原则：**版本历史是唯一权威**，数据库状态只是辅助。历史不可信 → 拒绝工作，不猜
3. autogenerate 对比发生在"生成时"，upgrade 执行的是"已定稿的 SQL"——没有运行时再检查

### 类比 Git

`git log` 显示 commit 存在但 `.git/objects` 找不到 → Git 报 `fatal: bad object` 而不是自己扫描重建。工具宁可停下来喊救命，也不基于猜测继续。

---

## 三、完整踩坑链

| # | 现象 | 根因 | 解决 |
|---|------|------|------|
| 1 | `no such column: conversation_id` | `db.create_all()` 不更新旧表结构 | 引入迁移系统 |
| 2 | `Can't locate revision 'd982e2ee7cc7'` | 之前失败的 `stamp head` 在版本表写入不存在的版本号 | 清版本表记录 |
| 3 | `NoReferencedTableError: could not find table 'conversations'` | 表名单复数不一致（conversation vs conversations） | 统一表名 |
| 4 | `No changes in schema detected` | `app.py` 里 `db.create_all()` 和 Alembic 冲突——加载 Flask 时自动建表 | 删掉 `db.create_all()` |
| 5 | `no such index: ix_conversation_user_id` | 迁移脚本在"旧表存在"状态生成，删库后脚本失去上下文 | 删脚本、删库、重新生成 |
| 6 | `table users already exists` | 空壳脚本骗 autogenerate 以为库是空的 | 删空壳脚本、删库、重新生成 |

---

## 三.5、方法论教训

**每次动数据库之前，先思考当前架构能做出的最优解，而不是直接引入新的工具/系统。**

当时项目里已经有裸 alembic（部署阶段搭的），我却直接引了 Flask-Migrate（另一套迁移体系）——两套结构并存，产生了版本表冲突、坏记录、双目录等一系列连锁问题。

**正确做法**：动手前先盘点现状——

| 盘点项 | 当时应该问 |
|--------|-----------|
| 项目里已有什么迁移工具？ | 裸 alembic 已存在（alembic/ + alembic.ini） |
| 它处于什么状态？ | 空壳脚本、版本记录可能有问题 |
| 是修它，还是换新的？ | 修——同一套体系内解决问题，而不是引新体系制造并存 |
| 换新体系的代价？ | 两套并存冲突、清理成本、历史断裂 |

**原则**：在已有体系内修问题，除非现有体系有无法修复的根本缺陷。引入新工具前先确认"旧的为什么不行"——而不是默认"新的更好"。

---

## 三.6、环境变量隔离（企业级硬要求）

生产端和开发端的环境变量**必须隔离**，尤其是数据库连接和密钥。企业项目分 3-5 套环境（dev/test/staging/prod），每套独立管理。

### 三个强制隔离点

| 隔离点 | 为什么 |
|--------|--------|
| **数据库连接** | dev 是 SQLite（本地文件），prod 是 PostgreSQL（服务器）——连接串永远不同 |
| **签名密钥**（SECRET_KEY/JWT_SECRET_KEY） | 共用 = 开发密钥泄露 → 生产 token 可伪造。企业里密钥严格独立 |
| **误操作边界** | 共用配置时，开发环境跑 `alembic upgrade` 可能误连生产库——改坏生产表 |

### 你的项目当前状态

| 变量 | 现状 | 应该 |
|------|------|------|
| `DATABASE_URL` | ✅ 已隔离（SQLite vs PostgreSQL） | — |
| `SECRET_KEY` | ❌ 两套相同 | 生产生成独立随机值 |
| `JWT_SECRET_KEY` | ❌ 两套相同 | 生产生成独立随机值 |
| `DEEPSEEK_API_KEY` | 同一把 key | 个人项目可接受，企业会分账号 |

### 操作验证

迁移等操作前确认连的是哪个库：

```bash
# 本地
DATABASE_URL 未设置 → env.py 走 ini 的 sqlite ✅
# 生产容器
DATABASE_URL 由 docker-compose 注入 → postgresql://... ✅
```

---

## 四、最终正确流程（本地）

```bash
# ① 清理旧状态
rm alembic/versions/d982e2ee7cc7_initial.py    # 删空壳脚本
rm instance/aichat.db                           # 删旧库

# ② 从零生成
alembic revision --autogenerate -m "create all tables"
# → 生成 fc773b58aff4（纯 CREATE TABLE，因为库是空的）

# ③ 应用
alembic upgrade head
# → 建出 users / conversations / chat_history / alembic_version
```

**为什么删库**：autogenerate 生成的是"模型和库的差异"。空库让差异 = 完整定义——脚本干净，历史干净。

---

## 五、正常迁移流程（以后）

```bash
# 改 models.py 后
alembic revision --autogenerate -m "描述改动"
alembic upgrade head
# 可选回滚
alembic downgrade -1
```

---

## 六、关键概念总结

### 版本表（alembic_version）
Alembic 的记忆——记录"数据库当前处于哪个版本"。每次 upgrade 前查它，只执行未应用的脚本。

### autogenerate 对比的基准
- **生成时**：对比"模型"和"脚本历史推算出的状态"（不是直接查库！）
- 脚本历史不完整/矛盾 → 拒绝执行

### 迁移不是"搬数据"
迁移是在**同一个已存在的库**上增量改结构（`ALTER TABLE`），数据原封不动。这也是生产环境必须用迁移系统的原因——改表结构不能丢用户数据。

---

## 七、遗留问题与注意事项

1. **生产端迁移**：生产 PostgreSQL 的版本表也是坏的空壳记录——部署时需要用同样的流程清理（`alembic stamp` 或删库重建，取决于生产数据是否重要）
2. **`alembic.ini` 的 URL 写死**：已改 env.py 支持 `DATABASE_URL` 环境变量优先——生产容器设置环境变量即可，不用改 ini
3. **`db.create_all()` 已删除**：第一次启动 Flask 前必须先 `alembic upgrade head`
