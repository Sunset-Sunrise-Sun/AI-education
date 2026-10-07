"""Private Case A closed-loop demo endpoints; separate from production /plan."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.course_data import CaseAScopeError
from app.models.contracts import Change, CourseOffering, MakeupTask, PlanResult, Preference
from app.path_planner import apply_repair_proposal, generate_repair_proposals
from app.services.case_a_demo import (
    CASE_A_DEMO_SCOPE_LABEL,
    CaseADemoInputError,
    CaseADemoRuntime,
    CompletedBinding,
    get_case_a_demo_runtime,
)
from app.services.case_a_planning_override import (
    PLANNING_ONLY_DISCLOSURE,
    ElectiveSelection,
)
from app.services.case_a_roadmap import requirement_kind_label
from app.services.completed_courses_ingest import CompletedCoursesImportRejected, MAX_UPLOAD_BYTES

router = APIRouter(prefix="/case-a-demo", tags=["case-a-demo"])


class CaseAElectiveSelection(BaseModel):
    """用户明确选择的选修教学班（精确身份 `semester + course_id + class_id`）。"""

    model_config = ConfigDict(extra="forbid")
    semester: str = ""
    course_id: str = Field(min_length=1)
    class_id: str = ""


class RejectedOverrideItem(BaseModel):
    """被拒绝的覆盖输入（结构化；⛔ 不静默丢弃）。"""

    model_config = ConfigDict(extra="forbid")
    course_id: str
    reason: str


class AppliedElectiveItem(BaseModel):
    """本轮实际加入本学期方案的选修教学班（精确身份）。"""

    model_config = ConfigDict(extra="forbid")
    course_id: str
    course_name: str
    class_id: str
    credit: float


class PlanningOnlyDisclosurePayload(BaseModel):
    """三项披露文案：必须**同时**展示（⛔ 不是学校官方认定结果）。"""

    model_config = ConfigDict(extra="forbid")
    basis: str
    scope: str
    authority: str


class CaseADemoPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semester: str = Field(min_length=1)
    transcript_pdf_base64: str = Field(min_length=1)
    current_schedule: list[CourseOffering]
    manual_schedule_attested: bool = False
    preference: Preference
    #: 用户本次规划确认"按已满足处理"的课程号（**精确 `course_id`**，run-local，可撤销）。
    #: ⛔ 只覆盖本次规划，不改写来源可核验的基础评估。
    user_confirmed_manual_task_keys: list[str] = Field(default_factory=list)
    #: 用户明确加入本学期方案的选修教学班（服务端复核 CLEAR 后才生效）。
    elective_selections: list[CaseAElectiveSelection] = Field(default_factory=list)

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


# ---------------------------------------------------------------------------
# 加法式（Case A 专用）响应模型
#
# ⛔ 这些**不是** `/schemas/` 公共契约，也**不**改动冻结的 `PlanResult`：
#    它们只承载 Case A demo 的编排结果。
# ---------------------------------------------------------------------------


class RepairProposalItem(BaseModel):
    """一条**待用户确认**的同课程换班建议（⛔ 尚未生效、不复制 CourseOffering 取值）。"""

    model_config = ConfigDict(extra="forbid")
    proposal_id: str
    semester: str
    course_id: str
    current_class_id: str
    candidate_class_id: str
    original_state: str
    candidate_state: str
    reason: str


class RepairProposalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semester: str
    proposals: list[RepairProposalItem]
    unresolved: list[str]


class RoadmapCourseItem(BaseModel):
    """未来学期的一门课（**课程级**：⛔ 无 class_id / teacher / 时间 / 校区 / 容量）。"""

    model_config = ConfigDict(extra="forbid")
    course_id: str
    course_name: str
    credit: float
    requirement_kind: str
    requirement_label: str
    placement: str
    reason: str


class RoadmapSemesterItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semester_label: str
    curriculum_semester: int
    semester_index: int
    courses: list[RoadmapCourseItem]
    required_credit: float
    elective_credit: float
    total_credit: float
    warnings: list[str]


class ElectiveAccounting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_credit: float | None
    completed_credit: float | None
    current_semester_credit: float
    planned_credit: float
    remaining_credit: float | None
    gap_credit: float | None
    group_id: str | None


class AcademicRoadmapPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_semester: str | None
    current_semester_planned_course_ids: list[str]
    future_semesters: list[RoadmapSemesterItem]
    elective: ElectiveAccounting
    unresolved: list[str]
    warnings: list[str]


class CurrentElectiveItem(BaseModel):
    """当前学期**可考虑的专业选修**（候选；⛔ 不自动加入方案）。"""

    model_config = ConfigDict(extra="forbid")
    course_id: str
    course_name: str
    credit: float
    available_class_count: int
    conflicting_class_count: int
    unknown_schedule_class_count: int
    clear_class_count: int
    #: 唯一已确认无冲突教学班时给出班号；多个候选时为 `null`（由用户自己选）。
    unique_clear_class_id: str | None
    #: 面向用户的中文冲突说明（⛔ 不含机器码）。
    conflict_label: str


class CurrentSemesterLoadPayload(BaseModel):
    """当前学期学分负荷摘要（产品层口径）。"""

    model_config = ConfigDict(extra="forbid")
    selected_credit: float
    suggested_makeup_credit: float
    suggested_elective_credit: float
    projected_total_credit: float
    max_credit: float
    exceeds_max: bool
    #: 产品级默认上限说明（⛔ 不是学校政策声明）。
    policy_note: str


class CaseADemoPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: TranscriptSummary
    makeup_tasks: list[MakeupTask]
    course_offerings: list[CourseOffering]
    preference: Preference
    plan_result: PlanResult
    provenance: CaseADemoProvenance
    #: 结构化换班建议（⛔ 生成 ≠ 应用）。
    repair_proposals: RepairProposalSummary
    #: 未来学期课程级路线图；不可构建时为 `null`（⛔ 不返回假数据）。
    roadmap: AcademicRoadmapPayload | None
    #: `roadmap is None` 时的结构性说明。
    roadmap_note: str | None
    #: 上传成绩单与**已确认**已修事实的绑定结果。
    #:
    #: **唯一**受支持的取值是 `not_bound`：上传行**没有**官方课程号
    #: （真实成绩单即如此），因此本次**未**采用上传行做满足判定，
    #: 培养方案已确认事实**原样保留**。
    #:
    #: ⛔ **不存在** `bound` 取值：让上传行改写已确认满足事实需要伪造 provenance，
    #:    见 `app.services.case_a_demo._completed_binding` 的文档。
    #: ⛔ `not_bound` **不是**"已确认事实被抹掉"，也⛔ **不是**"上传行被当成已确认事实"。
    completed_binding: CompletedBinding
    #: 面向用户的绑定说明（始终非空：未绑定时必须给出说明）。
    completed_binding_note: str | None
    #: 当前学期**可考虑的专业选修**（最多 3 门；⛔ 只是候选，不自动加入方案）。
    current_elective_recommendations: list[CurrentElectiveItem]
    #: 当前学期学分负荷摘要（含产品级上限）。
    current_load: CurrentSemesterLoadPayload
    #: ---- 规划覆盖（run-local；⛔ 不改写来源可核验的基础评估） ----
    #:
    #: 本轮**实际生效**的"按已满足处理"确认（已通过校验的精确课程号）。
    applied_manual_confirmations: list[str]
    #: 被拒绝的确认输入（结构化中文原因；⛔ 不静默丢弃）。
    rejected_manual_confirmations: list[RejectedOverrideItem]
    #: 本轮实际加入本学期方案的选修教学班（精确身份）。
    applied_elective_sections: list[AppliedElectiveItem]
    #: 被拒绝的选修选择（结构化中文原因；⛔ 不静默丢弃）。
    rejected_elective_selections: list[RejectedOverrideItem]
    #: 有效（effective）补救任务：被确认的 `manual_confirmation` 在本轮视为已满足。
    #: ⚠️ `makeup_tasks` 始终保留**来源可核验**的基础评估，两者不得混为一谈。
    effective_makeup_tasks: list[MakeupTask]
    #: 三项披露文案（必须同时出现；⛔ 不是学校官方认定结果）。
    planning_only_disclosure: PlanningOnlyDisclosurePayload


class CaseADemoRepairApplyRequest(BaseModel):
    """显式换班确认：必须给出**完整身份**，⛔ 不接受"采用第一条建议"这类含糊输入。"""

    model_config = ConfigDict(extra="forbid")
    semester: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    from_class_id: str = Field(min_length=1)
    to_class_id: str = Field(min_length=1)
    current_schedule: list[CourseOffering]
    manual_schedule_attested: bool = False


class CaseADemoRepairApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    applied: bool
    schedule: list[CourseOffering]
    changes: list[Change]
    reason: str
    revalidated: bool
    remaining_conflicts: list[str]
    #: 应用后的当前课表重算的建议（⛔ 仍只是建议）。
    repair_proposals: RepairProposalSummary


def _runtime_or_503(runtime: CaseADemoRuntime | None) -> CaseADemoRuntime:
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "case_a_demo_not_configured", "message": "Case A demo runtime is unavailable."},
        )
    return runtime


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
    if len(request.transcript_pdf_base64) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 4:
        raise HTTPException(status_code=413, detail="Transcript PDF is too large.")
    try:
        pdf_bytes = base64.b64decode(request.transcript_pdf_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="Transcript PDF encoding is invalid.") from None
    try:
        run = configured.run(
            pdf_bytes=pdf_bytes,
            semester=request.semester,
            current_schedule=request.current_schedule,
            manual_schedule_attested=request.manual_schedule_attested,
            preference=request.preference,
            # 规划覆盖（run-local、可撤销）：⛔ 不改写来源可核验的基础评估。
            user_confirmed_manual_task_keys=tuple(request.user_confirmed_manual_task_keys),
            elective_selections=tuple(
                ElectiveSelection(
                    semester=item.semester,
                    course_id=item.course_id,
                    class_id=item.class_id,
                )
                for item in request.elective_selections
            ),
        )
    except CaseADemoInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except CompletedCoursesImportRejected as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.code, "message": exc.message},
        ) from None

    manual = any(item.source == "manual-entry://current-schedule" for item in request.current_schedule)
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
        provenance=CaseADemoProvenance(
            transcript="user-uploaded SYSU transcript PDF",
            curriculum="Case A target curriculum",
            course_data=CASE_A_DEMO_SCOPE_LABEL,
            current_schedule=("student-attested manual input" if manual else "selected accepted offering"),
            planner="actual RestrictedPlanner execution",
            is_full_semester=False,
        ),
        repair_proposals=_proposal_summary(run.repair_proposals),
        roadmap=_roadmap_payload(run.roadmap, group_id=run.elective_group_id),
        roadmap_note=run.roadmap_note,
        completed_binding=run.completed_binding,
        completed_binding_note=_binding_note(run.completed_binding),
        current_elective_recommendations=[
            CurrentElectiveItem(
                course_id=item.course_id,
                course_name=item.course_name,
                credit=item.credit,
                available_class_count=item.available_class_count,
                conflicting_class_count=item.conflicting_class_count,
                unknown_schedule_class_count=item.unknown_schedule_class_count,
                clear_class_count=item.clear_class_count,
                unique_clear_class_id=item.unique_clear_class_id,
                conflict_label=item.conflict_label,
            )
            for item in run.current_elective_recommendations
        ],
        current_load=CurrentSemesterLoadPayload(
            selected_credit=run.current_load.selected_credit,
            suggested_makeup_credit=run.current_load.suggested_makeup_credit,
            suggested_elective_credit=run.current_load.suggested_elective_credit,
            projected_total_credit=run.current_load.projected_total_credit,
            max_credit=run.current_load.max_credit,
            exceeds_max=run.current_load.exceeds_max,
            policy_note=(
                "本学期学分上限为产品默认值；若你在偏好中设置了更低的学分上限，以你的设置为准。"
                "⛔ 这不是学校政策声明。"
            ),
        ),
        # ---- 规划覆盖（run-local） ----
        applied_manual_confirmations=list(run.override.applied_course_ids),
        rejected_manual_confirmations=[
            RejectedOverrideItem(course_id=course_id, reason=reason)
            for course_id, reason in run.override.rejected_course_ids
        ],
        applied_elective_sections=[
            AppliedElectiveItem(
                course_id=item.course_id,
                course_name=item.course_name,
                class_id=item.class_id,
                credit=float(item.credit),
            )
            for item in run.override.accepted_elective_sections
        ],
        rejected_elective_selections=[
            RejectedOverrideItem(course_id=course_id, reason=reason)
            # ⚠️ 选修被拒的原因由 `resolve_elective_selections` 产出，
            #    经 `build_outcome` 放进 `rejected_elective_course_ids`。
            for course_id, reason in run.override.rejected_elective_course_ids
        ],
        # ⚠️ `makeup_tasks` 是**来源可核验**的基础评估，保持不变；
        #    `effective_makeup_tasks` 是本次规划看到的版本（含用户确认）。
        effective_makeup_tasks=list(run.override.effective_tasks),
        planning_only_disclosure=PlanningOnlyDisclosurePayload(**PLANNING_ONLY_DISCLOSURE),
    )


def _binding_note(binding: CompletedBinding) -> str:
    """上传成绩单绑定结果的**如实**说明（⛔ 不含任何成绩/姓名/学号）。

    ⛔ 这里没有 `bound` 分支：`CompletedBinding` 只有 `not_bound` 一个取值，
    因此说明**始终**存在 —— 前端不可能收到一个"没有说明的未绑定状态"。
    """

    return (
        "上传的成绩单没有官方课程号，无法与培养方案已确认的已修事实安全绑定；"
        "本次未使用上传行做满足判定，培养方案已确认的满足事实原样保留。"
        "⛔ 系统不会按课程名或学分猜测课程是否已修。"
    )


def _proposal_summary(proposals: object) -> RepairProposalSummary:
    """把内部 `RepairProposalSet` 映射成加法式响应（⛔ 不复制 CourseOffering 取值）。"""

    return RepairProposalSummary(
        semester=proposals.semester,  # type: ignore[attr-defined]
        proposals=[
            RepairProposalItem(
                proposal_id=item.proposal_id,
                semester=item.semester,
                course_id=item.target_course_id,
                current_class_id=item.current_class_id,
                candidate_class_id=item.candidate_class_id,
                original_state=item.original_state.value,
                candidate_state=item.candidate_state.value,
                reason=item.reason,
            )
            for item in proposals.proposals  # type: ignore[attr-defined]
        ],
        unresolved=list(proposals.unresolved),  # type: ignore[attr-defined]
    )


def _roadmap_payload(roadmap: object | None, *, group_id: str) -> AcademicRoadmapPayload | None:
    """把内部 `AcademicRoadmap` 映射成加法式响应。

    ⛔ 未来学期**只**输出课程级字段；本映射里不存在任何教学班级字段。
    ``group_id`` 由调用方（即本次 run 实际使用的选修组）如实传入，
    ⛔ 本层不自行猜测或另取一个常量。
    """

    if roadmap is None:
        return None
    requirement = roadmap.elective_requirement_credit  # type: ignore[attr-defined]
    completed = roadmap.elective_completed_credit  # type: ignore[attr-defined]
    current = roadmap.elective_current_semester_credit  # type: ignore[attr-defined]
    gap = (
        None
        if requirement is None or completed is None
        else round(requirement - completed - current, 6)
    )
    return AcademicRoadmapPayload(
        current_semester=roadmap.current_semester,  # type: ignore[attr-defined]
        current_semester_planned_course_ids=list(
            roadmap.current_semester_planned_course_ids  # type: ignore[attr-defined]
        ),
        future_semesters=[
            RoadmapSemesterItem(
                semester_label=semester.semester_label,
                curriculum_semester=semester.curriculum_semester,
                semester_index=semester.semester_index,
                courses=[
                    RoadmapCourseItem(
                        course_id=item.course_id,
                        course_name=item.course_name,
                        credit=item.credit,
                        requirement_kind=item.requirement_kind.value,
                        requirement_label=requirement_kind_label(item.requirement_kind),
                        placement=item.placement.value,
                        reason=item.reason,
                    )
                    for item in semester.courses
                ],
                required_credit=semester.required_credit,
                elective_credit=semester.elective_credit,
                total_credit=semester.total_credit,
                warnings=list(semester.warnings),
            )
            for semester in roadmap.future_semesters  # type: ignore[attr-defined]
        ],
        elective=ElectiveAccounting(
            requirement_credit=requirement,
            completed_credit=completed,
            current_semester_credit=current,
            planned_credit=roadmap.elective_planned_credit,  # type: ignore[attr-defined]
            remaining_credit=roadmap.elective_remaining_credit,  # type: ignore[attr-defined]
            gap_credit=gap,
            group_id=group_id,
        ),
        unresolved=list(roadmap.unresolved),  # type: ignore[attr-defined]
        warnings=list(roadmap.warnings),  # type: ignore[attr-defined]
    )


@router.post("/repair/apply", response_model=CaseADemoRepairApplyResponse)
def apply_case_a_repair(
    request: CaseADemoRepairApplyRequest,
    runtime: Annotated[CaseADemoRuntime | None, Depends(get_case_a_demo_runtime)],
) -> CaseADemoRepairApplyResponse:
    """**显式确认**一条换班建议后才应用（⛔ 绝不在生成建议时自动应用）。

    校验与"只能换同课程同学期、候选必须重新确认 CLEAR"都由
    `apply_repair_proposal()` fail closed 完成；本层只做输入边界与响应映射。
    """

    configured = _runtime_or_503(runtime)
    if request.semester != configured.course_data.scope.semester:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "case_a_demo_semester_not_in_scope",
                "message": "semester is not covered by the configured Case A scope",
            },
        )
    try:
        configured._validate_schedule(  # noqa: SLF001 - 与 /plan 完全同一套边界
            request.current_schedule,
            manual_schedule_attested=request.manual_schedule_attested,
        )
    except CaseADemoInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    offerings = configured.course_data.get_course_offerings(request.semester)
    applied = apply_repair_proposal(
        semester=request.semester,
        course_id=request.course_id,
        from_class_id=request.from_class_id,
        to_class_id=request.to_class_id,
        current_schedule=request.current_schedule,
        offerings=offerings,
    )
    refreshed = generate_repair_proposals(
        semester=request.semester,
        current_schedule=applied.schedule,
        offerings=offerings,
    )
    return CaseADemoRepairApplyResponse(
        status=applied.status.value,
        applied=applied.status.value == "applied",
        schedule=list(applied.schedule),
        changes=list(applied.changes),
        reason=applied.reason,
        revalidated=applied.revalidated,
        remaining_conflicts=list(applied.remaining_conflicts),
        repair_proposals=_proposal_summary(refreshed),
    )
