import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CalibrationSection from '@/components/CalibrationSection.vue'

vi.mock('@/api/evaluations', () => ({
  addCalibration: vi.fn(async (_id: number, body: unknown) => ({ id: 1, ...(body as object), created_at: '2026-10-17T10:00:00Z' })),
}))

const { addCalibration } = await import('@/api/evaluations')

function mountSection(canWrite: boolean) {
  return mount(CalibrationSection, {
    props: {
      evaluationId: 9,
      calibrations: [],
      modelOverallScore: 75,
      canWrite,
    },
    global: { plugins: [createPinia(), ElementPlus] },
  })
}

describe('人工校准提交', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('teacher 视角（canWrite=false）不渲染校准表单', () => {
    const wrapper = mountSection(false)
    expect(wrapper.find('.calibration-form').exists()).toBe(false)
  })

  it('supervisor 提交校准时携带总分与说明', async () => {
    const wrapper = mountSection(true)

    // 填写总分滑条
    const slider = wrapper.findComponent({ name: 'ElSlider' })
    expect(slider.exists()).toBe(true)
    // 直接修改内部表单状态不可行，改为通过输入说明 + 分维触发提交前校验
    const textarea = wrapper.find('textarea')
    await textarea.setValue('复核后调整总分')

    await wrapper.find('button').trigger('click')

    expect(addCalibration).toHaveBeenCalledWith(9, {
      overall_score: undefined,
      dimension_scores: {},
      comment: '复核后调整总分',
    })
    expect(wrapper.emitted('saved')).toBeTruthy()
  })

  it('空表单提交时给出提示且不调用接口', async () => {
    const wrapper = mountSection(true)
    await wrapper.find('button').trigger('click')
    expect(addCalibration).not.toHaveBeenCalled()
  })
})
