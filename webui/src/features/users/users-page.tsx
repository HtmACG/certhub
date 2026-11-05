import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderPlus, Pencil, Plus, Trash2, UserPlus, Users } from 'lucide-react'
import { toast } from 'sonner'
import {
  createUser,
  createUserGroup,
  deleteUser,
  deleteUserGroup,
  fetchPermissionCatalog,
  fetchUserGroups,
  fetchUserList,
  updateUser,
  updateUserGroup,
} from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label, Select } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState, TableSkeleton } from '@/components/ui/empty'
import { Pagination } from '@/components/pagination'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

interface UserRow {
  id: number
  userName: string
  nickname: string
  email: string
  role: string
  status: number
  groupId: number
  groupName: string
  totpEnabled: boolean
  createTime?: string
  lastLoginTime?: string
}

const EMPTY_FORM = { username: '', password: '', nickname: '', email: '', role: 'user', groupId: 0 }

export function UsersPage() {
  const [page, setPage] = useState(1)
  const [groupFilter, setGroupFilter] = useState(0)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [groupsOpen, setGroupsOpen] = useState(false)
  const [userToDelete, setUserToDelete] = useState<UserRow | null>(null)
  const [groupForm, setGroupForm] = useState<{ id?: number; name: string; remark: string; permissions: string[] }>({
    name: '',
    remark: '',
    permissions: [],
  })
  const queryClient = useQueryClient()

  const list = useQuery({
    queryKey: ['users', page, groupFilter],
    queryFn: () => fetchUserList({ current: page, size: 12, groupId: groupFilter || undefined }),
  })
  const groups = useQuery({ queryKey: ['user-groups'], queryFn: fetchUserGroups })
  const catalog = useQuery({
    queryKey: ['permission-catalog'],
    queryFn: fetchPermissionCatalog,
    enabled: groupsOpen,
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['users'] })
    void queryClient.invalidateQueries({ queryKey: ['user-groups'] })
  }

  const create = useMutation({
    mutationFn: () =>
      createUser({
        userName: form.username.trim(),
        password: form.password,
        nickname: form.nickname,
        email: form.email,
        role: form.role,
        status: 1,
        groupId: form.groupId,
      }),
    onSuccess: () => {
      toast.success('账号已创建')
      setOpen(false)
      setForm(EMPTY_FORM)
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteUser(id),
    onSuccess: () => {
      toast.success('已删除')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  /** 改状态 / 改用户组都走这条：后端会整条覆盖，没带的字段会被重置，所以一次带全 */
  const patch = useMutation({
    mutationFn: ({ item, groupId, status }: { item: UserRow; groupId?: number; status?: number }) =>
      updateUser(item.id, {
        userName: item.userName,
        password: '',
        nickname: item.nickname,
        email: item.email,
        role: item.role,
        status: status ?? item.status,
        groupId: groupId ?? item.groupId ?? 0,
      }),
    onSuccess: () => void invalidate(),
    onError: (error: Error) => toast.error(error.message),
  })

  const saveGroup = useMutation({
    mutationFn: () => {
      const body = {
        name: groupForm.name.trim(),
        remark: groupForm.remark.trim(),
        permissions: groupForm.permissions,
      }
      return groupForm.id ? updateUserGroup(groupForm.id, body) : createUserGroup(body)
    },
    onSuccess: () => {
      toast.success(groupForm.id ? '用户组已更新' : '用户组已创建')
      setGroupForm({ name: '', remark: '', permissions: [] })
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const removeGroup = useMutation({
    mutationFn: (id: number) => deleteUserGroup(id),
    onSuccess: () => {
      toast.success('用户组已删除，组内账号退回未分组')
      void invalidate()
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const records = (list.data?.records ?? []) as unknown as UserRow[]
  const groupOptions = groups.data ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="用户管理"
        description="管理员可以看全部流水线，普通成员只能看自己的；用户组只做归类，不改变权限"
        actions={
          <>
            <Select
              value={String(groupFilter)}
              onChange={(event) => {
                setGroupFilter(Number(event.target.value))
                setPage(1)
              }}
              className="h-8 w-36 text-sm"
            >
              <option value="0">全部用户组</option>
              {groupOptions.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </Select>
            <Button variant="outline" size="sm" onClick={() => setGroupsOpen(true)}>
              <FolderPlus />
              用户组
            </Button>
            <Button size="sm" onClick={() => setOpen(true)}>
              <UserPlus />
              新建账号
            </Button>
          </>
        }
      />

      <Card className="overflow-hidden">
        {list.isLoading ? (
          <TableSkeleton rows={5} />
        ) : records.length === 0 ? (
          <EmptyState icon={Users} title="还没有用户" description="默认只有一个管理员账号。" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>账号</TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>用户组</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>两步验证</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <p className="font-medium">{item.userName}</p>
                    <p className="text-xs text-muted-foreground">{item.nickname || '—'}</p>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.email || '—'}</TableCell>
                  <TableCell>
                    <Select
                      value={String(item.groupId || 0)}
                      onChange={(event) => patch.mutate({ item, groupId: Number(event.target.value) })}
                      className="h-8 w-36 text-xs"
                    >
                      <option value="0">未分组</option>
                      {groupOptions.map((group) => (
                        <option key={group.id} value={group.id}>
                          {group.name}
                        </option>
                      ))}
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Badge variant={item.role === 'admin' ? 'info' : 'muted'}>{item.role === 'admin' ? '管理员' : '成员'}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={item.totpEnabled ? 'success' : 'muted'}>{item.totpEnabled ? '已开启' : '未开启'}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={item.status === 1 ? 'success' : 'muted'}>{item.status === 1 ? '启用' : '停用'}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => patch.mutate({ item, status: item.status === 1 ? 0 : 1 })}
                      >
                        {item.status === 1 ? '停用' : '启用'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="xs"
                        className="text-destructive hover:bg-destructive/10"
                        onClick={() => setUserToDelete(item)}
                      >
                        删除
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
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建账号</DialogTitle>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>账号</Label>
              <Input value={form.username} onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>密码</Label>
              <Input type="password" value={form.password} onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>昵称</Label>
              <Input value={form.nickname} onChange={(event) => setForm((prev) => ({ ...prev, nickname: event.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>邮箱</Label>
              <Input value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>角色</Label>
              <Select value={form.role} onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value }))}>
                <option value="user">成员</option>
                <option value="admin">管理员</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>用户组</Label>
              <Select
                value={String(form.groupId)}
                onChange={(event) => setForm((prev) => ({ ...prev, groupId: Number(event.target.value) }))}
              >
                <option value="0">未分组</option>
                {groupOptions.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </Select>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button size="sm" disabled={!form.username || !form.password || create.isPending} onClick={() => create.mutate()}>
              <Plus />
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={groupsOpen} onOpenChange={setGroupsOpen}>
        <DialogContent size="lg">
          <DialogHeader>
            <DialogTitle>用户组</DialogTitle>
            <p className="text-sm text-muted-foreground">按团队或用途给账号归类，列表页可以按组筛选；不改变任何权限。</p>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[160px] flex-1 space-y-1.5">
                <Label>名称</Label>
                <Input
                  value={groupForm.name}
                  placeholder="例如：运维组"
                  onChange={(event) => setGroupForm((prev) => ({ ...prev, name: event.target.value }))}
                />
              </div>
              <div className="min-w-[160px] flex-1 space-y-1.5">
                <Label>备注</Label>
                <Input
                  value={groupForm.remark}
                  placeholder="可选"
                  onChange={(event) => setGroupForm((prev) => ({ ...prev, remark: event.target.value }))}
                />
              </div>
              <Button
                size="sm"
                disabled={!groupForm.name.trim() || saveGroup.isPending}
                onClick={() => saveGroup.mutate()}
              >
                {groupForm.id ? '保存' : '添加'}
              </Button>
              {groupForm.id && (
                <Button variant="outline" size="sm" onClick={() => setGroupForm({ name: '', remark: '', permissions: [] })}>
                  取消
                </Button>
              )}
            </div>

            <div className="space-y-2">
              <Label>可使用的功能</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                {(catalog.data ?? []).map((perm) => {
                  const checked = groupForm.permissions.includes(perm.key)
                  return (
                    <label
                      key={perm.key}
                      className="flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-accent"
                    >
                      <input
                        type="checkbox"
                        className="mt-0.5 size-3.5 accent-primary"
                        checked={checked}
                        onChange={(event) =>
                          setGroupForm((prev) => ({
                            ...prev,
                            permissions: event.target.checked
                              ? [...prev.permissions, perm.key]
                              : prev.permissions.filter((key) => key !== perm.key),
                          }))
                        }
                      />
                      <span className="min-w-0">
                        <span className="block font-medium">{perm.name}</span>
                        <span className="block text-xs text-muted-foreground">{perm.desc}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
              <p className="text-xs text-muted-foreground">
                管理员始终拥有全部权限；未勾选的功能在菜单里隐藏，接口层也会拒绝。
                跑流水线的用户通常还要勾「授权管理」，否则编辑器里选不了凭据。
              </p>
            </div>

            <div className="space-y-1">
              {groupOptions.length === 0 && (
                <p className="py-6 text-center text-sm text-muted-foreground">还没有用户组，先在上面添加一个。</p>
              )}
              {groupOptions.map((group) => (
                <div key={group.id} className="flex items-center gap-2 rounded-md border px-3 py-2">
                  <span className="text-sm font-medium">{group.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {group.userCount} 人 · {group.permissions?.length ?? 0} 项权限
                  </span>
                  {group.remark && <span className="truncate text-xs text-muted-foreground">· {group.remark}</span>}
                  <div className="ml-auto flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="编辑"
                      onClick={() =>
                        setGroupForm({
                          id: group.id,
                          name: group.name,
                          remark: group.remark,
                          permissions: group.permissions ?? [],
                        })
                      }
                    >
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="删除"
                      className="text-destructive hover:bg-destructive/10"
                      onClick={() => {
                        if (confirm(`删除用户组「${group.name}」？组内账号会退回未分组。`)) removeGroup.mutate(group.id)
                      }}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setGroupsOpen(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={!!userToDelete} onOpenChange={(next) => !next && setUserToDelete(null)}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>删除账号</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <p className="text-sm leading-relaxed">
              删除账号「{userToDelete?.userName}」后，该账号将无法登录；它名下的流水线、授权、证书不会自动转移。
            </p>
            <p className="mt-2 text-xs text-muted-foreground">只是临时不让登录的话，用「停用」更合适。</p>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setUserToDelete(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={remove.isPending}
              onClick={() => {
                if (userToDelete) remove.mutate(userToDelete.id)
                setUserToDelete(null)
              }}
            >
              删除账号
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
