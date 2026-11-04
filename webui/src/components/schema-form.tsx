import { useMemo, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import type { PluginField } from '@/lib/types'
import { Input, Label, Select, Textarea } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

export interface AccessOption {
  id: number
  name: string
  type: string
  category?: string
}

function visible(field: PluginField, values: Record<string, unknown>) {
  const rule = field.showWhen
  if (!rule) return true
  const rules = Array.isArray(rule) ? rule : [rule]
  return rules.every((item) => {
    const current = values[item.key]
    if (item.values) return item.values.includes(current)
    return current === item.value
  })
}

function FieldControl({
  field,
  value,
  onChange,
  accessOptions,
}: {
  field: PluginField
  value: unknown
  onChange: (value: unknown) => void
  accessOptions: AccessOption[]
}) {
  const [revealed, setRevealed] = useState(false)
  const component = field.component || 'text'

  if (component === 'password') {
    return (
      <div className="relative">
        <Input
          type={revealed ? 'text' : 'password'}
          value={(value as string) ?? ''}
          placeholder={field.placeholder || '留空表示不修改'}
          onChange={(event) => onChange(event.target.value)}
          className="pr-9"
        />
        <button
          type="button"
          onClick={() => setRevealed((prev) => !prev)}
          className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-1.5 text-muted-foreground hover:bg-accent"
          aria-label={revealed ? '隐藏' : '显示'}
        >
          {revealed ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
        </button>
      </div>
    )
  }

  if (component === 'select') {
    return (
      <Select value={(value as string) ?? ''} onChange={(event) => onChange(event.target.value)}>
        <option value="">请选择</option>
        {(field.options || []).map((option) => (
          <option key={String(option.value)} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </Select>
    )
  }

  if (component === 'access') {
    const options = accessOptions.filter((item) => {
      if (field.accessTypes?.length) return field.accessTypes.includes(item.type)
      if (field.accessCategory) return item.category === field.accessCategory
      return true
    })
    return (
      <Select value={(value as string) ?? ''} onChange={(event) => onChange(Number(event.target.value) || '')}>
        <option value="">请选择授权</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </Select>
    )
  }

  if (component === 'switch' || typeof field.default === 'boolean') {
    return (
      <div className="flex h-9 items-center">
        <Switch checked={Boolean(value)} onChange={(next) => onChange(next)} label={field.title} />
      </div>
    )
  }

  if (component === 'number') {
    return (
      <Input
        type="number"
        value={(value as number) ?? ''}
        placeholder={field.placeholder}
        onChange={(event) => onChange(event.target.value === '' ? '' : Number(event.target.value))}
      />
    )
  }

  if (component === 'textarea') {
    return (
      <Textarea
        value={(value as string) ?? ''}
        placeholder={field.placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    )
  }

  if (component === 'tags') {
    const list = Array.isArray(value) ? (value as string[]) : value ? String(value).split(',') : []
    return (
      <Input
        value={list.join(', ')}
        placeholder={field.placeholder || '多个值用逗号分隔，例如 foo.com, *.foo.com'}
        onChange={(event) =>
          onChange(
            event.target.value
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean),
          )
        }
      />
    )
  }

  return (
    <Input
      value={(value as string) ?? ''}
      placeholder={field.placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  )
}

export function SchemaFields({
  fields,
  values,
  onChange,
  accessOptions = [],
  columns = 2,
}: {
  fields: PluginField[]
  values: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  accessOptions?: AccessOption[]
  columns?: 1 | 2
}) {
  const groups = useMemo(() => {
    const map = new Map<string, PluginField[]>()
    fields.filter((field) => visible(field, values)).forEach((field) => {
      const key = field.group || ''
      map.set(key, [...(map.get(key) ?? []), field])
    })
    return Array.from(map.entries())
  }, [fields, values])

  return (
    <div className="space-y-5">
      {groups.map(([group, items]) => (
        <section key={group} className="space-y-3">
          {group && <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{group}</p>}
          <div className={cn('grid gap-4', columns === 2 ? 'sm:grid-cols-2' : 'grid-cols-1')}>
            {items.map((field) => (
              <div
                key={field.key}
                className={cn('space-y-1.5', field.component === 'textarea' && 'sm:col-span-2')}
              >
                <div className="flex items-center gap-1">
                  <Label htmlFor={field.key}>
                    {field.title}
                    {field.required && <span className="ml-0.5 text-destructive">*</span>}
                  </Label>
                </div>
                <FieldControl
                  field={field}
                  value={values[field.key]}
                  onChange={(next) => onChange(field.key, next)}
                  accessOptions={accessOptions}
                />
                {field.helper && <p className="text-xs leading-relaxed text-muted-foreground">{field.helper}</p>}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
