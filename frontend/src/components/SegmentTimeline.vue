<script setup lang="ts">
import { computed } from 'vue'

import type { SpeakerRole, TranscriptSegment } from '@/types/evaluation'
import { formatSeconds } from '@/utils/format'

const props = defineProps<{
  segments: TranscriptSegment[]
}>()

const emit = defineEmits<{
  seek: [seconds: number]
}>()

const ROLE_LABELS: Record<SpeakerRole, string> = {
  teacher: '教师',
  student: '学生',
  unknown: '未知',
}

/** 按开始时间排序 */
const sorted = computed(() => [...props.segments].sort((a, b) => a.start_seconds - b.start_seconds))

/** 同一 speaker_id 保持同色，未提供 speaker_id 时按角色取色 */
function roleClass(segment: TranscriptSegment): string {
  return `role-${segment.role}`
}
</script>

<template>
  <div v-if="sorted.length === 0" class="timeline-empty">
    <el-empty description="暂无转写分段数据" :image-size="64" />
  </div>
  <ol v-else class="timeline">
    <li
      v-for="(segment, index) in sorted"
      :key="index"
      class="segment"
      :class="roleClass(segment)"
      role="button"
      tabindex="0"
      :aria-label="`跳转到 ${formatSeconds(segment.start_seconds)}`"
      @click="emit('seek', segment.start_seconds)"
      @keydown.enter="emit('seek', segment.start_seconds)"
    >
      <div class="segment-meta">
        <span class="segment-time tabular">
          {{ formatSeconds(segment.start_seconds) }} - {{ formatSeconds(segment.end_seconds) }}
        </span>
        <span class="segment-role">{{ ROLE_LABELS[segment.role] }}</span>
        <span v-if="segment.speaker_id" class="segment-speaker">{{ segment.speaker_id }}</span>
      </div>
      <p class="segment-text">{{ segment.text }}</p>
    </li>
  </ol>
</template>

<style scoped>
.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  border-left: 1px solid var(--border);
}

.segment {
  position: relative;
  padding: 8px 12px 8px 16px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color 0.15s;
}

.segment:hover,
.segment:focus-visible {
  background: var(--bg-page);
  outline: none;
}

.segment::before {
  content: '';
  position: absolute;
  left: -3px;
  top: 12px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--segment-color);
}

.role-teacher {
  --segment-color: var(--role-teacher);
}

.role-student {
  --segment-color: var(--role-student);
}

.role-unknown {
  --segment-color: var(--role-unknown);
}

.segment-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.segment-time {
  font-size: 12px;
  color: var(--text-secondary);
}

.segment-role {
  font-size: 12px;
  color: var(--segment-color);
  border: 1px solid color-mix(in srgb, var(--segment-color) 40%, transparent);
  background: color-mix(in srgb, var(--segment-color) 8%, transparent);
  border-radius: var(--radius-sm);
  padding: 0 6px;
}

.segment-speaker {
  font-size: 12px;
  color: var(--text-placeholder);
}

.segment-text {
  margin-top: 2px;
  font-size: 14px;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}
</style>
