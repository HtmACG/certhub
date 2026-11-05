import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  CirclePlus,
  Copy,
  GripVertical,
  Info,
  Link2,
  Pencil,
  Play,
  Plus,
  Power,
  PowerOff,
  Save,
  ScrollText,
  Settings2,
  Trash2,
  Workflow,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  createPipeline,
  fetchAccessList,
  fetchPipelineDetail,
  fetchPluginMeta,
  runPipeline,
  runStage,
  updatePipeline,
} from '@/lib/api'
import type { PipelineContent, PipelineStage, PipelineTask, PluginField, TaskPlugin } from '@/lib/types'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label, Select, Textarea, Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { StatusBadge } from '@/components/status'
import { SchemaFields } from '@/components/schema-form'
import { LogTerminal } from '@/components/log-terminal'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { EmptyState, Skeleton } from '@/components/ui/empty'
import { PluginLogo } from '@/components/plugin-logo'
import { PipelineCanvas, MAX_TASKS_PER_STAGE, type CanvasContextTarget, type TaskRunState } from './pipeline-canvas'
import { TaskPalette } from './task-palette'
import { ScheduleDialog, describeCron, type ScheduleValue } from './schedule-dialog'
import { useRunLog } from '@/lib/use-run-log'
import type { Edge } from '@xyflow/react'
import { cn } from '@/lib/utils'

const STAGE_TONE = ['var(--stage-cert)', 'var(--stage-deploy)', 'var(--stage-notify)'] as const

function newId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`
}

function defaultsFor(fields: PluginField[]) {
  const values: Record<string, unknown> = {}
  fields.forEach((field) => {
    if (field.default !== undefined) values[field.key] = field.default
  })
  return values
}

/** 日志按「===== 阶段：X =====」切成段，第一段（阶段标记之前）是运行准备 */
function splitStageLogs(lines: string[]) {
  const groups: { title: string; lines: string[] }[] = [{ title: '', lines: [] }]
  lines.forEach((line) => {
    const match = line.match(/=====\s*阶段：(.+?)\s*=====/)
    if (match) groups.push({ title: match[1], lines: [] })
    else groups[groups.length - 1].lines.push(line)
  })
  return groups
}

function EditableTitle({ value, onSave }: { value: string; onSave: (next: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)

  useEffect(() => {
    setDraft(value)
  }, [value])

  const commit = () => {
    const next = draft.trim()
    setEditing(false)
    if (!next || next === value) {
      setDraft(value)
      return
    }
    onSave(next)
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        title="点击修改标题"
        className="group flex max-w-full items-center gap-2 text-left"
      >
        <span className="truncate">{value}</span>
        <Pencil className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </button>
    )
  }

  return (
    <input
      autoFocus
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') commit()
        if (event.key === 'Escape') {
          setDraft(value)
          setEditing(false)
        }
      }}
      className="w-full min-w-[240px] rounded-md border border-input bg-background px-2 py-1 text-xl font-semibold tracking-tight outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    />
  )
}

export function PipelineEditorPage() {
  const params = useParams()
  const id = Number(params.id)
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()

  const detail = useQuery({ queryKey: ['pipeline', id], queryFn: () => fetchPipelineDetail(id), enabled: Number.isFinite(id) })
  const meta = useQuery({ queryKey: ['plugin-meta'], queryFn: fetchPluginMeta, staleTime: 10 * 60_000 })
  const accessList = useQuery({ queryKey: ['access-options'], queryFn: () => fetchAccessList({ current: 1, size: 200 }) })

  const [title, setTitle] = useState('')
  const [remark, setRemark] = useState('')
  const [content, setContent] = useState<PipelineContent | null>(null)
  const [dirty, setDirty] = useState(false)
  const [historyId, setHistoryId] = useState<number | null>(() => {
    const value = Number(searchParams.get('history'))
    return Number.isFinite(value) && value > 0 ? value : null
  })

  const [pickerStage, setPickerStage] = useState<string | null>(null)
  const [view, setView] = useState<'canvas' | 'list'>(() =>
    localStorage.getItem('certhub.pipelineView') === 'list' ? 'list' : 'canvas',
  )
  const [pickerGroup, setPickerGroup] = useState('cert')
  const [editing, setEditing] = useState<{ stageId: string; task: PipelineTask } | null>(null)
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [errorTarget, setErrorTarget] = useState('')
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const [linkedDraft, setLinkedDraft] = useState(true)
  const [logView, setLogView] = useState<{ title: string; lines: string[] } | null>(null)
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null)
  const [highlightTaskId, setHighlightTaskId] = useState<string | null>(null)
  const [menu, setMenu] = useState<CanvasContextTarget | null>(null)
  const [edgeToRemove, setEdgeToRemove] = useState<Edge | null>(null)
  const [logOpen, setLogOpen] = useState(true)
  const [infoOpen, setInfoOpen] = useState(false)

  const openTask = (stageId: string, task: PipelineTask) => {
    setEditing({ stageId, task })
    setDraft({ ...task.input })
    setErrorTarget(task.onErrorTaskId || '')
    setLinkedDraft(task.linked !== false)
  }

  useEffect(() => {
    if (!detail.data) return
    setTitle(detail.data.title)
    setRemark(detail.data.remark || '')
    setContent(detail.data.content)
    setDirty(false)
  }, [detail.data])

  /** 连上之后卡片闪一下，用户能确认线接的是哪一张卡 */
  useEffect(() => {
    if (!highlightTaskId) return
    const timer = window.setTimeout(() => setHighlightTaskId(null), 1600)
    return () => window.clearTimeout(timer)
  }, [highlightTaskId])

  const log = useRunLog(historyId)

  /** SSE 推来的任务状态：画布和列表都按它标红 / 标绿 */
  const runTasks = useMemo(() => {
    const map = new Map<string, TaskRunState>()
    log.tasks.forEach((item) => {
      const taskId = typeof item.taskId === 'string' ? item.taskId : ''
      if (!taskId) return
      map.set(taskId, {
        status: String(item.status || ''),
        message: item.message ? String(item.message) : undefined,
      })
    })
    return map
  }, [log.tasks])

  /** 列表视图也要能看出「第 N 步」：只数已接入的任务，和画布口径一致 */
  const seqById = useMemo(() => {
    const map = new Map<string, number>()
    let step = 0
    content?.stages.forEach((stage) =>
      stage.tasks.forEach((task) => {
        if (task.linked === false) return
        step += 1
        map.set(task.id, step)
      }),
    )
    return map
  }, [content])

  const save = useMutation({
    mutationFn: () =>
      updatePipeline(id, {
        title,
        remark,
        content,
        type: detail.data?.type ?? 'cert_apply',
        disabled: detail.data?.disabled ?? false,
        keepHistoryCount: detail.data?.keepHistoryCount ?? 20,
      }),
    onSuccess: () => {
      toast.success('已保存')
      setDirty(false)
      void queryClient.invalidateQueries({ queryKey: ['pipeline', id] })
      void queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const timerTrigger = content?.triggers?.find((trigger) => trigger.type === 'timer')

  const buildTriggers = (cron: string, enabled: boolean) => {
    const base = content?.triggers ?? []
    const others = base.filter((trigger) => trigger.type !== 'timer')
    const existing = base.find((trigger) => trigger.type === 'timer')
    const timer = enabled && cron ? [{ id: existing?.id || 'trigger-timer', type: 'timer', cron, enabled: true }] : []
    return [...others, ...timer]
  }

  const saveSchedule = useMutation({
    mutationFn: (value: ScheduleValue) => {
      if (!content) return Promise.reject(new Error('流水线还没加载完'))
      return updatePipeline(id, {
        title,
        remark,
        content: { ...content, triggers: buildTriggers(value.cron, value.enabled) },
        type: detail.data?.type ?? 'cert_apply',
        disabled: detail.data?.disabled ?? false,
        keepHistoryCount: detail.data?.keepHistoryCount ?? 20,
      })
    },
    onSuccess: (_data, value) => {
      setContent((prev) => (prev ? { ...prev, triggers: buildTriggers(value.cron, value.enabled) } : prev))
      setScheduleOpen(false)
      setDirty(false)
      toast.success(value.enabled && value.cron ? `已设置为${describeCron(value.cron)}` : '已关闭定时运行')
      void queryClient.invalidateQueries({ queryKey: ['pipeline', id] })
      void queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const rename = useMutation({
    mutationFn: (next: string) =>
      updatePipeline(id, {
        title: next,
        remark,
        content: content ?? { stages: [], triggers: [] },
        type: detail.data?.type ?? 'cert_apply',
        disabled: detail.data?.disabled ?? false,
        keepHistoryCount: detail.data?.keepHistoryCount ?? 20,
      }),
    onSuccess: (_data, next) => {
      setTitle(next)
      toast.success('标题已更新')
      void queryClient.invalidateQueries({ queryKey: ['pipeline', id] })
      void queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const run = useMutation({
    mutationFn: () => runPipeline(id),
    onSuccess: (data) => {
      setHistoryId(data.historyId)
      setSearchParams({ history: String(data.historyId) }, { replace: true })
      toast.success('已开始运行')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const runStageNow = useMutation({
    mutationFn: (stageId: string) => runStage(id, stageId),
    onSuccess: (data) => {
      setHistoryId(data.historyId)
      setSearchParams({ history: String(data.historyId) }, { replace: true })
      toast.success('已开始运行本阶段')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const saveAndRun = useMutation({
    mutationFn: async () => {
      if (!content) throw new Error('流水线还没加载完')
      await updatePipeline(id, {
        title,
        remark,
        content,
        type: detail.data?.type ?? 'cert_apply',
        disabled: detail.data?.disabled ?? false,
        keepHistoryCount: detail.data?.keepHistoryCount ?? 20,
      })
      return runPipeline(id)
    },
    onSuccess: (data) => {
      setDirty(false)
      setHistoryId(data.historyId)
      setSearchParams({ history: String(data.historyId) }, { replace: true })
      toast.success('已保存并开始运行')
      void queryClient.invalidateQueries({ queryKey: ['pipeline', id] })
    },
    onError: (error: Error) => toast.error(error.message),
  })

  /** Ctrl/Cmd + S 保存，不用去点按钮 */
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        if (dirty && !save.isPending) save.mutate()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [dirty, save])

  /** 点别处 / 滚动 / Esc 关掉右键菜单 */
  useEffect(() => {
    if (!menu) return
    const close = () => setMenu(null)
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('click', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('keydown', onKey)
    }
  }, [menu])

  const createEmpty = useMutation({
    mutationFn: () => createPipeline({ title: '未命名流水线', content: { stages: [], triggers: [] } }),
  })

  const plugins = meta.data?.plugins ?? []
  const pluginByType = useMemo(() => new Map(plugins.map((plugin) => [plugin.type, plugin])), [plugins])
  const accessOptions = useMemo(
    () => (accessList.data?.records ?? []).map((item) => ({ id: item.id, name: item.name, type: item.type, category: item.category })),
    [accessList.data],
  )

  const updateStage = (stageId: string, patch: Partial<PipelineStage>) => {
    setContent((prev) =>
      prev ? { ...prev, stages: prev.stages.map((stage) => (stage.id === stageId ? { ...stage, ...patch } : stage)) } : prev,
    )
    setDirty(true)
  }

  const updateTask = (stageId: string, taskId: string, patch: Partial<PipelineTask>) => {
    setContent((prev) =>
      prev
        ? {
            ...prev,
            stages: prev.stages.map((stage) =>
              stage.id === stageId
                ? { ...stage, tasks: stage.tasks.map((task) => (task.id === taskId ? { ...task, ...patch } : task)) }
                : stage,
            ),
          }
        : prev,
    )
    setDirty(true)
  }

  /** 按任务 id 改一处（画布连线不用关心它属于哪个阶段） */
  const patchTask = (taskId: string, patch: Partial<PipelineTask>) => {
    setContent((prev) =>
      prev
        ? {
            ...prev,
            stages: prev.stages.map((stage) => ({
              ...stage,
              tasks: stage.tasks.map((task) => (task.id === taskId ? { ...task, ...patch } : task)),
            })),
          }
        : prev,
    )
    setDirty(true)
  }

  /**
   * 画布上拖出来的连线：
   * - 从「成功」出口拖到任务 = 把这个任务接入执行链（等价于列表里的「接入流程」按钮）
   * - 从「失败」出口拖到任务 = 给源任务设置「失败后跳转到」
   * 顺序永远由「阶段顺序 + 阶段内顺序」决定，所以只接受指向后面任务的连线。
   */
  const connectTasks = (sourceId: string, sourceHandle: string | null, targetId: string) => {
    if (!content) return
    const flat = content.stages.flatMap((stage) => stage.tasks)
    const sourceAt = flat.findIndex((task) => task.id === sourceId)
    const targetAt = flat.findIndex((task) => task.id === targetId)
    // 连到阶段容器之类的目标：不是任务，直接忽略
    if (sourceAt < 0 || targetAt < 0) return
    if (targetAt <= sourceAt) {
      toast.error('只能连到排在后面的任务（顺序 = 阶段顺序 + 阶段内顺序）')
      return
    }
    const target = flat[targetAt]
    const targetName = target.title || pluginByType.get(target.type)?.name || target.type

    if (sourceHandle === 'error') {
      const occupied = flat.find((task) => task.onErrorTaskId === targetId && task.id !== sourceId)
      if (occupied) {
        toast.error(`「${occupied.title || occupied.type}」已经接了这条失败线，一个目标只能接一条`)
        return
      }
      patchTask(sourceId, { onErrorTaskId: targetId })
      setHighlightTaskId(targetId)
      toast.success(`已接上「失败后 → ${targetName}」，记得保存`)
      return
    }

    if (target.linked !== false) {
      toast.info(`「${targetName}」已经在执行链里了`)
      return
    }
    const step = flat.slice(0, targetAt).filter((task) => task.linked !== false).length + 1
    patchTask(targetId, { linked: true })
    setHighlightTaskId(targetId)
    toast.success(`已把「${targetName}」接入执行链（第 ${step} 步），保存后生效`)
  }

  /** 删除阶段：画布和列表共用，先确认 */
  const removeStage = (stageId: string) => {
    const stage = content?.stages.find((item) => item.id === stageId)
    if (!stage) return
    const count = stage.tasks.length
    if (!confirm(`删除阶段「${stage.title}」${count ? `以及里面的 ${count} 个任务` : ''}？`)) return
    setContent((prev) => (prev ? { ...prev, stages: prev.stages.filter((item) => item.id !== stageId) } : prev))
    setDirty(true)
  }

  const removeTask = (_stageId: string, taskId: string) => {
    setContent((prev) =>
      prev
        ? {
            ...prev,
            stages: prev.stages.map((stage) => ({
              ...stage,
              tasks: stage.tasks
                .filter((task) => task.id !== taskId)
                // 删掉的任务可能被别的任务当作「失败后」目标，顺手清掉悬空引用
                .map((task) => (task.onErrorTaskId === taskId ? { ...task, onErrorTaskId: undefined } : task)),
            })),
          }
        : prev,
    )
    setDirty(true)
  }

  /** 删除任务：先确认，removeTask 顺手清掉指向它的「失败后」引用 */
  const removeTaskWithConfirm = (stageId: string, taskId: string) => {
    const task = content?.stages.flatMap((item) => item.tasks).find((item) => item.id === taskId)
    if (!task) return
    if (!confirm(`删除任务「${task.title || task.type}」？`)) return
    removeTask(stageId, taskId)
  }

  /** 看某个阶段的日志：按阶段标记切段 */
  const openStageLog = (stageId: string) => {
    const stage = content?.stages.find((item) => item.id === stageId)
    if (!stage) return
    const group = splitStageLogs(log.lines).find((item) => item.title === stage.title)
    setLogView({ title: `阶段：${stage.title}`, lines: group?.lines ?? [] })
  }

  /** 看某个任务的日志：执行日志里每条都带 [任务名] 前缀 */
  const openTaskLog = (taskId: string) => {
    const task = content?.stages.flatMap((item) => item.tasks).find((item) => item.id === taskId)
    if (!task) return
    const title = task.title || pluginByType.get(task.type)?.name || task.type
    setLogView({ title: `任务：${title}`, lines: log.lines.filter((line) => line.includes(`[${title}]`)) })
  }

  const startRenameStage = (stageId: string) => {
    const stage = content?.stages.find((item) => item.id === stageId)
    if (stage) setRenaming({ id: stage.id, title: stage.title })
  }

  const commitRename = () => {
    if (!renaming) return
    const next = renaming.title.trim()
    if (!next) {
      toast.error('阶段名称不能为空')
      return
    }
    updateStage(renaming.id, { title: next })
    setRenaming(null)
    toast.success('已重命名，记得保存')
  }

  /** 点连线：先弹确认框，确认后才改草稿 */
  const askRemoveEdge = (edge: Edge) => setEdgeToRemove(edge)

  const confirmRemoveEdge = () => {
    const edge = edgeToRemove
    if (!edge) return
    if (edge.id.startsWith('ok-')) {
      patchTask(edge.target, { linked: false })
      toast.success('已断开连线，记得保存')
    } else if (edge.id.startsWith('err-')) {
      patchTask(edge.source, { onErrorTaskId: undefined })
      toast.success('已删除「失败后」连线，记得保存')
    }
    setEdgeToRemove(null)
  }

  /** 拖动阶段后写回坐标：网格对齐由画布的 snapGrid 负责，这里只落库 */
  const moveStagePos = (stageId: string, position: { x: number; y: number }) => {
    setContent((prev) =>
      prev
        ? {
            ...prev,
            layout: {
              ...prev.layout,
              stages: { ...prev.layout?.stages, [stageId]: position },
            },
          }
        : prev,
    )
    setDirty(true)
  }

  /** 复制任务：参数一起复制，默认不接入，避免悄悄改变执行链 */
  const duplicateTask = (taskId: string) => {
    if (!content) return
    const stage = content.stages.find((item) => item.tasks.some((task) => task.id === taskId))
    if (!stage) return
    const index = stage.tasks.findIndex((task) => task.id === taskId)
    const source = stage.tasks[index]
    const title = `${source.title || pluginByType.get(source.type)?.name || source.type} 副本`
    const copy: PipelineTask = { ...source, id: newId('task'), title, input: { ...source.input }, linked: false }
    const tasks = [...stage.tasks]
    tasks.splice(index + 1, 0, copy)
    setContent({ ...content, stages: content.stages.map((item) => (item.id === stage.id ? { ...item, tasks } : item)) })
    setDirty(true)
    toast.success(`已复制「${title}」，还没接入执行链`)
  }

  /**
   * 从右侧任务列表添加：拖到某个阶段就加到哪里，点击则加到第一个阶段（没有阶段就建一个）。
   * 建完直接打开配置，少一次点击。
   */
  const addFromPalette = (stageId: string, type: string) => {
    const plugin = pluginByType.get(type)
    if (!plugin) {
      toast.error('这个任务类型不在插件表里，刷新一下试试')
      return
    }
    const base = content ?? { stages: [], triggers: [] }
    const stages = base.stages.length
      ? [...base.stages]
      : [{ id: newId('stage'), title: '阶段 1', tasks: [] }]
    const targetId = stages.some((item) => item.id === stageId) ? stageId : stages[0].id
    const target = stages.find((item) => item.id === targetId)
    if (!target) return
    if (target.tasks.length >= MAX_TASKS_PER_STAGE) {
      toast.error(`每个阶段最多 ${MAX_TASKS_PER_STAGE} 个任务`)
      return
    }
    const task: PipelineTask = {
      id: newId('task'),
      type: plugin.type,
      title: plugin.name,
      input: defaultsFor(plugin.inputs),
      enabled: true,
      linked: false,
    }
    setContent({
      ...base,
      stages: stages.map((item) => (item.id === targetId ? { ...item, tasks: [...item.tasks, task] } : item)),
    })
    setDirty(true)
    openTask(targetId, task)
  }

  /** 右键菜单项：按点中的对象给出可用操作 */
  type MenuItem = { icon: typeof Plus; label: string; run: () => void; danger?: boolean; disabled?: boolean }
  const getMenuItems = (): MenuItem[] => {
    if (!menu) return []
    if (menu.kind === 'task') {
      const stage = content?.stages.find((item) => item.id === menu.stageId)
      const task = stage?.tasks.find((item) => item.id === menu.taskId)
      if (!task || !stage) return []
      return [
        { icon: Settings2, label: '配置参数', run: () => openTask(stage.id, task) },
        { icon: Copy, label: '复制任务', run: () => duplicateTask(task.id) },
        { icon: ScrollText, label: '查看日志', run: () => openTaskLog(task.id) },
        {
          icon: task.enabled === false ? Power : PowerOff,
          label: task.enabled === false ? '启用' : '停用',
          run: () => patchTask(task.id, { enabled: task.enabled === false }),
        },
        {
          icon: Trash2,
          label: '删除任务',
          danger: true,
          run: () => removeTaskWithConfirm(stage.id, task.id),
        },
      ]
    }
    if (menu.kind === 'stage') {
      const stage = content?.stages.find((item) => item.id === menu.stageId)
      if (!stage) return []
      return [
        {
          icon: Plus,
          label: '添加任务',
          run: () => {
            setPickerStage(stage.id)
            setPickerGroup(stage.tasks.length === 0 ? 'cert' : 'deploy')
          },
        },
        {
          icon: Play,
          label: '单独运行本阶段',
          disabled: stage.enabled === false || !stage.tasks.some((task) => task.enabled !== false && task.linked !== false),
          run: () => runStageNow.mutate(stage.id),
        },
        { icon: ScrollText, label: '查看本阶段日志', run: () => openStageLog(stage.id) },
        { icon: Pencil, label: '重命名', run: () => startRenameStage(stage.id) },
        {
          icon: stage.enabled === false ? Power : PowerOff,
          label: stage.enabled === false ? '启用阶段' : '停用阶段',
          run: () => updateStage(stage.id, { enabled: stage.enabled === false }),
        },
        { icon: Trash2, label: '删除阶段', danger: true, run: () => removeStage(stage.id) },
      ]
    }
    if (menu.kind === 'edge') {
      return [
        {
          icon: Trash2,
          label: menu.edge.id.startsWith('err-') ? '删除「失败后」连线' : '断开这条连线',
          danger: true,
          run: () => setEdgeToRemove(menu.edge),
        },
      ]
    }
    return [{ icon: CirclePlus, label: '添加阶段', run: addStage }]
  }

  const moveStage = (index: number, direction: -1 | 1) => {
    setContent((prev) => {
      if (!prev) return prev
      const next = [...prev.stages]
      const target = index + direction
      if (target < 0 || target >= next.length) return prev
      ;[next[index], next[target]] = [next[target], next[index]]
      return { ...prev, stages: next }
    })
    setDirty(true)
  }

  const addStage = () => {
    setContent((prev) =>
      prev
        ? {
            ...prev,
            stages: [...prev.stages, { id: newId('stage'), title: `阶段 ${prev.stages.length + 1}`, tasks: [] }],
          }
        : { stages: [{ id: newId('stage'), title: '阶段 1', tasks: [] }], triggers: [] },
    )
    setDirty(true)
  }

  const addTask = (plugin: TaskPlugin) => {
    if (!pickerStage) return
    const stage = content?.stages.find((item) => item.id === pickerStage)
    if (stage && stage.tasks.length >= MAX_TASKS_PER_STAGE) {
      toast.error(`每个阶段最多 ${MAX_TASKS_PER_STAGE} 个任务`)
      return
    }
    const task: PipelineTask = {
      id: newId('task'),
      type: plugin.type,
      title: plugin.name,
      input: defaultsFor(plugin.inputs),
      enabled: true,
      linked: false,
    }
    setContent((prev) =>
      prev
        ? { ...prev, stages: prev.stages.map((stage) => (stage.id === pickerStage ? { ...stage, tasks: [...stage.tasks, task] } : stage)) }
        : prev,
    )
    setDirty(true)
    setPickerStage(null)
    openTask(pickerStage, task)
  }

  const taskTitleById = useMemo(() => {
    const map = new Map<string, string>()
    content?.stages.forEach((stage) =>
      stage.tasks.forEach((task) => {
        map.set(task.id, task.title || pluginByType.get(task.type)?.name || task.type)
      }),
    )
    return map
  }, [content, pluginByType])

  /** 已被别的任务占用的「失败后」目标：一个目标只能接一条失败线 */
  const occupiedTargets = useMemo(() => {
    const map = new Map<string, string>()
    content?.stages.forEach((stage) =>
      stage.tasks.forEach((task) => {
        if (!task.onErrorTaskId || task.id === editing?.task.id) return
        map.set(task.onErrorTaskId, task.title || pluginByType.get(task.type)?.name || task.type)
      }),
    )
    return map
  }, [content, editing, pluginByType])

  /** 「失败后」只能指向排在后面的任务，且目标不能被别人占用，避免成环/多入边 */
  const laterTasks = useMemo(() => {
    if (!content || !editing) return [] as { id: string; title: string; occupiedBy?: string }[]
    const flat = content.stages.flatMap((stage) =>
      stage.tasks.map((task) => ({
        id: task.id,
        title: task.title || pluginByType.get(task.type)?.name || task.type,
      })),
    )
    const index = flat.findIndex((task) => task.id === editing.task.id)
    if (index < 0) return []
    return flat.slice(index + 1).map((task) => ({ ...task, occupiedBy: occupiedTargets.get(task.id) }))
  }, [content, editing, pluginByType, occupiedTargets])

  const domainSummary = useMemo(() => {
    const domains = new Set<string>()
    content?.stages.forEach((stage) =>
      stage.tasks.forEach((task) => {
        const list = task.input?.domains
        if (Array.isArray(list)) list.forEach((item) => typeof item === 'string' && domains.add(item))
      }),
    )
    return Array.from(domains)
  }, [content])

  if (detail.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-[280px] w-full" />
      </div>
    )
  }

  if (detail.isError || !content) {
    return (
      <Card>
        <EmptyState
          icon={Workflow}
          title="没有找到这条流水线"
          description="它可能已经被删除，或者链接里的编号不对。"
          action={
            createEmpty.isPending ? (
              <Button disabled>创建中…</Button>
            ) : (
              <Button onClick={() => createEmpty.mutate()}>
                <Plus />
                新建一条
              </Button>
            )
          }
        />
      </Card>
    )
  }

  const currentPlugin = editing ? pluginByType.get(editing.task.type) : undefined
  const menuItems = menu ? getMenuItems() : []
  const edgeTargetTask = edgeToRemove
    ? content?.stages.flatMap((stage) => stage.tasks).find((task) => task.id === edgeToRemove.target)
    : undefined
  const edgeTargetName = edgeTargetTask
    ? edgeTargetTask.title || pluginByType.get(edgeTargetTask.type)?.name || edgeTargetTask.type
    : '这个任务'
  const isErrorEdge = Boolean(edgeToRemove?.id.startsWith('err-'))

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/pipelines" className="inline-flex items-center gap-1 hover:text-foreground">
          <ArrowLeft className="size-3.5" />
          证书流水线
        </Link>
        <span>/</span>
        <span className="truncate">{title || '未命名'}</span>
      </div>

      <PageHeader
        title={<EditableTitle value={title || '未命名流水线'} onSave={(next) => rename.mutate(next)} />}
        description={
          <span className="flex flex-wrap items-center gap-2">
            {log.status || detail.data?.lastStatus ? (
              <StatusBadge status={log.status || detail.data?.lastStatus} />
            ) : (
              <Badge variant="muted">未运行</Badge>
            )}
            <span>{content.stages.length} 个阶段</span>
            <span>·</span>
            <span>{seqById.size} 步已接入</span>
            {content.stages.reduce((sum, stage) => sum + stage.tasks.length, 0) > seqById.size && (
              <span className="text-muted-foreground">
                （{content.stages.reduce((sum, stage) => sum + stage.tasks.length, 0) - seqById.size} 个未接入，不执行）
              </span>
            )}
            {domainSummary.length > 0 && (
              <>
                <span>·</span>
                <span className="truncate">域名 {domainSummary.join(', ')}</span>
              </>
            )}
            {dirty && <Badge variant="warning">未保存</Badge>}
          </span>
        }
        actions={
          <>
            <div className="flex h-8 items-center rounded-md border p-0.5">
              {(['canvas', 'list'] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    setView(item)
                    localStorage.setItem('certhub.pipelineView', item)
                  }}
                  className={cn(
                    'rounded px-2.5 py-1 text-xs transition-colors',
                    view === item ? 'bg-accent font-medium text-foreground' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {item === 'canvas' ? '画布' : '列表'}
                </button>
              ))}
            </div>
            <Button variant="outline" size="sm" onClick={() => setScheduleOpen(true)}>
              <CalendarClock />
              定时任务
              <Badge variant="muted">
                {timerTrigger?.cron && timerTrigger.enabled !== false ? describeCron(timerTrigger.cron) : '未设置'}
              </Badge>
            </Button>
            <Button variant="outline" size="sm" onClick={addStage}>
              <CirclePlus />
              添加阶段
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => save.mutate()}
              disabled={!dirty || save.isPending}
              title="保存（Ctrl+S）"
            >
              <Save />
              保存
            </Button>
            <Button
              size="sm"
              onClick={() => (dirty ? saveAndRun.mutate() : run.mutate())}
              disabled={saveAndRun.isPending || run.isPending || !!detail.data?.running}
              title={dirty ? '有未保存的改动：先保存再运行（Ctrl+S 只保存）' : '运行流水线'}
            >
              <Play />
              {detail.data?.running ? '运行中…' : dirty ? '保存并运行' : '运行'}
            </Button>
          </>
        }
      />

      <div className="flex h-[calc(100vh-270px)] min-h-[540px] gap-4">
        <div className="flex w-[300px] shrink-0 flex-col gap-3">
          <div className="min-h-0 flex-1">
            <TaskPalette
              plugins={plugins}
              groups={meta.data?.groups ?? []}
              onAdd={(type) => addFromPalette('', type)}
            />
          </div>
          <Card className="flex shrink-0 items-center gap-2 px-3 py-2 text-[11px] text-muted-foreground">
            <span className="truncate">
              定时 {timerTrigger?.cron && timerTrigger.enabled !== false ? describeCron(timerTrigger.cron) : '未设置'}
            </span>
            <span className="ml-auto shrink-0">
              {detail.data?.nextRunTime ? `下次 ${detail.data.nextRunTime}` : '不自动运行'}
            </span>
            <Button variant="ghost" size="icon-sm" title="流水线信息 / 备注" onClick={() => setInfoOpen(true)}>
              <Info className="size-3.5" />
            </Button>
          </Card>
        </div>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
          {content.stages.length === 0 && (
            <Card>
              <EmptyState
                icon={Workflow}
                title="这条流水线还是空的"
                description="先加一个阶段，再把申请、部署这类任务放进去。"
                action={
                  <Button size="sm" onClick={addStage}>
                    <Plus />
                    添加阶段
                  </Button>
                }
              />
            </Card>
          )}

          {content.stages.length > 0 && view === 'canvas' && (
            <>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="h-0 w-6 border-t-2 border-border" />
                  顺序执行（箭头方向）
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-0 w-6 border-t-2 border-dashed border-warning" />
                  失败后跳转
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="size-3 rounded-sm border border-dashed border-muted-foreground" />
                  虚线卡片 = 未接入，不执行
                </span>
                <span className="ml-auto">
                  拖右侧圆点连线（上「成功」/ 下「失败」）；拖阶段标题条移动，松手吸网格且不会与其它阶段重叠
                </span>
              </div>
              <div className="min-h-0 flex-1">
                <PipelineCanvas
                  content={content}
                  plugins={pluginByType}
                  running={Boolean(detail.data?.running || log.connected)}
                  runTasks={runTasks}
                  highlightTaskId={highlightTaskId}
                  onConnect={connectTasks}
                  onEditTask={(stageId, task) => {
                    openTask(stageId, task)
                  }}
                  onOpenStage={() => setView('list')}
                  onAddTask={(stageId) => {
                    setPickerStage(stageId)
                    const stage = content.stages.find((item) => item.id === stageId)
                    setPickerGroup((stage?.tasks.length ?? 0) === 0 ? 'cert' : 'deploy')
                  }}
                  onToggleStage={(stageId, enabled) => updateStage(stageId, { enabled })}
                  onRemoveStage={removeStage}
                  onToggleTask={(taskId, enabled) => patchTask(taskId, { enabled })}
                  onRemoveTask={removeTaskWithConfirm}
                  onRunStage={(stageId) => runStageNow.mutate(stageId)}
                  onStageLog={openStageLog}
                  onRenameStage={startRenameStage}
                  onTaskLog={openTaskLog}
                  onRemoveEdge={askRemoveEdge}
                  onContextMenu={setMenu}
                  onDropTask={addFromPalette}
                  layout={content.layout}
                  onMoveStage={moveStagePos}
                />
              </div>
            </>
          )}

          {view === 'list' && (
            <div className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
              {content.stages.map((stage, index) => {
            const tone = STAGE_TONE[index % STAGE_TONE.length]
            return (
              <Card key={stage.id} className="overflow-hidden">
                <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
                  <span
                    className="flex size-6 items-center justify-center rounded-full text-[11px] font-semibold text-white"
                    style={{ background: tone }}
                  >
                    {index + 1}
                  </span>
                  <input
                    value={stage.title}
                    onChange={(event) => updateStage(stage.id, { title: event.target.value })}
                    className="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm font-medium outline-none focus:ring-0"
                  />
                  <Badge variant="muted">{stage.tasks.length} 个任务</Badge>
                  <div className="flex items-center gap-1">
                    <Switch
                      checked={stage.enabled !== false}
                      onChange={(next) => updateStage(stage.id, { enabled: next })}
                      label="阶段开关"
                    />
                    <Button variant="ghost" size="icon-sm" title="上移" onClick={() => moveStage(index, -1)}>
                      <ChevronUp />
                    </Button>
                    <Button variant="ghost" size="icon-sm" title="下移" onClick={() => moveStage(index, 1)}>
                      <ChevronDown />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="删除阶段"
                      className="text-destructive hover:bg-destructive/10"
                      onClick={() => removeStage(stage.id)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </div>

                <div className={cn('space-y-2 p-3', stage.enabled === false && 'opacity-60')}>
                  {stage.tasks.map((task) => {
                    const plugin = pluginByType.get(task.type)
                    const run = runTasks.get(task.id)
                    const summary = Array.isArray(task.input?.domains)
                      ? (task.input.domains as string[]).join(', ')
                      : String(task.input?.siteName || task.input?.certName || task.input?.dir || '')
                    return (
                      <div
                        key={task.id}
                        title={run?.message || undefined}
                        className={cn(
                          'flex flex-wrap items-center gap-3 rounded-lg border bg-card px-3 py-2',
                          task.enabled === false && 'opacity-60',
                          task.linked === false && 'border-dashed bg-muted/30',
                          run?.status === 'failed' && 'border-destructive/60 bg-destructive/5',
                        )}
                      >
                        <GripVertical className="size-4 shrink-0 text-muted-foreground/50" />
                        <PluginLogo plugin={plugin} size={26} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="truncate text-sm font-medium">{task.title || plugin?.name || task.type}</p>
                            <Badge variant="outline">{plugin?.group === 'deploy' ? '部署' : plugin?.group === 'notify' ? '通知' : '申请'}</Badge>
                            {task.linked === false && <Badge variant="muted">未接入</Badge>}
                            {task.linked !== false && seqById.get(task.id) && (
                              <Badge variant="muted">第 {seqById.get(task.id)} 步</Badge>
                            )}
                            {task.onErrorTaskId && (
                              <Badge variant="outline" className="border-warning/40 text-warning">
                                失败后 → {taskTitleById.get(task.onErrorTaskId) || '已删除的任务'}
                              </Badge>
                            )}
                            {task.enabled === false && <Badge variant="muted">已停用</Badge>}
                            {run?.status === 'failed' && <Badge variant="destructive">失败</Badge>}
                            {run?.status === 'running' && <Badge variant="info">执行中</Badge>}
                          </div>
                          <p className="truncate text-xs text-muted-foreground">{summary || plugin?.desc || task.type}</p>
                        </div>
                        <Switch
                          checked={task.enabled !== false}
                          onChange={(next) => updateTask(stage.id, task.id, { enabled: next })}
                          label="任务开关"
                        />
                        {task.linked === false && (
                          <Button
                            variant="outline"
                            size="xs"
                            onClick={() => updateTask(stage.id, task.id, { linked: true })}
                          >
                            <Link2 />
                            接入流程
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="配置"
                          onClick={() => openTask(stage.id, task)}
                        >
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="移除"
                          className="text-destructive hover:bg-destructive/10"
                          onClick={() => removeTaskWithConfirm(stage.id, task.id)}
                        >
                          <Trash2 />
                        </Button>
                        {run?.status === 'failed' && run.message && (
                          <p className="w-full truncate text-xs text-destructive" title={run.message}>
                            {run.message}
                          </p>
                        )}
                      </div>
                    )
                  })}

                  <button
                    type="button"
                    disabled={stage.tasks.length >= MAX_TASKS_PER_STAGE}
                    onClick={() => {
                      setPickerStage(stage.id)
                      setPickerGroup(stage.tasks.length === 0 ? 'cert' : 'deploy')
                    }}
                    className={cn(
                      'flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed py-2 text-sm transition-colors',
                      stage.tasks.length >= MAX_TASKS_PER_STAGE
                        ? 'cursor-not-allowed border-border text-muted-foreground/60'
                        : 'text-muted-foreground hover:border-solid hover:bg-accent hover:text-foreground',
                    )}
                  >
                    <Plus className="size-4" />
                    {stage.tasks.length >= MAX_TASKS_PER_STAGE
                      ? `本阶段已满 ${MAX_TASKS_PER_STAGE} 个任务`
                      : `添加任务 ${stage.tasks.length}/${MAX_TASKS_PER_STAGE}`}
                  </button>
                </div>
              </Card>
            )
          })}
            </div>
          )}
          <div className="shrink-0">
            <Card className={cn('flex flex-col overflow-hidden', logOpen && 'h-[240px]')}>
            <div className="flex shrink-0 items-center justify-between gap-2 border-b px-4 py-2">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">运行日志</p>
                {historyId && !log.connected && <StatusBadge status={log.status || 'success'} />}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {log.connected && <Badge variant="info">实时</Badge>}
                <span>{log.lines.length} 行</span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  title={logOpen ? '收起日志' : '展开日志'}
                  onClick={() => setLogOpen((prev) => !prev)}
                >
                  {logOpen ? <ChevronDown /> : <ChevronUp />}
                </Button>
              </div>
            </div>
            {logOpen && <LogTerminal fill lines={log.lines} className="m-3 min-h-0 flex-1" />}
          </Card>
          </div>
        </div>
      </div>

      <Dialog open={!!edgeToRemove} onOpenChange={(open) => !open && setEdgeToRemove(null)}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>{isErrorEdge ? '删除「失败后」连线' : '断开接入连线'}</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {isErrorEdge
                ? '删除后，这一步失败时不再跳转到后面指定的任务，会按顺序继续往下执行。'
                : `断开后，「${edgeTargetName}」不再接入执行链，运行时会被跳过，画布上显示为未接入。`}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">改动先落在草稿里，点「保存」后才生效。</p>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setEdgeToRemove(null)}>
              取消
            </Button>
            <Button variant="destructive" size="sm" onClick={confirmRemoveEdge}>
              {isErrorEdge ? '删除连线' : '断开'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!pickerStage} onOpenChange={(open) => !open && setPickerStage(null)}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>添加任务</DialogTitle>
            <p className="text-sm text-muted-foreground">任务类型来自后端插件表，新增插件会自动出现在这里。</p>
          </DialogHeader>
          <div className="flex gap-1 border-b px-6 py-2">
            {(meta.data?.groups ?? []).map((group) => (
              <button
                key={group.key}
                type="button"
                onClick={() => setPickerGroup(group.key)}
                className={cn(
                  'rounded-md px-3 py-1 text-sm',
                  pickerGroup === group.key ? 'bg-accent font-medium' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {group.name}
              </button>
            ))}
          </div>
          <DialogBody className="grid gap-2 sm:grid-cols-2">
            {plugins
              .filter((plugin) => plugin.group === pickerGroup)
              .map((plugin) => (
                <button
                  key={plugin.type}
                  type="button"
                  onClick={() => addTask(plugin)}
                  className="flex items-start gap-2.5 rounded-lg border p-3 text-left transition-colors hover:bg-accent"
                >
                  <PluginLogo plugin={plugin} size={26} className="mt-0.5" />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{plugin.name}</span>
                    <span className="mt-1 line-clamp-2 block text-xs text-muted-foreground">{plugin.desc || plugin.type}</span>
                  </span>
                </button>
              ))}
          </DialogBody>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent size="lg">
          <DialogHeader>
            <div className="flex items-center gap-2.5">
              {currentPlugin && <PluginLogo plugin={currentPlugin} size={30} />}
              <DialogTitle>{editing ? editing.task.title || currentPlugin?.name : ''}</DialogTitle>
            </div>
            <p className="text-sm text-muted-foreground">{currentPlugin?.desc || '按插件声明的字段填写，留空的凭据不会覆盖旧值。'}</p>
          </DialogHeader>
          <DialogBody>
            {currentPlugin ? (
              <SchemaFields
                fields={currentPlugin.inputs}
                values={draft}
                onChange={(key, value) => setDraft((prev) => ({ ...prev, [key]: value }))}
                accessOptions={accessOptions}
              />
            ) : (
              <p className="text-sm text-muted-foreground">没有找到这个任务类型的元数据，可能是后端版本较旧。</p>
            )}
            <div className="mt-5 space-y-3 border-t pt-4">
              <div className="flex items-center gap-2">
                <Switch checked={linkedDraft} onChange={setLinkedDraft} label="接入流程" />
                <span className="text-sm">接入流程</span>
                <span className="text-xs text-muted-foreground">
                  {linkedDraft ? '会参与执行顺序' : '不接入就不会被执行，画布上也不连线'}
                </span>
              </div>

              <div className="space-y-1.5">
                <Label>失败后跳转到</Label>
                <Select
                  value={errorTarget}
                  disabled={!linkedDraft}
                  onChange={(event) => setErrorTarget(event.target.value)}
                >
                  <option value="">不跳转，按顺序继续</option>
                  {laterTasks.map((task) => (
                    <option key={task.id} value={task.id} disabled={Boolean(task.occupiedBy)}>
                      {task.title}
                      {task.occupiedBy ? `（已被「${task.occupiedBy}」占用）` : ''}
                    </option>
                  ))}
                </Select>
                <p className="text-xs text-muted-foreground">
                  只能指向排在它后面的任务；一个任务最多只能接入一条「失败后」连线。命中后中间的任务会被跳过。
                </p>
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setEditing(null)}>
              取消
            </Button>
            <Button
              size="sm"
              onClick={() => {
                if (!editing) return
                if (errorTarget && occupiedTargets.has(errorTarget)) {
                  toast.error(`目标已被「${occupiedTargets.get(errorTarget)}」占用，一个任务只能接入一条失败线`)
                  return
                }
                updateTask(editing.stageId, editing.task.id, {
                  input: draft,
                  title: String(draft.title || editing.task.title),
                  linked: linkedDraft,
                  onErrorTaskId: linkedDraft ? errorTarget || undefined : undefined,
                })
                setEditing(null)
              }}
            >
              保存任务
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {menu && (
        <div
          className="fixed inset-0 z-50"
          onClick={() => setMenu(null)}
          onContextMenu={(event) => {
            event.preventDefault()
            setMenu(null)
          }}
        >
          <div
            className="absolute w-52 overflow-hidden rounded-lg border bg-popover p-1 shadow-lg"
            style={{
              left: Math.min(menu.x, window.innerWidth - 230),
              top: Math.min(menu.y, window.innerHeight - 36 * menuItems.length - 16),
            }}
            onClick={(event) => event.stopPropagation()}
          >
            {menuItems.map((item) => (
              <button
                key={item.label}
                type="button"
                disabled={item.disabled}
                onClick={() => {
                  setMenu(null)
                  item.run()
                }}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40',
                  item.danger && 'text-destructive hover:bg-destructive/10',
                )}
              >
                <item.icon className="size-3.5" />
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <Dialog open={!!logView} onOpenChange={(open) => !open && setLogView(null)}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>{logView?.title}</DialogTitle>
            <p className="text-sm text-muted-foreground">只显示这一次执行的日志；还没运行过就是空的。</p>
          </DialogHeader>
          <DialogBody>
            <LogTerminal lines={logView?.lines ?? []} className="max-h-[46vh]" />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setLogView(null)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!renaming} onOpenChange={(open) => !open && setRenaming(null)}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>重命名阶段</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-1.5">
              <Label>阶段名称</Label>
              <Input
                autoFocus
                value={renaming?.title ?? ''}
                onChange={(event) => setRenaming((prev) => (prev ? { ...prev, title: event.target.value } : prev))}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') commitRename()
                }}
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setRenaming(null)}>
              取消
            </Button>
            <Button size="sm" onClick={commitRename}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={infoOpen} onOpenChange={setInfoOpen}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>流水线信息</DialogTitle>
            <p className="text-sm text-muted-foreground">备注和其它改动一起，点「保存」时落库。</p>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label>备注</Label>
                <Textarea
                  value={remark}
                  placeholder="这条流水线负责什么"
                  onChange={(event) => {
                    setRemark(event.target.value)
                    setDirty(true)
                  }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>定时运行</span>
                <span>{timerTrigger?.cron && timerTrigger.enabled !== false ? describeCron(timerTrigger.cron) : '未设置'}</span>
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>下次运行</span>
                <span>{detail.data?.nextRunTime || '未设置'}</span>
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>最近运行</span>
                <span>{detail.data?.lastHistoryTime || '还没有运行'}</span>
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button size="sm" onClick={() => setInfoOpen(false)}>
              完成
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ScheduleDialog
        open={scheduleOpen}
        onOpenChange={setScheduleOpen}
        cron={timerTrigger?.cron}
        enabled={timerTrigger ? timerTrigger.enabled !== false : false}
        saving={saveSchedule.isPending}
        onSave={(value) => saveSchedule.mutate(value)}
      />
    </div>
  )
}
