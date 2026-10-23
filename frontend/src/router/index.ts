import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { isAdmin } from '@/utils/roles'

declare module 'vue-router' {
  interface RouteMeta {
    /** 需要登录，默认 true（/login 显式关闭） */
    requiresAuth?: boolean
    /** 仅管理员可访问 */
    adminOnly?: boolean
    /** 页面标题 */
    title?: string
  }
}

export const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/',
    redirect: '/courses',
  },
  {
    path: '/courses',
    name: 'courses',
    component: () => import('@/views/CourseListView.vue'),
    meta: { title: '课程' },
  },
  {
    path: '/courses/:id',
    name: 'course-detail',
    component: () => import('@/views/CourseDetailView.vue'),
    meta: { title: '课程详情' },
  },
  {
    path: '/supervisions',
    name: 'supervision-courses',
    component: () => import('@/views/SupervisionCoursesView.vue'),
    meta: { title: '我查过的课' },
  },
  {
    path: '/evaluations/:id',
    name: 'evaluation-detail',
    component: () => import('@/views/EvaluationDetailView.vue'),
    meta: { title: '评价详情' },
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/AdminUsersView.vue'),
    meta: { adminOnly: true, title: '用户管理' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { requiresAuth: false, title: '页面不存在' },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

/** 守卫入参的最小结构（兼容 vue-router 的 RouteLocationNormalized） */
export interface GuardTarget {
  meta: { requiresAuth?: boolean; adminOnly?: boolean }
  path: string
  query?: unknown
}

/** 路由守卫：登录态 + 角色控制；单独导出便于测试 */
export function routeGuard(to: GuardTarget) {
  const auth = useAuthStore()
  if (auth.isAuthenticated && to.path === '/login') {
    return { path: '/courses' }
  }
  if (to.meta.requiresAuth === false) {
    return true
  }
  if (!auth.isAuthenticated) {
    return { path: '/login', query: { redirect: to.path } }
  }
  if (to.meta.adminOnly && !isAdmin(auth.user)) {
    return { path: '/courses' }
  }
  return true
}

router.beforeEach((to) => routeGuard(to))

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · AI 教学督导系统` : 'AI 教学督导系统'
})
