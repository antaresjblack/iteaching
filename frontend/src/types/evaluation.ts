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

/** v2 指标状态：evaluated 已评价，insufficient_evidence 依据不足 */
export type IndicatorStatus = 'evaluated' | 'insufficient_evidence'

/** 指标证据：segment_id 对应分段，quote 为逐字引文 */
export interface IndicatorEvidence {
  segment_id: string
  quote: string
}

/** v2 六维指标（后端 IndicatorResult 脱敏输出） */
export interface IndicatorRead {
  id: DimensionKey
  status: IndicatorStatus
  score: number | null
  reason: string
  evidence: IndicatorEvidence[]
}

/** 评价详情（后端 serialize_evaluation 输出） */
export interface EvaluationRead {
  /** AI已观察维度均分，非完整总分，不含人工校准 */
  observed_score?: number | null
  observed_count?: number
  dimension_count?: number
  id: number
  recording_id: string
  version: number
  mode: EvaluationMode
  /** v2 的评价标准版本；v1 或缺失时为 legacy-v1 */
  rubric_version: string
  /** v2 六维指标与逐字证据；v1/basic 可能为空数组 */
  indicators: IndicatorRead[]
  transcript: string
  segments: TranscriptSegment[]
  /** 校准后生效总分；v2 存在依据不足时可为 null */
  overall_score: number | null
  /** AI 模型原始总分；可为 null */
  model_overall_score: number | null
  /** AI 模型原始六维分；可为 null */
  model_dimension_scores: Partial<Record<DimensionKey, number | null>>
  overall_evidence: string
  problems: string[]
  /** 校准后生效六维分；basic 模式可能为空对象，v2 单项可为 null */
  dimension_scores: Partial<Record<DimensionKey, number | null>>
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
  /** 两次评价的评价标准与模式一致才可比 */
  comparable: boolean
  /** 不可比时说明原因 */
  reason: string | null
  latest: {
    evaluation_id: number
    recording_id: string
    recorded_at: string
    overall_score: number | null
    dimension_scores: Record<string, number | null>
  }
  previous: {
    evaluation_id: number
    recording_id: string
    recorded_at: string
    overall_score: number | null
    dimension_scores: Record<string, number | null>
  }
  delta: {
    /** 不可比或任一次总分缺失时为 null */
    overall_score: number | null
    dimension_scores: Partial<Record<DimensionKey, number | null>>
  }
}
