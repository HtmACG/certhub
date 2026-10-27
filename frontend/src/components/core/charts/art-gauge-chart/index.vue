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
      // 指针与进度弧的颜色：没指定就按使用率分档（绿 / 黄 / 红）
      const activeColor = props.color || usageColor((value / max) * 100)
      // canvas 里读不到 CSS 变量，暗色模式按明暗各给一套配色
      const trackColor = isDark.value ? '#2f3440' : '#EDF0F5'
      const tickColor = isDark.value ? '#565e6d' : '#C9CFDC'
      const labelColor = isDark.value ? '#8a93a6' : '#9AA1B2'
      const anchorBorder = isDark.value ? '#23262d' : '#ffffff'

      return {
        animationDuration: 900,
        animationDurationUpdate: 700,
        animationEasing: 'cubicOut',
        series: [
          {
            type: 'gauge',
            min: 0,
            max,
            // 240° 扫角，底部留口 —— 车速表那种感觉
            startAngle: 210,
            endAngle: -30,
            splitNumber: props.splitNumber,
            // 半径放大一点 + 刻度数字放到环内侧，外圈留白，
            // 免得窄高度画布把刻度数字裁掉（用户反馈「刻度被遮挡」）
            radius: '92%',
            center: ['50%', '58%'],
            // 表盘底环
            axisLine: {
              roundCap: true,
              lineStyle: { width: 12, color: [[1, trackColor]] }
            },
            // 当前值弧段
            progress: {
              show: true,
              roundCap: true,
              width: 12,
              itemStyle: { color: activeColor }
            },
            // 指针：长度略微收短，避免指向某个刻度数字时正好压在数字上
            pointer: {
              show: true,
              length: '38%',
              width: 4,
              offsetCenter: [0, '4%'],
              itemStyle: { color: activeColor }
            },
            // 指针轴心
            anchor: {
              show: true,
              showAbove: true,
              size: 12,
              itemStyle: {
                color: activeColor,
                borderColor: anchorBorder,
                borderWidth: 2
              }
            },
            // 小刻度 / 大刻度
            axisTick: {
              distance: -12,
              length: 4,
              splitNumber: 4,
              lineStyle: { color: tickColor, width: 1 }
            },
            splitLine: {
              distance: -12,
              length: 9,
              lineStyle: { color: tickColor, width: 2 }
            },
            // 刻度数字画在表盘内侧（ECharts 的 gauge 里正数距离 = 往里收，
            // 它会扣掉 splitLine 的长度和 splitLine.distance），
            // 这样数字不会贴到画布边缘被裁掉，也不会被圆弧/指针压住。
            // 公式：数字半径 = radius - splitLine.length - (distance + splitLine.distance)
            axisLabel: {
              distance: 30,
              fontSize: 11,
              color: labelColor,
              formatter: (v: number) => String(Math.round(v))
            },
            // 表盘下方的名称（可选）
            title: {
              show: Boolean(props.name),
              offsetCenter: [0, '88%'],
              fontSize: 12,
              color: labelColor
            },
            // 数字读数：放在底部留口的下方，和指针不打架（车速表的数字表位置）
            detail: {
              valueAnimation: true,
              offsetCenter: [0, '58%'],
              fontSize: 24,
              fontWeight: 700,
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
