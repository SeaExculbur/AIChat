# Git 回退版本复盘

> 项目：AIChat v1.0  
> 日期：2026-08-13  
> 场景：撤销一次"引入了不该引入的迁移系统"的 commit，回到上一个版本

---

## 一、场景

做了一次 commit（b6cff1c：用 Flask-Migrate 重建迁移系统），后来发现方向错了——项目里本来就有裸 alembic，不该引入第二套迁移体系。需要回退到上一个 commit（efbc807），但不丢工作区未提交的改动。

---

## 二、三种 reset 模式

| 模式 | 命令 | HEAD 指针 | 暂存区 | 工作区文件 |
|------|------|----------|--------|-----------|
| **--soft** | `git reset --soft HEAD~1` | ✅ 回退 | ❌ 保留（改动还在暂存区） | ❌ 保留 |
| **--mixed**（默认） | `git reset HEAD~1` | ✅ 回退 | ✅ 清空（改动回到未暂存） | ❌ 保留 |
| **--hard** | `git reset --hard HEAD~1` | ✅ 回退 | ✅ 清空 | ✅ **丢弃** |

### 怎么选

| 需求 | 用哪个 |
|------|--------|
| 撤销 commit，但改动全保留，重新整理提交 | `--mixed` |
| 撤销 commit，改动保留在暂存区，马上重新提交 | `--soft` |
| 撤销 commit，改动也全部丢弃（回到干净状态） | `--hard` |

**危险提示**：`--hard` 会删除工作区未提交的改动——不可恢复。使用前必须确认工作区没有想保留的文件。

举例：我改了前端和后端，后端commit了，但是我希望回到后端的上一个commit的状态，我就用mixed，因为mixed保留工作区的改动，也就是保留了前端的改动，后端被回退到了上一个commit。只有用了hard，工作区所有的改动全部丢失，包括前后端。soft相当于自动执行了git add。

---

## 三、本次实际操作

### ① 确认回退目标

```bash
git log --oneline -3
# b6cff1c chore: 用 Flask-Migrate 重建数据库迁移系统   ← 要撤销的
# efbc807 feat: 实现多会话管理系统                     ← 回退目标
# 6c518a2 feat: Docker Compose 添加 PostgreSQL 服务
```

### ② 检查本地是否领先远程

```bash
git status --short --branch
# ## dev...origin/dev [ahead 1]    ← 本地领先远程 1 个 commit
git log --oneline origin/dev..HEAD
# b6cff1c ...                        ← 未 push 的只有这一个
```

**关键**：未 push → 回退后本地和远程自然对齐 → 不需要 `--force`。

### ③ 执行回退（选 --mixed 保工作区）

```bash
git reset --mixed HEAD~1
# Unstaged changes after reset:      ← 改动全部回到工作区，没丢
#   M backend/app.py
#   M backend/models.py
#   D backend/alembic/...
```

### ④ 还原文件内容

`--mixed` 只动 commit 指针和暂存区——**磁盘上的文件内容还是改过的版本**。要回到 commit 里的版本，需要 `git restore`：

```bash
git restore backend/app.py backend/models.py backend/requirements.txt README.md
git restore backend/alembic.ini backend/alembic/
```

### ⑤ 清理未跟踪文件

`git reset` 不碰未跟踪文件（untracked）——本次新增的 `backend/migrations/` 目录要手动删：

```bash
rm -rf backend/migrations/
```

---

## 四、关键概念

### HEAD~1 是什么

`HEAD` = 当前 commit。`HEAD~1` = 前一个 commit（父 commit）。`HEAD~2` = 前两个。

### reset 只动指针，不动磁盘

| reset 做了什么 | 没做什么 |
|--------------|---------|
| HEAD 指针移到目标 commit | 不删除磁盘文件 |
| 暂存区按模式重置 | 工作区文件内容不变（--hard 除外） |

所以"回退 commit"之后，文件内容还原要靠 `git restore`（从 commit 恢复）——两步配合才是完整回退。

### 回退后要不要 push --force

```
本地已 push → 回退后本地落后于远程 → 需要 push --force 覆盖
本地未 push → 回退后本地和远程对齐 → 直接 push 或不用 push
```

**判断**：`git status --short --branch` 显示 `ahead N` 就是本地领先；回退后重新看，若不再领先则不需要 force。

---

## 五、git restore 速查

| 命令 | 干什么 |
|------|--------|
| `git restore 文件名` | 把工作区文件还原成 HEAD 版本（丢弃未提交改动） |
| `git restore --staged 文件名` | 把暂存区还原，文件回到未暂存状态（保留改动） |
| `git restore --source=HEAD~1 文件名` | 还原成指定 commit 的版本 |

---

## 六、本次决策复盘

| 决策 | 是否正确 |
|------|---------|
| 用 `--mixed` 而非 `--hard` | ✅——工作区有 Chat.vue、部署文档等无关改动，`--hard` 会全删 |
| 回退前先查 `ahead 1` | ✅——确认未 push，省掉 force 的麻烦 |
| 回退后 `git restore` 还原文件 | ✅——`--mixed` 不改磁盘内容，不 restore 的话文件还是改过的 |
| 手动删 `migrations/` | ✅——reset 不碰 untracked 文件 |

---

## 七、一句话

**回退 commit = 移指针（reset）+ 还原文件（restore）+ 清理未跟踪（rm）三步**。`--mixed` 保工作区、`--hard` 丢工作区，选错一步代价不同——用前先 `git status` 确认工作区有什么。
