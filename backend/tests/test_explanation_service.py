"""解释服务（Explanation）测试：有据可查、只读、失败安全。

覆盖：
- 正常情况：完整上下文下每个 `PlanResult` 条目 / 每条 `MakeupTask` 都有解释；
- 状态区分：required / satisfied / manual_confirmation / possibly_equivalent 得到不同且准确的说明；
- 缺证据：没有 MakeupTask 上下文时**不得**猜测判定状态；
- 只读：解释不修改输入，摘要可核对；解释模块不导入 Planner / Curriculum / Course Data / Mock 通道；
- 边界：空方案、空列表、超长文本、空 meetings、重复课程号；
- 失败路径：请求体非法（422）、上下文超规模（422）、模型适配层失败时**如实降级**。
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import explanation as explanation_api
from app.explanation import (
    GeneratorKind,
    ItemKind,
    build_explanation,
    build_explanation_facts,
    plan_digest,
)
from app.explanation.adapter import (
    ModelAdapterError,
    try_model_answer,
    validate_model_answer,
)
from app.explanation import service as explanation_service
from app.explanation import models as explanation_models
from app.explanation import templates as explanation_templates
from app.explanation.service import ExplanationService
from app.models.contracts import CourseOffering, MakeupTask, PlanResult
from app.services import mock_service

EXPLANATION_PATH = "/api/v1/explanation/plan"


def _offering(
    course_id: str,
    class_id: str,
    *,
    data_source: str = "mock",
    meetings: list[dict[str, object]] | None = None,
) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=f"{course_id} 课程",
        class_id=class_id,
        semester="2026-1",
        meetings=meetings
        if meetings is not None
        else [{"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1, 2]}],
        data_source=data_source,
    )


def _task(course_id: str, status: str, **overrides: object) -> MakeupTask:
    payload: dict[str, object] = {
        "course_id": course_id,
        "course_name": f"{course_id} 课程",
        "credit": 3,
        "status": status,
        "reason": f"{course_id} 的判定说明",
        "source_evidence": f"mock://curriculum/{course_id}（演示数据）",
    }
    payload.update(overrides)
    return MakeupTask(**payload)  # type: ignore[arg-type]


def _plan(**overrides: object) -> PlanResult:
    payload: dict[str, object] = {
        "status": "partially_feasible",
        "selected_classes": [{"course_id": "C1", "class_id": "C1-01"}],
        "changes": [],
        "risks": [],
        "unresolved": [],
        "objective_summary": "演示摘要",
    }
    payload.update(overrides)
    return PlanResult(**payload)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# 正常情况
# --------------------------------------------------------------------------------------


def test_full_context_produces_one_explanation_per_plan_and_task_entry() -> None:
    tasks = [
        _task("C1", "required"),
        _task("C2", "satisfied"),
    ]
    offerings = [_offering("C1", "C1-01"), _offering("C2", "C2-01")]
    plan = _plan(
        selected_classes=[
            {"course_id": "C1", "class_id": "C1-01"},
            {"course_id": "C2", "class_id": "C2-01"},
        ],
        changes=[
            {
                "course_id": "C1",
                "from_class": "C1-02",
                "to_class": "C1-01",
                "reason": "原教学班命中回避时段",
            }
        ],
        risks=[{"course_id": "C1", "level": "high", "reason": "剩余容量偏低"}],
        unresolved=[{"type": "manual_confirmation", "message": "学分差额待判定"}],
    )

    response = build_explanation(
        explanation_models.ExplanationRequest(
            plan_result=plan, makeup_tasks=tasks, course_offerings=offerings
        )
    )

    kinds = [item.kind for item in response.items]
    assert kinds.count(ItemKind.MAKEUP_TASK) == 2
    assert kinds.count(ItemKind.SELECTED_CLASS) == 2
    assert kinds.count(ItemKind.CHANGE) == 1
    assert kinds.count(ItemKind.RISK) == 1
    assert kinds.count(ItemKind.UNRESOLVED) == 1
    assert kinds.count(ItemKind.PLAN_STATUS) == 1

    # 每条解释都必须有强证据或明确的前提缺失说明
    for item in response.items:
        assert item.answer.strip() != ""
        assert item.strong_evidence or item.premise_evidence

    # 生成方式如实：未配置模型 ⇒ 规则模板，且声明里写明不是模型输出
    assert response.generation.generator_kind is GeneratorKind.RULE_TEMPLATE
    assert response.generation.model_configured is False
    assert "确定性规则模板" in response.generation.disclaimer
    assert all(
        item.generation.generator_kind is GeneratorKind.RULE_TEMPLATE for item in response.items
    )

    # 来源字段可追溯：每条 MakeupTask 解释都引用 status / reason / source_evidence
    makeup_items = [item for item in response.items if item.kind is ItemKind.MAKEUP_TASK]
    for item in makeup_items:
        fields = {reference.source_field for reference in item.strong_evidence}
        assert {"status", "reason", "source_evidence"} <= fields


def test_statuses_get_distinct_and_accurate_explanations() -> None:
    tasks = [
        _task("C1", "required"),
        _task("C2", "satisfied"),
        _task("C3", "manual_confirmation"),
        _task("C4", "possibly_equivalent"),
    ]

    response = build_explanation(
        explanation_models.ExplanationRequest(
            plan_result=_plan(selected_classes=[]), makeup_tasks=tasks
        )
    )

    by_course = {
        item.target_course_id: item
        for item in response.items
        if item.kind is ItemKind.MAKEUP_TASK
    }

    assert by_course["C1"].code == "makeup_status_required"
    assert by_course["C2"].code == "makeup_status_satisfied"
    assert by_course["C3"].code == "makeup_status_manual_confirmation"
    assert by_course["C4"].code == "makeup_status_possibly_equivalent"

    answers = {course: item.answer for course, item in by_course.items()}
    assert len(set(answers.values())) == 4

    # 「可能等价」不得被写成学校已批准
    assert "尚未" in answers["C4"]
    assert "认定" in answers["C4"]
    equivalent_confirmations = " ".join(
        requirement.reason for requirement in by_course["C4"].requires_human_confirmation
    )
    assert "人工确认" in equivalent_confirmations

    # 「已满足」必须提示不等于学校正式认定
    satisfied_confirmations = " ".join(
        requirement.reason for requirement in by_course["C2"].requires_human_confirmation
    )
    assert "正式" in satisfied_confirmations

    # 每个状态码不同 ⇒ 不会被错误确证为同一结论
    assert len({item.code for item in by_course.values()}) == 4


def test_evidence_quotes_original_field_values_verbatim() -> None:
    task = _task(
        "C1",
        "manual_confirmation",
        reason="新旧方案学分不一致（原 3 学分 / 新 2 学分）",
        source_evidence="mock://curriculum/manual/C1（演示数据，非真实判定结果）",
    )

    response = build_explanation(
        explanation_models.ExplanationRequest(plan_result=_plan(), makeup_tasks=[task])
    )
    item = next(i for i in response.items if i.kind is ItemKind.MAKEUP_TASK)

    values = {reference.source_field: reference.raw_value for reference in item.strong_evidence}
    assert values["reason"] == task.reason
    assert values["source_evidence"] == task.source_evidence
    assert task.reason in item.answer


def test_change_explanation_repeats_planner_reason_and_does_not_recompute_conflicts() -> None:
    reason = "原教学班为星期五 7-8 节，命中用户避开的时段"
    plan = _plan(
        changes=[
            {
                "course_id": "C1",
                "from_class": "C1-02",
                "to_class": "C1-01",
                "reason": reason,
            }
        ]
    )
    offerings = [_offering("C1", "C1-01"), _offering("C1", "C1-02")]

    response = build_explanation(
        explanation_models.ExplanationRequest(plan_result=plan, course_offerings=offerings)
    )
    item = next(i for i in response.items if i.kind is ItemKind.CHANGE)

    assert reason in item.answer
    assert "没有重新做冲突检测" in item.answer
    raw_values = [reference.raw_value for reference in item.strong_evidence]
    assert reason in raw_values


def test_risk_and_unresolved_are_quoted_not_interpreted() -> None:
    plan = _plan(
        selected_classes=[],
        risks=[{"course_id": None, "level": "low", "reason": "总学分低于上限"}],
        unresolved=[{"type": "missing_data", "message": "仅基于 Mock 教学班数据"}],
    )

    response = build_explanation(explanation_models.ExplanationRequest(plan_result=plan))
    risk = next(i for i in response.items if i.kind is ItemKind.RISK)
    unresolved = next(i for i in response.items if i.kind is ItemKind.UNRESOLVED)

    assert "总学分低于上限" in risk.answer
    assert "不补充、不推断其它风险类型" in risk.answer
    assert "missing_data" in unresolved.answer
    assert "不把未解决事项当作已确认结论" in unresolved.answer


# --------------------------------------------------------------------------------------
# 缺证据 / 空输入
# --------------------------------------------------------------------------------------


def test_missing_makeup_context_never_guesses_status() -> None:
    plan = _plan(selected_classes=[{"course_id": "C1", "class_id": "C1-01"}])

    response = build_explanation(
        explanation_models.ExplanationRequest(plan_result=plan, course_offerings=[])
    )

    item = next(i for i in response.items if i.kind is ItemKind.SELECTED_CLASS)
    assert item.code == "selected_class_without_makeup_context"
    assert "没有包含 Curriculum 的补修任务上下文" in item.answer

    # 明确标记「字段不存在」，而不是「值为空」
    absent = [reference for reference in item.strong_evidence if reference.source_field == "status"]
    assert absent and absent[0].raw_value == ""
    assert absent[0].kind.value == "absent"

    # 不得出现任何补修状态关键词
    for status_word in ("required", "satisfied", "possibly_equivalent", "manual_confirmation"):
        assert status_word not in item.answer

    assert any("未包含 MakeupTask 上下文" in warning for warning in response.warnings)


def test_empty_plan_result_still_explains_status_without_claiming_feasible() -> None:
    plan = _plan(selected_classes=[], status="infeasible")

    response = build_explanation(explanation_models.ExplanationRequest(plan_result=plan))
    status_item = next(i for i in response.items if i.kind is ItemKind.PLAN_STATUS)

    assert "不可行" in status_item.answer
    assert "本解释不重新求解" in status_item.answer
    assert status_item.requires_human_confirmation


def test_empty_lists_produce_cautious_explanation() -> None:
    plan = _plan(selected_classes=[], status="feasible")

    response = build_explanation(explanation_models.ExplanationRequest(plan_result=plan))
    status_item = next(i for i in response.items if i.kind is ItemKind.PLAN_STATUS)

    confirmations = " ".join(
        requirement.reason for requirement in status_item.requires_human_confirmation
    )
    assert "不构成" in confirmations


def test_offering_without_meetings_is_not_treated_as_conflict_free() -> None:
    plan = _plan(selected_classes=[{"course_id": "C1", "class_id": "C1-01"}])
    offerings = [_offering("C1", "C1-01", meetings=[])]

    response = build_explanation(
        explanation_models.ExplanationRequest(
            plan_result=plan,
            makeup_tasks=[_task("C1", "required")],
            course_offerings=offerings,
        )
    )
    item = next(i for i in response.items if i.kind is ItemKind.SELECTED_CLASS)

    assert "没有可用排课信息" in item.answer
    confirmations = " ".join(
        requirement.reason for requirement in item.requires_human_confirmation
    )
    assert "不存在时间冲突" in confirmations
    # 空 meetings **不得**被解释成"没有上课时间 / 异步 / 时间自由"
    assert "不表示无课" in item.answer or "不得据此推断" in item.answer
    assert "异步" in item.answer and "不表示" in item.answer or "不得据此推断" in item.answer


def test_change_referencing_missing_offering_is_flagged_not_filled_in() -> None:
    plan = _plan(
        changes=[
            {
                "course_id": "C1",
                "from_class": "C1-02",
                "to_class": "C1-01",
                "reason": "原教学班命中回避时段",
            }
        ]
    )
    # 上下文里只有新教学班，原教学班缺失
    response = build_explanation(
        explanation_models.ExplanationRequest(
            plan_result=plan,
            makeup_tasks=[_task("C1", "required")],
            course_offerings=[_offering("C1", "C1-01")],
        )
    )
    item = next(i for i in response.items if i.kind is ItemKind.CHANGE)

    assert any("C1/C1-02" in warning for warning in response.warnings)
    assert "未包含原教学班对象" in item.answer
    assert any(reference.kind.value == "absent" for reference in item.premise_evidence)
    # 不得凭空补出原教学班的排课信息
    assert "C1-02 教学班排课" not in item.answer


def test_unreferenced_selected_class_is_reported_in_warnings() -> None:
    plan = _plan(selected_classes=[{"course_id": "C9", "class_id": "C9-99"}])

    response = build_explanation(
        explanation_models.ExplanationRequest(
            plan_result=plan,
            makeup_tasks=[_task("C1", "required")],
            course_offerings=[_offering("C1", "C1-01")],
        )
    )

    assert any("C9/C9-99" in warning for warning in response.warnings)
    assert any("C9 没有对应的 MakeupTask" in warning for warning in response.warnings)


def test_duplicate_makeup_task_courses_are_reported_and_first_wins() -> None:
    plan = _plan(selected_classes=[])
    tasks = [_task("C1", "required"), _task("C1", "satisfied")]

    response = build_explanation(
        explanation_models.ExplanationRequest(plan_result=plan, makeup_tasks=tasks)
    )

    items = [i for i in response.items if i.kind is ItemKind.MAKEUP_TASK]
    assert len(items) == 1
    assert items[0].code == "makeup_status_required"
    assert any("重复课程号" in warning for warning in response.warnings)


def test_missing_source_evidence_and_prerequisites_are_marked_absent() -> None:
    task = MakeupTask(
        course_id="C1",
        course_name="课程 C1",
        credit=3,
        status="satisfied",
        reason=None,
        source_evidence=None,
        prerequisites=[],
    )

    response = build_explanation(
        explanation_models.ExplanationRequest(plan_result=_plan(), makeup_tasks=[task])
    )
    item = next(i for i in response.items if i.kind is ItemKind.MAKEUP_TASK)

    absent_fields = {
        reference.source_field
        for reference in item.strong_evidence + item.premise_evidence
        if reference.kind.value == "absent"
    }
    assert {"reason", "source_evidence", "prerequisites"} <= absent_fields

    confirmations = " ".join(
        requirement.reason for requirement in item.requires_human_confirmation
    )
    assert "无法复核" in confirmations
    assert "不存在先修要求" in confirmations or "没有先修课程声明" in confirmations


def test_long_text_is_truncated_with_explicit_marker() -> None:
    long_reason = "很长的判定说明" * 2000
    task = _task("C1", "required", reason=long_reason)

    response = build_explanation(
        explanation_models.ExplanationRequest(plan_result=_plan(), makeup_tasks=[task])
    )
    item = next(i for i in response.items if i.kind is ItemKind.MAKEUP_TASK)

    # 正文被截断（模型输出上限同样受此约束：模板文本是先决条件之一）
    assert len(item.answer) <= explanation_models.MAX_TEXT_LENGTH
    assert "原文已截断" in item.answer
    # 来源引用也有上限，不会把整份超长原文塞进响应
    reason_ref = next(
        reference for reference in item.strong_evidence if reference.source_field == "reason"
    )
    assert len(reason_ref.raw_value) <= explanation_models.MAX_RAW_VALUE_LENGTH
    assert item.answer.count("原文已截断") == 1


# --------------------------------------------------------------------------------------
# 只读保证
# --------------------------------------------------------------------------------------


def test_explanation_does_not_mutate_inputs() -> None:
    tasks = [_task("C1", "required")]
    offerings = [_offering("C1", "C1-01")]
    plan = _plan(
        selected_classes=[{"course_id": "C1", "class_id": "C1-01"}],
        changes=[{"course_id": "C1", "from_class": "C1-02", "to_class": "C1-01", "reason": "r"}],
        risks=[{"course_id": "C1", "level": "medium", "reason": "risk"}],
        unresolved=[{"type": "manual_confirmation", "message": "m"}],
    )

    before_plan = copy.deepcopy(plan.model_dump(mode="json"))
    before_tasks = copy.deepcopy([task.model_dump(mode="json") for task in tasks])
    before_offerings = copy.deepcopy([offering.model_dump(mode="json") for offering in offerings])
    digest_before = plan_digest(plan)

    response = build_explanation(
        explanation_models.ExplanationRequest(
            plan_result=plan, makeup_tasks=tasks, course_offerings=offerings
        )
    )

    assert plan.model_dump(mode="json") == before_plan
    assert [task.model_dump(mode="json") for task in tasks] == before_tasks
    assert [offering.model_dump(mode="json") for offering in offerings] == before_offerings

    # 响应暴露的指纹就是被解释方案的指纹
    assert response.plan_result_digest == digest_before
    assert response.source_summary.plan_result_digest == digest_before
    assert response.context_digest == build_explanation_facts(
        explanation_models.ExplanationRequest(
            plan_result=plan, makeup_tasks=tasks, course_offerings=offerings
        )
    ).context_digest


def test_explanation_package_never_imports_planning_or_mock_pipeline() -> None:
    forbidden = {
        "app.planner",
        "app.curriculum",
        "app.course_data",
        "app.services.mock_service",
        "app.api.mock",
        "app.integration",
        "app.services.planning_runtime",
        "requests",
        "httpx",
        "urllib.request",
    }

    package_dir = Path(inspect.getfile(explanation_service)).parent
    modules = [explanation_models, explanation_templates, explanation_service, explanation_api]

    for module in modules:
        tree = ast.parse(inspect.getsource(module))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)

        assert not (imports & forbidden), f"{module.__name__} 不应导入 {imports & forbidden}"

    assert package_dir.name == "explanation"


def test_explanation_module_does_not_touch_filesystem_or_network() -> None:
    for module in (
        explanation_models,
        explanation_templates,
        explanation_service,
        explanation_api,
    ):
        source = inspect.getsource(module)
        for banned in ("open(", "os.environ", "subprocess", "socket", "requests.get"):
            assert banned not in source, f"{module.__name__} 出现 {banned}"


# --------------------------------------------------------------------------------------
# 可选模型适配层：必须如实标注，失败即降级
# --------------------------------------------------------------------------------------


class _EchoAdapter:
    """合法适配器：把模板答案原样回传（通过事实绑定校验）。"""

    model_id = "test-echo"

    def complete(
        self, *, question: str, facts_answer: str, fact_catalog: tuple[str, ...]
    ) -> str:
        return f"{facts_answer}（由测试模型润色）"


class _HallucinatingAdapter:
    """非法适配器：编造学分与课程号，必须被事实绑定校验拦下。"""

    model_id = "test-hallucinating"

    def complete(
        self, *, question: str, facts_answer: str, fact_catalog: tuple[str, ...]
    ) -> str:
        return f"{facts_answer} 该课程为 99 学分，等价于课程 XX99999，已获学校批准。"


class _BrokenAdapter:
    model_id = "test-broken"

    def complete(
        self, *, question: str, facts_answer: str, fact_catalog: tuple[str, ...]
    ) -> str:
        raise RuntimeError("model service down")


def test_configured_model_is_marked_as_model_generated() -> None:
    request = explanation_models.ExplanationRequest(
        plan_result=_plan(), makeup_tasks=[_task("C1", "required")]
    )

    response = ExplanationService(model_adapter=_EchoAdapter()).explain(request)

    assert response.generation.generator_kind is GeneratorKind.MODEL
    assert response.generation.model_configured is True
    assert response.generation.model_id == "test-echo"
    assert response.generation.fallback_reason is None
    assert "AI 模型" in response.generation.disclaimer
    assert all(item.generation.generator_kind is GeneratorKind.MODEL for item in response.items)


def test_partially_model_generated_response_is_not_labelled_as_model() -> None:
    """只要有一条解释没通过校验，整体就不算"模型生成"（如实收口）。"""

    class PartiallyFailingAdapter:
        model_id = "test-partial"

        def __init__(self) -> None:
            self.calls = 0

        def complete(
            self, *, question: str, facts_answer: str, fact_catalog: tuple[str, ...]
        ) -> str:
            self.calls += 1
            if self.calls == 1:
                # 第一条故意引入事实目录之外的数量信息 ⇒ 校验必须拒绝
                return f"{facts_answer} 该课程为 42 学分。"
            return f"{facts_answer}（由测试模型润色）"

    request = explanation_models.ExplanationRequest(
        plan_result=_plan(), makeup_tasks=[_task("C1", "required")]
    )
    response = ExplanationService(model_adapter=PartiallyFailingAdapter()).explain(request)

    kinds = [item.generation.generator_kind for item in response.items]
    assert GeneratorKind.MODEL_UNAVAILABLE in kinds
    assert GeneratorKind.MODEL in kinds

    # 整体必须是降级（不能因为部分条目成功就宣称模型生成）
    assert response.generation.generator_kind is GeneratorKind.MODEL_UNAVAILABLE
    assert response.generation.fallback_reason is not None

    # 幻觉数字没有进入任何解释
    for item in response.items:
        assert "42 学分" not in item.answer


@pytest.mark.parametrize("adapter", [_HallucinatingAdapter(), _BrokenAdapter()])
def test_failed_model_degrades_to_template_and_says_so(adapter: object) -> None:
    request = explanation_models.ExplanationRequest(
        plan_result=_plan(), makeup_tasks=[_task("C1", "required")]
    )

    response = ExplanationService(model_adapter=adapter).explain(request)  # type: ignore[arg-type]

    assert response.generation.generator_kind is GeneratorKind.MODEL_UNAVAILABLE
    assert response.generation.fallback_reason is not None
    assert "降级" in response.generation.disclaimer
    assert "模型输出" in response.generation.disclaimer or "未通过" in response.generation.disclaimer

    # 模板文本可用，且幻觉内容没有被写进任何解释
    for item in response.items:
        assert item.generation.generator_kind is GeneratorKind.MODEL_UNAVAILABLE
        assert "99 学分" not in item.answer
        assert "XX99999" not in item.answer
        assert item.answer.strip() != ""


def test_model_output_validation_rejects_unbound_facts() -> None:
    from app.explanation.templates import TemplateDraft

    draft = TemplateDraft(title="t", answer="C1 需要补修，学分 3。")
    catalog = ("makeup_task=C1|status=required|credit=3", "PlanResult.status=partially_feasible")

    assert validate_model_answer(candidate="C1 需要补修，学分 3。", draft=draft, catalog=catalog)

    # 来源 URI 里的数字是标识符，不应被误判成编造的数量信息
    assert validate_model_answer(
        candidate="C1 需要补修，学分 3。依据 mock://curriculum/62001001（演示数据）",
        draft=draft,
        catalog=catalog + ("mock://curriculum/62001001（演示数据）",),
    )

    with pytest.raises(ModelAdapterError):
        validate_model_answer(candidate="C1 需要补修，学分 5。", draft=draft, catalog=catalog)

    with pytest.raises(ModelAdapterError):
        validate_model_answer(candidate="C9 需要补修，学分 3。", draft=draft, catalog=catalog)

    with pytest.raises(ModelAdapterError):
        validate_model_answer(candidate="与事实无关的答案。", draft=draft, catalog=catalog)

    with pytest.raises(ModelAdapterError):
        validate_model_answer(candidate=123, draft=draft, catalog=catalog)  # type: ignore[arg-type]


def test_try_model_answer_without_adapter_reports_reason() -> None:
    from app.explanation.templates import TemplateDraft

    result = try_model_answer(
        None, facts=build_explanation_facts(
            explanation_models.ExplanationRequest(plan_result=_plan())
        ), draft=TemplateDraft(title="t", answer="a")
    )

    assert result.usable is False
    assert result.reason == "未配置模型适配层"


# --------------------------------------------------------------------------------------
# API 层
# --------------------------------------------------------------------------------------


def _api_payload() -> dict[str, object]:
    return {
        "plan_result": {
            "status": "partially_feasible",
            "selected_classes": [{"course_id": "C1", "class_id": "C1-01"}],
            "changes": [],
            "risks": [],
            "unresolved": [],
        },
        "makeup_tasks": [
            {
                "course_id": "C1",
                "course_name": "课程 C1",
                "credit": 3,
                "status": "required",
                "reason": "新培养方案必修",
                "source_evidence": "mock://curriculum/C1（演示数据）",
            }
        ],
        "course_offerings": [
            {
                "course_id": "C1",
                "course_name": "课程 C1",
                "class_id": "C1-01",
                "semester": "2026-1",
                "meetings": [
                    {"weekday": 1, "start_section": 1, "end_section": 2, "weeks": [1, 2]}
                ],
                "data_source": "mock",
            }
        ],
    }


def test_explanation_endpoint_returns_rule_based_explanations(client: TestClient) -> None:
    response = client.post(EXPLANATION_PATH, json=_api_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == explanation_models.EXPLANATION_CONTRACT_VERSION
    assert body["generation"]["generator_kind"] == "rule_based_template"
    assert body["generation"]["model_configured"] is False
    assert body["source_summary"]["contains_mock_marker"] is True
    assert len(body["plan_result_digest"]) == 64
    assert any(item["kind"] == "makeup_task" for item in body["items"])
    # 解释通道不是 Mock 通道：不得带 X-Data-Source 标记
    assert "X-Data-Source" not in response.headers


def test_explanation_endpoint_minimal_body_has_no_context(client: TestClient) -> None:
    response = client.post(
        EXPLANATION_PATH,
        json={
            "plan_result": {
                "status": "infeasible",
                "selected_classes": [],
                "changes": [],
                "risks": [],
                "unresolved": [],
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_summary"]["makeup_task_count"] == 0
    assert body["generation"]["generator_kind"] == "rule_based_template"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty"),
        pytest.param({"plan_result": {"status": "unknown"}}, id="bad-status"),
        pytest.param(
            {**_api_payload(), "student_id": "SHOULD-NOT-BE-ACCEPTED"}, id="extra-field"
        ),
        pytest.param(
            {**_api_payload(), "plan_result": {"status": "feasible"}}, id="missing-lists"
        ),
    ],
)
def test_explanation_endpoint_rejects_malformed_requests(
    client: TestClient, payload: dict[str, object]
) -> None:
    response = client.post(EXPLANATION_PATH, json=payload)

    assert response.status_code == 422
    assert "X-Data-Source" not in response.headers


def test_explanation_endpoint_rejects_oversized_context(client: TestClient) -> None:
    oversized = {
        "plan_result": _api_payload()["plan_result"],
        "makeup_tasks": [
            {
                "course_id": f"C{index}",
                "course_name": f"课程 {index}",
                "credit": 3,
                "status": "required",
            }
            for index in range(explanation_service.MAX_CONTEXT_ITEMS + 1)
        ],
    }

    response = client.post(EXPLANATION_PATH, json=oversized)

    assert response.status_code == 422
    assert "X-Data-Source" not in response.headers


def test_explanation_endpoint_is_registered_alongside_existing_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert EXPLANATION_PATH in paths
    # 既有路径未被改动
    assert "/api/v1/plan" in paths
    assert "/api/v1/mock/demo" in paths
    assert "/api/v1/completed-courses/import" in paths


def test_explanation_matches_mock_demo_case_without_guessing(
    mock_data_dir: Path,
) -> None:
    """用仓库真实 Mock 数据跑一遍：不一致处必须进 warnings，而不是被猜出来。"""

    payload = {
        "plan_result": mock_service.load_plan_result().model_dump(mode="json"),
        "makeup_tasks": [
            task.model_dump(mode="json") for task in mock_service.load_makeup_tasks()
        ],
        "course_offerings": [
            offering.model_dump(mode="json") for offering in mock_service.load_course_offerings()
        ],
    }

    response = build_explanation(explanation_models.ExplanationRequest(**payload))  # type: ignore[arg-type]

    assert response.source_summary.contains_mock_marker is True
    assert response.source_summary.course_offering_count == 9

    # Mock 数据本身是自洽的（4 个选中教学班都能在 9 个教学班上下文里找到），
    # 所以这里**不应**出现"找不到上下文"的警告；一旦出现，说明解释开始自行猜测。
    assert response.warnings == []

    change_item = next(i for i in response.items if i.kind is ItemKind.CHANGE)
    assert "Planner 给出的调整原因原文" in change_item.answer

    # 没有任何解释声称课程等价已认定
    for item in response.items:
        assert "已获学校批准" not in item.answer
        assert "等价认定完成" not in item.answer


def test_explanation_does_not_leak_transcript_like_fields() -> None:
    """解释请求模型不接受任何成绩 / 身份字段（结构上就不可能夹带）。"""

    schema = explanation_models.ExplanationRequest.model_json_schema()
    serialized = json.dumps(schema, ensure_ascii=False).lower()

    for banned in ("student_id", "score", "grade", "id_card", "gpa"):
        assert banned not in serialized

    task_fields = set(MakeupTask.model_fields)
    assert not (task_fields & {"score", "grade", "student_id"})
