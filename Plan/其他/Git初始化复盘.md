# Git 初始化与首次提交 — 操作复盘

> 项目：AIChat v1.0
> 日期：2026-06-09
> 内容：从零初始化 Git 仓库 → 提交文件 → 推送到 GitHub 全流程

---

## 一、操作步骤回顾

### 1. 初始化仓库

```bash
cd /e/my_project/AIChat_v1.0
git init
```

`git init` 在项目根目录创建 `.git/` 隐藏文件夹，这里面存了 Git 的全部版本历史。

### 2. 切换到开发分支

```bash
git checkout -b dev
# 或等价的
git switch -c dev
```

两种写法效果完全一样：创建 `dev` 分支并切换过去。

- `main` — 留给生产环境代码
- `dev` — 日常开发在这条分支
- 以后每做一个功能：从 `dev` 拉 `feature/xxx` 分支，做完合并回 `dev`

### 3. 创建 `.gitignore`

文件名就叫 `.gitignore`，前面没有别的东西。点开头 = Unix/Linux 隐藏文件。

内容指定哪些文件/文件夹不进入版本控制：

```
__pycache__/   # Python 编译缓存
*.pyc          # 编译后的字节码
.env           # 环境变量（含敏感信息）
node_modules/  # 前端依赖（体积巨大，可重新安装）
dist/          # 构建产物
.idea/         # IDE 配置
.vscode/       # 编辑器配置
```

**原则**：只忽略"可重新生成的、环境相关的、含敏感信息的"东西。

#### .gitignore 配置语法详解

| 写法 | 效果 | 匹配示例 |
|------|------|---------|
| `*.pyc` | 所有 `.pyc` 文件，不管在哪个子目录 | `app.pyc`、`sub/utils.pyc` |
| `__pycache__/` | 所有叫 `__pycache__` 的文件夹 | 任何位置的这个文件夹 |
| `/config.json` | **只**忽略根目录的那个 | `config.json` 被忽略，`sub/config.json` 不受影响 |
| `!文件` | **例外规则**——之前被忽略的，重新包含 | `*.log` 全忽略，`!important.log` 保留它 |
| `#` | 注释行 | `# 这是注释` |

**路径写法说明**：

```gitignore
logs/debug.log         # 只忽略 logs 目录下的 debug.log
/important.log         # 开头的 / = 只匹配根目录，子目录同名文件不管
```

#### 重要陷阱

**`.gitignore` 只能拦截"还没被跟踪"的文件。** 如果一个文件已经 `git commit` 进仓库了，再加 `.gitignore` 是拦不住的——Git 会继续跟踪它。要让忽略生效，必须先：

```bash
git rm --cached 文件名    # 从 Git 跟踪中移除，但保留本地文件
```

#### `.git/info/exclude`（纯本地生效）

如果你只想在自己电脑上忽略某文件，不希望影响协作者（比如本地临时脚本、个人配置文件），写到项目根目录的 `.git/info/exclude` 里。写法和 `.gitignore` 完全一样，但这个文件不被 Git 跟踪，push 不会带上。

### 4. 暂存并提交

```bash
git add .
git commit -m "chore: 初始化项目结构和 .gitignore"
```

#### Git 的三个区域

```
工作目录（你的文件夹）
   ↓ git add       → 暂存区（购物车：决定这次提交哪些东西）
   ↓ git commit    → 本地仓库（拍快照：永久存入 Git 历史）
   ↓ git push      → 远程仓库（GitHub：云端备份）
```

- `git add .` — 当前目录所有变更放入暂存区
- `git commit -m "...message..."` — 把暂存区内容永久存档
- `git add 文件名` 比 `git add .` 更安全，大项目里不容易误加不想提交的文件

#### Commit Message 格式（Conventional Commits）

```
feat:     新功能        feat: 添加用户注册接口
fix:      修 bug       fix: 修复登录失败不提示错误
chore:    杂务         chore: 初始化项目结构
docs:     文档         docs: 更新 README
refactor: 重构         refactor: 提取公共 JWT 验证
test:     测试         test: 添加聊天接口单元测试
```

`chore` 的意思是"杂务/琐事"——建目录、改配置、装依赖用这个前缀。

### 5. 查看状态

```bash
git status
```

输出解读：
```
On branch dev            → 当前在 dev 分支
No commits yet           → 还没做过 commit（这次是首次提交）
Changes to be committed: → 以下文件在暂存区，等着被 commit
    new file: README.md  → 新建文件
```

### 6. 追加文件到上一次 commit

```bash
git add README.md
git commit --amend
```

`--amend` = 销毁上一次 commit，新建一个包含所有文件的新 commit。不是真的"修改"，而是"替换"——所以 commit hash 会变。

只有**没 push 之前**可以随便 `--amend`，push 之后再用需要 `git push --force`（有风险）。

### 7. 关联远程仓库（GitHub）

```bash
git remote add origin https://github.com/SeaExculbur/AIChat.git
```

- `origin` — 远程仓库的别名，约定俗成都叫这个名字
- 查看已关联的远程仓库：`git remote -v`

### 8. 推送到 GitHub

```bash
git push -u origin dev
```

- `push` — 把本地 commit 上传到云端的同名分支
- `-u` — 绑定本地 `dev` 和远程 `dev`，之后在这个分支上只需 `git push` 三个字母

---

## 二、遇到的问题 & 解决方案

### 问题 1：LF/CRLF 换行符警告

```
warning: LF will be replaced by CRLF the next time Git touches it
```

**原因**：Windows 换行符是 CRLF（`\r\n`），Unix/Linux 是 LF（`\n`）。Git 在 Windows 上默认配置了 `core.autocrlf true`，提交时自动统一成 LF 存进仓库，检出时转回 CRLF。

**处理**：这是正常行为，不影响代码，不需要处理。

### 问题 2：提交时提示"作者身份未知"

```
Author identity unknown
*** Please tell me who you are.
```

**原因**：Git 需要记录每个 commit 的作者。第一次使用 Git 必须先配置 name 和 email。

**解决**：
```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

| 配置层级 | 作用范围 | 配置文件 |
|---------|---------|---------|
| `--global` | 本机所有仓库 | `C:\Users\123\.gitconfig` |
| `--local` | 仅当前仓库 | 项目根目录 `.git/config` |

优先级：`local > global`。

### 问题 3：GitHub 因邮箱隐私拒绝推送

```
error: GH007: Your push would publish a private email address.
```

**原因**：GitHub 开启了 "Block command line pushes that expose my email"（阻止推送暴露真实邮箱的 commit）。本地的 commit 里记录的是真实邮箱 `3041970456@qq.com`，被 GitHub 检测到后拒绝。

**解决**：将 Git 配置的邮箱改为 GitHub 匿名邮箱，然后重写 commit：

```bash
git config --global user.email "174923904+SeaExculbur@users.noreply.github.com"
git commit --amend --reset-author
git push -u origin dev
```

`--reset-author` 的作用：用当前 `user.name` 和 `user.email` 配置刷新 commit 里的作者信息。普通 `--amend` 只追加文件，不改作者。

| 命令 | 效果 |
|------|------|
| `git commit --amend` | 追加文件，作者信息不变 |
| `git commit --amend --reset-author` | 追加文件 + 刷新作者信息 |

---

## 三、GitHub 邮箱隐私机制

GitHub 设置（https://github.com/settings/emails）里有三个相关选项：

| 设置 | 作用 |
|------|------|
| Keep my email addresses private | 网页上隐藏真实邮箱，对外显示匿名邮箱 |
| Block command line pushes that expose my email | 阻止任何包含你真实邮箱的 git push |
| 匿名邮箱（`ID+用户名@users.noreply.github.com`） | GitHub 自动分配的替代邮箱 |

**最佳实践**：
1. 本地 Git 配置用匿名邮箱
2. 两个开关都保持 On
3. 这样所有新 commit 都记录匿名邮箱，push 不会被拒绝，网页上也不会暴露真实邮箱

---

## 四、基础概念速查

### push / fetch / pull 区别

```
git push  = 本地 → 远程（上传）
git fetch = 远程 → 本地下载，但不碰当前文件（只查看）
git pull  = fetch + merge（下载并立即合并到当前分支）
```

- `push` = 备份到云端，多人协作时分享代码
- `pull` 有风险：本地有未提交的改动时直接 pull 容易混乱。原则是**先 commit（或 stash），再 pull**

### git switch vs git checkout

| | `git checkout` | `git switch` |
|------|------|------|
| 引入 | Git 1.0（2005） | Git 2.23（2019） |
| 功能 | 身兼数职（切分支 + 恢复文件 + 创建分支） | 只做分支切换/创建 |
| 风险 | 职责多，新手容易误操作 | 单一职责，不会出错 |

Git 官方后来把 `checkout` 拆成了 `switch`（管分支）和 `restore`（管文件恢复）。两个都能用，新教程推荐 `switch`。

### 合并冲突概念

当两个人改了同一个文件的同一行时，Git 不知道该留谁的，会停下来让你手动决定——这叫**合并冲突**。你一个人开发时基本不会遇到。

---

## 五、常用命令速查

```bash
git init                          # 初始化仓库
git status                        # 查看当前状态
git add .                         # 暂存所有变更
git add 文件名                     # 暂存指定文件
git commit -m "message"           # 提交
git commit --amend                # 追加到上一次提交
git log --oneline                 # 查看提交历史
git branch -vv                    # 查看本地分支与远程的绑定关系
git remote -v                     # 查看远程仓库配置
git remote add origin URL         # 添加远程仓库
git remote remove origin          # 删除错误的远程关联
git push -u origin 分支名         # 首次推送并绑定
git push                          # 绑定后的简写
git config --global user.name ""  # 设置全局用户名
git config --global user.email "" # 设置全局邮箱
git config user.name              # 查看当前仓库的用户名
```

---

## 六、Git 底层存储机制

### 四种对象

Git 不是存"文件差异"——是存**完整的快照**。每次 commit 产生四种对象：

| 对象 | 是什么 | 存储方式 |
|------|--------|---------|
| **blob** | 文件的实际内容 | SHA-1 哈希命名，存在 `.git/objects/` |
| **tree** | 目录结构（文件名 → blob hash 的映射） | 同上 |
| **commit** | 元数据（作者、时间、message）+ 指向 tree + 指向父 commit | 同上 |
| **tag** | 指向某个 commit 的别名（如 `v1.0`） | 同上 |

### 去重机制

两个文件内容相同 → blob hash 相同 → `.git/objects/` 里只存一份。100 次 commit 里文件没改过 → 每次 commit 的 tree 都指向同一个 blob hash，Git 不重复存储。

### commit hash 的不可篡改链

```
commit_hash = SHA-1(
    文件内容的 tree hash
    + 父 commit 的 hash      ← 父 hash 参与子 hash 计算
    + 作者 + 时间 + message
)
```

改中间任何一个 commit → 它的 hash 变了 → 所有后续 commit 的 hash 全变。从 HEAD 顺着父链往上追溯，重新计算每一步的 hash——如果末尾跟远程对不上，说明中间被篡改了。

---

## 七、Git 与二进制文件

### 为什么 `.db` 文件不能进 Git

1. **运行产物**，不是源码——`db.create_all()` 生成，clone 的人会在自己电脑上重新生成
2. **含用户数据**——测试账号、密码哈希不应出现在公开仓库
3. **Git 去重对二进制文件完全失效**

### 根本原因

文本文件改一行 → 大部分 blob 不变 → 哈希复用率高。`.db` 文件改了任意数据 → SQLite 内部 B-Tree 页面结构重新组织 → 几乎所有的字节都变了 → 没有任何旧 blob 可以复用 → 每次 commit 存一份接近完整大小（~100 KB）的新副本。50 次 commit → `.git/` 膨胀到 ~5.5 MB。

### 合并冲突的差异

Git 对文本文件可以逐行比对、自动合并。二进制文件只有"全扔给你选一个"——不能手动编辑合并。

---

## 八、Git 合并规则补充

| 两个人改同一文件的 | Git 的行为 |
|-----------------|-----------|
| 不同行（各自独立） | 自动拼接为一个新版本——**不是"新覆盖旧"，是各取改动拼在一起** |
| 同一行 | 标记冲突 `<<<<<<<` / `=======` / `>>>>>>>`，暂停合并，等你手动选 |
| 同一位置加了不同内容（相邻行） | 也标记冲突——不知道谁先谁后 |

Git 从不在两个合法改动间二选一——能合并的合并，合不上的标记出来让你决定。

---

## 九、push 底层流程与 fast-forward

### push 的处理流程

```
① 协商：本地跟远程比对 commit 链，确认对方缺哪些对象
② 打包：缺的 blob/tree/commit 打包成 packfile（delta 压缩）
③ 传输：发送 pack 到远程
④ 远程解压、验证 hash、更新 ref
```

已有 blob 不重传——每次 push 只传远程确认缺失的对象。

### fast-forward 规则

远端 HEAD = C。你要 push 到的 commit = D：

- D 的祖先链里包含 C → **快进（fast-forward）** → 允许
- D 的祖先链里不包含 C（如你 amend 销毁了 C，D 的 parent 是 B）→ **拒绝**

Git 问的是"你能在远程的基础上接着推石头，不需要侧移吗？"——而不是"你们是不是一个根开始的？"

### push 输出解读

```
Enumerating objects: 15, done.     → 扫描出 15 个需要处理的对象（blob + tree + commit，不是文件数）
Counting objects: 100% (15/15)     → 确认计数无误
Delta compression using up to 16 threads  → 用 16 线程做 delta 压缩（线程，不是进程）
Compressing objects: 100% (8/8)    → 8 个被压缩（太小的、已压缩的跳过）
Writing objects: 100% (8/8)        → 8 个通过网络发送中
Total 8 (delta 3), reused 0        → 共 8 个 pack 对象，3 个含 delta 差异，0 个从旧 pack 复用
remote: Resolving deltas: 100% (3/3)  → 远端把 delta 压缩的对象解压还原为完整对象
```

---

## 十、.gitignore 进阶规则

### 路径前缀规则

| 写法 | 匹配范围 |
|------|---------|
| `*.pyc` | 所有 `.pyc` 文件（不写路径前缀 = 全局生效，等效于 `**/*.pyc`） |
| `node_modules/` | 所有叫 `node_modules` 的文件夹 |
| `/config.json` | **只**限根目录 |
| `Plan/test/` | 忽略整个 `test/` 目录 |

### `*` vs `**` vs 尾斜杠

- `*`：匹配当前层级的文件**和文件夹名**——不跨越 `/`
- `**`：递归匹配任意层级
- `Plan/test/`：忽略整个目录——最省事的写法

**`Plan/test/*` 能忽略子文件夹吗？** 能——因为 `*` 匹配目录名，目录被忽略后里面所有内容跟着消失。

### `!` 例外规则

```gitignore
Plan/test/**           # 全部忽略
!Plan/test/.gitkeep    # 但这个文件例外，保留
```

顺序必须写在忽略规则之后才生效。

### 重要规则

- 规则行首**绝对不能有缩进**（空格或 tab）——否则 Git 不认
- 不以 `/` 开头的规则 = 全局生效——你不需要写 `**/` 前缀
- `.gitignore` 只拦"还没被跟踪"的文件——已 commit 的文件需要先 `git rm --cached`

---

## 十一、fork 与开源协作

### 为什么不能直接 push 别人的仓库

你没有写权限——GitHub 物理上拒绝。fork 就是让 GitHub 自动帮你创建一个你有写权限的副本。

### fork vs 手动建空白仓库

| | 手动建空白仓库 | fork |
|------|------|------|
| 归因 | 不显示来源——看起来像原创 | 仓库页顶部显示 "forked from XXX" |
| 开 PR | 维护者要手动加 remote 才能对比 | GitHub fork 网络自动关联 |
| 同步上游更新 | 手动加 upstream、手动 pull | fork 天生支持 `git fetch upstream` |

### 开源 PR 完整流程

```
fork → git clone → git checkout -b xxx → 改代码 
  → git commit → git push → GitHub 上开 PR
  → 维护者 review → 改 → push（PR 自动更新）
  → 维护者 merge → 你的代码进了主仓库
```

---

## 十二、PR（Pull Request）流程

### PR 是什么

你不是主仓库的直接写权限持有者——你想把自己的改动合入主仓库，需要向维护者发一个**合并请求（Pull Request）**。维护者审查你的代码后决定是否合并。

### 为什么需要 PR

没有 PR 时，任何贡献者可以直接 push 到主分支——没有代码审查，没有质量门禁，一个人误操作直接破坏整个项目。PR 提供了：必须有人看过你的代码才能合入，且审查意见公开透明。

### PR 的标准操作流程

```
① fork 主仓库 → 你自己的 GitHub 账号下有了副本（你有写权限）
② git clone 你的 fork → 本地开发
③ git checkout -b feature/xxx → 从 dev 拉功能分支
④ 写代码 → git add → git commit → git push
⑤ GitHub 上点 "New Pull Request" → 描述你改了什么
⑥ 维护者 review → 提出修改意见
⑦ 本地改 → commit → push（PR 自动更新，不需要重开）
⑧ 维护者点 "Merge" → 你的代码进入主仓库
```

### PR 模板（`.github/PULL_REQUEST_TEMPLATE.md`）

在仓库根目录的 `.github/` 文件夹下创建这个文件，以后任何人（包括你自己）打开发 PR 页面时，描述框会自动填充模板：

```markdown
## 做了什么

## 怎么测试

- [ ] 本地跑通
- [ ] 接口测试通过
```

### 个人迭代也用 PR 的原因

即使只有你一个人开发，从 `feature/xxx` 合并到 `dev` 时走 PR 流程可以：看到自己改了哪些文件、确认 diff 没有调试代码或硬编码密码、PR 模板强迫自己写清楚这次改了什么。以后有协作者加入时，这套流程已经就位。

---

## 十三、这次提交了哪些文件

```
.gitignore
CLAUDE.md
Plan/Plan.html
Plan/开发上线流程.md
README.md
```

五份文件，一次 commit。commit hash：`683c967`。
