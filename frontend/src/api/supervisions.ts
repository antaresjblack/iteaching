import { get } from './http'

import type { CourseQuery, SupervisedCourseRead } from '@/types/course'

/** GET /supervisions/my-courses（我查过的课：按课程去重，含最近关联时间；支持四条件组合筛选） */
export function listMySupervisedCourses(
  query: CourseQuery = {},
): Promise<SupervisedCourseRead[]> {
  return get<SupervisedCourseRead[]>('/supervisions/my-courses', { params: query })
}
