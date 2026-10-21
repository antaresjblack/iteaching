/** 音频 Blob 加载：带 Bearer 头下载 → objectURL；重载/卸载时 revoke */
import { onScopeDispose, readonly, ref } from 'vue'

import { downloadRecordingAudio } from '@/api/recordings'

export function useAudioSource() {
  const url = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<Error | null>(null)

  function revoke(): void {
    if (url.value) {
      URL.revokeObjectURL(url.value)
      url.value = null
    }
  }

  async function load(recordingId: string): Promise<void> {
    revoke()
    loading.value = true
    error.value = null
    try {
      const blob = await downloadRecordingAudio(recordingId)
      url.value = URL.createObjectURL(blob)
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
    } finally {
      loading.value = false
    }
  }

  onScopeDispose(revoke)

  return { url: readonly(url), loading: readonly(loading), error: readonly(error), load, revoke }
}
