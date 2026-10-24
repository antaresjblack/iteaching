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

/** 当前账号是否为某条录音/评价的上传者本人（角色与账号 id 需同时匹配） */
export function isUploader(
  user: UserRead | null | undefined,
  uploadedByRole: string,
  uploadedById: number,
): boolean {
  return !!user && user.role === uploadedByRole && user.id === uploadedById
}

/** 能否校准：管理员，或上传者本人（教师/督导均可校准自己上传的录音） */
export function canCalibrateEvaluation(
  user: UserRead | null | undefined,
  uploadedByRole: string,
  uploadedById: number,
): boolean {
  return isAdmin(user) || isUploader(user, uploadedByRole, uploadedById)
}

/** 能否写督导评语：管理员，或上传该音频的督导本人 */
export function canReviewEvaluation(
  user: UserRead | null | undefined,
  uploadedByRole: string,
  uploadedById: number,
): boolean {
  if (isAdmin(user)) return true
  return user?.role === 'supervisor' && isUploader(user, uploadedByRole, uploadedById)
}
