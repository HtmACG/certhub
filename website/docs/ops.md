---
title: 备份与升级
description: CertHub 的数据目录、在线备份与恢复、定时备份、升级与迁移机器的注意事项。
---

# 备份与升级

系统按「部署一次、长期自转」设计：证书由定时任务自动续期，日常没有人需要登进来点按钮。因此**备份是唯一不能省的事** —— 硬盘一坏，私钥就没了。

## 数据目录

默认 `backend/data`（可用 `CERTD_DATA_DIR` 改）：

```text
data/
├── certd.db          # SQLite 数据库（流水线、授权、证书元数据、历史）
├── certs/            # 每张证书的文件（按用户分目录）
├── secret.key        # JWT 签名 + 凭据加密密钥（务必一起备份）
└── backups/          # backup.py 的默认输出目录
```

::: danger secret.key 不能丢
`secret.key` 同时用于签 JWT 和加密库里的凭据。丢了等于：所有人登录态失效、**库里的云厂商凭据全部解不开**。换机器迁移时一定要带上它。
:::

## 在线备份

自带脚本会做**在线一致备份**（SQLite 在线备份接口，不是直接拷贝文件），内容包含数据库、`certs/` 与 `secret.key`：

```bash
cd backend
python tools/backup.py --dir /data/backup/certhub --keep 30
```

| 参数 | 说明 |
| --- | --- |
| `--dir` | 备份输出目录，默认 `data/backups` |
| `--keep` | 保留份数，默认 14 |
| `--restore <zip>` | 从备份恢复 |
| `--no-secret` | 备份时不包含 `secret.key`（只想备份数据时用） |

## 恢复

```bash
cd backend
python tools/backup.py --restore /data/backup/certhub/certhub-20260101-030000.zip
```

恢复会**先把当前库另存一份**再覆盖，操作失误还能退回来。恢复完成后重启服务。

::: tip 恢复演练
上线后第 1 周做一次：把备份解到另一台机器，起服务，确认能登录、能看到证书、能跑一条流水线。**只验证「备份文件存在」等于没验证。**
:::

## 定时备份

Linux（cron）：

```text
0 3 * * * cd /opt/certhub/backend && /opt/certhub/.venv/bin/python tools/backup.py --dir /data/backup/certhub --keep 30 >> /var/log/certhub-backup.log 2>&1
```

Windows（计划任务）：操作 → 启动程序 →

```text
程序：   D:\certdsystem\.venv\Scripts\python.exe
参数：   tools\backup.py --dir D:\backup\certhub --keep 30
起始于： D:\certdsystem\certd-lite\backend
```

容器部署的话，直接备份挂载出来的数据卷目录即可：

```bash
sudo tar czf /backup/certhub-$(date +%F).tar.gz -C /opt/certhub data
```

## 升级

```bash
# 源码部署
git pull
cd webui && npm install && npm run deploy      # 前端产物复制到 frontend/dist
cd ../backend && .venv/bin/pip install -r requirements.txt
sudo systemctl restart certhub
```

```bash
# Docker
cd /opt/certhub && sudo docker compose up -d --build
```

升级前先跑一次备份。数据目录是挂载的，重建容器不会丢数据；但**依赖变更**（例如新增了 Python 包）必须重新构建镜像，否则启动时 import 失败。

### 回滚

- 前端：`webui/scripts/deploy.mjs` 会把旧产物备份成 `frontend/dist.bak-<时间戳>`，改名换回来即可。
- 后端：`git checkout <上一个版本>` 后重装依赖、重启。
- 数据：用升级前的备份 `--restore`。

## 迁移机器

1. 新机器装好依赖，**先不要启动**。
2. 把旧机器的 `data/` 整个拷过来（含 `secret.key`）。
3. 启动，用原账号登录 —— 凭据能解开、流水线能跑，说明迁移成功。

## 容量与清理

| 项目 | 默认 | 怎么改 |
| --- | --- | --- |
| 每条流水线的执行历史 | 保留 20 条 | 流水线「定时任务」抽屉里的「保留条数」 |
| 备份份数 | 14 份 | `--keep N` |
| 证书文件 | 每次签发一份，不自动删 | 证书库删除后文件仍在 `data/certs`，可按需清理旧目录 |

启动日志会打印数据目录、数据库、时区、并发与**剩余磁盘**，日常盯这一行就够。
