"""AI 接口的来源可信性（F-05）回归测试。

修掉的行为：AI 接口的教学班**全部来自请求体**，请求方可以自己写 `data_source=real`。
修复前这会让响应报 `real`、前端显示"上下文全部为 real 教学班"，
并且**抑制**"不代表真实教务开课"的风险提示。

修复后：⛔ 请求方的自述**永远**换不来"已核验"：
- 上下文来源降级为 `real_unverified`；
- 响应新增的 `context_source_verified` 恒为 `false`；
- 风险提示**必然**出现（不可被请求体抑制）。

⛔ 本文件不产生任何真实批准，全部为合成夹具。
"""

from __future__ import annotations

import json

import pytest

from app.ai_planning.context import (
    CONTEXT_SOURCE_MIXED,
    CONTEXT_SOURCE_REAL,
    CONTEXT_SOURCE_REAL_UNVERIFIED,
    CONTEXT_SOURCE_UNKNOWN,
    PlanningContext,
    build_context,
)
from app.ai_planning.errors import PlanContextInvalidError
from app.models.contracts import CourseOffering, PlanResult, Preference
from tests.ai_planning_fixtures import base_plan


def _offering(source: str, course_id: str = "DS101", class_id: str = "ds-01") -> CourseOffering:
    return CourseOffering.model_validate({
        "course_id": course_id, "course_name": "示例课程", "class_id": class_id,
        "semester": "2026-1",
        "meetings": [{"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1]}],
        "data_source": source,
    })


def _plan() -> PlanResult:
    return base_plan()


# --------------------------------------------------------------------------- #
# 上下文层：自述 real 一律降级
# --------------------------------------------------------------------------- #

def test_caller_supplied_real_is_downgraded_to_unverified() -> None:
    """⛔ 请求体写 real ⇒ `real_unverified`，不是 `real`。"""

    context = build_context(
        semester="2026-1", base_plan=_plan(), makeup_tasks=[],
        offerings=[_offering("real")], preference=Preference(),
    )
    assert context.data_source == CONTEXT_SOURCE_REAL_UNVERIFIED
    assert context.source_verified is False


def test_explicit_server_side_verification_keeps_real() -> None:
    """只有**服务端**显式传入 `source_verified=True` 才保留 `real`。

    ⚠️ 这是给"服务端自己装配并通过 provenance 门"的链路留的接口，
    ⛔ 不是给 AI 请求用的（AI 接口硬编码传 False）。
    """

    context = build_context(
        semester="2026-1", base_plan=_plan(), makeup_tasks=[],
        offerings=[_offering("real")], preference=Preference(), source_verified=True,
    )
    assert context.data_source == CONTEXT_SOURCE_REAL
    assert context.source_verified is True


def test_mock_and_unknown_are_unchanged() -> None:
    mock = build_context(
        semester="2026-1", base_plan=_plan(), makeup_tasks=[],
        offerings=[_offering("mock")], preference=Preference(),
    )
    empty = build_context(
        semester="2026-1", base_plan=_plan(), makeup_tasks=[],
        offerings=[], preference=Preference(),
    )
    assert mock.data_source == "mock"
    assert mock.source_verified is False
    assert empty.data_source == CONTEXT_SOURCE_UNKNOWN
    assert empty.source_verified is False


def test_mixed_sources_are_not_upgraded_by_source_verified() -> None:
    mixed = build_context(
        semester="2026-1", base_plan=_plan(), makeup_tasks=[],
        offerings=[_offering("mock"), _offering("real", "ALGO201", "algo-02")],
        preference=Preference(), source_verified=True,
    )
    assert mixed.data_source == CONTEXT_SOURCE_MIXED


def test_declaring_real_without_verification_cannot_be_forced_through() -> None:
    """即使把 `source_verified=False` 显式写出来，结果也一样（默认即安全）。"""

    context = build_context(
        semester="2026-1", base_plan=_plan(), makeup_tasks=[],
        offerings=[_offering("real")], preference=Preference(), source_verified=False,
    )
    assert context.data_source == CONTEXT_SOURCE_REAL_UNVERIFIED


def test_planning_context_rejects_non_boolean_source_verified() -> None:
    with pytest.raises(PlanContextInvalidError):
        PlanningContext(
            semester="2026-1", base_plan=_plan(), makeup_tasks=(), offerings=(),
            preference=Preference(), data_source="mock",
            digest="0" * 64, source_verified="yes",  # type: ignore[arg-type]
        )


def test_planning_context_post_init_downgrades_real_without_verification() -> None:
    """不变量写在校验里：**任何**构造路径都不能让"未核验的 real"留下来。"""

    context = PlanningContext(
        semester="2026-1", base_plan=_plan(), makeup_tasks=(), offerings=(),
        preference=Preference(), data_source=CONTEXT_SOURCE_REAL, digest="0" * 64,
    )
    assert context.data_source == CONTEXT_SOURCE_REAL_UNVERIFIED


# --------------------------------------------------------------------------- #
# 通过真实 HTTP：响应必须如实报告"未核验"
# --------------------------------------------------------------------------- #

def test_interpret_response_reports_unverified_context_over_real_http() -> None:
    """走真实 FastAPI + 真实 HTTP：自述 real ⇒ 响应 real_unverified 且 verified=false。"""

    from tests.test_ai_planning_joint_e2e import LiveServer, http_json, rule_model
    from tests.test_ai_planning_joint_e2e import make_config
    from app.ai_planning import AiPlanningService, SessionStore
    from app.planner import RestrictedPlannerProvider

    context = {
        "semester": "2026-1",
        "base_plan": _plan().model_dump(mode="json"),
        "makeup_tasks": [],
        # ⚠️ 请求方自己把教学班标成 real —— 这正是要挡的自述
        "course_offerings": [_offering("real").model_dump(mode="json")],
        "preference": Preference().model_dump(mode="json"),
    }
    service = AiPlanningService(
        config=make_config(), intent_model=rule_model(),
        planner=RestrictedPlannerProvider(), sessions=SessionStore(max_sessions=10),
    )

    with LiveServer(service) as server:
        status, body = http_json(
            server.base_url, "POST", "/api/v1/ai-planning/interpret",
            {"context": context, "user_message": "尽量别在周五上课，最多 12 学分"},
        )

    assert status == 200, body
    assert body["data_source"] == CONTEXT_SOURCE_REAL_UNVERIFIED
    assert body["context_source_verified"] is False


def test_context_body_cannot_smuggle_source_verified() -> None:
    """请求模型是 `extra="forbid"`：⛔ 无法通过请求体打开"已核验"。"""

    from app.api.ai_planning import PlanContextBody

    with pytest.raises(Exception):
        PlanContextBody.model_validate({
            "semester": "2026-1",
            "base_plan": _plan().model_dump(mode="json"),
            "makeup_tasks": [],
            "course_offerings": [],
            "preference": Preference().model_dump(mode="json"),
            "source_verified": True,
        })


# --------------------------------------------------------------------------- #
# 风险提示：⛔ 不可被请求体抑制
# --------------------------------------------------------------------------- #

def test_risk_note_appears_for_unverified_real_over_http() -> None:
    """任务书明确要求：不允许这类数据压制来源风险提示。"""

    from tests.test_ai_planning_joint_e2e import LiveServer, http_json, rule_model, make_config
    from tests.ai_planning_fixtures import confirm_payload
    from app.ai_planning import AiPlanningService, SessionStore
    from app.planner import RestrictedPlannerProvider

    context = {
        "semester": "2026-1",
        "base_plan": _plan().model_dump(mode="json"),
        "makeup_tasks": [],
        "course_offerings": [_offering("real").model_dump(mode="json")],
        "preference": Preference().model_dump(mode="json"),
    }
    service = AiPlanningService(
        config=make_config(), intent_model=rule_model(),
        planner=RestrictedPlannerProvider(), sessions=SessionStore(max_sessions=10),
    )

    with LiveServer(service) as server:
        _, draft = http_json(
            server.base_url, "POST", "/api/v1/ai-planning/interpret",
            {"context": context, "user_message": "尽量别在周五上课，最多 12 学分"},
        )
        status, solved = http_json(
            server.base_url, "POST", "/api/v1/ai-planning/solve",
            {
                "intent_id": draft["intent_id"], "plan_digest": draft["plan_digest"],
                "confirmed_intent": confirm_payload(
                    plan_digest=draft["plan_digest"], weekday=5,
                ),
            },
        )

    assert status == 200, solved
    joined = " ".join(solved.get("risks") or [])
    assert "未经服务端独立核验" in joined, (
        "自述 real 的来源**必须**带风险提示；修复前这条会被抑制（缺口 F-05）"
    )
