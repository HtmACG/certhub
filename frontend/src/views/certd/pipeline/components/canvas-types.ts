/**
 * 流水线画布的类型与常量
 * =========================================================
 * 单独放一个文件，是因为 `<script setup>` 里不能写 `export`。
 * 坐标语义：
 *   stages —— 绝对坐标（画布坐标系）
 *   tasks  —— 相对所属阶段容器的坐标（Vue Flow 的 parentNode 语义）
 */
export interface CanvasLayout {
  stages: Record<string, { x: number; y: number }>
  tasks: Record<string, { x: number; y: number }>
}

export const emptyLayout = (): CanvasLayout => ({ stages: {}, tasks: {} })

/** 画布布局常量：节点尺寸变了要同步改 pipeline-canvas.vue 的 CSS */
export const CANVAS_METRICS = {
  nodeWidth: 256,
  nodeHeight: 160,
  stageHead: 44,
  stagePadX: 16,
  /** 右侧多留一点：给任务卡两个出口（成功后 / 失败后）的标签让位，标签不压卡片内容 */
  stagePadRight: 64,
  stagePadBottom: 16,
  gapY: 26,
  gapX: 92,
  /** 阶段底部「添加任务」按钮：高度 + 与最后一个卡片的间距 */
  addButtonHeight: 34,
  addButtonGap: 10
} as const

/** 单个阶段的任务上限：超过这个数量卡片会挤成一列长条，画布缩放后看不清 */
export const MAX_TASKS_PER_STAGE = 5
