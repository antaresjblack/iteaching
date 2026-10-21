/** 上传表单前端校验（后端响应为最终依据） */

export const ALLOWED_EXTENSIONS = ['.wav', '.mp3', '.m4a'] as const
/** 与后端 MAX_UPLOAD_SIZE_MB 默认值一致 */
export const MAX_UPLOAD_SIZE_MB = 500

export interface UploadFormValues {
  file: File | null
  recordedAt: string
  consentConfirmed: boolean
}

export interface UploadFormErrors {
  file?: string
  recordedAt?: string
  consent?: string
}

/** 返回 { valid, errors }；errors 中每个字段一条中文提示 */
export function validateUpload(values: UploadFormValues): { valid: boolean; errors: UploadFormErrors } {
  const errors: UploadFormErrors = {}

  if (!values.file) {
    errors.file = '请选择录音文件'
  } else {
    const name = values.file.name.toLowerCase()
    const extension = name.slice(name.lastIndexOf('.'))
    if (!(ALLOWED_EXTENSIONS as readonly string[]).includes(extension)) {
      errors.file = '仅支持 WAV、MP3、M4A 格式'
    } else if (values.file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) {
      errors.file = `文件不能超过 ${MAX_UPLOAD_SIZE_MB}MB`
    }
  }

  if (!values.recordedAt) {
    errors.recordedAt = '请选择录制时间'
  }

  if (!values.consentConfirmed) {
    errors.consent = '必须确认已获得隐私授权'
  }

  return { valid: Object.keys(errors).length === 0, errors }
}
