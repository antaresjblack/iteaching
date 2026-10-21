<script setup lang="ts">
import { ChatLineSquare } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { ref } from 'vue'

import { addReview } from '@/api/evaluations'
import type { ReviewRead } from '@/types/evaluation'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{
  evaluationId: number
  reviews: ReviewRead[]
  canWrite: boolean
}>()

const emit = defineEmits<{
  saved: []
}>()

const comment = ref('')
const submitting = ref(false)

async function handleSubmit(): Promise<void> {
  const text = comment.value.trim()
  if (!text) {
    ElMessage.warning('评语内容不能为空')
    return
  }
  submitting.value = true
  try {
    await addReview(props.evaluationId, text)
    ElMessage.success('评语已保存')
    comment.value = ''
    emit('saved')
  } catch {
    // 错误已由 http 层统一提示
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <h3 class="section-title">督导评语</h3>

    <div v-if="reviews.length === 0" class="review-empty">
      <span class="text-secondary">暂无评语</span>
    </div>
    <ul v-else class="review-list">
      <li v-for="review in reviews" :key="review.id" class="review-item">
        <div class="review-head">
          <span class="review-icon"><el-icon><ChatLineSquare /></el-icon></span>
          <span class="review-time tabular">{{ formatDateTime(review.created_at) }}</span>
        </div>
        <p class="review-text">{{ review.comment }}</p>
      </li>
    </ul>

    <div v-if="canWrite" class="review-form">
      <el-input
        v-model="comment"
        type="textarea"
        :rows="3"
        maxlength="10000"
        show-word-limit
        placeholder="填写对本次课堂的督导评语"
      />
      <div class="review-actions">
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!comment.trim()"
          @click="handleSubmit"
        >
          保存评语
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-list {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
}

.review-item {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 8px;
  background: var(--surface);
}

.review-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.review-icon {
  color: var(--brand);
  display: inline-flex;
}

.review-time {
  font-size: 12px;
  color: var(--text-secondary);
}

.review-text {
  margin-top: 4px;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.review-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.review-actions {
  display: flex;
  justify-content: flex-end;
}

.review-empty {
  padding: 12px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius);
  margin-bottom: 16px;
}
</style>
