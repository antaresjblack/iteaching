/** BOPPPS 六维 key（与后端 Dimension 枚举一致） */
export type DimensionKey =
  | 'bridge_in'
  | 'objectives'
  | 'pre_assessment'
  | 'participatory_learning'
  | 'post_assessment'
  | 'summary'

/** 六维固定顺序，用于雷达图/对比图 */
export const DIMENSION_KEYS: readonly DimensionKey[] = [
  'bridge_in',
  'objectives',
  'pre_assessment',
  'participatory_learning',
  'post_assessment',
  'summary',
] as const

export type SpeakerRole = 'teacher' | 'student' | 'unknown'

export type EvaluationMode = 'basic' | 'boppps'

/** 转写分段（后端 TranscriptSegmentInput/输出） */
export interface TranscriptSegment {
  start_seconds: number
  end_seconds: number
  text: string
  speaker_id: string | null
  role: SpeakerRole
}

/** 改进建议，source 为 ai（模型生成）或 rule（规则生成） */
export interface Suggestion {
  text: string
  source: 'ai' | 'rule'
}

/** 督导评语 */
export interface ReviewRead {
  id: number
  comment: string
  created_at: string
}

/** 人工校准记录（后端按 id 倒序应用最新一次校准） */
export interface CalibrationRead {
  id: number
  overall_score: number | null
  dimension_scores: Record<string, number> | null
  comment: string
  created_at: string
}

/** 评价详情（后端 serialize_evaluation 输出） */
export interface EvaluationRead {
  id: number
  recording_id: string
  version: number
  mode: EvaluationMode
  transcript: string
  segments: TranscriptSegment[]
  /** 校准后生效总分 */
  overall_score: number
  /** AI 模型原始总分 */
  model_overall_score: number
  overall_evidence: string
  problems: string[]
  /** basic 模式可能为空对象 */
  dimension_scores: Partial<Record<DimensionKey, number>>
  suggestions: Suggestion[]
  reviews: ReviewRead[]
  calibrations: CalibrationRead[]
}

/** GET /courses/{id}/evaluations 分页项（评价 + 录制时间） */
export interface EvaluationListItem extends EvaluationRead {
  recorded_at: string
}

/** 分页响应 data 字段 */
export interface EvaluationPage {
  items: EvaluationListItem[]
  page: number
  page_size: number
  total: number
}

/** GET /courses/{id}/comparison 的 data 字段 */
export interface ComparisonResult {
  latest: {
    evaluation_id: number
    recording_id: string
    recorded_at: string
    overall_score: number
    dimension_scores: Record<string, number>
  }
  previous: {
    evaluation_id: number
    recording_id: string
    recorded_at: string
    overall_score: number
    dimension_scores: Record<string, number>
  }
  delta: {
    overall_score: number
    dimension_scores: Partial<Record<DimensionKey, number | null>>
  }
}
