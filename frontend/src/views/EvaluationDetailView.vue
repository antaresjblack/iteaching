<script setup lang="ts">
import { ArrowLeft } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getCourse } from '@/api/courses'
import { getEvaluationById } from '@/api/evaluations'
import AudioPlayer from '@/components/AudioPlayer.vue'
import BopppsRadarChart from '@/components/BopppsRadarChart.vue'
import CalibrationSection from '@/components/CalibrationSection.vue'
import ReviewSection from '@/components/ReviewSection.vue'
import SegmentTimeline from '@/components/SegmentTimeline.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/types/api'
import type { CourseRead } from '@/types/course'
import type { EvaluationRead } from '@/types/evaluation'
import { formatScore } from '@/utils/format'
import { canReviewCourse } from '@/utils/roles'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const evaluationId = Number(route.params.id)

const loading = ref(false)
const error = ref<Error | null>(null)
const evaluation = ref<EvaluationRead | null>(null)
const course = ref<CourseRead | null>(null)

/** 是否未完成（404：评价尚未生成） */
const notReady = computed(
  () => !loading.value && error.value instanceof ApiError && error.value.status === 404,
)

/** 写权限：管理员或该课程的指定督导 */
const canWrite = computed(() => canReviewCourse(auth.user, course.value))

/** 校准后总分与 AI 原始分不同时展示差异 */
const showModelScore = computed(() => {
  const item = evaluation.value
  return !!item && item.overall_score !== item.model_overall_score
})

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    evaluation.value = await getEvaluationById(evaluationId)
    // 课程信息用于写权限判断；加载失败不影响只读展示（后端会拦截写入）
    const courseIdParam = route.query.course_id
    if (typeof courseIdParam === 'string') {
      course.value = await getCourse(Number(courseIdParam)).catch(() => null)
    }
  } catch (err) {
    evaluation.value = null
    error.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    loading.value = false
  }
}

async function refreshAfterWrite(): Promise<void> {
  await load()
}

function handleSeek(seconds: number): void {
  audioPlayer.value?.seekTo(seconds)
}

const audioPlayer = ref<InstanceType<typeof AudioPlayer> | null>(null)

void load()
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div class="header-left">
        <el-button
          text
          :icon="ArrowLeft"
          aria-label="返回"
          title="返回"
          @click="router.back()"
        />
        <div>
          <h2 class="page-title">课堂评价</h2>
          <p v-if="course" class="page-subtitle">{{ course.name }}</p>
        </div>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated />

    <div v-else-if="notReady" class="state-panel">
      <el-empty description="评价尚未完成">
        <p class="text-secondary">AI 处理完成后即可查看本次课堂的转写与评价</p>
        <el-button type="primary" @click="load">刷新</el-button>
      </el-empty>
    </div>

    <div v-else-if="error" class="state-panel">
      <el-empty :description="error.message || '评价加载失败'">
        <el-button type="primary" @click="load">重试</el-button>
      </el-empty>
    </div>

    <template v-else-if="evaluation">
      <!-- 总分摘要 -->
      <section class="score-summary">
        <div class="score-main">
          <div class="score-label">总分（校准后生效）</div>
          <div class="score-value tabular">{{ formatScore(evaluation.overall_score) }}</div>
          <div v-if="showModelScore" class="score-model tabular">
            AI 原始分 {{ formatScore(evaluation.model_overall_score) }}
          </div>
        </div>
        <div class="score-side">
          <el-tag :type="evaluation.mode === 'boppps' ? 'primary' : 'info'" size="small">
            {{ evaluation.mode === 'boppps' ? 'BOPPPS 六维评价' : '基础评价' }}
          </el-tag>
          <el-tag v-if="evaluation.reviews.length > 0" type="success" size="small">
            已评审
          </el-tag>
          <el-tag v-if="evaluation.calibrations.length > 0" type="warning" size="small">
            已校准
          </el-tag>
        </div>
      </section>

      <!-- 音频播放器 -->
      <section>
        <h3 class="section-title">课堂录音</h3>
        <AudioPlayer ref="audioPlayer" :recording-id="evaluation.recording_id" />
      </section>

      <!-- BOPPPS 六维 -->
      <section>
        <h3 class="section-title">BOPPPS 六维评分</h3>
        <div class="radar-panel">
          <BopppsRadarChart :dimension-scores="evaluation.dimension_scores" />
        </div>
      </section>

      <!-- 转写时间轴 -->
      <section>
        <h3 class="section-title">转写与发言分段</h3>
        <div class="timeline-panel">
          <SegmentTimeline :segments="evaluation.segments" @seek="handleSeek" />
        </div>
      </section>

      <!-- 证据与问题 -->
      <section class="evidence-section">
        <h3 class="section-title">评分证据</h3>
        <p class="evidence-text">{{ evaluation.overall_evidence || '—' }}</p>
      </section>

      <section>
        <h3 class="section-title">问题</h3>
        <el-empty v-if="evaluation.problems.length === 0" description="未发现问题" :image-size="56" />
        <ol v-else class="problem-list">
          <li v-for="(problem, index) in evaluation.problems" :key="index" class="problem-item">
            {{ problem }}
          </li>
        </ol>
      </section>

      <!-- 改进建议 -->
      <section>
        <h3 class="section-title">改进建议</h3>
        <el-empty v-if="evaluation.suggestions.length === 0" description="暂无建议" :image-size="56" />
        <ul v-else class="suggestion-list">
          <li v-for="(suggestion, index) in evaluation.suggestions" :key="index" class="suggestion-item">
            <el-tag :type="suggestion.source === 'ai' ? 'primary' : 'info'" size="small" class="suggestion-tag">
              {{ suggestion.source === 'ai' ? 'AI 建议' : '规则生成' }}
            </el-tag>
            <span class="suggestion-text">{{ suggestion.text }}</span>
          </li>
        </ul>
      </section>

      <!-- 督导评语与人工校准 -->
      <section>
        <ReviewSection
          :evaluation-id="evaluation.id"
          :reviews="evaluation.reviews"
          :can-write="canWrite"
          @saved="refreshAfterWrite"
        />
      </section>

      <section>
        <CalibrationSection
          :evaluation-id="evaluation.id"
          :calibrations="evaluation.calibrations"
          :model-overall-score="evaluation.model_overall_score"
          :can-write="canWrite"
          @saved="refreshAfterWrite"
        />
      </section>
    </template>
  </div>
</template>

<style scoped>
.header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}

.state-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.score-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 20px;
  margin-bottom: 8px;
}

.score-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.score-value {
  font-size: 32px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--brand);
}

.score-model {
  font-size: 12px;
  color: var(--text-placeholder);
}

.score-side {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.radar-panel,
.timeline-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.evidence-text {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.problem-list {
  margin: 0;
  padding-left: 22px;
}

.problem-item {
  margin-bottom: 6px;
  color: var(--text-primary);
}

.suggestion-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 8px;
  background: var(--surface);
}

.suggestion-tag {
  flex-shrink: 0;
  margin-top: 2px;
}

.suggestion-text {
  color: var(--text-primary);
  overflow-wrap: anywhere;
}
</style>
