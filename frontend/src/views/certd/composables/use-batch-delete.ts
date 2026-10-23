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

export interface BatchDeleteOptions<T> {
  /** 资源中文名，用于确认框与提示文案，例如「证书」 */
  label: string
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
    const preview = rows
      .slice(0, 3)
      .map((row) => options.nameOf?.(row) || '#' + row.id)
      .join('、')
    await ElMessageBox.confirm(
      `确定删除选中的 ${rows.length} 个${options.label}吗？` +
        (preview ? `（${preview}${rows.length > 3 ? ' 等' : ''}）` : ''),
      `批量删除${options.label}`,
      { type: 'warning' }
    )
    removing.value = true
    try {
      for (const row of rows) {
        await remove(row.id)
      }
      ElMessage.success(`已删除 ${rows.length} 个${options.label}`)
      clearSelection()
      options.onDone?.()
    } finally {
      removing.value = false
    }
  }

  return { selectedRows, selectedIds, removing, handleSelectionChange, removeSelected, clearSelection }
}
