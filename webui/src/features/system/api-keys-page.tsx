import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { createApiKey, deleteApiKey, fetchApiKeys } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

type ApiKeyRow = Record<string, unknown>

export function ApiKeysPage() {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [created, setCreated] = useState<{ keyId: string; secret: string } | null>(null)
  const [keyToDelete, setKeyToDelete] = useState<ApiKeyRow | null>(null)
  const queryClient = useQueryClient()

  const list = useQuery({ queryKey: ['api-keys'], queryFn: fetchApiKeys })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['api-keys'] })

  const create = useMutation({
    mutationFn: () => createApiKey(name.trim()),
    onSuccess: (data) => {
      setCreated({ keyId: data.keyId, secret: data.secret })
      setName('')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteApiKey(id),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const records = list.data ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="开放接口"
        description="给脚本或 CI 用的 Key，只显示一次，丢了就重建"
        actions={
          <Button size="sm" onClick={() => { setCreated(null); setOpen(true) }}>
            <Plus />
            新建 Key
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {list.isLoading ? (
          <TableSkeleton rows={3} />
        ) : records.length === 0 ? (
          <EmptyState icon={KeyRound} title="还没有 API Key" description="创建后可以用它触发流水线，不用登录网页。" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>Key ID</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead>最近使用</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(records as ApiKeyRow[]).map((item) => (
                <TableRow key={String(item.id)}>
                  <TableCell className="font-medium">{String(item.name ?? '—')}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {String(item.keyId ?? '—')}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{String(item.createTime ?? '—')}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{String(item.lastUsedTime ?? '从未')}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive hover:bg-destructive/10"
                      onClick={() => setKeyToDelete(item)}
                    >
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>新建 API Key</DialogTitle>
            <p className="text-sm text-muted-foreground">Key 只在创建后显示一次，请立刻保存。</p>
          </DialogHeader>
          <DialogBody className="space-y-3">
            {created ? (
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label>Key ID</Label>
                  <code className="block break-all rounded-md border bg-muted px-3 py-2 font-mono text-xs">{created.keyId}</code>
                </div>
                <div className="space-y-1">
                  <Label>Secret</Label>
                  <code className="block break-all rounded-md border bg-muted px-3 py-2 font-mono text-xs">{created.secret}</code>
                </div>
                <p className="text-xs text-muted-foreground">
                  Secret 只在这里出现一次，关掉就看不到了。调用时放在请求头 <code>X-Api-Key</code> 和 <code>X-Api-Secret</code> 里。
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label>名称</Label>
                <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：CI 发布脚本" />
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              关闭
            </Button>
            {!created && (
              <Button size="sm" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
                创建
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={!!keyToDelete} onOpenChange={(next) => !next && setKeyToDelete(null)}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>删除 API Key</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <p className="text-sm leading-relaxed">
              删除「{String(keyToDelete?.name ?? '')}」后，使用这个 Key 调用开放接口的脚本会立刻收到 401，无法恢复。
            </p>
            <p className="mt-2 text-xs text-muted-foreground">如果只是临时停用，建议先替换脚本里的 Key 再删。</p>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setKeyToDelete(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={remove.isPending}
              onClick={() => {
                if (keyToDelete) remove.mutate(Number(keyToDelete.id))
                setKeyToDelete(null)
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
