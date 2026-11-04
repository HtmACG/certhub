<!--
  DNS 记录管理（原「CNAME 记录」）
  =========================================================
  一个页面管两类记录，用「来源」列区分：

  1. 手动登记（CNAME）：把待申请证书的域名 CNAME 到自己的代理域名，
     之后 ACME 的 TXT 记录只需写到代理域名，绕开不被支持的服务商；
     可以绑定授权同步到对端、随时校验是否生效。
  2. 自动登记（TXT）：证书申请走 DNS 验证时，引擎每写一条
     _acme-challenge.<域名> 的验证记录都会更新到这里（写入次数、最近值、
     来源流水线、清理时间）。验证完记录会被删掉，但这一行留着，
     所以「这个域名到底走没走过 DNS 记录」一眼就能看出来。这类行只读。
-->
<template>
  <div class="certd-cname art-full-height g-scope">
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
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />{{ $t('certd.dns.cnameCreate') }}
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
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
        <template #domain="{ row }">
          <div class="cell-main">{{ row.domain }}</div>
          <div class="cell-sub">
            {{ $t('certd.dns.domainMain', { main: row.mainDomain, host: row.hostRecord }) }}
          </div>
        </template>
        <template #recordValue="{ row }">
          <div class="cell-value">
            <ElTag size="small" effect="plain" class="type-tag">{{ row.recordType }}</ElTag>
            <ElTooltip :content="row.recordValue" placement="top" :disabled="!row.recordValue">
              <span class="mono ellipsis">{{ row.recordValue }}</span>
            </ElTooltip>
          </div>
        </template>
        <template #source="{ row }">
          <ElTooltip :content="sourceMeta(row).hint" placement="top" :disabled="!sourceMeta(row).hint">
            <ElTag size="small" :type="sourceMeta(row).type" effect="light">
              {{ sourceMeta(row).text }}
            </ElTag>
          </ElTooltip>
        </template>
        <template #accessId="{ row }">
          <span v-if="!row.accessId" class="cell-sub">{{ $t('certd.dns.cnameLocalOnly') }}</span>
          <span v-else>{{ accessName(row.accessId) }}</span>
        </template>
        <template #status="{ row }">
          <ElTooltip :content="row.error" :disabled="!row.error" placement="top">
            <ElTag :type="statusMeta(row.status).type" size="small" effect="plain">
              {{ statusMeta(row.status).text }}
            </ElTag>
          </ElTooltip>
        </template>
        <template #updateTime="{ row }">
          <template v-if="isManual(row)">
            <div class="cell-sub">
              {{ row.verifyTime ? $t('certd.dns.verifiedAt', { time: row.verifyTime }) : $t('certd.dns.notVerified') }}
            </div>
          </template>
          <template v-else>
            <div class="cell-sub">{{ $t('certd.dns.writeCount', { n: row.writeCount || 1 }) }}</div>
            <div class="cell-sub">
              {{ row.status === 'cleaned'
                ? $t('certd.dns.cleanedAt', { time: row.cleanedTime || row.updateTime })
                : $t('certd.dns.latestAt', { time: row.updateTime || row.createTime }) }}
            </div>
          </template>
        </template>
        <template #operation="{ row }">
          <!-- 自动登记的验证记录由流水线写入 / 清理，页面只读，不提供同步与校验 -->
          <div v-if="isManual(row)" class="cell-actions">
            <ElButton link :disabled="!row.accessId" :loading="busyId === row.id" @click="sync(row)">
              {{ $t('certd.dns.cnameSync') }}
            </ElButton>
            <ElButton link :loading="busyId === row.id" @click="verify(row)">{{ $t('certd.dns.cnameVerify') }}</ElButton>
            <ElButton link @click="openEdit(row)">{{ $t('certd.dns.edit') }}</ElButton>
            <ElButton link type="danger" @click="remove(row)">{{ $t('certd.dns.delete') }}</ElButton>
          </div>
          <div v-else class="cell-actions">
            <span class="cell-sub">{{ $t('certd.dns.cnameAuto') }}</span>
            <ElButton link type="danger" @click="remove(row)">{{ $t('certd.dns.delete') }}</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog
      v-model="dialogVisible"
      :title="editingId ? $t('certd.dns.cnameEditTitle') : $t('certd.dns.cnameCreate')"
      width="min(560px, 94vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElFormItem :label="$t('certd.dns.domainLabel')">
          <ElInput v-model="form.domain" :placeholder="$t('certd.dns.domainPh')" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.dns.valueLabel')">
          <ElInput v-model="form.recordValue" placeholder="abc123.cname.example.net" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.dns.colAccess')">
          <ElSelect
            v-model="form.accessId"
            :placeholder="$t('certd.dns.accessPh')"
            clearable
            class="w-full"
          >
            <ElOption
              v-for="item in dnsAccess"
              :key="item.id"
              :label="item.name + '（' + item.typeName + '）'"
              :value="item.id"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem v-if="form.accessId" :label="$t('certd.dns.syncOnSave')">
          <ElSwitch v-model="form.sync" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.table.remark')">
          <ElInput v-model="form.remark" :placeholder="$t('certd.common.optional')" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton :loading="checking" @click="checkNow">{{ $t('certd.dns.cnameVerifyCurrent') }}</ElButton>
          <div class="dialog-footer-right">
            <ElButton @click="dialogVisible = false">{{ $t('certd.dns.cancel') }}</ElButton>
            <ElButton type="primary" :loading="saving" @click="save">{{ $t('certd.dns.save') }}</ElButton>
          </div>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import {
    checkCnameValue,
    createCname,
    deleteCname,
    fetchAccessOptions,
    fetchCnameList,
    syncCname,
    updateCname,
    verifyCname,
  } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { $t, i18n } from '@/locales'

  defineOptions({ name: 'CertdDnsCname' })

  const searchForm = ref<Record<string, any>>({
    keyword: undefined,
    status: undefined,
    source: undefined,
  })
  const searchItems = computed(() => [
    { key: 'keyword', label: $t('certd.dns.colDomain'), type: 'input', placeholder: $t('certd.dns.keywordPh') },
    {
      key: 'source',
      label: $t('certd.dns.colSource'),
      type: 'select',
      options: [
        { label: $t('certd.dns.sourceManual'), value: 'manual' },
        { label: $t('certd.dns.sourceAcme'), value: 'acme' },
        { label: $t('certd.dns.sourceCloud'), value: 'cloud' },
      ],
    },
    {
      key: 'status',
      label: $t('certd.dns.colStatus'),
      type: 'select',
      options: [
        { label: $t('certd.dns.statusPending'), value: 'pending' },
        { label: $t('certd.dns.statusSynced'), value: 'synced' },
        { label: $t('certd.dns.statusValid'), value: 'valid' },
        { label: $t('certd.dns.statusWritten'), value: 'written' },
        { label: $t('certd.dns.statusCleaned'), value: 'cleaned' },
        { label: $t('certd.dns.statusError'), value: 'error' },
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
      apiFn: fetchCnameList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { prop: 'domain', label: $t('certd.dns.colDomain'), minWidth: 250, useSlot: true },
        { prop: 'recordValue', label: $t('certd.dns.colRecordValue'), minWidth: 220, useSlot: true },
        { prop: 'source', label: $t('certd.dns.colSource'), width: 130, useSlot: true },
        { prop: 'accessId', label: $t('certd.dns.colAccess'), minWidth: 150, useSlot: true },
        { prop: 'status', label: $t('certd.dns.colStatus'), width: 110, useSlot: true },
        { prop: 'updateTime', label: $t('certd.dns.colUpdateTime'), width: 200, useSlot: true },
        { prop: 'remark', label: $t('certd.table.remark'), minWidth: 130 },
        { prop: 'operation', label: $t('certd.common.actions'), width: 230, fixed: 'right', useSlot: true },
      ],
    },
  })

  type TagKind = 'info' | 'primary' | 'success' | 'warning' | 'danger'

  /**
   * 状态 / 来源文案一律存 key，渲染时再取词
   * —— 模块顶层的 $t() 只求值一次，切语言不会跟着变（见 locales/index.ts）
   */
  const STATUS_META: Record<string, { textKey: string; type: TagKind }> = {
    // 手动登记的 CNAME
    pending: { textKey: 'certd.dns.statusPending', type: 'info' },
    synced: { textKey: 'certd.dns.statusSynced', type: 'primary' },
    valid: { textKey: 'certd.dns.statusValid', type: 'success' },
    // 证书申请自动登记的验证记录
    written: { textKey: 'certd.dns.statusWritten', type: 'success' },
    cleaned: { textKey: 'certd.dns.statusCleaned', type: 'info' },
    error: { textKey: 'certd.dns.statusError', type: 'danger' },
  }

  const statusMeta = (status: string) => {
    const meta = STATUS_META[status]
    return { text: meta ? $t(meta.textKey) : status || $t('certd.common.unknown'), type: meta?.type || ('info' as const) }
  }

  /** 来源：manual 手动登记 / acme 证书申请 / cloud 云厂商免费证书 */
  const SOURCE_META: Record<string, { textKey: string; type: TagKind }> = {
    manual: { textKey: 'certd.dns.sourceManual', type: 'primary' },
    acme: { textKey: 'certd.dns.sourceAcme', type: 'success' },
    cloud: { textKey: 'certd.dns.sourceCloud', type: 'warning' },
  }

  /** 自动登记的验证记录只读：页面上不给同步 / 编辑 / 校验 */
  const isManual = (row: any) => (row?.source || 'manual') === 'manual'

  const sourceMeta = (row: any) => {
    const key = row?.source || 'manual'
    const meta = SOURCE_META[key]
    const text = meta ? $t(meta.textKey) : key
    const type = meta?.type || ('info' as TagKind)
    const hint = isManual(row)
      ? $t('certd.dns.sourceHintManual')
      : $t('certd.dns.sourceHintAuto', { name: row?.pipelineTitle || $t('certd.dns.pipelineDeleted') })
    return { text, type, hint }
  }

  const dnsAccess = ref<any[]>([])
  const busyId = ref(0)

  const loadAccess = async () => {
    dnsAccess.value = (await fetchAccessOptions({ category: 'dns' })) || []
  }

  const accessName = (id: number) =>
    dnsAccess.value.find((item) => item.id === id)?.name || $t('certd.dns.accessName', { id })

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }

  const handleReset = () => resetSearchParams()

  const dialogVisible = ref(false)
  const editingId = ref(0)
  const saving = ref(false)
  const checking = ref(false)
  const form = reactive({
    domain: '',
    recordValue: '',
    accessId: undefined as number | undefined,
    remark: '',
    sync: true,
  })

  const openCreate = () => {
    editingId.value = 0
    form.domain = ''
    form.recordValue = ''
    form.accessId = undefined
    form.remark = ''
    form.sync = true
    dialogVisible.value = true
  }

  const openEdit = (row: any) => {
    editingId.value = row.id
    form.domain = row.domain
    form.recordValue = row.recordValue
    form.accessId = row.accessId || undefined
    form.remark = row.remark
    form.sync = false
    dialogVisible.value = true
  }

  const checkNow = async () => {
    if (!form.domain.trim() || !form.recordValue.trim()) {
      ElMessage.warning($t('certd.dns.needDomainValue'))
      return
    }
    checking.value = true
    try {
      const res = await checkCnameValue({
        domain: form.domain.trim(),
        expected: form.recordValue.trim(),
      })
      if (res?.success) ElMessage.success(res.message || $t('certd.dns.pointOk'))
      else ElMessage.error(res?.message || $t('certd.dns.pointFail'))
    } finally {
      checking.value = false
    }
  }

  const save = async () => {
    if (!form.domain.trim()) {
      ElMessage.warning($t('certd.dns.domainRequired'))
      return
    }
    if (!form.recordValue.trim()) {
      ElMessage.warning($t('certd.dns.valueRequired'))
      return
    }
    const payload = {
      domain: form.domain.trim(),
      recordValue: form.recordValue.trim(),
      accessId: form.accessId || 0,
      remark: form.remark.trim(),
      sync: form.sync,
    }
    saving.value = true
    try {
      if (editingId.value) await updateCname(editingId.value, payload)
      else await createCname(payload)
      dialogVisible.value = false
      refreshData()
    } finally {
      saving.value = false
    }
  }

  const sync = async (row: any) => {
    busyId.value = row.id
    try {
      const res = await syncCname(row.id)
      ElMessage.success(res?.status === 'error' ? $t('certd.dns.syncFailed') : $t('certd.dns.syncedOk'))
      refreshData()
    } finally {
      busyId.value = 0
    }
  }

  const verify = async (row: any) => {
    busyId.value = row.id
    try {
      const res = await verifyCname(row.id)
      if (res?.success) ElMessage.success(res.message || $t('certd.dns.pointOk'))
      else ElMessage.error(res?.message || $t('certd.dns.pointFail'))
      refreshData()
    } finally {
      busyId.value = 0
    }
  }

  const remove = async (row: any) => {
    const manual = isManual(row)
    await ElMessageBox.confirm(
      manual
        ? $t('certd.dns.confirmDeleteManual', { name: row.domain })
        : $t('certd.dns.confirmDeleteAuto', { name: row.domain }),
      manual ? $t('certd.dns.deleteTitleManual') : $t('certd.dns.deleteTitleAuto'),
      { type: 'warning', confirmButtonText: $t('certd.common.confirm'), cancelButtonText: $t('certd.common.cancel') }
    )
    await deleteCname(row.id, manual)
    refreshData()
  }

  onMounted(loadAccess)
</script>

<style scoped>
  .cell-main {
    font-weight: 500;
    word-break: break-all;
  }

  .cell-sub {
    margin-top: 2px;
    font-size: 12px;
    color: var(--art-gray-500);
    word-break: break-all;
  }

  .mono {
    font-family: var(--font-mono);
    font-size: 12px;
    word-break: break-all;
  }

  /* 记录值：类型标签 + 单行省略（TXT 值很长，完整内容在 tooltip 里） */
  .cell-value {
    display: flex;
    gap: 6px;
    align-items: center;
    min-width: 0;
  }

  .type-tag {
    flex: 0 0 auto;
  }

  .cell-value .ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    word-break: normal;
  }

  .cell-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }

  .dialog-footer-right {
    display: flex;
    gap: 8px;
  }
</style>
