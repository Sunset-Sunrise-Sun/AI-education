"""Compare supplied requirements using explicit decisions or scoped case rules."""

from __future__ import annotations

import math
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.requirements import (
    CurriculumCourse,
    CurriculumVersion,
    RequirementKind,
)
from app.curriculum.terms import (
    SCOPE_FUTURE,
    SCOPE_HISTORICAL,
    SCOPE_UNRESOLVED,
    ConfirmedScopeDecision,
    ScopeDecision as InternalScopeDecision,
    scope_decisions,
)
from app.models.contracts import Course, MakeupStatus, MakeupTask

_BUILD_TOKEN = object()

# Group scope classification. These are internal facts, never public contract values.
GROUP_SCOPE_UNSCOPED = "unscoped"
GROUP_SCOPE_HISTORICAL = "historical"
GROUP_SCOPE_FUTURE = "future"
GROUP_SCOPE_MIXED = "mixed"


def _text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")


def _items(values: object, kind: type, field: str) -> tuple:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise CurriculumNormalizationError(f"{field}: expected a sequence")
    result = tuple(values)
    if any(not isinstance(value, kind) for value in result):
        raise CurriculumNormalizationError(f"{field}: unexpected item type")
    return result


@dataclass(frozen=True, slots=True)
class MatchingRules:
    """Evidence-backed case configuration, not a public or school-policy DTO."""

    target_version_id: str
    completed_source_id: str
    evidence: str
    allow_exact_match: bool = False
    allow_confirmed_absence: bool = False

    def __post_init__(self) -> None:
        for field in ("target_version_id", "completed_source_id", "evidence"):
            _text(getattr(self, field), field)
        for field in ("allow_exact_match", "allow_confirmed_absence"):
            if type(getattr(self, field)) is not bool:
                raise CurriculumNormalizationError(f"{field}: expected a boolean")


@dataclass(frozen=True, slots=True)
class ConfirmedRecognition:
    target_version_id: str
    target_course_id: str
    completed_source_id: str
    completed_source_record: str
    recognized_credit: float
    evidence: str

    def __post_init__(self) -> None:
        for field in (
            "target_version_id", "target_course_id", "completed_source_id",
            "completed_source_record", "evidence",
        ):
            _text(getattr(self, field), field)
        value = self.recognized_credit
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CurriculumNormalizationError("recognized_credit: invalid number")
        try:
            value = float(value)
        except (OverflowError, ValueError):
            raise CurriculumNormalizationError("recognized_credit: invalid number") from None
        if not math.isfinite(value) or value < 0:
            raise CurriculumNormalizationError("recognized_credit: invalid number")
        object.__setattr__(self, "recognized_credit", value)


@dataclass(frozen=True, slots=True)
class ConfirmedMissingRequirement:
    target_version_id: str
    target_course_id: str
    completed_source_id: str
    evidence: str

    def __post_init__(self) -> None:
        for field in ("target_version_id", "target_course_id", "completed_source_id", "evidence"):
            _text(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class ConfirmedElectiveSelection:
    """An explicit future choice within one flat credit group, not earned credit."""

    target_version_id: str
    group_id: str
    course_ids: tuple[str, ...]
    evidence: str

    def __post_init__(self) -> None:
        for name in ("target_version_id", "group_id", "evidence"):
            _text(getattr(self, name), name)
        course_ids = _items(self.course_ids, str, "selection course_ids")
        if not course_ids:
            raise CurriculumNormalizationError("selection course_ids: expected at least one course")
        for course_id in course_ids:
            _text(course_id, "selection course_ids")
        if len(set(course_ids)) != len(course_ids):
            raise CurriculumNormalizationError("selection course_ids: duplicate course reference")
        object.__setattr__(self, "course_ids", course_ids)


def _elective_selections(
    version: CurriculumVersion, values: Sequence[ConfirmedElectiveSelection],
) -> tuple[ConfirmedElectiveSelection, ...]:
    selections = _items(values, ConfirmedElectiveSelection, "elective_selections")
    groups = {group.group_id for group in version.groups}
    targets: dict[str, list[CurriculumCourse]] = defaultdict(list)
    for course in version.courses:
        targets[course.course_id].append(course)
    seen_groups: set[str] = set()
    for selection in selections:
        if selection.target_version_id != version.version_id or selection.group_id not in groups:
            raise CurriculumNormalizationError("elective selection: outside the supplied curriculum")
        if selection.group_id in seen_groups:
            raise CurriculumNormalizationError("elective selection: duplicate group decision")
        seen_groups.add(selection.group_id)
        for course_id in selection.course_ids:
            entries = targets.get(course_id, [])
            if len(entries) != 1:
                raise CurriculumNormalizationError("elective selection: target is not uniquely defined")
            target = entries[0]
            if target.requirement is not RequirementKind.ELECTIVE or target.group_id != selection.group_id:
                raise CurriculumNormalizationError("elective selection: target must belong to the selected pool")
    return selections


@dataclass(frozen=True, slots=True)
class CourseMatch:
    target: CurriculumCourse
    status: MakeupStatus
    candidates: tuple[CompletedCourse, ...]
    reason: str
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target, CurriculumCourse) or not isinstance(self.status, MakeupStatus):
            raise CurriculumNormalizationError("match: unexpected target or status type")
        _text(self.reason, "match reason")
        object.__setattr__(self, "candidates", _items(self.candidates, CompletedCourse, "candidates"))
        references = _items(self.evidence, str, "match evidence")
        if not references:
            raise CurriculumNormalizationError("match evidence: expected source references")
        for reference in references:
            _text(reference, "match evidence")
        object.__setattr__(self, "evidence", references)


@dataclass(frozen=True, slots=True)
class GroupGap:
    group_id: str
    remaining_credit: float | None
    reason: str
    scope: str = GROUP_SCOPE_UNSCOPED
    historical_minimum_credit: float | None = None

    def __post_init__(self) -> None:
        _text(self.group_id, "group_id")
        _text(self.reason, "group reason")
        if self.scope not in (
            GROUP_SCOPE_UNSCOPED, GROUP_SCOPE_HISTORICAL, GROUP_SCOPE_FUTURE, GROUP_SCOPE_MIXED
        ):
            raise CurriculumNormalizationError("group gap: unsupported scope classification")
        for field in ("remaining_credit", "historical_minimum_credit"):
            value = getattr(self, field)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CurriculumNormalizationError(f"{field}: invalid number")
            try:
                value = float(value)
            except (OverflowError, ValueError):
                raise CurriculumNormalizationError(f"{field}: invalid number") from None
            if not math.isfinite(value) or value < 0:
                raise CurriculumNormalizationError(f"{field}: invalid number")
            object.__setattr__(self, field, value)

    @property
    def historical_ambiguous(self) -> bool:
        """A mixed group whose historical share of the minimum is not stated."""
        return self.scope == GROUP_SCOPE_MIXED and self.historical_minimum_credit is None


@dataclass(frozen=True, slots=True)
class ConfirmedGroupScopeDecision:
    """An explicit credit split for ONE mixed course group.

    A plan source that only states "this group needs 6 credits" does **not**
    state how many of them were expected before the transfer cut-off. That split
    can never be derived from course counts, recommended terms, or earned
    credits, so a mixed group needs this explicit, evidence-backed decision.

    ``historical_minimum_credit`` is the historical share only; it is never a
    school policy statement.
    """

    target_version_id: str
    group_id: str
    historical_minimum_credit: float
    evidence: str

    def __post_init__(self) -> None:
        for name in ("target_version_id", "group_id", "evidence"):
            _text(getattr(self, name), name)
        value = self.historical_minimum_credit
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CurriculumNormalizationError("historical_minimum_credit: invalid number")
        try:
            value = float(value)
        except (OverflowError, ValueError):
            raise CurriculumNormalizationError("historical_minimum_credit: invalid number") from None
        if not math.isfinite(value) or value < 0:
            raise CurriculumNormalizationError("historical_minimum_credit: invalid number")
        object.__setattr__(self, "historical_minimum_credit", value)


@dataclass(frozen=True, slots=True)
class MakeupScope:
    """Case-level boundary for *historical* transfer makeup decisions.

    ``as_of_term`` answers exactly one question: **up to which explicit term
    should historical makeup gaps be judged?** It is supplied by the case input
    together with its own evidence; it is never derived from the system date,
    from a deadline field, or from a school policy this MVP does not have.

    This object stays inside the Curriculum module: it is not part of the
    ``CurriculumProvider`` signature, ``MakeupTask``, Integration, or Planner.
    """

    target_version_id: str
    as_of_term: str
    evidence: str

    def __post_init__(self) -> None:
        for name in ("target_version_id", "as_of_term", "evidence"):
            _text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class CurriculumDiff:
    old: CurriculumVersion
    new: CurriculumVersion
    matches: tuple[CourseMatch, ...]
    group_gaps: tuple[GroupGap, ...]
    added_course_ids: tuple[str, ...] | None
    removed_course_ids: tuple[str, ...] | None
    changed_course_ids: tuple[str, ...] | None
    unrepresented_requirements: tuple[str, ...]
    elective_selections: tuple[ConfirmedElectiveSelection, ...] = ()
    makeup_scope: MakeupScope | None = None
    scope_decisions: tuple[InternalScopeDecision, ...] = ()
    _build_token: object = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.old, CurriculumVersion) or not isinstance(self.new, CurriculumVersion):
            raise CurriculumNormalizationError("diff: unexpected curriculum type")
        matches = _items(self.matches, CourseMatch, "matches")
        if tuple(match.target for match in matches) != self.new.courses:
            raise CurriculumNormalizationError("diff: matches must cover the supplied target entries in order")
        object.__setattr__(self, "matches", matches)
        object.__setattr__(self, "group_gaps", _items(self.group_gaps, GroupGap, "group_gaps"))
        object.__setattr__(self, "elective_selections", _elective_selections(self.new, self.elective_selections))
        if self.makeup_scope is not None:
            if not isinstance(self.makeup_scope, MakeupScope):
                raise CurriculumNormalizationError("diff: unexpected makeup scope type")
            if self.makeup_scope.target_version_id != self.new.version_id:
                raise CurriculumNormalizationError("diff: makeup scope is outside the target curriculum")
            decisions = _items(self.scope_decisions, InternalScopeDecision, "scope_decisions")
            if not decisions:
                raise CurriculumNormalizationError("diff: a makeup scope requires scope decisions")
            if [decision.course_id for decision in decisions] != [course.course_id for course in self.new.courses]:
                raise CurriculumNormalizationError("diff: scope decisions must cover the target entries in order")
            object.__setattr__(self, "scope_decisions", decisions)
        elif self.scope_decisions:
            raise CurriculumNormalizationError("diff: scope decisions require an explicit makeup scope")
        for field in ("added_course_ids", "removed_course_ids", "changed_course_ids", "unrepresented_requirements"):
            value = getattr(self, field)
            if value is None and field != "unrepresented_requirements":
                continue
            values = _items(value, str, field)
            for item in values:
                _text(item, field)
            object.__setattr__(self, field, values)

    def scope_bucket(self, course_id: str) -> str | None:
        """Return the historical/future/unresolved bucket, or ``None`` when unscoped."""
        if self.makeup_scope is None:
            return None
        for decision in self.scope_decisions:
            if decision.course_id == course_id:
                return decision.bucket
        raise CurriculumNormalizationError("diff: target is outside the makeup scope")

    def unresolved_scope_courses(self) -> tuple[str, ...]:
        """Target entries whose arrangement term cannot be safely classified."""
        return tuple(decision.course_id for decision in self.scope_decisions if decision.unresolved)


def _name(value: str) -> str:
    # Formatting alone never authorizes recognition without scoped case rules.
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _source(record: CompletedCourse) -> str:
    return f"{record.source_id}#{record.source_record}"


def _candidate_records(
    target: CurriculumCourse, completed: tuple[CompletedCourse, ...]
) -> tuple[tuple[CompletedCourse, ...], tuple[CompletedCourse, ...]]:
    identity = tuple(record for record in completed if (
        record.course_id_status is CourseIdStatus.CONFIRMED and record.course_id == target.course_id
    ))
    named = tuple(record for record in completed if (
        record.passed and _name(record.course_name) == _name(target.course_name)
        and record not in identity
    ))
    return identity, named


def _exact_rule_candidates(
    target: CurriculumCourse,
    identity: tuple[CompletedCourse, ...],
    named: tuple[CompletedCourse, ...],
    by_ref: dict[tuple[str, str], list[CompletedCourse]],
) -> tuple[tuple[CompletedCourse, ...], str | None]:
    """Return unambiguous exact passing facts; do not combine attempt credits."""
    if any(len(by_ref[(record.source_id, record.source_record)]) != 1 for record in identity + named):
        return (), "修读来源引用重复，无法唯一定位记录，待人工核对。"
    if any(record.course_id_status is CourseIdStatus.PENDING for record in named):
        return (), "匹配候选的课程号仍待确认，不能自动抵认。"
    passed = tuple(record for record in identity if record.passed)
    if any(_name(record.course_name) != _name(target.course_name) for record in passed):
        return (), "相同课程号存在课程名称冲突，待人工核对。"
    if any(record.credit != target.credit for record in passed):
        return (), "相同课程号存在学分差异，补修认定待人工核对。"
    return passed, None


def _group_scope_decisions(
    version: CurriculumVersion,
    decisions: tuple[InternalScopeDecision, ...],
    values: Sequence[ConfirmedGroupScopeDecision],
) -> dict[str, ConfirmedGroupScopeDecision]:
    """Validate explicit credit splits for mixed groups.

    Only a *mixed* group (some members arranged within the historical range and
    some after it) may carry a split. A split is refused when the source already
    places every member on one side, or when it cannot actually be met by the
    historical members or exceeds the stated group minimum.
    """

    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CurriculumNormalizationError("confirmed_group_scope_decisions: expected a sequence")
    bucket_by_record = {decision.source_record: decision.bucket for decision in decisions}
    groups = {group.group_id: group for group in version.groups}
    seen: set[str] = set()
    result: dict[str, ConfirmedGroupScopeDecision] = {}
    for value in values:
        if not isinstance(value, ConfirmedGroupScopeDecision):
            raise CurriculumNormalizationError("confirmed group scope decision: unexpected entry type")
        if value.target_version_id != version.version_id:
            raise CurriculumNormalizationError(
                "confirmed group scope decision: target version is outside the supplied curriculum"
            )
        group = groups.get(value.group_id)
        if group is None:
            raise CurriculumNormalizationError(
                "confirmed group scope decision: group is not in the supplied curriculum"
            )
        if value.group_id in seen:
            raise CurriculumNormalizationError(
                "confirmed group scope decision: duplicate decision for the same group"
            )
        seen.add(value.group_id)
        if group.minimum_credit is None:
            raise CurriculumNormalizationError(
                "confirmed group scope decision: group minimum credit is unknown"
            )
        if value.historical_minimum_credit > group.minimum_credit:
            raise CurriculumNormalizationError(
                "confirmed group scope decision: historical share exceeds the group minimum"
            )
        members = [course for course in version.courses if course.group_id == value.group_id]
        member_buckets = {bucket_by_record.get(course.source_record) for course in members}
        if (
            SCOPE_HISTORICAL not in member_buckets
            or (SCOPE_FUTURE not in member_buckets and SCOPE_UNRESOLVED not in member_buckets)
        ):
            raise CurriculumNormalizationError(
                "confirmed group scope decision: only a mixed group needs a credit split"
            )
        available = math.fsum(
            course.credit for course in members
            if bucket_by_record.get(course.source_record) == SCOPE_HISTORICAL
        )
        if value.historical_minimum_credit > available:
            raise CurriculumNormalizationError(
                "confirmed group scope decision: historical share exceeds the historical course pool"
            )
        result[value.group_id] = value
    return result


def build_curriculum_diff(
    old: CurriculumVersion,
    new: CurriculumVersion,
    completed: Sequence[CompletedCourse],
    *,
    recognitions: Sequence[ConfirmedRecognition] = (),
    missing_requirements: Sequence[ConfirmedMissingRequirement] = (),
    completed_complete: bool = False,
    completed_completeness_evidence: str | None = None,
    completed_source_id: str | None = None,
    rules: MatchingRules | None = None,
    elective_selections: Sequence[ConfirmedElectiveSelection] = (),
    makeup_scope: MakeupScope | None = None,
    confirmed_scope_decisions: Sequence[ConfirmedScopeDecision] = (),
    confirmed_group_scope_decisions: Sequence[ConfirmedGroupScopeDecision] = (),
) -> CurriculumDiff:
    """Use supplied decisions or case rules; defaults never approve equivalence.

    When an explicit ``makeup_scope`` is supplied, every target entry is also
    classified as historical, future, or unresolved. When it is omitted, the
    generic curriculum-diff behaviour is preserved unchanged.
    """
    if not isinstance(old, CurriculumVersion) or not isinstance(new, CurriculumVersion):
        raise CurriculumNormalizationError("curriculum: expected a CurriculumVersion")
    if makeup_scope is not None:
        if not isinstance(makeup_scope, MakeupScope):
            raise CurriculumNormalizationError("scope: expected a MakeupScope")
        if makeup_scope.target_version_id != new.version_id:
            raise CurriculumNormalizationError("scope: makeup scope is outside the supplied curriculum")
        decisions = scope_decisions(new, makeup_scope.as_of_term, confirmed_scope_decisions)
    else:
        if confirmed_scope_decisions:
            raise CurriculumNormalizationError("scope: confirmed decisions require an explicit makeup scope")
        if confirmed_group_scope_decisions:
            raise CurriculumNormalizationError("scope: group decisions require an explicit makeup scope")
        decisions = ()
    completed = _items(completed, CompletedCourse, "completed")
    recognitions = _items(recognitions, ConfirmedRecognition, "recognitions")
    missing_requirements = _items(missing_requirements, ConfirmedMissingRequirement, "missing_requirements")
    elective_selections = _elective_selections(new, elective_selections)
    selections_by_course = {
        course_id: selection for selection in elective_selections for course_id in selection.course_ids
    }
    groups_by_id = {group.group_id: group for group in new.groups}
    if type(completed_complete) is not bool:
        raise CurriculumNormalizationError("completed_complete: expected a boolean")
    if completed_complete:
        _text(completed_completeness_evidence, "completed_completeness_evidence")
    elif completed_completeness_evidence is not None:
        _text(completed_completeness_evidence, "completed_completeness_evidence")
    source_ids = {record.source_id for record in completed}
    if completed_source_id is not None:
        _text(completed_source_id, "completed_source_id")
        if source_ids - {completed_source_id}:
            raise CurriculumNormalizationError("completed records do not belong to the supplied source")
    elif len(source_ids) == 1:
        completed_source_id = next(iter(source_ids))
    elif len(source_ids) > 1:
        raise CurriculumNormalizationError("completed records require one case-specific source")
    if rules is not None:
        if not isinstance(rules, MatchingRules):
            raise CurriculumNormalizationError("rules: expected MatchingRules")
        if completed_source_id is None:
            raise CurriculumNormalizationError("rules: completed source scope is required")
        if rules.target_version_id != new.version_id or rules.completed_source_id != completed_source_id:
            raise CurriculumNormalizationError("rules: configuration is outside the supplied case")

    target_counts = Counter(course.course_id for course in new.courses)
    by_ref: dict[tuple[str, str], list[CompletedCourse]] = defaultdict(list)
    for record in completed:
        by_ref[(record.source_id, record.source_record)].append(record)

    granted: dict[str, list[ConfirmedRecognition]] = defaultdict(list)
    ref_uses: dict[tuple[str, str], set[str]] = defaultdict(set)
    missing: dict[str, list[ConfirmedMissingRequirement]] = defaultdict(list)
    for decision in (*recognitions, *missing_requirements):
        if decision.target_version_id != new.version_id or decision.target_course_id not in target_counts:
            raise CurriculumNormalizationError("decision: target is outside the supplied curriculum")
    for decision in recognitions:
        granted[decision.target_course_id].append(decision)
        ref_uses[(decision.completed_source_id, decision.completed_source_record)].add(decision.target_course_id)
    for decision in missing_requirements:
        targets = [course for course in new.courses if course.course_id == decision.target_course_id]
        if any(course.requirement is not RequirementKind.REQUIRED and not (
            course.requirement is RequirementKind.ELECTIVE and course.course_id in selections_by_course
        ) for course in targets):
            raise CurriculumNormalizationError("missing requirement: target must be required or explicitly selected")
        missing[decision.target_course_id].append(decision)

    automatic: dict[str, tuple[tuple[CompletedCourse, ...], str | None]] = {}
    if rules is not None and (rules.allow_exact_match or rules.allow_confirmed_absence):
        for target in new.courses:
            identity, named = _candidate_records(target, completed)
            exact, conflict = _exact_rule_candidates(target, identity, named, by_ref)
            automatic[target.course_id] = exact if rules.allow_exact_match else (), conflict
            if (rules.allow_exact_match and target_counts[target.course_id] == 1
                    and target.requirement is not RequirementKind.UNKNOWN
                    and not granted[target.course_id] and not missing[target.course_id]):
                for record in exact:
                    ref_uses[(record.source_id, record.source_record)].add(target.course_id)

    has_unknown_passed_identity = any(
        record.passed and record.course_id_status is CourseIdStatus.PENDING for record in completed
    )
    matches: list[CourseMatch] = []
    for target in new.courses:
        identity, named = _candidate_records(target, completed)
        candidates = identity + named
        evidence = [f"{new.source_id}#{target.source_record}"]
        evidence.extend(_source(record) for record in candidates)
        if makeup_scope is not None:
            # The scope decision is part of the provenance of every task, so the
            # explicit as-of basis stays auditable in the projected output.
            evidence.append(makeup_scope.evidence)
        approved = granted[target.course_id]
        missing_decisions = missing[target.course_id]
        evidence.extend(decision.evidence for decision in (*approved, *missing_decisions))
        if rules is not None:
            evidence.append(f"case 匹配规则依据：{rules.evidence}")
        selection = selections_by_course.get(target.course_id)
        if selection is not None:
            evidence.extend((
                f"{new.source_id}#{groups_by_id[selection.group_id].source_record}",
                f"人工选修计划选择依据：{selection.evidence}",
            ))
        exact, rule_conflict = automatic.get(target.course_id, ((), None))
        status = MakeupStatus.MANUAL_CONFIRMATION
        reason = "未发现匹配，但缺课认定尚未确认。"

        if target_counts[target.course_id] > 1:
            reason = "培养方案重复列出同一课程号，要求归属待确认。"
        elif target.requirement is RequirementKind.UNKNOWN:
            reason = "该课程的修读要求尚待确认。"
        elif approved and missing_decisions:
            reason = "课程认定与缺课确认相互冲突，待人工核对。"
        elif approved:
            if len(approved) != 1:
                reason = "存在多条认定记录，待确认适用关系。"
            else:
                decision = approved[0]
                ref = (decision.completed_source_id, decision.completed_source_record)
                records = by_ref.get(ref, [])
                if len(ref_uses[ref]) > 1:
                    reason = "同一修读记录被用于多门目标课程，认定分配待确认。"
                elif len(records) != 1:
                    reason = "认定依据无法唯一定位修读记录，待人工核对。"
                elif not records[0].passed:
                    reason = "认定依据与未通过记录冲突，待人工核对。"
                elif decision.recognized_credit < target.credit:
                    reason = "已认定学分不足，补修方式待确认。"
                else:
                    status = MakeupStatus.SATISFIED
                    reason = "已有明确课程认定依据。"
                for record in records:
                    if record not in candidates:
                        candidates += (record,)
                        evidence.append(_source(record))
        elif missing_decisions and any(record.passed for record in candidates):
            reason = "缺课确认与已修候选相互冲突，待人工核对。"
        elif rule_conflict is not None:
            reason = rule_conflict
        elif exact:
            if any(len(ref_uses[(record.source_id, record.source_record)]) > 1 for record in exact):
                reason = "同一修读记录被用于多门目标课程，认定分配待确认。"
            else:
                status = MakeupStatus.SATISFIED
                reason = "依据本 case 匹配规则，课程号、规范化名称、学分及通过事实完全匹配。"
        elif target.requirement is RequirementKind.ELECTIVE and selection is None:
            reason = "选修课程保留在课程池，不逐门判为必补。"
            if named:
                status = MakeupStatus.POSSIBLY_EQUIVALENT
                reason = "发现名称候选，选修认定与组要求仍需核对。"
        elif any(record.passed for record in identity):
            reason = "课程号相同，正式抵认尚未确认。"
        elif named:
            status = MakeupStatus.POSSIBLY_EQUIVALENT
            reason = "发现名称候选，等价关系待人工确认。"
        elif not new.complete or not completed_complete:
            reason = "输入范围未确认完整，不能确定缺课。"
        elif has_unknown_passed_identity:
            reason = "仍有课程号待确认的已修记录，不能确定缺课。"
        elif missing_decisions and any(decision.completed_source_id != completed_source_id for decision in missing_decisions):
            reason = "缺课确认与已修数据来源不匹配，待人工核对。"
        elif len(missing_decisions) == 1:
            status = MakeupStatus.REQUIRED
            reason = "已有明确补修需求确认依据。"
        elif len(missing_decisions) > 1:
            reason = "存在多条缺课确认记录，待人工核对。"
        elif rules is not None and rules.allow_confirmed_absence:
            if any(len(records) != 1 for records in by_ref.values()):
                reason = "已修来源引用重复，完整记录的缺课判断待人工核对。"
            else:
                status = MakeupStatus.REQUIRED
                reason = "依据本 case 缺课规则，完整目标要求与已修记录中未发现通过匹配或身份未知的通过记录。"
        if status is MakeupStatus.REQUIRED:
            evidence.extend((
                f"目标方案完整性依据：{new.completeness_evidence}",
                f"已修记录来源：{completed_source_id}",
                f"已修记录完整性依据：{completed_completeness_evidence}",
            ))
        matches.append(CourseMatch(target, status, candidates, reason, tuple(dict.fromkeys(evidence))))

    unrepresented: list[str] = []
    if any(course.requirement is RequirementKind.ELECTIVE and course.group_id is None for course in new.courses):
        unrepresented.append("elective course has no group requirement")
    bucket_by_record = {decision.source_record: decision.bucket for decision in decisions}
    group_scope = _group_scope_decisions(new, decisions, confirmed_group_scope_decisions)
    group_gaps: list[GroupGap] = []
    for group in new.groups:
        if group.minimum_credit is None:
            group_gaps.append(GroupGap(group.group_id, None, "课程组学分要求尚未确认。"))
            continue
        members = [course for course in new.courses if course.group_id == group.group_id]
        member_buckets = {bucket_by_record.get(course.source_record) for course in members}
        if makeup_scope is None:
            scope = GROUP_SCOPE_UNSCOPED
        elif SCOPE_HISTORICAL not in member_buckets:
            # No member of this group is arranged within the historical range, so
            # the group states no historical requirement and must not block the
            # current historical projection.
            scope = GROUP_SCOPE_FUTURE
        elif SCOPE_FUTURE not in member_buckets and SCOPE_UNRESOLVED not in member_buckets:
            scope = GROUP_SCOPE_HISTORICAL
        else:
            scope = GROUP_SCOPE_MIXED
        decision = group_scope.get(group.group_id)
        historical_minimum = None
        if scope == GROUP_SCOPE_MIXED and decision is not None:
            historical_minimum = decision.historical_minimum_credit
        eligible = [
            match for match in matches
            if match.target.group_id == group.group_id
            and (
                scope != GROUP_SCOPE_HISTORICAL
                or bucket_by_record.get(match.target.source_record) == SCOPE_HISTORICAL
            )
            and (
                match.status is MakeupStatus.SATISFIED
                or (
                    scope == GROUP_SCOPE_HISTORICAL
                    and match.target.requirement is RequirementKind.REQUIRED
                )
            )
        ]
        try:
            covered = math.fsum(match.target.credit for match in eligible)
        except OverflowError:
            raise CurriculumNormalizationError("group credits: total is not finite") from None
        if scope == GROUP_SCOPE_FUTURE:
            # Future-only: the historical share is zero by construction.
            remaining = 0.0
        elif scope == GROUP_SCOPE_MIXED and historical_minimum is None:
            # The source never states the historical share; keep the total as the
            # conservative bar rather than inventing a proportional split.
            remaining = max(group.minimum_credit - covered, 0.0)
        else:
            bar = group.minimum_credit if historical_minimum is None else historical_minimum
            remaining = max(bar - covered, 0.0)
        if remaining > 0:
            if scope == GROUP_SCOPE_MIXED:
                reason = "混合课程组的历史学分要求无法从来源分割，需人工确认。"
            elif scope == GROUP_SCOPE_FUTURE:
                reason = "课程组要求全部安排在历史范围之后。"
            else:
                reason = "课程组仍有未确认满足的学分要求。"
            group_gaps.append(GroupGap(
                group.group_id, remaining, reason, scope, historical_minimum,
            ))

    # Historical projection view: a group with no historical member is dropped
    # entirely, so the unmet-group rewrite below cannot reach future groups.
    historical_gaps = tuple(
        gap for gap in group_gaps if gap.scope != GROUP_SCOPE_FUTURE
    )
    unmet_groups = {gap.group_id for gap in historical_gaps}
    matches = [
        CourseMatch(match.target, MakeupStatus.MANUAL_CONFIRMATION, match.candidates,
                    "选修组已满足，未修的已选课程不因此成为补修要求。", match.evidence)
        if (match.status is MakeupStatus.REQUIRED and match.target.requirement is RequirementKind.ELECTIVE
            and match.target.group_id not in unmet_groups) else match
        for match in matches
    ]

    added = removed = changed = None
    if old.complete and new.complete:
        old_ids = {course.course_id for course in old.courses}
        new_ids = set(target_counts)
        added = tuple(dict.fromkeys(course.course_id for course in new.courses if course.course_id not in old_ids))
        removed = tuple(dict.fromkeys(course.course_id for course in old.courses if course.course_id not in new_ids))
        semantic_fields = (
            "course_name", "credit", "requirement", "course_type", "group_id",
            "recommended_term_text", "prerequisites", "recommended_semester", "deadline_semester",
        )
        def signatures(version: CurriculumVersion, course_id: str) -> tuple:
            return tuple(tuple(getattr(course, field) for field in semantic_fields)
                         for course in version.courses if course.course_id == course_id)
        changed = tuple(dict.fromkeys(
            course.course_id for course in new.courses if course.course_id in old_ids
            and signatures(old, course.course_id) != signatures(new, course.course_id)
        ))
    diff = CurriculumDiff(old, new, tuple(matches), tuple(group_gaps), added, removed, changed,
                          tuple(unrepresented), elective_selections, makeup_scope, decisions)
    # Replacements and manually assembled results remain useful for inspection,
    # but cannot bypass the builder's recognition and group checks.
    object.__setattr__(diff, "_build_token", _BUILD_TOKEN)
    return diff


def _require_built_diff(diff: object) -> None:
    if not isinstance(diff, CurriculumDiff) or diff._build_token is not _BUILD_TOKEN:
        raise CurriculumNormalizationError("diff: rebuild before projecting planning results")


def selected_elective_course_ids(diff: CurriculumDiff) -> tuple[str, ...]:
    """Return non-earned choices for groups with an actual gap, in source order."""
    if not isinstance(diff, CurriculumDiff):
        raise CurriculumNormalizationError("diff: expected a CurriculumDiff")
    unmet = {gap.group_id for gap in diff.group_gaps}
    selected = {course_id for selection in diff.elective_selections if selection.group_id in unmet
                for course_id in selection.course_ids}
    return tuple(match.target.course_id for match in diff.matches
                 if match.target.course_id in selected and match.status is not MakeupStatus.SATISFIED)


def group_plan_covers_requirement(diff: CurriculumDiff, group_id: str) -> bool:
    """Check earned credits and expressed future requirements for a flat group.

    Known mandatory requirements already have public tasks. Unearned elective
    requirements need an explicit choice. Pending matching or prerequisites
    stay pending; capacity never changes a task's status or the earned gap.

    When an explicit makeup scope is active, coverage is judged against that
    group's *historical* bar instead of its total minimum credit, so a group
    whose requirement is arranged entirely after the historical range cannot
    demand historical makeup credits.
    """
    if not isinstance(diff, CurriculumDiff):
        raise CurriculumNormalizationError("diff: expected a CurriculumDiff")
    group = next((value for value in diff.new.groups if value.group_id == group_id), None)
    if group is None or group.minimum_credit is None or not diff.new.complete:
        return False
    counts = Counter(match.target.course_id for match in diff.matches)
    if any(count != 1 for count in counts.values()):
        return False
    if diff.makeup_scope is None:
        bar = group.minimum_credit
        eligible = list(diff.matches)
    else:
        gap = next((value for value in diff.group_gaps if value.group_id == group_id), None)
        if gap is not None:
            if gap.historical_ambiguous:
                # The historical share of the minimum is unstated: never split it.
                return False
            if gap.scope == GROUP_SCOPE_FUTURE:
                return gap.remaining_credit == 0
            bar = gap.historical_minimum_credit if gap.historical_minimum_credit is not None else group.minimum_credit
        else:
            bar = group.minimum_credit
        eligible = [
            match for match in diff.matches
            if match.target.group_id == group_id
            and diff.scope_bucket(match.target.course_id) == SCOPE_HISTORICAL
        ]
    selected = set(selected_elective_course_ids(diff))
    try:
        coverage = math.fsum(
            match.target.credit for match in eligible
            if match.target.group_id == group_id and (
                match.status is MakeupStatus.SATISFIED
                or match.target.requirement is RequirementKind.REQUIRED
                or (match.target.requirement is RequirementKind.ELECTIVE and match.target.course_id in selected)
            )
        )
    except OverflowError:
        return False
    return math.isfinite(coverage) and coverage >= bar


def elective_plan_covers_group(diff: CurriculumDiff, group_id: str) -> bool:
    """Compatibility wrapper for the general flat-group plan coverage check."""
    return group_plan_covers_requirement(diff, group_id)


def project_makeup_tasks(diff: CurriculumDiff) -> list[MakeupTask]:
    """Project flat groups covered by known mandatory tasks or explicit choices."""
    _require_built_diff(diff)
    if not diff.new.complete:
        raise CurriculumNormalizationError("target curriculum is incomplete")
    # The scope only stops *unmet future requirements* from being reported as
    # current makeup. An entry already confirmed SATISFIED keeps its existing
    # public semantics and must never be withheld because of its term.
    def historical_unmet(match: CourseMatch) -> bool:
        if match.status is MakeupStatus.SATISFIED:
            return False
        return (diff.makeup_scope is not None
                and diff.scope_bucket(match.target.course_id) == SCOPE_FUTURE)

    def unresolved_unmet(match: CourseMatch) -> bool:
        if match.status is MakeupStatus.SATISFIED:
            return False
        return (diff.makeup_scope is not None
                and diff.scope_bucket(match.target.course_id) == SCOPE_UNRESOLVED)

    # An uninterpretable arrangement term on an unmet requirement is a missing
    # manual range decision, not a future course: fail closed.
    unresolved_unmet_ids = [m.target.course_id for m in diff.matches if unresolved_unmet(m)]
    if unresolved_unmet_ids:
        raise CurriculumNormalizationError(
            "makeup scope: target entries have no confirmable arrangement term"
        )
    if diff.unrepresented_requirements:
        raise CurriculumNormalizationError("group requirements cannot be projected to MakeupTask")
    ids = [match.target.course_id for match in diff.matches]
    if len(set(ids)) != len(ids):
        raise CurriculumNormalizationError("duplicate target course requirements cannot be projected")
    by_id = {match.target.course_id: match for match in diff.matches}
    groups_by_id = {group.group_id: group for group in diff.new.groups}
    for gap in diff.group_gaps:
        if gap.scope == GROUP_SCOPE_FUTURE:
            # No member is arranged within the historical range: nothing to project.
            continue
        if groups_by_id[gap.group_id].minimum_credit is None:
            raise CurriculumNormalizationError("group requirements cannot be projected to MakeupTask")
        if gap.historical_ambiguous:
            raise CurriculumNormalizationError(
                "group scope: mixed group minimum credit cannot be split without a decision"
            )
        if not group_plan_covers_requirement(diff, gap.group_id):
            raise CurriculumNormalizationError("group plan cannot cover the known credit requirement")
    selected_tasks = set(selected_elective_course_ids(diff))

    emitted_ids = {
        match.target.course_id for match in diff.matches
        if not historical_unmet(match)
        and (
            match.target.requirement is not RequirementKind.ELECTIVE
            or match.status is MakeupStatus.SATISFIED or match.target.course_id in selected_tasks
        )
    }
    referenced_pool: set[str] = set()
    pending = [course_id for course_id in emitted_ids if by_id[course_id].status is not MakeupStatus.SATISFIED]
    while pending:
        course_id = pending.pop()
        for reference in by_id[course_id].target.prerequisites or ():
            predecessor = by_id.get(reference)
            if (predecessor is not None and predecessor.target.requirement is RequirementKind.ELECTIVE
                    and predecessor.status is not MakeupStatus.SATISFIED and reference not in emitted_ids):
                referenced_pool.add(reference)
                emitted_ids.add(reference)
                pending.append(reference)
    scope_evidence = {
        decision.course_id: decision.evidence
        for decision in diff.scope_decisions if decision.evidence is not None
    }
    tasks: list[MakeupTask] = []
    for match in diff.matches:
        target = match.target
        if target.course_id not in emitted_ids:
            continue
        reason = match.reason
        status = match.status
        evidence = "；".join(match.evidence)
        if target.course_id in scope_evidence:
            # An explicit human range decision stays auditable on the task.
            evidence += f"；人工范围确认依据：{scope_evidence[target.course_id]}"
        if target.course_id in selected_tasks:
            reason += "人工已确认选修计划范围，所列学分是未来计划，不表示课程已修或选修组已满足。"
        elif target.course_id in referenced_pool:
            status = MakeupStatus.MANUAL_CONFIRMATION
            reason += "选修池课程被未满足目标课程引用为先修，是否需要独立修读及选修认定待人工确认。"
            group = groups_by_id[target.group_id]
            evidence += f"；先修引用涉及选修池：{diff.new.source_id}#{group.source_record}"
        if target.prerequisites is None:
            reason += "先修关系未知，待人工确认。"
            evidence += "；先修关系未确认"
            if status is not MakeupStatus.SATISFIED:
                status = MakeupStatus.MANUAL_CONFIRMATION
        tasks.append(MakeupTask(
            course_id=target.course_id, course_name=target.course_name, credit=target.credit,
            status=status, recommended_semester=target.recommended_semester,
            deadline_semester=target.deadline_semester, prerequisites=list(target.prerequisites or ()),
            reason=reason, source_evidence=evidence,
        ))
    return tasks


def project_courses(version: CurriculumVersion) -> list[Course]:
    """Export unambiguous, complete course entries through the existing model."""
    if not isinstance(version, CurriculumVersion):
        raise CurriculumNormalizationError("curriculum: expected a CurriculumVersion")
    if not version.complete:
        raise CurriculumNormalizationError("curriculum is incomplete")
    ids = [entry.course_id for entry in version.courses]
    if len(set(ids)) != len(ids):
        raise CurriculumNormalizationError("duplicate course contexts cannot be projected")
    result = []
    for entry in version.courses:
        source = f"{version.source_id}#{entry.source_record}"
        if entry.prerequisites is None:
            source += "；先修关系未确认"
        result.append(Course(
            course_id=entry.course_id, course_name=entry.course_name, credit=entry.credit,
            course_type=entry.course_type, recommended_semester=entry.recommended_semester,
            prerequisites=list(entry.prerequisites or ()), source=source,
        ))
    return result


@dataclass(frozen=True, slots=True)
class CurriculumResultProvider:
    diff: CurriculumDiff

    def __post_init__(self) -> None:
        _require_built_diff(self.diff)

    def get_makeup_tasks(self) -> list[MakeupTask]:
        return project_makeup_tasks(self.diff)
