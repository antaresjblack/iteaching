<script setup lang="ts">
import { RadarChart } from 'echarts/charts'
import { RadarComponent, TooltipComponent } from 'echarts/components'
import { init, use, type ECharts } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { DIMENSION_KEYS, type DimensionKey } from '@/types/evaluation'
import { DIMENSION_LABELS } from '@/utils/dimensions'

use([RadarChart, RadarComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  dimensionScores: Partial<Record<DimensionKey, number | null>>
}>()

const chartEl = ref<HTMLDivElement>()
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const isScored = (key: DimensionKey): boolean => typeof props.dimensionScores[key] === 'number'

/** 仅在图中以0占位，实际空分不改变。 */
const hasMissing = computed(() => DIMENSION_KEYS.some((key) => !isScored(key)))

function render(): void {
  if (!chartEl.value) return
  chart ??= init(chartEl.value)
  const indicators = DIMENSION_KEYS.map((key) => ({
    name: DIMENSION_LABELS[key] + (isScored(key) ? '' : '\n（证据不足）'),
    max: 100,
  }))
  const values = DIMENSION_KEYS.map((key) => (isScored(key) ? props.dimensionScores[key] as number : 0))
  chart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: () => DIMENSION_KEYS.map((key) =>
        `${DIMENSION_LABELS[key]}：${isScored(key) ? props.dimensionScores[key] + ' 分' : '证据不足（图中按0占位）'}`,
      ).join('<br/>'),
    },
    radar: {
      indicator: indicators,
      radius: '55%',
      axisName: { color: '#5c6b73', fontSize: 12 },
      splitArea: { areaStyle: { color: ['#f4f6f7', '#ffffff'] } },
      splitLine: { lineStyle: { color: '#dce3e6' } },
      axisLine: { lineStyle: { color: '#dce3e6' } },
    },
    series: [
      {
        type: 'radar',
        data: [{ value: values, name: '评分' }],
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: '#175e6b', width: 2 },
        itemStyle: { color: '#175e6b' },
        areaStyle: { color: 'rgba(23, 94, 107, 0.18)' },
      },
    ],
  })
}

onMounted(() => {
  render()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  if (chartEl.value) resizeObserver.observe(chartEl.value)
})

watch(() => props.dimensionScores, render, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="radar-wrap">
    <div ref="chartEl" class="radar-chart" />
    <p v-if="hasMissing" class="radar-note">证据不足的维度在图中按 0 占位，不代表实际得分，不计入已观察维度均分。</p>
  </div>
</template>

<style scoped>
.radar-wrap {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.radar-chart {
  width: 100%;
  max-width: 420px;
  height: 300px;
}

.radar-note {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
