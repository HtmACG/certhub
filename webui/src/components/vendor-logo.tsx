import { useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * 厂商标识：优先用后端下发的本地文件（/logos/...），加载失败再退回图标或「品牌色底 + 首字母」。
 * 不直连 CDN —— 内网和离线环境取不到图，卡片会变成空白块。
 */
export function VendorLogo({
  logoFile,
  name,
  color,
  size = 28,
  icon,
  className,
}: {
  logoFile?: string
  name: string
  color?: string
  size?: number
  icon?: ReactNode
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  const letter = (name || '?').trim().slice(0, 1).toUpperCase()
  const tint = color || 'var(--muted-foreground)'

  if (logoFile && !failed) {
    return (
      <span
        className={cn('flex shrink-0 items-center justify-center overflow-hidden rounded-md border bg-background', className)}
        style={{ width: size, height: size, padding: Math.max(3, size * 0.14) }}
      >
        <img
          src={logoFile}
          alt={name}
          loading="lazy"
          className="size-full object-contain"
          onError={() => setFailed(true)}
        />
      </span>
    )
  }

  return (
    <span
      className={cn('flex shrink-0 items-center justify-center rounded-md border font-semibold', className)}
      style={{
        width: size,
        height: size,
        fontSize: Math.max(10, size * 0.42),
        color: tint,
        background: `color-mix(in oklab, ${tint} 10%, var(--background))`,
        borderColor: `color-mix(in oklab, ${tint} 22%, var(--border))`,
      }}
      aria-hidden
    >
      {icon ?? letter}
    </span>
  )
}
