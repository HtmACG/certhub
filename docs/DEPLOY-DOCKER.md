# Docker 生产部署（单机 80 端口）

对应实际已部署的机器：`10.10.12.140`（Ubuntu 26.04 + Docker 29，配置见 `deploy/`）。

## 一、准备

1. 先在本机构建前端（服务器上不装 Node）：

   ```bash
   cd frontend && node node_modules/vite/bin/vite.js build
   ```

2. 把下面这些放到服务器同一个目录（例如 `/opt/certhub`）：

   ```
   /opt/certhub/
   ├── backend/                # 后端源码
   ├── frontend-dist/          # 就是本机 frontend/dist
   ├── Dockerfile              # 见 deploy/Dockerfile
   └── docker-compose.yml      # 见 deploy/docker-compose.yml（改掉两个 CHANGE_ME）
   ```

## 二、构建与启动

```bash
cd /opt/certhub
sudo docker compose up -d --build      # 首次约 1 分钟（依赖装一次，后面走缓存）
sudo docker compose ps                 # 等到 (healthy)
curl -s http://127.0.0.1/api/health    # {"code":200,...,"db":"ok","scheduler":"running"}
```

浏览器打开 `http://<服务器IP>/`，用 `CERTD_ADMIN_USERNAME` / `CERTD_ADMIN_PASSWORD` 登录
（这两个变量**只在首次初始化建库时**生效，之后改密码走「账号与安全」）。

## 三、必须做的三件事

1. **把 `CERTD_SECRET_KEY` 写死并备份**。它同时用于签 JWT 和加密库里的云厂商凭据，
   换了等于所有人重新登录、且旧凭据全部解不开。
2. **备份 `data/`**：`certd.db` + `certs/` + `secret.key` 都在里面。
   ```bash
   sudo tar czf /backup/certhub-$(date +%F).tar.gz -C /opt/certhub data
   ```
3. **改掉默认管理员密码**（新密码要求 ≥8 位、非纯数字、不与用户名相同）。

## 四、国内网络的两个镜像

- 基础镜像：Docker Hub 直连不通，用 `docker.m.daocloud.io/library/python:3.12-slim`，
  拉下来后 `docker tag docker.m.daocloud.io/library/python:3.12-slim python:3.12-slim`，
  Dockerfile 就能照常用 `FROM python:3.12-slim`。
- pip：Dockerfile 里已经指定清华源 `https://pypi.tuna.tsinghua.edu.cn/simple`。

## 五、更新

```bash
# 本机：重新构建前端 → 重新打包 → 上传到 /opt/certhub → 服务器上：
cd /opt/certhub && sudo docker compose up -d --build
sudo docker builder prune -af          # 顺手清构建缓存（磁盘紧张时很有用）
```

数据目录是挂载的，重建容器不会丢数据。

## 六、与仓库根目录 Dockerfile 的区别

根目录的 `Dockerfile` 是「一条命令从源码构建」（有 `node:20-alpine` 阶段，需要服务器能装 npm 依赖）；
`deploy/` 这套是**用本地构建好的 dist**，服务器只需 python 与 pip，构建快、依赖少，适合内网/国内机器。
