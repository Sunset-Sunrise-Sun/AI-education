"""Personal Planning：**个人输入驱动的规划入口**（本轮新增，非公共契约）。

```text
已核验培养方案版本目录（app.curriculum.catalog）
        +
学生本人输入（本人已修事实 / 已有正式认定凭据 / 明确标注的规划假设）
        ↓
本学生独立的 CurriculumCase（⛔ 不复用任何 case 文件或其他学生的结论）
        ↓
既有 Curriculum → MakeupTask[] → PlannerProvider.plan(...) 路线
        ↓
PersonalPlanResult（版本元信息 + 补修任务 + 可选规划结果 + 来源说明）
```

## 这个包不做什么

- ⛔ 不修改 `/schemas/` 与 `/docs/interfaces/`（公共契约）；
- ⛔ 不修改四个已冻结的 Integration 调用签名
  （`CurriculumProvider.get_makeup_tasks` / `CourseDataProvider.get_course_offerings` /
  `PlannerProvider.plan` / `PlanningOrchestrator.build_plan`）；
- ⛔ 不修改 `POST /api/v1/plan` 的请求 / 响应契约，也不动已冻结的 Case A runtime；
- ⛔ 不重写课程认定、等价性、学分、期限、先修或组学分规则；
- ⛔ 不用 LLM 输出替代确定性判断，也⛔ 不把规划假设当成学校认定。

## 与旧 Case A 的关系

旧 Case A 由**固定 case 文件**驱动，继续原样可用；本包是**平行的新入口**，
两者互不读取对方状态。
"""

from __future__ import annotations

from app.personal.planning import (
    PERSONAL_PLAN_REQUEST_FIELDS,
    PersonalPlanRequest,
    PersonalPlanResult,
    build_personal_plan,
    normalize_personal_plan_request,
    personal_curriculum_case,
)
from app.personal.student_input import (
    PLANNING_ASSUMPTION_LABEL,
    STUDENT_INPUT_FIELDS,
    PlanningAssumption,
    StudentInput,
    normalize_student_input,
)

__all__ = [
    "PERSONAL_PLAN_REQUEST_FIELDS",
    "PLANNING_ASSUMPTION_LABEL",
    "STUDENT_INPUT_FIELDS",
    "PersonalPlanRequest",
    "PersonalPlanResult",
    "PlanningAssumption",
    "StudentInput",
    "build_personal_plan",
    "normalize_personal_plan_request",
    "normalize_student_input",
    "personal_curriculum_case",
]
