<!--
  域名管理
  =========================================================
  记录「域名 → 验证方式 → DNS 授权」的对应关系。
  申请证书时可以直接对照这里选择授权，不用回想哪个域名该用哪家 DNS。
-->
<template>
  <div class="certd-domain art-full-height g-scope">
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
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />新增域名
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
        <template #verifyType="{ row }">
          <ElTag size="small" effect="plain">{{ verifyText(row.verifyType) }}</ElTag>
        </template>
        <template #accessId="{ row }">
          <span v-if="!row.accessId" class="cell-sub">未绑定</span>
          <span v-else>{{ accessName(row.accessId) }}</span>
        </template>
        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton link @click="openEdit(row)">编辑</ElButton>
            <ElButton link type="danger" @click="remove(row)">删除</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog
      v-model="dialogVisible"
      :title="editingId ? '编辑域名' : '新增域名'"
      width="min(520px, 94vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElFormItem label="域名">
          <ElInput v-model="form.domain" placeholder="example.com 或 *.example.com" />
        </ElFormItem>
        <ElFormItem label="验证方式">
          <ElRadioGroup v-model="form.verifyType">
            <ElRadioButton label="dns">DNS 验证</ElRadioButton>
            <ElRadioButton label="http">HTTP 验证</ElRadioButton>
          </ElRadioGroup>
        </ElFormItem>
        <ElFormItem label="DNS 授权">
          <ElSelect v-model="form.accessId" placeholder="可选，绑定后申请证书更快" clearable class="w-full">
            <ElOption
              v-for="item in dnsAccess"
              :key="item.id"
              :label="item.name + '（' + item.typeName + '）'"
              :value="item.id"
            />
          </ElSelect>
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
    createDomain,
    deleteDomain,
    fetchAccessOptions,
    fetchDomainList,
    updateDomain,
  } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useBatchDelete } from '../composables/use-batch-delete'

  defineOptions({ name: 'CertdDomain' })

  const searchForm = ref<Record<string, any>>({ keyword: undefined })
  const searchItems = [{ key: 'keyword', label: '域名', type: 'input', placeholder: '搜索域名' }]

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
      apiFn: fetchDomainList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { type: 'selection', width: 48 },
        { prop: 'domain', label: '域名', minWidth: 220 },
        { prop: 'verifyType', label: '验证方式', width: 120, useSlot: true },
        { prop: 'accessId', label: 'DNS 授权', minWidth: 180, useSlot: true },
        { prop: 'remark', label: '备注', minWidth: 160 },
        { prop: 'createTime', label: '添加时间', width: 170 },
        { prop: 'operation', label: '操作', width: 140, fixed: 'right', useSlot: true },
      ],
    },
  })

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteDomain,
    { label: '域名', nameOf: (row: any) => row.domain, onDone: () => refreshData() }
  )

  const dnsAccess = ref<any[]>([])

  const loadAccess = async () => {
    dnsAccess.value = (await fetchAccessOptions({ category: 'dns' })) || []
  }

  const accessName = (id: number) => dnsAccess.value.find((item) => item.id === id)?.name || '授权 ' + id

  const verifyText = (type: string) => {
    const map: Record<string, string> = { dns: 'DNS 验证', http: 'HTTP 验证', cname: 'CNAME 验证' }
    return map[type] || type
  }

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }

  const handleReset = () => resetSearchParams()

  const dialogVisible = ref(false)
  const editingId = ref(0)
  const saving = ref(false)
  const form = reactive({ domain: '', verifyType: 'dns', accessId: undefined as number | undefined, remark: '' })

  const openCreate = () => {
    editingId.value = 0
    form.domain = ''
    form.verifyType = 'dns'
    form.accessId = undefined
    form.remark = ''
    dialogVisible.value = true
  }

  const openEdit = (row: any) => {
    editingId.value = row.id
    form.domain = row.domain
    form.verifyType = row.verifyType
    form.accessId = row.accessId || undefined
    form.remark = row.remark
    dialogVisible.value = true
  }

  const save = async () => {
    if (!form.domain.trim()) {
      ElMessage.warning('请填写域名')
      return
    }
    const payload = { ...form, accessId: form.accessId || 0 }
    saving.value = true
    try {
      if (editingId.value) await updateDomain(editingId.value, payload)
      else await createDomain(payload)
      dialogVisible.value = false
      refreshData()
    } finally {
      saving.value = false
    }
  }

  const remove = async (row: any) => {
    await ElMessageBox.confirm('确定删除域名「' + row.domain + '」吗？', '删除域名', { type: 'warning' })
    await deleteDomain(row.id)
    ElMessage.success('已删除')
    refreshData()
  }

  onMounted(loadAccess)
</script>

<style scoped>
  .cell-sub {
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .cell-actions {
    display: flex;
    gap: 4px;
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
