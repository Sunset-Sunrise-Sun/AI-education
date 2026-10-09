"""AI Planning Controller 服务层：意图草稿 → 用户确认 → 受控求解 → 候选。

```text
interpret()            模型只输出**结构化意图草稿**，不求解、不改方案
        ↓  用户在前端确认（并消解全部歧义）
solve()                后端把已确认意图翻译成**既有四参数 Planner** 的输入，
                       再对 Planner 返回的 PlanResult 做确定性复核
        ↓  用户第二次确认
adopt()                绑定方案指纹的采用；候选过期 / 指纹不符 ⇒ fail closed
```

## 安全不变量（实现层面强制）

| 不变量 | 实现位置 |
| --- | --- |
| 模型输出**永远不能**直接成为 `PlanResult` | `_run_planner` 只调用注入的 `PlannerProvider` |
| 模型提到的课程 / 教学班必须在白名单内 | `intent.cross_check` / `parse_intent_draft` |
| "太累 / 少上一点"不得变成固定学分数 | `HardConstraint.__post_init__` + `cross_check` |
| 未确认意图绝不求解 | `solve()` 第一步校验 `confirmed_intent` |
| 未二次确认绝不改方案 | 候选是**新对象**；只有 `adopt()` 才推进 `adopted_version` |
| 指纹变化 ⇒ 旧意图 / 旧候选失效 | 每步都与 `PlanningContext.digest` 比对 |
| 模型调用次数有上限 | `ModelCallBudget` + `AiPlanningConfig.max_calls_per_request` |
| 会话有界且不落盘 | `SessionStore`（进程内 LRU，超限淘汰最旧） |

## 状态机

```text
intent_draft → intent_confirmed → candidate_ready | no_feasible_candidate | blocked
                                              → adopted | rejected
```
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Final, Iterable

from pydantic import ValidationError

from app.ai_planning.config import AiPlanningConfig
from app.ai_planning.context import PlanningContext
from app.ai_planning.deepseek_client import (
    GENERATOR_DEEPSEEK_LIVE,
    IntentModel,
    ModelAnswer,
)
from app.ai_planning.errors import (
    AdoptionConflictError,
    AiPlanningError,
    CandidateInvalidError,
    IntentNotConfirmableError,
    IntentValidationError,
    ModelCallBudgetExceededError,
    ModelUnavailableError,
    ModelOutputInvalidError,
    SessionExpiredError,
    SessionNotFoundError,
    SolveUnsupportedError,
)
from app.ai_planning.intent import (
    ADJUSTMENT_SCOPE_CURRENT_SEMESTER,
    Ambiguity,
    ConfirmedIntent,
    IntentDraft,
    cross_check,
    parse_intent_draft,
    validate_confirmed_intent,
)
from app.ai_planning.minimize import build_messages, sanitize_user_message
from app.models.contracts import (
    Change,
    CourseOffering,
    PlanResult,
    Preference,
    TimeBlock,
)

__all__ = [
    "ADOPTED",
    "BLOCKED",
    "CANDIDATE_READY",
    "INTENT_CONFIRMED",
    "INTENT_DRAFT",
    "NO_FEASIBLE_CANDIDATE",
    "PLAN_KIND_NO_CANDIDATE",
    "PLAN_KIND_PLAN_RESULT",
    "REJECTED",
    "AiPlanningService",
    "CandidateDiff",
    "CandidateRecord",
    "IntentRecord",
    "SessionStore",
    "SolveOutcome",
    "compute_candidate_diff",
]

#: 内部状态名（⛔ 不是公共 Schema；响应里如实报告）。
INTENT_DRAFT: Final[str] = "intent_draft"
INTENT_CONFIRMED: Final[str] = "intent_confirmed"
CANDIDATE_READY: Final[str] = "candidate_ready"
NO_FEASIBLE_CANDIDATE: Final[str] = "no_feasible_candidate"
BLOCKED: Final[str] = "blocked"
ADOPTED: Final[str] = "adopted"
REJECTED: Final[str] = "rejected"

#: 候选方案载体的两种取值：真实 `PlanResult` / 无候选（附阻塞原因）。
PLAN_KIND_PLAN_RESULT: Final[str] = "PlanResult"
PLAN_KIND_NO_CANDIDATE: Final[str] = "none"

_MAX_SESSIONS_DEFAULT: Final[int] = 200


# --------------------------------------------------------------------------- #
# 会话存储
# --------------------------------------------------------------------------- #

@dataclass
class IntentRecord:
    intent_id: str
    context: PlanningContext
    draft: IntentDraft
    ambiguities: tuple[Ambiguity, ...]
    generator_kind: str
    generator_note: str
    created_at: float
    state: str = INTENT_DRAFT
    confirmed: ConfirmedIntent | None = None


@dataclass
class CandidateRecord:
    candidate_id: str
    intent_id: str
    plan_digest: str
    diff: "CandidateDiff"
    risks: tuple[str, ...]
    unresolved: tuple[str, ...]
    generator_kind: str
    created_at: float
    candidate_plan: PlanResult | None = None
    state: str = CANDIDATE_READY


class SessionStore:
    """**进程内**有界会话存储（⛔ 不落盘、⛔ 不是持久账户）。

    超出上限时淘汰**最旧**的意图与候选。进程重启即全部失效，
    这符合任务书"若无可靠持久化机制，明确仅在进程/会话内可用且失效时 fail-closed"。
    """

    def __init__(self, *, max_sessions: int = _MAX_SESSIONS_DEFAULT) -> None:
        if isinstance(max_sessions, bool) or not isinstance(max_sessions, int) or max_sessions < 1:
            raise ValueError("max_sessions 必须是正整数。")
        self._max = max_sessions
        self._intents: "OrderedDict[str, IntentRecord]" = OrderedDict()
        self._candidates: "OrderedDict[str, CandidateRecord]" = OrderedDict()

    def __len__(self) -> int:
        return len(self._intents)

    def clear(self) -> None:
        self._intents.clear()
        self._candidates.clear()

    def put_intent(self, record: IntentRecord) -> None:
        if not isinstance(record, IntentRecord):
            raise TypeError("record 必须是 IntentRecord。")
        self._intents[record.intent_id] = record
        self._intents.move_to_end(record.intent_id)
        self._evict()

    def get_intent(self, intent_id: str) -> IntentRecord:
        record = self._intents.get(intent_id)
        if record is None:
            raise SessionNotFoundError("该 intent_id 不存在或已过期，请重新解析意图。")
        self._intents.move_to_end(intent_id)
        return record

    def put_candidate(self, record: CandidateRecord) -> None:
        if not isinstance(record, CandidateRecord):
            raise TypeError("record 必须是 CandidateRecord。")
        self._candidates[record.candidate_id] = record
        self._candidates.move_to_end(record.candidate_id)
        self._evict()

    def get_candidate(self, candidate_id: str) -> CandidateRecord:
        record = self._candidates.get(candidate_id)
        if record is None:
            raise SessionNotFoundError("该 candidate_id 不存在或已过期，请重新求解。")
        self._candidates.move_to_end(candidate_id)
        return record

    def _evict(self) -> None:
        while len(self._intents) > self._max:
            self._intents.popitem(last=False)
        while len(self._candidates) > self._max:
            self._candidates.popitem(last=False)

    def adopted_count(self) -> int:
        """已被采用的候选数量（进程内计数，⛔ 不是持久账户版本）。"""

        return sum(1 for item in self._candidates.values() if item.state == ADOPTED)

    def candidate_state(self, candidate_id: str) -> str | None:
        record = self._candidates.get(candidate_id)
        return None if record is None else record.state


class ModelCallBudget:
    """单次 HTTP 请求内的模型调用计数（有上限，⛔ 不重试）。"""

    def __init__(self, limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit 必须是正整数。")
        self._limit = limit
        self.calls = 0
        self.prompt_tokens_estimate = 0
        self.completion_tokens_estimate = 0

    def consume(self, answer: ModelAnswer) -> None:
        self.calls += 1
        self.prompt_tokens_estimate += answer.prompt_tokens_estimate
        self.completion_tokens_estimate += answer.completion_tokens_estimate
        if self.calls > self._limit:
            raise ModelCallBudgetExceededError("本次请求的模型调用次数超过上限。")


# --------------------------------------------------------------------------- #
# 候选差异（**确定性**统计，⛔ 不交给模型）
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class CandidateDiff:
    """原方案与候选方案的**确定性**差异。"""

    added: tuple[tuple[str, str], ...] = ()
    removed: tuple[tuple[str, str], ...] = ()
    replaced: tuple[tuple[str, str, str], ...] = ()
    kept: tuple[tuple[str, str], ...] = ()
    base_credit: float = 0.0
    candidate_credit: float = 0.0
    credit_unknown_course_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("added", "removed", "kept"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "replaced", tuple(self.replaced))
        object.__setattr__(
            self, "credit_unknown_course_ids", tuple(self.credit_unknown_course_ids)
        )

    @property
    def credit_delta(self) -> float | None:
        if self.credit_unknown_course_ids:
            return None
        return self.candidate_credit - self.base_credit

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.replaced)

    def to_payload(self) -> dict:
        return {
            "added": [{"course_id": cid, "class_id": cid_class} for cid, cid_class in self.added],
            "removed": [{"course_id": cid, "class_id": cid_class} for cid, cid_class in self.removed],
            "replaced": [
                {"course_id": cid, "from_class": old, "to_class": new}
                for cid, old, new in self.replaced
            ],
            "kept": [{"course_id": cid, "class_id": cid_class} for cid, cid_class in self.kept],
            "base_credit": self.base_credit,
            "candidate_credit": self.candidate_credit,
            "credit_delta": self.credit_delta,
            "credit_unknown_course_ids": list(self.credit_unknown_course_ids),
            "empty": self.empty,
        }


def _credits(
    keys: Iterable[tuple[str, str]], offerings: tuple[CourseOffering, ...]
) -> tuple[float, tuple[str, ...]]:
    """按教学班的 `credit` 统计学分；缺声明的课程单独列出（⛔ 不按 0 静默计入）。"""

    index: dict[tuple[str, str], CourseOffering] = {
        (item.course_id, item.class_id): item for item in offerings
    }
    total = 0.0
    unknown: list[str] = []
    for key in keys:
        offering = index.get(key)
        credit = None if offering is None else offering.credit
        if credit is None:
            if key[0] not in unknown:
                unknown.append(key[0])
            continue
        total += float(credit)
    return total, tuple(unknown)


def compute_candidate_diff(
    *, base: PlanResult, candidate: PlanResult, offerings: tuple[CourseOffering, ...]
) -> CandidateDiff:
    """由两份 `PlanResult` 计算差异；⛔ 完全确定性，⛔ 不涉及任何模型输出。"""

    base_keys = {(item.course_id, item.class_id) for item in base.selected_classes}
    cand_keys = {(item.course_id, item.class_id) for item in candidate.selected_classes}

    kept = tuple(sorted(base_keys & cand_keys))
    base_by_course = {course_id: class_id for course_id, class_id in base_keys}
    cand_by_course = {course_id: class_id for course_id, class_id in cand_keys}

    replaced: list[tuple[str, str, str]] = []
    for course_id in sorted(set(base_by_course) & set(cand_by_course)):
        if base_by_course[course_id] != cand_by_course[course_id]:
            replaced.append((course_id, base_by_course[course_id], cand_by_course[course_id]))

    base_credit, base_unknown = _credits(base_keys, offerings)
    cand_credit, cand_unknown = _credits(cand_keys, offerings)
    unknown = tuple(sorted(set(base_unknown) | set(cand_unknown)))

    return CandidateDiff(
        added=tuple(sorted(cand_keys - base_keys)),
        removed=tuple(sorted(base_keys - cand_keys)),
        replaced=tuple(replaced),
        kept=kept,
        base_credit=base_credit,
        candidate_credit=cand_credit,
        credit_unknown_course_ids=unknown,
    )


# --------------------------------------------------------------------------- #
# 求解输出
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class SolveOutcome:
    """一次"确认后求解"的结果。"""

    status: str                     # candidate_ready | no_feasible_candidate | blocked
    candidate_id: str | None
    candidate_plan: PlanResult | None
    diff: CandidateDiff | None
    risks: tuple[str, ...]
    unresolved: tuple[str, ...]
    message: str
    blocked_reason: str | None
    generator_kind: str
    data_source: str
    plan_digest: str


# --------------------------------------------------------------------------- #
# 服务
# --------------------------------------------------------------------------- #

@dataclass
class AiPlanningService:
    """控制器：意图解析 + 受控求解 + 采用。

    `intent_model` 是**注入点**：真实 `DeepSeekChatClient` 或测试假模型。
    ⛔ 未注入时不能解析意图（`model_unavailable`），
    ⛔ 绝不会静默回退到某个内置假模型。
    """

    config: AiPlanningConfig
    intent_model: IntentModel | None = None
    planner: object | None = None
    sessions: SessionStore = field(default_factory=SessionStore)
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        if not isinstance(self.config, AiPlanningConfig):
            raise TypeError("config 必须是 AiPlanningConfig。")
        if self.intent_model is not None and not hasattr(self.intent_model, "complete"):
            raise TypeError("intent_model 必须实现 complete(messages)。")

    # ------------------------------------------------------------------ #
    # 1. 意图解析（只读；⛔ 不求解、⛔ 不改方案）
    # ------------------------------------------------------------------ #

    def interpret(self, *, message: str, context: PlanningContext) -> tuple[IntentRecord, ModelAnswer]:
        if not isinstance(context, PlanningContext):
            raise TypeError("context 必须是 PlanningContext。")
        if not self.config.enabled:
            raise ModelUnavailableError(
                "AI 规划控制器未启用（AI_PLANNING_ENABLED 未打开）；本次不解析意图。"
            )
        # 先做输入校验（含个人信息拒绝），⛔ 不合规的消息不会离开服务器。
        sanitize_user_message(message)
        if self.intent_model is None:
            raise ModelUnavailableError(
                "未配置意图解析模型（没有可用密钥时不会伪造解析结果）。"
            )

        messages = build_messages(message=message, context=context)
        answer = self.intent_model.complete(messages)
        if not answer.ok:
            raise ModelUnavailableError(
                f"意图解析模型当前不可用（{answer.reason}）；原方案保持不变。"
            )

        draft = parse_intent_draft(answer.payload)
        cleaned, ambiguities = cross_check(draft, context)
        note = (
            "真实 DeepSeek 在线调用"
            if answer.generator_kind == GENERATOR_DEEPSEEK_LIVE
            else "注入的测试替身模型（不是线上模型）"
        )
        record = IntentRecord(
            intent_id=_new_id("intent", context.digest, cleaned.summary + message),
            context=context,
            draft=cleaned,
            ambiguities=ambiguities,
            generator_kind=answer.generator_kind,
            generator_note=note,
            created_at=self._now(),
        )
        self.sessions.put_intent(record)
        return record, answer

    # ------------------------------------------------------------------ #
    # 2. 确认 + 求解（**仅**在用户明确确认后执行）
    # ------------------------------------------------------------------ #

    def solve(
        self,
        *,
        intent_id: str,
        plan_digest: str,
        confirmed_intent: object,
    ) -> SolveOutcome:
        record = self.sessions.get_intent(intent_id)
        if plan_digest != record.context.digest:
            raise SessionExpiredError(
                "本次确认依据的方案指纹与服务器当前上下文不一致；请重新解析意图。"
            )
        if record.ambiguities:
            raise IntentNotConfirmableError(
                "意图仍有未消解的歧义，必须先由用户回答后才能求解。"
            )

        confirmed = _read_confirmed_intent(confirmed_intent, record.context)
        validated = validate_confirmed_intent(confirmed, record.context)
        record.confirmed = validated
        record.state = INTENT_CONFIRMED

        unsupported = _unsupported_reason(validated)
        if unsupported is not None:
            return SolveOutcome(
                status=BLOCKED,
                candidate_id=None,
                candidate_plan=None,
                diff=None,
                risks=(),
                unresolved=(),
                message="当前受控 Planner 无法表达该调整意图，未生成任何候选。",
                blocked_reason=unsupported,
                generator_kind=record.generator_kind,
                data_source=record.context.data_source,
                plan_digest=record.context.digest,
            )

        if self.planner is None:
            return SolveOutcome(
                status=BLOCKED,
                candidate_id=None,
                candidate_plan=None,
                diff=None,
                risks=(),
                unresolved=(),
                message="未装配受控 Planner，未生成任何候选。",
                blocked_reason="planner_not_configured",
                generator_kind=record.generator_kind,
                data_source=record.context.data_source,
                plan_digest=record.context.digest,
            )

        preference = _preference_for(validated, record.context)
        current_schedule = list(record.context.selected_by_course.values())

        try:
            candidate_plan = self.planner.plan(
                makeup_tasks=list(record.context.makeup_tasks),
                offerings=list(record.context.offerings),
                current_schedule=current_schedule,
                preference=preference,
            )
        except ValidationError:
            # 受控 Planner 自己违反了 `PlanResult` 契约 ⇒ 这是**程序缺陷**，
            # ⛔ 不吞、⛔ 不翻译成 BLOCKED、⛔ 不给用户一个假的"不支持"。
            raise
        except AiPlanningError:
            raise
        except (ValueError, TypeError) as exc:
            # Planner 的**输入校验**失败（倒置节次 / 混合学期 / 重复身份等）
            # ⇒ 明确 unsupported，⛔ 不硬造候选。
            return SolveOutcome(
                status=BLOCKED,
                candidate_id=None,
                candidate_plan=None,
                diff=None,
                risks=(),
                unresolved=(),
                message="受控 Planner 拒绝本次参数，未生成任何候选。",
                blocked_reason=f"planner_rejected_input: {type(exc).__name__}",
                generator_kind=record.generator_kind,
                data_source=record.context.data_source,
                plan_digest=record.context.digest,
            )

        if not isinstance(candidate_plan, PlanResult):
            raise CandidateInvalidError("Planner 返回的对象不是 PlanResult。")

        lock_violations = _lock_violations(validated, candidate_plan, record.context)
        if lock_violations:
            return SolveOutcome(
                status=BLOCKED,
                candidate_id=None,
                candidate_plan=None,
                diff=None,
                risks=(),
                unresolved=tuple(lock_violations),
                message="候选破坏了用户锁定的课程，已拒绝该候选并保留原方案。",
                blocked_reason="locked_course_would_change",
                generator_kind=record.generator_kind,
                data_source=record.context.data_source,
                plan_digest=record.context.digest,
            )

        phantom = _unavailable_selected_keys(candidate_plan, record.context)
        if phantom:
            # ⛔ 绝不能把一个"本次输入里根本没有的班次"当成候选返回给用户。
            return SolveOutcome(
                status=BLOCKED,
                candidate_id=None,
                candidate_plan=None,
                diff=None,
                risks=(),
                unresolved=tuple(
                    f"候选引用了本次输入中没有教学班信息的班次：{course_id}/{class_id}"
                    for course_id, class_id in phantom
                ),
                message="候选引用了本次有效教学班之外的班次，已拒绝并保留原方案。",
                blocked_reason="candidate_references_unavailable_class",
                generator_kind=record.generator_kind,
                data_source=record.context.data_source,
                plan_digest=record.context.digest,
            )

        diff = compute_candidate_diff(
            base=record.context.base_plan,
            candidate=candidate_plan,
            offerings=record.context.offerings,
        )
        unresolved = tuple(item.message for item in candidate_plan.unresolved)
        risks = _risks_for(diff, candidate_plan, record.context)
        status = NO_FEASIBLE_CANDIDATE if diff.empty else CANDIDATE_READY

        candidate_id = _new_id(
            "candidate", record.context.digest, intent_id, candidate_plan.model_dump_json()
        )
        self.sessions.put_candidate(CandidateRecord(
            candidate_id=candidate_id,
            intent_id=intent_id,
            plan_digest=record.context.digest,
            diff=diff,
            risks=risks,
            unresolved=unresolved,
            generator_kind=record.generator_kind,
            created_at=self._now(),
            candidate_plan=candidate_plan,
            state=status,
        ))
        return SolveOutcome(
            status=status,
            candidate_id=candidate_id,
            candidate_plan=candidate_plan,
            diff=diff,
            risks=risks,
            unresolved=unresolved,
            message=(
                "已按确认意图调用受控 Planner 生成候选；请对照差异后决定是否采用。"
                if status == CANDIDATE_READY
                else "受控 Planner 已执行，但本次意图没有产生任何与原方案不同的候选；原方案保持不变。"
            ),
            blocked_reason=None,
            generator_kind=record.generator_kind,
            data_source=record.context.data_source,
            plan_digest=record.context.digest,
        )

    # ------------------------------------------------------------------ #
    # 3. 二次确认：采用 / 拒绝
    # ------------------------------------------------------------------ #

    def adopt(
        self, *, candidate_id: str, plan_digest: str, accept: bool
    ) -> tuple[CandidateRecord, int]:
        record = self.sessions.get_candidate(candidate_id)
        if record.plan_digest != plan_digest:
            raise SessionExpiredError(
                "采用请求携带的方案指纹与候选不一致；候选已失效，原方案保持不变。"
            )
        if record.candidate_plan is None:
            raise AdoptionConflictError("该候选没有可采用的方案，无法采用。")
        if not accept:
            record.state = REJECTED
            return record, self._adopted_version()

        if record.state == ADOPTED:
            # 同一候选重复采用 ⇒ 明确冲突，⛔ 不重复推进版本。
            raise AdoptionConflictError("该候选已经被采用过，本次不做任何改动。")
        if record.state == REJECTED:
            raise AdoptionConflictError("该候选已被用户拒绝，不能再次采用。")
        if record.state != CANDIDATE_READY:
            raise AdoptionConflictError("该候选当前不处于可采用状态。")

        if self._is_expired(record.created_at):
            record.state = BLOCKED
            raise SessionExpiredError("该候选已超过有效期，请重新解析意图并求解。")

        record.state = ADOPTED
        return record, self._adopted_version(record)

    def reject(self, *, candidate_id: str, plan_digest: str) -> CandidateRecord:
        record, _ = self.adopt(candidate_id=candidate_id, plan_digest=plan_digest, accept=False)
        return record

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    def _now(self) -> float:
        return float(self.clock())  # type: ignore[operator]

    def _is_expired(self, created_at: float) -> bool:
        return (self._now() - created_at) > float(self.config.adopt_ttl_seconds)

    def _adopted_version(self, record: CandidateRecord | None = None) -> int:
        return self.sessions.adopted_count()


def _read_confirmed_intent(value: object, context: PlanningContext) -> ConfirmedIntent:
    """把请求里的"已确认意图"读成 `ConfirmedIntent`；⛔ 缺失即拒绝。"""

    if value is None:
        raise IntentValidationError("必须由用户确认意图后才能求解（缺少 confirmed_intent）。")
    if isinstance(value, ConfirmedIntent):
        return value
    if isinstance(value, IntentDraft):
        return validate_confirmed_intent(value, context)
    if not isinstance(value, dict):
        raise IntentValidationError("confirmed_intent 形状非法。")
    return _confirmed_from_payload(value, context)


def _confirmed_from_payload(payload: dict, context: PlanningContext) -> ConfirmedIntent:
    """把前端回传的确认意图（JSON）读成 `ConfirmedIntent`，并逐项严格校验。"""

    allowed = {
        "plan_digest", "semester", "scope", "target_semester",
        "hard_constraints", "soft_preferences", "locked_courses", "user_note",
    }
    if set(payload) - allowed:
        raise IntentValidationError("confirmed_intent 包含未声明字段。")

    digest = payload.get("plan_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise IntentValidationError("confirmed_intent.plan_digest 非法。")
    if digest != context.digest:
        raise SessionExpiredError("confirm 携带的方案指纹与当前上下文不一致。")

    semester = payload.get("semester")
    if not isinstance(semester, str) or semester.strip() != context.semester:
        raise IntentValidationError("confirmed_intent.semester 与当前学期不一致。")

    scope = payload.get("scope")
    if scope != ADJUSTMENT_SCOPE_CURRENT_SEMESTER:
        raise IntentValidationError("confirmed_intent.scope 只能是 current_semester。")

    from app.ai_planning.intent import HardConstraint, LockedCourse, SoftPreference

    hard = tuple(
        HardConstraint(
            kind=row.get("kind"), value=row.get("value"), evidence=row.get("evidence"),
        )
        for row in _rows(payload.get("hard_constraints"), "hard_constraints")
    )
    soft = tuple(
        SoftPreference(kind=row.get("kind"), value=row.get("value"), note=row.get("note"))
        for row in _rows(payload.get("soft_preferences"), "soft_preferences")
    )
    locked = tuple(
        LockedCourse(
            course_id=row.get("course_id"), class_id=row.get("class_id"),
            reason=row.get("reason"),
        )
        for row in _rows(payload.get("locked_courses"), "locked_courses")
    )
    return ConfirmedIntent(
        plan_digest=digest,
        semester=semester.strip(),
        scope=scope,
        target_semester=payload.get("target_semester"),
        hard_constraints=hard,
        soft_preferences=soft,
        locked_courses=locked,
        user_note=payload.get("user_note"),
    )


def _rows(value: object, field_name: str) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise IntentValidationError(f"confirmed_intent.{field_name} 必须是数组。")
    rows: list[dict] = []
    for row in value:
        if not isinstance(row, dict):
            raise IntentValidationError(f"confirmed_intent.{field_name} 中条目必须是对象。")
        rows.append(row)
    return rows


def _unsupported_reason(intent: ConfirmedIntent) -> str | None:
    """哪些意图**无法**用冻结的四参数 Planner 表达（⛔ 不硬造候选）。"""

    for constraint in intent.hard_constraints:
        if constraint.kind == "exclude_course":
            return "exclude_course_hard_constraint_not_supported_by_frozen_planner"
    if intent.target_semester is not None and intent.target_semester != intent.semester:
        return "cross_semester_adjustment_not_supported"
    return None


def _preference_for(intent: ConfirmedIntent, context: PlanningContext) -> Preference:
    """把已确认意图翻译成公共 `Preference`（⛔ 不新增字段、⛔ 不发明上限）。

    - `max_credit_limit` → `Preference.max_credit`（用户明确给出的数字）；
    - `avoid_weekday` → `Preference.avoid_times` 覆盖**全天**（1..12 节）；
    - 其余软偏好**不**翻译成硬规则（只在响应里说明，⛔ 不参与证明无解）。
    """

    base = context.preference.model_dump()
    max_credit = intent.credit_limit
    avoid_times = list(base.get("avoid_times") or [])
    for preference in intent.soft_preferences:
        if preference.kind == "avoid_weekday" and preference.value is not None:
            weekday = int(preference.value)
            if 1 <= weekday <= 7 and not any(
                block.weekday == weekday for block in context.preference.avoid_times
            ):
                avoid_times.append(TimeBlock(
                    weekday=weekday, start_section=1, end_section=12,
                ).model_dump())
    return Preference(
        max_credit=base.get("max_credit") if max_credit is None else max_credit,
        avoid_cross_campus=bool(base.get("avoid_cross_campus", False)),
        preferred_courses=list(base.get("preferred_courses") or []),
        avoid_times=avoid_times,
        notes=base.get("notes"),
    )


def _lock_violations(
    intent: ConfirmedIntent, candidate: PlanResult, context: PlanningContext
) -> list[str]:
    """候选是否破坏了用户锁定的课程（⛔ 任何破坏都必须拒绝候选）。"""

    candidate_keys = {
        (item.course_id, item.class_id) for item in candidate.selected_classes
    }
    violations: list[str] = []
    for lock in intent.locked_courses:
        if (lock.course_id, lock.class_id) not in candidate_keys:
            violations.append(
                f"锁定的课程 {lock.course_id}（班次 {lock.class_id}）在候选里发生了变化。"
            )
    for change in candidate.changes:
        for lock in intent.locked_courses:
            if change.course_id == lock.course_id and change.from_class == lock.class_id:
                violations.append(
                    f"锁定的课程 {lock.course_id}（班次 {lock.class_id}）被候选换班。"
                )
    return violations


def _unavailable_selected_keys(
    candidate: PlanResult, context: PlanningContext
) -> tuple[tuple[str, str], ...]:
    """候选里**本次输入没有任何教学班信息**的班次（⛔ 不得当成真实候选返回）。

    允许集合 = 有效教学班 ∪ 原方案已选班次。
    超出这个集合的班次意味着候选建立在一份不存在的供给之上 —— 即使 Planner
    是在 `missing_data` 下"按任务要求"补上的，也⛔ 不能返回给用户。
    """

    allowed = set(context.class_keys) | set(context.selected_keys())
    phantom = [
        (item.course_id, item.class_id)
        for item in candidate.selected_classes
        if (item.course_id, item.class_id) not in allowed
    ]
    return tuple(phantom)


def _risks_for(
    diff: CandidateDiff, candidate: PlanResult, context: PlanningContext
) -> tuple[str, ...]:
    """候选的风险提示：全部由**确定性**事实推导，⛔ 不来自模型输出。"""

    risks: list[str] = []
    if diff.removed:
        risks.append(
            "候选移除了原方案中的教学班：" + "、".join(cid for cid, _ in diff.removed)
        )
    if diff.replaced:
        risks.append(
            "候选发生了换班：" + "、".join(cid for cid, _, _ in diff.replaced)
        )
    if diff.credit_unknown_course_ids:
        risks.append(
            "以下课程没有声明学分，候选学分合计无法确认："
            + "、".join(diff.credit_unknown_course_ids)
        )
    if not diff.empty and candidate.changes and all(
        change.from_class is None for change in candidate.changes
    ):
        risks.append("候选只包含新增教学班，未改动任何已选班次。")
    if context.data_source != "real":
        risks.append(f"本次上下文的教学班数据来源为 {context.data_source}，不代表真实教务开课。")
    return tuple(risks)


def _new_id(kind: str, *parts: str) -> str:
    """由内容派生的稳定 id（⛔ 不含任何个人信息，⛔ 不用于鉴权）。"""

    payload = "\u0000".join([kind, *parts])
    return f"{kind}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"
