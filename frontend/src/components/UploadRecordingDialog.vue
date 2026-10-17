<script setup lang="ts">
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules, type UploadFile, type UploadInstance, type UploadRawFile, type UploadUserFile } from 'element-plus'
import { computed, reactive, ref } from 'vue'

import { uploadRecording } from '@/api/recordings'
import type { UploadData } from '@/types/recording'
import { localDateTimeToIso } from '@/utils/format'
import { validateUpload } from '@/utils/validateUpload'

const props = defineProps<{
  courseId: number
}>()

const emit = defineEmits<{
  uploaded: [data: UploadData, filename: string, recordedAt: string]
}>()

const visible = defineModel<boolean>('visible', { default: false })

const formRef = ref<FormInstance>()
const uploadRef = ref<UploadInstance>()
const fileList = ref<UploadUserFile[]>([])
const submitting = ref(false)
const progress = ref(0)

const form = reactive({
  recordedAt: '',
  consentConfirmed: false,
})

const selectedFile = computed<File | null>(() => fileList.value[0]?.raw ?? null)

const rules: FormRules = {
  recordedAt: [{ required: true, message: '请选择录制时间', trigger: 'change' }],
  consentConfirmed: [
    {
      validator: (_rule, value: boolean, callback) => {
        if (!value) callback(new Error('必须确认已获得隐私授权'))
        else callback()
      },
      trigger: 'change',
    },
  ],
}

/** el-upload 选择文件后的前端校验（类型/大小），后端校验为最终依据 */
function handleFileChange(file: UploadFile): void {
  const raw = file.raw
  if (!raw) return
  const result = validateUpload({
    file: raw,
    recordedAt: form.recordedAt || 'placeholder',
    consentConfirmed: true,
  })
  if (result.errors.file) {
    fileList.value = []
    uploadRef.value?.clearFiles()
    ElMessage.error(result.errors.file)
  }
}

function handleFileExceed(files: File[]): void {
  // 单文件：用新文件替换旧文件
  const file = files[0]
  if (!file) return
  const raw = Object.assign(file, { uid: Date.now() }) as UploadRawFile
  fileList.value = [
    {
      name: file.name,
      percentage: 0,
      status: 'ready',
      size: file.size,
      raw,
      uid: raw.uid,
    },
  ]
}

function reset(): void {
  form.recordedAt = ''
  form.consentConfirmed = false
  fileList.value = []
  progress.value = 0
  formRef.value?.clearValidate()
}

async function handleSubmit(): Promise<void> {
  if (submitting.value) return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const file = selectedFile.value
  if (!file) {
    ElMessage.error('请选择录音文件')
    return
  }
  // 最终完整校验（文件 + 时间 + 授权）
  const check = validateUpload({
    file,
    recordedAt: form.recordedAt,
    consentConfirmed: form.consentConfirmed,
  })
  if (!check.valid) {
    ElMessage.error(Object.values(check.errors)[0] ?? '表单校验未通过')
    return
  }

  submitting.value = true
  progress.value = 0
  try {
    const data = await uploadRecording(
      props.courseId,
      {
        file,
        recorded_at: localDateTimeToIso(form.recordedAt),
        consent_confirmed: form.consentConfirmed,
      },
      (percent) => {
        progress.value = percent
      },
    )
    ElMessage.success('上传成功，已进入处理队列')
    emit('uploaded', data, file.name, form.recordedAt)
    visible.value = false
    reset()
  } catch {
    // 错误已由 http 层统一提示（413/415/422 等）
  } finally {
    submitting.value = false
  }
}

function handleClosed(): void {
  if (!submitting.value) reset()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="上传课堂录音"
    width="520px"
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="录音文件" required>
        <el-upload
          ref="uploadRef"
          v-model:file-list="fileList"
          drag
          action="#"
          :auto-upload="false"
          :limit="1"
          accept=".wav,.mp3,.m4a"
          :on-change="handleFileChange"
          :on-exceed="handleFileExceed"
          class="upload-area"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽文件到此处，或<em>点击选择</em></div>
          <template #tip>
            <div class="el-upload__tip">仅支持 WAV、MP3、M4A，不超过 500MB</div>
          </template>
        </el-upload>
      </el-form-item>

      <el-form-item label="录制时间" prop="recordedAt">
        <el-date-picker
          v-model="form.recordedAt"
          type="datetime"
          placeholder="选择课堂录制时间"
          value-format="YYYY-MM-DDTHH:mm:ss"
          format="YYYY-MM-DD HH:mm"
          style="width: 100%"
          :disabled-date="(date: Date) => date.getTime() > Date.now()"
        />
      </el-form-item>

      <el-form-item prop="consentConfirmed">
        <el-checkbox v-model="form.consentConfirmed">
          我确认本次录音已获得相关人员的隐私授权
        </el-checkbox>
      </el-form-item>

      <el-progress
        v-if="submitting"
        :percentage="progress"
        :stroke-width="8"
        class="upload-progress"
        :format="(p: number) => (p < 100 ? '上传中 ' + p + '%' : '服务器校验中…')"
      />
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!selectedFile" @click="handleSubmit">
        上传
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.upload-area :deep(.el-upload-dragger) {
  border-color: var(--border-strong);
  border-radius: var(--radius);
  background: var(--bg-page);
  transition:
    border-color 0.15s,
    background-color 0.15s;
}

.upload-area :deep(.el-upload-dragger:hover) {
  border-color: var(--brand);
  background: var(--brand-soft);
}

.upload-icon {
  font-size: 34px;
  color: var(--brand);
  margin-bottom: 4px;
}

.upload-progress {
  margin-top: 4px;
}
</style>
