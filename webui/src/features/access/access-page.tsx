import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, PlugZap, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  createAccess,
  deleteAccess,
  fetchAccessList,
  fetchPluginMeta,
  testAccess,
  updateAccess,
} from '@/lib/api'
import type { AccessItem } from '@/lib/types'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label, Textarea } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { SchemaFields } from '@/components/schema-form'
import { VendorLogo } from '@/components/vendor-logo'

function TypePicker({
  value,
  onChange,
  grouped,
  categories,
  types,
  disabled,
}: {
  value: string
  onChange: (type: string) => void
  grouped: Map<string, { key: string; name: string }[]>
  categories: { key: string; name: string }[]
  types: Record<string, { name: string; logoFile?: string; color?: string }>
  disabled?: boolean
}) {
  if (disabled) return null
  return (
    <div className="space-y-3">
      <Label>授权类型</Label>
      <div className="scrollbar-thin max-h-[260px] space-y-3 overflow-y-auto rounded-lg border p-3">
        {Array.from(grouped.entries()).map(([category, items]) => (
          <div key={category} className="space-y-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {categories.find((item) => item.key === category)?.name || category}
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {items.map((item) => {
                const meta = types[item.key]
                const active = value === item.key
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => onChange(item.key)}
                    className={
                      'flex items-center gap-2 rounded-md border px-2 py-1.5 text-left text-xs transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ' +
                      (active ? 'border-foreground/50 bg-accent font-medium' : 'hover:bg-accent/60')
                    }
                  >
                    <VendorLogo logoFile={meta?.logoFile} name={item.name} color={meta?.color} size={22} />
                    <span className="truncate">{item.name}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function AccessPage() {
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<AccessItem | null>(null)
  const [type, setType] = useState('')
  const [name, setName] = useState('')
  const [remark, setRemark] = useState('')
  const [config, setConfig] = useState<Record<string, unknown>>({})
  const queryClient = useQueryClient()

  const list = useQuery({ queryKey: ['access', page], queryFn: () => fetchAccessList({ current: page, size: 12 }) })
  const meta = useQuery({ queryKey: ['plugin-meta'], queryFn: fetchPluginMeta, staleTime: 10 * 60_000 })

  const accessTypes = meta.data?.accessTypes ?? {}
  const categories = meta.data?.accessCategories ?? []
  const currentType = type ? accessTypes[type] : undefined

  const grouped = useMemo(() => {
    const map = new Map<string, { key: string; name: string }[]>()
    Object.entries(accessTypes).forEach(([key, value]) => {
      const category = value.category || 'other'
      map.set(category, [...(map.get(category) ?? []), { key, name: value.name }])
    })
    return map
  }, [accessTypes])

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['access'] })

  const reset = () => {
    setType('')
    setName('')
    setRemark('')
    setConfig({})
    setEditing(null)
  }

  const save = useMutation({
    mutationFn: () => {
      const body = {
        type,
        name: name.trim(),
        remark: remark.trim(),
        config,
        category: accessTypes[type]?.category || 'dns',
      }
      return editing ? updateAccess(editing.id, body) : createAccess(body)
    },
    onSuccess: () => {
      toast.success('已保存授权')
      setOpen(false)
      reset()
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteAccess(id),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const probe = useMutation({
    mutationFn: (id: number) => testAccess(id),
    onSuccess: (data) => {
      if (data.success) toast.success(data.message || '连通性正常')
      else toast.error(data.message || '连通性测试失败')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const records = list.data?.records ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="授权管理"
        description="DNS、面板、主机和云厂商的凭据都放在这里，流水线里只选不填"
        actions={
          <Button size="sm" onClick={() => { reset(); setOpen(true) }}>
            <Plus />
            新建授权
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {list.isLoading ? (
          <TableSkeleton rows={6} />
        ) : records.length === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="还没有授权"
            description="加一条 DNS 授权后，申请证书时就能自动写验证记录。"
            action={
              <Button size="sm" onClick={() => { reset(); setOpen(true) }}>
                <Plus />
                新建授权
              </Button>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>分类</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <VendorLogo
                        logoFile={accessTypes[item.type]?.logoFile}
                        name={accessTypes[item.type]?.name || item.typeName || item.type}
                        color={accessTypes[item.type]?.color}
                        size={30}
                      />
                      <div className="min-w-0">
                        <p className="truncate font-medium">{item.name}</p>
                        {(() => {
                          const typeLabel = accessTypes[item.type]?.name || item.typeName || item.type
                          const extra = [typeLabel !== item.name ? typeLabel : null, item.remark || null]
                            .filter(Boolean)
                            .join(' · ')
                          return extra ? <p className="truncate text-xs text-muted-foreground">{extra}</p> : null
                        })()}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {categories.find((category) => category.key === item.category)?.name || item.category}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.createTime}</TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="xs" onClick={() => probe.mutate(item.id)} disabled={probe.isPending}>
                        <PlugZap />
                        测试
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="编辑"
                        onClick={() => {
                          setEditing(item)
                          setType(item.type)
                          setName(item.name)
                          setRemark(item.remark)
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
                        title="删除"
                        onClick={() => {
                          if (confirm(`删除授权「${item.name}」？正在使用它的流水线会失败。`)) remove.mutate(item.id)
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
            <DialogTitle>{editing ? `编辑授权 · ${editing.name}` : '新建授权'}</DialogTitle>
            <p className="text-sm text-muted-foreground">字段由后端插件声明，密码框留空表示不改动已存的值。</p>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <TypePicker
              value={type}
              onChange={(next) => {
                setType(next)
                setConfig({})
              }}
              grouped={grouped}
              categories={categories}
              types={accessTypes}
              disabled={!!editing}
            />
            {editing && (
              <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
                <VendorLogo
                  logoFile={accessTypes[type]?.logoFile}
                  name={accessTypes[type]?.name || type}
                  color={accessTypes[type]?.color}
                  size={24}
                />
                <span className="text-sm">{accessTypes[type]?.name || type}</span>
                <span className="ml-auto text-xs text-muted-foreground">类型创建后不能改</span>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>名称</Label>
              <Input
                autoFocus
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="例如：阿里云 DNS（主账号）"
              />
            </div>
            <div className="space-y-1.5">
              <Label>备注</Label>
              <Textarea value={remark} onChange={(event) => setRemark(event.target.value)} placeholder="可选" />
            </div>
            {currentType ? (
              <div className="border-t pt-4">
                <SchemaFields
                  fields={currentType.inputs}
                  values={config}
                  onChange={(key, value) => setConfig((prev) => ({ ...prev, [key]: value }))}
                />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">选择类型后会出现对应的配置字段。</p>
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
