# Docker 生产部署（单机 80 端口）

对应实际已部署的机器：`10.10.12.140`（Ubuntu 26.04 + Docker 29，配置见 `deploy/`）。

## 一、准备

1. 先在本机构建前端（服务器上不装 Node）。**新前端在 `webui/`（React + Vite）**：

   ```bash
   cd webui && npm run build          # 产物在 webui/dist
   ```
   上传到服务器时把 `webui/dist` 改名成 `frontend-dist`（服务器固定用这个目录名）。

2. 把下面这些放到服务器同一个目录（例如 `/opt/certhub`）：

   ```
   /opt/certhub/
   ├── backend/                # 后端源码
   ├── frontend-dist/          # 就是本机 webui/dist
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
# 本机：重新构建前端（webui/dist）→ 重新打包 → 上传到 /opt/certhub → 服务器上：
cd webui && npm run build
# 上传时：backend/ → /opt/certhub/backend/，webui/dist → /opt/certhub/frontend-dist/
cd /opt/certhub && sudo docker compose up -d --build
sudo docker builder prune -af          # 顺手清构建缓存（磁盘紧张时很有用）
```

数据目录是挂载的，重建容器不会丢数据。

## 六、与仓库根目录 Dockerfile 的区别

根目录的 `Dockerfile` 是「一条命令从源码构建」（有 `node:20-alpine` 阶段，需要服务器能装 npm 依赖）；
`deploy/` 这套是**用本地构建好的 dist**，服务器只需 python 与 pip，构建快、依赖少，适合内网/国内机器。

## 七、Docker Hub 拉不动时的兜底（实测）

`docker compose up -d --build` 如果卡在 `python:3.12-slim` 的层下载
（日志里 `Pulling fs layer` 长时间停在几 MB），说明基础镜像拉不下来。
这时可以直接拿**服务器上已有的 certhub 镜像**当基础，跳过拉取：

```bash
cd /opt/certhub

cat > Dockerfile.localbase <<'EOF'
FROM certhub:1.0.0
WORKDIR /app
COPY backend/ backend/
COPY frontend-dist/ frontend/dist/
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple qrcode
WORKDIR /app/backend
EXPOSE 8000
VOLUME ["/app/backend/data"]
CMD ["python", "run.py"]
EOF

sudo docker build -f Dockerfile.localbase -t certhub:1.0.0-new .
sudo docker run --rm --entrypoint python certhub:1.0.0-new -c "import qrcode; print('qrcode ok')"
sudo docker tag certhub:1.0.0-new certhub:1.0.0
sudo docker compose up -d --force-recreate
```

- 前提是旧镜像还在（`docker images | grep certhub`）；镜像也被删了才需要按第四节先拉
  `docker.m.daocloud.io/library/python:3.12-slim` 再 tag。
- 新依赖（本次是 `qrcode`）要在 `RUN pip install` 里补上，否则启动时 import 失败。
- 2026-11-03 的这次升级就是走这条兜底路径（Docker Hub 拉取 15 分钟只下了 1MB）。

