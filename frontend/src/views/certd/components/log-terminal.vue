<!--
  日志终端（黑底 + 语法高亮 + 复制 / 清空）
  =========================================================
  1. 背景固定黑色：日志是「看数据」，不要跟主题一起变白，白底看 PEM / JSON 更累；
  2. 「高亮」用分词渲染，每段一个 span —— **不用 v-html**
     （日志里有用户填的域名、密钥路径，禁止把用户内容当 HTML 注入）；
  3. 不放复制 / 清空 / 跟随开关：跟随是默认行为（往上翻自动暂停，滚回底部继续）；
  4. accent 传入阶段主题色，不同阶段的终端一眼可区分。
-->
<template>
  <div
    class="log-terminal"
    :class="{ 'is-accented': !!accent }"
    :style="accent ? { '--log-accent': accent } : undefined"
  >
    <div v-if="showHeader || $slots.actions" class="log-terminal-head">
      <div class="log-terminal-title">
        <ArtSvgIcon icon="ri:terminal-box-line" />
        <span>{{ title || '日志' }}</span>
        <span class="log-terminal-count">{{ lines.length }} 行</span>
      </div>
      <div v-if="$slots.actions" class="log-terminal-actions">
        <slot name="actions" />
      </div>
    </div>

    <div ref="boxRef" class="log-terminal-body" :style="{ height }" @scroll="onScroll">
      <p v-if="!lines.length" class="log-terminal-empty">{{ emptyText }}</p>
      <p v-for="(line, index) in lines" :key="index" class="log-line">
        <span v-for="(token, tokenIndex) in tokenize(line)" :key="tokenIndex" :class="token.cls">
          {{ token.text }}
        </span>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
  defineOptions({ name: 'LogTerminal' })

  interface Props {
    /** 日志行 */
    lines: string[]
    /** 标题（可选） */
    title?: string
    /** 内容区高度，默认自适应 */
    height?: string
    /** 是否显示头（标题 + 行数） */
    showHeader?: boolean
    /** 没有日志时的提示 */
    emptyText?: string
    /** 主题色：不同阶段的日志终端用各自的阶段色，一眼能区分是哪一段 */
    accent?: string
  }

  const props = withDefaults(defineProps<Props>(), {
    title: '',
    height: '100%',
    showHeader: true,
    emptyText: '暂无日志',
    accent: '',
  })

  const boxRef = ref<HTMLElement>()
  /** 默认跟随最新日志；用户往上翻时自动暂停，滚回底部再继续（不提供开关按钮） */
  const autoScroll = ref(true)

  const scrollToBottom = () => {
    const box = boxRef.value
    if (!box || !autoScroll.value) return
    box.scrollTop = box.scrollHeight
  }

  const onScroll = () => {
    const box = boxRef.value
    if (!box) return
    // 用户往上翻看历史时不强行拽回底部
    autoScroll.value = box.scrollHeight - box.scrollTop - box.clientHeight < 40
  }

  watch(
    () => props.lines.length,
    () => nextTick(scrollToBottom)
  )

  interface Token {
    text: string
    cls: string
  }

  /** 剩余文本里的高亮规则：URL / PEM / JSON / 关键字 / IP */
  const INLINE_RULES: { re: RegExp; cls: string }[] = [
    { re: /https?:\/\/[^\s，,)'"]+/g, cls: 'is-url' },
    { re: /-----BEGIN[^-]*-----|-----END[^-]*-----/g, cls: 'is-pem' },
    { re: /"(?:[^"\\]|\\.)*"\s*:/g, cls: 'is-key' },
    { re: /"(?:[^"\\]|\\.)*"/g, cls: 'is-string' },
    { re: /\b\d{1,3}(?:\.\d{1,3}){3}\b/g, cls: 'is-ip' },
    {
      re: /成功|通过|完成|就绪|success|已完成|验证通过|部署完成|执行成功/gi,
      cls: 'is-ok',
    },
    {
      re: /失败|错误|异常|超时|拒绝|失败：|failed|error|exception|traceback|invalid/gi,
      cls: 'is-error',
    },
    { re: /警告|重试|跳过|未生效|warn/gi, cls: 'is-warn' },
  ]

  const STAGE_LINE = /^=+\s*阶段[:：].*=+$/

  /**
   * 把一行日志切成「带颜色的小段」。
   * 先摘出时间戳 / 阶段分隔 / [任务名]，剩下的再按规则找 URL、PEM、关键字。
   */
  const tokenize = (line: string): Token[] => {
    const tokens: Token[] = []
    const push = (text: string, cls: string) => {
      if (text) tokens.push({ text, cls })
    }

    let rest = line
    const timeMatch = /^(\[\d{2}:\d{2}:\d{2}\]\s*)/.exec(rest)
    if (timeMatch) {
      push(timeMatch[1], 'is-time')
      rest = rest.slice(timeMatch[0].length)
    }

    if (STAGE_LINE.test(rest)) {
      push(rest, 'is-stage')
      return tokens
    }

    const taskMatch = /^(\[[^\]]{1,40}\]\s*)/.exec(rest)
    if (taskMatch && !/^\[(?:info|warn|error)\]/i.test(taskMatch[1])) {
      push(taskMatch[1], 'is-task')
      rest = rest.slice(taskMatch[0].length)
    }

    // 在剩余文本里找所有规则命中，按位置切片
    const hits: { start: number; end: number; cls: string }[] = []
    for (const rule of INLINE_RULES) {
      rule.re.lastIndex = 0
      let match = rule.re.exec(rest)
      while (match) {
        const start = match.index
        const end = start + match[0].length
        const overlapped = hits.some((hit) => start < hit.end && end > hit.start)
        if (!overlapped) hits.push({ start, end, cls: rule.cls })
        match = rule.re.exec(rest)
      }
    }
    hits.sort((left, right) => left.start - right.start)

    let cursor = 0
    for (const hit of hits) {
      if (hit.start > cursor) push(rest.slice(cursor, hit.start), '')
      push(rest.slice(hit.start, hit.end), hit.cls)
      cursor = hit.end
    }
    if (cursor < rest.length) push(rest.slice(cursor), '')
    return tokens
  }
</script>

<style scoped>
  .log-terminal {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    /* 日志恒为黑底：不跟随主题，白底看 PEM / JSON 太累 */
    background: #0b0e14;
    border: 1px solid #1f2430;
    border-radius: 10px;
  }

  /* 传入 accent 时，用阶段色描边 + 标题着色：不同阶段的日志终端长得不一样 */
  .log-terminal.is-accented {
    border-left: 3px solid var(--log-accent, #1f2430);
  }

  .log-terminal.is-accented .log-terminal-title {
    color: var(--log-accent, #c9d1d9);
  }

  .log-terminal.is-accented .log-terminal-title :deep(svg) {
    color: var(--log-accent, currentColor);
  }

  .log-terminal-head {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    padding: 6px 10px;
    background: #11151c;
    border-bottom: 1px solid #1f2430;
  }

  .log-terminal-title {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 12.5px;
    color: #c9d1d9;
  }

  .log-terminal-count {
    color: #6e7781;
  }

  .log-terminal-actions {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .log-terminal-actions :deep(.el-button) {
    flex: 0 0 auto;
  }

  .log-terminal-body {
    flex: 1;
    min-height: 80px;
    padding: 8px 12px;
    overflow: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
    font-size: 12px;
    line-height: 1.7;
    background: #0b0e14;
  }

  .log-line {
    margin: 0;
    color: #c9d1d9;
    white-space: pre-wrap;
    word-break: break-all;
  }

  .log-terminal-empty {
    margin: 8px 0;
    color: #6e7781;
  }

  .log-line :deep(.is-time),
  .log-line .is-time {
    color: #7d8590;
  }

  .log-line .is-stage {
    font-weight: 600;
    color: #a371f7;
  }

  .log-line .is-task {
    font-weight: 600;
    color: #58a6ff;
  }

  .log-line .is-url {
    color: #79c0ff;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .log-line .is-pem {
    color: #d2a8ff;
  }

  .log-line .is-key {
    color: #7ee787;
  }

  .log-line .is-string {
    color: #a5d6ff;
  }

  .log-line .is-ip {
    color: #ffa657;
  }

  .log-line .is-ok {
    color: #3fb950;
  }

  .log-line .is-error {
    color: #f85149;
  }

  .log-line .is-warn {
    color: #d29922;
  }
</style>
