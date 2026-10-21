/** 认证 store：登录写入内存与 localStorage、restore 恢复会话、无凭证保持未登录、logout 清空 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/auth'
import type { LoginData } from '@/types/auth'

vi.mock('@/api/auth', () => ({
  login: vi.fn(async (): Promise<LoginData> => ({
    access_token: 'token-abc',
    token_type: 'bearer',
    user: { id: 2, username: 'teacher', role: 'teacher', is_active: true },
  })),
  fetchMe: vi.fn(),
}))

describe('认证状态', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('登录后写入内存与 localStorage（登录状态恢复的数据源）', async () => {
    const store = useAuthStore()
    await store.login({ username: 'teacher', password: 'password123456' })

    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.username).toBe('teacher')
    expect(localStorage.getItem('iteaching_token')).toBe('token-abc')
    expect(JSON.parse(localStorage.getItem('iteaching_user') ?? '{}').role).toBe('teacher')
  })

  it('restore 从 localStorage 恢复登录状态', () => {
    localStorage.setItem('iteaching_token', 'token-restored')
    localStorage.setItem(
      'iteaching_user',
      JSON.stringify({ id: 3, username: 'supervisor', role: 'supervisor', is_active: true }),
    )

    const store = useAuthStore()
    store.restore()

    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.role).toBe('supervisor')
  })

  it('restore 在无凭证时保持未登录', () => {
    const store = useAuthStore()
    store.restore()
    expect(store.isAuthenticated).toBe(false)
  })

  it('logout 清空内存与 localStorage', async () => {
    const store = useAuthStore()
    await store.login({ username: 'teacher', password: 'password123456' })
    store.logout()

    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
    expect(localStorage.getItem('iteaching_token')).toBeNull()
    expect(localStorage.getItem('iteaching_user')).toBeNull()
  })
})
