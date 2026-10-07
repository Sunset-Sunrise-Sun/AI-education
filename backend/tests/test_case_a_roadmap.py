"""Case A roadmap wiring: term chain, confirmed-satisfaction facts, elective credit.

These tests use a **synthetic** curriculum (no real student data, no real
artifacts) so every term/scope/satisfaction fact is explicit and reviewable.

Boundaries under test:

- curriculum semester numbers come from the curriculum's OWN term labels, and
  ⛔ are never renumbered from 1 for the future list;
- range terms are only resolved when the curriculum already decided their
  direction, and a ``future`` range uses its own written end term;
- only ``satisfied`` makeup tasks are treated as satisfied, and an outside-group
  satisfied course never becomes elective credit;
- the elective gap is ``requirement − completed − current``, with the minimum
  read from ``CurriculumGroup`` (⛔ no hard-coded credit).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.curriculum.case import load_curriculum_case
from app.curriculum.terms import AcademicTerm, parse_academic_term
from app.models.contracts import MakeupStatus
from app.services.case_a_roadmap import (
    CaseARoadmapError,
    build_case_a_roadmap,
    derive_term_chain,
    future_semesters_after,
    requirement_kind_label,
    resolve_course_target_terms,
)
from app.curriculum.requirements import RequirementKind

SEMESTER = "2026-1"


def _course(
    course_id: str,
    name: str,
    credit: float,
    *,
    term: str | None = None,
    requirement: str = "required",
    group_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "course_id": course_id,
        "course_name": name,
        "credit": credit,
        "requirement": requirement,
        "source_record": f"row:{course_id}",
        "prerequisites": None,
    }
    if term is not None:
        payload["recommended_term_text"] = term
    if group_id is not None:
        payload["group_id"] = group_id
    return payload


def _payload(
    courses: list[dict[str, object]],
    *,
    groups: list[dict[str, object]] | None = None,
    decisions: list[dict[str, object]] | None = None,
    as_of_term: str = "2025-2",
) -> dict[str, object]:
    return {
        "data_source": "mock",
        "old": {
            "version_id": "synthetic-old",
            "major": "示例源专业",
            "cohort": "2025",
            "source_id": "synthetic://old",
            "complete": True,
            "completeness_evidence": "synthetic://old/scope",
            "course_records": [_course("OLD-1", "示例旧专业课", 3.0)],
        },
        "new": {
            "version_id": "synthetic-new",
            "major": "示例目标专业",
            "cohort": "2025",
            "source_id": "synthetic://new",
            "complete": True,
            "completeness_evidence": "synthetic://new/scope",
            "course_records": courses,
            "group_records": groups or [],
        },
        "completed": {"source_id": "synthetic://completed", "complete": True,
                      "completeness_evidence": "synthetic://completed/scope", "records": []},
        "confirmed_scope_decisions": decisions or [],
        # 有裁决就必须有显式 makeup_scope（Curriculum 的既有约束，⛔ 不绕过）。
        "makeup_scope": {
            "target_version_id": "synthetic-new",
            "as_of_term": as_of_term,
            "evidence": "synthetic://makeup-scope",
        },
    }


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "case.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _load(tmp_path: Path, **kwargs: object):  # type: ignore[no-untyped-def]
    return load_curriculum_case(_write(tmp_path, _payload(**kwargs)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 学期号链：来自课程自身的学期事实
# ---------------------------------------------------------------------------


def test_term_chain_numbers_terms_continuously_from_reference() -> None:
    """2025-1..2028-2 共 8 个学期；参照学期 2026-1 是第 3 学期。"""

    terms = [parse_academic_term(text) for text in
             ("2025-1", "2025-2", "2026-1", "2026-2", "2027-1", "2027-2", "2028-1", "2028-2")]
    chain = derive_term_chain(
        [term for term in terms if term is not None], reference_term=parse_academic_term("2026-1")  # type: ignore[arg-type]
    )
    assert chain.term_index["2025-1"] == 1
    assert chain.term_index["2026-1"] == 3
    assert chain.term_index["2026-2"] == 4
    assert chain.term_index["2027-1"] == 5
    assert chain.term_index["2028-2"] == 8


def test_future_semesters_start_after_the_current_semester() -> None:
    terms = [parse_academic_term(text) for text in ("2025-1", "2026-1", "2026-2", "2027-1")]
    chain = derive_term_chain(
        [term for term in terms if term is not None], reference_term=parse_academic_term("2026-1")  # type: ignore[arg-type]
    )
    declared = future_semesters_after(chain, current_semester_label=SEMESTER)
    assert [(item.semester_label, item.curriculum_semester, item.semester_index) for item in declared] == [
        ("2026-2", 3, 1),
        ("2027-1", 4, 2),
    ]
    # ⛔ 当前学期绝不进入未来学期
    assert all(item.semester_label != SEMESTER for item in declared)


def test_future_semester_horizon_must_be_in_the_chain() -> None:
    terms = [parse_academic_term(text) for text in ("2026-1", "2026-2")]
    chain = derive_term_chain(
        [term for term in terms if term is not None], reference_term=parse_academic_term("2026-1")  # type: ignore[arg-type]
    )
    with pytest.raises(CaseARoadmapError):
        future_semesters_after(
            chain, current_semester_label=SEMESTER, last_curriculum_semester="2030-1"
        )
    with pytest.raises(CaseARoadmapError):
        future_semesters_after(
            chain, current_semester_label=SEMESTER, last_curriculum_semester="2025-1"
        )


# ---------------------------------------------------------------------------
# 课程目标学期：单学期直接用；区间只有被裁决成 future 才用其结束学期
# ---------------------------------------------------------------------------


def test_single_term_course_resolves_directly(tmp_path: Path) -> None:
    case = _load(tmp_path, courses=[_course("C1", "示例课", 3.0, term="2027-1")])
    resolved, unresolved = resolve_course_target_terms(case)
    assert resolved["C1"] == AcademicTerm(year=2027, half=1)
    assert unresolved == ()


def test_range_term_without_decision_is_not_guessed(tmp_path: Path) -> None:
    """区间 + 无裁决 ⇒ ⛔ 不猜方向，如实记 unresolved。"""

    case = _load(tmp_path, courses=[_course("C1", "示例课", 3.0, term="2026-1~2026-2")])
    resolved, unresolved = resolve_course_target_terms(case)
    assert "C1" not in resolved
    assert len(unresolved) == 1
    assert "不猜测方向" in unresolved[0]


def test_future_range_uses_its_own_end_term(tmp_path: Path) -> None:
    case = _load(
        tmp_path,
        courses=[_course("C1", "示例课", 3.0, term="2026-1~2026-2")],
        decisions=[
            {
                "target_version_id": "synthetic-new",
                "target_source_record": "row:C1",
                "target_course_id": "C1",
                "decision": "future",
                "evidence": "synthetic://decisions/1",
            }
        ],
    )
    resolved, unresolved = resolve_course_target_terms(case)
    assert resolved["C1"] == AcademicTerm(year=2026, half=2)
    assert unresolved == ()


def test_historical_range_is_neither_planned_nor_reported(tmp_path: Path) -> None:
    """historical 区间是转专业前的历史窗口：⛔ 不进未来路线图，也⛔ 不算 unresolved。"""

    case = _load(
        tmp_path,
        courses=[_course("C1", "示例课", 3.0, term="2025-1~2025-2")],
        decisions=[
            {
                "target_version_id": "synthetic-new",
                "target_source_record": "row:C1",
                "target_course_id": "C1",
                "decision": "historical",
                "evidence": "synthetic://decisions/2",
            }
        ],
    )
    resolved, unresolved = resolve_course_target_terms(case)
    assert "C1" not in resolved
    assert unresolved == ()


def test_course_without_term_fact_is_reported(tmp_path: Path) -> None:
    case = _load(tmp_path, courses=[_course("C1", "示例课", 3.0, term=None)])
    resolved, unresolved = resolve_course_target_terms(case)
    assert resolved == {}
    assert len(unresolved) == 1


# ---------------------------------------------------------------------------
# 路线图：课程级、无教学班字段、satisfied only
# ---------------------------------------------------------------------------


def _roadmap_case(tmp_path: Path, **kwargs: object):  # type: ignore[no-untyped-def]
    """与真实 Case A 同构的学期跨度：2025-1 .. 2027-1，当前 2026-1 = 第 3 学期。

    把转专业前的学期（2025-1 / 2025-2）也写进培养方案，学期号链才会覆盖完整跨度，
    ⛔ 不会把未来学期误编号成从 1 开始。
    """

    courses = kwargs.pop(  # type: ignore[arg-type]
        "courses",
        [
            _course("PAST-1", "示例已过必修", 2.0, term="2025-1"),
            _course("PAST-2", "示例已过必修 2", 2.0, term="2025-2"),
            _course("REQ-A", "示例必修 A", 3.0, term="2026-2"),
            _course("REQ-B", "示例必修 B", 3.0, term="2027-1"),
        ],
    )
    return load_curriculum_case(_write(tmp_path, _payload(courses=courses, **kwargs)))  # type: ignore[arg-type]


def test_roadmap_is_course_level_and_never_reports_section_fields(tmp_path: Path) -> None:
    case = _roadmap_case(tmp_path)
    roadmap = build_case_a_roadmap(
        case, makeup_tasks=[], current_semester_label=SEMESTER, elective_group_id=None
    )
    forbidden = {
        "class_id",
        "teacher",
        "weekday",
        "start_section",
        "end_section",
        "weeks",
        "campus",
        "classroom",
        "capacity",
        "remaining_capacity",
        "meetings",
    }
    for semester in roadmap.future_semesters:
        for item in semester.courses:
            assert not (set(item.__dataclass_fields__) & forbidden)
    # 未满足的课（含未满足的**已过**学期课程）都应被安排；⛔ 没有任何课被静默丢弃。
    assert set(roadmap.future_course_ids) == {"PAST-1", "PAST-2", "REQ-A", "REQ-B"}


def test_recommended_term_drives_placement_by_curriculum_number(tmp_path: Path) -> None:
    """2026-2 ⇒ 培养方案第 4 学期；2027-1 ⇒ 第 5 学期（⛔ 不是列表第 1/2 项）。"""

    case = _roadmap_case(tmp_path)
    roadmap = build_case_a_roadmap(
        case, makeup_tasks=[], current_semester_label=SEMESTER, elective_group_id=None
    )
    placed = {
        item.course_id: semester.curriculum_semester
        for semester in roadmap.future_semesters
        for item in semester.courses
    }
    assert placed["REQ-A"] == 4
    assert placed["REQ-B"] == 5


def test_satisfied_task_is_not_replanned_but_manual_confirmation_is(tmp_path: Path) -> None:
    from app.models.contracts import MakeupTask

    case = _roadmap_case(
        tmp_path,
        courses=[
            _course("SAT-1", "示例已满足", 3.0, term="2026-2"),
            _course("AMB-1", "示例待人工认定", 3.0, term="2026-2"),
        ],
    )
    roadmap = build_case_a_roadmap(
        case,
        makeup_tasks=[
            MakeupTask(course_id="SAT-1", course_name="示例已满足", credit=3.0,
                       status=MakeupStatus.SATISFIED),
            MakeupTask(course_id="AMB-1", course_name="示例待人工认定", credit=3.0,
                       status=MakeupStatus.MANUAL_CONFIRMATION),
        ],
        current_semester_label=SEMESTER,
        elective_group_id=None,
    )
    assert "SAT-1" not in roadmap.future_course_ids
    assert "AMB-1" in roadmap.future_course_ids
    # 未满足的状态必须如实告知，⛔ 不得静默升级
    assert any("manual_confirmation" in item for item in roadmap.warnings)


def test_possibly_equivalent_is_never_promoted(tmp_path: Path) -> None:
    from app.models.contracts import MakeupTask

    case = _roadmap_case(tmp_path, courses=[_course("EQ-1", "示例可能等价", 3.0, term="2026-2")])
    roadmap = build_case_a_roadmap(
        case,
        makeup_tasks=[
            MakeupTask(course_id="EQ-1", course_name="示例可能等价", credit=3.0,
                       status=MakeupStatus.POSSIBLY_EQUIVALENT)
        ],
        current_semester_label=SEMESTER,
        elective_group_id=None,
    )
    assert "EQ-1" in roadmap.future_course_ids


# ---------------------------------------------------------------------------
# 选修学分账
# ---------------------------------------------------------------------------


GROUP = "SYN-ELECTIVE-POOL"


def _elective_case(tmp_path: Path, *, minimum: float) -> object:
    return load_curriculum_case(
        _write(
            tmp_path,
            _payload(
                courses=[
                    _course("E1", "示例选修 1", 3.0, term="2026-2", requirement="elective", group_id=GROUP),
                    _course("E2", "示例选修 2", 3.0, term="2026-2", requirement="elective", group_id=GROUP),
                    _course("E3", "示例选修 3", 3.0, term="2026-2", requirement="elective", group_id=GROUP),
                    _course("E4", "示例选修 4", 3.0, term="2026-2", requirement="elective", group_id=GROUP),
                    _course("E5", "示例选修 5", 3.0, term="2026-2", requirement="elective", group_id=GROUP),
                    _course("D1", "示例已修选修", 3.0, term="2025-1", requirement="elective", group_id=GROUP),
                    _course("D2", "示例已修选修 2", 5.0, term="2025-2", requirement="elective", group_id=GROUP),
                    _course("C1", "示例本学期选修", 3.0, term="2026-1", requirement="elective", group_id=GROUP),
                    _course("C2", "示例本学期选修 2", 3.0, term="2026-1", requirement="elective", group_id=GROUP),
                    _course("OUT", "示例组外必修", 2.0, term="2026-1"),
                ],
                groups=[
                    {
                        "group_id": GROUP,
                        "name": "示例专业选修池",
                        "minimum_credit": minimum,
                        "source_record": "row:group",
                    }
                ],
            ),
        )
    )


def test_elective_minimum_is_read_from_curriculum_not_hard_coded(tmp_path: Path) -> None:
    """⛔ 代码里没有 23：把培养方案写成 11.0 时账目必须跟着变成 11.0。"""

    from app.models.contracts import MakeupTask

    case = _elective_case(tmp_path, minimum=11.0)
    tasks = [
        MakeupTask(course_id="D1", course_name="示例已修选修", credit=3.0, status=MakeupStatus.SATISFIED),
        MakeupTask(course_id="D2", course_name="示例已修选修 2", credit=5.0, status=MakeupStatus.SATISFIED),
    ]
    roadmap = build_case_a_roadmap(
        case,
        makeup_tasks=tasks,
        current_semester_label=SEMESTER,
        elective_group_id=GROUP,
    )
    assert roadmap.elective_requirement_credit == 11.0
    assert roadmap.elective_completed_credit == 8.0
    assert roadmap.elective_current_semester_credit == 0.0
    # 缺口 = 11 − 8 − 0 = 3
    assert roadmap.elective_planned_credit == 3.0
    assert roadmap.elective_remaining_credit == 0.0


def test_current_semester_elective_credit_reduces_the_future_gap(tmp_path: Path) -> None:
    from app.models.contracts import MakeupTask

    case = _elective_case(tmp_path, minimum=23.0)
    tasks = [
        MakeupTask(course_id="D1", course_name="示例已修选修", credit=3.0, status=MakeupStatus.SATISFIED),
        MakeupTask(course_id="D2", course_name="示例已修选修 2", credit=5.0, status=MakeupStatus.SATISFIED),
    ]
    current_courses = [item for item in case.new.courses if item.course_id in {"C1", "C2"}]
    roadmap = build_case_a_roadmap(
        case,
        makeup_tasks=tasks,
        current_semester_label=SEMESTER,
        elective_group_id=GROUP,
        current_semester_courses=current_courses,
        elective_current_semester_course_ids=["C1", "C2"],
    )
    assert roadmap.elective_requirement_credit == 23.0
    assert roadmap.elective_completed_credit == 8.0
    assert roadmap.elective_current_semester_credit == 6.0
    # 缺口 = 23 − 8 − 6 = 9（⛔ 不是 15）
    assert roadmap.elective_planned_credit == 9.0
    assert roadmap.elective_remaining_credit == 0.0


def test_current_semester_evidence_absent_is_reported_not_guessed(tmp_path: Path) -> None:
    case = _elective_case(tmp_path, minimum=23.0)
    roadmap = build_case_a_roadmap(
        case,
        makeup_tasks=[],
        current_semester_label=SEMESTER,
        elective_group_id=GROUP,
        elective_current_semester_course_ids=None,
    )
    assert roadmap.elective_current_semester_credit == 0.0
    assert any("本学期选修学分证据不足" in item for item in roadmap.unresolved)


def test_satisfied_course_outside_the_group_is_not_elective_credit(tmp_path: Path) -> None:
    """组外已满足课程⛔ 不得算作选修学分（不猜组归属）。"""

    from app.models.contracts import MakeupTask

    case = _elective_case(tmp_path, minimum=23.0)
    tasks = [
        MakeupTask(course_id="OUT", course_name="示例组外必修", credit=2.0,
                   status=MakeupStatus.SATISFIED),
    ]
    roadmap = build_case_a_roadmap(
        case,
        makeup_tasks=tasks,
        current_semester_label=SEMESTER,
        elective_group_id=GROUP,
    )
    assert roadmap.elective_completed_credit == 0.0
    # 组外课程仍然不得被重新规划
    assert "OUT" not in roadmap.future_course_ids


def test_unknown_elective_group_fails_closed(tmp_path: Path) -> None:
    case = _elective_case(tmp_path, minimum=23.0)
    with pytest.raises(CaseARoadmapError):
        build_case_a_roadmap(
            case,
            makeup_tasks=[],
            current_semester_label=SEMESTER,
            elective_group_id="NO-SUCH-GROUP",
        )


def test_requirement_kind_label_maps_every_kind() -> None:
    assert requirement_kind_label(RequirementKind.REQUIRED) == "必修"
    assert requirement_kind_label(RequirementKind.ELECTIVE) == "选修"
    assert requirement_kind_label(RequirementKind.UNKNOWN) == "未分类"
