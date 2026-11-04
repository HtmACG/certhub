import {
  Activity,
  Award,
  FileClock,
  KeyRound,
  LayoutDashboard,
  Link2,
  Network,
  ScrollText,
  Settings,
  ShieldCheck,
  UserCog,
  Users,
  Workflow,
  Bell,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  description?: string
  /** 需要的功能权限键（和 app/permissions.py 对齐）；不填 = 所有人可看 */
  perm?: string
  /** 仅管理员可见/可进 */
  adminOnly?: boolean
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

export const NAV: NavGroup[] = [
  {
    label: '概览',
    items: [{ to: '/', label: '工作台', icon: LayoutDashboard, description: '证书、流水线与系统状态' }],
  },
  {
    label: '证书流程',
    items: [
      { to: '/pipelines', label: '证书流水线', icon: Workflow, description: '申请、部署与通知的执行编排', perm: 'pipelines' },
      { to: '/history', label: '执行历史', icon: FileClock, description: '每一次运行的结果与日志', perm: 'history' },
      { to: '/certs', label: '证书库', icon: Award, description: '已签发的证书与到期时间', perm: 'certs' },
    ],
  },
  {
    label: '接入资源',
    items: [
      { to: '/access', label: '授权管理', icon: ShieldCheck, description: 'DNS、主机与云厂商凭据', perm: 'access' },
      { to: '/dns', label: 'DNS 记录', icon: Link2, description: 'CNAME 与子域名托管', perm: 'dns' },
      { to: '/monitor', label: '站点监控', icon: Activity, description: '站点证书有效期巡检', perm: 'monitor' },
      { to: '/notifications', label: '通知渠道', icon: Bell, description: '邮件、Webhook 与机器人', perm: 'notifications' },
    ],
  },
  {
    label: '系统',
    items: [
      { to: '/settings', label: '系统设置', icon: Settings, description: '站点、网络与安全策略', adminOnly: true },
      { to: '/account', label: '账号安全', icon: UserCog, description: '资料、密码与两步验证' },
      { to: '/users', label: '用户管理', icon: Users, description: '账号、用户组与角色', adminOnly: true },
      { to: '/audit', label: '审计日志', icon: ScrollText, description: '谁在什么时候改了什么', adminOnly: true },
      { to: '/api-keys', label: '开放接口', icon: KeyRound, description: '给脚本用的 API Key', adminOnly: true },
    ],
  },
]

export const ALL_NAV = NAV.flatMap((group) => group.items)

export function findNav(pathname: string): NavItem | undefined {
  if (pathname === '/') return ALL_NAV[0]
  if (pathname.startsWith('/pipelines/')) {
    return { to: '/pipelines', label: '流水线详情', icon: Network, description: '阶段与任务编排' }
  }
  return [...ALL_NAV].sort((a, b) => b.to.length - a.to.length).find((item) => pathname.startsWith(item.to))
}
