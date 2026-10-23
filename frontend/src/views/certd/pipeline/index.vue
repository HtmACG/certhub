<!--
  证书流水线列表
  =========================================================
  certd 的列表页交互：搜索 + 批量 + 单条操作 + 运行即看日志。
  这里做了三处「简化」：
  1. 新建默认走模板（8 套常用组合），不想配就先选一个骨架；
  2. 运行直接在抽屉里看实时日志，不用先进详情页再点一次；
  3. 批量操作一个弹窗搞定运行 / 启停 / 定时 / 通知 / 删除。
-->
<template>
  <div class="certd-pipeline art-full-height g-scope">
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
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />新建流水线
            </ElButton>
            <ElDropdown trigger="click" @command="handleBatchCommand">
              <ElButton :disabled="!selectedIds.length">
                批量操作（{{ selectedIds.length }}）
                <ArtSvgIcon icon="ri:arrow-down-s-line" class="ml-1" />
              </ElButton>
              <template #dropdown>
                <ElDropdownMenu>
                  <ElDropdownItem command="run">立即运行</ElDropdownItem>
                  <ElDropdownItem command="enable">启用</ElDropdownItem>
                  <ElDropdownItem command="disable">停用</ElDropdownItem>
                  <ElDropdownItem command="cron" divided>设置定时</ElDropdownItem>
                  <ElDropdownItem command="notify">设置通知</ElDropdownItem>
                  <ElDropdownItem command="delete" divided>删除</ElDropdownItem>
                </ElDropdownMenu>
              </template>
            </ElDropdown>
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
        <template #title="{ row }">
          <div class="cell-title">
            <ElLink type="primary" :underline="false" @click="goDetail(row)">
              {{ row.title }}
            </ElLink>
            <div class="cell-tags">
              <ElTag v-if="row.disabled" size="small" type="info" effect="plain">已停用</ElTag>
              <ElTag
                v-for="kind in kindsOf(row)"
                :key="kind.key"
                size="small"
                effect="plain"
                :style="{ color: kind.color }"
              >
                {{ kind.text }}
              </ElTag>
            </div>
            <div v-if="row.domains && row.domains.length" class="cell-domains">
              {{ row.domains.join(' , ') }}
            </div>
          </div>
        </template>

        <template #lastStatus="{ row }">
          <div class="cell-status">
            <ElTag :type="runStatusMeta(row.lastStatus).type" size="small" effect="light">
              {{ runStatusMeta(row.lastStatus).text }}
            </ElTag>
            <span v-if="row.running" class="cell-running">
              <ArtSvgIcon icon="ri:loader-4-line" class="animate-spin" />运行中
            </span>
          </div>
          <div class="cell-sub">{{ row.lastHistoryTime || '尚未执行' }}</div>
        </template>

        <template #cert="{ row }">
          <template v-if="row.certExpiresTime">
            <ElTag :type="certStatusMeta(daysLeft(row)).type" size="small" effect="light">
              {{ certStatusMeta(daysLeft(row)).text }}
            </ElTag>
            <div class="cell-sub">{{ row.certExpiresTime }}</div>
          </template>
          <span v-else class="cell-sub">暂无证书</span>
        </template>

        <template #trigger="{ row }">
          <div class="cell-sub">
            {{ row.triggerCount ? '定时任务 ' + row.triggerCount + ' 个' : '仅手动' }}
          </div>
          <div v-if="row.nextRunTime" class="cell-sub">下次 {{ row.nextRunTime }}</div>
        </template>

        <template #operation="{ row }">
          <div class="cell-actions">
            <ElTooltip content="立即运行">
              <ArtButtonTable type="view" @click="runNow(row)" />
            </ElTooltip>
            <ElTooltip content="编辑">
              <ArtButtonTable type="edit" @click="goDetail(row)" />
            </ElTooltip>
            <ElDropdown trigger="click" @command="(cmd: string) => handleRowCommand(cmd, row)">
              <ArtButtonTable type="more" />
              <template #dropdown>
                <ElDropdownMenu>
                  <ElDropdownItem command="copy">复制</ElDropdownItem>
                  <ElDropdownItem command="toggle">
                    {{ row.disabled ? '启用' : '停用' }}
                  </ElDropdownItem>
                  <ElDropdownItem command="history">执行历史</ElDropdownItem>
                  <ElDropdownItem command="delete" divided>删除</ElDropdownItem>
                </ElDropdownMenu>
              </template>
            </ElDropdown>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <!-- 新建：模板优先 -->
    <ElDialog v-model="createVisible" title="新建流水线" width="min(880px, 92vw)" destroy-on-close>
      <div class="template-tip">
        选一个模板即可生成骨架（阶段与任务都已配好），之后再填域名与授权即可运行。
      </div>
      <div class="template-grid" v-loading="templateLoading">
        <div
          v-for="tpl in templates"
          :key="tpl.id"
          class="template-item"
          :class="{ 'is-active': selectedTemplate === tpl.id }"
          @click="selectedTemplate = tpl.id"
        >
          <div class="template-head">
            <span class="template-name">{{ tpl.name }}</span>
            <ElTag size="small" effect="plain">{{ tpl.stageCount }} 阶段</ElTag>
          </div>
          <p class="template-desc">{{ tpl.desc }}</p>
          <div class="template-tags">
            <ElTag v-for="tag in tpl.tags" :key="tag" size="small" effect="light">{{ tag }}</ElTag>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="createBlank">从空白创建</ElButton>
          <ElButton type="primary" :loading="creating" :disabled="!selectedTemplate" @click="createFromTemplate">
            用模板创建
          </ElButton>
        </div>
      </template>
    </ElDialog>

    <!-- 批量：定时 -->
    <ElDialog v-model="cronVisible" title="设置定时" width="min(460px, 92vw)">
      <ElForm label-width="90px" label-position="top">
        <ElFormItem label="cron 表达式">
          <ElInput v-model="cronValue" placeholder="0 3 * * *" clearable />
        </ElFormItem>
        <ElFormItem label="常用预设">
          <div class="preset-wrap">
            <ElTag
              v-for="preset in CRON_PRESETS"
              :key="preset.value"
              class="preset-tag"
              :type="cronValue === preset.value ? 'primary' : 'info'"
              effect="light"
              @click="cronValue = preset.value"
            >
              {{ preset.label }}
            </ElTag>
          </div>
        </ElFormItem>
        <p class="form-tip">留空表示移除定时任务，只保留手动 / Webhook 触发。</p>
      </ElForm>
      <template #footer>
        <ElButton @click="cronVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="batching" @click="applyBatchCron">确定</ElButton>
      </template>
    </ElDialog>

    <!-- 批量：通知 -->
    <ElDialog v-model="notifyVisible" title="设置通知渠道" width="min(460px, 92vw)">
      <ElSelect v-model="notifyValue" placeholder="选择通知渠道" clearable filterable class="w-full">
        <ElOption
          v-for="item in notificationOptions"
          :key="item.id"
          :label="item.name + '（' + item.typeName + '）'"
          :value="item.id"
        />
      </ElSelect>
      <p class="form-tip">会在流水线末尾追加 / 更新一个「发送通知」阶段；留空则移除该阶段。</p>
      <template #footer>
        <ElButton @click="notifyVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="batching" @click="applyBatchNotify">确定</ElButton>
      </template>
    </ElDialog>

    <!-- 运行日志 -->
    <ElDrawer v-model="logVisible" title="运行日志" size="46%" destroy-on-close>
      <LogPanel
        :history-id="logHistoryId"
        :closable="true"
        empty-text="正在启动流水线…"
        @close="logVisible = false"
      />
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
  import { useTable } from '@/hooks/core/useTable'
  import {
    batchPipeline,
    copyPipeline,
    createPipelineFromTemplate,
    deletePipeline,
    fetchNotificationOptions,
    fetchPipelineList,
    fetchPipelineTemplates,
    runPipeline,
    togglePipeline,
  } from '@/api/certd'
  import type { PipelineItem } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { CRON_PRESETS, STAGE_KIND_META, certStatusMeta, runStatusMeta } from '@/utils/certd'
  import LogPanel from '../components/log-panel.vue'

  defineOptions({ name: 'CertdPipeline' })

  const router = useRouter()
  const route = useRoute()

  const searchForm = ref<Record<string, any>>({ keyword: undefined, status: undefined })
  const selectedIds = ref<number[]>([])
  const selectedRows = ref<PipelineItem[]>([])

  const searchItems = [
    { key: 'keyword', label: '关键字', type: 'input', placeholder: '流水线名称 / 备注' },
    {
      key: 'status',
      label: '最近结果',
      type: 'select',
      options: [
        { label: '成功', value: 'success' },
        { label: '失败', value: 'failed' },
        { label: '运行中', value: 'running' },
      ],
    },
    {
      key: 'disabled',
      label: '启用状态',
      type: 'select',
      options: [
        { label: '已启用', value: 'false' },
        { label: '已停用', value: 'true' },
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
      apiFn: fetchPipelineList,
      apiParams: { current: 1, size: 10 },
      columnsFactory: () => [
        { type: 'selection', width: 48 },
        { prop: 'title', label: '流水线 / 域名', minWidth: 240, useSlot: true },
        { prop: 'lastStatus', label: '最近执行', width: 150, useSlot: true },
        { prop: 'cert', label: '证书有效期', width: 150, useSlot: true },
        { prop: 'trigger', label: '触发方式', width: 150, useSlot: true },
        { prop: 'operation', label: '操作', width: 150, fixed: 'right', useSlot: true },
      ],
    },
    hooks: {
      onSuccess: () => {
        selectedIds.value = []
        selectedRows.value = []
      },
    },
  })

  /** 流程分类标签：由后端解析 content 得出（申请 / 部署 / 通知） */
  const kindsOf = (row: PipelineItem) =>
    ((row as any).kinds || []).map((key: string) => ({
      key,
      text: STAGE_KIND_META[key as 'cert' | 'deploy' | 'notify']?.text || key,
      color: STAGE_KIND_META[key as 'cert' | 'deploy' | 'notify']?.color || '#909399',
    }))

  const daysLeft = (row: PipelineItem) => {
    if (!row.certExpiresTime) return null
    const end = new Date(row.certExpiresTime.replace(/-/g, '/')).getTime()
    return Math.floor((end - Date.now()) / 86400000)
  }

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }

  const handleReset = () => {
    resetSearchParams()
  }

  const handleSelectionChange = (rows: PipelineItem[]) => {
    selectedRows.value = rows
    selectedIds.value = rows.map((row) => row.id)
  }

  const goDetail = (row: PipelineItem) => {
    router.push('/certd/pipeline/detail/' + row.id)
  }

  /* ---------------- 新建 ---------------- */
  const createVisible = ref(false)
  const templateLoading = ref(false)
  const templates = ref<any[]>([])
  const selectedTemplate = ref('')
  const creating = ref(false)

  const openCreate = async () => {
    createVisible.value = true
    if (templates.value.length) return
    templateLoading.value = true
    try {
      templates.value = (await fetchPipelineTemplates()) || []
    } finally {
      templateLoading.value = false
    }
  }

  const createFromTemplate = async () => {
    if (!selectedTemplate.value) return
    creating.value = true
    try {
      const result = await createPipelineFromTemplate({ templateId: selectedTemplate.value })
      ElMessage.success('已创建：' + result.title)
      createVisible.value = false
      router.push('/certd/pipeline/detail/' + result.id)
    } finally {
      creating.value = false
    }
  }

  const createBlank = async () => {
    createVisible.value = false
    router.push({ path: '/certd/pipeline/detail/0', query: { blank: '1' } })
  }

  /* ---------------- 单条操作 ---------------- */
  const logVisible = ref(false)
  const logHistoryId = ref<number | null>(null)

  const runNow = async (row: PipelineItem) => {
    if (row.running) {
      ElMessage.warning('该流水线正在运行中')
      return
    }
    const result = await runPipeline(row.id)
    logHistoryId.value = result?.historyId || null
    logVisible.value = true
    refreshData()
  }

  const handleRowCommand = async (command: string, row: PipelineItem) => {
    if (command === 'copy') {
      const result = await copyAndOpen(row)
      return result
    }
    if (command === 'toggle') {
      const result = await togglePipeline(row.id)
      ElMessage.success(result?.disabled ? '已停用' : '已启用')
      refreshData()
      return
    }
    if (command === 'history') {
      router.push({ path: '/certd/history', query: { pipelineId: row.id } })
      return
    }
    if (command === 'delete') {
      await ElMessageBox.confirm('删除后该流水线的执行历史也会一起删除，确定吗？', '删除流水线', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
      await deletePipeline(row.id)
      ElMessage.success('已删除')
      refreshData()
    }
  }

  const copyAndOpen = async (row: PipelineItem) => {
    // 复制走 api 的 /copy，创建完直接跳到新流水线编辑页
    const result = await copyPipeline(row.id)
    ElMessage.success('已复制')
    refreshData()
    router.push('/certd/pipeline/detail/' + result.id)
  }

  /* ---------------- 批量操作 ---------------- */
  const batching = ref(false)
  const cronVisible = ref(false)
  const cronValue = ref('')
  const notifyVisible = ref(false)
  const notifyValue = ref<number | undefined>()
  const notificationOptions = ref<{ id: number; name: string; typeName: string }[]>([])

  const handleBatchCommand = async (command: string) => {
    if (!selectedIds.value.length) return
    if (command === 'cron') {
      cronVisible.value = true
      return
    }
    if (command === 'notify') {
      notifyVisible.value = true
      if (!notificationOptions.value.length) {
        notificationOptions.value = (await fetchNotificationOptions()) || []
      }
      return
    }
    if (command === 'delete') {
      await ElMessageBox.confirm(
        '将删除选中的 ' + selectedIds.value.length + ' 条流水线，确定吗？',
        '批量删除',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
      )
    }
    await submitBatch(command as any)
  }

  const submitBatch = async (action: 'run' | 'enable' | 'disable' | 'delete', extra: Record<string, any> = {}) => {
    batching.value = true
    try {
      const result = await batchPipeline({ action, ids: selectedIds.value, ...extra })
      const success = result?.success?.length || 0
      const failed = result?.failed?.length || 0
      if (failed) {
        ElMessage.warning('成功 ' + success + ' 条，失败 ' + failed + ' 条：' + result.failed[0]?.msg)
      } else {
        ElMessage.success('已处理 ' + success + ' 条')
      }
      refreshData()
    } finally {
      batching.value = false
    }
  }

  const applyBatchCron = async () => {
    batching.value = true
    try {
      const result = await batchPipeline({
        action: 'cron',
        ids: selectedIds.value,
        cron: cronValue.value,
      })
      const failed = result?.failed?.length || 0
      ElMessage[failed ? 'warning' : 'success'](
        failed ? '失败 ' + failed + ' 条' : '定时已更新'
      )
      cronVisible.value = false
      refreshData()
    } finally {
      batching.value = false
    }
  }

  const applyBatchNotify = async () => {
    batching.value = true
    try {
      const result = await batchPipeline({
        action: 'notify',
        ids: selectedIds.value,
        notificationId: notifyValue.value || 0,
      })
      const failed = result?.failed?.length || 0
      ElMessage[failed ? 'warning' : 'success'](failed ? '失败 ' + failed + ' 条' : '通知已更新')
      notifyVisible.value = false
      refreshData()
    } finally {
      batching.value = false
    }
  }

  onMounted(() => {
    // 工作台的「新建流水线」按钮直接打开模板弹窗
    if (route.query.create === 'template') openCreate()
  })
</script>

<style scoped>
  .cell-title {
    min-width: 0;
  }

  .cell-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }

  /* 域名可能有十几个：允许换两行，不要一个字一个省略号地挤在一行里 */
  .cell-domains {
    display: -webkit-box;
    margin-top: 4px;
    overflow: hidden;
    font-size: 12px;
    line-height: 1.5;
    color: var(--art-gray-500);
    word-break: break-all;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }

  .cell-status {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .cell-running {
    display: inline-flex;
    gap: 3px;
    align-items: center;
    font-size: 12px;
    color: var(--el-color-warning);
  }

  .cell-sub {
    margin-top: 2px;
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .cell-actions {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
  }

  /* 操作按钮固定尺寸：element 的按钮在 flex 容器里默认可被压缩，排在最后会被挤成一条缝 */
  .cell-actions :deep(.el-button),
  .cell-actions :deep(.art-button-table) {
    flex: 0 0 auto;
  }

  .template-tip {
    margin-bottom: 12px;
    font-size: 13px;
    color: var(--art-gray-600);
  }

  .template-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 10px;
    max-height: 52vh;
    overflow: auto;
  }

  .template-item {
    padding: 12px;
    cursor: pointer;
    border: 1px solid var(--art-card-border);
    border-radius: 8px;
    transition: all 0.2s;
  }

  .template-item:hover,
  .template-item.is-active {
    border-color: var(--theme-color);
    background: var(--el-color-primary-light-9);
  }

  .template-head {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }

  .template-name {
    font-size: 13px;
    font-weight: 600;
  }

  .template-desc {
    margin: 6px 0;
    font-size: 12px;
    line-height: 1.6;
    color: var(--art-gray-600);
  }

  .template-tags,
  .preset-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .preset-tag {
    cursor: pointer;
  }

  .form-tip {
    margin: 8px 0 0;
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  @media (max-width: 768px) {
    .template-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
