import { useId } from 'react'

/**
 * 全局水印：固定铺满视口，半透明、斜向重复。
 * 用 SVG pattern 而不是 data-URI 背景，颜色能跟着 --foreground 走，深浅色主题都可见。
 */
export function Watermark({ text }: { text?: string }) {
  const rawId = useId()
  const id = `wm-${rawId.replace(/[^a-zA-Z0-9_-]/g, '')}`
  const value = (text || '').trim()
  if (!value) return null

  return (
    <svg
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[5] h-full w-full select-none text-foreground"
    >
      <defs>
        <pattern
          id={id}
          width="280"
          height="160"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(-24)"
        >
          <text
            x="8"
            y="86"
            fill="currentColor"
            fillOpacity="0.06"
            fontSize="13"
            fontWeight="500"
            fontFamily="system-ui, -apple-system, 'Segoe UI', sans-serif"
          >
            {value}
          </text>
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  )
}
