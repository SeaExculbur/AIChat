# Docker 构建链路与镜像传输

> 本文回答：源码怎么变成服务器上的容器、镜像从哪来、为什么这样传、每一步的利弊。
> Docker 镜像分层、Compose 基础概念见已有的《Docker容器化部署.md》，这里只写这次部署新增的部分。

---

## 一、先分清两种镜像

| 类型 | 例子 | 谁做的 | 作用 |
|---|---|---|---|
| **基础镜像** | `python:3.13-slim`、`node:22-alpine`、`postgres:18-alpine`、`nginx:alpine` | 官方/发行方 | 提供操作系统用户空间 + 运行时 |
| **应用镜像** | `aichat-flask`、`aichat-nginx` | 你，用 Dockerfile 构建 | 基础镜像 + 你的代码 + 依赖 |

服务器上最终运行的是**应用镜像**；基础镜像是"底"。拉不到基础镜像，应用镜像就构建不出来。

---

## 二、把应用镜像送上服务器的三条路

```text
路线 A：源码上传 → 服务器 docker build
路线 B：本机 docker build → docker save → scp → docker load
路线 C：本机 docker build → push 到镜像仓库 → 服务器 docker pull
```

| 路线 | 传输内容 | 优点 | 缺点 | 适用 |
|---|---|---|---|---|
| **A. 服务器构建**（本次采用） | 几十 KB 源码 | 传输小、流程简单、不需要镜像仓库 | 服务器要能装依赖、耗 CPU/内存 | 单人小项目 |
| B. save/load | 几百 MB 的镜像 tar | 服务器不需要构建能力 | 每次改代码重传整个镜像层 | 服务器网络差/无法构建 |
| C. registry | 镜像（分层传输） | 可复现、适合 CI、多机部署 | 要维护仓库账号、网络链路 | 团队/生产集群 |

**为什么选 A**：源码只有几十 KB，而镜像有几百 MB；服务器 2 核 2G 装一次依赖就够用。路由 B/C 是"用带宽换服务器算力"，对当前场景不划算。

---

## 三、源码怎么传：tar over SSH

### 3.1 为什么不用 git clone

服务器访问 `https://github.com` 返回 `000`（被网络阻断/不可达），所以不能从 GitHub 拉代码。

### 3.2 为什么用 tar + ssh

```bash
cd /e/My_project/AIChat_v1.0

tar -czf - \
  --exclude='backend/venv' \
  --exclude='backend/__pycache__' \
  --exclude='backend/instance' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/dist' \
  backend frontend nginx docker-compose.yml \
  | ssh aichat 'mkdir -p /root/AIChat && tar -xzf - -C /root/AIChat'
```

逐段：

| 片段 | 作用 |
|---|---|
| `tar -czf -` | 打包（c）+ gzip（z）+ 输出到 stdout（`-`），**本地不生成压缩包文件** |
| `--exclude=...` | 跳过平台相关目录和运行时数据 |
| `| ssh aichat '...'` | 字节流通过 SSH 加密管道送到服务器 |
| `tar -xzf - -C /root/AIChat` | 服务器从 stdin 读（`-`）→ gunzip → 解包到 `/root/AIChat` |

### 3.3 排除项的物理原因

| 排除项 | 原因 |
|---|---|
| `backend/venv` | 虚拟环境里是 **Windows 的 Python 解释器和 .pyd/.dll**，Linux 不能执行 |
| `frontend/node_modules` | 里面有平台相关的原生二进制（如 esbuild 的 `.node`），Windows 版在 Linux 加载失败 |
| `backend/instance` | 本地 SQLite 开发库，生产用 Postgres，带过去只会造成混淆 |
| `frontend/dist` | 服务器会自己构建前端，本地产物不需要（也不应依赖） |
| `pgdata` / `data` | 数据库运行时目录，属于服务器状态，不能从开发机覆盖 |

### 3.4 为什么不 `scp -r`

- `scp -r` 不能方便地按规则排除 `node_modules`（几十万个文件）
- tar 可以"边传边解压"，本地和服务器都不落中间文件
- 一条管道完成，失败时更容易看出是哪一段

---

## 四、镜像源：为什么拉不到基础镜像

### 4.1 现象

```text
docker.io/library/postgres:18-alpine: not found
docker.io/library/python:3.13-slim: not found
```

注意：不是超时，是 **not found**。说明请求到了某个镜像服务，但那个服务里没有这个镜像。

### 4.2 原因

服务器原来的 `/etc/docker/daemon.json` 配了阿里云的个人加速器：

```json
{ "registry-mirrors": ["https://xup15o5d.mirror.aliyuncs.com"] }
```

这个加速器是**不完整/过期的**：`nginx:alpine` 有缓存，`python` / `postgres` / `node` 没有。Docker 优先走 mirror，mirror 返回 not found，就不会再回 Docker Hub 找。

### 4.3 修复

把可用的公共镜像源放在前面：

```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://xup15o5d.mirror.aliyuncs.com"
  ]
}
```

```bash
sudo systemctl restart docker
docker info --format '{{json .RegistryConfig.Mirrors}}'
docker pull postgres:18-alpine
```

### 4.4 镜像源到底是什么

`registry-mirrors` 是 Docker daemon 的配置：当你执行 `docker pull python:3.13-slim`（不带仓库前缀的名字，默认属于 Docker Hub）时，daemon 先按列表顺序问这些 mirror，拿不到再问 Docker Hub。

它**只影响拉取**，不影响构建出来的镜像内容（镜像内容的完整性由 digest / layer 校验保证）。

### 4.5 信任提醒

`docker.1ms.run` 是第三方公共服务，不是官方源。用它意味着你信任它返回的镜像没有被篡改。对学习项目可以接受；对生产环境，应该使用官方 registry、云厂商的容器镜像服务，或用 digest 锁定。

---

## 五、构建上下文与 `.dockerignore`

### 5.1 什么是构建上下文

执行 `docker build ./frontend` 时，Docker 会先把 `./frontend` 目录打包发给构建器（BuildKit），这个目录叫**构建上下文（build context）**。Dockerfile 里的 `COPY` 只能复制上下文里的文件。

本次构建日志里：

```
transferring context: 124.52kB
```

124KB 说明 `node_modules` 和 `dist` 都被排除了。如果没排除，上下文可能是几百 MB。

### 5.2 `.dockerignore` 和 `.gitignore` 的区别

| 文件 | 管什么 |
|---|---|
| `.gitignore` | Git 哪些文件不进版本库 |
| `.dockerignore` | Docker 构建上下文里哪些文件不发给构建器 |

两者**互不生效**。前端目录里必须有：

```
node_modules
dist
```

### 5.3 没有 `.dockerignore` 会怎样

`frontend/Dockerfile` 里：

```dockerfile
RUN npm ci          # 在容器里装 Linux 版依赖
COPY . .            # 把上下文复制进镜像
```

如果上下文包含 Windows 的 `node_modules`，`COPY . .` 会把它覆盖到容器内的 `node_modules` 上——Linux 下加载 Windows 的 esbuild 二进制会直接报错。这是"看起来构建成功、实际跑不起来"的典型原因。

---

## 六、前端为什么要多阶段构建

`frontend/Dockerfile`：

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

| 阶段 | 内容 | 最终镜像里保留吗 |
|---|---|---|
| `build` | Node、npm、源码、node_modules、构建过程 | ❌ 只保留 `dist` |
| 最终阶段 | nginx + `dist` | ✅ |

**好处**：最终镜像只有约 38MB，没有 Node 运行时，也没有源码和几万个依赖文件，攻击面更小。

**代价**：每次构建都要跑 `npm ci` + `vite build`。Docker 层缓存能帮忙：只要 `package.json` / `package-lock.json` 不变，`npm ci` 那一层会复用，只重跑 `COPY . .` 和 `npm run build`。

---

## 七、常用命令的准确语义

| 命令 | 做什么 | 容易误解的点 |
|---|---|---|
| `docker compose build flask` | 按 Dockerfile 构建镜像 | 只造镜像，不启动容器 |
| `docker compose up -d` | 创建网络、创建/重建并启动容器 | 镜像不存在时会构建；镜像已存在就直接用 |
| `docker compose up -d --no-deps flask` | 只重建/启动 flask，不碰依赖服务 | 适合"只改了后端" |
| `docker compose restart flask` | 停止再启动**同一个容器** | **不会**换新镜像 |
| `docker compose ps` | 查看容器状态 | 纯查看，不改任何东西 |
| `docker compose exec flask alembic upgrade head` | 在运行中的容器里执行命令 | 容器必须已启动 |
| `docker compose logs --tail=50 flask` | 看容器日志 | 排查 500/启动失败的第一入口 |

### 7.1 `build` 之后为什么还要 `up`

镜像构建出来后只是躺在 `/var/lib/docker` 里；正在运行的容器仍然用创建它时的旧镜像。`up` 会比较镜像 ID，发现变了就删旧容器、用新镜像建新容器。

### 7.2 `build` 和 `up --build` 的区别

- `build`：只构建
- `up --build`：先构建所有需要的镜像，再启动/重建容器
- 本项目 2G 内存，建议拆开构建，避免并行构建打满内存

---

## 八、端口映射 vs 进程监听

```yaml
nginx:
  ports:
    - "80:80"
    - "443:443"
```

这是 **Docker 的端口发布**：宿主机 80/443 → 容器 80/443，由 docker-proxy 负责转发。

它不等于 nginx 已经在 443 上监听。如果 nginx 配置里只有 `listen 80;`：

- 宿主机 443 有 docker-proxy 在听
- 但容器内 443 没有进程监听
- 外部连接会被拒绝或重置

所以 `ss -tlnp` 看到 443 有进程，不代表 HTTPS 能用；还要看 nginx 配置和 `curl --resolve` 的结果。

---

## 九、基础镜像版本漂移：nginx 1.21.5 → 1.31.8

### 9.1 现象

构建出来的 nginx 版本是 **1.21.5**（2021 年），而 `nginx:alpine` 本应是最新版。

### 9.2 原因

之前用那个不完整的阿里云加速器拉过 `nginx:alpine`，拿到的是旧缓存。Docker 本地已有同名标签，构建时直接用了本地旧镜像。

### 9.3 修复

```bash
docker pull nginx:alpine          # 更新本地标签
docker compose build nginx        # 重新构建应用镜像
docker compose up -d --no-deps nginx
docker compose exec nginx nginx -v
```

结果：`nginx/1.31.8`。

### 9.4 教训

`nginx:alpine` 是**浮动标签**，今天拉和明天拉可能不是同一个版本。生产环境应该钉住：

- `nginx:1.31.8-alpine`（精确 tag）
- 或 `nginx@sha256:...`（digest，内容哈希，最严格）

这相当于 npm 的 lockfile 思路：把"实际用的版本"固定下来。

---

## 十、利弊总结

| 决策 | 选择 | 好处 | 代价 |
|---|---|---|---|
| 代码传输 | tar over SSH | 可排除、不落中间文件 | 没有增量同步，每次全量 |
| 构建位置 | 服务器构建 | 传输小、不需要镜像仓库 | 服务器耗 CPU/内存 |
| 前端构建 | Docker 多阶段 | 产物可复现、镜像自包含 | 服务器跑 npm/Vite |
| 镜像来源 | 第三方 mirror | 网络可达 | 信任边界变化 |
| 端口发布 | 80/443 映射 | 外部可访问 | 增加攻击面，需要安全组配合 |

---

## 十一、常见坑速查

| 现象 | 根因 | 处理 |
|---|---|---|
| `not found` 拉不到基础镜像 | mirror 不完整 | 换 mirror、`docker pull` 验证 |
| 构建上下文几百 MB | 没写 `.dockerignore` | 排除 `node_modules`、`dist` |
| 改了代码但容器还是旧行为 | 只 `build` 没 `up` | `docker compose up -d --no-deps 服务` |
| `restart` 后还是旧代码 | restart 不换镜像 | 用 `up` 重建容器 |
| 443 端口映射了但连不上 | nginx 没监听 443 | 检查 `listen 443 ssl` 和 `nginx -t` |
| 基础镜像版本很旧 | 本地旧 tag 缓存 | `docker pull` 后重建 |
