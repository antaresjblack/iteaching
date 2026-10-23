<script setup lang="ts">
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/types/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

/** 按角色跳转：admin 到用户管理，其余到课程列表 */
function homePath(role: Role): string {
  return role === 'admin' ? '/admin/users' : '/courses'
}

async function handleSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || submitting.value) return
  submitting.value = true
  try {
    const user = await auth.login({ username: form.username.trim(), password: form.password })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : homePath(user.role)
    await router.replace(redirect)
  } catch (err: unknown) {
    // 登录失败提示：认证接口的 401 不会被 http 拦截器统一弹，由这里手动提示
    const msg = err instanceof Error ? err.message : '登录失败，请稍后重试'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <span class="brand-mark">教</span>
        <h1 class="brand-title">AI 教学督导系统</h1>
        <p class="brand-sub">课堂录音 · 转写分析 · 督导评价</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="handleSubmit">
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            :prefix-icon="User"
            placeholder="请输入用户名"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            :prefix-icon="Lock"
            placeholder="请输入密码"
            show-password
            autocomplete="current-password"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-button
          type="primary"
          native-type="submit"
          class="login-button"
          :loading="submitting"
          @click="handleSubmit"
        >
          登录
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  padding: 36px 32px 28px;
}

.login-brand {
  text-align: center;
  margin-bottom: 28px;
}

.brand-mark {
  width: 44px;
  height: 44px;
  margin: 0 auto 12px;
  border-radius: var(--radius);
  background: var(--brand);
  color: #fff;
  font-size: 22px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.brand-sub {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.login-button {
  width: 100%;
  margin-top: 4px;
}
</style>
