<!--
  审计日志（管理员）
  =========================================================
  记录登录、流水线增删改、授权变更、设置修改等操作，免费功能。
-->
<template>
  <div class="certd-audit art-full-height g-scope">
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
            <ElButton :disabled="!selectedRows.length" @click="copySelected">
              <ArtSvgIcon icon="ri:file-copy-line" class="mr-1" />
              {{ $t('certd.audit.copySelected') }}<template v-if="selectedRows.length"> ({{ selectedRows.length }})</template>
            </ElButton>
            <span class="cell-sub">{{ $t('certd.audit.readonly') }}</span>
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
        <template #detail="{ row }">
          <span class="cell-detail">{{ row.detail || '-' }}</span>
        </template>
      </ArtTable>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import { fetchAuditList } from '@/api/certd'
  import { ElMessage } from 'element-plus'
  import { $t } from '@/locales'

  defineOptions({ name: 'CertdSystemAudit' })

  const searchForm = ref<Record<string, any>>({ keyword: undefined })
  const searchItems = computed(() => [
    { key: 'keyword', label: $t('certd.audit.action'), type: 'input', placeholder: $t('certd.audit.actionPh') },
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
      apiFn: fetchAuditList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { type: 'selection', width: 48 },
        { prop: 'createTime', label: $t('certd.audit.colTime'), width: 190 },
        { prop: 'username', label: $t('certd.audit.colUser'), width: 140 },
        { prop: 'action', label: $t('certd.audit.action'), width: 190 },
        { prop: 'detail', label: $t('certd.common.detail'), minWidth: 240, useSlot: true },
        { prop: 'ip', label: 'IP', width: 150 },
      ],
    },
  })

  /* 审计日志只读：多选后只能复制出去留档，不提供删除 */
  const selectedRows = ref<any[]>([])
  const handleSelectionChange = (rows: any[]) => {
    selectedRows.value = rows
  }

  const copySelected = async () => {
    if (!selectedRows.value.length) return
    const text = selectedRows.value
      .map((row) =>
        [row.createTime, row.username, row.action, row.detail, row.ip]
          .filter((cell) => cell !== undefined && cell !== null && cell !== '')
          .join(' | ')
      )
      .join('\n')
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success($t('certd.audit.copied', { n: selectedRows.value.length }))
    } catch {
      ElMessage.error($t('certd.audit.copyFailed'))
    }
  }

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }
  const handleReset = () => resetSearchParams()
</script>

<style scoped>
  .cell-detail {
    display: inline-block;
    word-break: break-all;
    color: var(--art-gray-700);
  }
</style>
