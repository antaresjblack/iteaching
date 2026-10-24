from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DatabaseSession, require_role
from app.models import AccountBase, Course, Teacher
from app.schemas.business import (
    COURSE_TIME_PATTERN,
    CourseCreate,
    CourseRead,
    CourseStatus,
    CourseUpdate,
    Role,
)

router = APIRouter()


def can_access_course(user: AccountBase, course: Course) -> bool:
    """管理员与督导均可访问课程；督导与课程的多对多关系经录音关联表达。"""
    if user.role in (Role.ADMIN.value, Role.SUPERVISOR.value):
        return True
    return user.role == Role.TEACHER.value and course.teacher_id == user.id


def get_accessible_course(db: DatabaseSession, user: AccountBase, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if not can_access_course(user, course):
        raise HTTPException(status_code=403, detail="Course access denied")
    return course


def _resolve_teacher(db: DatabaseSession, teacher_id: int) -> Teacher:
    teacher = db.get(Teacher, teacher_id)
    if teacher is None or not teacher.is_active:
        raise HTTPException(status_code=422, detail="teacher_id must refer to an active teacher")
    return teacher


def _ensure_code_available(db: DatabaseSession, code: str, exclude_id: int | None = None) -> None:
    query = select(Course.id).where(Course.code == code)
    if exclude_id is not None:
        query = query.where(Course.id != exclude_id)
    if db.scalar(query) is not None:
        raise HTTPException(status_code=409, detail="Course code already exists")


def _commit_course(db: DatabaseSession, course: Course) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Course code already exists") from exc
    db.refresh(course)


def _schedule_matches(
    schedules: list[dict[str, object]], weekday: int | None, time: str | None
) -> bool:
    """时间筛选：任一时间段命中即可（按星期与/或起止区间判断）。"""
    if weekday is None and time is None:
        return True
    for item in schedules:
        if weekday is not None and item.get("weekday") != weekday:
            continue
        if time is not None and not (
            str(item.get("start_time")) <= time <= str(item.get("end_time"))
        ):
            continue
        return True
    return False


@router.post("/courses", status_code=status.HTTP_201_CREATED)
def create_course(body: CourseCreate, user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    require_role(user, Role.ADMIN.value, Role.SUPERVISOR.value)
    code = body.code.strip()
    _ensure_code_available(db, code)
    # 关联到教师账号时以账号姓名为准生成快照；否则保留录入姓名（未匹配状态）
    teacher_id = body.teacher_id
    teacher_name = body.teacher_name.strip()
    if teacher_id is not None:
        teacher_name = _resolve_teacher(db, teacher_id).name
    course = Course(
        code=code,
        name=body.name.strip(),
        location=body.location.value,
        class_name=body.class_name.strip(),
        schedules=[item.model_dump() for item in body.schedules],
        assessment_form=body.assessment_form.value,
        description=body.description.strip() if body.description else None,
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        status=body.status.value,
    )
    db.add(course)
    _commit_course(db, course)
    return {"code": 0, "message": "success", "data": CourseRead.model_validate(course)}


@router.get("/courses")
def list_courses(
    user: CurrentUser,
    db: DatabaseSession,
    location: Annotated[str | None, Query(max_length=200)] = None,
    course_status: Annotated[CourseStatus | None, Query(alias="status")] = None,
    teacher_id: Annotated[int | None, Query(gt=0)] = None,
    teacher_name: Annotated[str | None, Query(max_length=80)] = None,
    name: Annotated[str | None, Query(max_length=200)] = None,
    weekday: Annotated[int | None, Query(ge=1, le=7)] = None,
    time: Annotated[str | None, Query(pattern=COURSE_TIME_PATTERN)] = None,
) -> dict[str, object]:
    query = select(Course).order_by(Course.id)
    if user.role == Role.TEACHER.value:
        query = query.where(Course.teacher_id == user.id)
    courses = db.scalars(query).all()

    keyword = (location or "").strip().lower()
    keyword_teacher = (teacher_name or "").strip().lower()
    keyword_name = (name or "").strip().lower()
    items = [
        course
        for course in courses
        if (not keyword or keyword in course.location.lower())
        and (not keyword_teacher or keyword_teacher in course.teacher_name.lower())
        and (not keyword_name or keyword_name in course.name.lower())
        and (course_status is None or course.status == course_status.value)
        and (teacher_id is None or course.teacher_id == teacher_id)
        and _schedule_matches(course.schedules, weekday, time)
    ]
    return {
        "code": 0,
        "message": "success",
        "data": [CourseRead.model_validate(item) for item in items],
    }


@router.get("/courses/{course_id}")
def read_course(course_id: int, user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    course = get_accessible_course(db, user, course_id)
    return {"code": 0, "message": "success", "data": CourseRead.model_validate(course)}


@router.patch("/courses/{course_id}")
def update_course(
    course_id: int, body: CourseUpdate, user: CurrentUser, db: DatabaseSession
) -> dict[str, object]:
    require_role(user, Role.ADMIN.value)
    course = get_accessible_course(db, user, course_id)
    data = body.model_dump(exclude_unset=True)

    if data.get("code") is not None:
        code = str(data["code"]).strip()
        _ensure_code_available(db, code, exclude_id=course.id)
        course.code = code
    for field in ("name", "class_name"):
        if data.get(field) is not None:
            setattr(course, field, str(data[field]).strip())
    if data.get("location") is not None:
        course.location = body.location.value  # type: ignore[union-attr]
    if data.get("schedules") is not None:
        course.schedules = list(data["schedules"])
    if data.get("assessment_form") is not None:
        course.assessment_form = str(data["assessment_form"])
    if data.get("status") is not None:
        course.status = str(data["status"])
    if "description" in data:
        description = body.description
        course.description = description.strip() if description else None

    if "teacher_id" in data:
        if body.teacher_id is None:
            raise HTTPException(status_code=422, detail="教师必须匹配系统已有账号，不能解除关联")
        course.teacher_id = body.teacher_id
        course.teacher_name = _resolve_teacher(db, body.teacher_id).name
    elif "teacher_name" in data:
        # 只改姓名不同时改 teacher_id 会导致姓名快照与账号不一致，禁止这种情况
        raise HTTPException(
            status_code=422,
            detail="teacher_name 不能单独修改，请同步提交 teacher_id",
        )

    _commit_course(db, course)
    return {"code": 0, "message": "success", "data": CourseRead.model_validate(course)}
