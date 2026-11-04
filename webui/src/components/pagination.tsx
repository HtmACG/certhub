import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function Pagination({
  current,
  size,
  total,
  onChange,
}: {
  current: number
  size: number
  total: number
  onChange: (page: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / size))
  const from = total === 0 ? 0 : (current - 1) * size + 1
  const to = Math.min(current * size, total)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3">
      <p className="text-xs text-muted-foreground tabular-nums">
        {from}–{to} / 共 {total} 条
      </p>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon-sm" disabled={current <= 1} onClick={() => onChange(current - 1)}>
          <ChevronLeft />
        </Button>
        <span className="px-2 text-xs text-muted-foreground tabular-nums">
          {current} / {pages}
        </span>
        <Button variant="outline" size="icon-sm" disabled={current >= pages} onClick={() => onChange(current + 1)}>
          <ChevronRight />
        </Button>
      </div>
    </div>
  )
}
