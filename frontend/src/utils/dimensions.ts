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
