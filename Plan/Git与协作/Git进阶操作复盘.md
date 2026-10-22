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

## 七、git mv——移动/重命名 + 暂存

```bash
git mv 旧路径 新路径
```

大致等价于：

```bash
mv 旧路径 新路径
git add -A
```

区别是 `git status` 会显示成 `R`（renamed），而不是"删除一个 + 新增一个"。

### Git 其实不记录"重命名"

Git 的对象模型里没有 rename 这个动作。提交里保存的是"旧路径不存在了、新路径出现了"，展示 diff 时通过**内容相似度**推断这是一次重命名。

- `git log --follow 文件`：跨重命名追踪单个文件的历史
- `git diff -M`：开启重命名检测

### `R` 与 `RM`

| 标记 | 含义 |
|---|---|
| `R` | 已暂存的重命名，内容没变 |
| `RM` | 已暂存的重命名 + 工作区又改了内容 |

`RM` 的文件，`git commit` 只提交暂存区里的版本（重命名 + 旧内容），工作区的新内容要再 `git add` 才会进下一次提交。

### 为什么用 `git mv`

- 历史、blame、review 都更连续
- 大量整理目录时，diff 更清晰

**限制**：只能移动已经被 Git 跟踪的文件。被 `.gitignore` 忽略的文件只能用普通 `mv`。

---

## 八、merge commit vs 普通 commit

### 父提交数量不同

```
普通 commit：  父提交 A ← 新 commit
merge commit： 父提交 A ─┐
                          ├→ merge commit
               父提交 B ─┘
```

- 普通 commit 只有一个父提交，diff 就是"这次改了什么"
- merge commit 有两个（或更多）父提交，意义是"把两条历史线接在一起"

### 记录的内容不同

| | 普通 commit | merge commit |
|---|---|---|
| 记录对象 | 一次具体的代码/文档改动 | 一次分支整合事件 |
| 典型 message | `fix: 数据库密码改为环境变量注入` | `Merge branch 'dev' into main` |
| diff | `git show <commit>` 直接看到 | 干净合并时 `git show` 可能什么都不显示 |
| 粒度 | 细，一次一件事 | 粗，一次合并一批提交 |

### 为什么干净合并看不到 diff

merge commit 的文件树 = 被合并分支最新提交的文件树，它自己**没有新增代码改动**。真正的改动在被合并的那些普通 commit 里。

如果合并时手动解决了冲突，merge commit 可能包含额外的冲突解决改动，这时 message 要写清"冲突是怎么解的"。

### 合并消息的三种写法

```bash
git merge --no-ff dev -m "merge: 发布 dev 到 main"   # 自定义
git merge --no-ff dev --no-edit                     # 用默认 "Merge branch 'dev' into main"
git merge --no-ff dev                               # 打开编辑器
```

**普通 commit 的 message 不会被自动复制成 merge message**；merge commit 是另一条提交，记录的是合并动作。

---

## 九、分支合并实操

### 先看差异

```bash
git fetch origin
git log --oneline --left-right --graph dev...feature/manual-approval
```

- `<` 开头：只在 `dev` 上的提交
- `>` 开头：只在 feature 上的提交
- 只有 `>`：feature 领先，`dev` 没有独有提交，合并不会冲突

### 合并 feature 到 dev

```bash
git checkout dev
git pull --ff-only origin dev
git merge --no-ff feature/manual-approval -m "merge: 合并功能到 dev"
git push origin dev
```

- `--no-ff`：即使能快进，也强制生成 merge commit，保留"这是一次功能分支合并"的记录
- `--ff-only`：只允许快进，不能快进就报错；用于"同步远端，不要产生合并提交"

### 创建 main 分支

如果远端还没有 main：

```bash
git checkout dev
git checkout -b main
git push -u origin main
```

验证：

```bash
git branch -vv
git ls-remote --heads origin
```

### 验证内容一致

`main` 和 feature 的 commit hash 不同，但文件树可能相同：

```bash
git diff --stat main feature/manual-approval   # 空输出 = 内容一致
git show --no-patch --format="%H%n%P" main     # 第二行应有两个父提交 hash
```

### 冲突处理

```bash
git status
# 编辑冲突文件，删掉 <<<<<<< ======= >>>>>>> 标记
git add <冲突文件>
git merge --continue
```

---

## 十、tag 与 GitHub Release

### tag 是给 commit 起的固定名字

| 类型 | 命令 | 特点 |
|---|---|---|
| 轻量 tag | `git tag v0.1.0` | 只是一个指针 |
| annotated tag | `git tag -a v0.1.0 -m "..."` | 独立对象，记录打标签的人、时间、说明，发布版本推荐 |

推送 tag：

```bash
git tag -a v0.1.0 -m "AIChat v0.1.0 — 首个可上线版本"
git push origin v0.1.0
```

### Release 是 tag + 发布说明

GitHub 的 Release 不会触发部署，它只是：

- 给某个 commit 打 tag
- 附上发布说明、源码包
- 在仓库页面形成一个可回溯的版本节点

Release notes 建议写：

- 功能列表
- 技术栈
- **已知限制**（比只写"已完成"更有价值）
- 部署方式

```bash
gh release create v0.1.0 --title "AIChat v0.1.0" --notes-file RELEASE_NOTES.md
```

### 版本号怎么选

- `0.x`：功能可用，但还有明显缺口、无自动化测试——符合 MVP 阶段
- `1.0`：对外承诺稳定接口和较完整的质量保障

项目版本号和"稳定度"是两件事，Release notes 里写清楚即可。

---

## 十一、本次操作总结

```
任务                          命令
修正 GitHub 语言统计          .gitattributes + *.html linguist-detectable=false
重写 commit message          git rebase -i --root → pick 改 reword
强制覆盖远程                  git push --force
取消跟踪但保留本地文件         git rm --cached
抹掉全部历史                  git checkout --orphan + 删旧分支
追加内容到文件                echo "..." >> 文件名
移动/重命名并暂存             git mv 旧 新
查看分支差异                  git log --left-right --graph dev...feature
保留合并节点                  git merge --no-ff
接受默认合并消息              git merge --no-edit
快进合并                      git merge --ff-only
创建并推送新分支              git checkout -b main → git push -u origin main
打发布标签                    git tag -a v0.1.0 -m "..."
```
