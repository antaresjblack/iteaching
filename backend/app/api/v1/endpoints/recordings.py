from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.api.deps import CurrentUser, DatabaseSession
from app.api.v1.endpoints.courses import get_accessible_course
from app.core.config import settings
from app.models import ProcessingTask, Recording, User
from app.services.recordings import probe_audio, redact_text
from app.services.storage import ensure_private_directory, open_private_file

router = APIRouter()
MAX_CHUNK_BYTES = 1024 * 1024
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a"}


def get_accessible_recording(db: DatabaseSession, user: User, recording_id: str) -> Recording:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    get_accessible_course(db, user, recording.course_id)
    return recording


@router.post("/courses/{course_id}/recordings", status_code=status.HTTP_201_CREATED)
async def upload_recording(
    course_id: int,
    user: CurrentUser,
    db: DatabaseSession,
    file: Annotated[UploadFile, File()],
    recorded_at: Annotated[datetime, Form()],
    consent_confirmed: Annotated[bool, Form()],
    consent_version: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    get_accessible_course(db, user, course_id)
    if not consent_confirmed:
        raise HTTPException(status_code=422, detail="Privacy consent must be confirmed")
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="recorded_at must include a timezone")
    original_name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only WAV, MP3 and M4A files are supported")

    recording_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    directory = settings.upload_dir / recording_id[:2]
    ensure_private_directory(settings.upload_dir)
    ensure_private_directory(directory)
    temporary_path = directory / f"{recording_id}.upload"
    final_path = directory / f"{recording_id}{extension}"
    total_bytes = 0
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    try:
        with open_private_file(temporary_path) as destination:
            while chunk := await file.read(MAX_CHUNK_BYTES):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=413, detail="Audio file exceeds configured size limit"
                    )
                destination.write(chunk)
        duration = probe_audio(temporary_path, extension)
        os.replace(temporary_path, final_path)
        recording = Recording(
            id=recording_id,
            course_id=course_id,
            uploaded_by_id=user.id,
            storage_path=str(final_path.resolve()),
            original_filename=original_name[:255],
            media_type=file.content_type or "application/octet-stream",
            recorded_at=recorded_at,
            consent_at=datetime.now(UTC),
            consent_version=(consent_version or settings.consent_version)[:40],
            duration_seconds=duration,
        )
        db.add_all(
            [
                recording,
                ProcessingTask(id=task_id, recording_id=recording_id, status="QUEUED", attempts=0),
            ]
        )
        db.commit()
    except Exception:
        db.rollback()
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return {
        "code": 0,
        "message": "success",
        "data": {"recording_id": recording_id, "task_id": task_id, "status": "QUEUED"},
    }


@router.get("/recordings/{recording_id}/status")
def recording_status(
    recording_id: str, user: CurrentUser, db: DatabaseSession
) -> dict[str, object]:
    recording = get_accessible_recording(db, user, recording_id)
    task = (
        db.query(ProcessingTask).filter(ProcessingTask.recording_id == recording.id).one_or_none()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Processing task not found")
    return {
        "code": 0,
        "message": "success",
        "data": {
            "recording_id": recording.id,
            "task_id": task.id,
            "status": task.status,
            "attempts": task.attempts,
            "error": redact_text(task.last_error or "") if task.status == "FAILED" else None,
        },
    }


@router.get("/recordings/{recording_id}/audio")
def download_recording(recording_id: str, user: CurrentUser, db: DatabaseSession) -> FileResponse:
    recording = get_accessible_recording(db, user, recording_id)
    path = Path(recording.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")
    safe_name = Path(recording.original_filename).name.replace('"', "")
    return FileResponse(path, media_type=recording.media_type, filename=safe_name)


@router.delete("/recordings/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(recording_id: str, user: CurrentUser, db: DatabaseSession) -> Response:
    recording = get_accessible_recording(db, user, recording_id)
    path = Path(recording.storage_path)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Audio file could not be removed") from exc
    db.delete(recording)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
