# PostgreSQL 18 数据卷变更——一个会静默丢数据的坑

> 这个坑不会报错，容器照常启动、数据照常写入，但你以为在 `./pgdata` 里的数据，其实在 Docker 的匿名卷里。

---

## 一、先复习：bind mount 是什么

```yaml
db:
  volumes:
    - ./pgdata:/var/lib/postgresql
```

左边是**宿主机**路径（相对 `docker-compose.yml` 所在目录），右边是**容器内**路径。这个挂载叫 **bind mount（绑定挂载）**：把宿主机的一个目录直接映射到容器里，两边看到的是同一份文件。

数据持久化的关键就在这：容器删了没关系，只要宿主机目录还在，数据就在。

具体原理见已有的《Docker底层补充——Windows架构与卷映射.md》和《Docker容器化部署.md》。

---

## 二、PostgreSQL 18 改了什么

### 2.1 旧版本的行为

PostgreSQL 17 及以前，官方镜像的默认数据目录是：

```
PGDATA=/var/lib/postgresql/data
```

官方 Dockerfile 声明：

```dockerfile
VOLUME /var/lib/postgresql/data
```

所以大家习惯写：

```yaml
volumes:
  - ./pgdata:/var/lib/postgresql/data
```

### 2.2 PostgreSQL 18 的变化

从 18 开始，官方镜像改成了：

```
PGDATA=/var/lib/postgresql/18/docker
VOLUME /var/lib/postgresql
```

为什么改：为了让 `pg_upgrade` 和未来大版本升级更方便——把版本号放进路径，不同大版本的数据目录可以并列存在，父目录作为卷挂载点更灵活。

### 2.3 旧配置会发生什么

如果还写：

```yaml
volumes:
  - ./pgdata:/var/lib/postgresql/data
```

那么：

- 容器内 `/var/lib/postgresql/data` 被挂载到宿主机 `./pgdata`
- 但 PostgreSQL 18 实际把数据写到 `/var/lib/postgresql/18/docker`
- 这个路径**没有**被挂载，数据落进了镜像声明的匿名卷（`/var/lib/postgresql`）

结果：

| 你以为 | 实际 |
|---|---|
| 数据在 `./pgdata` | `./pgdata` 是空的 |
| 备份 `./pgdata` 就安全了 | 备份的是空目录 |
| `docker compose down` 后数据还在 | 数据在匿名卷里，`down -v` 或 `prune` 可能被删 |

**最危险的地方**：不会报错。Postgres 正常启动、正常读写，只有你去 `ls ./pgdata` 才会发现是空的。

---

## 三、怎么确认镜像的真实配置

不要凭记忆，直接看镜像：

```bash
docker image inspect postgres:18-alpine --format '{{json .Config.Env}}'
docker image inspect postgres:18-alpine --format '{{json .Config.Volumes}}'
```

本次输出（节选）：

```json
// Env
"PGDATA=/var/lib/postgresql/18/docker"

// Volumes
{"/var/lib/postgresql":{}}
```

这就确认了两件事：

1. 数据目录是 `/var/lib/postgresql/18/docker`
2. 官方声明的卷是父目录 `/var/lib/postgresql`

---

## 四、正确的 compose 写法

```yaml
db:
  image: postgres:18-alpine
  volumes:
    - ./pgdata:/var/lib/postgresql
```

挂父目录，而不是挂 `.../18/docker`。

### 为什么挂父目录，而不是精确挂 PGDATA

两种都能让数据落到宿主机，但挂父目录有三个好处：

1. **跟随官方约定**：官方 `VOLUME` 就是父目录，跟着它走不容易出错
2. **升级友好**：未来 PostgreSQL 19 的路径可能是 `/var/lib/postgresql/19/docker`，父目录挂载不用改 compose
3. **pg_upgrade 需要**：升级时要在父目录下同时看到旧版本和新版本的数据目录

---

## 五、怎么验证数据真的落到了宿主机

### 5.1 看数据库自己认为的数据目录

```bash
docker compose exec db psql -U aichat -d aichat -c "SHOW data_directory;"
```

期望：

```
/var/lib/postgresql/18/docker
```

### 5.2 看宿主机目录有没有东西

```bash
ls -la /root/AIChat/pgdata
```

修复后应该能看到 `18/` 目录、`PG_VERSION` 等文件；修复前是空的。

### 5.3 看容器挂载

```bash
docker inspect aichat-db-1 --format '{{json .Mounts}}'
```

确认 `Source` 是宿主机的 `/root/AIChat/pgdata`，`Destination` 是 `/var/lib/postgresql`。

---

## 六、如果已经有数据了怎么办

本次是新服务器，还没有数据，直接改挂载即可。如果是一个已经在跑的旧实例：

1. **先备份**（在容器里做逻辑备份）：

```bash
docker compose exec -T db pg_dump -U aichat -d aichat > backup.sql
```

2. 停止服务、调整挂载
3. 让 Postgres 在新数据目录初始化
4. 把 `backup.sql` 导回去：

```bash
cat backup.sql | docker compose exec -T db psql -U aichat -d aichat
```

**不要**直接把旧容器里的 `/var/lib/postgresql/data` 拷到新路径——18 的目录结构和权限可能不兼容，逻辑备份（pg_dump）最稳。

---

## 七、备份策略（比挂载更根本）

bind mount 只解决"容器删了数据还在"，解决不了"磁盘坏了 / 误删 / 被勒索"。

建议定期逻辑备份：

```bash
# 每天 3 点备份，保留 7 天
0 3 * * * docker compose -f /root/AIChat/docker-compose.yml exec -T db pg_dump -U aichat -d aichat | gzip > /root/backup/aichat-$(date +\%F).sql.gz
```

备份要验证能恢复，否则等于没有备份。

---

## 八、一句话总结

**镜像声明的 `VOLUME` 和 `PGDATA` 决定了数据实际写在哪；挂载点必须和它们对齐。**
PG18 的路径变了，旧 compose 不会报错，只会让 `./pgdata` 静默变空。升级基础镜像时，先 `docker image inspect` 看 Env 和 Volumes，再决定挂载路径。
