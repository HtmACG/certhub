import { AppRouteRecord } from '@/types/router'

/**
 * CertHub 业务路由
 *
 * 每个页面都是独立的一级路由（框架会自动用 Layout 包裹），
 * 不再有「证书管理」这层容器菜单，菜单栏直接展示各功能入口。
 */
export const certdRoutes: AppRouteRecord[] = [
  {
    path: '/certd/dashboard',
    name: 'CertdDashboard',
    component: '/certd/dashboard',
    meta: { title: 'certd.menu.dashboard', icon: 'ri:dashboard-line', keepAlive: true },
  },
  {
    path: '/certd/pipeline',
    name: 'CertdPipeline',
    component: '/certd/pipeline',
    meta: { title: 'certd.menu.pipeline', icon: 'ri:node-tree', keepAlive: true },
  },
  {
    path: '/certd/pipeline/detail/:id',
    name: 'CertdPipelineDetail',
    component: '/certd/pipeline/detail',
    meta: { title: 'certd.menu.pipelineDetail', icon: 'ri:git-branch-line', isHide: true, isHideTab: true },
  },
  {
    // 分组已合并进「证书流水线」页的第二个页签，这里只保留老链接的跳转
    path: '/certd/pipeline-group',
    name: 'CertdPipelineGroupLegacy',
    component: '/certd/pipeline',
    redirect: '/certd/pipeline?tab=group',
    meta: { title: 'certd.menu.pipelineGroup', icon: 'ri:stack-line', isHide: true, isHideTab: true },
  },
  {
    path: '/certd/history',
    name: 'CertdHistory',
    component: '/certd/history',
    meta: { title: 'certd.menu.history', icon: 'ri:history-line', keepAlive: true },
  },
  {
    path: '/certd/cert',
    name: 'CertdCert',
    component: '/certd/cert',
    meta: { title: 'certd.menu.cert', icon: 'ri:award-line', keepAlive: true },
  },
  {
    path: '/certd/dns-cname',
    name: 'CertdDnsCname',
    component: '/certd/dns/cname',
    meta: { title: 'certd.menu.dnsCname', icon: 'ri:links-line', keepAlive: true },
  },
  {
    path: '/certd/dns-subdomain',
    name: 'CertdDnsSubdomain',
    component: '/certd/dns/subdomain',
    meta: { title: 'certd.menu.dnsSubdomain', icon: 'ri:organization-chart', keepAlive: true },
  },
  {
    path: '/certd/access',
    name: 'CertdAccess',
    component: '/certd/access',
    meta: { title: 'certd.menu.access', icon: 'ri:draft-line', keepAlive: true },
  },
  {
    path: '/certd/notification',
    name: 'CertdNotification',
    component: '/certd/notification',
    meta: { title: 'certd.menu.notification', icon: 'ri:notification-3-line', keepAlive: true },
  },
  {
    path: '/certd/monitor',
    name: 'CertdMonitor',
    component: '/certd/monitor',
    meta: { title: 'certd.menu.monitor', icon: 'ri:radar-line', keepAlive: true },
  },
  {
    path: '/certd/user',
    name: 'CertdSystemUser',
    component: '/certd/system/user',
    meta: { title: 'certd.menu.user', icon: 'ri:user-line', roles: ['R_SUPER'], keepAlive: true },
  },
  {
    path: '/certd/setting',
    name: 'CertdSystemSetting',
    component: '/certd/system/setting',
    // 安全页签里有「我的账号」，普通用户也要能进；管理员专属页签由页面内 isAdmin 控制
    meta: { title: 'certd.menu.setting', icon: 'ri:settings-4-line', keepAlive: true },
  },
  {
    path: '/certd/audit',
    name: 'CertdSystemAudit',
    component: '/certd/system/audit',
    meta: { title: 'certd.menu.audit', icon: 'ri:file-list-3-line', roles: ['R_SUPER'], keepAlive: true },
  },
  {
    path: '/certd/apikey',
    name: 'CertdSystemApiKey',
    component: '/certd/system/apikey',
    meta: { title: 'certd.menu.apikey', icon: 'ri:terminal-box-line', keepAlive: true },
  },
  {
    // 「账号与安全」已合并进「系统设置 → 安全」，这里只保留老链接的跳转
    path: '/certd/profile',
    name: 'CertdProfileLegacy',
    component: '/certd/system/setting',
    redirect: '/certd/setting?tab=security',
    meta: { title: 'certd.menu.profile', icon: 'ri:user-settings-line', isHide: true, isHideTab: true },
  },
]
