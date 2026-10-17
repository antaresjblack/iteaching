import { get, post } from './http'

import type { Role, UserRead } from '@/types/auth'

export interface UserCreateBody {
  username: string
  password: string
  role: Role
}

/** GET /users（仅 admin） */
export function listUsers(): Promise<UserRead[]> {
  return get<UserRead[]>('/users')
}

/** POST /users（仅 admin），用户名冲突时后端返回 409 */
export function createUser(body: UserCreateBody): Promise<UserRead> {
  return post<UserRead>('/users', body)
}
