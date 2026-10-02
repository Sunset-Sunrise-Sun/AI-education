"""Load a local structured case without exposing private records."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.curriculum.academic import AcademicAnalysis, PriorityPolicy, analyze_academic_path
from app.curriculum.completed_courses import CompletedCourse, normalize_completed_courses
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CurriculumDiff,
    CurriculumResultProvider,
    MatchingRules,
    build_curriculum_diff,
)
from app.curriculum.requirements import CurriculumVersion, normalize_curriculum_version
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


def _version(value: object) -> CurriculumVersion:
    record = _object(value, required={"version_id", "major", "cohort", "source_id", "course_records"},
                     optional={"group_records", "complete", "completeness_evidence", "total_credit",
                               "practice_credit", "study_years"}, label="curriculum")
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
        for key, kind in (("completed", CompletedCourse), ("recognitions", ConfirmedRecognition),
                          ("missing_requirements", ConfirmedMissingRequirement)):
            values = _sequence(getattr(self, key), key)
            if any(not isinstance(value, kind) for value in values):
                raise CurriculumNormalizationError(f"{key}: unexpected item type")
            object.__setattr__(self, key, values)
        # Validate scope, rules and explicit decisions even before a Provider is used.
        self.build_diff()
        sources = (self.old.source_id, self.new.source_id, self.completed_source_id)
        evidence = tuple(decision.evidence for decision in (*self.recognitions, *self.missing_requirements))
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
        )


def normalize_curriculum_case(payload: object) -> CurriculumCase:
    record = _object(payload, required={"data_source", "old", "new", "completed"},
                     optional={"rules", "recognitions", "missing_requirements", "priority_policy"}, label="case")
    try:
        data_source = DataSource(record["data_source"])
    except (ValueError, TypeError):
        raise CurriculumNormalizationError("data_source: expected mock or real") from None
    old, new = _version(record["old"]), _version(record["new"])
    completed = _object(record["completed"], required={"source_id", "records"},
                        optional={"complete", "completeness_evidence"}, label="completed")
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
    return CurriculumCase(
        data_source, old, new, rows, completed["source_id"],
        completed.get("complete", False), completed.get("completeness_evidence"),
        rules, recognitions, missing, priority_policy,
    )


def load_curriculum_case(path: str | Path) -> CurriculumCase:
    if not isinstance(path, (str, Path)):
        raise CurriculumNormalizationError("case: invalid input path")

    def invalid_constant(value: str):
        raise CurriculumNormalizationError("case: non-finite JSON number")

    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CurriculumNormalizationError("case: duplicate JSON field")
            result[key] = value
        return result

    try:
        raw = Path(path).read_bytes()
        if len(raw) > 8 * 1024 * 1024:
            raise CurriculumNormalizationError("case: file size limit exceeded")
        payload = json.loads(raw.decode("utf-8"), parse_constant=invalid_constant, object_pairs_hook=unique_fields)
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise CurriculumNormalizationError("case: invalid or unreadable JSON") from None
    return normalize_curriculum_case(payload)


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
