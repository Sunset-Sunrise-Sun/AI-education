"""解释服务（Explanation）—— **只读**消费已存在的结构化结果，产出可追溯的解释。

## 边界（硬，来自 `/AGENTS.md` 与 `docs/final_upgrade/AGENT_B.md`）

- ⛔ 本包**不**计算、**不**改写、**不**修复任何业务结论：
  不改 `PlanResult`，不改 `MakeupTask` 状态，不判定课程等价，不新增先修边，
  不推断 Planner 内部未给出的理由；
- ⛔ 不导入 Planner / Curriculum / Course Data / `mock_service`：
  解释只消费调用方**已经拿到**的公共契约对象（`PlanResult` / `MakeupTask` / `CourseOffering`）；
- ⛔ 不引入新的付费服务、密钥或大型依赖；可选 LLM 适配层默认**未配置**，
  未配置 / 调用失败时降级为**明确标注**的规则模板，且响应中如实说明实际生成方式；
- ✅ 解释的每一条陈述都必须绑定**真实存在的来源字段**（`reason` / `source_evidence` /
  `prerequisites` / `meetings` / `changes[].reason` / `risks[].reason` / `unresolved[]`），
  无法绑定的关系一律标记为**待人工确认**，不得编造学校规则。
"""

from __future__ import annotations

from app.explanation.models import (
    EXPLANATION_CONTRACT_VERSION,
    ConfirmationRequirement,
    EvidenceKind,
    EvidenceReference,
    EvidenceStrength,
    ExplanationFacts,
    ExplanationGeneration,
    ExplanationItem,
    ExplanationRequest,
    ExplanationResponse,
    GeneratorKind,
    ItemKind,
    SourceSummary,
)
from app.explanation.service import (
    ExplanationService,
    build_explanation,
    build_explanation_facts,
    plan_digest,
)

__all__ = [
    "EXPLANATION_CONTRACT_VERSION",
    "ConfirmationRequirement",
    "EvidenceKind",
    "EvidenceReference",
    "EvidenceStrength",
    "ExplanationFacts",
    "ExplanationGeneration",
    "ExplanationItem",
    "ExplanationRequest",
    "ExplanationResponse",
    "ExplanationService",
    "GeneratorKind",
    "ItemKind",
    "SourceSummary",
    "build_explanation",
    "build_explanation_facts",
    "plan_digest",
]
