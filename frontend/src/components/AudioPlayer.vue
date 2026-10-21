<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { useAudioSource } from '@/composables/useAudioSource'

const props = defineProps<{
  recordingId: string
}>()

const player = ref<HTMLAudioElement>()
const { url, loading, error, load } = useAudioSource()

onMounted(() => {
  void load(props.recordingId)
})

watch(
  () => props.recordingId,
  (id) => {
    void load(id)
  },
)

/** 供外部（转写时间轴）跳转播放位置 */
function seekTo(seconds: number): void {
  if (player.value && url.value) {
    player.value.currentTime = seconds
    void player.value.play()
  }
}

defineExpose({ seekTo })
</script>

<template>
  <div class="audio-panel">
    <div v-if="loading" class="audio-state">
      <el-skeleton :rows="1" animated />
    </div>
    <div v-else-if="error" class="audio-state">
      <span class="text-secondary">音频加载失败，请刷新重试</span>
    </div>
    <audio v-else-if="url" ref="player" :src="url" controls preload="metadata" class="audio-player" />
  </div>
</template>

<style scoped>
.audio-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
}

.audio-player {
  width: 100%;
  height: 36px;
  display: block;
}

.audio-state {
  min-height: 36px;
  display: flex;
  align-items: center;
}
</style>
