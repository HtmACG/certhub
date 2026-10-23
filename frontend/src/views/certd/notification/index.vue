<!--
  通知渠道
  =========================================================
  与授权管理同一套元数据驱动：类型清单与字段都来自后端 NOTIFY_TYPES。
  每条渠道可「发一条测试消息」，避免证书到期提醒发不出去却没人发现。
-->
<template>
  <div class="certd-notification art-full-height g-scope">
    <ElCard class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="refreshData">
        <template #left>
          <ElSpace wrap>
            <ElButton type="primary" @click="openCreate">
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />新增通知渠道
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
        <template #name="{ row }">
          <div class="cell-name">
            <span class="cell-title">{{ row.name }}</span>
            <ElTag v-if="row.isDefault" size="small" type="primary" effect="plain">默认</ElTag>
          </div>
        </template>

        <template #enabled="{ row }">
          <ElTag :type="row.enabled ? 'success' : 'info'" size="small" effect="light">
            {{ row.enabled ? '已启用' : '已停用' }}
          </ElTag>
        </template>

        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton link type="primary" :loading="testingId === row.id" @click="test(row)">
              测试
            </ElButton>
            <ElButton link @click="openEdit(row)">编辑</ElButton>
            <ElButton link type="danger" @click="remove(row)">删除</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDrawer
      v-model="dialogVisible"
      :title="editingId ? '编辑通知渠道' : '新增通知渠道'"
      size="min(680px, 96vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElFormItem label="通知类型">
          <ElSelect v-model="form.type" placeholder="选择通知类型" class="w-full" @change="onTypeChange">
            <ElOption
              v-for="(meta, key) in notifyTypes"
              :key="key"
              :label="meta.name"
              :value="key"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="渠道名称">
          <ElInput v-model="form.name" placeholder="例如：运维钉钉群" />
        </ElFormItem>
        <ElFormItem label="启用">
          <ElSwitch v-model="form.enabled" />
          <span class="form-tip ml-2">停用后流水线不会再用它发通知</span>
        </ElFormItem>
        <ElFormItem label="设为默认">
          <ElSwitch v-model="form.isDefault" />
          <span class="form-tip ml-2">不指定通知渠道的任务会用它</span>
        </ElFormItem>
        <PluginForm v-if="currentType" v-model="form.config" :fields="currentType.inputs" :span="12" />
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="dialogVisible = false">取消</ElButton>
          <ElButton type="primary" :loading="saving" @click="save">保存</ElButton>
        </div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import {
    createNotification,
    deleteNotification,
    fetchNotificationList,
    testNotification,
    updateNotification,
  } from '@/api/certd'
  import type { NotificationItem } from '@/api/certd'
  import { usePluginStore } from '@/store/modules/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useBatchDelete } from '../composables/use-batch-delete'
  import PluginForm from '../components/plugin-form.vue'

  defineOptions({ name: 'CertdNotification' })

  const pluginStore = usePluginStore()
  const notifyTypes = computed(() => pluginStore.notifyTypes)

  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    handleSizeChange,
    handleCurrentChange,
    refreshData,
  } = useTable({
    core: {
      apiFn: fetchNotificationList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { type: 'selection', width: 48 },
        { prop: 'name', label: '渠道名称', minWidth: 200, useSlot: true },
        { prop: 'typeName', label: '类型', width: 160 },
        { prop: 'enabled', label: '状态', width: 110, useSlot: true },
        { prop: 'createTime', label: '创建时间', width: 170 },
        { prop: 'operation', label: '操作', width: 180, fixed: 'right', useSlot: true },
      ],
    },
  })

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteNotification,
    { label: '通知渠道', nameOf: (row: any) => row.name, onDone: () => refreshData() }
  )

  const dialogVisible = ref(false)
  const editingId = ref(0)
  const saving = ref(false)
  const testingId = ref(0)

  const form = reactive({
    type: '',
    name: '',
    enabled: true,
    isDefault: false,
    config: {} as Record<string, any>,
  })

  const currentType = computed(() => notifyTypes.value[form.type])

  const resetConfig = () => {
    const config: Record<string, any> = {}
    for (const field of currentType.value?.inputs || []) {
      if (field.default !== undefined) {
        config[field.key] = Array.isArray(field.default) ? [...field.default] : field.default
      } else if (field.component === 'switch') {
        config[field.key] = false
      } else {
        config[field.key] = ''
      }
    }
    form.config = config
  }

  const onTypeChange = () => {
    resetConfig()
    if (!form.name) form.name = currentType.value?.name || ''
  }

  const openCreate = () => {
    editingId.value = 0
    form.type = 'email'
    form.name = ''
    form.enabled = true
    form.isDefault = false
    resetConfig()
    dialogVisible.value = true
  }

  const openEdit = (row: NotificationItem) => {
    editingId.value = row.id
    form.type = row.type
    form.name = row.name
    form.enabled = row.enabled
    form.isDefault = row.isDefault
    form.config = { ...(row.config || {}) }
    dialogVisible.value = true
  }

  const save = async () => {
    if (!form.type) {
      ElMessage.warning('请选择通知类型')
      return
    }
    if (!form.name.trim()) {
      ElMessage.warning('请填写渠道名称')
      return
    }
    const config: Record<string, any> = {}
    for (const [key, value] of Object.entries(form.config || {})) {
      config[key] = typeof value === 'string' ? value.trim() : value
    }
    const payload = { ...form, name: form.name.trim(), config }
    saving.value = true
    try {
      if (editingId.value) {
        await updateNotification(editingId.value, payload)
        ElMessage.success('已保存')
      } else {
        await createNotification(payload)
        ElMessage.success('已添加')
      }
      dialogVisible.value = false
      refreshData()
    } finally {
      saving.value = false
    }
  }

  const test = async (row: NotificationItem) => {
    testingId.value = row.id
    try {
      const result = await testNotification(row.id)
      if (result?.success) ElMessage.success(result.message || '发送成功')
      else ElMessageBox.alert(result?.message || '发送失败', '测试结果', { type: 'warning' })
    } finally {
      testingId.value = 0
    }
  }

  const remove = async (row: NotificationItem) => {
    await ElMessageBox.confirm('确定删除「' + row.name + '」吗？', '删除通知渠道', {
      type: 'warning',
    })
    await deleteNotification(row.id)
    ElMessage.success('已删除')
    refreshData()
  }

  onMounted(() => pluginStore.ensureLoaded())
</script>

<style scoped>
  .cell-name {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .cell-title {
    font-weight: 500;
  }

  .cell-actions {
    display: flex;
    gap: 4px;
    align-items: center;
  }

  .form-tip {
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
