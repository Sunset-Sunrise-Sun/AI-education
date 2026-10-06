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

## 多 shard 合并（2026-1 深分页异常的应对）

学校接口在 **offset >= 6500** 稳定返回 `HTTP 600 {"code":50015000,...}`。
Architecture Review 裁决（**方案 B**）：

```text
五个独立 shard bundle（各自是真实捕获的分页流）
        ↓  各自走现有 collect_captured_pages_snapshot()
   五个 OfferingSnapshot
        ↓  merge_offering_snapshots([...], baseline_total=<baseline>)
   合并后的 complete OfferingSnapshot
```

⛔ **不重编号 / 不重切分 / 不生成伪连续全局 pages**
（那会伪造一个学校从未返回过的分页流，已被明确否决）；
⛔ **不改 Capture Bundle format**。

本模块**零网络**：没有 endpoint、没有 Cookie / Session / Token、没有 crawler。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.course_data.errors import CourseDataNormalizationError
from app.models.contracts import CourseOffering, DataSource

__all__ = [
    "OfferingSnapshot",
    "SnapshotCourseDataProvider",
    "merge_offering_snapshots",
]

#: 允许的 completeness 取值（`Literal` 只在类型检查期生效，运行期另行校验）。
_Completeness = Literal["partial", "complete"]
_ALLOWED_COMPLETENESS = ("partial", "complete")


def _class_key(offering: CourseOffering) -> tuple[str, str, str]:
    """判断"同一个教学班"的当前公共键。

    ⚠️ **不能按 `course_id` 去重** —— 一门课本来就可以有多个教学班。
    """

    return (offering.semester, offering.course_id, offering.class_id)


def _reportable_identity(offering: CourseOffering) -> str:
    """跨 shard 重复时**只报告最小 identity**。

    用公共字段名（`course_id` / `class_id`），⛔ 不回显课程名 / 教师 / 容量
    等无关内容。
    """

    return (
        f"semester={offering.semester} "
        f"course_id={offering.course_id} "
        f"class_id={offering.class_id}"
    )


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


def merge_offering_snapshots(
    snapshots: Sequence[OfferingSnapshot],
    *,
    baseline_total: int,
) -> OfferingSnapshot:
    """把**多个 shard 的 `OfferingSnapshot`** 合并成一份 `complete` 快照。

    背景（2026-1 真实证据）：学校接口在 **offset >= 6500** 稳定返回
    `HTTP 600 {"code":50015000,"message":"系统异常"}`。
    ⇒ 不绕过深分页，改为按**已确认的校区维度**分片：每个 shard 各自独立分页，
    各自走**现有的** `collect_captured_pages_snapshot()`，最后在此合并。

    ⛔ **本函数不接触 Capture Bundle 格式**：
    它只消费已经由现有入口产出的 `OfferingSnapshot`，
    ⛔ **不重编号 / 不重切分 / 不生成任何伪连续全局 pages**
    （那属于被明确否决的方案 A）。

    合并成功**必须同时满足**（任一不满足 → `CourseDataNormalizationError`，fail closed）：

    ```text
    1. 至少一个 shard
    2. 所有 shard semester 一致
    3. 每个 shard is_complete == True            （即 completeness == "complete"）
    4. 每个 shard loaded_count == reported_total （由 OfferingSnapshot 自身保证，此处复核）
    5. sum_shard_reported_total == baseline_total
    6. total_loaded_rows == sum_shard_reported_total
    7. duplicate_identity_count == 0             （校区 shard 视为**互斥分区**）
    8. unique_identity_count == baseline_total
    ```

    `identity = (semester, courseNum, classNumber)` —— 即公共
    `(semester, course_id, class_id)`。⛔ **不得只按 `course_id` 去重**。

    ⚠️ 任一 shard 不完整（partial）时**不合并**：⛔ 不允许"其余几个校区先算成功"。
    ⚠️ 跨 shard 重复 → fail closed，错误信息只报告**最小 identity + 两个 shard 名**，
    ⛔ **不静默去重后继续声称 complete**。

    ⚠️ 这是 Course Data **内部**函数：不进 `schemas/`、不进 `docs/interfaces/`、
    不进 Provider / API，也不是新的公共 Schema。
    """

    if isinstance(snapshots, (str, bytes)) or not isinstance(snapshots, Sequence):
        raise CourseDataNormalizationError(
            f"snapshots 必须是 OfferingSnapshot 序列，实际是 {type(snapshots).__name__}"
        )

    shard_list = list(snapshots)

    if not shard_list:
        raise CourseDataNormalizationError("merge 至少需要一个 shard snapshot")

    if isinstance(baseline_total, bool) or not isinstance(baseline_total, int):
        raise CourseDataNormalizationError(
            f"baseline_total 必须是整数，实际是 {type(baseline_total).__name__}"
        )
    if baseline_total < 0:
        raise CourseDataNormalizationError(f"baseline_total 不能为负：{baseline_total}")

    first = shard_list[0]
    if not isinstance(first, OfferingSnapshot):
        raise CourseDataNormalizationError(
            f"merge 只接受 OfferingSnapshot，实际是 {type(first).__name__}"
        )

    semester = first.semester
    sum_shard_reported_total = 0
    total_loaded_rows = 0

    #: identity → 第一个持有它的 shard 名（只存名字，用于重复报告）。
    seen: dict[tuple[str, str, str], str] = {}
    merged: list[CourseOffering] = []

    for index, snapshot in enumerate(shard_list):
        shard_name = f"shard[{index}]"

        if not isinstance(snapshot, OfferingSnapshot):
            raise CourseDataNormalizationError(
                f"{shard_name} 不是 OfferingSnapshot，实际是 {type(snapshot).__name__}"
            )

        # 条件 2：semester 一致。
        if snapshot.semester != semester:
            raise CourseDataNormalizationError(
                f"{shard_name} 的 semester({snapshot.semester}) 与 "
                f"shard[0]({semester}) 不一致；拒绝合并"
            )

        # 条件 3 + 4：每个 shard 必须自身完整且计数自洽。
        if not snapshot.is_complete:
            raise CourseDataNormalizationError(
                f"{shard_name} 不是 complete 快照"
                f"（completeness={snapshot.completeness!r}，"
                f"loaded_count={snapshot.loaded_count}，"
                f"reported_total={snapshot.reported_total}）；"
                f"任一 shard 不完整即整体失败，不允许『其余 shard 先算成功』"
            )

        if snapshot.reported_total is None or snapshot.loaded_count != snapshot.reported_total:
            raise CourseDataNormalizationError(
                f"{shard_name} 的 loaded_count({snapshot.loaded_count}) != "
                f"reported_total({snapshot.reported_total})；拒绝合并"
            )

        sum_shard_reported_total += snapshot.reported_total
        total_loaded_rows += snapshot.loaded_count

        # 条件 7：跨 shard 重复 identity → fail closed（不静默去重）。
        for offering in snapshot.offerings:
            identity = _class_key(offering)
            previous = seen.get(identity)
            if previous is not None:
                raise CourseDataNormalizationError(
                    f"跨 shard 出现重复教学班 identity：{_reportable_identity(offering)}"
                    f"（同时出现在 {previous} 与 {shard_name}）；"
                    f"校区 shard 应互斥，拒绝静默去重后继续"
                )
            seen[identity] = shard_name
            merged.append(offering)

    # 条件 5：各 shard reported_total 之和必须等于 baseline。
    if sum_shard_reported_total != baseline_total:
        raise CourseDataNormalizationError(
            f"各 shard reported_total 之和({sum_shard_reported_total}) != "
            f"baseline_total({baseline_total})；分片未覆盖全体或与 baseline 不一致，拒绝合并"
        )

    # 条件 6：累计行数必须等于各 shard total 之和。
    if total_loaded_rows != sum_shard_reported_total:
        raise CourseDataNormalizationError(
            f"total_loaded_rows({total_loaded_rows}) != "
            f"sum_shard_reported_total({sum_shard_reported_total})；拒绝合并"
        )

    unique_identity_count = len(seen)

    # 条件 8：唯一 identity 数必须等于 baseline。
    if unique_identity_count != baseline_total:
        raise CourseDataNormalizationError(
            f"unique_identity_count({unique_identity_count}) != "
            f"baseline_total({baseline_total})；覆盖不足或超出，拒绝合并"
        )

    # 到这里：8 条全部成立。merged 的 loaded_count == baseline_total == reported_total，
    # 因此 `OfferingSnapshot` 的 complete 不变量自然成立。
    return OfferingSnapshot(
        semester=semester,
        offerings=tuple(merged),
        completeness="complete",
        reported_total=baseline_total,
    )
