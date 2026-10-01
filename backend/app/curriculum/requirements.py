"""Immutable, internal curriculum requirements from explicit structured facts.

These objects retain curriculum context and unknown values independently of
the public Course and MakeupTask contracts. No document parsing, recognition,
dependency inference, semester-text conversion, or makeup decision occurs.
Callers must sanitize text and provide verified source references. Error
messages identify fields and row numbers without echoing input values.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from app.curriculum.errors import CurriculumNormalizationError

__all__ = [
    "RequirementKind",
    "CurriculumCourse",
    "CurriculumGroup",
    "CurriculumVersion",
    "normalize_curriculum_version",
]


class RequirementKind(str, Enum):
    """Explicit requirement classification, not inferred from course type."""

    REQUIRED = "required"
    ELECTIVE = "elective"
    UNKNOWN = "unknown"


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CurriculumNormalizationError(f"{field}: expected a string or null")
    return value if value.strip() else None


def _nonnegative_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurriculumNormalizationError(f"{field}: expected a finite nonnegative number")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        raise CurriculumNormalizationError(
            f"{field}: expected a finite nonnegative number"
        ) from None
    if not math.isfinite(number) or number < 0:
        raise CurriculumNormalizationError(f"{field}: expected a finite nonnegative number")
    return number


def _optional_semester(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CurriculumNormalizationError(f"{field}: expected a positive integer or null")
    return value


def _sequence(value: object, field: str) -> Sequence:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CurriculumNormalizationError(f"{field}: expected a sequence")
    return value


def _requirement(value: object) -> RequirementKind:
    if isinstance(value, RequirementKind):
        return value
    if isinstance(value, str):
        try:
            return RequirementKind(value)
        except ValueError:
            pass
    raise CurriculumNormalizationError("requirement: unsupported classification")


def _prerequisites(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    material = tuple(_sequence(value, "prerequisites"))
    for item in material:
        _required_text(item, "prerequisites")
    if len(set(material)) != len(material):
        raise CurriculumNormalizationError("prerequisites: duplicate course references")
    return material


@dataclass(frozen=True, slots=True)
class CurriculumCourse:
    """One source entry, retaining curriculum-specific requirement context.

    ``prerequisites=None`` means unknown; ``()`` explicitly means no
    prerequisites. Integer semester fields are accepted only as supplied facts.
    A term description is never converted into those fields automatically.
    """

    course_id: str
    course_name: str
    credit: float
    requirement: RequirementKind
    source_record: str
    course_type: str | None = None
    group_id: str | None = None
    recommended_term_text: str | None = None
    prerequisites: tuple[str, ...] | None = None
    recommended_semester: int | None = None
    deadline_semester: int | None = None

    def __post_init__(self) -> None:
        for field in ("course_id", "course_name", "source_record"):
            _required_text(getattr(self, field), field)
        object.__setattr__(self, "credit", _nonnegative_number(self.credit, "credit"))
        object.__setattr__(self, "requirement", _requirement(self.requirement))
        for field in ("course_type", "group_id", "recommended_term_text"):
            object.__setattr__(self, field, _optional_text(getattr(self, field), field))
        object.__setattr__(self, "prerequisites", _prerequisites(self.prerequisites))
        for field in ("recommended_semester", "deadline_semester"):
            object.__setattr__(self, field, _optional_semester(getattr(self, field), field))


@dataclass(frozen=True, slots=True)
class CurriculumGroup:
    """An explicit course group whose minimum credit may remain unknown."""

    group_id: str
    name: str
    minimum_credit: float | None
    source_record: str

    def __post_init__(self) -> None:
        for field in ("group_id", "name", "source_record"):
            _required_text(getattr(self, field), field)
        if self.minimum_credit is not None:
            object.__setattr__(
                self, "minimum_credit", _nonnegative_number(self.minimum_credit, "minimum_credit")
            )


@dataclass(frozen=True, slots=True)
class CurriculumVersion:
    """A source-backed version with an explicit completeness declaration.

    Course IDs may occur repeatedly because source entries may carry distinct
    context. Unique source-record references prevent accidental overwriting.
    Completeness evidence is supplied by the caller; counts do not prove it.
    """

    version_id: str
    major: str
    cohort: str
    source_id: str
    courses: tuple[CurriculumCourse, ...]
    groups: tuple[CurriculumGroup, ...] = ()
    complete: bool = False
    completeness_evidence: str | None = None
    total_credit: float | None = None
    practice_credit: float | None = None
    study_years: int | None = None

    def __post_init__(self) -> None:
        for field in ("version_id", "major", "cohort", "source_id"):
            _required_text(getattr(self, field), field)
        for field in ("total_credit", "practice_credit"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _nonnegative_number(value, field))
        object.__setattr__(self, "study_years", _optional_semester(self.study_years, "study_years"))
        if not isinstance(self.complete, bool):
            raise CurriculumNormalizationError("complete: expected a boolean")
        evidence = _optional_text(self.completeness_evidence, "completeness_evidence")
        if self.complete and evidence is None:
            raise CurriculumNormalizationError(
                "completeness_evidence: a complete version requires explicit evidence"
            )

        courses = tuple(_sequence(self.courses, "courses"))
        groups = tuple(_sequence(self.groups, "groups"))
        group_ids: set[str] = set()
        for row, group in enumerate(groups, start=1):
            if not isinstance(group, CurriculumGroup):
                raise CurriculumNormalizationError(f"groups row {row}: expected a CurriculumGroup")
            if group.group_id in group_ids:
                raise CurriculumNormalizationError(f"groups row {row}: group_id: duplicate reference")
            group_ids.add(group.group_id)

        source_records: set[str] = set()
        for row, course in enumerate(courses, start=1):
            if not isinstance(course, CurriculumCourse):
                raise CurriculumNormalizationError(f"courses row {row}: expected a CurriculumCourse")
            if course.source_record in source_records:
                raise CurriculumNormalizationError(f"courses row {row}: source_record: duplicate reference")
            source_records.add(course.source_record)
            if course.group_id is not None and course.group_id not in group_ids:
                raise CurriculumNormalizationError(f"courses row {row}: group_id: unknown reference")

        object.__setattr__(self, "courses", courses)
        object.__setattr__(self, "groups", groups)
        object.__setattr__(self, "completeness_evidence", evidence)


_COURSE_REQUIRED = ("course_id", "course_name", "credit", "requirement", "source_record")
_COURSE_ALLOWED = frozenset(_COURSE_REQUIRED) | {
    "course_type", "group_id", "recommended_term_text", "prerequisites",
    "recommended_semester", "deadline_semester",
}
_GROUP_REQUIRED = ("group_id", "name", "minimum_credit", "source_record")
_GROUP_ALLOWED = frozenset(_GROUP_REQUIRED)


def _normalize_records(
    records: object, *, label: str, required: tuple[str, ...], allowed: frozenset[str], model: type
) -> tuple:
    normalized = []
    for row, record in enumerate(_sequence(records, label), start=1):
        if not isinstance(record, Mapping):
            raise CurriculumNormalizationError(f"{label} row {row}: expected a mapping")
        if any(key not in allowed for key in record):
            # Even unknown key names can contain private source text.
            raise CurriculumNormalizationError(f"{label} row {row}: unexpected record field")
        for field in required:
            if field not in record:
                raise CurriculumNormalizationError(f"{label} row {row}: missing field {field}")
        try:
            normalized.append(model(**record))
        except CurriculumNormalizationError as exc:
            raise CurriculumNormalizationError(f"{label} row {row}: {exc}") from None
    return tuple(normalized)


def normalize_curriculum_version(
    *,
    version_id: str,
    major: str,
    cohort: str,
    source_id: str,
    course_records: Sequence[Mapping[str, object]],
    group_records: Sequence[Mapping[str, object]] = (),
    complete: bool = False,
    completeness_evidence: str | None = None,
    total_credit: float | None = None,
    practice_credit: float | None = None,
    study_years: int | None = None,
) -> CurriculumVersion:
    """Normalize explicit records without parsing files or assuming rules.

    Course record keys use the CurriculumCourse field names; group record
    keys use CurriculumGroup field names. Unknown fields fail the whole import.
    Empty courses are permitted and are never inferred to be complete.
    """

    # Validate metadata before inspecting any source rows.
    CurriculumVersion(
        version_id=version_id, major=major, cohort=cohort, source_id=source_id,
        courses=(), complete=complete, completeness_evidence=completeness_evidence,
        total_credit=total_credit, practice_credit=practice_credit, study_years=study_years,
    )
    groups = _normalize_records(
        group_records, label="groups", required=_GROUP_REQUIRED,
        allowed=_GROUP_ALLOWED, model=CurriculumGroup,
    )
    courses = _normalize_records(
        course_records, label="courses", required=_COURSE_REQUIRED,
        allowed=_COURSE_ALLOWED, model=CurriculumCourse,
    )
    return CurriculumVersion(
        version_id=version_id, major=major, cohort=cohort, source_id=source_id,
        courses=courses, groups=groups, complete=complete,
        completeness_evidence=completeness_evidence,
        total_credit=total_credit, practice_credit=practice_credit, study_years=study_years,
    )
