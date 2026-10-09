"""确定性解释模板。

## 本文件的硬规则

1. **模板只能复述事实**：所有文本都由 `ExplanationFacts` 中的字段拼出，
   不新增任何课程 / 学期 / 学分 / 时间 / 先修 / 等价关系；
2. **不推断 Planner 内部理由**：调班原因只复述 `changes[].reason` 原文，
   本模块不做冲突检测，也不声称某班「必然冲突」；
3. **不确证未知**：没有来源的关系一律进 `requires_human_confirmation`；
4. **不把「可能等价」说成学校已批准**：`possibly_equivalent` 的语义严格按
   `MakeupTask.status` 的字面含义表达，等价认定永远列为待人工确认。

模板函数只接受已经构建好的 `ExplanationFacts` 与一条目标记录，返回纯数据
（`TemplateDraft`），不接触网络、不读文件、不写状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from app.explanation.models import (
    MAX_RAW_VALUE_LENGTH,
    MAX_TEXT_LENGTH,
    QUOTED_FIELD_LIMIT,
    TRUNCATION_MARKER,
    ConfirmationRequirement,
    EvidenceKind,
    EvidenceReference,
    EvidenceStrength,
    ExplanationFacts,
)
from app.models.contracts import (
    CourseOffering,
    MakeupStatus,
    MakeupTask,
    PlanResult,
    RiskLevel,
    Unresolved,
)

#: 缺少 Curriculum 上下文时的统一说法（不得猜任务状态）。
_MISSING_MAKEUP_CONTEXT: Final[str] = (
    "本次解释请求没有包含 Curriculum 的补修任务上下文（MakeupTask），"
    "因此这条课程只能追溯 Planner 已给出的结果，无法说明它的补修判定依据。"
)

_MAKEUP_STATUS_TEXT: Final[dict[MakeupStatus, str]] = {
    MakeupStatus.REQUIRED: "按目标培养方案要求，这门课被判定为需要补修。",
    MakeupStatus.POSSIBLY_EQUIVALENT: (
        "这门课被判定为「可能等价」：系统只提出候选关系，"
        "**尚未**获得课程等价认定。"
    ),
    MakeupStatus.MANUAL_CONFIRMATION: "这门课被判定为需要人工确认，系统没有给出最终结论。",
    MakeupStatus.SATISFIED: "这门课被判定为已满足，系统不把它列入补修范围。",
}

_PLAN_STATUS_TEXT: Final[dict[str, str]] = {
    "feasible": "Planner 判定该方案整体可行。",
    "partially_feasible": "Planner 判定该方案仅部分可行：存在未能完全满足的条件。",
    "infeasible": "Planner 判定该方案不可行。",
}

_RISK_LEVEL_TEXT: Final[dict[RiskLevel, str]] = {
    RiskLevel.HIGH: "高",
    RiskLevel.MEDIUM: "中",
    RiskLevel.LOW: "低",
}


#: 文本被截断时追加的**唯一**标记。
#: ⚠️ 字段级裁剪与正文级裁剪必须使用同一个标记，否则「同一句话被截两次」
#: 会产生两个不同标记，破坏"原始取值可核对"的语义。
_TRUNCATION_MARKER: Final[str] = TRUNCATION_MARKER


def _clip(text: str, limit: int = MAX_TEXT_LENGTH) -> str:
    """截断过长文本；显式给出截断标记，不静默丢弃。"""

    if len(text) <= limit:
        return text
    return f"{text[:limit]}{_TRUNCATION_MARKER}"


#: 单条**来源字段**在正文中被引用的长度上限。
#: ⚠️ 必须显著小于 `MAX_TEXT_LENGTH`：正文最后还要整体裁剪一次，
#: 若来源字段独自占满上限，最终文本会因追加截断标记而超长。
_QUOTED_FIELD_LIMIT: Final[int] = QUOTED_FIELD_LIMIT


def quote_field_text(text: str) -> str:
    """引用来源字段原文（超长时截断，并**当场**标注截断标记）。

    截断标记在此处就加上，正文层的整体裁剪通常不会再触发，
    因此「引用被截断」与「整段正文被截断」不会互相混淆。

    ⚠️ 事实目录（`adapter.fact_catalog`）必须对同一字段调用本函数，
    否则模型看到的「事实」会比模板实际引用的原文更长。
    """

    if len(text) <= _QUOTED_FIELD_LIMIT:
        return text
    return f"{text[:_QUOTED_FIELD_LIMIT]}{_TRUNCATION_MARKER}"


#: 内部别名，保持模板代码简短。
_quote = quote_field_text


def _raw(value: object, limit: int = MAX_RAW_VALUE_LENGTH) -> str:
    """把来源字段的原始取值转成可展示片段（不改写语义，超长则截断并标注）。

    ⚠️ 事实目录（`adapter.fact_catalog`）在引用长文本字段时必须使用 `_quote()`，
    两者对同一字段的取值必须一致，否则「事实」与实际引用的原文会不一致。
    """

    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}{_TRUNCATION_MARKER}"


@dataclass(frozen=True, slots=True)
class TemplateDraft:
    """模板产出：结构化事实 + 事实绑定的文本。"""

    title: str
    answer: str
    strong_evidence: tuple[EvidenceReference, ...] = ()
    premise_evidence: tuple[EvidenceReference, ...] = ()
    confirmations: tuple[ConfirmationRequirement, ...] = ()
    extra_facts: tuple[str, ...] = field(default=())


def _status_evidence(task: MakeupTask) -> EvidenceReference:
    return EvidenceReference(
        kind=EvidenceKind.CONFIRMED_RULE,
        strength=EvidenceStrength.CONFIRMED,
        source_object="MakeupTask",
        source_field="status",
        raw_value=_raw(task.status.value),
        note="Curriculum 模块输出的判定状态；本解释不改写该判定。",
    )


def _source_evidence_reference(task: MakeupTask) -> EvidenceReference:
    """Curriculum 给出的材料来源字段；缺失即 `absent`，绝不补齐。"""

    if task.source_evidence is None or not task.source_evidence.strip():
        return EvidenceReference(
            kind=EvidenceKind.ABSENT,
            strength=EvidenceStrength.ABSENT,
            source_object="MakeupTask",
            source_field="source_evidence",
            raw_value="",
            note="该补修任务没有提供材料来源字段，无法说明判定依据来自哪份材料。",
        )

    return EvidenceReference(
        kind=EvidenceKind.CONFIRMED_RULE,
        strength=EvidenceStrength.CONFIRMED,
        source_object="MakeupTask",
        source_field="source_evidence",
        raw_value=quote_field_text(task.source_evidence),
        note="Curriculum 声明的判定材料来源；其真实性由 Curriculum 负责。",
    )


def _reason_reference(task: MakeupTask) -> EvidenceReference:
    if task.reason is None or not task.reason.strip():
        return EvidenceReference(
            kind=EvidenceKind.ABSENT,
            strength=EvidenceStrength.ABSENT,
            source_object="MakeupTask",
            source_field="reason",
            raw_value="",
            note="该补修任务没有提供判定说明字段。",
        )

    return EvidenceReference(
        kind=EvidenceKind.CONFIRMED_RULE,
        strength=EvidenceStrength.CONFIRMED,
        source_object="MakeupTask",
        source_field="reason",
        raw_value=quote_field_text(task.reason),
        note="Curriculum 给出的判定说明原文。",
    )


def _prerequisite_references(task: MakeupTask) -> tuple[EvidenceReference, ...]:
    if not task.prerequisites:
        return (
            EvidenceReference(
                kind=EvidenceKind.ABSENT,
                strength=EvidenceStrength.ABSENT,
                source_object="MakeupTask",
                source_field="prerequisites",
                raw_value="",
                note="该补修任务没有声明先修课程；这不等于确认「没有先修要求」。",
            ),
        )

    return tuple(
        EvidenceReference(
            kind=EvidenceKind.CONFIRMED_RULE,
            strength=EvidenceStrength.PARTIAL,
            source_object="MakeupTask",
            source_field="prerequisites",
            raw_value=_raw(course_id),
            note=(
                "Curriculum 声明的先修课程号；本解释只原样转述，"
                "不新增、不猜测、不重写任何先修边。"
            ),
        )
        for course_id in task.prerequisites
    )


def _offering_reference(offering: CourseOffering) -> EvidenceReference:
    return EvidenceReference(
        kind=EvidenceKind.SYSTEM_SUGGESTION,
        strength=EvidenceStrength.CONFIRMED,
        source_object="CourseOffering",
        source_field="meetings",
        raw_value=quote_field_text(_meetings_text(offering)),
        note="Course Data 提供的教学班排课信息，用于核对被选中教学班的实际时间。",
    )


def _meetings_text(offering: CourseOffering) -> str:
    """把 `meetings[]` 转成中性文本；空数组**不得**被解释成「无课」或「无冲突」。"""

    if not offering.meetings:
        return "当前来源快照没有可用排课信息（不得据此推断为无课、异步、时间自由或不存在冲突）"

    return "；".join(
        f"周{meeting.weekday} {meeting.start_section}-{meeting.end_section} 节 "
        f"第{'/'.join(str(week) for week in meeting.weeks)}周"
        f"{f' {meeting.campus}' if meeting.campus else ''}"
        f"{f' {meeting.classroom}' if meeting.classroom else ''}"
        for meeting in offering.meetings
    )


def makeup_task_draft(
    facts: ExplanationFacts, task: MakeupTask, *, offering: CourseOffering | None
) -> TemplateDraft:
    """解释一条 `MakeupTask` 的判定状态（satisfied / required / manual_confirmation / ...）。"""

    parts = [_MAKEUP_STATUS_TEXT[task.status]]

    if task.reason:
        parts.append(f"Curriculum 给出的判定说明：{_quote(task.reason)}")

    if task.source_evidence:
        parts.append(f"判定依据材料：{_quote(task.source_evidence)}")

    if task.recommended_semester is not None:
        parts.append(f"建议安排在第 {task.recommended_semester} 学期。")
    if task.deadline_semester is not None:
        parts.append(f"最迟需在第 {task.deadline_semester} 学期完成。")

    if task.prerequisites:
        parts.append(
            "Curriculum 声明的先修课程：" + "、".join(task.prerequisites) + "（本解释不新增或改写先修关系）。"
        )

    if offering is not None:
        parts.append(f"当前方案选中的教学班排课：{_meetings_text(offering)}")

    confirmations: list[ConfirmationRequirement] = []

    if task.status is MakeupStatus.POSSIBLY_EQUIVALENT:
        confirmations.append(
            ConfirmationRequirement(
                reason=(
                    "「可能等价」只是待核对的候选关系，系统没有认定课程等价；"
                    "是否互认需要教务 / 人工确认。"
                ),
                evidence=_status_evidence(task),
            )
        )
    elif task.status is MakeupStatus.MANUAL_CONFIRMATION:
        confirmations.append(
            ConfirmationRequirement(
                reason="该判定本身要求人工确认，本解释不代替人工给出结论。",
                evidence=_status_evidence(task),
            )
        )
    elif task.status is MakeupStatus.SATISFIED:
        confirmations.append(
            ConfirmationRequirement(
                reason=(
                    "「已满足」来自现有记录的判定，**不等于**学校已完成正式课程认定；"
                    "正式认定仍以教务审批为准。"
                ),
                evidence=_status_evidence(task),
            )
        )

    if not task.source_evidence or not task.source_evidence.strip():
        confirmations.append(
            ConfirmationRequirement(
                reason="该判定没有提供来源材料，无法复核其依据。",
                evidence=_source_evidence_reference(task),
            )
        )

    if not task.prerequisites:
        confirmations.append(
            ConfirmationRequirement(
                reason="没有先修课程声明时，不能据此确认「不存在先修要求」。",
                evidence=_prerequisite_references(task)[0],
            )
        )

    strong = [_status_evidence(task), _reason_reference(task), _source_evidence_reference(task)]
    premise = list(_prerequisite_references(task))
    if offering is not None:
        premise.append(_offering_reference(offering))

    return TemplateDraft(
        title=f"{task.course_name}（{task.course_id}）为什么是这个补修判定",
        answer=_clip(" ".join(parts)),
        strong_evidence=tuple(strong),
        premise_evidence=tuple(premise),
        confirmations=tuple(confirmations),
        extra_facts=(f"MakeupTask.status = {task.status.value}",),
    )


def missing_makeup_context_draft(course_id: str, *, offering: CourseOffering | None) -> TemplateDraft:
    """解释请求缺少 Curriculum 上下文时的**如实**说明。"""

    parts = [_MISSING_MAKEUP_CONTEXT]
    if offering is not None:
        parts.append(f"当前方案选中的教学班排课：{_meetings_text(offering)}")

    absent = EvidenceReference(
        kind=EvidenceKind.ABSENT,
        strength=EvidenceStrength.ABSENT,
        source_object="MakeupTask",
        source_field="status",
        raw_value="",
        note="请求中没有提供该课程的 MakeupTask，因此补修判定无法追溯。",
    )

    premise = []
    if offering is not None:
        premise.append(_offering_reference(offering))

    return TemplateDraft(
        title=f"{course_id} 的补修判定依据",
        answer=_clip(" ".join(parts)),
        strong_evidence=(absent,),
        premise_evidence=tuple(premise),
        confirmations=(
            ConfirmationRequirement(
                reason="缺少 Curriculum 上下文，无法说明该课程为何被列入方案；需人工核对。",
                evidence=absent,
            ),
        ),
    )


def selected_class_draft(
    *,
    course_id: str,
    class_id: str,
    task: MakeupTask | None,
    offering: CourseOffering | None,
) -> TemplateDraft:
    """解释「为什么方案里排了这个教学班」。"""

    parts: list[str] = []

    if task is not None:
        parts.append(f"该课程在 Curriculum 判定中为「{task.status.value}」。")
        if task.reason:
            parts.append(f"判定说明：{_quote(task.reason)}")
        if task.recommended_semester is not None:
            parts.append(f"建议学期：第 {task.recommended_semester} 学期。")
    else:
        parts.append(_MISSING_MAKEUP_CONTEXT)

    if offering is not None:
        parts.append(f"该教学班排课：{_meetings_text(offering)}")
        if offering.remaining_capacity is not None:
            parts.append(f"该教学班剩余容量：{offering.remaining_capacity}。")
    else:
        parts.append(
            "解释请求没有包含该教学班的 CourseOffering 上下文，"
            "因此无法展示它的实际排课信息。"
        )

    parts.append(
        "本解释不重新做冲突检测：是否与其他课程冲突、为何它是可行选择，"
        "以 Planner 输出的 changes / risks / unresolved 为准。"
    )

    strong: list[EvidenceReference] = []
    premise: list[EvidenceReference] = []
    confirmations: list[ConfirmationRequirement] = []

    if task is not None:
        strong.append(_status_evidence(task))
        strong.append(_reason_reference(task))
    else:
        strong.append(
            EvidenceReference(
                kind=EvidenceKind.ABSENT,
                strength=EvidenceStrength.ABSENT,
                source_object="MakeupTask",
                source_field="status",
                raw_value="",
                note="请求中没有提供该课程的 MakeupTask。",
            )
        )

    if offering is not None:
        strong.append(_offering_reference(offering))
    else:
        premise.append(
            EvidenceReference(
                kind=EvidenceKind.ABSENT,
                strength=EvidenceStrength.ABSENT,
                source_object="CourseOffering",
                source_field="meetings",
                raw_value=class_id,
                note="请求中没有提供该教学班对象，排课信息无法追溯。",
            )
        )

    if task is not None and task.status in (
        MakeupStatus.POSSIBLY_EQUIVALENT,
        MakeupStatus.MANUAL_CONFIRMATION,
    ):
        confirmations.append(
            ConfirmationRequirement(
                reason=(
                    "该课程的资格状态尚未最终确认，入选资格可能随人工确认结果变化。"
                ),
                evidence=_status_evidence(task),
            )
        )

    if offering is not None and not offering.meetings:
        confirmations.append(
            ConfirmationRequirement(
                reason=(
                    "该教学班在来源快照中没有可用排课信息，"
                    "不能据此声明它与其他课程不存在时间冲突。"
                ),
                evidence=_offering_reference(offering),
            )
        )

    return TemplateDraft(
        title=f"{course_id} 教学班 {class_id} 的安排依据",
        answer=_clip(" ".join(parts)),
        strong_evidence=tuple(strong),
        premise_evidence=tuple(premise),
        confirmations=tuple(confirmations),
    )


def change_draft(
    *,
    course_id: str,
    from_class: str | None,
    to_class: str | None,
    reason: str,
    from_offering: CourseOffering | None,
    to_offering: CourseOffering | None,
) -> TemplateDraft:
    """解释一条 `changes[]`：只复述 Planner 给出的原因 + 两个教学班的排课事实。"""

    parts = [
        f"Planner 记录的调整：{'原教学班 ' + (from_class or '（未提供）') if from_class else '（未提供原教学班）'}"
        f" → 调整为 {to_class or '（未提供）'}。",
        f"Planner 给出的调整原因原文：{_quote(reason)}",
    ]

    if from_offering is not None:
        parts.append(f"原教学班排课：{_meetings_text(from_offering)}")
    else:
        parts.append("解释请求未包含原教学班对象，其排课信息无法追溯。")

    if to_offering is not None:
        parts.append(f"新教学班排课：{_meetings_text(to_offering)}")

    parts.append(
        "以上排课信息只是对两个教学班的**事实转述**，"
        "本解释没有重新做冲突检测，也没有独立验证 Planner 的调整原因。"
    )

    strong = [
        EvidenceReference(
            kind=EvidenceKind.SYSTEM_SUGGESTION,
            strength=EvidenceStrength.CONFIRMED,
            source_object="PlanResult.changes",
            source_field="reason",
            raw_value=quote_field_text(reason),
            note="Planner 输出的调整原因，本解释原样转述。",
        ),
        EvidenceReference(
            kind=EvidenceKind.SYSTEM_SUGGESTION,
            strength=EvidenceStrength.CONFIRMED,
            source_object="PlanResult.changes",
            source_field="from_class",
            raw_value=_raw(from_class),
            note="调整前教学班号。",
        ),
        EvidenceReference(
            kind=EvidenceKind.SYSTEM_SUGGESTION,
            strength=EvidenceStrength.CONFIRMED,
            source_object="PlanResult.changes",
            source_field="to_class",
            raw_value=_raw(to_class),
            note="调整后教学班号。",
        ),
    ]

    premise: list[EvidenceReference] = []
    confirmations: list[ConfirmationRequirement] = [
        ConfirmationRequirement(
            reason=(
                "调整原因是 Planner 的求解结论（系统建议），"
                "不代表学校规则或教务已批准的调班结果。"
            ),
            evidence=strong[0],
        )
    ]

    for label, offering in (("原教学班", from_offering), ("新教学班", to_offering)):
        if offering is None:
            premise.append(
                EvidenceReference(
                    kind=EvidenceKind.ABSENT,
                    strength=EvidenceStrength.ABSENT,
                    source_object="CourseOffering",
                    source_field="class_id",
                    raw_value="",
                    note=f"请求中没有提供{label}对象，其排课信息无法追溯。",
                )
            )
        else:
            premise.append(_offering_reference(offering))
            if not offering.meetings:
                confirmations.append(
                    ConfirmationRequirement(
                        reason=(
                            f"{label}在来源快照中没有可用排课信息，"
                            "不能据此判断它与其他课程是否存在冲突。"
                        ),
                        evidence=_offering_reference(offering),
                    )
                )

    return TemplateDraft(
        title=f"{course_id} 的调班原因",
        answer=_clip(" ".join(parts)),
        strong_evidence=tuple(strong),
        premise_evidence=tuple(premise),
        confirmations=tuple(confirmations),
    )


def risk_draft(*, course_id: str | None, level: RiskLevel, reason: str) -> TemplateDraft:
    """解释一条 `risks[]`：原样转述等级与原因，不新增风险类型。"""

    target = course_id if course_id else "整体方案"
    answer = _clip(
        f"Planner 对{target}给出的风险等级为「{_RISK_LEVEL_TEXT[level]}」，"
        f"原因原文：{_quote(reason)} 本解释不补充、不推断其它风险类型。"
    )

    evidence = (
        EvidenceReference(
            kind=EvidenceKind.SYSTEM_SUGGESTION,
            strength=EvidenceStrength.CONFIRMED,
            source_object="PlanResult.risks",
            source_field="level",
            raw_value=_raw(level.value),
            note="Planner 给出的风险等级。",
        ),
        EvidenceReference(
            kind=EvidenceKind.SYSTEM_SUGGESTION,
            strength=EvidenceStrength.CONFIRMED,
            source_object="PlanResult.risks",
            source_field="reason",
            raw_value=quote_field_text(reason),
            note="Planner 给出的风险原因原文。",
        ),
    )

    return TemplateDraft(
        title=f"{target} 的风险依据",
        answer=answer,
        strong_evidence=evidence,
        confirmations=(
            ConfirmationRequirement(
                reason="风险是 Planner 的判断，不构成选课结果或学校结论，请以教务系统为准。",
                evidence=evidence[1],
            ),
        ),
    )


def unresolved_draft(*, item: Unresolved) -> TemplateDraft:
    """解释一条 `unresolved[]`：类型与消息原样转述，不解释成已知结论。"""

    answer = _clip(
        f"Planner 将这条事项标记为未解决（type = {item.type}），说明：{_quote(item.message)} "
        "本解释不把未解决事项当作已确认结论，也不代替人工确认。"
    )

    evidence = (
        EvidenceReference(
            kind=EvidenceKind.SYSTEM_SUGGESTION,
            strength=EvidenceStrength.PARTIAL,
            source_object="PlanResult.unresolved",
            source_field="type",
            raw_value=_raw(item.type),
            note="Planner 给出的未解决事项类型（公共契约未限定取值）。",
        ),
        EvidenceReference(
            kind=EvidenceKind.SYSTEM_SUGGESTION,
            strength=EvidenceStrength.PARTIAL,
            source_object="PlanResult.unresolved",
            source_field="message",
            raw_value=quote_field_text(item.message),
            note="Planner 给出的未解决事项说明原文。",
        ),
    )

    return TemplateDraft(
        title=f"未解决事项：{item.type}",
        answer=answer,
        strong_evidence=evidence,
        confirmations=(
            ConfirmationRequirement(
                reason="该事项在 Planner 输出中尚未解决，需要人工 / 教务确认后才能采用。",
                evidence=evidence[1],
            ),
        ),
    )


def plan_status_draft(
    *, result: PlanResult, has_unresolved: bool, has_high_risk: bool
) -> TemplateDraft:
    """解释整体 `PlanResult.status`：只复述状态与计数。"""

    parts = [
        _PLAN_STATUS_TEXT[result.status.value],
        f"方案包含 {len(result.selected_classes)} 个建议教学班、{len(result.changes)} 项调整、"
        f"{len(result.risks)} 项风险提示、{len(result.unresolved)} 项未解决事项。",
    ]

    if result.objective_summary:
        parts.append(f"Planner 给出的求解目标摘要：{_quote(result.objective_summary)}")

    parts.append("本解释不重新求解，也不改写该状态。")

    # ⚠️ 这些计数是**来自 PlanResult 的事实**，必须进入事实目录：
    # 否则正文里出现的数字无法在事实目录中找到，模型输出校验会把合法陈述误判成编造。
    extra_facts = (
        f"plan_status={result.status.value}",
        f"selected_classes_count={len(result.selected_classes)}",
        f"changes_count={len(result.changes)}",
        f"risks_count={len(result.risks)}",
        f"unresolved_count={len(result.unresolved)}",
    )

    strong = [
        EvidenceReference(
            kind=EvidenceKind.SYSTEM_SUGGESTION,
            strength=EvidenceStrength.CONFIRMED,
            source_object="PlanResult",
            source_field="status",
            raw_value=_raw(result.status.value),
            note="Planner 给出的整体方案状态。",
        )
    ]

    if result.objective_summary:
        strong.append(
            EvidenceReference(
                kind=EvidenceKind.SYSTEM_SUGGESTION,
                strength=EvidenceStrength.CONFIRMED,
                source_object="PlanResult",
                source_field="objective_summary",
                raw_value=quote_field_text(result.objective_summary),
                note="Planner 给出的求解目标摘要原文。",
            )
        )

    confirmations: list[ConfirmationRequirement] = []

    if result.status.value != "feasible":
        confirmations.append(
            ConfirmationRequirement(
                reason=(
                    "方案状态不是完全可行，采用前需人工确认未解决事项与风险。"
                ),
                evidence=strong[0],
            )
        )
    if has_unresolved:
        confirmations.append(
            ConfirmationRequirement(
                reason="方案仍包含未解决事项，本解释不会把它们当作已确认结论。",
                evidence=strong[0],
            )
        )
    if has_high_risk:
        confirmations.append(
            ConfirmationRequirement(
                reason="方案包含高风险提示，是否采用需人工判断。",
                evidence=strong[0],
            )
        )

    if not result.selected_classes and not result.changes and not result.risks and not result.unresolved:
        confirmations.append(
            ConfirmationRequirement(
                reason=(
                    "本方案各列表均为空：这只表示没有对应条目，"
                    "不构成「已排好课」或「无冲突」的结论。"
                ),
                evidence=strong[0],
            )
        )

    return TemplateDraft(
        title="整体方案状态的依据",
        answer=_clip(" ".join(parts)),
        strong_evidence=tuple(strong),
        confirmations=tuple(confirmations),
        extra_facts=extra_facts,
    )
