"""督导听课关联接口：课程—督导—音频三要素的建立与「我查过的课」聚合查询。"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DatabaseSession, require_role
from app.api.v1.endpoints.courses import _schedule_matches, get_accessible_course
from app.models import Course, Recording, SupervisionLink
from app.schemas.business import (
    COURSE_TIME_PATTERN,
    Role,
    SupervisedCourseRead,
    SupervisionLinkCreate,
)

router = APIRouter()


def _serialize_link(link: SupervisionLink) -> dict[str, object]:
    return {
        "id": link.id,
        "course_id": link.course_id,
        "supervisor_id": link.supervisor_id,
        "recording_id": link.recording_id,
        "created_at": link.created_at,
    }


@router.post("/courses/{course_id}/supervision-links", status_code=status.HTTP_201_CREATED)
def create_supervision_link(
    course_id: int,
    body: SupervisionLinkCreate,
    user: CurrentUser,
    db: DatabaseSession,
    response: Response,
) -> dict[str, object]:
    """督导上传音频成功后将音频与课程关联。

    幂等：同一督导重复关联同一音频返回已有关联记录（HTTP 200）。
    同一督导对同一课程多次听课可产生多条关联。
    """
    require_role(user, Role.SUPERVISOR.value)
    get_accessible_course(db, user, course_id)
    recording = db.get(Recording, body.recording_id)
    if recording is None or recording.course_id != course_id:
        raise HTTPException(status_code=404, detail="Recording not found in this course")

    existing = db.scalar(
        select(SupervisionLink).where(
            SupervisionLink.supervisor_id == user.id,
            SupervisionLink.recording_id == recording.id,
        )
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return {"code": 0, "message": "already linked", "data": _serialize_link(existing)}

    link = SupervisionLink(course_id=course_id, supervisor_id=user.id, recording_id=recording.id)
    db.add(link)
    try:
        db.commit()
    except IntegrityError:
        # 并发重复提交：唯一约束兜底，回退后读取已有关联
        db.rollback()
        existing = db.scalar(
            select(SupervisionLink).where(
                SupervisionLink.supervisor_id == user.id,
                SupervisionLink.recording_id == recording.id,
            )
        )
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return {"code": 0, "message": "already linked", "data": _serialize_link(existing)}
    db.refresh(link)
    return {"code": 0, "message": "success", "data": _serialize_link(link)}


@router.get("/supervisions/my-courses")
def list_my_supervised_courses(
    user: CurrentUser,
    db: DatabaseSession,
    teacher_name: Annotated[str | None, Query(max_length=80)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
    weekday: Annotated[int | None, Query(ge=1, le=7)] = None,
    time: Annotated[str | None, Query(pattern=COURSE_TIME_PATTERN)] = None,
    name: Annotated[str | None, Query(max_length=200)] = None,
) -> dict[str, object]:
    """我查过的课：按课程去重，展示最近一次关联时间。

    四条件（教师名称、上课地点、时间、课程名称）支持组合查询。
    """
    require_role(user, Role.SUPERVISOR.value)
    last_linked = func.max(SupervisionLink.created_at).label("last_linked_at")
    rows = db.execute(
        select(SupervisionLink.course_id, last_linked)
        .where(SupervisionLink.supervisor_id == user.id)
        .group_by(SupervisionLink.course_id)
        .order_by(last_linked.desc())
    ).all()
    course_ids = [row.course_id for row in rows]
    loaded = {
        item.id: item for item in db.scalars(select(Course).where(Course.id.in_(course_ids))).all()
    }
    keyword_teacher = (teacher_name or "").strip().lower()
    keyword_location = (location or "").strip().lower()
    keyword_name = (name or "").strip().lower()
    items: list[SupervisedCourseRead] = []
    for row in rows:
        course = loaded.get(row.course_id)
        if course is None:
            continue
        if keyword_teacher and keyword_teacher not in course.teacher_name.lower():
            continue
        if keyword_location and keyword_location not in course.location.lower():
            continue
        if keyword_name and keyword_name not in course.name.lower():
            continue
        if not _schedule_matches(course.schedules, weekday, time):
            continue
        items.append(
            SupervisedCourseRead(
                id=course.id,
                code=course.code,
                name=course.name,
                location=course.location,
                class_name=course.class_name,
                schedules=course.schedules,
                assessment_form=course.assessment_form,
                description=course.description,
                teacher_id=course.teacher_id,
                teacher_name=course.teacher_name,
                status=course.status,
                created_at=course.created_at,
                last_linked_at=row.last_linked_at,
            )
        )
    return {"code": 0, "message": "success", "data": items}
