import type { AxiosProgressEvent } from 'axios'

import { del, get, getBlob, post } from './http'

import type {
  CourseRecording,
  RecordingStatus,
  SupervisionLink,
  UploadData,
  UploadPayload,
} from '@/types/recording'

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
  if (payload.description) {
    form.append('description', payload.description)
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

/** GET /courses/{id}/recordings（课程音频列表，含上传者角色与姓名） */
export function listCourseRecordings(courseId: number): Promise<CourseRecording[]> {
  return get<CourseRecording[]>(`/courses/${courseId}/recordings`)
}

/** POST /courses/{id}/supervision-links（督导上传后关联音频；重复关联幂等） */
export function createSupervisionLink(
  courseId: number,
  recordingId: string,
): Promise<SupervisionLink> {
  return post<SupervisionLink>(`/courses/${courseId}/supervision-links`, {
    recording_id: recordingId,
  })
}

/** GET /recordings/{id}/audio → Blob（需 Bearer 头，用 blob 方式获取） */
export function downloadRecordingAudio(id: string): Promise<Blob> {
  return getBlob(`/recordings/${id}/audio`)
}

/** DELETE /recordings/{id} → 204 */
export function deleteRecording(id: string): Promise<void> {
  return del(`/recordings/${id}`)
}
