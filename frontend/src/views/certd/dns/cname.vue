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
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />新增 CNAME 记录
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
            主域名 {{ row.mainDomain }} · 主机记录 {{ row.hostRecord }}
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
          <span v-if="!row.accessId" class="cell-sub">仅本地登记</span>
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
            <div class="cell-sub">{{ row.verifyTime ? '最近校验 ' + row.verifyTime : '未校验' }}</div>
          </template>
          <template v-else>
            <div class="cell-sub">写入 {{ row.writeCount || 1 }} 次</div>
            <div class="cell-sub">
              {{ row.status === 'cleaned'
                ? '清理于 ' + (row.cleanedTime || row.updateTime)
                : '最近 ' + (row.updateTime || row.createTime) }}
            </div>
          </template>
        </template>
        <template #operation="{ row }">
          <!-- 自动登记的验证记录由流水线写入 / 清理，页面只读，不提供同步与校验 -->
          <div v-if="isManual(row)" class="cell-actions">
            <ElButton link :disabled="!row.accessId" :loading="busyId === row.id" @click="sync(row)">
              同步
            </ElButton>
            <ElButton link :loading="busyId === row.id" @click="verify(row)">校验</ElButton>
            <ElButton link @click="openEdit(row)">编辑</ElButton>
            <ElButton link type="danger" @click="remove(row)">删除</ElButton>
          </div>
          <div v-else class="cell-actions">
            <span class="cell-sub">自动登记</span>
            <ElButton link type="danger" @click="remove(row)">删除</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog
      v-model="dialogVisible"
      :title="editingId ? '编辑 CNAME 记录' : '新增 CNAME 记录'"
      width="min(560px, 94vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElFormItem label="域名（记录名）">
          <ElInput v-model="form.domain" placeholder="_acme-challenge.example.com 或 www.example.com" />
        </ElFormItem>
        <ElFormItem label="记录值（CNAME 目标）">
          <ElInput v-model="form.recordValue" placeholder="abc123.cname.example.net" />
        </ElFormItem>
        <ElFormItem label="DNS 授权">
          <ElSelect
            v-model="form.accessId"
            placeholder="可选，绑定后可直接同步到服务商"
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
        <ElFormItem v-if="form.accessId" label="保存后立即同步">
          <ElSwitch v-model="form.sync" />
        </ElFormItem>
        <ElFormItem label="备注">
          <ElInput v-model="form.remark" placeholder="可选" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton :loading="checking" @click="checkNow">校验当前指向</ElButton>
          <div class="dialog-footer-right">
            <ElButton @click="dialogVisible = false">取消</ElButton>
            <ElButton type="primary" :loading="saving" @click="save">保存</ElButton>
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

  defineOptions({ name: 'CertdDnsCname' })

  const searchForm = ref<Record<string, any>>({
    keyword: undefined,
    status: undefined,
    source: undefined,
  })
  const searchItems = [
    { key: 'keyword', label: '域名', type: 'input', placeholder: '搜索域名 / 记录值 / 流水线' },
    {
      key: 'source',
      label: '来源',
      type: 'select',
      options: [
        { label: '手动登记', value: 'manual' },
        { label: '证书申请', value: 'acme' },
        { label: '云厂商证书', value: 'cloud' },
      ],
    },
    {
      key: 'status',
      label: '状态',
      type: 'select',
      options: [
        { label: '待同步', value: 'pending' },
        { label: '已同步', value: 'synced' },
        { label: '已生效', value: 'valid' },
        { label: '已写入', value: 'written' },
        { label: '已清理', value: 'cleaned' },
        { label: '异常', value: 'error' },
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
      apiFn: fetchCnameList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { prop: 'domain', label: '域名', minWidth: 250, useSlot: true },
        { prop: 'recordValue', label: '记录值', minWidth: 220, useSlot: true },
        { prop: 'source', label: '来源', width: 120, useSlot: true },
        { prop: 'accessId', label: 'DNS 授权', minWidth: 150, useSlot: true },
        { prop: 'status', label: '状态', width: 110, useSlot: true },
        { prop: 'updateTime', label: '最近活动', width: 180, useSlot: true },
        { prop: 'remark', label: '备注', minWidth: 130 },
        { prop: 'operation', label: '操作', width: 210, fixed: 'right', useSlot: true },
      ],
    },
  })

  type TagKind = 'info' | 'primary' | 'success' | 'warning' | 'danger'

  const STATUS_META: Record<string, { text: string; type: TagKind }> = {
    // 手动登记的 CNAME
    pending: { text: '待同步', type: 'info' },
    synced: { text: '已同步', type: 'primary' },
    valid: { text: '已生效', type: 'success' },
    // 证书申请自动登记的验证记录
    written: { text: '已写入', type: 'success' },
    cleaned: { text: '已清理', type: 'info' },
    error: { text: '异常', type: 'danger' },
  }

  const statusMeta = (status: string) => STATUS_META[status] || { text: status || '未知', type: 'info' as const }

  /** 来源：manual 手动登记 / acme 证书申请 / cloud 云厂商免费证书 */
  const SOURCE_META: Record<string, { text: string; type: TagKind }> = {
    manual: { text: '手动登记', type: 'primary' },
    acme: { text: '证书申请', type: 'success' },
    cloud: { text: '云厂商证书', type: 'warning' },
  }

  /** 自动登记的验证记录只读：页面上不给同步 / 编辑 / 校验 */
  const isManual = (row: any) => (row?.source || 'manual') === 'manual'

  const sourceMeta = (row: any) => {
    const key = row?.source || 'manual'
    const meta = SOURCE_META[key] || { text: key, type: 'info' as TagKind }
    const hint = isManual(row)
      ? '手动登记的 CNAME：可同步到对端、校验是否生效'
      : '证书申请自动写入的验证记录（来源流水线：' +
        (row?.pipelineTitle || '已删除的流水线') +
        '），只读'
    return { ...meta, hint }
  }

  const dnsAccess = ref<any[]>([])
  const busyId = ref(0)

  const loadAccess = async () => {
    dnsAccess.value = (await fetchAccessOptions({ category: 'dns' })) || []
  }

  const accessName = (id: number) => dnsAccess.value.find((item) => item.id === id)?.name || '授权 ' + id

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
      ElMessage.warning('请先填写域名与记录值')
      return
    }
    checking.value = true
    try {
      const res = await checkCnameValue({
        domain: form.domain.trim(),
        expected: form.recordValue.trim(),
      })
      if (res?.success) ElMessage.success(res.message || 'CNAME 指向正确')
      else ElMessage.error(res?.message || 'CNAME 尚未生效')
    } finally {
      checking.value = false
    }
  }

  const save = async () => {
    if (!form.domain.trim()) {
      ElMessage.warning('请填写域名')
      return
    }
    if (!form.recordValue.trim()) {
      ElMessage.warning('请填写记录值')
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
      ElMessage.success(res?.status === 'error' ? '同步失败，请查看状态说明' : '已同步到 DNS 服务商')
      refreshData()
    } finally {
      busyId.value = 0
    }
  }

  const verify = async (row: any) => {
    busyId.value = row.id
    try {
      const res = await verifyCname(row.id)
      if (res?.success) ElMessage.success(res.message || 'CNAME 指向正确')
      else ElMessage.error(res?.message || 'CNAME 尚未生效')
      refreshData()
    } finally {
      busyId.value = 0
    }
  }

  const remove = async (row: any) => {
    const manual = isManual(row)
    await ElMessageBox.confirm(
      manual
        ? '确定删除 CNAME 记录「' + row.domain + '」吗？已同步到 DNS 服务商的记录会一并删除。'
        : '确定删除这条验证记录留痕「' + row.domain + '」吗？只删本地记录，不影响 DNS 解析。',
      manual ? '删除 CNAME 记录' : '删除 DNS 记录留痕',
      { type: 'warning' }
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
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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
