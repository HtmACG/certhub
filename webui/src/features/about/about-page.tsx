import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Github, Globe, Info, Mail, RefreshCw, Users } from 'lucide-react'
import { toast } from 'sonner'
import { fetchAbout, fetchUpdates, type UpdatesData } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

function formatDate(value: string) {
  return value ? value.slice(0, 10) : ''
}

export function AboutPage() {
  const queryClient = useQueryClient()
  const about = useQuery({ queryKey: ['meta-about'], queryFn: fetchAbout, staleTime: 10 * 60_000 })
  const updates = useQuery({ queryKey: ['meta-updates'], queryFn: () => fetchUpdates(false), staleTime: 5 * 60_000 })

  const refresh = useMutation({
    mutationFn: () => fetchUpdates(true),
    onSuccess: (data) => {
      queryClient.setQueryData(['meta-updates'], data)
      if (data.error) toast.error(data.error)
      else if (data.updateAvailable) toast.success(`发现新版本 ${data.latest}`)
      else toast.success('已是最新版本')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const data: UpdatesData | undefined = updates.data
  const info = about.data

  return (
    <div className="space-y-5">
      <PageHeader title="关于 CertHub" description="版本、开发者信息与 GitHub 更新记录" />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Info className="size-4" />
              项目信息
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">名称</span>
              <span className="font-medium">{info?.name || 'CertHub'}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">版本</span>
              <Badge variant="info">v{info?.version || '1.0.0'}</Badge>
            </div>
            <div className="flex items-start justify-between gap-3">
              <span className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
                <Users className="size-3.5" />
                开发者
              </span>
              <span className="text-right">
                {(info?.developers ?? ['北慕林奈', '墨韵先知软媒工坊']).map((name) => (
                  <span key={name} className="block font-medium">
                    {name}
                  </span>
                ))}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Globe className="size-3.5" />
                网站
              </span>
              <a
                href={info?.website || 'https://www.htmacg.com'}
                target="_blank"
                rel="noreferrer"
                className="truncate text-primary hover:underline"
              >
                {(info?.website || 'https://www.htmacg.com').replace(/^https?:\/\//, '')}
              </a>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Mail className="size-3.5" />
                邮箱
              </span>
              <a href={`mailto:${info?.email || 'htmacg@163.com'}`} className="text-primary hover:underline">
                {info?.email || 'htmacg@163.com'}
              </a>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Github className="size-3.5" />
                GitHub
              </span>
              <a
                href={info?.repoUrl || 'https://github.com/HtmACG/certhub'}
                target="_blank"
                rel="noreferrer"
                className="truncate text-primary hover:underline"
              >
                {info?.repo || 'HtmACG/certhub'}
              </a>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                <RefreshCw className="size-4" />
                更新记录
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={refresh.isPending}
                onClick={() => refresh.mutate()}
              >
                <RefreshCw className={refresh.isPending ? 'animate-spin' : undefined} />
                检查更新
              </Button>
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {data?.error
                ? data.error
                : data?.updateAvailable
                  ? `发现新版本 ${data.latest}（当前 v${data.current}）`
                  : data
                    ? `已是最新版本（v${data.current}，检查于 ${data.checkedAt}）`
                    : '正在检查 GitHub ...'}
            </p>
          </CardHeader>
          <CardContent className="max-h-[520px] space-y-3 overflow-y-auto">
            {data?.releases?.length ? (
              data.releases.map((release) => (
                <div key={release.tag + release.publishedAt} className="rounded-lg border px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={release.prerelease ? 'muted' : 'success'}>{release.tag || '未命名'}</Badge>
                    <span className="text-sm font-medium">{release.name || release.tag}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{formatDate(release.publishedAt)}</span>
                  </div>
                  {release.body && (
                    <p className="mt-1.5 line-clamp-4 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                      {release.body}
                    </p>
                  )}
                  {release.url && (
                    <a href={release.url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-primary hover:underline">
                      在 GitHub 查看
                    </a>
                  )}
                </div>
              ))
            ) : data?.commits?.length ? (
              data.commits.map((commit) => (
                <div key={commit.sha} className="flex items-start gap-2 rounded-lg border px-3 py-2">
                  <code className="mt-0.5 shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px]">{commit.sha}</code>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{commit.message || '（无提交说明）'}</p>
                    <p className="text-xs text-muted-foreground">
                      {commit.author || '未知作者'} · {formatDate(commit.date)}
                    </p>
                  </div>
                  {commit.url && (
                    <a href={commit.url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
                      查看
                    </a>
                  )}
                </div>
              ))
            ) : (
              <p className="py-10 text-center text-sm text-muted-foreground">
                {data?.error ? '暂时拿不到更新记录' : data ? '这个仓库还没有 Release 或提交记录' : '加载中…'}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <p className="text-xs text-muted-foreground">
        更新检查走 GitHub API，境内服务器如果访问不了，请到「系统设置 → 网络」配置代理；仓库地址可在「系统设置 → 站点信息」里修改。
      </p>
    </div>
  )
}
