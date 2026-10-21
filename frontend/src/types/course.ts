/** 后端 CourseRead */
export interface CourseRead {
  id: number
  name: string
  supervisor_id: number
  teacher_id: number
  created_at: string
}

/** POST /courses 请求体 */
export interface CourseCreate {
  name: string
  teacher_id: number
  supervisor_id?: number | null
}
