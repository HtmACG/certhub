<!--
  开放接口（API Key）
  =========================================================
  给外部系统用的密钥：可以列流水线、触发运行、读取证书。
  密钥只在创建时明文显示一次，之后库里只存加密值。
-->
<template>
  <div class="certd-apikey art-full-height g-scope">
    <ElCard class="art-card mb-3" shadow="never">
      <div class="apikey-head">
        <div>
          <div class="apikey-title">{{ $t('certd.apikey.headTitle') }}</div>
          <p class="apikey-desc">
            {{ $t('certd.apikey.headDescBefore') }}<code>X-API-Key</code> {{ $t('certd.apikey.headDescAnd') }}
            <code>X-API-Secret</code>{{ $t('certd.apikey.headDescAfter') }}
            <code>GET /api/open/v1/pipelines</code>
            <code>POST /api/open/v1/pipelines/{id}/run</code>
            <code>GET /api/open/v1/certs</code>
          </p>
        </div>
        <ElButton type="primary" @click="createVisible = true">
          <ArtSvgIcon icon="ri:key-2-line" class="mr-1" />{{ $t('certd.apikey.create') }}
        </ElButton>
      </div>
    </ElCard>

    <ElCard class="art-table-card">
      <ArtTableHeader :loading="loading" @refresh="load">
        <template #left>
          <ElSpace wrap>
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
            <span class="cell-sub">{{ $t('certd.apikey.totalPrefix') }}{{ list.length }}{{ $t('certd.apikey.totalSuffix') }}</span>
          </ElSpace>
        </template>
      </ArtTableHeader>
      <ArtTable
        :data="list"
        :columns="columns"
        :loading="loading"
        :pagination="undefined"
        row-key="id"
        @selection-change="handleSelectionChange"
      >
        <template #enabled="{ row }">
          <ElTag :type="row.enabled ? 'success' : 'info'" size="small" effect="light">
            {{ row.enabled ? $t('certd.common.enable') : $t('certd.common.disable') }}
          </ElTag>
        </template>
        <template #operation="{ row }">
          <ElButton link type="danger" @click="remove(row)">{{ $t('certd.common.delete') }}</ElButton>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog v-model="createVisible" :title="$t('certd.apikey.createTitle')" width="min(460px, 94vw)">
      <ElForm label-position="top">
        <ElFormItem :label="$t('certd.apikey.nameLabel')">
          <ElInput v-model="createName" :placeholder="$t('certd.apikey.namePh')" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="createVisible = false">{{ $t('certd.common.cancel') }}</ElButton>
          <ElButton type="primary" :loading="creating" @click="create">{{ $t('certd.common.create') }}</ElButton>
        </div>
      </template>
    </ElDialog>

    <ElDialog v-model="secretVisible" :title="$t('certd.apikey.createdTitle')" width="min(560px, 94vw)">
      <ElAlert type="warning" :closable="false" class="mb-3">
        {{ $t('certd.apikey.secretWarn') }}
      </ElAlert>
      <ElDescriptions :column="1" border>
        <ElDescriptionsItem label="X-API-Key">
          <span class="mono">{{ created.keyId }}</span>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="X-API-Secret">
          <span class="mono break-all">{{ created.secret }}</span>
        </ElDescriptionsItem>
      </ElDescriptions>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="copySecret">{{ $t('certd.apikey.copySecret') }}</ElButton>
          <ElButton type="primary" @click="secretVisible = false">{{ $t('certd.apikey.saved') }}</ElButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import type { ColumnOption } from '@/types'
  import { createApiKey, deleteApiKey, fetchApiKeys } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useBatchDelete } from '../composables/use-batch-delete'
  import { $t } from '@/locales'

  defineOptions({ name: 'CertdSystemApiKey' })

  const loading = ref(false)
  const list = ref<any[]>([])
  const createVisible = ref(false)
  const secretVisible = ref(false)
  const createName = ref('')
  const creating = ref(false)
  const created = ref<any>({})

  const columns = computed<ColumnOption[]>(() => [
    { type: 'selection', width: 48 },
    { prop: 'name', label: $t('certd.table.name'), minWidth: 160 },
    { prop: 'keyId', label: 'Key ID', minWidth: 200 },
    { prop: 'enabled', label: $t('certd.table.status'), width: 110, useSlot: true },
    { prop: 'lastUsedTime', label: $t('certd.apikey.colLastUsed'), width: 190 },
    { prop: 'createTime', label: $t('certd.table.createdAt'), width: 190 },
    { prop: 'operation', label: $t('certd.common.actions'), width: 110, fixed: 'right', useSlot: true },
  ])

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteApiKey,
    { label: () => $t('certd.apikey.itemLabel'), nameOf: (row: any) => row.name, onDone: () => load() }
  )

  const load = async () => {
    loading.value = true
    try {
      list.value = (await fetchApiKeys()) || []
    } finally {
      loading.value = false
    }
  }

  const create = async () => {
    if (!createName.value.trim()) {
      ElMessage.warning($t('certd.apikey.nameRequired'))
      return
    }
    creating.value = true
    try {
      created.value = await createApiKey({ name: createName.value.trim() })
      createVisible.value = false
      secretVisible.value = true
      createName.value = ''
      load()
    } finally {
      creating.value = false
    }
  }

  const copySecret = async () => {
    try {
      await navigator.clipboard.writeText(
        'X-API-Key: ' + created.value.keyId + '\nX-API-Secret: ' + created.value.secret
      )
      ElMessage.success($t('certd.common.copied'))
    } catch {
      ElMessage.error($t('certd.common.copyFailed'))
    }
  }

  const remove = async (row: any) => {
    await ElMessageBox.confirm($t('certd.apikey.confirmDelete'), $t('certd.apikey.deleteTitle'), {
      type: 'warning',
      confirmButtonText: $t('certd.common.confirm'),
      cancelButtonText: $t('certd.common.cancel'),
    })
    await deleteApiKey(row.id)
    load()
  }

  onMounted(load)
</script>

<style scoped>
  .apikey-head {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
  }

  .apikey-title {
    font-size: 15px;
    font-weight: 600;
  }

  .apikey-desc {
    max-width: 760px;
    margin: 6px 0 0;
    font-size: 12px;
    line-height: 1.7;
    color: var(--art-gray-600);
  }

  .apikey-desc code,
  .mono {
    padding: 1px 4px;
    font-family: var(--font-mono);
    font-size: 12px;
    background: var(--muted);
    border-radius: var(--radius-sm);
  }

  .cell-sub {
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
