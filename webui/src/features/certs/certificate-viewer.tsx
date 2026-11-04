import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Copy, KeyRound, ShieldAlert } from 'lucide-react'
import { toast } from 'sonner'
import { fetchCertDetail } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/empty'
import { Dialog, DialogBody, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { StatusBadge, daysTone } from '@/components/status'

type TabKey = 'overview' | 'pem' | 'chain' | 'key'

function CopyButton({ text, label = '复制' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      variant="ghost"
      size="xs"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          toast.success('已复制')
          window.setTimeout(() => setCopied(false), 1500)
        } catch {
          toast.error('浏览器拒绝写剪贴板，请手动选中复制')
        }
      }}
    >
      {copied ? <Check /> : <Copy />}
      {label}
    </Button>
  )
}

function Field({ label, value, mono }: { label: string; value?: string; mono?: boolean }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={mono ? 'break-all font-mono text-xs' : 'break-words text-sm'}>{value || '—'}</p>
    </div>
  )
}

function PemBlock({ title, pem }: { title: string; pem: string }) {
  return (
    <section className="overflow-hidden rounded-lg border">
      <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2">
        <p className="text-xs font-medium">{title}</p>
        <CopyButton text={pem} />
      </div>
      <pre className="scrollbar-thin max-h-[240px] overflow-auto bg-muted/20 px-3 py-2 font-mono text-[11px] leading-relaxed">
        {pem || '没有内容'}
      </pre>
    </section>
  )
}

export function CertificateViewer({
  certId,
  open,
  onOpenChange,
}: {
  certId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [tab, setTab] = useState<TabKey>('overview')
  const detail = useQuery({
    queryKey: ['cert-detail', certId],
    queryFn: () => fetchCertDetail(certId as number),
    enabled: open && !!certId,
  })

  const cert = detail.data
  const info = cert?.details

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) setTab('overview')
      }}
    >
      <DialogContent size="xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            {cert?.domains?.join(', ') || cert?.domain || '证书详情'}
            {cert && <StatusBadge status={cert.status} />}
            {cert && <Badge variant={daysTone(cert.daysLeft)}>剩 {cert.daysLeft} 天</Badge>}
          </DialogTitle>
          <p className="text-sm text-muted-foreground">
            {cert ? `颁发者 ${cert.issuer || info?.issuer || '—'} · 到期 ${cert.notAfter}` : '读取证书…'}
          </p>
        </DialogHeader>

        <DialogBody className="min-h-[420px] space-y-4">
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { value: 'overview', label: '概览' },
              { value: 'pem', label: '证书' },
              { value: 'chain', label: '证书链', count: info?.chain?.length },
              { value: 'key', label: '私钥' },
            ]}
          />

          {detail.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-5 w-1/2" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : !cert ? (
            <p className="py-10 text-center text-sm text-muted-foreground">没有拿到证书内容，可能已经被删除。</p>
          ) : tab === 'overview' ? (
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="主体（Subject）" value={info?.subject || cert.domain} />
                <Field label="颁发者（Issuer）" value={info?.issuer || cert.issuer} mono />
                <Field label="生效时间" value={cert.notBefore} />
                <Field label="到期时间" value={cert.notAfter} />
                <Field label="签名算法" value={info?.signatureAlgorithm} />
                <Field label="公钥" value={info?.publicKey} />
                <Field label="序列号" value={info?.serialNumber} mono />
                <Field label="SHA-256 指纹" value={info?.fingerprintSha256} mono />
              </div>

              <div className="space-y-2 border-t pt-4">
                <p className="text-[11px] text-muted-foreground">SAN（证书覆盖的域名）</p>
                <div className="flex flex-wrap gap-1.5">
                  {(info?.san?.length ? info.san : cert.domains).map((domain) => (
                    <Badge key={domain} variant="muted" className="font-mono">
                      {domain}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="grid gap-2 border-t pt-4 text-xs text-muted-foreground sm:grid-cols-3">
                <span>证书链 {info?.chainCount ?? 1} 张</span>
                <span>{info?.isSelfSigned ? '自签名证书' : '由 CA 签发'}</span>
                <span>入库 {cert.createTime}</span>
              </div>
            </div>
          ) : tab === 'pem' ? (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                站点证书（PEM）。下载接口能拿到完整链和私钥，这里只用于核对内容。
              </p>
              <PemBlock title="CERTIFICATE" pem={cert.certPem} />
            </div>
          ) : tab === 'chain' ? (
            <div className="space-y-3">
              {(info?.chain ?? []).map((item) => (
                <div key={item.index} className="space-y-2 rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">#{item.index}</Badge>
                    <span className="text-sm font-medium">{item.kind}</span>
                    {item.isCA && <Badge variant="info">CA</Badge>}
                    <span className="ml-auto text-[11px] text-muted-foreground">
                      {item.notBefore} → {item.notAfter}
                    </span>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label="主体" value={item.subject} />
                    <Field label="颁发者" value={item.issuer} />
                  </div>
                  <details className="group">
                    <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                      查看 PEM
                    </summary>
                    <div className="mt-2">
                      <PemBlock title="PEM" pem={item.pem} />
                    </div>
                  </details>
                </div>
              ))}
              {(info?.chain ?? []).length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">后端没有返回证书链明细。</p>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/8 px-3 py-2 text-xs text-warning">
                <ShieldAlert className="mt-0.5 size-4 shrink-0" />
                私钥只在本机显示。复制走之后请自己负责保管，别贴到聊天工具里。
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <KeyRound className="size-3.5" />
                {cert.keyPem ? '已加载私钥' : '库里没有私钥'}
              </div>
              <PemBlock title="PRIVATE KEY" pem={cert.keyPem} />
            </div>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  )
}
