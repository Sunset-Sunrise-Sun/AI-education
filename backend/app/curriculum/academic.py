"""Internal, source-backed dependency checks and explicitly requested ordering.

No school rules, prerequisite edges, deadlines, weights, or semester schedules
are inferred here. The public MakeupTask list and its order remain unchanged.
"""

from __future__ import annotations

import heapq
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import CurriculumDiff, group_plan_covers_requirement, selected_elective_course_ids
from app.curriculum.requirements import RequirementKind
from app.models.contracts import MakeupStatus

__all__ = ["AcademicIssue", "AcademicAnalysis", "PriorityPolicy", "analyze_academic_path"]


def _text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")


def _references(values: object, field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CurriculumNormalizationError(f"{field}: expected source references")
    material = tuple(values)
    for value in material:
        _text(value, field)
    return material


@dataclass(frozen=True, slots=True)
class AcademicIssue:
    code: str
    course_id: str | None
    message: str
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.code, "issue code")
        _text(self.message, "issue message")
        if self.course_id is not None:
            _text(self.course_id, "issue course_id")
        object.__setattr__(self, "evidence", _references(self.evidence, "issue evidence"))


@dataclass(frozen=True, slots=True)
class AcademicAnalysis:
    issues: tuple[AcademicIssue, ...]
    dependency_order: tuple[str, ...] | None
    priority_order: tuple[str, ...] | None

    def __post_init__(self) -> None:
        if isinstance(self.issues, (str, bytes, bytearray)) or not isinstance(self.issues, Sequence):
            raise CurriculumNormalizationError("issues: expected issue entries")
        material = tuple(self.issues)
        if any(not isinstance(issue, AcademicIssue) for issue in material):
            raise CurriculumNormalizationError("issues: unexpected issue type")
        object.__setattr__(self, "issues", material)
        for field in ("dependency_order", "priority_order"):
            value = getattr(self, field)
            if value is not None:
                order = _references(value, field)
                if len(set(order)) != len(order):
                    raise CurriculumNormalizationError(f"{field}: duplicate course references")
                object.__setattr__(self, field, order)


@dataclass(frozen=True, slots=True)
class PriorityPolicy:
    """A caller-confirmed internal policy, scoped to one target version.

    ``deadline_first=False`` uses source order among currently available nodes.
    Neither mode defines weights or changes the public Provider's task order.
    """

    target_version_id: str
    evidence: str
    deadline_first: bool = True

    def __post_init__(self) -> None:
        _text(self.target_version_id, "priority target_version_id")
        _text(self.evidence, "priority evidence")
        if type(self.deadline_first) is not bool:
            raise CurriculumNormalizationError("deadline_first: expected a boolean")


def _topological_order(
    course_ids: tuple[str, ...], prerequisites: dict[str, tuple[str, ...]],
    deadlines: dict[str, int] | None = None,
) -> tuple[str, ...] | None:
    """Use only supplied edges; source order is a deterministic tie breaker."""
    indices = {course_id: index for index, course_id in enumerate(course_ids)}
    indegree = {course_id: len(prerequisites.get(course_id, ())) for course_id in course_ids}
    followers: dict[str, list[str]] = {course_id: [] for course_id in course_ids}
    for course_id, required in prerequisites.items():
        for prerequisite in required:
            followers[prerequisite].append(course_id)

    def key(course_id: str) -> tuple[int, int, str]:
        return (deadlines[course_id] if deadlines is not None else 0, indices[course_id], course_id)

    available = [key(course_id) for course_id in course_ids if indegree[course_id] == 0]
    heapq.heapify(available)
    order: list[str] = []
    while available:
        _, _, course_id = heapq.heappop(available)
        order.append(course_id)
        for follower in followers[course_id]:
            indegree[follower] -= 1
            if indegree[follower] == 0:
                heapq.heappush(available, key(follower))
    return tuple(order) if len(order) == len(course_ids) else None


def analyze_academic_path(
    diff: CurriculumDiff, *, priority_policy: PriorityPolicy | None = None,
) -> AcademicAnalysis:
    """Describe known facts without promoting uncertainty to a final plan.

    Dependency order covers supplied target entries, including satisfied ones.
    Priority order covers only confirmed required tasks. An external course is
    not deemed satisfied merely because a matching candidate was passed.
    """
    if not isinstance(diff, CurriculumDiff):
        raise CurriculumNormalizationError("diff: expected a CurriculumDiff")
    if priority_policy is not None:
        if not isinstance(priority_policy, PriorityPolicy):
            raise CurriculumNormalizationError("priority_policy: unexpected policy type")
        if priority_policy.target_version_id != diff.new.version_id:
            raise CurriculumNormalizationError("priority policy: target version mismatch")

    issues: list[AcademicIssue] = []
    graph_complete = diff.new.complete
    priority_complete = True

    def issue(code: str, course_id: str | None, message: str, evidence: tuple[str, ...]) -> None:
        issues.append(AcademicIssue(code, course_id, message, evidence))

    if not diff.new.complete:
        issue("curriculum_incomplete", None, "目标培养方案范围尚未确认完整。", (diff.new.source_id,))
    if (
        diff.new.total_credit is not None
        and diff.new.practice_credit is not None
        and diff.new.practice_credit > diff.new.total_credit
    ):
        issue("credit_summary_inconsistent", None, "来源中的实践学分高于总学分，汇总事实需核对。", (diff.new.source_id,))
    counts = Counter(match.target.course_id for match in diff.matches)
    course_ids = tuple(counts)
    by_id = {match.target.course_id: match for match in diff.matches}
    selected_electives = set(selected_elective_course_ids(diff))
    for course_id, count in counts.items():
        if count > 1:
            graph_complete = False
            issue("duplicate_course_id", course_id, "同一课程号存在多个要求条目，依赖归属尚未确认。", by_id[course_id].evidence)

    edges: dict[str, tuple[str, ...]] = {}
    external_references: dict[str, None] = {}
    for match in diff.matches:
        target = match.target
        course_id = target.course_id
        needed_requirement = target.requirement is not RequirementKind.ELECTIVE or course_id in selected_electives
        if match.status in {MakeupStatus.MANUAL_CONFIRMATION, MakeupStatus.POSSIBLY_EQUIVALENT}:
            issue("matching_unconfirmed", course_id, "课程匹配或认定仍需人工确认。", match.evidence)
            if needed_requirement:
                priority_complete = False
        if (
            target.recommended_semester is not None and target.deadline_semester is not None
            and target.recommended_semester > target.deadline_semester
        ):
            issue("recommended_semester_after_deadline", course_id,
                  "来源推荐学期晚于期限，需核对课程要求；不能据此判断实际安排或逾期。", match.evidence)
        if target.prerequisites is None:
            graph_complete = False
            issue("prerequisites_unknown", course_id, "来源尚未确认先修关系，不能当作没有先修。", match.evidence)
        else:
            # Repeated source contexts remain ambiguous. Retain all explicit
            # edges for diagnosis rather than letting a later row erase them.
            edges[course_id] = tuple(dict.fromkeys(edges.get(course_id, ()) + target.prerequisites))
            for reference in target.prerequisites:
                if reference not in by_id:
                    external_references[reference] = None
                    graph_complete = False
                    issue("external_prerequisite_unresolved", course_id, "先修课程在目标范围外，尚无明确已满足依据。", match.evidence)
                elif (
                    match.status is MakeupStatus.REQUIRED
                    and by_id[reference].status not in {MakeupStatus.SATISFIED, MakeupStatus.REQUIRED}
                ):
                    priority_complete = False
                    issue("prerequisite_match_unconfirmed", course_id, "先修课程的满足或补修结论尚未确认。", match.evidence + by_id[reference].evidence)
        if match.status is not MakeupStatus.SATISFIED and needed_requirement:
            if target.deadline_semester is None:
                if priority_policy is not None and priority_policy.deadline_first:
                    priority_complete = False
                issue("deadline_unknown", course_id, "来源未提供明确的整数补修期限，不能从推荐学期推断。", match.evidence)

    # These comparisons identify source-data pressure, not semester feasibility.
    # A later prerequisite deadline is an upper bound, not its scheduled term.
    for match in diff.matches:
        target = match.target
        if match.status is not MakeupStatus.REQUIRED or target.deadline_semester is None:
            continue
        for reference in target.prerequisites or ():
            predecessor = by_id.get(reference)
            if (
                counts[target.course_id] == 1 and counts[reference] == 1
                and predecessor is not None and predecessor.status is MakeupStatus.REQUIRED
                and predecessor.target.deadline_semester is not None
                and target.deadline_semester < predecessor.target.deadline_semester
            ):
                issue("deadline_dependency_pressure", target.course_id,
                      "后续课程期限早于未满足的先修课程期限，应核对先修链安排；现有信息不能判断逾期或不可行。",
                      tuple(dict.fromkeys(match.evidence + predecessor.evidence)))

    if diff.new.complete:
        for group in diff.new.groups:
            members = tuple(course for course in diff.new.courses if course.group_id == group.group_id)
            if group.minimum_credit is None or any(counts[course.course_id] > 1 for course in members):
                continue
            try:
                capacity = math.fsum(course.credit for course in members)
            except OverflowError:
                # Nonnegative finite credits can only overflow above a finite
                # quota, so overflow cannot establish insufficient capacity.
                continue
            if capacity < group.minimum_credit:
                evidence = (f"{diff.new.source_id}#{group.source_record}",)
                evidence += tuple(f"{diff.new.source_id}#{course.source_record}" for course in members)
                evidence += (diff.new.completeness_evidence,)
                issue("group_capacity_insufficient", None,
                      "所提供完整课程组的课程池学分不足以达到组最低要求，需核对来源范围或要求。", evidence)

    for gap in diff.group_gaps:
        group = next((group for group in diff.new.groups if group.group_id == gap.group_id), None)
        evidence = (f"{diff.new.source_id}#{group.source_record}",) if group is not None else (diff.new.source_id,)
        if group_plan_covers_requirement(diff, gap.group_id):
            covered_matches = tuple(match for match in diff.matches if match.target.group_id == gap.group_id and (
                match.status is MakeupStatus.SATISFIED
                or match.target.requirement is RequirementKind.REQUIRED
                or (match.target.requirement is RequirementKind.ELECTIVE and match.target.course_id in selected_electives)
            ))
            future_requirements = tuple(match for match in covered_matches if match.status is not MakeupStatus.SATISFIED)
            plan_sources = []
            if any(match.target.requirement is RequirementKind.REQUIRED for match in future_requirements):
                plan_sources.append("已知必修要求")
            if any(match.target.requirement is RequirementKind.ELECTIVE for match in future_requirements):
                plan_sources.append("人工选修计划")
            evidence += tuple(reference for match in covered_matches for reference in match.evidence)
            evidence += tuple(selection.evidence for selection in diff.elective_selections if selection.group_id == gap.group_id)
            evidence += (diff.new.completeness_evidence,)
            issue("group_credit_outstanding", None,
                  f"课程组实际学分仍有缺口，{'及'.join(plan_sources)}可表达剩余计划；计划不表示学分已取得。",
                  tuple(dict.fromkeys(evidence)))
        else:
            priority_complete = False
            issue("group_requirement_unresolved", None, "课程组仍有未确认的学分要求或缺口。", evidence)
    if diff.unrepresented_requirements:
        priority_complete = False
        issue("unrepresented_requirement", None, "部分课程要求无法由现有任务表示完整表达。", (diff.new.source_id,))

    # Retain every explicit edge in the known subgraph. Missing adjacency facts
    # for unknown or external nodes never authorize exporting a complete order.
    known_order = _topological_order(course_ids + tuple(external_references), edges)
    if known_order is None:
        graph_complete = False
        issue("dependency_cycle", None, "已有先修边形成环，不能自行删除或改写。", tuple(f"{diff.new.source_id}#{match.target.source_record}" for match in diff.matches))
    dependency_order = known_order if graph_complete else None

    priority_order = None
    if priority_policy is None:
        issue("priority_unconfirmed", None, "尚未提供已确认的内部优先级策略。", ())
    elif dependency_order is not None and priority_complete:
        needed = tuple(match.target.course_id for match in diff.matches if match.status is MakeupStatus.REQUIRED)
        needed_set = set(needed)
        needed_edges = {
            course_id: tuple(reference for reference in edges[course_id] if reference in needed_set)
            for course_id in needed
        }
        deadlines = {course_id: by_id[course_id].target.deadline_semester for course_id in needed}
        priority_order = _topological_order(needed, needed_edges, deadlines if priority_policy.deadline_first else None)
    if priority_policy is not None and priority_order is None:
        issue("priority_unresolved", None, "依赖、认定或期限信息不足，不能给出最终优先顺序。", (priority_policy.evidence,))
    return AcademicAnalysis(tuple(issues), dependency_order, priority_order)
