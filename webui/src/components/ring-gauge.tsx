import { cn } from '@/lib/utils'

const TONE = {
  ok: 'var(--success)',
  warn: 'var(--warning)',
  danger: 'var(--destructive)',
  idle: 'var(--muted-foreground)',
} as const

export type GaugeTone = keyof typeof TONE

/** 240° 弧线仪表：数值居中，没有指针和刻度数字 */
export function RingGauge({
  value,
  label,
  caption,
  tone,
  unit = '%',
  size = 132,
}: {
  value: number
  label: string
  caption?: string
  tone: GaugeTone
  unit?: string
  size?: number
}) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0))
  const radius = size / 2 - 10
  const circumference = 2 * Math.PI * radius
  const sweep = 240 / 360
  const arc = circumference * sweep
  const dash = (clamped / 100) * arc
  const color = TONE[tone]

  return (
    <div className="flex items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-[150deg]">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--muted)"
            strokeWidth={9}
            strokeLinecap="round"
            strokeDasharray={`${arc} ${circumference}`}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={9}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference}`}
            style={{ transition: 'stroke-dasharray 500ms ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold tabular-nums tracking-tight">
            {clamped.toFixed(0)}
            <span className="ml-0.5 text-xs font-normal text-muted-foreground">{unit}</span>
          </span>
        </div>
      </div>
      <div className="min-w-0 space-y-0.5">
        <p className="text-sm font-medium">{label}</p>
        {caption && <p className={cn('text-xs text-muted-foreground')}>{caption}</p>}
      </div>
    </div>
  )
}
