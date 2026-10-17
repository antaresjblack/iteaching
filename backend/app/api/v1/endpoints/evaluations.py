from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DatabaseSession
from app.api.v1.endpoints.courses import get_accessible_course
from app.api.v1.endpoints.recordings import get_accessible_recording
from app.models import Course, Evaluation, EvaluationReview, Recording, ScoreCalibration, User
from app.schemas.business import CalibrationCreate, ReviewCreate, Role
from app.services.recordings import (
    DIMENSION_KEYS,
    effective_scores,
    redact_text,
    serialize_evaluation,
)

router = APIRouter()


def get_accessible_evaluation(db: DatabaseSession, user: User, evaluation_id: int) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    get_accessible_recording(db, user, evaluation.recording_id)
    return evaluation


def require_supervisor_or_admin(user: User, course: Course) -> None:
    if user.role == Role.ADMIN.value:
        return
    if user.role != Role.SUPERVISOR.value or course.supervisor_id != user.id:
        raise HTTPException(
            status_code=403, detail="Only the assigned supervisor can review evaluations"
        )


@router.get("/recordings/{recording_id}/evaluation")
def read_recording_evaluation(
    recording_id: str, user: CurrentUser, db: DatabaseSession
) -> dict[str, object]:
    recording = get_accessible_recording(db, user, recording_id)
    evaluation = db.scalar(select(Evaluation).where(Evaluation.recording_id == recording.id))
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return {"code": 0, "message": "success", "data": serialize_evaluation(evaluation)}


@router.get("/evaluations/{evaluation_id}")
def read_evaluation(
    evaluation_id: int, user: CurrentUser, db: DatabaseSession
) -> dict[str, object]:
    evaluation = get_accessible_evaluation(db, user, evaluation_id)
    return {"code": 0, "message": "success", "data": serialize_evaluation(evaluation)}


@router.get("/courses/{course_id}/evaluations")
def list_course_evaluations(
    course_id: int,
    user: CurrentUser,
    db: DatabaseSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    get_accessible_course(db, user, course_id)
    base_query = select(Evaluation).join(Recording).where(Recording.course_id == course_id)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    evaluations = db.scalars(
        base_query.order_by(Recording.recorded_at.desc(), Evaluation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": [
                {**serialize_evaluation(item), "recorded_at": item.recording.recorded_at}
                for item in evaluations
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    }


@router.get("/courses/{course_id}/comparison")
def compare_recent_classes(
    course_id: int, user: CurrentUser, db: DatabaseSession
) -> dict[str, object]:
    get_accessible_course(db, user, course_id)
    evaluations = db.scalars(
        select(Evaluation)
        .join(Recording)
        .where(Recording.course_id == course_id)
        .order_by(Recording.recorded_at.desc(), Evaluation.id.desc())
        .limit(2)
    ).all()
    if len(evaluations) < 2:
        return {"code": 0, "message": "success", "data": None}
    latest, previous = evaluations
    latest_overall, latest_dimensions = effective_scores(latest)
    previous_overall, previous_dimensions = effective_scores(previous)
    return {
        "code": 0,
        "message": "success",
        "data": {
            "latest": {
                "evaluation_id": latest.id,
                "recording_id": latest.recording_id,
                "recorded_at": latest.recording.recorded_at,
                "overall_score": latest_overall,
                "dimension_scores": latest_dimensions,
            },
            "previous": {
                "evaluation_id": previous.id,
                "recording_id": previous.recording_id,
                "recorded_at": previous.recording.recorded_at,
                "overall_score": previous_overall,
                "dimension_scores": previous_dimensions,
            },
            "delta": {
                "overall_score": latest_overall - previous_overall,
                "dimension_scores": {
                    key: (
                        latest_dimensions[key] - previous_dimensions[key]
                        if key in latest_dimensions and key in previous_dimensions
                        else None
                    )
                    for key in DIMENSION_KEYS
                },
            },
        },
    }


@router.post("/evaluations/{evaluation_id}/reviews", status_code=status.HTTP_201_CREATED)
def add_review(
    evaluation_id: int,
    body: ReviewCreate,
    user: CurrentUser,
    db: DatabaseSession,
) -> dict[str, object]:
    evaluation = get_accessible_evaluation(db, user, evaluation_id)
    course = db.get(Course, evaluation.recording.course_id)
    require_supervisor_or_admin(user, course)
    review = EvaluationReview(
        evaluation_id=evaluation.id, supervisor_id=user.id, comment=body.comment
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": review.id,
            "comment": redact_text(review.comment),
            "created_at": review.created_at,
        },
    }


@router.post("/evaluations/{evaluation_id}/calibrations", status_code=status.HTTP_201_CREATED)
def calibrate_evaluation(
    evaluation_id: int,
    body: CalibrationCreate,
    user: CurrentUser,
    db: DatabaseSession,
) -> dict[str, object]:
    evaluation = get_accessible_evaluation(db, user, evaluation_id)
    course = db.get(Course, evaluation.recording.course_id)
    require_supervisor_or_admin(user, course)
    calibration = ScoreCalibration(
        evaluation_id=evaluation.id,
        supervisor_id=user.id,
        overall_score=body.overall_score,
        dimension_scores=body.dimension_scores,
        comment=body.comment,
    )
    db.add(calibration)
    db.commit()
    db.refresh(calibration)
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": calibration.id,
            "overall_score": calibration.overall_score,
            "dimension_scores": calibration.dimension_scores,
            "comment": redact_text(calibration.comment or ""),
            "created_at": calibration.created_at,
        },
    }
