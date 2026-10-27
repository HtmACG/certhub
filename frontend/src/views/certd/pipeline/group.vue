<!--
  流水线分组
  =========================================================
  把几条流水线编成一组，按顺序「试一试」：
  · 第一条成功 → 分组成功，后面的不再跑；
  · 第一条失败 → 看它配的「失败后执行」是哪条，有就跑那条，没有就判分组失败；
  · 同一条流水线在一次分组里只跑一次（防止 A→B→A 转不出来）。

  典型用法：主 CA 失败自动转备用 CA。执行记录里能看到每一步的状态和对应的执行历史。
-->
<template>
  <div class="certd-group art-full-height g-scope">
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
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />新建分组
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
        <template #name="{ row }">
          <div class="cell-main">{{ row.name }}</div>
          <div class="cell-sub">
            {{ row.items.length }} 条流水线
            <template v-if="row.remark"> · {{ row.remark }}</template>
          </div>
        </template>

        <template #chain="{ row }">
          <div class="chain">
            <template v-for="(item, index) in row.items" :key="item.pipelineId">
              <ElTag v-if="index" size="small" type="info" effect="plain" class="chain-arrow">
                <template v-if="row.items[index - 1].onFailurePipelineId === item.pipelineId">
                  失败后 →
                </template>
                <template v-else>→</template>
              </ElTag>
              <ElTag
                size="small"
                :type="index === 0 ? 'primary' : 'success'"
                effect="light"
                class="chain-node"
              >
                {{ item.pipelineTitle }}
              </ElTag>
            </template>
            <div v-if="fallbackOf(row)" class="cell-sub">
              失败后执行：{{ fallbackOf(row) }}
            </div>
          </div>
        </template>

        <template #enabled="{ row }">
          <ElTag size="small" :type="row.enabled ? 'success' : 'info'" effect="light">
            {{ row.enabled ? '已启用' : '已停用' }}
          </ElTag>
        </template>

        <template #lastRun="{ row }">
          <template v-if="row.lastRun">
            <ElTag size="small" :type="runStatusMeta(row.lastRun.status).type" effect="light">
              {{ runStatusMeta(row.lastRun.status).text }}
            </ElTag>
            <div class="cell-sub">{{ row.lastRun.startTime }}</div>
          </template>
          <span v-else class="cell-sub">还没运行过</span>
        </template>

        <template #operation="{ row }">
          <div class="cell-actions">
            <ElTooltip content="运行分组">
              <ElButton
                link
                type="primary"
                :loading="runningId === row.id"
                @click="runGroup(row)"
              >
                <ArtSvgIcon icon="ri:play-circle-line" />
              </ElButton>
            </ElTooltip>
            <ElTooltip content="执行记录">
              <ElButton link @click="openRuns(row)">
                <ArtSvgIcon icon="ri:history-line" />
              </ElButton>
            </ElTooltip>
            <ElTooltip content="编辑">
              <ElButton link @click="openEdit(row)">
                <ArtSvgIcon icon="ri:edit-line" />
              </ElButton>
            </ElTooltip>
            <ElTooltip content="删除">
              <ElButton link type="danger" @click="remove(row)">
                <ArtSvgIcon icon="ri:delete-bin-line" />
              </ElButton>
            </ElTooltip>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <!-- 新建 / 编辑 -->
    <ElDialog
      v-model="dialogVisible"
      :title="editingId ? '编辑分组' : '新建分组'"
      width="min(720px, 94vw)"
      destroy-on-close
    >
      <ElForm label-position="top">
        <ElRow :gutter="16">
          <ElCol :xs="24" :sm="14">
            <ElFormItem label="分组名称">
              <ElInput v-model="form.name" placeholder="例如：htmacg.cn 主备 CA" />
            </ElFormItem>
          </ElCol>
          <ElCol :xs="24" :sm="10">
            <ElFormItem label="启用">
              <ElSwitch v-model="form.enabled" />
            </ElFormItem>
          </ElCol>
          <ElCol :span="24">
            <ElFormItem label="备注">
              <ElInput v-model="form.remark" placeholder="可选：这个分组管哪些域名" />
            </ElFormItem>
          </ElCol>
        </ElRow>

        <ElDivider content-position="left">执行顺序（失败后按这里的配置往下走）</ElDivider>

        <div v-for="(item, index) in form.items" :key="index" class="item-row">
          <span class="item-index">{{ index + 1 }}</span>
          <ElSelect
            v-model="item.pipelineId"
            placeholder="选择流水线"
            filterable
            class="item-select"
          >
            <ElOption
              v-for="option in pipelineOptions"
              :key="option.id"
              :label="option.title"
              :value="option.id"
              :disabled="usedPipelineIds(index).includes(option.id)"
            />
          </ElSelect>
          <span class="item-label">失败后执行</span>
          <ElSelect
            v-model="item.onFailurePipelineId"
            placeholder="不执行（直接判失败）"
            clearable
            filterable
            class="item-select"
          >
            <ElOption
              v-for="option in pipelineOptions.filter((o) => o.id !== item.pipelineId)"
              :key="option.id"
              :label="option.title"
              :value="option.id"
            />
          </ElSelect>
          <ElButton link type="danger" :disabled="form.items.length <= 1" @click="removeItem(index)">
            删除
          </ElButton>
        </div>

        <ElButton size="small" @click="addItem">
          <ArtSvgIcon icon="ri:add-line" class="mr-1" />添加流水线
        </ElButton>
        <p class="form-tip">
          分组按顺序「试一试」：某条成功就结束；某条失败就跳它这一行的「失败后执行」，
          没配就直接判分组失败。同一条流水线在一次分组里只会跑一次。
        </p>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="dialogVisible = false">取消</ElButton>
          <ElButton type="primary" :loading="saving" @click="save">保存</ElButton>
        </div>
      </template>
    </ElDialog>

    <!-- 执行记录 -->
    <ElDrawer
      v-model="runsVisible"
      :title="'执行记录 · ' + (currentGroup?.name || '')"
      size="min(720px, 96vw)"
      destroy-on-close
    >
      <div v-loading="runsLoading" class="runs-panel">
        <div v-if="!runs.length" class="cell-sub">这个分组还没有执行记录。</div>
        <ElCard v-for="run in runs" :key="run.id" shadow="never" class="run-card">
          <div class="run-head">
            <ElTag size="small" :type="runStatusMeta(run.status).type" effect="light">
              {{ runStatusMeta(run.status).text }}
            </ElTag>
            <span class="cell-sub">{{ run.startTime }} → {{ run.endTime || '进行中' }}</span>
          </div>
          <ul class="run-steps">
            <li v-for="step in run.steps" :key="step.index + '-' + step.pipelineId" class="run-step">
              <span class="step-index">{{ step.index }}</span>
              <span class="step-title">{{ step.pipelineTitle }}</span>
              <ElTag size="small" :type="runStatusMeta(step.status).type" effect="plain">
                {{ runStatusMeta(step.status).text }}
              </ElTag>
              <span v-if="step.nextPipelineTitle" class="step-next">
                → 失败后转 {{ step.nextPipelineTitle }}
              </span>
              <ElButton
                v-if="step.historyId"
                link
                type="primary"
                class="step-log"
                @click="openHistory(step.historyId)"
              >
                日志
              </ElButton>
            </li>
          </ul>
        </ElCard>
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import {
    createPipelineGroup,
    deletePipelineGroup,
    fetchPipelineGroupList,
    fetchPipelineGroupRun,
    fetchPipelineGroupRuns,
    fetchPipelineList,
    runPipelineGroup,
    updatePipelineGroup,
  } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { runStatusMeta } from '@/utils/certd'

  defineOptions({ name: 'CertdPipelineGroup' })

  const router = useRouter()

  const searchForm = ref<Record<string, any>>({ keyword: undefined })
  const searchItems = [
    { key: 'keyword', label: '关键字', type: 'input', placeholder: '分组名称 / 备注' },
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
      apiFn: fetchPipelineGroupList,
      apiParams: { current: 1, size: 10 },
      columnsFactory: () => [
        { prop: 'name', label: '分组 / 备注', minWidth: 200, useSlot: true },
        { prop: 'chain', label: '执行顺序', minWidth: 320, useSlot: true },
        { prop: 'enabled', label: '状态', width: 100, useSlot: true },
        { prop: 'lastRun', label: '最近运行', width: 170, useSlot: true },
        { prop: 'operation', label: '操作', width: 170, fixed: 'right', useSlot: true },
      ],
    },
  })

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }

  const handleReset = () => resetSearchParams()

  /** 第一行的「失败后执行」摘要（表格里只展示一条，够看） */
  const fallbackOf = (row: any) => row.items?.[0]?.onFailurePipelineTitle || ''

  /* ---------------- 流水线下拉 ---------------- */
  const pipelineOptions = ref<{ id: number; title: string }[]>([])

  const loadPipelines = async () => {
    const result = await fetchPipelineList({ current: 1, size: 200 })
    const records = Array.isArray(result) ? result : result?.records || []
    pipelineOptions.value = records.map((row: any) => ({ id: row.id, title: row.title }))
  }

  /** 同一次提交里已经用过的流水线（下拉里置灰，避免重复选） */
  const usedPipelineIds = (index: number) =>
    form.items
      .map((item, i) => (i === index ? 0 : item.pipelineId))
      .filter((id): id is number => Boolean(id))

  /* ---------------- 新建 / 编辑 ---------------- */
  const dialogVisible = ref(false)
  const editingId = ref(0)
  const saving = ref(false)
  const form = reactive<{ name: string; remark: string; enabled: boolean; items: any[] }>({
    name: '',
    remark: '',
    enabled: true,
    items: [],
  })

  const resetForm = () => {
    form.name = ''
    form.remark = ''
    form.enabled = true
    form.items = [{ pipelineId: undefined, onFailurePipelineId: undefined }]
  }

  const openCreate = async () => {
    editingId.value = 0
    resetForm()
    await loadPipelines()
    dialogVisible.value = true
  }

  const openEdit = async (row: any) => {
    editingId.value = row.id
    await loadPipelines()
    form.name = row.name
    form.remark = row.remark || ''
    form.enabled = row.enabled !== false
    form.items = row.items.length
      ? row.items.map((item: any) => ({
          pipelineId: item.pipelineId,
          onFailurePipelineId: item.onFailurePipelineId || undefined,
        }))
      : [{ pipelineId: undefined, onFailurePipelineId: undefined }]
    dialogVisible.value = true
  }

  const addItem = () => {
    form.items.push({ pipelineId: undefined, onFailurePipelineId: undefined })
  }

  const removeItem = (index: number) => {
    form.items.splice(index, 1)
  }

  const save = async () => {
    if (!form.name.trim()) {
      ElMessage.warning('请填写分组名称')
      return
    }
    const items = form.items
      .filter((item) => item.pipelineId)
      .map((item) => ({
        pipelineId: item.pipelineId,
        onFailurePipelineId: item.onFailurePipelineId || 0,
      }))
    if (!items.length) {
      ElMessage.warning('请至少添加一条流水线')
      return
    }
    const payload = {
      name: form.name.trim(),
      remark: form.remark.trim(),
      enabled: form.enabled,
      items,
    }
    saving.value = true
    try {
      if (editingId.value) await updatePipelineGroup(editingId.value, payload)
      else await createPipelineGroup(payload)
      dialogVisible.value = false
      refreshData()
    } finally {
      saving.value = false
    }
  }

  /* ---------------- 运行 ---------------- */
  const runningId = ref(0)
  const runsVisible = ref(false)
  const runsLoading = ref(false)
  const runs = ref<any[]>([])
  const currentGroup = ref<any>(null)

  const loadRuns = async (groupId: number) => {
    const result = await fetchPipelineGroupRuns({ current: 1, size: 20, groupId })
    runs.value = Array.isArray(result) ? result : result?.records || []
  }

  const openRuns = async (row: any) => {
    currentGroup.value = row
    runs.value = []
    runsVisible.value = true
    runsLoading.value = true
    try {
      await loadRuns(row.id)
    } finally {
      runsLoading.value = false
    }
  }

  /** 跑一下分组，然后轮询这次运行的结果（分组是后台线程串行跑的） */
  const runGroup = async (row: any) => {
    runningId.value = row.id
    try {
      const result = await runPipelineGroup(row.id)
      ElMessage.success('已提交，正在按顺序执行')
      const runId = result?.runId || 0
      if (runId) {
        const final = await waitRun(runId)
        if (final?.status === 'success') ElMessage.success('分组执行成功')
        else if (final?.status) ElMessage.warning('分组执行失败，可以打开「执行记录」看是哪一步')
      }
      refreshData()
      if (runsVisible.value && currentGroup.value?.id === row.id) await loadRuns(row.id)
    } finally {
      runningId.value = 0
    }
  }

  /** 轮询单个运行记录直到结束（最多等 10 分钟） */
  const waitRun = async (runId: number) => {
    for (let i = 0; i < 300; i += 1) {
      const detail = await fetchPipelineGroupRun(runId)
      if (detail && detail.status !== 'running') return detail
      await new Promise((resolve) => setTimeout(resolve, 2000))
    }
    return null
  }

  const openHistory = (historyId: number) => {
    router.push({ path: '/certd/history', query: { historyId } })
  }

  const remove = async (row: any) => {
    await ElMessageBox.confirm(
      '确定删除分组「' + row.name + '」吗？执行记录会一起删除，流水线本身不受影响。',
      '删除分组',
      { type: 'warning' }
    )
    await deletePipelineGroup(row.id)
    ElMessage.success('已删除')
    refreshData()
  }
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

  .cell-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    align-items: center;
  }

  /* 执行顺��：标签 + 箭头 */
  .chain {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
    min-width: 0;
  }

  .chain-node {
    max-width: 160px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /*
   * el-tag 是 inline-flex + 居中，文字比 max-width 宽时两边一起被裁，
   * 连省略号都没有（看起来像「第一个字莫名没了」）。
   * 真正要截断的是里面的内容层，给它定宽 + 省略号。
   */
  .chain-node :deep(.el-tag__content) {
    display: block;
    max-width: 128px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chain-arrow {
    flex: 0 0 auto;
  }

  /* 编辑弹窗里的成员行 */
  .item-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px dashed var(--art-card-border);
  }

  .item-index {
    flex: 0 0 22px;
    font-size: 12px;
    font-weight: 600;
    color: var(--art-gray-500);
    text-align: center;
  }

  .item-label {
    flex: 0 0 auto;
    font-size: 12px;
    color: var(--art-gray-600);
  }

  .item-select {
    flex: 1 1 180px;
    min-width: 140px;
  }

  .form-tip {
    margin: 10px 0 0;
    font-size: 12px;
    line-height: 1.6;
    color: var(--art-gray-500);
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  /* 执行记录抽屉 */
  .runs-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .run-card :deep(.el-card__body) {
    padding: 12px 14px;
  }

  .run-head {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 8px;
  }

  .run-steps {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .run-step {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    padding: 6px 0;
    font-size: 12.5px;
    border-top: 1px solid var(--art-card-border);
  }

  .run-step:first-child {
    border-top: none;
  }

  .step-index {
    flex: 0 0 18px;
    font-weight: 600;
    color: var(--art-gray-500);
  }

  .step-title {
    flex: 1 1 120px;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--art-gray-800);
  }

  .step-next {
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .step-log {
    margin-left: auto;
  }
</style>
