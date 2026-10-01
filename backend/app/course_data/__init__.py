"""Course Data 内部实现包（Phase 2B-2A：Normalization Core）。

```text
已确认 SYSU 字段  →  确定性转换 / 校验  →  CourseOffering
                  →  带 completeness 的内部 snapshot
                  →  CourseDataProvider.get_course_offerings(semester)
```

⚠️ **本包是 Course Data 的内部实现，不是跨模块公共契约。**

- 公共边界**只有** `CourseDataProvider.get_course_offerings(semester)`
  （见 `docs/interfaces/integration.md`，Phase 2B-1 已冻结）；
  本包的 `SnapshotCourseDataProvider` **结构上满足**它，但**不继承、不修改**它。
- 本包**不修改** `schemas/`、`docs/interfaces/`、`integration/`。
- `OfferingSnapshot` 是**内部对象**，不会成为新的跨模块 Schema。

⚠️ **零网络**：本包没有 endpoint、没有 Cookie / Session / Token、没有 crawler、
没有 Playwright / Selenium、不 import `mock_service`，**也不会自动 fallback 到 Mock**。

当前阶段边界（**故意的，不是功能遗漏**）：

- ✅ 已完成：已确认字段的确定性映射 / 校验、两种已记录周次格式的展开、
  带 completeness 的内部快照、Provider 最小落点；
- ⏳ 未实现：`teachingTimePlaceStr` 的完整 parser（缺真实脱敏 Raw string）、
  授权 import adapter、完整 semester snapshot；
- ⛔ 未确认、**本轮不做**：`weekDay → weekday`、`openingSchoolName → campus`、
  meeting 级教师关联（known deferred representation gap）。
"""

from __future__ import annotations

from app.course_data.errors import CourseDataNormalizationError
from app.course_data.normalization import build_course_offering, expand_weeks
from app.course_data.snapshot import OfferingSnapshot, SnapshotCourseDataProvider

__all__ = [
    "CourseDataNormalizationError",
    "OfferingSnapshot",
    "SnapshotCourseDataProvider",
    "build_course_offering",
    "expand_weeks",
]
