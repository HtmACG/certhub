<!--
  授权管理（凭据）
  =========================================================
  按类别分标签页 + 表格列表：一屏能看到「我有哪些凭据、填了什么、能不能连上」。
  · 类型清单来自后端 ACCESS_TYPES，新增厂商只改后端；
  · 表单字段同样来自元数据，密码框带「小眼睛」看明文；
  · 表格支持多选，选中后可批量删除；
  · 每条授权都能「测试连通性」，不用等到跑流水线才发现密钥填错。
-->
<template>
  <div class="certd-access art-full-height g-scope">
    <ElCard class="art-card mb-3" shadow="never">
      <div class="access-toolbar">
        <div class="access-tabs">
          <div
            v-for="tab in categoryTabs"
            :key="tab.key"
            class="access-tab"
            :class="{ 'is-active': activeCategory === tab.key }"
            @click="switchCategory(tab.key)"
          >
            {{ tab.name }}
            <span class="access-tab-count">{{ tab.count }}</span>
          </div>
        </div>
        <div class="access-tools">
          <ElInput
            v-model="keyword"
            class="access-search"
            :placeholder="$t('certd.access.searchPlaceholder')"
            clearable
          >
            <template #prefix>
              <ArtSvgIcon icon="ri:search-line" />
            </template>
          </ElInput>
          <ElButton type="primary" @click="openCreate()">
            <ArtSvgIcon icon="ri:add-line" class="mr-1" />{{ $t('certd.access.create') }}
          </ElButton>
        </div>
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
            <span class="access-count">
              {{ $t('certd.access.totalPrefix') }}{{ filtered.length }}{{ $t('certd.access.totalSuffix') }}<template v-if="keyword || activeCategory">
                {{ $t('certd.access.filtered') }}</template
              >
            </span>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <ArtTable
        :data="paged"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @selection-change="handleSelectionChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
        <template #name="{ row }">
          <div class="cell-brand">
            <BrandAvatar
              :logo-file="logoFileOf(row.type)"
              :logo="accessTypes[row.type]?.logo"
              :short="accessTypes[row.type]?.short"
              :color="accessTypes[row.type]?.color"
              :name="row.typeName"
              :size="30"
            />
            <div class="cell-brand-text">
              <div class="cell-name" :title="row.name">{{ row.name }}</div>
              <!-- 没备注就不渲染这一行：8 行「（无备注）」是纯噪音，还拉高了行高 -->
              <div v-if="row.remark" class="cell-remark" :title="row.remark">
                {{ row.remark }}
              </div>
            </div>
          </div>
        </template>

        <template #typeName="{ row }">
          <div class="cell-type">
            <span class="cell-type-name">{{ row.typeName }}</span>
            <ElTag size="small" effect="plain">
              {{ accessTypes[row.type]?.categoryName || row.category }}
            </ElTag>
          </div>
        </template>

        <template #summary="{ row }">
          <div class="cell-tags">
            <ElTag
              v-for="key in previewKeys(row)"
              :key="key"
              size="small"
              effect="plain"
              class="access-key-tag"
              :title="key"
            >
              {{ key }}
            </ElTag>
            <span v-if="!previewKeys(row).length" class="cell-muted">—</span>
          </div>
        </template>

        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton
              link
              type="primary"
              :loading="testingId === row.id"
              @click="testAccess2(row)"
            >
              {{ $t('certd.access.test') }}
            </ElButton>
            <ElButton link @click="openEdit(row)">{{ $t('certd.common.edit') }}</ElButton>
            <ElButton link type="danger" @click="remove(row)">{{ $t('certd.common.delete') }}</ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <!-- 新增 / 编辑 -->
    <ElDrawer
      v-model="dialogVisible"
      :title="editingId ? $t('certd.access.editTitle') : $t('certd.access.create')"
      size="min(720px, 96vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElFormItem v-if="!editingId" :label="$t('certd.access.typeLabel')">
          <ElInput v-model="typeKeyword" :placeholder="$t('certd.access.typePh')" clearable />
        </ElFormItem>
        <div v-if="!editingId" class="type-picker">
          <div v-for="group in typeGroups" :key="group.key" class="type-group">
            <div class="type-group-title">{{ group.name }}</div>
            <div class="type-group-items">
              <div
                v-for="entry in group.items"
                :key="entry.key"
                class="type-item"
                :class="{ 'is-active': form.type === entry.key }"
                @click="selectType(entry.key)"
              >
                <BrandAvatar
                  :logo-file="logoFileOf(entry.key)"
                  :logo="entry.meta.logo"
                  :short="entry.meta.short"
                  :color="entry.meta.color"
                  :name="entry.meta.name"
                  :size="30"
                />
                <span class="type-item-name">{{ entry.meta.name }}</span>
              </div>
            </div>
          </div>
          <ElEmpty v-if="!typeGroups.length" :description="$t('certd.access.emptyType')" />
        </div>

        <template v-if="form.type">
          <ElDivider content-position="left">{{ accessTypes[form.type]?.desc }}</ElDivider>
          <ElFormItem :label="$t('certd.access.nameLabel')">
            <ElInput v-model="form.name" :placeholder="$t('certd.access.namePh')" />
          </ElFormItem>
          <PluginForm
            v-if="currentType"
            v-model="form.config"
            :fields="currentType.inputs"
            :span="12"
          />
          <ElFormItem :label="$t('certd.table.remark')">
            <ElInput v-model="form.remark" :placeholder="$t('certd.access.remarkPh')" />
          </ElFormItem>
        </template>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="dialogVisible = false">{{ $t('certd.common.cancel') }}</ElButton>
          <ElButton type="primary" :loading="saving" :disabled="!form.type" @click="save">
            {{ $t('certd.common.save') }}
          </ElButton>
        </div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import {
    createAccess,
    deleteAccess,
    fetchAccessList,
    testAccess,
    updateAccess,
  } from '@/api/certd'
  import type { AccessItem } from '@/api/certd'
  import type { ColumnOption } from '@/types'
  import { usePluginStore } from '@/store/modules/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { $t } from '@/locales'
  import BrandAvatar from '../components/brand-avatar.vue'
  import PluginForm from '../components/plugin-form.vue'

  defineOptions({ name: 'CertdAccess' })

  const route = useRoute()
  const pluginStore = usePluginStore()

  const loading = ref(false)
  const items = ref<AccessItem[]>([])
  const activeCategory = ref('')
  const keyword = ref('')

  const accessTypes = computed(() => pluginStore.accessTypes)
  const categories = computed(() => pluginStore.accessCategories)

  const categoryTabs = computed(() => {
    const list = [{ key: '', name: '全部', count: items.value.length }]
    for (const category of categories.value) {
      list.push({
        key: category.key,
        name: category.name,
        count: items.value.filter((item) => item.category === category.key).length,
      })
    }
    return list
  })

  const filtered = computed(() => {
    const text = keyword.value.trim().toLowerCase()
    return items.value.filter((item) => {
      if (activeCategory.value && item.category !== activeCategory.value) return false
      if (!text) return true
      return [item.name, item.typeName, item.remark]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(text))
    })
  })

  /* ---------------- 表格分页（本地切页，数据一次拉全） ---------------- */
  const page = reactive({ current: 1, size: 20 })
  const paged = computed(() =>
    filtered.value.slice((page.current - 1) * page.size, page.current * page.size)
  )
  const pagination = computed(() => ({
    total: filtered.value.length,
    current: page.current,
    size: page.size,
  }))

  const handleSizeChange = (size: number) => {
    page.size = size
    page.current = 1
  }
  const handleCurrentChange = (current: number) => {
    page.current = current
  }

  // 换分类 / 改关键字后回到第一页，否则会停在一个已经不存在的页码上
  watch([activeCategory, keyword], () => {
    page.current = 1
  })

  /* ---------------- 多选 ---------------- */
  const selectedRows = ref<AccessItem[]>([])
  const selectedIds = computed(() => selectedRows.value.map((row) => row.id))
  const removing = ref(false)

  const handleSelectionChange = (rows: AccessItem[]) => {
    selectedRows.value = rows
  }

  const load = async () => {
    loading.value = true
    try {
      await pluginStore.ensureLoaded()
      const result: any = await fetchAccessList({ page: 1, size: 500 })
      items.value = result?.records || []
      // 刷新后原来勾中的行可能已经不存在了，清掉避免批量删除误伤
      selectedRows.value = []
    } finally {
      loading.value = false
    }
  }

  const switchCategory = (key: string) => {
    activeCategory.value = key
  }

  const logoFileOf = (type: string) => accessTypes.value[type]?.logoFile || ''

  /** 卡片上只预览「非敏感」的标识字段，密钥不铺到表格里 */
  const previewKeys = (item: AccessItem) => {
    const meta = accessTypes.value[item.type]
    if (!meta) return []
    const result: string[] = []
    for (const field of meta.inputs || []) {
      if (field.component === 'password') continue
      const value = (item.config || {})[field.key]
      if (value === undefined || value === null || value === '') continue
      // 开关是行为选项不是身份标识，铺到列表里只会变成噪音（「忽略证书校验：是」）
      if (typeof value === 'boolean') continue
      result.push(field.title + '：' + previewValue(field, value))
      if (result.length >= 3) break
    }
    return result
  }

  /** 下拉字段显示选项文案而不是原始值（群晖版本显示「自动识别」而不是「auto」） */
  const previewValue = (field: any, value: any): string => {
    if (field.component === 'select' && Array.isArray(field.options)) {
      const hit = field.options.find((option: any) => String(option.value) === String(value))
      if (hit) return String(hit.label).slice(0, 24)
    }
    return String(value).slice(0, 24)
  }

  const columns: ColumnOption[] = [
    { type: 'selection', width: 48 },
    { prop: 'name', label: $t('certd.access.colName'), minWidth: 240, useSlot: true },
    { prop: 'typeName', label: $t('certd.access.colType'), width: 200, useSlot: true },
    { prop: 'summary', label: $t('certd.access.colFields'), minWidth: 280, useSlot: true },
    { prop: 'operation', label: $t('certd.common.actions'), width: 180, fixed: 'right', useSlot: true },
  ]

  /* ---------------- 新增 / 编辑 ---------------- */
  const dialogVisible = ref(false)
  const saving = ref(false)
  const editingId = ref(0)
  const typeKeyword = ref('')

  const form = reactive({
    type: '',
    name: '',
    remark: '',
    config: {} as Record<string, any>,
  })

  const currentType = computed(() => accessTypes.value[form.type])

  const typeGroups = computed(() => {
    const text = typeKeyword.value.trim().toLowerCase()
    return categories.value
      .map((category) => ({
        key: category.key,
        name: category.name,
        items: Object.entries(accessTypes.value)
          .filter(([key, meta]) => {
            if (meta.category !== category.key) return false
            if (!text) return true
            return (
              meta.name.toLowerCase().includes(text) ||
              key.toLowerCase().includes(text) ||
              (meta.desc || '').toLowerCase().includes(text)
            )
          })
          .map(([key, meta]) => ({ key, meta })),
      }))
      .filter((group) => group.items.length > 0)
  })

  const selectType = (type: string) => {
    form.type = type
    const meta = accessTypes.value[type]
    if (!form.name) form.name = meta?.name || ''
    // 按元数据默认值初始化
    const config: Record<string, any> = {}
    for (const field of meta?.inputs || []) {
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

  const openCreate = (type?: string) => {
    editingId.value = 0
    form.type = ''
    form.name = ''
    form.remark = ''
    form.config = {}
    typeKeyword.value = ''
    dialogVisible.value = true
    if (type) selectType(type)
  }

  const openEdit = (item: AccessItem) => {
    editingId.value = item.id
    form.type = item.type
    form.name = item.name
    form.remark = item.remark
    // 后端明文下发，直接铺进表单；密码框默认星号，点小眼睛看明文。
    // 老授权里没有的新字段（比如群晖后来加的「设为默认证书」）用元数据默认值补齐：
    // 不补的话开关会显示成「关」，用户一保存就把默认行为改掉了。
    const meta = accessTypes.value[item.type]
    const config: Record<string, any> = {}
    for (const field of meta?.inputs || []) {
      const saved = item.config?.[field.key]
      if (saved !== undefined) {
        config[field.key] = saved
      } else if (field.deriveFrom) {
        // 新加的字段从别的字段推导（群晖「已开启二步验证」由 otpType 推导）。
        // 不推导的话，默认值 False 会把原本用验证密钥的授权悄悄改成不验证码。
        const source = item.config?.[field.deriveFrom.key]
        const mapped = field.deriveFrom.map?.[String(source)]
        config[field.key] = mapped === undefined ? field.default : mapped
      } else if (field.default !== undefined) {
        config[field.key] = Array.isArray(field.default) ? [...field.default] : field.default
      } else {
        config[field.key] = field.component === 'switch' ? false : ''
      }
    }
    for (const [key, value] of Object.entries(item.config || {})) {
      if (!(key in config)) config[key] = value
    }
    form.config = config
    dialogVisible.value = true
  }

  const save = async () => {
    if (!form.name.trim()) {
      ElMessage.warning($t('certd.access.nameRequired'))
      return
    }
    // 保存前 trim：粘贴密钥最常带首尾空格，会导致签名失败且极难排查
    const config: Record<string, any> = {}
    for (const [key, value] of Object.entries(form.config || {})) {
      config[key] = typeof value === 'string' ? value.trim() : value
    }
    const payload = {
      category: accessTypes.value[form.type]?.category || 'cloud',
      type: form.type,
      name: form.name.trim(),
      remark: form.remark,
      config,
    }
    saving.value = true
    try {
      if (editingId.value) {
        await updateAccess(editingId.value, payload)
        ElMessage.success($t('certd.common.saved'))
      } else {
        await createAccess(payload)
        ElMessage.success($t('certd.common.added'))
      }
      dialogVisible.value = false
      load()
    } finally {
      saving.value = false
    }
  }

  /* ---------------- 测试 / 删除 ---------------- */
  const testingId = ref(0)

  const testAccess2 = async (item: AccessItem) => {
    testingId.value = item.id
    try {
      const result = await testAccess(item.id)
      if (result?.success) {
        ElMessage.success(result.message || $t('certd.access.testOk'))
      } else {
        ElMessageBox.alert(result?.message || $t('certd.access.testFail'), $t('certd.access.testResult'), {
        type: 'warning',
        confirmButtonText: $t('certd.common.confirm'),
      })
      }
    } finally {
      testingId.value = 0
    }
  }

  const remove = async (item: AccessItem) => {
    await ElMessageBox.confirm(
      $t('certd.access.confirmDelete', { name: item.name }),
      $t('certd.access.deleteTitle'),
      { type: 'warning', confirmButtonText: $t('certd.common.confirm'), cancelButtonText: $t('certd.common.cancel') }
    )
    await deleteAccess(item.id)
    ElMessage.success($t('certd.common.deleted'))
    load()
  }

  const removeSelected = async () => {
    const ids = [...selectedIds.value]
    if (!ids.length) return
    await ElMessageBox.confirm(
      $t('certd.access.confirmBatchDelete', { n: ids.length }),
      $t('certd.access.batchDeleteTitle'),
      { type: 'warning', confirmButtonText: $t('certd.common.confirm'), cancelButtonText: $t('certd.common.cancel') }
    )
    removing.value = true
    try {
      // 后端只有单条删除接口，这里串行调用：量级很小，失败会中断并报错
      for (const id of ids) {
        await deleteAccess(id)
      }
      ElMessage.success($t('certd.access.batchDeleted', { n: ids.length }))
      load()
    } finally {
      removing.value = false
    }
  }

  onMounted(() => {
    load()
    if (route.query.create) openCreate()
  })
</script>

<style scoped>
  .access-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
  }

  .access-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .access-tab {
    display: flex;
    gap: 6px;
    align-items: center;
    height: 30px;
    padding: 0 10px;
    font-size: 13px;
    font-weight: 500;
    color: var(--muted-foreground);
    cursor: pointer;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    transition:
      background-color 0.15s ease,
      color 0.15s ease;
  }

  .access-tab:hover {
    color: var(--foreground);
    background: var(--accent);
  }

  /* 选中态对齐 shadcn 的「选中导航项」：近黑底 + 反白字（暗色自动反转为浅底深字） */
  .access-tab.is-active {
    color: var(--primary-foreground);
    background: var(--primary);
    border-color: transparent;
  }

  .access-tab-count {
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    opacity: 0.7;
  }

  .access-tools {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }

  .access-search {
    width: 220px;
  }

  .access-count {
    font-size: 12px;
    color: var(--art-gray-500);
  }

  /* ---------------- 表格单元格 ---------------- */
  .cell-brand {
    display: flex;
    gap: 10px;
    align-items: center;
    min-width: 0;
  }

  .cell-brand-text {
    min-width: 0;
  }

  .cell-name {
    overflow: hidden;
    font-size: 13.5px;
    font-weight: 600;
    color: var(--art-gray-900);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cell-remark {
    margin-top: 2px;
    overflow: hidden;
    font-size: 12px;
    color: var(--art-gray-500);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cell-type {
    display: flex;
    gap: 6px;
    align-items: center;
    min-width: 0;
  }

  .cell-type-name {
    overflow: hidden;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cell-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .access-key-tag {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .cell-muted {
    font-size: 12px;
    color: var(--art-gray-400);
  }

  .cell-actions {
    display: flex;
    gap: 4px;
    align-items: center;
  }

  /* ---------------- 类型选择 ---------------- */
  .type-picker {
    max-height: 34vh;
    padding-right: 4px;
    overflow: auto;
  }

  .type-group {
    margin-bottom: 10px;
  }

  .type-group-title {
    margin-bottom: 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--art-gray-600);
  }

  .type-group-items {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 6px;
  }

  .type-item {
    display: flex;
    gap: 6px;
    align-items: center;
    padding: 6px 8px;
    cursor: pointer;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    transition:
      border-color 0.14s ease,
      background-color 0.14s ease;
  }

  .type-item:hover {
    background: var(--accent);
  }

  .type-item.is-active {
    border-color: var(--ring);
    background: var(--accent);
  }

  .type-item-name {
    overflow: hidden;
    font-size: 12px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
