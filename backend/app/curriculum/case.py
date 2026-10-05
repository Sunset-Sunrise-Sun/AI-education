"""Load a local structured case without exposing private records."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.curriculum.academic import AcademicAnalysis, PriorityPolicy, analyze_academic_path
from app.curriculum.completed_courses import CompletedCourse, normalize_completed_courses
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.json_reader import load_json_input, resolve_local_input
from app.curriculum.matching import (
    ConfirmedElectiveSelection,
    ConfirmedGroupScopeDecision,
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CurriculumDiff,
    CurriculumResultProvider,
    MakeupScope,
    MatchingRules,
    build_curriculum_diff,
)
from app.curriculum.requirements import CurriculumVersion, normalize_curriculum_version
from app.curriculum.terms import ConfirmedScopeDecision
from app.models.contracts import DataSource, MakeupTask

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_CASE_PATH = _REPO_ROOT / "mock_data" / "curriculum_demo" / "case.json"


def _object(value: object, *, required: set[str], optional: set[str], label: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise CurriculumNormalizationError(f"{label}: expected an object")
    if set(value) - required - optional:
        raise CurriculumNormalizationError(f"{label}: unexpected field")
    if required - set(value):
        raise CurriculumNormalizationError(f"{label}: missing required field")
    return value


def _sequence(value: object, label: str) -> tuple:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CurriculumNormalizationError(f"{label}: expected an array")
    return tuple(value)


def _decisions(values: object, model: type, keys: set[str], label: str) -> tuple:
    result = []
    for row, value in enumerate(_sequence(values, label), 1):
        record = _object(value, required=keys, optional=set(), label=label)
        try:
            result.append(model(**record))
        except CurriculumNormalizationError:
            raise CurriculumNormalizationError(f"{label} row {row}: invalid decision") from None
    return tuple(result)


def _version(value: object, *, directory: Path | None = None) -> CurriculumVersion:
    record = _object(value, required={"version_id", "major", "cohort", "source_id"},
                     optional={"group_records", "complete", "completeness_evidence", "total_credit",
                               "practice_credit", "study_years", "course_records", "docx"}, label="curriculum")
    if ("course_records" in record) == ("docx" in record):
        raise CurriculumNormalizationError("curriculum: provide course_records or docx exclusively")
    if "docx" in record:
        if directory is None:
            raise CurriculumNormalizationError("curriculum: file inputs require load_curriculum_case")
        from app.curriculum.docx_reader import load_curriculum_docx

        document = _object(record["docx"], required={"path", "tables"}, optional=set(), label="docx input")
        metadata = {key: value for key, value in record.items() if key not in {"docx", "source_id"}}
        # Check metadata before accessing any explicitly referenced local file.
        normalize_curriculum_version(source_id=record["source_id"], course_records=(), **metadata)
        result = load_curriculum_docx(
            resolve_local_input(document["path"], directory=directory, label="docx input"),
            source_id=record["source_id"], tables=document["tables"],
        )
        return result.to_version(**metadata)
    return normalize_curriculum_version(**record)


@dataclass(frozen=True, slots=True)
class CurriculumCase:
    data_source: DataSource
    old: CurriculumVersion
    new: CurriculumVersion
    completed: tuple[CompletedCourse, ...]
    completed_source_id: str
    completed_complete: bool = False
    completed_completeness_evidence: str | None = None
    rules: MatchingRules | None = None
    recognitions: tuple[ConfirmedRecognition, ...] = ()
    missing_requirements: tuple[ConfirmedMissingRequirement, ...] = ()
    priority_policy: PriorityPolicy | None = None
    elective_selections: tuple[ConfirmedElectiveSelection, ...] = ()
    makeup_scope: MakeupScope | None = None
    confirmed_scope_decisions: tuple[ConfirmedScopeDecision, ...] = ()
    confirmed_group_scope_decisions: tuple[ConfirmedGroupScopeDecision, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.data_source, DataSource):
            raise CurriculumNormalizationError("case: expected an explicit data source")
        if not isinstance(self.old, CurriculumVersion) or not isinstance(self.new, CurriculumVersion):
            raise CurriculumNormalizationError("case: expected curriculum versions")
        if not isinstance(self.completed_source_id, str) or not self.completed_source_id.strip():
            raise CurriculumNormalizationError("completed_source_id: expected a nonempty string")
        if self.priority_policy is not None:
            if not isinstance(self.priority_policy, PriorityPolicy):
                raise CurriculumNormalizationError("priority_policy: unexpected type")
            if self.priority_policy.target_version_id != self.new.version_id:
                raise CurriculumNormalizationError("priority policy: target version mismatch")
        if self.makeup_scope is not None:
            if not isinstance(self.makeup_scope, MakeupScope):
                raise CurriculumNormalizationError("makeup_scope: unexpected type")
            if self.makeup_scope.target_version_id != self.new.version_id:
                raise CurriculumNormalizationError("makeup scope: target version mismatch")
        for key, kind in (("completed", CompletedCourse), ("recognitions", ConfirmedRecognition),
                          ("missing_requirements", ConfirmedMissingRequirement),
                          ("elective_selections", ConfirmedElectiveSelection)):
            values = _sequence(getattr(self, key), key)
            if any(not isinstance(value, kind) for value in values):
                raise CurriculumNormalizationError(f"{key}: unexpected item type")
            object.__setattr__(self, key, values)
        # Validate scope, rules and explicit decisions even before a Provider is used.
        self.build_diff()
        sources = (self.old.source_id, self.new.source_id, self.completed_source_id)
        evidence = tuple(decision.evidence for decision in (
            *self.recognitions, *self.missing_requirements, *self.elective_selections,
        ))
        evidence += tuple(value for value in (
            self.old.completeness_evidence, self.new.completeness_evidence,
            self.completed_completeness_evidence,
        ) if value is not None)
        evidence += tuple(record.id_match_source for record in self.completed if record.id_match_source is not None)
        evidence += tuple(record.source_record for record in self.completed)
        evidence += tuple(entry.source_record for version in (self.old, self.new) for entry in version.courses)
        evidence += tuple(group.source_record for version in (self.old, self.new) for group in version.groups)
        if self.rules is not None:
            evidence += (self.rules.evidence,)
        if self.priority_policy is not None:
            evidence += (self.priority_policy.evidence,)
        if self.makeup_scope is not None:
            evidence += (self.makeup_scope.evidence,)
        evidence += tuple(decision.evidence for decision in self.confirmed_scope_decisions)
        evidence += tuple(decision.evidence for decision in self.confirmed_group_scope_decisions)
        if self.data_source is DataSource.REAL and any("mock://" in value.lower() for value in sources + evidence):
            raise CurriculumNormalizationError("case: explicit Mock sources cannot be labeled real")

    def build_diff(self) -> CurriculumDiff:
        return build_curriculum_diff(
            self.old, self.new, self.completed,
            completed_source_id=self.completed_source_id,
            completed_complete=self.completed_complete,
            completed_completeness_evidence=self.completed_completeness_evidence,
            rules=self.rules, recognitions=self.recognitions,
            missing_requirements=self.missing_requirements,
            elective_selections=self.elective_selections,
            makeup_scope=self.makeup_scope,
            confirmed_scope_decisions=self.confirmed_scope_decisions,
            confirmed_group_scope_decisions=self.confirmed_group_scope_decisions,
        )


def normalize_curriculum_case(payload: object) -> CurriculumCase:
    """Validate structured facts without opening files or resolving references."""
    return _normalize_case(payload)


def _normalize_case(payload: object, *, directory: Path | None = None) -> CurriculumCase:
    record = _object(payload, required={"data_source", "old", "new", "completed"},
                     optional={"rules", "recognitions", "missing_requirements", "priority_policy",
                               "elective_selections", "makeup_scope", "confirmed_scope_decisions",
                               "confirmed_group_scope_decisions"}, label="case")
    try:
        data_source = DataSource(record["data_source"])
    except (ValueError, TypeError):
        raise CurriculumNormalizationError("data_source: expected mock or real") from None
    old, new = _version(record["old"], directory=directory), _version(record["new"], directory=directory)
    completed = _object(record["completed"], required={"source_id"},
                        optional={"complete", "completeness_evidence", "records", "xlsx"}, label="completed")
    if ("records" in completed) == ("xlsx" in completed):
        raise CurriculumNormalizationError("completed: provide records or xlsx exclusively")
    if "xlsx" in completed:
        if directory is None:
            raise CurriculumNormalizationError("completed: file inputs require load_curriculum_case")
        from app.curriculum.xlsx_reader import load_completed_courses_xlsx

        workbook = _object(completed["xlsx"], required={"path"}, optional={"sheet_name"}, label="xlsx input")
        rows = load_completed_courses_xlsx(
            resolve_local_input(workbook["path"], directory=directory, label="xlsx input"),
            source_id=completed["source_id"], sheet_name=workbook.get("sheet_name", "已修课程_脱敏"),
        )
    else:
        rows = normalize_completed_courses(completed["records"], source_id=completed["source_id"])
    rules = None
    if record.get("rules") is not None:
        rules_record = _object(record["rules"], required={"target_version_id", "completed_source_id", "evidence"},
                               optional={"allow_exact_match", "allow_confirmed_absence"}, label="rules")
        rules = MatchingRules(**rules_record)
    priority_policy = None
    if record.get("priority_policy") is not None:
        policy_record = _object(record["priority_policy"], required={"target_version_id", "evidence"},
                                optional={"deadline_first"}, label="priority_policy")
        priority_policy = PriorityPolicy(**policy_record)
    recognitions = _decisions(record.get("recognitions", ()), ConfirmedRecognition,
                             {"target_version_id", "target_course_id", "completed_source_id",
                              "completed_source_record", "recognized_credit", "evidence"}, "recognitions")
    missing = _decisions(record.get("missing_requirements", ()), ConfirmedMissingRequirement,
                         {"target_version_id", "target_course_id", "completed_source_id", "evidence"},
                         "missing_requirements")
    selections = _decisions(record.get("elective_selections", ()), ConfirmedElectiveSelection,
                            {"target_version_id", "group_id", "course_ids", "evidence"},
                            "elective_selections")
    makeup_scope = None
    if record.get("makeup_scope") is not None:
        scope_record = _object(record["makeup_scope"],
                               required={"target_version_id", "as_of_term", "evidence"},
                               optional=set(), label="makeup_scope")
        makeup_scope = MakeupScope(**scope_record)
    confirmed_scope = _decisions(
        record.get("confirmed_scope_decisions", ()), ConfirmedScopeDecision,
        {"target_version_id", "target_source_record", "target_course_id", "decision", "evidence"},
        "confirmed_scope_decisions",
    )
    confirmed_group_scope = _decisions(
        record.get("confirmed_group_scope_decisions", ()), ConfirmedGroupScopeDecision,
        {"target_version_id", "group_id", "historical_minimum_credit", "evidence"},
        "confirmed_group_scope_decisions",
    )
    return CurriculumCase(
        data_source=data_source, old=old, new=new, completed=rows,
        completed_source_id=completed["source_id"], completed_complete=completed.get("complete", False),
        completed_completeness_evidence=completed.get("completeness_evidence"),
        rules=rules, recognitions=recognitions, missing_requirements=missing,
        priority_policy=priority_policy, elective_selections=selections,
        makeup_scope=makeup_scope,
        confirmed_scope_decisions=confirmed_scope,
        confirmed_group_scope_decisions=confirmed_group_scope,
    )


def load_curriculum_case(path: str | Path) -> CurriculumCase:
    payload = load_json_input(path)
    try:
        directory = Path(path).resolve().parent
    except (OSError, ValueError, RuntimeError):
        raise CurriculumNormalizationError("case: invalid input path") from None
    return _normalize_case(payload, directory=directory)


@dataclass(frozen=True, slots=True)
class CurriculumCaseProvider:
    case: CurriculumCase
    _diff: CurriculumDiff = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.case, CurriculumCase):
            raise CurriculumNormalizationError("case: expected a CurriculumCase")
        object.__setattr__(self, "_diff", self.case.build_diff())

    def get_makeup_tasks(self) -> list[MakeupTask]:
        return CurriculumResultProvider(self._diff).get_makeup_tasks()

    def get_academic_analysis(self) -> AcademicAnalysis:
        return analyze_academic_path(self._diff, priority_policy=self.case.priority_policy)

    def get_curriculum_diff(self) -> CurriculumDiff:
        """Return immutable internal facts, including unresolved group gaps."""
        return self._diff

    def get_validation_summary(self) -> dict:
        """Inspect blocked cases using counts and fixed diagnostics only."""
        from collections import Counter

        error = None
        try:
            tasks = self.get_makeup_tasks()
        except CurriculumNormalizationError as exc:
            error = str(exc)
            tasks = None
        analysis = self.get_academic_analysis()
        return {
            "data_source": self.case.data_source.value,
            "target_records": len(self.case.new.courses),
            "completed_records": len(self.case.completed),
            "group_gap_count": len(self._diff.group_gaps),
            "projection_ready": error is None,
            "projection_error": error,
            "makeup_task_count": len(tasks) if tasks is not None else None,
            "status_counts": dict(Counter(task.status.value for task in tasks)) if tasks is not None else None,
            "academic_issue_counts": dict(Counter(issue.code for issue in analysis.issues)),
            "dependency_order_available": analysis.dependency_order is not None,
            "priority_order_available": analysis.priority_order is not None,
        }


def load_demo_case() -> CurriculumCase:
    case = load_curriculum_case(DEMO_CASE_PATH)
    if case.data_source is not DataSource.MOCK or any(not source.startswith("mock://") for source in (
        case.old.source_id, case.new.source_id, case.completed_source_id,
    )):
        raise CurriculumNormalizationError("demo: only artificial Mock cases may be displayed")
    return case


def demo_output() -> dict:
    provider = CurriculumCaseProvider(load_demo_case())
    return {"data_source": "mock", "makeup_tasks": [
        task.model_dump(mode="json") for task in provider.get_makeup_tasks()
    ]}
