---
title: 故障排查
description: CertHub 常见故障速查：DNS 验证、证书不生效、日志不实时、定时不触发、登录问题与数据目录异常。
---

# 故障排查

## 先看这三个地方

| 位置 | 能看出什么 |
| --- | --- |
| **执行历史 → 查看日志** | 失败在哪个任务、哪一步、对端返回了什么 |
| `backend.log` / 容器日志 | 启动异常、数据库、调度器、未处理错误 |
| `GET /api/health` | 数据库、磁盘、调度器是否正常（异常返回 503） |

业务性异常（`PipelineError` / `DeployError` / `AcmeError` / `NotifyError` / `DnsError` 等）**不会打堆栈**，日志里只有一行中文结论；云厂商错误压成 `[Code] Message` 一行。

## 证书申请

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `Did not find challenge value` / `incorrectResponse` | DNS 记录还没生效就通知了 CA | 任务里把「DNS 传播等待」调到 300~600 秒，或加大「传播校验重试次数」 |
| DNS 验证一直等待生效 | AK 没有该域名的解析权限，或域名不在这个账号下 | 用最小权限子账号，确认域名的权威 NS 指向这家服务商 |
| 提示「未到续期时间」 | 剩余天数大于 `renewDays`（默认 20） | 调小「提前续期天数」，或打开「强制续期」 |
| `Unknown external account binding (EAB) key` | Google EAB 过期（7 天） | 授权管理里更新 EAB 凭据后重跑 |
| `External account binding has already been used` | 一次性 EAB 被复用（FreeSSL / LiteSSL） | 轮换一份新 EAB |
| `The bound account does not exist` | EAB 与所选 CA 不匹配 | 确认 EAB 授权的「所属 CA」选对，重新取一份 EAB |
| 访问 Google / ZeroSSL 超时、`WinError 10054` | 国内网络 | 系统设置 → 网络设置：填 HTTP 代理，或给 CA 配反向代理域名 |
| 泛域名验证失败 | 用了 HTTP-01 | 泛域名只能用 DNS-01 |
| CAA 记录导致签发被拒 | 域名有严格 CAA | 把 `trustasia.com`（LiteSSL）/ 对应 CA 的 CAA 身份加进去 |
| 免费证书报额度不足 | 云厂商免费额度用尽 | 换 CA 或走 ACME |

## 部署

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 流水线成功，但站点还是旧证书 | 部署路径不对 / 没重载 / 浏览器缓存 | 证书库里确认证书是新的；检查 `certPath` 与 `reloadCmd`；部分面板需要手动重载 |
| 报「需要「群晖 DSM」类型的授权，当前选的是「宝塔面板」」 | 授权类型与插件不匹配 | 在任务里改选正确类型的授权 |
| 群晖登录失败 | 设备 ID 过期（约 30 天）或未开启「信任设备跳过双重验证」 | 重新点「获取设备 ID」；或在授权里配「验证密钥」由系统自动回退 |
| 权限不足 / 写不进目录 | SSH 账号无写权限 | 换有权限的账号，或给 sudoers 放行重载命令 |
| CDN 已更新但访问还是旧证书 | CDN 生效延迟 | 等几分钟；必要时在云控制台刷新证书绑定 |

## 界面与日志

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 执行日志不实时、一直转圈 | 反向代理开了 buffering | Nginx 加 `proxy_buffering off;` 与 `proxy_read_timeout 3600s;` |
| 页面显示旧内容 | 浏览器缓存了旧 bundle | `Ctrl + F5`；确认 `frontend/dist` 是构建后的产物 |
| 日志里有 `status=running` 的僵尸记录 | 进程被强杀 | 重启服务，启动时会把它们标成 `failed` 并补一句「服务重启，本次执行已中断」 |
| 点「停止」后还在跑一会儿 | 协作式停止，只在任务边界检查标志位 | 正常现象，等当前 HTTP 请求结束 |

## 定时任务

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 到点不触发 | 调度器没起来 / 时区不对 | 看 `/api/health` 的 `scheduler`；确认 `CERTD_TZ=Asia/Shanghai` |
| 改了 cron 但下次运行时间没变 | 服务端会立即重算，前端需刷新 | 刷新页面；仍不对就看系统设置里的时区 |
| 停用后仍显示下次运行时间 | 老数据 | 重新启用再停用一次即可重算 |

## 登录与账号

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 提示「当前未开放注册」 | 自助注册默认关闭 | 系统设置 → 站点信息 打开，或由管理员建号 |
| 账号被锁 | 连续失败 5 次，锁 10 分钟 | 等 10 分钟，或管理员在用户管理里重置密码（会清除锁定） |
| 管理员密码忘了 | 没有邮件找回 | 管理员重置；单账号场景见下方「重置密码」 |
| 登录态全部失效 | `data/secret.key` 被删 / 换机没带过来 | 恢复备份里的 `secret.key` |

### 重置密码（有另一台机器可用时）

```bash
python -c "import sys;sys.path.insert(0,'backend');from app.security import hash_password;print(hash_password('新密码'))"
```

把结果写进 `user` 表的 `password` 字段，同时把 `login_fail_count` 置 0、`locked_until` 置 NULL。

## 数据与磁盘

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 数据目录暴涨 | 历史记录 + 证书文件累积 | 调小执行历史保留条数，清理 `data/certs` 旧目录与旧备份 |
| 启动报磁盘不足 / 健康检查 503 | 剩余空间 < 200MB | 清理磁盘，或迁移数据目录到更大的分区 |
| 换机器后凭据都解不开 | 没带 `secret.key` | 从备份恢复 `secret.key` 后重启 |

## 还是解决不了？

提 issue 时请带上：**执行历史里的完整日志**（含阶段标题）、CertHub 版本、部署方式（源码 / Docker）、涉及的插件类型。日志里的凭据已被脱敏，可以放心贴。
