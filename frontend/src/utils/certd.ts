/**
 * CertHub 前端通用工具
 *
 * 只放「跟后端状态码绑定」的纯函数：状态文案、颜色、耗时格式化、任务分类。
 * 后端状态值：流水线/历史 running|success|failed|canceled，证书 valid|expired，
 * 站点 ok|error|unknown —— 改后端枚举时同步改这里。
 *
 * @module utils/certd
 */
import type { PipelineStage, PipelineTask } from '@/api/certd'

export type TagType = 'success' | 'danger' | 'warning' | 'info' | 'primary'

export interface StatusMeta {
  text: string
  type: TagType
  icon: string
}

/** 流水线 / 执行记录状态 */
export function runStatusMeta(status?: string): StatusMeta {
  switch (status) {
    case 'success':
      return { text: '成功', type: 'success', icon: 'ri:checkbox-circle-line' }
    case 'failed':
      return { text: '失败', type: 'danger', icon: 'ri:close-circle-line' }
    case 'running':
      return { text: '运行中', type: 'warning', icon: 'ri:loader-4-line' }
    case 'canceled':
      return { text: '已取消', type: 'info', icon: 'ri:stop-circle-line' }
    default:
      return { text: '未执行', type: 'info', icon: 'ri:subtract-line' }
  }
}

/** 证书状态（按剩余天数分档，比只看 valid/expired 更有用） */
export function certStatusMeta(daysLeft: number | null | undefined): StatusMeta {
  if (daysLeft === null || daysLeft === undefined) {
    return { text: '未知', type: 'info', icon: 'ri:question-line' }
  }
  if (daysLeft < 0) return { text: '已过期', type: 'danger', icon: 'ri:error-warning-line' }
  if (daysLeft <= 7) return { text: '剩余 ' + daysLeft + ' 天', type: 'danger', icon: 'ri:alarm-line' }
  if (daysLeft <= 30) return { text: '剩余 ' + daysLeft + ' 天', type: 'warning', icon: 'ri:time-line' }
  return { text: '剩余 ' + daysLeft + ' 天', type: 'success', icon: 'ri:shield-check-line' }
}

/** 站点监控状态 */
export function siteStatusMeta(status?: string): StatusMeta {
  switch (status) {
    case 'ok':
      return { text: '正常', type: 'success', icon: 'ri:checkbox-circle-line' }
    case 'error':
      return { text: '异常', type: 'danger', icon: 'ri:error-warning-line' }
    default:
      return { text: '未检测', type: 'info', icon: 'ri:question-line' }
  }
}

/** 触发方式 */
export function triggerText(type?: string): string {
  const map: Record<string, string> = {
    manual: '手动',
    timer: '定时',
    webhook: 'Webhook',
    openapi: '开放接口',
  }
  return map[type || ''] || type || '-'
}

/** 耗时：后端给秒 */
export function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds < 0) return '-'
  if (seconds < 60) return Math.round(seconds) + ' 秒'
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes < 60) return minutes + ' 分 ' + rest + ' 秒'
  return Math.floor(minutes / 60) + ' 时 ' + (minutes % 60) + ' 分'
}

/** 域名列表 → 展示文本 */
export function domainsText(domains?: string[] | string): string {
  if (!domains) return ''
  if (Array.isArray(domains)) return domains.filter(Boolean).join(', ')
  return String(domains)
}

/** 任务所属大类：证书申请 / 证书部署 / 通知 */
export function taskKindOf(type: string): 'cert' | 'deploy' | 'notify' {
  if (type === 'Notify') return 'notify'
  if (type.indexOf('CertApply') === 0) return 'cert'
  return 'deploy'
}

/** 阶段大类：取第一个任务的大类（阶段里可以混，以主任务为准） */
export function stageKindOf(stage: PipelineStage): 'cert' | 'deploy' | 'notify' {
  const first = (stage.tasks || [])[0]
  return first ? taskKindOf(first.type) : 'deploy'
}

export interface StageKindMeta {
  key: 'cert' | 'deploy' | 'notify'
  text: string
  color: string
  icon: string
}

export const STAGE_KIND_META: Record<'cert' | 'deploy' | 'notify', StageKindMeta> = {
  // 取色走 Google Material 调色板：蓝 600 / 绿 700 / 琥珀 800（都满足白底可读）
  cert: { key: 'cert', text: '证书申请', color: '#1a73e8', icon: 'ri:file-shield-2-line' },
  deploy: { key: 'deploy', text: '证书部署', color: '#1e8e3e', icon: 'ri:rocket-2-line' },
  notify: { key: 'notify', text: '发送通知', color: '#e37400', icon: 'ri:notification-3-line' },
}

/** 流水线里出现的阶段大类集合，列表页用来打标签 */
export function pipelineKinds(stages?: PipelineStage[]): StageKindMeta[] {
  const keys = new Set<string>()
  for (const stage of stages || []) keys.add(stageKindOf(stage))
  return [...keys].map((key) => STAGE_KIND_META[key as 'cert' | 'deploy' | 'notify'])
}

/** 任务卡片上一次执行结果 */
export function taskRunStatus(
  lastRun: Record<string, any> | undefined,
  taskId: string
): StatusMeta | null {
  const item = lastRun?.[taskId]
  if (!item) return null
  return runStatusMeta(item.status)
}

/** 生成短 id（阶段 / 任务） */
export function shortId(prefix: string): string {
  return prefix + '-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
}

/** cron 常用预设（新建定时器时给用户点选，不用背表达式） */
export const CRON_PRESETS: { label: string; value: string; desc: string }[] = [
  { label: '每天凌晨 3 点', value: '0 3 * * *', desc: '0 3 * * *' },
  { label: '每天凌晨 1 点', value: '0 1 * * *', desc: '0 1 * * *' },
  { label: '每 6 小时', value: '0 */6 * * *', desc: '0 */6 * * *' },
  { label: '每周一凌晨 2 点', value: '0 2 * * 1', desc: '0 2 * * 1' },
  { label: '每月 1 号凌晨 2 点', value: '0 2 1 * *', desc: '0 2 1 * *' },
]

/** 阶段里设置了「失败继续」的任务（卡片上用来说明容错） */
export function stageIgnoreErrors(stage: PipelineStage): PipelineTask[] {
  return (stage.tasks || []).filter((task) => task.continueOnError)
}

/** showWhen 的单个条件：单值 value 或多值 values */
export interface ShowWhenCondition {
  key: string
  value?: any
  values?: any[]
}

/**
 * 判断字段是否应该显示。
 *
 * 支持三种写法（后端 plugins.py 直接写同构的 dict / list）：
 *   { key: 'otpType', value: 'key' }              单值
 *   { key: 'otpType', values: ['key', 'code'] }   多值
 *   [{ key: 'twoFactor', value: true }, ...]      多条件，全部满足才显示
 */
export function matchShowWhen(
  showWhen: ShowWhenCondition | ShowWhenCondition[] | undefined,
  input: Record<string, any>
): boolean {
  if (!showWhen) return true
  const conditions = Array.isArray(showWhen) ? showWhen : [showWhen]
  return conditions.every((condition) => {
    const current = input?.[condition.key]
    if (Array.isArray(condition.values)) return condition.values.includes(current)
    if (condition.value !== undefined) return current === condition.value
    return true
  })
}
