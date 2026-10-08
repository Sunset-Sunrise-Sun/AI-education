"""可选模型适配层（**默认未配置**，绝不伪装成模型调用）。

## 为什么默认关闭

任务书要求：没有模型密钥或外部服务时，必须提供**可追溯的确定性解释**，
并明确标识其非模型生成。因此：

- 本模块提供一个**显式注入**的适配器协议；没有注入适配器时，
  解释完全由 `templates.py` 生成，响应中 `generator_kind = rule_based_template`；
- ⛔ 本仓库**不**自带任何网络调用、SDK、密钥读取或服务选型
  （选型属受控事项，见 `/AGENTS.md` 第 7 节）；
- 适配器失败 / 输出未通过事实绑定校验 ⇒ **降级回模板**，并把原因写进响应
  （`model_unavailable_fell_back_to_template`），⛔ 不静默、⛔ 不重试、⛔ 不伪造成功。

## 事实绑定校验（防幻觉的硬门槛）

即使配置了模型，模型输出也**不能直接作为答案**。校验包含：

1. 模板给出的**已核实陈述**必须原样出现在模型输出中（防改写事实）；
2. 输出中出现的**数量型数字**必须能在事实目录里找到（防编造学分、周次、容量）；
3. 输出中出现的**课程号 / 教学班号**必须来自事实目录（防编造课程与等价关系）；
4. 输出必须是**单个字符串**且长度受限。

任何一条不满足 ⇒ 该条解释降级为模板，并记录原因。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from app.explanation.models import MAX_TEXT_LENGTH, ExplanationFacts
from app.explanation.templates import TemplateDraft, quote_field_text

#: 数量型数字 token（含小数）；用于防止模型改写学分 / 周次 / 容量。
#: ⚠️ 前置断言：数字前**不能**紧邻标识符字符，避免把「C1」中的 1、
#: 或来源 URI 里的数字误判成数量信息。
_NUMBER_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<![0-9A-Za-z_./:-])\d+(?:\.\d+)?")

#: 类课程号 / 教学班号的标识符（**必须含 ASCII 字母**，防止把
#: 「第 4 学期」这类普通数字被误判成课程号）。
_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")

#: 来源 URI / 路径（`mock://curriculum/62001001` 等）：其中的数字是**标识符**，
#: 不是可自由生成的数量信息，因此先整段剥离再抽数字。
_URI_LIKE_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")

#: 模型输出的最大长度（比模板上限更严格，避免把整份结果回灌给用户）。
MAX_MODEL_ANSWER_LENGTH: Final[int] = 800


@runtime_checkable
class ExplanationModelAdapter(Protocol):
    """可选模型适配器：**只接收已构建的事实**，返回草稿文本。

    实现方（未来集成）必须：

    - 只把 `facts_answer` 与 `fact_catalog` 交给模型，⛔ 不传原始成绩单 / 个人信息；
    - 要求模型做**结构化输出**且字段形状固定；
    - 不缓存、不落盘、不打印学生数据。
    """

    model_id: str

    def complete(
        self, *, question: str, facts_answer: str, fact_catalog: tuple[str, ...]
    ) -> str: ...


class ModelAdapterError(RuntimeError):
    """模型不可用 / 调用失败 / 输出不合法。"""


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """模型适配结果：文本或降级原因（二者必有其一）。"""

    text: str | None
    reason: str | None

    @property
    def usable(self) -> bool:
        return self.text is not None


def fact_catalog(facts: ExplanationFacts, draft: TemplateDraft) -> tuple[str, ...]:
    """构建**唯一**可被模型引用的事实目录（顺序稳定，便于测试）。

    目录内容全部来自输入对象与结构化证据，不含自由生成的推断。
    ⚠️ 长自由文本字段必须与模板一样用 `quote_field_text()` 截断，
    否则「模型看到的事实」会比「模板实际引用的原文」更长。
    """

    entries: list[str] = []

    result = facts.plan_result
    entries.append(f"PlanResult.status={result.status.value}")
    for selected in result.selected_classes:
        entries.append(f"selected_class={selected.course_id}|{selected.class_id}")
    for change in result.changes:
        entries.append(
            f"change={change.course_id}|from={change.from_class or ''}|to={change.to_class or ''}"
            f"|reason={quote_field_text(change.reason)}"
        )
    for risk in result.risks:
        entries.append(
            f"risk={risk.course_id or ''}|level={risk.level.value}"
            f"|reason={quote_field_text(risk.reason)}"
        )
    for item in result.unresolved:
        entries.append(f"unresolved={item.type}|message={quote_field_text(item.message)}")
    for task in facts.makeup_tasks:
        entries.append(
            f"makeup_task={task.course_id}|status={task.status.value}"
            f"|credit={task.credit}|reason={quote_field_text(task.reason or '')}"
            f"|source_evidence={quote_field_text(task.source_evidence or '')}"
        )
        for prerequisite in task.prerequisites:
            entries.append(f"prerequisite={task.course_id}->{prerequisite}")
    for offering in facts.course_offerings:
        entries.append(
            f"offering={offering.course_id}|class={offering.class_id}"
            f"|data_source={offering.data_source.value}|meetings={len(offering.meetings)}"
        )

    if result.objective_summary:
        entries.append(f"objective_summary={quote_field_text(result.objective_summary)}")

    entries.extend(draft.extra_facts)
    entries.extend(reference.raw_value for reference in draft.strong_evidence)
    entries.extend(reference.raw_value for reference in draft.premise_evidence)
    entries.extend(requirement.reason for requirement in draft.confirmations)

    # 去重但保持顺序
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in entries:
        if entry and entry not in seen:
            seen.add(entry)
            ordered.append(entry)
    return tuple(ordered)


def _numbers(text: str) -> set[str]:
    """抽取**数量型**数字 token（先剥离 URI，再抽取纯数字）。"""

    without_uris = _URI_LIKE_PATTERN.sub(" ", text)
    return set(_NUMBER_PATTERN.findall(without_uris))


def _identifiers(text: str) -> set[str]:
    """抽取课程号 / 教学班号这类标识符（必须含 ASCII 字母且含数字）。"""

    return {
        token
        for token in _IDENTIFIER_PATTERN.findall(_URI_LIKE_PATTERN.sub(" ", text))
        if any(character.isdigit() for character in token)
    }


def _catalog_numbers(catalog: tuple[str, ...]) -> set[str]:
    numbers: set[str] = set()
    for entry in catalog:
        numbers |= _numbers(entry)
    return numbers


def _catalog_identifiers(catalog: tuple[str, ...]) -> set[str]:
    identifiers: set[str] = set()
    for entry in catalog:
        identifiers |= _identifiers(entry)
    return identifiers


def validate_model_answer(
    *, candidate: object, draft: TemplateDraft, catalog: tuple[str, ...]
) -> str:
    """校验模型输出是否严格绑定事实；不合法时抛出 `ModelAdapterError`。

    这是**唯一**的验收门槛：不通过 ⇒ 调用方必须降级为模板。
    """

    if not isinstance(candidate, str):
        raise ModelAdapterError("模型输出不是字符串")

    text = candidate.strip()
    if not text:
        raise ModelAdapterError("模型输出为空")
    if len(text) > MAX_MODEL_ANSWER_LENGTH:
        raise ModelAdapterError("模型输出超长")

    if draft.answer not in text:
        raise ModelAdapterError("模型输出未包含已核实的事实陈述（可能改写或删除了事实）")

    catalog_numbers = _catalog_numbers(catalog)
    unknown_numbers = sorted(number for number in _numbers(text) if number not in catalog_numbers)
    if unknown_numbers:
        raise ModelAdapterError("模型输出引入了事实目录之外的数量信息")

    catalog_identifiers = _catalog_identifiers(catalog)
    unknown_identifiers = sorted(
        token for token in _identifiers(text) if token not in catalog_identifiers
    )
    if unknown_identifiers:
        raise ModelAdapterError("模型输出引入了事实目录之外的课程 / 教学班标识")

    return text[:MAX_TEXT_LENGTH]


def try_model_answer(
    adapter: ExplanationModelAdapter | None,
    *,
    facts: ExplanationFacts,
    draft: TemplateDraft,
) -> AdapterResult:
    """尝试用模型润色一条解释；任何失败都返回降级原因，⛔ 不抛出、不重试。"""

    if adapter is None:
        return AdapterResult(None, "未配置模型适配层")

    catalog = fact_catalog(facts, draft)
    try:
        raw = adapter.complete(
            question=draft.title,
            facts_answer=draft.answer,
            fact_catalog=catalog,
        )
    except Exception:  # noqa: BLE001 - 适配器属外部实现，任何异常都必须降级而不是中断解释
        return AdapterResult(None, "模型调用失败")

    try:
        return AdapterResult(
            validate_model_answer(candidate=raw, draft=draft, catalog=catalog), None
        )
    except ModelAdapterError as exc:
        return AdapterResult(None, f"模型输出未通过事实绑定校验（{exc}）")
