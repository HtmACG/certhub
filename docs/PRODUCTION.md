# 上线部署与运维手册（一次性交付版）

> 本系统按「部署一次、长期自转」设计：证书由流水线的定时任务**自动续期**，
> 部署目标也是自动的，日常没有人需要登进来点按钮。
> 因此上线前必须把下面 6 件事做对，否则半年后一定出问题：**HTTPS、数据备份、定时任务、通知渠道、磁盘、健康检查**。

---

## 一、部署形态

### 1. 源码部署（推荐给单机 / 内网）

```bash
# 依赖
python 3.11+
cd backend && pip install -r requirements.txt

# 前端（已构建好放在 frontend/dist，改了源码才需要重新构建）
cd frontend && node node_modules/vite/bin/vite.js build

# 启动
cd backend && ../.venv/Scripts/python.exe run.py     # Windows
cd backend && ../.venv/bin/python run.py             # Linux
```

生产建议用 systemd 托管（崩溃自动拉起）：

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

### 2. Docker

```bash
docker compose up -d
# 数据卷必须映射出来：/app/backend/data
```

---

## 二、必配环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `CERTD_DATA_DIR` | 建议 | 数据目录（数据库 + 证书 + 签名密钥）。**必须挂持久卷** |
| `CERTD_SECRET_KEY` | 建议 | JWT 签名密钥；不填会自动生成到 `data/secret.key`。**不要删这个文件**，删了所有人登录态失效、加密凭据解不开 |
| `CERTD_ADMIN_PASSWORD` | 首次 | 只在第一次初始化时建管理员用；默认 `123456`，**上线后立刻登录改掉** |
| `CERTD_TZ` | 建议 | 默认 `Asia/Shanghai`，影响定时任务与到期提醒时间 |
| `CERTD_CORS_ORIGINS` | 建议 | 默认 `*`；上线改成实际访问域名，例如 `https://certs.example.com` |
| `CERTD_DB_URL` | 可选 | 默认 SQLite；换 PostgreSQL/MySQL 时填 SQLAlchemy URL |
| `CERTD_PIPELINE_CONCURRENCY` | 可选 | 同时跑的流水线数，默认 3；机器小别调大 |
| `CERTD_DNS_WAIT` | 可选 | DNS 传播检查的基础等待（秒），默认 10 |

启动日志里会打印数据目录、数据库、时区、并发和**剩余磁盘**；如果还是默认密码或 CORS 通配，会打 `WARNING`。

---

## 三、反向代理 + HTTPS（最容易出问题的一步）

Nginx 示例（**SSE 必须关缓冲**，否则执行日志不实时、页面像卡住）：

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

> 面板本身用 HTTP 时，「复制链接 / Webhook」也要跟着改；内网部署建议至少加一层 Basic Auth 或限制来源 IP。

---

## 四、首次上线步骤（照着做一遍）

1. 登录 → **账号与安全 → 修改密码**（别留 123456；新密码要求 ≥8 位、非纯数字、不与用户名相同）；
   管理员建议在同一页开启两步验证（扫码绑定）。
2. **授权管理**：把要用的云厂商 / DNS / 面板 / SSH 授权逐条加上，点「测试」确认通。
3. **通知渠道**：加一个（邮件 / 企微 / 钉钉 / Webhook），设为默认。
4. **证书流水线**：新建一条「申请 + 部署 + 通知」，先不要开定时，点「运行」跑一遍，看日志到成功。
5. 验证部署结果（去目标站点 / CDN 看证书是不是新的）。
6. 打开**定时任务**抽屉，设成每天一次（03:00 之类），保存。
7. **站点监控**加上关键站点的 URL，到期前会自动告警。
8. **系统设置**：站点信息（名称 / 副标题 / Logo）、安全（登录失败上限、强制两步验证）、网络代理（访问 Google / ZeroSSL 需要）。

---

## 五、备份与恢复（**上线必须配，否则硬盘一坏全没了**）

系统自带备份脚本，备份内容：SQLite 数据库（在线一致备份）、`certs/` 证书与私钥、`secret.key`。

```bash
# 手动备份
cd backend && python tools/backup.py --dir /data/backup/certhub --keep 30

# 恢复（会先把当前库另存一份，再覆盖）
python tools/backup.py --restore /data/backup/certhub/certhub-20260101-030000.zip
```

**每天凌晨自动备份（Linux cron）**：

```cron
0 3 * * * cd /opt/certhub/backend && /opt/certhub/.venv/bin/python tools/backup.py --dir /data/backup/certhub --keep 30 >> /var/log/certhub-backup.log 2>&1
```

**Windows 计划任务**：操作 → 启动程序 → `E:\certdsystem\.venv\Scripts\python.exe`，参数 `tools\backup.py --dir D:\backup\certhub --keep 30`，起始于 `E:\certdsystem\certd-lite\backend`。

> 上线后第 1 周做一次**恢复演练**：把备份解到另一台机器，起服务，确认能登录、能看到证书、能跑一条流水线。
> 只验证「备份文件存在」等于没验证。

---

## 六、监控与告警

- **健康检查**：`GET /api/health`，正常返回 `code=200`；数据库不可用 / 磁盘 < 200MB / 调度器没起来时返回 **503** 并在 `data` 里给出原因。
  用 Uptime Kuma / 云监控 / 宝塔告警盯这个地址即可。
- **业务告警**：证书到期前 N 天（系统设置 → 到期提醒，默认 15 天）会通过默认通知渠道推送；站点监控异常也会推。
- **建议额外看的**：`data/` 目录占用、备份目录占用、`backend.log` 里的 ERROR。

---

## 七、容量与清理

| 项目 | 默认 | 怎么改 |
|---|---|---|
| 每个流水线的执行历史 | 保留 20 条 | 流水线「定时任务」抽屉里的「保留条数」 |
| 备份份数 | 14 份 | `tools/backup.py --keep N` |
| 证书文件 | 每次签发一份，不自动删 | 证书库删除后文件仍在 `data/certs`，可按需清理旧目录 |

---

## 八、安全加固

> 完整审计结论、已修项与**残余风险清单**见 `docs/SECURITY.md`，这里只列操作要点。

- 默认管理员密码必须改（系统启动日志会 WARN）；公网必须上 HTTPS。
- 密码规则：**≥8 位、不能是纯数字、不能与用户名相同**；注册、建用户、改密、管理员重置四处统一校验。
  改密成功后会被强制要求重新登录（旧 token 在过期前仍然有效，换身份才安全）。
- **忘记密码**：系统没有邮件找回（不带 SMTP）。管理员可在 **用户管理 → 重置密码** 给任何账号重置，
  支持一键生成 16 位随机强密码；重置会清除该账号的失败锁定。
- 系统设置 → 安全：登录失败上限（默认 5 次 / 锁 10 分钟，**两步验证码输错也计入**）、**强制两步验证**（重要系统建议开）。
- **自助注册默认关闭**：单团队自用没必要开；要多人协作时在「系统设置 → 站点信息」里显式打开。
- API 文档（`/api/docs`）默认关闭，只在本机调试时用 `CERTD_DOCS=1` 打开。
- 已内置安全响应头（nosniff / SAMEORIGIN / no-referrer / Permissions-Policy），HTTPS 请求额外发 HSTS；
  **未启用 CSP**（前端有内联样式与 data: 图片，需单独联调）。
- 两步验证支持**扫码绑定**（账号与安全 → 两步验证），也支持手动输入密钥；换手机时用同一张二维码再加一台设备。
- 凭据（AK/SK、面板 Token、证书私钥）在接口层是**明文**返回、数据库里加密存储（`security.encrypt_json`）；这是产品设计（便于排障），因此**数据库和备份文件本身要当机密文件对待**。
- 用最小权限的云厂商授权：只给 DNS 解析 / CDN 证书相关权限，不要给主账号 AK。
- 反向代理层建议限制后台访问来源 IP。

---

## 九、常见故障速查

| 现象 | 原因 | 处理 |
|---|---|---|
| 证书申请失败 `incorrectResponse / Did not find challenge value` | DNS 记录还没生效就通知了 CA | 任务高级设置里把「DNS 传播等待」调到 300~600，或调大「传播校验重试次数」 |
| `Unknown external account binding (EAB) key` | Google EAB 过期（7 天） | 授权管理里更新 EAB 凭据后重跑 |
| 访问 Google / ZeroSSL 超时 | 国内网络 | 系统设置 → 网络代理（httpProxy / httpsProxy，或填反代域名） |
| 页面显示旧内容 | 浏览器缓存旧 bundle | Ctrl+F5；确认 `frontend/dist` 是构建后的产物 |
| 执行日志不实时、一直转圈 | 反代开了 buffering | Nginx 加 `proxy_buffering off` |
| 定时任务不触发 | 调度器没起来 / 时区不对 | 看 `/api/health` 的 `scheduler`；确认 `CERTD_TZ` |
| 数据目录暴涨 | 历史记录 + 证书文件累积 | 调小保留条数、清理旧证书目录、检查备份目录 |
| 登录态全部失效 | `data/secret.key` 被删或换机没带过去 | 恢复备份里的 `secret.key` |
| 管理员密码忘了 | 没有邮件找回 | 找另一台机器用同一份代码生成哈希：`python -c "import sys;sys.path.insert(0,'backend');from app.security import hash_password;print(hash_password('新密码'))"`，把结果写进 `user` 表 `password` 字段（同时把 `login_fail_count=0`、`locked_until=NULL`） |
| 登录提示「当前未开放注册」 | 自助注册默认关闭 | 需要多人协作时在「系统设置 → 站点信息」打开，或由管理员在用户管理里建号 |

---

## 十、本次交付的边界（明确不做的事）

为避免上线后「以为有、其实没有」，这些**不在**本次交付范围：

1. **第三方 OAuth 扫码登录**（微信 / GitHub / Gitee）与 **Passkey**：需要公网回调域名和第三方应用审核，不属于自建证书系统核心，本版本不做。
   （两步验证的**扫码绑定**是有的，见个人中心。）
2. **支付 / 套餐 / 钱包 / 邀请返佣**：商业版能力，已移除。
3. **插件市场 / 插件热插拔**：插件清单由后端 `plugins.py` 元数据驱动，新增插件需要改代码重新部署。
4. **多租户 / 项目空间 / 角色细分**：当前是「管理员 + 普通用户」两级，数据按用户隔离。
5. **CNAME 代理验证 / DNS 持久验证 / 多 DNS 提供商**：需要额外的托管服务或 Google 特殊能力，当前只支持 **DNS-01（直接 DNS 验证）** 与 **HTTP-01 文件验证**。
   如果域名解析商不在支持列表里，做法是：把这个域名的 NS 指到支持的服务商（阿里云 / 腾讯云 / Cloudflare…），再走 DNS 验证。

维护方式：本系统按一次性交付，**上线后不再迭代**。上面第十节列的就是边界，需求超出边界时按新项目评估。
