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
    <!--
      「流水线」和「流水线分组」本来是侧边栏两个入口，按需求合并成一个页面两个页签。
      分组不是列表的筛选条件，而是另一套对象（把几条流水线编成一组按顺序试），
      所以用页签而不是筛选器。
    -->
    <div class="page-switch" role="tablist" aria-label="流水线 / 分组">
      <button
        type="button"
        role="tab"
        :aria-selected="activeTab === 'pipeline'"
        :class="{ 'is-active': activeTab === 'pipeline' }"
        @click="switchTab('pipeline')"
      >
        <ArtSvgIcon icon="ri:node-tree" />{{ $t('certd.pipeline.tabList') }}
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="activeTab === 'group'"
        :class="{ 'is-active': activeTab === 'group' }"
        @click="switchTab('group')"
      >
        <ArtSvgIcon icon="ri:stack-line" />{{ $t('certd.pipeline.tabGroup') }}
      </button>
    </div>

    <template v-if="activeTab === 'pipeline'">
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
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />{{ $t('certd.pipeline.create') }}
            </ElButton>
            <ElDropdown trigger="click" @command="handleBatchCommand">
              <ElButton :disabled="!selectedIds.length">
                {{ $t('certd.common.batchActions') }} ({{ selectedIds.length }})
                <ArtSvgIcon icon="ri:arrow-down-s-line" class="ml-1" />
              </ElButton>
              <template #dropdown>
                <ElDropdownMenu>
                  <ElDropdownItem command="run">{{ $t('certd.pipeline.runNow') }}</ElDropdownItem>
                  <ElDropdownItem command="enable">{{ $t('certd.pipeline.enable') }}</ElDropdownItem>
                  <ElDropdownItem command="disable">{{ $t('certd.pipeline.disable') }}</ElDropdownItem>
                  <ElDropdownItem command="cron" divided>{{ $t('certd.pipeline.setCron') }}</ElDropdownItem>
                  <ElDropdownItem command="notify">{{ $t('certd.pipeline.setNotify') }}</ElDropdownItem>
                  <ElDropdownItem command="delete" divided>{{ $t('certd.pipeline.delete') }}</ElDropdownItem>
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
            <!-- 名称和分类标签放同一行：标签下移一行会让整行高出一截，
                 4 条记录的表就能差出 40px，看起来「松松垮垮」。 -->
            <div class="cell-title-row">
              <!-- 不用 ElLink：它是 inline-flex + 居中，配 overflow:hidden 时
                   长标题会从两头一起被裁。这里用普通 span（block + ellipsis）。 -->
              <span
                class="cell-title-link"
                :title="row.title"
                role="link"
                tabindex="0"
                @click="goDetail(row)"
                @keyup.enter="goDetail(row)"
              >
                {{ row.title }}
              </span>
              <ElTag
                v-for="kind in kindsOf(row)"
                :key="kind.key"
                size="small"
                effect="plain"
                class="cell-kind"
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

        <template #enabled="{ row }">
          <ElTooltip
            :content="row.disabled ? $t('certd.pipeline.disabledTip') : $t('certd.pipeline.enabledTip')"
          >
            <span class="cell-enabled">
              <ElSwitch
                :model-value="!row.disabled"
                size="small"
                :loading="togglingId === row.id"
                :before-change="() => toggleRowEnabled(row)"
              />
              <span class="cell-enabled-text" :class="{ 'is-off': row.disabled }">
                {{ row.disabled ? $t('certd.status.disabled') : $t('certd.common.enabled') }}
              </span>
            </span>
          </ElTooltip>
        </template>

        <template #lastStatus="{ row }">
          <div class="cell-status">
            <ElTag :type="runStatusMeta(row.lastStatus).type" size="small" effect="light">
              {{ runStatusMeta(row.lastStatus).text }}
            </ElTag>
            <span v-if="row.running" class="cell-running">
              <ArtSvgIcon icon="ri:loader-4-line" class="animate-spin" />{{ $t('certd.pipeline.running') }}
            </span>
          </div>
          <div class="cell-sub">{{ row.lastHistoryTime || $t('certd.status.pending') }}</div>
        </template>

        <template #cert="{ row }">
          <template v-if="row.certExpiresTime">
            <ElTag :type="certStatusMeta(daysLeft(row)).type" size="small" effect="light">
              {{ certStatusMeta(daysLeft(row)).text }}
            </ElTag>
            <div class="cell-sub">{{ row.certExpiresTime }}</div>
          </template>
          <span v-else class="cell-sub">{{ $t('certd.pipeline.noCert') }}</span>
        </template>

        <template #trigger="{ row }">
          <div class="cell-sub">
            {{ row.triggerCount ? $t('certd.pipeline.triggerCount', { n: row.triggerCount }) : $t('certd.pipeline.manualOnly') }}
          </div>
          <div v-if="row.nextRunTime" class="cell-sub">{{ $t('certd.pipeline.nextRun', { time: row.nextRunTime }) }}</div>
        </template>

        <template #operation="{ row }">
          <div class="cell-actions">
            <ElTooltip :content="$t('certd.pipeline.runNow')">
              <ArtButtonTable type="view" @click="runNow(row)" />
            </ElTooltip>
            <ElTooltip :content="$t('certd.common.edit')">
              <ArtButtonTable type="edit" @click="goDetail(row)" />
            </ElTooltip>
            <ElDropdown trigger="click" @command="(cmd: string) => handleRowCommand(cmd, row)">
              <ArtButtonTable type="more" />
              <template #dropdown>
                <ElDropdownMenu>
                  <ElDropdownItem command="copy">{{ $t('certd.pipeline.copy') }}</ElDropdownItem>
                  <ElDropdownItem command="toggle">
                    {{ row.disabled ? $t('certd.pipeline.enable') : $t('certd.pipeline.disable') }}
                  </ElDropdownItem>
                  <ElDropdownItem command="history">{{ $t('certd.pipeline.historyAction') }}</ElDropdownItem>
                  <ElDropdownItem command="delete" divided>{{ $t('certd.pipeline.delete') }}</ElDropdownItem>
                </ElDropdownMenu>
              </template>
            </ElDropdown>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <!-- 新建：模板优先 -->
    <ElDialog v-model="createVisible" :title="$t('certd.pipeline.create')" width="min(880px, 92vw)" destroy-on-close>
      <div class="template-tip">
        {{ $t('certd.pipeline.templateHint') }}
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
            <ElTag size="small" effect="plain">{{ $t('certd.dashboard.stageCount', { n: tpl.stageCount }) }}</ElTag>
          </div>
          <p class="template-desc">{{ tpl.desc }}</p>
          <div class="template-tags">
            <ElTag v-for="tag in tpl.tags" :key="tag" size="small" effect="light">{{ tag }}</ElTag>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="createBlank">{{ $t('certd.pipeline.createBlank') }}</ElButton>
          <ElButton type="primary" :loading="creating" :disabled="!selectedTemplate" @click="createFromTemplate">
            {{ $t('certd.pipeline.createFromTemplate') }}
          </ElButton>
        </div>
      </template>
    </ElDialog>

    <!-- 批量：定时 -->
    <ElDialog v-model="cronVisible" :title="$t('certd.pipeline.setCron')" width="min(460px, 92vw)">
      <ElForm label-width="90px" label-position="top">
        <ElFormItem :label="$t('certd.pipeline.cronExpr')">
          <ElInput v-model="cronValue" placeholder="0 3 * * *" clearable />
        </ElFormItem>
        <ElFormItem :label="$t('certd.pipeline.presets')">
          <div class="preset-wrap">
            <ElTag
              v-for="preset in CRON_PRESETS"
              :key="preset.value"
              class="preset-tag"
              :type="cronValue === preset.value ? 'primary' : 'info'"
              effect="light"
              @click="cronValue = preset.value"
            >
              {{ $t(preset.labelKey) }}
            </ElTag>
          </div>
        </ElFormItem>
        <p class="form-tip">{{ $t('certd.pipeline.cronHint') }}</p>
      </ElForm>
      <template #footer>
        <ElButton @click="cronVisible = false">{{ $t('certd.common.cancel') }}</ElButton>
        <ElButton type="primary" :loading="batching" @click="applyBatchCron">{{ $t('certd.common.confirm') }}</ElButton>
      </template>
    </ElDialog>

    <!-- 批量：通知 -->
    <ElDialog v-model="notifyVisible" :title="$t('certd.pipeline.setNotify')" width="min(460px, 92vw)">
      <ElSelect v-model="notifyValue" :placeholder="$t('certd.pipeline.pickChannel')" clearable filterable class="w-full">
        <ElOption
          v-for="item in notificationOptions"
          :key="item.id"
          :label="item.name + '（' + item.typeName + '）'"
          :value="item.id"
        />
      </ElSelect>
      <p class="form-tip">{{ $t('certd.pipeline.notifyHint') }}</p>
      <template #footer>
        <ElButton @click="notifyVisible = false">{{ $t('certd.common.cancel') }}</ElButton>
        <ElButton type="primary" :loading="batching" @click="applyBatchNotify">{{ $t('certd.common.confirm') }}</ElButton>
      </template>
    </ElDialog>

    <!-- 运行日志 -->
    <ElDrawer v-model="logVisible" :title="$t('certd.table.logs')" size="46%" destroy-on-close>
      <LogPanel
        :history-id="logHistoryId"
        :closable="true"
        :empty-text="$t('certd.pipeline.starting')"
        @close="logVisible = false"
      />
    </ElDrawer>
    </template>

    <!-- 分组：原「流水线分组」页整页搬进来，自己带搜索栏和表格 -->
    <PipelineGroup v-else />
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
  import { $t } from '@/locales'
  import LogPanel from '../components/log-panel.vue'
  import PipelineGroup from './group.vue'

  defineOptions({ name: 'CertdPipeline' })

  const router = useRouter()
  const route = useRoute()

  // 页签：流水线（默认）/ 分组（原独立页面）
  const activeTab = ref<'pipeline' | 'group'>(route.query.tab === 'group' ? 'group' : 'pipeline')

  /**
   * 切换页签时把 tab 写回地址栏：
   * 老的 /certd/pipeline-group 会重定向到 ?tab=group，刷新后也要停在同一页。
   */
  const switchTab = (tab: 'pipeline' | 'group') => {
    if (activeTab.value === tab) return
    activeTab.value = tab
    router.replace({ path: route.path, query: tab === 'group' ? { tab: 'group' } : {} })
  }

  const searchForm = ref<Record<string, any>>({ keyword: undefined, status: undefined })
  const selectedIds = ref<number[]>([])
  const selectedRows = ref<PipelineItem[]>([])

  /** 搜索项文案随语言变化，用 computed 包一层 */
  const searchItems = computed(() => [
    { key: 'keyword', label: $t('certd.search.keyword'), type: 'input', placeholder: $t('certd.search.pipelinePlaceholder') },
    {
      key: 'status',
      label: $t('certd.search.lastResult'),
      type: 'select',
      options: [
        { label: $t('certd.status.success'), value: 'success' },
        { label: $t('certd.status.failed'), value: 'failed' },
        { label: $t('certd.status.running'), value: 'running' },
      ],
    },
    {
      key: 'disabled',
      label: $t('certd.search.enabledState'),
      type: 'select',
      options: [
        { label: $t('certd.common.enabled'), value: 'false' },
        { label: $t('certd.status.disabled'), value: 'true' },
      ],
    },
  ])

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
        { prop: 'title', label: $t('certd.pipeline.colTitle'), minWidth: 240, useSlot: true },
        // 启用 / 停用直接在这里开关（以前放在流水线编辑页顶部，勾完还得保存一次）
        // 宽度给够：开关 36 + 间隙 8 + 「已启用」36，再加单元格 12×2 内边距 ≈ 104
        { prop: 'enabled', label: $t('certd.pipeline.colEnabled'), width: 116, useSlot: true },
        { prop: 'lastStatus', label: $t('certd.pipeline.colLastRun'), width: 160, useSlot: true },
        { prop: 'cert', label: $t('certd.pipeline.colCert'), width: 150, useSlot: true },
        // 「下次 2026-11-01 03:00:00」一行放得下才不会折成三行把行高压到 100px
        { prop: 'trigger', label: $t('certd.pipeline.colTrigger'), width: 190, useSlot: true },
        { prop: 'operation', label: $t('certd.common.actions'), width: 150, fixed: 'right', useSlot: true },
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
    ((row as any).kinds || []).map((key: string) => {
      const meta = STAGE_KIND_META[key as 'cert' | 'deploy' | 'notify']
      return {
        key,
        text: meta ? $t(meta.textKey) : key,
        color: meta?.color || 'var(--muted-foreground)',
      }
    })

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

  /** 表格里「启用」开关正在切的那一行（只转它自己的圈） */
  const togglingId = ref(0)

  /**
   * 表格里直接启停一条流水线。
   * 用 before-change 返回 Promise：成功才真正切换，失败时开关自己回弹，
   * 不会出现「界面显示已启用、库里还是停用」的假状态。
   */
  const toggleRowEnabled = async (row: PipelineItem) => {
    if (togglingId.value === row.id) return false
    togglingId.value = row.id
    try {
      const result = await togglePipeline(row.id)
      const disabled = Boolean(result?.disabled)
      ;(row as any).disabled = disabled
      ElMessage.success(disabled ? '已停用' : '已启用')
      return true
    } catch {
      return false
    } finally {
      togglingId.value = 0
    }
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
  /* 页签：与详情页「画布 / 列表」保持同一套视觉，切页不换语言。
     shadcn 的 tabs 是「下划线式」：透明底 + 选中项 2px 下划条，
     不再用 Material 的胶囊分段控件。 */
  .page-switch {
    display: inline-flex;
    flex: 0 0 auto;
    gap: 4px;
    align-self: flex-start;
    padding: 0;
    margin-bottom: 12px;
    background: transparent;
    border-bottom: 1px solid var(--border);
    border-radius: 0;
  }

  .page-switch button {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    height: 36px;
    padding: 0 4px;
    font-family: var(--font-sans, inherit);
    font-size: 14px;
    font-weight: 500;
    color: var(--muted-foreground);
    cursor: pointer;
    background: transparent;
    border: 0;
    border-radius: 0;
    transition:
      color 0.14s ease,
      box-shadow 0.14s ease;
  }

  .page-switch button:hover {
    color: var(--foreground);
  }

  /* 选中：前景色字 + 2px 下划线（shadcn tabs 的 data-[state=active] 形态） */
  .page-switch button.is-active {
    color: var(--foreground);
    background: transparent;
    box-shadow: inset 0 -2px 0 0 var(--foreground);
  }

  /*
   * 分组页自带 art-full-height（height: var(--art-full-height) = 整页高度），
   * 嵌在页签下面会多撑出「页签条」那 30px。这里改成占满剩余空间：
   * 写 height:auto 是不够的 —— 高度变成内容驱动后，表格没有可用高度，
   * el-table 的 empty 块只分到 60px，空状态插画会被裁成一条。
   */
  .certd-pipeline :deep(.certd-group) {
    flex: 1 1 auto;
    height: auto;
    min-height: 0;
  }

  .cell-title {
    min-width: 0;
  }

  .cell-title-row {
    display: flex;
    gap: 6px;
    align-items: center;
    min-width: 0;
  }

  /*
   * 标题：block + 省略号（Element 的 .el-link 是 inline-flex + 居中，
   * 直接 overflow:hidden 会「从两头一起裁」，长标题会丢掉开头的字母）。
   */
  .cell-title-link {
    display: block;
    min-width: 0;
    overflow: hidden;
    font-weight: 500;
    color: var(--foreground);
    cursor: pointer;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cell-title-link:hover {
    text-decoration: underline;
    text-underline-offset: 4px;
  }

  .cell-kind {
    flex: 0 0 auto;
  }

  /* 启停：开关 + 文字同一行，别把文字压到第二行去撑高行高 */
  .cell-enabled {
    display: inline-flex;
    gap: 8px;
    align-items: center;
  }

  .cell-enabled-text {
    font-size: 12px;
    color: var(--muted-foreground);
    white-space: nowrap;
  }

  .cell-enabled-text.is-off {
    color: var(--warning);
  }

  /* 域名可能有十几个：允许换两行，不要一个字一个省略号地挤在一行里。
     用 anywhere 而不是 break-all：优先在逗号处断，实在放不下才在词中断。 */
  .cell-domains {
    display: -webkit-box;
    margin-top: 2px;
    overflow: hidden;
    font-size: 12px;
    line-height: 1.5;
    color: var(--muted-foreground);
    overflow-wrap: anywhere;
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
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    transition:
      border-color 0.15s ease,
      background-color 0.15s ease;
  }

  .template-item:hover,
  .template-item.is-active {
    border-color: var(--ring);
    background: var(--accent);
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
