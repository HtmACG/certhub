<!--
  执行历史
  =========================================================
  按「流水线 / 状态」筛选，点开抽屉看逐行日志（历史记录走回放，不重新执行）。
-->
<template>
  <div class="certd-history art-full-height g-scope">
    <ArtSearchBar
      v-model="searchForm"
      :items="searchItems"
      :show-expand="false"
      @search="handleSearch"
      @reset="handleReset"
    />

    <ElCard class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="refreshData">
        <template #left>
          <ElSpace wrap>
            <ElButton :disabled="!searchForm.pipelineId" @click="clearAll">
              清理本流水线历史
            </ElButton>
            <ElButton
              type="danger"
              plain
              :disabled="!selectedIds.length"
              :loading="removing"
              @click="removeSelected"
            >
              <ArtSvgIcon icon="ri:delete-bin-line" class="mr-1" />
              批量删除<template v-if="selectedIds.length">（{{ selectedIds.length }}）</template>
            </ElButton>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        row-key="id"
        @selection-change="handleSelectionChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
        <template #pipelineTitle="{ row }">
          <ElLink type="primary" :underline="false" @click="goPipeline(row)">
            {{ row.pipelineTitle }}
          </ElLink>
        </template>
        <template #status="{ row }">
          <ElTag :type="runStatusMeta(row.status).type" size="small" effect="light">
            {{ runStatusMeta(row.status).text }}
          </ElTag>
        </template>
        <template #triggerType="{ row }">
          <span class="cell-sub">{{ triggerText(row.triggerType) }}</span>
        </template>
        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton link type="primary" @click="openLog(row)">日志</ElButton>
            <ElButton v-if="row.status === 'running'" link type="warning" @click="stop(row)">
              停止
            </ElButton>
            <ElButton link type="danger" @click="remove(row)">删除</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDrawer v-model="logVisible" :title="'执行日志 · ' + (current?.pipelineTitle || '')" size="min(880px, 96vw)" destroy-on-close>
      <LogPanel
        :history-id="logHistoryId"
        :title="'执行日志 · ' + (current?.pipelineTitle || '')"
        :closable="true"
        @close="logVisible = false"
        @stop="stop(current)"
      />
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import {
    clearHistory,
    deleteHistory,
    fetchHistoryList,
    stopHistory,
  } from '@/api/certd'
  import type { HistoryItem } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useBatchDelete } from '../composables/use-batch-delete'
  import { formatDuration, runStatusMeta, triggerText } from '@/utils/certd'
  import LogPanel from '../components/log-panel.vue'

  defineOptions({ name: 'CertdHistory' })

  const router = useRouter()
  const route = useRoute()

  const searchForm = ref<Record<string, any>>({
    pipelineId: route.query.pipelineId ? Number(route.query.pipelineId) : undefined,
    status: undefined,
  })

  const searchItems = [
    {
      key: 'status',
      label: '执行结果',
      type: 'select',
      options: [
        { label: '成功', value: 'success' },
        { label: '失败', value: 'failed' },
        { label: '运行中', value: 'running' },
        { label: '已取消', value: 'canceled' },
      ],
    },
  ]

  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    searchParams,
    getData,
    resetSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshData,
  } = useTable({
    core: {
      apiFn: fetchHistoryList,
      apiParams: {
        current: 1,
        size: 20,
        pipelineId: route.query.pipelineId ? Number(route.query.pipelineId) : undefined,
      },
      columnsFactory: () => [
        { type: 'selection', width: 48 },
        { prop: 'pipelineTitle', label: '流水线', minWidth: 200, useSlot: true },
        { prop: 'status', label: '结果', width: 110, useSlot: true },
        { prop: 'triggerType', label: '触发方式', width: 110, useSlot: true },
        { prop: 'startTime', label: '开始时间', width: 170 },
        { prop: 'duration', label: '耗时', width: 100, formatter: (row: HistoryItem) => formatDuration(row.duration) },
        { prop: 'taskCount', label: '任务数', width: 90 },
        { prop: 'operation', label: '操作', width: 180, fixed: 'right', useSlot: true },
      ],
    },
  })

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteHistory,
    { label: '执行记录', nameOf: (row: any) => row.pipelineTitle || ("#" + row.id), onDone: () => refreshData() }
  )

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }

  const handleReset = () => {
    searchForm.value.pipelineId = undefined
    searchParams.pipelineId = undefined
    resetSearchParams()
  }

  const goPipeline = (row: HistoryItem) => {
    router.push('/certd/pipeline/detail/' + row.pipelineId)
  }

  const logVisible = ref(false)
  const logHistoryId = ref<number | null>(null)
  const current = ref<HistoryItem | null>(null)

  const openLog = (row: HistoryItem) => {
    current.value = row
    logHistoryId.value = row.id
    logVisible.value = true
  }

  const stop = async (row: HistoryItem | null) => {
    if (!row) return
    await stopHistory(row.id)
    ElMessage.success('已请求停止')
    refreshData()
  }

  const remove = async (row: HistoryItem) => {
    await ElMessageBox.confirm('确定删除这条执行记录吗？', '删除记录', { type: 'warning' })
    await deleteHistory(row.id)
    refreshData()
  }

  const clearAll = async () => {
    await ElMessageBox.confirm('将清空该流水线的全部执行记录，确定吗？', '清理历史', {
      type: 'warning',
    })
    await clearHistory(Number(searchForm.value.pipelineId))
    refreshData()
  }
</script>

<style scoped>
  .cell-sub {
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .cell-actions {
    display: flex;
    gap: 6px;
  }
</style>
