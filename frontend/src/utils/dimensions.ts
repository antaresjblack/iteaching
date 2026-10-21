/** BOPPPS 六维中文名（与后端 DIMENSION_LABELS 一致） */
import type { DimensionKey } from '@/types/evaluation'

export const DIMENSION_LABELS: Record<DimensionKey, string> = {
  bridge_in: '导入',
  objectives: '目标',
  pre_assessment: '前测',
  participatory_learning: '参与式学习',
  post_assessment: '后测',
  summary: '总结',
}

/** 兼容历史评价中的内部维度标记，仅用于问题和建议正文。 */
export function readableFeedback(text: string): string {
  const labels: Record<string, string> = { ...DIMENSION_LABELS, objectives: '教学目标' }
  return text
    .replace(/\[\s*(bridge_in|objectives|pre_assessment|participatory_learning|post_assessment|summary)\s*\]/g,
      (_, key: string) => `【${labels[key]}】`)
    .replace(/\b(bridge_in|objectives|pre_assessment|participatory_learning|post_assessment|summary)\b/g,
      (key) => labels[key] ?? key)
    .replace(/\[(high|medium|low)\]/g,
      (_, key: string) => `【${({ high: '高优先级', medium: '中优先级', low: '低优先级' } as Record<string, string>)[key]}】`)
}
