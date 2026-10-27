<!--
  流水线连线（自定义 edge）
  =========================================================
  顺序连线和「失败后」连线共用同一套线型：贝塞尔曲线 + 中点圆点。
  语义只靠出口区分（卡片右侧上点是成功后、下点是失败后），
  不再用红色虚线 / 「失败后」胶囊，也不再为了避让中间阶段绕底部通道 ——
  跨阶段失败线就是一条直接连过去的贝塞尔，和普通连线同一种画法。
-->
<template>
  <BaseEdge :id="id" :path="path" :marker-end="markerEnd" :style="style" />
  <circle class="pipeline-edge-dot" :cx="dotX" :cy="dotY" r="3.2" />
</template>

<script setup lang="ts">
  import { BaseEdge, getBezierPath } from '@vue-flow/core'
  import type { Position } from '@vue-flow/core'

  // inheritAttrs: false 是必需的：这个组件是「多根节点」（BaseEdge + 中点圆点），
  // Vue 无法决定把 Vue Flow 透传的其余属性（sourceNode / events / label…）挂到哪个根上，
  // 每次重建都会刷一串 [Vue warn] Extraneous non-props attributes。这些属性我们本来也不用。
  defineOptions({ name: 'PipelineEdge', inheritAttrs: false })

  const props = defineProps<{
    id: string
    sourceX: number
    sourceY: number
    targetX: number
    targetY: number
    sourcePosition: Position
    targetPosition: Position
    markerEnd?: string
    /** Vue Flow 会把 edge 上的 data 透传进来；现在路由不再用它，声明出来避免落到 fragment 根上报警告 */
    data?: Record<string, any>
    /**
     * 描边样式是 edge 对象上的 style，Vue Flow 以 **prop** 的形式传进来。
     * 不声明、不转发的话它会被当成普通属性丢掉 —— 表现是「明明设了 stroke 还是默认色」。
     */
    style?: Record<string, any>
  }>()

  /** getBezierPath 返回 [path, labelX, labelY, offsetX, offsetY] */
  const geometry = computed(() =>
    getBezierPath({
      sourceX: props.sourceX,
      sourceY: props.sourceY,
      sourcePosition: props.sourcePosition,
      targetX: props.targetX,
      targetY: props.targetY,
      targetPosition: props.targetPosition
    })
  )

  const path = computed(() => geometry.value[0])
  const dotX = computed(() => geometry.value[1])
  const dotY = computed(() => geometry.value[2])
</script>

<style scoped>
  .pipeline-edge-dot {
    fill: var(--flow-edge, #4285f4);
    stroke: var(--g-surface, #fff);
    stroke-width: 1.5;
  }
</style>
