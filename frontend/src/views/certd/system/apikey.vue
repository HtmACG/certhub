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
          <div class="apikey-title">对外接口</div>
          <p class="apikey-desc">
            请求头带上 <code>X-API-Key</code> 与 <code>X-API-Secret</code> 即可调用：
            <code>GET /api/open/v1/pipelines</code>、
            <code>POST /api/open/v1/pipelines/{id}/run</code>、
            <code>GET /api/open/v1/certs</code>。
          </p>
        </div>
        <ElButton type="primary" @click="createVisible = true">
          <ArtSvgIcon icon="ri:key-2-line" class="mr-1" />创建密钥
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
              批量删除<template v-if="selectedIds.length">（{{ selectedIds.length }}）</template>
            </ElButton>
            <span class="cell-sub">共 {{ list.length }} 个密钥</span>
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
            {{ row.enabled ? '启用' : '停用' }}
          </ElTag>
        </template>
        <template #operation="{ row }">
          <ElButton link type="danger" @click="remove(row)">删除</ElButton>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog v-model="createVisible" title="创建 API 密钥" width="min(460px, 94vw)">
      <ElForm label-position="top">
        <ElFormItem label="密钥名称">
          <ElInput v-model="createName" placeholder="例如：运维脚本" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="createVisible = false">取消</ElButton>
          <ElButton type="primary" :loading="creating" @click="create">创建</ElButton>
        </div>
      </template>
    </ElDialog>

    <ElDialog v-model="secretVisible" title="密钥已创建" width="min(560px, 94vw)">
      <ElAlert type="warning" :closable="false" class="mb-3">
        密钥只在创建时显示一次，请立刻复制保存。
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
          <ElButton @click="copySecret">复制密钥</ElButton>
          <ElButton type="primary" @click="secretVisible = false">我已保存</ElButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { createApiKey, deleteApiKey, fetchApiKeys } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useBatchDelete } from '../composables/use-batch-delete'

  defineOptions({ name: 'CertdSystemApiKey' })

  const loading = ref(false)
  const list = ref<any[]>([])
  const createVisible = ref(false)
  const secretVisible = ref(false)
  const createName = ref('')
  const creating = ref(false)
  const created = ref<any>({})

  const columns = computed(() => [
    { type: 'selection', width: 48 },
    { prop: 'name', label: '名称', minWidth: 160 },
    { prop: 'keyId', label: 'Key ID', minWidth: 200 },
    { prop: 'enabled', label: '状态', width: 100, useSlot: true },
    { prop: 'lastUsedTime', label: '最近使用', width: 170 },
    { prop: 'createTime', label: '创建时间', width: 170 },
    { prop: 'operation', label: '操作', width: 100, fixed: 'right', useSlot: true },
  ])

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteApiKey,
    { label: '密钥', nameOf: (row: any) => row.name, onDone: () => load() }
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
      ElMessage.warning('请填写密钥名称')
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
      ElMessage.success('已复制')
    } catch {
      ElMessage.error('复制失败')
    }
  }

  const remove = async (row: any) => {
    await ElMessageBox.confirm('删除后使用该密钥的外部系统会立即失效，确定吗？', '删除密钥', {
      type: 'warning',
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
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    background: var(--art-gray-100);
    border-radius: 4px;
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
