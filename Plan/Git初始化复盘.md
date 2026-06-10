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

## 六、这次提交了哪些文件

```
.gitignore
CLAUDE.md
Plan/Plan.html
Plan/开发上线流程.md
README.md
```

五份文件，一次 commit。commit hash：`683c967`。
