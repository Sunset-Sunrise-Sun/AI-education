"""Regressions for the Codex review blockers #1 and #2.

Blocker #1: accepted Case A satisfaction facts were discarded when the uploaded
transcript was bound in, so confirmed-satisfied requirements could be replanned.

Blocker #2: current-semester elective credit was supported internally but never
wired by the runtime, so ``requirement - completed - current = planned + remaining``
was false at the real endpoint.

Synthetic data only; zero network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.models.contracts import CourseOffering, DataSource, Preference
from app.services.case_a_demo import (
    CaseADemoInputError,
    CaseADemoRuntime,
    _with_approved_scope_decisions,
)
from app.services.case_a_roadmap import bind_current_semester_courses

from tests import pdf_fixtures
from tests.test_case_a_roadmap_api import _case_payload, _course, _plan

SEMESTER = "2026-1"
GROUP = "CSE-ELECTIVE-POOL"


# ---------------------------------------------------------------------------
# Blocker #1 — accepted satisfaction facts must survive the PDF import
# ---------------------------------------------------------------------------


def _satisfaction_payload() -> dict[str, object]:
    """Case carrying a **confirmed satisfied** assessment for CSE310.

    `rules` are bound to the confirmed completed source, exactly like the accepted
    Case A baseline: satisfaction is source-backed, not a name guess.
    """

    payload = _case_payload()
    payload["new"]["course_records"] = [  # type: ignore[index]
        _course("PAST-1", "示例已过必修", 2.0, term="2025-1"),
        _course("CSE310", "示例操作系统", 3.0, term="2025-2"),
        _course("TODO-1", "示例待补必修", 3.0, term="2026-2"),
        # 选修组成员：用于验证本学期选修学分确实进入账目
        _course("EL-1", "示例选修 1", 3.0, term="2026-2",
                requirement="elective", group_id=GROUP),
        _course("EL-2", "示例选修 2", 3.0, term="2026-2",
                requirement="elective", group_id=GROUP),
    ]
    payload["new"]["group_records"] = [  # type: ignore[index]
        {
            "group_id": GROUP,
            "name": "示例专业选修池",
            "minimum_credit": 3.0,
            "source_record": "row:group",
        }
    ]
    # A completed record that matched CSE310, plus the rules that authorise the
    # exact-match assessment. Both are part of the accepted, source-backed facts.
    payload["completed"] = {  # type: ignore[assignment]
        "source_id": "synthetic://completed",
        "complete": True,
        "completeness_evidence": "synthetic://completed/scope",
        "records": [
            {
                "course_id": "CSE310",
                "course_name": "示例操作系统",
                "credit": 3.0,
                "semester": "2025-2",
                "passed": True,
                "course_type": "专必",
                "course_id_status": "confirmed",
                "id_match_source": "synthetic://completed/scope",
            }
        ],
    }
    payload["rules"] = {
        "target_version_id": "synthetic-new",
        "completed_source_id": "synthetic://completed",
        "evidence": "synthetic://matching-rules",
        "allow_exact_match": True,
        "allow_confirmed_absence": False,
    }
    return payload


def _runtime(tmp_path: Path, payload: dict[str, object]) -> CaseADemoRuntime:
    from tests.test_case_a_course_data_scope import (
        SHENZHEN,
        SOUTH,
        _import_campus,
        _offering,
    )
    from app.course_data import (
        CaseAScopedCourseDataProvider,
        build_case_a_dataset,
        initialize_course_data_store,
    )
    from app.curriculum.case import load_curriculum_case
    from app.planner import RestrictedPlannerProvider

    store = tmp_path / "case-a.sqlite3"
    initialize_course_data_store(store)
    _import_campus(
        store,
        number=SOUTH,
        offerings=[_offering("TODO-1", "01", semester=SEMESTER, course_name="示例待补必修")],
    )
    # 一门**选修组成员**的真实教学班，用于验证"本学期选修学分"确实进入账目。
    _import_campus(
        store,
        number=SHENZHEN,
        offerings=[
            _offering("CSE310", "01", semester=SEMESTER, course_name="示例操作系统"),
            _offering("EL-1", "01", semester=SEMESTER, course_name="示例选修 1"),
        ],
    )
    dataset = build_case_a_dataset(store, semester=SEMESTER)
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return CaseADemoRuntime(
        base_case=load_curriculum_case(case_path),
        course_data=CaseAScopedCourseDataProvider(dataset),
        planner=RestrictedPlannerProvider(),
    )


def test_accepted_satisfied_fact_is_not_discarded_by_the_pdf_import(tmp_path: Path) -> None:
    """⛔ 回归：上传成绩单不得抹掉已确认满足事实，且已满足课程不得被重新规划。"""

    runtime = _runtime(tmp_path, _satisfaction_payload())
    pdf = pdf_fixtures.build_case_a_transcript_pdf(tmp_path / "t.pdf").read_bytes()

    # 基线（未上传任何行）：CSE310 已确认满足
    from app.curriculum import CurriculumCaseProvider

    baseline = CurriculumCaseProvider(runtime.base_case).get_makeup_tasks()
    baseline_satisfied = {t.course_id for t in baseline if t.status.value == "satisfied"}
    assert "CSE310" in baseline_satisfied

    run = runtime.run(
        pdf_bytes=pdf,
        semester=SEMESTER,
        current_schedule=[],
        manual_schedule_attested=False,
        preference=Preference(),
    )
    after = {t.course_id: t.status.value for t in run.makeup_tasks}
    # ⛔ 已确认满足事实必须仍在
    assert after.get("CSE310") == "satisfied"
    # ⛔ 已满足课程不得出现在未来路线图里（不得被重新规划）
    assert "CSE310" not in set(run.roadmap.future_course_ids if run.roadmap else ())
    # 未满足的课仍然要被安排
    assert "TODO-1" in set(run.roadmap.future_course_ids if run.roadmap else ())


def test_manual_confirmation_is_never_promoted_by_the_import(tmp_path: Path) -> None:
    """⛔ 未被满足的课不得因为上传了成绩单就变成 satisfied。"""

    runtime = _runtime(tmp_path, _satisfaction_payload())
    pdf = pdf_fixtures.build_case_a_transcript_pdf(tmp_path / "t.pdf").read_bytes()
    run = runtime.run(
        pdf_bytes=pdf,
        semester=SEMESTER,
        current_schedule=[],
        manual_schedule_attested=False,
        preference=Preference(),
    )
    statuses = {t.course_id: t.status.value for t in run.makeup_tasks}
    assert statuses.get("TODO-1") != "satisfied"


def test_import_without_course_ids_is_reported_as_not_bound(tmp_path: Path) -> None:
    """真实成绩单没有官方课程号 ⇒ 如实标记 `not_bound`，⛔ 不静默。"""

    runtime = _runtime(tmp_path, _satisfaction_payload())
    pdf = pdf_fixtures.build_case_a_transcript_pdf(tmp_path / "t.pdf").read_bytes()
    run = runtime.run(
        pdf_bytes=pdf,
        semester=SEMESTER,
        current_schedule=[],
        manual_schedule_attested=False,
        preference=Preference(),
    )
    assert run.completed_binding == "not_bound"


def _import_with(tmp_path: Path, rows: list[object]) -> object:
    """构造一个仅替换 `courses` 的导入替身（其余字段保持真实取值）。"""

    import dataclasses

    pdf = pdf_fixtures.build_case_a_transcript_pdf(tmp_path / "fake.pdf").read_bytes()
    from app.services.completed_courses_pdf_ingest import (
        PDF_MEDIA_TYPE,
        CompletedCoursesPdfImport,
        import_completed_courses_pdf_bytes,
    )

    real = import_completed_courses_pdf_bytes(
        pdf, declared_length=len(pdf), media_type=PDF_MEDIA_TYPE
    )
    return dataclasses.replace(real, courses=tuple(rows))


def _completed_row(course_id: str | None, passed: bool):  # type: ignore[no-untyped-def]
    from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus

    return CompletedCourse(
        course_id=course_id,
        course_name="示例课程",
        credit=3.0,
        semester="2025-2",
        passed=passed,
        course_type="专必",
        course_id_status=CourseIdStatus.CONFIRMED if course_id else CourseIdStatus.PENDING,
        id_match_source="synthetic://completed" if course_id else None,
        source_id="synthetic://completed",
        source_record="row:1",
    )


def test_contradicting_import_fails_closed(tmp_path: Path) -> None:
    """上传行与已确认事实矛盾 ⇒ fail closed（⛔ 不猜测哪一侧正确）。"""

    runtime = _runtime(tmp_path, _satisfaction_payload())

    # ① 未知课程号：不在培养方案已确认事实中
    with pytest.raises(CaseADemoInputError, match="已确认事实之外"):
        runtime._completed_binding(_import_with(tmp_path, [_completed_row("UNKNOWN-9", True)]))  # noqa: SLF001

    # ② 把已确认通过的课程标为未通过
    with pytest.raises(CaseADemoInputError, match="标为未通过"):
        runtime._completed_binding(_import_with(tmp_path, [_completed_row("CSE310", False)]))  # noqa: SLF001

    # ③ 部分有课程号、部分没有 ⇒ 无法安全绑定
    with pytest.raises(CaseADemoInputError, match="部分记录带有课程号"):
        runtime._completed_binding(  # noqa: SLF001
            _import_with(tmp_path, [_completed_row("CSE310", True), _completed_row(None, True)])
        )

    # ④ 空行集合等价于"没有课程号" ⇒ not_bound（保留已确认事实），⛔ 不是矛盾
    binding, _case = runtime._completed_binding(_import_with(tmp_path, []))  # noqa: SLF001
    assert binding == "not_bound"

    # ⑤ 有课程号、且全部已知、但范围与已确认事实不一致（多出一门已确认事实之外的课
    #    已在 ① 覆盖）⇒ 这里用"缺了一门已确认课程"的等价场景：
    #    把两门都已确认的课程只上传其中一门。
    payload_two = _satisfaction_payload()
    payload_two["completed"]["records"].append(  # type: ignore[index]
        {
            "course_id": "PAST-1",
            "course_name": "示例已过必修",
            "credit": 2.0,
            "semester": "2025-1",
            "passed": True,
            "course_type": "公必",
            "course_id_status": "confirmed",
            "id_match_source": "synthetic://completed/scope",
        }
    )
    runtime_two = _runtime(tmp_path, payload_two)
    from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus

    only_cse310 = CompletedCourse(
        course_id="CSE310",
        course_name="示例操作系统",
        credit=3.0,
        semester="2025-2",
        passed=True,
        course_type="专必",
        course_id_status=CourseIdStatus.CONFIRMED,
        id_match_source="synthetic://completed",
        source_id="synthetic://completed",
        source_record="row:1",
    )
    with pytest.raises(CaseADemoInputError, match="范围不一致"):
        runtime_two._completed_binding(_import_with(tmp_path, [only_cse310]))  # noqa: SLF001


# ---------------------------------------------------------------------------
# Blocker #2 — current-semester elective credit must reach the runtime
# ---------------------------------------------------------------------------


def test_current_semester_elective_credit_reaches_the_runtime(tmp_path: Path) -> None:
    """一门**精确身份**的选修组课程在本学期课表里 ⇒ 恰好计入一次本学期学分。"""

    runtime = _runtime(tmp_path, _satisfaction_payload())
    offerings = runtime.course_data.get_course_offerings(SEMESTER)
    member_ids = {
        course.course_id
        for course in runtime.base_case.new.courses
        if course.group_id == GROUP
    }
    elective_offering = next(
        (item for item in offerings if item.course_id in member_ids), None
    )
    assert elective_offering is not None, (
        "regression must exercise the real path: the fixture has to carry an accepted "
        "offering for an elective-group member"
    )

    pdf = pdf_fixtures.build_case_a_transcript_pdf(tmp_path / "t.pdf").read_bytes()
    base = runtime.run(
        pdf_bytes=pdf,
        semester=SEMESTER,
        current_schedule=[],
        manual_schedule_attested=False,
        preference=Preference(),
    )
    with_current = runtime.run(
        pdf_bytes=pdf,
        semester=SEMESTER,
        current_schedule=[elective_offering],
        manual_schedule_attested=False,
        preference=Preference(),
    )
    assert with_current.roadmap is not None and base.roadmap is not None
    delta = (
        with_current.roadmap.elective_current_semester_credit
        - base.roadmap.elective_current_semester_credit
    )
    assert delta == elective_offering.credit
    # 该课程不得同时被排进未来学期
    assert elective_offering.course_id not in set(with_current.roadmap.future_course_ids)


def test_nonexact_current_schedule_course_is_unresolved_with_zero_credit(tmp_path: Path) -> None:
    """⛔ 课程号不在培养方案里 ⇒ 0 学分 + unresolved（⛔ 不按名字或学分猜测）。"""

    runtime = _runtime(tmp_path, _satisfaction_payload())
    alien = CourseOffering(
        course_id="NOT-IN-CURRICULUM",
        course_name="示例操作系统",  # 与培养方案课程**同名**，⛔ 不得因此绑定
        class_id="01",
        semester=SEMESTER,
        meetings=[],
        data_source=DataSource.REAL,
    )
    courses, elective_ids, unresolved = bind_current_semester_courses(
        runtime.base_case, [alien], elective_group_id=GROUP
    )
    assert courses == ()
    assert elective_ids == ()
    assert len(unresolved) == 1
    assert "NOT-IN-CURRICULUM" in unresolved[0]
