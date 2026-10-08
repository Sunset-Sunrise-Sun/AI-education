"""新增/选修接纳的确定性边界测试（**全部使用显式 Mock 教学班**）。

覆盖本轮要求的边界：

1. 两门新增彼此冲突 → 都不被自动接纳；
2. 周次不重叠 → 不构成冲突（可以被接纳）；
3. 超过学生声明的学分上限 → 不被自动接纳；
4. 原课表本身已超限 → 只提示，不篡改；
5. 重复添加 / 重复身份 → 明确拒绝；
6. 建议课表内的相互冲突必须先被检出（不能只看"与当前课表比"）。
"""

from __future__ import annotations

import pytest

from app.models.contracts import CourseOffering, MakeupTask, Meeting, Preference
from app.planner import RestrictedPlannerProvider
from app.planner.credit_limit import (
    CREDIT_STATE_NOT_DECLARED,
    CREDIT_STATE_OVER_LIMIT,
    CREDIT_STATE_UNVERIFIABLE,
    CREDIT_STATE_WITHIN_LIMIT,
    CreditLedger,
    credit_ledger,
    credit_state,
    task_credit_map,
)


def section(
    cid: str = "A",
    class_id: str = "a",
    day: int = 1,
    *,
    weeks: list[int] | None = None,
    credit: float | None = 3.0,
    start: int = 1,
    end: int = 2,
) -> CourseOffering:
    return CourseOffering(
        course_id=cid, course_name=f"Mock {cid}", class_id=class_id, semester="2026-1",
        credit=credit,
        meetings=[Meeting(
            weekday=day, start_section=start, end_section=end, weeks=weeks or [1, 3],
        )],
        data_source="mock",
    )


def task(cid: str = "A", *, credit: float = 3.0, **fields) -> MakeupTask:
    return MakeupTask(
        course_id=cid, course_name=f"Mock {cid}", credit=credit,
        status=fields.pop("status", "required"), **fields,
    )


def run(tasks=None, offerings=None, current=None, preference=None):
    return RestrictedPlannerProvider().plan(
        makeup_tasks=tasks or [], offerings=offerings or [],
        current_schedule=current or [], preference=preference or Preference(),
    )


def ids(result):
    return [(item.course_id, item.class_id) for item in result.selected_classes]


def messages(result) -> str:
    return " ".join(item.message for item in result.unresolved)


# --------------------------------------------------------------------------- #
# 学分台账（纯函数）
# --------------------------------------------------------------------------- #

def test_ledger_prefers_declared_offering_credit():
    ledger = credit_ledger([section(credit=2.5)], task_credits={"A": 9.0})
    assert ledger.declared_total == 2.5
    assert ledger.complete is True


def test_ledger_falls_back_to_task_credit():
    ledger = credit_ledger([section(credit=None)], task_credits={"A": 4.0})
    assert ledger.declared_total == 4.0
    assert ledger.complete is True


def test_ledger_marks_unknown_credit_instead_of_zero():
    ledger = credit_ledger([section(credit=None)])
    assert ledger.declared_total == 0.0
    assert ledger.complete is False
    assert ledger.unknown_course_ids == ("A",)


def test_ledger_treats_missing_credit_as_unusable():
    # ⚠️ `credit=True` / 负数都到不了这里：公共模型会先规范化或直接拒绝。
    # 这里只断言"没有可用的学分声明"这一条，不假装能拦住模型已经规范化的情况。
    assert credit_ledger([section(credit=None)]).complete is False


def test_credit_state_matrix():
    complete = CreditLedger(6.0, (), 2)
    incomplete = CreditLedger(0.0, ("A",), 1)
    assert credit_state(Preference(), complete) == CREDIT_STATE_NOT_DECLARED
    assert credit_state(Preference(max_credit=6), complete) == CREDIT_STATE_WITHIN_LIMIT
    assert credit_state(Preference(max_credit=5.9), complete) == CREDIT_STATE_OVER_LIMIT
    # 无法证明 ≠ 通过。
    assert credit_state(Preference(max_credit=100), incomplete) == CREDIT_STATE_UNVERIFIABLE


def test_task_credit_map_keeps_first_declared_value():
    assert task_credit_map([task("A", credit=3.0), task("A", credit=5.0)]) == {"A": 3.0}


def test_ledger_input_validation():
    with pytest.raises(TypeError):
        credit_ledger("not-a-sequence")
    with pytest.raises(TypeError):
        credit_ledger([object()])
    with pytest.raises(TypeError):
        credit_state(object(), CreditLedger(0.0, (), 0))
    with pytest.raises(ValueError):
        CreditLedger(-1.0, (), 0)


# --------------------------------------------------------------------------- #
# 1. 两门新增彼此冲突
# --------------------------------------------------------------------------- #

def test_two_mutually_conflicting_additions_are_not_accepted():
    result = run([task("A"), task("B")], [section("A", "a"), section("B", "b")])
    assert ids(result) == []
    assert result.changes == []
    assert "彼此冲突" in messages(result)


def test_conflicting_addition_order_does_not_change_the_result():
    offers = [section("A", "a"), section("B", "b")]
    first = run([task("A"), task("B")], offers)
    second = run([task("B"), task("A")], offers)
    assert first.model_dump() == second.model_dump()


# --------------------------------------------------------------------------- #
# 2. 周次不重叠
# --------------------------------------------------------------------------- #

def test_disjoint_weeks_are_not_a_conflict():
    offers = [section("A", "a", 1, weeks=[1, 3]), section("B", "b", 1, weeks=[2, 4])]
    result = run([task("A"), task("B")], offers)
    assert set(ids(result)) == {("A", "a"), ("B", "b")}


def test_overlapping_weeks_are_a_conflict():
    offers = [section("A", "a", 1, weeks=[1, 3]), section("B", "b", 1, weeks=[3, 5])]
    result = run([task("A"), task("B")], offers)
    assert ids(result) == []
    assert "彼此冲突" in messages(result)


# --------------------------------------------------------------------------- #
# 3. 学分上限
# --------------------------------------------------------------------------- #

def test_total_credit_over_the_declared_limit_is_not_accepted():
    result = run(
        [task("A", credit=3.0)], [section("A", "a", credit=3.0)],
        preference=Preference(max_credit=2),
    )
    assert ids(result) == []
    assert "超过学生声明的学分上限" in messages(result)


def test_total_credit_at_the_declared_limit_is_accepted():
    result = run(
        [task("A", credit=3.0)], [section("A", "a", credit=3.0)],
        preference=Preference(max_credit=3),
    )
    assert ids(result) == [("A", "a")]
    assert "未超过学生声明的学分上限" in messages(result)


def test_cumulative_additions_respect_the_limit_together():
    # 两门新增各自都没问题，但**累计**超限 → 不允许只留一门（不按顺序牺牲）。
    offers = [section("A", "a", 1, credit=4.0), section("B", "b", 2, credit=4.0)]
    result = run([task("A"), task("B")], offers, preference=Preference(max_credit=6))
    assert ids(result) == []
    assert "超过学生声明的学分上限" in messages(result)


def test_missing_credit_declaration_makes_the_limit_unverifiable():
    result = run(current=[section("B", "b", 2, credit=None)], preference=Preference(max_credit=1))
    assert ids(result) == [("B", "b")]
    assert "无法证明" in messages(result)


# --------------------------------------------------------------------------- #
# 4. 原课表已超限
# --------------------------------------------------------------------------- #

def test_already_over_limit_current_schedule_is_reported_not_rewritten():
    current = [section("B", "b", 2, credit=10.0)]
    result = run(current=current, preference=Preference(max_credit=4))
    assert ids(result) == [("B", "b")]
    assert "本身已超过" in messages(result)
    assert "不自动删除或替换" in messages(result)


def test_over_limit_current_schedule_does_not_block_an_independent_proof():
    # 原课表已超限仍保留；无解证明只按时间冲突，不因学分上限改写。
    current = [section("B", "b", 1, credit=10.0), section("C", "c", 1, credit=10.0)]
    result = run(current=current, preference=Preference(max_credit=4))
    assert result.status.value == "infeasible"
    assert ids(result) == [("B", "b"), ("C", "c")]


# --------------------------------------------------------------------------- #
# 5. 重复添加 / 重复身份
# --------------------------------------------------------------------------- #

def test_duplicate_task_is_rejected():
    with pytest.raises(ValueError, match="重复"):
        run([task("A"), task("A")], [section("A", "a")])


def test_duplicate_offering_identity_is_rejected():
    with pytest.raises(ValueError, match="重复"):
        run([task("A")], [section("A", "a"), section("A", "a")])


def test_already_selected_course_is_never_added_twice():
    result = run([task("A")], [section("A", "alt", 2)], [section("A", "a")])
    assert ids(result) == [("A", "a")]
    assert result.changes == []


# --------------------------------------------------------------------------- #
# 6. 完整集合校验（不只是"与当前课表比"）
# --------------------------------------------------------------------------- #

def test_joint_selection_is_always_conflict_free():
    offers = [
        section("A", "a", 1), section("B", "b", 1),
        section("C", "c", 2), section("D", "d", 2),
    ]
    result = run([task(cid) for cid in "ABCD"], offers)
    selected = [item for item in offers if (item.course_id, item.class_id) in set(ids(result))]
    for index, left in enumerate(selected):
        for right in selected[index + 1:]:
            from app.planner.conflicts import ConflictState, check_conflict

            assert check_conflict(left, right) is not ConflictState.CONFLICT
