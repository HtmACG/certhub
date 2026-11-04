import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { ChevronDown, ChevronLeft, ChevronRight, CircleX, Info, LayoutDashboard, LogOut, Menu, Moon, ShieldCheck, Sun, UserCog, X } from 'lucide-react'
import { NAV, findNav } from './nav'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { useSiteConfig } from '@/lib/site'
import { cn } from '@/lib/utils'

const TAB_KEY = 'certhub.tabs'

interface Tab {
  path: string
  label: string
}

function useTheme() {
  const [dark, setDark] = useState(() => localStorage.getItem('certhub.theme') === 'dark')
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    document.documentElement.classList.toggle('light', !dark)
    localStorage.setItem('certhub.theme', dark ? 'dark' : 'light')
  }, [dark])
  return { dark, toggle: () => setDark((prev) => !prev) }
}

function labelFor(pathname: string) {
  const nav = findNav(pathname)
  if (pathname.startsWith('/pipelines/')) {
    const id = pathname.split('/')[2]
    return `流水线 ${id}`
  }
  return nav?.label ?? '页面'
}

const HOME_TAB: Tab = { path: '/', label: '工作台' }

/** 去重 + 保证工作台在最前：老缓存里可能存过重复路径，读出来先洗一遍 */
function normalizeTabs(list: Tab[]): Tab[] {
  const seen = new Set<string>()
  const out: Tab[] = []
  ;(Array.isArray(list) ? list : []).forEach((tab) => {
    if (!tab || typeof tab.path !== 'string' || !tab.path) return
    if (tab.path === '/') return
    if (seen.has(tab.path)) return
    seen.add(tab.path)
    out.push({ path: tab.path, label: tab.label || labelFor(tab.path) })
  })
  return [HOME_TAB, ...out]
}

function useTabs() {
  const location = useLocation()
  const navigate = useNavigate()
  const [tabs, setTabs] = useState<Tab[]>(() => {
    try {
      const raw = sessionStorage.getItem(TAB_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as Tab[]
        if (Array.isArray(parsed) && parsed.length) return normalizeTabs(parsed)
      }
    } catch {
      /* 忽略损坏的缓存 */
    }
    return [HOME_TAB]
  })

  useEffect(() => {
    const path = location.pathname
    setTabs((prev) => normalizeTabs([...prev, { path, label: labelFor(path) }]))
  }, [location.pathname])

  useEffect(() => {
    sessionStorage.setItem(TAB_KEY, JSON.stringify(tabs))
  }, [tabs])

  /** 批量关闭：工作台始终保留；当前页签被关掉时跳到 fallback */
  const apply = (next: Tab[], fallback: string) => {
    const clean = normalizeTabs(next)
    setTabs(clean)
    if (!clean.some((tab) => tab.path === location.pathname)) {
      navigate(clean.some((tab) => tab.path === fallback) ? fallback : clean[0].path)
    }
  }

  const close = (path: string) => {
    const index = tabs.findIndex((tab) => tab.path === path)
    const next = tabs.filter((tab) => tab.path !== path)
    const fallback = next[Math.max(0, index - 1)] ?? next[0] ?? HOME_TAB
    apply(next, fallback.path)
  }

  const closeLeft = (path: string) => {
    const index = tabs.findIndex((tab) => tab.path === path)
    apply(tabs.slice(index), path)
  }

  const closeRight = (path: string) => {
    const index = tabs.findIndex((tab) => tab.path === path)
    apply(tabs.slice(0, index + 1), path)
  }

  const closeOthers = (path: string) => {
    apply(tabs.filter((tab) => tab.path === path), path)
  }

  const closeAll = () => {
    apply([HOME_TAB], '/')
  }

  return { tabs, close, closeLeft, closeRight, closeOthers, closeAll }
}

function UserAvatar({ src, name }: { src?: string; name: string }) {
  const [failed, setFailed] = useState(false)
  const letter = (name || 'A').slice(0, 1).toUpperCase()
  if (!src || failed) {
    return (
      <span className="flex size-7 items-center justify-center rounded-full border bg-muted text-xs font-medium">
        {letter}
      </span>
    )
  }
  return (
    <img
      src={src}
      alt={name}
      onError={() => setFailed(true)}
      className="size-7 rounded-full border bg-muted object-cover"
    />
  )
}

function Brand({ site }: { site?: { name?: string; subtitle?: string; logo?: string } }) {
  const name = site?.name || 'CertHub'
  const subtitle = site?.subtitle || '证书自动化控制台'
  return (
    <div className="flex items-center gap-2.5 px-4 py-4">
      {site?.logo ? (
        <img src={site.logo} alt={name} className="size-8 rounded-lg border object-contain" />
      ) : (
        <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <ShieldCheck className="size-4" />
        </div>
      )}
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold leading-tight">{name}</p>
        <p className="truncate text-[11px] leading-tight text-muted-foreground">{subtitle}</p>
      </div>
    </div>
  )
}

function Sidebar({ onNavigate, site }: { onNavigate?: () => void; site?: { name?: string; subtitle?: string; logo?: string } }) {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const perms = new Set(user?.permissions ?? [])
  const groups = NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) =>
      isAdmin ? true : !item.adminOnly && (!item.perm || perms.has(item.perm)),
    ),
  })).filter((group) => group.items.length > 0)

  return (
    <div className="flex h-full w-[248px] flex-col border-r bg-sidebar">
      <Brand site={site} />
      <nav className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {groups.map((group) => (
          <div key={group.label} className="space-y-1">
            <p className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">
              {group.label}
            </p>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors',
                    isActive
                      ? 'bg-sidebar-accent font-medium text-foreground'
                      : 'text-muted-foreground hover:bg-sidebar-accent/70 hover:text-foreground',
                  )
                }
              >
                <item.icon className="size-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="border-t px-4 py-3">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          CertHub · 开源证书自动化
          <br />
          本地部署，无付费与授权限制
        </p>
        <NavLink
          to="/about"
          onClick={onNavigate}
          className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground"
        >
          <Info className="size-3.5" />
          关于 / 更新记录
        </NavLink>
      </div>
    </div>
  )
}

function Breadcrumb({ pathname }: { pathname: string }) {
  const nav = findNav(pathname)
  const group = NAV.find((item) => item.items.some((entry) => entry.to === nav?.to))
  const detail = pathname.startsWith('/pipelines/') ? `流水线 ${pathname.split('/')[2]}` : null

  return (
    <nav aria-label="面包屑" className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
      {group && <span className="shrink-0">{group.label}</span>}
      <span className="shrink-0 text-muted-foreground/50">/</span>
      {detail ? (
        <>
          <NavLink to="/pipelines" className="shrink-0 hover:text-foreground">
            {nav?.label}
          </NavLink>
          <span className="shrink-0 text-muted-foreground/50">/</span>
          <span className="truncate text-foreground">{detail}</span>
        </>
      ) : (
        <span className="truncate text-foreground">{nav?.label ?? '控制台'}</span>
      )}
    </nav>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const { dark, toggle } = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const { tabs, close, closeLeft, closeRight, closeOthers, closeAll } = useTabs()
  const [tabMenu, setTabMenu] = useState<{ x: number; y: number; path: string } | null>(null)
  const site = useSiteConfig().data

  const activePath = location.pathname

  // 顶部标签栏：标签多了以后用鼠标滚轮横向滚动，并且不显示滚动条
  const tabBarRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = tabBarRef.current
    if (!el) return
    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return
      const max = el.scrollWidth - el.clientWidth
      if (max <= 0) return
      // 有些鼠标/触控板按「行」给 delta，换算成像素
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? el.clientWidth : 1
      const delta = event.deltaY * unit
      const next = el.scrollLeft + delta
      // 已经到头就交还给页面，避免把整页滚动也吃掉
      if ((next < 0 && delta < 0) || (next > max && delta > 0)) return
      event.preventDefault()
      el.scrollLeft = next
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    // 从菜单跳到远处的标签时，把它滚进可视范围
    const activeEl = el.querySelector('[data-active-tab="true"]') as HTMLElement | null
    activeEl?.scrollIntoView({ inline: 'nearest', block: 'nearest' })
    return () => el.removeEventListener('wheel', onWheel)
  }, [activePath])

  useEffect(() => {
    setMobileOpen(false)
    setMenuOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (site?.title) document.title = site.title
  }, [site?.title])

  useEffect(() => {
    if (!tabMenu) return
    const dismiss = (event: PointerEvent) => {
      if (!(event.target as HTMLElement).closest('[data-tab-menu]')) setTabMenu(null)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setTabMenu(null)
    }
    window.addEventListener('pointerdown', dismiss)
    window.addEventListener('keydown', onKey)
    window.addEventListener('scroll', () => setTabMenu(null), true)
    return () => {
      window.removeEventListener('pointerdown', dismiss)
      window.removeEventListener('keydown', onKey)
    }
  }, [tabMenu])

  const breadcrumbKey = useMemo(() => activePath, [activePath])

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="sticky top-0 hidden h-screen shrink-0 lg:block">
        <Sidebar site={site} />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <div className="absolute left-0 top-0 h-full shadow-lg">
            <Sidebar site={site} onNavigate={() => setMobileOpen(false)} />
            <Button variant="ghost" size="icon-sm" className="absolute right-2 top-2" onClick={() => setMobileOpen(false)}>
              <X />
            </Button>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur">
          <header className="flex h-14 items-center gap-3 px-4 lg:px-6">
            <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setMobileOpen(true)}>
              <Menu />
            </Button>
            <Breadcrumb pathname={breadcrumbKey} />

            <div className="ml-auto flex items-center gap-1">
              <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="切换主题">
                {dark ? <Sun /> : <Moon />}
              </Button>

              <div className="relative">
                <button
                  type="button"
                  onClick={() => setMenuOpen((prev) => !prev)}
                  className="flex items-center gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-accent"
                >
                  <UserAvatar
                    src={user?.avatar || '/avatar-default.webp'}
                    name={user?.nickname || user?.userName || '用户'}
                  />
                  <span className="hidden max-w-[120px] truncate sm:block">{user?.nickname || user?.userName}</span>
                  <ChevronDown className="size-3.5 text-muted-foreground" />
                </button>
                {menuOpen && (
                  <div className="absolute right-0 top-11 z-40 w-48 overflow-hidden rounded-lg border bg-popover p-1 shadow-md">
                    <div className="px-2 py-1.5">
                      <p className="truncate text-sm font-medium">{user?.nickname || user?.userName}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {user?.role === 'admin' ? '管理员' : '成员'}
                      </p>
                    </div>
                    <div className="my-1 h-px bg-border" />
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
                      onClick={() => navigate('/account')}
                    >
                      <UserCog className="size-4" />
                      账号安全
                    </button>
                    {user?.role === 'admin' && (
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
                        onClick={() => navigate('/settings')}
                      >
                        <ShieldCheck className="size-4" />
                        系统设置
                      </button>
                    )}
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
                      onClick={() => navigate('/about')}
                    >
                      <Info className="size-4" />
                      关于 CertHub
                    </button>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-destructive hover:bg-destructive/10"
                      onClick={signOut}
                    >
                      <LogOut className="size-4" />
                      退出登录
                    </button>
                  </div>
                )}
              </div>
            </div>
          </header>

          <div
            ref={tabBarRef}
            style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' } as React.CSSProperties}
            className="tabbar-scroll-hidden scrollbar-none flex h-10 items-center gap-1 overflow-x-auto overflow-y-hidden px-2"
          >
            {tabs.map((tab, index) => {
              const active = tab.path === activePath
              const previousActive = index > 0 && tabs[index - 1].path === activePath
              const Icon = findNav(tab.path)?.icon ?? LayoutDashboard
              return (
                <Fragment key={tab.path}>
                  {index > 0 && !active && !previousActive && <span className="mx-0.5 h-3.5 w-px shrink-0 bg-border" />}
                  <div
                    data-active-tab={active ? 'true' : undefined}
                    onContextMenu={(event) => {
                      event.preventDefault()
                      setTabMenu({ x: event.clientX, y: event.clientY, path: tab.path })
                    }}
                    className={cn(
                      'group flex h-8 shrink-0 items-center gap-1.5 rounded-md pl-2.5 pr-1.5 text-xs transition-colors',
                      active
                        ? 'bg-muted font-medium text-foreground'
                        : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                    )}
                  >
                    <Icon className="size-3.5 shrink-0" />
                    <button type="button" onClick={() => navigate(tab.path)} className="max-w-[150px] truncate">
                      {tab.label}
                    </button>
                    {tab.path !== '/' && (
                      <button
                        type="button"
                        aria-label={`关闭 ${tab.label}`}
                        onClick={() => close(tab.path)}
                        className={cn(
                          'rounded p-0.5 transition-opacity hover:bg-background/80 hover:text-foreground',
                          active ? 'opacity-70' : 'opacity-0 group-hover:opacity-70',
                        )}
                      >
                        <X className="size-3" />
                      </button>
                    )}
                  </div>
                </Fragment>
              )
            })}
          </div>
        </div>

        <main
          className={cn(
            'min-w-0 flex-1 px-4 py-5 lg:px-6 lg:py-6',
            // 流水线编辑页是工作台，铺满整宽；其它页面保持居中的阅读宽度
            /^\/pipelines\/\d+/.test(activePath) ? 'w-full max-w-none' : 'mx-auto w-full max-w-[1440px]',
          )}
        >
          {children}
        </main>
      </div>

      {tabMenu &&
        (() => {
          const index = tabs.findIndex((tab) => tab.path === tabMenu.path)
          const items = [
            { label: '关闭左侧', icon: ChevronLeft, disabled: index <= 1, run: () => closeLeft(tabMenu.path) },
            { label: '关闭右侧', icon: ChevronRight, disabled: index >= tabs.length - 1, run: () => closeRight(tabMenu.path) },
            { label: '关闭其他', icon: X, disabled: tabs.length <= 2, run: () => closeOthers(tabMenu.path) },
            { label: '关闭全部', icon: CircleX, disabled: tabs.length <= 1, run: closeAll },
          ]
          return (
            <div
              data-tab-menu
              style={{
                left: Math.min(tabMenu.x, window.innerWidth - 176),
                top: Math.min(tabMenu.y, window.innerHeight - 176),
              }}
              className="fixed z-50 w-40 rounded-lg border bg-popover p-1 shadow-md"
            >
              {items.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  disabled={item.disabled}
                  onClick={() => {
                    item.run()
                    setTabMenu(null)
                  }}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-40"
                >
                  <item.icon className="size-4 text-muted-foreground" />
                  {item.label}
                </button>
              ))}
            </div>
          )
        })()}
    </div>
  )
}
