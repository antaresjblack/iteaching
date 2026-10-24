from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DatabaseSession
from app.api.v1.endpoints.courses import get_accessible_course
from app.core.config import settings
from app.models import AccountBase, Admin, ProcessingTask, Recording, Supervisor, Teacher
from app.schemas.business import RecordingRead, Role
from app.services.recordings import probe_audio, redact_text
from app.services.storage import ensure_private_directory, open_private_file

router = APIRouter()
MAX_CHUNK_BYTES = 1024 * 1024
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a"}

# 上传者角色 → 账号表，用于回填姓名
UPLOADER_MODELS: dict[str, type[AccountBase]] = {
    Role.ADMIN.value: Admin,
    Role.SUPERVISOR.value: Supervisor,
    Role.TEACHER.value: Teacher,
}


def uploader_name(db: DatabaseSession, recording: Recording) -> str | None:
    """按 recording.uploaded_by_role 到对应账号表取姓名，取不到时退回用户名。"""
    model = UPLOADER_MODELS.get(recording.uploaded_by_role)
    if model is None:
        return None
    account = db.get(model, recording.uploaded_by_id)
    if account is None:
        return None
    return getattr(account, "name", None) or account.username


def task_status(task: ProcessingTask | None) -> str:
    """列表项状态：无任务视为已完成（兼容历史数据）。"""
    return task.status if task is not None else "SUCCEEDED"


def task_error(task: ProcessingTask | None) -> str | None:
    """仅失败任务返回脱敏后的错误原因。"""
    if task is None or task.status != "FAILED":
        return None
    return redact_text(task.last_error or "")


def recording_visible(user: AccountBase, recording: Recording) -> bool:
    """录音可见性：
    - 管理员：全部；
    - 督导：仅自己上传的录音（教师上传的不可见）；
    - 教师：本课程全部录音（自己 + 督导），跨课程访问由 get_accessible_course 拦截。
    """
    if user.role == Role.ADMIN.value:
        return True
    if user.role == Role.SUPERVISOR.value:
        return (
            recording.uploaded_by_role == Role.SUPERVISOR.value
            and recording.uploaded_by_id == user.id
        )
    if user.role == Role.TEACHER.value:
        return True
    return False


def get_accessible_recording(
    db: DatabaseSession, user: AccountBase, recording_id: str
) -> Recording:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    get_accessible_course(db, user, recording.course_id)
    if not recording_visible(user, recording):
        raise HTTPException(status_code=403, detail="Recording not visible to current account")
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
    description: Annotated[str | None, Form()] = None,
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
            uploaded_by_role=user.role,
            storage_path=str(final_path.resolve()),
            original_filename=original_name[:255],
            media_type=file.content_type or "application/octet-stream",
            description=(description or "").strip()[:500] or None,
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


@router.get("/courses/{course_id}/recordings")
def list_course_recordings(
    course_id: int, user: CurrentUser, db: DatabaseSession
) -> dict[str, object]:
    """课程音频列表：含上传者角色与姓名，供督导区分教师音频（只读）与听课音频。"""
    get_accessible_course(db, user, course_id)
    recordings = db.scalars(
        select(Recording)
        .where(Recording.course_id == course_id)
        .order_by(Recording.recorded_at.desc(), Recording.created_at.desc())
    ).all()
    recordings = [item for item in recordings if recording_visible(user, item)]
    # 一次性取出这些录音的处理任务，避免逐条查询
    tasks: dict[str, ProcessingTask] = {}
    if recordings:
        tasks = {
            task.recording_id: task
            for task in db.scalars(
                select(ProcessingTask).where(
                    ProcessingTask.recording_id.in_([item.id for item in recordings])
                )
            ).all()
        }
    return {
        "code": 0,
        "message": "success",
        "data": [
            RecordingRead(
                id=item.id,
                course_id=item.course_id,
                uploaded_by_id=item.uploaded_by_id,
                uploaded_by_role=item.uploaded_by_role,
                uploader_name=uploader_name(db, item),
                original_filename=item.original_filename,
                media_type=item.media_type,
                recorded_at=item.recorded_at,
                duration_seconds=item.duration_seconds,
                description=item.description,
                created_at=item.created_at,
                status=task_status(tasks.get(item.id)),
                error=task_error(tasks.get(item.id)),
            )
            for item in recordings
        ],
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
    # 教师上传的音频督导只读；仅上传者本人与管理员可删除。
    # 三张账号表独立自增，id 可能相同，必须同时比对角色才能确认归属。
    is_uploader = recording.uploaded_by_role == user.role and recording.uploaded_by_id == user.id
    if user.role != Role.ADMIN.value and not is_uploader:
        raise HTTPException(status_code=403, detail="Only the uploader can delete this recording")
    path = Path(recording.storage_path)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Audio file could not be removed") from exc
    db.delete(recording)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
