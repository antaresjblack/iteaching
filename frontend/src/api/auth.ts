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
