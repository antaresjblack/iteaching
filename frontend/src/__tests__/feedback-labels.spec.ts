import { describe, expect, it } from 'vitest'
import { readableFeedback } from '@/utils/dimensions'

describe('问题与建议中文展示', () => {
  it('转换历史维度和优先级标记', () => {
    expect(readableFeedback('[pre_assessment] 缺少检查；[high] 完善post_assessment'))
      .toBe('【前测】 缺少检查；【高优先级】 完善后测')
  })
  it('保留普通中文与未知标记', () => {
    expect(readableFeedback('【前测】增加提问[示例]')).toBe('【前测】增加提问[示例]')
  })
})
