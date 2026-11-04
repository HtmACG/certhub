import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2, Network, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  createCname,
  createSubdomain,
  deleteCname,
  deleteSubdomain,
  fetchAccessList,
  fetchCnameList,
  fetchSubdomainList,
  syncCname,
  verifyCname,
} from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label, Select, Textarea } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Tabs } from '@/components/ui/tabs'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

type TabKey = 'cname' | 'subdomain'

export function DnsPage() {
  const [tab, setTab] = useState<TabKey>('cname')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()

  const access = useQuery({ queryKey: ['access-options'], queryFn: () => fetchAccessList({ current: 1, size: 200 }) })
  const cname = useQuery({ queryKey: ['cname', page], queryFn: () => fetchCnameList({ current: page, size: 10 }) })
  const subdomain = useQuery({
    queryKey: ['subdomain', page],
    queryFn: () => fetchSubdomainList({ current: page, size: 10 }),
    enabled: tab === 'subdomain',
  })

  const accessOptions = access.data?.records ?? []
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['cname'] })
    void queryClient.invalidateQueries({ queryKey: ['subdomain'] })
  }

  const create = useMutation<unknown, Error, void>({
    mutationFn: () =>
      tab === 'cname'
        ? createCname({
            domain: form.domain?.trim(),
            accessId: Number(form.accessId),
            recordValue: form.recordValue?.trim(),
            remark: form.remark?.trim(),
          })
        : createSubdomain({ domain: form.domain?.trim(), accessId: Number(form.accessId), remark: form.remark?.trim() }),
    onSuccess: () => {
      toast.success(tab === 'cname' ? 'CNAME 记录已添加' : '子域名托管已添加')
      setOpen(false)
      setForm({})
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const removeCname = useMutation({
    mutationFn: ({ id, remote }: { id: number; remote: boolean }) => deleteCname(id, remote),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const removeSubdomain = useMutation({
    mutationFn: (id: number) => deleteSubdomain(id),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const sync = useMutation({
    mutationFn: (id: number) => syncCname(id),
    onSuccess: () => {
      toast.success('已同步到 DNS 服务商')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const verify = useMutation({
    mutationFn: (id: number) => verifyCname(id),
    onSuccess: (data) => (data.success ? toast.success('记录已生效') : toast.error(data.message || '记录还没生效')),
    onError: (error: Error) => toast.error(error.message),
  })

  const cnameRecords = cname.data?.records ?? []
  const subdomainRecords = subdomain.data?.records ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="DNS 记录"
        description="CNAME 手动登记，证书申请写入的验证记录只读留痕"
        actions={
          <>
            <Tabs
              value={tab}
              onChange={(next) => {
                setTab(next)
                setPage(1)
              }}
              items={[
                { value: 'cname', label: 'CNAME 记录' },
                { value: 'subdomain', label: '子域名托管' },
              ]}
            />
            <Button size="sm" onClick={() => { setForm({}); setOpen(true) }}>
              <Plus />
              {tab === 'cname' ? '添加记录' : '添加托管'}
            </Button>
          </>
        }
      />

      <Card className="overflow-hidden">
        {tab === 'cname' ? (
          cname.isLoading ? (
            <TableSkeleton rows={6} />
          ) : cnameRecords.length === 0 ? (
            <EmptyState icon={Link2} title="还没有 CNAME 记录" description="把手动维护的 CNAME 登记进来，可以定时校验是否生效。" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>记录名</TableHead>
                  <TableHead>目标值</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>校验时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cnameRecords.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="max-w-[260px] truncate font-medium">{item.hostRecord || item.domain}</TableCell>
                    <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">{item.recordValue}</TableCell>
                    <TableCell>
                      <Badge variant={item.source === 'manual' ? 'outline' : 'muted'}>
                        {item.source === 'manual' ? '手动' : item.source === 'acme' ? '证书申请' : '云端'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={item.status === 'valid' ? 'success' : item.status === 'error' ? 'destructive' : 'muted'}>
                        {item.status === 'valid' ? '已生效' : item.status === 'synced' ? '已同步' : item.status === 'error' ? '异常' : '待同步'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{item.verifyTime || '—'}</TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        {item.source === 'manual' && (
                          <>
                            <Button variant="ghost" size="xs" onClick={() => sync.mutate(item.id)}>
                              <RefreshCw />
                              同步
                            </Button>
                            <Button variant="ghost" size="xs" onClick={() => verify.mutate(item.id)}>
                              校验
                            </Button>
                          </>
                        )}
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-destructive hover:bg-destructive/10"
                          onClick={() => {
                            if (confirm('删除这条记录？勾选「同时删除服务商记录」会调用 DNS API。')) removeCname.mutate({ id: item.id, remote: false })
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
          )
        ) : subdomain.isLoading ? (
          <TableSkeleton rows={4} />
        ) : subdomainRecords.length === 0 ? (
          <EmptyState icon={Network} title="还没有子域名托管" description="把子域名交给主账号托管后，申请证书就能自动写记录。" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>子域名</TableHead>
                <TableHead>授权</TableHead>
                <TableHead className="text-center">启用</TableHead>
                <TableHead>备注</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {subdomainRecords.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-medium">{item.domain}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {accessOptions.find((option) => option.id === item.accessId)?.name || `#${item.accessId}`}
                  </TableCell>
                  <TableCell className="text-center">
                    <div className="flex justify-center">
                      <Switch checked={!item.disabled} onChange={() => undefined} disabled label="启用" />
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.remark || '—'}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive hover:bg-destructive/10"
                      onClick={() => {
                        if (confirm(`删除子域名托管「${item.domain}」？`)) removeSubdomain.mutate(item.id)
                      }}
                    >
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {!!(tab === 'cname' ? cname.data?.total : subdomain.data?.total) && (
          <Pagination
            current={page}
            size={10}
            total={(tab === 'cname' ? cname.data?.total : subdomain.data?.total) ?? 0}
            onChange={setPage}
          />
        )}
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tab === 'cname' ? '添加 CNAME 记录' : '添加子域名托管'}</DialogTitle>
            <p className="text-sm text-muted-foreground">记录会先用这里选的 DNS 授权写入服务商。</p>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label>{tab === 'cname' ? '域名' : '子域名'}</Label>
              <Input
                value={form.domain || ''}
                onChange={(event) => setForm((prev) => ({ ...prev, domain: event.target.value }))}
                placeholder="foo.example.com"
              />
            </div>
            {tab === 'cname' && (
              <div className="space-y-1.5">
                <Label>目标值</Label>
                <Input
                  value={form.recordValue || ''}
                  onChange={(event) => setForm((prev) => ({ ...prev, recordValue: event.target.value }))}
                  placeholder="target.example.net"
                />
              </div>
            )}
            <div className="space-y-1.5">
              <Label>DNS 授权</Label>
              <Select value={form.accessId || ''} onChange={(event) => setForm((prev) => ({ ...prev, accessId: event.target.value }))}>
                <option value="">请选择</option>
                {accessOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>备注</Label>
              <Textarea value={form.remark || ''} onChange={(event) => setForm((prev) => ({ ...prev, remark: event.target.value }))} />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button size="sm" disabled={!form.domain || !form.accessId || create.isPending} onClick={() => create.mutate()}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
