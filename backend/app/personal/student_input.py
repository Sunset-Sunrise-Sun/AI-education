"""个人规划输入（**非公共契约**，只在 Personal Planning 模块内部使用）。

```text
学生本次输入（所选版本 id + 本人已修事实 + 本人认定凭据 + 偏好 + 现有课表）
        ↓  normalize_student_input(...)
StudentInput（已校验、已归一化的**本人**输入）
```

## 这个模块为什么存在

旧 Case A 的输入是**固定 case 文件**：一位学生的已修事实、个案规则与范围决定
全部写在 case JSON 里。个人规划入口必须能让**另一位学生**用自己的材料，
在**同一个已核验目标培养方案**上独立算出自己的结果，而⛔ **不能**继承
Case A 的 `satisfied` 状态、个案认定或范围裁定。

因此这里刻意把"这一位学生的输入"做成**显式对象**，并且：

- ⛔ **不复用任何 case 文件**：调用方传什么就是什么，模型不知道 Case A 存在；
- ⛔ **不新增 / 不修改公共 Schema**：本模块的对象不是公共契约，
  `CourseOffering` / `Preference` 仍复用 `app.models.contracts` 的现有模型；
- ⛔ **不做课程认定**：`ConfirmedRecognition` 只是**接受**调用方给出的、
  已有正式依据的认定事实；本模块不判断等价、不认定学分、不生成优先级；
- ⛔ **不接受"来源不明"的认定**：每条认定都必须写明 `evidence`，且必须属于
  **本人**已修来源（`completed_source_id` 由调用方给出，⛔ 不取学生行里的值）。

## 与 Curriculum 内部对象的关系

`StudentInput` 最终被组装成**既有** `CurriculumCase` 的输入形态，
交给既有 `normalize_curriculum_case` / `build_curriculum_diff` 计算。
本模块⛔ **不**复制、重写任何匹配 / 组学分 / scope 判定逻辑。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.curriculum.completed_courses import CompletedCourse, normalize_completed_courses
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedElectiveSelection,
    ConfirmedGroupScopeDecision,
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    MakeupScope,
    MatchingRules,
)
from app.curriculum.terms import ConfirmedScopeDecision
from app.models.contracts import CourseOffering, DataSource, Preference

__all__ = [
    "PLANNING_ASSUMPTION_LABEL",
    "STUDENT_INPUT_FIELDS",
    "PlanningAssumption",
    "StudentInput",
    "normalize_student_input",
]

#: 规划假设的**显式**标记：一个"我认为我修过 / 我打算修"的假设，
#: 与"已有正式认定凭据"是两件不同的事，必须在输出里可区分。
PLANNING_ASSUMPTION_LABEL = "planning_assumption_not_a_recognition"

#: 本模块接受的输入字段（⛔ 未知字段直接拒绝，不猜测）。
STUDENT_INPUT_FIELDS = (
    "completed",
    "recognitions",
    "missing_requirements",
    "elective_selections",
    "planning_assumptions",
    "rules",
    "makeup_scope",
    "confirmed_scope_decisions",
    "confirmed_group_scope_decisions",
    "preference",
    "current_schedule",
)

_COMPLETED_REQUIRED: tuple[str, ...] = ()
_COMPLETED_ALLOWED = frozenset({"source_id", "complete", "completeness_evidence", "records"})

_RULES_REQUIRED = ("evidence",)
_RULES_ALLOWED = frozenset(_RULES_REQUIRED) | {
    "target_version_id", "completed_source_id", "allow_exact_match", "allow_confirmed_absence",
}

_SCOPE_REQUIRED = ("as_of_term", "evidence")
_SCOPE_ALLOWED = frozenset(_SCOPE_REQUIRED) | {"target_version_id"}

_ASSUMPTION_REQUIRED = ("course_id", "evidence")
_ASSUMPTION_ALLOWED = frozenset(_ASSUMPTION_REQUIRED) | {"note"}

_RECOGNITION_REQUIRED = (
    "target_course_id", "completed_source_record", "recognized_credit", "evidence",
)
_RECOGNITION_ALLOWED = frozenset(_RECOGNITION_REQUIRED) | {"target_version_id", "completed_source_id"}

_MISSING_REQUIRED = ("target_course_id", "evidence")
_MISSING_ALLOWED = frozenset(_MISSING_REQUIRED) | {"target_version_id", "completed_source_id"}

_SELECTION_REQUIRED = ("group_id", "course_ids", "evidence")
_SELECTION_ALLOWED = frozenset(_SELECTION_REQUIRED) | {"target_version_id"}

_SCOPE_DECISION_REQUIRED = ("target_source_record", "target_course_id", "decision", "evidence")
_SCOPE_DECISION_ALLOWED = frozenset(_SCOPE_DECISION_REQUIRED) | {"target_version_id"}

_GROUP_DECISION_REQUIRED = ("group_id", "historical_minimum_credit", "evidence")
_GROUP_DECISION_ALLOWED = frozenset(_GROUP_DECISION_REQUIRED) | {"target_version_id"}


def _object(value: object, *, required: tuple[str, ...], allowed: frozenset[str], label: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise CurriculumNormalizationError(f"{label}: expected an object")
    if any(key not in allowed for key in value):
        # ⛔ 不回报未知键名：键名本身也可能夹带私有来源文本。
        raise CurriculumNormalizationError(f"{label}: unexpected record field")
    for field in required:
        if field not in value:
            raise CurriculumNormalizationError(f"{label}: missing field {field}")
    return value


def _sequence(value: object, field: str) -> Sequence:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CurriculumNormalizationError(f"{field}: expected a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CurriculumNormalizationError(f"{field}: expected a string or null")
    return value if value.strip() else None


def _bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise CurriculumNormalizationError(f"{field}: expected a boolean")
    return value


def _match_declared_version(value: object, expected: str, field: str) -> None:
    """若调用方给出了版本 id，就必须与本次选定版本一致；不给则由系统填入。"""

    declared = _optional_text(value, field)
    if declared is not None and declared != expected:
        raise CurriculumNormalizationError(f"{field}: outside the selected target version")


def _match_declared_source(value: object, expected: str, field: str) -> None:
    declared = _optional_text(value, field)
    if declared is not None and declared != expected:
        raise CurriculumNormalizationError(
            f"{field}: recorded evidence belongs to another completed source"
        )


@dataclass(frozen=True, slots=True)
class PlanningAssumption:
    """一条**明确标注的规划假设**（不是认定）。

    典型用法：学生说"我这门课应该能抵"或"我打算下学期修这门"。
    它不是正式认定凭据，因此：

    - ⛔ 绝不改变任何 `MakeupTask.status`；
    - ✅ 只作为**待人工核验**的依据带进 `source_evidence`，
      让人工能区分"有凭据的认定"与"学生假设"。
    """

    course_id: str
    evidence: str
    note: str | None = None

    def __post_init__(self) -> None:
        _text(self.course_id, "assumption course_id")
        _text(self.evidence, "assumption evidence")
        object.__setattr__(self, "note", _optional_text(self.note, "assumption note"))


@dataclass(frozen=True, slots=True)
class StudentInput:
    """**这一位学生**的完整输入（已归一化，尚未计算）。"""

    data_source: DataSource
    completed: tuple[CompletedCourse, ...]
    completed_source_id: str
    completed_complete: bool
    completed_completeness_evidence: str | None
    rules: MatchingRules | None
    recognitions: tuple[ConfirmedRecognition, ...]
    missing_requirements: tuple[ConfirmedMissingRequirement, ...]
    elective_selections: tuple[ConfirmedElectiveSelection, ...]
    confirmed_scope_decisions: tuple[ConfirmedScopeDecision, ...]
    confirmed_group_scope_decisions: tuple[ConfirmedGroupScopeDecision, ...]
    makeup_scope: MakeupScope | None
    planning_assumptions: tuple[PlanningAssumption, ...]
    preference: Preference
    current_schedule: tuple[CourseOffering, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.data_source, DataSource):
            raise CurriculumNormalizationError("data_source: expected an explicit data source")
        _text(self.completed_source_id, "completed_source_id")
        _bool(self.completed_complete, "completed_complete")
        object.__setattr__(
            self, "completed_completeness_evidence",
            _optional_text(self.completed_completeness_evidence, "completed_completeness_evidence"),
        )
        if self.completed_complete and self.completed_completeness_evidence is None:
            raise CurriculumNormalizationError(
                "completed_completeness_evidence: a complete transcript requires explicit evidence"
            )
        for field, kind in (
            ("completed", CompletedCourse),
            ("recognitions", ConfirmedRecognition),
            ("missing_requirements", ConfirmedMissingRequirement),
            ("elective_selections", ConfirmedElectiveSelection),
            ("confirmed_scope_decisions", ConfirmedScopeDecision),
            ("confirmed_group_scope_decisions", ConfirmedGroupScopeDecision),
            ("planning_assumptions", PlanningAssumption),
            ("current_schedule", CourseOffering),
        ):
            values = tuple(getattr(self, field))
            if any(not isinstance(value, kind) for value in values):
                raise CurriculumNormalizationError(f"{field}: unexpected item type")
            object.__setattr__(self, field, values)
        if self.rules is not None and not isinstance(self.rules, MatchingRules):
            raise CurriculumNormalizationError("rules: unexpected type")
        if self.makeup_scope is not None and not isinstance(self.makeup_scope, MakeupScope):
            raise CurriculumNormalizationError("makeup_scope: unexpected type")
        if not isinstance(self.preference, Preference):
            raise CurriculumNormalizationError("preference: expected a Preference")

        # 本人来源一致性：⛔ 不允许把别的学生的修读记录混进来。
        if {record.source_id for record in self.completed} - {self.completed_source_id}:
            raise CurriculumNormalizationError(
                "completed: records must belong to this student's completed source"
            )
        for decision in (*self.recognitions, *self.missing_requirements):
            if decision.completed_source_id != self.completed_source_id:
                raise CurriculumNormalizationError(
                    "decision: recorded evidence belongs to another completed source"
                )
        pairs = [
            (value.target_course_id, value.completed_source_record)
            for value in self.recognitions
        ]
        if len(set(pairs)) != len(pairs):
            raise CurriculumNormalizationError("recognitions: duplicate decision for one record")
        assumptions = [value.course_id for value in self.planning_assumptions]
        if len(set(assumptions)) != len(assumptions):
            raise CurriculumNormalizationError("planning_assumptions: duplicate course reference")

    @property
    def assumption_course_ids(self) -> tuple[str, ...]:
        return tuple(value.course_id for value in self.planning_assumptions)

    def assumption_evidence_for(self, course_id: str) -> tuple[str, ...]:
        return tuple(
            f"{PLANNING_ASSUMPTION_LABEL}：{value.evidence}"
            for value in self.planning_assumptions
            if value.course_id == course_id
        )


def normalize_student_input(
    payload: object,
    *,
    target_version_id: str,
    completed_source_id: str,
    data_source: DataSource,
) -> StudentInput:
    """把一次个人规划请求归一化成**本人**输入。

    ``target_version_id`` 是**已被目录解析过**的目标版本；
    ``completed_source_id`` 由调用方（而不是学生数据）给出：
    ⛔ 不允许学生行自带来源 id，否则一行数据就能冒充"另一个来源的已修记录"。
    """

    if not isinstance(data_source, DataSource):
        raise CurriculumNormalizationError("data_source: expected an explicit data source")
    _text(target_version_id, "target_version_id")
    _text(completed_source_id, "completed_source_id")
    if not isinstance(payload, Mapping):
        raise CurriculumNormalizationError("student input: expected an object")
    if any(key not in STUDENT_INPUT_FIELDS for key in payload):
        raise CurriculumNormalizationError("student input: unexpected record field")

    completed_record = _object(
        payload.get("completed", {}), required=_COMPLETED_REQUIRED,
        allowed=_COMPLETED_ALLOWED, label="completed",
    )
    completed = normalize_completed_courses(
        _sequence(completed_record.get("records", ()), "completed records"),
        source_id=completed_source_id,
    )
    completed_complete = _bool(completed_record.get("complete", False), "completed complete")
    completed_evidence = _optional_text(
        completed_record.get("completeness_evidence"), "completed completeness_evidence"
    )
    if completed_complete and completed_evidence is None:
        raise CurriculumNormalizationError(
            "completed_completeness_evidence: a complete transcript requires explicit evidence"
        )
    _match_declared_source(completed_record.get("source_id"), completed_source_id, "completed source_id")

    rules = None
    if payload.get("rules") is not None:
        rules_record = _object(
            payload["rules"], required=_RULES_REQUIRED, allowed=_RULES_ALLOWED, label="rules",
        )
        _match_declared_version(rules_record.get("target_version_id"), target_version_id,
                               "rules target_version_id")
        _match_declared_source(rules_record.get("completed_source_id"), completed_source_id,
                               "rules completed_source_id")
        rules = MatchingRules(
            target_version_id=target_version_id,
            completed_source_id=completed_source_id,
            evidence=rules_record["evidence"],
            allow_exact_match=_bool(rules_record.get("allow_exact_match", False),
                                    "rules allow_exact_match"),
            allow_confirmed_absence=_bool(rules_record.get("allow_confirmed_absence", False),
                                          "rules allow_confirmed_absence"),
        )

    recognitions = []
    for row in _sequence(payload.get("recognitions", ()), "recognitions"):
        item = _object(row, required=_RECOGNITION_REQUIRED, allowed=_RECOGNITION_ALLOWED,
                       label="recognitions")
        _match_declared_version(item.get("target_version_id"), target_version_id,
                                "recognition target_version_id")
        _match_declared_source(item.get("completed_source_id"), completed_source_id,
                               "recognition completed_source_id")
        recognitions.append(ConfirmedRecognition(
            target_version_id=target_version_id,
            target_course_id=item["target_course_id"],
            completed_source_id=completed_source_id,
            completed_source_record=item["completed_source_record"],
            recognized_credit=item["recognized_credit"],
            evidence=item["evidence"],
        ))

    missing_requirements = []
    for row in _sequence(payload.get("missing_requirements", ()), "missing_requirements"):
        item = _object(row, required=_MISSING_REQUIRED, allowed=_MISSING_ALLOWED,
                       label="missing_requirements")
        _match_declared_version(item.get("target_version_id"), target_version_id,
                                "missing requirement target_version_id")
        _match_declared_source(item.get("completed_source_id"), completed_source_id,
                               "missing requirement completed_source_id")
        missing_requirements.append(ConfirmedMissingRequirement(
            target_version_id=target_version_id,
            target_course_id=item["target_course_id"],
            completed_source_id=completed_source_id,
            evidence=item["evidence"],
        ))

    selections = []
    for row in _sequence(payload.get("elective_selections", ()), "elective_selections"):
        item = _object(row, required=_SELECTION_REQUIRED, allowed=_SELECTION_ALLOWED,
                       label="elective_selections")
        _match_declared_version(item.get("target_version_id"), target_version_id,
                                "elective selection target_version_id")
        selections.append(ConfirmedElectiveSelection(
            target_version_id=target_version_id,
            group_id=item["group_id"],
            course_ids=_sequence(item["course_ids"], "selection course_ids"),
            evidence=item["evidence"],
        ))

    confirmed_scope = []
    for row in _sequence(payload.get("confirmed_scope_decisions", ()), "confirmed_scope_decisions"):
        item = _object(row, required=_SCOPE_DECISION_REQUIRED, allowed=_SCOPE_DECISION_ALLOWED,
                       label="confirmed_scope_decisions")
        _match_declared_version(item.get("target_version_id"), target_version_id,
                                "scope decision target_version_id")
        confirmed_scope.append(ConfirmedScopeDecision(
            target_version_id=target_version_id,
            target_source_record=item["target_source_record"],
            target_course_id=item["target_course_id"],
            decision=item["decision"],
            evidence=item["evidence"],
        ))

    confirmed_group_scope = []
    for row in _sequence(
        payload.get("confirmed_group_scope_decisions", ()), "confirmed_group_scope_decisions"
    ):
        item = _object(row, required=_GROUP_DECISION_REQUIRED, allowed=_GROUP_DECISION_ALLOWED,
                       label="confirmed_group_scope_decisions")
        _match_declared_version(item.get("target_version_id"), target_version_id,
                                "group scope decision target_version_id")
        confirmed_group_scope.append(ConfirmedGroupScopeDecision(
            target_version_id=target_version_id,
            group_id=item["group_id"],
            historical_minimum_credit=item["historical_minimum_credit"],
            evidence=item["evidence"],
        ))

    makeup_scope = None
    if payload.get("makeup_scope") is not None:
        scope_record = _object(
            payload["makeup_scope"], required=_SCOPE_REQUIRED, allowed=_SCOPE_ALLOWED,
            label="makeup_scope",
        )
        _match_declared_version(scope_record.get("target_version_id"), target_version_id,
                                "makeup scope target_version_id")
        makeup_scope = MakeupScope(
            target_version_id=target_version_id,
            as_of_term=scope_record["as_of_term"],
            evidence=scope_record["evidence"],
        )

    assumptions = []
    for row in _sequence(payload.get("planning_assumptions", ()), "planning_assumptions"):
        item = _object(row, required=_ASSUMPTION_REQUIRED, allowed=_ASSUMPTION_ALLOWED,
                       label="planning_assumptions")
        assumptions.append(PlanningAssumption(
            course_id=item["course_id"], evidence=item["evidence"], note=item.get("note"),
        ))

    preference_payload = payload.get("preference", {})
    preference = (
        preference_payload if isinstance(preference_payload, Preference)
        else Preference.model_validate(preference_payload)
    )

    current_schedule = []
    for item in _sequence(payload.get("current_schedule", []), "current_schedule"):
        if not isinstance(item, CourseOffering):
            raise CurriculumNormalizationError("current_schedule: expected CourseOffering items")
        current_schedule.append(item)

    return StudentInput(
        data_source=data_source,
        completed=completed,
        completed_source_id=completed_source_id,
        completed_complete=completed_complete,
        completed_completeness_evidence=completed_evidence,
        rules=rules,
        recognitions=tuple(recognitions),
        missing_requirements=tuple(missing_requirements),
        elective_selections=tuple(selections),
        confirmed_scope_decisions=tuple(confirmed_scope),
        confirmed_group_scope_decisions=tuple(confirmed_group_scope),
        makeup_scope=makeup_scope,
        planning_assumptions=tuple(assumptions),
        preference=preference,
        current_schedule=tuple(current_schedule),
    )
