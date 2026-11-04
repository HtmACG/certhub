import { cn } from '@/lib/utils'

export function Tabs<T extends string>({
  value,
  onChange,
  items,
  className,
}: {
  value: T
  onChange: (value: T) => void
  items: { value: T; label: string; count?: number }[]
  className?: string
}) {
  return (
    <div className={cn('inline-flex h-9 items-center gap-1 rounded-lg bg-muted p-1 text-muted-foreground', className)}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          onClick={() => onChange(item.value)}
          className={cn(
            'inline-flex h-7 items-center gap-1.5 rounded-md px-3 text-sm font-medium transition-colors',
            value === item.value
              ? 'bg-background text-foreground shadow-xs'
              : 'hover:text-foreground',
          )}
        >
          {item.label}
          {typeof item.count === 'number' && (
            <span className="rounded bg-muted-foreground/10 px-1 text-[11px] tabular-nums">{item.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}
