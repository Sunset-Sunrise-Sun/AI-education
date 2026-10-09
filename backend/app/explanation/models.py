"""解释服务的请求 / 响应模型。

⚠️ 这些模型**不是**公共 Schema（`/schemas/`）的一部分：它们是解释接口**私有**的
线格式，只描述「解释条目长什么样」，不新增、不修改任何公共业务对象。
公共对象（`PlanResult` / `MakeupTask` / `CourseOffering` / `Preference`）一律**原样复用**
`app.models.contracts` 中的模型，本模块不重新定义它们。

设计原则：

1. **每条解释都必须能追溯到字段**：`strong_evidence` / `premise_evidence` 里每一行都写明
   来源对象 + 字段 + 原始取值（取值可以被截断，但不允许改写或合成）；
2. **不确证未知关系**：`requires_human_confirmation` 记录「本解释不能替你下结论」的事项；
3. **来源分类**（`EvidenceKind`）与「确证规则 / 学生输入或假设 / 系统建议 / 未知」四类严格对应；
4. **生成方式必须如实**：`generation.generator_kind` 明确区分规则模板与真实模型调用，
   并对每个条目单独标注，未配置模型时**不得**把模板说成 AI。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.contracts import CourseOffering, MakeupTask, PlanResult

#: 解释线格式的版本号；结构变更时必须递增，便于前端判别。
EXPLANATION_CONTRACT_VERSION = "explanation-v1"

#: 单个自由文本字段的截断上限（防止把上游超长文本无界转述）。
MAX_TEXT_LENGTH = 1200

#: `evidence_ref.raw_value` 的截断上限（原文片段只能作为溯源提示）。
MAX_RAW_VALUE_LENGTH = 400

#: 文本被截断时追加的**唯一**标记（字段级与正文级共用，避免两个不同标记）。
TRUNCATION_MARKER = "…（原文已截断）"

#: 「被引用的来源原文」的长度上限。
#: ⚠️ 必须满足 `QUOTED_FIELD_LIMIT + len(TRUNCATION_MARKER) <= MAX_RAW_VALUE_LENGTH`，
#: 否则字段级 `raw_value` 会因为追加标记而超过上限（自相矛盾）。
QUOTED_FIELD_LIMIT = MAX_RAW_VALUE_LENGTH - len(TRUNCATION_MARKER)

_FORBID_EXTRA = ConfigDict(extra="forbid")


class EvidenceKind(str, Enum):
    """证据 / 前提的**性质**（对应任务书的四分类）。

    - `confirmed_rule`：来自正式规则或模块权威判定（例如 Curriculum 给出的补修判定）；
      ⚠️ 只表示「该结论由哪个模块以哪条字段给出」，**不**代替人工确认学校正式规则；
    - `student_input_or_assumption`：来自学生输入或输入中的假设 / 演示数据；
    - `system_suggestion`：系统 / 算法的建议（例如 Planner 的调班原因），
      它是**已给出的结论**，不是学校规则，也不是学生事实；
    - `unknown`：当前来源无法支持该关系（例如先修关系缺来源、教学班无排课信息）；
    - `absent`：该字段在当前上下文中**根本不存在**（例如解释只收到 `PlanResult`，
      没有收到 `MakeupTask` 上下文）—— 与「值为空」严格区分。
    """

    CONFIRMED_RULE = "confirmed_rule"
    STUDENT_INPUT_OR_ASSUMPTION = "student_input_or_assumption"
    SYSTEM_SUGGESTION = "system_suggestion"
    UNKNOWN = "unknown"
    ABSENT = "absent"


class EvidenceStrength(str, Enum):
    """证据强度：只描述「能不能支撑当前这句话」，不评价学校政策。"""

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    ABSENT = "absent"


class GeneratorKind(str, Enum):
    """解释文本的**实际**生成方式（不允许含糊）。"""

    RULE_TEMPLATE = "rule_based_template"
    MODEL = "model"
    MODEL_UNAVAILABLE = "model_unavailable_fell_back_to_template"


class ItemKind(str, Enum):
    """解释条目类型，与被解释的 `PlanResult` / `MakeupTask` 字段一一对应。"""

    MAKEUP_TASK = "makeup_task"
    SELECTED_CLASS = "selected_class"
    CHANGE = "change"
    RISK = "risk"
    UNRESOLVED = "unresolved"
    PLAN_STATUS = "plan_status"


class EvidenceReference(BaseModel):
    """一条可核对的来源引用：**对象 + 字段 + 原始取值**。

    `raw_value` 是上游字段的**原样片段**（必要时截断），因此人工可以据此复核；
    它不是本服务生成的解释文本。
    """

    model_config = _FORBID_EXTRA

    kind: EvidenceKind
    strength: EvidenceStrength
    source_object: str = Field(min_length=1, description="来源对象，例如 MakeupTask / PlanResult")
    source_field: str = Field(min_length=1, description="来源字段名，例如 status / reason")
    raw_value: str = Field(
        default="",
        description="该字段的原始取值（可截断，不改写）；字段不存在时为空字符串",
    )
    note: str = Field(default="", description="为什么这条引用支撑当前解释")


class ConfirmationRequirement(BaseModel):
    """本解释**不能**替用户 / 教务下结论的事项。"""

    model_config = _FORBID_EXTRA

    reason: str = Field(min_length=1)
    evidence: EvidenceReference | None = None


class ExplanationGeneration(BaseModel):
    """生成方式与降级原因（必须如实填写）。"""

    model_config = _FORBID_EXTRA

    generator_kind: GeneratorKind
    model_configured: bool = Field(description="是否配置了真实模型适配层")
    model_id: str | None = Field(default=None, description="已配置模型的标识；未配置为 None")
    fallback_reason: str | None = Field(
        default=None, description="发生降级时的原因（未配置 / 调用失败 / 输出校验未通过）"
    )
    disclaimer: str = Field(min_length=1, description="面向用户的生成方式声明")


class SourceSummary(BaseModel):
    """本次解释实际用到的数据来源概况（Mock / Real 必须可见）。"""

    model_config = _FORBID_EXTRA

    plan_result_digest: str = Field(min_length=1, description="被解释的 PlanResult 摘要（校验未被改写）")
    context_digest: str = Field(min_length=1)
    makeup_task_count: int = Field(ge=0)
    course_offering_count: int = Field(ge=0)
    contains_mock_marker: bool = Field(
        description="上下文中是否出现 Mock 来源标记（source_evidence 含 mock:// 或演示数据字样）"
    )
    contains_real_offering: bool = Field(description="是否收到 data_source = real 的教学班")
    notes: list[str] = Field(default_factory=list)


class ExplanationItem(BaseModel):
    """单条解释：结构化事实 + 由事实生成的文本 + 待人工确认事项。"""

    model_config = _FORBID_EXTRA

    item_id: str = Field(min_length=1, description="稳定标识，前端用它定位该条目")
    kind: ItemKind
    code: str = Field(min_length=1, description="解释规则码，例如 makeup_status_required")
    target_course_id: str | None = None
    target_class_id: str | None = None
    title: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    strong_evidence: list[EvidenceReference] = Field(default_factory=list)
    premise_evidence: list[EvidenceReference] = Field(default_factory=list)
    requires_human_confirmation: list[ConfirmationRequirement] = Field(default_factory=list)
    generation: ExplanationGeneration


class ExplanationRequest(BaseModel):
    """解释请求：只包含**已经存在**的公共对象，不含任何个人身份或成绩明细。"""

    model_config = _FORBID_EXTRA

    plan_result: PlanResult
    makeup_tasks: list[MakeupTask] | None = Field(
        default=None,
        description="可选：Curriculum 已输出的补修任务上下文；缺失时解释会明确标记「上下文不存在」",
    )
    course_offerings: list[CourseOffering] | None = Field(
        default=None, description="可选：Course Data 已输出的教学班上下文"
    )


class ExplanationFacts(BaseModel):
    """由请求构建出的**事实平面**（全部来自输入对象，不做业务推断）。

    它是模板与可选模型适配层唯一的输入，因此「解释只说这些事实」是可检查的。
    """

    model_config = _FORBID_EXTRA

    plan_result: PlanResult
    makeup_tasks: list[MakeupTask] = Field(default_factory=list)
    course_offerings: list[CourseOffering] = Field(default_factory=list)
    makeup_tasks_provided: bool = False
    course_offerings_provided: bool = False
    plan_result_digest: str = Field(min_length=1)
    context_digest: str = Field(min_length=1)
    source_summary: SourceSummary


class ExplanationResponse(BaseModel):
    """解释响应：条目 + 生成方式 + 来源概况 + 未覆盖请求。"""

    model_config = _FORBID_EXTRA

    contract_version: str = EXPLANATION_CONTRACT_VERSION
    plan_result_digest: str = Field(min_length=1)
    context_digest: str = Field(min_length=1)
    generation: ExplanationGeneration
    source_summary: SourceSummary
    warnings: list[str] = Field(default_factory=list)
    items: list[ExplanationItem] = Field(default_factory=list)
