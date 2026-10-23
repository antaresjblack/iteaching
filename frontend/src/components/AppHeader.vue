<script setup lang="ts">
import { Key, SwitchButton } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { changePassword } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { isAdmin, roleLabel } from '@/utils/roles'

const auth = useAuthStore()
const router = useRouter()

const isSupervisor = computed(() => auth.user?.role === 'supervisor')

const navItems = computed(() => [
  { label: '课程', path: '/courses' },
  ...(isSupervisor.value ? [{ label: '我查过的课', path: '/supervisions' }] : []),
  ...(isAdmin(auth.user) ? [{ label: '用户管理', path: '/admin/users' }] : []),
])

// ---- 修改密码 ----
const passwordVisible = ref(false)
const passwordSubmitting = ref(false)
const passwordFormRef = ref<FormInstance>()
const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const passwordRules: FormRules = {
  oldPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 12, message: '新密码至少 12 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== passwordForm.newPassword) {
          callback(new Error('两次输入的新密码不一致'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}

function openPasswordDialog(): void {
  passwordForm.oldPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
  passwordVisible.value = true
}

function resetPasswordForm(): void {
  passwordFormRef.value?.clearValidate()
}

async function submitPassword(): Promise<void> {
  const valid = await passwordFormRef.value?.validate().catch(() => false)
  if (!valid) return
  passwordSubmitting.value = true
  try {
    await changePassword(passwordForm.oldPassword, passwordForm.newPassword)
    ElMessage.success('密码已修改，请使用新密码重新登录')
    passwordVisible.value = false
    auth.logout()
    await router.push('/login')
  } catch {
    // 错误已由 http 层统一提示
  } finally {
    passwordSubmitting.value = false
  }
}

async function handleLogout(): Promise<void> {
  await ElMessageBox.confirm('确定退出登录吗？', '退出登录', {
    confirmButtonText: '退出',
    cancelButtonText: '取消',
    type: 'warning',
  })
  auth.logout()
  await router.push('/login')
}
</script>

<template>
  <header class="app-header">
    <div class="header-inner">
      <div class="brand">
        <span class="brand-mark">教</span>
        <span class="brand-name">AI 教学督导系统</span>
      </div>

      <nav v-if="auth.isAuthenticated" class="nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-link"
          active-class="nav-link--active"
          :aria-label="item.label"
        >
          {{ item.label }}
        </RouterLink>
      </nav>

      <div v-if="auth.isAuthenticated" class="user-area">
        <span class="username">{{ auth.user?.username }}</span>
        <span class="role-tag">{{ roleLabel(auth.user!.role) }}</span>
        <el-button
          text
          :icon="Key"
          aria-label="修改密码"
          title="修改密码"
          @click="openPasswordDialog"
        />
        <el-button
          text
          :icon="SwitchButton"
          aria-label="退出登录"
          title="退出登录"
          @click="handleLogout"
        />
      </div>
    </div>

    <el-dialog
      v-model="passwordVisible"
      title="修改密码"
      width="440px"
      :close-on-click-modal="false"
      @closed="resetPasswordForm"
    >
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-position="top"
      >
        <el-form-item label="当前密码" prop="oldPassword">
          <el-input v-model="passwordForm.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="passwordForm.newPassword"
            type="password"
            show-password
            placeholder="至少 12 位"
          />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input v-model="passwordForm.confirmPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordVisible = false">取消</el-button>
        <el-button type="primary" :loading="passwordSubmitting" @click="submitPassword">
          确认修改
        </el-button>
      </template>
    </el-dialog>
  </header>
</template>

<style scoped>
.app-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 20;
}

.header-inner {
  max-width: 1160px;
  margin: 0 auto;
  padding: 0 16px;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.brand-mark {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  background: var(--brand);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.brand-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.nav {
  display: flex;
  gap: 4px;
  flex: 1;
}

.nav-link {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 14px;
  transition:
    color 0.15s,
    background-color 0.15s;
}

.nav-link:hover {
  color: var(--brand);
  background: var(--brand-soft);
}

.nav-link--active {
  color: var(--brand);
  background: var(--brand-soft);
  font-weight: 600;
}

.user-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.username {
  font-size: 13px;
  color: var(--text-primary);
}

.role-tag {
  font-size: 12px;
  color: var(--brand);
  background: var(--brand-soft);
  border-radius: var(--radius-sm);
  padding: 1px 8px;
}

@media (max-width: 640px) {
  .brand-name {
    display: none;
  }

  .header-inner {
    gap: 12px;
  }
}
</style>
