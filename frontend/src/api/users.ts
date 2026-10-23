import { get, post } from './http'

import type { Department, Role, SupervisorLevel, UserRead } from '@/types/auth'

/** 角色专属字段：admin 不传；teacher/supervisor 必传 name、department；督导另需 level。工号由后端自动生成 */
export interface UserCreateBody {
  username: string
  password: string
  role: Role
  name?: string
  department?: Department
  phone?: string
  level?: SupervisorLevel
}

/** GET /users（仅 admin） */
export function listUsers(): Promise<UserRead[]> {
  return get<UserRead[]>('/users')
}

/** POST /users（仅 admin），用户名冲突时后端返回 409 */
export function createUser(body: UserCreateBody): Promise<UserRead> {
  return post<UserRead>('/users', body)
}

/** 教师搜索命中字段 */
export interface TeacherCandidate {
  id: number
  name: string
  employee_no: string | null
  department: string | null
  username: string
}

/** GET /teachers（admin + supervisor 可访问），按姓名/院系/工号模糊匹配 */
export function searchTeachers(keyword: string, limit = 20): Promise<TeacherCandidate[]> {
  return get<TeacherCandidate[]>('/teachers', { params: { keyword, limit } })
}

/** POST /users/{id}/reset-password（仅 admin，按角色定位分表；新密码至少 12 位） */
export function resetUserPassword(
  userId: number,
  role: Role,
  newPassword: string,
): Promise<null> {
  return post<null>(`/users/${userId}/reset-password`, { new_password: newPassword }, {
    params: { role },
  })
}
