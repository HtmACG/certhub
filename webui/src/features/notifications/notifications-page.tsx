import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Pencil, Send, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  createNotification,
  deleteNotification,
  fetchNotificationList,
  fetchPluginMeta,
  testNotification,
  updateNotification,
} from '@/lib/api'
import type { NotificationItem } from '@/lib/types'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label, Select } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { SchemaFields } from '@/components/schema-form'

export function NotificationsPage() {
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<NotificationItem | null>(null)
  const [type, setType] = useState('')
  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [config, setConfig] = useState<Record<string, unknown>>({})
  const queryClient = useQueryClient()

  const list = useQuery({ queryKey: ['notifications', page], queryFn: () => fetchNotificationList({ current: page, size: 12 }) })
  const meta = useQuery({ queryKey: ['plugin-meta'], queryFn: fetchPluginMeta, staleTime: 10 * 60_000 })
  const notifyTypes = meta.data?.notifyTypes ?? {}
  const currentType = type ? notifyTypes[type] : undefined

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['notifications'] })

  const reset = () => {
    setEditing(null)
    setType('')
    setName('')
    setEnabled(true)
    setConfig({})
  }

  const save = useMutation({
    mutationFn: () => {
      const body = { type, name: name.trim(), enabled, config }
      return editing ? updateNotification(editing.id, body) : createNotification(body)
    },
    onSuccess: () => {
      toast.success('已保存渠道')
      setOpen(false)
      reset()
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteNotification(id),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const probe = useMutation({
    mutationFn: (id: number) => testNotification(id),
    onSuccess: (data) => (data.success ? toast.success(data.message || '已发送测试消息') : toast.error(data.message || '发送失败')),
    onError: (error: Error) => toast.error(error.message),
  })

  const records = list.data?.records ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="通知渠道"
        description="证书签发、续期失败、站点异常都会走这里配置的渠道"
        actions={
          <Button size="sm" onClick={() => { reset(); setOpen(true) }}>
            <Plus />
            新建渠道
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {list.isLoading ? (
          <TableSkeleton rows={5} />
        ) : records.length === 0 ? (
          <EmptyState
            icon={Bell}
            title="还没有通知渠道"
            description="先加一个邮箱或 Webhook，出问题时才知道。"
            action={
              <Button size="sm" onClick={() => { reset(); setOpen(true) }}>
                <Plus />
                新建渠道
              </Button>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>类型</TableHead>
                <TableHead className="text-center">启用</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <p className="font-medium">{item.name}</p>
                    {item.isDefault && <Badge variant="muted">默认</Badge>}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.typeName || notifyTypes[item.type]?.name || item.type}</TableCell>
                  <TableCell className="text-center">
                    <div className="flex justify-center">
                      <Switch
                        checked={item.enabled}
                        onChange={() => {
                          void updateNotification(item.id, { ...item, enabled: !item.enabled }).then(() => invalidate())
                        }}
                        label="启用"
                      />
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.createTime}</TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="xs" onClick={() => probe.mutate(item.id)}>
                        <Send />
                        测试
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => {
                          setEditing(item)
                          setType(item.type)
                          setName(item.name)
                          setEnabled(item.enabled)
                          setConfig({ ...item.config })
                          setOpen(true)
                        }}
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="text-destructive hover:bg-destructive/10"
                        onClick={() => {
                          if (confirm(`删除渠道「${item.name}」？`)) remove.mutate(item.id)
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

      <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) reset() }}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>{editing ? `编辑渠道 · ${editing.name}` : '新建通知渠道'}</DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>渠道类型</Label>
                <Select value={type} disabled={!!editing} onChange={(event) => { setType(event.target.value); setConfig({}) }}>
                  <option value="">请选择</option>
                  {Object.entries(notifyTypes).map(([key, value]) => (
                    <option key={key} value={key}>
                      {value.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>名称</Label>
                <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：运维群机器人" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={enabled} onChange={setEnabled} label="启用" />
              <span className="text-sm text-muted-foreground">启用后参与通知</span>
            </div>
            {currentType && (
              <div className="border-t pt-4">
                <SchemaFields
                  fields={currentType.inputs}
                  values={config}
                  onChange={(key, value) => setConfig((prev) => ({ ...prev, [key]: value }))}
                />
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button size="sm" disabled={!type || !name.trim() || save.isPending} onClick={() => save.mutate()}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
