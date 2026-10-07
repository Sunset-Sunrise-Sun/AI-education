"""Distinct Case A demo runtime; never participates in production full-semester wiring."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from app.course_data import (
    CaseAScopeError,
    CaseAScopedCourseDataProvider,
    build_case_a_dataset,
)
from app.curriculum import (
    CurriculumCase,
    CurriculumCaseProvider,
    CurriculumNormalizationError,
    load_curriculum_case,
)
from app.curriculum.case_a_decisions import (
    AS_OF_TERM,
    CASE_TARGET_VERSION_ID,
    confirmed_scope_decisions,
    is_supported_scope_decision_set,
)
from app.curriculum.plan_profiles import ELECTIVE_POOL_GROUP_ID
from app.integration import PlanningOrchestrator
from app.models.contracts import CourseOffering, DataSource, MakeupTask, PlanResult, Preference
from app.path_planner import RepairProposalSet, generate_repair_proposals
from app.planner import RestrictedPlannerProvider
from app.path_planner import AcademicRoadmap
from app.services.case_a_roadmap import (
    CaseARoadmapError,
    bind_current_semester_courses,
    build_case_a_roadmap,
)
from app.services.completed_courses_pdf_ingest import (
    PDF_MEDIA_TYPE,
    CompletedCoursesPdfImport,
    import_completed_courses_pdf_bytes,
)

CASE_A_DEMO_SCOPE_LABEL = "case-scoped:south+shenzhen"
MANUAL_SCHEDULE_SOURCE = "manual-entry://current-schedule"

#: Case A 目标培养方案里的专业选修组。
#:
#: ⚠️ 这是**Curriculum 模块的权威常量**（`app.curriculum.plan_profiles`），
#: ⛔ 本模块不自行定义一个新的组名；可用环境变量覆盖，
#: 但覆盖值若不在培养方案里，路线图会 **fail closed**（报告 unresolved），
#: ⛔ 绝不会静默伪造一个组或一个最低学分。
CASE_A_ELECTIVE_GROUP_ID = ELECTIVE_POOL_GROUP_ID

_ENABLED = "APP_CASE_A_DEMO_ENABLED"
_CASE_PATH = "APP_CASE_A_DEMO_CURRICULUM_CASE_PATH"
_STORE_PATH = "APP_CASE_A_DEMO_COURSE_DATA_SQLITE_PATH"
_SEMESTER = "APP_CASE_A_DEMO_SEMESTER"
_SOUTH_SHA = "APP_CASE_A_DEMO_SOUTH_ACCEPTANCE_SHA256"
_SHENZHEN_SHA = "APP_CASE_A_DEMO_SHENZHEN_ACCEPTANCE_SHA256"
_ROADMAP_HORIZON = "APP_CASE_A_DEMO_ROADMAP_LAST_SEMESTER"
_ELECTIVE_GROUP = "APP_CASE_A_DEMO_ELECTIVE_GROUP_ID"
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")


class CaseADemoInputError(ValueError):
    """A private Case A request failed a safe input boundary."""


@dataclass(frozen=True, slots=True)
class CaseADemoRun:
    transcript: CompletedCoursesPdfImport
    makeup_tasks: list[MakeupTask]
    offerings: list[CourseOffering]
    preference: Preference
    plan_result: PlanResult
    #: 当前学期**结构化**换班建议（⛔ 只生成，不应用；应用需调用方显式确认）。
    repair_proposals: RepairProposalSet
    #: 未来学期**课程级**路线图；不可构建时为 `None`（⛔ 不返回假数据）。
    roadmap: AcademicRoadmap | None
    #: 路线图不可构建的原因（`roadmap is None` 时给出；⛔ 只含结构性说明）。
    roadmap_note: str | None
    #: 本次实际使用的选修组 id（供响应如实回显，⛔ 不由 API 层另行猜测）。
    elective_group_id: str = CASE_A_ELECTIVE_GROUP_ID
    #: 上传成绩单的绑定结果：`bound` / `not_bound`。
    #: `not_bound` 表示**本次未采用上传行做满足判定**，已确认事实原样保留
    #: （⛔ 不是静默抹掉，也⛔ 不是把上传行当成已确认事实）。
    completed_binding: str = "bound"


@dataclass(frozen=True, slots=True)
class CaseADemoRuntime:
    base_case: CurriculumCase
    course_data: CaseAScopedCourseDataProvider
    planner: RestrictedPlannerProvider
    #: 未来路线图的上界学期（可选）；缺省取培养方案链尾。
    roadmap_last_semester: str | None = None
    #: 需要满足最低学分的选修组（缺省用 Curriculum 的权威常量）。
    elective_group_id: str = CASE_A_ELECTIVE_GROUP_ID

    def _completed_binding(
        self, imported: CompletedCoursesPdfImport
    ) -> tuple[str, CurriculumCase]:
        """决定上传的成绩单能否**安全绑定**到已确认的已修事实。

        背景（⛔ 不得回退）：基础 case 的已确认满足事实来自
        `rules`（绑定 `case-owner-confirmed://case-a/d4`）**与基础 case 自己的
        `completed` 行**。上传的 PDF 若无法绑定，替换 `completed` 并清空 `rules`
        会**静默抹掉**这些已确认事实（真实基线 = 12 satisfied + 11 manual_confirmation），
        从而使已满足的要求被重新规划。

        三种结果：

        ```text
        bound       每一行都有已确认课程号、课程号集合与基础 case 完全一致、
                    且不存在"已确认通过却被上传行标为未通过"的矛盾
                    ⇒ 用上传行；已确认满足事实由同一套 rules 继续生效
        not_bound   上传行没有任何课程号（真实成绩单就是这种：PDF 不含官方课程号）
                    ⇒ ⛔ 保留基础 case 的已确认事实与 rules，
                      并**明确标记**本次未采用上传行做满足判定（⛔ 不静默）
        contradict  上传行与已确认事实互相矛盾
                    （部分有课程号 / 出现未知课程号 / 把已确认通过的课标成未通过）
                    ⇒ fail closed，⛔ 不猜测哪一侧正确
        ```

        ⛔ 任何情况下都不把 `manual_confirmation` / `possibly_equivalent` 提升为满足。
        """

        rows = tuple(imported.courses)
        confirmed = {row.course_id: row for row in self.base_case.completed if row.course_id}

        identified = [row for row in rows if row.course_id is not None]
        if not identified:
            # 真实成绩单：PDF 不提供官方课程号 ⇒ 无法绑定。
            return "not_bound", self.base_case

        unknown = sorted(row.course_id for row in identified if row.course_id not in confirmed)
        if unknown:
            raise CaseADemoInputError(
                "上传的成绩单包含培养方案已确认事实之外的课程号；"
                "⛔ 无法安全绑定，拒绝在不确定的已修事实上继续规划。"
            )
        for row in identified:
            original = confirmed.get(row.course_id)
            if original is not None and original.passed and not row.passed:
                raise CaseADemoInputError(
                    f"上传的成绩单把已确认通过的课程 {row.course_id} 标为未通过；"
                    f"⛔ 两侧事实矛盾，拒绝继续。"
                )
        if len(identified) != len(rows):
            raise CaseADemoInputError(
                "上传的成绩单只有部分记录带有课程号；⛔ 无法安全绑定，拒绝继续。"
            )
        if {row.course_id for row in identified} != set(confirmed):
            raise CaseADemoInputError(
                "上传的成绩单与培养方案已确认的已修事实范围不一致；"
                "⛔ 无法安全绑定，拒绝在不确定的已修事实上继续规划。"
            )
        return "bound", replace(
            self.base_case,
            completed=rows,
            completed_source_id=imported.source_id,
            completed_complete=True,
            completed_completeness_evidence=(
                f"user-uploaded-sysu-transcript-pdf:sha256:{imported.artifact_sha256}"
            ),
        )

    def _curriculum(self, imported: CompletedCoursesPdfImport) -> CurriculumCaseProvider:
        _binding, case = self._completed_binding(imported)
        return CurriculumCaseProvider(case)

    def _validate_schedule(
        self,
        schedule: list[CourseOffering],
        *,
        manual_schedule_attested: bool,
    ) -> None:
        accepted = {
            (item.semester, item.course_id, item.class_id): item
            for item in self.course_data.dataset.offerings
        }
        for item in schedule:
            if item.data_source is not DataSource.REAL:
                raise CaseADemoInputError("current_schedule must be explicitly real")
            if item.source == MANUAL_SCHEDULE_SOURCE:
                if not manual_schedule_attested:
                    raise CaseADemoInputError(
                        "student-attested manual current_schedule requires explicit confirmation"
                    )
                continue
            original = accepted.get((item.semester, item.course_id, item.class_id))
            if original is None or original.model_dump(mode="json") != item.model_dump(mode="json"):
                raise CaseADemoInputError(
                    "current_schedule must contain accepted Case A offerings or attested manual entries"
                )

    def run(
        self,
        *,
        pdf_bytes: bytes,
        semester: str,
        current_schedule: list[CourseOffering],
        preference: Preference,
        manual_schedule_attested: bool,
    ) -> CaseADemoRun:
        if semester != self.course_data.scope.semester:
            raise CaseADemoInputError("semester does not match the configured Case A scope")
        self._validate_schedule(
            current_schedule, manual_schedule_attested=manual_schedule_attested
        )
        imported = import_completed_courses_pdf_bytes(
            pdf_bytes,
            declared_length=len(pdf_bytes),
            media_type=PDF_MEDIA_TYPE,
        )
        binding, effective_case = self._completed_binding(imported)
        curriculum = CurriculumCaseProvider(effective_case)
        tasks = curriculum.get_makeup_tasks()
        offerings = self.course_data.get_course_offerings(semester)
        orchestrator = PlanningOrchestrator(
            curriculum=curriculum,
            course_data=self.course_data,
            planner=self.planner,
        )
        result = orchestrator.build_plan(
            semester=semester,
            current_schedule=current_schedule,
            preference=preference,
        )
        # 当前学期结构化换班建议：**只生成**，⛔ 不应用、⛔ 不改 current_schedule。
        repair_proposals = generate_repair_proposals(
            semester=semester,
            current_schedule=current_schedule,
            offerings=offerings,
        )
        # 未来学期课程级路线图：只吃 Curriculum 事实（⛔ 不需要任何 Course Data）。
        #
        # ⚠️ 本学期真实教学班按**精确课程身份**绑定到培养方案课程后再传入，
        #    否则 `elective_current_semester_credit` 永远是 0，
        #    使 `requirement - completed - current = planned + remaining` 在真实接口上不成立。
        current_courses, elective_current_ids, binding_unresolved = bind_current_semester_courses(
            effective_case,
            current_schedule,
            elective_group_id=self.elective_group_id,
        )
        roadmap: AcademicRoadmap | None = None
        roadmap_note: str | None = None
        try:
            roadmap = build_case_a_roadmap(
                effective_case,
                makeup_tasks=tasks,
                current_semester_label=semester,
                last_curriculum_semester=self.roadmap_last_semester,
                elective_group_id=self.elective_group_id,
                current_semester_courses=current_courses,
                elective_current_semester_course_ids=elective_current_ids,
            )
            if binding_unresolved:
                roadmap = _with_extra_notes(roadmap, binding_unresolved)
        except CaseARoadmapError as exc:
            # ⛔ 不编造路线图：如实说明为什么无法构建（只含结构性说明）。
            roadmap_note = f"未来学期路线图无法构建：{exc}"
        return CaseADemoRun(
            imported,
            tasks,
            offerings,
            preference,
            result,
            repair_proposals,
            roadmap,
            roadmap_note,
            self.elective_group_id,
            binding,
        )


def _with_extra_notes(roadmap: AcademicRoadmap, extra: Sequence[str]) -> AcademicRoadmap:
    """把绑定阶段的 unresolved 如实并入路线图（⛔ 不吞掉、不改其它字段）。"""

    return replace(roadmap, unresolved=(*roadmap.unresolved, *extra))


def _with_approved_scope_decisions(base_case: CurriculumCase) -> CurriculumCase:
    """Return the case carrying every approved Case A scope decision.

    A private artifact built before the historical ruling carries only the four
    ``future`` decisions. The scope question for the three ranges ending at the
    cut-off must not depend on whether a completed course happened to be recognised
    (a transcript PDF carries no course id), so the runtime completes the case with
    the approved decisions it is missing instead of mutating anything.

    ⛔ Only decisions that are literally part of the approved set are ever added, and
    an artifact carrying a decision **outside** that set is rejected by the caller -
    this is a completion of approved data, not a relaxation of the gate.
    """

    approved = confirmed_scope_decisions()
    present = {decision.target_source_record for decision in base_case.confirmed_scope_decisions}
    missing = tuple(
        decision for decision in approved if decision.target_source_record not in present
    )
    if not missing:
        return base_case
    return replace(
        base_case,
        confirmed_scope_decisions=(*base_case.confirmed_scope_decisions, *missing),
    )


def build_case_a_demo_runtime(environment: Mapping[str, str]) -> CaseADemoRuntime | None:
    """Fail closed unless every explicit Case A demo input is present and valid."""

    if environment.get(_ENABLED) != "1":
        return None
    values = {
        name: environment.get(name, "").strip()
        for name in (_CASE_PATH, _STORE_PATH, _SEMESTER, _SOUTH_SHA, _SHENZHEN_SHA)
    }
    if any(not value for value in values.values()):
        return None
    if _SHA256.fullmatch(values[_SOUTH_SHA]) is None or _SHA256.fullmatch(values[_SHENZHEN_SHA]) is None:
        return None
    try:
        base_case = load_curriculum_case(values[_CASE_PATH])
        if (
            base_case.data_source is not DataSource.REAL
            or base_case.new.version_id != CASE_TARGET_VERSION_ID
            or base_case.makeup_scope is None
            or base_case.makeup_scope.as_of_term != AS_OF_TERM
            # Only an approved decision set is accepted; an artifact that invented a
            # decision of its own is still rejected.
            or not is_supported_scope_decision_set(base_case.confirmed_scope_decisions)
        ):
            return None
        base_case = _with_approved_scope_decisions(base_case)
        # Validate the approved base projection before replacing its completed input.
        CurriculumCaseProvider(base_case).get_makeup_tasks()
        dataset = build_case_a_dataset(
            values[_STORE_PATH],
            semester=values[_SEMESTER],
            expected_campus_sha256={
                "south-campus": values[_SOUTH_SHA].lower(),
                "shenzhen-campus": values[_SHENZHEN_SHA].lower(),
            },
        )
    except (CaseAScopeError, CurriculumNormalizationError):
        return None
    return CaseADemoRuntime(
        base_case=base_case,
        course_data=CaseAScopedCourseDataProvider(dataset),
        planner=RestrictedPlannerProvider(),
        roadmap_last_semester=(environment.get(_ROADMAP_HORIZON) or "").strip() or None,
        elective_group_id=(environment.get(_ELECTIVE_GROUP) or "").strip()
        or CASE_A_ELECTIVE_GROUP_ID,
    )


def get_case_a_demo_runtime() -> CaseADemoRuntime | None:
    return build_case_a_demo_runtime(os.environ)
