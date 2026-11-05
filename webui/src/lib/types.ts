export interface Page<T> {
  records: T[]
  total: number
  current: number
  size: number
}

export interface PluginField {
  key: string
  title: string
  component?: string
  required?: boolean
  default?: unknown
  options?: { label: string; value: string | number }[]
  helper?: string
  placeholder?: string
  group?: string
  showWhen?: { key: string; value?: unknown; values?: unknown[] } | { key: string; value?: unknown; values?: unknown[] }[]
  remote?: string
  accessCategory?: string
  accessTypes?: string[]
}

export interface TaskPlugin {
  type: string
  name: string
  group: string
  category?: string
  icon?: string
  desc?: string
  inputs: PluginField[]
  logo?: string
  logoFile?: string
  color?: string
}

export interface AccessType {
  name: string
  category: string
  desc?: string
  inputs: PluginField[]
  logo?: string
  logoFile?: string
  color?: string
  categoryName?: string
}

export interface PluginMeta {
  groups: { key: string; name: string }[]
  plugins: TaskPlugin[]
  accessTypes: Record<string, AccessType>
  accessCategories: { key: string; name: string; color: string; desc: string }[]
  notifyTypes: Record<string, { name: string; inputs: PluginField[] }>
  acmeProviders: Record<string, { name: string; directory: string; eab?: boolean }>
}

export interface PipelineTask {
  id: string
  type: string
  title: string
  input: Record<string, unknown>
  enabled?: boolean
  linked?: boolean
  continueOnError?: boolean
  onErrorTaskId?: string
}

export interface PipelineStage {
  id: string
  title: string
  tasks: PipelineTask[]
  enabled?: boolean
}

export interface PipelineContent {
  stages: PipelineStage[]
  triggers: { id: string; type: string; cron?: string; enabled?: boolean }[]
  triggerKey?: string
  /** 画布上手动摆过的阶段坐标（网格对齐后落库），没有就用自动布局 */
  layout?: {
    stages?: Record<string, { x: number; y: number }>
  }
}

export interface PipelineItem {
  id: number
  title: string
  remark: string
  disabled: boolean
  type: string
  lastHistoryTime: string
  nextRunTime: string
  keepHistoryCount: number
  createTime: string
  running: boolean
  stageCount: number
  stepCount: number
  stepDisabledCount?: number
  taskCount?: number
  triggerCount: number
  domains: string[]
  kinds?: string[]
  lastStatus: string
  certDomains: string[]
  certIssuer: string
  certExpiresTime: string
}

export interface PipelineDetail extends PipelineItem {
  content: PipelineContent
  lastRun?: {
    id: number
    status: string
    startTime: string
    endTime: string
    duration: number | null
    tasks: Record<string, unknown>
  }
}

export interface HistoryItem {
  id: number
  pipelineId: number
  pipelineTitle: string
  status: string
  triggerType: string
  startTime: string
  endTime: string
  duration: number
  taskCount: number
}

export interface CertItem {
  id: number
  domains: string[]
  domain: string
  issuer: string
  status: string
  notBefore: string
  notAfter: string
  daysLeft: number
  createTime: string
  pipelineId: number
}

export interface CertChainItem {
  index: number
  kind: string
  isCA: boolean
  subject: string
  issuer: string
  notBefore: string
  notAfter: string
  signatureAlgorithm: string
  publicKey: string
  pem: string
}

export interface CertDetail extends CertItem {
  certPem: string
  keyPem: string
  details?: {
    subject?: string
    subjectCommonName?: string
    organization?: string
    issuer?: string
    issuerOrganization?: string
    san?: string[]
    serialNumber?: string
    fingerprintSha256?: string
    signatureAlgorithm?: string
    publicKey?: string
    chainCount?: number
    isSelfSigned?: boolean
    chain?: CertChainItem[]
  }
}

export interface AccessItem {
  id: number
  category: string
  type: string
  name: string
  remark: string
  typeName: string
  config: Record<string, unknown>
  secretKeys: string[]
  createTime: string
}

export interface NotificationItem {
  id: number
  type: string
  typeName: string
  name: string
  enabled: boolean
  isDefault: boolean
  config: Record<string, unknown>
  createTime: string
}

export interface SiteItem {
  id: number
  url: string
  port: number
  enabled: boolean
  notifyEnabled: boolean
  status: string
  error: string
  issuer: string
  notBefore: string
  expireTime: string
  daysLeft: number | null
  lastCheckTime: string
}

export interface CnameItem {
  id: number
  domain: string
  mainDomain: string
  hostRecord: string
  recordValue: string
  accessId: number
  source?: string
  status: string
  error: string
  verifyTime: string
  remark: string
  createTime: string
}

export interface SubdomainItem {
  id: number
  domain: string
  accessId: number
  disabled: boolean
  remark: string
  createTime: string
}

export interface Overview {
  stats: {
    pipelineTotal: number
    pipelineEnabled: number
    certTotal: number
    certValid: number
    certExpiring: number
    certExpired: number
    siteTotal: number
    siteError: number
    successRate: number
    avgDuration: number
    runTotal30d: number
  }
  expiringCerts: { id: number; domains: string[]; daysLeft: number; notAfter: string }[]
  recentHistories: HistoryItem[]
  recentPipelines?: PipelineItem[]
}

export interface SystemInfo {
  hostname: string
  system: string
  os: string
  uptime: number
  cpu: { name: string; percent: number; perCore: number[]; coresPhysical: number; coresLogical: number; freqMhz: number }
  memory: { total: number; used: number; percent: number }
  swap: { total: number; used: number; percent: number }
  disks: { device: string; mount: string; total: number; used: number; percent: number; system: boolean }[]
  systemDisk?: { device: string; total: number; used: number; percent: number }
}

export interface UserInfo {
  userId: number
  userName: string
  nickname: string
  email: string
  avatar: string
  role: string
  roles: string[]
  isAdmin?: boolean
  /** 有效功能权限键（管理员 = 全部） */
  permissions?: string[]
  /** 闲置多少分钟自动退出（0 = 关闭） */
  idleTimeoutMinutes?: number
  totpEnabled: boolean
}

export interface UserGroupItem {
  id: number
  name: string
  remark: string
  permissions: string[]
  userCount: number
}

export interface PermissionItem {
  key: string
  name: string
  desc: string
}
