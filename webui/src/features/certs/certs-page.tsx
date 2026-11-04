import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Award, Download, Eye, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { deleteCert, downloadCert, fetchCertList, importCert } from '@/lib/api'
import { CertificateViewer } from './certificate-viewer'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label, Textarea } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { daysTone } from '@/components/status'

export function CertsPage() {
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [cert, setCert] = useState('')
  const [key, setKey] = useState('')
  const [remark, setRemark] = useState('')
  const [viewingId, setViewingId] = useState<number | null>(null)
  const queryClient = useQueryClient()

  const list = useQuery({ queryKey: ['certs', page], queryFn: () => fetchCertList({ current: page, size: 12 }) })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['certs'] })

  const importMutation = useMutation({
    mutationFn: () => importCert({ cert: cert.trim(), key: key.trim(), remark: remark.trim() }),
    onSuccess: () => {
      toast.success('证书已入库')
      setOpen(false)
      setCert('')
      setKey('')
      setRemark('')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteCert(id),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const records = list.data?.records ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="证书库"
        description="流水线签发和手动上传的证书都在这里，私钥不离开本机"
        actions={
          <Button size="sm" onClick={() => setOpen(true)}>
            <Plus />
            上传证书
          </Button>
        }
      />

      <Card className="overflow-hidden">
        {list.isLoading ? (
          <TableSkeleton rows={6} />
        ) : records.length === 0 ? (
          <EmptyState
            icon={Award}
            title="证书库是空的"
            description="跑一条申请流水线，或者把已有证书的 PEM 与私钥粘贴进来。"
            action={
              <Button size="sm" onClick={() => setOpen(true)}>
                <Plus />
                上传证书
              </Button>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>域名</TableHead>
                <TableHead>签发者</TableHead>
                <TableHead>生效时间</TableHead>
                <TableHead>到期时间</TableHead>
                <TableHead className="text-center">剩余</TableHead>
                <TableHead className="text-right">下载</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="max-w-[320px]">
                    <p className="truncate font-medium">{item.domains?.join(', ') || item.domain}</p>
                    <p className="text-xs text-muted-foreground">#{item.id} · 入库 {item.createTime}</p>
                  </TableCell>
                  <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">{item.issuer}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.notBefore}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.notAfter}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant={daysTone(item.daysLeft)}>{item.daysLeft} 天</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="xs" onClick={() => setViewingId(item.id)}>
                        <Eye />
                        查看
                      </Button>
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => downloadCert(item.id, 'pem', 'cert').catch((error: Error) => toast.error(error.message))}
                      >
                        <Download />
                        证书
                      </Button>
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => downloadCert(item.id, 'pem', 'key').catch((error: Error) => toast.error(error.message))}
                      >
                        私钥
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="text-destructive hover:bg-destructive/10"
                        title="删除"
                        onClick={() => {
                          if (confirm(`删除 ${item.domains?.join(', ') || item.domain} 的证书？`)) remove.mutate(item.id)
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
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>上传证书</DialogTitle>
            <p className="text-sm text-muted-foreground">粘贴完整证书链和对应的私钥，私钥只保存在本机数据库。</p>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label>证书链（PEM）</Label>
              <Textarea
                value={cert}
                onChange={(event) => setCert(event.target.value)}
                placeholder="-----BEGIN CERTIFICATE-----"
                className="min-h-[140px] font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label>私钥（PEM）</Label>
              <Textarea
                value={key}
                onChange={(event) => setKey(event.target.value)}
                placeholder="-----BEGIN PRIVATE KEY-----"
                className="min-h-[120px] font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label>备注</Label>
              <Textarea value={remark} onChange={(event) => setRemark(event.target.value)} placeholder="可选，方便以后辨认" />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button size="sm" disabled={!cert.trim() || !key.trim() || importMutation.isPending} onClick={() => importMutation.mutate()}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CertificateViewer
        certId={viewingId}
        open={viewingId !== null}
        onOpenChange={(next) => {
          if (!next) setViewingId(null)
        }}
      />
    </div>
  )
}
