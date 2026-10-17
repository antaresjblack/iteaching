<script setup lang="ts">
import { ArrowLeft } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="page not-found">
    <el-empty description="页面不存在或已被移除">
      <el-button type="primary" :icon="ArrowLeft" @click="router.push('/courses')">返回课程列表</el-button>
    </el-empty>
  </div>
</template>

<style scoped>
.not-found {
  padding-top: 80px;
}
</style>
