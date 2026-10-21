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

/** 总分变化：可比且双方均有分数时显示带符号差值，否则显示占位 */
const deltaText = computed(() => {
  const value = result.value?.comparable ? result.value.delta.overall_score : null
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
  }
  return '—'
})

/** 总分变化的涨跌配色；null 时无涨跌 */
const deltaClass = computed(() => {
  const value = result.value?.comparable ? result.value.delta.overall_score : null
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value >= 0 ? 'delta-up' : 'delta-down'
  }
  return ''
})

function validScore(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

const rows = computed(() => DIMENSION_KEYS.map((key) => {
  const latest = result.value?.latest.dimension_scores[key]
  const previous = result.value?.previous.dimension_scores[key]
  const delta = result.value?.comparable && validScore(latest) && validScore(previous)
    ? latest - previous : null
  return {
    key, label: DIMENSION_LABELS[key],
    latest: validScore(latest) ? latest.toFixed(1) : '证据不足',
    previous: validScore(previous) ? previous.toFixed(1) : '证据不足',
    delta: delta === null ? '—' : `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}`,
  }
}))

const canPlotChart = computed(() => !!result.value && DIMENSION_KEYS.some((key) =>
  validScore(result.value?.latest.dimension_scores[key]) ||
  validScore(result.value?.previous.dimension_scores[key]),
))

function renderChart(data: ComparisonResult): void {
  if (!chartEl.value) return
  if (!canPlotChart.value) return
  chart ??= init(chartEl.value)
  const latest = DIMENSION_KEYS.map((key) => validScore(data.latest.dimension_scores[key]) ? data.latest.dimension_scores[key] : '-')
  const previous = DIMENSION_KEYS.map((key) => validScore(data.previous.dimension_scores[key]) ? data.previous.dimension_scores[key] : '-')
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

onMounted(() => void load())

watch(() => props.courseId, () => void load())

// 图表元素在异步结果到达后才出现；跟随元素创建、销毁并监听尺寸变化。
watch(chartEl, (element) => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
  if (element && result.value) {
    renderChart(result.value)
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(element)
  }
}, { flush: 'post' })

watch(result, (data) => {
  if (data) renderChart(data)
}, { flush: 'post' })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div v-loading="loading" class="comparison">
    <div class="comparison-toolbar">
      <el-button :loading="loading" @click="load">刷新评价对比</el-button>
    </div>
    <template v-if="error">
      <el-empty :description="error instanceof ApiError ? error.message : '对比数据加载失败'">
        <el-button type="primary" @click="load">重试</el-button>
      </el-empty>
    </template>

    <el-empty v-else-if="insufficient" description="至少需要两次已完成评价才能对比">
      <span class="text-secondary">上传并处理两节课堂录音后，这里将展示总分与六维变化</span>
    </el-empty>

    <template v-else-if="result">
      <el-alert
        v-if="!result.comparable"
        type="warning"
        :closable="false"
        show-icon
        class="comparison-notice"
        :title="result.reason || '两次评价标准或模式不同，无法直接比较'"
      />

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
          <div class="summary-value tabular" :class="deltaClass">{{ deltaText }}</div>
          <div class="summary-meta">缺少完整总分时，请查看下方各维度变化</div>
        </div>
      </div>

      <h4 class="comparison-subtitle">BOPPPS 六维对比</h4>
      <p class="comparison-hint">展示最近两次已完成评价。证据不足的维度留空；仅在标准一致且双方都有分数时计算变化。</p>
      <div v-if="canPlotChart" ref="chartEl" class="comparison-chart" />
      <el-table :data="rows" style="width: 100%">
        <el-table-column prop="label" label="评价维度" min-width="140" />
        <el-table-column prop="previous" label="上次" min-width="100" />
        <el-table-column prop="latest" label="本次" min-width="100" />
        <el-table-column prop="delta" label="变化" min-width="80" />
      </el-table>
    </template>
  </div>
</template>

<style scoped>
.comparison {
  min-height: 200px;
}

.comparison-toolbar {
  margin-bottom: 14px;
}

.comparison-hint {
  color: var(--text-secondary);
  font-size: 13px;
}

.comparison-notice {
  margin-bottom: 14px;
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
