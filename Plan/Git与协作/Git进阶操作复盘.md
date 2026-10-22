# Git 进阶操作复盘

> 日期：2026-07-05
> 内容：重写历史、孤儿分支、.gitattributes、缓存区操作

---

## 一、.gitattributes — 修正 GitHub 语言统计

### 问题

AIChat 仓库实际代码是 Python + Vue，但 GitHub 显示主语言为 HTML。因为 GitHub 的 linguist 按字节数统计，HTML 文件字节数最高时就标成 HTML 项目。

### 解决

在仓库根目录创建 `.gitattributes`（注意：是文件不是文件夹）：

```
*.html linguist-detectable=false
```

这告诉 GitHub 的语言统计工具：不要统计 HTML 文件。仓库主语言会变成占比第二高的语言（Vue 或 Python）。

### 原理

GitHub 使用开源库 [linguist](https://github.com/github-linguist/linguist) 做语言检测。`.gitattributes` 里可以覆盖 linguist 的默认行为。常用规则：

| 规则 | 效果 |
|------|------|
| `*.html linguist-detectable=false` | 不统计 HTML |
| `docs/* linguist-documentation` | 把 docs 目录标记为文档，不计入语言统计 |
| `*.js linguist-language=Vue` | 强制把 .js 文件归类为 Vue |

`linguist-detectable=false` 和加入 `.gitignore` 是不同的概念——前者只影响 GitHub 的语言统计显示，不影响版本控制。文件依然被 Git 正常跟踪。

---

## 二、git rebase -i --root — 重写全部提交历史

### 用途

修改仓库从第一个 commit 开始的所有 commit message。

### 操作

```bash
git rebase -i --root
```

逐词拆解：

- `rebase`：重写提交历史
- `-i`（interactive）：打开编辑器让你逐条选择每个 commit 怎么处理
- `--root`：从仓库的第一个 commit 开始（不用 `--root` 则只 rebase 当前分支的新增 commit）

编辑器打开后，每行一个 commit：

```
pick 0413bd1 Initial commit
pick 24b47b7 Fix README images
```

### pick vs reword vs squash

| 命令 | 效果 |
|------|------|
| `pick` | 保留这个 commit，原样不动 |
| `reword` | 保留 commit，但打开编辑器让你改 message |
| `squash` | 把这个 commit 合并到上一个 commit |
| `drop` | 删除这个 commit |

### 本次操作

把两行的 `pick` 都改成 `reword`，保存退出。Git 会依次弹出两次编辑器，每次让你修改对应 commit 的 message。删掉末尾的 `Co-Authored-By:` 行，保存退出。历史重写完成。

### 重要

rebase 重写历史后，所有 commit hash 都会变。已经 push 过的分支必须用 `git push --force` 才能推送。**不要在主分支上和协作者共用时做 rebase**——你们的历史分叉后无法正常合并。

---

## 三、git push --force — 强制覆盖远程历史

### 用途

本地历史被 rebase/amend 重写后，和远程历史产生分叉，普通 push 会被拒绝。`--force` 强制用本地历史覆盖远程。

### 什么时候能用

- 个人仓库、没有协作者、没有 fork
- 你确定远程的旧 commit 没有别人基于它做开发

### 什么时候绝不能用

- 主分支上有协作者
- 仓库被 fork 过
- 已经有人基于你的旧 commit 开了 PR

**一句话：只有你一个人的仓库才能 safe force push。**

---

## 四、git checkout --orphan — 抹掉全部历史

### 用途

把一个仓库的所有 commit 历史压成一条干净的 `Initial commit`。适用于旧仓库 commit 历史混乱、想重新开始的场景。

### 操作

```bash
git checkout --orphan new-main    # 创建无历史的新分支
git add -A                         # 暂存所有文件
git commit -m "Initial commit"     # 第一个也是唯一的 commit
git branch -D main                 # 删掉旧分支
git branch -m new-main main        # 新分支改名为 main
git push --force origin main       # 覆盖远程
```

### --orphan 是什么

`--orphan`（孤儿分支）创建一条**没有任何父 commit** 的新分支。在这个分支上，`git log` 是空的，所有文件都在 "Changes to be committed" 状态。它和你 `git init` 一个全新仓库的效果一样，区别是工作目录里的文件不受影响。

### 坑：孤儿分支上不能用 git reset HEAD

孤儿分支没有任何 commit，所以 `HEAD` 引用不存在。

```bash
git reset HEAD 文件名    # 报错：ambiguous argument 'HEAD'
```

正确做法是用 `git rm --cached`：

```bash
git rm --cached 文件名    # 从暂存区移除，保留本地文件
```

---

## 五、git rm --cached vs 系统 rm vs .gitignore

三个操作的区别经常混淆：

| 操作 | 本地文件 | Git 跟踪 |
|------|---------|---------|
| 系统 `rm 文件名` | 删除 | 下次 commit 才停止跟踪 |
| `git rm 文件名` | 删除 | 立即停止跟踪 |
| `git rm --cached 文件名` | **保留** | 立即停止跟踪 |

`--cached` 的含义：只操作 Git 的索引（缓存区），不动工作目录里的真实文件。这是"我不想再跟踪这个文件了，但我本地还要留着它"的标准做法。

### 典型使用场景

1. 不小心把 `.env` commit 了 → `git rm --cached .env` + 把 `.env` 加入 `.gitignore` + commit
2. 要把 `CLAUDE.md` 从仓库中去掉但本地还需要 → `git rm --cached CLAUDE.md` + 加入 `.gitignore`

---

## 六、echo >> 文件 — 追加文本

```bash
echo ".claude/" >> .gitignore    # 追加一行到文件末尾
```

- `>` 单箭头：覆盖写入（原有内容被清空）
- `>>` 双箭头：追加写入（原有内容保留）

等价于用记事本打开 `.gitignore`，在最后一行敲 `.claude/`，保存。

---

## 七、本次操作总结

```
任务                          命令
修正 GitHub 语言统计          .gitattributes + *.html linguist-detectable=false
重写 commit message          git rebase -i --root → pick 改 reword
强制覆盖远程                  git push --force
取消跟踪但保留本地文件         git rm --cached
抹掉全部历史                  git checkout --orphan + 删旧分支
追加内容到文件                echo "..." >> 文件名
```
