import { http, download } from './http'
import type {
  AccessItem,
  CertDetail,
  CertItem,
  CnameItem,
  HistoryItem,
  NotificationItem,
  Overview,
  Page,
  PermissionItem,
  PipelineDetail,
  PipelineItem,
  PluginMeta,
  SiteItem,
  SubdomainItem,
  SystemInfo,
  UserGroupItem,
  UserInfo,
} from './types'

export interface ListQuery {
  current?: number
  size?: number
  [key: string]: unknown
}

/* ---------------------------------------------------------------- 认证 / 站点 */

export const login = (params: { userName: string; password: string; captchaCode?: string; captchaToken?: string }) =>
  http.post<{ token: string; refreshToken: string }>('/api/auth/login', params)

export const fetchCaptcha = () =>
  http.get<{ token: string; image: string; expiresIn: number; enabled: boolean }>('/api/auth/captcha')

export const fetchSiteConfig = () =>
  http.get<{
    name: string
    subtitle?: string
    title: string
    logo: string
    loginBackground?: string
    loginNotice: string
    homeNotice: string
    copyright: string
    watermark?: string
  }>('/api/site/config')

export const fetchUserInfo = () => http.get<UserInfo>('/api/user/info')

export const bind2fa = (bindToken: string, code: string) =>
  http.post<{ token: string; refreshToken: string }>('/api/auth/2fa/bind', { code }, { headers: { Authorization: bindToken } })

export const fetch2faSecretForBind = (bindToken: string) =>
  http.post<{ secret: string; uri: string; userName: string }>('/api/auth/2fa/secret', {}, { headers: { Authorization: bindToken } })

/* ---------------------------------------------------------------- 仪表盘 */

export const fetchOverview = () => http.get<Overview>('/api/dashboard/overview')
export const fetchSystemInfo = () => http.get<SystemInfo>('/api/dashboard/system')

/* ---------------------------------------------------------------- 流水线 */

export const fetchPipelineList = (params: ListQuery) => http.get<Page<PipelineItem>>('/api/pipeline/list', { params })
export const fetchPipelineDetail = (id: number) => http.get<PipelineDetail>(`/api/pipeline/${id}`)
export const createPipeline = (body: unknown) => http.post<{ id: number }>('/api/pipeline', body)
export const updatePipeline = (id: number, body: unknown) => http.put(`/api/pipeline/${id}`, body)
export const deletePipeline = (id: number) => http.del(`/api/pipeline/${id}`)
export const copyPipeline = (id: number) => http.post<{ id: number }>(`/api/pipeline/${id}/copy`)
export const runPipeline = (id: number) => http.post<{ historyId: number }>(`/api/pipeline/${id}/run`)
export const runStage = (id: number, stageId: string) =>
  http.post<{ historyId: number }>(`/api/pipeline/${id}/stage/run`, { stageId })
export const togglePipeline = (id: number) => http.post<{ disabled: boolean }>(`/api/pipeline/${id}/disable`)
export const fetchTemplates = () =>
  http.get<{ id: string; name: string; desc: string; tags: string[]; stageCount: number }[]>('/api/pipeline/templates')
export const createFromTemplate = (body: { templateId: string; title?: string }) =>
  http.post<{ id: number; title: string }>('/api/pipeline/from-template', body)
export const fetchPluginMeta = () => http.get<PluginMeta>('/api/pipeline/plugins')
export const fetchPluginOptions = (taskType: string, field: string, input: Record<string, unknown>) =>
  http.post<{ items: { label: string; value: unknown }[]; error: string; total: number }>(
    `/api/pipeline/plugin/${taskType}/options/${field}`,
    { input },
  )
export const batchPipeline = (body: { action: string; ids: number[]; notificationId?: number; cron?: string }) =>
  http.post<{ success: unknown[]; failed: unknown[] }>('/api/pipeline/batch', body)

/* ---------------------------------------------------------------- 关于 / 更新检查 */

export interface UpdateRelease {
  tag: string
  name: string
  publishedAt: string
  body: string
  url: string
  prerelease: boolean
}

export interface UpdateCommit {
  sha: string
  message: string
  date: string
  url: string
  author: string
}

export interface UpdatesData {
  repo: string
  repoUrl: string
  current: string
  latest: string
  updateAvailable: boolean
  source: string
  releases: UpdateRelease[]
  commits: UpdateCommit[]
  checkedAt: string
  error: string
}

export const fetchAbout = () =>
  http.get<{
    name: string
    version: string
    developers: string[]
    website: string
    email: string
    repo: string
    repoUrl: string
  }>('/api/meta/about')
export const fetchUpdates = (refresh = false) =>
  http.get<UpdatesData>(`/api/meta/updates${refresh ? '?refresh=1' : ''}`)

/* ---------------------------------------------------------------- 执行历史 */

export const fetchHistoryList = (params: ListQuery) => http.get<Page<HistoryItem>>('/api/history/list', { params })
export const fetchHistoryDetail = (id: number) => http.get<Record<string, unknown>>(`/api/history/${id}`)
export const deleteHistory = (id: number) => http.del(`/api/history/${id}`)
export const stopHistory = (id: number) => http.post(`/api/history/${id}/stop`)
export const clearHistory = (pipelineId = 0) => http.post('/api/history/clear', { pipelineId })

/* ---------------------------------------------------------------- 证书 */

export const fetchCertList = (params: ListQuery) => http.get<Page<CertItem>>('/api/cert/list', { params })
export const fetchCertDetail = (id: number) => http.get<CertDetail>(`/api/cert/${id}`)
export const importCert = (body: { cert: string; key: string; remark?: string }) =>
  http.post<{ id: number; domains: string[]; notAfter: string }>('/api/cert/import', body)
export const deleteCert = (id: number) => http.del(`/api/cert/${id}`)
export const downloadCert = (id: number, format: string, type: 'cert' | 'key' = 'cert') =>
  download(`/api/cert/${id}/download?format=${format}&type=${type}`, `cert-${id}.${format}`)

/* ---------------------------------------------------------------- 授权 / 通知 */

export const fetchAccessList = (params: ListQuery) => http.get<Page<AccessItem>>('/api/access/list', { params })
export const createAccess = (body: unknown) => http.post<{ id: number }>('/api/access', body)
export const updateAccess = (id: number, body: unknown) => http.put(`/api/access/${id}`, body)
export const deleteAccess = (id: number) => http.del(`/api/access/${id}`)
export const testAccess = (id: number) => http.post<{ success: boolean; message: string }>(`/api/access/${id}/test`)

export const fetchNotificationList = (params: ListQuery) =>
  http.get<Page<NotificationItem>>('/api/notification/list', { params })
export const createNotification = (body: unknown) => http.post<{ id: number }>('/api/notification', body)
export const updateNotification = (id: number, body: unknown) => http.put(`/api/notification/${id}`, body)
export const deleteNotification = (id: number) => http.del(`/api/notification/${id}`)
export const testNotification = (id: number) =>
  http.post<{ success: boolean; message: string }>(`/api/notification/${id}/test`)

/* ---------------------------------------------------------------- DNS / 监控 */

export const fetchCnameList = (params: ListQuery) => http.get<Page<CnameItem>>('/api/dns/cname/list', { params })
export const createCname = (body: unknown) => http.post<CnameItem>('/api/dns/cname', body)
export const deleteCname = (id: number, remote = false) => http.del(`/api/dns/cname/${id}`, { params: { remote } })
export const syncCname = (id: number) => http.post<CnameItem>(`/api/dns/cname/${id}/sync`)
export const verifyCname = (id: number) =>
  http.post<{ success: boolean; actual: string; message: string }>(`/api/dns/cname/${id}/verify`)

export const fetchSubdomainList = (params: ListQuery) =>
  http.get<Page<SubdomainItem>>('/api/dns/subdomain/list', { params })
export const createSubdomain = (body: unknown) => http.post<SubdomainItem>('/api/dns/subdomain', body)
export const deleteSubdomain = (id: number) => http.del(`/api/dns/subdomain/${id}`)

export const fetchSiteList = (params: ListQuery) => http.get<Page<SiteItem>>('/api/monitor/site/list', { params })
export const createSite = (body: unknown) => http.post('/api/monitor/site', body)
export const deleteSite = (id: number) => http.del(`/api/monitor/site/${id}`)
export const checkSite = (id: number) => http.post<SiteItem>(`/api/monitor/site/${id}/check`)

/* ---------------------------------------------------------------- 系统 */

export const fetchSettings = () => http.get<Record<string, Record<string, unknown>>>('/api/settings')
export const updateSettings = (values: Record<string, unknown>) => http.put('/api/settings', { values })
export const fetchAuditList = (params: ListQuery) => http.get<Page<Record<string, unknown>>>('/api/settings/audit/list', { params })
export const fetchApiKeys = () => http.get<Record<string, unknown>[]>('/api/open/keys')
export const createApiKey = (name: string) =>
  http.post<{ id: number; keyId: string; secret: string }>('/api/open/keys', { name })
export const deleteApiKey = (id: number) => http.del(`/api/open/keys/${id}`)
export const fetchUserList = (params: ListQuery) => http.get<Page<Record<string, unknown>>>('/api/user/list', { params })
export const createUser = (body: unknown) => http.post('/api/user', body)
export const updateUser = (id: number, body: unknown) => http.put(`/api/user/${id}`, body)
export const deleteUser = (id: number) => http.del(`/api/user/${id}`)

/* ---------------------------------------------------------------- 用户组 */

export const fetchUserGroups = () => http.get<UserGroupItem[]>('/api/user/groups')
export const fetchPermissionCatalog = () => http.get<PermissionItem[]>('/api/user/permissions')
export const createUserGroup = (body: { name: string; remark?: string; permissions?: string[] }) =>
  http.post<{ id: number }>('/api/user/groups', body)
export const updateUserGroup = (id: number, body: { name: string; remark?: string; permissions?: string[] }) =>
  http.put(`/api/user/groups/${id}`, body)
export const deleteUserGroup = (id: number) => http.del(`/api/user/groups/${id}`)

/* ---------------------------------------------------------------- 账号安全（当前登录用户） */

export const updateProfile = (body: { nickname: string; email: string }) => http.put('/api/user/info', body)
export const changePassword = (body: { oldPassword: string; newPassword: string }) =>
  http.put('/api/user/password', body)
export const fetch2faSetup = () =>
  http.get<{ secret: string; uri: string; qr: string; account: string; enabled: boolean }>('/api/user/2fa/secret')
export const enable2fa = (code: string) => http.post('/api/user/2fa/enable', { code })
export const disable2fa = (code: string) => http.post('/api/user/2fa/disable', { code })
