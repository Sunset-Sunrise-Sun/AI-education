"""带 completeness 的**内部**教学班快照 + production Provider 的最小落点。

```text
Adapter / Parser  →  OfferingSnapshot  →  SnapshotCourseDataProvider  →  Integration
                     （本轮实现）           （本轮实现）
```

## `OfferingSnapshot` 是 Course Data **内部对象**

⛔ 它**不是**新的跨模块 Schema，不会进入 `schemas/`，Integration 也看不到它。
它的唯一作用是让"**这一份数据到底完不完整**"变成**代码里的强制事实**，
而不是文档里的一句好话。

## completeness 规则（Data Gate C9）

```text
loaded_count = len(offerings)

partial  ：可以没有 reported_total；若有，则 reported_total >= loaded_count
complete ：必须有 reported_total，且 reported_total == loaded_count
```

这样以后**不可能**拿"2 条侦察样本"去声称"complete semester snapshot"。

## 当前定位

**Phase 2B-2A** 只做到这里：本地标准化 + 快照 + Provider 落点。
**真实授权 import adapter、完整 `teachingTimePlaceStr` parser、完整 2026-1 snapshot
均尚未实现。**

本模块**零网络**：没有 endpoint、没有 Cookie / Session / Token、没有 crawler。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.course_data.errors import CourseDataNormalizationError
from app.models.contracts import CourseOffering, DataSource

__all__ = ["OfferingSnapshot", "SnapshotCourseDataProvider"]

#: 允许的 completeness 取值（`Literal` 只在类型检查期生效，运行期另行校验）。
_Completeness = Literal["partial", "complete"]
_ALLOWED_COMPLETENESS = ("partial", "complete")


def _class_key(offering: CourseOffering) -> tuple[str, str, str]:
    """判断"同一个教学班"的当前公共键。

    ⚠️ **不能按 `course_id` 去重** —— 一门课本来就可以有多个教学班。
    """

    return (offering.semester, offering.course_id, offering.class_id)


@dataclass(frozen=True)
class OfferingSnapshot:
    """某一学期的教学班快照（Course Data 内部对象）。

    - `semester` —— 本快照对应的学期；
    - `offerings` —— 该学期的教学班（**全部**都必须 `semester` 一致、`data_source = real`）；
    - `completeness` —— `"partial"` 或 `"complete"`；
    - `reported_total` —— 上游报告的该学期总教学班数（`complete` 时必填）。

    构造时即完成全部一致性校验；不合法直接
    `CourseDataNormalizationError`，**不静默修正、不静默丢数据**。
    """

    semester: str
    offerings: tuple[CourseOffering, ...]
    completeness: _Completeness
    reported_total: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.semester, str) or not self.semester.strip():
            raise CourseDataNormalizationError(
                f"snapshot.semester 必须是非空字符串：{self.semester!r}"
            )

        if self.completeness not in _ALLOWED_COMPLETENESS:
            raise CourseDataNormalizationError(
                f"completeness 只能是 {_ALLOWED_COMPLETENESS}，实际是 {self.completeness!r}"
            )

        # 冻结 dataclass 仍是"名义不可变"：把传入的 list 真正固化成 tuple，
        # 避免外部持有同一个 list 后继续增删，让快照悄悄变样。
        if not isinstance(self.offerings, tuple):
            object.__setattr__(self, "offerings", tuple(self.offerings))

        if self.reported_total is not None:
            if isinstance(self.reported_total, bool) or not isinstance(self.reported_total, int):
                raise CourseDataNormalizationError(
                    f"reported_total 必须是整数或 None，实际是 "
                    f"{type(self.reported_total).__name__}：{self.reported_total!r}"
                )
            if self.reported_total < 0:
                raise CourseDataNormalizationError(
                    f"reported_total 不能为负：{self.reported_total!r}"
                )

        loaded_count = len(self.offerings)

        seen: set[tuple[str, str, str]] = set()
        for offering in self.offerings:
            if not isinstance(offering, CourseOffering):
                raise CourseDataNormalizationError(
                    f"snapshot 只能包含 CourseOffering，实际混入 {type(offering).__name__}"
                )
            if offering.semester != self.semester:
                raise CourseDataNormalizationError(
                    f"snapshot({self.semester}) 混入了其它学期的教学班："
                    f"{offering.class_id} → {offering.semester}"
                )
            if offering.data_source is not DataSource.REAL:
                raise CourseDataNormalizationError(
                    f"真实 snapshot 不得混入 data_source="
                    f"{offering.data_source.value!r} 的教学班：{offering.class_id}"
                )

            key = _class_key(offering)
            if key in seen:
                # ⛔ 不静默保留第一条：同一教学班出现两次说明上游或解析有问题。
                raise CourseDataNormalizationError(
                    f"snapshot 中出现重复教学班（semester, course_id, class_id）：{key}"
                )
            seen.add(key)

        if self.completeness == "complete":
            if self.reported_total is None:
                raise CourseDataNormalizationError(
                    "completeness='complete' 时必须提供 reported_total，"
                    "否则无法证明快照是完整的"
                )
            if self.reported_total != loaded_count:
                raise CourseDataNormalizationError(
                    f"completeness='complete' 但 reported_total({self.reported_total}) "
                    f"≠ loaded_count({loaded_count})"
                )
        else:
            if self.reported_total is not None and self.reported_total < loaded_count:
                raise CourseDataNormalizationError(
                    f"reported_total({self.reported_total}) 不能小于已加载数量({loaded_count})"
                )

    @property
    def loaded_count(self) -> int:
        """已加载的教学班数量。"""

        return len(self.offerings)

    @property
    def is_complete(self) -> bool:
        """本快照是否**已被证明**为该学期的完整快照。"""

        return self.completeness == "complete"


class SnapshotCourseDataProvider:
    """production `CourseDataProvider` 的最小落点。

    - 持有一个**已经标准化好**的 `OfferingSnapshot`；
    - `get_course_offerings(semester)`：学期匹配则返回该学期教学班，否则返回 `[]`；
    - ⛔ **不做网络请求**，⛔ **不自动 fallback 到 Mock**。

      "查不到"就如实返回空列表 —— 这是数据事实，不是错误。

    结构上满足 Phase 2B-1 冻结的 `CourseDataProvider`（`docs/interfaces/integration.md`），
    但**不继承、不修改**该 Protocol。
    """

    def __init__(self, snapshot: OfferingSnapshot) -> None:
        if not isinstance(snapshot, OfferingSnapshot):
            raise CourseDataNormalizationError(
                f"SnapshotCourseDataProvider 只接受 OfferingSnapshot，"
                f"实际是 {type(snapshot).__name__}"
            )
        self._snapshot = snapshot

    @property
    def snapshot(self) -> OfferingSnapshot:
        """只读地暴露持有的快照（`OfferingSnapshot` 本身不可变）。"""

        return self._snapshot

    def get_course_offerings(self, semester: str) -> list[CourseOffering]:
        """返回**该学期**的教学班列表；学期不匹配时返回空列表。"""

        if semester != self._snapshot.semester:
            return []

        # 返回一份新的 list：内容与顺序原样，但调用方无法改动内部快照。
        return list(self._snapshot.offerings)
