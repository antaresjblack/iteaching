<script setup lang="ts">
import { Refresh, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { leaveCourse, listMySupervisedCourses } from '@/api/supervisions'
import { LOCATION_GROUPS, type CourseQuery, type SupervisedCourseRead } from '@/types/course'
import { formatDateTime } from '@/utils/format'
import { formatSchedules, WEEKDAY_LABELS } from '@/utils/course'

const router = useRouter()

const loading = ref(false)
const error = ref<Error | null>(null)
const courses = ref<SupervisedCourseRead[]>([])

/** 与课程列表一致的四条件筛选：教师名称、上课地点、时间、课程名称 */
const filters = reactive({
  teacherName: '',
  location: '',
  weekday: null as number | null,
  time: null as string | null,
  name: '',
})

const hasFilter = computed(
  () =>
    !!filters.teacherName.trim() ||
    !!filters.location ||
    filters.weekday !== null ||
    !!filters.time ||
    !!filters.name.trim(),
)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const query: CourseQuery = {
      teacher_name: filters.teacherName.trim() || undefined,
      location: filters.location || undefined,
      weekday: filters.weekday ?? undefined,
      time: filters.time || undefined,
      name: filters.name.trim() || undefined,
    }
    courses.value = await listMySupervisedCourses(query)
  } catch (err) {
    courses.value = []
    error.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    loading.value = false
  }
}

function resetFilters(): void {
  filters.teacherName = ''
  filters.location = ''
  filters.weekday = null
  filters.time = null
  filters.name = ''
  void load()
}

function openDetail(row: SupervisedCourseRead): void {
  void router.push({ name: 'course-detail', params: { id: row.id } })
}

async function handleLeave(row: SupervisedCourseRead): Promise<void> {
  await ElMessageBox.confirm(
    `退出后将从「我查过的课」中移除课程「${row.name}」，确认退出？`,
    '退出课程',
    { confirmButtonText: '退出', cancelButtonText: '取消', type: 'warning' },
  )
  try {
    await leaveCourse(row.id)
    ElMessage.success('已退出课程')
    void load()
  } catch {
    // 错误已由 http 层统一提示
  }
}

void load()
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">我查过的课</h2>
        <p class="page-subtitle">展示你主动加入的全部课程与加入时间</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </div>

    <div class="filter-bar">
      <el-input
        v-model="filters.teacherName"
        clearable
        placeholder="教师名称"
        class="filter-location"
        @keyup.enter="load"
      />
      <el-select v-model="filters.location" clearable filterable placeholder="上课地点" class="filter-item">
        <el-option-group
          v-for="group in LOCATION_GROUPS"
          :key="group.building"
          :label="group.building"
        >
          <el-option v-for="item in group.rooms" :key="item" :label="item" :value="item" />
        </el-option-group>
      </el-select>
      <el-select v-model="filters.weekday" clearable placeholder="星期" class="filter-item">
        <el-option
          v-for="(label, index) in WEEKDAY_LABELS"
          :key="label"
          :label="label"
          :value="index + 1"
        />
      </el-select>
      <el-time-picker
        v-model="filters.time"
        clearable
        format="HH:mm"
        value-format="HH:mm"
        placeholder="时间（任一时段）"
        class="filter-item"
      />
      <el-input
        v-model="filters.name"
        clearable
        placeholder="课程名称"
        class="filter-location"
        @keyup.enter="load"
      />
      <el-button type="primary" :icon="Search" @click="load">筛选</el-button>
      <el-button @click="resetFilters">重置</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />

    <div v-else-if="error" class="state-panel">
      <el-empty :description="error.message || '加载失败'">
        <el-button type="primary" @click="load">重试</el-button>
      </el-empty>
    </div>

    <el-empty
      v-else-if="courses.length === 0"
      :description="hasFilter ? '没有符合筛选条件的课程' : '还没有加入过课程，去「全部课程」加入要督导的课程吧'"
    />

    <el-table v-else :data="courses" class="course-table" @row-click="openDetail">
      <el-table-column label="课程名称" min-width="180">
        <template #default="{ row }">
          <span class="course-name">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="code" label="课程编号" width="120" />
      <el-table-column label="教师" width="120">
        <template #default="{ row }">
          <span>{{ row.teacher_name }}</span>
          <span v-if="row.teacher_id === null" class="text-secondary">（未匹配）</span>
        </template>
      </el-table-column>
      <el-table-column prop="location" label="上课地点" width="100" />
      <el-table-column label="授课时间" min-width="220">
        <template #default="{ row }">
          <span class="text-secondary">{{ formatSchedules(row.schedules) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="加入时间" width="170">
        <template #default="{ row }">
          <span class="tabular text-secondary">{{ formatDateTime(row.joined_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button
            text
            type="primary"
            :icon="View"
            aria-label="查看课程详情"
            title="查看课程详情"
            @click.stop="openDetail(row)"
          >
            详情
          </el-button>
          <el-button
            text
            type="danger"
            aria-label="退出课程"
            title="退出课程"
            @click.stop="handleLeave(row)"
          >
            退出
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.course-table {
  background: var(--surface);
  border-radius: var(--radius);
}

.course-name {
  font-weight: 500;
}

.state-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

:deep(.el-table__row) {
  cursor: pointer;
}

/* 与全部课程页一致的筛选栏布局：单行紧凑排列 */
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.filter-location {
  width: 180px;
}

.filter-item {
  width: 150px;
}
</style>
