import { get, post } from './http'

import type { LoginData, UserRead } from '@/types/auth'

export interface LoginBody {
  username: string
  password: string
}

/** POST /auth/login */
export function login(body: LoginBody): Promise<LoginData> {
  return post<LoginData>('/auth/login', body)
}

/** GET /auth/me */
export function fetchMe(): Promise<UserRead> {
  return get<UserRead>('/auth/me')
}

/** POST /auth/password（本人修改密码，需校验旧密码；新密码至少 12 位） */
export function changePassword(oldPassword: string, newPassword: string): Promise<null> {
  return post<null>('/auth/password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
}
