"""督导课程成员接口：加入/退出课程，以及「我查过的课」聚合查询。"""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DatabaseSession, require_role
from app.api.v1.endpoints.courses import _schedule_matches, get_accessible_course
from app.models import Course, CourseSupervisor
from app.schemas.business import (
    COURSE_TIME_PATTERN,
    Role,
    SupervisedCourseRead,
)

router = APIRouter()


def _serialize_membership(membership: CourseSupervisor) -> dict[str, object]:
    return {
        "id": membership.id,
        "course_id": membership.course_id,
        "supervisor_id": membership.supervisor_id,
        "created_at": membership.created_at,
    }


@router.post("/courses/{course_id}/join", status_code=status.HTTP_201_CREATED)
def join_course(
    course_id: int,
    user: CurrentUser,
    db: DatabaseSession,
    response: Response,
) -> dict[str, object]:
    """督导主动加入某门课程；重复加入返回已有关联（幂等）。"""
    require_role(user, Role.SUPERVISOR.value)
    get_accessible_course(db, user, course_id)
    existing = db.scalar(
        select(CourseSupervisor).where(
            CourseSupervisor.course_id == course_id,
            CourseSupervisor.supervisor_id == user.id,
        )
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return {"code": 0, "message": "already joined", "data": _serialize_membership(existing)}

    membership = CourseSupervisor(course_id=course_id, supervisor_id=user.id)
    db.add(membership)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(CourseSupervisor).where(
                CourseSupervisor.course_id == course_id,
                CourseSupervisor.supervisor_id == user.id,
            )
        )
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return {"code": 0, "message": "already joined", "data": _serialize_membership(existing)}
    db.refresh(membership)
    return {"code": 0, "message": "success", "data": _serialize_membership(membership)}


@router.delete("/courses/{course_id}/join", status_code=status.HTTP_204_NO_CONTENT)
def leave_course(course_id: int, user: CurrentUser, db: DatabaseSession) -> Response:
    """督导退出已加入的课程。"""
    require_role(user, Role.SUPERVISOR.value)
    membership = db.scalar(
        select(CourseSupervisor).where(
            CourseSupervisor.course_id == course_id,
            CourseSupervisor.supervisor_id == user.id,
        )
    )
    if membership is not None:
        db.delete(membership)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    """我查过的课：督导主动加入的课程，按加入时间倒序展示。

    四条件（教师名称、上课地点、时间、课程名称）支持组合查询。
    """
    require_role(user, Role.SUPERVISOR.value)
    rows = db.execute(
        select(CourseSupervisor.course_id, CourseSupervisor.created_at)
        .where(CourseSupervisor.supervisor_id == user.id)
        .order_by(CourseSupervisor.created_at.desc())
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
                joined_at=row.created_at,
            )
        )
    return {"code": 0, "message": "success", "data": items}
