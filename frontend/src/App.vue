<script setup lang="ts">
import { useRoute } from 'vue-router'

import AppHeader from '@/components/AppHeader.vue'

const route = useRoute()
</script>

<template>
  <div class="app-shell">
    <AppHeader v-if="route.meta.requiresAuth !== false" />
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.app-main {
  flex: 1;
}
</style>
