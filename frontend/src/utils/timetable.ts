/** 周课表工具：时间段→节次映射与课程卡片网格布局计算（纯函数，便于单元测试） */
import type { CourseRead, CourseSchedule } from '@/types/course'

import { ASSESSMENT_FORM_LABELS, PERIOD_TIMES, weekLabel } from '@/utils/course'

/** 课表卡片马卡龙配色：低饱和度柔和色系，按课程循环取色 */
export const TIMETABLE_COLORS = ['#FFF2CC', '#E2F0D9', '#DEEBF7', '#E2DFF0', '#FCE4D6'] as const

/** 周课表节次数（与 PERIOD_TIMES 一一对应） */
export const PERIOD_COUNT = PERIOD_TIMES.length

/** 一张课表卡片：网格位置 + 展示字段 */
export interface TimetableCard {
  courseId: number
  name: string
  location: string
  className: string
  teacherName: string
  assessment: string
  /** 1-7 对应周一至周日（网格列 = weekday + 1，第 1 列为节次表头） */
  weekday: number
  /** 起始节次（1 起，网格行 = startPeriod + 1，第 1 行为星期表头） */
  startPeriod: number
  /** 跨节数（连续上多节时垂直合并） */
  span: number
  /** 周次文案，如「第1-16周」，未设置时为空串 */
  week: string
  /** 配色下标 */
  colorIndex: number
  /** 原始课程数据，点击卡片时回传 */
  course: CourseRead
}

/** HH:MM 转分钟数，用于无重叠时的最近节次回退计算 */
function toMinutes(time: string): number {
  const [h, m] = time.split(':').map(Number)
  return (h ?? 0) * 60 + (m ?? 0)
}

/**
 * 将一个授课时间段映射到节次区间。
 * 与节次时间有重叠的节次全部纳入（如 08:30-10:10 → 第 1-2 节，08:30-12:10 → 第 1-4 节）；
 * 完全落在节次表之外的时间（如晚间课）回退为时间上最接近的单节，保证卡片可见。
 */
export function periodRange(schedule: CourseSchedule): { start: number; span: number } {
  const hits: number[] = []
  PERIOD_TIMES.forEach((period, index) => {
    if (schedule.start_time < period.end && schedule.end_time > period.start) hits.push(index + 1)
  })
  if (hits.length > 0) return { start: hits[0], span: hits.length }

  let nearest = 1
  let best = Number.POSITIVE_INFINITY
  PERIOD_TIMES.forEach((period, index) => {
    const diff = Math.abs(toMinutes(schedule.start_time) - toMinutes(period.start))
    if (diff < best) {
      best = diff
      nearest = index + 1
    }
  })
  return { start: nearest, span: 1 }
}

/**
 * 将课程列表转换为课表卡片。
 * 同一课程的多条时间段各自生成卡片并共用配色；已被占用的节次不再重复放置
 * （后段从冲突处截断，起始节次被占则丢弃该时间段），避免卡片重叠。
 */
export function buildTimetableCards(courses: CourseRead[]): TimetableCard[] {
  const cards: TimetableCard[] = []
  const occupied = new Set<string>()
  for (const course of courses) {
    const colorIndex = course.id % TIMETABLE_COLORS.length
    for (const schedule of course.schedules ?? []) {
      const { start, span } = periodRange(schedule)
      const slots: string[] = []
      for (let offset = 0; offset < span; offset += 1) {
        const key = `${schedule.weekday}-${start + offset}`
        if (occupied.has(key)) break
        slots.push(key)
      }
      if (slots.length === 0) continue
      slots.forEach((key) => occupied.add(key))
      cards.push({
        courseId: course.id,
        name: course.name,
        location: course.location,
        className: course.class_name,
        teacherName: course.teacher_name,
        assessment: ASSESSMENT_FORM_LABELS[course.assessment_form] ?? course.assessment_form,
        weekday: schedule.weekday,
        startPeriod: start,
        span: slots.length,
        // 卡片内展示不带括号的周次文案（weekLabel 返回「（第X-Y周）」）
        week: weekLabel(schedule).replace(/[（）]/g, ''),
        colorIndex,
        course,
      })
    }
  }
  return cards
}
