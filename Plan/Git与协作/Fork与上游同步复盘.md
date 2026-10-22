# Fork 与上游同步 — 操作复盘

> 日期：2026-07-06
> 内容：fork 后的远程管理、fetch/merge 流程、标签机制、图形化 diff

---

## 一、origin 和 upstream 的区别

### origin

`git clone` 你自己的 fork 时，Git 自动给你 GitHub 上的仓库起名叫 `origin`。它就是一个 URL 的缩写。

```bash
git remote -v    # 查看所有远程源
# origin  https://github.com/SeaExculbur/oss-issue-scout.git (fetch)
# origin  https://github.com/SeaExculbur/oss-issue-scout.git (push)
```

origin 是你的——有完整读写权限。

### upstream

upstream 是原始仓库（你 fork 的来源）。不是 Git 自动配的——需要手动添加：

```bash
git remote add upstream https://github.com/原作者/原仓库.git
```

你对 upstream 只有读权限，不能 push（写了也会被 GitHub 拒绝）。

---

## 二、git fetch — 只拉取，不合并

```bash
git fetch upstream
```

fetch 做的事：去远程仓库看有没有新 commit，有就下载到本地，但**不碰你当前的工作目录和分支**。

fetch 之后的状态：

```
你的 main 分支         → 停在原地，不受影响
upstream/main（快照）  → 指向远程最新的 commit
origin/main（快照）    → 停在原地，不受影响
```

### fetch 输出解读

```
 * [new branch]      main       -> upstream/main
 * [new tag]         v0.2.0     -> v0.2.0
```

- `main -> upstream/main`：远程的 main 分支下载到本地，存为 `upstream/main`（加前缀防止和 origin/main 冲突）
- `v0.2.0 -> v0.2.0`：标签两边同名——标签是死的，不会有冲突，不需要前缀

### 查看 fetch 拉下来的内容

```bash
git log main..upstream/main --oneline    # 看新增了哪些 commit
git diff main upstream/main              # 看具体代码改了哪里
git show upstream/main:文件名             # 看快照里某个文件的完整内容
```

---

## 三、git merge — 把快照合进工作分支

```bash
git checkout main
git merge upstream/main
git push origin main
```

merge 不是"覆盖"——是把两条线（你的改动 + 上游的改动）拼在一起。如果有冲突（改了同一个地方），Git 标出来让你选。

---

## 四、origin/main 和 upstream/main 的本质

这两个不是文件夹、不是副本——是存在 `.git/refs/remotes/` 下的文件，内容只有一行：一个 commit hash。

```
.git/refs/remotes/origin/main     → 内容：你 GitHub fork 上 main 指向的 commit hash
.git/refs/remotes/upstream/main   → 内容：原作者 main 指向的 commit hash
```

它们的作用是让 Git 知道"远程现在指向哪个 commit"——这样 `git status` 才能告诉你 "ahead of origin/main by 1 commit"（该 push 了）。

### 为什么是指针而不是计数器

计数器方案：快照里记一个数字——"本地领先远程 N 个 commit"。

问题：`git commit --amend`、`git reset`、`git rebase` 都会改写历史。你 commit 了 3 次，amend 了最后一次，计数器应该显示 2 还是 3？你 reset 回退了两次 commit——计数器现在是多少？任何对历史的修改都会让计数器失效，因为它算的是"执行过几次 commit 命令"，不是"两者之间精确差了什么"。

哈希指针方案：只存一个问题——**远程上一次停在哪个 commit？**

```
origin/main → a1b2c3d
main        → f4e5d6c
```

不管中间 amend、reset、rebase 了多少次，两个 hash 一对比，Git 顺着祖先链精确算出差异。指针不会说谎。

**更根本的原因**——Git 里所有的"快照"底层都是同一种东西：ref（引用）。本地分支 `main` 是一个 ref（指向一个 hash），远程快照 `origin/main` 是一个 ref，标签 `v1.0` 也是 ref。三者共享同一个数据结构，区别只在行为规则上：

| | 允许 commit | 谁更新它 | 命名空间 |
|------|------|------|------|
| 本地分支 `main` | ✅ | 你 | 无前缀 |
| 远程快照 `origin/main` | ❌ 只读 | fetch/push | `remotes/origin/` |
| 标签 `v0.2.0` | ❌ 只读 | fetch | `tags/` |

Git 不会为远程快照单独发明一套"计数器机制"——三种 ref 用同一套哈希指针就够了。

---

## 五、标签（tag）与分支的不对称

| | 分支 | 标签 |
|------|------|------|
| 是否可变 | 活——每次 commit 往前移动 | 死——永远指向同一个 commit |
| 是否有命名空间 | 有——origin/main、upstream/main | 没有——全局唯一 |
| fetch 行为 | 加前缀存到快照，不碰本地分支 | 直接创建，不区分来源 |
| 同名冲突 | 不会冲突（前缀隔离） | fetch 报错拒绝 |

标签可以随时贴到任何一个已存在的 commit 上：

```bash
git tag v1.0.0                # 当前 commit
git tag v1.0.0 a1b2c3d        # 过去的某个 commit
```

---

## 六、图形化 diff 工具配置

在终端看 diff 比较费劲，可以配 VS Code 作为图形化 diff 工具。

### 配置

```bash
git config --global diff.tool vscode
git config --global difftool.vscode.cmd 'code --wait --diff "$LOCAL" "$REMOTE"'
```

### 使用

```bash
git difftool main upstream/main    # 左右分屏对比两个分支
```

### 参数解释

- `--wait`：让 Git 等你关掉 VS Code 窗口后才继续。不加 Git 会直接跳过或多个窗口打架
- `--diff`：VS Code 启动即进入 diff 对比模式
- `$LOCAL` `$REMOTE`：Git 替换成实际文件路径

### 取消配置

```bash
git config --global --unset diff.tool
git config --global --unset difftool.vscode.cmd
```

---

## 七、git fetch vs git pull

| | fetch | pull |
|------|------|------|
| 下载远程数据 | ✅ | ✅ |
| 自动合并 | ❌ 不碰你的代码 | ✅ fetch + merge 一步到位 |

用 fetch + 手动 merge 的好处：先看别人改了啥，再决定合并。直接 pull 可能把冲突炸进当前工作区。

---

## 八、选择性合并（本次未使用，备忘）

| 粒度 | 命令 |
|------|------|
| 只要某个 commit | `git cherry-pick <hash>` |
| 合并不自动提交 | `git merge --no-commit upstream/main` |
| 逐块确认（同一文件内） | `git merge --no-commit upstream/main` + `git add -p 文件名` |
