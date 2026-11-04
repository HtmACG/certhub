---
title: 安装部署
description: CertHub 的三种安装方式（一键脚本、手动源码、Docker），环境变量、反向代理与 systemd 托管。
---

# 安装部署

CertHub 是单进程服务：后端 FastAPI 负责接口与静态托管，前端构建产物由后端直接发出。安装完只有一个端口（默认 `8000`）。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| Python | 3.11 及以上（3.12 / 3.13 均可） |
| Node.js | 18 及以上，**只在构建前端时需要**（服务器可以直接用构建好的产物） |
| 数据库 | 默认 SQLite，可切 PostgreSQL / MySQL |
| 端口 | 默认 8000，可用 `CERTD_PORT` 改 |
| 系统 | Linux / Windows / macOS 均可 |

## 方式一：一键脚本（推荐）

脚本会依次做四件事：建虚拟环境 → 装后端依赖 → 装前端依赖并构建 → 启动服务。

```bash
# Linux / macOS
cd certd-lite
bash start.sh
```

```bat
:: Windows：双击 start.bat，或在 CMD 里执行
start.bat
```

构建产物会被复制到 `frontend/dist`，后端从那里托管页面。启动后访问 <http://127.0.0.1:8000>。

::: tip 默认账号
`admin` / `123456`。**首次登录请立刻改密码**，新密码要求 ≥8 位、不能是纯数字、不能与用户名相同。
:::

## 方式二：手动安装

```bash
# 1. 后端
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip.exe

# 2. 前端（改了前端源码才需要）
cd ../webui
npm install
npm run deploy        # 构建并把 dist 复制到 ../frontend/dist

# 3. 启动
cd ../backend
.venv/bin/python run.py                          # Windows: .venv\Scripts\python.exe run.py
```

开发模式前端单独跑（热更新）：

```bash
cd webui && npm run dev      # http://localhost:5174，/api 自动代理到 127.0.0.1:8000
```

## 方式三：Docker

仓库根目录的 `Dockerfile` 是「一条命令从源码构建」，需要服务器能装 npm 依赖：

```bash
docker compose up -d
# 数据卷必须映射出来：/app/backend/data
```

内网或国内机器建议用 `deploy/` 那套：本机构建好 `webui/dist`，服务器只装 Python，构建快、依赖少。详见仓库的 `docs/DEPLOY-DOCKER.md`。

::: warning 三个必须做的事
1. **固定 `CERTD_SECRET_KEY` 并备份**：它同时用于签 JWT 和加密库里的凭据，换了等于所有人重新登录、旧凭据全部解不开。
2. **备份 `data/`**：`certd.db`、`certs/`、`secret.key` 都在里面。
3. **改掉默认管理员密码**。
:::

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `CERTD_PORT` | `8000` | 监听端口 |
| `CERTD_DATA_DIR` | `backend/data` | 数据目录（数据库、证书、密钥），**必须挂持久卷** |
| `CERTD_SECRET_KEY` | 自动生成到 `data/secret.key` | JWT 签名 + 凭据加密密钥，生产务必写死并备份 |
| `CERTD_DB_URL` | `sqlite:///data/certd.db` | 数据库连接串，可换 PostgreSQL / MySQL |
| `CERTD_ADMIN_USERNAME` / `CERTD_ADMIN_PASSWORD` | `admin` / `123456` | 只在首次初始化建库时生效 |
| `CERTD_TZ` | `Asia/Shanghai` | 影响定时任务与到期提醒的时间 |
| `CERTD_CORS_ORIGINS` | `*` | 上线建议改成实际访问域名 |
| `CERTD_PIPELINE_CONCURRENCY` | `3` | 同时执行的流水线数，机器小别调大 |
| `CERTD_DNS_WAIT` | `10` | DNS 传播检查的基础等待秒数 |
| `CERTD_DOCS` | 关闭 | 设为 `1` 才暴露 `/api/docs`，只在本机调试时用 |

启动日志会打印数据目录、数据库、时区、并发与剩余磁盘；如果还是默认密码或 CORS 通配，会打 `WARNING`。

## 反向代理 + HTTPS

管理后台不建议直接暴露公网。用 Nginx 反代时，**SSE 必须关缓冲**，否则执行日志不实时、页面像卡住：

```nginx
server {
    listen 443 ssl http2;
    server_name certs.example.com;

    ssl_certificate     /etc/nginx/ssl/certs.example.com.crt;
    ssl_certificate_key /etc/nginx/ssl/certs.example.com.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 日志流（SSE）
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }

    client_max_body_size 20m;   # 导入证书 / 上传 Logo
}
```

## 用 systemd 托管（Linux）

```ini
# /etc/systemd/system/certhub.service
[Unit]
Description=CertHub
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/certhub/backend
Environment=CERTD_DATA_DIR=/opt/certhub-data
Environment=CERTD_TZ=Asia/Shanghai
Environment=CERTD_CORS_ORIGINS=https://certs.example.com
ExecStart=/opt/certhub/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now certhub
curl -s http://127.0.0.1:8000/api/health
```

## 首次上线检查清单

1. 登录 → **账号安全 → 修改密码**，建议同时开启两步验证。
2. **授权管理**：把要用的云厂商 / DNS / 面板 / SSH 授权逐条加上，点「测试」确认通。
3. **通知渠道**：加一个（邮件 / 企微 / 钉钉 / Webhook），设为默认。
4. **证书流水线**：新建一条「申请 + 部署 + 通知」，先不开定时，手动跑一遍到成功。
5. 去目标站点 / CDN 确认证书确实换新了。
6. 打开**定时任务**，设成每天一次（03:00 之类）后保存。
7. **站点监控**加上关键站点 URL。
8. **系统设置**：站点信息（名称 / 副标题 / Logo）、安全（登录失败上限、强制两步验证）、网络代理（访问 Google / ZeroSSL 需要）。

## 升级

```bash
# 源码部署
git pull
cd webui && npm install && npm run deploy
cd ../backend && .venv/bin/pip install -r requirements.txt
sudo systemctl restart certhub
```

```bash
# Docker
cd /opt/certhub && sudo docker compose up -d --build
```

数据目录是挂载的，重建容器不会丢数据。**升级前先备份**，见 [备份与升级](./ops)。
