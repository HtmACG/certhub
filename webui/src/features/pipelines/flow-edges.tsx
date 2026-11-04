import { BaseEdge, EdgeLabelRenderer, type EdgeProps } from '@xyflow/react'

export type Point = [number, number]

/** 直角折线 + 圆角，避免尖角看起来像表格线 */
export function roundedPath(points: Point[], radius = 8) {
  if (points.length < 2) return ''
  const commands: string[] = [`M ${points[0][0]} ${points[0][1]}`]

  for (let index = 1; index < points.length - 1; index += 1) {
    const [px, py] = points[index]
    const [prevX, prevY] = points[index - 1]
    const [nextX, nextY] = points[index + 1]
    const inLength = Math.hypot(px - prevX, py - prevY)
    const outLength = Math.hypot(nextX - px, nextY - py)
    const r = Math.min(radius, inLength / 2, outLength / 2)
    const ax = px + ((prevX - px) / (inLength || 1)) * r
    const ay = py + ((prevY - py) / (inLength || 1)) * r
    const bx = px + ((nextX - px) / (outLength || 1)) * r
    const by = py + ((nextY - py) / (outLength || 1)) * r
    commands.push(`L ${ax} ${ay}`, `Q ${px} ${py} ${bx} ${by}`)
  }

  const [lastX, lastY] = points[points.length - 1]
  commands.push(`L ${lastX} ${lastY}`)
  return commands.join(' ')
}

interface RoutedData {
  points?: Point[]
  label?: { x: number; y: number; text: string }
}

/** 路径点在布局阶段算好（绕开卡片），这里只负责画线和标签 */
export function RoutedEdge({ data, style, markerEnd }: EdgeProps) {
  const routed = (data || {}) as RoutedData
  const points = routed.points || []
  if (points.length < 2) return null

  return (
    <>
      <BaseEdge path={roundedPath(points, 8)} markerEnd={markerEnd} style={style} />
      {routed.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              transform: `translate(-50%, -50%) translate(${routed.label.x}px, ${routed.label.y}px)`,
            }}
            className="pointer-events-none absolute rounded border bg-background px-1.5 py-0.5 text-[10px] leading-none text-warning"
          >
            {routed.label.text}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}
