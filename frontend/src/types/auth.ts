/** 与后端 app/schemas/business.py 对齐的角色枚举 */
export type Role = 'admin' | 'supervisor' | 'teacher'

/** 后端 UserRead */
export interface UserRead {
  id: number
  username: string
  role: Role
  is_active: boolean
}

/** POST /auth/login 成功后 data 字段 */
export interface LoginData {
  access_token: string
  token_type: 'bearer'
  user: UserRead
}
