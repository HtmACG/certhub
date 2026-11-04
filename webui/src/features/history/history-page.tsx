import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileClock, RefreshCw, ScrollText } from 'lucide-react'
import { fetchHistoryDetail, fetchHistoryList } from '@/lib/api'
import type { HistoryItem } from '@/lib/types'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Select } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/status'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'
import { Dialog, DialogBody, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { LogTerminal } from '@/components/log-terminal'
import { duration } from '@/lib/format'

function logsOf(payload: unknown): string[] {
  if (!payload || typeof payload !== 'object') return []
  const record = payload as Record<string, unknown>
  const raw = record.log ?? record.logs
  if (Array.isArray(raw)) return raw.map((line) => String(line))
  if (typeof raw === 'string') return raw.split('\n')
  return []
}

export function HistoryPage() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('all')
  const [current, setCurrent] = useState<HistoryItem | null>(null)

  const list = useQuery({
    queryKey: ['history', page, status],
    queryFn: () => fetchHistoryList({ current: page, size: 12, status: status === 'all' ? undefined : status }),
  })

  const detail = useQuery({
    queryKey: ['history-detail', current?.id],
    queryFn: () => fetchHistoryDetail(current!.id),
    enabled: !!current,
  })

  const records = list.data?.records ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="执行历史"
        description="每次运行都会留一条记录，失败的那次可以直接看日志"
        actions={
          <Button variant="outline" size="sm" onClick={() => list.refetch()} disabled={list.isFetching}>
            <RefreshCw className={list.isFetching ? 'animate-spin' : ''} />
            刷新
          </Button>
        }
      />

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
          <Select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }} className="h-8 w-32 text-sm">
            <option value="all">全部状态</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
            <option value="running">运行中</option>
          </Select>
          <span className="ml-auto text-xs text-muted-foreground">共 {list.data?.total ?? 0} 条</span>
        </div>

        {list.isLoading ? (
          <TableSkeleton rows={8} />
        ) : records.length === 0 ? (
          <EmptyState icon={FileClock} title="还没有运行记录" description="流水线跑过一次之后，这里会出现结果。" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>流水线</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>触发方式</TableHead>
                <TableHead>开始时间</TableHead>
                <TableHead className="text-right">耗时</TableHead>
                <TableHead className="text-right">任务数</TableHead>
                <TableHead className="text-right">日志</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="max-w-[360px] truncate font-medium">{item.pipelineTitle}</TableCell>
                  <TableCell>
                    <StatusBadge status={item.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.triggerType === 'timer' ? '定时' : item.triggerType === 'manual' ? '手动' : item.triggerType}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.startTime}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{duration(item.duration)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{item.taskCount}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="xs" onClick={() => setCurrent(item)}>
                      <ScrollText />
                      查看
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {!!list.data?.total && <Pagination current={page} size={12} total={list.data.total} onChange={setPage} />}
      </Card>

      <Dialog open={!!current} onOpenChange={(open) => !open && setCurrent(null)}>
        <DialogContent size="xl">
          <DialogHeader>
            <DialogTitle>{current?.pipelineTitle}</DialogTitle>
            <p className="text-sm text-muted-foreground">
              {current?.startTime} · {duration(current?.duration)}
            </p>
          </DialogHeader>
          <DialogBody>
            {detail.isLoading ? (
              <div className="py-10 text-center text-sm text-muted-foreground">读取日志…</div>
            ) : (
              <LogTerminal lines={logsOf(detail.data)} title="执行日志" />
            )}
          </DialogBody>
        </DialogContent>
      </Dialog>
    </div>
  )
}
