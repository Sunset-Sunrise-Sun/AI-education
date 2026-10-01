"""Integration 的三个 Provider「插座」（`typing.Protocol`）。

设计原则（`/AGENTS.md` 第 4、5 节 + Data Gate DG-05 / DG-03）：

- **只声明 Integration 需要的最小形状**，不搬运任何上游内部结构；
- Integration 只与 `/schemas/*.schema.json` 的**公共对象**打交道：
  `MakeupTask` / `CourseOffering` / `Preference` / `PlanResult`；
- 这些 Protocol 是 `docs/interfaces/integration.md` 的**代码侧映射**：
  它们**不新增业务字段或 Schema**，
  但其**跨模块调用签名属于已确认的 Integration 公共接口边界**，
  **不得由实现模块私自修改**（变更须走 `/AGENTS.md` 第 4 节 `【接口变更请求】`）。

三个边界各自的"不知道"清单（很重要，防止 Integration 越权深入上游实现）：

| Provider | Integration **只**知道 | Integration **绝不能**知道 |
|---|---|---|
| `CurriculumProvider` | `MakeupTask[]` | 培养方案文件、`CompletedCourse` 内部结构、`CurriculumVersion`、`CurriculumCourse`、课程匹配实现 |
| `CourseDataProvider` | `semester` → `CourseOffering[]` | `jwxt.sysu.edu.cn`、POST endpoint、`pageNo` / `pageSize`、Cookie / Session、`teachingTimePlaceStr`、`class_ID`、`courseNumber` |
| `PlannerProvider` | 四个入参 → `PlanResult` | 求解器内部（OR-Tools / 图算法）、冲突检测实现、Path Repair 步骤 |

关于依赖与优先级（Data Gate **DG-05**）：

- Planner 唯一可消费的公开依赖信息是 **`MakeupTask.prerequisites[]`**；
- 本轮**不新增** `DependencyGraph` / `DependencyResult` / `PriorityResult` / `priority`；
- `PlannerProvider.plan()` 因此**不接收** `priority`、`dependency_graph`、`risk_scores` 之类的参数。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.contracts import (
    CourseOffering,
    MakeupTask,
    PlanResult,
    Preference,
)

__all__ = [
    "CourseDataProvider",
    "CurriculumProvider",
    "PlannerProvider",
]


@runtime_checkable
class CurriculumProvider(Protocol):
    """Curriculum 侧插座：Integration 只消费 Curriculum **已经产生的** `MakeupTask[]`。

    Integration **不知道**：培养方案文件形态、`CompletedCourse` 内部结构、
    `CurriculumVersion` / `CurriculumCourse`、课程匹配与差分实现。

    具体实现将来可以在**构造时**绑定用户 / case 上下文（例如"某个学生适用哪一版培养方案"），
    但那属于实现内部输入，**本 Protocol 不表达它**。
    """

    def get_makeup_tasks(self) -> list[MakeupTask]:
        """返回 Curriculum 产出的补修任务列表（可能为空）。"""
        ...


@runtime_checkable
class CourseDataProvider(Protocol):
    """Course Data 侧插座：Integration 只知道 `semester` → `CourseOffering[]`。

    Integration **绝不能**知道 `jwxt.sysu.edu.cn`、POST endpoint、`pageNo` / `pageSize`、
    Cookie / Session、`teachingTimePlaceStr`、`class_ID`、`courseNumber`
    —— 这些全部属于 Course Data Adapter 的实现细节。

    这是 **Phase 2B-2 Course Data MVP** 将真正实现的插座（本轮只有 Protocol，没有实现）。
    """

    def get_course_offerings(self, semester: str) -> list[CourseOffering]:
        """返回该学期的教学班列表（可能为空；是否为空由上游决定）。"""
        ...


@runtime_checkable
class PlannerProvider(Protocol):
    """Planner 侧插座：Integration 把输入原样交给 Planner，并原样接收 `PlanResult`。

    `current_schedule` 按 Data Gate **DG-03** 继续复用公共类型 `CourseOffering[]`，
    但语义是"**学生当前已经选择的教学班子集**"：

    ```text
    CourseOffering[]                     —— 学校全部供给
    current_schedule: CourseOffering[]   —— 学生已经选择的子集
    ```

    两者类型相同、语义不同。Integration **只负责传递**，不做区分判断。

    ⚠️ 入参**不包含** `priority` / `dependency_graph` / `risk_scores`（DG-05）：
    Planner 只能消费 `MakeupTask.prerequisites[]` 中已经给出的依赖边。
    """

    def plan(
        self,
        *,
        makeup_tasks: list[MakeupTask],
        offerings: list[CourseOffering],
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult:
        """执行确定性求解并返回 `PlanResult`（是否可行由 Planner 决定）。"""
        ...
