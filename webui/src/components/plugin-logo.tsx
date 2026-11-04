import { Bell, FolderCog, Server, ShieldCheck, Waypoints } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { TaskPlugin } from '@/lib/types'
import { VendorLogo } from './vendor-logo'

const GROUP_ICON: Record<string, LucideIcon> = {
  cert: ShieldCheck,
  deploy: Waypoints,
  notify: Bell,
}

/** 插件标识：有本地 logo 用 logo，没有就按分组退回一个图标，不留空白块 */
export function PluginLogo({
  plugin,
  size = 26,
  className,
}: {
  plugin?: TaskPlugin
  size?: number
  className?: string
}) {
  const Icon = (plugin && GROUP_ICON[plugin.group]) || (plugin?.group === 'deploy' ? Server : FolderCog)
  return (
    <VendorLogo
      logoFile={plugin?.logoFile}
      name={plugin?.name || plugin?.type || '?'}
      size={size}
      className={className}
      icon={<Icon className="size-[55%]" strokeWidth={1.9} />}
    />
  )
}
