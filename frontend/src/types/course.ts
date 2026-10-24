/** 课程状态：未开始 / 进行中 / 已结束 */
export type CourseStatus = 'not_started' | 'in_progress' | 'finished'

/** 考察形式：当前仅百分制，预留其他形式 */
export type AssessmentForm = 'percent'

/**
 * 上课地址枚举：教学楼 + 3 位教室编号（如 文法227），新建课程时只能从下列值中选择。
 * 历史课程可能仍保存旧的纯教学楼值，编辑旧课程时原值会原样回显。
 */
export type LegacyLocation = '1号楼' | '生医' | '文法' | '建筑' | '信息'

/** 每栋教学楼的教室编号（3 位数字） */
export const CLASSROOM_NUMBERS = ['101', '102', '103', '104', '105'] as const

/** 教学楼列表：与后端 TeachingLocation 枚举保持一致 */
export const LOCATION_BUILDINGS: readonly LegacyLocation[] = ['1号楼', '生医', '文法', '建筑', '信息']

/** 教室选项：教学楼 + 教室编号（模板字面量类型展开为 25 个组合） */
export type ClassroomLocation = `${LegacyLocation}${(typeof CLASSROOM_NUMBERS)[number]}` | '文管A447'

export type TeachingLocation = LegacyLocation | ClassroomLocation

/** 按教学楼分组的教室选项，供下拉框 el-option-group 使用 */
export const LOCATION_GROUPS: ReadonlyArray<{
  building: LegacyLocation | '文管'
  rooms: ClassroomLocation[]
}> = [...LOCATION_BUILDINGS.map((building) => ({
  building,
  rooms: CLASSROOM_NUMBERS.map((room) => `${building}${room}` as ClassroomLocation),
})), { building: '文管', rooms: ['文管A447'] }]

/** 全部教室选项（扁平列表，用于筛选栏等场景） */
export const LOCATION_OPTIONS: readonly ClassroomLocation[] = LOCATION_GROUPS.flatMap(
  (group) => group.rooms,
)

/** 单个授课时间段：weekday 1-7 对应周一至周日，时间为 HH:MM；周次为按周批量录入时的可选范围 */
export interface CourseSchedule {
  weekday: number
  start_time: string
  end_time: string
  start_week?: number
  end_week?: number
}

/** 后端 CourseRead */
export interface CourseRead {
  id: number
  code: string
  name: string
  location: string
  class_name: string
  schedules: CourseSchedule[]
  assessment_form: AssessmentForm
  description: string | null
  teacher_id: number | null
  teacher_name: string
  status: CourseStatus
  created_at: string
}

/** POST /courses 请求体 */
export interface CourseCreate {
  code: string
  name: string
  location: string
  class_name: string
  schedules: CourseSchedule[]
  assessment_form: AssessmentForm
  description?: string | null
  teacher_id?: number | null
  teacher_name: string
  status: CourseStatus
}

/** PATCH /courses/{id} 请求体：仅提交需要更新的字段 */
export type CourseUpdate = Partial<CourseCreate>

/** GET /courses 筛选参数 */
export interface CourseQuery {
  location?: string
  status?: CourseStatus
  teacher_id?: number
  /** 教师名称模糊匹配 */
  teacher_name?: string
  /** 课程名称模糊匹配 */
  name?: string
  weekday?: number
  /** HH:MM，按任一时间段匹配 */
  time?: string
}

/** GET /supervisions/my-courses 列表项：课程 + 最近关联时间 */
export interface SupervisedCourseRead extends CourseRead {
  last_linked_at: string
}
