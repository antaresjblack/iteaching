/** 角色判断与展示工具：权限逻辑集中在此，模板中不做散落判断 */
import type { UserRead } from '@/types/auth'

export const ROLE_LABELS: Record<UserRead['role'], string> = {
  admin: '管理员',
  supervisor: '督导',
  teacher: '教师',
}

export function roleLabel(role: UserRead['role']): string {
  return ROLE_LABELS[role]
}

export function isAdmin(user: UserRead | null | undefined): boolean {
  return user?.role === 'admin'
}

/** 能否对课程的评价写评语/校准：管理员与督导均可（督导经录音与课程多对多关联） */
export function canReviewCourse(user: UserRead | null | undefined): boolean {
  return user?.role === 'admin' || user?.role === 'supervisor'
}
