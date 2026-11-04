---
title: 证书签发
description: CertHub 的 12 种签发来源、ACME 流程、DNS-01 / HTTP-01 验证方式选择、EAB、云厂商免费证书与证书导出。
---

# 证书签发

CertHub 内置自研 ACME v2 客户端，同时支持云厂商免费证书、商业 CA、本地自签与自有证书导入。

## 签发来源

| 来源 | 类型 | 有效期 | 验证方式 | 说明 |
| --- | --- | --- | --- | --- |
| Let's Encrypt | ACME CA | 90 天 | DNS-01 / HTTP-01 | 公益 CA，支持泛域名 |
| Google Trust Services | ACME CA | 90 天 | DNS-01 / HTTP-01 | 必须先建 **EAB 凭据**（7 天失效） |
| ZeroSSL | ACME CA | 90 天 | DNS-01 / HTTP-01 | 首次使用自动换取 EAB |
| FreeSSL / LiteSSL | ACME CA | 90 天 | DNS-01 / HTTP-01 | 亚洲诚信出品，**必须带 EAB**，EAB 只能用一次 |
| Buypass | ACME CA | 180 天 | DNS-01 / HTTP-01 | 挪威 CA，免费 180 天 |
| 自定义 ACME | ACME CA | 以 CA 为准 | 取决于 CA | 填目录地址即可对接私有 CA |
| 阿里云免费证书 | 云厂商 | 3 个月 | DNS 验证 | 单域名 DV，受账号免费额度限制 |
| 腾讯云免费证书 | 云厂商 | 3 个月 | DNS 验证 | 单域名 DV，受账号免费额度限制 |
| 火山引擎免费证书 | 云厂商 | 以控制台为准 | DNS 验证 | `QuickApplyCertificate`，单域名 DV |
| TrustAsia 亚洲诚信 | 商业 CA | 按产品 | DNS / CNAME / 文件 | 支持 DV / OV / EV |
| 自签证书 | 本地 | 默认 365 天 | 无需验证 | 测试 / 内网用 |
| 上传自有证书 | 导入 | 以证书为准 | 无需验证 | 只入库，之后同样可部署与监控 |

## 申请任务的字段

在阶段里添加 **证书申请（CertApply）** 任务，核心字段：

| 字段 | 说明 |
| --- | --- |
| 证书域名 | 可填多个；泛域名写 `*.example.com`，**同时要加 `example.com`** 才能覆盖主域 |
| 证书颁发机构 | 上面 12 种来源之一 |
| 联系邮箱 | CA 用来发到期提醒，建议填真实邮箱 |
| EAB 凭据 | 仅 Google / FreeSSL-LiteSSL / 自定义 CA 出现，从授权管理里选 |
| 域名验证方式 | DNS 验证（推荐，支持泛域名）/ HTTP 验证 |
| DNS 授权 | DNS 验证时选，必须是支持 DNS 能力的云厂商授权 |
| 密钥类型 | ECC 256（推荐）/ ECC 384 / RSA 2048 / 3072 / 4096 |
| 提前续期天数 | 默认 20 天，没到时间自动跳过签发 |
| 首选证书链 | 默认用 CA 默认链；老设备兼容选 `ISRG Root X1` / `GlobalSign` |
| 证书配置档 | CA 默认 / `tlsserver` / `shortlived` / `classic` |
| 强制续期 | 忽略剩余天数，立刻重新签 |
| 证书已存在且未过期就跳过 | 默认开启，避免重复申请触发限流 |

高级设置里还有 DNS 传播等待、传播校验重试次数、申请失败重试次数、跳过本地 DNS 校验等参数，遇到「DNS 没生效就通知 CA」时优先调这几个。

## DNS-01 还是 HTTP-01？

| 方式 | 适用场景 | 要求 |
| --- | --- | --- |
| **DNS-01** | 泛域名、站点不对外暴露、内网服务 | 域名 DNS 托管在已支持的服务商（阿里云 / 腾讯云 / 华为云 / Cloudflare / GoDaddy / NameSilo） |
| **HTTP-01** | 单域名、站点 80 端口可从公网访问 | 能把验证文件对外提供；可写入本机目录或上传到远程主机 |

::: warning 泛域名必须用 DNS-01
HTTP-01 无法验证 `*.example.com`。如果解析商不在支持列表里，做法是把域名的 NS 指到支持的服务商（阿里云 / 腾讯云 / Cloudflare 等），再走 DNS 验证。
:::

## ACME 签发流程

1. 读取 / 创建 ACME 账户（密钥按「用户 + CA」隔离保存，加密存储）。
2. 创建订单 → 逐个域名完成 DNS-01 / HTTP-01 挑战。
3. 轮询授权状态 → 生成密钥与 CSR → finalize → 下载证书链。
4. 保存证书（私钥 AES-GCM 加密入库）+ 写入 `data/certs/{userId}/`。
5. 输出变量 `cert.crt` / `cert.key` / `cert.domain` / `cert.expiresTime` 供部署任务使用。

::: tip 国内网络访问 Google / ZeroSSL 超时
系统设置 → **网络设置** 里可以配 HTTP 代理（`http://`、`https://`、`socks5://`），也可以给 CA 域名配**反向代理域名**。任务里还能单独勾「使用代理访问 CA」或填自定义反代地址。日志会写明实际走了哪条路。
:::

## 关于 EAB

Google 的 EAB key 创建后 **7 天失效**；FreeSSL / LiteSSL 的 EAB **注册成功一次就作废**。所以：

- EAB 统一放在 **授权管理 → 证书签发**，任务里只选不填。
- 首次注册成功后，账户私钥与账户 URL 会同时写回**任务**和**EAB 授权**，其它流水线复用同一份 EAB 时不会重复注册。
- CA 侧的账户被删 / 换了 CA 时，系统会改用 EAB 重新注册一次。
- 报错 `External account binding has already been used` → 这条 EAB 已经用过了，去轮换一份新的。

FreeSSL 的 ACME 目录地址是 `https://acme.litessl.com/acme/v2/directory`（老的 `acme.freessl.cn` 已下线）。该目录 `externalAccountRequired = true`，**必须带 EAB**。域名有严格 CAA 记录时，要把 `trustasia.com` 加进去。

## 云厂商免费证书

阿里云、腾讯云、火山引擎的流程一致：申请 → 取回验证记录并自动写入 DNS → 轮询 → 入库。

- **阿里云**：`CreateCertificateForPackageRequest`（`ProductCode=digicert-free-1-free`，即 3 个月个人测试证书）→ `DescribeCertificateState`。
- **腾讯云**：`ApplyCertificate`（`PackageType=83`）→ `DescribeCertificate` → `DownloadCertificate`。
- **火山引擎**：`QuickApplyCertificate` → `CertificateGetInstance`。

::: warning 免费额度是有限的
免费证书依赖账号的免费额度，额度用尽会直接返回业务错误；而且都是**单域名 DV**，泛域名请走 ACME。
:::

## 自签与导入

- **自签**：不需要域名验证，适合内网、测试环境；默认有效期 365 天。
- **导入**：`POST /api/cert/import` 接收 PEM（证书链 + 私钥），入库前会校验 PEM 头是否齐全、证书与私钥是否成对。导入的证书与流水线签发的证书**完全等价** —— 部署与到期提醒读的都是证书库。

## 证书库与导出

![证书详情](/assets/shots/cert.png)

证书库显示域名、签发机构、生效 / 到期时间、剩余天数，点「查看」可以分标签看证书、证书链与私钥。

导出格式：

```text
GET /api/cert/{id}/download?format=pem|der|pfx|p7b|jks|nginx&type=cert|key&password=xxx
```

- **JKS** 是 Sun 私有格式，无纯 Python 写入实现：服务端先生成 PKCS#12，再调用 JDK `keytool` 转换。没装 JDK 时会提示改用 PFX（Java 同样能加载 PKCS#12）。
- **PFX 兼容性**：Windows Server 2016 / 2008 老系统可在申请任务的「PFX 兼容性」里选 SHA1 + 3DES 的组合。

## 常见报错

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| `Did not find challenge value` / `incorrectResponse` | DNS 记录还没生效就通知了 CA | 把「DNS 传播等待」调到 300~600 秒，或加大传播校验重试次数 |
| `Unknown external account binding (EAB) key` | Google EAB 过期（7 天） | 更新 EAB 授权后重跑 |
| `External account binding has already been used` | 一次性 EAB 被复用 | 轮换 EAB |
| `The bound account does not exist` | EAB 与 CA 对不上 | 重新取一份 EAB，确认「所属 CA」选对 |
| 域名验证失败但 DNS 记录看着是对的 | 权威 NS 不是你以为的那家 | `dig NS example.com` 确认解析商，再换对应授权 |

更多见 [故障排查](./troubleshoot)。
