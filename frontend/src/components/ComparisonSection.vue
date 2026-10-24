<script setup lang="ts">
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use, type ECharts } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { compareCourse, readComparisonAnalysis, generateComparisonAnalysis } from '@/api/evaluations'
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
const analysis = ref('')
const analysisLoading = ref(false)
const analysisError = ref('')
async function generateAnalysis(): Promise<void> {
  const version = loadVersion
  analysisLoading.value = true
  analysisError.value = ''
  try {
    const data = await generateComparisonAnalysis(props.courseId)
    if (version === loadVersion) analysis.value = data.analysis
  } catch {
    if (version === loadVersion) analysisError.value = '综合分析暂未生成成功，请重试。'
  } finally {
    analysisLoading.value = false
  }
}
let loadVersion = 0
const chartEl = ref<HTMLDivElement>()
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const insufficient = computed(() => !loading.value && !error.value && result.value === null)

/** 总分变化：可比且双方均有分数时显示带符号差值，否则显示占位 */
const deltaValue = computed(() => {
  const data = result.value
  if (!data?.comparable) return null
  return data.delta.overall_score ?? data.delta.observed_score ?? null
})

/** 总分不可得时，差值退化为“已观察维度均分”的变化 */
const deltaIsObserved = computed(
  () => result.value?.delta.overall_score == null && result.value?.delta.observed_score != null,
)

const deltaText = computed(() => {
  const value = deltaValue.value
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
  }
  return '—'
})

/** 总分变化的涨跌配色；null 时无涨跌 */
const deltaClass = computed(() => {
  const value = deltaValue.value
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value >= 0 ? 'delta-up' : 'delta-down'
  }
  return ''
})

/** 将 LLM 输出的 Markdown 要点（**加粗** 与 "- " 列表）安全渲染为 HTML。 */
function renderAnalysis(text: string): string {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
  const emphasize = (s: string) => s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  const blocks: string[] = []
  let list: string[] = []
  const flush = () => {
    if (list.length) {
      blocks.push(`<ul>${list.map((item) => `<li>${item}</li>`).join('')}</ul>`)
      list = []
    }
  }
  for (const raw of escaped.split(/\r?\n/)) {
    const line = raw.trim()
    if (/^[-*•]\s+/.test(line)) {
      list.push(emphasize(line.replace(/^[-*•]\s+/, '')))
    } else {
      flush()
      if (line) blocks.push(`<p>${emphasize(line)}</p>`)
    }
  }
  flush()
  return blocks.join('')
}

function validScore(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** 混合展示：完整总分优先，六维不齐时退回“已观察维度均分”，避免只显示占位符 */
function sideScore(side: 'latest' | 'previous'): number | null {
  const item = result.value?.[side]
  if (!item) return null
  return item.overall_score ?? item.observed_score
}

/** 变化条：差值为 0 时渲染居中细线，避免宽度为 0 而导致完全看不见 */
function barStyle(change: number): Record<string, string> {
  if (change === 0) return { left: 'calc(50% - 1px)', width: '2px' }
  return {
    left: `${change < 0 ? 50 + change / 2 : 50}%`,
    width: `${Math.abs(change) / 2}%`,
  }
}

const rows = computed(() => DIMENSION_KEYS.map((key) => {
  const latest = result.value?.latest.dimension_scores[key]
  const previous = result.value?.previous.dimension_scores[key]
  const delta = result.value?.comparable && validScore(latest) && validScore(previous)
    ? latest - previous : null
  return {
    key, label: DIMENSION_LABELS[key], change: delta,
    latest: validScore(latest) ? latest.toFixed(1) : '证据不足',
    previous: validScore(previous) ? previous.toFixed(1) : '证据不足',
    delta: delta === null ? '—' : `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}`,
  }
}))

const comparableRows = computed(() => rows.value.filter((row) => row.change !== null))
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
    legend: { data: ['上次', '本次'], top: 0 },
    grid: { left: 8, right: 8, top: 36, bottom: 0, containLabel: true },
    xAxis: {
      type: 'category',
      data: DIMENSION_KEYS.map((key) => DIMENSION_LABELS[key]),
      axisLabel: { color: '#5c6b73' },
    },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: '#5c6b73' } },
    series: [
      {
        name: '上次',
        type: 'bar',
        data: previous,
        itemStyle: { color: '#b9cfd3' },
        barMaxWidth: 18,
      },
      {
        name: '本次',
        type: 'bar',
        data: latest,
        itemStyle: { color: '#175e6b' },
        barMaxWidth: 18,
      },
    ],
  })
}

async function load(): Promise<void> {
  const version = ++loadVersion
  loading.value = true
  error.value = null
  analysis.value = ''
  analysisError.value = ''
  try {
    const data = await compareCourse(props.courseId)
    if (version !== loadVersion) return
    result.value = data
    loading.value = false
    if (data) {
      try {
        const cached = await readComparisonAnalysis(props.courseId)
        if (version === loadVersion) analysis.value = cached?.analysis ?? ''
      } catch {
        if (version === loadVersion) analysisError.value = '综合分析加载失败，可点击重新生成。'
      }
    }
  } catch (err) {
    if (version !== loadVersion) return
    result.value = null
    error.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    if (version === loadVersion) {
      loading.value = false

    }
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
  ++loadVersion
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div v-loading="loading" class="comparison">
    <div class="comparison-toolbar">
      <el-button :loading="loading" :disabled="analysisLoading" @click="load">刷新评价对比</el-button>
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
          <div class="summary-label">{{ result.latest.overall_score == null ? '本次均分' : '本次总分' }}</div>
          <div class="summary-value tabular">{{ formatScore(sideScore('latest')) }}</div>
          <div class="summary-meta tabular">
            <template v-if="result.latest.overall_score == null">
              已观察 {{ result.latest.observed_count }}/6 项 ·
            </template>
            {{ formatDateTime(result.latest.recorded_at) }}
          </div>
        </div>
        <div class="summary-card">
          <div class="summary-label">{{ result.previous.overall_score == null ? '上次均分' : '上次总分' }}</div>
          <div class="summary-value tabular">{{ formatScore(sideScore('previous')) }}</div>
          <div class="summary-meta tabular">
            <template v-if="result.previous.overall_score == null">
              已观察 {{ result.previous.observed_count }}/6 项 ·
            </template>
            {{ formatDateTime(result.previous.recorded_at) }}
          </div>
        </div>
        <div class="summary-card summary-card--delta">
          <div class="summary-label">{{ deltaIsObserved ? '均分变化' : '总分变化' }}</div>
          <div class="summary-value tabular" :class="deltaClass">{{ deltaText }}</div>
          <div class="summary-meta">
            {{ deltaIsObserved
              ? '六维不齐，按两次都已观察的维度均分对比'
              : '缺少完整总分时，请查看下方各维度变化' }}
          </div>
        </div>
      </div>

      <section class="insight-panel">
        <div class="insight-heading"><h4>课堂变化解读</h4><el-tag size="small" type="info">AI 综合分析</el-tag></div>
        <div v-if="analysis" class="analysis-text" v-html="renderAnalysis(analysis)"></div>
        <p v-else class="comparison-hint">综合两次评价的问题、建议、督导评语与评分变化，生成课堂改进分析。</p>
        <p v-if="analysisError" role="alert">{{ analysisError }}</p>
        <el-button v-if="!analysis" type="primary" :loading="analysisLoading" @click="generateAnalysis">{{ analysisLoading ? '正在综合分析…' : '生成综合分析' }}</el-button>
        <p class="comparison-hint">AI 辅助解读，请结合实际课堂复核。相同评价只生成一次；评价或评语更新后可重新生成。</p>
      </section>
      <div class="visual-grid">
        <section class="visual-panel">
          <h4>各维度分数变化</h4>
          <p class="comparison-hint">共同有分数的维度 · 单位：分</p>
          <el-empty v-if="!comparableRows.length" description="暂无可比较维度" :image-size="48" />
          <div v-for="row in comparableRows" :key="row.key" class="change-row">
            <span>{{ row.label }}</span>
            <div class="change-track" :aria-label="`${row.label}变化${row.delta}分`" role="img">
              <i :class="row.change! < 0 ? 'negative' : 'positive'" :style="barStyle(row.change!)" />
            </div>
            <strong>{{ row.delta }}</strong>
          </div>
          <div class="scale-labels"><span>下降 −100</span><span>0</span><span>上升 +100</span></div>
        </section>

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
.analysis-text { white-space: normal; }
.analysis-text p { margin: 0 0 6px; }
.analysis-text ul { margin: 0; padding-left: 20px; }
.analysis-text li { margin: 4px 0; }
.analysis-text strong { font-weight: 600; }
.insight-panel { background: #eef6f5; border-left: 4px solid #175e6b; padding: 16px 20px; border-radius: 8px; margin-bottom: 20px; line-height: 1.8; }
.insight-heading { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.insight-heading h4, .visual-panel h4 { margin: 0; }
.visual-grid, .feedback-grid { display: grid; grid-template-columns: 1fr; gap: 16px; margin-bottom: 24px; }
.visual-panel { border: 1px solid var(--border); border-radius: 10px; padding: 18px; background: var(--surface); }
.change-row { display: grid; grid-template-columns: 90px 1fr 55px; align-items: center; gap: 10px; margin: 14px 0; font-size: 13px; }
.change-track { position: relative; height: 16px; background: #f1f4f5; border-radius: 4px; }
.change-track::after { content: ''; position: absolute; left: 50%; top: -3px; height: 22px; border-left: 1px solid #9bacb2; }
.change-track i { position: absolute; top: 0; height: 100%; border-radius: 3px; }
.positive { background: #175e6b; } .negative { background: #ce8254; }
.scale-labels { display: flex; justify-content: space-between; margin: 8px 65px 0 100px; font-size: 11px; color: var(--text-secondary); }
.coverage-row { margin: 24px 0; } .coverage-row strong { float: right; } .coverage-row :deep(.el-progress) { margin-top: 12px; }
.feedback-panel { line-height: 1.8; overflow-wrap: anywhere; } .feedback-panel h5 { margin: 18px 0 8px; font-size: 14px; }
.feedback-panel ul { padding-left: 20px; margin: 0; } .feedback-panel li { margin: 8px 0; }
.feedback-panel blockquote { margin: 10px 0; padding: 10px 14px; background: #f6f8f9; border-left: 3px solid #b9cfd3; }
.feedback-panel small { display: block; color: var(--text-secondary); }
@media (max-width: 760px) { .visual-grid, .feedback-grid { grid-template-columns: 1fr; } }

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
