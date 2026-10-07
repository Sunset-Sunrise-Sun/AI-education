"""Path Planner：把"单学期补修建议"推进为"转专业学业路径规划"的第一阶段。

本包**不修改**任何冻结契约：

- ⛔ 不改 `PlannerProvider.plan(...)` 四参数签名；
- ⛔ 不改 `CourseOffering` / `Meeting` / `Preference` / `PlanResult` 公共 Schema；
- ⛔ 不改 `RestrictedPlannerProvider` 的公开语义（只**复用**它的原语）；
- ⛔ 不改 Course Data / Curriculum 的信任语义。

两条**分离**的职责：

```text
当前学期  repair_proposals：教学班级（section-level）调整建议
          → 复用 planner.section_repair.find_alternative_sections()
          → ⛔ 生成建议 ≠ 应用建议；只有调用方**显式选择**后才会应用

未来学期  future_roadmap：课程级（course-level）多学期路线图
          → 只吃 Curriculum 事实（CurriculumVersion / CompletedCourse ...）
          → ⛔ 禁止要求、预测或生成未来 CourseOffering
```

⛔ 未来学期**不需要**任何 Course Data 采集：培养方案给出的"每学期开设/建议课程 +
学分 + 培养要求"已经足够；⛔ 不得用本学期真实开课去断言未来教学班。
"""

from __future__ import annotations

from app.path_planner.future_roadmap import (
    AcademicRoadmap,
    FutureSemester,
    RoadmapInputError,
    SemesterCoursePlan,
    SemesterPlan,
    build_academic_roadmap,
)
from app.path_planner.repair_proposals import (
    RepairApplicationResult,
    RepairApplicationStatus,
    RepairProposalSet,
    SectionRepairProposal,
    apply_repair_proposal,
    generate_repair_proposals,
)

__all__ = [
    "AcademicRoadmap",
    "FutureSemester",
    "RepairApplicationResult",
    "RepairApplicationStatus",
    "RepairProposalSet",
    "RoadmapInputError",
    "SectionRepairProposal",
    "SemesterCoursePlan",
    "SemesterPlan",
    "apply_repair_proposal",
    "build_academic_roadmap",
    "generate_repair_proposals",
]
