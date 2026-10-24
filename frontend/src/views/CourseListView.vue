<script setup lang="ts">
import { Delete, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createCourse, listCourses, updateCourse } from '@/api/courses'
import { joinCourse } from '@/api/supervisions'
import { searchTeachers, type TeacherCandidate } from '@/api/users'
import WeeklyTimetable from '@/components/WeeklyTimetable.vue'
import { useAuthStore } from '@/stores/auth'
import { DEPARTMENTS } from '@/types/auth'
import type {
  AssessmentForm,
  CourseCreate,
  CourseQuery,
  CourseRead,
  CourseSchedule,
  CourseStatus,
  TeachingLocation,
} from '@/types/course'
import { LOCATION_GROUPS } from '@/types/course'
import {
  ASSESSMENT_FORM_LABELS,
  CLASS_OPTIONS,
  COURSE_STATUS_LABELS,
  COURSE_STATUS_TAG_TYPES,
  GRADE_OPTIONS,
  PERIOD_OPTIONS,
  PERIOD_TIMES,
  WEEKDAY_LABELS,
  formatSchedules,
  parseClassName,
  teachingWeekOf,
  weekLabel,
} from '@/utils/course'
import { SEMESTER_STARTS } from '@/utils/course'

const auth = useAuthStore()
const router = useRouter()

const loading = ref(false)
const error = ref<Error | null>(null)
const courses = ref<CourseRead[]>([])

/** 筛选条件：教师名称、上课地点、时间、课程名称，支持组合查询；时间按任一时间段匹配 */
const filters = reactive({
  teacherName: '',
  location: '',
  weekday: null as number | null,
  time: null as string | null,
  name: '',
})

const dialogVisible = ref(false)
const dialogSubmitting = ref(false)
const formRef = ref<FormInstance>()

/** 新建/编辑共用表单；id 为 null 表示新建。班级拆为院系/年级/班级三段；教师强制匹配系统已有账号 */
const form = reactive({
  id: null as number | null,
  code: '',
  name: '',
  location: null as TeachingLocation | null,
  classDept: '',
  classGrade: null as number | null,
  classClasses: [] as string[],
  schedules: [] as CourseSchedule[],
  assessmentForm: 'percent' as AssessmentForm,
  description: '',
  teacherId: null as number | null,
  teacherName: '',
  status: 'not_started' as CourseStatus,
})

/** 教师搜索框：展示用输入（display）、下拉候选列表、是否命中有效账号 */
const teacherQuery = ref('')
const teacherCandidates = ref<TeacherCandidate[]>([])
const teacherSelected = ref<TeacherCandidate | null>(null)
const teacherSearching = ref(false)
const teacherNoMatch = ref(false)
let teacherDebounceTimer: ReturnType<typeof setTimeout> | null = null

/** 时间段录入模式：single 逐条设置；weekly 按周批量（星期 + 节次 + 周次范围） */
const scheduleMode = ref<'single' | 'weekly'>('single')

/** 按周批量的临时表单：同一周次范围内星期与节次保持一致 */
const batch = reactive({
  weekday: 3,
  startPeriod: 3,
  endPeriod: 4,
  startWeek: 1,
  endWeek: 16,
})

/** 编辑课程仅管理员可见（督导不允许编辑课程详细信息） */
const canEdit = computed(() => auth.user?.role === 'admin')
const isSupervisor = computed(() => auth.user?.role === 'supervisor')

/** 新建课程仅管理员可见；督导端首页按要求移除新建入口（仅保留编辑） */
const canCreate = computed(() => auth.user?.role === 'admin')

const dialogTitle = computed(() => (form.id === null ? '新建课程' : '编辑课程'))

/** 教师视图：课程展示重构为网格周课表，点击卡片进入课程详情（上传录音、查看评价等） */
const isTeacher = computed(() => auth.user?.role === 'teacher')

/** 表格 slot 中的 row 为 any，这里统一收口类型，避免模板内索引报错 */
function assessmentLabel(value: AssessmentForm): string {
  return ASSESSMENT_FORM_LABELS[value] ?? value
}

function statusLabel(value: CourseStatus): string {
  return COURSE_STATUS_LABELS[value] ?? value
}

function statusTagType(value: CourseStatus): 'info' | 'primary' | 'success' {
  return COURSE_STATUS_TAG_TYPES[value] ?? 'info'
}

const rules: FormRules = {
  code: [
    { required: true, message: '请输入课程编号', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_-]+$/, message: '课程编号仅支持字母、数字、下划线与短横线', trigger: 'blur' },
  ],
  name: [{ required: true, message: '请输入课程名称', trigger: 'blur' }],
  location: [{ required: true, message: '请选择上课地址', trigger: 'change' }],
  classDept: [{ required: true, message: '请选择开课院系', trigger: 'change' }],
  classGrade: [{ required: true, message: '请选择年级', trigger: 'change' }],
  classClasses: [
    {
      required: true,
      validator: (
        _rule: object,
        value: string[] | null,
        callback: (error?: Error) => void,
      ) => {
        if (!value || value.length === 0) callback(new Error('请至少选择一个班级'))
        else callback()
      },
      trigger: 'change',
    },
  ],
}

/** 学期起始日期使用 utils/course 中的 SEMESTER_STARTS（与后端 config 保持一致） */

/** 根据当前月份推断所属学期（9 月起是秋季，3 月起是春季） */
const currentSemester = computed<'spring' | 'autumn'>(() => {
  const m = new Date().getMonth() + 1
  return m >= 9 || m <= 2 ? 'autumn' : 'spring'
})
const semesterStartLabel = computed(
  () => (currentSemester.value === 'spring' ? '春季' : '秋季') + `学期 · ${SEMESTER_STARTS[currentSemester.value]} 为第 1 周`,
)

/** 教师课表头部：当前教学周（按学期起始日期自动推算） */
const teachingWeek = computed(() => teachingWeekOf(new Date()))

/** 教师搜索：300ms 防抖，支持姓名/院系/工号模糊匹配。
 *  el-autocomplete 的 fetch-suggestions 回调要求 item 必须带 value 字段，
 *  点击候选项时 value 会回填到输入框，@select 回调拿到完整 item。
 */
function fetchTeacherSuggestions(queryString: string, cb: (arg: unknown[]) => void): void {
  if (teacherDebounceTimer) clearTimeout(teacherDebounceTimer)
  if (!queryString.trim()) {
    cb([])
    return
  }
  teacherDebounceTimer = setTimeout(async () => {
    teacherSearching.value = true
    try {
      const list = await searchTeachers(queryString.trim(), 10)
      teacherCandidates.value = list
      // 必须构造带 value 字段的 items，否则 el-autocomplete 无法回填
      cb(list.map((c) => ({ value: formatTeacherLabel(c), ...c })))
    } catch {
      teacherCandidates.value = []
      cb([])
    } finally {
      teacherSearching.value = false
    }
  }, 300)
}

/** 教师选择回调：点击下拉候选后，el-autocomplete 会把带 value + id 的 item 传进来 */
function onTeacherSelect(item: { id: number; name: string }): void {
  teacherSelected.value = { id: item.id, name: item.name } as TeacherCandidate
  teacherNoMatch.value = false
  form.teacherId = item.id
  form.teacherName = item.name
}

/** 教师输入变化：清空已选中，等待重新匹配 */
function onTeacherInputChange(value: string): void {
  // 若输入框内容与当前选中教师的展示文本一致则保持
  if (
    teacherSelected.value &&
    value === formatTeacherLabel(teacherSelected.value as TeacherCandidate)
  )
    return
  teacherSelected.value = null
  teacherNoMatch.value = value.trim().length > 0
  form.teacherId = null
  form.teacherName = ''
}

/** 教师输入框 blur 时若未选中任何候选项，标记"未找到该教师" */
function onTeacherBlur(): void {
  if (teacherSelected.value === null && teacherQuery.value.trim().length > 0) {
    teacherNoMatch.value = true
  }
}

/** 教师下拉候选展示文本：姓名 + 院系 + 工号 */
function formatTeacherLabel(c: TeacherCandidate): string {
  const parts = [c.name, c.department, c.employee_no].filter(Boolean)
  return parts.join(' · ')
}

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
    courses.value = await listCourses(query)
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

function resetForm(): void {
  form.id = null
  form.code = ''
  form.name = ''
  form.location = null
  form.classDept = ''
  form.classGrade = null
  form.classClasses = []
  form.schedules = [{ weekday: 1, start_time: '08:30', end_time: '10:10' }]
  form.assessmentForm = 'percent'
  form.description = ''
  form.teacherId = null
  form.teacherName = ''
  form.status = 'not_started'
  scheduleMode.value = 'single'
  teacherQuery.value = ''
  teacherSelected.value = null
  teacherCandidates.value = []
  teacherNoMatch.value = false
}

function openCreate(): void {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: CourseRead): void {
  form.id = row.id
  form.code = row.code
  form.name = row.name
  form.location = row.location as TeachingLocation
  const parsed = parseClassName(row.class_name)
  form.classDept = parsed?.department ?? ''
  form.classGrade = parsed?.grade ?? null
  form.classClasses = parsed ? [...parsed.classes] : [row.class_name]
  form.schedules = row.schedules.length
    ? row.schedules.map((item) => ({ ...item }))
    : [{ weekday: 1, start_time: '08:30', end_time: '10:10' }]
  form.assessmentForm = row.assessment_form
  form.description = row.description ?? ''
  form.teacherId = row.teacher_id
  form.teacherName = row.teacher_name
  form.status = row.status
  // 编辑时若有已匹配教师，构造一个"伪"候选用于回显；教师搜索字段用姓名展示
  if (row.teacher_id != null) {
    teacherSelected.value = {
      id: row.teacher_id,
      name: row.teacher_name,
      department: null,
      employee_no: null,
      username: '',
    }
    teacherQuery.value = row.teacher_name
    teacherNoMatch.value = false
  } else {
    teacherSelected.value = null
    teacherQuery.value = ''
    teacherNoMatch.value = true
  }
  dialogVisible.value = true
}

function addSchedule(): void {
  form.schedules.push({ weekday: 1, start_time: '08:30', end_time: '10:10' })
}

/** 按周批量添加：星期 + 节次范围 + 周次范围折算为一条时间段（范围内时间一致） */
function addBatchSchedule(): void {
  if (batch.startPeriod > batch.endPeriod) {
    ElMessage.warning('结束节次不能早于起始节次')
    return
  }
  if (batch.endWeek < batch.startWeek) {
    ElMessage.warning('结束周不能早于起始周')
    return
  }
  const start = PERIOD_TIMES[batch.startPeriod - 1]
  const end = PERIOD_TIMES[batch.endPeriod - 1]
  form.schedules.push({
    weekday: batch.weekday,
    start_time: start.start,
    end_time: end.end,
    start_week: batch.startWeek,
    end_week: batch.endWeek,
  })
}

function removeSchedule(index: number): void {
  form.schedules.splice(index, 1)
}

function schedulesValid(): boolean {
  if (form.schedules.length === 0) {
    ElMessage.warning('请至少添加一个授课时间段')
    return false
  }
  for (const item of form.schedules) {
    if (!item.start_time || !item.end_time || item.end_time <= item.start_time) {
      ElMessage.warning('授课时间段的结束时间必须晚于开始时间')
      return false
    }
    if (item.start_week != null && item.end_week != null && item.end_week < item.start_week) {
      ElMessage.warning('授课时间段的结束周不能早于起始周')
      return false
    }
  }
  return true
}

function buildPayload(): CourseCreate {
  return {
    code: form.code.trim(),
    name: form.name.trim(),
    location: form.location ?? '',
    // 三段班级拼接为文本存储：如"计算机学院 2026级 1班、2班"
    class_name: `${form.classDept} ${form.classGrade}级 ${form.classClasses.join('、')}`.trim(),
    schedules: form.schedules.map((item) => ({ ...item })),
    assessment_form: form.assessmentForm,
    description: form.description.trim() || null,
    teacher_id: form.teacherId,
    teacher_name: form.teacherName.trim(),
    status: form.status,
  }
}

async function handleSubmit(): Promise<void> {
  if (dialogSubmitting.value) return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || !schedulesValid()) return
  if (!teacherSelected.value || !form.teacherId) {
    ElMessage.warning('请先从下拉列表中选择一位已存在的教师')
    teacherNoMatch.value = true
    return
  }
  dialogSubmitting.value = true
  try {
    if (form.id === null) {
      const course = await createCourse(buildPayload())
      ElMessage.success('课程已创建')
      courses.value = [course, ...courses.value]
    } else {
      const course = await updateCourse(form.id, buildPayload())
      const index = courses.value.findIndex((item) => item.id === course.id)
      if (index >= 0) courses.value.splice(index, 1, course)
      ElMessage.success('课程已更新')
    }
    dialogVisible.value = false
  } catch {
    // 错误已由 http 层统一提示
  } finally {
    dialogSubmitting.value = false
  }
}

function goDetail(row: CourseRead): void {
  void router.push({ name: 'course-detail', params: { id: row.id } })
}

/** 督导主动加入课程（幂等）：加入后可在「我查过的课」中看到 */
async function handleJoin(row: CourseRead): Promise<void> {
  try {
    await joinCourse(row.id)
    ElMessage.success(`已加入课程「${row.name}」`)
  } catch {
    // 错误已由 http 层统一提示
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <!-- 教师视图：课程展示重构为网格周课表，点击卡片进入课程详情 -->
    <template v-if="isTeacher">
      <div class="page-header">
        <div>
          <h2 class="page-title">
            我的课表
            <el-tag class="week-tag" type="primary" effect="light">
              {{ teachingWeek.year }}{{ teachingWeek.semester === 'spring' ? '春季' : '秋季' }}学期 · 教学周第
              {{ teachingWeek.week }} 周
            </el-tag>
          </h2>
          <p class="page-subtitle">按周展示授课安排，跨节课程纵向合并，点击卡片进入课程详情</p>
        </div>
      </div>

      <div v-if="error" class="state-panel">
        <el-empty description="加载课程失败">
          <el-button type="primary" @click="load">重试</el-button>
        </el-empty>
      </div>
      <div v-else class="state-panel" v-loading="loading" element-loading-text="加载中...">
        <WeeklyTimetable :courses="courses" @select="goDetail" />
      </div>
    </template>

    <!-- 管理员 / 督导视图：课程列表 -->
    <template v-else>
    <div class="page-header">
      <div>
        <h2 class="page-title">全部课程</h2>
        <p class="page-subtitle">支持按教师名称、上课地点、时间、课程名称组合筛选，点击课程行查看详情</p>
      </div>
      <el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreate">新建课程</el-button>
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
        <el-option v-for="(label, index) in WEEKDAY_LABELS" :key="label" :label="label" :value="index + 1" />
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
      <el-empty :description="error.message || '课程列表加载失败'">
        <el-button type="primary" @click="load">重试</el-button>
      </el-empty>
    </div>

    <el-empty v-else-if="courses.length === 0" description="暂无课程">
      <el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreate">新建课程</el-button>
    </el-empty>

    <el-table v-else :data="courses" class="course-table" @row-click="goDetail">
      <el-table-column prop="code" label="课程编号" width="130">
        <template #default="{ row }">
          <span class="tabular">{{ row.code }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="课程名称" min-width="180">
        <template #default="{ row }">
          <span class="course-name">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="location" label="上课地址" min-width="140" />
      <el-table-column prop="class_name" label="授课班级" min-width="140" />
      <el-table-column label="授课时间" min-width="200">
        <template #default="{ row }">
          <span class="text-secondary">{{ formatSchedules(row.schedules) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="考察形式" width="100">
        <template #default="{ row }">
          {{ assessmentLabel(row.assessment_form) }}
        </template>
      </el-table-column>
      <el-table-column label="教师" min-width="130">
        <template #default="{ row }">
          <span>{{ row.teacher_name }}</span>
          <el-tag v-if="row.teacher_id === null" size="small" type="warning" class="teacher-tag">未匹配</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTagType(row.status)">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="canEdit || isSupervisor" label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canEdit" text type="primary" @click.stop="openEdit(row)">编辑</el-button>
          <el-button v-if="isSupervisor" text type="primary" @click.stop="handleJoin(row)">加入</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="680px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="form-grid">
          <el-form-item label="课程编号" prop="code">
            <el-input v-model="form.code" maxlength="40" placeholder="如：MATH-001" />
          </el-form-item>
          <el-form-item label="课程名称" prop="name">
            <el-input v-model="form.name" maxlength="200" placeholder="如：高等数学" />
          </el-form-item>
          <el-form-item label="上课地址" prop="location">
            <el-select v-model="form.location" filterable placeholder="请选择上课地址">
              <el-option-group
                v-for="group in LOCATION_GROUPS"
                :key="group.building"
                :label="group.building"
              >
                <el-option v-for="item in group.rooms" :key="item" :label="item" :value="item" />
              </el-option-group>
            </el-select>
          </el-form-item>
          <el-form-item label="开课院系" prop="classDept">
            <el-select v-model="form.classDept" placeholder="如：计算机学院">
              <el-option v-for="item in DEPARTMENTS" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="年级" prop="classGrade">
            <el-select v-model="form.classGrade" placeholder="如：2026 级">
              <el-option v-for="grade in GRADE_OPTIONS" :key="grade" :label="`${grade} 级`" :value="grade" />
            </el-select>
          </el-form-item>
          <el-form-item label="授课班级" prop="classClasses">
            <el-select
              v-model="form.classClasses"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="班级（可多选，支持自定义）"
            >
              <el-option v-for="item in CLASS_OPTIONS" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
        </div>

        <el-form-item label="授课时间">
          <div class="schedule-block">
            <el-radio-group v-model="scheduleMode" size="small" class="schedule-mode">
              <el-radio-button label="single">逐条添加</el-radio-button>
              <el-radio-button label="weekly">按周批量</el-radio-button>
            </el-radio-group>

            <template v-if="scheduleMode === 'weekly'">
              <div class="semester-hint">
                <span>📅 当前学期：</span>
                <span class="semester-label">{{ semesterStartLabel }}</span>
                <span class="semester-tip">（可在后端配置中调整起始日期）</span>
              </div>
              <div class="batch-row">
                <el-select v-model="batch.weekday" class="schedule-weekday" placeholder="星期">
                  <el-option v-for="(label, i) in WEEKDAY_LABELS" :key="label" :label="label" :value="i + 1" />
                </el-select>
                <el-select v-model="batch.startPeriod" class="schedule-period" placeholder="起始节次">
                  <el-option v-for="opt in PERIOD_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <span class="text-secondary">至</span>
                <el-select v-model="batch.endPeriod" class="schedule-period" placeholder="结束节次">
                  <el-option v-for="opt in PERIOD_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <span class="text-secondary">第</span>
                <el-input-number v-model="batch.startWeek" :min="1" :max="52" :controls="false" class="schedule-week" />
                <span class="text-secondary">-</span>
                <el-input-number v-model="batch.endWeek" :min="1" :max="52" :controls="false" class="schedule-week" />
                <span class="text-secondary">周</span>
                <el-button type="primary" :icon="Plus" @click="addBatchSchedule">添加</el-button>
              </div>
            </template>

            <div class="schedule-list">
              <div v-for="(item, index) in form.schedules" :key="index" class="schedule-row">
                <el-select v-model="item.weekday" class="schedule-weekday" placeholder="星期">
                  <el-option v-for="(label, i) in WEEKDAY_LABELS" :key="label" :label="label" :value="i + 1" />
                </el-select>
                <el-time-picker
                  v-model="item.start_time"
                  format="HH:mm"
                  value-format="HH:mm"
                  placeholder="开始"
                  class="schedule-time"
                />
                <span class="text-secondary">至</span>
                <el-time-picker
                  v-model="item.end_time"
                  format="HH:mm"
                  value-format="HH:mm"
                  placeholder="结束"
                  class="schedule-time"
                />
                <el-tag v-if="item.start_week != null && item.end_week != null" size="small" class="week-tag">
                  {{ weekLabel(item) }}
                </el-tag>
                <el-button text type="danger" :icon="Delete" aria-label="删除时间段" @click="removeSchedule(index)" />
              </div>
              <el-button v-if="scheduleMode === 'single'" text type="primary" :icon="Plus" @click="addSchedule">
                添加时间段
              </el-button>
            </div>
          </div>
        </el-form-item>

        <div class="form-grid">
          <el-form-item label="考察形式">
            <el-select v-model="form.assessmentForm">
              <el-option
                v-for="(label, value) in ASSESSMENT_FORM_LABELS"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="课程状态">
            <el-select v-model="form.status">
              <el-option
                v-for="(label, value) in COURSE_STATUS_LABELS"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="教师" required>
            <el-autocomplete
              v-model="teacherQuery"
              :fetch-suggestions="fetchTeacherSuggestions"
              placeholder="输入姓名/院系/工号搜索..."
              :loading="teacherSearching"
              clearable
              @select="onTeacherSelect"
              @input="onTeacherInputChange"
              @blur="onTeacherBlur"
            >
              <template #default="{ item }">
                <div class="teacher-option">
                  <span class="teacher-option-name">{{ item.name }}</span>
                  <span class="teacher-option-meta">{{ item.department }} · {{ item.employee_no }}</span>
                </div>
              </template>
            </el-autocomplete>
            <p v-if="teacherNoMatch && !teacherSelected" class="field-tip error-tip">
              未找到该教师，请从下拉列表中选择一位已存在的教师
            </p>
          </el-form-item>
        </div>

        <el-form-item label="课程简介">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="选填，最多 500 字"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="dialogSubmitting" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="dialogSubmitting" @click="handleSubmit">
          {{ form.id === null ? '创建' : '保存' }}
        </el-button>
      </template>
    </el-dialog>
    </template>
  </div>
</template>

<style scoped>
/* 教师课表标题旁的教学周标签 */
.week-tag {
  margin-left: 10px;
  vertical-align: middle;
  font-weight: 500;
}

.state-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

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

.course-table {
  background: var(--surface);
  border-radius: var(--radius);
  cursor: pointer;
}

.course-name {
  color: var(--brand);
  font-weight: 500;
}

.teacher-tag {
  margin-left: 6px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}

.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.schedule-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.schedule-mode {
  align-self: flex-start;
}

.batch-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}

.schedule-period {
  width: 120px;
}

.schedule-week {
  width: 64px;
}

.week-tag {
  flex-shrink: 0;
}

.field-tip {
  margin: 0 0 12px;
  color: var(--text-secondary, #909399);
  font-size: 12px;
  line-height: 1.6;
}

.error-tip {
  color: var(--el-color-danger, #f56c6c);
}

.semester-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #f0f9ff;
  border: 1px solid #b3e5fc;
  border-radius: 4px;
  font-size: 12px;
  color: #0288d1;
}

.semester-label {
  font-weight: 600;
}

.semester-tip {
  color: #78909c;
}

.teacher-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.teacher-option-name {
  font-weight: 500;
}

.teacher-option-meta {
  color: var(--text-secondary, #909399);
  font-size: 12px;
}

.schedule-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.schedule-weekday {
  width: 96px;
}

.schedule-time {
  width: 120px;
}
</style>
