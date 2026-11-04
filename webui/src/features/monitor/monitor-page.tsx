import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { checkSite, createSite, deleteSite, fetchSiteList } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'
import { StatusBadge, daysTone } from '@/components/status'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export function MonitorPage() {
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [port, setPort] = useState('443')
  const queryClient = useQueryClient()

  const list = useQuery({ queryKey: ['sites', page], queryFn: () => fetchSiteList({ current: page, size: 12 }) })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['sites'] })

  const create = useMutation({
    mutationFn: () => createSite({ url: url.trim(), port: Number(port) || 443, enabled: true, notifyEnabled: true }),
    onSuccess: () => {
      toast.success('已添加站点')
      setOpen(false)
      setUrl('')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteSite(id),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const check = useMutation({
    mutationFn: (id: number) => checkSite(id),
    onSuccess: () => {
      toast.success('巡检完成')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const records = list.data?.records ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="站点监控"
        description="定时读对端证书的有效期，快到期时提前提醒"
        actions={
          <Button size="sm" onClick={() => setOpen(true)}>
            <Plus />
            添加站点
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {list.isLoading ? (
          <TableSkeleton rows={6} />
        ) : records.length === 0 ? (
          <EmptyState icon={Activity} title="还没有监控站点" description="加一个 https 地址，就能看到对端证书什么时候到期。" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>站点</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>签发者</TableHead>
                <TableHead>到期时间</TableHead>
                <TableHead className="text-center">剩余</TableHead>
                <TableHead>最近巡检</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="max-w-[280px]">
                    <p className="truncate font-medium">{item.url}</p>
                    <p className="text-xs text-muted-foreground">端口 {item.port}</p>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={item.status} />
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">{item.issuer || '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.expireTime || '—'}</TableCell>
                  <TableCell className="text-center">
                    {item.daysLeft == null ? <span className="text-xs text-muted-foreground">—</span> : <Badge variant={daysTone(item.daysLeft)}>{item.daysLeft} 天</Badge>}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.lastCheckTime || '—'}</TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="xs" onClick={() => check.mutate(item.id)} disabled={check.isPending}>
                        <RefreshCw />
                        巡检
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="text-destructive hover:bg-destructive/10"
                        onClick={() => {
                          if (confirm(`删除监控「${item.url}」？`)) remove.mutate(item.id)
                        }}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {!!list.data?.total && <Pagination current={page} size={12} total={list.data.total} onChange={setPage} />}
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>添加监控站点</DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label>地址</Label>
              <Input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" />
            </div>
            <div className="space-y-1.5">
              <Label>端口</Label>
              <Input value={port} onChange={(event) => setPort(event.target.value)} inputMode="numeric" />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button size="sm" disabled={!url.trim() || create.isPending} onClick={() => create.mutate()}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
