import { useState } from 'react'
import { ImagePlus, Trash2, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const MAX_BYTES = 1024 * 1024

function readAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('读取文件失败'))
    reader.readAsDataURL(file)
  })
}

/** 图片上传：转 data URI 存进设置，原图限制 1MB（base64 后会更大，但数据库存的是文本） */
export function ImageUploader({
  label,
  hint,
  value,
  onChange,
  aspect = 'square',
}: {
  label: string
  hint: string
  value?: string
  onChange: (value: string) => void
  aspect?: 'square' | 'wide'
}) {
  const [busy, setBusy] = useState(false)

  const pick = async (file: File | undefined) => {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      toast.error('只支持图片文件')
      return
    }
    if (file.size > MAX_BYTES) {
      toast.error(`图片不能超过 1MB（当前 ${(file.size / 1024 / 1024).toFixed(2)}MB）`)
      return
    }
    setBusy(true)
    try {
      onChange(await readAsDataUrl(file))
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <label className="inline-flex cursor-pointer items-center">
            <input
              type="file"
              accept="image/*"
              className="hidden"
              disabled={busy}
              onChange={(event) => {
                void pick(event.target.files?.[0])
                event.target.value = ''
              }}
            />
            <Button asChild variant="outline" size="sm" disabled={busy}>
              <span>
                <Upload />
                {value ? '更换' : '上传'}
              </span>
            </Button>
          </label>
          {value && (
            <Button
              variant="ghost"
              size="icon-sm"
              className="text-destructive hover:bg-destructive/10"
              onClick={() => onChange('')}
              title="移除"
            >
              <Trash2 />
            </Button>
          )}
        </div>
      </div>

      <div
        className={cn(
          'flex items-center justify-center overflow-hidden rounded-lg border bg-muted/30',
          aspect === 'square' ? 'size-16' : 'h-24 w-44',
        )}
      >
        {value ? (
          <img src={value} alt={label} className="size-full object-contain" />
        ) : (
          <div className="flex flex-col items-center gap-1 text-muted-foreground">
            <ImagePlus className="size-4" />
            <span className="text-[10px]">未设置</span>
          </div>
        )}
      </div>
    </div>
  )
}
