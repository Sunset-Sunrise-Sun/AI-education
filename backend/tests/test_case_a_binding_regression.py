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
from app.services.case_a_roadmap import (
    bind_current_semester_courses,
    build_case_a_roadmap,
)

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


def test_any_official_course_id_upload_fails_closed_by_design(tmp_path: Path) -> None:
    """⛔ 只要上传行带官方课程号就 fail closed —— 这是**设计**，不是缺陷。

    原因（见 `_completed_binding` 文档）：`CurriculumCase` 把 `completed` 行硬绑定在
    自己的 `source_id` 上，上传件与已确认来源是**两个来源**；
    用上传行改写满足事实只能靠伪造 provenance。因此本实现明确 fail closed，
    而不是"宣称支持 bound 但构造失败"。
    """

    runtime = _runtime(tmp_path, _satisfaction_payload())

    # ① 与已确认课程号完全一致（Codex 复现的那条路径）⇒ 仍然 fail closed
    with pytest.raises(CaseADemoInputError, match="不伪造来源"):
        runtime._completed_binding(_import_with(tmp_path, [_completed_row("CSE310", True)]))  # noqa: SLF001

    # ② 未知课程号 ⇒ 同样 fail closed（同一条信息，⛔ 不区分"是否一致"）
    with pytest.raises(CaseADemoInputError, match="不伪造来源"):
        runtime._completed_binding(_import_with(tmp_path, [_completed_row("UNKNOWN-9", True)]))  # noqa: SLF001

    # ③ 部分有课程号、部分没有 ⇒ 同样 fail closed
    with pytest.raises(CaseADemoInputError, match="不伪造来源"):
        runtime._completed_binding(  # noqa: SLF001
            _import_with(tmp_path, [_completed_row("CSE310", True), _completed_row(None, True)])
        )

    # ④ 已确认通过的课被标成未通过 ⇒ 也 fail closed（同样是带课程号的上传）
    with pytest.raises(CaseADemoInputError, match="不伪造来源"):
        runtime._completed_binding(_import_with(tmp_path, [_completed_row("CSE310", False)]))  # noqa: SLF001


def test_not_bound_keeps_a_valid_constructible_case(tmp_path: Path) -> None:
    """`not_bound` 必须返回一个**能真正构造**的有效 case（⛔ 不是"宣称可用却构不出"）。

    这正是 Codex 复现的问题：旧 `bound` 分支替换 `completed_source_id` 后
    `CurriculumCase` 直接拒绝构造（`rules: configuration is outside the supplied case`
    / `completed records do not belong to the supplied source`）。
    """

    from app.curriculum import CurriculumCaseProvider

    runtime = _runtime(tmp_path, _satisfaction_payload())

    # 空行集合与"全部无课程号"都必须走 not_bound，且返回的 case 必须可用
    for rows in ([], [_completed_row(None, True), _completed_row(None, True)]):
        effective = runtime._completed_binding(_import_with(tmp_path, rows))  # noqa: SLF001
        assert effective is runtime.base_case or effective.completed_source_id == runtime.base_case.completed_source_id
        # 关键：能真正构造 provider 并产出补修任务（⛔ 不会抛 CurriculumNormalizationError）
        tasks = CurriculumCaseProvider(effective).get_makeup_tasks()
        statuses = {task.course_id: task.status.value for task in tasks}
        # 已确认满足事实保留
        assert statuses.get("CSE310") == "satisfied"
        # ⛔ manual_confirmation / possibly_equivalent 未被提升
        assert statuses.get("TODO-1") != "satisfied"


def test_curriculum_provider_construction_matches_the_single_return_contract(
    tmp_path: Path,
) -> None:
    """直接锁定单返回值契约，⛔ 防止 `_binding, case = ...` 这类过期解包回归。

    历史缺陷：`_curriculum()` 曾写成
    `_binding, case = self._completed_binding(imported)`，
    而 `_completed_binding()` 只返回一个 `CurriculumCase`
    ⇒ `TypeError: cannot unpack non-iterable CurriculumCase object`
    （Codex 独立复现）。该 helper 已删除；这里同时验证：
    ① 返回值**不可迭代解包**；② 用它构造 provider 是正确的用法；
    ③ 死 helper 不会回来。
    """

    from app.curriculum import CurriculumCaseProvider
    from app.services.case_a_demo import CaseADemoRuntime

    runtime = _runtime(tmp_path, _satisfaction_payload())
    effective = runtime._completed_binding(_import_with(tmp_path, []))  # noqa: SLF001

    # ① 单值返回：任何"解包两个"的写法都必须失败
    with pytest.raises(TypeError):
        _binding, _case = effective  # type: ignore[misc]  # noqa: F841

    # ② 正确用法：直接交给 provider
    tasks = CurriculumCaseProvider(effective).get_makeup_tasks()
    assert tasks, "the returned case must project makeup tasks"

    # ③ 死 helper 必须保持删除状态
    assert not hasattr(CaseADemoRuntime, "_curriculum"), (
        "_curriculum() must stay removed: it was dead code carrying the stale unpack"
    )


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


def test_completed_and_current_elective_overlap_is_counted_once(tmp_path: Path) -> None:
    """⛔ 同一选修课程身份**不得**同时计入已完成与本学期（双计分）。

    构造真实矛盾状态：`EL-1` 既被确认为**已满足**（计入 completed），
    又出现在本学期课表里。两个身份集合必须互斥 ⇒ 只算一次 + 确定性报告 + 不重复规划。
    """

    from app.models.contracts import MakeupStatus, MakeupTask

    runtime = _runtime(tmp_path, _satisfaction_payload())
    offerings = runtime.course_data.get_course_offerings(SEMESTER)
    elective_offering = next(
        (item for item in offerings if item.course_id == "EL-1"), None
    )
    assert elective_offering is not None, "fixture must carry an accepted EL-1 class"

    # ① 第一道防线：binder 收到 completed 身份时必须拒绝把它算作"本学期在修"
    courses, elective_ids, unresolved = bind_current_semester_courses(
        runtime.base_case,
        [elective_offering],
        elective_group_id=GROUP,
        completed_course_ids={"EL-1"},
    )
    assert "EL-1" not in {course.course_id for course in courses}
    assert elective_ids == ()
    assert any("已被记为**已确认完成**" in item for item in unresolved)

    # ② 第二道防线：即使调用方把重叠集合强行传进路线图，账目也只算一次并报告。
    #    `elective_completed_course_ids` 由**已确认满足**的补修任务推导，
    #    因此这里用真实路径制造重叠：EL-1 既 satisfied，又在本学期课表里。
    #    注意 `current_semester_courses` 要传**培养方案课程**（不是教学班）。
    el1_course = next(
        course for course in runtime.base_case.new.courses if course.course_id == "EL-1"
    )
    roadmap = build_case_a_roadmap(
        runtime.base_case,
        makeup_tasks=[
            MakeupTask(
                course_id="EL-1",
                course_name="示例选修 1",
                credit=3.0,
                status=MakeupStatus.SATISFIED,
            )
        ],
        current_semester_label=SEMESTER,
        elective_group_id=GROUP,
        current_semester_courses=[el1_course],
        elective_current_semester_course_ids=["EL-1"],
    )
    # 只算一次：已完成得 3 学分，本学期**不再**重复计入
    assert roadmap.elective_completed_credit == 3.0
    assert roadmap.elective_current_semester_credit == 0.0
    # 确定性报告
    assert any("只计一次" in item and "EL-1" in item for item in roadmap.unresolved)
    # 账目恒等式仍然成立
    assert (
        roadmap.elective_requirement_credit
        - roadmap.elective_completed_credit
        - roadmap.elective_current_semester_credit
        == roadmap.elective_planned_credit + roadmap.elective_remaining_credit
    )
    # ⛔ 该课程不得再被排入未来学期
    assert "EL-1" not in set(roadmap.future_course_ids)
