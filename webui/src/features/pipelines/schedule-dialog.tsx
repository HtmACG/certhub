import { useEffect, useMemo, useState } from 'react'
import { CalendarClock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input, Label, Select } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export type ScheduleMode = 'off' | 'daily' | 'weekly' | 'monthly' | 'custom'

export interface ScheduleValue {
  enabled: boolean
  cron: string
}

const WEEKDAYS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 0, label: '周日' },
]

const pad = (value: number) => String(value).padStart(2, '0')

/** 把 cron 反推成「每天 03:00 / 每周一 02:00 / 每月 1 日 04:00」，认不出就原样显示 */
export function describeCron(cron?: string) {
  if (!cron || !cron.trim()) return ''
  const text = cron.trim()
  const daily = /^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*$/.exec(text)
  if (daily) return `每天 ${pad(Number(daily[2]))}:${pad(Number(daily[1]))}`
  const weekly = /^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+([0-6])$/.exec(text)
  if (weekly) {
    const day = WEEKDAYS.find((item) => item.value === Number(weekly[3]))?.label || '周日'
    return `${day} ${pad(Number(weekly[2]))}:${pad(Number(weekly[1]))}`
  }
  const monthly = /^(\d{1,2})\s+(\d{1,2})\s+1\s+\*\s+\*$/.exec(text)
  if (monthly) return `每月 1 日 ${pad(Number(monthly[2]))}:${pad(Number(monthly[1]))}`
  return text
}

function parse(cron: string | undefined, enabled: boolean) {
  const text = (cron || '').trim()
  const time = /^(\d{1,2})\s+(\d{1,2})\s+/.exec(text)
  const hhmm = time ? `${pad(Number(time[2]))}:${pad(Number(time[1]))}` : '03:00'
  const weekly = /^\d{1,2}\s+\d{1,2}\s+\*\s+\*\s+([0-6])$/.exec(text)
  const monthly = /^\d{1,2}\s+\d{1,2}\s+1\s+\*\s+\*$/.exec(text)
  const daily = /^\d{1,2}\s+\d{1,2}\s+\*\s+\*\s+\*$/.exec(text)

  let mode: ScheduleMode = 'custom'
  if (!text) mode = 'daily'
  else if (daily) mode = 'daily'
  else if (weekly) mode = 'weekly'
  else if (monthly) mode = 'monthly'

  return {
    enabled,
    mode,
    time: hhmm,
    weekday: weekly ? Number(weekly[1]) : 1,
    custom: text,
  }
}

export function ScheduleDialog({
  open,
  onOpenChange,
  cron,
  enabled,
  saving,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  cron?: string
  enabled: boolean
  saving?: boolean
  onSave: (value: ScheduleValue) => void
}) {
  const initial = useMemo(() => parse(cron, enabled), [cron, enabled])
  const [mode, setMode] = useState<ScheduleMode>(initial.mode)
  const [runEnabled, setRunEnabled] = useState(enabled)
  const [time, setTime] = useState(initial.time)
  const [weekday, setWeekday] = useState(initial.weekday)
  const [custom, setCustom] = useState(initial.custom)

  useEffect(() => {
    if (!open) return
    setMode(initial.mode)
    setRunEnabled(enabled)
    setTime(initial.time)
    setWeekday(initial.weekday)
    setCustom(initial.custom)
  }, [open, initial, enabled])

  const [hour, minute] = time.split(':').map((item) => Number(item) || 0)
  const cronValue =
    mode === 'off'
      ? ''
      : mode === 'custom'
        ? custom.trim()
        : mode === 'daily'
          ? `${minute} ${hour} * * *`
          : mode === 'weekly'
            ? `${minute} ${hour} * * ${weekday}`
            : `${minute} ${hour} 1 * *`

  const summary = mode === 'off' || !cronValue ? '不定时运行' : describeCron(cronValue)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarClock className="size-4" />
            定时运行
          </DialogTitle>
          <p className="text-sm text-muted-foreground">按日历选就行，不用自己背 cron。</p>
        </DialogHeader>

        <DialogBody className="space-y-5">
          <div className="flex items-center gap-2">
            <Switch checked={runEnabled && mode !== 'off'} onChange={setRunEnabled} label="启用定时" />
            <span className="text-sm text-muted-foreground">
              {runEnabled && mode !== 'off' ? '到点自动运行这条流水线' : '只手动运行'}
            </span>
          </div>

          <div className="space-y-1.5">
            <Label>频率</Label>
            <Select
              value={mode}
              onChange={(event) => {
                const next = event.target.value as ScheduleMode
                setMode(next)
                if (next !== 'off') setRunEnabled(true)
              }}
            >
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="monthly">每月 1 日</option>
              <option value="custom">自定义 cron</option>
              <option value="off">不启用</option>
            </Select>
          </div>

          {mode !== 'custom' && mode !== 'off' && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>时间</Label>
                <Input type="time" value={time} onChange={(event) => setTime(event.target.value || '03:00')} />
              </div>
              {mode === 'weekly' && (
                <div className="space-y-1.5">
                  <Label>星期</Label>
                  <Select value={String(weekday)} onChange={(event) => setWeekday(Number(event.target.value))}>
                    {WEEKDAYS.map((day) => (
                      <option key={day.value} value={day.value}>
                        {day.label}
                      </option>
                    ))}
                  </Select>
                </div>
              )}
            </div>
          )}

          {mode === 'custom' && (
            <div className="space-y-1.5">
              <Label>cron 表达式</Label>
              <Input
                value={custom}
                onChange={(event) => setCustom(event.target.value)}
                placeholder="0 3 * * *"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">五段式：分 时 日 月 周。例如 `0 3 * * *` 是每天 03:00。</p>
            </div>
          )}

          <div className="rounded-lg border bg-muted/40 px-3 py-2.5 text-sm">
            <p className="font-medium">{summary}</p>
            <p className="mt-0.5 font-mono text-xs text-muted-foreground">{cronValue || '不设置触发器'}</p>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            size="sm"
            disabled={saving || (mode === 'custom' && !custom.trim())}
            onClick={() => onSave({ enabled: runEnabled && mode !== 'off', cron: cronValue })}
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
