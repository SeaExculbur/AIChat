# HTTPS 证书与 TLS 握手——从 ACME 验证到 443 监听

> 本文回答：HTTPS 到底解决了什么、证书和私钥分别是什么、Let's Encrypt 怎么确认域名归你、nginx 为什么必须先有证书才能监听 443、自动续期为什么要 reload。

---

## 一、HTTPS 解决三个问题

| 问题 | HTTP | HTTPS |
|---|---|---|
| **保密性** | 明文，中间人能看内容 | 加密，中间人只看到密文 |
| **完整性** | 内容可被篡改 | 篡改会导致校验失败 |
| **身份认证** | 不知道对面是谁 | 证书证明"对面确实是这个域名" |

HTTP 下，登录密码、JWT token、聊天内容都以明文经过公网；HTTPS 把整条 HTTP 报文放进 TLS 加密通道里。

---

## 二、证书和私钥分别是什么

### 2.1 一对密钥

- **公钥**：可以公开，用来加密、验签
- **私钥**：绝不能泄露，用来解密、签名

它们成对生成，数学上配对，但**不能从公钥反推出私钥**。

### 2.2 证书里有什么

一个 TLS 证书（X.509）主要包含：

| 字段 | 例子 | 作用 |
|---|---|---|
| 域名（SAN） | `seaexculbur.com`、`www.seaexculbur.com` | 证明这个证书属于哪些域名 |
| 公钥 | 一长串 | 与服务器私钥配对 |
| 签发者（CA） | Let's Encrypt | 谁给它签的字 |
| 有效期 | 2026-10-22 ~ 2027-01-20 | 过期就失效 |
| CA 的数字签名 | 一长串 | 证明证书内容没被篡改 |

**证书是公开的**：每个访问你网站的浏览器都会收到它。它不是秘密，伪造它也没用，因为没有对应私钥就无法完成握手。

**私钥是绝密的**：泄露后别人可以冒充你的域名，直到证书被吊销。

### 2.3 证书链和信任根

浏览器不直接信任 Let's Encrypt 签发的证书，而是信任一个**根证书**（Root CA），根证书预先装在操作系统/浏览器里。

验证链：

```
你的证书（leaf）
   ↑ 由中间 CA 签发
中间 CA 证书（intermediate）
   ↑ 由根 CA 签发
根 CA 证书（root，浏览器自带）
```

服务器在握手时要发送 **leaf + intermediate**，这就是 `fullchain.pem`。根证书不用发，浏览器自己有。

---

## 三、ACME 与 Let's Encrypt

### 3.1 名词

- **CA（Certificate Authority）**：证书颁发机构，负责签名
- **Let's Encrypt**：一个免费、自动化的 CA
- **ACME**：CA 和客户端之间的协议，全称 Automatic Certificate Management Environment
- **certbot**：一个 ACME 客户端，负责"申请、验证、下载、续期"

Let's Encrypt 不关心你用什么客户端，certbot、acme.sh、Caddy 都可以，只要说 ACME 协议。

### 3.2 为什么需要"验证域名"

如果任何人随便填一个域名就能拿到证书，那证书就失去了"证明身份"的意义。所以 CA 在签发前必须确认：**申请者真的控制这个域名**。

常见验证方式：

| 方式 | 做法 | 要求 |
|---|---|---|
| **HTTP-01**（本次使用） | CA 访问 `http://域名/.well-known/acme-challenge/<token>`，比对内容 | 80 端口对公网可达 |
| DNS-01 | 在 DNS 里加一条 TXT 记录 | 能改 DNS，支持通配符证书 |
| TLS-ALPN-01 | 在 443 上用特殊 ALPN 协议验证 | 443 可达，实现较复杂 |

---

## 四、HTTP-01 的完整流程

```text
1. certbot 在服务器本地生成一对密钥（公钥 + 私钥），私钥不出服务器
2. certbot 向 Let's Encrypt 提交域名和公钥（CSR）
3. Let's Encrypt 返回一个挑战 token
4. certbot 把 token 写到 webroot：
   /root/AIChat/certbot/www/.well-known/acme-challenge/<token>
5. Let's Encrypt 从公网访问：
   http://seaexculbur.com/.well-known/acme-challenge/<token>
6. DNS 把域名解析到服务器公网 IP
7. 请求到达 nginx
8. nginx 根据 location 把请求映射到 /var/www/certbot/...
9. nginx 返回文件内容
10. Let's Encrypt 比对内容 → 确认你控制域名
11. Let's Encrypt 用 CA 私钥给你的公钥签名，签发证书
12. certbot 把证书和私钥写入 /etc/letsencrypt/live/<域名>/
```

**注意第 1 步**：私钥是 certbot 本地生成的，不是 Let's Encrypt 发给你的。CA 只对你的公钥签名，从不接触私钥。

---

## 五、webroot + Docker 挂载

### 5.1 certbot 在宿主机，nginx 在容器

```
宿主机 Ubuntu
├── /root/AIChat/certbot/www/          ← certbot 写挑战文件
│        │ bind mount（只读）
│        ▼
│   容器 nginx: /var/www/certbot/      ← nginx 读挑战文件
│
└── /etc/letsencrypt/                  ← certbot 写证书和私钥
         │ bind mount（只读）
         ▼
    容器 nginx: /etc/letsencrypt/      ← nginx 读证书
```

compose：

```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
  - ./certbot/www:/var/www/certbot:ro
  - /etc/letsencrypt:/etc/letsencrypt:ro
```

### 5.2 为什么是两个目录

| 目录 | 内容 | 敏感度 | 生命周期 |
|---|---|---|---|
| `certbot/www` | 挑战文件 | 公开（会被 HTTP 访问） | 验证完即可丢 |
| `/etc/letsencrypt` | 证书、私钥、账户信息、续期配置 | 私钥绝密 | 长期保留 |

**不能合并的原因**：

1. 私钥不能放在一个会被 HTTP 暴露的目录里
2. 两者生命周期不同：挑战文件临时，证书长期
3. certbot 默认布局就是 `/etc/letsencrypt`，改路径要改 `--config-dir` 等参数，续期容易出错

### 5.3 为什么加 `:ro`

容器里的 nginx 只需要**读**：

- 读挑战文件返回给 CA
- 读证书完成 TLS 握手

写文件的是宿主机上的 certbot。只读挂载把容器的权限降到"只能看"，即使 nginx 被攻破也改不了证书。

---

## 六、nginx 的 ACME 配置

阶段一，在 80 的 server 块里：

```nginx
location /.well-known/acme-challenge/ {
    root /var/www/certbot;
}
```

请求 `/ .well-known/acme-challenge/<token>` 会映射到容器内的 `/var/www/certbot/.well-known/acme-challenge/<token>`。

**为什么不能只靠 `location /`**：前端是 SPA，`try_files $uri /index.html` 会把所有找不到的路径都返回 `index.html`。CA 拿到 HTML 而不是 token，验证失败。

**location 匹配规则**：`/.well-known/acme-challenge/` 是更具体的前缀，优先级高于 `/`，所以挑战请求不会被 SPA 吞掉。

---

## 七、certbot 命令与输出

```bash
sudo certbot certonly --webroot \
  -w /root/AIChat/certbot/www \
  -d seaexculbur.com -d www.seaexculbur.com \
  --email 你的邮箱 --agree-tos
```

| 参数 | 作用 |
|---|---|
| `certonly` | 只申请证书，不改 nginx 配置 |
| `--webroot` | 用 webroot 方式做 HTTP-01 验证 |
| `-w` | webroot 目录（certbot 往这里写挑战文件） |
| `-d` | 域名，可重复；证书会覆盖所有 `-d` |
| `--email` | 账户联系邮箱，用于到期提醒 |
| `--agree-tos` | 同意 CA 的服务条款 |

这次输出（节选）：

```text
Account registered.
Requesting a certificate for seaexculbur.com and www.seaexculbur.com

Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/seaexculbur.com/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/seaexculbur.com/privkey.pem
This certificate expires on 2027-01-20.
```

### 7.1 证书目录结构

```text
/etc/letsencrypt/
├── live/seaexculbur.com/
│   ├── cert.pem        → 你的域名证书（leaf）
│   ├── chain.pem       → 中间 CA 证书
│   ├── fullchain.pem   → cert.pem + chain.pem（nginx 用这个）
│   └── privkey.pem     → 私钥（600，只有 root 能读）
├── archive/seaexculbur.com/
│   └── 每次续期生成的新文件（带时间戳）
├── accounts/           → ACME 账户密钥
└── renewal/            → 续期配置
```

`live/` 下的文件是**符号链接**，指向 `archive/` 里当前版本。续期时 certbot 在 `archive/` 写新文件，再更新 `live/` 的链接，所以 nginx 配置里的路径不用改。

---

## 八、nginx 443 配置

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name seaexculbur.com www.seaexculbur.com;

    ssl_certificate     /etc/letsencrypt/live/seaexculbur.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seaexculbur.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    location / {
        root /usr/share/nginx/html;
        try_files $uri /index.html;
    }

    location /api/ {
        proxy_pass http://flask:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

| 指令 | 作用 |
|---|---|
| `listen 443 ssl` | 在 443 上启用 TLS |
| `http2 on` | 启用 HTTP/2（nginx 1.25.1+ 的新写法） |
| `ssl_certificate` | 证书链（leaf + intermediate） |
| `ssl_certificate_key` | 私钥 |
| `ssl_protocols` | 只允许 TLS 1.2 / 1.3，禁用旧版本 |
| `ssl_session_cache` | 缓存 TLS 会话，减少重复握手 |
| `X-Forwarded-Proto` | 告诉 Flask 原始协议是 HTTPS |

80 的 server 块：

```nginx
server {
    listen 80;
    server_name seaexculbur.com www.seaexculbur.com;

    # 续期验证走这里，不能删
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # 其他请求全部跳 HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}
```

**为什么 80 还要留 ACME location**：证书 90 天续期时，CA 还会来访问这个路径。如果 80 全部 301，验证请求被跳到 443，而 443 的证书可能已经过期，续期就会失败。

---

## 九、TLS 握手时到底发了什么

以 TLS 1.3 为例：

```text
ClientHello                   客户端：支持的算法、随机数、密钥交换参数
ServerHello                   服务器：选定的算法、服务器随机数、密钥交换参数
EncryptedExtensions
Certificate                   服务器：证书链（公开）
CertificateVerify             服务器：对握手 transcript 的签名（用私钥生成）
Finished
```

### 9.1 证书是必须发的

客户端需要证书来：

1. 验证域名是否匹配
2. 验证是否由受信任的 CA 签发
3. 从证书里取出**公钥**

### 9.2 私钥从不发送

服务器用私钥做两件事：

- 在 `CertificateVerify` 里对握手内容**签名**
- （TLS 1.2 的 RSA 密钥交换中）解密客户端用公钥加密的预主密钥

发送的是**签名结果**，不是私钥。客户端用证书里的公钥验签，成功就证明"服务器确实持有对应私钥"。

**为什么不能发私钥**：

1. 协议里没有这个消息类型
2. 发了也没用，客户端不需要
3. 私钥一旦离开服务器，就等于身份被复制

### 9.3 证书"公开"和"私钥保密"的边界

- 证书：每次握手发给客户端 → 公开
- 私钥：只在内存里参与运算 → 绝密
- 两者都没有 HTTP URL；但证书会被主动发送，私钥不会

如果想深挖"nginx 为什么不会把私钥当文件发出去"，见本文第十一节"HTTP 可见性"。

---

## 十、自动续期

### 10.1 有效期

Let's Encrypt 证书有效期 **90 天**。certbot 默认在到期前 **30 天**开始尝试续期，每天跑两次。

### 10.2 定时器

apt 安装的 certbot 会注册 systemd timer：

```bash
systemctl list-timers | grep certbot
systemctl status certbot.timer
```

### 10.3 续期后为什么要 reload nginx

certbot 续期只替换磁盘上的证书文件。**nginx 启动时把证书读进内存**，之后一直用内存里的那份。不 reload，磁盘上换了新证书，nginx 还在用旧的，90 天后浏览器会看到过期证书。

所以要在续期成功后自动 reload：

```bash
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy

sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh >/dev/null <<'EOF'
#!/bin/sh
cd /root/AIChat && docker compose exec -T nginx nginx -s reload
EOF

sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

`renewal-hooks/deploy/` 下的脚本会在**每次续期成功后**自动执行。

### 10.4 验证

```bash
sudo certbot renew --dry-run
```

`--dry-run` 使用 Let's Encrypt 的测试环境，不会消耗正式证书的签发额度，也不会替换真实证书。

**注意**：`--dry-run` 不一定会执行 deploy 钩子（取决于 certbot 版本和参数）。所以钩子脚本要单独手动跑一次：

```bash
sudo /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

看到 `signal process started` 就说明 nginx 收到了 reload 信号。

---

## 十一、HTTP 可见性 vs TLS 发送

这是两套独立的通道，别混：

| 通道 | 传什么 | 决定者 |
|---|---|---|
| HTTP 请求/响应 | URL 对应的文件内容 | nginx 的 `location` / `root` 配置 |
| TLS 握手 | 协议规定的握手消息 | TLS 协议 + 加密库实现 |

- 挑战文件有 HTTP URL → 因为它被 `location /.well-known/acme-challenge/` 映射了
- 证书没有 HTTP URL → 没有 location 指向 `/etc/letsencrypt`；它在 TLS 握手时发送
- 私钥没有 HTTP URL，也不在 TLS 握手消息里 → 只在本地做签名运算

**安全边界靠配置**：如果写了 `location /leak/ { alias /etc/letsencrypt/; }`，私钥就能被 HTTP 下载。Docker 的 `:ro` 只防写，不防读，也不决定 URL。

---

## 十二、故障排查

| 现象 | 可能原因 | 排查 |
|---|---|---|
| `curl: (7) Failed to connect ... 443` | nginx 没监听 443 / 容器没映射 / 安全组没开 | `grep listen 443`、`docker compose ps`、服务器本机 `curl --resolve` |
| `nginx -t` 报 `cannot load certificate` | 证书路径不对 / 挂载没生效 | `docker compose exec nginx ls /etc/letsencrypt/live/...` |
| `nginx -t` 报 `unknown directive "http2"` | nginx 版本低于 1.25.1 | 升级镜像，或改用 `listen 443 ssl http2;` |
| 浏览器证书不受信任 | 自签名 / 链不完整 | 用 `fullchain.pem`，不要用 `cert.pem` |
| 证书域名不匹配 | 申请时漏了 `www` | 重新签发，`-d` 带上所有域名 |
| 301 循环 | 443 块里也写了跳转 | 跳转只放在 80 块 |
| 续期失败 | 80 的 ACME location 被删/被跳转 | 保留 `/.well-known/acme-challenge/` |
| 公网不通、本机通 | 安全组 443 未放行 | 阿里云控制台检查入方向 |

### 12.1 本机模拟公网请求

```bash
curl -I --resolve seaexculbur.com:443:127.0.0.1 https://seaexculbur.com
```

`--resolve` 强制把域名解析到 `127.0.0.1`，这样请求走本机回环，但 SNI 和 Host 仍然是真实域名，可以同时验证 TLS 证书和 nginx 配置。

- 本机通、公网不通 → 安全组
- 本机也不通 → nginx / 容器端口映射

---

## 十三、常用术语速查

| 术语 | 解释 |
|---|---|
| **TLS** | 传输层安全协议，HTTPS 的加密层 |
| **握手（handshake）** | 建立加密连接前的协商过程 |
| **CA** | 证书颁发机构 |
| **ACME** | 自动证书管理协议 |
| **CSR** | 证书签名请求，包含域名和公钥 |
| **leaf / fullchain** | 叶子证书 / 叶子 + 中间证书链 |
| **SNI** | TLS 握手时客户端告知要访问的域名 |
| **HTTP/2** | 多路复用、头部压缩的 HTTP 新版本 |
| **HSTS** | 强制浏览器以后只用 HTTPS 访问 |
| **OCSP** | 查询证书是否被吊销的协议 |

---

## 十四、安全建议

1. **私钥权限 600**：`/etc/letsencrypt/live/.../privkey.pem` 只有 root 能读
2. **不要让任何 URL 指向 `/etc/letsencrypt`**
3. **容器只读挂载**证书目录
4. **只启用 TLS 1.2 / 1.3**
5. **HSTS 等稳定后再加**：

```nginx
add_header Strict-Transport-Security "max-age=31536000" always;
```

HSTS 会让浏览器以后强制走 HTTPS；如果配置错了，回退比较麻烦，所以先确认 HTTPS 稳定。

---

## 十五、一句话总结

**Let's Encrypt 通过 HTTP-01 确认你控制域名 → certbot 本地生成密钥对、把挑战文件写进 webroot → CA 签名证书 → nginx 用 fullchain + 私钥监听 443 → 握手时发证书、私钥只在本地签名 → 90 天续期时用 deploy 钩子 reload nginx。**
