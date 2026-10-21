<script setup lang="ts">
import { SwitchButton } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { isAdmin, roleLabel } from '@/utils/roles'

const auth = useAuthStore()
const router = useRouter()

const navItems = computed(() => [
  { label: '课程', path: '/courses' },
  ...(isAdmin(auth.user) ? [{ label: '用户管理', path: '/admin/users' }] : []),
])

async function handleLogout(): Promise<void> {
  await ElMessageBox.confirm('确定退出登录吗？', '退出登录', {
    confirmButtonText: '退出',
    cancelButtonText: '取消',
    type: 'warning',
  })
  auth.logout()
  await router.push('/login')
}
</script>

<template>
  <header class="app-header">
    <div class="header-inner">
      <div class="brand">
        <span class="brand-mark">教</span>
        <span class="brand-name">AI 教学督导系统</span>
      </div>

      <nav v-if="auth.isAuthenticated" class="nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-link"
          active-class="nav-link--active"
          :aria-label="item.label"
        >
          {{ item.label }}
        </RouterLink>
      </nav>

      <div v-if="auth.isAuthenticated" class="user-area">
        <span class="username">{{ auth.user?.username }}</span>
        <span class="role-tag">{{ roleLabel(auth.user!.role) }}</span>
        <el-button
          text
          :icon="SwitchButton"
          aria-label="退出登录"
          title="退出登录"
          @click="handleLogout"
        />
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 20;
}

.header-inner {
  max-width: 1160px;
  margin: 0 auto;
  padding: 0 16px;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.brand-mark {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  background: var(--brand);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.brand-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.nav {
  display: flex;
  gap: 4px;
  flex: 1;
}

.nav-link {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 14px;
  transition:
    color 0.15s,
    background-color 0.15s;
}

.nav-link:hover {
  color: var(--brand);
  background: var(--brand-soft);
}

.nav-link--active {
  color: var(--brand);
  background: var(--brand-soft);
  font-weight: 600;
}

.user-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.username {
  font-size: 13px;
  color: var(--text-primary);
}

.role-tag {
  font-size: 12px;
  color: var(--brand);
  background: var(--brand-soft);
  border-radius: var(--radius-sm);
  padding: 1px 8px;
}

@media (max-width: 640px) {
  .brand-name {
    display: none;
  }

  .header-inner {
    gap: 12px;
  }
}
</style>
