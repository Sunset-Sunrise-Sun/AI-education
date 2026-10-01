"""Integration 层：Curriculum / Course Data / Planner 之间的**编排边界**。

本包只回答一个问题：

> **按什么顺序调用上游模块，并把它们的结果原样交给下游？**

它的位置（`docs/interfaces/integration.md`）：

```text
CurriculumProvider ─────┐
                        │
CourseDataProvider ─────┼──> PlanningOrchestrator ───> PlannerProvider
                        │
current_schedule ───────┤
Preference ─────────────┘
```

**Integration = 调用 / 编排，不是业务算法。**

本包**不得**：
- 判断学生缺什么课、判断课程是否等价、认定 prerequisite、生成 priority；
- 检测时间冲突、选择教学班、执行 Path Repair、修改 `PlanResult`；
- 在 Provider 报错时返回 fallback（尤其是返回 Mock 结果）。

目前这里只有：

- `ports.py` —— 三个最小 `Provider` Protocol（插座）；
- `orchestrator.py` —— 按固定顺序调用三个 Provider 的 `PlanningOrchestrator`。

⚠️ **本包与 `/api/v1/mock/*` 是两条互不相干的通道。**
`app/services/mock_service.py` 仍是**永久 Mock-only** 的独立回放通道，
Integration **不会**在真实 Provider 缺失时自动回退到它。

⚠️ **本轮尚未接入任何生产 Provider**，也**没有暴露真实 API**。
"""

from __future__ import annotations

from app.integration.orchestrator import PlanningOrchestrator
from app.integration.ports import (
    CourseDataProvider,
    CurriculumProvider,
    PlannerProvider,
)

__all__ = [
    "CourseDataProvider",
    "CurriculumProvider",
    "PlannerProvider",
    "PlanningOrchestrator",
]
