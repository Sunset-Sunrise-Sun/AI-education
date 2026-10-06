"""Distinct Case A demo runtime; never participates in production full-semester wiring."""

from __future__ import annotations

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
from app.curriculum.case_a_decisions import (
    AS_OF_TERM,
    CASE_TARGET_VERSION_ID,
    confirmed_scope_decisions,
)
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
class CaseADemoRun:
    transcript: CompletedCoursesPdfImport
    makeup_tasks: list[MakeupTask]
    offerings: list[CourseOffering]
    preference: Preference
    plan_result: PlanResult


@dataclass(frozen=True, slots=True)
class CaseADemoRuntime:
    base_case: CurriculumCase
    course_data: CaseAScopedCourseDataProvider
    planner: RestrictedPlannerProvider

    def _curriculum(self, imported: CompletedCoursesPdfImport) -> CurriculumCaseProvider:
        dynamic = replace(
            self.base_case,
            completed=imported.courses,
            completed_source_id=imported.source_id,
            completed_complete=True,
            completed_completeness_evidence=(
                f"user-uploaded-sysu-transcript-pdf:sha256:{imported.artifact_sha256}"
            ),
            # Rules/decisions carrying the old completed_source_id or source_record
            # are deliberately not retargeted. No implicit pdf:N mapping is permitted.
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
        curriculum = self._curriculum(imported)
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
        return CaseADemoRun(imported, tasks, offerings, preference, result)


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
            or base_case.confirmed_scope_decisions != confirmed_scope_decisions()
        ):
            return None
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
