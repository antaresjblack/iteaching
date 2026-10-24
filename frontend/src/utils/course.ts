/** 课程展示工具：状态/考察形式文案与多时间段格式化 */
import type { AssessmentForm, CourseSchedule, CourseStatus } from '@/types/course'

export const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export const COURSE_STATUS_LABELS: Record<CourseStatus, string> = {
  not_started: '未开始',
  in_progress: '进行中',
  finished: '已结束',
}

export const COURSE_STATUS_TAG_TYPES: Record<CourseStatus, 'info' | 'primary' | 'success'> = {
  not_started: 'info',
  in_progress: 'primary',
  finished: 'success',
}

export const ASSESSMENT_FORM_LABELS: Record<AssessmentForm, string> = {
  percent: '百分制',
}

export function weekdayLabel(weekday: number): string {
  return WEEKDAY_LABELS[weekday - 1] ?? '—'
}

/** 多时间段 → "周一 08:30-10:10（第1-16周）；周三 14:00-15:40" */
export function formatSchedules(schedules: CourseSchedule[] | null | undefined): string {
  if (!schedules || schedules.length === 0) return '—'
  return schedules
    .map((item) => `${weekdayLabel(item.weekday)} ${item.start_time}-${item.end_time}${weekLabel(item)}`)
    .join('；')
}

/** 周次范围文案：未设置周次时返回空串 */
export function weekLabel(item: CourseSchedule): string {
  if (item.start_week == null || item.end_week == null) return ''
  return item.start_week === item.end_week
    ? `（第${item.start_week}周）`
    : `（第${item.start_week}-${item.end_week}周）`
}

/** 节次时间表：按第 X 节映射起止时间（第 3-4 节 → 10:30-12:10） */
export const PERIOD_TIMES = [
  { start: '08:30', end: '09:15' },
  { start: '09:25', end: '10:10' },
  { start: '10:30', end: '11:15' },
  { start: '11:25', end: '12:10' },
  { start: '14:00', end: '14:45' },
  { start: '14:55', end: '15:40' },
  { start: '16:00', end: '16:45' },
  { start: '16:55', end: '17:40' },
] as const

/** 节次下拉选项：第 1 节 ~ 第 8 节 */
export const PERIOD_OPTIONS = PERIOD_TIMES.map((_, index) => ({
  value: index + 1,
  label: `第 ${index + 1} 节`,
}))

/** 授课班级可选班级（支持 allow-create 自定义输入） */
export const CLASS_OPTIONS = Array.from({ length: 15 }, (_, i) => `${i + 1}班`)

/** 年级可选范围：当前年份前后各覆盖数届 */
export const GRADE_OPTIONS = [2022, 2023, 2024, 2025, 2026, 2027, 2028]

/** 学期起始日期（MM.DD，前端默认值；后端可通过 /api/v1/config 下发，需与其 config 保持一致） */
export const SEMESTER_STARTS = { spring: '03.01', autumn: '08.31' } as const

/** 当前教学周信息 */
export interface TeachingWeek {
  semester: 'spring' | 'autumn'
  /** 学期起点所在年份（1-2 月仍归属上一年秋季学期） */
  year: number
  /** 教学周序号，从第 1 周开始 */
  week: number
}

/**
 * 推断给定日期所处的学期与教学周。
 * 取不晚于该日期的最近一个学期起点（去年/今年/明年的春、秋起点中挑选），
 * 按「起点当天为第 1 周第 1 天、每 7 天进入下一周」推算周序号。
 */
export function teachingWeekOf(
  now: Date,
  starts: { spring: string; autumn: string } = SEMESTER_STARTS,
): TeachingWeek {
  const candidates: Array<{ semester: 'spring' | 'autumn'; start: Date }> = []
  for (const year of [now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1]) {
    for (const key of ['spring', 'autumn'] as const) {
      const [month, day] = starts[key].split('.').map(Number)
      candidates.push({ semester: key, start: new Date(year, (month ?? 1) - 1, day ?? 1) })
    }
  }
  const current = candidates
    .filter((item) => item.start.getTime() <= now.getTime())
    .sort((a, b) => b.start.getTime() - a.start.getTime())[0]
  if (!current) return { semester: 'autumn', year: now.getFullYear(), week: 1 }
  const days = Math.floor((now.getTime() - current.start.getTime()) / 86400000)
  return { semester: current.semester, year: current.start.getFullYear(), week: Math.floor(days / 7) + 1 }
}

export interface ParsedClassName {
  department: string
  grade: number
  classes: string[]
}

/** 将 class_name 文本反解为院系/年级/班级三段，格式不符时返回 null */
export function parseClassName(value: string): ParsedClassName | null {
  const match = value.match(/^(.+?学院)\s*(\d{4})级\s*(.+)$/)
  if (!match) return null
  const classes = match[3].split(/[、，,;；\s]+/).filter(Boolean)
  if (classes.length === 0) return null
  return { department: match[1], grade: Number(match[2]), classes }
}
