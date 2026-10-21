/** 本地上传记录：上传成功后登记，页面刷新后仍可跟踪任务状态 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import type { LocalUploadRecord } from '@/types/recording'

const STORAGE_KEY = 'iteaching_uploads'

function loadAll(): LocalUploadRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? (JSON.parse(raw) as LocalUploadRecord[]) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export const useRecordingsStore = defineStore('recordings', () => {
  const records = ref<LocalUploadRecord[]>(loadAll())

  function persist(): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records.value))
  }

  function add(record: LocalUploadRecord): void {
    records.value.unshift(record)
    persist()
  }

  function updateStatus(recordingId: string, patch: Partial<Pick<LocalUploadRecord, 'status' | 'error'>>): void {
    const record = records.value.find((item) => item.recording_id === recordingId)
    if (record) {
      Object.assign(record, patch)
      persist()
    }
  }

  function remove(recordingId: string): void {
    records.value = records.value.filter((item) => item.recording_id !== recordingId)
    persist()
  }

  function byCourse(courseId: number): LocalUploadRecord[] {
    return records.value.filter((item) => item.course_id === courseId)
  }

  /** 返回某课程下仍未结束（可继续轮询）的记录 */
  function pendingOf(courseId: number): LocalUploadRecord[] {
    return records.value.filter(
      (item) => item.course_id === courseId && item.status !== 'SUCCEEDED' && item.status !== 'FAILED',
    )
  }

  return { records, add, updateStatus, remove, byCourse, pendingOf }
})
