"""课程组学分进度（Phase 4）回归测试。

覆盖：
  1. 三个数字自洽：`remaining == max(required - earned, 0)`
  2. `group_credit_progress` 与判定**同源**：`remaining` 与 `GroupGap.remaining_credit` 一致
  3. 已满足的组也给出 0 缺口（不能因为"没有 gap"就丢掉这组）
  4. 学生**已表达的选修计划**不计入 `earned_credit`（它是未来意图，不是已获学分）
  5. 未提供课程组时返回空元组（不报错）
  6. ⛔ 未构建的 diff 必须拒绝（沿用既有 fail-closed 语义）
"""

from __future__ import annotations

import pytest

from app.curriculum import (
    ConfirmedElectiveSelection,
    CurriculumNormalizationError,
    RequirementKind,
    build_curriculum_diff,
    group_credit_progress,
    normalize_curriculum_version,
)
from app.models.contracts import MakeupStatus


def _version(*, group_minimum: float, courses: tuple[dict, ...]):
    return normalize_curriculum_version(
        version_id="v-new",
        major="m",
        cohort="c",
        source_id="mock://v-new",
        complete=True,
        completeness_evidence="mock://evidence/v-new",
        group_records=[
            {
                "group_id": "G1",
                "name": "专业选修课",
                "minimum_credit": group_minimum,
                "source_record": "table:1!row:1",
            }
        ],
        course_records=courses,
    )


def _elective(course_id: str, name: str, credit: float) -> dict:
    return {
        "course_id": course_id,
        "course_name": name,
        "credit": credit,
        "requirement": "elective",
        "group_id": "G1",
        "source_record": f"table:1!row:{course_id}",
        "prerequisites": [],
    }


def _build(*, group_minimum: float, courses: tuple[dict, ...], completed=(), selections=()):
    version = _version(group_minimum=group_minimum, courses=courses)
    return build_curriculum_diff(
        version,
        version,
        completed,
        completed_complete=True,
        completed_completeness_evidence="mock://evidence/completed",
        elective_selections=selections,
    )


def test_earned_zero_when_nothing_satisfied() -> None:
    diff = _build(
        group_minimum=6.0,
        courses=(_elective("E1", "选修甲", 3.0), _elective("E2", "选修乙", 3.0)),
    )
    progress = group_credit_progress(diff)
    assert len(progress) == 1
    item = progress[0]
    assert item.group_id == "G1"
    assert item.undecided is False
    assert item.required_credit == 6.0
    # 没有认定 ⇒ 已获 0、还差 6
    assert item.earned_credit == 0.0
    assert item.remaining_credit == 6.0


def test_three_numbers_are_self_consistent_and_match_group_gap() -> None:
    """⛔ 禁止两套算法：`remaining` 必须等于 `required - earned`，
    并且与判定产生的 `GroupGap.remaining_credit` 完全一致。"""

    diff = _build(
        group_minimum=6.0,
        courses=(_elective("E1", "选修甲", 3.0), _elective("E2", "选修乙", 3.0)),
    )
    item = group_credit_progress(diff)[0]

    expected = max((item.required_credit or 0.0) - (item.earned_credit or 0.0), 0.0)
    assert item.remaining_credit == pytest.approx(expected)

    # 与判定口径对照：本组存在缺口时应与 GroupGap 一致
    gaps = {gap.group_id: gap for gap in diff.group_gaps}
    assert "G1" in gaps
    assert gaps["G1"].remaining_credit == pytest.approx(item.remaining_credit)


def test_undecided_group_reports_null_instead_of_zero() -> None:
    """组学分下限未知 ⇒ 三个数字必须为 `None`，⛔ 不得伪装成 0。"""

    version = normalize_curriculum_version(
        version_id="v-new",
        major="m",
        cohort="c",
        source_id="mock://v-new",
        complete=True,
        completeness_evidence="mock://evidence/v-new",
        group_records=[
            {
                "group_id": "G1",
                "name": "专业选修课",
                "minimum_credit": None,
                "source_record": "table:1!row:1",
            }
        ],
        course_records=(_elective("E1", "选修甲", 3.0),),
    )
    diff = build_curriculum_diff(
        version,
        version,
        (),
        completed_complete=True,
        completed_completeness_evidence="mock://evidence/completed",
    )
    item = group_credit_progress(diff)[0]
    assert item.undecided is True
    assert item.required_credit is None
    assert item.earned_credit is None
    assert item.remaining_credit is None


def test_elective_selection_is_not_counted_as_earned() -> None:
    """⚠️ 学生"已表达的选修计划"是未来意图，⛔ 不计入 earned_credit。

    这与 `group_plan_covers_requirement()` 的口径**不同**：
    后者回答"计划是否够覆盖"，本函数回答"已获得多少学分"。
    """

    diff = _build(
        group_minimum=6.0,
        courses=(_elective("E1", "选修甲", 3.0), _elective("E2", "选修乙", 3.0)),
        selections=(
            ConfirmedElectiveSelection(
                target_version_id="v-new",
                group_id="G1",
                course_ids=("E1",),
                evidence="mock://evidence/selection",
            ),
        ),
    )
    item = group_credit_progress(diff)[0]
    # 计划选了 E1（3 学分），但它**没有**被认定 ⇒ earned 仍为 0
    assert item.earned_credit == 0.0
    assert item.remaining_credit == 6.0


def test_no_groups_returns_empty_tuple() -> None:
    version = normalize_curriculum_version(
        version_id="v-new",
        major="m",
        cohort="c",
        source_id="mock://v-new",
        complete=True,
        completeness_evidence="mock://evidence/v-new",
        course_records=(
            {
                "course_id": "R1",
                "course_name": "必修甲",
                "credit": 3.0,
                "requirement": RequirementKind.REQUIRED.value,
                "source_record": "table:1!row:R1",
                "prerequisites": [],
            },
        ),
    )
    diff = build_curriculum_diff(
        version,
        version,
        (),
        completed_complete=True,
        completed_completeness_evidence="mock://evidence/completed",
    )
    assert group_credit_progress(diff) == ()


def test_group_fully_after_cut_off_reports_zero_bar_with_explanation() -> None:
    """⚠️ 培养方案写明的下限 ≠ 转专业时点口径的额度时，必须给出可读说明。

    构造：一个 makeup_scope 生效、且**所有**成员都安排在时点之后的组。
    期望：required=0（历史无额度），并有 scope_note 解释差异，
    ⛔ 不得让页面出现"方案写 6 学分、进度要求 0 学分"这种无解释的矛盾。
    """

    from app.curriculum.matching import MakeupScope
    from app.curriculum.terms import ConfirmedScopeDecision

    version = _version(
        group_minimum=6.0,
        courses=(_elective("E1", "选修甲", 3.0), _elective("E2", "选修乙", 3.0)),
    )
    # 两个成员都判定为 future ⇒ 该组在时点上没有历史额度
    scope_decisions = tuple(
        ConfirmedScopeDecision(
            target_version_id="v-new",
            target_source_record=course["source_record"],
            target_course_id=course["course_id"],
            decision="future",
            evidence="mock://evidence/scope",
        )
        for course in (_elective("E1", "选修甲", 3.0), _elective("E2", "选修乙", 3.0))
    )
    diff = build_curriculum_diff(
        version,
        version,
        (),
        completed_complete=True,
        completed_completeness_evidence="mock://evidence/completed",
        makeup_scope=MakeupScope(
            target_version_id="v-new",
            as_of_term="2025-2",
            evidence="mock://evidence/as-of",
        ),
        confirmed_scope_decisions=scope_decisions,
    )
    item = group_credit_progress(diff)[0]
    assert item.required_credit == 0.0
    assert item.remaining_credit == 0.0
    assert item.scope_note, "额度为 0 而方案写明 6 学分时必须有解释"
    assert "转专业时点之后" in item.scope_note


def test_scope_note_absent_when_bar_matches_plan_minimum() -> None:
    """口径一致时⛔ 不产生多余的说明。"""

    diff = _build(
        group_minimum=6.0,
        courses=(_elective("E1", "选修甲", 3.0), _elective("E2", "选修乙", 3.0)),
    )
    item = group_credit_progress(diff)[0]
    assert item.required_credit == 6.0
    assert item.scope_note is None


def test_unbuilt_diff_is_rejected() -> None:
    """⛔ 未通过 builder 构造的 diff 必须拒绝（既有 fail-closed 语义）。"""

    with pytest.raises(CurriculumNormalizationError):
        group_credit_progress(object())  # type: ignore[arg-type]


def test_satisfied_member_raises_earned_credit() -> None:
    """已认定满足的成员必须计入 earned，从而降低 remaining。"""

    version = _version(
        group_minimum=6.0,
        courses=(_elective("E1", "选修甲", 3.0), _elective("E2", "选修乙", 3.0)),
    )
    from app.curriculum.matching import ConfirmedRecognition
    from app.curriculum.completed_courses import normalize_completed_courses

    completed = normalize_completed_courses(
        [
            {
                "course_id": None,
                "course_name": "选修甲",
                "credit": 3.0,
                "semester": "2025-1",
                "passed": True,
                "course_type": None,
                "course_id_status": "pending",
                "id_match_source": None,
                "source_record": "pdf:1",
            }
        ],
        source_id="upload:pdf:sha256:test",
    )
    diff = build_curriculum_diff(
        version,
        version,
        completed,
        completed_complete=True,
        completed_completeness_evidence="mock://evidence/completed",
        recognitions=(
            ConfirmedRecognition(
                target_version_id="v-new",
                target_course_id="E1",
                completed_source_id="upload:pdf:sha256:test",
                completed_source_record="pdf:1",
                recognized_credit=3.0,
                evidence="mock://evidence/recognition",
            ),
        ),
    )
    # 先确认这条认定确实产生了 SATISFIED
    satisfied = [m for m in diff.matches if m.status is MakeupStatus.SATISFIED]
    assert [m.target.course_id for m in satisfied] == ["E1"]

    item = group_credit_progress(diff)[0]
    assert item.earned_credit == 3.0
    assert item.remaining_credit == 3.0
