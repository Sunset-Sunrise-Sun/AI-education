"""Course-identity candidates for completed-course records. **Identity only.**

This module answers exactly one question: *which catalogue courses could this
transcript record be?* It never answers whether that course satisfies a target
curriculum requirement, and it never recognises credit.

It is deliberately separate from the recognition machinery:

- it does **not** construct, accept or return ``ConfirmedRecognition`` /
  ``ConfirmedMissingRequirement`` / ``ConfirmedElectiveSelection``;
- it does **not** touch ``MatchingRules`` or the ``scope`` decision objects in
  ``case_a_decisions.py``;
- it does **not** feed ``build_curriculum_diff``, so it cannot change any
  ``MakeupTask`` or produce ``SATISFIED``;
- it emits **no** recognised-credit value of any kind.

The only matching method implemented is **exact normalised-name equality**. There is
no fuzzy, substring, phonetic, abbreviation or edit-distance matching, and a course
number is **never** derived from a course name — a candidate course number always
comes from the supplied catalogue entry and therefore only proves that *this
candidate identity exists in this catalogue version*. It proves nothing about the
target curriculum.

Two independent guarantees matter for safety:

1. **Version binding.** Every candidate records the catalogue ``version_id`` it came
   from, and the caller must pass the ``target_version_id`` they intend to bind to.
   A mismatch is an error, so a candidate from one version can never be silently
   applied to another.
2. **Source binding.** Every candidate and every record identifier carries the
   transcript ``source_id`` as well as the ``source_record``. A confirmation built
   from these identifiers therefore stops applying when the transcript artifact
   changes, because its ``source_id`` changes with the artifact digest.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.requirements import CurriculumVersion

__all__ = [
    "IdentityMatchMethod",
    "IdentityStatus",
    "IdentityCandidate",
    "IdentityCandidateSet",
    "build_identity_candidates",
    "normalize_course_name",
]


class IdentityMatchMethod(str, Enum):
    """How a candidate was found. Only exact normalised equality exists today."""

    EXACT_NORMALIZED_NAME = "exact_normalized_name"


class IdentityStatus(str, Enum):
    """How well the record's identity is pinned down. Never a recognition result."""

    #: Exactly one catalogue course has this normalised name.
    CANDIDATES_FOUND = "candidates_found"
    #: Several catalogue courses share the name; a human must choose. None is picked.
    AMBIGUOUS = "ambiguous"
    #: No catalogue course in this version carries the name.
    UNRESOLVED = "unresolved"
    #: The record already carries a confirmed identity, so it needs no candidate.
    ALREADY_CONFIRMED = "already_confirmed"


def normalize_course_name(value: str) -> str:
    """The single normalisation used for exact name comparison.

    NFKC-fold, casefold, and drop all whitespace. This mirrors the existing
    internal name comparison so this module cannot drift from it, and formatting
    differences alone never create a candidate.
    """

    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError("course_name: expected a nonempty string")
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")
    return value


def _items(values: object, kind: type, field: str) -> tuple:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CurriculumNormalizationError(f"{field}: expected a sequence")
    out = []
    for value in values:
        if not isinstance(value, kind):
            raise CurriculumNormalizationError(f"{field}: unexpected item type")
        out.append(value)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class IdentityCandidate:
    """One possible catalogue identity for one transcript record.

    ⛔ There is no credit field. ``recognized_credit`` belongs to the recognition
    decision, which is a separate, authorised step.

    **What identifies a candidate.** ``course_id`` alone is not enough: a catalogue may
    legitimately contain several byte-identical entries (the real Case A catalogue holds
    six identical 体育 rows sharing one course id *and* one source record). The identity
    of a candidate is therefore exactly:

        (source_version_id, course_id, catalog_source_record, catalog_entry_ordinal)

    ``catalog_entry_ordinal`` is the entry's position within
    ``CurriculumVersion.courses``, so the value always describes an entry the caller was
    actually shown. It is derived from the loaded catalogue only — never from a course
    name and never from any caller-supplied course number.
    """

    #: Version of the catalogue this candidate came from. Pins the candidate.
    source_version_id: str
    #: Version the caller intends to bind to. Must equal ``source_version_id``.
    target_version_id: str
    course_id: str
    course_name: str
    #: The requirement slot recorded by the catalogue entry; context only, never a
    #: statement that the record satisfies it.
    course_requirement: str
    match_method: IdentityMatchMethod
    #: Why this candidate was proposed. Always present; never blank.
    evidence: str
    #: Catalogue record this candidate was read from.
    catalog_source_record: str
    #: Position of this entry within ``CurriculumVersion.courses`` (0-based). Separates
    #: byte-identical catalogue entries that share a course id and a source record.
    catalog_entry_ordinal: int
    #: Transcript artifact identity. Changes when the transcript changes.
    completed_source_id: str
    #: The specific transcript row this candidate is about.
    completed_source_record: str
    #: The transcript's own course name, so a reviewer can compare the two strings.
    completed_course_name: str
    #: True when the record was passed; a failed record still yields candidates.
    completed_passed: bool

    def __post_init__(self) -> None:
        for field in (
            "source_version_id", "target_version_id", "course_id", "course_name",
            "course_requirement", "evidence", "catalog_source_record",
            "completed_source_id", "completed_source_record", "completed_course_name",
        ):
            _text(getattr(self, field), field)
        if self.source_version_id != self.target_version_id:
            raise CurriculumNormalizationError(
                "candidate: source version does not match the target version"
            )
        if not isinstance(self.match_method, IdentityMatchMethod):
            raise CurriculumNormalizationError("candidate: unsupported match method")
        ordinal = self.catalog_entry_ordinal
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
            raise CurriculumNormalizationError(
                "candidate: catalog_entry_ordinal must be a nonnegative integer"
            )
        if not isinstance(self.completed_passed, bool):
            raise CurriculumNormalizationError("candidate: completed_passed must be a boolean")

    @property
    def identity(self) -> tuple[str, str, str, int]:
        """The values that uniquely denote this catalogue entry.

        An assertion records this tuple rather than a bare course id, so a choice can
        always be traced back to the exact entry that was displayed.
        """

        return (
            self.source_version_id,
            self.course_id,
            self.catalog_source_record,
            self.catalog_entry_ordinal,
        )

    @property
    def record_reference(self) -> tuple[str, str]:
        """The ``(source_id, source_record)`` identity of the transcript row."""

        return self.completed_source_id, self.completed_source_record


@dataclass(frozen=True, slots=True)
class IdentityCandidateSet:
    """Candidate identities for exactly one transcript record.

    One set is emitted per transcript record, so two transcript rows that happen to
    share a name produce two separate sets and are never merged.
    """

    completed_source_id: str
    completed_source_record: str
    completed_course_name: str
    completed_passed: bool
    target_version_id: str
    status: IdentityStatus
    candidates: tuple[IdentityCandidate, ...]
    #: Why the record still needs a human. Always present.
    pending_reason: str
    #: Extra context that is not a decision, e.g. how many catalogue entries matched.
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in (
            "completed_source_id", "completed_source_record", "completed_course_name",
            "target_version_id", "pending_reason",
        ):
            _text(getattr(self, field), field)
        if not isinstance(self.status, IdentityStatus):
            raise CurriculumNormalizationError("set: unsupported identity status")
        if not isinstance(self.completed_passed, bool):
            raise CurriculumNormalizationError("set: completed_passed must be a boolean")
        object.__setattr__(
            self, "candidates", _items(self.candidates, IdentityCandidate, "candidates")
        )
        notes = _items(self.notes, str, "notes")
        for note in notes:
            _text(note, "note")
        object.__setattr__(self, "notes", notes)

        # The status must agree with the candidate payload; a caller must not be able
        # to claim a unique match while carrying several candidates.
        expected = {
            IdentityStatus.ALREADY_CONFIRMED: 0,
            IdentityStatus.UNRESOLVED: 0,
            IdentityStatus.CANDIDATES_FOUND: 1,
        }
        if self.status in expected:
            if len(self.candidates) != expected[self.status]:
                raise CurriculumNormalizationError(
                    f"set: status {self.status.value} does not match the candidate count"
                )
        elif len(self.candidates) < 2:
            raise CurriculumNormalizationError(
                "set: ambiguous status requires at least two candidates"
            )
        for candidate in self.candidates:
            if candidate.record_reference != (self.completed_source_id, self.completed_source_record):
                raise CurriculumNormalizationError(
                    "set: candidate does not belong to this transcript record"
                )
            if candidate.target_version_id != self.target_version_id:
                raise CurriculumNormalizationError(
                    "set: candidate version does not match the set version"
                )

    @property
    def record_reference(self) -> tuple[str, str]:
        return self.completed_source_id, self.completed_source_record

    @property
    def needs_confirmation(self) -> bool:
        """Whether a human still has to act on this record."""

        return self.status in (
            IdentityStatus.CANDIDATES_FOUND,
            IdentityStatus.AMBIGUOUS,
            IdentityStatus.UNRESOLVED,
        )


_UNRESOLVED_REASON = "目录中没有任何课程与该记录的名称精确匹配，身份无法确定，待人工核对。"
_CONFIRMED_REASON = "该记录已带有明确的课程身份，无需再生成候选。"


def _validated_records(completed: Sequence[CompletedCourse]) -> tuple[CompletedCourse, ...]:
    """Return the records after checking the identifier integrity of the input.

    A record is identified by ``(source_id, source_record)``. Two violations are input
    errors and are **never** repaired silently, because quietly dropping or merging
    records would hide exactly the mistake a reviewer needs to see:

    1. the same ``(source_id, source_record)`` twice — one identifier cannot denote two
       rows, so any candidate or later confirmation built on it would be ambiguous;
    2. more than one ``source_id`` in a single call — Case A works within one transcript
       artifact, and mixing artifacts would let a decision bound to one transcript be
       read as if it belonged to another.

    Repeated *course names* with distinct ``source_record`` are legal and untouched: the
    real Case A transcript has two 体育 rows and they must stay separate.
    """

    if isinstance(completed, (str, bytes, bytearray)) or not isinstance(completed, Sequence):
        raise CurriculumNormalizationError("completed: expected a sequence")

    records: list[CompletedCourse] = []
    for record in completed:
        if not isinstance(record, CompletedCourse):
            raise CurriculumNormalizationError("completed: unexpected item type")
        records.append(record)

    source_ids = {record.source_id for record in records}
    if len(source_ids) > 1:
        raise CurriculumNormalizationError(
            "completed: records from more than one source_id cannot be combined"
        )

    seen: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    for record in records:
        reference = (record.source_id, record.source_record)
        if reference in seen:
            duplicates.add(reference)
        seen.add(reference)
    if duplicates:
        # Field names and row identifiers only; no record content is echoed.
        listed = ", ".join(sorted(f"{sid}#{srec}" for sid, srec in duplicates))
        raise CurriculumNormalizationError(
            f"completed: duplicate record identity ({listed})"
        )

    return tuple(records)


def build_identity_candidates(
    completed: Sequence[CompletedCourse],
    catalog: CurriculumVersion,
    *,
    target_version_id: str,
) -> tuple[IdentityCandidateSet, ...]:
    """Return one :class:`IdentityCandidateSet` per transcript record, in input order.

    ``catalog`` is the course catalogue with an explicit version identity (a
    :class:`CurriculumVersion`). ``target_version_id`` is the version the caller
    intends to bind confirmations to; it must equal ``catalog.version_id``, otherwise
    a candidate from one version could be paired with another version's requirements.

    The input must be internally consistent: every record must carry the same
    ``source_id`` and each ``(source_id, source_record)`` must be unique. Both
    violations raise :class:`CurriculumNormalizationError` rather than being repaired,
    so a malformed input never produces a plausible-looking candidate list.

    Nothing here recognises credit, satisfies a requirement, or selects a candidate.
    """

    if not isinstance(catalog, CurriculumVersion):
        raise CurriculumNormalizationError("catalog: expected a CurriculumVersion")
    _text(target_version_id, "target_version_id")
    if catalog.version_id != target_version_id:
        raise CurriculumNormalizationError(
            "catalog: version does not match the requested target version"
        )
    records_in = _validated_records(completed)

    # Index the catalogue by normalised name. Every entry is kept, so repeated names
    # stay visible instead of being collapsed into one.
    by_name: dict[str, list] = {}
    for ordinal, course in enumerate(catalog.courses):
        by_name.setdefault(normalize_course_name(course.course_name), []).append((ordinal, course))

    sets: list[IdentityCandidateSet] = []
    for record in records_in:

        if record.course_id_status is CourseIdStatus.CONFIRMED:
            sets.append(IdentityCandidateSet(
                completed_source_id=record.source_id,
                completed_source_record=record.source_record,
                completed_course_name=record.course_name,
                completed_passed=record.passed,
                target_version_id=target_version_id,
                status=IdentityStatus.ALREADY_CONFIRMED,
                candidates=(),
                pending_reason=_CONFIRMED_REASON,
            ))
            continue

        matches = by_name.get(normalize_course_name(record.course_name), [])

        if not matches:
            sets.append(IdentityCandidateSet(
                completed_source_id=record.source_id,
                completed_source_record=record.source_record,
                completed_course_name=record.course_name,
                completed_passed=record.passed,
                target_version_id=target_version_id,
                status=IdentityStatus.UNRESOLVED,
                candidates=(),
                pending_reason=_UNRESOLVED_REASON,
                notes=(f"catalog_version:{target_version_id}",),
            ))
            continue

        candidates = tuple(
            IdentityCandidate(
                source_version_id=catalog.version_id,
                target_version_id=target_version_id,
                course_id=course.course_id,
                course_name=course.course_name,
                course_requirement=getattr(course.requirement, "value", str(course.requirement)),
                match_method=IdentityMatchMethod.EXACT_NORMALIZED_NAME,
                evidence=(
                    f"名称精确匹配（NFKC+casefold+去空白）：成绩单「{record.course_name}」"
                    f" == 目录课程 {course.course_id}「{course.course_name}」；"
                    f"目录版本 {catalog.version_id}；目录条目 {course.source_record}；"
                    f"成绩单 {record.source_id}#{record.source_record}。"
                    "⚠️ 仅证明该候选身份存在于该目录版本，不代表满足目标培养方案要求。"
                ),
                catalog_source_record=course.source_record,
                catalog_entry_ordinal=ordinal,
                completed_source_id=record.source_id,
                completed_source_record=record.source_record,
                completed_course_name=record.course_name,
                completed_passed=record.passed,
            )
            for ordinal, course in matches
        )

        ambiguous = len(candidates) > 1
        if ambiguous:
            pending_reason = (
                f"目录中有 {len(candidates)} 门课程与该记录名称完全相同，"
                "无法自动确定是哪一门，需人工选择一个候选身份。"
            )
        else:
            pending_reason = (
                "名称精确匹配到唯一候选，但该候选身份是否满足目标培养方案要求、"
                "能否认定学分，仍须由授权依据确认。"
            )

        notes = [f"catalog_version:{target_version_id}", f"name_match_count:{len(candidates)}"]
        if not record.passed:
            notes.append("record_not_passed:该记录未通过，仅生成身份候选，不产生任何已修认定。")

        sets.append(IdentityCandidateSet(
            completed_source_id=record.source_id,
            completed_source_record=record.source_record,
            completed_course_name=record.course_name,
            completed_passed=record.passed,
            target_version_id=target_version_id,
            status=IdentityStatus.AMBIGUOUS if ambiguous else IdentityStatus.CANDIDATES_FOUND,
            candidates=candidates,
            pending_reason=pending_reason,
            notes=tuple(notes),
        ))

    return tuple(sets)
