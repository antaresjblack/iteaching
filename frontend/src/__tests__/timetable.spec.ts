/** 周课表工具测试：时间段→节次映射、跨节合并、占位冲突与配色分配 */
import { describe, expect, it } from 'vitest'

import type { CourseRead, CourseSchedule } from '@/types/course'
import { teachingWeekOf } from '@/utils/course'
import { buildTimetableCards, periodRange } from '@/utils/timetable'

/** 构造一条课程记录的辅助函数，schedules 为可选时间段数组 */
function makeCourse(id: number, schedules: CourseSchedule[]): CourseRead {
  return {
    id,
    code: `C-${id}`,
    name: `课程${id}`,
    location: '文法101',
    class_name: '计算机学院 2024级 3班',
    schedules,
    assessment_form: 'percent',
    description: null,
    teacher_id: null,
    teacher_name: '张老师',
    status: 'not_started',
    created_at: '2026-10-23T00:00:00Z',
  }
}

describe('periodRange 时间段→节次映射', () => {
  it('两节连上的时间段映射为跨 2 节（08:30-10:10 → 第 1-2 节）', () => {
    // 标准两节连排：起止时间与节次表完全对齐
    const result = periodRange({ weekday: 1, start_time: '08:30', end_time: '10:10' })
    expect(result).toEqual({ start: 1, span: 2 })
  })

  it('下午时段映射正确（14:00-15:40 → 第 5-6 节）', () => {
    // 跨过上午/下午分界的时间不应被误并入上午节次
    const result = periodRange({ weekday: 3, start_time: '14:00', end_time: '15:40' })
    expect(result).toEqual({ start: 5, span: 2 })
  })

  it('四节连上的大段课程映射为跨 4 节（08:30-12:10 → 第 1-4 节）', () => {
    // 模拟参考图中的跨四节合并卡片
    const result = periodRange({ weekday: 2, start_time: '08:30', end_time: '12:10' })
    expect(result).toEqual({ start: 1, span: 4 })
  })

  it('完全落在节次表外的时间回退为最接近的单节（19:00-20:40）', () => {
    // 晚间课：与 8 节次表无重叠，取开始时间最接近的第 8 节，保证卡片可见
    const result = periodRange({ weekday: 5, start_time: '19:00', end_time: '20:40' })
    expect(result).toEqual({ start: 8, span: 1 })
  })
})

describe('buildTimetableCards 网格布局计算', () => {
  it('同一课程多条时间段各自生成卡片并共用配色', () => {
    // 周一 1-2 节与周三 3-4 节各一张卡片，colorIndex 相同
    const cards = buildTimetableCards([
      makeCourse(1, [
        { weekday: 1, start_time: '08:30', end_time: '10:10', start_week: 1, end_week: 16 },
        { weekday: 3, start_time: '10:30', end_time: '12:10' },
      ]),
    ])
    expect(cards).toHaveLength(2)
    expect(cards[0]?.weekday).toBe(1)
    expect(cards[0]?.startPeriod).toBe(1)
    expect(cards[0]?.week).toBe('第1-16周')
    expect(cards[1]?.startPeriod).toBe(3)
    expect(cards.every((card) => card.colorIndex === 1 % 5)).toBe(true)
  })

  it('节次被其他课程占用时不再重复放置，避免卡片重叠', () => {
    // 课程 2 与课程 1 在周一第 1-2 节完全冲突，课程 2 的该时间段应被丢弃
    const cards = buildTimetableCards([
      makeCourse(1, [{ weekday: 1, start_time: '08:30', end_time: '10:10' }]),
      makeCourse(2, [{ weekday: 1, start_time: '08:30', end_time: '10:10' }]),
    ])
    expect(cards).toHaveLength(1)
    expect(cards[0]?.courseId).toBe(1)
  })

  it('部分冲突时截断到空闲节次', () => {
    // 课程 2 从第 2 节开始与课程 1 冲突：第 2 节被占，卡片截断丢弃（起始节次被占即整段跳过）
    const cards = buildTimetableCards([
      makeCourse(1, [{ weekday: 2, start_time: '10:30', end_time: '12:10' }]),
      makeCourse(3, [{ weekday: 2, start_time: '08:30', end_time: '12:10' }]),
    ])
    // 课程 1 先放置占第 3-4 节；课程 3 请求第 1-4 节，第 3 节冲突后截断为第 1-2 节
    expect(cards).toHaveLength(2)
    expect(cards[1]?.startPeriod).toBe(1)
    expect(cards[1]?.span).toBe(2)
  })

  it('卡片携带课程原始数据供点击详情使用', () => {
    // course 字段直接引用原对象，弹窗展示所需字段均可取到
    const source = makeCourse(7, [{ weekday: 4, start_time: '14:00', end_time: '15:40' }])
    const [card] = buildTimetableCards([source])
    expect(card?.course.id).toBe(7)
    expect(card?.name).toBe('课程7')
    expect(card?.assessment).toBe('百分制')
  })
})

describe('teachingWeekOf 教学周推算', () => {
  it('学期起始日当天为第 1 周（2026-03-01 → 2026 春季第 1 周）', () => {
    // 起点当天即第 1 周第 1 天
    const result = teachingWeekOf(new Date(2026, 2, 1))
    expect(result).toEqual({ semester: 'spring', year: 2026, week: 1 })
  })

  it('起始日满 7 天后进入第 2 周（2026-03-08）', () => {
    // 第 8 天（含）起进入下一周
    const result = teachingWeekOf(new Date(2026, 2, 8))
    expect(result).toEqual({ semester: 'spring', year: 2026, week: 2 })
  })

  it('秋季学期按 08.31 起点推算（2025-09-05 → 秋季第 1 周）', () => {
    // 8.31 至 9.5 不足 7 天，仍属第 1 周
    const result = teachingWeekOf(new Date(2025, 8, 5))
    expect(result).toEqual({ semester: 'autumn', year: 2025, week: 1 })
  })

  it('寒假日期归属上一年秋季学期（2026-01-15 → 2025 秋季第 20 周）', () => {
    // 1-2 月取不到当年学期起点，回溯到 2025-08-31：137 天 → 第 20 周
    const result = teachingWeekOf(new Date(2026, 0, 15))
    expect(result).toEqual({ semester: 'autumn', year: 2025, week: 20 })
  })

  it('暑假日期归属当年春季学期（2026-07-01 → 2026 春季第 18 周）', () => {
    // 7 月在 08.31 之前，最近起点为 2026-03-01：122 天 → 第 18 周
    const result = teachingWeekOf(new Date(2026, 6, 1))
    expect(result).toEqual({ semester: 'spring', year: 2026, week: 18 })
  })
})
