---
title: 架构与目录
description: CertHub 的技术栈、代码结构、关键模块、主要接口与冒烟测试。
---

# 架构与目录

## 技术栈

| 层 | 选择 |
| --- | --- |
| 后端 | Python 3.11+ / FastAPI / SQLAlchemy 2 / SQLite（可切 PostgreSQL、MySQL） |
| 调度 | APScheduler（定时流水线、站点巡检、到期提醒） |
| 密码学 | cryptography（密钥、CSR、证书解析、PFX / P7B 导出） |
| ACME | 自研 ACME v2 客户端（JWS 签名、订单、挑战、EAB） |
| 远程执行 | paramiko（SSH / SFTP） |
| 前端 | React 19 + Vite 6 + TypeScript + Tailwind CSS v4 + shadcn/ui 风格组件 |
| 状态与路由 | TanStack Query + react-router-dom 7（HashRouter，兼容后端静态托管） |

## 目录结构

```text
certd-lite/
├── backend/
│   ├── app/
│   │   ├── main.py            # 入口、路由注册、静态托管、安全响应头
│   │   ├── config.py          # 配置（环境变量覆盖）
│   │   ├── db.py / models.py  # 数据库与模型
│   │   ├── security.py        # 密码哈希、JWT、AES-GCM 加密
│   │   ├── plugins.py         # ★ 插件元数据注册表（驱动前端表单）
│   │   ├── templates.py       # 流水线模板
│   │   ├── defaults.py        # 系统设置默认值
│   │   ├── permissions.py     # 功能权限键
│   │   ├── deps.py            # 依赖注入、统一响应、审计
│   │   ├── routers/           # auth / pipeline / history / access / cert / monitor ...
│   │   └── services/
│   │       ├── engine.py      # 流水线执行引擎（阶段、任务、变量、失败跳转）
│   │       ├── acme.py        # ACME v2 客户端
│   │       ├── dns.py         # 6 家 DNS 服务商适配
│   │       ├── deploy*.py     # 75 个部署插件（按厂商拆文件）
│   │       ├── notify.py      # 10 种通知渠道
│   │       ├── logbus.py      # 进程内日志发布/订阅（SSE）
│   │       ├── scheduler.py   # 定时调度
│   │       └── net.py         # 代理与反向代理
│   ├── data/                  # SQLite、证书文件、secret.key（运行时生成）
│   ├── tools/                 # backup.py、fetch_access_logos.py
│   └── requirements.txt
├── webui/                     # 前端源码（React）
├── frontend/dist/             # 前端构建产物（后端托管这个目录）
├── website/                   # 本站（VitePress）
├── tests/smoke.py             # 接口冒烟
└── start.bat / start.sh
```

## 元数据驱动

新增签发方式 / 部署目标 / DNS 服务商 / 通知渠道，**只改后端** `plugins.py` 的注册表：

| 注册表 | 作用 |
| --- | --- |
| `TASK_PLUGINS` | 任务插件（申请 / 部署 / 通知）及其表单字段 |
| `ACCESS_TYPES` | 授权类型及其表单字段 |
| `NOTIFY_TYPES` | 通知渠道及其字段 |
| `ACME_PROVIDERS` | CA 名称、目录地址、是否要 EAB |

前端表单、授权下拉、任务选择器、概览页的「支持的证书」全部由这些元数据自动生成，**不要在前端硬编码插件清单**。

字段的敏感属性由 `component == "password"` 声明，不靠字段名猜。字段还可以声明动作按钮（`action`），例如群晖的「获取设备 ID」。

## 主要接口

所有业务接口返回统一信封：`{ code, msg, data }`，鉴权用请求头 `Authorization: <token>`。

| 接口 | 说明 |
| --- | --- |
| `POST /api/auth/login` | 登录，返回 `token` / `refreshToken` |
| `GET /api/auth/captcha` | 图形验证码（失败次数达到阈值后要求） |
| `GET /api/pipeline/plugins` | 任务插件元数据 |
| `GET /api/pipeline/list` | 流水线列表（分页） |
| `GET /api/pipeline/templates` | 模板列表 |
| `POST /api/pipeline/from-template` | 按模板创建 |
| `POST /api/pipeline/{id}/run` | 运行，立即返回 `historyId` |
| `POST /api/pipeline/{id}/stage/run` | 单独运行某个阶段 |
| `POST /api/pipeline/batch` | 批量运行 / 启停 / 改定时 / 删除 |
| `GET /api/history/{id}/stream` | **SSE** 实时日志（历史记录则回放） |
| `POST /api/history/{id}/stop` | 协作式停止 |
| `GET /api/access/options?types=a,b` | 授权下拉（按精确类型过滤） |
| `POST /api/access/{id}/test` | 测试授权连通性 |
| `POST /api/access/synology/device-id` | 换取群晖受信设备令牌 |
| `GET /api/cert/list` | 证书库 |
| `POST /api/cert/import` | 导入自有证书 |
| `GET /api/cert/{id}/download` | 导出 PEM / DER / PFX / P7B / JKS / Nginx |
| `GET /api/monitor/site/list` | 站点监控列表 |
| `GET /api/settings` | 系统设置（site / security / notify / network） |
| `GET /api/health` | 健康检查（异常返回 503） |

## 开放接口

给脚本 / CI 用的独立命名空间，用 API 密钥鉴权（**不用** JWT）：

```bash
curl -H "x-api-key: ck_xxx" -H "x-api-secret: yyy" \
     http://127.0.0.1:8000/api/open/v1/pipelines

curl -X POST -H "x-api-key: ck_xxx" -H "x-api-secret: yyy" \
     http://127.0.0.1:8000/api/open/v1/pipelines/7/run

curl -H "x-api-key: ck_xxx" -H "x-api-secret: yyy" \
     http://127.0.0.1:8000/api/open/v1/certs
```

| 接口 | 说明 |
| --- | --- |
| `GET /api/open/v1/pipelines` | 列出流水线 |
| `POST /api/open/v1/pipelines/{id}/run` | 触发运行 |
| `GET /api/open/v1/certs` | 最近 100 张证书 |
| `GET /api/open/v1/certs/{id}` | 单张证书详情 |

密钥管理（创建 / 删除）走登录态接口 `/api/open/keys`，secret 只在创建时返回一次。

## 前端开发

```bash
cd webui
npm install
npm run dev      # http://localhost:5174，/api 代理到 127.0.0.1:8000
npm run build    # 产物 webui/dist
npm run deploy   # 构建并复制到 ../frontend/dist（后端托管的目录）
```

目录约定：`src/components/ui` 是设计系统，`src/components/layout` 是外壳与导航，`src/features/<域>` 按页面拆分，`src/lib` 放 http、类型与 SSE 日志 hook。

## 冒烟测试

后端启动后跑接口冒烟（覆盖鉴权、分页、插件一致性、加密、限速等断言）：

```bash
python tests/smoke.py --base http://127.0.0.1:8000 --user admin --password 123456
```

新增插件、改了注册表、动了引擎之后都应该跑一遍再提交。
