"""解释服务门面：构建事实平面 → 逐条生成解释 → 校验未被改写。

## 只读保证

`build_explanation()` 在任何情况下都：

1. **不修改**调用方传入的 `PlanResult` / `MakeupTask` / `CourseOffering` 对象
   （只在末尾重新计算摘要，若与入口摘要不一致即抛错）；
2. **不调用** Planner / Curriculum / Course Data / Mock 通道；
3. **不产生**任何新的业务结论（补修判定、等价关系、先修边、冲突结论都不新增）。

> ⚠️ 返回的 `plan_result_digest` 就是「被解释的那份方案」的指纹：
> 调用方可以据此确认解释没有偷换方案，也不会改写方案。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from app.explanation.adapter import (
    ExplanationModelAdapter,
    try_model_answer,
)
from app.explanation.models import (
    ConfirmationRequirement,
    EvidenceReference,
    ExplanationFacts,
    ExplanationGeneration,
    ExplanationItem,
    ExplanationRequest,
    ExplanationResponse,
    GeneratorKind,
    ItemKind,
    SourceSummary,
)
from app.explanation.templates import (
    TemplateDraft,
    change_draft,
    makeup_task_draft,
    missing_makeup_context_draft,
    plan_status_draft,
    risk_draft,
    selected_class_draft,
    unresolved_draft,
)
from app.models.contracts import CourseOffering, MakeupTask, PlanResult

#: 请求中允许的最大补修任务数 / 教学班数（防止无界请求；超出即 422）。
MAX_CONTEXT_ITEMS = 500

_RULE_DISCLAIMER = (
    "本解释由**确定性规则模板**生成：文本只由已有结构化字段拼出，"
    "没有调用任何 AI 模型（未配置模型服务）。"
)

_MODEL_DISCLAIMER = (
    "本解释的文本部分由已配置的**AI 模型**润色生成，"
    "但内容被限制在给定事实目录内（已通过事实绑定校验）；"
    "解释不改变任何规划结论。"
)

_FALLBACK_DISCLAIMER = (
    "已配置的 AI 模型本次**未被采用**（未通过事实绑定校验或调用失败），"
    "本条解释已降级为**确定性规则模板**，不是模型输出。"
)


def canonical_json(payload: object) -> str:
    """稳定序列化：用于摘要计算（键排序、无空白、枚举取 `value`）。"""

    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")  # type: ignore[union-attr]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_digest(plan_result: PlanResult) -> str:
    """`PlanResult` 的内容指纹。"""

    return _sha256(canonical_json(plan_result))


def context_digest(*, makeup_tasks: Sequence[MakeupTask], offerings: Sequence[CourseOffering]) -> str:
    """解释上下文的指纹（补修任务 + 教学班，顺序敏感）。"""

    return _sha256(
        canonical_json(
            {
                "makeup_tasks": [task.model_dump(mode="json") for task in makeup_tasks],
                "course_offerings": [offering.model_dump(mode="json") for offering in offerings],
            }
        )
    )


_MOCK_MARKERS = ("mock://", "演示数据", "非真实")


def _contains_mock_marker(makeup_tasks: Sequence[MakeupTask]) -> bool:
    for task in makeup_tasks:
        if task.source_evidence and any(marker in task.source_evidence for marker in _MOCK_MARKERS):
            return True
    return False


def _source_summary(
    *, facts_plan_digest: str, ctx_digest: str, makeup_tasks: Sequence[MakeupTask],
    offerings: Sequence[CourseOffering],
) -> SourceSummary:
    notes: list[str] = []
    contains_mock = _contains_mock_marker(makeup_tasks)
    contains_real = any(offering.data_source.value == "real" for offering in offerings)

    if contains_mock and contains_real:
        notes.append(
            "本次解释同时引用了 Mock 与 Real 来源：Mock 条目仅用于演示，"
            "不得作为真实教务结论使用。"
        )
    elif contains_mock:
        notes.append("本次解释引用的补修任务包含演示数据标记（Mock）。")
    elif makeup_tasks:
        notes.append("本次解释引用的补修任务未出现演示数据标记。")

    if offerings and not contains_real:
        notes.append("本次解释引用的教学班全部为 Mock 来源。")
    if not offerings:
        notes.append("本次解释没有收到教学班上下文。")

    return SourceSummary(
        plan_result_digest=facts_plan_digest,
        context_digest=ctx_digest,
        makeup_task_count=len(makeup_tasks),
        course_offering_count=len(offerings),
        contains_mock_marker=contains_mock,
        contains_real_offering=contains_real,
        notes=notes,
    )


def build_explanation_facts(request: ExplanationRequest) -> ExplanationFacts:
    """把请求整理成事实平面（不做任何业务推断）。"""

    makeup_tasks = list(request.makeup_tasks or [])
    offerings = list(request.course_offerings or [])

    if len(makeup_tasks) > MAX_CONTEXT_ITEMS or len(offerings) > MAX_CONTEXT_ITEMS:
        raise ExplanationContextTooLarge(
            f"解释上下文条目过多（上限 {MAX_CONTEXT_ITEMS} 条 / 类）。"
        )

    plan_fingerprint = plan_digest(request.plan_result)
    ctx_fingerprint = context_digest(makeup_tasks=makeup_tasks, offerings=offerings)

    return ExplanationFacts(
        plan_result=request.plan_result,
        makeup_tasks=makeup_tasks,
        course_offerings=offerings,
        makeup_tasks_provided=request.makeup_tasks is not None,
        course_offerings_provided=request.course_offerings is not None,
        plan_result_digest=plan_fingerprint,
        context_digest=ctx_fingerprint,
        source_summary=_source_summary(
            facts_plan_digest=plan_fingerprint,
            ctx_digest=ctx_fingerprint,
            makeup_tasks=makeup_tasks,
            offerings=offerings,
        ),
    )


class ExplanationContextTooLarge(ValueError):
    """解释上下文超过允许规模。"""


@dataclass(frozen=True, slots=True)
class _Index:
    """事实索引：只做「按标识查找」，不做任何推断。"""

    tasks_by_course: dict[str, MakeupTask]
    offerings_by_key: dict[tuple[str, str], CourseOffering]
    offerings_by_course: dict[str, tuple[CourseOffering, ...]]
    duplicate_course_tasks: tuple[str, ...]


def _index(facts: ExplanationFacts) -> _Index:
    tasks_by_course: dict[str, MakeupTask] = {}
    duplicates: list[str] = []
    for task in facts.makeup_tasks:
        if task.course_id in tasks_by_course:
            duplicates.append(task.course_id)
            continue
        tasks_by_course[task.course_id] = task

    offerings_by_key: dict[tuple[str, str], CourseOffering] = {}
    by_course: dict[str, list[CourseOffering]] = {}
    for offering in facts.course_offerings:
        offerings_by_key.setdefault((offering.course_id, offering.class_id), offering)
        by_course.setdefault(offering.course_id, []).append(offering)

    return _Index(
        tasks_by_course=tasks_by_course,
        offerings_by_key=offerings_by_key,
        offerings_by_course={course: tuple(items) for course, items in by_course.items()},
        duplicate_course_tasks=tuple(duplicates),
    )


def _generation(
    *, adapter: ExplanationModelAdapter | None, used_model: bool, fallback_reason: str | None
) -> ExplanationGeneration:
    if used_model:
        kind = GeneratorKind.MODEL
        disclaimer = _MODEL_DISCLAIMER
    elif fallback_reason is not None:
        kind = GeneratorKind.MODEL_UNAVAILABLE
        disclaimer = _FALLBACK_DISCLAIMER
    else:
        kind = GeneratorKind.RULE_TEMPLATE
        disclaimer = _RULE_DISCLAIMER

    return ExplanationGeneration(
        generator_kind=kind,
        model_configured=adapter is not None,
        model_id=getattr(adapter, "model_id", None) if adapter is not None else None,
        fallback_reason=fallback_reason,
        disclaimer=disclaimer,
    )


def _item(
    *,
    item_id: str,
    kind: ItemKind,
    code: str,
    draft: TemplateDraft,
    course_id: str | None = None,
    class_id: str | None = None,
    adapter: ExplanationModelAdapter | None,
    facts: ExplanationFacts,
) -> ExplanationItem:
    """把模板草稿（或通过校验的模型输出）封装成解释条目。"""

    fallback_reason: str | None = None
    answer = draft.answer
    used_model = False

    if adapter is not None:
        result = try_model_answer(adapter, facts=facts, draft=draft)
        if result.usable and result.text is not None:
            answer = result.text
            used_model = True
        else:
            fallback_reason = result.reason

    return ExplanationItem(
        item_id=item_id,
        kind=kind,
        code=code,
        target_course_id=course_id,
        target_class_id=class_id,
        title=draft.title,
        answer=answer,
        strong_evidence=list(draft.strong_evidence),
        premise_evidence=list(draft.premise_evidence),
        requires_human_confirmation=list(draft.confirmations),
        generation=_generation(
            adapter=adapter, used_model=used_model, fallback_reason=fallback_reason
        ),
    )


class ExplanationService:
    """解释服务：默认纯规则模板；可选注入模型适配层。"""

    def __init__(self, *, model_adapter: ExplanationModelAdapter | None = None) -> None:
        self._model_adapter = model_adapter

    @property
    def model_configured(self) -> bool:
        return self._model_adapter is not None

    def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        """生成解释响应；**只读**且不产生任何新业务结论。"""

        facts = build_explanation_facts(request)
        index = _index(facts)
        adapter = self._model_adapter

        warnings: list[str] = []
        if facts.makeup_tasks_provided and index.duplicate_course_tasks:
            warnings.append(
                "上下文里存在重复课程号的 MakeupTask，解释只采用首次出现的一条："
                + "、".join(sorted(set(index.duplicate_course_tasks)))
            )
        if not facts.makeup_tasks_provided:
            warnings.append(
                "请求未包含 MakeupTask 上下文：补修判定类解释会明确标记「无法追溯」，"
                "不会推测判定状态。"
            )
        if not facts.course_offerings_provided:
            warnings.append(
                "请求未包含 CourseOffering 上下文：教学班排课信息无法追溯。"
            )

        items: list[ExplanationItem] = []

        plan_item, plan_draft = self._plan_status_item(facts)
        items.append(
            _item(
                item_id=plan_item,
                kind=ItemKind.PLAN_STATUS,
                code="plan_status_overview",
                draft=plan_draft,
                adapter=adapter,
                facts=facts,
            )
        )

        # ⚠️ 只解释**去重后**的补修任务（重复课程号已进 warnings），
        #    避免同一条任务被解释两次。
        for task in facts.makeup_tasks:
            if index.tasks_by_course.get(task.course_id) is not task:
                continue
            offering = self._selected_offering_for(index, facts, task.course_id)
            items.append(
                _item(
                    item_id=f"makeup_task:{task.course_id}",
                    kind=ItemKind.MAKEUP_TASK,
                    code=f"makeup_status_{task.status.value}",
                    draft=makeup_task_draft(facts, task, offering=offering),
                    course_id=task.course_id,
                    adapter=adapter,
                    facts=facts,
                )
            )

        for selected in facts.plan_result.selected_classes:
            task = index.tasks_by_course.get(selected.course_id)
            offering = index.offerings_by_key.get((selected.course_id, selected.class_id))
            if offering is None:
                warnings.append(
                    f"方案中的教学班 {selected.course_id}/{selected.class_id} "
                    "不在解释上下文的教学班列表中。"
                )
            if task is None and facts.makeup_tasks_provided:
                warnings.append(
                    f"方案中的课程 {selected.course_id} 没有对应的 MakeupTask 上下文。"
                )
            if task is None:
                draft = missing_makeup_context_draft(selected.course_id, offering=offering)
                code = "selected_class_without_makeup_context"
            else:
                draft = selected_class_draft(
                    course_id=selected.course_id,
                    class_id=selected.class_id,
                    task=task,
                    offering=offering,
                )
                code = "selected_class_evidence"
            items.append(
                _item(
                    item_id=f"selected_class:{selected.course_id}:{selected.class_id}",
                    kind=ItemKind.SELECTED_CLASS,
                    code=code,
                    draft=draft,
                    course_id=selected.course_id,
                    class_id=selected.class_id,
                    adapter=adapter,
                    facts=facts,
                )
            )

        for position, change in enumerate(facts.plan_result.changes):
            from_offering = (
                index.offerings_by_key.get((change.course_id, change.from_class))
                if change.from_class
                else None
            )
            to_offering = (
                index.offerings_by_key.get((change.course_id, change.to_class))
                if change.to_class
                else None
            )
            if change.from_class and from_offering is None:
                warnings.append(
                    f"调班记录的原教学班 {change.course_id}/{change.from_class} "
                    "不在解释上下文的教学班列表中。"
                )
            if change.to_class and to_offering is None:
                warnings.append(
                    f"调班记录的新教学班 {change.course_id}/{change.to_class} "
                    "不在解释上下文的教学班列表中。"
                )
            items.append(
                _item(
                    item_id=f"change:{change.course_id}:{position}",
                    kind=ItemKind.CHANGE,
                    code="change_reason_from_planner",
                    draft=change_draft(
                        course_id=change.course_id,
                        from_class=change.from_class,
                        to_class=change.to_class,
                        reason=change.reason,
                        from_offering=from_offering,
                        to_offering=to_offering,
                    ),
                    course_id=change.course_id,
                    class_id=change.to_class,
                    adapter=adapter,
                    facts=facts,
                )
            )

        for position, risk in enumerate(facts.plan_result.risks):
            items.append(
                _item(
                    item_id=f"risk:{risk.course_id or 'global'}:{position}",
                    kind=ItemKind.RISK,
                    code=f"risk_{risk.level.value}",
                    draft=risk_draft(
                        course_id=risk.course_id, level=risk.level, reason=risk.reason
                    ),
                    course_id=risk.course_id,
                    adapter=adapter,
                    facts=facts,
                )
            )

        for position, unresolved in enumerate(facts.plan_result.unresolved):
            items.append(
                _item(
                    item_id=f"unresolved:{position}",
                    kind=ItemKind.UNRESOLVED,
                    code="unresolved_item",
                    draft=unresolved_draft(item=unresolved),
                    adapter=adapter,
                    facts=facts,
                )
            )

        # 只读保证：重算摘要，任何不一致都说明输入被改写过。
        if plan_digest(facts.plan_result) != facts.plan_result_digest:
            raise ExplanationMutationDetected("解释过程中 PlanResult 被改写，已中止输出。")

        generation = self._response_generation(items, adapter)

        return ExplanationResponse(
            plan_result_digest=facts.plan_result_digest,
            context_digest=facts.context_digest,
            generation=generation,
            source_summary=facts.source_summary,
            warnings=_dedupe(warnings),
            items=items,
        )

    def _plan_status_item(self, facts: ExplanationFacts) -> tuple[str, TemplateDraft]:
        return (
            "plan_status",
            plan_status_draft(
                result=facts.plan_result,
                has_unresolved=bool(facts.plan_result.unresolved),
                has_high_risk=any(risk.level.value == "high" for risk in facts.plan_result.risks),
            ),
        )

    def _response_generation(
        self, items: Sequence[ExplanationItem], adapter: ExplanationModelAdapter | None
    ) -> ExplanationGeneration:
        """整体生成方式：只有**全部**条目都用了模型，才算模型生成。"""

        model_items = sum(
            1 for item in items if item.generation.generator_kind is GeneratorKind.MODEL
        )
        failure = next(
            (
                item.generation.fallback_reason
                for item in items
                if item.generation.generator_kind is GeneratorKind.MODEL_UNAVAILABLE
                and item.generation.fallback_reason
            ),
            None,
        )

        if adapter is not None and model_items == len(items) and items:
            return _generation(adapter=adapter, used_model=True, fallback_reason=None)
        if adapter is not None and failure is not None:
            return _generation(adapter=adapter, used_model=False, fallback_reason=failure)
        return _generation(adapter=adapter, used_model=False, fallback_reason=None)

    @staticmethod
    def _selected_offering_for(
        index: _Index, facts: ExplanationFacts, course_id: str
    ) -> CourseOffering | None:
        """该课程在方案里**被选中**的教学班（只读查找，找不到就返回 None）。

        ⚠️ 只按 `PlanResult.selected_classes` 查找：本模块不做「哪个班更合适」的判断。
        """

        for selected in facts.plan_result.selected_classes:
            if selected.course_id == course_id:
                return index.offerings_by_key.get((selected.course_id, selected.class_id))
        return None


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


class ExplanationMutationDetected(RuntimeError):
    """解释过程检测到输入被改写（只读保证被破坏）。"""


def build_explanation(
    request: ExplanationRequest, *, model_adapter: ExplanationModelAdapter | None = None
) -> ExplanationResponse:
    """便捷入口：无状态地构建一次解释响应。"""

    return ExplanationService(model_adapter=model_adapter).explain(request)
