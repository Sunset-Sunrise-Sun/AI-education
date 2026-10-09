"""AI Planning Controller 服务层测试（**全部 Mock**，⛔ 不调用真实 DeepSeek）。

覆盖任务书要求的验收用例：

1. 正常意图 → 确认 → 受控求解 → 候选；
2. **未确认不求解**；
3. 锁定课程不被破坏；
4. 模糊学分（无依据）不进入求解；
5. 未知课程（幻觉课程号）被拒绝；
6. 数据快照过期；
7. 模型不可用 / 无密钥；
8. 无教学班；
9. 结果无法满足 / 未采用 ⇒ 原方案不变；
10. 意图数据隔离（会话之间不串）。
"""

from __future__ import annotations

import json

import pytest

from app.ai_planning import (
    ADOPTED,
    BLOCKED,
    CANDIDATE_READY,
    NO_FEASIBLE_CANDIDATE,
    AiPlanningConfig,
    AiPlanningService,
    ConfirmedIntent,
    IntentValidationError,
    MessageRejectedError,
    ModelOutputInvalidError,
    ModelUnavailableError,
    SessionExpiredError,
    SessionNotFoundError,
    SessionStore,
    ScriptedIntentModel,
    RuleFakeIntentModel,
    UnavailableIntentModel,
    build_context,
)
from app.ai_planning.errors import AdoptionConflictError, IntentNotConfirmableError
from app.models.contracts import SelectedClass
from app.planner import RestrictedPlannerProvider
from tests.ai_planning_fixtures import (
    ALGO_ALT_CLASS,
    ALGO_CLASS,
    ALGO_COURSE,
    DS_CLASS,
    DS_COURSE,
    NET_CLASS,
    NET_COURSE,
    SEMESTER,
    base_plan,
    confirm_payload,
    context_payload,
    makeup_tasks,
    offerings,
)


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #

def config(*, enabled: bool = True, api_key: str | None = None, ttl: int = 900) -> AiPlanningConfig:
    return AiPlanningConfig(
        enabled=enabled, api_key=api_key, base_url="https://api.deepseek.com",
        model="deepseek-flash", max_output_tokens=1200, request_timeout=20.0,
        max_calls_per_request=3, max_sessions=200, adopt_ttl_seconds=ttl,
    )


def context(*, include_offerings: bool = True, max_credit: float | None = None):
    payload = context_payload(include_offerings=include_offerings, max_credit=max_credit)
    from app.models.contracts import (
        CourseOffering,
        MakeupTask,
        PlanResult,
        Preference,
    )

    return build_context(
        semester=payload["semester"],
        base_plan=PlanResult.model_validate(payload["base_plan"]),
        makeup_tasks=[MakeupTask.model_validate(row) for row in payload["makeup_tasks"]],
        offerings=[CourseOffering.model_validate(row) for row in payload["course_offerings"]],
        preference=Preference.model_validate(payload["preference"]),
    )


def rule_model() -> RuleFakeIntentModel:
    """假模型：把每个课程号映射到**当前方案已选**的班次，便于测试锁定路径。"""

    selected = {
        item.course_id: item.class_id for item in base_plan().selected_classes
    }
    return RuleFakeIntentModel(
        known_course_ids=(DS_COURSE, ALGO_COURSE, NET_COURSE),
        known_class_by_course={
            course_id: selected.get(course_id, f"{course_id.lower()}-01")
            for course_id in (DS_COURSE, ALGO_COURSE, NET_COURSE)
        },
    )


def service(
    *,
    model=None,
    planner=None,
    cfg: AiPlanningConfig | None = None,
    clock=None,
) -> AiPlanningService:
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    return AiPlanningService(
        config=cfg or config(),
        intent_model=model if model is not None else rule_model(),
        planner=planner if planner is not None else RestrictedPlannerProvider(),
        sessions=SessionStore(),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# 1. 正常路径
# --------------------------------------------------------------------------- #

def test_interpret_extracts_explicit_credit_limit_without_solving():
    svc = service()
    record, answer = svc.interpret(
        message="这学期太累，最多 6 学分，尽量别在周五上课",
        context=context(),
    )
    assert answer.generator_kind == "test_double"      # ⛔ 绝不是 deepseek_live
    assert record.draft.scope == "current_semester"
    kinds = {item.kind for item in record.draft.hard_constraints}
    # "最多 6 学分" 是学生**明确给出的数字** → 允许成为硬约束
    assert kinds == {"max_credit_limit"}
    assert {item.kind for item in record.draft.soft_preferences} == {"avoid_weekday"}
    assert record.ambiguities == ()
    assert record.state == "intent_draft"


def test_vague_tiredness_is_not_converted_into_a_credit_number():
    """没有明确的学分数字 ⇒ 必须留待用户填写，⛔ 不猜一个上限。"""

    svc = service()
    record, _ = svc.interpret(message="这学期太累，少上一点课就行", context=context())
    assert record.draft.hard_constraints == ()
    codes = {item.code for item in record.ambiguities}
    assert "credit_limit_missing_evidence" in codes
    # ⛔ 没有数字就绝不猜
    assert all(
        item.value is None
        for item in record.draft.soft_preferences
        if item.kind == "prefer_fewer_credits"
    )


def test_declared_context_limit_removes_the_credit_ambiguity():
    """上下文里已经声明了上限 ⇒ 不再需要用户填写，歧义消失。"""

    svc = service()
    record, _ = svc.interpret(
        message="尽量别在周五上课", context=context(max_credit=24.0)
    )
    assert "credit_limit_missing_evidence" not in {item.code for item in record.ambiguities}
    assert record.ambiguities == ()


def test_full_flow_confirmed_intent_produces_a_planner_candidate():
    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    assert record.ambiguities == ()

    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(plan_digest=record.context.digest, weekday=5),
    )
    assert outcome.status == CANDIDATE_READY
    assert outcome.candidate_plan is not None
    assert outcome.diff is not None
    added = {(cid, cid_class) for cid, cid_class in outcome.diff.added}
    # 唯一 CLEAR 新增：算法 algo-02（algo-01 与已选的数据结构同段冲突）
    assert (ALGO_COURSE, ALGO_ALT_CLASS) in added
    assert (ALGO_COURSE, ALGO_CLASS) not in added
    assert (DS_COURSE, DS_CLASS) in {(c, k) for c, k in outcome.diff.kept}
    # 原方案对象**没有被改动**
    assert record.context.base_plan.selected_classes[0].class_id == DS_CLASS


# --------------------------------------------------------------------------- #
# 2. 未确认不求解
# --------------------------------------------------------------------------- #

def test_unconfirmed_intent_never_reaches_the_planner():
    calls: list[str] = []

    class RecordingPlanner:
        def plan(self, **kwargs):  # pragma: no cover - 不应该被调用
            calls.append("called")
            raise AssertionError("未确认的意图不得调用 Planner")

    svc = service(planner=RecordingPlanner())
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    with pytest.raises(IntentValidationError):
        svc.solve(
            intent_id=record.intent_id,
            plan_digest=record.context.digest,
            confirmed_intent={"plan_digest": record.context.digest},  # 缺 semester/scope
        )
    assert calls == []


def test_intent_with_ambiguities_cannot_be_solved():
    svc = service()
    record, _ = svc.interpret(message="太累了少上一点", context=context())
    assert record.ambiguities
    with pytest.raises(IntentNotConfirmableError):
        svc.solve(
            intent_id=record.intent_id,
            plan_digest=record.context.digest,
            confirmed_intent=confirm_payload(plan_digest=record.context.digest),
        )


def test_plan_digest_mismatch_is_rejected_before_solving():
    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    with pytest.raises(SessionExpiredError):
        svc.solve(
            intent_id=record.intent_id,
            plan_digest="0" * 64,
            confirmed_intent=confirm_payload(plan_digest="0" * 64),
        )


def test_unknown_intent_id_is_not_found():
    svc = service()
    with pytest.raises(SessionNotFoundError):
        svc.solve(
            intent_id="intent_does_not_exist",
            plan_digest="a" * 64,
            confirmed_intent=confirm_payload(plan_digest="a" * 64),
        )


# --------------------------------------------------------------------------- #
# 3. 锁定课程
# --------------------------------------------------------------------------- #

def test_locked_course_is_preserved_in_the_candidate():
    svc = service()
    record, _ = svc.interpret(
        message=f"{DS_COURSE} 必须保留，尽量别在周五上课",
        context=context(max_credit=24.0),
    )
    assert record.ambiguities == ()
    assert [item.course_id for item in record.draft.locked_courses] == [DS_COURSE]

    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(
            plan_digest=record.context.digest, locked=True, weekday=5
        ),
    )
    assert outcome.status == CANDIDATE_READY
    selected = {
        (item.course_id, item.class_id) for item in outcome.candidate_plan.selected_classes
    }
    assert (DS_COURSE, DS_CLASS) in selected


def test_candidate_breaking_a_locked_course_is_rejected():
    """Planner 若把锁定课程换掉 / 移除，控制器必须拒绝候选并保留原方案。"""

    class LockBreakingPlanner:
        def plan(self, *, makeup_tasks, offerings, current_schedule, preference):
            from app.models.contracts import PlanResult, PlanStatus

            return PlanResult(
                status=PlanStatus.FEASIBLE,
                selected_classes=[],       # 把锁定课程整个删掉
                changes=[],
                risks=[],
                unresolved=[],
            )

    svc = service(planner=LockBreakingPlanner())
    record, _ = svc.interpret(
        message=f"{DS_COURSE} 必须保留，尽量别在周五上课",
        context=context(max_credit=24.0),
    )
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(
            plan_digest=record.context.digest, locked=True, weekday=5
        ),
    )
    assert outcome.status == BLOCKED
    assert outcome.blocked_reason == "locked_course_would_change"
    assert outcome.candidate_plan is None
    assert outcome.unresolved


def test_locking_a_course_outside_the_current_plan_is_an_ambiguity():
    """锁定目标必须在**当前方案已选中**的班次里；否则不能凭空锁定。"""

    svc = service(model=ScriptedIntentModel(script=(json.dumps({
        "summary": "保留算法课",
        "scope": "current_semester",
        "locked_courses": [
            {"course_id": ALGO_COURSE, "class_id": ALGO_ALT_CLASS, "reason": "学生要求"}
        ],
    }),)))
    record, _ = svc.interpret(
        message=f"{ALGO_COURSE} 必须保留，最多 20 学分",
        context=context(max_credit=24.0),
    )
    codes = {item.code for item in record.ambiguities}
    assert "target_course_unknown" in codes
    # 未选中的班次不会被"锁定"，⛔ 也不会因此进入求解
    assert record.draft.locked_courses == ()


def test_locking_a_class_that_cannot_exist_is_rejected_by_whitelist():
    """白名单之外的班次 ⇒ 整份草稿被拒绝（⛔ 不静默丢弃、⛔ 不假装锁定成功）。"""

    svc = service(model=ScriptedIntentModel(script=(json.dumps({
        "summary": "锁定一个不存在的班次",
        "scope": "current_semester",
        "locked_courses": [{"course_id": DS_COURSE, "class_id": "does-not-exist"}],
    }),)))
    with pytest.raises(ModelOutputInvalidError) as excinfo:
        svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    assert "does-not-exist" not in str(excinfo.value)


# --------------------------------------------------------------------------- #
# 4. 模糊学分
# --------------------------------------------------------------------------- #

def test_credit_limit_without_evidence_is_not_accepted():
    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    with pytest.raises(IntentValidationError):
        svc.solve(
            intent_id=record.intent_id,
            plan_digest=record.context.digest,
            confirmed_intent=confirm_payload(
                plan_digest=record.context.digest, max_credit=3.0, evidence=None
            ),
        )


def test_credit_limit_above_the_declared_max_is_rejected():
    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=4.0))
    with pytest.raises(IntentValidationError):
        svc.solve(
            intent_id=record.intent_id,
            plan_digest=record.context.digest,
            confirmed_intent=confirm_payload(
                plan_digest=record.context.digest, max_credit=10.0
            ),
        )


def test_confirmed_credit_limit_is_forwarded_to_the_planner():
    seen: dict = {}

    class SpyPlanner:
        def plan(self, *, makeup_tasks, offerings, current_schedule, preference):
            seen["max_credit"] = preference.max_credit
            seen["avoid"] = [block.weekday for block in preference.avoid_times]
            from app.models.contracts import PlanResult, PlanStatus

            return PlanResult(
                status=PlanStatus.PARTIALLY_FEASIBLE,
                selected_classes=[
                    SelectedClass(course_id=item.course_id, class_id=item.class_id)
                    for item in current_schedule
                ],
                changes=[], risks=[], unresolved=[],
            )

    svc = service(planner=SpyPlanner())
    record, _ = svc.interpret(message="最多 20 学分，尽量别在周五上课", context=context())
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(
            plan_digest=record.context.digest, max_credit=20.0, weekday=5
        ),
    )
    assert outcome.status == NO_FEASIBLE_CANDIDATE  # Spy 没有改动任何班次
    assert seen["max_credit"] == 20.0
    assert 5 in seen["avoid"]


# --------------------------------------------------------------------------- #
# 5. 未知课程 / 幻觉
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("payload", [
    json.dumps({
        "summary": "非法 scope", "scope": "any_semester",
    }),
    json.dumps({
        "summary": "非法 kind", "scope": "current_semester",
        "hard_constraints": [{"kind": "make_it_easy", "value": 1}],
    }),
    json.dumps({
        "summary": "未知字段", "scope": "current_semester", "student_name": "示例",
    }),
    json.dumps({
        "summary": "无依据的学分换算", "scope": "current_semester",
        "hard_constraints": [{"kind": "max_credit_limit", "value": None}],
    }),
])
def test_invalid_model_output_fails_closed(payload):
    svc = service(model=ScriptedIntentModel(script=(payload,)))
    with pytest.raises(ModelOutputInvalidError):
        svc.interpret(message="随便说点什么", context=context(max_credit=24.0))


@pytest.mark.parametrize("locked", [
    [{"course_id": "HALLUCINATED1", "class_id": "h-01"}],
    [{"course_id": DS_COURSE, "class_id": "no-such-class"}],
])
def test_hallucinated_course_or_class_in_locked_list_is_rejected_by_whitelist(locked):
    svc = service(model=ScriptedIntentModel(script=(json.dumps({
        "summary": "锁定幻觉目标", "scope": "current_semester", "locked_courses": locked,
    }),)))
    # 形状合法但不在白名单 → 整份草稿被拒绝（⛔ 不是"提示一下"、⛔ 不静默丢弃）
    with pytest.raises(ModelOutputInvalidError) as excinfo:
        svc.interpret(message="帮我锁定这门课", context=context(max_credit=24.0))
    # ⛔ 错误信息不回显模型给出的标识
    assert "HALLUCINATED1" not in str(excinfo.value)
    assert "no-such-class" not in str(excinfo.value)


# --------------------------------------------------------------------------- #
# 6. 快照过期
# --------------------------------------------------------------------------- #

def test_changed_context_invalidates_the_previous_intent():
    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    other = context(max_credit=12.0)      # 上下文变了 ⇒ 指纹变了
    assert other.digest != record.context.digest
    with pytest.raises(SessionExpiredError):
        svc.solve(
            intent_id=record.intent_id,
            plan_digest=other.digest,
            confirmed_intent=confirm_payload(plan_digest=other.digest, weekday=5),
        )


def test_expired_candidate_cannot_be_adopted():
    now = {"value": 1000.0}
    svc = service(cfg=config(ttl=60), clock=lambda: now["value"])
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(plan_digest=record.context.digest, weekday=5),
    )
    assert outcome.candidate_id is not None
    now["value"] += 61          # 超过 TTL
    with pytest.raises(SessionExpiredError):
        svc.adopt(
            candidate_id=outcome.candidate_id,
            plan_digest=outcome.plan_digest,
            accept=True,
        )
    assert svc.sessions.candidate_state(outcome.candidate_id) == BLOCKED


# --------------------------------------------------------------------------- #
# 7. 模型不可用
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("reason", ["model_disabled", "missing_api_key", "http_401",
                                    "http_402", "http_429", "http_5xx", "timeout",
                                    "network_error", "invalid_json", "empty_content"])
def test_unavailable_model_never_produces_an_intent(reason):
    svc = service(model=UnavailableIntentModel(reason=reason))
    with pytest.raises(ModelUnavailableError) as excinfo:
        svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    # 错误信息只含固定原因码，不含任何取值
    assert reason in str(excinfo.value)


def test_disabled_controller_refuses_to_interpret():
    svc = service(cfg=config(enabled=False))
    with pytest.raises(ModelUnavailableError):
        svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))


def test_no_intent_model_injected_is_explicit_unavailable():
    svc = AiPlanningService(
        config=config(api_key="placeholder"),
        intent_model=None,
        planner=RestrictedPlannerProvider(),
    )
    with pytest.raises(ModelUnavailableError):
        svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))


# --------------------------------------------------------------------------- #
# 8. 无教学班
# --------------------------------------------------------------------------- #

def test_missing_offerings_never_invents_a_class_and_reports_missing_data():
    """没有任何教学班输入时：⛔ 不得凭空补班次，缺口必须如实暴露。

    注意：当前冻结的 `PlannerProvider` 只能从 `offerings` 里取到
    "当前已选班"的完整对象，因此没有供给时它连已选班也无法保留 ——
    控制器**不隐藏**这一点：候选里只剩空课表、`removed` 列出被移除的课程、
    `risks` 明确指出移除、`unresolved` 保留 `missing_data` 原因。
    """

    svc = service()
    record, _ = svc.interpret(
        message="尽量别在周五上课", context=context(include_offerings=False, max_credit=24.0)
    )
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(plan_digest=record.context.digest, weekday=5),
    )
    assert outcome.status == CANDIDATE_READY
    assert outcome.candidate_plan is not None
    assert {(c.course_id, c.class_id) for c in outcome.candidate_plan.selected_classes} == set()
    assert outcome.diff is not None
    assert (DS_COURSE, DS_CLASS) in outcome.diff.removed
    assert any("移除了原方案中的教学班" in risk for risk in outcome.risks)
    # 缺供给原因必须如实透出，⛔ 不推断学校未开课
    assert any("没有候选教学班" in message for message in outcome.unresolved)


# --------------------------------------------------------------------------- #
# 9. 结果无法满足 / 未采用 ⇒ 原方案不变
# --------------------------------------------------------------------------- #

def test_planner_rejecting_input_returns_blocked_not_a_fabricated_candidate():
    class RejectingPlanner:
        def plan(self, **kwargs):
            raise ValueError("当前课表含已知时间冲突")

    svc = service(planner=RejectingPlanner())
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(plan_digest=record.context.digest, weekday=5),
    )
    assert outcome.status == BLOCKED
    assert outcome.candidate_plan is None
    assert outcome.blocked_reason is not None
    assert outcome.blocked_reason.startswith("planner_rejected_input")


def test_rejecting_a_candidate_keeps_the_original_plan():
    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(plan_digest=record.context.digest, weekday=5),
    )
    adopted_record, version = svc.adopt(
        candidate_id=outcome.candidate_id,
        plan_digest=outcome.plan_digest,
        accept=False,
    )
    assert adopted_record.state == "rejected"
    assert version == 0
    assert record.context.base_plan.selected_classes[0].class_id == DS_CLASS


def test_adopting_twice_is_a_conflict_and_does_not_advance_the_version():
    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(plan_digest=record.context.digest, weekday=5),
    )
    _, version = svc.adopt(
        candidate_id=outcome.candidate_id, plan_digest=outcome.plan_digest, accept=True
    )
    assert version == 1
    with pytest.raises(AdoptionConflictError):
        svc.adopt(
            candidate_id=outcome.candidate_id, plan_digest=outcome.plan_digest, accept=True
        )
    assert svc.sessions.adopted_count() == 1
    assert svc.sessions.candidate_state(outcome.candidate_id) == ADOPTED


def test_adopting_with_a_mismatched_digest_is_rejected():
    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(plan_digest=record.context.digest, weekday=5),
    )
    with pytest.raises(SessionExpiredError):
        svc.adopt(
            candidate_id=outcome.candidate_id, plan_digest="b" * 64, accept=True
        )


# --------------------------------------------------------------------------- #
# 10. 意图数据隔离
# --------------------------------------------------------------------------- #

def test_two_intents_have_isolated_ids_and_payloads():
    svc = service()
    first, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    second, _ = svc.interpret(message="最多 20 学分", context=context(max_credit=24.0))
    assert first.intent_id != second.intent_id
    assert first.draft.hard_constraints == ()
    assert {item.kind for item in second.draft.hard_constraints} == {"max_credit_limit"}


def test_message_with_personal_information_is_never_sent_to_the_model():
    sent: list[str] = []

    class RecordingModel:
        model_id = "recording"

        def complete(self, messages):
            sent.extend(item.get("content", "") for item in messages)
            from app.ai_planning.deepseek_client import ModelAnswer, GENERATOR_TEST_DOUBLE

            return ModelAnswer(
                generator_kind=GENERATOR_TEST_DOUBLE, model_id=self.model_id,
                payload={"summary": "不该到这里", "scope": "current_semester"},
            )

    svc = service(model=RecordingModel())
    with pytest.raises(MessageRejectedError):
        svc.interpret(message="我的学号是 2025123456，帮我少上点课", context=context())
    assert sent == []          # 一个字节都没有离开服务器


def test_context_minimization_excludes_private_fields():
    ctx = context()
    payload = ctx.model_payload()
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("student_name", "student_id", "grade", "score", "gpa", "notes", "备注"):
        assert forbidden not in serialized


def test_session_store_evicts_oldest_when_bounded():
    store = SessionStore(max_sessions=2)
    svc = AiPlanningService(
        config=config(), intent_model=rule_model(),
        planner=RestrictedPlannerProvider(), sessions=store,
    )
    ids = []
    for index, message in enumerate(("尽量别在周五上课", "最多 20 学分", "尽量别在周二上课")):
        record, _ = svc.interpret(
            message=message, context=context(max_credit=24.0 + index)
        )
        ids.append(record.intent_id)
    assert len(set(ids)) == 3
    assert len(store) == 2
    with pytest.raises(SessionNotFoundError):
        store.get_intent(ids[0])


def test_context_payload_has_no_student_identity_fields_at_all():
    """控制器请求体本身就不接受身份字段（在 API 层由 extra=forbid 强制）。"""

    payload = context_payload()
    assert set(payload) == {
        "semester", "base_plan", "makeup_tasks", "course_offerings", "preference",
    }


def test_semester_and_task_identity_are_bound_in_the_digest():
    base = context()
    changed = build_context(
        semester=SEMESTER,
        base_plan=base_plan(),
        makeup_tasks=[task for task in makeup_tasks() if task.course_id != NET_COURSE],
        offerings=offerings(),
    )
    assert base.digest != changed.digest


def test_net_course_status_is_reported_not_silently_solved():
    """待人工确认（manual_confirmation）的课程不应被自动加入候选。"""

    svc = service()
    record, _ = svc.interpret(message="尽量别在周五上课", context=context(max_credit=24.0))
    outcome = svc.solve(
        intent_id=record.intent_id,
        plan_digest=record.context.digest,
        confirmed_intent=confirm_payload(plan_digest=record.context.digest, weekday=5),
    )
    selected = {(item.course_id, item.class_id) for item in outcome.candidate_plan.selected_classes}
    assert (NET_COURSE, NET_CLASS) not in selected
    assert outcome.status == CANDIDATE_READY
