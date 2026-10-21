import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ComparisonSection from '@/components/ComparisonSection.vue'
import { compareCourse } from '@/api/evaluations'
import type { ComparisonResult } from '@/types/evaluation'

const chart = vi.hoisted(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }))
vi.mock('echarts/core', () => ({ use: vi.fn(), init: vi.fn(() => chart) }))
vi.mock('@/api/evaluations', () => ({ compareCourse: vi.fn() }))

function fixture(comparable = true): ComparisonResult {
  const base = { evaluation_id: 1, recording_id: 'a', recorded_at: '2026-10-21T08:00:00Z', overall_score: null }
  return {
    comparable, reason: comparable ? null : '评价标准不同',
    latest: { ...base, dimension_scores: { bridge_in: 60, objectives: null, pre_assessment: 0 } },
    previous: { ...base, dimension_scores: { bridge_in: 40, objectives: 50, pre_assessment: 0 } },
    delta: { overall_score: null, dimension_scores: {} },
  }
}

describe('部分评分对比', () => {
  beforeEach(() => vi.clearAllMocks())
  it('绘制已有分数，缺失保持空值，真实零分参与比较', async () => {
    vi.mocked(compareCourse).mockResolvedValue(fixture())
    const wrapper = mount(ComparisonSection, { props: { courseId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.find('.comparison-chart').exists()).toBe(true)
    expect(wrapper.text()).toContain('证据不足')
    expect(wrapper.text()).toContain('+20.0')
    expect(wrapper.text()).toContain('+0.0')
    const option = chart.setOption.mock.calls.at(-1)![0]
    expect(option.series[0].data.slice(0, 3)).toEqual([60, '-', 0])
    vi.mocked(compareCourse).mockResolvedValue(null)
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('至少需要两次')
    expect(wrapper.find('.comparison-chart').exists()).toBe(false)
    expect(chart.dispose).toHaveBeenCalled()
    wrapper.unmount()
  })
  it('不同标准仍展示分数，但不计算变化', async () => {
    vi.mocked(compareCourse).mockResolvedValue(fixture(false))
    const wrapper = mount(ComparisonSection, { props: { courseId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('评价标准不同')
    expect(wrapper.text()).toContain('60.0')
    expect(wrapper.text()).not.toContain('+20.0')
    wrapper.unmount()
  })
})
