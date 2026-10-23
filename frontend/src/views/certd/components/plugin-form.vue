<!--
  插件表单（元数据驱动）
  =========================================================
  用 Art Design Pro 的 ArtForm 负责栅格 / 响应式 / 标签排版，
  字段控件交给 PluginField，字段清单完全来自后端 /api/pipeline/plugins。

  字段可以带 group（小节标题）：同组的字段渲染到一个带标题的区块里，
  字段多的插件（群晖、宝塔）才不至于变成一长串没头没尾的输入框。
  不带 group 的字段落在无标题区，观感与以前完全一致。

  不要在这里为某个插件写特例：要新增字段请改后端 plugins.py。
-->
<template>
  <div class="plugin-form">
    <section v-for="section in sections" :key="section.key" class="plugin-form-section">
      <div v-if="section.title" class="plugin-form-section-title">{{ section.title }}</div>
      <ArtForm
        v-model="model"
        :items="section.items"
        :span="span"
        :label-position="labelPosition"
        label-width="120px"
        :show-reset="false"
        :show-submit="false"
      >
        <template v-for="item in section.items" :key="item.key" #[item.key]="{ modelValue }">
          <PluginField
            v-model="model[item.key]"
            :item="fieldOf(item.key)"
            :task-type="taskType"
            :form-values="modelValue || model"
            :cert-domains="certDomains"
          />
        </template>
      </ArtForm>
    </section>
  </div>
</template>

<script setup lang="ts">
  import { useWindowSize } from '@vueuse/core'
  import type { PluginField as PluginFieldMeta } from '@/api/certd'
  import ArtForm from '@/components/core/forms/art-form/index.vue'
  import PluginField from './plugin-field.vue'
  import { matchShowWhen } from '@/utils/certd'

  defineOptions({ name: 'PluginForm' })

  interface Props {
    /** 字段元数据（后端插件 inputs） */
    fields: PluginFieldMeta[]
    /** 任务类型，远程下拉需要 */
    taskType?: string
    /** 每行列数（24 栅格的 span，默认 12 = 两列） */
    span?: number
    /** 流水线申请的证书域名：远程资源（宝塔站点 / CDN 加速域名）按它自动匹配 */
    certDomains?: string[]
  }

  const props = withDefaults(defineProps<Props>(), {
    span: 12,
    certDomains: () => [],
  })

  /** 表单数据：直接绑定任务 input 对象，插件字段会就地写入 */
  const model = defineModel<Record<string, any>>({ default: () => ({}) })

  const { width } = useWindowSize()
  // 窄屏改成上下布局，标签不挤压输入框（移动端/半屏窗口都能用）
  const labelPosition = computed(() => (width.value < 768 ? 'top' : 'right'))

  const fieldMap = computed(() => {
    const map: Record<string, PluginFieldMeta> = {}
    for (const field of props.fields || []) map[field.key] = field
    return map
  })

  const fieldOf = (key: string) => fieldMap.value[key] || { key, title: key }

  /** 按 showWhen 过滤后的可见字段 */
  const visibleFields = computed(() =>
    (props.fields || []).filter((field) => matchShowWhen(field.showWhen, model.value || {}))
  )

  /** ArtForm 需要的 items 结构（label + span + type） */
  const toFormItem = (field: PluginFieldMeta) => ({
    key: field.key,
    label: field.required ? field.title + ' *' : field.title,
    // 多行输入 / 标签 / 说明偏长的字段占整行，避免挤成一条
    span: fieldsTakeFullRow(field) ? 24 : props.span,
  })

  /** 按 group 切成小节，保持后端声明的字段顺序 */
  const sections = computed(() => {
    const list: { key: string; title: string; items: ReturnType<typeof toFormItem>[] }[] = []
    for (const field of visibleFields.value) {
      const title = String(field.group || '').trim()
      const key = title || '__default__'
      let section = list.find((item) => item.key === key)
      if (!section) {
        section = { key, title, items: [] }
        list.push(section)
      }
      section.items.push(toFormItem(field))
    }
    return list
  })

  function fieldsTakeFullRow(field: PluginFieldMeta): boolean {
    if (field.component === 'textarea' || field.component === 'tags') return true
    if (field.component === 'notification') return true
    if (field.helper && field.helper.length > 24) return true
    return false
  }

  /** 父组件可以在打开表单时调用，补齐元数据里声明的默认值 */
  const applyDefaults = () => {
    const target = model.value
    if (!target) return
    for (const field of props.fields || []) {
      if (target[field.key] === undefined && field.default !== undefined) {
        target[field.key] = Array.isArray(field.default) ? [...field.default] : field.default
      }
    }
  }

  defineExpose({ applyDefaults })
</script>

<style scoped>
  /* ArtForm 自带 px-4 pt-4 内边距，分小节后每节都加一次会撑得太开，这里收掉 */
  .plugin-form-section :deep(section) {
    padding: 0;
  }

  .plugin-form-section + .plugin-form-section {
    margin-top: 2px;
  }

  .plugin-form-section-title {
    display: flex;
    gap: 10px;
    align-items: center;
    margin: 10px 0 8px;
    font-size: 12px;
    font-weight: 600;
    line-height: 1;
    color: var(--art-gray-600);
    letter-spacing: 0.02em;
  }

  .plugin-form-section-title::after {
    flex: 1;
    height: 1px;
    content: '';
    background: var(--art-card-border);
  }
</style>
