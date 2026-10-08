"""结构化**意图草稿**（控制器内部对象，**不是**公共 Schema）。

```text
用户自然语言（"这学期太累，但数据结构必须保留、尽量别在周五上课"）
        ↓  DeepSeek / 注入式模型（只输出严格 JSON）
IntentDraft（范围 + 硬约束 + 软偏好 + 锁定课程 + 歧义）
        ↓  本地确定性校验（枚举白名单 + 课程 / 教学班白名单 + 学分依据）
用户确认后的 ConfirmedIntent（后端补齐指纹与范围）
```

## 为什么模型输出不能直接用

模型输出是**不可信建议**。它最多只能表达"用户想要什么"，
⛔ **不能**更改学校认定、毕业要求、先修关系、容量、学分事实或证据等级。
因此本模块：

- 用**严格枚举**而不是自由文本表达约束类型；
- 每个约束都必须能被本地规则**验证或标记为歧义**；
- "少上一点课 / 太累"**绝不**自动变成某个固定学分上限；
  没有明确数字就是 `credit_limit_missing_evidence` 歧义，必须由用户填写；
- 模型提到的课程号 / 教学班号必须落在上下文白名单内，否则整份草稿被拒绝。

## 与公共契约的关系

本模块的对象是**私有**的，且⛔ **不会**被塞进 `Preference` / `PlanResult` 等公共对象。
真正传给 Planner 的只有既有四参数签名里的 `Preference` 与 `current_schedule`。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from app.ai_planning.context import PlanningContext
from app.ai_planning.errors import IntentValidationError, ModelOutputInvalidError

__all__ = [
    "ADJUSTMENT_SCOPE_CURRENT_SEMESTER",
    "ADJUSTMENT_SCOPE_UNSUPPORTED",
    "AMBIGUITY_CODES",
    "CONSTRAINT_KINDS",
    "Ambiguity",
    "ConfirmedIntent",
    "HardConstraint",
    "IntentDraft",
    "LockedCourse",
    "SoftPreference",
    "parse_intent_draft",
    "validate_confirmed_intent",
]

ADJUSTMENT_SCOPE_CURRENT_SEMESTER: Final[str] = "current_semester"
ADJUSTMENT_SCOPE_UNSUPPORTED: Final[str] = "future_semesters"

#: 固定歧义码（前端按码渲染；⛔ 不解析自由文本判断）。
AMBIGUITY_CODES: Final[tuple[str, ...]] = (
    "credit_limit_missing_evidence",
    "credit_limit_conflicts_with_declared_max",
    "locked_course_unknown",
    "target_course_unknown",
    "target_class_unknown",
    "adjustment_scope_ambiguous",
    "adjustment_scope_unsupported",
    "constraint_kind_unknown",
    "soft_preference_not_executable",
    "no_adjustable_target",
)

CONSTRAINT_KINDS: Final[tuple[str, ...]] = (
    "max_credit_limit",
    "lock_course",
    "exclude_course",
    "avoid_weekday",
    "prefer_fewer_credits",
    "prefer_keep_prerequisites",
)

_SOFT_EXECUTABLE: Final[frozenset[str]] = frozenset({
    "avoid_weekday",
    "prefer_fewer_credits",
    "prefer_keep_prerequisites",
})

#: 课程号 / 教学班号的**形状**校验：只允许 ASCII 字母数字与 `-` `_`，
#: 防止把自由文本（或注入内容）当成课程号。
_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")

_MAX_TEXT: Final[int] = 200
_MAX_REFS: Final[int] = 200


class _Mode(str, Enum):
    HARD = "hard"
    SOFT = "soft"


def _text(value: object, field_name: str, *, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelOutputInvalidError(f"模型输出的 {field_name} 必须是非空字符串。")
    text = value.strip()
    if len(text) > limit:
        raise ModelOutputInvalidError(f"模型输出的 {field_name} 超长。")
    return text


def _optional_text(value: object, field_name: str, *, limit: int = _MAX_TEXT) -> str | None:
    if value is None:
        return None
    return _text(value, field_name, limit=limit)


def _code(value: object, field_name: str) -> str:
    text = _text(value, field_name, limit=40)
    if _CODE_PATTERN.fullmatch(text) is None:
        raise ModelOutputInvalidError(f"模型输出的 {field_name} 不是合法的课程 / 教学班标识。")
    return text


def _object(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise ModelOutputInvalidError(f"模型输出的 {field_name} 必须是对象。")
    return value


def _list(value: object, field_name: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ModelOutputInvalidError(f"模型输出的 {field_name} 必须是数组。")
    if len(value) > _MAX_REFS:
        raise ModelOutputInvalidError(f"模型输出的 {field_name} 条目过多。")
    return value


@dataclass(frozen=True, slots=True)
class Ambiguity:
    """一条**必须由用户消解**的歧义。"""

    code: str
    question: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.code not in AMBIGUITY_CODES:
            raise IntentValidationError("歧义码不在允许集合内。")
        _text(self.question, "ambiguity question")
        object.__setattr__(self, "detail", _optional_text(self.detail, "ambiguity detail"))


@dataclass(frozen=True, slots=True)
class LockedCourse:
    """用户明确要求**不得改动**的课程（必须已在当前方案里）。"""

    course_id: str
    class_id: str
    reason: str | None = None

    def __post_init__(self) -> None:
        _code(self.course_id, "locked course_id")
        _code(self.class_id, "locked class_id")
        object.__setattr__(self, "reason", _optional_text(self.reason, "locked reason"))


@dataclass(frozen=True, slots=True)
class HardConstraint:
    """硬约束：必须被满足，否则不得生成候选。"""

    kind: str
    value: float | None = None
    evidence: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in CONSTRAINT_KINDS:
            raise ModelOutputInvalidError("硬约束类型不在允许集合内。")
        object.__setattr__(self, "evidence", _optional_text(self.evidence, "constraint evidence"))
        if self.kind == "max_credit_limit":
            value = self.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                # "少上一点课" 不得被换算成某个固定学分数。
                raise ModelOutputInvalidError(
                    "max_credit_limit 必须给出明确数值，不能由模型自行推断。"
                )
            number = float(value)
            if not (0 <= number <= 60) or number != number:
                raise ModelOutputInvalidError("max_credit_limit 超出允许范围。")
            object.__setattr__(self, "value", number)
        elif self.value is not None:
            raise ModelOutputInvalidError(f"硬约束 {self.kind} 不接受数值。")


@dataclass(frozen=True, slots=True)
class SoftPreference:
    """软偏好：可以影响排序 / 提示，⛔ 但不能被当成硬规则证明无解。"""

    kind: str
    value: float | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in CONSTRAINT_KINDS:
            raise ModelOutputInvalidError("软偏好类型不在允许集合内。")
        object.__setattr__(self, "note", _optional_text(self.note, "soft note"))
        if self.value is not None:
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise ModelOutputInvalidError("软偏好数值必须是数字。")
            object.__setattr__(self, "value", float(self.value))


@dataclass(frozen=True, slots=True)
class IntentDraft:
    """模型输出的**结构化意图草稿**（已通过形状校验，尚未与上下文核对）。"""

    summary: str
    scope: str
    target_semester: str | None
    hard_constraints: tuple[HardConstraint, ...] = ()
    soft_preferences: tuple[SoftPreference, ...] = ()
    locked_courses: tuple[LockedCourse, ...] = ()
    confidence: float = 0.0
    notes: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        _text(self.summary, "summary")
        if self.scope not in (ADJUSTMENT_SCOPE_CURRENT_SEMESTER, ADJUSTMENT_SCOPE_UNSUPPORTED):
            raise ModelOutputInvalidError("模型输出的 scope 不在允许集合内。")
        object.__setattr__(self, "target_semester", _optional_text(self.target_semester, "semester", limit=20))
        confidence = self.confidence
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ModelOutputInvalidError("confidence 必须是数字。")
        number = float(confidence)
        if not (0.0 <= number <= 1.0):
            raise ModelOutputInvalidError("confidence 必须在 0..1。")
        object.__setattr__(self, "confidence", number)
        for name, kind in (
            ("hard_constraints", HardConstraint),
            ("soft_preferences", SoftPreference),
            ("locked_courses", LockedCourse),
        ):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, kind) for value in values):
                raise ModelOutputInvalidError(f"{name} 中条目类型非法。")
            seen: set = set()
            for value in values:
                key = (value.kind, value.value) if not isinstance(value, LockedCourse) else (
                    value.course_id, value.class_id,
                )
                if key in seen:
                    raise ModelOutputInvalidError(f"{name} 存在重复条目。")
                seen.add(key)
            object.__setattr__(self, name, values)
        notes = tuple(self.notes)
        object.__setattr__(self, "notes", tuple(_text(note, "note") for note in notes))


def parse_intent_draft(payload: object) -> IntentDraft:
    """把模型返回的 JSON **严格**解析成 `IntentDraft`。

    ⛔ 未知字段直接拒绝（不猜测、不忽略）；任何字段非法都抛 `ModelOutputInvalidError`。
    """

    record = _object(payload, "intent")
    allowed = {
        "summary", "scope", "target_semester", "hard_constraints", "soft_preferences",
        "locked_courses", "confidence", "notes",
    }
    if set(record) - allowed:
        raise ModelOutputInvalidError("模型输出包含未声明字段。")
    for required in ("summary", "scope"):
        if required not in record:
            raise ModelOutputInvalidError(f"模型输出缺少必填字段 {required}。")

    hard: list[HardConstraint] = []
    for row in _list(record.get("hard_constraints"), "hard_constraints"):
        item = _object(row, "hard_constraint")
        if set(item) - {"kind", "value", "evidence"}:
            raise ModelOutputInvalidError("hard_constraint 包含未声明字段。")
        hard.append(HardConstraint(
            kind=item.get("kind"), value=item.get("value"), evidence=item.get("evidence"),
        ))

    soft: list[SoftPreference] = []
    for row in _list(record.get("soft_preferences"), "soft_preferences"):
        item = _object(row, "soft_preference")
        if set(item) - {"kind", "value", "note"}:
            raise ModelOutputInvalidError("soft_preference 包含未声明字段。")
        soft.append(SoftPreference(
            kind=item.get("kind"), value=item.get("value"), note=item.get("note"),
        ))

    locked: list[LockedCourse] = []
    for row in _list(record.get("locked_courses"), "locked_courses"):
        item = _object(row, "locked_course")
        if set(item) - {"course_id", "class_id", "reason"}:
            raise ModelOutputInvalidError("locked_course 包含未声明字段。")
        locked.append(LockedCourse(
            course_id=item.get("course_id"), class_id=item.get("class_id"),
            reason=item.get("reason"),
        ))

    notes = tuple(_text(note, "note") for note in _list(record.get("notes"), "notes"))
    return IntentDraft(
        summary=record["summary"],
        scope=record["scope"],
        target_semester=record.get("target_semester"),
        hard_constraints=tuple(hard),
        soft_preferences=tuple(soft),
        locked_courses=tuple(locked),
        confidence=record.get("confidence", 0.0),
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# 与上下文核对（白名单 + 依据）
# --------------------------------------------------------------------------- #

def cross_check(
    draft: IntentDraft, context: PlanningContext,
) -> tuple[IntentDraft, tuple[Ambiguity, ...]]:
    """把草稿与**本次有效上下文**核对；返回（清理后的草稿, 歧义）。

    规则：

    - **白名单之外**的课程号 / 教学班号 ⇒ **整份草稿被拒绝**
      （`ModelOutputInvalidError`）：模型不许引入不存在的课程 / 班次，
      ⛔ 这不是"提示一下"，也⛔ 不允许静默丢弃；
    - 白名单内但**当前方案里没有选中**的锁定目标 ⇒ `target_course_unknown` 歧义，
      这类条目从草稿中移除（⛔ 不会凭模型输出锁定一门未选中的课）；
    - 硬约束 `max_credit_limit` 必须能被本地验证：
      无 `evidence` ⇒ `credit_limit_missing_evidence`（⛔ 模型不能自行把
      "少上一点"变成数字）；
      与上下文声明的上限冲突 ⇒ `credit_limit_conflicts_with_declared_max`；
    - 若上下文**没有**声明学分上限，而草稿也没有给出可验证的上限，
      则"是否超限"无法证明 ⇒ `credit_limit_missing_evidence`（保守留待用户填写）；
    - 未支持的调整范围（未来学期）⇒ 明确歧义，⛔ 不假装能改；
    - 目前没有可调整目标 ⇒ 歧义，避免生成一个"什么都没变"的候选。
    """

    ambiguities: list[Ambiguity] = []
    known_courses = context.course_ids
    known_keys = context.class_keys
    selected_keys = context.selected_keys()

    kept_locks: list[LockedCourse] = []
    for lock in draft.locked_courses:
        if lock.course_id not in known_courses:
            raise ModelOutputInvalidError(
                "模型输出的锁定课程不在本次有效数据里（已拒绝整份草稿）。"
            )
        if (lock.course_id, lock.class_id) not in known_keys:
            raise ModelOutputInvalidError(
                "模型输出的锁定教学班不在本次有效教学班里（已拒绝整份草稿）。"
            )
        if (lock.course_id, lock.class_id) not in selected_keys:
            ambiguities.append(Ambiguity(
                code="target_course_unknown",
                question=(
                    f"课程 {lock.course_id} 当前并未在方案里选中班次 {lock.class_id}，"
                    "无法锁定一个未选中的班，请确认意图。"
                ),
                detail=None,
            ))
            continue
        kept_locks.append(lock)

    kept_hard: list[HardConstraint] = []
    has_verifiable_limit = False
    for constraint in draft.hard_constraints:
        if constraint.kind == "max_credit_limit":
            if constraint.evidence is None:
                ambiguities.append(Ambiguity(
                    code="credit_limit_missing_evidence",
                    question=(
                        "你说的“少上一点 / 太累”没有给出明确学分上限。"
                        "请填写本学期的学分上限（例如 22），系统不会替你猜。"
                    ),
                    detail="模型未给出可验证的学分上限依据",
                ))
                continue
            declared = context.preference.max_credit
            if declared is not None and constraint.value is not None and constraint.value > declared:
                ambiguities.append(Ambiguity(
                    code="credit_limit_conflicts_with_declared_max",
                    question=(
                        f"你填写的上限 {constraint.value:g} 高于方案里已声明的上限 "
                        f"{declared:g}，请确认以哪一个为准。"
                    ),
                    detail=None,
                ))
                continue
            has_verifiable_limit = True
        kept_hard.append(constraint)

    if context.preference.max_credit is None and not has_verifiable_limit:
        # 没有声明的上限、也没有用户给出的数字 ⇒ 学分是否超限无法证明。
        if "credit_limit_missing_evidence" not in {item.code for item in ambiguities}:
            ambiguities.append(Ambiguity(
                code="credit_limit_missing_evidence",
                question=(
                    "当前方案没有声明学分上限，本次意图也没有给出数字。"
                    "请填写本学期的学分上限（例如 22）；系统不会替你猜一个值。"
                ),
                detail="缺少可验证的学分上限",
            ))

    kept_soft: list[SoftPreference] = []
    for preference in draft.soft_preferences:
        if preference.kind not in _SOFT_EXECUTABLE:
            ambiguities.append(Ambiguity(
                code="soft_preference_not_executable",
                question=(
                    f"软偏好 {preference.kind} 目前没有确定性执行语义，"
                    "本次只作为说明记录，不参与求解。"
                ),
                detail=None,
            ))
            continue
        kept_soft.append(preference)

    scope = draft.scope
    if scope != ADJUSTMENT_SCOPE_CURRENT_SEMESTER:
        ambiguities.append(Ambiguity(
            code="adjustment_scope_unsupported",
            question=(
                "本次只能调整**当前学期**的教学班与负荷；未来学期的自动重排尚未验收，"
                "请把范围改回当前学期。"
            ),
            detail="跨学期自动调整不在本轮支持范围",
        ))

    adjustable = bool(context.required_course_ids) or bool(context.selected_keys())
    if not adjustable:
        ambiguities.append(Ambiguity(
            code="no_adjustable_target",
            question="本次上下文里没有可调整的补修课程或已选班次，无法生成候选。",
            detail=None,
        ))

    cleaned = IntentDraft(
        summary=draft.summary,
        scope=ADJUSTMENT_SCOPE_CURRENT_SEMESTER,
        target_semester=draft.target_semester,
        hard_constraints=tuple(kept_hard),
        soft_preferences=tuple(kept_soft),
        locked_courses=tuple(kept_locks),
        confidence=draft.confidence,
        notes=draft.notes,
    )
    return cleaned, tuple(ambiguities)


@dataclass(frozen=True, slots=True)
class ConfirmedIntent:
    """用户**确认后**的意图：后端补齐范围、指纹与已校验约束。"""

    plan_digest: str
    semester: str
    scope: str
    target_semester: str | None
    hard_constraints: tuple[HardConstraint, ...]
    soft_preferences: tuple[SoftPreference, ...]
    locked_courses: tuple[LockedCourse, ...]
    user_note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan_digest, str) or len(self.plan_digest) != 64:
            raise IntentValidationError("plan_digest 必须是 64 位指纹。")
        _text(self.semester, "semester", limit=20)
        if self.scope != ADJUSTMENT_SCOPE_CURRENT_SEMESTER:
            raise IntentValidationError("确认后的调整范围只能是当前学期。")
        object.__setattr__(self, "target_semester", _optional_text(self.target_semester, "semester", limit=20))
        object.__setattr__(self, "user_note", _optional_text(self.user_note, "user note"))
        for name, kind in (
            ("hard_constraints", HardConstraint),
            ("soft_preferences", SoftPreference),
            ("locked_courses", LockedCourse),
        ):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, kind) for value in values):
                raise IntentValidationError(f"{name} 中条目类型非法。")
            object.__setattr__(self, name, values)

    @property
    def credit_limit(self) -> float | None:
        for constraint in self.hard_constraints:
            if constraint.kind == "max_credit_limit":
                return constraint.value
        return None


def validate_confirmed_intent(
    draft_intent: "ConfirmedIntent | IntentDraft", context: PlanningContext,
) -> ConfirmedIntent:
    """校验"用户确认过的意图"仍与当前上下文一致（fail closed）。

    ⛔ 确认不等于可以改写事实：这里会重新核对白名单与学分依据，
    任何一项不满足都抛 `IntentValidationError`，不允许进入求解。
    """

    if isinstance(draft_intent, ConfirmedIntent):
        source = draft_intent
        digest = source.plan_digest
    elif isinstance(draft_intent, IntentDraft):
        cleaned, ambiguities = cross_check(draft_intent, context)
        if ambiguities:
            raise IntentValidationError("意图仍有未消解的歧义，不能确认。")
        source = ConfirmedIntent(
            plan_digest=context.digest,
            semester=context.semester,
            scope=cleaned.scope,
            target_semester=cleaned.target_semester or context.semester,
            hard_constraints=cleaned.hard_constraints,
            soft_preferences=cleaned.soft_preferences,
            locked_courses=cleaned.locked_courses,
        )
        digest = source.plan_digest
    else:
        raise IntentValidationError("确认意图类型非法。")

    if digest != context.digest:
        raise IntentValidationError("确认依据的方案指纹与当前上下文不一致。")

    known_courses = context.course_ids
    known_keys = context.class_keys
    selected_keys = context.selected_keys()

    for lock in source.locked_courses:
        if lock.course_id not in known_courses or (lock.course_id, lock.class_id) not in known_keys:
            raise IntentValidationError("锁定的课程 / 教学班不在本次有效数据里。")
        if (lock.course_id, lock.class_id) not in selected_keys:
            raise IntentValidationError("只能锁定当前方案里已经选中的教学班。")

    declared = context.preference.max_credit
    for constraint in source.hard_constraints:
        if constraint.kind == "max_credit_limit":
            if constraint.evidence is None:
                raise IntentValidationError("学分上限缺少可验证依据。")
            if declared is not None and constraint.value is not None and constraint.value > declared:
                raise IntentValidationError("学分上限高于方案里已声明的上限。")

    return ConfirmedIntent(
        plan_digest=context.digest,
        semester=context.semester,
        scope=ADJUSTMENT_SCOPE_CURRENT_SEMESTER,
        target_semester=source.target_semester or context.semester,
        hard_constraints=source.hard_constraints,
        soft_preferences=source.soft_preferences,
        locked_courses=source.locked_courses,
        user_note=source.user_note,
    )
