# npm 锁文件与可复现构建

> 这次部署里最"隐蔽"的一个坑：本地能构建，服务器 `npm ci` 报 `EUSAGE`。
> 根因不是网络，也不是代码，而是 `package-lock.json` 不完整。

---

## 一、三个东西分别是什么

| 名称 | 类比 | 内容 |
|---|---|---|
| `package.json` | **采购需求单** | 直接依赖的名字 + 版本范围（`^1.18.0`） |
| `package-lock.json` | **实际收货单** | 每个包的精确版本、下载地址、内容哈希、依赖关系 |
| `node_modules/` | **仓库里的实物** | 真正下载下来的代码，几百 MB，不进 Git |

### 1.1 `package.json` 只写直接依赖

```json
{
  "dependencies": {
    "axios": "^1.18.0",
    "naive-ui": "^2.44.1",
    "pinia": "^3.0.4",
    "vue": "^3.5.34",
    "vue-router": "^5.1.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^6.0.6",
    "vite": "^8.0.12"
  }
}
```

7 个直接依赖，但它们又依赖别的包，层层展开，本次一共 **170 个包**。这些间接依赖（transitive dependencies）不会写进 `package.json`。

### 1.2 `^`、`~`、精确版本

| 写法 | 允许范围 | 含义 |
|---|---|---|
| `^3.5.34` | `>=3.5.34 <4.0.0` | 主版本不变，允许升级 |
| `~3.5.34` | `>=3.5.34 <3.6.0` | 只允许补丁级升级 |
| `3.5.34` | 只能是 `3.5.34` | 精确锁定 |
| `*` | 任意 | 不推荐 |

`^` 带来灵活性，也带来不确定性：今天装到 3.5.38，下个月可能装到 3.5.40。lock 文件的作用就是把"这一次实际解析出的版本"固定下来。

---

## 二、lock 文件长什么样

本次 `frontend/package-lock.json`：2287 行，80,732 字节，约 170 个包条目。

顶层结构：

```json
{
  "name": "frontend",
  "version": "0.0.0",
  "lockfileVersion": 3,
  "requires": true,
  "packages": {
    "": { ... },
    "node_modules/某个包": { ... }
  }
}
```

`lockfileVersion: 3` 是 npm 7+ 的格式，npm 10 / npm 11 都能读。

### 2.1 根条目 `""`

```json
"": {
  "name": "frontend",
  "version": "0.0.0",
  "dependencies": { "axios": "^1.18.0", ... },
  "devDependencies": { "vite": "^8.0.12", ... }
}
```

它是 `package.json` 里**与依赖有关的字段**的快照，用于和 `package.json` 对账。`private`、`type`、`scripts` 这些和装包无关的字段不会出现在 lock 里。

### 2.2 一个普通包条目

```json
"node_modules/@emnapi/core": {
  "version": "1.11.3",
  "resolved": "https://registry.npmjs.org/@emnapi/core/-/core-1.11.3.tgz",
  "integrity": "sha512-zLpS5asjEb7lq8jYLq37N6XKaE41DIexlY1rF/z4/tIl3wo13Sqm28fRyfIsKZD+NZ8mM5RoKkpW/rBcuoSZSg==",
  "dev": true,
  "optional": true,
  "peer": true,
  "dependencies": {
    "@emnapi/wasi-threads": "1.2.3",
    "tslib": "^2.4.0"
  }
}
```

| 字段 | 含义 |
|---|---|
| 键 `node_modules/@emnapi/core` | 这个包装到哪个目录 |
| `version` | **精确版本**，没有 `^` |
| `resolved` | 下载 `.tgz` 的 URL |
| `integrity` | 文件的 SHA-512 哈希，下载后校验，防篡改/防损坏 |
| `dev` | 只在开发/构建时需要 |
| `optional` | 可选依赖，装不上不影响整体安装（常用于平台相关的原生包） |
| `peer` | 作为 peer 依赖被提升到顶层 |
| `dependencies` | 这个包自己又依赖谁 |

### 2.3 嵌套的 `node_modules`

```json
"node_modules/@rolldown/binding-wasm32-wasi/node_modules/@emnapi/wasi-threads": {
  "version": "1.2.1",
  ...
}
```

路径里出现两次 `node_modules`，表示：顶层用的是 `@emnapi/wasi-threads@1.2.3`，但这个包需要 `1.2.1`。两个版本不能共存于同一个目录，npm 就把旧版本嵌套装在它自己的 `node_modules` 下。

**同一个包的不同版本可以同时存在**，靠路径隔离。

---

## 三、`npm install` vs `npm ci`

| 命令 | 读什么 | 会不会改 lock | 适用场景 |
|---|---|---|---|
| `npm install` | `package.json` + 已有 lock | 可能会更新 lock | 日常开发、加依赖 |
| `npm ci` | **只信 lock** | 不会 | CI、Docker 构建 |

`npm ci` 的规则：

1. 先删掉 `node_modules`
2. 校验 `package.json` 和 `package-lock.json` 是否一致
3. 不一致直接报 `EUSAGE` 并退出
4. 一致则严格按 lock 安装

**严格是特性，不是缺点**：它保证"同一份 lock，在任何机器、任何时间，装出来的依赖完全一样"。

---

## 四、这次到底出了什么问题

### 4.1 报错

```text
npm error `npm ci` can only install packages when your package.json and
package-lock.json or npm-shrinkwrap.json are in sync.

Missing: @emnapi/core@1.11.3 from lock file
Missing: @emnapi/runtime@1.11.3 from lock file
Invalid: lock file's @emnapi/wasi-threads@1.2.1 does not satisfy 1.2.3
Missing: @emnapi/core@1.10.0 from lock file
...
```

### 4.2 依赖链

```text
vite 8
  └─ rolldown
       └─ @rolldown/binding-wasm32-wasi（可选，cpu=wasm32）
            ├─ @emnapi/core@1.10.0
            ├─ @emnapi/runtime@1.10.0
            └─ @napi-rs/wasm-runtime
```

`@rolldown/binding-wasm32-wasi` 是"没有原生二进制时用的 WASM 版本"，标记为 `optional`。它的依赖在 lock 里**被引用**了，但 `packages` 字典里**没有对应的包条目**。

### 4.3 为什么本地生成时没发现

| 环境 | Node | npm |
|---|---|---|
| 本机 Windows | v24.11.1 | **11.6.2** |
| 容器 `node:22-alpine` | 22.x | **10.x** |

- npm 11 生成 lock 时，对 optional / platform 相关依赖的处理和 npm 10 不同，写出了"引用存在、条目缺失"的 lock
- npm 11 自己的 `npm ci` 可能能容忍
- npm 10 的 `npm ci` 严格校验，发现缺条目就拒绝

这不是你代码的问题，是 **npm 大版本之间的 lock 解析差异**。

---

## 五、为什么不能把 Dockerfile 改成 `npm install`

看起来只要把：

```dockerfile
RUN npm ci
```

改成：

```dockerfile
RUN npm install
```

构建就能过。但这样等于：

- Docker 每次构建时自己重新解析依赖
- lock 文件失去"固定版本"的作用
- 今天构建和明天构建可能装到不同版本
- 出问题时无法复现"当时到底装的哪个版本"

lock 文件存在的意义就是防止这件事，所以正确做法是**修 lock**，不是绕过它。

---

## 六、修复过程

### 6.1 用 npm 10 在临时目录重新生成

不要直接改仓库里的 lock，先在临时目录验证：

```bash
TMP=/c/Users/123/AppData/Local/Temp/aichat-lock-test
mkdir -p "$TMP"
cp frontend/package.json frontend/package-lock.json "$TMP"/
cd "$TMP"

# 用 npm 10（和容器一致）重新生成，显式指定 npmjs 源
npx -y npm@10 install --package-lock-only \
  --ignore-scripts --no-audit --no-fund \
  --registry=https://registry.npmjs.org
```

**为什么要显式 `--registry`**：本机 npm 默认源可能是 npmmirror，生成的新条目会写成 `registry.npmmirror.com`，和原 lock 的 `registry.npmjs.org` 混在一起。显式指定可以保持来源一致。

### 6.2 用 dry-run 验证

```bash
npx -y npm@10 ci --dry-run \
  --ignore-scripts --no-audit --no-fund \
  --registry=https://registry.npmjs.org
```

`--dry-run` 只做校验和依赖解析，不真正安装。能列出 "added 170 packages" 且不报 `EUSAGE`，就说明 lock 和 `package.json` 同步了。

### 6.3 对比 diff，确认只改了该改的

```bash
diff -u frontend/package-lock.json "$TMP/package-lock.json"
```

本次结果：**63 行新增，8 行删除**。

- 新增 `@emnapi/core`、`@emnapi/runtime`（1.11.3）
- 新增嵌套的 `@rolldown/binding-wasm32-wasi/node_modules/@emnapi/*`（1.10.0）
- `@emnapi/wasi-threads` 从 1.2.1 → 1.2.3
- 去掉几个包上的 `"peer": true` 标记（npm 10 重新计算的结果，版本没变）

### 6.4 替换、提交、上传、重建

```bash
cp "$TMP/package-lock.json" frontend/package-lock.json
git add frontend/package-lock.json
git commit -m "fix: 补全 npm 锁文件缺失的 @emnapi 可选依赖"
```

上传：

```powershell
scp E:\My_project\AIChat_v1.0\frontend\package-lock.json `
  aichat:/root/AIChat/frontend/package-lock.json
```

服务器重建：

```bash
cd /root/AIChat
docker compose build nginx
docker compose up -d --no-deps nginx
```

因为 `COPY package.json package-lock.json ./` 这一层的输入变了，`npm ci` 会重新执行。

---

## 七、Docker 层缓存和 lock 的关系

`frontend/Dockerfile`：

```dockerfile
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build
```

| 改动 | 会重跑哪一层 |
|---|---|
| 只改 `src/` 代码 | `COPY . .` 和 `npm run build`；`npm ci` 命中缓存 |
| 改 `package.json` 或 `package-lock.json` | `npm ci` 重新执行 |
| 改 `Dockerfile` 里 `npm ci` 之前的指令 | 从改动处往后全部重新执行 |

把 `package*.json` 单独提前 `COPY`，就是为了"依赖没变时不重装依赖"。这是 Dockerfile 里最常见的优化之一。

---

## 八、日常开发的正确姿势

1. **加依赖用 `npm install 包名`**，它会同时更新 `package.json` 和 `package-lock.json`
2. **两个文件一起提交**，不要只提交 `package.json`
3. **不要手动编辑 lock 文件**
4. **不要提交 `node_modules`**
5. **Docker 构建用 `npm ci`**，不要用 `npm install`
6. **本地 Node/npm 大版本尽量和 Docker 基础镜像一致**；不一致时，至少保证 lock 能被目标版本的 `npm ci` 接受

---

## 九、一句话总结

**`package.json` 说"要什么范围"，lock 说"实际装了哪个精确版本"，`npm ci` 说"只按 lock 装，不一致就报错"。**
这次是"lock 缺了几条可选依赖的记录"，npm 11 生成时没暴露，npm 10 严格校验时抓出来了。修法是**用目标环境的 npm 版本重新生成 lock**，而不是让 Docker 改成 `npm install` 绕过去。
