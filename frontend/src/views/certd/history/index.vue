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
              {{ $t('certd.history.clearPipelineHistory') }}
            </ElButton>
            <ElButton
              type="danger"
              plain
              :disabled="!selectedIds.length"
              :loading="removing"
              @click="removeSelected"
            >
              <ArtSvgIcon icon="ri:delete-bin-line" class="mr-1" />
              {{ $t('certd.history.batchDelete') }}<template v-if="selectedIds.length"> ({{ selectedIds.length }})</template>
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
            <ElButton link type="primary" @click="openLog(row)">{{ $t('certd.history.log') }}</ElButton>
            <ElButton v-if="row.status === 'running'" link type="warning" @click="stop(row)">
              {{ $t('certd.history.stop') }}
            </ElButton>
            <ElButton link type="danger" @click="remove(row)">{{ $t('certd.history.delete') }}</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDrawer v-model="logVisible" :title="logTitle" size="min(880px, 96vw)" destroy-on-close>
      <LogPanel
        :history-id="logHistoryId"
        :title="logTitle"
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
  import { $t } from '@/locales'
  import LogPanel from '../components/log-panel.vue'

  defineOptions({ name: 'CertdHistory' })

  const router = useRouter()
  const route = useRoute()

  const searchForm = ref<Record<string, any>>({
    pipelineId: route.query.pipelineId ? Number(route.query.pipelineId) : undefined,
    status: undefined,
  })

  /** 搜索项文案随语言变化 */
  const searchItems = computed(() => [
    {
      key: 'status',
      label: $t('certd.history.result'),
      type: 'select',
      options: [
        { label: $t('certd.status.success'), value: 'success' },
        { label: $t('certd.status.failed'), value: 'failed' },
        { label: $t('certd.status.running'), value: 'running' },
        { label: $t('certd.status.canceled'), value: 'canceled' },
      ],
    },
  ])

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
        { prop: 'pipelineTitle', label: $t('certd.history.colPipeline'), minWidth: 200, useSlot: true },
        { prop: 'status', label: $t('certd.history.colResult'), width: 120, useSlot: true },
        { prop: 'triggerType', label: $t('certd.history.colTrigger'), width: 120, useSlot: true },
        { prop: 'startTime', label: $t('certd.history.colStartTime'), width: 170 },
        { prop: 'duration', label: $t('certd.history.colDuration'), width: 100, formatter: (row: HistoryItem) => formatDuration(row.duration) },
        { prop: 'taskCount', label: $t('certd.history.colTaskCount'), width: 96 },
        { prop: 'operation', label: $t('certd.common.actions'), width: 190, fixed: 'right', useSlot: true },
      ],
    },
  })

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteHistory,
    { label: () => $t('certd.history.recordLabel'), nameOf: (row: any) => row.pipelineTitle || ("#" + row.id), onDone: () => refreshData() }
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

  /** 抽屉标题：执行日志 · 流水线名（流水线名是用户数据，不翻译） */
  const logTitle = computed(
    () => $t('certd.history.execLogTitle') + (current.value?.pipelineTitle ? ' · ' + current.value.pipelineTitle : '')
  )

  const openLog = (row: HistoryItem) => {
    current.value = row
    logHistoryId.value = row.id
    logVisible.value = true
  }

  const stop = async (row: HistoryItem | null) => {
    if (!row) return
    await stopHistory(row.id)
    $t('certd.history.stopRequested') && ElMessage.success($t('certd.history.stopRequested'))
    refreshData()
  }

  const remove = async (row: HistoryItem) => {
    await ElMessageBox.confirm($t('certd.history.confirmDelete'), $t('certd.history.deleteTitle'), {
    type: 'warning',
    confirmButtonText: $t('certd.common.confirm'),
    cancelButtonText: $t('certd.common.cancel'),
  })
    await deleteHistory(row.id)
    refreshData()
  }

  const clearAll = async () => {
    await ElMessageBox.confirm($t('certd.history.confirmClear'), $t('certd.history.clearTitle'), {
      type: 'warning',
      confirmButtonText: $t('certd.common.confirm'),
      cancelButtonText: $t('certd.common.cancel'),
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
