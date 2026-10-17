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
  dimensionScores: Partial<Record<DimensionKey, number>>
}>()

const chartEl = ref<HTMLDivElement>()
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const hasData = computed(() => DIMENSION_KEYS.some((key) => props.dimensionScores[key] !== undefined))

function render(): void {
  if (!chartEl.value) return
  if (!hasData.value) return
  chart ??= init(chartEl.value)
  const indicators = DIMENSION_KEYS.map((key) => ({
    name: DIMENSION_LABELS[key],
    max: 100,
  }))
  const values = DIMENSION_KEYS.map((key) => props.dimensionScores[key] ?? 0)
  chart.setOption({
    radar: {
      indicator: indicators,
      radius: '65%',
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
    <div v-if="!hasData" class="radar-placeholder">
      <el-empty description="基础评价未包含六维分数" :image-size="56" />
    </div>
    <div v-show="hasData" ref="chartEl" class="radar-chart" />
  </div>
</template>

<style scoped>
.radar-wrap {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.radar-chart {
  width: 100%;
  max-width: 420px;
  height: 260px;
}

.radar-placeholder {
  width: 100%;
}
</style>
