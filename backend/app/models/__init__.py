"""公共契约模型（Pydantic 版）。

真源是仓库根目录的 `/schemas/*.schema.json`，本包只是它的后端映射。
"""

from app.models.contracts import (
    Change,
    Course,
    CourseOffering,
    DataSource,
    MakeupStatus,
    MakeupTask,
    PlanResult,
    PlanStatus,
    Preference,
    Risk,
    RiskLevel,
    SelectedClass,
    TimeBlock,
    Unresolved,
)

__all__ = [
    "Change",
    "Course",
    "CourseOffering",
    "DataSource",
    "MakeupStatus",
    "MakeupTask",
    "PlanResult",
    "PlanStatus",
    "Preference",
    "Risk",
    "RiskLevel",
    "SelectedClass",
    "TimeBlock",
    "Unresolved",
]
