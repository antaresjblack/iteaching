<!-- 周课表组件：左侧节次 + 顶部星期的二维网格，课程卡片按节次跨行合并 -->
<script setup lang="ts">
import { computed } from 'vue'

import { WEEKDAY_LABELS, PERIOD_TIMES } from '@/utils/course'
import {
  buildTimetableCards,
  PERIOD_COUNT,
  TIMETABLE_COLORS,
  type TimetableCard,
} from '@/utils/timetable'
import type { CourseRead } from '@/types/course'

const props = defineProps<{ courses: CourseRead[] }>()

const emit = defineEmits<{ (e: 'select', course: CourseRead): void }>()

/** 网格样式：节次表头列 + 7 个星期列；第 1 行为星期表头，其余行为节次 */
const gridStyle = computed(() => ({
  gridTemplateColumns: '76px repeat(7, minmax(108px, 1fr))',
  gridTemplateRows: `44px repeat(${PERIOD_COUNT}, 84px)`,
}))

const cards = computed(() => buildTimetableCards(props.courses))

/** 卡片定位：星期 → 列（+1 避开节次列），节次 → 行（+1 避开表头行），跨节垂直合并 */
function cardStyle(card: TimetableCard): Record<string, string> {
  return {
    gridColumn: `${card.weekday + 1} / span 1`,
    gridRow: `${card.startPeriod + 1} / span ${card.span}`,
    background: TIMETABLE_COLORS[card.colorIndex],
  }
}

function onCardClick(card: TimetableCard): void {
  emit('select', card.course)
}
</script>

<template>
  <div class="tt-scroll">
    <div class="tt-grid" :style="gridStyle">
      <!-- 左上角斜线分割单元格：右上"星期"、左下"节次" -->
      <div class="tt-cell tt-corner">
        <span class="corner-text corner-weekday">星期</span>
        <span class="corner-text corner-period">节次</span>
      </div>

      <!-- 顶部星期表头：显式定位第 1 行，避免与卡片占位冲突 -->
      <div
        v-for="(label, dayIndex) in WEEKDAY_LABELS"
        :key="label"
        class="tt-cell tt-head"
        :style="{ gridColumn: `${dayIndex + 2}`, gridRow: '1' }"
      >
        {{ label }}
      </div>

      <!-- 节次行：表头列 + 7 个空白格，全部显式定位（自动流动会跳过卡片占用的格子导致错位） -->
      <template v-for="(period, pIndex) in PERIOD_TIMES" :key="`row-${pIndex}`">
        <div
          class="tt-cell tt-period-head"
          :style="{ gridColumn: '1', gridRow: `${pIndex + 2}` }"
        >
          <span class="period-name">第{{ ['一', '二', '三', '四', '五', '六', '七', '八'][pIndex] }}节</span>
          <span class="period-time">{{ period.start }}</span>
        </div>
        <div
          v-for="day in 7"
          :key="`blank-${pIndex}-${day}`"
          class="tt-cell tt-blank"
          :style="{ gridColumn: `${day + 1}`, gridRow: `${pIndex + 2}` }"
        />
      </template>

      <!-- 课程卡片：圆角色块，跨节垂直合并 -->
      <div
        v-for="card in cards"
        :key="`${card.courseId}-${card.weekday}-${card.startPeriod}`"
        class="tt-card"
        :style="cardStyle(card)"
        @click="onCardClick(card)"
      >
        <p class="card-name">{{ card.name }}</p>
        <p class="card-meta">{{ card.location }}<template v-if="card.week"> · {{ card.week }}</template></p>
        <p class="card-meta">{{ card.className }}</p>
        <p v-if="card.teacherName" class="card-meta">{{ card.teacherName }}</p>
        <p class="card-assess">{{ card.assessment }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tt-scroll {
  overflow-x: auto;
  background: var(--surface);
  border-radius: var(--radius);
}

.tt-grid {
  display: grid;
  min-width: 880px;
}

.tt-cell {
  border-right: 1px solid #f0f0f0;
  border-bottom: 1px solid #f0f0f0;
}

/* 表头：极浅蓝底 + 亮蓝文字 */
.tt-head {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f9fe;
  color: #2e7cd6;
  font-size: 13px;
}

/* 左上角斜线分割 */
.tt-corner {
  position: relative;
  background: #f3f9fe;
  overflow: hidden;
}

.tt-corner::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top right,
    transparent calc(50% - 0.5px),
    #c9dff2 calc(50% - 0.5px),
    #c9dff2 calc(50% + 0.5px),
    transparent calc(50% + 0.5px)
  );
}

.corner-text {
  position: absolute;
  color: #2e7cd6;
  font-size: 12px;
}

.corner-weekday {
  top: 6px;
  right: 8px;
}

.corner-period {
  bottom: 6px;
  left: 8px;
}

/* 节次表头 */
.tt-period-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  background: #f3f9fe;
}

.period-name {
  color: #2e7cd6;
  font-size: 13px;
}

.period-time {
  color: #8fb8e0;
  font-size: 11px;
}

.tt-blank {
  background: #fff;
}

/* 课程卡片：无边框圆角色块，hover 轻微上浮 + 阴影 */
.tt-card {
  z-index: 1;
  margin: 3px;
  padding: 6px 8px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.tt-card:hover {
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.14);
  transform: translateY(-1px);
}

.card-name {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-meta {
  margin: 0 0 2px;
  font-size: 12px;
  color: #5a5e66;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-assess {
  margin: 4px 0 0;
  font-size: 11px;
  color: #909399;
}
</style>
