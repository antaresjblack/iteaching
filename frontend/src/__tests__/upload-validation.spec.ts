/** 上传表单前端校验：文件必填/后缀白名单/体积上限、录制时间必填、隐私授权必须勾选 */
import { describe, expect, it } from 'vitest'

import { MAX_UPLOAD_SIZE_MB, validateUpload } from '@/utils/validateUpload'

function fakeFile(name: string, size: number): File {
  const file = new File([], name, { type: 'audio/wav' })
  // 测试中不实际分配大文件，直接覆写 size 属性
  Object.defineProperty(file, 'size', { value: size })
  return file
}

describe('上传表单校验', () => {
  const base = {
    file: fakeFile('lesson.wav', 1024),
    recordedAt: '2026-10-17T09:00:00',
    consentConfirmed: true,
  }

  it('完整表单校验通过', () => {
    expect(validateUpload(base).valid).toBe(true)
  })

  it('缺少文件', () => {
    const result = validateUpload({ ...base, file: null })
    expect(result.valid).toBe(false)
    expect(result.errors.file).toContain('录音文件')
  })

  it('拒绝不支持的后缀', () => {
    const result = validateUpload({ ...base, file: fakeFile('lesson.mp4', 1024) })
    expect(result.valid).toBe(false)
    expect(result.errors.file).toContain('WAV、MP3、M4A')
  })

  it('拒绝超过 500MB 的文件', () => {
    const result = validateUpload({
      ...base,
      file: fakeFile('big.wav', MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1),
    })
    expect(result.valid).toBe(false)
    expect(result.errors.file).toContain(`${MAX_UPLOAD_SIZE_MB}MB`)
  })

  it('缺少录制时间', () => {
    const result = validateUpload({ ...base, recordedAt: '' })
    expect(result.valid).toBe(false)
    expect(result.errors.recordedAt).toContain('录制时间')
  })

  it('未确认隐私授权', () => {
    const result = validateUpload({ ...base, consentConfirmed: false })
    expect(result.valid).toBe(false)
    expect(result.errors.consent).toContain('隐私授权')
  })
})
