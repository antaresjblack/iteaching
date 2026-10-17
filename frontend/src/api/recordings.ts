import type { AxiosProgressEvent } from 'axios'

import { del, get, getBlob, post } from './http'

import type { RecordingStatus, UploadData, UploadPayload } from '@/types/recording'

/** POST /courses/{id}/recordings（multipart 上传，onProgress 回调上传进度 0-100） */
export function uploadRecording(
  courseId: number,
  payload: UploadPayload,
  onProgress?: (percent: number) => void,
): Promise<UploadData> {
  const form = new FormData()
  form.append('file', payload.file)
  form.append('recorded_at', payload.recorded_at)
  form.append('consent_confirmed', payload.consent_confirmed ? 'true' : 'false')
  if (payload.consent_version) {
    form.append('consent_version', payload.consent_version)
  }
  return post<UploadData>(`/courses/${courseId}/recordings`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30 * 60_000,
    onUploadProgress: (event: AxiosProgressEvent) => {
      if (event.total && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    },
  })
}

/** GET /recordings/{id}/status（轮询任务状态） */
export function getRecordingStatus(id: string): Promise<RecordingStatus> {
  return get<RecordingStatus>(`/recordings/${id}/status`)
}

/** GET /recordings/{id}/audio → Blob（需 Bearer 头，用 blob 方式获取） */
export function downloadRecordingAudio(id: string): Promise<Blob> {
  return getBlob(`/recordings/${id}/audio`)
}

/** DELETE /recordings/{id} → 204 */
export function deleteRecording(id: string): Promise<void> {
  return del(`/recordings/${id}`)
}
