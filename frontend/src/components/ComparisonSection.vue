<script setup lang="ts">
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use, type ECharts } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { compareCourse } from '@/api/evaluations'
import { ApiError } from '@/types/api'
import { DIMENSION_KEYS, type ComparisonResult } from '@/types/evaluation'
import { DIMENSION_LABELS } from '@/utils/dimensions'
import { formatDateTime, formatScore } from '@/utils/format'

use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  courseId: number
}>()

const loading = ref(false)
const error = ref<Error | null>(null)
const result = ref<ComparisonResult | null>(null)
const chartEl = ref<HTMLDivElement>()
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const insufficient = computed(() => !loading.value && !error.value && result.value === null)

function renderChart(data: ComparisonResult): void {
  if (!chartEl.value) return
  chart ??= init(chartEl.value)
  const latest = DIMENSION_KEYS.map((key) => data.latest.dimension_scores[key] ?? 0)
  const previous = DIMENSION_KEYS.map((key) => data.previous.dimension_scores[key] ?? 0)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['本次', '上次'], top: 0 },
    grid: { left: 8, right: 8, top: 36, bottom: 0, containLabel: true },
    xAxis: {
      type: 'category',
      data: DIMENSION_KEYS.map((key) => DIMENSION_LABELS[key]),
      axisLabel: { color: '#5c6b73' },
    },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: '#5c6b73' } },
    series: [
      {
        name: '本次',
        type: 'bar',
        data: latest,
        itemStyle: { color: '#175e6b' },
        barMaxWidth: 18,
      },
      {
        name: '上次',
        type: 'bar',
        data: previous,
        itemStyle: { color: '#b9cfd3' },
        barMaxWidth: 18,
      },
    ],
  })
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    result.value = await compareCourse(props.courseId)
  } catch (err) {
    result.value = null
    error.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  if (chartEl.value) resizeObserver.observe(chartEl.value)
})

watch(
  () => props.courseId,
  () => void load(),
)

watch(
  () => result.value,
  (data) => {
    if (data) {
      // 等待 DOM 渲染后再初始化图表
      requestAnimationFrame(() => renderChart(data))
    }
  },
  { deep: true },
)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div v-loading="loading" class="comparison">
    <template v-if="error">
      <el-empty :description="error instanceof ApiError ? error.message : '对比数据加载失败'">
        <el-button type="primary" @click="load">重试</el-button>
      </el-empty>
    </template>

    <el-empty v-else-if="insufficient" description="至少需要两次已完成评价才能对比">
      <span class="text-secondary">上传并处理两节课堂录音后，这里将展示总分与六维变化</span>
    </el-empty>

    <template v-else-if="result">
      <div class="summary-cards">
        <div class="summary-card">
          <div class="summary-label">本次总分</div>
          <div class="summary-value tabular">{{ formatScore(result.latest.overall_score) }}</div>
          <div class="summary-meta tabular">{{ formatDateTime(result.latest.recorded_at) }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">上次总分</div>
          <div class="summary-value tabular">{{ formatScore(result.previous.overall_score) }}</div>
          <div class="summary-meta tabular">{{ formatDateTime(result.previous.recorded_at) }}</div>
        </div>
        <div class="summary-card summary-card--delta">
          <div class="summary-label">总分变化</div>
          <div
            class="summary-value tabular"
            :class="result.delta.overall_score >= 0 ? 'delta-up' : 'delta-down'"
          >
            {{ result.delta.overall_score >= 0 ? '+' : '' }}{{ result.delta.overall_score.toFixed(1) }}
          </div>
          <div class="summary-meta">较上次课堂</div>
        </div>
      </div>

      <h4 class="comparison-subtitle">BOPPPS 六维对比</h4>
      <div ref="chartEl" class="comparison-chart" />
    </template>
  </div>
</template>

<style scoped>
.comparison {
  min-height: 200px;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.summary-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.summary-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.summary-value {
  font-size: 26px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
}

.summary-card--delta .summary-value.delta-up {
  color: var(--success);
}

.summary-card--delta .summary-value.delta-down {
  color: var(--danger);
}

.summary-meta {
  font-size: 12px;
  color: var(--text-placeholder);
}

.comparison-subtitle {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.comparison-chart {
  width: 100%;
  height: 280px;
}
</style>
