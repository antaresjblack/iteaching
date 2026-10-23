/** 与后端 app/schemas/business.py 对齐的角色枚举 */
export type Role = 'admin' | 'supervisor' | 'teacher'

/** 后端 UserRead（分表后新增角色专属字段，admin 为空） */
export interface UserRead {
  id: number
  username: string
  role: Role
  is_active: boolean
  employee_no?: string | null
  department?: string | null
  phone?: string | null
  name?: string | null
  level?: SupervisorLevel | null
  last_login_at?: string | null
}

/** 督导级别：校级 / 院级 */
export type SupervisorLevel = '校级' | '院级'

/** 院系枚举：与后端 Department 对齐，新增院系时在此追加 */
export const DEPARTMENTS = [
  '计算机学院',
  '数学学院',
  '外国语学院',
  '经济管理学院',
  '马克思主义学院',
  '体育学院',
] as const

export type Department = (typeof DEPARTMENTS)[number]

/** POST /auth/login 成功后 data 字段 */
export interface LoginData {
  access_token: string
  token_type: 'bearer'
  user: UserRead
}
