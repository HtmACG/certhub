import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { AppShell } from '@/components/layout/app-shell'
import { LoginPage } from '@/features/auth/login-page'
import { DashboardPage } from '@/features/dashboard/dashboard-page'
import { PipelinesPage } from '@/features/pipelines/pipelines-page'
import { PipelineEditorPage } from '@/features/pipelines/pipeline-editor-page'
import { HistoryPage } from '@/features/history/history-page'
import { CertsPage } from '@/features/certs/certs-page'
import { AccessPage } from '@/features/access/access-page'
import { NotificationsPage } from '@/features/notifications/notifications-page'
import { DnsPage } from '@/features/dns/dns-page'
import { MonitorPage } from '@/features/monitor/monitor-page'
import { SettingsPage } from '@/features/settings/settings-page'
import { UsersPage } from '@/features/users/users-page'
import { AuditPage } from '@/features/system/audit-page'
import { ApiKeysPage } from '@/features/system/api-keys-page'
import { AccountPage } from '@/features/account/account-page'
import { AboutPage } from '@/features/about/about-page'

function Protected({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth()
  const location = useLocation()

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <AppShell>{children}</AppShell>
}

function NoAccess() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="max-w-md space-y-2 text-center">
        <p className="text-lg font-semibold">没有访问权限</p>
        <p className="text-sm text-muted-foreground">
          这个功能不在你所在用户组的权限范围内，需要的话联系管理员调整用户组权限。
        </p>
      </div>
    </div>
  )
}

/** 路由级权限：管理员放行；其余按用户组勾选的权限键判断 */
function Guard({
  perm,
  adminOnly,
  children,
}: {
  perm?: string
  adminOnly?: boolean
  children: React.ReactNode
}) {
  const { user } = useAuth()
  if (!user) return null
  if (user.role === 'admin') return <>{children}</>
  if (adminOnly) return <NoAccess />
  if (perm && !(user.permissions ?? []).includes(perm)) return <NoAccess />
  return <>{children}</>
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Protected>
            <DashboardPage />
          </Protected>
        }
      />
      <Route
        path="/pipelines"
        element={
          <Protected>
            <Guard perm="pipelines">
              <PipelinesPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/pipelines/:id"
        element={
          <Protected>
            <Guard perm="pipelines">
              <PipelineEditorPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/history"
        element={
          <Protected>
            <Guard perm="history">
              <HistoryPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/certs"
        element={
          <Protected>
            <Guard perm="certs">
              <CertsPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/access"
        element={
          <Protected>
            <Guard perm="access">
              <AccessPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/notifications"
        element={
          <Protected>
            <Guard perm="notifications">
              <NotificationsPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/dns"
        element={
          <Protected>
            <Guard perm="dns">
              <DnsPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/monitor"
        element={
          <Protected>
            <Guard perm="monitor">
              <MonitorPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/settings"
        element={
          <Protected>
            <Guard adminOnly>
              <SettingsPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/users"
        element={
          <Protected>
            <Guard adminOnly>
              <UsersPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/audit"
        element={
          <Protected>
            <Guard adminOnly>
              <AuditPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/api-keys"
        element={
          <Protected>
            <Guard adminOnly>
              <ApiKeysPage />
            </Guard>
          </Protected>
        }
      />
      <Route
        path="/account"
        element={
          <Protected>
            <AccountPage />
          </Protected>
        }
      />
      <Route
        path="/about"
        element={
          <Protected>
            <AboutPage />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
