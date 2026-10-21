<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { createUser, listUsers } from '@/api/users'
import type { Role, UserRead } from '@/types/auth'
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
})

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_.-]{3,80}$/, message: '3-80 位，仅限字母、数字、_ . -', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 10, max: 128, message: '密码长度需为 10-128 位', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
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
  dialogVisible.value = true
}

async function handleCreate(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || dialogSubmitting.value) return
  dialogSubmitting.value = true
  try {
    const user = await createUser({
      username: form.username.trim(),
      password: form.password,
      role: form.role,
    })
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
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建用户" width="420px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" maxlength="80" placeholder="3-80 位字母、数字、_ . -" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password maxlength="128" placeholder="至少 10 位" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="教师" value="teacher" />
            <el-option label="督导" value="supervisor" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
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
</style>
