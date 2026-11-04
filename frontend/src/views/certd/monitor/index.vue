<!--
  站点证书监控
  =========================================================
  定时探测站点证书，到期前推送提醒。
  · 列表直接给出「剩余天数」与探测结果，异常站点红标；
  · 每条可立即「检测一次」，不用等定时任务。
-->
<template>
  <div class="certd-monitor art-full-height g-scope">
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
            <ElButton type="primary" @click="openCreate">
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />{{ $t('certd.monitor.create') }}
            </ElButton>
            <ElButton
              type="danger"
              plain
              :disabled="!selectedIds.length"
              :loading="removing"
              @click="removeSelected"
            >
              <ArtSvgIcon icon="ri:delete-bin-line" class="mr-1" />
              {{ $t('certd.common.batchDelete') }}<template v-if="selectedIds.length"> ({{ selectedIds.length }})</template>
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
        <template #url="{ row }">
          <div class="cell-url">
            <span class="cell-title">{{ row.url }}</span>
            <span class="cell-sub">{{ row.error || row.issuer || $t('certd.monitor.noCertInfo') }}</span>
          </div>
        </template>
        <template #status="{ row }">
          <ElTag :type="siteStatusMeta(row.status).type" size="small" effect="light">
            {{ siteStatusMeta(row.status).text }}
          </ElTag>
        </template>
        <template #daysLeft="{ row }">
          <ElTag v-if="row.daysLeft !== null" :type="certStatusMeta(row.daysLeft).type" size="small" effect="light">
            {{ $t('certd.monitor.daysLeft', { days: row.daysLeft }) }}
          </ElTag>
          <span v-else class="cell-sub">-</span>
          <div class="cell-sub">{{ row.expireTime }}</div>
        </template>
        <template #lastCheckTime="{ row }">
          <span class="cell-sub">{{ row.lastCheckTime || $t('certd.monitor.notChecked') }}</span>
        </template>
        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton link type="primary" :loading="checkingId === row.id" @click="check(row)">
              {{ $t('certd.monitor.check') }}
            </ElButton>
            <ElButton link @click="openEdit(row)">{{ $t('certd.common.edit') }}</ElButton>
            <ElButton link type="danger" @click="remove(row)">{{ $t('certd.common.delete') }}</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog
      v-model="dialogVisible"
      :title="editingId ? $t('certd.monitor.editTitle') : $t('certd.monitor.create')"
      width="min(520px, 94vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElFormItem :label="$t('certd.monitor.siteLabel')">
          <ElInput v-model="form.url" placeholder="https://example.com" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.monitor.portLabel')">
          <ElInputNumber v-model="form.port" :min="1" :max="65535" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.monitor.enabledLabel')">
          <ElSwitch v-model="form.enabled" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.monitor.notifyLabel')">
          <ElSwitch v-model="form.notifyEnabled" />
          <span class="cell-sub ml-2">{{ $t('certd.monitor.leadDaysHint') }}</span>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="dialogVisible = false">{{ $t('certd.common.cancel') }}</ElButton>
          <ElButton type="primary" :loading="saving" @click="save">{{ $t('certd.common.save') }}</ElButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import {
    checkSite,
    createSite,
    deleteSite,
    fetchSiteList,
    updateSite,
  } from '@/api/certd'
  import type { SiteItem } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { $t } from '@/locales'
  import { useBatchDelete } from '../composables/use-batch-delete'
  import { certStatusMeta, siteStatusMeta } from '@/utils/certd'

  defineOptions({ name: 'CertdMonitor' })

  const searchForm = ref<Record<string, any>>({ keyword: undefined })
  const searchItems = computed(() => [
    {
      key: 'keyword',
      label: $t('certd.monitor.colSite'),
      type: 'input',
      placeholder: $t('certd.monitor.searchPlaceholder'),
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
      apiFn: fetchSiteList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { type: 'selection', width: 48 },
        { prop: 'url', label: $t('certd.monitor.colSite'), minWidth: 240, useSlot: true },
        { prop: 'status', label: $t('certd.monitor.colStatus'), width: 110, useSlot: true },
        { prop: 'daysLeft', label: $t('certd.monitor.colCertExpiry'), width: 160, useSlot: true },
        { prop: 'lastCheckTime', label: $t('certd.monitor.colLastCheck'), width: 175, useSlot: true },
        { prop: 'operation', label: $t('certd.common.actions'), width: 180, fixed: 'right', useSlot: true },
      ],
    },
  })

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteSite,
    { label: () => $t('certd.monitor.itemLabel'), nameOf: (row: any) => row.url, onDone: () => refreshData() }
  )

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }

  const handleReset = () => resetSearchParams()

  const dialogVisible = ref(false)
  const editingId = ref(0)
  const saving = ref(false)
  const checkingId = ref(0)

  const form = reactive({ url: '', port: 443, enabled: true, notifyEnabled: true })

  const openCreate = () => {
    editingId.value = 0
    form.url = ''
    form.port = 443
    form.enabled = true
    form.notifyEnabled = true
    dialogVisible.value = true
  }

  const openEdit = (row: SiteItem) => {
    editingId.value = row.id
    form.url = row.url
    form.port = row.port
    form.enabled = row.enabled
    form.notifyEnabled = row.notifyEnabled
    dialogVisible.value = true
  }

  const save = async () => {
    if (!form.url.trim()) {
      ElMessage.warning($t('certd.monitor.siteRequired'))
      return
    }
    saving.value = true
    try {
      if (editingId.value) await updateSite(editingId.value, { ...form })
      else await createSite({ ...form })
      dialogVisible.value = false
      refreshData()
    } finally {
      saving.value = false
    }
  }

  const check = async (row: SiteItem) => {
    checkingId.value = row.id
    try {
      const result = await checkSite(row.id)
      if (result?.status === 'ok')
        ElMessage.success($t('certd.monitor.checkOk', { time: result.expireTime || '-' }))
      else ElMessage.warning(result?.error || $t('certd.monitor.checkFail'))
      refreshData()
    } finally {
      checkingId.value = 0
    }
  }

  const remove = async (row: SiteItem) => {
    await ElMessageBox.confirm($t('certd.monitor.confirmDelete', { name: row.url }), $t('certd.monitor.deleteTitle'), {
      type: 'warning',
      confirmButtonText: $t('certd.common.confirm'),
      cancelButtonText: $t('certd.common.cancel'),
    })
    await deleteSite(row.id)
    refreshData()
  }
</script>

<style scoped>
  .cell-url {
    min-width: 0;
  }

  .cell-title {
    display: block;
    overflow: hidden;
    font-weight: 500;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cell-sub {
    display: block;
    overflow: hidden;
    font-size: 12px;
    color: var(--art-gray-500);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cell-actions {
    display: flex;
    gap: 6px;
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
