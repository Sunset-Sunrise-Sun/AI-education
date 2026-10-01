"""`PlanningOrchestrator`：Integration 的最小编排骨架。

它**只做一件事**：按固定顺序调用三个 Provider，并把结果**原样**串起来。

```text
CurriculumProvider.get_makeup_tasks()
            ↓
CourseDataProvider.get_course_offerings(semester)
            ↓
PlannerProvider.plan(
    makeup_tasks=...,
    offerings=...,
    current_schedule=...,
    preference=...
)
            ↓
原样返回 PlanResult
```

## 明确禁止放进本文件的东西

- ❌ **任何业务判断**：不判断学生缺什么课、不判断课程是否等价、不认定 prerequisite、
  不生成 priority、不检测冲突、不选择教学班、不执行 Path Repair、不修改 `PlanResult`；
- ❌ **任何"顺手的"数据加工**：不排序、不筛选、不去重、不补默认值、不计算派生值；
- ❌ **任何 fallback**：Provider 抛异常时**让它继续向上抛**，
  绝不返回一份 Mock `PlanResult`、也不自动切换到 Mock 通道。

因此本文件里**不应出现**：`if` 分支判断业务、`sort`、`max`、推导式过滤、
以及对 `/api/v1/mock/*` 或 `mock_service` 的任何引用。

错误处理原则：**本轮不设计复杂异常体系** —— Provider 的异常原样向上传递。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.integration.ports import (
    CourseDataProvider,
    CurriculumProvider,
    PlannerProvider,
)
from app.models.contracts import CourseOffering, PlanResult, Preference

__all__ = ["PlanningOrchestrator"]


@dataclass(frozen=True)
class PlanningOrchestrator:
    """持有三个 Provider，并定义它们之间的调用顺序。

    只持有边界，不持有状态、不持有缓存、不持有上下文。
    """

    curriculum: CurriculumProvider
    course_data: CourseDataProvider
    planner: PlannerProvider

    def build_plan(
        self,
        *,
        semester: str,
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult:
        """按固定顺序取数并交给 Planner，返回 Planner 给出的同一个对象。

        参数说明：

        - `semester` —— **原样**传给 Course Data（本层不改写、不校验、不补默认值）；
        - `current_schedule` —— 学生**当前已经选择**的教学班子集（`CourseOffering[]`）；
          允许为空列表，本层不会因此报错；
        - `preference` —— 用户偏好，原样下传。

        返回值就是 `PlannerProvider.plan()` 的返回值本身：
        本层不包装、不复制、不改写 `PlanResult`。
        """

        makeup_tasks = self.curriculum.get_makeup_tasks()
        offerings = self.course_data.get_course_offerings(semester)

        return self.planner.plan(
            makeup_tasks=makeup_tasks,
            offerings=offerings,
            current_schedule=current_schedule,
            preference=preference,
        )
