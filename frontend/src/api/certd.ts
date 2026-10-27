/**
 * CertHub 接口层
 *
 * 全部接口与 backend/app/routers/* 一一对应，统一走 @/utils/http，
 * 后端返回 { code, msg, data }，http 层已把 data 拆出来。
 *
 * 约定：
 * 1. 列表接口一律 { records, total, current, size }，直接喂给 useTable；
 * 2. 凭据字段后端明文下发（AGENTS.md 第一条），前端用「小眼睛」控制显示；
 * 3. 下载类接口返回二进制，不能走 http 封装，单独用 fetch 处理。
 *
 * @module api/certd
 */
import request from '@/utils/http'
import { useUserStore } from '@/store/modules/user'

export const API_BASE = import.meta.env.VITE_API_URL || '/'

/** 统一拼绝对地址（fetch / SSE 用） */
export function apiUrl(path: string): string {
  const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE
  return `${base}${path.startsWith('/') ? path : '/' + path}`
}

/* ------------------------------------------------------------------ 类型 */

/** 插件表单字段元数据（后端 plugins.py 的 f()） */
export interface PluginField {
  key: string
  title: string
  component?: string
  required?: boolean
  default?: any
  options?: { label: string; value: any }[]
  helper?: string
  placeholder?: string
  /** 分组标题：同组字段在表单里归到一个小节（不写就落在无标题区） */
  group?: string
  /** 显示条件：单条件或「多条件全部满足」 */
  showWhen?: { key: string; value?: any; values?: any[] } | { key: string; value?: any; values?: any[] }[]
  /** 老数据没有这个字段时，从另一个字段推导值（例如群晖「二步验证」由 otpType 推导） */
  deriveFrom?: { key: string; map?: Record<string, any> }
  remote?: string
  remoteFrom?: string
  accessCategory?: string
  domainFrom?: string
  /** 远程资源是否按证书域名自动匹配并选中（站点 / 加速域名用） */
  autoMatchDomains?: boolean
  /** 该字段允许的授权类型（精确到类型，例如群晖任务只认 synology） */
  accessTypes?: string[]
  /**
   * 字段动作按钮：渲染在字段下方，点一下做一件事并把结果写回字段。
   * 目前只有群晖的「获取设备ID」（输一次 6 位验证码换长期免验证码的受信设备令牌）。
   */
  action?: {
    type: 'synology-device-id' | string
    label?: string
    icon?: string
    hint?: string
  }
  [key: string]: any
}

/** 任务插件元数据 */
export interface TaskPlugin {
  type: string
  name: string
  group: 'cert' | 'deploy' | 'notify' | string
  category?: string
  icon?: string
  desc?: string
  inputs: PluginField[]
  outputs?: any[]
  logo?: string
  /** 本地图标相对路径（后端 fetch_access_logos.py 下的，离线可用） */
  logoFile?: string
  color?: string
  favicon?: string
  short?: string
  pro?: boolean
}

/** 授权类型元数据 */
export interface AccessType {
  name: string
  category: string
  desc?: string
  capabilities?: string[]
  inputs: PluginField[]
  logo?: string
  color?: string
  favicon?: string
  short?: string
  categoryName?: string
  categoryColor?: string
  logoFile?: string
}

/** 通知类型元数据 */
export interface NotifyType {
  name: string
  inputs: PluginField[]
  pro?: boolean
}

/** /api/pipeline/plugins 的完整返回 */
export interface PluginMeta {
  groups: { key: string; name: string }[]
  plugins: TaskPlugin[]
  accessTypes: Record<string, AccessType>
  accessCategories: { key: string; name: string; color: string; desc: string }[]
  notifyTypes: Record<string, NotifyType>
  acmeProviders: Record<string, { name: string; directory: string; eab?: boolean }>
  dnsProviders: Record<string, any>
}

/** 流水线任务 */
export interface PipelineTask {
  id: string
  type: string
  title: string
  input: Record<string, any>
  continueOnError?: boolean
  /** 任务卡片上的开关：false = 运行时跳过这一步（缺省 / true 都是启用） */
  enabled?: boolean
  /**
   * 失败后跳转：本任务执行失败时，跳到这个任务继续跑（跳过中间的任务）。
   * 只能指向执行顺序里排在后面的任务，否则会成环。
   */
  onErrorTaskId?: string
  /**
   * 是否已经连到流程里（缺省 = true，老数据不用迁移）。
   * 画布上新加的步骤是 false：不画自动连线，运行时也跳过，
   * 必须手动把线连到它身上（`linked` 变 true）才会参与执行。
   */
  linked?: boolean
}

/** 流水线阶段 */
export interface PipelineStage {
  id: string
  title: string
  tasks: PipelineTask[]
  /**
   * 阶段开关（画布阶段卡片右上角）：false = 运行时整段跳过（缺省 / true 都是启用）。
   * 和任务的 enabled 同一个语义，只是粒度到阶段 —— 临时不想发证书时不用逐个关任务。
   */
  enabled?: boolean
}

/** 流水线触发器 */
export interface PipelineTrigger {
  id: string
  type: string
  cron?: string
  enabled?: boolean
}

/** 流水线内容 */
export interface PipelineContent {
  stages: PipelineStage[]
  triggers: PipelineTrigger[]
  triggerKey?: string
  /**
   * 画布坐标（可选）。
   * stages 是画布绝对坐标，tasks 是相对所属阶段容器的坐标 —— 与 Vue Flow 的 parentNode 语义一致。
   * 后端只校验 stages，这个字段原样存回，老数据没有就按阶段自动排版。
   */
  layout?: {
    stages?: Record<string, { x: number; y: number }>
    tasks?: Record<string, { x: number; y: number }>
  }
}

/** 流水线列表项 */
export interface PipelineItem {
  id: number
  title: string
  remark: string
  disabled: boolean
  type: string
  keepHistoryCount: number
  lastHistoryTime: string
  nextRunTime: string
  validTime: string
  createTime: string
  updateTime: string
  running: boolean
  stageCount: number
  /** 会实际执行的步骤数（已排除「已停用」和「未连线」） */
  stepCount: number
  /** 已停用的步骤数 */
  stepDisabledCount?: number
  /** 画布上没连线的步骤数：不连线就不执行 */
  stepUnlinkedCount?: number
  /** 结构里的任务总数（含停用 / 未连线） */
  taskCount?: number
  triggerCount: number
  domains: string[]
  /** 流程分类：cert / deploy / notify（后端解析 content 得出） */
  kinds?: string[]
  lastStatus: string
  certDomains: string[]
  certIssuer: string
  certEffectiveTime: string
  certExpiresTime: string
}

/** 流水线详情 */
export interface PipelineDetail extends PipelineItem {
  content: PipelineContent
  lastRun?: {
    id: number
    status: string
    startTime: string
    endTime: string
    duration: number | null
    tasks: Record<string, any>
  }
}

/** 执行历史 */
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

/** 授权 */
export interface AccessItem {
  id: number
  category: string
  type: string
  name: string
  remark: string
  typeName: string
  config: Record<string, any>
  secretKeys: string[]
  createTime: string
}

/** 通知渠道 */
export interface NotificationItem {
  id: number
  type: string
  typeName: string
  name: string
  enabled: boolean
  isDefault: boolean
  config: Record<string, any>
  createTime: string
}

/** 证书 */
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

/** CNAME 记录 */
export interface CnameRecordItem {
  id: number
  domain: string
  mainDomain: string
  hostRecord: string
  recordValue: string
  accessId: number
  /** pending 待同步 / synced 已同步 / valid 已生效 / error 异常 */
  status: string
  error: string
  synced: boolean
  verifyTime: string
  remark: string
  createTime: string
}

/** 子域名托管 */
export interface SubDomainItem {
  id: number
  domain: string
  accessId: number
  disabled: boolean
  remark: string
  createTime: string
}

/** 站点监控 */
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

/* ------------------------------------------------------------------ 认证 */

export function fetchLogin(params: { userName: string; password: string; code?: string }) {
  return request.post<{ token: string; refreshToken: string }>({
    url: '/api/auth/login',
    params,
  })
}

export function fetchAuthSettings() {
  return request.get<{
    siteName: string
    subtitle?: string
    title: string
    registerEnabled: boolean
    copyright: string
  }>({ url: '/api/auth/settings' })
}

/** 站点公开配置（登录页 / 首页公告 / 菜单标题 / Logo） */
export function fetchSiteConfig() {
  return request.get<{
    name: string
    subtitle?: string
    title: string
    logo: string
    loginNotice: string
    homeNotice: string
    hideBrand: boolean
    registerEnabled: boolean
    copyright: string
  }>({ url: '/api/site/config' })
}

/* ------------------------------------------------------------------ 用户 */

export function fetchUserInfo() {
  return request.get<any>({ url: '/api/user/info' })
}

export function updateProfile(params: { nickname: string; email: string }) {
  return request.put({ url: '/api/user/info', params, showSuccessMessage: true })
}

export function changePassword(params: { oldPassword: string; newPassword: string }) {
  return request.put({ url: '/api/user/password', params, showSuccessMessage: true })
}

export function fetch2faSecret() {
  return request.get<{ secret: string; uri: string }>({ url: '/api/user/2fa/secret' })
}

export function enable2fa(code: string) {
  return request.post({ url: '/api/user/2fa/enable', params: { code }, showSuccessMessage: true })
}

export function disable2fa(code: string) {
  return request.post({ url: '/api/user/2fa/disable', params: { code }, showSuccessMessage: true })
}

export function fetchUserList(params: any) {
  return request.get({ url: '/api/user/list', params })
}

export function createUser(params: any) {
  return request.post({ url: '/api/user', params, showSuccessMessage: true })
}

export function updateUser(id: number, params: any) {
  return request.put({ url: `/api/user/${id}`, params, showSuccessMessage: true })
}

export function deleteUser(id: number) {
  return request.del({ url: `/api/user/${id}`, showSuccessMessage: true })
}

/* ------------------------------------------------------------------ 插件元数据 */

/** 一次性拿到所有插件 / 授权 / 通知的元数据（前端不再硬编码插件清单） */
export function fetchPluginMeta() {
  return request.get<PluginMeta>({ url: '/api/pipeline/plugins' })
}

/** 表单里的「远程下拉」：按当前授权实时拉取对端资源（域名 / 站点 / 证书 ID …） */
export function fetchPluginOptions(taskType: string, field: string, input: Record<string, any>) {
  return request.post<{
    kind: string
    accessType: string
    total: number
    items: any[]
    error: string
  }>({
    url: `/api/pipeline/plugin/${taskType}/options/${field}`,
    params: { input },
    showErrorMessage: false,
  })
}

/* ------------------------------------------------------------------ 流水线 */

export function fetchPipelineList(params: any) {
  return request.get({ url: '/api/pipeline/list', params })
}

export function fetchPipelineTemplates() {
  return request.get<{ id: string; name: string; desc: string; tags: string[]; stageCount: number }[]>({
    url: '/api/pipeline/templates',
  })
}

export function fetchPipelineDetail(id: number) {
  return request.get<PipelineDetail>({ url: `/api/pipeline/${id}` })
}

export function createPipeline(params: any) {
  return request.post<{ id: number }>({ url: '/api/pipeline', params })
}

export function updatePipeline(id: number, params: any) {
  return request.put({ url: `/api/pipeline/${id}`, params, showSuccessMessage: true })
}

export function deletePipeline(id: number) {
  return request.del({ url: `/api/pipeline/${id}` })
}

/** 运行流水线，返回 historyId，前端据此直接开 SSE 看实时日志 */
export function runPipeline(id: number) {
  return request.post<{ historyId: number }>({ url: `/api/pipeline/${id}/run` })
}

/** 单独运行某一个阶段（阶段卡片上的「执行」按钮），返回 historyId */
export function runStagePipeline(id: number, stageId: string) {
  return request.post<{ historyId: number }>({
    url: `/api/pipeline/${id}/stage/run`,
    params: { stageId },
  })
}

export function togglePipeline(id: number) {
  return request.post<{ disabled: boolean }>({ url: `/api/pipeline/${id}/disable` })
}

/* ------------------------------------------------------------------ 流水线分组 */

/** 分组列表（成员里带流水线标题，失败转移也带标题） */
export function fetchPipelineGroupList(params: any) {
  return request.get({ url: '/api/pipeline-group/list', params })
}

export function createPipelineGroup(body: any) {
  return request.post<{ id: number }>({ url: '/api/pipeline-group', params: body })
}

export function updatePipelineGroup(id: number, body: any) {
  return request.put({ url: `/api/pipeline-group/${id}`, params: body })
}

export function deletePipelineGroup(id: number) {
  return request.del({ url: `/api/pipeline-group/${id}` })
}

/** 运行分组：按顺序尝试，某条失败就跳它配置的「失败后执行」 */
export function runPipelineGroup(id: number) {
  return request.post<{ runId: number; groupId: number }>({
    url: `/api/pipeline-group/${id}/run`,
  })
}

export function fetchPipelineGroupRuns(params: any) {
  return request.get({ url: '/api/pipeline-group/run/list', params })
}

export function fetchPipelineGroupRun(runId: number) {
  return request.get<any>({ url: `/api/pipeline-group/run/${runId}`, showErrorMessage: false })
}

export function copyPipeline(id: number) {
  return request.post<{ id: number }>({ url: `/api/pipeline/${id}/copy`, showSuccessMessage: true })
}

export function fetchPipelineCerts(id: number) {
  return request.get<any[]>({ url: `/api/pipeline/${id}/certs` })
}

export function batchPipeline(params: {
  action: 'run' | 'enable' | 'disable' | 'delete' | 'notify' | 'cron'
  ids: number[]
  notificationId?: number
  cron?: string
}) {
  return request.post<{ success: any[]; failed: any[] }>({ url: '/api/pipeline/batch', params })
}

export function createPipelineFromTemplate(params: { templateId: string; title?: string }) {
  return request.post<{ id: number; title: string }>({
    url: '/api/pipeline/from-template',
    params,
  })
}

export function genTriggerKey() {
  return request.post<{ key: string }>({ url: '/api/pipeline/gen-key' })
}

/* ------------------------------------------------------------------ 执行历史 */

export function fetchHistoryList(params: any) {
  return request.get({ url: '/api/history/list', params })
}

export function fetchHistoryDetail(id: number) {
  return request.get<any>({ url: `/api/history/${id}` })
}

export function deleteHistory(id: number) {
  return request.del({ url: `/api/history/${id}`, showSuccessMessage: true })
}

export function stopHistory(id: number) {
  return request.post({ url: `/api/history/${id}/stop`, showSuccessMessage: true })
}

export function clearHistory(pipelineId = 0) {
  return request.post({ url: '/api/history/clear', params: { pipelineId }, showSuccessMessage: true })
}

/* ------------------------------------------------------------------ 授权 */

export function fetchAccessList(params: any) {
  return request.get({ url: '/api/access/list', params })
}

export function fetchAccessOptions(
  params: { category?: string; type?: string; types?: string } = {}
) {
  return request.get<any[]>({ url: '/api/access/options', params })
}

export function createAccess(params: any) {
  return request.post<{ id: number }>({ url: '/api/access', params })
}

export function updateAccess(id: number, params: any) {
  return request.put({ url: `/api/access/${id}`, params })
}

export function deleteAccess(id: number) {
  return request.del({ url: `/api/access/${id}`, showSuccessMessage: true })
}

/** 嗅探 DNS 授权下的域名（申请证书时一键带出） */
export function fetchAccessDomains(id: number) {
  return request.get<{ type: string; domains: string[]; patterns: string[] }>({
    url: `/api/access/${id}/domains`,
    showErrorMessage: false,
  })
}

/**
 * 群晖「获取设备ID」：输一次 6 位双重认证验证码，换一个长期免验证码的受信设备令牌。
 * config 传表单里的当前值（url / username / password / deviceName / insecure），
 * accessId 非空时后端会拿库里的配置兜底（编辑已有授权时密码框为空）。
 */
export function fetchSynologyDeviceId(params: {
  config: Record<string, any>
  otpCode: string
  accessId?: number
}) {
  return request.post<{ deviceId: string; deviceName: string }>({
    url: '/api/access/synology/device-id',
    params,
    showErrorMessage: false,
  })
}

/** 连通性测试：成功/失败都走 200，看返回的 success 字段 */
export function testAccess(id: number) {
  return request.post<{ success: boolean; message: string }>({
    url: `/api/access/${id}/test`,
    showErrorMessage: false,
  })
}

/* ------------------------------------------------------------------ 证书库 */

export function fetchCertList(params: any) {
  return request.get({ url: '/api/cert/list', params })
}

export function fetchCertDetail(id: number) {
  return request.get<any>({ url: `/api/cert/${id}` })
}

export function importCert(params: { cert: string; key: string; remark?: string }) {
  return request.post<{ id: number; domains: string[]; notAfter: string }>({
    url: '/api/cert/import',
    params,
  })
}

export function deleteCert(id: number) {
  return request.del({ url: `/api/cert/${id}`, showSuccessMessage: true })
}

/**
 * 下载证书（二进制）。
 * 不能走 http 封装：它会把响应当 JSON 解析，而且这里需要按 Content-Disposition 落盘。
 */
export async function downloadCert(
  id: number,
  format: string,
  options: { password?: string; args?: string; type?: 'cert' | 'key' } = {}
): Promise<void> {
  const { accessToken } = useUserStore()
  const query = new URLSearchParams({ format, type: options.type || 'cert' })
  if (options.password) query.set('password', options.password)
  // PFX 的 Windows 老版本兼容参数（-macalg / -keypbe / -certpbe）
  if (options.args) query.set('args', options.args)

  const res = await fetch(apiUrl(`/api/cert/${id}/download?${query.toString()}`), {
    headers: { Authorization: accessToken },
  })
  if (!res.ok) throw new Error(`下载失败（HTTP ${res.status}）`)

  // 后端失败时返回的是 JSON，这里要抛出来而不是存成一个坏文件
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    const data = await res.json()
    throw new Error(data.msg || '下载失败')
  }

  const disposition = res.headers.get('content-disposition') || ''
  const matched = /filename="?([^"]+)"?/.exec(disposition)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = matched ? matched[1] : `cert-${id}.${format}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/* ------------------------------------------------------------------ 域名 */

export function fetchDomainList(params: any) {
  return request.get({ url: '/api/domain/list', params })
}

export function createDomain(params: any) {
  return request.post({ url: '/api/domain', params, showSuccessMessage: true })
}

export function updateDomain(id: number, params: any) {
  return request.put({ url: `/api/domain/${id}`, params, showSuccessMessage: true })
}

export function deleteDomain(id: number) {
  return request.del({ url: `/api/domain/${id}`, showSuccessMessage: true })
}

/* ------------------------------------------------------------------ CNAME 记录 / 子域名托管 */

export function fetchCnameList(params: any) {
  return request.get({ url: '/api/dns/cname/list', params })
}

export function createCname(params: any) {
  return request.post<CnameRecordItem>({
    url: '/api/dns/cname',
    params,
    showSuccessMessage: true,
  })
}

export function updateCname(id: number, params: any) {
  return request.put<CnameRecordItem>({
    url: `/api/dns/cname/${id}`,
    params,
    showSuccessMessage: true,
  })
}

export function deleteCname(id: number, remote = false) {
  return request.del({
    url: `/api/dns/cname/${id}`,
    params: { remote },
    showSuccessMessage: true,
  })
}

export function syncCname(id: number) {
  return request.post<CnameRecordItem>({ url: `/api/dns/cname/${id}/sync` })
}

export function verifyCname(id: number) {
  return request.post<{
    success: boolean
    actual: string
    message: string
    record: CnameRecordItem
  }>({ url: `/api/dns/cname/${id}/verify`, showErrorMessage: false })
}

/** 新增前临时校验，不落库 */
export function checkCnameValue(params: { domain: string; expected: string }) {
  return request.post<{ success: boolean; actual: string; message: string }>({
    url: '/api/dns/cname/check',
    params,
    showErrorMessage: false,
  })
}

export function fetchSubdomainList(params: any) {
  return request.get({ url: '/api/dns/subdomain/list', params })
}

export function createSubdomain(params: any) {
  return request.post<SubDomainItem>({
    url: '/api/dns/subdomain',
    params,
    showSuccessMessage: true,
  })
}

export function updateSubdomain(id: number, params: any) {
  return request.put<SubDomainItem>({
    url: `/api/dns/subdomain/${id}`,
    params,
    showSuccessMessage: true,
  })
}

export function deleteSubdomain(id: number) {
  return request.del({ url: `/api/dns/subdomain/${id}`, showSuccessMessage: true })
}

export function verifySubdomain(id: number) {
  return request.post<{ success: boolean; ns: string[]; message: string }>({
    url: `/api/dns/subdomain/${id}/verify`,
    showErrorMessage: false,
  })
}

/* ------------------------------------------------------------------ 站点监控 */

export function fetchSiteList(params: any) {
  return request.get({ url: '/api/monitor/site/list', params })
}

export function createSite(params: any) {
  return request.post({ url: '/api/monitor/site', params })
}

export function updateSite(id: number, params: any) {
  return request.put({ url: `/api/monitor/site/${id}`, params })
}

export function deleteSite(id: number) {
  return request.del({ url: `/api/monitor/site/${id}`, showSuccessMessage: true })
}

export function checkSite(id: number) {
  return request.post<any>({ url: `/api/monitor/site/${id}/check` })
}

/* ------------------------------------------------------------------ 通知渠道 */

export function fetchNotificationList(params: any) {
  return request.get({ url: '/api/notification/list', params })
}

export function fetchNotificationOptions() {
  return request.get<{ id: number; name: string; typeName: string }[]>({
    url: '/api/notification/options',
  })
}

export function createNotification(params: any) {
  return request.post({ url: '/api/notification', params })
}

export function updateNotification(id: number, params: any) {
  return request.put({ url: `/api/notification/${id}`, params })
}

export function deleteNotification(id: number) {
  return request.del({ url: `/api/notification/${id}`, showSuccessMessage: true })
}

export function testNotification(id: number) {
  return request.post<{ success: boolean; message: string }>({
    url: `/api/notification/${id}/test`,
    showErrorMessage: false,
  })
}

/* ------------------------------------------------------------------ 概览 / 系统设置 / 开放接口 */

export function fetchOverview() {
  return request.get<any>({ url: '/api/dashboard/overview' })
}

/** 系统信息（CPU / 内存 / 硬盘使用率），工作台系统信息看板 */
export function fetchSystemInfo() {
  return request.get<any>({ url: '/api/dashboard/system' })
}

export function fetchSettings() {
  return request.get<any>({ url: '/api/settings' })
}

export function updateSettings(values: Record<string, any>) {
  return request.put({ url: '/api/settings', params: { values }, showSuccessMessage: true })
}

export function testProxy(params: {
  httpProxy?: string
  httpsProxy?: string
  reverseProxy?: string
  target?: string
}) {
  return request.post<any>({ url: '/api/settings/proxy/test', params, showErrorMessage: false })
}

export function fetchAuditList(params: any) {
  return request.get({ url: '/api/settings/audit/list', params })
}

export function fetchApiKeys() {
  return request.get<any[]>({ url: '/api/open/keys' })
}

export function createApiKey(params: { name: string }) {
  return request.post<any>({ url: '/api/open/keys', params })
}

export function deleteApiKey(id: number) {
  return request.del({ url: `/api/open/keys/${id}`, showSuccessMessage: true })
}
