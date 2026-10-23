/**
 * 执行日志的 SSE 客户端
 * =====================
 * 一次连接，三种用法：
 *   1. 整条流水线的日志（总览）；
 *   2. 按阶段拆分（每个阶段卡片下方独立显示）；
 *   3. 按任务过滤（点任务图标弹出该任务的日志）。
 *
 * 为什么不用 EventSource：它带不了 Authorization 头，这里用 fetch + ReadableStream 自己解析。
 * 日志里含用户填的域名与密钥路径，**只做分词渲染，禁止 v-html**。
 *
 * @module views/certd/composables/use-run-log
 */
import { apiUrl } from '@/api/certd'
import { useUserStore } from '@/store/modules/user'

/** 任务执行状态（来自 SSE 的 tasks 事件） */
export interface RunLogTask {
  taskId?: string
  title?: string
  stage?: string
  status?: string
  message?: string
  duration?: number
}

/** 一个阶段的日志分组 */
export interface StageLog {
  /** 阶段标题（与流水线里的阶段名一致） */
  title: string
  lines: string[]
}

const STAGE_MARKER = /^\[\d{2}:\d{2}:\d{2}\]\s*=+\s*阶段[:：](.+?)\s*=+\s*$/

export function useRunLog() {
  const userStore = useUserStore()

  const lines = ref<string[]>([])
  const tasks = ref<RunLogTask[]>([])
  const status = ref('')
  const historyId = ref<number | null>(null)
  const connected = ref(false)

  let controller: AbortController | null = null

  /** 按「===== 阶段：xxx =====」把日志切成阶段分组 */
  const stageLogs = computed<StageLog[]>(() => {
    const groups: StageLog[] = []
    let current: StageLog | null = null
    for (const line of lines.value) {
      const match = STAGE_MARKER.exec(line)
      if (match) {
        current = { title: match[1].trim(), lines: [line] }
        groups.push(current)
        continue
      }
      if (!current) {
        // 第一个阶段标记之前的行（流水线开始、触发方式等）归到「准备」分组
        if (!groups.length) {
          current = { title: '', lines: [] }
          groups.push(current)
        } else {
          current = groups[0]
        }
      }
      current.lines.push(line)
    }
    return groups
  })

  /** 正在执行的阶段：取「状态为 running 的任务」所属阶段 */
  const runningStage = computed(() => {
    const task = tasks.value.find((item) => item.status === 'running')
    return task?.stage || ''
  })

  /** 该阶段是否有日志 */
  const stageLines = (title: string): string[] => {
    if (!title) return []
    const matched = stageLogs.value.find((group) => group.title === title)
    return matched ? matched.lines : []
  }

  /** 某个任务自己的日志行（按 [任务名] 前缀过滤；没有就退回整阶段） */
  const taskLines = (taskTitle: string, stageTitle = ''): string[] => {
    if (!taskTitle) return []
    const scope = stageTitle ? stageLines(stageTitle) : lines.value
    const hit = scope.filter((line) => line.includes('[' + taskTitle + ']'))
    return hit.length ? hit : scope
  }

  const clear = () => {
    lines.value = []
  }

  const stop = () => {
    controller?.abort()
    controller = null
    connected.value = false
  }

  /** 解析一帧 SSE：可能带 event: xxx + data: {...} */
  const handleFrame = (frame: string) => {
    let event = ''
    const dataLines: string[] = []
    for (const raw of frame.split('\n')) {
      const line = raw.replace(/\r$/, '')
      if (!line || line.startsWith(':')) continue
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (!dataLines.length) return
    let payload: Record<string, any>
    try {
      payload = JSON.parse(dataLines.join('\n'))
    } catch {
      return
    }
    if (event === 'tasks') {
      tasks.value = (payload.tasks || []) as RunLogTask[]
      if (payload.status) status.value = payload.status
      return
    }
    if (event === 'status' || event === 'end') {
      status.value = payload.status || status.value
      if (event === 'end') connected.value = false
      return
    }
    if (typeof payload.line === 'string') lines.value.push(payload.line)
  }

  const connect = async (id: number | null | undefined) => {
    stop()
    lines.value = []
    tasks.value = []
    status.value = ''
    historyId.value = id || null
    if (!id) return

    const abort = new AbortController()
    controller = abort
    connected.value = true
    try {
      const res = await fetch(apiUrl('/api/history/' + id + '/stream?offset=0'), {
        headers: { Authorization: userStore.accessToken },
        signal: abort.signal,
      })
      if (!res.ok || !res.body) {
        lines.value.push('日志流连接失败（HTTP ' + res.status + '）')
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let index = buffer.indexOf('\n\n')
        while (index !== -1) {
          handleFrame(buffer.slice(0, index))
          buffer = buffer.slice(index + 2)
          index = buffer.indexOf('\n\n')
        }
      }
    } catch (error: any) {
      if (error?.name !== 'AbortError') {
        lines.value.push('日志流中断：' + (error?.message || error))
      }
    } finally {
      if (controller === abort) {
        controller = null
        connected.value = false
      }
    }
  }

  onUnmounted(stop)

  return {
    lines,
    tasks,
    status,
    historyId,
    connected,
    stageLogs,
    runningStage,
    stageLines,
    taskLines,
    connect,
    stop,
    clear,
  }
}
