import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import {
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Edge,
  type FinalConnectionState,
  type Node,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Pencil, Play, Plus, ScrollText, Trash2, Unlink } from 'lucide-react'
import type { PipelineContent, PipelineTask, TaskPlugin } from '@/lib/types'
import { PluginLogo } from '@/components/plugin-logo'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { RoutedEdge } from './flow-edges'
import { TASK_DRAG_TYPE } from './task-palette'

const TASK_W = 264
const TASK_H = 136
const TASK_GAP = 20
const STAGE_HEADER = 46
const STAGE_PAD = 12
const STAGE_RIGHT_PAD = 36
const ADD_ZONE = 40
const STAGE_GAP = 60
const ORIGIN_X = 24
const ORIGIN_Y = 24
export const MAX_TASKS_PER_STAGE = 5

const STAGE_W = TASK_W + STAGE_PAD + STAGE_RIGHT_PAD
const SUCCESS_Y = TASK_H * 0.38
const ERROR_Y = TASK_H * 0.72
/** 拖动落点吸附的网格，和背景点阵一致 */
const GRID = 16

const stageHeightOf = (taskCount: number) =>
  STAGE_HEADER +
  Math.max(taskCount, 1) * TASK_H +
  Math.max(taskCount - 1, 0) * TASK_GAP +
  ADD_ZONE +
  STAGE_PAD

type Rect = { x: number; y: number; w: number; h: number }
type Pt = [number, number]

/** 轴对齐线段是否穿过矩形内部（只贴着边走不算） */
function segmentHitsRect(a: Pt, b: Pt, rect: Rect) {
  const minX = Math.min(a[0], b[0])
  const maxX = Math.max(a[0], b[0])
  const minY = Math.min(a[1], b[1])
  const maxY = Math.max(a[1], b[1])
  return (
    maxX > rect.x + 0.5 &&
    minX < rect.x + rect.w - 0.5 &&
    maxY > rect.y + 0.5 &&
    minY < rect.y + rect.h - 0.5
  )
}

function pathHits(points: Pt[], rects: Rect[]) {
  let hits = 0
  for (let i = 0; i < points.length - 1; i += 1) {
    for (const rect of rects) {
      if (segmentHitsRect(points[i], points[i + 1], rect)) hits += 1
    }
  }
  return hits
}

function pathLength(points: Pt[]) {
  let total = 0
  for (let i = 0; i < points.length - 1; i += 1) {
    total += Math.abs(points[i + 1][0] - points[i][0]) + Math.abs(points[i + 1][1] - points[i][1])
  }
  return total
}

/** 取最长一段的中点放标签（「失败后」） */
function labelPoint(points: Pt[]): Pt {
  let best: Pt = points[0]
  let bestLen = -1
  for (let i = 0; i < points.length - 1; i += 1) {
    const len = Math.abs(points[i + 1][0] - points[i][0]) + Math.abs(points[i + 1][1] - points[i][1])
    if (len > bestLen) {
      bestLen = len
      best = [(points[i][0] + points[i + 1][0]) / 2, (points[i][1] + points[i + 1][1]) / 2]
    }
  }
  return best
}

/**
 * 自适应正交布线：给出几条候选路径（中缝 / 顶部走廊 / 底部走廊 / 外圈），
 * 按「穿模次数 → 长度」选最优。卡片被拖到任意相对位置时都不会横穿别的卡片。
 */
function routeAdaptive(
  from: { x: number; y: number },
  to: { x: number; y: number },
  obstacles: Rect[],
  bounds: { top: number; bottom: number; left: number; right: number },
  prefer: 'top' | 'bottom',
): Pt[] {
  const gap = 24
  const { x: sx, y: sy } = from
  const { x: tx, y: ty } = to
  const candidates: Pt[][] = []

  const midX = (sx + tx) / 2
  if (tx > sx + gap) candidates.push([[sx, sy], [midX, sy], [midX, ty], [tx, ty]])

  const topRoute: Pt[] = [[sx, sy], [sx + gap, sy], [sx + gap, bounds.top], [tx - gap, bounds.top], [tx - gap, ty], [tx, ty]]
  const bottomRoute: Pt[] = [[sx, sy], [sx + gap, sy], [sx + gap, bounds.bottom], [tx - gap, bounds.bottom], [tx - gap, ty], [tx, ty]]
  if (prefer === 'top') candidates.push(topRoute, bottomRoute)
  else candidates.push(bottomRoute, topRoute)

  candidates.push([[sx, sy], [bounds.right, sy], [bounds.right, ty], [tx, ty]])
  candidates.push([[sx, sy], [sx + gap, sy], [sx + gap, bounds.top], [bounds.left, bounds.top], [bounds.left, ty], [tx, ty]])

  let best = candidates[0]
  let bestHits = Number.POSITIVE_INFINITY
  let bestLength = Number.POSITIVE_INFINITY
  candidates.forEach((points) => {
    const hits = pathHits(points, obstacles)
    const length = pathLength(points)
    if (hits < bestHits || (hits === bestHits && length < bestLength)) {
      best = points
      bestHits = hits
      bestLength = length
    }
  })
  return best
}

const STAGE_TONE = ['var(--stage-cert)', 'var(--stage-deploy)', 'var(--stage-notify)'] as const

type StageLite = PipelineContent['stages'][number]

/** 右键菜单请求：画布只负责报告「在谁身上点了右键」，具体菜单由页面渲染 */
export type CanvasContextTarget =
  | { kind: 'task'; taskId: string; stageId: string; x: number; y: number }
  | { kind: 'stage'; stageId: string; x: number; y: number }
  | { kind: 'edge'; edge: Edge; x: number; y: number }
  | { kind: 'pane'; x: number; y: number }

/** 执行状态（来自 SSE 的 tasks 事件），用来在画布上标红 / 标绿 */
export interface TaskRunState {
  status: string
  message?: string
}

interface StageNodeData extends Record<string, unknown> {
  title: string
  index: number
  tone: string
  count: number
  enabled: boolean
  atLimit: boolean
  failed: boolean
  canRun: boolean
  onAdd: () => void
  onToggle: () => void
  onRemove: () => void
  onRun: () => void
  onLog: () => void
  onRename: () => void
}

interface TaskNodeData extends Record<string, unknown> {
  task: PipelineTask
  plugin?: TaskPlugin
  run?: TaskRunState
  /** 执行顺序（只数已接入的任务），未接入时没有 */
  seq?: number
  highlight?: boolean
  /** 已经有「成功后」连线：右端的成功点不再显示，避免重复拖线 */
  hasOkOut?: boolean
  /** 已经配了「失败后」跳转：右端的失败点不再显示 */
  hasErrOut?: boolean
  onToggle: () => void
  onRemove: () => void
  onLog: () => void
}

function StageNode({ data }: NodeProps<Node<StageNodeData>>) {
  return (
    <div
      className={cn(
        'group size-full rounded-xl border border-dashed border-foreground/25 bg-card shadow-xs',
        !data.enabled && 'opacity-55',
        // 失败整卡红描边：四条边都描，不能只描左边
        data.failed && 'border-solid border-destructive/60 bg-[color-mix(in_oklab,var(--destructive)_7%,var(--card))]',
      )}
    >
      <div className="flex h-[46px] cursor-grab items-center gap-1.5 pl-3 pr-2 active:cursor-grabbing">
        <span
          className="flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white"
          style={{ background: data.failed ? 'var(--destructive)' : data.tone }}
        >
          {data.index + 1}
        </span>
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold" title={data.title}>
          {data.title}
        </span>
        {data.failed && <Badge variant="destructive">有失败</Badge>}

        {/* 阶段操作 hover 才出现；开关常驻，它是状态指示，不能藏起来 */}
        <div className="pointer-events-none flex items-center opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100">
          <button
            type="button"
            title={data.canRun ? '单独运行本阶段' : '这个阶段没有可运行的任务'}
            disabled={!data.canRun}
            className="nodrag nopan rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            onClick={(event) => {
              event.stopPropagation()
              data.onRun()
            }}
          >
            <Play className="size-3.5" />
          </button>
          <button
            type="button"
            title="查看本阶段日志"
            className="nodrag nopan rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={(event) => {
              event.stopPropagation()
              data.onLog()
            }}
          >
            <ScrollText className="size-3.5" />
          </button>
          <button
            type="button"
            title="重命名阶段"
            className="nodrag nopan rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={(event) => {
              event.stopPropagation()
              data.onRename()
            }}
          >
            <Pencil className="size-3.5" />
          </button>
          <button
            type="button"
            title="删除阶段"
            className="nodrag nopan rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            onClick={(event) => {
              event.stopPropagation()
              data.onRemove()
            }}
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>

        <span className="nodrag nopan shrink-0" onClick={(event) => event.stopPropagation()}>
          <Switch
            checked={data.enabled}
            onChange={() => data.onToggle()}
            label={data.enabled ? '停用这个阶段' : '启用这个阶段'}
            title={data.enabled ? '点击停用：停用后整段跳过' : '点击启用：启用后按顺序执行整段'}
            className="scale-90"
          />
        </span>
      </div>

      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation()
          data.onAdd()
        }}
        disabled={data.atLimit}
        className={cn(
          'nodrag nopan absolute inset-x-2.5 bottom-2 flex h-8 cursor-pointer items-center justify-center gap-1 rounded-md border border-dashed text-xs transition-colors',
          data.atLimit
            ? 'cursor-not-allowed border-foreground/20 text-foreground/40'
            : 'border-foreground/25 text-foreground/60 hover:border-solid hover:bg-accent hover:text-foreground',
        )}
      >
        <Plus className="size-3.5" />
        {data.atLimit ? `本阶段已满 ${MAX_TASKS_PER_STAGE} 个任务` : `添加任务 ${data.count}/${MAX_TASKS_PER_STAGE}`}
      </button>

      <Handle type="target" position={Position.Top} className="!size-0 !border-0 !bg-transparent !opacity-0" />
    </div>
  )
}

function TaskNode({ data }: NodeProps<Node<TaskNodeData>>) {
  const { task, plugin, run, seq, highlight } = data
  const summary = Array.isArray(task.input?.domains)
    ? (task.input.domains as string[]).join(', ')
    : String(task.input?.siteName || task.input?.certName || task.input?.dir || '')
  const off = task.enabled === false
  const unlinked = task.linked === false
  const subtitle = plugin?.name && plugin.name !== task.title ? plugin.name : task.type
  const failed = run?.status === 'failed'
  const runningNow = run?.status === 'running'

  return (
    <div
      title={run?.message || undefined}
      style={{ height: TASK_H, width: TASK_W }}
      className={cn(
        'nodrag group flex cursor-pointer flex-col gap-1.5 rounded-lg border border-foreground/20 bg-card px-3.5 py-2.5 pr-12 shadow-sm transition-colors hover:border-foreground/40',
        off && 'opacity-60',
        unlinked && 'border-dashed bg-muted',
        // 跑完 / 跑挂的结果要能一眼看出来：失败整张卡红描边 + 红底
        failed && 'border-destructive/70 bg-[color-mix(in_oklab,var(--destructive)_7%,var(--card))]',
        !failed && runningNow && 'border-info/60',
        !failed && !runningNow && run?.status === 'success' && 'border-success/50',
        // 刚连上的卡片闪一下描边，用户能确认「线接到了哪里」
        highlight && 'ring-2 ring-info/60',
      )}
    >
      <div className="flex items-start gap-2">
        <PluginLogo plugin={plugin} size={32} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold leading-tight">{task.title || plugin?.name || task.type}</p>
          <p className="mt-0.5 truncate text-[11px] leading-tight text-foreground/55">{subtitle}</p>
        </div>
        {failed && <Badge variant="destructive">失败</Badge>}
        {!failed && runningNow && <Badge variant="info">执行中</Badge>}
        {off && <Badge variant="muted">停用</Badge>}
        {unlinked && (
          <Badge variant="muted" className="gap-0.5">
            <Unlink className="size-2.5" />
            未接入
          </Badge>
        )}
      </div>
      <p className="line-clamp-2 text-[11px] leading-relaxed text-foreground/60">
        {summary || plugin?.desc || '还没有填写参数'}
      </p>

      {/* 步骤的启停与删除直接放在卡片上：画布上也要能改，不用切回列表视图 */}
      <div
        className="nodrag nopan mt-auto flex items-center justify-between gap-2 border-t border-foreground/10 pt-2"
        onClick={(event) => event.stopPropagation()}
      >
        <span className="flex min-w-0 items-center gap-1">
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-foreground/80">
            {unlinked ? '未接入' : `第 ${seq ?? '-'} 步`}
          </span>
          {unlinked && <span className="truncate text-[10px] text-foreground/50">不执行</span>}
          {off && <span className="truncate text-[10px] text-foreground/50">已停用</span>}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            title="查看该任务日志"
            className="pointer-events-none rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover:pointer-events-auto group-hover:opacity-100"
            onClick={(event) => {
              event.stopPropagation()
              data.onLog()
            }}
          >
            <ScrollText className="size-3.5" />
          </button>
          <button
            type="button"
            title="删除任务"
            className="pointer-events-none rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:pointer-events-auto group-hover:opacity-100"
            onClick={(event) => {
              event.stopPropagation()
              data.onRemove()
            }}
          >
            <Trash2 className="size-3.5" />
          </button>
          <Switch
            checked={!off}
            onChange={() => data.onToggle()}
            label={off ? '启用这个任务' : '停用这个任务'}
            title={off ? '点击启用：启用后按顺序执行' : '点击停用：停用后运行会跳过这个任务'}
            className="ml-1 scale-75"
          />
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Left}
        style={{ background: 'var(--foreground)', boxShadow: '0 0 0 2px var(--card)' }}
        className="!size-3 !border-0"
      />
      <Handle
        id="success"
        type="source"
        position={Position.Right}
        isConnectable={!data.hasOkOut}
        style={{
          top: '38%',
          background: unlinked ? 'var(--muted-foreground)' : 'var(--success)',
          boxShadow: '0 0 0 2px var(--card)',
          opacity: data.hasOkOut ? 0 : 1,
          pointerEvents: data.hasOkOut ? 'none' : 'auto',
        }}
        className="!size-3 !border-0"
        title={data.hasOkOut ? undefined : '成功后：拖到下一个任务'}
      />
      <Handle
        id="error"
        type="source"
        position={Position.Right}
        isConnectable={!data.hasErrOut}
        style={{
          top: '72%',
          background: unlinked ? 'var(--muted-foreground)' : 'var(--warning)',
          boxShadow: '0 0 0 2px var(--card)',
          opacity: data.hasErrOut ? 0 : 1,
          pointerEvents: data.hasErrOut ? 'none' : 'auto',
        }}
        className="!size-3 !border-0"
        title={data.hasErrOut ? undefined : '失败后：拖到出问题时跳转的任务'}
      />
      {/* 同阶段内的上下对接走这两个隐藏锚点：底部出、顶部进，不再绕到右侧横穿卡片 */}
      <Handle
        id="success-v"
        type="source"
        position={Position.Bottom}
        isConnectable={false}
        className="!size-0 !border-0 !bg-transparent !opacity-0"
      />
      <Handle
        id="in-top"
        type="target"
        position={Position.Top}
        isConnectable={false}
        className="!size-0 !border-0 !bg-transparent !opacity-0"
      />

      <span className="pointer-events-none absolute right-1 top-[38%] -translate-y-1/2 rounded-sm bg-card px-1 text-[10px] font-medium leading-tight text-success">
        成功
      </span>
      <span className="pointer-events-none absolute right-1 top-[72%] -translate-y-1/2 rounded-sm bg-card px-1 text-[10px] font-medium leading-tight text-warning">
        失败
      </span>
    </div>
  )
}

const nodeTypes = { stage: StageNode, task: TaskNode }
const edgeTypes = { routed: RoutedEdge }

function CanvasInner({
  content,
  plugins,
  running,
  runTasks,
  highlightTaskId,
  onConnect,
  onEditTask,
  onOpenStage,
  onAddTask,
  onToggleStage,
  onRemoveStage,
  onToggleTask,
  onRemoveTask,
  onRunStage,
  onStageLog,
  onRenameStage,
  onTaskLog,
  onRemoveEdge,
  onContextMenu,
  onDropTask,
  layout,
  onMoveStage,
}: {
  content: PipelineContent
  plugins: Map<string, TaskPlugin>
  running?: boolean
  runTasks?: Map<string, TaskRunState>
  highlightTaskId?: string | null
  onConnect?: (source: string, sourceHandle: string | null, target: string) => void
  onEditTask: (stageId: string, task: PipelineTask) => void
  onOpenStage: (stage: StageLite) => void
  onAddTask: (stageId: string) => void
  onToggleStage: (stageId: string, enabled: boolean) => void
  onRemoveStage: (stageId: string) => void
  onToggleTask: (taskId: string, enabled: boolean) => void
  onRemoveTask: (stageId: string, taskId: string) => void
  onRunStage: (stageId: string) => void
  onStageLog: (stageId: string) => void
  onRenameStage: (stageId: string) => void
  onTaskLog: (taskId: string) => void
  onRemoveEdge: (edge: Edge) => void
  onContextMenu: (target: CanvasContextTarget) => void
  onDropTask: (stageId: string, type: string) => void
  layout?: PipelineContent['layout']
  onMoveStage: (stageId: string, position: { x: number; y: number }) => void
}) {
  const { fitView, screenToFlowPosition } = useReactFlow()
  const connectedRef = useRef(false)

  const handleConnect = useCallback(
    (connection: Connection) => {
      connectedRef.current = true
      if (!connection.source || !connection.target || connection.source === connection.target) return
      onConnect?.(connection.source, connection.sourceHandle ?? null, connection.target)
    },
    [onConnect],
  )

  /** 落点常常在卡片中间、离左侧锚点很远，React Flow 只在锚点附近才认；这里按落点补一条 */
  const handleConnectEnd = useCallback(
    (event: MouseEvent | TouchEvent, state: FinalConnectionState) => {
      if (connectedRef.current) return
      const fromNode = state?.fromNode
      if (!onConnect || !fromNode) return
      const point =
        'changedTouches' in event
          ? { x: event.changedTouches[0]?.clientX ?? 0, y: event.changedTouches[0]?.clientY ?? 0 }
          : { x: (event as MouseEvent).clientX, y: (event as MouseEvent).clientY }
      const target = document
        .elementFromPoint(point.x, point.y)
        ?.closest('.react-flow__node-task') as HTMLElement | null
      const targetId = target?.dataset.id
      if (!targetId || targetId === fromNode.id) return
      onConnect(fromNode.id, state.fromHandle?.id ?? null, targetId)
    },
    [onConnect],
  )

  /** 从右侧任务列表拖进来的插件：落在哪个阶段就加到哪个阶段 */
  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      const type = event.dataTransfer.getData(TASK_DRAG_TYPE)
      if (!type) return
      event.preventDefault()
      // 松手时鼠标下面就是那张阶段卡；拿不到再退回按 x 估算
      const element = document.elementFromPoint(event.clientX, event.clientY)
      const stageId = (element?.closest('.react-flow__node-stage') as HTMLElement | null)?.dataset.id
      if (stageId) {
        onDropTask(stageId, type)
        return
      }
      const point = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      const index = Math.max(
        0,
        Math.min(content.stages.length - 1, Math.round((point.x - ORIGIN_X) / (STAGE_W + STAGE_GAP))),
      )
      const stage = content.stages[index]
      onDropTask(stage ? stage.id : '', type)
    },
    [content, onDropTask, screenToFlowPosition],
  )

  /**
   * 节点骨架：data / 尺寸 / 初始坐标。拖动期间这个 memo 不会重算，
   * 位置由下面那份 nodes 状态管，避免每帧重建节点导致闪烁。
   */
  const baseNodes = useMemo(() => {
    const nextNodes: Node[] = []

    // 先算执行顺序：只有「已接入」的任务才算步骤，卡片底部要显示「第 N 步」
    const ordered = content.stages.flatMap((stage) =>
      stage.tasks.map((task) => ({ task, stageId: stage.id })),
    )
    const linkedOrder = ordered.filter((item) => item.task.linked !== false)
    const seqById = new Map<string, number>()
    linkedOrder.forEach((item, index) => seqById.set(item.task.id, index + 1))

    // 已经连出去的端口就不再显示（成功后=链上的下一个；失败后=配了跳转的任务）
    const hasOkOut = new Set(linkedOrder.slice(0, -1).map((item) => item.task.id))
    const hasErrOut = new Set<string>()
    const errTargets = new Set<string>()
    ordered.forEach(({ task }) => {
      if (task.linked === false || !task.onErrorTaskId || errTargets.has(task.onErrorTaskId)) return
      errTargets.add(task.onErrorTaskId)
      hasErrOut.add(task.id)
    })

    let x = ORIGIN_X

    content.stages.forEach((stage, stageIndex) => {
      const tone = STAGE_TONE[stageIndex % STAGE_TONE.length]
      const tasks = stage.tasks
      const height = stageHeightOf(tasks.length)

      // 位置：存进 content.layout 的坐标优先，没有就自动横排
      const stagePos = layout?.stages?.[stage.id] ?? { x, y: ORIGIN_Y }

      nextNodes.push({
        id: stage.id,
        type: 'stage',
        position: stagePos,
        data: {
          title: stage.title,
          index: stageIndex,
          tone,
          count: tasks.length,
          enabled: stage.enabled !== false,
          atLimit: tasks.length >= MAX_TASKS_PER_STAGE,
          failed: tasks.some((task) => runTasks?.get(task.id)?.status === 'failed'),
          canRun:
            stage.enabled !== false &&
            tasks.some((task) => task.enabled !== false && task.linked !== false),
          onAdd: () => onAddTask(stage.id),
          onToggle: () => onToggleStage(stage.id, stage.enabled === false),
          onRemove: () => onRemoveStage(stage.id),
          onRun: () => onRunStage(stage.id),
          onLog: () => onStageLog(stage.id),
          onRename: () => onRenameStage(stage.id),
        } satisfies StageNodeData,
        style: { width: STAGE_W, height },
        zIndex: 0,
        draggable: true,
        selectable: false,
      })

      tasks.forEach((task, taskIndex) => {
        nextNodes.push({
          id: task.id,
          type: 'task',
          parentId: stage.id,
          position: { x: STAGE_PAD, y: STAGE_HEADER + taskIndex * (TASK_H + TASK_GAP) },
          data: {
            task,
            plugin: plugins.get(task.type),
            run: runTasks?.get(task.id),
            seq: seqById.get(task.id),
            highlight: task.id === highlightTaskId,
            hasOkOut: hasOkOut.has(task.id),
            hasErrOut: hasErrOut.has(task.id),
            onToggle: () => onToggleTask(task.id, task.enabled === false),
            onRemove: () => onRemoveTask(stage.id, task.id),
            onLog: () => onTaskLog(task.id),
          } satisfies TaskNodeData,
          zIndex: 2,
          draggable: false,
          selectable: false,
        })
      })

      x += STAGE_W + STAGE_GAP
    })

    return nextNodes
  }, [
    content,
    plugins,
    runTasks,
    highlightTaskId,
    layout,
    onAddTask,
    onToggleStage,
    onRemoveStage,
    onToggleTask,
    onRemoveTask,
    onRunStage,
    onStageLog,
    onRenameStage,
    onTaskLog,
  ])

  const onInit = useCallback(() => {
    requestAnimationFrame(() => fitView({ padding: 0.12, maxZoom: 1.8, duration: 200 }))
  }, [fitView])

  // 阶段数量变化后重新对准：新加/删掉阶段时画布别留一大片空白。
  // 用 ref 记住上一次的数量，避免拖动时每帧重渲染又把视口 fitView 一次（那会闪）。
  const stageCount = content.stages.length
  const lastStageCount = useRef(stageCount)
  useEffect(() => {
    if (!stageCount || stageCount === lastStageCount.current) return
    lastStageCount.current = stageCount
    const timer = window.setTimeout(() => fitView({ padding: 0.14, maxZoom: 1.8, duration: 220 }), 80)
    return () => window.clearTimeout(timer)
  }, [stageCount, fitView])

  // 位置放在本地 nodes 状态里：拖动走 applyNodeChanges，不重建节点，所以不会闪。
  // 外部数据（标题 / 状态 / 开关）变化时刷新节点，但**保留当前坐标**，不把用户拖过的位置弹回去。
  const [nodes, setNodes] = useState<Node[]>(baseNodes)
  useEffect(() => {
    setNodes((current) => {
      const posById = new Map(current.map((node) => [node.id, node.position]))
      return baseNodes.map((node) => ({ ...node, position: posById.get(node.id) ?? node.position }))
    })
  }, [baseNodes])

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current))
  }, [])

  const edgeVisuals = useMemo(
    () => ({
      success: { stroke: running ? 'var(--info)' : 'var(--muted-foreground)', strokeWidth: 2 },
      failure: { stroke: 'var(--warning)', strokeWidth: 2, strokeDasharray: '5 3' },
    }),
    [running],
  )

  /** 连线按节点当前坐标重算：拖动阶段时线会实时跟过去 */
  const edges = useMemo(() => {
    const list: Edge[] = []
    const stagePos = new Map<string, { x: number; y: number }>()
    nodes.forEach((node) => {
      if (node.type === 'stage') stagePos.set(node.id, node.position)
    })

    const taskPoint = new Map<string, { x: number; y: number; stage: number }>()
    content.stages.forEach((stage, stageIndex) => {
      const pos = stagePos.get(stage.id) ?? { x: ORIGIN_X, y: ORIGIN_Y }
      stage.tasks.forEach((task, taskIndex) => {
        taskPoint.set(task.id, {
          x: pos.x + STAGE_PAD,
          y: pos.y + STAGE_HEADER + taskIndex * (TASK_H + TASK_GAP),
          stage: stageIndex,
        })
      })
    })

    const stageRects: Rect[] = []
    const taskRects: Rect[] = []
    content.stages.forEach((stage) => {
      const pos = stagePos.get(stage.id) ?? { x: ORIGIN_X, y: ORIGIN_Y }
      stageRects.push({ x: pos.x, y: pos.y, w: STAGE_W, h: stageHeightOf(stage.tasks.length) })
      stage.tasks.forEach((_task, taskIndex) => {
        taskRects.push({
          x: pos.x + STAGE_PAD,
          y: pos.y + STAGE_HEADER + taskIndex * (TASK_H + TASK_GAP),
          w: TASK_W,
          h: TASK_H,
        })
      })
    })
    const bounds = {
      top: Math.min(...stageRects.map((rect) => rect.y)) - 24,
      bottom: Math.max(...stageRects.map((rect) => rect.y + rect.h)) + 24,
      left: Math.min(...stageRects.map((rect) => rect.x)) - 24,
      right: Math.max(...stageRects.map((rect) => rect.x + rect.w)) + 24,
    }
    // 起点/终点所在阶段不当作障碍（线本来就要从它的留白里出来），但所有任务卡都算障碍
    const obstaclesFor = (sourceStage: number, targetStage: number): Rect[] => [
      ...stageRects.filter((_, index) => index !== sourceStage && index !== targetStage),
      ...taskRects,
    ]

    const ordered = content.stages.flatMap((stage) => stage.tasks)
    const linkedOrder = ordered.filter((task) => task.linked !== false)

    for (let index = 0; index < linkedOrder.length - 1; index += 1) {
      const from = linkedOrder[index]
      const to = linkedOrder[index + 1]
      const a = taskPoint.get(from.id)
      const b = taskPoint.get(to.id)
      if (!a || !b) continue

      if (a.stage === b.stage) {
        // 同阶段内上下对接：上一张卡底部中心直接落到下一张卡顶部中心
        const cx = a.x + TASK_W / 2
        list.push({
          id: `ok-${from.id}-${to.id}`,
          source: from.id,
          sourceHandle: 'success-v',
          target: to.id,
          targetHandle: 'in-top',
          type: 'routed',
          data: { points: [[cx, a.y + TASK_H], [cx, b.y]] },
          style: edgeVisuals.success,
        })
        continue
      }

      const points = routeAdaptive(
        { x: a.x + TASK_W, y: a.y + SUCCESS_Y },
        { x: b.x, y: b.y + TASK_H / 2 },
        obstaclesFor(a.stage, b.stage),
        bounds,
        'top',
      )

      list.push({
        id: `ok-${from.id}-${to.id}`,
        source: from.id,
        sourceHandle: 'success',
        target: to.id,
        type: 'routed',
        data: { points },
        style: edgeVisuals.success,
      })
    }

    // 「失败后」：每个任务最多一条，且一个目标最多被一条失败线接入
    const usedTargets = new Set<string>()

    ordered.forEach((task) => {
      if (task.linked === false) return
      const target = task.onErrorTaskId
      if (!target || usedTargets.has(target)) return
      const a = taskPoint.get(task.id)
      const b = taskPoint.get(target)
      if (!a || !b || b.y < a.y) return

      usedTargets.add(target)
      const points = routeAdaptive(
        { x: a.x + TASK_W, y: a.y + ERROR_Y },
        { x: b.x, y: b.y + TASK_H / 2 },
        obstaclesFor(a.stage, b.stage),
        bounds,
        'bottom',
      )
      const label = labelPoint(points)

      list.push({
        id: `err-${task.id}-${target}`,
        source: task.id,
        sourceHandle: 'error',
        target,
        type: 'routed',
        data: { points, label: { x: label[0], y: label[1], text: '失败后' } },
        style: edgeVisuals.failure,
      })
    })

    return list
  }, [nodes, content, edgeVisuals])

  /** 松手：先吸到 16px 网格，再沿 x 推开重叠的阶段 —— 卡片之间永远不会叠在一起 */
  const handleStageDrop = useCallback(
    (stageId: string, raw: { x: number; y: number }) => {
      const stage = content.stages.find((item) => item.id === stageId)
      if (!stage) return
      const size = { w: STAGE_W, h: stageHeightOf(stage.tasks.length) }
      let x = Math.round(raw.x / GRID) * GRID
      const y = Math.round(raw.y / GRID) * GRID
      const others = nodes
        .filter((node) => node.type === 'stage' && node.id !== stageId)
        .map((node) => {
          const count = content.stages.find((item) => item.id === node.id)?.tasks.length ?? 0
          return { x: node.position.x, y: node.position.y, w: STAGE_W, h: stageHeightOf(count) }
        })
      for (let guard = 0; guard < 32; guard += 1) {
        const hit = others.find(
          (rect) =>
            x < rect.x + rect.w + GRID &&
            x + size.w + GRID > rect.x &&
            y < rect.y + rect.h + GRID &&
            y + size.h + GRID > rect.y,
        )
        if (!hit) break
        x = Math.round((hit.x + hit.w + GRID * 2) / GRID) * GRID
      }
      const position = { x, y }
      setNodes((current) => current.map((node) => (node.id === stageId ? { ...node, position } : node)))
      onMoveStage(stageId, position)
    },
    [content.stages, nodes, onMoveStage],
  )

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onInit={onInit}
      fitView
      minZoom={0.4}
      maxZoom={2}
      nodesDraggable={false}
      nodesConnectable
      elementsSelectable={false}
      nodeClickDistance={4}
      onNodesChange={handleNodesChange}
      onNodeDragStop={(_, node) => {
        if (node.type !== 'stage') return
        handleStageDrop(node.id, node.position)
      }}
      onDragOver={(event) => {
        event.preventDefault()
        event.dataTransfer.dropEffect = 'copy'
      }}
      onDrop={handleDrop}
      connectionRadius={36}
      connectionLineStyle={{ stroke: 'var(--foreground)', strokeWidth: 1.5, strokeDasharray: '4 3' }}
      isValidConnection={(connection) => connection.source !== connection.target}
      onConnect={handleConnect}
      onConnectStart={() => {
        connectedRef.current = false
      }}
      onConnectEnd={handleConnectEnd}
      proOptions={{ hideAttribution: true }}
      onNodeContextMenu={(event, node) => {
        event.preventDefault()
        if (node.type === 'task' && node.parentId) {
          onContextMenu({ kind: 'task', taskId: node.id, stageId: node.parentId, x: event.clientX, y: event.clientY })
        } else {
          onContextMenu({ kind: 'stage', stageId: node.id, x: event.clientX, y: event.clientY })
        }
      }}
      onEdgeContextMenu={(event, edge) => {
        event.preventDefault()
        onContextMenu({ kind: 'edge', edge, x: event.clientX, y: event.clientY })
      }}
      onPaneContextMenu={(event) => {
        event.preventDefault()
        onContextMenu({ kind: 'pane', x: event.clientX, y: event.clientY })
      }}
      onEdgeClick={(_, edge) => {
        if (edge.id.startsWith('ok-') || edge.id.startsWith('err-')) onRemoveEdge(edge)
      }}
      onNodeClick={(_, node) => {
        if (node.type !== 'task') return
        const stage = content.stages.find((item) => item.tasks.some((task) => task.id === node.id))
        const task = stage?.tasks.find((item) => item.id === node.id)
        if (stage && task) onEditTask(stage.id, task)
      }}
      onNodeDoubleClick={(_, node) => {
        const stage = content.stages.find((item) => item.id === node.id)
        if (stage) onOpenStage(stage)
      }}
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={16}
        size={1.2}
        color="color-mix(in oklab, var(--muted-foreground) 45%, transparent)"
      />
      <Controls showInteractive={false} className="!rounded-md !border !bg-background !shadow-xs" />
      <MiniMap
        pannable
        zoomable
        style={{ width: 160, height: 104 }}
        className="!right-3 !bottom-3 hidden !rounded-md !border !bg-card sm:block"
        nodeColor={(node) => (node.type === 'stage' ? 'var(--muted-foreground)' : 'var(--primary)')}
        nodeStrokeColor={(node) => (node.type === 'stage' ? 'var(--muted-foreground)' : 'var(--primary)')}
        maskColor="color-mix(in oklab, var(--background) 78%, transparent)"
      />
    </ReactFlow>
  )
}

/** 画布视图：阶段横排、任务竖排；顺序线和失败线都在布局阶段算好绕行路径 */
export function PipelineCanvas(props: {
  content: PipelineContent
  plugins: Map<string, TaskPlugin>
  running?: boolean
  runTasks?: Map<string, TaskRunState>
  highlightTaskId?: string | null
  onConnect?: (source: string, sourceHandle: string | null, target: string) => void
  onEditTask: (stageId: string, task: PipelineTask) => void
  onOpenStage: (stage: StageLite) => void
  onAddTask: (stageId: string) => void
  onToggleStage: (stageId: string, enabled: boolean) => void
  onRemoveStage: (stageId: string) => void
  onToggleTask: (taskId: string, enabled: boolean) => void
  onRemoveTask: (stageId: string, taskId: string) => void
  onRunStage: (stageId: string) => void
  onStageLog: (stageId: string) => void
  onRenameStage: (stageId: string) => void
  onTaskLog: (taskId: string) => void
  onRemoveEdge: (edge: Edge) => void
  onContextMenu: (target: CanvasContextTarget) => void
  onDropTask: (stageId: string, type: string) => void
  layout?: PipelineContent['layout']
  onMoveStage: (stageId: string, position: { x: number; y: number }) => void
}) {
  return (
    <div className="h-full overflow-hidden rounded-xl border bg-[color-mix(in_oklab,var(--foreground)_5%,var(--background))]">
      <ReactFlowProvider>
        <CanvasInner {...props} />
      </ReactFlowProvider>
    </div>
  )
}
