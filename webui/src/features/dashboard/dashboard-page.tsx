import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Activity, Award, Cpu, HardDrive, MemoryStick, RefreshCw, Workflow } from 'lucide-react'
import { fetchOverview, fetchSystemInfo } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { StatCard } from '@/components/stat-card'
import { RingGauge, type GaugeTone } from '@/components/ring-gauge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { StatusBadge, daysTone } from '@/components/status'
import { EmptyState, Skeleton } from '@/components/ui/empty'
import { formatBytes } from '@/lib/format'

function toneFor(percent: number): GaugeTone {
  if (percent >= 90) return 'danger'
  if (percent >= 70) return 'warn'
  return 'ok'
}

function uptimeText(seconds: number) {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days} 天 ${hours} 小时`
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟`
  return `${minutes} 分钟`
}

export function DashboardPage() {
  const overview = useQuery({ queryKey: ['overview'], queryFn: fetchOverview, refetchInterval: 30_000 })
  const system = useQuery({ queryKey: ['system'], queryFn: fetchSystemInfo, refetchInterval: 30_000 })

  const stats = overview.data?.stats
  const sys = system.data
  const disk = sys?.systemDisk ?? sys?.disks?.find((item) => item.system) ?? sys?.disks?.[0]

  return (
    <div className="space-y-5">
      <PageHeader
        title="工作台"
        description="证书、流水线与主机的当前状态"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => overview.refetch()} disabled={overview.isFetching}>
              <RefreshCw className={overview.isFetching ? 'animate-spin' : ''} />
              刷新
            </Button>
            <Button size="sm" asChild>
              <Link to="/pipelines">
                <Workflow />
                管理流水线
              </Link>
            </Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="流水线"
          value={stats?.pipelineTotal ?? '—'}
          hint={stats ? `${stats.pipelineEnabled} 条启用 · 30 天运行 ${stats.runTotal30d} 次` : undefined}
          icon={Workflow}
        />
        <StatCard
          label="有效证书"
          value={stats?.certValid ?? '—'}
          hint={stats ? `共 ${stats.certTotal} 张 · ${stats.certExpiring} 张 30 天内到期` : undefined}
          icon={Award}
          tone={stats && stats.certExpiring > 0 ? 'warning' : 'success'}
        />
        <StatCard
          label="运行成功率"
          value={stats ? `${stats.successRate.toFixed(1)}%` : '—'}
          hint={stats ? `平均耗时 ${stats.avgDuration}s` : undefined}
          icon={Activity}
          tone={stats && stats.successRate < 80 ? 'warning' : 'success'}
        />
        <StatCard
          label="站点监控"
          value={stats?.siteTotal ?? '—'}
          hint={stats ? (stats.siteError > 0 ? `${stats.siteError} 个站点异常` : '全部正常') : undefined}
          icon={Activity}
          tone={stats && stats.siteError > 0 ? 'destructive' : 'default'}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>系统信息</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                {sys ? `${sys.hostname} · ${sys.os}` : '读取中…'}
              </p>
            </div>
            {sys && <Badge variant="muted">已运行 {uptimeText(sys.uptime)}</Badge>}
          </CardHeader>
          <CardContent className="pt-2">
            {system.isLoading ? (
              <div className="grid gap-4 sm:grid-cols-3">
                {[0, 1, 2].map((index) => (
                  <Skeleton key={index} className="h-[132px] w-full" />
                ))}
              </div>
            ) : sys ? (
              <div className="grid gap-4 sm:grid-cols-3">
                <RingGauge
                  value={sys.cpu.percent}
                  label="CPU"
                  caption={`${sys.cpu.coresPhysical} 核 / ${sys.cpu.coresLogical} 线程`}
                  tone={toneFor(sys.cpu.percent)}
                  size={112}
                />
                <RingGauge
                  value={sys.memory.percent}
                  label="内存"
                  caption={`${formatBytes(sys.memory.used)} / ${formatBytes(sys.memory.total)}`}
                  tone={toneFor(sys.memory.percent)}
                  size={112}
                />
                <RingGauge
                  value={disk?.percent ?? 0}
                  label="系统盘"
                  caption={disk ? `${formatBytes(disk.used)} / ${formatBytes(disk.total)}` : '未获取到磁盘'}
                  tone={toneFor(disk?.percent ?? 0)}
                  size={112}
                />
              </div>
            ) : (
              <EmptyState icon={Cpu} title="系统信息不可用" description="后端接口 /api/dashboard/system 没有返回数据。" />
            )}

            {sys && (
              <>
                <div className="mt-4 space-y-2 border-t pt-3">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>每核心负载</span>
                    <span className="tabular-nums">{sys.cpu.perCore.length} 线程</span>
                  </div>
                  <div className="flex gap-1">
                    {sys.cpu.perCore.map((value, index) => (
                      <div
                        key={index}
                        title={`核心 ${index + 1}：${value}%`}
                        className="h-6 flex-1 rounded-[3px]"
                        style={{
                          background:
                            value >= 90
                              ? 'var(--destructive)'
                              : value >= 70
                                ? 'var(--warning)'
                                : 'var(--success)',
                          opacity: 0.25 + Math.min(value, 100) * 0.0075,
                        }}
                      />
                    ))}
                  </div>
                </div>
                <div className="mt-3 grid gap-2 border-t pt-3 text-xs text-muted-foreground sm:grid-cols-3">
                  <span className="flex items-center gap-1.5">
                    <Cpu className="size-3.5" /> {sys.cpu.freqMhz} MHz
                  </span>
                  <span className="flex items-center gap-1.5">
                    <MemoryStick className="size-3.5" /> 交换分区 {sys.swap.percent.toFixed(0)}%
                  </span>
                  <span className="flex items-center gap-1.5">
                    <HardDrive className="size-3.5" /> {sys.disks.length} 块磁盘
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>最近运行</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 pt-1">
            {overview.isLoading && <Skeleton className="h-40 w-full" />}
            {overview.data?.recentHistories?.slice(0, 6).map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-2 border-b py-2 last:border-0">
                <div className="min-w-0">
                  <p className="truncate text-sm">{item.pipelineTitle}</p>
                  <p className="text-xs text-muted-foreground">{item.startTime}</p>
                </div>
                <StatusBadge status={item.status} />
              </div>
            ))}
            {!overview.isLoading && !overview.data?.recentHistories?.length && (
              <p className="py-8 text-center text-sm text-muted-foreground">还没有运行记录</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>即将到期</CardTitle>
          <Button variant="ghost" size="xs" asChild>
            <Link to="/certs">查看证书库</Link>
          </Button>
        </CardHeader>
        <CardContent className="pt-2">
          {overview.data?.expiringCerts?.length ? (
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {overview.data.expiringCerts.map((cert) => (
                <div key={cert.id} className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{cert.domains?.join(', ') || '—'}</p>
                    <p className="text-xs text-muted-foreground">到期 {cert.notAfter}</p>
                  </div>
                  <Badge variant={daysTone(cert.daysLeft)}>{cert.daysLeft} 天</Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-muted-foreground">30 天内没有证书到期</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
