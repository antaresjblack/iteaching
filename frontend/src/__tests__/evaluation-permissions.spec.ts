/** 评价详情页权限：teacher 只读，课程督导/管理员可见写入控件 */
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import EvaluationDetailView from '@/views/EvaluationDetailView.vue'
import { useAuthStore } from '@/stores/auth'
import type { EvaluationRead } from '@/types/evaluation'

const evaluation: EvaluationRead = {
  id: 9,
  recording_id: 'rec-1',
  version: 1,
  mode: 'basic',
  rubric_version: 'legacy-v1',
  indicators: [],
  transcript: '转写文本',
  segments: [],
  overall_score: 82,
  model_overall_score: 75,
  model_dimension_scores: {},
  overall_evidence: '证据',
  problems: [],
  dimension_scores: {},
  suggestions: [],
  reviews: [],
  calibrations: [],
}

vi.mock('@/api/evaluations', () => ({
  getEvaluationById: vi.fn(async () => evaluation),
  addReview: vi.fn(),
  addCalibration: vi.fn(),
}))

vi.mock('@/api/courses', () => ({
  getCourse: vi.fn(async () => ({
    id: 1,
    code: 'MATH-001',
    name: '测试课程',
    location: '信息',
    class_name: '2026 级 1 班',
    schedules: [{ weekday: 1, start_time: '08:00', end_time: '09:40' }],
    assessment_form: 'percent',
    description: null,
    teacher_id: 3,
    teacher_name: '李老师',
    status: 'not_started',
    created_at: '2026-10-01T08:00:00Z',
  })),
}))

vi.mock('@/api/recordings', () => ({
  downloadRecordingAudio: vi.fn(async () => new Blob()),
}))

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/evaluations/:id', component: EvaluationDetailView },
    ],
  })
}

async function mountView(role: 'admin' | 'supervisor' | 'teacher') {
  const router = makeRouter()
  await router.push('/evaluations/9?course_id=1')
  await router.isReady()

  // 组件与测试共用同一个 pinia 实例
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  localStorage.setItem('iteaching_token', 'token-x')
  localStorage.setItem(
    'iteaching_user',
    JSON.stringify({ id: role === 'teacher' ? 3 : 2, username: role, role, is_active: true }),
  )
  auth.restore()

  return mount(EvaluationDetailView, {
    global: {
      plugins: [pinia, router, ElementPlus],
      stubs: {
        AudioPlayer: { template: '<div class="audio-stub" />' },
        BopppsRadarChart: { template: '<div class="radar-stub" />' },
        SegmentTimeline: { template: '<div class="timeline-stub" />' },
      },
    },
  })
}

describe('评价详情页权限', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('teacher 视角只读：看不到评语输入与校准表单', async () => {
    const wrapper = await mountView('teacher')
    // 等待异步加载
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()

    const reviewSection = wrapper.findComponent({ name: 'ReviewSection' })
    const calibrationSection = wrapper.findComponent({ name: 'CalibrationSection' })
    expect(reviewSection.exists()).toBe(true)
    expect(reviewSection.props('canWrite')).toBe(false)
    expect(calibrationSection.props('canWrite')).toBe(false)
  })

  it('课程督导视角：可写评语与校准', async () => {
    const wrapper = await mountView('supervisor')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()

    const reviewSection = wrapper.findComponent({ name: 'ReviewSection' })
    const calibrationSection = wrapper.findComponent({ name: 'CalibrationSection' })
    expect(reviewSection.props('canWrite')).toBe(true)
    expect(calibrationSection.props('canWrite')).toBe(true)
  })

  it('督导可审核任意课程的评价（多对多经录音关联，不再按课程绑定）', async () => {
    const { getCourse } = await import('@/api/courses')
    vi.mocked(getCourse).mockResolvedValueOnce({
      id: 1,
      code: 'MATH-002',
      name: '测试课程',
      location: '建筑',
      class_name: '2026 级 2 班',
      schedules: [{ weekday: 2, start_time: '10:00', end_time: '11:40' }],
      assessment_form: 'percent',
      description: null,
      teacher_id: 3,
      teacher_name: '赵老师',
      status: 'not_started',
      created_at: '2026-10-01T08:00:00Z',
    })
    const wrapper = await mountView('supervisor')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()

    const reviewSection = wrapper.findComponent({ name: 'ReviewSection' })
    expect(reviewSection.props('canWrite')).toBe(true)
  })
})
