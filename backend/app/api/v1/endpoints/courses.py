from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DatabaseSession, require_role
from app.models import Course, User
from app.schemas.business import CourseCreate, CourseRead, Role

router = APIRouter()


def can_access_course(user: User, course: Course) -> bool:
    return (
        user.role == Role.ADMIN.value
        or (user.role == Role.SUPERVISOR.value and course.supervisor_id == user.id)
        or (user.role == Role.TEACHER.value and course.teacher_id == user.id)
    )


def get_accessible_course(db: DatabaseSession, user: User, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if not can_access_course(user, course):
        raise HTTPException(status_code=403, detail="Course access denied")
    return course


@router.post("/courses", status_code=status.HTTP_201_CREATED)
def create_course(body: CourseCreate, user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    require_role(user, Role.ADMIN.value, Role.SUPERVISOR.value)
    teacher = db.get(User, body.teacher_id)
    if teacher is None or teacher.role != Role.TEACHER.value or not teacher.is_active:
        raise HTTPException(status_code=422, detail="teacher_id must refer to an active teacher")
    supervisor_id = user.id if user.role == Role.SUPERVISOR.value else body.supervisor_id
    if supervisor_id is None:
        raise HTTPException(status_code=422, detail="supervisor_id is required for administrators")
    supervisor = db.get(User, supervisor_id)
    if supervisor is None or supervisor.role != Role.SUPERVISOR.value or not supervisor.is_active:
        raise HTTPException(
            status_code=422, detail="supervisor_id must refer to an active supervisor"
        )
    if user.role == Role.SUPERVISOR.value and supervisor_id != user.id:
        raise HTTPException(status_code=403, detail="Supervisors can only assign themselves")
    course = Course(name=body.name, supervisor_id=supervisor_id, teacher_id=teacher.id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return {"code": 0, "message": "success", "data": CourseRead.model_validate(course)}


@router.get("/courses")
def list_courses(user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    query = select(Course).order_by(Course.id)
    if user.role == Role.SUPERVISOR.value:
        query = query.where(Course.supervisor_id == user.id)
    elif user.role == Role.TEACHER.value:
        query = query.where(Course.teacher_id == user.id)
    courses = db.scalars(query).all()
    return {
        "code": 0,
        "message": "success",
        "data": [CourseRead.model_validate(item) for item in courses],
    }


@router.get("/courses/{course_id}")
def read_course(course_id: int, user: CurrentUser, db: DatabaseSession) -> dict[str, object]:
    course = get_accessible_course(db, user, course_id)
    return {"code": 0, "message": "success", "data": CourseRead.model_validate(course)}
