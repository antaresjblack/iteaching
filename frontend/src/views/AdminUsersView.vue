<script setup lang="ts">
import { Key, Plus } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { createUser, listUsers, resetUserPassword } from '@/api/users'
import type { UserCreateBody } from '@/api/users'
import type { Department, Role, SupervisorLevel, UserRead } from '@/types/auth'
import { DEPARTMENTS } from '@/types/auth'
import { ApiError } from '@/types/api'
import { ROLE_LABELS } from '@/utils/roles'

const loading = ref(false)
const error = ref<Error | null>(null)
const users = ref<UserRead[]>([])

const dialogVisible = ref(false)
const dialogSubmitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  username: '',
  password: '',
  role: 'teacher' as Role,
  // 角色专属字段：教师/督导填写，管理员不填
  name: '',
  department: '' as Department | '',
  phone: '',
  level: '' as SupervisorLevel | '',
})

/** 基础校验规则；角色专属字段的必填规则由 computed 动态追加 */
const baseRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_.-]{3,80}$/, message: '3-80 位，仅限字母、数字、_ . -', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 12, max: 128, message: '密码至少 12 位', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const rules = computed<FormRules>(() => {
  if (form.role === 'admin') {
    return baseRules
  }
  return {
    ...baseRules,
    name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
    department: [{ required: true, message: '请选择院系', trigger: 'change' }],
    // 级别仅督导需要
    ...(form.role === 'supervisor'
      ? { level: [{ required: true, message: '请选择级别', trigger: 'change' }] }
      : {}),
  }
})

/** 切换角色时清理已隐藏字段的校验状态与取值 */
function handleRoleChange(): void {
  if (form.role === 'admin') {
    form.name = ''
    form.department = ''
    form.phone = ''
    form.level = ''
  } else if (form.role === 'teacher') {
    form.level = ''
  }
  formRef.value?.clearValidate(['name', 'department', 'phone', 'level'])
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    users.value = await listUsers()
  } catch (err) {
    users.value = []
    error.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    loading.value = false
  }
}

function openDialog(): void {
  form.username = ''
  form.password = ''
  form.role = 'teacher'
  form.name = ''
  form.department = ''
  form.phone = ''
  form.level = ''
  formRef.value?.clearValidate()
  dialogVisible.value = true
}

async function handleCreate(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || dialogSubmitting.value) return
  dialogSubmitting.value = true
  try {
    const payload: UserCreateBody = {
      username: form.username.trim(),
      password: form.password,
      role: form.role,
    }
    // 管理员只有基础字段；教师/督导补齐专属字段
    if (form.role !== 'admin') {
      payload.name = form.name.trim()
      payload.department = form.department as Department
      payload.phone = form.phone.trim() || undefined
    }
    if (form.role === 'supervisor') {
      payload.level = form.level as SupervisorLevel
    }
    const user = await createUser(payload)
    ElMessage.success('用户已创建')
    dialogVisible.value = false
    users.value = [user, ...users.value]
  } catch (err) {
    // 409 用户名已存在：定位到用户名字段
    if (err instanceof ApiError && err.status === 409) {
      formRef.value?.validateField('username')
      ElMessage.error('用户名已存在')
    }
  } finally {
    dialogSubmitting.value = false
  }
}

onMounted(load)

// ---- 管理员强制重置密码 ----
const resetVisible = ref(false)
const resetSubmitting = ref(false)
const resetTarget = ref<UserRead | null>(null)
const resetFormRef = ref<FormInstance>()

const resetRules: FormRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 12, max: 128, message: '密码至少 12 位', trigger: 'blur' },
  ],
}

const resetForm = reactive({ newPassword: '' })

function openReset(row: UserRead): void {
  resetTarget.value = row
  resetForm.newPassword = ''
  resetFormRef.value?.clearValidate()
  resetVisible.value = true
}

async function handleReset(): Promise<void> {
  const valid = await resetFormRef.value?.validate().catch(() => false)
  if (!valid || !resetTarget.value || resetSubmitting.value) return
  resetSubmitting.value = true
  try {
    await resetUserPassword(resetTarget.value.id, resetTarget.value.role, resetForm.newPassword)
    ElMessage.success(`已重置「${resetTarget.value.username}」的密码`)
    resetVisible.value = false
  } catch {
    // 错误已由 http 层统一提示
  } finally {
    resetSubmitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">用户管理</h2>
        <p class="page-subtitle">创建督导、教师账号并查看账号状态</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openDialog">新建用户</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />

    <div v-else-if="error" class="state-panel">
      <el-empty :description="error.message || '用户列表加载失败'">
        <el-button type="primary" @click="load">重试</el-button>
      </el-empty>
    </div>

    <el-empty v-else-if="users.length === 0" description="暂无用户" />

    <el-table v-else :data="users" class="users-table">
      <el-table-column prop="id" label="ID" width="90">
        <template #default="{ row }">
          <span class="tabular">{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="用户名" min-width="160" />
      <el-table-column label="姓名" width="120">
        <template #default="{ row }">{{ row.name || '-' }}</template>
      </el-table-column>
      <el-table-column label="工号" width="150">
        <template #default="{ row }">
          <span class="tabular">{{ row.employee_no || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="院系" min-width="150">
        <template #default="{ row }">{{ row.department || '-' }}</template>
      </el-table-column>
      <el-table-column label="级别" width="100">
        <template #default="{ row }">{{ row.level || '-' }}</template>
      </el-table-column>
      <el-table-column label="角色" width="120">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'supervisor' ? 'warning' : 'info'" size="small">
            {{ ROLE_LABELS[row.role as Role] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.role !== 'admin'"
            text
            type="primary"
            :icon="Key"
            aria-label="重置密码"
            title="重置密码"
            @click="openReset(row)"
          >
            重置密码
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="resetVisible"
      title="重置密码"
      width="420px"
      :close-on-click-modal="false"
    >
      <p class="reset-tip">
        即将重置「{{ resetTarget?.username }}」（{{ resetTarget ? ROLE_LABELS[resetTarget.role] : '' }}）
        的登录密码，重置后请通知本人使用新密码登录。
      </p>
      <el-form ref="resetFormRef" :model="resetForm" :rules="resetRules" label-position="top">
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="resetForm.newPassword"
            type="password"
            show-password
            maxlength="128"
            placeholder="至少 12 位"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetSubmitting" @click="handleReset">
          确认重置
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialogVisible" title="新建用户" width="480px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" maxlength="80" placeholder="3-80 位字母、数字、_ . -" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password maxlength="128" placeholder="至少 12 位" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%" @change="handleRoleChange">
            <el-option label="教师" value="teacher" />
            <el-option label="督导" value="supervisor" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <!-- 教师/督导专属字段；管理员只有基础账号字段 -->
        <template v-if="form.role !== 'admin'">
          <p style="margin: -4px 0 12px; font-size: 12px; color: var(--el-text-color-secondary)">
            工号由系统自动生成（督导 1xxxx、教师 2xxxx），无需填写
          </p>
          <el-form-item label="姓名" prop="name">
            <el-input v-model="form.name" maxlength="80" placeholder="请输入姓名" />
          </el-form-item>
          <el-form-item label="院系" prop="department">
            <el-select v-model="form.department" placeholder="请选择院系" style="width: 100%">
              <el-option v-for="item in DEPARTMENTS" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="电话" prop="phone">
            <el-input v-model="form.phone" maxlength="40" placeholder="选填" />
          </el-form-item>
          <el-form-item v-if="form.role === 'supervisor'" label="级别" prop="level">
            <el-select v-model="form.level" placeholder="请选择级别" style="width: 100%">
              <el-option label="校级" value="校级" />
              <el-option label="院级" value="院级" />
            </el-select>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button :disabled="dialogSubmitting" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="dialogSubmitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.state-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.users-table {
  background: var(--surface);
  border-radius: var(--radius);
}

.reset-tip {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
}
</style>
