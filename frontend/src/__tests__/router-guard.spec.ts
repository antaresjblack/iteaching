/** 路由权限守卫：未登录跳 /login 并回传 redirect、已登录访问 /login 跳首页、adminOnly 角色限制 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { routeGuard } from '@/router'
import { useAuthStore } from '@/stores/auth'

function setUser(role: 'admin' | 'supervisor' | 'teacher' | null): void {
  const store = useAuthStore()
  store.restore()
  if (role) {
    localStorage.setItem('iteaching_token', 'token-x')
    localStorage.setItem(
      'iteaching_user',
      JSON.stringify({ id: 1, username: role, role, is_active: true }),
    )
    store.restore()
  }
}

describe('路由权限守卫', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('未登录访问需要鉴权的页面 → 重定向到 /login 并携带 redirect', () => {
    const result = routeGuard({ meta: { requiresAuth: true }, path: '/courses', query: undefined })
    expect(result).toEqual({ path: '/login', query: { redirect: '/courses' } })
  })

  it('已登录访问 /login → 重定向到 /courses', () => {
    setUser('teacher')
    const result = routeGuard({ meta: { requiresAuth: false }, path: '/login', query: undefined })
    expect(result).toEqual({ path: '/courses' })
  })

  it('教师访问 adminOnly 页面 → 重定向到 /courses', () => {
    setUser('teacher')
    const result = routeGuard({ meta: { adminOnly: true, requiresAuth: true }, path: '/admin/users', query: undefined })
    expect(result).toEqual({ path: '/courses' })
  })

  it('管理员访问 adminOnly 页面 → 放行', () => {
    setUser('admin')
    const result = routeGuard({ meta: { adminOnly: true, requiresAuth: true }, path: '/admin/users', query: undefined })
    expect(result).toBe(true)
  })

  it('已登录访问普通页面 → 放行', () => {
    setUser('supervisor')
    const result = routeGuard({ meta: { requiresAuth: true }, path: '/courses', query: undefined })
    expect(result).toBe(true)
  })
})
