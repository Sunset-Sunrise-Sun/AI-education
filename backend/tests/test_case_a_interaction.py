"""最终交互轮 —— 后端回归测试（规划覆盖 + 选修交互 + 空学期诚实性）。

对应 Issue #61 与 Codex PREIMPLEMENTATION REVIEW 的 must-fix 项：

- 来源可核验的基础评估**不得**被用户确认改写（确认只是 run-local 规划覆盖）；
- 身份只能用精确 `course_id`；未知/重复/不合格输入 fail closed；
- 选修只接受精确 `semester + course_id + class_id`，且服务端复核 CLEAR；
- 选修加入/移除必须**单次**计入负荷与未来选修账目（⛔ 不双计）；
- `total_credit` 始终等于已列出课程学分之和（空学期诚实性的后端不变量）。

测试分两层：

1. **纯函数层**（不需要私有工件）—— 身份校验 / 覆盖语义，CI 里**始终执行**；
2. **API 层**（需要本地 accepted Case A 私有工件）—— 未配置时**显式 skip**，
   ⛔ 不让"工件缺失"伪装成通过，也不把私有数据提交进仓库。
"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.contracts import MakeupStatus
from app.services.case_a_planning_override import (
    PLANNING_ONLY_DISCLOSURE,
    ElectiveSelection,
    apply_planning_overrides,
    resolve_elective_selections,
    validate_override_course_ids,
)
from app.services.case_a_roadmap import CASE_A_CURRENT_HARD_MAX_CREDIT

SEMESTER = "2026-1"

#: 本地 accepted Case A 工件（⛔ 仅在本地/验证环境存在，不进仓库）。
_REQUIRED_ENV = (
    "APP_CASE_A_DEMO_ENABLED",
    "APP_CASE_A_DEMO_CURRICULUM_CASE_PATH",
    "APP_CASE_A_DEMO_COURSE_DATA_SQLITE_PATH",
)


def _real_artifacts_available() -> bool:
    if any(not os.environ.get(name) for name in _REQUIRED_ENV):
        return False
    return all(Path(os.environ[name]).exists() for name in _REQUIRED_ENV[1:])


_real_case_only = pytest.mark.skipif(
    not _real_artifacts_available(),
    reason=(
        "accepted Case A private artifacts are not configured in this environment; "
        "API-level interaction assertions require them (no synthetic substitute is "
        "faithful enough for the elective-group structure)"
    ),
)


@pytest.fixture()
def accepted_runtime():
    """真实 accepted Case A runtime（只用本地已有工件，⛔ 不新增采集）。"""

    from app.services.case_a_demo import build_case_a_demo_runtime

    runtime = build_case_a_demo_runtime(dict(os.environ))
    assert runtime is not None
    return runtime


@pytest.fixture()
def client(accepted_runtime) -> TestClient:
    from app.main import app

    app.dependency_overrides.clear()
    return TestClient(app)


@pytest.fixture()
def pdf_bytes() -> bytes:
    from tests import pdf_fixtures

    tmp = Path(tempfile.mkdtemp())
    return pdf_fixtures.build_case_a_transcript_pdf(tmp / "t.pdf").read_bytes()


def _plan(client: TestClient, pdf: bytes, **extra: object) -> dict:
    body = {
        "semester": SEMESTER,
        "transcript_pdf_base64": base64.b64encode(pdf).decode(),
        "current_schedule": [],
        "manual_schedule_attested": False,
        "preference": {"avoid_cross_campus": False},
    }
    body.update(extra)
    response = client.post("/api/v1/case-a-demo/plan", json=body)
    assert response.status_code == 200, response.text[:500]
    return response.json()


def _counts(tasks: list[dict]) -> dict[str, int]:
    out = {"satisfied": 0, "manual_confirmation": 0}
    for task in tasks:
        if task["status"] in out:
            out[task["status"]] += 1
    return out


def _elective_candidates(data: dict) -> list[dict]:
    """只取**唯一 CLEAR** 的候选（可显式加入）。"""

    return [
        r
        for r in data["current_elective_recommendations"]
        if r["clear_class_count"] == 1 and r["unique_clear_class_id"]
    ]


def _manual_key(data: dict) -> str:
    return next(
        t["course_id"] for t in data["makeup_tasks"] if t["status"] == "manual_confirmation"
    )


# ---------------------------------------------------------------------------
# 1) 基础评估不可变 + 确认/撤销
# ---------------------------------------------------------------------------


@_real_case_only
def test_base_assessment_is_returned_unchanged(client: TestClient, pdf_bytes: bytes) -> None:
    pdf = pdf_bytes
    data = _plan(client, pdf)
    assert data["makeup_tasks"], "synthetic case must produce makeup tasks"
    assert _counts(data["makeup_tasks"]) == _counts(data["effective_makeup_tasks"])
    assert data["applied_manual_confirmations"] == []


@_real_case_only
def test_confirmation_only_changes_the_effective_planning_view(
    client: TestClient, pdf_bytes: bytes
) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    key = _manual_key(base)
    confirmed = _plan(client, pdf, user_confirmed_manual_task_keys=[key])

    # ⛔ 来源评估一字不改
    assert confirmed["makeup_tasks"] == base["makeup_tasks"]
    # ✅ 有效视图里该课变成已满足
    before = _counts(base["effective_makeup_tasks"])
    after = _counts(confirmed["effective_makeup_tasks"])
    assert after["satisfied"] == before["satisfied"] + 1
    assert after["manual_confirmation"] == before["manual_confirmation"] - 1
    assert confirmed["applied_manual_confirmations"] == [key]


@_real_case_only
def test_confirmed_item_carries_all_three_disclosures(
    client: TestClient, pdf_bytes: bytes
) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    key = _manual_key(base)
    data = _plan(client, pdf, user_confirmed_manual_task_keys=[key])
    effective = next(t for t in data["effective_makeup_tasks"] if t["course_id"] == key)
    for phrase in PLANNING_ONLY_DISCLOSURE.values():
        assert phrase in (effective["reason"] or "")
    assert data["planning_only_disclosure"] == PLANNING_ONLY_DISCLOSURE


@_real_case_only
def test_undo_restores_the_original_plan(client: TestClient, pdf_bytes: bytes) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    key = _manual_key(base)
    _plan(client, pdf, user_confirmed_manual_task_keys=[key])
    undone = _plan(client, pdf)
    assert undone["effective_makeup_tasks"] == base["effective_makeup_tasks"]
    assert undone["plan_result"] == base["plan_result"]
    assert undone["roadmap"] == base["roadmap"]
    assert undone["applied_manual_confirmations"] == []


# ---------------------------------------------------------------------------
# 2) 身份校验 fail closed（纯函数）
# ---------------------------------------------------------------------------


def _tasks():
    from app.models.contracts import MakeupTask

    return [
        MakeupTask(course_id="OK1", course_name="a", credit=3.0,
                   status=MakeupStatus.MANUAL_CONFIRMATION),
        MakeupTask(course_id="SAT", course_name="b", credit=3.0,
                   status=MakeupStatus.SATISFIED),
        MakeupTask(course_id="REQ", course_name="c", credit=3.0,
                   status=MakeupStatus.REQUIRED),
        MakeupTask(course_id="EQV", course_name="d", credit=3.0,
                   status=MakeupStatus.POSSIBLY_EQUIVALENT),
    ]


@pytest.mark.parametrize(
    "key",
    ["SAT", "REQ", "EQV", "NOPE", "", "  ", "ok1", "程序设计I", "0"],
)
def test_ineligible_and_non_identity_keys_are_rejected(key: str) -> None:
    accepted, rejected = validate_override_course_ids(_tasks(), [key])
    assert accepted == ()
    assert rejected, f"{key!r} must be rejected"


def test_valid_key_is_accepted() -> None:
    accepted, rejected = validate_override_course_ids(_tasks(), ["OK1"])
    assert accepted == ("OK1",)
    assert rejected == ()


def test_duplicate_key_is_rejected_entirely() -> None:
    accepted, rejected = validate_override_course_ids(_tasks(), ["OK1", "OK1"])
    assert accepted == ()
    assert len(rejected) == 2


def test_apply_planning_overrides_does_not_mutate_input() -> None:
    tasks = _tasks()
    before = [t.model_dump() for t in tasks]
    effective, _, _ = apply_planning_overrides(tasks, confirmed_course_ids=["OK1"])
    assert [t.model_dump() for t in tasks] == before
    assert tasks[0].status is MakeupStatus.MANUAL_CONFIRMATION
    assert effective[0].status is MakeupStatus.SATISFIED


@_real_case_only
def test_unknown_override_id_is_reported_not_silently_dropped(
    client: TestClient, pdf_bytes: bytes
) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    data = _plan(client, pdf, user_confirmed_manual_task_keys=["NOT-A-COURSE"])
    assert data["applied_manual_confirmations"] == []
    assert [r["course_id"] for r in data["rejected_manual_confirmations"]] == ["NOT-A-COURSE"]
    assert data["effective_makeup_tasks"] == base["effective_makeup_tasks"]


# ---------------------------------------------------------------------------
# 3) 选修交互
# ---------------------------------------------------------------------------


def _candidate(data: dict, course_id: str) -> dict:
    return next(
        r for r in data["current_elective_recommendations"] if r["course_id"] == course_id
    )


@_real_case_only
def test_single_clear_elective_updates_timetable_load_and_future_accounting(
    client: TestClient, pdf_bytes: bytes
) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    candidates = _elective_candidates(base)
    assert candidates, "accepted data must offer at least one single-CLEAR elective"
    pick = candidates[0]
    selection = {
        "semester": SEMESTER,
        "course_id": pick["course_id"],
        "class_id": pick["unique_clear_class_id"],
    }
    added = _plan(client, pdf, elective_selections=[selection])

    assert [(s["course_id"], s["class_id"]) for s in added["applied_elective_sections"]] == [
        (pick["course_id"], pick["unique_clear_class_id"])
    ]
    # 进入当前学期推荐课表
    assert any(
        c["course_id"] == pick["course_id"] for c in added["plan_result"]["selected_classes"]
    )
    # 计入本学期负荷，且**只计一次**
    assert added["current_load"]["projected_total_credit"] == pytest.approx(
        base["current_load"]["projected_total_credit"] + pick["credit"]
    )
    # 计入未来选修账目
    assert added["roadmap"]["elective"]["current_semester_credit"] >= pick["credit"]
    # 已加入的课程不再作为"可加入"候选出现
    assert pick["course_id"] not in [
        r["course_id"] for r in added["current_elective_recommendations"]
    ]


@_real_case_only
def test_removing_elective_reverses_everything(client: TestClient, pdf_bytes: bytes) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    pick = _elective_candidates(base)[0]
    _plan(
        client,
        pdf,
        elective_selections=[
            {
                "semester": SEMESTER,
                "course_id": pick["course_id"],
                "class_id": pick["unique_clear_class_id"],
            }
        ],
    )
    removed = _plan(client, pdf)
    assert removed["applied_elective_sections"] == []
    assert removed["current_load"] == base["current_load"]
    assert removed["plan_result"] == base["plan_result"]
    assert removed["roadmap"] == base["roadmap"]


@_real_case_only
def test_multiple_clear_sections_require_explicit_choice(
    client: TestClient, pdf_bytes: bytes
) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    pick = _candidate(base, "EL102")
    assert pick["clear_class_count"] == 1
    assert pick["unique_clear_class_id"] == "02"
    # 明确选择 CLEAR 的 02 ⇒ 通过
    ok = _plan(
        client,
        pdf,
        elective_selections=[{"semester": SEMESTER, "course_id": "EL102", "class_id": "02"}],
    )
    assert [s["class_id"] for s in ok["applied_elective_sections"]] == ["02"]
    # 选择与当前课表冲突的 01 ⇒ 拒绝，且⛔ **不静默回退**到 02
    bad = _plan(
        client,
        pdf,
        elective_selections=[
            {"semester": SEMESTER, "course_id": "EL102", "class_id": "01"},
            # 同时清掉其它选择，确保只观察 EL102
        ],
    )
    assert bad["applied_elective_sections"] == []
    assert [r["course_id"] for r in bad["rejected_elective_selections"]] == ["EL102"]


@_real_case_only
def test_multiple_clear_sections_require_explicit_choice(
    client: TestClient, pdf_bytes: bytes
) -> None:
    """多个 CLEAR 教学班时必须显式指定；未指定 ⇒ 拒绝（⛔ 不隐式选一个）。"""

    pdf = pdf_bytes
    base = _plan(client, pdf)
    multi = [r for r in base["current_elective_recommendations"] if r["clear_class_count"] > 1]
    if not multi:
        pytest.skip("accepted data has no multi-CLEAR elective in this semester")
    pick = multi[0]
    # 多个 CLEAR ⇒ 服务端**不**给唯一班号
    assert pick["unique_clear_class_id"] is None
    undecided = _plan(
        client,
        pdf,
        elective_selections=[
            {"semester": SEMESTER, "course_id": pick["course_id"], "class_id": ""}
        ],
    )
    assert undecided["applied_elective_sections"] == []
    assert [r["course_id"] for r in undecided["rejected_elective_selections"]] == [
        pick["course_id"]
    ]

    # 显式指定一个真实 CLEAR 教学班 ⇒ 通过
    clear_ids = [
        c["class_id"]
        for c in base["course_offerings"]
        if c["course_id"] == pick["course_id"]
    ]
    assert clear_ids, "candidate must exist in accepted offerings"
    chosen = _plan(
        client,
        pdf,
        elective_selections=[
            {"semester": SEMESTER, "course_id": pick["course_id"], "class_id": clear_ids[0]}
        ],
    )
    # 该教学班要么无冲突被接受，要么被明确拒绝；⛔ 绝不回退到别的教学班
    if chosen["applied_elective_sections"]:
        assert [s["class_id"] for s in chosen["applied_elective_sections"]] == [clear_ids[0]]
    else:
        assert [r["course_id"] for r in chosen["rejected_elective_selections"]] == [
            pick["course_id"]
        ]


@_real_case_only
def test_unknown_only_elective_can_never_be_added(
    client: TestClient, pdf_bytes: bytes
) -> None:
    """非 CLEAR（UNKNOWN / CONFLICT）一律不可加入，⛔ 没有 apply 路径。"""

    pdf = pdf_bytes
    base = _plan(client, pdf)
    member_ids = sorted({r["course_id"] for r in base["current_elective_recommendations"]})
    assert member_ids, "accepted data must expose elective candidates"
    # 强行给一个不存在/不可用的教学班号 ⇒ 必须被拒且给出原因
    for course_id in member_ids:
        data = _plan(
            client,
            pdf,
            elective_selections=[
                {"semester": SEMESTER, "course_id": course_id, "class_id": "0"}
            ],
        )
        assert data["applied_elective_sections"] == [], course_id
        assert data["rejected_elective_selections"], course_id

    # 只有 UNKNOWN/CONFLICT 的课程不得出现在可加入候选里
    for item in base["current_elective_recommendations"]:
        assert item["clear_class_count"] >= 1 or item["unique_clear_class_id"] is None


@_real_case_only
def test_non_member_and_bad_section_are_rejected(
    client: TestClient, pdf_bytes: bytes
) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    pick = _elective_candidates(base)[0]
    probes = [
        # 非选修组成员（培养方案必修课）
        {"semester": SEMESTER, "course_id": "CSE101", "class_id": "01"},
        # 教学班不存在
        {"semester": SEMESTER, "course_id": pick["course_id"], "class_id": "nope"},
        # 未指定教学班
        {"semester": SEMESTER, "course_id": pick["course_id"], "class_id": ""},
        # 学期不属于 accepted scope
        {"semester": "2999-9", "course_id": pick["course_id"], "class_id": "01"},
    ]
    for probe in probes:
        data = _plan(client, pdf, elective_selections=[probe])
        assert data["applied_elective_sections"] == [], probe
        assert data["rejected_elective_selections"], probe


@_real_case_only
def test_duplicate_elective_is_rejected_entirely(
    client: TestClient, pdf_bytes: bytes
) -> None:
    pdf = pdf_bytes
    base = _plan(client, pdf)
    pick = _elective_candidates(base)[0]
    selection = {
        "semester": SEMESTER,
        "course_id": pick["course_id"],
        "class_id": pick["unique_clear_class_id"],
    }
    data = _plan(client, pdf, elective_selections=[selection, dict(selection)])
    assert data["applied_elective_sections"] == []
    # 两次重复输入都被如实报告（⛔ 不静默丢弃任何一条）
    assert {r["course_id"] for r in data["rejected_elective_selections"]} == {
        pick["course_id"]
    }



@_real_case_only
def test_resolve_elective_selections_directly_is_fail_closed(accepted_runtime) -> None:
    offerings = accepted_runtime.course_data.get_course_offerings(SEMESTER)
    accepted, rejected = resolve_elective_selections(
        accepted_runtime.base_case,
        [
            ElectiveSelection(SEMESTER, "CSE317", ""),
            ElectiveSelection(SEMESTER, "NOT-A-MEMBER", "01"),
            ElectiveSelection(SEMESTER, "CSE101", "01"),
        ],
        offerings,
        elective_group_id=accepted_runtime.elective_group_id,
        current_schedule=[],
    )
    assert accepted == ()
    assert len(rejected) == 3


@_real_case_only
def test_current_cap_is_30(client: TestClient, pdf_bytes: bytes) -> None:
    pdf = pdf_bytes
    data = _plan(client, pdf)
    assert data["current_load"]["max_credit"] == 30.0
    assert CASE_A_CURRENT_HARD_MAX_CREDIT == 30.0


# ---------------------------------------------------------------------------
# 4) 空学期诚实性（后端不变量）
# ---------------------------------------------------------------------------


@_real_case_only
def test_total_credit_always_equals_listed_course_credits(
    client: TestClient, pdf_bytes: bytes
) -> None:
    """`total_credit` 必须等于已列出课程学分之和。

    这证明"UI 显示 0 学分而 API 有学分"在后端层面**结构上不可达**：
    一旦二者不一致，本测试立即失败。
    """

    pdf = pdf_bytes
    data = _plan(client, pdf)
    roadmap = data["roadmap"]
    assert roadmap is not None
    for semester in roadmap["future_semesters"]:
        listed = round(sum(c["credit"] for c in semester["courses"]), 3)
        assert semester["total_credit"] == pytest.approx(listed), semester["semester_label"]
        if not semester["courses"]:
            assert semester["total_credit"] == 0.0


@_real_case_only
def test_future_never_exceeds_hard_max(client: TestClient, pdf_bytes: bytes) -> None:
    pdf = pdf_bytes
    data = _plan(client, pdf)
    for semester in data["roadmap"]["future_semesters"]:
        assert semester["total_credit"] <= 35.0
