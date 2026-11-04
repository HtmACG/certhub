---
title: 新增插件
description: 二次开发指南：新增部署插件、DNS 服务商、通知渠道与 CA，以及必须遵守的验收标准。
---

# 新增插件

CertHub 是**元数据驱动**的：插件清单由后端注册表决定，前端表单、授权下拉、任务选择器全部自动生成。所以加功能不需要动前端。

## 新增部署插件

### 第 1 步：写 handler

在 `backend/app/services/deploy.py`（或对应的 `deploy_*.py`）里实现：

```python
def deploy_to_xxx(ctx: CertContext, config: dict, log: Callable) -> None:
    log("开始部署 ...")
    # ctx.crt / ctx.key / ctx.pfx / ctx.domain / ctx.domains
    # 路径里的变量用 ctx.render("...{{cert.domain}}...")
```

::: tip 两个约定
1. **`config` 里已经有授权内容**。任务表单只存 `accessId`，引擎执行前会把授权里的地址、账号、密钥合并进 `config`（授权为底稿、任务入参覆盖），所以直接读 `config["url"]` / `config["username"]` 即可，不要再自己去查授权表。
2. **内网面板统一用 `_panel_request()` 发请求**。它会关掉 `trust_env` —— 宿主机上若配了 `HTTP_PROXY`，httpx 默认会把 `192.168.x.x` 的内网请求也丢给代理，表现成「连不上」却看不出原因；同时把连接类异常翻成中文。公网云厂商接口不要用它，那些场景反而需要走代理。
:::

### 第 2 步：注册 handler

```python
DEPLOY_HANDLERS["DeployToXxx"] = deploy_to_xxx
```

### 第 3 步：登记元数据

在 `backend/app/plugins.py` 的 `TASK_PLUGINS` 里加一条（名称、描述、`inputs`、`category`、`logo`），前端会自动出现这个插件。

`inputs` 里用 `f("key", "标题", "password")` 这样的工厂函数声明字段：

| 参数 | 作用 |
| --- | --- |
| `component` | `input` / `password` / `select` / `switch` / `number` / `textarea` / `access` / `notification` |
| `options` | select 的选项 |
| `showWhen` | 条件显示（例如只有开启两步验证才显示密钥字段） |
| `accessTypes` | 授权字段只接受哪些精确类型 |
| `action` | 字段下方的动作按钮（例如群晖「获取设备 ID」） |

::: warning 三个必须做的检查
1. **`accessId` 字段必须带 `accessTypes`**：只按 `accessCategory` 过滤会让「部署到群晖」的下拉里出现宝塔授权。注册表见 `_DEPLOY_ACCESS_TYPES`。
2. **`inputs` 必须覆盖 handler 真正读的配置**：把 handler 里所有 `config.get("xxx")` 的键抄出来对齐。群晖就踩过这个坑 —— handler 早就读 `asDefault`，但表单里没有这个开关，用户只能吃默认值。
3. **字段标题要写清楚去哪找**，例如「两步验证密钥：DSM → 个人设置 → 双重验证」。
:::

### 第 4 步：加 logo（可选）

厂商图标要**本地化**，不要让前端直连 CDN（内网、离线环境下会变成空白块）。图标文件放在 `frontend/public/logos/`，元数据里给相对路径 `logoFile`。

## 新增 DNS 服务商

1. 继承 `BaseDnsProvider`，实现 `add_txt` / `remove_txt`。
2. 注册到 `dns.PROVIDERS`。
3. `plugins.py` 的 `ACCESS_TYPES` 增加授权类型，`DNS_PROVIDERS` 增加条目。
4. 如果该服务商能做 DNS-01 验证，把它的 key 加进 `_DNS_CAPABLE`，否则证书任务的「DNS 授权」下拉里不会出现它。

## 新增通知渠道

1. `notify.py` 实现 `send_xxx(config, title, content)`。
2. 注册到 `SENDERS`。
3. `plugins.py` 的 `NOTIFY_TYPES` 增加配置项。
4. **必须做业务码校验**：很多国内渠道 token 错了也返回 HTTP 200，只在响应体里给 `errcode` / `code`。只判状态码会把「没发出去」记成成功。错误信息里只保留主机名，别把带 token 的完整 URL 写进日志。

## 新增 CA

CA 的名称、目录地址、是否要 EAB **只有 `plugins.ACME_PROVIDERS` 一份**。引擎统一走 `_ca_name()` / `_ca_directory()` / `_ca_needs_eab()`，不要在引擎里手抄字典 —— 以前抄过，新增 FreeSSL 时漏改，表现是「选了 FreeSSL 却报『自定义 ACME 需要填写 ACME 目录地址』」。

## 验收标准

改完必须过这几关，缺一条都可能上线后翻车：

1. `python tests/smoke.py` 全绿（含插件一致性断言）。
2. 前端能选到这个插件，表单字段齐全、必填项有校验。
3. 授权类型不匹配时给出中文结论，而不是让用户对着数字 ID 猜。
4. 错误路径有中文文案：业务异常只打一行，不甩堆栈，云厂商错误压成 `[Code] Message`。
5. 新异常类登记到 `engine._EXPECTED_NAMES`，否则日志里会出现堆栈。
6. 涉及凭据的字段，保存前 trim，留空不覆盖旧值。

## 相关约定

项目根目录的 `AGENTS.md` 是硬性约定（凭据明文查看、元数据驱动、插件覆盖率、错误文案规范等），改代码前先读一遍。**与代码冲突时以它为准，并回头把代码改对。**
