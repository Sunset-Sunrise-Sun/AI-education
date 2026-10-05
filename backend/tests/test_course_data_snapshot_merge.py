"""`merge_offering_snapshots()` 测试（2026-1 五校区分片合并，**纯 synthetic、零网络**）。

背景：学校接口在 **offset >= 6500** 稳定返回
`HTTP 600 {"code":50015000,"message":"系统异常"}`。
Architecture Review 裁决采用 **方案 B**：

```text
五个独立 shard bundle（各自是真实捕获的分页流，**不重编号、不重切分**）
        ↓  各自走现有 collect_captured_pages_snapshot()
   五个 OfferingSnapshot
        ↓  merge_offering_snapshots([...], baseline_total=<baseline>)
   合并后的 complete OfferingSnapshot
```

⛔ 本文件**不访问网络**、⛔ 不使用真实采集产物；
所有 row / 校区 / 计数均为**人工虚构**（结构与真实一致，数字不等于真实分片值）。

⚠️ 真实分片参数（校区 id 与各校区 total）**只作验收参考**，
⛔ **不得**写进本文件当作断言常量 —— 真实采集一律以**本次响应**为准。
"""

from __future__ import annotations

import pytest

from app.course_data import (
    CourseDataNormalizationError,
    OfferingSnapshot,
    merge_offering_snapshots,
)
from app.models.contracts import CourseOffering, DataSource

SEMESTER = "2026-1"


def _offering(course_id: str, class_id: str, *, course_name: str = "示例课程") -> CourseOffering:
    """一条人工虚构教学班（`meetings = []` 合法，DG-07A 起）。"""

    return CourseOffering(
        course_id=course_id,
        course_name=course_name,
        class_id=class_id,
        semester=SEMESTER,
        credit=3,
        meetings=[],
        data_source=DataSource.REAL,
    )


def _shard(name: str, count: int, *, start: int = 0, complete: bool = True) -> OfferingSnapshot:
    """构造一个 shard 快照：`count` 条**全局唯一** identity。

    `start` 用于让不同 shard 的 identity 不重叠。
    """

    offerings = tuple(
        _offering(f"C{start + index:04d}", f"{name}-A{index:04d}")
        for index in range(count)
    )
    return OfferingSnapshot(
        semester=SEMESTER,
        offerings=offerings,
        completeness="complete" if complete else "partial",
        reported_total=count,
    )


def _five_shards() -> list[OfferingSnapshot]:
    """五个互斥 shard（覆盖 2 + 1 + 4 + 2 + 3 = 12）。"""

    return [
        _shard("东", 2, start=0),
        _shard("北", 1, start=2),
        _shard("南", 4, start=3),
        _shard("深圳", 2, start=7),
        _shard("珠海", 3, start=9),
    ]


# ---------------------------------------------------------------------------
# 1. 五 shard 全成功 → success
# ---------------------------------------------------------------------------


def test_five_shards_merge_into_complete_snapshot() -> None:
    shards = _five_shards()
    baseline = sum(s.reported_total for s in shards)  # 12

    merged = merge_offering_snapshots(shards, baseline_total=baseline)

    assert merged.is_complete is True
    assert merged.completeness == "complete"
    assert merged.loaded_count == baseline
    assert merged.reported_total == baseline
    assert merged.semester == SEMESTER


def test_merge_preserves_every_offering_and_shard_order() -> None:
    """合并**不丢行、不改顺序**：先 shard[0] 全部，再 shard[1]……"""

    shards = _five_shards()
    baseline = sum(s.reported_total for s in shards)

    merged = merge_offering_snapshots(shards, baseline_total=baseline)

    merged_keys = [(o.semester, o.course_id, o.class_id) for o in merged.offerings]
    expected_keys = [
        (o.semester, o.course_id, o.class_id) for s in shards for o in s.offerings
    ]
    assert merged_keys == expected_keys


def test_merge_accepts_single_shard() -> None:
    (merged,) = [merge_offering_snapshots([_shard("东", 3)], baseline_total=3)]

    assert merged.loaded_count == 3
    assert merged.is_complete is True


# ---------------------------------------------------------------------------
# 2. baseline 漂移 → fail
# ---------------------------------------------------------------------------


def test_baseline_drift_sum_greater_than_baseline_fails() -> None:
    """`Σ shard reported_total > baseline`（baseline 变小 / 分片口径不符）→ fail。"""

    shards = _five_shards()

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        merge_offering_snapshots(shards, baseline_total=11)  # 实际 Σ = 12

    assert "baseline_total" in str(excinfo.value)


def test_baseline_drift_sum_less_than_baseline_fails() -> None:
    """`Σ shard reported_total < baseline`（覆盖不足）→ fail。"""

    shards = _five_shards()

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        merge_offering_snapshots(shards, baseline_total=13)  # 实际 Σ = 12

    assert "baseline_total" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 3. 任一 shard partial → fail
# ---------------------------------------------------------------------------


def test_any_partial_shard_fails_whole_merge() -> None:
    """任一 shard 不完整 → 整体失败，⛔ 不允许"其余 shard 先算成功"。"""

    shards = _five_shards()
    # 把第 3 个 shard 换成 partial（reported_total 大于已加载数）
    shards[2] = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_offering("C9001", "南-A9001"),),
        completeness="partial",
        reported_total=500,
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        merge_offering_snapshots(shards, baseline_total=12)

    message = str(excinfo.value)
    assert "shard[2]" in message
    assert "complete" in message


def test_partial_shard_fails_even_when_others_are_complete() -> None:
    """明确锁定：**四个 complete + 一个 partial** 也不得合并成功。"""

    complete_shards = _five_shards()[:4]
    partial = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(),
        completeness="partial",
        reported_total=7,
    )

    with pytest.raises(CourseDataNormalizationError):
        merge_offering_snapshots([*complete_shards, partial], baseline_total=12)


# ---------------------------------------------------------------------------
# 4. shard 计数不自洽 / total 中途变化 → fail
# ---------------------------------------------------------------------------


def test_shard_loaded_count_mismatch_fails() -> None:
    """`loaded_count != reported_total`：`OfferingSnapshot` 自身即拒绝构造。

    这对应"某一页 total 中途变化 / 提前停滞"—— 该 shard 根本无法成为
    `complete` 快照，因此合并前就已 fail closed。
    """

    with pytest.raises(CourseDataNormalizationError):
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(_offering("C1", "A1"),),
            completeness="complete",
            reported_total=2,  # ≠ loaded_count(1)
        )


def test_shard_total_change_between_pages_is_not_mergeable() -> None:
    """模拟"某 shard 第一页报 total=3、实际只取到 1 条" → 合并被拒绝。"""

    good = _shard("东", 2, start=0)
    # 该 shard 第一页声称 total=3，但只取到 1 条 → 只能是 partial
    stalled = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_offering("C0002", "北-A0000"),),
        completeness="partial",
        reported_total=3,
    )

    with pytest.raises(CourseDataNormalizationError):
        merge_offering_snapshots([good, stalled], baseline_total=3)


def test_semester_mismatch_between_shards_fails() -> None:
    """shard 之间 semester 不一致 → fail。"""

    a = _shard("东", 2, start=0)
    # 该 shard 的 semester 与 shard[0] 不同（其 offering 也须同 semester，
    # 否则先被 OfferingSnapshot 自身拒绝）
    other_semester_offering = CourseOffering(
        course_id="C9999",
        course_name="示例课程",
        class_id="北-A9999",
        semester="2025-2",
        credit=3,
        meetings=[],
        data_source=DataSource.REAL,
    )
    b = OfferingSnapshot(
        semester="2025-2",
        offerings=(other_semester_offering,),
        completeness="complete",
        reported_total=1,
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        merge_offering_snapshots([a, b], baseline_total=3)

    assert "semester" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 5. 跨 shard duplicate identity → fail（报告最小 identity + shard 名）
# ---------------------------------------------------------------------------


def test_cross_shard_duplicate_identity_fails_closed() -> None:
    """校区 shard 应互斥；出现同一 `(semester, courseNum, classNumber)` → fail。"""

    duplicated = _offering("C0000", "东-A0000")
    shard_a = OfferingSnapshot(
        semester=SEMESTER, offerings=(duplicated,), completeness="complete", reported_total=1
    )
    shard_b = OfferingSnapshot(
        semester=SEMESTER, offerings=(duplicated,), completeness="complete", reported_total=1
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        merge_offering_snapshots([shard_a, shard_b], baseline_total=2)

    message = str(excinfo.value)
    # 报告最小 identity
    assert "C0000" in message
    assert "东-A0000" in message
    # 报告两个 shard 名
    assert "shard[0]" in message
    assert "shard[1]" in message


def test_duplicate_report_does_not_echo_course_name_or_teacher() -> None:
    """重复报告只含 identity，⛔ 不回显课程名等无关内容。"""

    a = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_offering("C1", "A1", course_name="不该出现的课程名"),),
        completeness="complete",
        reported_total=1,
    )
    b = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_offering("C1", "A1", course_name="不该出现的课程名"),),
        completeness="complete",
        reported_total=1,
    )

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        merge_offering_snapshots([a, b], baseline_total=2)

    assert "不该出现的课程名" not in str(excinfo.value)


def test_same_course_different_class_is_not_a_duplicate() -> None:
    """同一门课的**不同教学班**不是重复（⛔ 不得只按 course_id 去重）。"""

    a = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_offering("C1", "A1"),),
        completeness="complete",
        reported_total=1,
    )
    b = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_offering("C1", "A2"),),
        completeness="complete",
        reported_total=1,
    )

    merged = merge_offering_snapshots([a, b], baseline_total=2)

    assert merged.loaded_count == 2


# ---------------------------------------------------------------------------
# 6. merged unique < / > baseline → fail
# ---------------------------------------------------------------------------


def test_merged_unique_less_than_baseline_fails() -> None:
    """唯一 identity 数 < baseline（覆盖不足）→ fail。"""

    shards = _five_shards()

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        merge_offering_snapshots(shards, baseline_total=13)

    assert "baseline_total" in str(excinfo.value)


def test_merged_unique_greater_than_baseline_fails() -> None:
    """唯一 identity 数 > baseline（shard 计数虚高）→ fail。"""

    shards = _five_shards()

    with pytest.raises(CourseDataNormalizationError) as excinfo:
        merge_offering_snapshots(shards, baseline_total=11)

    assert "baseline_total" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 7. 输入与基线参数校验
# ---------------------------------------------------------------------------


def test_empty_shard_list_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        merge_offering_snapshots([], baseline_total=0)


@pytest.mark.parametrize("baseline", [None, "12", 12.0, True, -1])
def test_invalid_baseline_is_rejected(baseline: object) -> None:
    with pytest.raises(CourseDataNormalizationError):
        merge_offering_snapshots([_shard("东", 1)], baseline_total=baseline)  # type: ignore[arg-type]


def test_non_snapshot_input_is_rejected() -> None:
    with pytest.raises(CourseDataNormalizationError):
        merge_offering_snapshots([{"not": "a snapshot"}], baseline_total=1)  # type: ignore[list-item]


def test_merged_result_is_usable_by_provider() -> None:
    """合并结果必须能被**现有** Provider 落点直接持有（不改 Provider）。"""

    from app.course_data import SnapshotCourseDataProvider

    shards = _five_shards()
    baseline = sum(s.reported_total for s in shards)
    merged = merge_offering_snapshots(shards, baseline_total=baseline)

    provider = SnapshotCourseDataProvider(merged)

    assert len(provider.get_course_offerings(SEMESTER)) == baseline
    assert provider.get_course_offerings("2099-9") == []
