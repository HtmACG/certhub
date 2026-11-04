import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { KeyRound, Loader2, ShieldCheck, ShieldOff, UserCog } from 'lucide-react'
import { toast } from 'sonner'
import { changePassword, disable2fa, enable2fa, fetch2faSetup, updateProfile } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Label } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'

export function AccountPage() {
  const { user, refresh } = useAuth()

  const [nickname, setNickname] = useState('')
  const [email, setEmail] = useState('')
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  //: 后端直接返回二维码 data URL（SVG），不依赖在线服务
  const [setup, setSetup] = useState<{ secret: string; uri: string; qr: string } | null>(null)
  const [code, setCode] = useState('')

  useEffect(() => {
    setNickname(user?.nickname || '')
    setEmail(user?.email || '')
  }, [user?.nickname, user?.email])

  const profile = useMutation({
    mutationFn: () => updateProfile({ nickname: nickname.trim(), email: email.trim() }),
    onSuccess: async () => {
      await refresh()
      toast.success('资料已保存')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const password = useMutation({
    mutationFn: () => changePassword({ oldPassword, newPassword }),
    onSuccess: () => {
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
      toast.success('密码已修改')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const start2fa = useMutation({
    mutationFn: fetch2faSetup,
    onSuccess: (data) => setSetup({ secret: data.secret, uri: data.uri, qr: data.qr }),
    onError: (error: Error) => toast.error(error.message),
  })

  const enable = useMutation({
    mutationFn: () => enable2fa(code.trim()),
    onSuccess: async () => {
      await refresh()
      setSetup(null)
      setCode('')
      toast.success('两步验证已开启')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const disable = useMutation({
    mutationFn: () => disable2fa(code.trim()),
    onSuccess: async () => {
      await refresh()
      setCode('')
      toast.success('两步验证已关闭')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const twoFactorOn = Boolean(user?.totpEnabled)

  return (
    <div className="space-y-5">
      <PageHeader title="账号安全" description="个人资料、登录密码与两步验证" />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserCog className="size-4" />
              基本资料
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label>登录账号</Label>
              <Input value={user?.userName || ''} disabled />
            </div>
            <div className="space-y-1.5">
              <Label>昵称</Label>
              <Input value={nickname} onChange={(event) => setNickname(event.target.value)} placeholder="显示在右上角" />
            </div>
            <div className="space-y-1.5">
              <Label>邮箱</Label>
              <Input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="用于接收通知" />
            </div>
            <Button size="sm" disabled={profile.isPending} onClick={() => profile.mutate()}>
              保存资料
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-4" />
              修改密码
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label>原密码</Label>
              <Input
                type="password"
                value={oldPassword}
                onChange={(event) => setOldPassword(event.target.value)}
                autoComplete="current-password"
              />
            </div>
            <div className="space-y-1.5">
              <Label>新密码</Label>
              <Input
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-1.5">
              <Label>确认新密码</Label>
              <Input
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                autoComplete="new-password"
              />
            </div>
            <Button
              size="sm"
              disabled={!oldPassword || !newPassword || password.isPending}
              onClick={() => {
                if (newPassword !== confirmPassword) {
                  toast.error('两次输入的新密码不一致')
                  return
                }
                password.mutate()
              }}
            >
              修改密码
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {twoFactorOn ? <ShieldCheck className="size-4" /> : <ShieldOff className="size-4" />}
            两步验证（TOTP）
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            开启后登录除了密码还要输入验证器 App 里的 6 位动态码；支持 Google Authenticator、1Password、Microsoft Authenticator 等。
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant={twoFactorOn ? 'success' : 'muted'}>{twoFactorOn ? '已开启' : '未开启'}</Badge>
            <span className="text-xs text-muted-foreground">
              {twoFactorOn ? '登录时会要求输入动态验证码。' : '建议管理员账号都开启。'}
            </span>
          </div>

          {!twoFactorOn && !setup && (
            <Button size="sm" disabled={start2fa.isPending} onClick={() => start2fa.mutate()}>
              {start2fa.isPending && <Loader2 className="animate-spin" />}
              开启两步验证
            </Button>
          )}

          {!twoFactorOn && setup && (
            <div className="flex flex-wrap items-start gap-5">
              <div className="rounded-lg border bg-white p-3">
                {setup.qr ? (
                  <img src={setup.qr} alt="两步验证二维码" className="size-44" />
                ) : (
                  <p className="w-44 py-10 text-center text-xs text-muted-foreground">二维码生成失败，请用下面的密钥手动添加</p>
                )}
              </div>
              <div className="min-w-[260px] flex-1 space-y-3">
                <p className="text-sm">用验证器 App 扫左边的二维码，或手动输入密钥：</p>
                <code className="block break-all rounded-md border bg-muted px-2 py-1.5 font-mono text-xs">{setup.secret}</code>
                <div className="space-y-1.5">
                  <Label>输入 App 上显示的 6 位验证码</Label>
                  <Input
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    placeholder="123456"
                    inputMode="numeric"
                    className="max-w-[200px]"
                  />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" disabled={code.trim().length < 6 || enable.isPending} onClick={() => enable.mutate()}>
                    {enable.isPending && <Loader2 className="animate-spin" />}
                    确认开启
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSetup(null)
                      setCode('')
                    }}
                  >
                    取消
                  </Button>
                </div>
              </div>
            </div>
          )}

          {twoFactorOn && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label>关闭时需要验证当前动态码</Label>
                <Input
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder="123456"
                  inputMode="numeric"
                  className="max-w-[200px]"
                />
              </div>
              <Button
                variant="destructive"
                size="sm"
                disabled={code.trim().length < 6 || disable.isPending}
                onClick={() => disable.mutate()}
              >
                {disable.isPending && <Loader2 className="animate-spin" />}
                关闭两步验证
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
