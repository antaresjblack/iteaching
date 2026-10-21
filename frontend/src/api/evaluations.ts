import { get, post } from './http'

import type {
  CalibrationRead,
  ComparisonResult,
  EvaluationPage,
  EvaluationRead,
  ReviewRead,
} from '@/types/evaluation'

/** GET /recordings/{id}/evaluation（评价未生成时 404） */
export function getEvaluationByRecording(recordingId: string): Promise<EvaluationRead> {
  return get<EvaluationRead>(`/recordings/${recordingId}/evaluation`)
}

/** GET /evaluations/{id} */
export function getEvaluationById(id: number): Promise<EvaluationRead> {
  return get<EvaluationRead>(`/evaluations/${id}`)
}

/** GET /courses/{id}/evaluations（分页，按录制时间倒序） */
export function listCourseEvaluations(
  courseId: number,
  page: number,
  pageSize: number,
): Promise<EvaluationPage> {
  return get<EvaluationPage>(`/courses/${courseId}/evaluations`, {
    params: { page, page_size: pageSize },
  })
}

/** GET /courses/{id}/comparison（不足两次时 data 为 null） */
export function compareCourse(courseId: number): Promise<ComparisonResult | null> {
  return get<ComparisonResult | null>(`/courses/${courseId}/comparison`)
}

/** POST /evaluations/{id}/reviews（仅该课程督导/admin） */
export function addReview(evaluationId: number, comment: string): Promise<ReviewRead> {
  return post<ReviewRead>(`/evaluations/${evaluationId}/reviews`, { comment })
}

export interface CalibrationCreate {
  overall_score?: number
  dimension_scores?: Record<string, number>
  comment?: string
}

/** POST /evaluations/{id}/calibrations（总分/分维/说明至少一项） */
export function addCalibration(
  evaluationId: number,
  body: CalibrationCreate,
): Promise<CalibrationRead> {
  return post<CalibrationRead>(`/evaluations/${evaluationId}/calibrations`, body)
}
