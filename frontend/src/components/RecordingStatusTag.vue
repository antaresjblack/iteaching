<script setup lang="ts">
import { computed } from 'vue'

import type { DisplayStatus } from '@/types/recording'

const props = defineProps<{
  status: DisplayStatus
}>()

const STATUS_META: Record<DisplayStatus, { label: string; type: 'info' | 'primary' | 'success' | 'danger' | 'warning' }> = {
  QUEUED: { label: '排队中', type: 'info' },
  PROCESSING: { label: '处理中', type: 'primary' },
  SUCCEEDED: { label: '已完成', type: 'success' },
  FAILED: { label: '失败', type: 'danger' },
  TIMEOUT: { label: '刷新已暂停', type: 'warning' },
}

const meta = computed(() => STATUS_META[props.status])
</script>

<template>
  <el-tag :type="meta.type" size="small" :disable-transitions="true">
    <span v-if="status === 'PROCESSING'" class="processing-dot" aria-hidden="true" />
    {{ meta.label }}
  </el-tag>
</template>

<style scoped>
.processing-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 4px;
  border-radius: 50%;
  background: currentcolor;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .processing-dot {
    animation: none;
  }
}
</style>
