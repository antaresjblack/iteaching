import { get, post } from './http'

import type { CourseCreate, CourseRead } from '@/types/course'

/** GET /courses（按当前角色过滤） */
export function listCourses(): Promise<CourseRead[]> {
  return get<CourseRead[]>('/courses')
}

/** GET /courses/{id}，无权限 403 */
export function getCourse(id: number): Promise<CourseRead> {
  return get<CourseRead>(`/courses/${id}`)
}

/** POST /courses */
export function createCourse(body: CourseCreate): Promise<CourseRead> {
  return post<CourseRead>('/courses', body)
}
