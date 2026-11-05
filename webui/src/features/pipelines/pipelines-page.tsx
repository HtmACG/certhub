import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Clock, Copy, Pencil, Play, Plus, Power, PowerOff, Search, Trash2, Workflow, X } from 'lucide-react'
import { toast } from 'sonner'
import {
  batchPipeline,
  copyPipeline,
  createFromTemplate,
  deletePipeline,
  fetchNotificationList,
  fetchPipelineList,
  fetchTemplates,
  runPipeline,
  togglePipeline,
} from '@/lib/api'
import type { PipelineItem } from '@/lib/types'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Input, Label, Select } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { StatusBadge, KindBadges, daysTone } from '@/components/status'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { relativeTime } from '@/lib/format'

const BATCH_LABEL: Record<string, string> = {
  run: '批量运行',
  enable: '批量启用',
  disable: '批量停用',
  delete: '批量删除',
  cron: '批量设置定时',
  notify: '批量设置通知',
}

function daysLeftOf(iso?: string) {
  if (!iso) return null
  const time = new Date(iso.replace(' ', 'T')).getTime()
  if (Number.isNaN(time)) return null
  return Math.ceil((time - Date.now()) / 86400000)
}

export function PipelinesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [enabled, setEnabled] = useState('all')
  const [templateOpen, setTemplateOpen] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [cronOpen, setCronOpen] = useState(false)
  const [cronDraft, setCronDraft] = useState('0 3 * * *')
  const [notifyOpen, setNotifyOpen] = useState(false)
  const [notifyId, setNotifyId] = useState('')

  const list = useQuery({
    queryKey: ['pipelines', page, keyword, enabled],
    queryFn: () =>
      fetchPipelineList({
        current: page,
        size: 10,
        keyword: keyword || undefined,
        disabled: enabled === 'all' ? undefined : enabled === 'off',
      }),
  })

  const templates = useQuery({ queryKey: ['templates'], queryFn: fetchTemplates, enabled: templateOpen })

  const notifications = useQuery({
    queryKey: ['notification-options'],
    queryFn: () => fetchNotificationList({ current: 1, size: 100 }),
    enabled: notifyOpen,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['pipelines'] })

  const run = useMutation({
    mutationFn: (id: number) => runPipeline(id),
    onSuccess: (data, id) => {
      toast.success('已开始运行')
      navigate(`/pipelines/${id}?history=${data.historyId}`)
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const toggle = useMutation({
    mutationFn: (item: PipelineItem) => togglePipeline(item.id),
    onSuccess: () => {
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const copy = useMutation({
    mutationFn: (id: number) => copyPipeline(id),
    onSuccess: () => {
      toast.success('已复制流水线')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deletePipeline(id),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const batch = useMutation({
    mutationFn: (body: { action: string; ids: number[]; cron?: string; notificationId?: number }) =>
      batchPipeline(body),
    onSuccess: (data, body) => {
      const failed = (data.failed || []) as { msg?: string }[]
      const label = BATCH_LABEL[body.action] || '操作'
      if (failed.length) {
        toast.error(
          `${label}：成功 ${data.success.length} 条，失败 ${failed.length} 条${failed[0]?.msg ? `（${failed[0].msg}）` : ''}`,
        )
      } else {
        toast.success(`${label}：${data.success.length} 条已处理`)
      }
      setSelected([])
      setCronOpen(false)
      setNotifyOpen(false)
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const create = useMutation({
    mutationFn: (templateId: string) => createFromTemplate({ templateId }),
    onSuccess: (data) => {
      toast.success('已按模板创建')
      setTemplateOpen(false)
      navigate(`/pipelines/${data.id}`)
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const records = list.data?.records ?? []
  const pageIds = records.map((item) => item.id)
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selected.includes(id))
  const toggleOne = (id: number) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]))
  const toggleAll = () => setSelected(allSelected ? [] : pageIds)

  return (
    <div className="space-y-5">
      <PageHeader
        title="证书流水线"
        description="每个阶段按顺序执行；阶段内任务可以单独停用"
        actions={
          <Button size="sm" onClick={() => setTemplateOpen(true)}>
            <Plus />
            新建流水线
          </Button>
        }
      />

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={keyword}
              onChange={(event) => {
                setKeyword(event.target.value)
                setPage(1)
              }}
              placeholder="搜索标题或备注"
              className="h-8 pl-8 text-sm"
            />
          </div>
          <Select
            value={enabled}
            onChange={(event) => {
              setEnabled(event.target.value)
              setPage(1)
            }}
            className="h-8 w-32 text-sm"
          >
            <option value="all">全部状态</option>
            <option value="on">已启用</option>
            <option value="off">已停用</option>
          </Select>
          {selected.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 rounded-md border bg-muted/40 px-2 py-1">
              <span className="mr-1 text-xs font-medium">已选 {selected.length} 条</span>
              <Button
                variant="ghost"
                size="icon-sm"
                title="运行"
                disabled={batch.isPending}
                onClick={() => batch.mutate({ action: 'run', ids: selected })}
              >
                <Play />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                title="启用"
                disabled={batch.isPending}
                onClick={() => batch.mutate({ action: 'enable', ids: selected })}
              >
                <Power />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                title="停用"
                disabled={batch.isPending}
                onClick={() => batch.mutate({ action: 'disable', ids: selected })}
              >
                <PowerOff />
              </Button>
              <Button variant="ghost" size="icon-sm" title="设置定时" onClick={() => setCronOpen(true)}>
                <Clock />
              </Button>
              <Button variant="ghost" size="icon-sm" title="设置通知" onClick={() => setNotifyOpen(true)}>
                <Bell />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                title="删除"
                className="text-destructive hover:bg-destructive/10"
                disabled={batch.isPending}
                onClick={() => {
                  if (confirm(`批量删除 ${selected.length} 条流水线？执行历史也会一起删掉。`)) {
                    batch.mutate({ action: 'delete', ids: selected })
                  }
                }}
              >
                <Trash2 />
              </Button>
              <Button variant="ghost" size="icon-sm" title="取消选择" onClick={() => setSelected([])}>
                <X />
              </Button>
            </div>
          )}
          <span className="ml-auto text-xs text-muted-foreground">共 {list.data?.total ?? 0} 条</span>
        </div>

        {list.isLoading ? (
          <TableSkeleton rows={6} />
        ) : records.length === 0 ? (
          <EmptyState
            icon={Workflow}
            title="还没有流水线"
            description="从模板开始最快：选一个签发方式，再加部署目标。"
            action={
              <Button size="sm" onClick={() => setTemplateOpen(true)}>
                <Plus />
                从模板创建
              </Button>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <input
                    type="checkbox"
                    className="size-3.5 cursor-pointer align-middle accent-primary"
                    checked={allSelected}
                    onChange={toggleAll}
                    aria-label="选择当前页"
                  />
                </TableHead>
                <TableHead>名称</TableHead>
                <TableHead>分类</TableHead>
                <TableHead className="text-center">阶段 / 步骤</TableHead>
                <TableHead>证书</TableHead>
                <TableHead>最近运行</TableHead>
                <TableHead>触发方式</TableHead>
                <TableHead className="text-center">启用</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((item) => {
                const certDays = daysLeftOf(item.certExpiresTime)
                return (
                <TableRow key={item.id}>
                  <TableCell className="w-8">
                    <input
                      type="checkbox"
                      className="size-3.5 cursor-pointer align-middle accent-primary"
                      checked={selected.includes(item.id)}
                      onChange={() => toggleOne(item.id)}
                      aria-label={`选择 ${item.title}`}
                    />
                  </TableCell>
                  <TableCell className="max-w-[320px]">
                    <Link to={`/pipelines/${item.id}`} className="block truncate font-medium hover:underline">
                      {item.title}
                    </Link>
                    <p className="truncate text-xs text-muted-foreground">{item.remark || item.certDomains?.join(', ') || '—'}</p>
                  </TableCell>
                  <TableCell>
                    <KindBadges kinds={item.kinds} />
                  </TableCell>
                  <TableCell className="text-center text-sm tabular-nums">
                    {item.stageCount} / {item.stepCount}
                    {!!item.stepDisabledCount && (
                      <span className="ml-1 text-xs text-muted-foreground">（停用 {item.stepDisabledCount}）</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {certDays === null ? (
                      <span className="text-xs text-muted-foreground">还没有证书</span>
                    ) : (
                      <div className="space-y-1">
                        <Badge variant={daysTone(certDays)}>{certDays <= 0 ? '已过期' : `剩 ${certDays} 天`}</Badge>
                        <p
                          className="max-w-[180px] truncate text-xs text-muted-foreground"
                          title={item.certDomains?.join(', ')}
                        >
                          {item.certDomains?.join(', ') || item.certIssuer || '—'}
                        </p>
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={item.lastStatus} />
                      <span className="text-xs text-muted-foreground">{relativeTime(item.lastHistoryTime)}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <p className="text-xs">{item.triggerCount ? `${item.triggerCount} 个触发器` : '仅手动'}</p>
                    <p className="text-xs text-muted-foreground">
                      {item.nextRunTime ? `下次 ${item.nextRunTime}` : '不自动运行'}
                    </p>
                  </TableCell>
                  <TableCell className="text-center">
                    <div className="flex justify-center">
                      <Switch
                        checked={!item.disabled}
                        onChange={() => toggle.mutate(item)}
                        label={item.disabled ? '启用' : '停用'}
                      />
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="运行"
                        onClick={() => run.mutate(item.id)}
                        disabled={run.isPending || item.running}
                      >
                        <Play />
                      </Button>
                      <Button variant="ghost" size="icon-sm" title="编辑" asChild>
                        <Link to={`/pipelines/${item.id}`}>
                          <Pencil />
                        </Link>
                      </Button>
                      <Button variant="ghost" size="icon-sm" title="复制" onClick={() => copy.mutate(item.id)}>
                        <Copy />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="删除"
                        className="text-destructive hover:bg-destructive/10"
                        onClick={() => {
                          if (confirm(`删除流水线「${item.title}」？运行历史会保留。`)) remove.mutate(item.id)
                        }}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}

        {!!list.data?.total && (
          <Pagination
            current={page}
            size={10}
            total={list.data.total}
            onChange={(next) => {
              setPage(next)
              setSelected([])
            }}
          />
        )}
      </Card>

      <Dialog open={cronOpen} onOpenChange={setCronOpen}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>批量设置定时</DialogTitle>
            <p className="text-sm text-muted-foreground">
              应用到已选的 {selected.length} 条流水线；留空表示关掉定时。
            </p>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-1.5">
              <Label>cron 表达式</Label>
              <Input value={cronDraft} onChange={(event) => setCronDraft(event.target.value)} placeholder="0 3 * * *" />
              <p className="text-xs text-muted-foreground">
                五段式：分 时 日 月 周。例：0 3 * * *（每天 3:00）、0 3 * * 1（每周一 3:00）。
              </p>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setCronOpen(false)}>
              取消
            </Button>
            <Button
              size="sm"
              disabled={batch.isPending}
              onClick={() => batch.mutate({ action: 'cron', ids: selected, cron: cronDraft.trim() })}
            >
              应用
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={notifyOpen} onOpenChange={setNotifyOpen}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>批量设置通知</DialogTitle>
            <p className="text-sm text-muted-foreground">执行成功 / 失败时用同一条通知渠道。</p>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-1.5">
              <Label>通知渠道</Label>
              <Select value={notifyId} onChange={(event) => setNotifyId(event.target.value)}>
                <option value="">不通知</option>
                {(notifications.data?.records ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}（{item.typeName}）
                  </option>
                ))}
              </Select>
              <p className="text-xs text-muted-foreground">渠道在「通知渠道」页面维护；选「不通知」会清掉现有配置。</p>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setNotifyOpen(false)}>
              取消
            </Button>
            <Button
              size="sm"
              disabled={batch.isPending}
              onClick={() =>
                batch.mutate({ action: 'notify', ids: selected, notificationId: notifyId ? Number(notifyId) : 0 })
              }
            >
              应用
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={templateOpen} onOpenChange={setTemplateOpen}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>从模板新建</DialogTitle>
            <p className="text-sm text-muted-foreground">模板会生成阶段与任务，建好后可以继续改。</p>
          </DialogHeader>
          <DialogBody className="grid gap-2 sm:grid-cols-2">
            {templates.data?.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => create.mutate(template.id)}
                disabled={create.isPending}
                className="rounded-lg border p-3 text-left transition-colors hover:bg-accent disabled:opacity-60"
              >
                <p className="text-sm font-medium">{template.name}</p>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{template.desc}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {template.tags.map((tag) => (
                    <Badge key={tag} variant="muted">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </button>
            ))}
          </DialogBody>
          <DialogFooter>
            <Label className="mr-auto text-xs text-muted-foreground">选一个模板，直接进入编辑页</Label>
            <Button variant="outline" size="sm" onClick={() => setTemplateOpen(false)}>
              取消
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
