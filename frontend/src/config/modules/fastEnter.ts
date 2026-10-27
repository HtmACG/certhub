/**
 * 快速入口配置
 * 包含：应用列表、快速链接等配置
 *
 * 这里的每一项都是本系统（CertHub）自己的功能入口，和艺术模板的演示页无关。
 * routeName 必须与 src/router/modules/certd.ts 里的路由 name 一致，
 * 否则点击会跳不过去（handleNavigate 用的是 router.push({ name })）。
 */
import type { FastEnterConfig } from '@/types/config'

const fastEnterConfig: FastEnterConfig = {
  // 显示条件（屏幕宽度）
  minWidth: 1200,
  // 应用列表：日常最常进的几个页面
  applications: [
    {
      name: '证书流水线',
      description: '签发 · 部署 · 通知全流程',
      icon: 'ri:node-tree',
      iconColor: '#409eff',
      enabled: true,
      order: 1,
      routeName: 'CertdPipeline'
    },
    {
      name: '证书库',
      description: '已签发证书与到期时间',
      icon: 'ri:award-line',
      iconColor: '#1e8e3e',
      enabled: true,
      order: 2,
      routeName: 'CertdCert'
    },
    {
      name: '授权管理',
      description: '云厂商 / 面板 / DNS 凭据',
      icon: 'ri:draft-line',
      iconColor: '#7A7FFF',
      enabled: true,
      order: 3,
      routeName: 'CertdAccess'
    },
    {
      name: '通知渠道',
      description: '告警推送渠道配置',
      icon: 'ri:notification-3-line',
      iconColor: '#13DEB9',
      enabled: true,
      order: 4,
      routeName: 'CertdNotification'
    },
    {
      name: '站点监控',
      description: '站点证书巡检与告警',
      icon: 'ri:radar-line',
      iconColor: '#ffb100',
      enabled: true,
      order: 5,
      routeName: 'CertdMonitor'
    },
    {
      name: '执行历史',
      description: '每次运行的日志与结果',
      icon: 'ri:history-line',
      iconColor: '#ff6b6b',
      enabled: true,
      order: 6,
      routeName: 'CertdHistory'
    }
  ],
  // 快捷功能：其余常用入口
  quickLinks: [
    {
      name: '工作台',
      enabled: true,
      order: 1,
      routeName: 'CertdDashboard'
    },
    {
      name: 'CNAME 记录',
      enabled: true,
      order: 3,
      routeName: 'CertdDnsCname'
    },
    {
      name: '子域名托管',
      enabled: true,
      order: 4,
      routeName: 'CertdDnsSubdomain'
    },
    {
      name: '开放接口',
      enabled: true,
      order: 5,
      routeName: 'CertdSystemApiKey'
    },
    {
      name: '用户管理',
      enabled: true,
      order: 6,
      routeName: 'CertdSystemUser'
    },
    {
      name: '系统设置',
      enabled: true,
      order: 7,
      routeName: 'CertdSystemSetting'
    },
    {
      name: '审计日志',
      enabled: true,
      order: 8,
      routeName: 'CertdSystemAudit'
    },
    {
      name: '账号与安全',
      enabled: true,
      order: 9,
      // 已合并进「系统设置 → 安全」，快捷入口直接指过去
      routeName: 'CertdSystemSetting'
    }
  ]
}

export default Object.freeze(fastEnterConfig)
