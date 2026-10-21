/** 空数据与错误状态：课程列表空态/失败态、评价 404 提示"尚未完成" */
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { ApiError } from '@/types/api'
import CourseListView from '@/views/CourseListView.vue'
import EvaluationDetailView from '@/views/EvaluationDetailView.vue'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/courses', () => ({
  listCourses: vi.fn(),
  createCourse: vi.fn(),
  getCourse: vi.fn(),
}))

vi.mock('@/api/evaluations', () => ({
  getEvaluationById: vi.fn(),
}))

vi.mock('@/api/recordings', () => ({
  downloadRecordingAudio: vi.fn(async () => new Blob()),
}))

const { listCourses, getCourse } = await import('@/api/courses')
const { getEvaluationById } = await import('@/api/evaluations')

function setupAuth(role: 'admin' | 'supervisor' | 'teacher') {
  const pinia = createPinia()
  setActivePinia(pinia)
  localStorage.setItem('iteaching_token', 'token-x')
  localStorage.setItem(
    'iteaching_user',
    JSON.stringify({ id: 1, username: role, role, is_active: true }),
  )
  const auth = useAuthStore(pinia)
  auth.restore()
  return pinia
}

function mountWithRouter(component: Component): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component }],
  })
}

describe('空数据与错误状态', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('课程列表为空时展示空状态与操作引导', async () => {
    vi.mocked(listCourses).mockResolvedValue([])
    const pinia = setupAuth('teacher')
    const wrapper = mount(CourseListView, {
      global: { plugins: [pinia, ElementPlus] },
    })
    await flushPromises(wrapper)

    expect(wrapper.text()).toContain('暂无课程')
    expect(wrapper.text()).toContain('请联系管理员或督导为你分配课程')
  })

  it('课程列表加载失败时展示错误与重试，重试成功后恢复', async () => {
    vi.mocked(listCourses)
      .mockRejectedValueOnce(new ApiError('Internal server error', { status: 500 }))
      .mockResolvedValueOnce([{ id: 1, name: '课程A', supervisor_id: 2, teacher_id: 3, created_at: '2026-10-01T08:00:00Z' }])
    const pinia = setupAuth('supervisor')
    const wrapper = mount(CourseListView, {
      global: { plugins: [pinia, ElementPlus] },
    })
    await flushPromises(wrapper)
    expect(wrapper.text()).toContain('Internal server error')

    // 点击错误状态中的"重试"按钮（而非顶栏的"新建课程"）
    const retryButton = wrapper.findAll('button').find((button) => button.text().includes('重试'))
    expect(retryButton).toBeTruthy()
    await retryButton!.trigger('click')
    await flushPromises(wrapper)
    expect(wrapper.text()).toContain('课程A')
  })

  it('评价 404 时显示"评价尚未完成"而非系统异常', async () => {
    vi.mocked(getEvaluationById).mockRejectedValue(
      new ApiError('Evaluation not found', { status: 404 }),
    )
    vi.mocked(getCourse).mockResolvedValue({
      id: 1,
      name: '课程A',
      supervisor_id: 2,
      teacher_id: 3,
      created_at: '2026-10-01T08:00:00Z',
    })
    const pinia = setupAuth('teacher')
    const router = mountWithRouter(EvaluationDetailView)
    await router.push('/?course_id=1')
    await router.isReady()

    const wrapper = mount(EvaluationDetailView, {
      global: {
        plugins: [pinia, router, ElementPlus],
        stubs: { AudioPlayer: true, BopppsRadarChart: true, SegmentTimeline: true },
      },
    })
    await flushPromises(wrapper)

    expect(wrapper.text()).toContain('评价尚未完成')
  })
})

/** 等待组件内异步请求与响应式更新 */
async function flushPromises(wrapper: ReturnType<typeof mount>): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await wrapper.vm.$nextTick()
}
