/**
 * 官网用到的产品数据。
 *
 * 数据来源：backend/app/plugins.py 的注册表（TASK_PLUGINS / ACCESS_TYPES /
 * NOTIFY_TYPES / ACME_PROVIDERS / SUPPORTED_CERTS）。后端加插件后，这里补一条，
 * 首页与「生态集成」页会一起更新 —— 数量不要写死，用数组长度算。
 */

export interface EcoItem {
  name: string
  logo: string
}

export interface EcoGroup {
  title: string
  desc: string
  items: EcoItem[]
}

/** 证书颁发机构（首页品牌卡片） */
export const CAS = [
  { name: "Let's Encrypt", logo: '/logos/issuer/letsencrypt.svg', desc: '免费开放 CA · ACME 发起者' },
  { name: 'Google Trust', logo: '/logos/issuer/google.svg', desc: 'Google 旗下免费 CA' },
  { name: 'ZeroSSL', logo: '/logos/issuer/zerossl.svg', desc: '免费 DV · 支持 ACME' },
  { name: 'Buypass', logo: '/logos/issuer/buypass.svg', desc: '挪威 CA · 免费 180 天' },
  { name: 'LiteSSL', logo: '/logos/issuer/litessl.svg', desc: 'FreeSSL 出品 · ACME v2' },
  { name: '自定义 CA', logo: '/logos/issuer/custom.svg', desc: '对接企业私有 ACME' }
]

/** 首页「生态集成」四组，共 53 项 */
export const ECO_GROUPS: EcoGroup[] = [
  {
    title: '云厂商 · DNS 解析',
    desc: '自动写入 / 清理 DNS-01 验证记录',
    items: [
      { name: '阿里云', logo: '/logos/access/aliyun.svg' },
      { name: '腾讯云 / DNSPod', logo: '/logos/access/tencentcloud.svg' },
      { name: '华为云', logo: '/logos/access/huawei.svg' },
      { name: '火山引擎', logo: '/logos/access/volcengine.svg' },
      { name: 'AWS', logo: '/logos/access/aws.svg' },
      { name: '百度智能云', logo: '/logos/access/baiducloud.svg' },
      { name: 'Cloudflare', logo: '/logos/access/cloudflare.svg' },
      { name: 'GoDaddy', logo: '/logos/access/godaddy.svg' },
      { name: 'NameSilo', logo: '/logos/access/namesilo.svg' },
      { name: 'TrustAsia', logo: '/logos/access/trustasia.svg' },
      { name: '七牛云', logo: '/logos/access/qiniu.svg' }
    ]
  },
  {
    title: 'CDN · 对象存储',
    desc: '证书上传到分发节点或存储桶',
    items: [
      { name: 'Fastly', logo: '/logos/access/fastly.svg' },
      { name: '天翼云', logo: '/logos/access/ctyun.png' },
      { name: '京东云', logo: '/logos/access/jdcloud.png' },
      { name: '多吉云', logo: '/logos/access/dogecloud.png' },
      { name: '易盾 DCDN', logo: '/logos/access/yidun.png' },
      { name: '括彩云 CDN', logo: '/logos/access/kuocaicdn.png' },
      { name: '我爱云 CDN', logo: '/logos/access/woai.png' },
      { name: '白山云', logo: '/logos/access/baishan.png' },
      { name: '又拍云', logo: '/logos/access/upyun.png' },
      { name: 'S3 兼容存储', logo: '/logos/access/s3.svg' },
      { name: 'Cloudflare R2', logo: '/logos/access/r2.svg' }
    ]
  },
  {
    title: '主机 · 面板 · 集群',
    desc: '登录服务器或面板下发证书并重载',
    items: [
      { name: '主机 SSH', logo: '/logos/access/ssh.svg' },
      { name: 'FTP 服务器', logo: '/logos/access/ftp.svg' },
      { name: '宝塔面板', logo: '/logos/access/baota.png' },
      { name: '1Panel', logo: '/logos/access/1panel.svg' },
      { name: '群晖 DSM', logo: '/logos/access/synology.png' },
      { name: '威联通 QTS', logo: '/logos/access/qnap.svg' },
      { name: 'Proxmox VE', logo: '/logos/access/proxmox.svg' },
      { name: 'Nginx Proxy Manager', logo: '/logos/access/npm.svg' },
      { name: 'Kubernetes', logo: '/logos/access/k8s.svg' },
      { name: '雷池 WAF', logo: '/logos/access/safeline.svg' }
    ]
  },
  {
    title: '中间件部署 · 自动化任务',
    desc: '内置任务插件，覆盖长尾场景',
    items: [
      { name: 'Nginx', logo: '/logos/task/DeployToNginx.svg' },
      { name: 'Apache', logo: '/logos/task/DeployToApache.svg' },
      { name: 'Tomcat', logo: '/logos/task/DeployToTomcat.svg' },
      { name: 'IIS', logo: '/logos/task/DeployToIis.svg' },
      { name: 'HAProxy', logo: '/logos/task/DeployToHaproxy.svg' },
      { name: 'AWS ACM', logo: '/logos/task/DeployToAwsAcm.svg' },
      { name: '邮件服务器', logo: '/logos/task/DeployToMail.svg' },
      { name: 'OpenWrt', logo: '/logos/task/DeployToOpenwrt.svg' },
      { name: '本地目录', logo: '/logos/task/DeployToLocal.svg' },
      { name: '脚本部署', logo: '/logos/task/DeployToScript.svg' },
      { name: 'Webhook', logo: '/logos/task/DeployToWebhook.svg' },
      { name: '运行命令', logo: '/logos/task/DeployRunCommand.svg' },
      { name: '备份证书', logo: '/logos/task/DeployBackupCerts.svg' },
      { name: '等待', logo: '/logos/task/DeployWait.svg' },
      { name: 'EAB 凭据', logo: '/logos/access/eab.svg' }
    ]
  }
]

/** 全部部署插件（按后端 DEPLOY_TARGETS 分组） */
export const DEPLOY_GROUPS: { name: string; items: string[] }[] = [
  {
    name: '主机',
    items: [
      '部署到远程主机',
      '复制到本机目录',
      '部署到 Nginx（SSH）',
      '部署到 Apache（SSH）',
      '部署到 HAProxy（SSH）',
      '部署到 Tomcat（SSH）',
      '部署到 IIS（Windows）',
      '上传证书到 FTP',
      '执行远程主机命令',
      'ESXi-部署证书到ESXi'
    ]
  },
  {
    name: '云 CDN',
    items: [
      '部署到阿里云 CDN',
      '部署到阿里云 DCDN',
      '部署到阿里云直播',
      '部署到阿里云点播',
      '上传到阿里云 SLB 证书库',
      '部署到腾讯云 CDN',
      '部署到腾讯云 EdgeOne',
      '部署到腾讯云 CLB',
      '腾讯云-上传证书到SSL',
      '托管到火山引擎证书中心',
      '部署到火山引擎 CDN',
      '部署到火山引擎直播',
      '部署到七牛云',
      '部署到 AWS CloudFront',
      '上传证书到 AWS ACM',
      '部署到 Fastly',
      '部署到天翼云 CDN',
      '上传到京东云证书中心',
      '部署到京东云 CDN',
      '部署到多吉云 CDN',
      '部署到易盾 DCDN',
      '部署到括彩云 CDN',
      '部署到我爱云 CDN',
      '部署到又拍云 CDN / USS',
      '部署到白山云',
      '部署到百度云 CDN',
      '百度云-上传到证书托管',
      '中国移动-部署证书到CDN',
      '华为云-部署证书至CDN',
      '金山云-更新CDN证书',
      '雨云-更新证书',
      'UCloud-部署到WAF',
      'UCloud-上传到USSL',
      'UCloud-部署到CDN',
      'UCloud-部署到负载均衡'
    ]
  },
  {
    name: '面板',
    items: [
      '部署到宝塔面板',
      '部署到 1Panel',
      '部署到群晖 DSM',
      '部署到威联通 QTS',
      '部署到 Proxmox VE',
      '部署到 Nginx Proxy Manager',
      '部署到 OpenWrt / iStoreOS',
      '部署到雷池 WAF',
      'AcePanel-部署到网站',
      'AcePanel-面板证书',
      '飞牛NAS-部署证书'
    ]
  },
  {
    name: '对象存储',
    items: [
      '部署到阿里云 OSS',
      '部署到腾讯云 COS',
      '部署到华为云 OBS',
      '部署到火山引擎 TOS',
      '部署到 AWS S3',
      '部署到 S3 兼容存储',
      '部署到 Cloudflare R2',
      '部署到七牛 Kodo',
      'UCloud-部署到对象存储(US3)'
    ]
  },
  {
    name: '集群',
    items: [
      '部署到 K8s Secret',
      '部署到 K8s Ingress',
      '阿里云-部署到ACK',
      '百度云-部署到CCE',
      '腾讯云-部署到TKE'
    ]
  },
  {
    name: '其它',
    items: ['推送到自定义接口', '证书发送到邮箱', '在主机执行脚本', '等待', '数据备份']
  }
]

/** 签发来源（12 种） */
export const CERT_SOURCES = [
  { name: "Let's Encrypt", kind: 'ACME CA', validity: '90 天', challenge: 'DNS-01 / HTTP-01', tags: ['免费', 'DV', '泛域名'] },
  { name: 'Google Trust Services', kind: 'ACME CA', validity: '90 天', challenge: 'DNS-01 / HTTP-01', tags: ['免费', 'DV', '需 EAB'] },
  { name: 'ZeroSSL', kind: 'ACME CA', validity: '90 天', challenge: 'DNS-01 / HTTP-01', tags: ['免费', 'DV', '需 EAB'] },
  { name: 'FreeSSL / LiteSSL', kind: 'ACME CA', validity: '90 天', challenge: 'DNS-01 / HTTP-01', tags: ['免费', 'DV', '需 EAB'] },
  { name: 'Buypass', kind: 'ACME CA', validity: '180 天', challenge: 'DNS-01 / HTTP-01', tags: ['免费', 'DV'] },
  { name: '自定义 ACME', kind: 'ACME CA', validity: '以 CA 为准', challenge: '取决于 CA', tags: ['ACME v2'] },
  { name: '阿里云免费证书', kind: '云厂商', validity: '3 个月', challenge: 'DNS 验证', tags: ['免费', 'DV'] },
  { name: '腾讯云免费证书', kind: '云厂商', validity: '3 个月', challenge: 'DNS 验证', tags: ['免费', 'DV'] },
  { name: '火山引擎免费证书', kind: '云厂商', validity: '以控制台为准', challenge: 'DNS 验证', tags: ['免费', 'DV'] },
  { name: 'TrustAsia 亚洲诚信', kind: '商业 CA', validity: '按产品', challenge: 'DNS / CNAME / 文件', tags: ['DV', 'OV', 'EV'] },
  { name: '自签证书', kind: '本地', validity: '默认 365 天', challenge: '无需验证', tags: ['测试'] },
  { name: '上传自有证书', kind: '导入', validity: '以证书为准', challenge: '无需验证', tags: ['自有证书'] }
]

/** 通知渠道（10 种） */
export const NOTIFY_CHANNELS = [
  '邮件通知',
  'Webhook',
  '钉钉机器人',
  '飞书机器人',
  '企业微信机器人',
  'AnPush',
  'Server 酱',
  'PushPlus',
  'Telegram',
  'Bark'
]

/** 授权类型（41 种） */
export const ACCESS_TYPES = [
  { category: '云厂商 / DNS', items: ['阿里云', '腾讯云 / DNSPod', '华为云', '火山引擎', 'AWS', '百度智能云', 'Cloudflare', 'GoDaddy', 'NameSilo', 'TrustAsia', '七牛云', 'Fastly', '天翼云', '京东云', '多吉云', '易盾 DCDN', '括彩云 CDN', '我爱云 CDN', '白山云', '又拍云', 'S3 兼容存储', 'Cloudflare R2', '阿里云 ACK', '百度云 CCE', '腾讯云 TKE', '中国移动 CDN', '金山云', '雨云 Rainyun', '优刻得 UCloud'] },
  { category: '主机', items: ['主机 SSH', 'FTP 服务器'] },
  { category: '面板 / 集群', items: ['宝塔面板', '1Panel', '群晖 DSM', '威联通 QTS', 'Proxmox VE', 'Nginx Proxy Manager', 'Kubernetes', '长亭雷池 WAF', 'AcePanel'] },
  { category: '证书签发', items: ['EAB 凭据'] }
]

/** 首页统计数字 */
export const STATS = [
  { num: String(DEPLOY_GROUPS.reduce((n, g) => n + g.items.length, 0)), suffix: '', label: '部署目标插件' },
  { num: String(CERT_SOURCES.length), suffix: '', label: '证书签发来源' },
  { num: '6', suffix: '', label: 'DNS 服务商' },
  { num: String(NOTIFY_CHANNELS.length), suffix: '', label: '消息通知渠道' }
]
