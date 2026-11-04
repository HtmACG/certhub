import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ScrollText } from 'lucide-react'
import { fetchAuditList } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'

type AuditRow = Record<string, unknown>

const pick = (row: AuditRow, keys: string[], fallback = '—') => {
  for (const key of keys) {
    const value = row[key]
    if (value !== undefined && value !== null && value !== '') return String(value)
  }
  return fallback
}

export function AuditPage() {
  const [page, setPage] = useState(1)
  const list = useQuery({ queryKey: ['audit', page], queryFn: () => fetchAuditList({ current: page, size: 15 }) })
  const records = (list.data?.records ?? []) as AuditRow[]

  return (
    <div className="space-y-5">
      <PageHeader title="审计日志" description="登录、改设置、动流水线都会留一条记录" />

      <Card className="overflow-hidden">
        {list.isLoading ? (
          <TableSkeleton rows={8} />
        ) : records.length === 0 ? (
          <EmptyState icon={ScrollText} title="还没有审计记录" description="关键操作发生后会自动写入。" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>用户</TableHead>
                <TableHead>动作</TableHead>
                <TableHead>对象</TableHead>
                <TableHead>IP</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((row, index) => (
                <TableRow key={String(row.id ?? index)}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {pick(row, ['createTime', 'time', 'createdAt'])}
                  </TableCell>
                  <TableCell className="font-medium">{pick(row, ['userName', 'username', 'user'])}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{pick(row, ['action', 'event'])}</Badge>
                  </TableCell>
                  <TableCell className="max-w-[360px] truncate text-xs text-muted-foreground">
                    {pick(row, ['target', 'detail', 'message', 'path'])}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{pick(row, ['ip', 'clientIp'])}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {!!list.data?.total && <Pagination current={page} size={15} total={list.data.total} onChange={setPage} />}
      </Card>
    </div>
  )
}
