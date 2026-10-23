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
    meta: { title: '工作台', icon: 'ri:dashboard-line', keepAlive: true },
  },
  {
    path: '/certd/pipeline',
    name: 'CertdPipeline',
    component: '/certd/pipeline',
    meta: { title: '证书流水线', icon: 'ri:node-tree', keepAlive: true },
  },
  {
    path: '/certd/pipeline/detail/:id',
    name: 'CertdPipelineDetail',
    component: '/certd/pipeline/detail',
    meta: { title: '流水线详情', icon: 'ri:git-branch-line', isHide: true, isHideTab: true },
  },
  {
    path: '/certd/history',
    name: 'CertdHistory',
    component: '/certd/history',
    meta: { title: '执行历史', icon: 'ri:history-line', keepAlive: true },
  },
  {
    path: '/certd/cert',
    name: 'CertdCert',
    component: '/certd/cert',
    meta: { title: '证书库', icon: 'ri:award-line', keepAlive: true },
  },
  {
    path: '/certd/dns-cname',
    name: 'CertdDnsCname',
    component: '/certd/dns/cname',
    meta: { title: 'CNAME 记录', icon: 'ri:links-line', keepAlive: true },
  },
  {
    path: '/certd/dns-subdomain',
    name: 'CertdDnsSubdomain',
    component: '/certd/dns/subdomain',
    meta: { title: '子域名托管', icon: 'ri:organization-chart', keepAlive: true },
  },
  {
    path: '/certd/access',
    name: 'CertdAccess',
    component: '/certd/access',
    meta: { title: '授权管理', icon: 'ri:draft-line', keepAlive: true },
  },
  {
    path: '/certd/notification',
    name: 'CertdNotification',
    component: '/certd/notification',
    meta: { title: '通知渠道', icon: 'ri:notification-3-line', keepAlive: true },
  },
  {
    path: '/certd/monitor',
    name: 'CertdMonitor',
    component: '/certd/monitor',
    meta: { title: '站点监控', icon: 'ri:radar-line', keepAlive: true },
  },
  {
    path: '/certd/user',
    name: 'CertdSystemUser',
    component: '/certd/system/user',
    meta: { title: '用户管理', icon: 'ri:user-line', roles: ['R_SUPER'], keepAlive: true },
  },
  {
    path: '/certd/setting',
    name: 'CertdSystemSetting',
    component: '/certd/system/setting',
    meta: { title: '系统设置', icon: 'ri:settings-4-line', roles: ['R_SUPER'], keepAlive: true },
  },
  {
    path: '/certd/audit',
    name: 'CertdSystemAudit',
    component: '/certd/system/audit',
    meta: { title: '审计日志', icon: 'ri:file-list-3-line', roles: ['R_SUPER'], keepAlive: true },
  },
  {
    path: '/certd/apikey',
    name: 'CertdSystemApiKey',
    component: '/certd/system/apikey',
    meta: { title: '开放接口', icon: 'ri:terminal-box-line', keepAlive: true },
  },
  {
    path: '/certd/profile',
    name: 'CertdProfile',
    component: '/certd/profile',
    // 侧边栏可见：改密码、两步验证都要从这里进（头像下拉按要求只保留了"退出登录"）
    meta: { title: '账号与安全', icon: 'ri:user-settings-line', keepAlive: true },
  },
]
