from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Role(StrEnum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    TEACHER = "teacher"


class Department(StrEnum):
    """院系枚举：新增院系时在此追加即可，前后端下拉选项同步扩展。"""

    COMPUTER = "计算机学院"
    MATH = "数学学院"
    FOREIGN_LANGUAGE = "外国语学院"
    ECONOMICS_MANAGEMENT = "经济管理学院"
    MARXISM = "马克思主义学院"
    SPORTS = "体育学院"


class CourseStatus(StrEnum):
    """课程状态：未开始 / 进行中 / 已结束。"""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class AssessmentForm(StrEnum):
    """考察形式：当前仅百分制，后续可在此追加其他形式。"""

    PERCENT = "percent"


class TeachingLocation(StrEnum):
    """上课地址枚举：教学楼 + 3 位教室编号（如 文法227），新建课程只能从下列值中选择。

    五栋教学楼各设 101-105 五间教室；同时保留五栋教学楼的历史选项，
    仅用于兼容旧数据的读取与编辑，前端新建/编辑下拉不再展示。
    """

    # 历史选项：旧数据兼容，新建课程不再展示
    BUILDING_1 = "1号楼"
    BIOMEDICAL = "生医"
    HUMANITIES = "文法"
    ARCHITECTURE = "建筑"
    INFORMATION = "信息"

    # 1号楼教室
    BUILDING_1_101 = "1号楼101"
    BUILDING_1_102 = "1号楼102"
    BUILDING_1_103 = "1号楼103"
    BUILDING_1_104 = "1号楼104"
    BUILDING_1_105 = "1号楼105"

    # 生医教室
    BIOMEDICAL_101 = "生医101"
    BIOMEDICAL_102 = "生医102"
    BIOMEDICAL_103 = "生医103"
    BIOMEDICAL_104 = "生医104"
    BIOMEDICAL_105 = "生医105"

    # 文法教室
    HUMANITIES_101 = "文法101"
    HUMANITIES_102 = "文法102"
    HUMANITIES_103 = "文法103"
    HUMANITIES_104 = "文法104"
    HUMANITIES_105 = "文法105"

    # 建筑教室
    ARCHITECTURE_101 = "建筑101"
    ARCHITECTURE_102 = "建筑102"
    ARCHITECTURE_103 = "建筑103"
    ARCHITECTURE_104 = "建筑104"
    ARCHITECTURE_105 = "建筑105"

    # 信息教室
    INFORMATION_101 = "信息101"
    INFORMATION_102 = "信息102"
    INFORMATION_103 = "信息103"
    INFORMATION_104 = "信息104"
    INFORMATION_105 = "信息105"


class Dimension(StrEnum):
    BRIDGE_IN = "bridge_in"
    OBJECTIVES = "objectives"
    PRE_ASSESSMENT = "pre_assessment"
    PARTICIPATORY_LEARNING = "participatory_learning"
    POST_ASSESSMENT = "post_assessment"
    SUMMARY = "summary"


DIMENSION_KEYS = tuple(item.value for item in Dimension)
Score = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class UserCreate(BaseModel):
    username: Annotated[str, Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")]
    password: Annotated[str, Field(min_length=12, max_length=128)]
    role: Role
    # 角色专属字段：admin 忽略；teacher/supervisor 必填 name、department
    # employee_no 由系统按角色自动生成，不接受手动指定
    department: Department | None = None
    phone: Annotated[str | None, Field(max_length=40)] = None
    name: Annotated[str | None, Field(min_length=1, max_length=80)] = None
    level: Literal["校级", "院级"] | None = None

    @model_validator(mode="after")
    def validate_role_fields(self) -> UserCreate:
        if self.role in (Role.SUPERVISOR, Role.TEACHER):
            if not (self.name and self.department):
                raise ValueError("name and department are required for supervisor and teacher")
        if self.role == Role.SUPERVISOR and self.level is None:
            raise ValueError("level is required for supervisor")
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    is_active: bool
    employee_no: str | None = None
    department: str | None = None
    phone: str | None = None
    name: str | None = None
    level: str | None = None
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


COURSE_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
COURSE_CODE_PATTERN = r"^[A-Za-z0-9_-]+$"


class CourseSchedule(BaseModel):
    """单个授课时间段：weekday 1-7 对应周一至周日，时间为 HH:MM。

    按周批量录入时额外携带周次范围（如第 1-16 周），该范围内
    每次上课的星期与节次保持一致；缺省表示不限周次。
    """

    model_config = ConfigDict(extra="forbid")

    weekday: Annotated[int, Field(ge=1, le=7)]
    start_time: Annotated[str, Field(pattern=COURSE_TIME_PATTERN)]
    end_time: Annotated[str, Field(pattern=COURSE_TIME_PATTERN)]
    start_week: Annotated[int | None, Field(ge=1, le=52)] = None
    end_week: Annotated[int | None, Field(ge=1, le=52)] = None

    @model_validator(mode="after")
    def validate_time_range(self) -> CourseSchedule:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")
        # 周次必须成对出现，且结束周不早于起始周
        if (self.start_week is None) != (self.end_week is None):
            raise ValueError("start_week and end_week must be provided together")
        if (
            self.start_week is not None
            and self.end_week is not None
            and self.end_week < self.start_week
        ):
            raise ValueError("end_week must be greater than or equal to start_week")
        return self


class CourseCreate(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=40, pattern=COURSE_CODE_PATTERN)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    location: TeachingLocation
    class_name: Annotated[str, Field(min_length=1, max_length=200)]
    schedules: Annotated[list[CourseSchedule], Field(min_length=1, max_length=20)]
    assessment_form: AssessmentForm = AssessmentForm.PERCENT
    description: Annotated[str | None, Field(max_length=500)] = None
    # 教师必须匹配系统已有账号；teacher_name 由后端根据账号回填，创建时仍可传入作为兜底
    teacher_id: Annotated[int, Field(gt=0)]
    teacher_name: Annotated[str, Field(min_length=1, max_length=80)]
    status: CourseStatus = CourseStatus.NOT_STARTED


class CourseUpdate(BaseModel):
    """编辑课程：仅更新显式传入的字段；teacher_id 传 null 表示解除关联。"""

    code: Annotated[str | None, Field(min_length=1, max_length=40, pattern=COURSE_CODE_PATTERN)] = (
        None
    )
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    location: TeachingLocation | None = None
    class_name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    schedules: Annotated[list[CourseSchedule] | None, Field(min_length=1, max_length=20)] = None
    assessment_form: AssessmentForm | None = None
    description: Annotated[str | None, Field(max_length=500)] = None
    # 传 null 或不更新都表示保持原值；业务上将始终绑定有效教师
    teacher_id: Annotated[int | None, Field(gt=0)] = None
    teacher_name: Annotated[str | None, Field(min_length=1, max_length=80)] = None
    status: CourseStatus | None = None


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    location: str
    class_name: str
    schedules: list[CourseSchedule]
    assessment_form: AssessmentForm
    description: str | None = None
    teacher_id: int | None = None
    teacher_name: str
    status: CourseStatus
    created_at: datetime


class RecordingRead(BaseModel):
    """课程音频列表项：区分上传者角色，供督导只读查看教师音频。"""

    id: str
    course_id: int
    uploaded_by_id: int
    uploaded_by_role: Role
    uploader_name: str | None = None
    original_filename: str
    media_type: str
    recorded_at: datetime
    duration_seconds: float
    description: str | None = None
    created_at: datetime


class SupervisionLinkCreate(BaseModel):
    """督导把某段音频关联到课程（幂等：重复提交同一音频返回已有关联）。"""

    recording_id: Annotated[str, Field(min_length=1, max_length=36)]


class SupervisedCourseRead(CourseRead):
    """我查过的课：课程信息 + 最近一次关联时间。"""

    last_linked_at: datetime


class PasswordChange(BaseModel):
    """本人修改密码。"""

    old_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Annotated[str, Field(min_length=12, max_length=128)]


class PasswordReset(BaseModel):
    """管理员强制重置指定账号密码。"""

    new_password: Annotated[str, Field(min_length=12, max_length=128)]


class TaskClaimRequest(BaseModel):
    worker_id: Annotated[str, Field(min_length=1, max_length=120)] = "worker"


class TaskFailureRequest(BaseModel):
    retryable: bool = True
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class TranscriptSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    end_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    text: Annotated[str, Field(max_length=10000)]
    speaker_id: Annotated[str | None, Field(max_length=80)] = None
    role: Literal["teacher", "student", "unknown"] = "unknown"

    @model_validator(mode="after")
    def validate_time_range(self) -> TranscriptSegmentInput:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class SuggestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, Field(min_length=1, max_length=2000)]

    @model_validator(mode="before")
    @classmethod
    def accept_plain_text(cls, value: object) -> object:
        return {"text": value} if isinstance(value, str) else value


class IndicatorEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: Annotated[str, Field(min_length=1, max_length=80)]
    quote: Annotated[str, Field(min_length=1, max_length=10000)]


class IndicatorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Dimension
    status: Literal["evaluated", "insufficient_evidence"]
    score: Score | None
    reason: Annotated[str, Field(min_length=1, max_length=10000)]
    evidence: list[IndicatorEvidence] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_evidence(self) -> IndicatorResult:
        if self.status == "evaluated" and (self.score is None or not self.evidence):
            raise ValueError("evaluated indicator requires score and evidence")
        if self.status == "insufficient_evidence" and (self.score is not None or self.evidence):
            raise ValueError("insufficient evidence must not have a score or evidence")
        return self


class EvaluationResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1, 2]
    rubric_version: Annotated[str | None, Field(max_length=100)] = None
    indicators: list[IndicatorResult] = Field(default_factory=list, max_length=6)
    mode: Literal["basic", "boppps"]
    transcript: Annotated[str, Field(max_length=500000)]
    segments: list[TranscriptSegmentInput] = Field(default_factory=list, max_length=20000)
    overall_score: Score | None
    overall_evidence: Annotated[str, Field(min_length=1, max_length=20000)]
    problems: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=200
    )
    dimension_scores: dict[str, Score | None] = Field(default_factory=dict)
    suggestions: list[SuggestionInput] = Field(default_factory=list, max_length=50)

    @field_validator("dimension_scores")
    @classmethod
    def validate_dimension_names(cls, value: dict[str, float | None]) -> dict[str, float | None]:
        unknown = set(value) - set(DIMENSION_KEYS)
        if unknown:
            raise ValueError(f"unknown dimension(s): {', '.join(sorted(unknown))}")
        return value

    @model_validator(mode="after")
    def validate_mode_dimensions(self) -> EvaluationResultInput:
        if self.mode == "boppps" and set(self.dimension_scores) != set(DIMENSION_KEYS):
            raise ValueError("boppps results require scores for all six dimensions")
        if self.version == 1:
            if self.overall_score is None or any(
                score is None for score in self.dimension_scores.values()
            ):
                raise ValueError("version 1 requires numeric scores")
        else:
            if not self.rubric_version or not self.rubric_version.strip():
                raise ValueError("version 2 requires rubric_version")
            if len(self.indicators) != 6 or {i.id.value for i in self.indicators} != set(
                DIMENSION_KEYS
            ):
                raise ValueError("version 2 requires six unique indicators")
            expected = {i.id.value: i.score for i in self.indicators}
            if self.dimension_scores != expected:
                raise ValueError("dimension_scores must agree with indicators")
            # No fabricated overall score when some dimensions are unobserved.
            scores = list(expected.values())
            overall = round(sum(scores) / 6, 2) if all(s is not None for s in scores) else None
            if self.overall_score != overall:
                raise ValueError("overall score must be six-dimension mean or null")
            source = {f"s{n}": s.text for n, s in enumerate(self.segments, 1)}
            for indicator in self.indicators:
                for evidence in indicator.evidence:
                    if (
                        evidence.segment_id not in source
                        or evidence.quote not in source[evidence.segment_id]
                    ):
                        raise ValueError("indicator evidence must quote transcript segment")
        return self


class ReviewCreate(BaseModel):
    comment: Annotated[str, Field(min_length=1, max_length=10000)]


class CalibrationCreate(BaseModel):
    overall_score: Score | None = None
    dimension_scores: dict[str, Score] | None = None
    comment: Annotated[str | None, Field(max_length=10000)] = None

    @field_validator("dimension_scores")
    @classmethod
    def validate_calibration_dimensions(
        cls, value: dict[str, float] | None
    ) -> dict[str, float] | None:
        if value is not None and set(value) - set(DIMENSION_KEYS):
            raise ValueError("calibration contains unknown dimensions")
        return value

    @model_validator(mode="after")
    def require_calibration_value(self) -> CalibrationCreate:
        if self.overall_score is None and not self.dimension_scores and not self.comment:
            raise ValueError("at least one score or comment is required")
        return self
