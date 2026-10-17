/** 统一 HTTP 客户端：请求附加 Bearer token，响应解包 {code,message,data} 并集中处理错误 */
import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

import { ApiError, type ApiResponse } from '@/types/api'
import { clearToken } from '@/utils/token'

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('iteaching_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** 401 跳转处理器，可注入替换（如接入 Router），默认整页跳转 */
let redirectHandler: () => void = () => {
  window.location.href = '/login'
}

export function redirectToLogin(): void {
  redirectHandler()
}

export function setRedirectHandler(handler: () => void): void {
  redirectHandler = handler
}

function extractMessage(payload: unknown): string | undefined {
  if (payload && typeof payload === 'object' && 'message' in payload) {
    const message = (payload as { message?: unknown }).message
    if (typeof message === 'string' && message) return message
  }
  return undefined
}

apiClient.interceptors.response.use(
  (response) => {
    // 文件下载直接返回 Blob；204 无响应体
    if (response.config.responseType === 'blob' || response.status === 204) {
      return response
    }
    const body = response.data as ApiResponse<unknown> | undefined
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) {
        // 解包：调用方直接拿到 data（拦截器返回值经类型断言保持 axios 链兼容）
        return body.data as unknown as typeof response
      }
      return Promise.reject(new ApiError(body.message || '请求失败', { code: body.code }))
    }
    return response
  },
  (error: AxiosError) => {
    const status = error.response?.status
    const payload = error.response?.data
    const backendMessage = extractMessage(payload)

    if (status === 401) {
      clearToken()
      localStorage.removeItem('iteaching_user')
      ElMessage.error('登录已过期，请重新登录')
      redirectToLogin()
    } else if (status === 403) {
      ElMessage.error(backendMessage ? `没有权限执行此操作（${backendMessage}）` : '没有权限执行此操作')
    } else if (status && status !== 404) {
      // 404 由视图按场景展示（如"评价尚未完成"），不做全局提示
      ElMessage.error(backendMessage || '网络请求失败，请稍后重试')
    }

    if (error.code === 'ECONNABORTED' || !error.response) {
      return Promise.reject(new ApiError('网络连接失败，请检查后端服务是否已启动', { status }))
    }
    return Promise.reject(new ApiError(backendMessage || '请求失败', { code: (payload as ApiResponse<unknown>)?.code, status }))
  },
)

/** 类型化 GET：直接返回解包后的 data */
export function get<T>(url: string, config?: object): Promise<T> {
  return apiClient.get(url, config) as unknown as Promise<T>
}

export function post<T>(url: string, data?: unknown, config?: object): Promise<T> {
  return apiClient.post(url, data, config) as unknown as Promise<T>
}

export function del<T = void>(url: string): Promise<T> {
  return apiClient.delete(url) as unknown as Promise<T>
}

export function getBlob(url: string): Promise<Blob> {
  return apiClient
    .get(url, { responseType: 'blob' })
    .then((response) => response.data as Blob)
}
