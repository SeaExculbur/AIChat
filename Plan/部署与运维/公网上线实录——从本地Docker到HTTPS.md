# 公网上线实录——从本地 Docker 到 HTTPS

> 时间：2026-10-22
> 目标：把 AIChat 从"本地能跑"部署到阿里云 ECS，绑定域名并启用 HTTPS
> 本文是总览，具体原理拆在其余几篇里，见文末索引

---

## 一、最终架构

```
浏览器
  │  https://seaexculbur.com   （TLS 1.2/1.3 + HTTP/2）
  ▼
阿里云 ECS（Ubuntu 26.04，2 核 2G）
  │
  ├─ nginx 容器（nginx:1.31.8-alpine）
  │    ├─ 80  → 只做两件事：ACME 续期验证、其余 301 跳 HTTPS
  │    ├─ 443 → /      前端静态文件（Vite 构建产物）
  │    │        /api/  → 反向代理到 flask:5000
  │    │
  │    ├─ 挂载 ./nginx/nginx.conf          → /etc/nginx/conf.d/default.conf
  │    ├─ 挂载 ./certbot/www               → /var/www/certbot（ACME 验证文件）
  │    └─ 挂载 /etc/letsencrypt            → /etc/letsencrypt（证书，只读）
  │
  ├─ flask 容器（Gunicorn，4 个 sync worker）
  │    └─ 调 DeepSeek API，SSE 流式返回
  │
  └─ postgres 容器（postgres:18-alpine）
       └─ 数据落在宿主机 ./pgdata（bind mount）
```

对外只暴露 22 / 80 / 443。数据库只监听容器网络内的 5432，Flask 只监听容器网络内的 5000，都不对公网暴露。

---

## 二、上线前的状态

| 项 | 状态 |
|---|---|
| 本地代码 | `feature/manual-approval` 分支，后端接口 curl 通过，前端多会话基本可用 |
| 本地开发库 | SQLite（`backend/instance/aichat.db`） |
| 服务器 | 阿里云 ECS，Ubuntu 26.04.1，2 核 1.7G 内存，40G 磁盘 |
| 服务器软件 | Docker 29.1.3、Compose 2.40.3 已装 |
| 域名 | 已备案，但还没解析 |
| 安全组 | 只开了 22 和 ICMP，80/443 未开 |
| 代码仓库 | GitHub 上的 `SeaExculbur/AIChat` |

服务器上 `/root/AIChat` 不存在，是从零开始的。

---

## 三、阶段 0：服务器体检

```bash
ssh aichat
docker --version && docker compose version
free -h
df -h /
```

当时结果：

- 内存 1.7Gi，**swap 为 0**
- 磁盘 40G，已用 3.2G
- Docker / Compose 版本正常

**为什么先看内存**：2G 内存构建镜像（`pip install`、`npm ci`、Vite 打包）有 OOM 风险。swap 为 0 时，内存一旦打满，Linux 的 OOM Killer 会直接杀掉进程，表现为构建莫名其妙失败。所以第一步先补 2G swap：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

`/etc/fstab` 那一行是让 swap 在重启后自动挂载。

---

## 四、阶段 1：网络与镜像源

这一阶段踩了两个大坑，详见《Docker构建链路与镜像传输.md》。

### 4.1 GitHub 从服务器不可达

服务器访问 `https://github.com` 返回 `000`，所以不能 `git clone`。代码改用本机 `tar + ssh` 打包上传。

### 4.2 Docker Hub 不可达，阿里云加速器不完整

- 直连 `registry-1.docker.io` 返回 `000`
- 原来的阿里云个人加速器 `nginx:alpine` 能拉，但 `python:3.13-slim`、`postgres:18-alpine`、`node:22-alpine` 全部 `not found`
- 换成 `docker.1ms.run` 后能正常拉取

改 `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": ["https://docker.1ms.run", "https://xup15o5d.mirror.aliyuncs.com"]
}
```

然后 `sudo systemctl restart docker`。

**注意**：`docker.1ms.run` 是第三方公共加速器，用它意味着信任它没有篡改镜像。自用学习项目可以接受，但要意识到镜像的信任边界变了。

---

## 五、阶段 2：代码上传

因为 GitHub 不可达，用 tar 通过 SSH 传：

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

排除的东西和原因：

| 排除项 | 原因 |
|---|---|
| `backend/venv` | Windows 的虚拟环境，Linux 不能用 |
| `frontend/node_modules` | Windows 编译的二进制（如 esbuild），Linux 不能用 |
| `backend/instance` | 本地 SQLite 开发库，生产用 Postgres |
| `frontend/dist` | 方案 B 下由服务器构建，不需要本地产物 |
| `pgdata` / `data` | 数据库运行时目录，不能从开发机带过去 |

`backend/.env.production` **没有排除**，因为它是生产密钥文件，需要传上去；SSH 传输本身加密。传完立刻收紧权限：

```bash
chmod 600 /root/AIChat/backend/.env.production
```

---

## 六、阶段 3：构建镜像

### 6.1 为什么选"服务器上构建"

把应用镜像送上服务器有三条路：

1. 服务器上 `docker compose build`（本次采用）
2. 本机 build → `docker save` → 传 tar → `docker load`
3. 本机 build → push 到镜像仓库 → 服务器 pull

选 1 的原因：源码只有几十 KB，传源码最便宜；服务器有网络和 CPU，`pip install` 走清华源即可。路线 2 每次要传几百 MB 的镜像层；路线 3 还要额外维护镜像仓库账号。

### 6.2 前端采用多阶段构建

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

第一阶段用 Node 编译，第二阶段只把 `dist` 复制进 nginx。最终镜像里没有 Node、没有源码、没有 node_modules。

**关键前提**：必须有 `frontend/.dockerignore`：

```
node_modules
dist
```

没有它，`COPY . .` 会把本机 Windows 的 `node_modules` 复制进容器，覆盖掉 `npm ci` 装好的 Linux 版本，Vite 构建直接失败。`.gitignore` 管不到 Docker 构建上下文，只有 `.dockerignore` 管得到。

### 6.3 分两次构建

```bash
docker compose build flask
docker compose build nginx
docker compose up -d
```

没有用 `up -d --build` 一次全上，是因为两个构建并行会同时抢 1.7G 内存。分开跑，一次只有一个构建任务。

---

## 七、阶段 4：启动与迁移

```bash
docker compose up -d
docker compose ps
docker compose exec db pg_isready -U aichat -d aichat
docker compose exec flask alembic upgrade head
docker compose exec db psql -U aichat -d aichat -c "\dt"
```

期望四张表：

```
alembic_version
chat_history
conversations
users
```

**为什么迁移要单独跑**：容器启动只负责起进程，不会自动建表。`alembic upgrade head` 才是把迁移脚本打到 Postgres 上的动作。

---

## 八、阶段 5：域名与安全组

1. 阿里云安全组放行 80 / 443（TCP，`0.0.0.0/0`）
2. 阿里云云解析添加两条 A 记录：

| 主机记录 | 类型 | 记录值 |
|---|---|---|
| `@` | A | 服务器公网 IP |
| `www` | A | 服务器公网 IP |

3. 验证：

```bash
nslookup seaexculbur.com 223.5.5.5
nslookup www.seaexculbur.com 223.5.5.5
```

详见《域名备案与DNS解析实战.md》。

---

## 九、阶段 6：HTTPS

分两阶段，原因和完整流程见《HTTPS证书与TLS握手.md》：

1. **阶段一**：80 端口加 ACME 挑战目录 → 重启 nginx → certbot 签发证书
2. **阶段二**：加 443 server 块 + 80 的 301 跳转 → `nginx -t` → reload

最终验证：

```bash
curl -I https://seaexculbur.com     # 200
curl -I http://seaexculbur.com      # 301
```

---

## 十、最终验收清单

| 检查项 | 结果 |
|---|---|
| 三个容器 Up | ✅ |
| Postgres 可连接 | ✅ |
| 四张表存在，迁移版本为 head | ✅ |
| `http://域名` 返回 301 到 HTTPS | ✅ |
| `https://域名` 返回 200 | ✅ |
| 浏览器锁图标正常 | ✅ |
| 注册 → 管理员放行 → 登录 → 聊天 | ✅ |
| SSE 流式输出正常 | ✅ |
| 续期钩子可执行 | ✅ |

---

## 十一、复盘：这次为什么能走通

1. **每一步都验证，不跳步**：镜像能不能拉、容器是不是 Up、表是不是建出来、80/443 是不是真的监听，都用命令确认过，而不是"看起来应该行"。
2. **出错先定位在哪一层**：连不上 443，先分清是 DNS、安全组、Docker 端口映射、nginx 监听、证书，还是应用本身。分层排查比猜快。
3. **配置改动前先 `nginx -t`**：nginx 配置写错会导致整个进程起不来，先检查再 reload。
4. **明白每个挂载/端口存在的理由**：不是照抄 compose，而是知道"这个挂载解决什么问题、没有它会怎样"。

---

## 十二、相关文档索引

| 主题 | 文档 |
|---|---|
| 域名、备案、DNS | `域名备案与DNS解析实战.md` |
| Docker 构建、镜像源、代码传输 | `Docker构建链路与镜像传输.md` |
| PostgreSQL 18 数据卷 | `PostgreSQL18数据卷变更.md` |
| npm 锁文件与可复现构建 | `npm锁文件与可复现构建.md` |
| HTTPS、TLS、certbot | `HTTPS证书与TLS握手.md` |
| 本次所有坑的汇总 | `本次部署踩坑清单.md` |
| 上线后的安全与运维 | `上线后的安全与运维清单.md` |
| Docker 基础（已有） | `Docker容器化部署.md` |
| 网络基础（已有） | `计算机网络与通信原理.md` |
