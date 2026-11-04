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
import { i18n } from '@/locales'

export type TagType = 'success' | 'danger' | 'warning' | 'info' | 'primary'

/**
 * 取当前语言文案
 *
 * ⚠️ 一律在**函数体内**调用，不要在模块顶层求值：
 * 模块顶层会在首次 import 时定死语言，切语言后不跟随。
 */
function t(key: string, named?: Record<string, unknown>): string {
  const tr = i18n.global.t as unknown as (k: string, n?: Record<string, unknown>) => string
  return named ? tr(key, named) : tr(key)
}

export interface StatusMeta {
  text: string
  type: TagType
  icon: string
}

/** 流水线 / 执行记录状态 */
export function runStatusMeta(status?: string): StatusMeta {
  switch (status) {
    case 'success':
      return { text: t('certd.status.success'), type: 'success', icon: 'ri:checkbox-circle-line' }
    case 'failed':
      return { text: t('certd.status.failed'), type: 'danger', icon: 'ri:close-circle-line' }
    case 'running':
      return { text: t('certd.status.running'), type: 'warning', icon: 'ri:loader-4-line' }
    case 'canceled':
      return { text: t('certd.status.canceled'), type: 'info', icon: 'ri:stop-circle-line' }
    case 'skipped':
      return { text: t('certd.status.skipped'), type: 'info', icon: 'ri:skip-forward-line' }
    case 'disabled':
      return { text: t('certd.status.disabled'), type: 'info', icon: 'ri:pause-circle-line' }
    case 'unlinked':
      return { text: t('certd.status.unlinked'), type: 'info', icon: 'ri:link-unlink' }
    default:
      return { text: t('certd.status.pending'), type: 'info', icon: 'ri:subtract-line' }
  }
}

/**
 * 证书状态（按剩余天数分档，比只看 valid/expired 更有用）
 *
 * ⚠️ 英文下 `{days}d left` 比中文「剩余 N 天」长，标签会变宽。
 * 表格里的状态列宽度是按中文定的，见 assets/styles/core/shadcn-ui.scss 里
 * `.el-tag` 的 `white-space: nowrap` + 表格列的 `min-width`，不要改成会换行的写法。
 */
export function certStatusMeta(daysLeft: number | null | undefined): StatusMeta {
  if (daysLeft === null || daysLeft === undefined) {
    return { text: t('certd.status.unknown'), type: 'info', icon: 'ri:question-line' }
  }
  const text = t('certd.status.expiringSoon', { days: daysLeft })
  if (daysLeft < 0) return { text: t('certd.status.expired'), type: 'danger', icon: 'ri:error-warning-line' }
  if (daysLeft <= 7) return { text, type: 'danger', icon: 'ri:alarm-line' }
  if (daysLeft <= 30) return { text, type: 'warning', icon: 'ri:time-line' }
  return { text, type: 'success', icon: 'ri:shield-check-line' }
}

/** 站点监控状态 */
export function siteStatusMeta(status?: string): StatusMeta {
  switch (status) {
    case 'ok':
      return { text: t('certd.status.valid'), type: 'success', icon: 'ri:checkbox-circle-line' }
    case 'error':
      return { text: t('certd.status.error'), type: 'danger', icon: 'ri:error-warning-line' }
    default:
      return { text: t('certd.status.undetected'), type: 'info', icon: 'ri:question-line' }
  }
}

/** 触发方式 */
export function triggerText(type?: string): string {
  const map: Record<string, string> = {
    manual: t('certd.trigger.manual'),
    timer: t('certd.trigger.timer'),
    webhook: t('certd.trigger.webhook'),
    openapi: t('certd.trigger.openapi'),
  }
  return map[type || ''] || type || '-'
}

/**
 * 耗时：后端给秒
 *
 * 英文用 `1h 5m` / `1m 20s` 这种紧凑写法，
 * 中文保持「1 时 5 分」—— 两者宽度接近，表格不会因为切语言而抖动。
 */
export function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds < 0) return '-'
  if (seconds < 60) return t('certd.time.second', { n: Math.round(seconds) })
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes < 60) return t('certd.time.minuteSecond', { m: minutes, s: rest })
  return t('certd.time.hourMinute', { h: Math.floor(minutes / 60), m: minutes % 60 })
}

/** 资源使用率分档：正常 / 偏高 / 告警（CPU、内存、硬盘仪表共用同一套阈值） */
export type UsageLevel = 'normal' | 'warn' | 'alarm'

/**
 * 使用率 → 颜色
 * 走 shadcn 语义令牌（--success / --warning / --destructive），
 * 不再硬编码 Element 那套 #67c23a / #e6a23c / #f56c6c ——
 * 那三色在浅底上对比度只有 2.19，属于「看得见但读不清」。
 */
export const USAGE_LEVEL_COLOR: Record<UsageLevel, string> = {
  normal: 'var(--success)',
  warn: 'var(--warning)',
  alarm: 'var(--destructive)',
}

/** 使用率 → 分档：≥90% 告警、≥70% 偏高、其余正常 */
export function usageLevel(percent?: number | string | null): UsageLevel {
  const value = Number(percent) || 0
  if (value >= 90) return 'alarm'
  if (value >= 70) return 'warn'
  return 'normal'
}

/** 使用率 → 颜色 */
export function usageColor(percent?: number | string | null): string {
  return USAGE_LEVEL_COLOR[usageLevel(percent)]
}

/** 使用率 → 状态词 */
export function usageText(percent?: number | string | null): string {
  const level = usageLevel(percent)
  if (level === 'alarm') return t('certd.usage.alarm')
  if (level === 'warn') return t('certd.usage.warn')
  return t('certd.usage.normal')
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

/**
 * 阶段大类元信息
 *
 * ⚠️ `text` 这里**不能**做静态翻译。
 * certd.ts 是模块级单例，如果写成 `text: t('certd.stage.cert')`，
 * 会在首次 import 时就把当时的语言「烤死」进对象，切语言后不跟随。
 * 所以这里只存 `textKey`，取文案一律走 {@link stageKindText}。
 */
export interface StageKindMeta {
  key: 'cert' | 'deploy' | 'notify'
  textKey: string
  color: string
  icon: string
}

export const STAGE_KIND_META: Record<'cert' | 'deploy' | 'notify', StageKindMeta> = {
  /**
   * 环节色按 AGENTS 8.1 固定：申请蓝 / 部署绿 / 通知橙。
   * 但取的是 shadcn-tokens 里新增的 --stage-* 语义令牌（Tailwind 600/700 档的低饱和值），
   * 不再是 Material 的 #409eff / #67c23a / #e6a23c；
   * 暗色下由令牌自动提亮，这里不用再写第二套。
   *
   * 只用在图标 / 小徽标 / 3px 描边这类「点状强调」上；
   * 阶段标题、正文仍是 foreground，别把它们也染成彩色。
   */
  cert: {
    key: 'cert',
    textKey: 'certd.stage.cert',
    color: 'var(--stage-cert)',
    icon: 'ri:file-shield-2-line',
  },
  deploy: {
    key: 'deploy',
    textKey: 'certd.stage.deploy',
    color: 'var(--stage-deploy)',
    icon: 'ri:rocket-2-line',
  },
  notify: {
    key: 'notify',
    textKey: 'certd.stage.notify',
    color: 'var(--stage-notify)',
    icon: 'ri:notification-3-line',
  },
}

/** 阶段大类 → 当前语言文案（渲染时调用，切语言自动跟随） */
export function stageKindText(meta: StageKindMeta): string {
  return t(meta.textKey)
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

/**
 * cron 常用预设（新建定时器时给用户点选，不用背表达式）
 *
 * `desc` 只放表达式本身，给人看「选了哪条规则」；
 * `label` 是自然语言说明，取词走 {@link cronPresetLabel}。
 */
export const CRON_PRESETS: { labelKey: string; value: string; desc: string }[] = [
  { labelKey: 'certd.cron.dailyAt3', value: '0 3 * * *', desc: '0 3 * * *' },
  { labelKey: 'certd.cron.dailyAt1', value: '0 1 * * *', desc: '0 1 * * *' },
  { labelKey: 'certd.cron.every6h', value: '0 */6 * * *', desc: '0 */6 * * *' },
  { labelKey: 'certd.cron.weeklyMon2', value: '0 2 * * 1', desc: '0 2 * * 1' },
  { labelKey: 'certd.cron.monthly1st2', value: '0 2 1 * *', desc: '0 2 1 * *' },
]

/** cron 预设 → 当前语言说明 */
export function cronPresetLabel(preset: { labelKey: string }): string {
  return t(preset.labelKey)
}

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
