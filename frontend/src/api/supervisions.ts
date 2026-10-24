import { del, get, post } from './http'

import type { CourseQuery, SupervisedCourseRead } from '@/types/course'

/** GET /supervisions/my-courses（我查过的课：督导主动加入的课程，含加入时间；支持四条件组合筛选） */
export function listMySupervisedCourses(
  query: CourseQuery = {},
): Promise<SupervisedCourseRead[]> {
  return get<SupervisedCourseRead[]>('/supervisions/my-courses', { params: query })
}

/** POST /courses/{id}/join（督导主动加入课程；重复加入幂等） */
export function joinCourse(courseId: number): Promise<void> {
  return post<void>(`/courses/${courseId}/join`)
}

/** DELETE /courses/{id}/join（督导退出课程） */
export function leaveCourse(courseId: number): Promise<void> {
  return del(`/courses/${courseId}/join`)
}
