"""What a student says about a transcript record's course identity. **Not a decision.**

A :class:`StudentIdentityAssertion` records one of three things a student may say about
one transcript row:

- ``selected`` — "this row is this candidate";
- ``rejected`` — "none of the candidates is right";
- ``deferred`` — "I am not deciding yet".

It is deliberately **not** a recognition. The differences are structural, not stylistic:

- it carries **no** credit of any kind, so it can never express 学分认定;
- it never produces, or converts into, ``ConfirmedRecognition`` /
  ``ConfirmedMissingRequirement`` / ``ConfirmedElectiveSelection``;
- it does **not** touch ``CompletedCourse.course_id_status``. That value means
  "authenticated identity" to the matching layer, so writing a student's pick there would
  let the existing matcher treat a self-declaration as authoritative. Assertions live
  outside the completed-course records entirely;
- it does **not** call ``build_curriculum_diff``, change any ``MakeupTask``, or satisfy
  any requirement.

A student picking a candidate means only that they believe that row is that course. It is
**not** course equivalence and it is **not** evidence that any target requirement is met.
Turning an assertion into a recognition stays a separate, authorised act with its own
evidence, which this module does not implement.

Validation happens against the candidate sets **actually produced for this transcript and
this catalogue version**, so an assertion can only name a record and an entry the caller
was really shown.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.identity_candidates import (
    IdentityCandidate,
    IdentityCandidateSet,
    IdentityStatus,
)

__all__ = [
    "StudentIdentityDecision",
    "StudentIdentityAssertion",
    "validate_identity_assertions",
    "assertions_for_record",
]

#: The only source an assertion may claim. A student declares; they do not authorise.
STUDENT_ASSERTION_SOURCE = "student-declaration"


class StudentIdentityDecision(str, Enum):
    """What the student said about one transcript record. Never a recognition outcome."""

    SELECTED = "selected"
    REJECTED = "rejected"
    DEFERRED = "deferred"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")
    return value


@dataclass(frozen=True, slots=True)
class StudentIdentityAssertion:
    """One student statement about one transcript record.

    ``selected_candidate`` is present for ``selected`` only. It holds the whole
    :class:`IdentityCandidate` rather than a bare course id, so the choice points at the
    exact catalogue entry that was displayed. This matters because a catalogue may repeat
    a ``course_id`` across entries (the real Case A catalogue has six 体育 entries sharing
    one course id), and a bare id could not say which one the student meant.
    """

    #: Transcript artifact the record belongs to. Derived from the artifact digest.
    completed_source_id: str
    #: The specific transcript row this statement is about.
    completed_source_record: str
    #: Catalogue version the choice is made against.
    target_version_id: str
    decision: StudentIdentityDecision
    #: Who is speaking. Only :data:`STUDENT_ASSERTION_SOURCE` is accepted.
    assertion_source: str
    #: Free-text note. Optional; never a substitute for evidence.
    note: str | None = None
    #: The chosen catalogue entry. Present iff ``decision is SELECTED``.
    selected_candidate: IdentityCandidate | None = None

    def __post_init__(self) -> None:
        for field in ("completed_source_id", "completed_source_record",
                      "target_version_id", "assertion_source"):
            _text(getattr(self, field), field)
        if not isinstance(self.decision, StudentIdentityDecision):
            raise CurriculumNormalizationError("assertion: unsupported decision")
        if self.assertion_source != STUDENT_ASSERTION_SOURCE:
            raise CurriculumNormalizationError(
                "assertion: only a student declaration may be recorded here"
            )
        if self.note is not None:
            if not isinstance(self.note, str):
                raise CurriculumNormalizationError("assertion: note must be a string or null")
            object.__setattr__(self, "note", self.note.strip() or None)

        if self.decision is StudentIdentityDecision.SELECTED:
            if not isinstance(self.selected_candidate, IdentityCandidate):
                raise CurriculumNormalizationError(
                    "assertion: a selection requires the chosen candidate"
                )
        elif self.selected_candidate is not None:
            raise CurriculumNormalizationError(
                f"assertion: {self.decision.value} must not carry a selected candidate"
            )

    @property
    def record_reference(self) -> tuple[str, str]:
        """The ``(source_id, source_record)`` identity of the transcript row."""

        return self.completed_source_id, self.completed_source_record

    @property
    def is_a_recognition(self) -> bool:
        """Always ``False``. Present so the boundary is explicit and testable."""

        return False


def _index_records(
    candidate_sets: Sequence[IdentityCandidateSet],
) -> dict[tuple[str, str], IdentityCandidateSet]:
    index: dict[tuple[str, str], IdentityCandidateSet] = {}
    for item in candidate_sets:
        if not isinstance(item, IdentityCandidateSet):
            raise CurriculumNormalizationError("candidate_sets: unexpected item type")
        reference = item.record_reference
        if reference in index:
            raise CurriculumNormalizationError(
                "candidate_sets: duplicate record identity in the supplied sets"
            )
        index[reference] = item
    return index


def validate_identity_assertions(
    candidate_sets: Sequence[IdentityCandidateSet],
    assertions: Sequence[StudentIdentityAssertion],
    *,
    current_source_id: str,
    current_target_version_id: str,
) -> tuple[StudentIdentityAssertion, ...]:
    """Validate assertions against the candidate sets produced for this run.

    ``current_source_id`` and ``current_target_version_id`` are the context the caller is
    actually working in. They are checked even though ``completed_source_id`` already
    embeds the artifact digest and every candidate carries its ``source_version_id``,
    because an embedded digest only proves *which* artifact a value came from; it cannot
    prove that the value belongs to *this* transcript and catalogue. Stale assertions are
    therefore rejected explicitly rather than silently applied.

    Returns the assertions in input order. Raises
    :class:`CurriculumNormalizationError` for anything unknown, stale, out of range,
    contradictory or duplicated.
    """

    _text(current_source_id, "current_source_id")
    _text(current_target_version_id, "current_target_version_id")
    if isinstance(candidate_sets, (str, bytes, bytearray)) or not isinstance(candidate_sets, Sequence):
        raise CurriculumNormalizationError("candidate_sets: expected a sequence")
    if isinstance(assertions, (str, bytes, bytearray)) or not isinstance(assertions, Sequence):
        raise CurriculumNormalizationError("assertions: expected a sequence")

    index = _index_records(candidate_sets)

    seen_decisions: dict[tuple[str, str], StudentIdentityDecision] = {}
    validated: list[StudentIdentityAssertion] = []

    for position, assertion in enumerate(assertions, start=1):
        if not isinstance(assertion, StudentIdentityAssertion):
            raise CurriculumNormalizationError(
                f"assertions item {position}: expected a StudentIdentityAssertion"
            )

        # Rule 2 and rule 8: the transcript this statement was made about must be the one
        # currently loaded. A changed artifact changes source_id, so old statements fail
        # here instead of applying to the new transcript.
        if assertion.completed_source_id != current_source_id:
            raise CurriculumNormalizationError(
                f"assertions item {position}: record source does not match the current transcript"
            )
        # Rule 3 and rule 8: same for the catalogue version.
        if assertion.target_version_id != current_target_version_id:
            raise CurriculumNormalizationError(
                f"assertions item {position}: target version does not match the current catalogue"
            )

        reference = assertion.record_reference
        item = index.get(reference)
        # Rule 1: the statement must name exactly one record of this transcript. Records
        # are located by identifier only — never by course name and never by array index.
        if item is None:
            raise CurriculumNormalizationError(
                f"assertions item {position}: record is not part of the current transcript"
            )

        # Rule 7: at most one statement per record, including a repeated "deferred".
        # A second statement never silently supersedes the first — that would make the
        # stored outcome depend on submission order, which the system must not decide.
        # A client that wants to change its mind must resolve the conflict explicitly.
        previous = seen_decisions.get(reference)
        if previous is not None:
            raise CurriculumNormalizationError(
                f"assertions item {position}: record already has a {previous.value} assertion"
            )
        seen_decisions[reference] = assertion.decision

        if assertion.decision is StudentIdentityDecision.SELECTED:
            chosen = assertion.selected_candidate
            assert chosen is not None  # guaranteed by __post_init__
            # The chosen entry must belong to the same catalogue version as the choice.
            if chosen.target_version_id != current_target_version_id:
                raise CurriculumNormalizationError(
                    f"assertions item {position}: selected candidate is from another version"
                )
            # Rule 4: the choice must be one of the candidates generated for *this*
            # record — not another record's candidate, and not an invented one. Compared
            # on the candidate identity so a course id alone can never identify an entry.
            if chosen.record_reference != reference:
                raise CurriculumNormalizationError(
                    f"assertions item {position}: selected candidate belongs to another record"
                )
            if item.candidates:
                allowed = {candidate.identity for candidate in item.candidates}
                if chosen.identity not in allowed:
                    raise CurriculumNormalizationError(
                        f"assertions item {position}: selected candidate is not in this record's candidates"
                    )
                # The candidate object must match what was shown, not merely share an
                # identity tuple with a tampered copy.
                if chosen not in item.candidates:
                    raise CurriculumNormalizationError(
                        f"assertions item {position}: selected candidate does not match the shown candidate"
                    )
            else:
                # A record with no candidates cannot be satisfied by naming one, and a
                # course number supplied by a caller is never turned into a candidate.
                raise CurriculumNormalizationError(
                    f"assertions item {position}: record has no candidates to select from"
                )

        validated.append(assertion)

    return tuple(validated)


def assertions_for_record(
    assertions: Sequence[StudentIdentityAssertion],
    *,
    source_id: str,
    source_record: str,
) -> tuple[StudentIdentityAssertion, ...]:
    """Return the validated statements about one record, in input order.

    A convenience for callers that need one record's statements without re-deriving the
    reference themselves. It performs no validation; use
    :func:`validate_identity_assertions` first.
    """

    target = (source_id, source_record)
    out = []
    for assertion in assertions:
        if not isinstance(assertion, StudentIdentityAssertion):
            raise CurriculumNormalizationError("assertions: unexpected item type")
        if assertion.record_reference == target:
            out.append(assertion)
    return tuple(out)
