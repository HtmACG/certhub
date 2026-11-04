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
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />{{ $t('certd.dns.subdomainCreate') }}
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
          <div class="cell-sub">{{ $t('certd.dns.subdomainIndependent') }}</div>
        </template>
        <template #accessId="{ row }">
          <span v-if="!row.accessId" class="cell-sub">{{ $t('certd.dns.unbound') }}</span>
          <span v-else>{{ accessName(row.accessId) }}</span>
        </template>
        <template #disabled="{ row }">
          <ElTag :type="row.disabled ? 'info' : 'success'" size="small" effect="plain">
            {{ row.disabled ? $t('certd.common.disabled') : $t('certd.common.enabled') }}
          </ElTag>
        </template>
        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton link :loading="busyId === row.id" @click="verify(row)">{{ $t('certd.dns.subdomainVerifyNs') }}</ElButton>
            <ElButton link @click="openEdit(row)">{{ $t('certd.dns.edit') }}</ElButton>
            <ElButton link type="danger" @click="remove(row)">{{ $t('certd.dns.delete') }}</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog
      v-model="dialogVisible"
      :title="editingId ? $t('certd.dns.subdomainEdit') : $t('certd.dns.subdomainCreate')"
      width="min(520px, 94vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElFormItem :label="$t('certd.dns.subdomainLabel')">
          <ElInput v-model="form.domain" placeholder="apps.example.com" />
          <div class="form-tip">{{ $t('certd.dns.subdomainHint') }}</div>
        </ElFormItem>
        <ElFormItem :label="$t('certd.dns.colAccess')">
          <ElSelect
            v-model="form.accessId"
            :placeholder="$t('certd.dns.subdomainAccessPh')"
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
        <ElFormItem :label="$t('certd.group.enableLabel')">
          <ElSwitch v-model="form.disabled" :active-value="false" :inactive-value="true" />
          <span class="switch-text">{{ form.disabled ? $t('certd.common.disabled') : $t('certd.common.enabled') }}</span>
        </ElFormItem>
        <ElFormItem :label="$t('certd.table.remark')">
          <ElInput v-model="form.remark" :placeholder="$t('certd.common.optional')" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="dialogVisible = false">{{ $t('certd.dns.cancel') }}</ElButton>
          <ElButton type="primary" :loading="saving" @click="save">{{ $t('certd.dns.save') }}</ElButton>
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
  import { $t } from '@/locales'

  defineOptions({ name: 'CertdDnsSubdomain' })

  const searchForm = ref<Record<string, any>>({ keyword: undefined })
  const searchItems = [
    {
      key: 'keyword',
      label: $t('certd.dns.subdomainLabel'),
      type: 'input',
      placeholder: $t('certd.dns.subdomainKeywordPh'),
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
      apiFn: fetchSubdomainList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { prop: 'domain', label: $t('certd.dns.subdomainLabel'), minWidth: 260, useSlot: true },
        { prop: 'accessId', label: $t('certd.dns.colAccess'), minWidth: 180, useSlot: true },
        { prop: 'disabled', label: $t('certd.dns.colStatus'), width: 110, useSlot: true },
        { prop: 'remark', label: $t('certd.table.remark'), minWidth: 160 },
        { prop: 'createTime', label: $t('certd.table.createdAt'), width: 190 },
        { prop: 'operation', label: $t('certd.common.actions'), width: 200, fixed: 'right', useSlot: true },
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
      ElMessage.warning($t('certd.dns.subdomainRequired'))
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
        const detail = res.ns?.length
          ? $t('certd.dns.nsDelegatedTo') + '\n' + res.ns.join('\n')
          : $t('certd.dns.nsOk')
        ElMessageBox.alert(detail, $t('certd.dns.verifyPassed'), {
          type: 'success',
          confirmButtonText: $t('certd.common.confirm'),
        })
      } else {
        ElMessageBox.alert(res?.message || $t('certd.dns.verifyFailed'), $t('certd.dns.verifyFailed'), {
          type: 'warning',
          confirmButtonText: $t('certd.common.confirm'),
        })
      }
    } finally {
      busyId.value = 0
    }
  }

  const remove = async (row: any) => {
    await ElMessageBox.confirm($t('certd.dns.confirmDeleteSubdomain', { name: row.domain }), $t('certd.dns.deleteSubdomainTitle'), {
      type: 'warning',
      confirmButtonText: $t('certd.common.confirm'),
      cancelButtonText: $t('certd.common.cancel'),
    })
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
