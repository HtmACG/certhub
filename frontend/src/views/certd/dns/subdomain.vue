<!--
  子域名托管
  =========================================================
  免费二级域名在服务商处是独立 zone。登记后申请证书时，
  解析记录会写到该子域名下，而不是错误地写到上级域名。
-->
<template>
  <div class="certd-subdomain art-full-height g-scope">
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
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />新增子域名托管
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
          <div class="cell-sub">作为独立主域名解析</div>
        </template>
        <template #accessId="{ row }">
          <span v-if="!row.accessId" class="cell-sub">未绑定</span>
          <span v-else>{{ accessName(row.accessId) }}</span>
        </template>
        <template #disabled="{ row }">
          <ElTag :type="row.disabled ? 'info' : 'success'" size="small" effect="plain">
            {{ row.disabled ? '已停用' : '已启用' }}
          </ElTag>
        </template>
        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton link :loading="busyId === row.id" @click="verify(row)">校验 NS</ElButton>
            <ElButton link @click="openEdit(row)">编辑</ElButton>
            <ElButton link type="danger" @click="remove(row)">删除</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog
      v-model="dialogVisible"
      :title="editingId ? '编辑子域名托管' : '新增子域名托管'"
      width="min(520px, 94vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElFormItem label="子域名">
          <ElInput v-model="form.domain" placeholder="apps.example.com" />
          <div class="form-tip">
            需要先在上级域名添加 NS 委派记录，校验通过后才会作为独立 zone 使用。
          </div>
        </ElFormItem>
        <ElFormItem label="DNS 授权">
          <ElSelect
            v-model="form.accessId"
            placeholder="可选，绑定后可校验 zone 是否可读"
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
        <ElFormItem label="启用">
          <ElSwitch v-model="form.disabled" :active-value="false" :inactive-value="true" />
          <span class="switch-text">{{ form.disabled ? '已停用' : '已启用' }}</span>
        </ElFormItem>
        <ElFormItem label="备注">
          <ElInput v-model="form.remark" placeholder="可选" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="dialogVisible = false">取消</ElButton>
          <ElButton type="primary" :loading="saving" @click="save">保存</ElButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import {
    createSubdomain,
    deleteSubdomain,
    fetchAccessOptions,
    fetchSubdomainList,
    updateSubdomain,
    verifySubdomain,
  } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'

  defineOptions({ name: 'CertdDnsSubdomain' })

  const searchForm = ref<Record<string, any>>({ keyword: undefined })
  const searchItems = [
    { key: 'keyword', label: '子域名', type: 'input', placeholder: '搜索子域名或备注' },
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
      apiFn: fetchSubdomainList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { prop: 'domain', label: '子域名', minWidth: 260, useSlot: true },
        { prop: 'accessId', label: 'DNS 授权', minWidth: 180, useSlot: true },
        { prop: 'disabled', label: '状态', width: 110, useSlot: true },
        { prop: 'remark', label: '备注', minWidth: 160 },
        { prop: 'createTime', label: '添加时间', width: 170 },
        { prop: 'operation', label: '操作', width: 190, fixed: 'right', useSlot: true },
      ],
    },
  })

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
  const form = reactive({
    domain: '',
    accessId: undefined as number | undefined,
    disabled: false,
    remark: '',
  })

  const openCreate = () => {
    editingId.value = 0
    form.domain = ''
    form.accessId = undefined
    form.disabled = false
    form.remark = ''
    dialogVisible.value = true
  }

  const openEdit = (row: any) => {
    editingId.value = row.id
    form.domain = row.domain
    form.accessId = row.accessId || undefined
    form.disabled = row.disabled
    form.remark = row.remark
    dialogVisible.value = true
  }

  const save = async () => {
    if (!form.domain.trim()) {
      ElMessage.warning('请填写子域名')
      return
    }
    const payload = {
      domain: form.domain.trim(),
      accessId: form.accessId || 0,
      disabled: form.disabled,
      remark: form.remark.trim(),
    }
    saving.value = true
    try {
      if (editingId.value) await updateSubdomain(editingId.value, payload)
      else await createSubdomain(payload)
      dialogVisible.value = false
      refreshData()
    } finally {
      saving.value = false
    }
  }

  const verify = async (row: any) => {
    busyId.value = row.id
    try {
      const res = await verifySubdomain(row.id)
      if (res?.success) {
        const detail = res.ns?.length ? '已委派到：\n' + res.ns.join('\n') : 'NS 委派正常'
        ElMessageBox.alert(detail, '校验通过', { type: 'success' })
      } else {
        ElMessageBox.alert(res?.message || '校验未通过', '校验未通过', { type: 'warning' })
      }
    } finally {
      busyId.value = 0
    }
  }

  const remove = async (row: any) => {
    await ElMessageBox.confirm(
      '确定删除子域名托管「' + row.domain + '」吗？删除后解析记录将退回上级域名。',
      '删除子域名托管',
      { type: 'warning' }
    )
    await deleteSubdomain(row.id)
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
  }

  .cell-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .form-tip {
    margin-top: 6px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--art-gray-500);
  }

  .switch-text {
    margin-left: 8px;
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
