import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { KeyRound, Loader2, LockKeyhole, RefreshCw, ShieldCheck, User } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { useAuth } from '@/lib/auth'
import { useSiteConfig } from '@/lib/site'
import { bind2fa, fetch2faSecretForBind, fetchCaptcha, login, type ApiErrorLike } from '@/lib/auth-api'
import { cn } from '@/lib/utils'

const FEATURES = [
  '一条流水线里编排申请、部署、通知三个阶段',
  'DNS / 主机 / 面板 / 云厂商凭据统一放在授权里',
  '每次运行都有独立日志，失败在哪一步一眼能看见',
]

export function LoginPage() {
  const navigate = useNavigate()
  const { signIn, user, refresh } = useAuth()
  const siteQuery = useSiteConfig()
  const site = siteQuery.data

  const [userName, setUserName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [captcha, setCaptcha] = useState<{ token: string; image: string } | null>(null)
  const [captchaCode, setCaptchaCode] = useState('')

  const [bind, setBind] = useState<{ token: string; secret: string; uri: string } | null>(null)
  const [bindCode, setBindCode] = useState('')

  const background = site?.loginBackground
  const logo = site?.logo

  useEffect(() => {
    if (user) navigate('/', { replace: true })
  }, [user, navigate])

  useEffect(() => {
    if (site?.title) document.title = site.title
  }, [site?.title])

  const loadCaptcha = async () => {
    try {
      const data = await fetchCaptcha()
      setCaptcha({ token: data.token, image: data.image })
      setCaptchaCode('')
    } catch {
      setCaptcha(null)
    }
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login({
        userName: userName.trim(),
        password,
        captchaCode: captcha ? captchaCode : undefined,
        captchaToken: captcha ? captcha.token : undefined,
      })
      const payload = data as unknown as { token?: string; needBind2fa?: boolean; bindToken?: string }
      if (payload.needBind2fa && payload.bindToken) {
        const secret = await fetch2faSecretForBind(payload.bindToken)
        setBind({ token: payload.bindToken, secret: secret.secret, uri: secret.uri })
        return
      }
      if (!payload.token) throw new Error('登录响应里没有令牌')
      signIn(payload.token, {
        userId: 0,
        userName,
        nickname: userName,
        email: '',
        avatar: '',
        role: 'admin',
        roles: [],
        totpEnabled: false,
      })
      await refresh()
      toast.success('已登录')
      navigate('/', { replace: true })
    } catch (err) {
      const apiError = err as ApiErrorLike
      setError(apiError.message || '登录失败')
      if (apiError.data && typeof apiError.data === 'object' && (apiError.data as { needCaptcha?: boolean }).needCaptcha) {
        await loadCaptcha()
      }
    } finally {
      setLoading(false)
    }
  }

  const submitBind = async () => {
    if (!bind) return
    setLoading(true)
    try {
      const data = await bind2fa(bind.token, bindCode.trim())
      signIn(data.token, {
        userId: 0,
        userName,
        nickname: userName,
        email: '',
        avatar: '',
        role: 'admin',
        roles: [],
        totpEnabled: true,
      })
      await refresh()
      toast.success('两步验证已绑定')
      navigate('/', { replace: true })
    } catch (err) {
      setError((err as Error).message || '绑定失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-[minmax(0,1fr)_460px]">
      <section
        className={cn(
          'relative hidden flex-col justify-between overflow-hidden p-10 lg:flex',
          background ? 'text-white' : 'border-r bg-muted/40',
        )}
      >
        {background ? (
          <>
            <div
              className="absolute inset-0 bg-cover bg-center"
              style={{ backgroundImage: `url("${background}")` }}
            />
            <div className="absolute inset-0 bg-black/60" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/35 to-black/20" />
          </>
        ) : (
          <div className="grid-dots pointer-events-none absolute inset-0 opacity-[0.35]" />
        )}

        <div className="relative flex items-center gap-2.5">
          {logo ? (
            <img
              src={logo}
              alt={site?.name || 'logo'}
              className="size-9 rounded-lg border border-white/20 bg-white/10 object-contain p-1"
            />
          ) : (
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ShieldCheck className="size-4.5" />
            </div>
          )}
          <div>
            <p className="text-sm font-semibold leading-tight">{site?.name || 'CertHub'}</p>
            <p className={cn('text-xs leading-tight', background ? 'text-white/70' : 'text-muted-foreground')}>
              {site?.subtitle || '证书自动化管理系统'}
            </p>
          </div>
        </div>

        <div className="relative max-w-md space-y-5">
          <h1 className="text-balance text-2xl font-semibold leading-snug tracking-tight">
            证书到期之前自动续期，续期之后自动部署。
          </h1>
          <p className={cn('text-sm leading-relaxed', background ? 'text-white/75' : 'text-muted-foreground')}>
            不用记每个面板的路径。把签发、部署、提醒串成一条流水线，剩下的交给定时任务。
          </p>
          <ul className="space-y-2.5">
            {FEATURES.map((feature) => (
              <li
                key={feature}
                className={cn('flex items-start gap-2 text-sm', background ? 'text-white/75' : 'text-muted-foreground')}
              >
                <span
                  className={cn(
                    'mt-1.5 size-1.5 shrink-0 rounded-full',
                    background ? 'bg-white/50' : 'bg-foreground/40',
                  )}
                />
                {feature}
              </li>
            ))}
          </ul>
        </div>

        <p className={cn('relative text-xs', background ? 'text-white/60' : 'text-muted-foreground')}>
          {site?.loginNotice ? site.loginNotice : '数据保存在本机，不经过第三方服务。'}
        </p>
      </section>

      <section className="relative flex flex-col justify-center border-l bg-background px-6 py-12">
        <div className="mx-auto w-full max-w-[340px] space-y-8">
          <div className="flex items-center gap-2.5 lg:hidden">
            {logo ? (
              <img src={logo} alt={site?.name || 'logo'} className="size-8 rounded-lg border object-contain" />
            ) : (
              <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <ShieldCheck className="size-4" />
              </div>
            )}
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold leading-tight">{site?.name || 'CertHub'}</p>
              <p className="truncate text-xs text-muted-foreground">{site?.subtitle || '证书自动化管理系统'}</p>
            </div>
          </div>

          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">登录</h2>
            <p className="text-sm text-muted-foreground">用你的 {site?.name || 'CertHub'} 账号继续</p>
          </div>

          {bind ? (
            <div className="space-y-4 rounded-lg border bg-card p-4">
              <div className="flex items-center gap-2 text-sm font-medium">
                <KeyRound className="size-4" />
                首次登录需要绑定两步验证
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                用验证器 App 扫描或在 App 里手动输入这串密钥，然后填当前 6 位验证码。
              </p>
              <code className="block break-all rounded border bg-muted px-2 py-1.5 font-mono text-xs">{bind.secret}</code>
              <Input
                value={bindCode}
                onChange={(event) => setBindCode(event.target.value)}
                placeholder="6 位验证码"
                inputMode="numeric"
                maxLength={6}
              />
              <Button className="w-full" onClick={submitBind} disabled={loading || bindCode.trim().length !== 6}>
                {loading && <Loader2 className="size-4 animate-spin" />}
                绑定并登录
              </Button>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={submit}>
              <div className="space-y-1.5">
                <Label htmlFor="userName">账号</Label>
                <div className="relative">
                  <User className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="userName"
                    value={userName}
                    onChange={(event) => setUserName(event.target.value)}
                    autoComplete="username"
                    placeholder="admin"
                    className="pl-8"
                    required
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="password">密码</Label>
                <div className="relative">
                  <LockKeyhole className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="current-password"
                    placeholder="••••••"
                    className="pl-8"
                    required
                  />
                </div>
              </div>

              {captcha && (
                <div className="space-y-1.5">
                  <Label htmlFor="captcha">图形验证码</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="captcha"
                      value={captchaCode}
                      onChange={(event) => setCaptchaCode(event.target.value)}
                      placeholder="输入图中字符"
                      className="uppercase"
                      autoComplete="off"
                    />
                    <button
                      type="button"
                      onClick={loadCaptcha}
                      className="group relative h-9 shrink-0 overflow-hidden rounded-md border bg-muted"
                      title="换一张"
                    >
                      <img src={captcha.image} alt="验证码" className="h-full w-[104px] object-cover" />
                      <span className="absolute inset-0 hidden items-center justify-center bg-background/80 text-xs group-hover:flex">
                        <RefreshCw className="size-3.5" />
                      </span>
                    </button>
                  </div>
                </div>
              )}

              {error && (
                <p className="rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 text-xs text-destructive">
                  {error}
                </p>
              )}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading && <Loader2 className="size-4 animate-spin" />}
                登录
              </Button>
            </form>
          )}

          <p className="text-center text-xs text-muted-foreground">忘记密码？让管理员在「用户管理」里重置。</p>
        </div>

        <p className="absolute bottom-6 left-0 right-0 text-center text-[11px] text-muted-foreground/70">
          {site?.copyright || `© ${new Date().getFullYear()} CertHub`}
        </p>
      </section>
    </div>
  )
}
