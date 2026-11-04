/**
 * 列表表格的「多选 + 批量删除」
 * =========================================================
 * 后端每个资源都只有单条删除接口（DELETE /api/xxx/{id}），
 * 所以这里串行调用：量级都是几十条，串行不会慢，还能在出错时立刻停下，
 * 不会出现「删了一半又报错」还继续往下删的情况。
 *
 * 用法：
 *   const { selectedIds, removing, handleSelectionChange, removeSelected } =
 *     useBatchDelete(deleteCert, { label: '证书', nameOf: (row) => row.domain, onDone: refreshData })
 *
 * 对应模板：
 *   columns 第一列加 { type: 'selection', width: 48 }
 *   <ArtTable @selection-change="handleSelectionChange">
 *   <ElButton :disabled="!selectedIds.length" @click="removeSelected">批量删除</ElButton>
 *
 * @module views/certd/composables/use-batch-delete
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { i18n } from '@/locales'

/** 取当前语言文案（必须在函数体内调用，见 locales/index.ts 的说明） */
function t(key: string, named?: Record<string, unknown>): string {
  const tr = i18n.global.t as unknown as (k: string, n?: Record<string, unknown>) => string
  return named ? tr(key, named) : tr(key)
}

export interface BatchDeleteOptions<T> {
  /**
   * 资源名，用于确认框与提示文案，例如「证书」
   *
   * ⚠️ 传**函数**而不是字符串：字符串在 setup 里求值一次就被语言烤死了，
   * 切到英文后再删除，弹窗还是中文。
   */
  label: () => string
  /** 确认框里列出前几条，让用户确认没删错 */
  nameOf?: (row: T) => string
  /** 删除完成后的回调（一般是刷新列表） */
  onDone?: () => void
}

export function useBatchDelete<T extends { id: number }>(
  remove: (id: number) => Promise<unknown>,
  options: BatchDeleteOptions<T>
) {
  const selectedRows = ref<T[]>([])
  const removing = ref(false)

  const selectedIds = computed(() => selectedRows.value.map((row) => row.id))

  const handleSelectionChange = (rows: T[]) => {
    selectedRows.value = rows
  }

  const clearSelection = () => {
    selectedRows.value = []
  }

  const removeSelected = async () => {
    const rows = [...selectedRows.value]
    if (!rows.length) return
    const label = options.label()
    const preview = rows
      .slice(0, 3)
      .map((row) => options.nameOf?.(row as T) || '#' + row.id)
      .join('、')
    await ElMessageBox.confirm(
      t('certd.table.confirmBatchDelete', { n: rows.length, name: label }) +
        (preview ? `${t('certd.table.itemListOpen')}${preview}${rows.length > 3 ? t('certd.table.etc') : ''}${t('certd.table.itemListClose')}` : ''),
      t('certd.table.batchDeleteTitle', { name: label }),
      { type: 'warning', confirmButtonText: t('certd.common.confirm'), cancelButtonText: t('certd.common.cancel') }
    )
    removing.value = true
    try {
      for (const row of rows) {
        await remove(row.id)
      }
      ElMessage.success(t('certd.table.batchDeleted', { n: rows.length, name: label }))
      clearSelection()
      options.onDone?.()
    } finally {
      removing.value = false
    }
  }

  return { selectedRows, selectedIds, removing, handleSelectionChange, removeSelected, clearSelection }
}
