import { useEffect, useRef, useState } from 'react'
import { getToken } from './http'

export interface RunLogState {
  lines: string[]
  status: string
  tasks: Record<string, unknown>[]
  connected: boolean
}

/** 执行日志走 SSE，但 EventSource 不能带 Authorization，所以用 fetch 流自己解析 */
export function useRunLog(historyId: number | null) {
  const [state, setState] = useState<RunLogState>({ lines: [], status: '', tasks: [], connected: false })
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!historyId) {
      setState({ lines: [], status: '', tasks: [], connected: false })
      return
    }

    const controller = new AbortController()
    controllerRef.current = controller
    setState({ lines: [], status: 'running', tasks: [], connected: true })

    const run = async () => {
      try {
        const response = await fetch(`/api/history/${historyId}/stream`, {
          headers: { Authorization: getToken(), Accept: 'text/event-stream' },
          signal: controller.signal,
        })
        if (!response.ok || !response.body) throw new Error(`日志流打开失败（HTTP ${response.status}）`)

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          let boundary = buffer.indexOf('\n\n')
          while (boundary >= 0) {
            const raw = buffer.slice(0, boundary)
            buffer = buffer.slice(boundary + 2)
            boundary = buffer.indexOf('\n\n')

            let event = 'message'
            let data = ''
            for (const line of raw.split('\n')) {
              if (line.startsWith('event:')) event = line.slice(6).trim()
              else if (line.startsWith('data:')) data += line.slice(5).trim()
            }
            if (!data) continue

            try {
              const payload = JSON.parse(data) as Record<string, unknown>
              if (event === 'tasks') {
                setState((prev) => ({ ...prev, tasks: (payload.tasks as Record<string, unknown>[]) || [] }))
              } else if (event === 'status') {
                setState((prev) => ({ ...prev, status: String(payload.status || prev.status) }))
              } else if (event === 'end') {
                setState((prev) => ({ ...prev, status: String(payload.status || prev.status), connected: false }))
                return
              } else if (typeof payload.line === 'string') {
                const line = payload.line
                setState((prev) => ({ ...prev, lines: [...prev.lines, line] }))
              }
            } catch {
              // 非 JSON 的心跳行直接忽略
            }
          }
        }
        setState((prev) => ({ ...prev, connected: false }))
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          setState((prev) => ({
            ...prev,
            connected: false,
            lines: [...prev.lines, `[连接中断] ${(error as Error).message}`],
          }))
        }
      }
    }

    void run()
    return () => controller.abort()
  }, [historyId])

  return state
}
