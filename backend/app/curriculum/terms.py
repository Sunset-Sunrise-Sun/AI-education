"""Internal, strict academic-term parsing and historical-scope classification.

This module decides **only** whether a target curriculum entry's *recommended
arrangement term* falls at or before an explicitly supplied "as of" term.

Hard boundaries:

- No file parsing, no curriculum matching, no makeup decision.
- A recommended term is never treated as a prerequisite, a deadline, a school
  recognition rule, or a transfer-student makeup policy.
- No inference from the current system date; the as-of term must be supplied
  explicitly by the caller and carry its own evidence.
- Ranges, unknown values, blanks and malformed text are never guessed, and no
  input value is ever echoed back in an error message.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.requirements import CurriculumCourse, CurriculumVersion

__all__ = [
    "SCOPE_FUTURE",
    "SCOPE_HISTORICAL",
    "SCOPE_UNRESOLVED",
    "AcademicTerm",
    "ConfirmedScopeDecision",
    "ScopeDecision",
    "classify_term",
    "parse_academic_term",
    "scope_decisions",
    "validate_confirmed_scope_decisions",
]

# Only the single, confirmed canonical form is accepted: YYYY-1 / YYYY-2.
_TERM_PATTERN = re.compile(r"^(?P<year>[0-9]{4})-(?P<half>[12])$")
_MIN_YEAR = 1900
_MAX_YEAR = 9999

# Classification buckets. These are internal facts, never public contract values.
SCOPE_HISTORICAL = "historical"
SCOPE_FUTURE = "future"
SCOPE_UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class AcademicTerm:
    """A single, unambiguously parsed ``YYYY-H`` academic term."""

    year: int
    half: int

    def __post_init__(self) -> None:
        if isinstance(self.year, bool) or not isinstance(self.year, int):
            raise CurriculumNormalizationError("term: invalid academic year")
        if isinstance(self.half, bool) or not isinstance(self.half, int):
            raise CurriculumNormalizationError("term: invalid academic half")
        if not (_MIN_YEAR <= self.year <= _MAX_YEAR) or self.half not in (1, 2):
            raise CurriculumNormalizationError("term: invalid academic term")

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.year, self.half)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.half}"


def parse_academic_term(value: object) -> AcademicTerm | None:
    """Parse one strict ``YYYY-H`` term; return ``None`` when not interpretable.

    ``None`` means "this text is not a confirmed canonical term". It never means
    "no term requirement", and it is never silently defaulted. Ranges such as
    ``2025-1~2025-2``, the literal ``未知``/``空`` markers, blanks and any other
    shape all return ``None`` so that callers must fail closed instead of
    guessing an arrangement term.
    """

    if not isinstance(value, str):
        return None
    # Surrounding whitespace is rejected rather than trimmed: "2025-1 " is not a
    # confirmed value and must not be quietly normalized into one.
    match = _TERM_PATTERN.match(value)
    if match is None:
        return None
    return AcademicTerm(year=int(match.group("year")), half=int(match.group("half")))


def classify_term(recommended: AcademicTerm | None, as_of: AcademicTerm) -> str:
    """Classify one parsed recommended term against the explicit as-of term.

    Boundary rule: a term equal to ``as_of`` is **historical** (inclusive), so a
    course recommended for the as-of term itself is still a candidate makeup gap.

    An unparseable or absent recommended term is ``unresolved``: it is never
    classified as historical or future, because that would be a guess.
    """

    if not isinstance(as_of, AcademicTerm):
        raise CurriculumNormalizationError("scope: expected a parsed as-of term")
    if recommended is None:
        return SCOPE_UNRESOLVED
    return SCOPE_HISTORICAL if recommended.sort_key <= as_of.sort_key else SCOPE_FUTURE


@dataclass(frozen=True, slots=True)
class ConfirmedScopeDecision:
    """An explicit human range decision for ONE target requirement entry.

    This exists because real plan sources express some arrangement terms in a
    form no parser can safely interpret: ``2025-1~2025-2``, ``2025-1~2028-2``,
    ``未知``, ``空``, a missing value, or malformed text. Failing closed is
    correct, but without this entry point a real case could never be unblocked.

    Key boundaries:

    - It is keyed by ``target_source_record`` (the concrete requirement entry in
      the target version), **not** by ``course_id``: one course may appear in
      several contexts. ``target_course_id`` is kept only for diagnostics.
    - It may ONLY discharge an ``unresolved`` classification. It must never
      silently override an unambiguous single-term source fact; a decision that
      targets an auto-resolvable entry is rejected as a conflict.
    - Its ``evidence`` is an auditable reference, never a school transfer policy,
      a deadline, or a prerequisite.
    """

    target_version_id: str
    target_source_record: str
    target_course_id: str
    decision: str
    evidence: str

    def __post_init__(self) -> None:
        for name in ("target_version_id", "target_source_record", "target_course_id", "evidence"):
            _text(getattr(self, name), name)
        if self.decision not in (SCOPE_HISTORICAL, SCOPE_FUTURE):
            raise CurriculumNormalizationError(
                "confirmed scope decision: expected historical or future"
            )


def _text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")


def validate_confirmed_scope_decisions(
    version: CurriculumVersion, values: Sequence[ConfirmedScopeDecision],
) -> dict[str, ConfirmedScopeDecision]:
    """Validate human range decisions against the target version.

    Rejects duplicate decisions, unknown entries and decisions that point at a
    different curriculum version. Returns a mapping keyed by the target
    requirement entry's ``source_record``.
    """

    if not isinstance(version, CurriculumVersion):
        raise CurriculumNormalizationError("confirmed scope decision: expected a curriculum version")
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CurriculumNormalizationError("confirmed_scope_decisions: expected a sequence")
    by_record: dict[str, ConfirmedScopeDecision] = {}
    known_records = {course.source_record: course for course in version.courses}
    for value in values:
        if not isinstance(value, ConfirmedScopeDecision):
            raise CurriculumNormalizationError("confirmed scope decision: unexpected entry type")
        if value.target_version_id != version.version_id:
            raise CurriculumNormalizationError(
                "confirmed scope decision: target version is outside the supplied curriculum"
            )
        course = known_records.get(value.target_source_record)
        if course is None:
            raise CurriculumNormalizationError(
                "confirmed scope decision: target entry is not in the supplied curriculum"
            )
        if course.course_id != value.target_course_id:
            raise CurriculumNormalizationError(
                "confirmed scope decision: target entry does not match the stated course"
            )
        if value.target_source_record in by_record:
            raise CurriculumNormalizationError(
                "confirmed scope decision: duplicate decision for the same target entry"
            )
        by_record[value.target_source_record] = value
    return by_record


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """One target course's scope classification, retained for honest reporting."""

    course_id: str
    bucket: str
    recommended_term_text: str | None
    evidence: str | None = None
    source_record: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.course_id, str) or not self.course_id.strip():
            raise CurriculumNormalizationError("scope decision: expected a course reference")
        if self.bucket not in (SCOPE_HISTORICAL, SCOPE_FUTURE, SCOPE_UNRESOLVED):
            raise CurriculumNormalizationError("scope decision: unsupported classification")

    @property
    def unresolved(self) -> bool:
        return self.bucket == SCOPE_UNRESOLVED


def scope_decisions(
    version: CurriculumVersion,
    as_of_text: str,
    confirmed: Sequence[ConfirmedScopeDecision] = (),
) -> tuple[ScopeDecision, ...]:
    """Classify every supplied target entry against an explicit as-of term.

    The as-of term itself must already be a confirmed canonical term; an
    uninterpretable as-of value fails closed instead of falling back to any
    other term (and never to the system date).

    An entry the parser can resolve keeps its automatic classification. Only an
    entry that lands in ``unresolved`` may be discharged by a matching explicit
    ``ConfirmedScopeDecision``; a decision aimed at an auto-resolvable entry is
    rejected as a conflict with the source fact rather than silently applied.
    """

    if not isinstance(version, CurriculumVersion):
        raise CurriculumNormalizationError("scope: expected a curriculum version")
    as_of = parse_academic_term(as_of_text)
    if as_of is None:
        raise CurriculumNormalizationError(
            "scope: as_of_term must be a confirmed YYYY-H term"
        )
    confirmed_by_record = validate_confirmed_scope_decisions(version, confirmed)
    applied: set[str] = set()
    decisions = []
    for course in version.courses:
        if not isinstance(course, CurriculumCourse):
            raise CurriculumNormalizationError("scope: unexpected curriculum entry")
        bucket = classify_term(parse_academic_term(course.recommended_term_text), as_of)
        evidence = None
        if bucket == SCOPE_UNRESOLVED and course.source_record in confirmed_by_record:
            decision = confirmed_by_record[course.source_record]
            bucket = decision.decision
            evidence = decision.evidence
            applied.add(course.source_record)
        decisions.append(ScopeDecision(
            course_id=course.course_id,
            bucket=bucket,
            recommended_term_text=course.recommended_term_text,
            evidence=evidence,
            source_record=course.source_record,
        ))
    unapplied = set(confirmed_by_record) - applied
    if unapplied:
        # The entry already had an unambiguous term: the source fact wins and
        # the conflicting human decision must not be quietly ignored.
        raise CurriculumNormalizationError(
            "confirmed scope decision: conflicts with an unambiguous source term"
        )
    return tuple(decisions)
