<!--
  执行日志面板（SSE 实时 + 历史回放）
  =========================================================
  SSE 解析与按阶段拆分在 composables/use-run-log 里，
  这里只负责「工具条 + 终端」的组装（列表页的「运行」抽屉用它）。
  渲染交给 log-terminal：黑底 + 高亮（默认跟随最新日志，无复制 / 清空 / 跟随按钮）。
-->
<template>
  <div class="log-panel">
    <LogTerminal
      :lines="lines"
      :title="title"
      height="clamp(240px, 42vh, 520px)"
      :empty-text="emptyText"
    >
      <template #actions>
        <ElTag v-if="status" :type="statusMeta.type" size="small" effect="light">
          {{ statusMeta.text }}
        </ElTag>
        <ElButton v-if="status === 'running'" link type="danger" @click="emit('stop')">
          <ArtSvgIcon icon="ri:stop-circle-line" class="mr-1" />停止
        </ElButton>
        <ElButton v-if="closable" link @click="emit('close')">
          <ArtSvgIcon icon="ri:close-line" />
        </ElButton>
      </template>
    </LogTerminal>
  </div>
</template>

<script setup lang="ts">
  import { runStatusMeta } from '@/utils/certd'
  import LogTerminal from './log-terminal.vue'
  import { useRunLog } from '../composables/use-run-log'

  defineOptions({ name: 'LogPanel' })

  interface Props {
    /** 执行记录 id，为空时展示占位文案 */
    historyId?: number | null
    /** 标题 */
    title?: string
    /** 没有日志时的提示 */
    emptyText?: string
    /** 是否显示关闭按钮 */
    closable?: boolean
  }

  const props = withDefaults(defineProps<Props>(), {
    historyId: null,
    title: '执行日志',
    emptyText: '暂无日志，运行流水线后这里会实时滚动输出',
    closable: false,
  })

  const emit = defineEmits<{
    (e: 'tasks', tasks: any[], status: string): void
    (e: 'status', status: string): void
    (e: 'stop'): void
    (e: 'close'): void
  }>()

  const { lines, tasks, status, connect } = useRunLog()
  const statusMeta = computed(() => runStatusMeta(status.value))

  watch(
    () => props.historyId,
    (id) => {
      connect(id)
    },
    { immediate: true }
  )

  // 任务状态 / 整体状态透传给父组件（阶段卡片、任务卡上色用）
  watch(tasks, (value) => emit('tasks', value || [], status.value), { deep: true })
  watch(status, (value) => emit('status', value))

  defineExpose({ connect, lines, status })
</script>

<style scoped>
  .log-panel {
    width: 100%;
  }
</style>
