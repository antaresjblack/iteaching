import { get, patch, post } from './http'

import type { CourseCreate, CourseQuery, CourseRead, CourseUpdate } from '@/types/course'

/** GET /courses（按当前角色过滤，支持地点/状态/教师/时间段筛选） */
export function listCourses(query: CourseQuery = {}): Promise<CourseRead[]> {
  return get<CourseRead[]>('/courses', { params: query })
}

/** GET /courses/{id}，无权限 403 */
export function getCourse(id: number): Promise<CourseRead> {
  return get<CourseRead>(`/courses/${id}`)
}

/** POST /courses */
export function createCourse(body: CourseCreate): Promise<CourseRead> {
  return post<CourseRead>('/courses', body)
}

/** PATCH /courses/{id} */
export function updateCourse(id: number, body: CourseUpdate): Promise<CourseRead> {
  return patch<CourseRead>(`/courses/${id}`, body)
}
