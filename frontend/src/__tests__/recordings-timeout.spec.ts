import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useRecordingsStore } from '@/stores/recordings'
import type { DisplayStatus, LocalUploadRecord } from '@/types/recording'

function record(id: string, status: DisplayStatus, course = 1): LocalUploadRecord {
  return { recording_id: id, task_id: id, course_id: course, filename: 'test.wav',
    recorded_at: '', uploaded_at: '', status, error: null }
}

describe('超时后的状态刷新', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
  it('超时任务仍可查询，真正结束和其他课程的任务不查询', () => {
    const store = useRecordingsStore()
    store.add(record('timeout', 'TIMEOUT'))
    store.add(record('running', 'PROCESSING'))
    store.add(record('done', 'SUCCEEDED'))
    store.add(record('failed', 'FAILED'))
    store.add(record('other', 'TIMEOUT', 2))
    expect(store.pendingOf(1).map(r => r.recording_id).sort()).toEqual(['running', 'timeout'])
    store.updateStatus('timeout', { status: 'SUCCEEDED' })
    expect(store.pendingOf(1).map(r => r.recording_id)).toEqual(['running'])
  })
  it('页面重载后仍恢复查询本地存储的超时任务', () => {
    localStorage.setItem('iteaching_uploads', JSON.stringify([record('timeout', 'TIMEOUT')]))
    expect(useRecordingsStore().pendingOf(1).map(r => r.recording_id)).toEqual(['timeout'])
  })
})
