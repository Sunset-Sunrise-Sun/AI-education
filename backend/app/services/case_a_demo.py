"""Distinct Case A demo runtime; never participates in production full-semester wiring."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
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
from app.curriculum.completed_courses import (
    CompletedCourse,
    CourseIdStatus,
    normalize_completed_courses,
)
from app.curriculum.case_a_decisions import (
    AS_OF_TERM,
    CASE_TARGET_VERSION_ID,
    confirmed_scope_decisions,
    is_supported_scope_decision_set,
)
from app.curriculum.matching import GroupCreditProgress, group_credit_progress
from app.integration import PlanningOrchestrator
from app.models.contracts import CourseOffering, DataSource, MakeupTask, PlanResult, Preference
from app.planner import RestrictedPlannerProvider
from app.services.completed_courses_pdf_ingest import (
    PDF_MEDIA_TYPE,
    CompletedCoursesPdfImport,
    import_completed_courses_pdf_bytes,
)

CASE_A_DEMO_SCOPE_LABEL = "case-scoped:south+shenzhen"
MANUAL_SCHEDULE_SOURCE = "manual-entry://current-schedule"

_ENABLED = "APP_CASE_A_DEMO_ENABLED"
_CASE_PATH = "APP_CASE_A_DEMO_CURRICULUM_CASE_PATH"
_STORE_PATH = "APP_CASE_A_DEMO_COURSE_DATA_SQLITE_PATH"
_SEMESTER = "APP_CASE_A_DEMO_SEMESTER"
_SOUTH_SHA = "APP_CASE_A_DEMO_SOUTH_ACCEPTANCE_SHA256"
_SHENZHEN_SHA = "APP_CASE_A_DEMO_SHENZHEN_ACCEPTANCE_SHA256"
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")


class CaseADemoInputError(ValueError):
    """A private Case A request failed a safe input boundary."""


@dataclass(frozen=True, slots=True)
class TranscriptSummary:
    """成绩单输入的**计数摘要**（两条入口共用，⛔ 不含课程级明细）。"""

    source_id: str
    artifact_sha256: str
    record_count: int
    term_count: int
    terms: tuple[str, ...]
    pending_course_id_count: int


@dataclass(frozen=True, slots=True)
class CaseADemoRun:
    transcript: TranscriptSummary
    makeup_tasks: list[MakeupTask]
    offerings: list[CourseOffering]
    preference: Preference
    plan_result: PlanResult
    #: 课程组学分进度（由 matching 层计算，⛔ 不在 API 层重算）。
    elective_progress: tuple[GroupCreditProgress, ...]


@dataclass(frozen=True, slots=True)
class CaseADemoRuntime:
    base_case: CurriculumCase
    course_data: CaseAScopedCourseDataProvider
    planner: RestrictedPlannerProvider

    def _curriculum(
        self,
        courses: tuple[CompletedCourse, ...],
        source_id: str,
        completeness_evidence: str,
    ) -> CurriculumCaseProvider:
        """把**已归一化的已修课程事实**装进 case（⛔ 不接触任何未确认的识别结果）。

        ⚠️ 两条入口（成绩单 PDF / 用户确认后的图片识别记录）走的是**同一个**方法，
        因此图片与 PDF 必然进入**同一个**匹配引擎。
        """

        dynamic = replace(
            self.base_case,
            completed=courses,
            completed_source_id=source_id,
            completed_complete=True,
            completed_completeness_evidence=completeness_evidence,
            # Rules/decisions carrying the old completed_source_id or source_record
            # are deliberately not retargeted. No implicit pdf:N / img:N mapping is
            # permitted: 识别结果不携带课程号，任何"隐式映射"都是伪造认定。
            rules=None,
            recognitions=(),
            missing_requirements=(),
        )
        return CurriculumCaseProvider(dynamic)

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
        pdf_bytes: bytes | None = None,
        confirmed_records: list[dict[str, object]] | None = None,
        semester: str,
        current_schedule: list[CourseOffering],
        preference: Preference,
        manual_schedule_attested: bool,
    ) -> CaseADemoRun:
        """执行一次 Case A 规划。

        ⚠️ 成绩单输入**恰好提供一个**（由 API 层做互斥校验，这里再兜底一次）：

        ```text
        pdf_bytes          成绩单 PDF 字节        （主路径，行为完全不变）
        confirmed_records  **用户已确认**的图片识别记录
        ```

        ⛔ 识别原始结果**不得**从这条入口进入：本方法只接受
        `CompletedCourse` 输入形状的记录，且归一化层会拒绝未知字段
        （因此"OCR 原始 JSON"进不来）。
        """

        if (pdf_bytes is None) == (confirmed_records is None):
            raise CaseADemoInputError(
                "provide exactly one of pdf_bytes or confirmed_records"
            )
        if semester != self.course_data.scope.semester:
            raise CaseADemoInputError("semester does not match the configured Case A scope")
        self._validate_schedule(
            current_schedule, manual_schedule_attested=manual_schedule_attested
        )

        if pdf_bytes is not None:
            imported = import_completed_courses_pdf_bytes(
                pdf_bytes,
                declared_length=len(pdf_bytes),
                media_type=PDF_MEDIA_TYPE,
            )
            courses = imported.courses
            source_id = imported.source_id
            digest = imported.artifact_sha256
            evidence = f"user-uploaded-sysu-transcript-pdf:sha256:{digest}"
            summary = TranscriptSummary(
                source_id=source_id,
                artifact_sha256=digest,
                record_count=imported.record_count,
                term_count=imported.term_count,
                terms=tuple(imported.terms),
                pending_course_id_count=imported.pending_course_id_count,
            )
        else:
            courses, source_id, digest, summary = self._confirmed_input(confirmed_records or [])
            evidence = f"user-confirmed-transcript-image:sha256:{digest}"

        curriculum = self._curriculum(courses, source_id, evidence)
        tasks = curriculum.get_makeup_tasks()
        # ⚠️ 学分进度必须从**同一个 diff** 读取：这样页面数字与判定结论同源，
        #    ⛔ 不会出现"两套算法各算一次"的不一致。
        credit_progress = group_credit_progress(curriculum.get_curriculum_diff())
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
        return CaseADemoRun(
            summary, tasks, offerings, preference, result, credit_progress
        )

    def _confirmed_input(
        self, records: list[dict[str, object]]
    ) -> tuple[tuple[CompletedCourse, ...], str, str, TranscriptSummary]:
        """把**用户已确认**的图片识别记录归一化成 `CompletedCourse`。

        ⚠️ 硬边界：

        - 输入必须是 `completed.records` 形状；未知字段一律拒绝
          ⇒ ⛔ OCR 原始候选（含 `row_id` / `confidence` / `unconfirmed`）**进不来**；
        - `source_id` 由**内容摘要**派生（⛔ 不接受调用方字符串，⛔ 不信任文件名）；
        - 归一化层会强制 `course_id_status="pending"` 时 `course_id is None`，
          ⇒ ⛔ 不可能借这条入口伪造课程号认定。
        """

        stable = json.dumps(records, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(stable).hexdigest()
        source_id = f"upload:image:sha256:{digest[:16]}"
        try:
            courses = normalize_completed_courses(records, source_id=source_id)
        except CurriculumNormalizationError as exc:
            # ⛔ 不回显记录内容（可能含个人信息）。
            raise CaseADemoInputError(f"confirmed records rejected: {exc}") from None
        if not courses:
            raise CaseADemoInputError("confirmed records must not be empty")
        pending = sum(1 for course in courses if course.course_id_status is CourseIdStatus.PENDING)
        summary = TranscriptSummary(
            source_id=source_id,
            artifact_sha256=digest,
            record_count=len(courses),
            term_count=len({course.semester for course in courses}),
            terms=tuple(dict.fromkeys(course.semester for course in courses)),
            pending_course_id_count=pending,
        )
        return courses, source_id, digest, summary


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
    )


def get_case_a_demo_runtime() -> CaseADemoRuntime | None:
    return build_case_a_demo_runtime(os.environ)
