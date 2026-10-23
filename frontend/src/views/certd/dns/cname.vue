<!--
  CNAME 记录管理
  =========================================================
  把待申请证书的域名 CNAME 到自己的代理域名，
  之后 ACME 的 TXT 记录只需要写到代理域名，绕开不被支持的服务商。
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
          <span class="mono">{{ row.recordValue }}</span>
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
        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton link :disabled="!row.accessId" :loading="busyId === row.id" @click="sync(row)">
              同步
            </ElButton>
            <ElButton link :loading="busyId === row.id" @click="verify(row)">校验</ElButton>
            <ElButton link @click="openEdit(row)">编辑</ElButton>
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

  const searchForm = ref<Record<string, any>>({ keyword: undefined, status: undefined })
  const searchItems = [
    { key: 'keyword', label: '域名', type: 'input', placeholder: '搜索域名或记录值' },
    {
      key: 'status',
      label: '状态',
      type: 'select',
      options: [
        { label: '待同步', value: 'pending' },
        { label: '已同步', value: 'synced' },
        { label: '已生效', value: 'valid' },
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
        { prop: 'domain', label: '域名', minWidth: 260, useSlot: true },
        { prop: 'recordValue', label: '记录值', minWidth: 220, useSlot: true },
        { prop: 'accessId', label: 'DNS 授权', minWidth: 160, useSlot: true },
        { prop: 'status', label: '状态', width: 110, useSlot: true },
        { prop: 'verifyTime', label: '最近校验', width: 170 },
        { prop: 'remark', label: '备注', minWidth: 140 },
        { prop: 'operation', label: '操作', width: 210, fixed: 'right', useSlot: true },
      ],
    },
  })

  const STATUS_META: Record<string, { text: string; type: 'info' | 'primary' | 'success' | 'danger' }> = {
    pending: { text: '待同步', type: 'info' },
    synced: { text: '已同步', type: 'primary' },
    valid: { text: '已生效', type: 'success' },
    error: { text: '异常', type: 'danger' },
  }

  const statusMeta = (status: string) => STATUS_META[status] || { text: status || '未知', type: 'info' as const }

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
    await ElMessageBox.confirm(
      '确定删除 CNAME 记录「' + row.domain + '」吗？已同步到 DNS 服务商的记录会一并删除。',
      '删除 CNAME 记录',
      { type: 'warning' }
    )
    await deleteCname(row.id, true)
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
