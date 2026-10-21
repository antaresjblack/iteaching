/** 认证状态：登录/恢复/退出，凭证经 utils/token 持久化 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { login as loginApi, type LoginBody } from '@/api/auth'
import type { UserRead } from '@/types/auth'
import {
  clearStoredUser,
  clearToken,
  getStoredUser,
  getToken,
  setStoredUser,
  setToken,
} from '@/utils/token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<UserRead | null>(null)

  const isAuthenticated = computed(() => !!token.value && !!user.value)

  /** 应用启动时从 localStorage 恢复登录状态 */
  function restore(): void {
    token.value = getToken()
    user.value = getStoredUser()
  }

  /** 登录成功后写入内存与 localStorage */
  async function login(body: LoginBody): Promise<UserRead> {
    const data = await loginApi(body)
    token.value = data.access_token
    user.value = data.user
    setToken(data.access_token)
    setStoredUser(data.user)
    return data.user
  }

  /** 退出：清空内存与 localStorage */
  function logout(): void {
    token.value = null
    user.value = null
    clearToken()
    clearStoredUser()
  }

  return { token, user, isAuthenticated, restore, login, logout }
})
