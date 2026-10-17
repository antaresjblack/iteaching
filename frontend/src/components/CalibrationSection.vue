<script setup lang="ts">
import { EditPen } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { addCalibration } from '@/api/evaluations'
import { DIMENSION_KEYS, type CalibrationRead, type DimensionKey } from '@/types/evaluation'
import { DIMENSION_LABELS } from '@/utils/dimensions'
import { formatDateTime, formatScore } from '@/utils/format'

const props = defineProps<{
  evaluationId: number
  calibrations: CalibrationRead[]
  /** 模型原始分，用于展示"AI 原始分"参考 */
  modelOverallScore: number
  canWrite: boolean
}>()

const emit = defineEmits<{
  saved: []
}>()

const form = reactive({
  overallScore: null as number | null,
  dimensionScores: {} as Record<DimensionKey, number | null>,
  comment: '',
})

const submitting = ref(false)

/** 至少填写一项才能提交（与后端校验一致） */
const hasAnyValue = computed(
  () =>
    form.overallScore !== null ||
    DIMENSION_KEYS.some((key) => form.dimensionScores[key] !== null) ||
    form.comment.trim() !== '',
)

/** 按时间正序展示校准历史（后端按 id 倒序应用最新校准） */
const history = computed(() => [...props.calibrations].sort((a, b) => a.id - b.id))

watch(
  () => props.evaluationId,
  () => {
    form.overallScore = null
    form.dimensionScores = Object.fromEntries(DIMENSION_KEYS.map((key) => [key, null])) as Record<
      DimensionKey,
      number | null
    >
    form.comment = ''
  },
  { immediate: true },
)

function dimensionScoreOf(calibration: CalibrationRead, key: DimensionKey): number | null {
  return calibration.dimension_scores?.[key] ?? null
}

async function handleSubmit(): Promise<void> {
  if (!hasAnyValue.value) {
    ElMessage.warning('总分、维度分数或说明至少填写一项')
    return
  }
  submitting.value = true
  try {
    await addCalibration(props.evaluationId, {
      overall_score: form.overallScore ?? undefined,
      dimension_scores: Object.fromEntries(
        DIMENSION_KEYS.filter((key) => form.dimensionScores[key] !== null).map((key) => [
          key,
          form.dimensionScores[key] as number,
        ]),
      ),
      comment: form.comment.trim() || undefined,
    })
    ElMessage.success('校准已保存，分数已生效')
    form.overallScore = null
    form.comment = ''
    form.dimensionScores = Object.fromEntries(DIMENSION_KEYS.map((key) => [key, null])) as Record<
      DimensionKey,
      number | null
    >
    emit('saved')
  } catch {
    // 错误已由 http 层统一提示
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <h3 class="section-title">人工校准</h3>

    <div v-if="history.length === 0" class="calibration-empty">
      <span class="text-secondary">暂无校准记录</span>
    </div>
    <el-table v-else :data="history" size="small" class="calibration-table">
      <el-table-column label="时间" width="150">
        <template #default="{ row }">
          <span class="tabular">{{ formatDateTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="总分" width="90">
        <template #default="{ row }">
          <span class="tabular">{{ formatScore(row.overall_score) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="维度调整">
        <template #default="{ row }">
          <span v-if="row.dimension_scores">
            <el-tag
              v-for="key in DIMENSION_KEYS.filter((k) => dimensionScoreOf(row, k) !== null)"
              :key="key"
              size="small"
              type="info"
              class="dim-tag"
            >
              {{ DIMENSION_LABELS[key] }} {{ formatScore(dimensionScoreOf(row, key)) }}
            </el-tag>
          </span>
          <span v-else class="text-secondary">—</span>
        </template>
      </el-table-column>
      <el-table-column label="说明">
        <template #default="{ row }">
          <span :class="{ 'text-secondary': !row.comment }">{{ row.comment || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="canWrite" class="calibration-form">
      <el-form label-position="top">
        <el-form-item label="总分校准（留空表示不调整）">
          <el-slider
            v-model="form.overallScore"
            :min="0"
            :max="100"
            :step="0.5"
            show-input
            :show-input-controls="false"
            class="score-slider"
            :disabled="false"
          />
          <div class="slider-hint">
            AI 原始分 <span class="tabular">{{ formatScore(modelOverallScore) }}</span>，调整后将以校准分为准
          </div>
        </el-form-item>

        <el-form-item label="分维度校准（留空表示不调整）">
          <div class="dim-inputs">
            <div v-for="key in DIMENSION_KEYS" :key="key" class="dim-input">
              <span class="dim-label">{{ DIMENSION_LABELS[key] }}</span>
              <el-input-number
                v-model="form.dimensionScores[key]"
                :min="0"
                :max="100"
                :step="0.5"
                :precision="1"
                :controls="false"
                size="small"
                placeholder="留空"
              />
            </div>
          </div>
        </el-form-item>

        <el-form-item label="校准说明">
          <el-input
            v-model="form.comment"
            type="textarea"
            :rows="2"
            maxlength="10000"
            show-word-limit
            placeholder="说明调整依据（可选）"
          />
        </el-form-item>

        <div class="calibration-actions">
          <el-button type="primary" :icon="EditPen" :loading="submitting" :disabled="!hasAnyValue" @click="handleSubmit">
            保存校准
          </el-button>
        </div>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.calibration-table {
  margin-bottom: 16px;
}

.calibration-empty {
  padding: 12px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius);
  margin-bottom: 16px;
}

.dim-tag {
  margin: 0 4px 4px 0;
}

.calibration-form {
  margin-top: 8px;
}

.score-slider {
  max-width: 420px;
}

.slider-hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.dim-inputs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px 16px;
  width: 100%;
}

.dim-input {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dim-label {
  font-size: 13px;
  color: var(--text-secondary);
  flex-shrink: 0;
  min-width: 4em;
}

.calibration-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
