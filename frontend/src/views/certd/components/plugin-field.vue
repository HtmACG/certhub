<!--
  元数据驱动的表单字段渲染器
  =========================================================
  输入：后端 plugins.py 里的一条字段声明（PluginField）
  输出：对应的 Element Plus 控件；前端不再为每个插件手写一遍表单。

  支持 component：
    input / password / textarea / number / switch / select / tags / access / notification

  密码类字段一律 ElInput type=password show-password：
  后端明文下发（AGENTS.md 第一条），显示与否交给「小眼睛」。
-->
<template>
  <div class="plugin-field">
    <ElSelect
      v-if="item.component === 'access'"
      v-model="accessValue"
      :placeholder="placeholder"
      filterable
      clearable
      class="w-full"
      :loading="accessLoading"
    >
      <ElOption
        v-for="option in accessSelectOptions"
        :key="option.id"
        :label="option.name + (option.typeName ? '（' + option.typeName + '）' : '')"
        :value="option.id"
      />
      <template #empty>
        <div class="px-3 py-2 text-sm text-g-500">
          暂无{{ allowedTypeNames || (item.accessCategory ? categoryName : '') }}授权，请先到「授权管理」添加
        </div>
      </template>
    </ElSelect>

    <p v-if="accessMismatch" class="match-tip is-warn">
      <ArtSvgIcon icon="ri:error-warning-line" />
      当前选中的授权不是本任务需要的{{ allowedTypeNames }}类型，请重新选择
    </p>

    <ElSelect
      v-else-if="item.component === 'notification'"
      v-model="value"
      :placeholder="placeholder"
      filterable
      clearable
      class="w-full"
      :loading="notifyLoading"
    >
      <ElOption
        v-for="option in notifyOptions"
        :key="option.id"
        :label="option.name + '（' + option.typeName + '）'"
        :value="option.id"
      />
      <template #empty>
        <div class="px-3 py-2 text-sm text-g-500">暂无通知渠道，请先到「通知渠道」添加</div>
      </template>
    </ElSelect>

    <div v-else-if="item.component === 'select'" class="field-with-hint">
      <div class="flex items-center gap-2">
        <ElSelect
          v-model="value"
          :placeholder="placeholder || (item.remote ? '请先选择授权，再选这里' : '请选择')"
          filterable
          clearable
          class="flex-1"
          :loading="remoteLoading"
          @visible-change="onRemoteVisible"
          @change="onValueChange"
        >
          <ElOption
            v-for="option in selectOptions"
            :key="String(option.value)"
            :label="option.label"
            :value="option.value"
          />
          <template v-if="item.remote" #empty>
            <div class="px-3 py-2 text-sm text-g-500">
              {{ remoteError || '请先选择授权，或点右侧刷新按钮拉取' }}
            </div>
          </template>
        </ElSelect>
        <ElTooltip v-if="item.remote" content="重新从对端拉取列表">
          <ElButton :loading="remoteLoading" @click="refreshRemote">
            <ArtSvgIcon icon="ri:refresh-line" />
          </ElButton>
        </ElTooltip>
      </div>
      <p v-if="matchTip" class="match-tip" :class="{ 'is-auto': autoMatched }">
        <ArtSvgIcon :icon="autoMatched ? 'ri:magic-line' : 'ri:information-line'" />
        {{ matchTip }}
      </p>
    </div>

    <div v-else-if="item.component === 'tags'" class="field-with-hint">
      <div class="flex items-start gap-2">
        <ElInputTag
          v-model="tagValue"
          :placeholder="placeholder || '输入后回车添加'"
          clearable
          class="flex-1"
        />
        <ElTooltip v-if="item.domainFrom" content="从选中的 DNS 授权拉取域名，可多选后一次性填入">
          <ElButton :loading="domainLoading" @click="openDomainPicker">选择域名</ElButton>
        </ElTooltip>
      </div>
      <p v-if="matchTip" class="match-tip is-auto">
        <ArtSvgIcon icon="ri:magic-line" />
        {{ matchTip }}
      </p>
    </div>

    <ElInput
      v-else-if="item.component === 'password'"
      v-model="value"
      type="password"
      show-password
      clearable
      autocomplete="new-password"
      :placeholder="placeholder || '请输入' + item.title"
      class="w-full"
    />

    <ElInput
      v-else-if="item.component === 'textarea'"
      v-model="value"
      type="textarea"
      :autosize="{ minRows: 3, maxRows: 10 }"
      :placeholder="placeholder || '请输入' + item.title"
      class="w-full"
    />

    <ElInputNumber
      v-else-if="item.component === 'number'"
      v-model="value"
      :min="item.min ?? 0"
      :max="item.max ?? undefined"
      :placeholder="placeholder"
      controls-position="right"
      class="w-full"
    />

    <ElSwitch v-else-if="item.component === 'switch'" v-model="value" />

    <ElInput
      v-else
      v-model="value"
      clearable
      :placeholder="placeholder || '请输入' + item.title"
      class="w-full"
    />

    <p v-if="item.helper" class="plugin-field-helper">{{ item.helper }}</p>

    <!-- 拉取到的域名列表：可多选，支持全选 / 只选泛域名 / 搜索 -->
    <ElDialog
      v-model="domainPickerVisible"
      class="g-scope"
      :title="'从「' + (item.title || '域名') + '」选择域名'"
      width="min(640px, 94vw)"
      destroy-on-close
    >
      <div class="domain-picker-toolbar">
        <ElInput
          v-model="domainKeyword"
          placeholder="搜索域名"
          clearable
          class="flex-1"
          :prefix-icon="undefined"
        />
        <ElButton @click="toggleDomainSelection('all')">全选</ElButton>
        <ElButton @click="toggleDomainSelection('none')">清空</ElButton>
        <ElButton @click="toggleDomainSelection('wildcard')">只选泛域名</ElButton>
      </div>

      <ElCheckboxGroup v-model="selectedDomains" class="domain-picker-list">
        <ElCheckbox
          v-for="row in filteredDomains"
          :key="row.value"
          :value="row.value"
          :label="row.value"
          class="domain-picker-item"
        >
          <span class="domain-picker-name">{{ row.value }}</span>
          <ElTag size="small" effect="plain" :type="row.wildcard ? 'warning' : 'info'">
            {{ row.wildcard ? '泛域名' : '主域名' }}
          </ElTag>
        </ElCheckbox>
      </ElCheckboxGroup>

      <p v-if="!filteredDomains.length" class="match-tip">
        {{ domainError || '没有匹配的域名，换个关键字试试' }}
      </p>

      <template #footer>
        <div class="dialog-footer">
          <span class="match-tip">已选 {{ selectedDomains.length }} 个</span>
          <ElButton @click="domainPickerVisible = false">取消</ElButton>
          <ElButton type="primary" :loading="domainLoading" @click="applySelectedDomains">
            填入所选域名
          </ElButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import type { PluginField } from '@/api/certd'
  import {
    fetchAccessDomains,
    fetchAccessOptions,
    fetchNotificationOptions,
    fetchPluginOptions,
  } from '@/api/certd'
  import { ElMessage } from 'element-plus'
  import { matchShowWhen } from '@/utils/certd'
  import { usePluginStore } from '@/store/modules/certd'

  defineOptions({ name: 'PluginField' })

  interface Props {
    /** 字段元数据 */
    item: PluginField
    /** 所在任务类型（远程下拉要它才能找到对应的插件解析器） */
    taskType?: string
    /** 整个任务的输入值，供 showWhen / remoteFrom 使用 */
    formValues?: Record<string, any>
    /** 流水线申请的证书域名：远程资源按它自动匹配（宝塔站点 / CDN 加速域名等） */
    certDomains?: string[]
  }

  const props = defineProps<Props>()

  /** 字段值：直接双向绑定到父级表单的这一项 */
  const value = defineModel<any>()

  const accessOptions = ref<any[]>([])
  const accessLoading = ref(false)
  const notifyOptions = ref<{ id: number; name: string; typeName: string }[]>([])
  const notifyLoading = ref(false)
  const remoteOptions = ref<{ label: string; value: any; extra?: string }[]>([])
  const remoteLoading = ref(false)
  const remoteLoaded = ref(false)
  const remoteError = ref('')
  const domainLoading = ref(false)
  /** 上一次「按证书域名自动选中」的值：用户没改过它，域名变了要重新匹配 */
  const autoFilledValue = ref<any>(null)
  const matchCount = ref(0)
  const matchedOption = ref<{ label: string; value: any } | null>(null)

  const placeholder = computed(() => props.item.placeholder || '')

  /** tags 组件要求数组 */
  const tagValue = computed<string[]>({
    get: () => {
      const raw = value.value
      if (Array.isArray(raw)) return raw
      if (!raw) return []
      return String(raw)
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    },
    set: (next) => {
      value.value = next
    },
  })

  /** select 的候选项：远程下拉优先，其次是元数据里写死的 options */
  const selectOptions = computed(() => {
    if (remoteOptions.value.length > 0) return remoteOptions.value
    return (props.item.options || []) as { label: string; value: any }[]
  })

  /**
   * 授权下拉的可用选项。
   *
   * 老数据 / 从接口导入的流水线里，dnsAccessId 可能是字符串 "2"，或者指向一条
   * 已删除 / 类型不匹配的授权。这时下拉匹配不到 label，Element 会把**裸 id**
   * 直接显示出来（用户看到的就是「DNS 授权」下面一个莫名其妙的数字）。
   * 这里补一个同名占位项，把数字翻译成人话。
   */
  const accessSelectOptions = computed<any[]>(() => {
    const options = [...accessOptions.value]
    const current = value.value
    if (current === '' || current === null || current === undefined) return options
    if (options.some((option: any) => String(option.id) === String(current))) return options
    return [
      ...options,
      {
        id: current,
        name: '已选授权 #' + current,
        typeName: '已失效或类型不匹配，请重新选择'
      }
    ]
  })

  /**
   * 授权字段的 v-model：把字符串 id 归一成选项里的数字 id，
   * 否则 Element 认为"没选中"，界面上还会露出原始值。
   */
  const accessValue = computed<any>({
    get() {
      const current = value.value
      if (current === '' || current === null || current === undefined) return current
      const hit = accessOptions.value.find(
        (option: any) => String(option.id) === String(current)
      )
      return hit ? hit.id : current
    },
    set(next: any) {
      value.value = next
    }
  })

  /** 已选授权不在允许类型里（老数据 / 复制来的流水线）：提示用户重选 */
  const accessMismatch = computed(() => {
    const allowed: string[] = props.item.accessTypes || []
    if (!allowed.length || !value.value) return false
    if (!accessOptions.value.length) return false
    return !accessOptions.value.some((item: any) => String(item.id) === String(value.value))
  })

  /** 该字段允许的授权类型中文名（例如「群晖 DSM」），用于空态提示 */
  const allowedTypeNames = computed(() => {
    const allowed: string[] = props.item.accessTypes || []
    if (!allowed.length) return ''
    const store = usePluginStore()
    return allowed.map((type) => store.accessTypes[type]?.name || type).join(' / ')
  })

  const categoryName = computed(() => {
    const map: Record<string, string> = {
      cloud: '云厂商',
      host: '主机 SSH',
      panel: '服务器面板',
      cert: '证书签发',
      dns: 'DNS 服务商',
    }
    return map[props.item.accessCategory || ''] || ''
  })

  /**
   * 拉授权下拉。
   * category 是「能力」级别（dns 这种云厂商既能为 DNS 又能为 CDN 的场合要用），
   * accessTypes 是「精确类型」级别：宝塔 / 1Panel / 群晖 / 威联通都是 panel 分类，
   * 只按分类过滤会让「部署到群晖」里出现宝塔授权，所以有 accessTypes 时必须带上。
   */
  const loadAccess = async () => {
    if (accessLoading.value) return
    accessLoading.value = true
    try {
      const allowed: string[] = props.item.accessTypes || []
      const options =
        (await fetchAccessOptions({
          category: props.item.accessCategory,
          types: allowed.length ? allowed.join(',') : undefined,
        })) || []
      // 后端已经过滤过，这里再兜一次：老接口 / 缓存返回全量时也不会串味
      accessOptions.value = allowed.length
        ? options.filter((item: any) => allowed.includes(item.type))
        : options
    } finally {
      accessLoading.value = false
    }
  }

  const loadNotification = async () => {
    if (notifyLoading.value) return
    notifyLoading.value = true
    try {
      notifyOptions.value = (await fetchNotificationOptions()) || []
    } finally {
      notifyLoading.value = false
    }
  }

  /**
   * 远程资源下拉（域名 / 站点 / 证书 ID / 加速域名 / 命名空间…）
   * 由后端 services/resources.py 实时拉取，前端不硬编码资源清单。
   */
  const loadRemote = async (force = false) => {
    const item = props.item
    if (!item.remote || remoteLoading.value) return
    if (remoteLoaded.value && !force) return
    const accessKey = item.remoteFrom || 'accessId'
    const accessId = (props.formValues || {})[accessKey]
    if (!accessId) {
      remoteError.value = '请先选择对应授权，再刷新列表'
      return
    }
    remoteLoading.value = true
    remoteError.value = ''
    try {
      const data = await fetchPluginOptions(props.taskType || '', item.key, props.formValues || {})
      remoteOptions.value = (data.items || []).map((it: any) => ({
        label: it.label ?? it.name ?? it.title ?? String(it.value),
        value: it.value ?? it.id ?? it.domain ?? it.name,
        extra: typeof it.extra === 'string' ? it.extra : '',
      }))
      remoteLoaded.value = true
      if (data.error) remoteError.value = data.error
      applyAutoMatch()
    } catch (error: any) {
      remoteError.value = error?.message || '拉取失败'
    } finally {
      remoteLoading.value = false
    }
  }

  const onRemoteVisible = (visible: boolean) => {
    if (visible) loadRemote()
  }

  /** 把证书域名抹平成可比较的「主域名」列表（泛域名去掉 *. 前缀） */
  const certBaseDomains = computed(() =>
    (props.certDomains || [])
      .map((domain) => String(domain || '').trim().toLowerCase().replace(/^\*\./, ''))
      .filter(Boolean)
  )

  /** 候选资源的文本（站点名 / 加速域名 / 绑定的域名列表）与证书域名是否匹配 */
  const optionMatches = (option: { label: string; value: any; extra?: string }): boolean => {
    const texts = [option.label, option.value, option.extra]
      .filter((text) => text !== undefined && text !== null && text !== '')
      .flatMap((text) => String(text).replace(/，/g, ',').split(','))
      .map((text) => text.trim().toLowerCase())
      .filter(Boolean)
    for (const base of certBaseDomains.value) {
      for (const text of texts) {
        const candidate = text.replace(/^\*\./, '')
        if (candidate === base || candidate.endsWith('.' + base) || base.endsWith('.' + candidate)) {
          return true
        }
      }
    }
    return false
  }

  /**
   * 按证书域名自动匹配并选中（宝塔站点 / 1Panel 网站 / CDN 加速域名都走这里）。
   * 只在该字段声明了 autoMatchDomains 时生效；用户手动改过就不再覆盖。
   */
  const applyAutoMatch = () => {
    if (!props.item.autoMatchDomains) return
    const options = remoteOptions.value
    if (!options.length || !certBaseDomains.value.length) return

    const matches = options.filter(optionMatches)
    matchCount.value = matches.length
    matchedOption.value = matches[0] || null

    const current = value.value
    const untouched = current === undefined || current === null || current === '' ||
      (autoFilledValue.value !== null && current === autoFilledValue.value)
    if (!untouched || !matches.length) return

    const picked = matches[0].value
    if (props.item.component === 'tags') {
      const list = Array.isArray(current) ? current : []
      if (!list.length) value.value = [picked]
      else if (!list.includes(picked)) value.value = [...list, picked]
    } else {
      value.value = picked
    }
    autoFilledValue.value = picked
  }

  /** 用户手动选了别的值：清掉「自动匹配」标记 */
  const onValueChange = () => {
    if (autoFilledValue.value !== null && value.value !== autoFilledValue.value) {
      autoFilledValue.value = null
      matchedOption.value = null
    }
  }

  /** 字段下面那行提示：自动匹配到了什么 / 为什么没匹配上 */
  const matchTip = computed(() => {
    if (!props.item.autoMatchDomains || !conditionalVisible.value) return ''
    if (remoteLoading.value) return '正在从对端拉取列表…'
    if (remoteError.value) return remoteError.value
    if (!remoteOptions.value.length) return ''
    if (!certBaseDomains.value.length) {
      return '先在「证书申请」里填好域名，这里会自动匹配对端资源'
    }
    if (!matchCount.value) {
      return '没有与证书域名匹配的项，可以从列表里手动选择'
    }
    const label = matchedOption.value?.label || matchedOption.value?.value || ''
    const extra = matchCount.value > 1 ? '（共 ' + matchCount.value + ' 项匹配，已选第一个）' : ''
    return '按证书域名自动匹配：' + label + extra
  })

  /** 自动匹配到的就是当前值，才叫「自动」 */
  const autoMatched = computed(
    () => !!matchedOption.value && autoFilledValue.value !== null && value.value === autoFilledValue.value
  )

  /** 该字段当前是否可见（showWhen 判定），不可见时不做提示也不自动填 */
  const conditionalVisible = computed(() => matchShowWhen(props.item.showWhen, props.formValues || {}))

  /* ---------------- 域名拉取：拉一次、勾多个 ---------------- */
  const domainPickerVisible = ref(false)
  const domainKeyword = ref('')
  const domainError = ref('')
  const domainOptions = ref<{ value: string; wildcard: boolean }[]>([])
  const selectedDomains = ref<string[]>([])

  const filteredDomains = computed(() => {
    const keyword = domainKeyword.value.trim().toLowerCase()
    if (!keyword) return domainOptions.value
    return domainOptions.value.filter((row) => row.value.toLowerCase().includes(keyword))
  })

  /** 打开弹窗：先拉列表，默认勾上「当前值里还没有的」域名 */
  const openDomainPicker = async () => {
    const item = props.item
    const sourceKey = item.domainFrom
    if (!sourceKey) return
    const accessId = (props.formValues || {})[sourceKey]
    if (!accessId) {
      ElMessage.warning('请先选择 DNS 授权')
      return
    }
    domainKeyword.value = ''
    domainError.value = ''
    domainPickerVisible.value = true
    domainLoading.value = true
    try {
      const data = await fetchAccessDomains(Number(accessId))
      const base: string[] = data.domains || []
      const patterns: string[] = data.patterns || []
      // patterns 里是「主域名 + *.主域名」，这里标出哪条是泛域名
      const rows = (patterns.length ? patterns : base).map((value) => ({
        value,
        wildcard: value.startsWith('*.'),
      }))
      domainOptions.value = rows
      const current = new Set(tagValue.value)
      // 默认勾选：泛域名（大多数证书要的就是它）＋ 当前已填的
      selectedDomains.value = rows
        .filter((row) => row.wildcard || current.has(row.value))
        .map((row) => row.value)
      if (!rows.length) domainError.value = '该 DNS 授权下没有查到域名'
    } catch (error: any) {
      domainOptions.value = []
      domainError.value = error?.message || '拉取域名失败'
    } finally {
      domainLoading.value = false
    }
  }

  const toggleDomainSelection = (mode: 'all' | 'none' | 'wildcard') => {
    if (mode === 'none') {
      selectedDomains.value = []
      return
    }
    const scope = filteredDomains.value.filter((row) =>
      mode === 'all' ? true : row.wildcard
    )
    selectedDomains.value = scope.map((row) => row.value)
  }

  /** 把勾选的域名合并进当前值（已有的不重复、不覆盖用户手填的其他域名） */
  const applySelectedDomains = () => {
    if (!selectedDomains.value.length) {
      ElMessage.warning('请至少选择一个域名')
      return
    }
    const merged = [...new Set([...tagValue.value, ...selectedDomains.value])]
    tagValue.value = merged
    domainPickerVisible.value = false
    ElMessage.success('已填入 ' + selectedDomains.value.length + ' 个域名')
  }

  // 授权一选好就去拉对端资源，不用等用户点开下拉再等一次
  watch(
    () => (props.formValues || {})[props.item.remoteFrom || 'accessId'],
    (next, prev) => {
      if (!props.item.remote) return
      remoteOptions.value = []
      remoteLoaded.value = false
      remoteError.value = ''
      autoFilledValue.value = null
      matchCount.value = 0
      matchedOption.value = null
      if (next && next !== prev) loadRemote(true)
    }
  )

  // 证书域名变了（比如改了申请任务的域名）：重新匹配一次
  watch(certBaseDomains, () => {
    if (props.item.autoMatchDomains) applyAutoMatch()
  })

  onMounted(() => {
    if (props.item.component === 'access') loadAccess()
    if (props.item.component === 'notification') loadNotification()
    // 编辑已有任务时，授权已经选好，直接把远程资源拉出来
    if (props.item.remote) {
      const accessKey = props.item.remoteFrom || 'accessId'
      if ((props.formValues || {})[accessKey]) loadRemote(true)
    }
  })

  /** 表单数据变化后（选中授权）由父组件触发刷新 */
  defineExpose({ refreshRemote: () => loadRemote(true), refreshAccess: loadAccess })
</script>

<style scoped>
  .plugin-field {
    width: 100%;
  }

  .field-with-hint {
    width: 100%;
  }

  .match-tip {
    display: flex;
    gap: 4px;
    align-items: center;
    margin-top: 4px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--art-gray-600);
    word-break: break-all;
  }

  .match-tip.is-auto {
    color: var(--theme-color);
  }

  .match-tip.is-warn {
    color: var(--el-color-danger);
  }

  .domain-picker-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
  }

  .domain-picker-toolbar :deep(.el-button) {
    flex: 0 0 auto;
  }

  .domain-picker-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 46vh;
    overflow: auto;
  }

  .domain-picker-item {
    display: flex;
    gap: 8px;
    align-items: center;
    width: 100%;
    height: auto;
    padding: 6px 8px;
    margin: 0;
    border-radius: 8px;
  }

  .domain-picker-item:hover {
    background: var(--default-box-color);
  }

  .domain-picker-item :deep(.el-checkbox__label) {
    display: flex;
    flex: 1;
    gap: 8px;
    align-items: center;
    min-width: 0;
    overflow: hidden;
  }

  .domain-picker-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: flex-end;
  }

  .plugin-field-helper {
    margin-top: 4px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--art-gray-600);
  }
</style>
