/** 后端统一响应包装：code=0 成功，失败时 HTTP 状态码为 4xx/5xx 且 data 为 null */
export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
}

/** HTTP 层错误：携带后端业务码与状态码，供视图按状态分支处理 */
export class ApiError extends Error {
  code?: number
  status?: number

  constructor(message: string, options?: { code?: number; status?: number }) {
    super(message)
    this.name = 'ApiError'
    this.code = options?.code
    this.status = options?.status
  }
}
