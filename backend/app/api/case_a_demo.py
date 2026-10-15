"""Private Case A closed-loop demo endpoints; separate from production /plan."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.course_data import CaseAScopeError
from app.models.contracts import CourseOffering, MakeupTask, PlanResult, Preference
from app.curriculum.matching import group_credit_progress
from app.services.case_a_demo import (
    CASE_A_DEMO_SCOPE_LABEL,
    CaseADemoInputError,
    CaseADemoRuntime,
    get_case_a_demo_runtime,
)
from app.services.completed_courses_ingest import CompletedCoursesImportRejected, MAX_UPLOAD_BYTES

router = APIRouter(prefix="/case-a-demo", tags=["case-a-demo"])


class CaseADemoPlanRequest(BaseModel):
    """Case A 规划请求。

    ⚠️ 成绩单输入**二选一**（Phase 5 授权扩展）：

    ```text
    transcript_pdf_base64        成绩单 PDF 原始字节（主路径，行为不变）
    confirmed_completed_courses  **用户已确认**的图片识别课程记录
    ```

    - 二者**恰好提供一个**，否则 422；
    - `confirmed_completed_courses` 只接受 `completed.records` 形状；
      ⛔ OCR 原始候选（含 `row_id` / `confidence` / `unconfirmed`）会被
      `extra="forbid"` + 归一化层拒绝 ⇒ **未确认 / 原始识别结果进不来**。
    """

    model_config = ConfigDict(extra="forbid")
    semester: str = Field(min_length=1)
    #: 成绩单 PDF（base64）。与 `confirmed_completed_courses` 二选一。
    transcript_pdf_base64: str | None = None
    #: 用户确认后的图片识别记录（`completed.records` 形状）。二选一。
    confirmed_completed_courses: list[dict[str, object]] | None = None
    current_schedule: list[CourseOffering]
    manual_schedule_attested: bool = False
    preference: Preference


class TranscriptSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    artifact_sha256: str
    record_count: int
    term_count: int
    terms: list[str]
    pending_course_id_count: int


class CaseADemoProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: str
    curriculum: str
    course_data: str
    current_schedule: str
    planner: str
    is_full_semester: bool


class GroupCreditProgressResponse(BaseModel):
    """课程组学分进度（Phase 4）。

    ⚠️ 由 `app/curriculum/matching.py` 的 `group_credit_progress()` 计算，
    ⛔ 前端不得自行计算；它复用与判定**完全相同**的学分口径，
       因此页面上的数字与"谁该补修"的结论必然一致。

    `undecided=True` 表示该组的历史额度未确认（混合组未给拆分依据），
    此时三个数字均为 `null`，页面必须如实说明，⛔ 不得当成确定值展示。
    """

    model_config = ConfigDict(extra="forbid")

    group_id: str
    group_name: str
    required_credit: float | None
    earned_credit: float | None
    remaining_credit: float | None
    undecided: bool
    #: 为什么 `required_credit` 与培养方案写明的学分下限不同（可读说明）。
    scope_note: str | None = None


class CaseADemoPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: TranscriptSummary
    makeup_tasks: list[MakeupTask]
    course_offerings: list[CourseOffering]
    preference: Preference
    plan_result: PlanResult
    provenance: CaseADemoProvenance
    #: 课程组学分进度（专业选修组等）。默认空列表，兼容未提供课程组的方案。
    elective_progress: list[GroupCreditProgressResponse] = Field(default_factory=list)


def _runtime_or_503(runtime: CaseADemoRuntime | None) -> CaseADemoRuntime:
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "case_a_demo_not_configured", "message": "Case A demo runtime is unavailable."},
        )
    return runtime


def _validate_schedule_shape(current_schedule: list[CourseOffering]) -> None:
    """Report the two schedule-shape problems the Planner rejects as *request* errors.

    These are caller-fixable, so they must not surface as a 500. The Planner still runs
    every check itself and remains the authority on rules and semantics; this only
    turns its two input-shape rejections into a 422 whose message a user can act on,
    instead of letting a bare ``ValueError`` escape. No solving, ordering or rule
    logic is changed.
    """
    identities = [(item.semester, item.course_id, item.class_id) for item in current_schedule]
    if len(set(identities)) != len(identities):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "case_a_demo_duplicate_offering",
                "message": "current_schedule 存在重复教学班身份；同一教学班只能提交一次。",
            },
        )
    course_ids = [item.course_id for item in current_schedule]
    if len(set(course_ids)) != len(course_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "case_a_demo_multiple_classes_for_course",
                "message": "current_schedule 同一课程存在多个已选班；请先明确要保留哪一个教学班。",
            },
        )


@router.get("/offerings", response_model=list[CourseOffering])
def get_case_a_offerings(
    semester: str,
    runtime: Annotated[CaseADemoRuntime | None, Depends(get_case_a_demo_runtime)],
) -> list[CourseOffering]:
    configured = _runtime_or_503(runtime)
    try:
        return configured.course_data.get_course_offerings(semester)
    except CaseAScopeError as exc:
        # A semester the accepted Case A scope does not cover is a *request* problem,
        # never a server fault: map it to the demo's existing 422 contract instead of
        # letting it escape as a 500. The provider's own validation is untouched.
        raise HTTPException(
            status_code=422,
            detail={
                "error": "case_a_demo_semester_not_in_scope",
                "message": "semester is not covered by the configured Case A scope",
                "category": getattr(exc, "category", None),
            },
        ) from None


@router.post("/plan", response_model=CaseADemoPlanResponse)
def create_case_a_plan(
    request: CaseADemoPlanRequest,
    runtime: Annotated[CaseADemoRuntime | None, Depends(get_case_a_demo_runtime)],
) -> CaseADemoPlanResponse:
    configured = _runtime_or_503(runtime)
    _validate_schedule_shape(request.current_schedule)

    # ⚠️ 成绩单输入二选一（Phase 5）：恰好提供一个，否则 422。
    has_pdf = request.transcript_pdf_base64 is not None
    has_records = request.confirmed_completed_courses is not None
    if has_pdf == has_records:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "case_a_demo_transcript_input_ambiguous",
                "message": (
                    "请恰好提供一种成绩单输入："
                    "transcript_pdf_base64 或 confirmed_completed_courses。"
                ),
            },
        )

    pdf_bytes: bytes | None = None
    if has_pdf:
        raw = request.transcript_pdf_base64 or ""
        if len(raw) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 4:
            raise HTTPException(status_code=413, detail="Transcript PDF is too large.")
        try:
            pdf_bytes = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=422, detail="Transcript PDF encoding is invalid."
            ) from None

    try:
        run = configured.run(
            pdf_bytes=pdf_bytes,
            confirmed_records=request.confirmed_completed_courses,
            semester=request.semester,
            current_schedule=request.current_schedule,
            manual_schedule_attested=request.manual_schedule_attested,
            preference=request.preference,
        )
    except CaseADemoInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except CompletedCoursesImportRejected as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.code, "message": exc.message},
        ) from None

    manual = any(item.source == "manual-entry://current-schedule" for item in request.current_schedule)

    # ⚠️ 课程组学分进度由 matching 层计算（⛔ 前端不算、⛔ 本模块不重算）。
    #    组名取自该 case 的培养方案，用于页面展示。
    group_names = {group.group_id: group.name for group in configured.base_case.new.groups}
    progress = [
        GroupCreditProgressResponse(
            group_id=item.group_id,
            group_name=group_names.get(item.group_id, item.group_id),
            required_credit=item.required_credit,
            earned_credit=item.earned_credit,
            remaining_credit=item.remaining_credit,
            undecided=item.undecided,
            scope_note=item.scope_note,
        )
        for item in run.elective_progress
    ]

    return CaseADemoPlanResponse(
        transcript=TranscriptSummary(
            source_id=run.transcript.source_id,
            artifact_sha256=run.transcript.artifact_sha256,
            record_count=run.transcript.record_count,
            term_count=run.transcript.term_count,
            terms=list(run.transcript.terms),
            pending_course_id_count=run.transcript.pending_course_id_count,
        ),
        makeup_tasks=run.makeup_tasks,
        course_offerings=run.offerings,
        preference=run.preference,
        plan_result=run.plan_result,
        elective_progress=progress,
        provenance=CaseADemoProvenance(
            # ⚠️ 如实区分两条成绩单入口：图片路径的产物是**用户确认过的记录**，
            #    ⛔ 不是原始 PDF，也⛔ 不是 OCR 原始结果。
            transcript=(
                "user-uploaded SYSU transcript PDF"
                if has_pdf
                else "user-confirmed transcript image records (no PDF)"
            ),
            curriculum="Case A target curriculum",
            course_data=CASE_A_DEMO_SCOPE_LABEL,
            current_schedule=("student-attested manual input" if manual else "selected accepted offering"),
            planner="actual RestrictedPlanner execution",
            is_full_semester=False,
        ),
    )
