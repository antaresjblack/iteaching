/** 后端 ProcessingTask 状态枚举 */
export type TaskStatus = 'QUEUED' | 'PROCESSING' | 'SUCCEEDED' | 'FAILED'

/** 轮询超时是前端自定义状态，非后端状态值 */
export type DisplayStatus = TaskStatus | 'TIMEOUT'

/** POST /courses/{id}/recordings 成功后的 data 字段 */
export interface UploadData {
  recording_id: string
  task_id: string
  status: 'QUEUED'
}

/** GET /recordings/{id}/status 的 data 字段 */
export interface RecordingStatus {
  recording_id: string
  task_id: string
  status: TaskStatus
  attempts: number
  /** 仅 FAILED 时返回，已由后端脱敏 */
  error?: string | null
}

/** 上传录音表单载荷（组件内使用，提交时组装为 FormData） */
export interface UploadPayload {
  file: File
  /** ISO8601 带时区，如 2026-10-17T09:00:00+08:00 */
  recorded_at: string
  consent_confirmed: boolean
  consent_version?: string
  /** 内容说明（选填） */
  description?: string
}

/** GET /courses/{id}/recordings 列表项 */
export interface CourseRecording {
  id: string
  course_id: number
  uploaded_by_id: number
  /** 上传者角色：督导仅能看到自己上传的音频；教师可见本课程全部音频 */
  uploaded_by_role: 'admin' | 'supervisor' | 'teacher'
  uploader_name: string | null
  original_filename: string
  media_type: string
  recorded_at: string
  duration_seconds: number
  description: string | null
  created_at: string
  /** 处理任务状态：随列表一并返回，用于区分处理中/失败 */
  status: TaskStatus
  /** 仅 FAILED 时有值，已由后端脱敏 */
  error?: string | null
}

/** 本地上传记录（存 Pinia + localStorage，用于页面刷新后仍可跟踪任务） */
export interface LocalUploadRecord {
  course_id: number
  recording_id: string
  task_id: string
  filename: string
  recorded_at: string
  uploaded_at: string
  status: DisplayStatus
  /** 仅 FAILED 时存在 */
  error?: string | null
}
