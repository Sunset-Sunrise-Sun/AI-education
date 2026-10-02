"""Normalize completed-course facts without making recognition decisions.

This internal model is deliberately separate from the public ``Course`` model.
It retains the actual semester, pass result, unresolved course identity, and
source references. It does not deduplicate attempts, infer missing course IDs,
recognize credits, generate makeup tasks, or determine school policy.

Only explicitly listed record fields are accepted. Free-text fields must have
been sanitized by the caller; this module does not claim to anonymize text.
Validation errors contain field names and row numbers, never record values.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from app.curriculum.errors import CurriculumNormalizationError

__all__ = ["CompletedCourse", "CourseIdStatus", "normalize_completed_courses"]


class CourseIdStatus(str, Enum):
    """Whether the supplied course identity has supporting match evidence."""

    CONFIRMED = "confirmed"
    PENDING = "pending"


_STATUS_LABELS = {
    "confirmed": CourseIdStatus.CONFIRMED,
    "已确认": CourseIdStatus.CONFIRMED,
    "pending": CourseIdStatus.PENDING,
    "待确认": CourseIdStatus.PENDING,
}

_REQUIRED_RECORD_FIELDS = (
    "course_id",
    "course_name",
    "credit",
    "semester",
    "passed",
    "course_type",
    "course_id_status",
    "id_match_source",
)
_ALLOWED_RECORD_FIELDS = frozenset(_REQUIRED_RECORD_FIELDS) | {
    "source_record",
    "notes",
}


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CurriculumNormalizationError(f"{field}: expected a string or null")
    return value if value.strip() else None


def _normalize_status(value: object) -> CourseIdStatus:
    if isinstance(value, CourseIdStatus):
        return value
    if isinstance(value, str) and value.strip() in _STATUS_LABELS:
        return _STATUS_LABELS[value.strip()]
    raise CurriculumNormalizationError("course_id_status: unsupported status")


def _normalize_credit(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurriculumNormalizationError("credit: expected a finite nonnegative number")
    try:
        credit = float(value)
    except (OverflowError, TypeError, ValueError):
        raise CurriculumNormalizationError(
            "credit: expected a finite nonnegative number"
        ) from None
    if not math.isfinite(credit) or credit < 0:
        raise CurriculumNormalizationError("credit: expected a finite nonnegative number")
    return credit


@dataclass(frozen=True, slots=True)
class CompletedCourse:
    """Immutable facts about one completed-course record or course attempt.

    All constructor paths validate the same invariants. Pending identity is
    represented by ``course_id=None``; a nonempty pending ID is rejected rather
    than discarded. Confirmation requires an explicit ID and match source, but
    it does not imply formal course equivalence or credit recognition.
    """

    course_id: str | None
    course_name: str
    credit: float
    semester: str
    passed: bool
    course_type: str | None
    course_id_status: CourseIdStatus
    id_match_source: str | None
    source_id: str
    source_record: str
    notes: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.course_name, "course_name")
        _require_text(self.semester, "semester")
        _require_text(self.source_id, "source_id")
        _require_text(self.source_record, "source_record")
        if not isinstance(self.passed, bool):
            raise CurriculumNormalizationError("passed: expected a boolean")

        status = _normalize_status(self.course_id_status)
        course_id = _optional_text(self.course_id, "course_id")
        match_source = _optional_text(self.id_match_source, "id_match_source")
        if status is CourseIdStatus.CONFIRMED:
            _require_text(course_id, "course_id")
            _require_text(match_source, "id_match_source")
        elif course_id is not None:
            raise CurriculumNormalizationError(
                "course_id: pending identity must not contain a course ID"
            )

        object.__setattr__(self, "credit", _normalize_credit(self.credit))
        object.__setattr__(self, "course_id", course_id)
        object.__setattr__(self, "course_type", _optional_text(self.course_type, "course_type"))
        object.__setattr__(self, "course_id_status", status)
        object.__setattr__(self, "id_match_source", match_source)
        object.__setattr__(self, "notes", _optional_text(self.notes, "notes"))


def normalize_completed_courses(
    records: Sequence[Mapping[str, object]], *, source_id: str
) -> tuple[CompletedCourse, ...]:
    """Return every supplied record in its original order, including repeats.

    Required keys include nullable ``course_id``, ``course_type``, and
    ``id_match_source``. Optional keys are ``source_record`` and ``notes``.
    Source references default to ``row:1``, ``row:2``, and so on when omitted.
    Source IDs are supplied once by the caller, not read from student rows.
    One invalid row fails the whole operation without skipping records.
    """

    _require_text(source_id, "source_id")
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(records, Sequence):
        raise CurriculumNormalizationError("records: expected a sequence of mappings")

    normalized: list[CompletedCourse] = []
    for row_number, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise CurriculumNormalizationError(f"row {row_number}: expected a mapping")
        if any(key not in _ALLOWED_RECORD_FIELDS for key in record):
            # Unknown keys themselves may contain identifying information.
            raise CurriculumNormalizationError(f"row {row_number}: unexpected record field")
        for field in _REQUIRED_RECORD_FIELDS:
            if field not in record:
                raise CurriculumNormalizationError(f"row {row_number}: missing field {field}")

        try:
            normalized.append(
                CompletedCourse(
                    course_id=record["course_id"],
                    course_name=record["course_name"],
                    credit=record["credit"],
                    semester=record["semester"],
                    passed=record["passed"],
                    course_type=record["course_type"],
                    course_id_status=record["course_id_status"],
                    id_match_source=record["id_match_source"],
                    source_id=source_id,
                    source_record=record.get("source_record", f"row:{row_number}"),
                    notes=record.get("notes"),
                )
            )
        except CurriculumNormalizationError as exc:
            raise CurriculumNormalizationError(f"row {row_number}: {exc}") from None

    return tuple(normalized)
