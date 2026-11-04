---
title: 部署目标
description: CertHub 的 75 个部署插件：主机、面板、集群、云 CDN、对象存储与通用自动化任务。
---

# 部署目标

证书签发后，按流水线配置下发到目标并自动重载服务。内置 **75 个**部署插件，按交付方式分成六类，同类共用一套代码，差别只是默认路径、endpoint 与几个参数。

## 全部插件

<PluginGroups />

## 通用参数

主机 / 中间件类插件的字段基本一致：

| 字段 | 说明 |
| --- | --- |
| 主机授权 | 选一条 SSH 授权，决定传到哪台机器 |
| 证书路径 / 私钥路径 | 支持变量，例如 <code v-pre>/etc/nginx/ssl/{{cert.domain}}.crt</code> |
| PFX 路径 / 密码 | 需要 IIS、Java 等场景时填，留空则不生成 |
| 重载命令 | 例如 `nginx -s reload`、`systemctl reload httpd`、`docker restart nginx` |

::: tip 路径一定要带变量
同一台机器上放多张证书时，用 <code v-pre>{{cert.domain}}</code> 区分文件名，否则后一次部署会覆盖前一次。
:::

## 各类要点

### 主机 · 中间件

覆盖远程主机（SSH / SFTP）、本机目录、Nginx、Apache、HAProxy、Tomcat、IIS、FTP、执行远程命令、ESXi。

- 证书文件权限默认按 `644` 写入，私钥 `600`；服务账号不是 root 时注意目录属主。
- IIS 走 Windows 远程，需要开启 WinRM 或对应接口。
- 「执行远程主机命令」适合插件没覆盖的服务：传完证书后自己写一条 `systemctl reload xxx`。

### 面板

宝塔、1Panel、群晖 DSM、威联通 QTS、Proxmox VE、Nginx Proxy Manager、OpenWrt / iStoreOS、雷池 WAF、AcePanel、飞牛 NAS。

- 面板类授权要能**长期跑**：两步验证别只留「验证码」字段（30 秒就过期），要留 Base32 密钥由系统现算，或者用群晖的「设备 ID」。
- 宝塔 / 1Panel / NPM 支持**多站点选择**，一次部署可以覆盖同一面板上的多个站点。
- 群晖可以设「默认证书」并自定义证书名称（`asDefault` / `certDesc`），详见 [授权管理](./access)。

### 云 CDN

阿里云 CDN / DCDN / 直播 / 点播 / SLB、腾讯云 CDN / EdgeOne / CLB、火山引擎 CDN / 直播、AWS CloudFront、Fastly、七牛、天翼云、京东云、多吉云、易盾 DCDN、括彩云、我爱云、又拍云、白山云、百度云、华为云、中国移动、金山云、雨云、UCloud 等，共 35 个。

流程都是「上传证书到证书中心 → 绑定到加速域名」，因此需要对应云厂商授权，且账号要有证书与 CDN 的操作权限。

### 对象存储

阿里云 OSS、腾讯云 COS、华为云 OBS、火山引擎 TOS、AWS S3、S3 兼容存储、Cloudflare R2、七牛 Kodo、UCloud US3。

- 填 Endpoint、Access Key、Secret Key、Region，桶名在任务里选。
- 证书默认以 `application/x-pem-file` 写入，路径可自定义（例如 <code v-pre>ssl/{{cert.domain}}/fullchain.pem</code>）。

### 集群

Kubernetes Secret / Ingress、阿里云 ACK、百度云 CCE、腾讯云 TKE。

- K8s 需要 API Server 地址、Token、命名空间，可选集群 CA 证书。
- 部署到 Ingress 时会同时更新 `tls.crt` / `tls.key`，并触发对应 Ingress 生效。

### 通用任务

| 任务 | 用途 |
| --- | --- |
| 推送到自定义接口（Webhook） | 把证书推给自有系统，由对端完成安装；支持鉴权 Token 与附加参数 |
| 证书发送到邮箱 | 把证书作为附件发出，适合人工分发 |
| 在主机执行脚本 | 插件没覆盖的场景，用脚本兜底 |
| 等待 | 在两个任务之间插入固定延时，适配生效较慢的平台 |
| 数据备份 | 把证书归档到指定位置，配合外部备份策略 |

## 部署失败怎么查

1. 看日志里该任务的那一段（hover 任务卡 →「查看该任务日志」）。
2. 目标站点还是旧证书？先确认**证书库里的证书是新的**，再确认路径与重载命令。
3. 部分面板需要手动触发一次重载才生效；CDN 有几分钟的生效延迟。
4. 权限问题最常见：写不进目录、`reload` 没有 sudo 权限、云账号只有读权限。

更多见 [故障排查](./troubleshoot)。
