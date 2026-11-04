import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import type { TaskPlugin } from '@/lib/types'
import { PluginLogo } from '@/components/plugin-logo'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/** 拖拽时 dataTransfer 里的类型标识，画布按它判断「这是从任务列表拖过来的」 */
export const TASK_DRAG_TYPE = 'application/x-certhub-task'

/** 右侧任务列表：拖到画布上的某个阶段，或点一下直接加到默认阶段 */
export function TaskPalette({
  plugins,
  groups,
  onAdd,
}: {
  plugins: TaskPlugin[]
  groups: { key: string; name: string }[]
  onAdd: (type: string) => void
}) {
  const [keyword, setKeyword] = useState('')
  const [group, setGroup] = useState('all')

  const visible = useMemo(
    () =>
      plugins.filter((plugin) => {
        if (group !== 'all' && plugin.group !== group) return false
        if (!keyword.trim()) return true
        const text = `${plugin.name} ${plugin.type} ${plugin.desc || ''}`.toLowerCase()
        return text.includes(keyword.trim().toLowerCase())
      }),
    [plugins, group, keyword],
  )

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border bg-card">
      <div className="border-b px-3 py-2">
        <p className="text-sm font-medium">任务列表</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">拖到画布任意阶段，或点击添加</p>
      </div>

      <div className="space-y-2 border-b p-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索任务"
            className="h-8 pl-8 text-sm"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {[{ key: 'all', name: '全部' }, ...groups].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setGroup(item.key)}
              className={cn(
                'rounded-md border px-2 py-0.5 text-[11px] transition-colors',
                group === item.key
                  ? 'border-foreground/30 bg-accent font-medium text-foreground'
                  : 'text-muted-foreground hover:bg-accent',
              )}
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
        {visible.length === 0 && (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">没有匹配的任务</p>
        )}
        {visible.map((plugin) => (
          <div
            key={plugin.type}
            role="button"
            tabIndex={0}
            draggable
            onDragStart={(event) => {
              event.dataTransfer.setData(TASK_DRAG_TYPE, plugin.type)
              event.dataTransfer.effectAllowed = 'copy'
            }}
            onClick={() => onAdd(plugin.type)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onAdd(plugin.type)
            }}
            title={`${plugin.desc || plugin.name}（拖到画布，或点击添加）`}
            className="flex cursor-grab items-center gap-2 rounded-md border border-transparent px-2 py-1.5 transition-colors hover:border-border hover:bg-accent active:cursor-grabbing"
          >
            <PluginLogo plugin={plugin} size={22} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium">{plugin.name}</span>
              <span className="block truncate text-[10px] text-muted-foreground">{plugin.desc || plugin.type}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
