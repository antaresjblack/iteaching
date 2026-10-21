<script setup lang="ts">
import { ArrowLeft, Delete, Refresh, Upload, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getCourse } from '@/api/courses'
import { getEvaluationByRecording, listCourseEvaluations } from '@/api/evaluations'
import { deleteRecording, getRecordingStatus } from '@/api/recordings'
import ComparisonSection from '@/components/ComparisonSection.vue'
import RecordingStatusTag from '@/components/RecordingStatusTag.vue'
import UploadRecordingDialog from '@/components/UploadRecordingDialog.vue'
import { usePollingTask } from '@/composables/usePollingTask'
import { useRecordingsStore } from '@/stores/recordings'
import type { CourseRead } from '@/types/course'
import type { EvaluationListItem } from '@/types/evaluation'
import type { LocalUploadRecord, RecordingStatus, UploadData } from '@/types/recording'
import { formatDateTime, formatScore } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const recordingsStore = useRecordingsStore()

const courseId = Number(route.params.id)

const course = ref<CourseRead | null>(null)
const courseLoading = ref(false)
const courseError = ref<Error | null>(null)

const activeTab = ref('recordings')
const uploadVisible = ref(false)

// 历史评价分页
const historyLoading = ref(false)
const historyError = ref<Error | null>(null)
const historyItems = ref<EvaluationListItem[]>([])
const page = ref(1)
const pageSize = 10
const total = ref(0)

// 本地上传记录（含 localStorage 兜底）
const uploads = computed(() => recordingsStore.byCourse(courseId))

// 轮询：查询所有未结束上传记录的最新状态
const polling = usePollingTask<RecordingStatus[]>(async () => {
  const pending = recordingsStore.pendingOf(courseId)
  if (pending.length === 0) return []
  return Promise.all(
    pending.map((item) =>
      getRecordingStatus(item.recording_id).catch(() => null),
    ),
  ).then((results) => results.filter((item): item is RecordingStatus => item !== null))
}, {
  intervalMs: 5000,
  timeoutMs: 15 * 60 * 1000,
  shouldStop: () => recordingsStore.pendingOf(courseId).length === 0,
})

const pollingState = polling.state

/** 轮询返回后同步状态到 store */
watch(polling.data, (results) => {
  if (!results) return
  const map = new Map(results.map((item) => [item.recording_id, item]))
  for (const record of recordingsStore.byCourse(courseId)) {
    const latest = map.get(record.recording_id)
    if (!latest) continue
    if (latest.status !== record.status || latest.error !== record.error) {
      recordingsStore.updateStatus(record.recording_id, { status: latest.status, error: latest.error ?? null })
      if (latest.status === 'SUCCEEDED') {
        ElMessage.success(`「${record.filename}」处理完成`)
        void loadHistory()
      }
      if (latest.status === 'FAILED') ElMessage.error(`「${record.filename}」处理失败`)
    }
  }
})

/** 轮询超时：把仍非终态的记录标记为 TIMEOUT 并提示 */
watch(pollingState, (state) => {
  if (state === 'timeout') {
    for (const record of recordingsStore.pendingOf(courseId)) {
      recordingsStore.updateStatus(record.recording_id, { status: 'TIMEOUT', error: null })
    }
    ElMessage.warning('自动刷新已暂停，后台可能仍在处理，请点击刷新状态')
  }
})

function startPollingIfNeeded(): void {
  if (recordingsStore.pendingOf(courseId).length > 0) polling.start()
}

async function loadCourse(): Promise<void> {
  courseLoading.value = true
  courseError.value = null
  try {
    course.value = await getCourse(courseId)
  } catch (err) {
    course.value = null
    courseError.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    courseLoading.value = false
  }
}

async function loadHistory(): Promise<void> {
  historyLoading.value = true
  historyError.value = null
  try {
    const data = await listCourseEvaluations(courseId, page.value, pageSize)
    historyItems.value = data.items
    total.value = data.total
  } catch (err) {
    historyItems.value = []
    historyError.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    historyLoading.value = false
  }
}

function onUploaded(data: UploadData, filename: string, recordedAt: string): void {
  recordingsStore.add({
    course_id: courseId,
    recording_id: data.recording_id,
    task_id: data.task_id,
    filename,
    recorded_at: recordedAt,
    uploaded_at: new Date().toISOString(),
    status: 'QUEUED',
    error: null,
  })
  startPollingIfNeeded()
}

/** SUCCEEDED 后按 recording_id 取评价并跳转 */
async function viewEvaluation(record: LocalUploadRecord): Promise<void> {
  try {
    const evaluation = await getEvaluationByRecording(record.recording_id)
    await router.push({
      name: 'evaluation-detail',
      params: { id: evaluation.id },
      query: { course_id: String(courseId) },
    })
  } catch {
    ElMessage.warning('评价尚未完成，请稍后再试')
  }
}

async function handleDelete(record: LocalUploadRecord): Promise<void> {
  await ElMessageBox.confirm(
    `删除后录音及其转写、评价、评语、校准记录将一并删除，且不可恢复。确认删除「${record.filename}」？`,
    '删除录音',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
  )
  try {
    await deleteRecording(record.recording_id)
    recordingsStore.remove(record.recording_id)
    ElMessage.success('录音已删除')
    if (activeTab.value === 'history') await loadHistory()
  } catch {
    // 错误已由 http 层统一提示
  }
}

function manualRefreshStatuses(): void {
  if (recordingsStore.pendingOf(courseId).length > 0) {
    startPollingIfNeeded()
    ElMessage.info('正在刷新任务状态')
  } else {
    ElMessage.info('当前没有进行中的任务')
  }
}

watch(activeTab, (tab) => {
  if (tab === 'history') void loadHistory()
})

function handlePageChange(value: number): void {
  page.value = value
  void loadHistory()
}

watch(
  () => route.params.id,
  () => {
    void loadCourse()
    void loadHistory()
    startPollingIfNeeded()
  },
)

// 进入页面即加载并恢复轮询
void loadCourse()
void loadHistory()
startPollingIfNeeded()

onBeforeUnmount(() => {
  polling.stop()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div class="header-left">
        <el-button text :icon="ArrowLeft" aria-label="返回课程列表" title="返回课程列表" @click="router.push('/courses')" />
        <div>
          <h2 class="page-title">{{ course?.name ?? '课程详情' }}</h2>
          <p v-if="course" class="page-subtitle tabular">
            教师账号 ID {{ course.teacher_id }} · 督导账号 ID {{ course.supervisor_id }} ·
            创建于 {{ formatDateTime(course.created_at) }}
          </p>
        </div>
      </div>
    </div>

    <el-skeleton v-if="courseLoading" :rows="4" animated />

    <div v-else-if="courseError" class="state-panel">
      <el-empty :description="courseError.message || '课程加载失败'">
        <el-button type="primary" @click="loadCourse">重试</el-button>
      </el-empty>
    </div>

    <el-tabs v-else v-model="activeTab">
      <!-- Tab 1：录音与上传 -->
      <el-tab-pane label="录音与上传" name="recordings">
        <div class="tab-toolbar">
          <el-button type="primary" :icon="Upload" @click="uploadVisible = true">上传录音</el-button>
          <el-button :icon="Refresh" :loading="pollingState === 'polling'" @click="manualRefreshStatuses">
            刷新状态
          </el-button>
        </div>

        <el-empty v-if="uploads.length === 0" description="还没有上传过录音">
          <el-button type="primary" :icon="Upload" @click="uploadVisible = true">上传第一段课堂录音</el-button>
        </el-empty>

        <el-table v-else :data="uploads" class="uploads-table">
          <el-table-column label="文件名" min-width="180">
            <template #default="{ row }">
              <span class="filename">{{ row.filename }}</span>
            </template>
          </el-table-column>
          <el-table-column label="录制时间" width="160">
            <template #default="{ row }">
              <span class="tabular text-secondary">{{ formatDateTime(row.recorded_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="处理状态" width="120">
            <template #default="{ row }">
              <RecordingStatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="180">
            <template #default="{ row }">
              <span v-if="row.status === 'FAILED' && row.error" class="error-text">{{ row.error }}</span>
              <span v-else-if="row.status === 'TIMEOUT'" class="text-secondary">自动刷新已暂停，点击“刷新状态”查看后台进度</span>
              <span v-else class="text-secondary">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'SUCCEEDED'"
                text
                type="primary"
                :icon="View"
                aria-label="查看评价"
                title="查看评价"
                @click="viewEvaluation(row)"
              >
                查看评价
              </el-button>
              <el-button
                text
                type="danger"
                :icon="Delete"
                aria-label="删除录音"
                title="删除录音"
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 2：历史评价 -->
      <el-tab-pane label="历史评价" name="history">
        <div class="tab-toolbar">
          <el-button :icon="Refresh" :loading="historyLoading" @click="loadHistory">刷新历史评价</el-button>
        </div>
        <el-skeleton v-if="historyLoading" :rows="5" animated />

        <div v-else-if="historyError" class="state-panel">
          <el-empty :description="historyError.message || '历史评价加载失败'">
            <el-button type="primary" @click="loadHistory">重试</el-button>
          </el-empty>
        </div>

        <el-empty v-else-if="historyItems.length === 0" description="暂无已完成评价">
          <span class="text-secondary">上传录音并处理完成后，评价将显示在这里</span>
        </el-empty>

        <template v-else>
          <el-table :data="historyItems" class="history-table">
            <el-table-column label="录制时间" width="170">
              <template #default="{ row }">
                <span class="tabular">{{ formatDateTime(row.recorded_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已观察均分（AI）" width="160">
              <template #default="{ row }">
                <span class="tabular score">{{ formatScore(row.observed_score) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="评价覆盖" width="110">
              <template #default="{ row }">
                <span class="tabular">{{ row.mode === 'boppps' && row.observed_count != null ? `${row.observed_count}/6 项` : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="完整总分" width="110">
              <template #default="{ row }">
                <span class="tabular score">{{ formatScore(row.overall_score) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="模式" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.mode === 'boppps' ? 'primary' : 'info'">
                  {{ row.mode === 'boppps' ? 'BOPPPS 六维' : '基础评价' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="评语数" width="90">
              <template #default="{ row }">
                <span class="tabular text-secondary">{{ row.reviews.length }}</span>
              </template>
            </el-table-column>
            <el-table-column label="校准数" width="90">
              <template #default="{ row }">
                <span class="tabular text-secondary">{{ row.calibrations.length }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button
                  text
                  type="primary"
                  :icon="View"
                  aria-label="查看评价"
                  title="查看评价"
                  @click="router.push({ name: 'evaluation-detail', params: { id: row.id }, query: { course_id: String(courseId) } })"
                >
                  查看评价
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-row">
            <el-pagination
              :current-page="page"
              :page-size="pageSize"
              :total="total"
              layout="total, prev, pager, next"
              @current-change="handlePageChange"
            />
          </div>
        </template>
      </el-tab-pane>

      <!-- Tab 3：评价对比 -->
      <el-tab-pane label="评价对比" name="comparison">
        <ComparisonSection v-if="activeTab === 'comparison'" :course-id="courseId" />
      </el-tab-pane>
    </el-tabs>

    <UploadRecordingDialog v-model:visible="uploadVisible" :course-id="courseId" @uploaded="onUploaded" />
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

.tab-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.uploads-table,
.history-table {
  background: var(--surface);
  border-radius: var(--radius);
}

.filename {
  font-weight: 500;
}

.error-text {
  color: var(--danger);
  font-size: 13px;
}

.score {
  font-weight: 600;
  color: var(--brand);
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
