import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

/** 日志只做文本分词高亮，禁止 innerHTML —— 日志里带用户填的域名与密钥路径 */
function tokenize(line: string) {
  const parts: { text: string; className?: string }[] = []
  const pattern =
    /(\d{2}:\d{2}:\d{2})|(https?:\/\/\S+)|(\[[^\]]+\])|(\b(?:成功|失败|错误|警告|跳过)\b)|(\b\d+\.\d+\.\d+\.\d+\b)/g
  let last = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(line))) {
    if (match.index > last) parts.push({ text: line.slice(last, match.index) })
    const [text] = match
    const className = match[1]
      ? 'text-zinc-500'
      : match[2]
        ? 'text-sky-400 underline decoration-sky-400/40'
        : match[3]
          ? 'text-violet-300'
          : match[4]
            ? /成功/.test(text)
              ? 'text-emerald-400'
              : 'text-rose-400'
            : 'text-amber-300'
    parts.push({ text, className })
    last = match.index + text.length
  }
  if (last < line.length) parts.push({ text: line.slice(last) })
  return parts
}

export function LogTerminal({
  lines,
  title,
  accent,
  className,
  fill = false,
  empty = '还没有日志。运行一次流水线，这里会实时显示执行过程。',
}: {
  lines: string[]
  title?: string
  accent?: string
  className?: string
  /** true 时纵向铺满父容器（日志坞用），false 时保持固定最大高度（弹窗用） */
  fill?: boolean
  empty?: string
}) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [lines.length])

  return (
    <div
      className={cn(
        'overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950',
        fill && 'flex min-h-0 flex-col',
        className,
      )}
      style={accent ? { borderLeft: `3px solid ${accent}` } : undefined}
    >
      {title && (
        <div className="flex shrink-0 items-center justify-between border-b border-zinc-800 px-3 py-2">
          <span className="text-xs font-medium text-zinc-300" style={accent ? { color: accent } : undefined}>
            {title}
          </span>
          <span className="text-[11px] text-zinc-500">{lines.length} 行</span>
        </div>
      )}
      <div
        className={cn(
          'scrollbar-thin overflow-y-auto px-3 py-2 font-mono text-[12px] leading-relaxed text-zinc-300',
          fill ? 'min-h-0 flex-1' : 'h-full max-h-[320px] min-h-[140px]',
        )}
      >
        {lines.length === 0 ? (
          <p className="py-6 text-center text-zinc-500">{empty}</p>
        ) : (
          lines.map((line, index) => (
            <div key={index} className="whitespace-pre-wrap break-all">
              {tokenize(line).map((token, tokenIndex) => (
                <span key={tokenIndex} className={token.className}>
                  {token.text}
                </span>
              ))}
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}
