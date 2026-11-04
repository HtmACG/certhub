import { Badge } from '@/components/ui/badge'

type Variant = 'default' | 'secondary' | 'outline' | 'muted' | 'success' | 'warning' | 'destructive' | 'info'

const STATUS: Record<string, { label: string; variant: Variant }> = {
  success: { label: '成功', variant: 'success' },
  ok: { label: '正常', variant: 'success' },
  running: { label: '运行中', variant: 'info' },
  pending: { label: '等待中', variant: 'muted' },
  failed: { label: '失败', variant: 'destructive' },
  error: { label: '异常', variant: 'destructive' },
  skipped: { label: '已跳过', variant: 'muted' },
  disabled: { label: '已停用', variant: 'muted' },
  stopped: { label: '已停止', variant: 'warning' },
  valid: { label: '有效', variant: 'success' },
  expired: { label: '已过期', variant: 'destructive' },
  expiring: { label: '即将到期', variant: 'warning' },
}

export function StatusBadge({ status, className }: { status?: string; className?: string }) {
  const meta = STATUS[status || ''] || { label: status || '未知', variant: 'outline' as Variant }
  return (
    <Badge variant={meta.variant} className={className}>
      {meta.label}
    </Badge>
  )
}

export function KindBadges({ kinds }: { kinds?: string[] }) {
  const map: Record<string, { label: string; color: string }> = {
    cert: { label: '申请', color: 'var(--stage-cert)' },
    deploy: { label: '部署', color: 'var(--stage-deploy)' },
    notify: { label: '通知', color: 'var(--stage-notify)' },
  }
  if (!kinds?.length) return <span className="text-xs text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap items-center gap-1">
      {kinds.map((kind) => {
        const meta = map[kind] || { label: kind, color: 'var(--muted-foreground)' }
        return (
          <span
            key={kind}
            className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium"
            style={{ color: meta.color, borderColor: `color-mix(in oklab, ${meta.color} 35%, transparent)` }}
          >
            <span className="size-1.5 rounded-full" style={{ background: meta.color }} />
            {meta.label}
          </span>
        )
      })}
    </div>
  )
}

export function daysTone(days: number | null | undefined) {
  if (days == null) return 'muted' as const
  if (days <= 7) return 'destructive' as const
  if (days <= 30) return 'warning' as const
  return 'success' as const
}
