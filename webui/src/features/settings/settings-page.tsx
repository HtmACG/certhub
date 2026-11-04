import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Globe, Save, Settings, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { fetchSettings, updateSettings } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Label, Textarea } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Tabs } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/empty'
import { ImageUploader } from '@/components/image-uploader'

type TabKey = 'site' | 'network' | 'security'

export function SettingsPage() {
  const [tab, setTab] = useState<TabKey>('site')
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const [draft, setDraft] = useState<Record<string, Record<string, unknown>>>({})

  useEffect(() => {
    if (settings.data) setDraft(structuredClone(settings.data))
  }, [settings.data])

  const save = useMutation({
    mutationFn: () => updateSettings(draft),
    onSuccess: () => {
      toast.success('设置已保存')
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const set = (section: string, key: string, value: unknown) =>
    setDraft((prev) => ({ ...prev, [section]: { ...(prev[section] ?? {}), [key]: value } }))

  const site = draft.site ?? {}
  const network = draft.network ?? {}
  const security = draft.security ?? {}

  return (
    <div className="space-y-5">
      <PageHeader
        title="系统设置"
        description="站点信息、出网代理与登录安全"
        actions={
          <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending || settings.isLoading}>
            <Save />
            保存
          </Button>
        }
      />

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'site', label: '站点信息' },
          { value: 'network', label: '网络代理' },
          { value: 'security', label: '登录安全' },
        ]}
      />

      {settings.isLoading ? (
        <Skeleton className="h-72 w-full" />
      ) : (
        <>
          {tab === 'site' && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Globe className="size-4" />
                  站点信息
                </CardTitle>
                <p className="text-xs text-muted-foreground">这里的名称会出现在侧边栏与登录页，改了立刻生效。</p>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>站点名称</Label>
                  <Input value={(site.name as string) ?? ''} onChange={(event) => set('site', 'name', event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>副标题</Label>
                  <Input value={(site.subtitle as string) ?? ''} onChange={(event) => set('site', 'subtitle', event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>浏览器标题</Label>
                  <Input value={(site.title as string) ?? ''} onChange={(event) => set('site', 'title', event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>版权信息</Label>
                  <Input value={(site.copyright as string) ?? ''} onChange={(event) => set('site', 'copyright', event.target.value)} />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label>登录页公告</Label>
                  <Textarea
                    value={(site.loginNotice as string) ?? ''}
                    onChange={(event) => set('site', 'loginNotice', event.target.value)}
                    placeholder="留空则不显示"
                  />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label>GitHub 仓库</Label>
                  <Input
                    value={(site.githubRepo as string) ?? 'HtmACG/certhub'}
                    onChange={(event) => set('site', 'githubRepo', event.target.value)}
                    placeholder="owner/repo"
                  />
                  <p className="text-xs text-muted-foreground">
                    「关于」页的更新记录与检查更新读这个仓库；留空默认 HtmACG/certhub。
                  </p>
                </div>
                <div className="grid gap-6 border-t pt-5 sm:col-span-2 sm:grid-cols-2">
                  <ImageUploader
                    label="站点 Logo"
                    hint="显示在登录页与侧边栏，建议正方形 PNG/SVG，不超过 1MB"
                    value={(site.logo as string) ?? ''}
                    onChange={(value) => set('site', 'logo', value)}
                  />
                  <ImageUploader
                    label="登录页背景"
                    hint="只在登录页使用，建议横图，不超过 1MB；不设置就用点阵纹理"
                    value={(site.loginBackground as string) ?? ''}
                    onChange={(value) => set('site', 'loginBackground', value)}
                    aspect="wide"
                  />
                </div>
                <div className="flex items-center gap-2 sm:col-span-2">
                  <Switch
                    checked={Boolean(site.registerEnabled)}
                    onChange={(next) => set('site', 'registerEnabled', next)}
                    label="开放注册"
                  />
                  <span className="text-sm text-muted-foreground">允许新用户自行注册（默认关闭）</span>
                </div>
              </CardContent>
            </Card>
          )}

          {tab === 'network' && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bell className="size-4" />
                  出网代理
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  国内机器访问 Google / ZeroSSL 需要代理。填了就走代理，noProxy 命中的地址直连。
                </p>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>HTTP 代理</Label>
                  <Input
                    value={(network.httpProxy as string) ?? ''}
                    placeholder="http://127.0.0.1:7890"
                    onChange={(event) => set('network', 'httpProxy', event.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>HTTPS 代理</Label>
                  <Input
                    value={(network.httpsProxy as string) ?? ''}
                    placeholder="http://127.0.0.1:7890"
                    onChange={(event) => set('network', 'httpsProxy', event.target.value)}
                  />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label>不走代理的地址</Label>
                  <Input
                    value={(network.noProxy as string) ?? ''}
                    placeholder="localhost,127.0.0.1,internal.example.com"
                    onChange={(event) => set('network', 'noProxy', event.target.value)}
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {tab === 'security' && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="size-4" />
                  登录安全
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  密码错几次之后要求图形验证码；连续错太多次会临时锁定账号。
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-2">
                  <Switch
                    checked={security.captchaEnabled !== false}
                    onChange={(next) => set('security', 'captchaEnabled', next)}
                    label="图形验证码"
                  />
                  <span className="text-sm text-muted-foreground">启用图形验证码</span>
                </div>
                <div className="max-w-xs space-y-1.5">
                  <Label>失败几次后要求验证码</Label>
                  <Input
                    type="number"
                    value={(security.captchaAfter as number) ?? 1}
                    onChange={(event) => set('security', 'captchaAfter', Number(event.target.value))}
                  />
                </div>

                <div className="flex items-center gap-2">
                  <Switch
                    checked={security.loginNotify !== false}
                    onChange={(next) => set('security', 'loginNotify', next)}
                    label="登录邮件提醒"
                  />
                  <span className="text-sm text-muted-foreground">
                    登录成功后给账号邮箱发一封提醒（含登录 IP 与时间）
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  用户没填邮箱、或「通知渠道」里没有可用的邮件渠道时不发送；
                  SMTP 参数复用邮件通知渠道，收件人固定为登录账号自己的邮箱。
                </p>

                <div className="grid max-w-md gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label>密码错误几次后锁定</Label>
                    <Input
                      type="number"
                      min={1}
                      value={(security.loginFailLimit as number) ?? 5}
                      onChange={(event) => set('security', 'loginFailLimit', Number(event.target.value))}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>锁定多少分钟</Label>
                    <Input
                      type="number"
                      min={1}
                      value={(security.lockMinutes as number) ?? 10}
                      onChange={(event) => set('security', 'lockMinutes', Number(event.target.value))}
                    />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  连续输错密码达到次数后，账号锁定对应分钟数；锁定期内即使密码正确也会被拒绝。
                  两步验证码连续输错也按同一套计数。
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}

      <Card className="border-dashed bg-muted/30">
        <CardContent className="flex items-start gap-3 py-4 text-xs text-muted-foreground">
          <Settings className="mt-0.5 size-4 shrink-0" />
          <p>
            ACME 账户与 EAB 凭据在「授权管理 → 证书签发」里维护，不放在这里。改完设置点右上角保存；
            代理改动对下一次出网请求生效。
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
