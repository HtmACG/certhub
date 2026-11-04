<!--
  仪表盘（车速表样式）
  =========================================================
  工作台「系统信息」看板用它显示 CPU / 内存 / 系统盘使用率：
  底部留口的圆弧 + 外圈刻度 + 指针 + 中间数字读数，读数颜色跟阈值走。

  用 ECharts 的 gauge 系列（不是自己画 SVG）：动画、刻度和暗色主题联动
  都由 useChart / useChartComponent 统一处理，不用重造轮子。
-->
<template>
  <div
    ref="chartRef"
    class="art-gauge-chart relative w-full"
    :style="{ height: props.height }"
    v-loading="props.loading"
  ></div>
</template>

<script setup lang="ts">
  import type { EChartsOption } from '@/plugins/echarts'
  import { useChartComponent } from '@/hooks/core/useChart'
  import { usageColor } from '@/utils/certd'
  import type { GaugeChartProps } from '@/types/component/chart'

  defineOptions({ name: 'ArtGaugeChart' })

  const props = withDefaults(defineProps<GaugeChartProps>(), {
    height: '190px',
    loading: false,
    isEmpty: false,
    value: 0,
    max: 100,
    unit: '%',
    name: '',
    splitNumber: 5,
    decimals: 0,
    color: ''
  })

  const { chartRef, isDark } = useChartComponent({
    props,
    // 值 / 上限 / 指定颜色变化都要重绘（每 5 秒刷新系统信息时走这里）
    watchSources: [() => props.value, () => props.max, () => props.color],
    generateOptions: (): EChartsOption => {
      const max = Number(props.max) > 0 ? Number(props.max) : 100
      const raw = Number(props.value)
      const value = Math.min(max, Math.max(0, Number.isFinite(raw) ? raw : 0))
      const decimals = Math.max(0, Math.min(2, Number(props.decimals) || 0))

      /**
       * canvas 里不能直接用 var(--x)，但可以先把令牌算出来再交给 ECharts。
       * 这样刻度 / 轨道 / 读数颜色跟 shadcn 的 neutral 阶梯是同一套灰，
       * 不再是原来那种偏蓝的 #EDF0F5 / #C9CFDC（Material 的灰，和新主题不是一家）。
       * 取不到时退回同档位的字面值。
       */
      const readToken = (name: string, fallback: string) => {
        if (typeof window === 'undefined') return fallback
        const resolved = getComputedStyle(document.documentElement)
          .getPropertyValue(name)
          .trim()
        return resolved || fallback
      }

      /**
       * usageColor() 返回的是 var(--success) 这类令牌 —— DOM 里能用，canvas 里不行：
       * zrender 不解析 var()，指针 / 进度弧会画成黑色或透明。
       * 这里把 var(--x) 解析成实际颜色再交给 ECharts。
       */
      const resolveColor = (color: string | undefined, fallback: string) => {
        if (!color) return fallback
        const matched = /^var\(\s*(--[\w-]+)\s*\)$/.exec(color.trim())
        return matched ? readToken(matched[1], fallback) : color
      }

      // 指针与进度弧的颜色：没指定就按使用率分档（绿 / 黄 / 红）
      const activeColor = resolveColor(
        props.color || usageColor((value / max) * 100),
        readToken('--success', '#1a7f37')
      )

      const trackColor = readToken('--muted', isDark.value ? '#262626' : '#f5f5f5')
      const tickColor = readToken('--border', isDark.value ? '#404040' : '#d4d4d4')
      const labelColor = readToken('--muted-foreground', isDark.value ? '#a3a3a3' : '#737373')

      return {
        animationDuration: 900,
        animationDurationUpdate: 700,
        animationEasing: 'cubicOut',
        series: [
          {
            type: 'gauge',
            min: 0,
            max,
            // 240° 扫角，底部留口 —— 一条「环形进度」而不是车速表
            startAngle: 210,
            endAngle: -30,
            splitNumber: props.splitNumber,
            radius: '92%',
            center: ['50%', '54%'],
            // 表盘底环
            axisLine: {
              roundCap: true,
              lineStyle: { width: 10, color: [[1, trackColor]] }
            },
            // 当前值弧段
            progress: {
              show: true,
              roundCap: true,
              width: 10,
              itemStyle: { color: activeColor }
            },
            /*
             * 不再画指针和轴心。
             * 弧长 + 中央大数字已经把「用了多少」说清楚了，指针只是第三种表达，
             * 三个并排时那根针和中心圆点是最吵的元素（而且针尖常压在刻度数字上）。
             * 需要指针时把 pointer/anchor 的 show 改回 true 即可。
             */
            pointer: { show: false },
            anchor: { show: false },
            // 小刻度 / 大刻度：细、短、低对比，只做「有余量」的暗示
            axisTick: {
              distance: -10,
              length: 3,
              splitNumber: 4,
              lineStyle: { color: tickColor, width: 1, opacity: 0.7 }
            },
            splitLine: {
              distance: -10,
              length: 6,
              lineStyle: { color: tickColor, width: 1.5, opacity: 0.9 }
            },
            // 刻度数字不再画：百分比用量表里「大数字 + 弧长」已经说明一切，
            // 每个表盘再挂 6 个 0/20/…/100 的小数字，三个并排就是 18 个多余标签，
            // 是这张卡看着「吵」的主要原因。刻度线保留，只做「有余量」的暗示。
            axisLabel: { show: false },
            // 表盘下方的名称（可选）
            title: {
              show: Boolean(props.name),
              offsetCenter: [0, '92%'],
              fontSize: 12,
              color: labelColor
            },
            // 数字读数：放到环的正中间，替代原来「指针 + 底部数字」的双重表达
            detail: {
              valueAnimation: true,
              offsetCenter: [0, '-2%'],
              fontSize: 26,
              fontWeight: 600,
              color: activeColor,
              formatter: (v: number) => Number(v).toFixed(decimals) + props.unit
            },
            data: [{ value, name: props.name }]
          }
        ]
      }
    }
  })
</script>

<style scoped>
  .art-gauge-chart {
    position: relative;
    width: 100%;
  }
</style>
