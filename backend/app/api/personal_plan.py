"""Personal Planning API：**个人输入驱动**的规划入口（本轮新增，独立路由文件）。

```text
GET  /api/v1/personal-planning/curriculum-versions
POST /api/v1/personal-planning/plan
```

## 这个文件的位置

- 它是**独立模块**，只往 `app/main.py` 加**一行** `include_router`，
  ⛔ 不修改任何现有路由；
- ⛔ 不改 `POST /api/v1/plan` 的请求 / 响应契约，也⛔ 不改已冻结的 Case A runtime；
- ⛔ 不新增 / 不修改 `/schemas/*.schema.json`：
  本文件里的请求 / 响应模型都是**这个模块自己的 API 包络**，
  内部的公共对象仍复用 `app.models.contracts`
  （`Preference` / `CourseOffering` / `MakeupTask` / `PlanResult`）。

## 语义要点

- 每个请求的已修记录来源 id 由**服务端**从请求体内容摘要派生
  （`completed_source_id`），⛔ **不读学生行里的来源字段**；
- `MakeupTask[]` **只**来自**本学生**的 case，⛔ 不取自任何 case 文件；
- 需要排课时，只把**已装配的** production Course Data 与 Planner 接上，
  ⛔ 不在本模块里造教学班、⛔ 不回退到 Mock、⛔ 不伪造 `PlanResult`；
- 未在已核验目录中的版本、未核验方案、空 / 错误输入、待确认身份、未知等价
  —— 一律**明确拒绝或留待核验**，⛔ 不回退到固定 Case A。
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.curriculum.catalog import CatalogInspection, CurriculumCatalog
from app.curriculum.errors import CurriculumNormalizationError
from app.course_data import CourseDataStoreError
from app.models.contracts import CourseOffering, DataSource, MakeupTask, PlanResult
from app.personal import (
    PersonalPlanRequest,
    PersonalPlanResult,
    build_personal_plan,
    normalize_personal_plan_request,
)
from app.services.planning_runtime import (
    PlanningRuntimeInspection,
    inspect_planning_runtime,
)
from app.services.personal_runtime import (
    PersonalCatalogInspection,
    inspect_personal_catalog,
)

router = APIRouter(tags=["personal-planning"])

#: 本模块的**非公共**内容来源前缀：只用于标识"由请求体内容绑定"的已修来源。
_CONTENT_SOURCE_PREFIX = "personal-upload://sha256"

#: 未排课时给出的固定状态码（响应里与 `planning_skipped_reason` 一起返回）。
SKIPPED_NO_COURSE_DATA = "no_course_data"
SKIPPED_NO_SEMESTER = "no_semester"
SKIPPED_SEMESTER_NOT_BOUND = "semester_not_bound"


def _reject(code: str, message: str, *, http_status: int = 400) -> None:
    raise HTTPException(
        status_code=http_status,
        detail={"error": code, "message": message},
    )


def _catalog_dependency() -> PersonalCatalogInspection:
    """已核验版本目录的依赖；未配置时返回不可用结果，由路由翻译成明确错误码。"""

    return inspect_personal_catalog()


def _planning_runtime_dependency() -> PlanningRuntimeInspection:
    """已冻结的 production runtime 检查；未装配时也不报错，只是"没有排课能力"。"""

    return inspect_planning_runtime()


class CurriculumVersionMetadata(BaseModel):
    """一个**可选**培养方案版本的元信息（不含课程明细）。"""

    model_config = ConfigDict(extra="forbid")

    version_id: str
    major: str
    cohort: str
    campus: str | None
    track: str | None
    source_id: str
    verification_evidence: str
    verified_by: str | None
    complete: bool
    completeness_evidence: str | None
    total_credit: float | None
    practice_credit: float | None
    study_years: int | None
    course_count: int
    group_count: int


class RejectedVersion(BaseModel):
    """一个**不可选**的版本及固定原因码。"""

    model_config = ConfigDict(extra="forbid")

    version_id: str
    code: str
    detail: str


class CurriculumVersionListResponse(BaseModel):
    """可选版本清单 + 被拒条目 + 目录状态。"""

    model_config = ConfigDict(extra="forbid")

    catalog_ready: bool
    catalog_reason: str
    selectable_count: int
    versions: list[CurriculumVersionMetadata]
    rejected: list[RejectedVersion]


class StudentPreference(BaseModel):
    """公共 `Preference` 的请求侧镜像（⛔ 不新增字段，语义完全相同）。"""

    model_config = ConfigDict(extra="forbid")

    max_credit: float | None = None
    avoid_cross_campus: bool = False
    preferred_courses: list[str] = Field(default_factory=list)
    avoid_times: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class PersonalPlanBody(BaseModel):
    """一次个人规划请求体（⛔ 只含下面这些键，未知键直接拒绝）。"""

    model_config = ConfigDict(extra="forbid")

    old_version_id: str = Field(min_length=1)
    target_version_id: str = Field(min_length=1)
    semester: str | None = None
    student: dict[str, Any] = Field(default_factory=dict)
    preference: StudentPreference | None = None
    current_schedule: list[CourseOffering] = Field(default_factory=list)

    @field_validator("old_version_id", "target_version_id")
    @classmethod
    def version_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("培养方案版本 id 必须是非空字符串")
        return value

    @field_validator("semester")
    @classmethod
    def semester_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("semester 必须是非空字符串或省略")
        return value


class PersonalPlanResponse(BaseModel):
    """个人规划结果：**事实与规划分开**，并明确报告跳过了什么、为什么。"""

    model_config = ConfigDict(extra="forbid")

    old_version: CurriculumVersionMetadata
    target_version: CurriculumVersionMetadata
    data_source: str
    completed_source_id: str
    completed_record_count: int
    input_summary: dict[str, int]
    makeup_tasks: list[MakeupTask]
    status_counts: dict[str, int]
    planning: PlanResult | None
    planning_skipped_reason: str | None
    planning_skipped_code: str | None
    assuming_course_ids: list[str]
    notes: list[str]


def _as_metadata(payload: dict) -> CurriculumVersionMetadata:
    return CurriculumVersionMetadata(**payload)


def _completed_source_id(body: PersonalPlanBody) -> str:
    """由**请求体内容**派生已修来源 id；⛔ 不读学生行里的任何来源字段。"""

    canonical = json.dumps(
        {
            "student": body.student,
            "preference": None if body.preference is None else body.preference.model_dump(),
            "current_schedule": [item.model_dump(mode="json") for item in body.current_schedule],
            "old_version_id": body.old_version_id,
            "target_version_id": body.target_version_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{_CONTENT_SOURCE_PREFIX}:{hashlib.sha256(canonical).hexdigest()}"


def _status_counts(tasks: list[MakeupTask]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task.status.value] = counts.get(task.status.value, 0) + 1
    return counts


def _build_response(result: PersonalPlanResult) -> PersonalPlanResponse:
    tasks = list(result.makeup_tasks)
    code = None
    if result.planning_skipped_reason is not None:
        code = (
            SKIPPED_NO_COURSE_DATA
            if result.planning_skipped_reason.startswith(SKIPPED_NO_COURSE_DATA)
            else SKIPPED_NO_SEMESTER
            if result.planning_skipped_reason.startswith(SKIPPED_NO_SEMESTER)
            else SKIPPED_SEMESTER_NOT_BOUND
        )
    return PersonalPlanResponse(
        old_version=_as_metadata(result.old_version),
        target_version=_as_metadata(result.target_version),
        data_source=result.data_source.value,
        completed_source_id=result.completed_source_id,
        completed_record_count=result.completed_record_count,
        input_summary={
            "completed_record_count": result.completed_record_count,
            "makeup_task_count": len(tasks),
        },
        makeup_tasks=tasks,
        status_counts=_status_counts(tasks),
        planning=result.planning,
        planning_skipped_reason=result.planning_skipped_reason,
        planning_skipped_code=code,
        assuming_course_ids=list(result.assuming_course_ids),
        notes=list(result.notes),
    )


def _require_catalog(
    inspection: Annotated[PersonalCatalogInspection, Depends(_catalog_dependency)],
) -> CurriculumCatalog:
    """未配置 / 不可用的目录 → 明确 503，⛔ 不回退任何默认版本。"""

    if inspection.catalog is None:
        _reject(
            "personal_catalog_not_configured",
            "当前没有已核验的培养方案版本目录（未配置或不可用）；"
            "因此个人规划入口没有可选版本，也不会回退到固定 Case A。",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return inspection.catalog


def _declared_data_source(payload: dict[str, Any]) -> DataSource:
    """数据来源标记：只接受显式声明；缺省即 `mock`（⛔ 不自动升级成 real）。"""

    declared = payload.get("data_source")
    if declared is None:
        return DataSource.MOCK
    try:
        return DataSource(declared)
    except (TypeError, ValueError):
        _reject(
            "personal_plan_input_invalid",
            "data_source 只允许 mock 或 real；缺省为 mock。",
            http_status=422,
        )


def _student_payload(body: PersonalPlanBody) -> dict[str, Any]:
    """把请求体组装成本学生输入；⛔ 两个位置只能各出现一次。"""

    student: dict[str, Any] = dict(body.student)
    if body.preference is not None:
        if "preference" in student:
            _reject(
                "personal_plan_input_conflict",
                "preference 只能出现在请求体的一个位置，不能同时给出两份。",
            )
        student["preference"] = body.preference.model_dump()
    if body.current_schedule:
        if "current_schedule" in student:
            _reject(
                "personal_plan_input_conflict",
                "current_schedule 只能出现在请求体的一个位置，不能同时给出两份。",
            )
        student["current_schedule"] = list(body.current_schedule)
    return student


def _planning_status(
    runtime: PlanningRuntimeInspection, semester: str | None
) -> tuple[str | None, str | None]:
    """决定这次能不能排课，并给出**固定状态码 + 可读原因**。

    ⛔ 不在本模块里造教学班、⛔ 不读 Mock、⛔ 不回退：
    只有 production runtime 已装配且学期与其绑定一致时才调用 Planner。
    """

    if runtime.orchestrator is None:
        return (
            SKIPPED_NO_COURSE_DATA,
            "no_course_data: 当前没有已装配的真实教学班供给（production runtime 未就绪），"
            "因此没有调用 Planner；补修任务仍然有效，但⛔ 不代表任何可执行课表。",
        )
    if semester is None:
        return (
            SKIPPED_NO_SEMESTER,
            "no_semester: 本次未指定要把结果排进哪个学期，因此没有调用 Planner。",
        )
    return None, None


@router.get(
    "/personal-planning/curriculum-versions",
    response_model=CurriculumVersionListResponse,
    summary="列出可选的已核验培养方案版本",
    description=(
        "只列出已核验、来源声明支持且规则可表达的版本；"
        "未核验、来源声明不支持或形状非法的条目进入 `rejected`（带固定原因码）。"
        "未配置目录时返回 503，不猜任何默认版本。"
    ),
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "当前没有已核验的培养方案版本目录",
        }
    },
)
def list_curriculum_versions(
    inspection: Annotated[PersonalCatalogInspection, Depends(_catalog_dependency)],
) -> CurriculumVersionListResponse:
    """列出可选版本；目录不可用时明确 503。"""

    catalog = _require_catalog(inspection)
    result: CatalogInspection = catalog.inspection
    return CurriculumVersionListResponse(
        catalog_ready=True,
        catalog_reason=inspection.reason,
        selectable_count=len(result.entries),
        versions=[_as_metadata(item) for item in result.selectable],
        rejected=[
            RejectedVersion(version_id=item.version_id, code=item.code, detail=item.detail)
            for item in result.rejections
        ],
    )


@router.post(
    "/personal-planning/plan",
    response_model=PersonalPlanResponse,
    summary="按个人输入独立计算补修任务（可选接入已装配的 Planner）",
    description=(
        "接受所选源 / 目标培养方案版本 id 与学生本人输入，独立组装本学生的 case 并复用"
        "既有 Curriculum → MakeupTask[] 路线。真实教学班供给未装配时不调用 Planner，"
        "并在响应里明确说明原因。不可选版本 / 未核验方案 / 不完整输入一律明确拒绝。"
    ),
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "当前没有已核验的培养方案版本目录",
        }
    },
)
def create_personal_plan(
    body: PersonalPlanBody,
    catalog: Annotated[CurriculumCatalog, Depends(_require_catalog)],
    runtime: Annotated[PlanningRuntimeInspection, Depends(_planning_runtime_dependency)],
) -> PersonalPlanResponse:
    """校验 → 独立组装 → 计算；任何失败都明确拒绝，⛔ 不回退到演示数据。"""

    student = _student_payload(body)
    semester = None if body.semester is None else body.semester.strip()
    try:
        request: PersonalPlanRequest = normalize_personal_plan_request(
            {
                "old_version_id": body.old_version_id.strip(),
                "target_version_id": body.target_version_id.strip(),
                "semester": semester,
                "student": student,
            },
            catalog=catalog,
            data_source=_declared_data_source(student),
            completed_source_id=_completed_source_id(body),
        )
    except CurriculumNormalizationError as exc:
        _reject("personal_plan_input_invalid", str(exc), http_status=422)

    skipped_code, skipped_reason = _planning_status(runtime, request.semester)

    planner = None
    offerings = None
    if skipped_code is None:
        orchestrator = runtime.orchestrator
        try:
            # 只取**已装配的** production 教学班供给；MakeupTask[] 仍来自本学生 case。
            offerings = orchestrator.course_data.get_course_offerings(request.semester)
        except CourseDataStoreError:
            # 就绪性失败（acceptance 失效 / 计数不符）：翻译成同一个 503 readiness 契约，
            # ⛔ 不返回 500、⛔ 不回退到 Mock、⛔ 不假装"供给为空"。
            _reject(
                "personal_plan_course_data_unavailable",
                "真实教学班供给当前不可用（acceptance 已失效或不再匹配）；"
                "本次不返回任何规划结果，也不回退到 Mock。",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        planner = orchestrator.planner

    try:
        result = build_personal_plan(
            catalog, request, planner=planner, offerings=offerings,
        )
    except CurriculumNormalizationError as exc:
        _reject("personal_plan_not_projectable", str(exc), http_status=422)

    if skipped_reason is not None and result.planning is None:
        # 由本路由决定的跳过原因优先于通用装配原因，保证前端能区分"没供给"与"没学期"。
        from dataclasses import replace

        result = replace(result, planning_skipped_reason=skipped_reason)

    return _build_response(result)
