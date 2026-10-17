<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createCourse, listCourses } from '@/api/courses'
import { useAuthStore } from '@/stores/auth'
import type { CourseRead } from '@/types/course'
import { isAdmin } from '@/utils/roles'

const auth = useAuthStore()
const router = useRouter()

const loading = ref(false)
const error = ref<Error | null>(null)
const courses = ref<CourseRead[]>([])

const dialogVisible = ref(false)
const dialogSubmitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  teacherId: null as number | null,
  supervisorId: null as number | null,
})

const canCreate = computed(() => auth.user?.role === 'supervisor' || auth.user?.role === 'admin')

const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: '请输入课程名称', trigger: 'blur' }],
  teacherId: [{ required: true, message: '请输入教师账号 ID', trigger: 'blur' }],
  supervisorId: isAdmin(auth.user)
    ? [{ required: true, message: '请输入督导账号 ID', trigger: 'blur' }]
    : [],
}))

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    courses.value = await listCourses()
  } catch (err) {
    courses.value = []
    error.value = err instanceof Error ? err : new Error(String(err))
  } finally {
    loading.value = false
  }
}

function openDialog(): void {
  form.name = ''
  form.teacherId = null
  form.supervisorId = null
  dialogVisible.value = true
}

async function handleCreate(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || dialogSubmitting.value) return
  dialogSubmitting.value = true
  try {
    const course = await createCourse({
      name: form.name.trim(),
      teacher_id: form.teacherId as number,
      supervisor_id: isAdmin(auth.user) ? (form.supervisorId as number) : null,
    })
    ElMessage.success('课程已创建')
    dialogVisible.value = false
    courses.value = [course, ...courses.value]
  } catch {
    // 错误已由 http 层统一提示
  } finally {
    dialogSubmitting.value = false
  }
}

function goDetail(row: CourseRead): void {
  void router.push({ name: 'course-detail', params: { id: row.id } })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">我的课程</h2>
        <p class="page-subtitle">查看负责课程的课堂录音与评价</p>
      </div>
      <el-button v-if="canCreate" type="primary" :icon="Plus" @click="openDialog">新建课程</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />

    <div v-else-if="error" class="state-panel">
      <el-empty :description="error.message || '课程列表加载失败'">
        <el-button type="primary" @click="load">重试</el-button>
      </el-empty>
    </div>

    <el-empty v-else-if="courses.length === 0" description="暂无课程">
      <el-button v-if="canCreate" type="primary" :icon="Plus" @click="openDialog">新建课程</el-button>
      <span v-else class="text-secondary">请联系管理员或督导为你分配课程</span>
    </el-empty>

    <el-table v-else :data="courses" class="course-table" @row-click="goDetail">
      <el-table-column prop="name" label="课程名称" min-width="200">
        <template #default="{ row }">
          <span class="course-name">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="teacher_id" label="教师账号 ID" width="130">
        <template #default="{ row }">
          <span class="tabular">{{ row.teacher_id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="supervisor_id" label="督导账号 ID" width="130">
        <template #default="{ row }">
          <span class="tabular">{{ row.supervisor_id }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">
          <span class="tabular text-secondary">{{ row.created_at.slice(0, 10) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建课程" width="440px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="课程名称" prop="name">
          <el-input v-model="form.name" maxlength="200" placeholder="如：高等数学（周三 3-4 节）" />
        </el-form-item>
        <el-form-item label="任课教师账号 ID" prop="teacherId">
          <el-input-number v-model="form.teacherId" :min="1" :controls="false" style="width: 100%" placeholder="输入教师账号 ID" />
        </el-form-item>
        <el-form-item v-if="isAdmin(auth.user)" label="督导账号 ID" prop="supervisorId">
          <el-input-number v-model="form.supervisorId" :min="1" :controls="false" style="width: 100%" placeholder="输入督导账号 ID" />
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

.course-table {
  background: var(--surface);
  border-radius: var(--radius);
  cursor: pointer;
}

.course-name {
  color: var(--brand);
  font-weight: 500;
}
</style>
