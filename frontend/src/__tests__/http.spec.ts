/** 测试 http 拦截器：解包 code/message/data、401 自动退出、错误处理、Bearer 附加 */
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

import * as httpModule from '@/api/http'

const { apiClient, setRedirectHandler } = httpModule

/** 模拟真实 axios 行为：非 2xx 状态抛出 AxiosError（携带 response） */
function mockAdapter(status: number, body: unknown): AxiosAdapter {
  return async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    const response: AxiosResponse = {
      data: body,
      status,
      statusText: String(status),
      headers: {},
      config,
    }
    if (status >= 200 && status < 300) return response
    throw new AxiosError(`Request failed with status code ${status}`, String(status), config, undefined, response)
  }
}

describe('HTTP 拦截器', () => {
  const redirectSpy = vi.fn()

  beforeEach(() => {
    localStorage.clear()
    setRedirectHandler(redirectSpy)
  })

  afterEach(() => {
    apiClient.defaults.adapter = undefined
    setRedirectHandler(() => {
      window.location.href = '/login'
    })
    redirectSpy.mockClear()
  })

  it('code=0 时解包返回 data', async () => {
    apiClient.defaults.adapter = mockAdapter(200, { code: 0, message: 'success', data: { id: 7 } })
    const data = await apiClient.get('/anything')
    expect(data).toEqual({ id: 7 })
  })

  it('DELETE 204 响应原样返回（无响应体）', async () => {
    apiClient.defaults.adapter = mockAdapter(204, '')
    const response = await apiClient.delete('/anything')
    expect(response.status).toBe(204)
  })

  it('code≠0 时按失败处理', async () => {
    apiClient.defaults.adapter = mockAdapter(200, { code: 1001, message: 'business failed', data: null })
    await expect(apiClient.get('/anything')).rejects.toMatchObject({ message: 'business failed' })
  })

  it('401 时清除登录凭证并触发跳转登录页', async () => {
    localStorage.setItem('iteaching_token', 'token-1')
    localStorage.setItem('iteaching_user', JSON.stringify({ id: 1 }))
    apiClient.defaults.adapter = mockAdapter(401, {
      code: 40100,
      message: 'Invalid or missing access token',
      data: null,
    })

    await expect(apiClient.get('/anything')).rejects.toMatchObject({ status: 401 })
    expect(localStorage.getItem('iteaching_token')).toBeNull()
    expect(localStorage.getItem('iteaching_user')).toBeNull()
    expect(redirectSpy).toHaveBeenCalled()
  })

  it('403 时错误信息携带后端说明', async () => {
    apiClient.defaults.adapter = mockAdapter(403, { code: 40300, message: 'Course access denied', data: null })
    await expect(apiClient.get('/anything')).rejects.toMatchObject({ status: 403, message: 'Course access denied' })
  })

  it('请求自动附加 Bearer token', async () => {
    localStorage.setItem('iteaching_token', 'token-bearer')
    let capturedAuthorization: unknown
    apiClient.defaults.adapter = async (config) => {
      capturedAuthorization = config.headers.get('Authorization')
      return { data: { code: 0, message: 'success', data: null }, status: 200, statusText: 'OK', headers: {}, config }
    }
    await apiClient.get('/anything')
    expect(capturedAuthorization).toBe('Bearer token-bearer')
  })
})
