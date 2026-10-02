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
from app.models.contracts import Course, MakeupStatus, MakeupTask

_BUILD_TOKEN = object()


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

    def __post_init__(self) -> None:
        _text(self.group_id, "group_id")
        _text(self.reason, "group reason")
        if self.remaining_credit is not None:
            value = self.remaining_credit
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CurriculumNormalizationError("remaining_credit: invalid number")
            try:
                value = float(value)
            except (OverflowError, ValueError):
                raise CurriculumNormalizationError("remaining_credit: invalid number") from None
            if not math.isfinite(value) or value < 0:
                raise CurriculumNormalizationError("remaining_credit: invalid number")
            object.__setattr__(self, "remaining_credit", value)


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
    _build_token: object = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.old, CurriculumVersion) or not isinstance(self.new, CurriculumVersion):
            raise CurriculumNormalizationError("diff: unexpected curriculum type")
        matches = _items(self.matches, CourseMatch, "matches")
        if tuple(match.target for match in matches) != self.new.courses:
            raise CurriculumNormalizationError("diff: matches must cover the supplied target entries in order")
        object.__setattr__(self, "matches", matches)
        object.__setattr__(self, "group_gaps", _items(self.group_gaps, GroupGap, "group_gaps"))
        for field in ("added_course_ids", "removed_course_ids", "changed_course_ids", "unrepresented_requirements"):
            value = getattr(self, field)
            if value is None and field != "unrepresented_requirements":
                continue
            values = _items(value, str, field)
            for item in values:
                _text(item, field)
            object.__setattr__(self, field, values)


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
) -> CurriculumDiff:
    """Use supplied decisions or case rules; defaults never approve equivalence."""
    if not isinstance(old, CurriculumVersion) or not isinstance(new, CurriculumVersion):
        raise CurriculumNormalizationError("curriculum: expected a CurriculumVersion")
    completed = _items(completed, CompletedCourse, "completed")
    recognitions = _items(recognitions, ConfirmedRecognition, "recognitions")
    missing_requirements = _items(missing_requirements, ConfirmedMissingRequirement, "missing_requirements")
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
        if any(course.requirement is not RequirementKind.REQUIRED for course in targets):
            raise CurriculumNormalizationError("missing requirement: target must be explicitly required")
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
        approved = granted[target.course_id]
        missing_decisions = missing[target.course_id]
        evidence.extend(decision.evidence for decision in (*approved, *missing_decisions))
        if rules is not None:
            evidence.append(f"case 匹配规则依据：{rules.evidence}")
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
        elif target.requirement is RequirementKind.ELECTIVE:
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
        matches.append(CourseMatch(target, status, candidates, reason, tuple(dict.fromkeys(evidence))))

    unrepresented: list[str] = []
    if any(course.requirement is RequirementKind.ELECTIVE and course.group_id is None for course in new.courses):
        unrepresented.append("elective course has no group requirement")
    group_gaps: list[GroupGap] = []
    for group in new.groups:
        if group.minimum_credit is None:
            group_gaps.append(GroupGap(group.group_id, None, "课程组学分要求尚未确认。"))
            continue
        try:
            covered = math.fsum(
                match.target.credit for match in matches
                if match.target.group_id == group.group_id and match.status is MakeupStatus.SATISFIED
            )
        except OverflowError:
            raise CurriculumNormalizationError("group credits: total is not finite") from None
        remaining = max(group.minimum_credit - covered, 0.0)
        if remaining > 0:
            group_gaps.append(GroupGap(group.group_id, remaining, "课程组仍有未确认满足的学分要求。"))

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
    diff = CurriculumDiff(old, new, tuple(matches), tuple(group_gaps), added, removed, changed, tuple(unrepresented))
    # Replacements and manually assembled results remain useful for inspection,
    # but cannot bypass the builder's recognition and group checks.
    object.__setattr__(diff, "_build_token", _BUILD_TOKEN)
    return diff


def _require_built_diff(diff: object) -> None:
    if not isinstance(diff, CurriculumDiff) or diff._build_token is not _BUILD_TOKEN:
        raise CurriculumNormalizationError("diff: rebuild before projecting planning results")


def project_makeup_tasks(diff: CurriculumDiff) -> list[MakeupTask]:
    """Project representable results without inventing tasks for group gaps."""
    _require_built_diff(diff)
    if not diff.new.complete:
        raise CurriculumNormalizationError("target curriculum is incomplete")
    if diff.group_gaps or diff.unrepresented_requirements:
        raise CurriculumNormalizationError("group requirements cannot be projected to MakeupTask")
    ids = [match.target.course_id for match in diff.matches]
    if len(set(ids)) != len(ids):
        raise CurriculumNormalizationError("duplicate target course requirements cannot be projected")
    tasks: list[MakeupTask] = []
    for match in diff.matches:
        target = match.target
        if target.requirement is RequirementKind.ELECTIVE and match.status is not MakeupStatus.SATISFIED:
            continue
        reason = match.reason
        status = match.status
        evidence = "；".join(match.evidence)
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
