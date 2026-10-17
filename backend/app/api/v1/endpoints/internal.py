from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import DatabaseSession
from app.core.config import settings
from app.models import (
    DimensionScore,
    Evaluation,
    ImprovementSuggestion,
    ProcessingTask,
    Recording,
    TranscriptSegment,
)
from app.schemas.business import EvaluationResultInput, TaskClaimRequest, TaskFailureRequest
from app.services.recordings import redact_text

router = APIRouter()
MAX_ATTEMPTS = 3


def require_service_token(x_service_token: str | None = Header(default=None)) -> None:
    if not x_service_token or not secrets.compare_digest(
        x_service_token, settings.ai_service_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        )


WorkerAuthorized = Depends(require_service_token)


def _require_claim(task: ProcessingTask, claim_token: str | None) -> None:
    if (
        task.status != "PROCESSING"
        or not claim_token
        or not task.claim_token
        or not secrets.compare_digest(claim_token, task.claim_token)
    ):
        raise HTTPException(status_code=409, detail="Task is not claimed by this worker")


def _lease_expired(task: ProcessingTask, now: datetime) -> bool:
    lease = task.lease_expires_at
    if lease is None:
        return True
    if lease.tzinfo is None:
        lease = lease.replace(tzinfo=UTC)
    return lease <= now


@router.post("/internal/tasks/claim", dependencies=[WorkerAuthorized])
def claim_task(
    db: DatabaseSession,
    body: TaskClaimRequest | None = None,
) -> dict[str, object]:
    now = datetime.now(UTC)
    max_attempts = min(settings.task_max_attempts, MAX_ATTEMPTS)
    db.execute(
        update(ProcessingTask)
        .where(
            ProcessingTask.status == "PROCESSING",
            ProcessingTask.lease_expires_at <= now,
            ProcessingTask.attempts >= max_attempts,
        )
        .values(
            status="FAILED",
            lease_expires_at=None,
            claim_token=None,
            last_error="Processing lease expired after maximum attempts",
        )
    )
    eligible = or_(
        and_(ProcessingTask.status == "QUEUED", ProcessingTask.attempts < max_attempts),
        and_(
            ProcessingTask.status == "PROCESSING",
            ProcessingTask.lease_expires_at <= now,
            ProcessingTask.attempts < max_attempts,
        ),
    )
    task_id = db.scalar(
        select(ProcessingTask.id).where(eligible).order_by(ProcessingTask.created_at).limit(1)
    )
    if task_id is None:
        db.commit()
        return {"code": 0, "message": "success", "data": None}

    claim_token = secrets.token_urlsafe(32)
    worker_id = body.worker_id if body else "worker"
    result = db.execute(
        update(ProcessingTask)
        .where(ProcessingTask.id == task_id, eligible)
        .values(
            status="PROCESSING",
            attempts=ProcessingTask.attempts + 1,
            lease_expires_at=now + timedelta(seconds=settings.task_lease_seconds),
            claimed_by=worker_id,
            claim_token=claim_token,
            last_error=None,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if result.rowcount != 1:
        return {"code": 0, "message": "success", "data": None}
    task = db.get(ProcessingTask, task_id)
    recording = db.get(Recording, task.recording_id) if task else None
    if task is None or recording is None:
        raise HTTPException(status_code=404, detail="Task or recording not found")
    return {
        "code": 0,
        "message": "success",
        "data": {
            "task_id": task.id,
            "recording_id": recording.id,
            "worker_id": task.claimed_by,
            "claim_token": claim_token,
            "attempt": task.attempts,
            "lease_expires_at": task.lease_expires_at,
            "audio_url": f"{settings.api_v1_prefix}/internal/tasks/{task.id}/audio",
        },
    }


@router.get("/internal/tasks/{task_id}/audio", dependencies=[WorkerAuthorized])
def download_task_audio(
    task_id: str,
    db: DatabaseSession,
    x_task_claim_token: str | None = Header(default=None),
) -> FileResponse:
    task = db.get(ProcessingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _require_claim(task, x_task_claim_token)
    if _lease_expired(task, datetime.now(UTC)):
        raise HTTPException(status_code=409, detail="Task lease has expired")
    recording = db.get(Recording, task.recording_id)
    path = Path(recording.storage_path) if recording else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type=recording.media_type, filename=recording.original_filename)


@router.post("/internal/tasks/{task_id}/lease", dependencies=[WorkerAuthorized])
def renew_lease(
    task_id: str,
    db: DatabaseSession,
    x_task_claim_token: str | None = Header(default=None),
) -> dict[str, object]:
    task = db.get(ProcessingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _require_claim(task, x_task_claim_token)
    now = datetime.now(UTC)
    renewed_until = now + timedelta(seconds=settings.task_lease_seconds)
    result = db.execute(
        update(ProcessingTask)
        .where(
            ProcessingTask.id == task_id,
            ProcessingTask.status == "PROCESSING",
            ProcessingTask.claim_token == x_task_claim_token,
            ProcessingTask.lease_expires_at > now,
        )
        .values(lease_expires_at=renewed_until)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task lease has expired or was replaced")
    db.commit()
    return {"code": 0, "message": "success", "data": {"lease_expires_at": renewed_until}}


@router.post("/internal/tasks/{task_id}/result", dependencies=[WorkerAuthorized])
def submit_result(
    task_id: str,
    body: EvaluationResultInput,
    db: DatabaseSession,
    x_task_claim_token: str | None = Header(default=None),
) -> dict[str, object]:
    task = db.get(ProcessingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    raw_result = body.model_dump(mode="json")
    existing = db.scalar(select(Evaluation).where(Evaluation.recording_id == task.recording_id))
    if task.status == "SUCCEEDED" and existing is not None:
        if existing.raw_result == raw_result:
            return {
                "code": 0,
                "message": "success",
                "data": {"evaluation_id": existing.id, "idempotent": True},
            }
        raise HTTPException(
            status_code=409, detail="A different result already completed this task"
        ) from None
    _require_claim(task, x_task_claim_token)
    if _lease_expired(task, datetime.now(UTC)):
        raise HTTPException(status_code=409, detail="Task lease has expired")
    recording = db.get(Recording, task.recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    if any(segment.end_seconds > recording.duration_seconds for segment in body.segments):
        raise HTTPException(
            status_code=422,
            detail="Transcript segments cannot exceed audio duration",
        )
    task_update = db.execute(
        update(ProcessingTask)
        .where(
            ProcessingTask.id == task_id,
            ProcessingTask.status == "PROCESSING",
            ProcessingTask.claim_token == x_task_claim_token,
            ProcessingTask.lease_expires_at > datetime.now(UTC),
        )
        .values(
            status="SUCCEEDED",
            lease_expires_at=None,
            claim_token=None,
            last_error=None,
        )
        .execution_options(synchronize_session=False)
    )
    if task_update.rowcount != 1:
        db.rollback()
        current_task = db.get(ProcessingTask, task_id)
        existing = db.scalar(select(Evaluation).where(Evaluation.recording_id == task.recording_id))
        if (
            current_task is not None
            and current_task.status == "SUCCEEDED"
            and existing is not None
            and existing.raw_result == raw_result
        ):
            return {
                "code": 0,
                "message": "success",
                "data": {"evaluation_id": existing.id, "idempotent": True},
            }
        raise HTTPException(status_code=409, detail="Task lease has expired or was replaced")

    evaluation = Evaluation(
        recording_id=task.recording_id,
        version=body.version,
        mode=body.mode,
        raw_result=raw_result,
        transcript=body.transcript,
        overall_score=body.overall_score,
        overall_evidence=body.overall_evidence,
        problems=[{"description": item} for item in body.problems],
    )
    db.add(evaluation)
    db.flush()
    for item in body.segments:
        db.add(
            TranscriptSegment(
                evaluation_id=evaluation.id,
                start_seconds=item.start_seconds,
                end_seconds=item.end_seconds,
                text=item.text,
                speaker_id=item.speaker_id,
                role=item.role,
            )
        )
    for dimension, score in body.dimension_scores.items():
        db.add(DimensionScore(evaluation_id=evaluation.id, dimension=dimension, score=score))
    for item in body.suggestions:
        db.add(ImprovementSuggestion(evaluation_id=evaluation.id, text=item.text, source="ai"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        current_task = db.get(ProcessingTask, task_id)
        existing = db.scalar(select(Evaluation).where(Evaluation.recording_id == task.recording_id))
        if (
            current_task is not None
            and current_task.status == "SUCCEEDED"
            and existing is not None
            and existing.raw_result == raw_result
        ):
            return {
                "code": 0,
                "message": "success",
                "data": {"evaluation_id": existing.id, "idempotent": True},
            }
        raise HTTPException(
            status_code=409, detail="A different result already completed this task"
        ) from None
    db.refresh(evaluation)
    return {
        "code": 0,
        "message": "success",
        "data": {"evaluation_id": evaluation.id, "idempotent": False},
    }


@router.post("/internal/tasks/{task_id}/failure", dependencies=[WorkerAuthorized])
def submit_failure(
    task_id: str,
    body: TaskFailureRequest,
    db: DatabaseSession,
    x_task_claim_token: str | None = Header(default=None),
) -> dict[str, object]:
    task = db.get(ProcessingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _require_claim(task, x_task_claim_token)
    next_status = (
        "FAILED" if task.attempts >= min(settings.task_max_attempts, MAX_ATTEMPTS) else "QUEUED"
    )
    result = db.execute(
        update(ProcessingTask)
        .where(
            ProcessingTask.id == task_id,
            ProcessingTask.status == "PROCESSING",
            ProcessingTask.claim_token == x_task_claim_token,
            ProcessingTask.lease_expires_at > datetime.now(UTC),
        )
        .values(
            status=next_status,
            last_error=redact_text(body.reason),
            lease_expires_at=None,
            claim_token=None,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task lease has expired or was replaced")
    db.commit()
    return {
        "code": 0,
        "message": "success",
        "data": {"status": next_status, "attempts": task.attempts},
    }
