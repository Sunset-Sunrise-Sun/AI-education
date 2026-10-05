"""Sharded Capture-Set Orchestration 测试（**纯 synthetic、零网络、零真实采集**）。

覆盖 Architecture Review 要求编排层负责的全部条件：

```text
baseline_before == baseline_after（对拍在调用方；本层只接受一个已确认 baseline）
shard 集合恰好为五个已批准校区：无缺 / 无多余 / 无重复
每个 bundle 独立 complete
每个 shard semester == 2026-1
merge 后完整性全部成立（含跨 shard 无重复、unique == baseline）
duplicate 检查同时覆盖：**同 shard 内** 与 **跨 shard**
```

⚠️ 所有 row / 计数均为**人工虚构**；真实分片数字（1071/405/…）**不**进本文件，
⛔ 也不作断言常量。
"""

from __future__ import annotations

import json

import pytest

from app.course_data import (
    APPROVED_SHARD_IDS,
    CAPTURE_FORMAT,
    CourseDataNormalizationError,
    OfferingSnapshot,
    ShardedCaptureError,
    ShardedCaptureSet,
    ShardSource,
    SnapshotCourseDataProvider,
    collect_sharded_capture_set,
)
from app.course_data.captured_pages import CAPTURE_FORMAT as _CAPTURE_FORMAT_CHECK
from app.models.contracts import CourseOffering, DataSource

SEMESTER = "2026-1"
PAGE_SIZE = 200

#: 人工虚构的 schedule 文本（结构与真实一致，取值无关）。
SCHEDULE = "1-8周/星期五/第5-6节/示例教师/示例环节"


def _row(class_number: str) -> dict[str, object]:
    return {
        "courseNum": "00000000",
        "courseName": "示例课程",
        "classNumber": class_number,
        "yearTerm": SEMESTER,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": SCHEDULE,
    }


def _bundle(class_numbers: list[str], *, total: int | None = None) -> dict[str, object]:
    """把一个 shard 的若干教学班装成**一个**合法 Capture Bundle（单页足够）。"""

    if total is None:
        total = len(class_numbers)

    return {
        "format": CAPTURE_FORMAT,
        "semester": SEMESTER,
        "first_page_no": 1,
        "page_size": PAGE_SIZE,
        "pages": [
            {
                "page_no": 1,
                "response": {
                    "code": 200,
                    "data": {"total": total, "rows": [_row(c) for c in class_numbers]},
                },
            }
        ],
    }


def _shard_ids(prefix: str, count: int) -> list[str]:
    return [f"{prefix}-{index:04d}" for index in range(count)]


#: 五个 shard 各多少条（合计 12）—— 人工虚构，与真实分片数值无关。
SHARD_SIZES: dict[str, int] = {
    "东校园": 2,
    "北校园": 1,
    "南校园": 4,
    "深圳校区": 2,
    "珠海校区": 3,
}
TOTAL = sum(SHARD_SIZES.values())  # 12


def _sources() -> list[ShardSource]:
    return [
        ShardSource(shard_id=name, bundle=_bundle(_shard_ids(name, size)))
        for name, size in SHARD_SIZES.items()
    ]


def _baseline(total: int = TOTAL, *, semester: str = SEMESTER) -> list[OfferingSnapshot]:
    """baseline：不带分片筛选的**全量**快照（人工虚构，`total` 可覆盖以模拟漂移）。"""

    # baseline 的 identity 与各 shard 的**不同**：它只用来提供计数。
    baseline_offerings = tuple(
        CourseOffering(
            course_id=f"BASE{index:04d}",
            course_name="示例课程",
            class_id=f"BASE-{index:04d}",
            semester=semester,
            credit=3,
            meetings=[],
            data_source=DataSource.REAL,
        )
        for index in range(total)
    )
    return [
        OfferingSnapshot(
            semester=semester,
            offerings=baseline_offerings,
            completeness="complete",
            reported_total=total,
        )
    ]


def _snapshot(prefix: str, count: int, *, complete: bool = True) -> OfferingSnapshot:
    """直接构造一个 shard 快照（用于不经 bundle 的边界用例）。"""

    offerings = tuple(
        CourseOffering(
            course_id=f"C{index:04d}",
            course_name="示例课程",
            class_id=f"{prefix}-{index:04d}",
            semester=SEMESTER,
            credit=3,
            meetings=[],
            data_source=DataSource.REAL,
        )
        for index in range(count)
    )
    return OfferingSnapshot(
        semester=SEMESTER,
        offerings=offerings,
        completeness="complete" if complete else "partial",
        reported_total=count,
    )


# ---------------------------------------------------------------------------
# 1. 五 shard 全成功
# ---------------------------------------------------------------------------


def test_five_approved_shards_produce_merged_complete_snapshot() -> None:
    result = collect_sharded_capture_set(
        shard_sources=_sources(),
        baseline=_baseline(),
        expected_semester=SEMESTER,
    )

    assert len(result.shards) == len(APPROVED_SHARD_IDS) == 5
    assert result.merged.is_complete is True
    assert result.merged.loaded_count == TOTAL
    assert result.merged.reported_total == TOTAL
    assert result.baseline_reported_total == TOTAL
    assert result.baseline_loaded_count == TOTAL
    assert result.sum_shard_reported_total == TOTAL
    assert result.total_loaded_rows == TOTAL
    assert result.unique_identity_count == TOTAL


def test_merge_order_is_fixed_to_approved_order() -> None:
    """调用方传入顺序被规范化成已批准顺序（可复现）。"""

    shuffled = list(reversed(_sources()))

    result = collect_sharded_capture_set(
        shard_sources=shuffled,
        baseline=_baseline(),
        expected_semester=SEMESTER,
    )

    merged_ids = [o.class_id for o in result.merged.offerings]
    expected_first_shard_ids = _shard_ids(APPROVED_SHARD_IDS[0], SHARD_SIZES[APPROVED_SHARD_IDS[0]])
    assert merged_ids[: len(expected_first_shard_ids)] == expected_first_shard_ids


def test_merged_result_is_usable_by_existing_provider() -> None:
    result = collect_sharded_capture_set(
        shard_sources=_sources(),
        baseline=_baseline(),
        expected_semester=SEMESTER,
    )

    provider = SnapshotCourseDataProvider(result.merged)

    assert len(provider.get_course_offerings(SEMESTER)) == TOTAL
    assert provider.get_course_offerings("2099-9") == []


def test_result_is_sharded_capture_set_with_reconciliation_counts() -> None:
    """返回值是内部编排对象，且四个对账计数与输入自洽。"""

    result = collect_sharded_capture_set(
        shard_sources=_sources(),
        baseline=_baseline(),
        expected_semester=SEMESTER,
    )

    assert isinstance(result, ShardedCaptureSet)
    assert [snapshot.semester for snapshot in result.shards] == [SEMESTER] * len(
        APPROVED_SHARD_IDS
    )
    assert result.baseline_loaded_count == result.baseline_reported_total == TOTAL
    assert result.sum_shard_reported_total == TOTAL
    assert result.total_loaded_rows == TOTAL
    assert result.unique_identity_count == TOTAL


def test_sharded_capture_error_is_a_course_data_normalization_error() -> None:
    """⛔ 不发明新的顶层错误类型：调用方按既有基类一处捕获即可。"""

    assert issubclass(ShardedCaptureError, CourseDataNormalizationError)

    with pytest.raises(CourseDataNormalizationError):
        collect_sharded_capture_set(
            shard_sources=[], baseline=_baseline(), expected_semester=SEMESTER
        )


# ---------------------------------------------------------------------------
# 2. shard 集合：无缺 / 无多余 / 无重复
# ---------------------------------------------------------------------------


def test_missing_shard_fails() -> None:
    sources = [s for s in _sources() if s.shard_id != "南校园"]

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    assert "缺少已批准 shard" in str(excinfo.value)
    assert "南校园" in str(excinfo.value)


def test_extra_shard_fails() -> None:
    sources = [*_sources(), ShardSource(shard_id="未批准校区", bundle=_bundle(["X-0001"]))]

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    assert "未批准" in str(excinfo.value)


def test_duplicate_shard_id_fails() -> None:
    sources = [*_sources(), ShardSource(shard_id="东校园", bundle=_bundle(["Y-0001"]))]

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    assert "重复的 shard" in str(excinfo.value)


def test_empty_shard_list_fails() -> None:
    with pytest.raises(ShardedCaptureError):
        collect_sharded_capture_set(
            shard_sources=[], baseline=_baseline(), expected_semester=SEMESTER
        )


# ---------------------------------------------------------------------------
# 3. 每个 bundle 独立 complete
# ---------------------------------------------------------------------------


def test_partial_shard_bundle_fails() -> None:
    """某 bundle 自报 total 大于实际行数 → partial → 整体失败。"""

    sources = _sources()
    sources[0] = ShardSource(
        shard_id="东校园",
        # 声称 total=99 但只给 1 行 → partial
        bundle=_bundle(["东校园-0000"], total=99),
    )

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    assert "东校园" in str(excinfo.value)


def test_four_complete_plus_one_partial_fails() -> None:
    sources = _sources()
    sources[-1] = ShardSource(
        shard_id="珠海校区", bundle=_bundle(["珠海校区-0000"], total=3)
    )

    with pytest.raises(ShardedCaptureError):
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )


def test_shard_with_malformed_bundle_fails() -> None:
    """bundle 结构不合法 → 编排层包装为 ShardedCaptureError，不回显内容。"""

    sources = _sources()
    sources[1] = ShardSource(shard_id="北校园", bundle={"format": "wrong-format"})

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    message = str(excinfo.value)
    assert "北校园" in message
    # ⛔ 不暴露完整路径
    assert ":\\" not in message and "/home/" not in message


# ---------------------------------------------------------------------------
# 4. semester 校验
# ---------------------------------------------------------------------------


def test_shard_semester_mismatch_fails() -> None:
    sources = _sources()
    wrong = _bundle(["北校园-0000"])
    wrong["semester"] = "2025-2"
    wrong["pages"][0]["response"]["data"]["rows"][0]["yearTerm"] = "2025-2"
    sources[1] = ShardSource(shard_id="北校园", bundle=wrong)

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    assert "semester" in str(excinfo.value)


def test_baseline_semester_mismatch_fails() -> None:
    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=_sources(),
            baseline=_baseline(semester="2025-2"),
            expected_semester=SEMESTER,
        )

    message = str(excinfo.value)
    assert "baseline" in message
    assert "2025-2" in message


@pytest.mark.parametrize("bad_semester", ["", "   ", None])
def test_invalid_expected_semester_is_rejected(bad_semester: object) -> None:
    with pytest.raises(ShardedCaptureError):
        collect_sharded_capture_set(
            shard_sources=_sources(),
            baseline=_baseline(),
            expected_semester=bad_semester,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# 5. baseline 漂移 / 计数不自洽
# ---------------------------------------------------------------------------


def test_baseline_after_drift_fails() -> None:
    """baseline 变小（Σ shard > baseline）→ fail（对拍不等价）。

    断言失败**归因于覆盖性**（Σ shard 与 baseline 不一致），
    而不是被下游 merge 的 unique 校验顺手拦下 —— 否则这条前置检查就是摆设。
    """

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=_sources(), baseline=_baseline(TOTAL - 1), expected_semester=SEMESTER
        )

    message = str(excinfo.value)
    assert "baseline" in message
    assert "分片未覆盖全体或与基线不一致" in message
    assert str(TOTAL) in message and str(TOTAL - 1) in message


def test_baseline_after_growth_fails() -> None:
    """baseline 变大（Σ shard < baseline，覆盖不足）→ fail。"""

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=_sources(), baseline=_baseline(TOTAL + 1), expected_semester=SEMESTER
        )

    message = str(excinfo.value)
    assert "分片未覆盖全体或与基线不一致" in message


def test_baseline_must_be_exactly_one_snapshot() -> None:
    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=_sources(),
            baseline=[*_baseline(), *_baseline()],
            expected_semester=SEMESTER,
        )

    assert "恰好" in str(excinfo.value)


def test_baseline_partial_fails() -> None:
    baseline = [
        OfferingSnapshot(
            semester=SEMESTER,
            offerings=(),
            completeness="partial",
            reported_total=TOTAL,
        )
    ]

    with pytest.raises(ShardedCaptureError):
        collect_sharded_capture_set(
            shard_sources=_sources(), baseline=baseline, expected_semester=SEMESTER
        )


# ---------------------------------------------------------------------------
# 6. duplicate 检查：同 shard 内 与 跨 shard
# ---------------------------------------------------------------------------


def test_duplicate_within_shard_fails() -> None:
    """**同 shard 内**重复 identity → fail closed。"""

    sources = _sources()
    # 同 classNumber 出现两次（不同 courseName 以避免无关干扰）
    duplicated = _bundle(["东校园-0000", "东校园-0000"], total=2)
    sources[0] = ShardSource(shard_id="东校园", bundle=duplicated)

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    assert "东校园" in str(excinfo.value)


def test_duplicate_across_shards_fails() -> None:
    """**跨 shard** 重复 identity → fail closed，且两个 shard 都可定位。

    下层 `merge_offering_snapshots()` 只报**位置下标**（`shard[0]` / `shard[1]`），
    编排层负责把它还原成**校区名**（这是本层独有的信息）。
    """

    sources = _sources()
    clash = _bundle(["东校园-0000"], total=1)  # 与东校园已有 identity 冲突
    sources[1] = ShardSource(shard_id="北校园", bundle=clash)

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    message = str(excinfo.value)
    # identity 本身可读
    assert "东校园-0000" in message
    # 下标 → 校区名 的还原表
    assert "shard[0]=东校园" in message
    assert "shard[1]=北校园" in message
    # 冲突发生的两个位置下标（来自下层）
    assert "shard[0]" in message and "shard[1]" in message


def test_duplicate_report_does_not_echo_course_name() -> None:
    sources = _sources()
    clash = _bundle(["东校园-0000"], total=1)
    clash["pages"][0]["response"]["data"]["rows"][0]["courseName"] = "不该出现的课程名"
    sources[1] = ShardSource(shard_id="北校园", bundle=clash)

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    assert "不该出现的课程名" not in str(excinfo.value)


def test_same_course_different_class_across_shards_is_allowed() -> None:
    """同一 `courseNum` 的**不同** `classNumber` **不算**重复（identity 含 classNumber）。"""

    sources = _sources()
    # 北校园只有 1 条：用与东校园相同的 courseNum、不同 classNumber
    same_course = _bundle(["北校园-9999"], total=1)
    for row in same_course["pages"][0]["response"]["data"]["rows"]:
        row["courseNum"] = "00000000"  # 与其它 shard 相同
    sources[1] = ShardSource(shard_id="北校园", bundle=same_course)

    result = collect_sharded_capture_set(
        shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
    )

    assert result.merged.loaded_count == TOTAL


# ---------------------------------------------------------------------------
# 7. 输入类型校验
# ---------------------------------------------------------------------------


def test_non_shard_source_input_is_rejected() -> None:
    with pytest.raises(ShardedCaptureError):
        collect_sharded_capture_set(
            shard_sources=[{"shard_id": "东校园"}],  # type: ignore[list-item]
            baseline=_baseline(),
            expected_semester=SEMESTER,
        )


def test_non_snapshot_baseline_is_rejected() -> None:
    with pytest.raises(ShardedCaptureError):
        collect_sharded_capture_set(
            shard_sources=_sources(),
            baseline=["not-a-snapshot"],  # type: ignore[list-item]
            expected_semester=SEMESTER,
        )


# ---------------------------------------------------------------------------
# 8. 文件路径入口（真实 bundle 文件 → load_capture_bundle）
# ---------------------------------------------------------------------------


def test_bundle_files_are_loaded_from_explicit_paths(tmp_path) -> None:
    """⛔ 不扫描目录：每份 bundle 必须**显式**给出路径。"""

    sources = []
    for name, size in SHARD_SIZES.items():
        path = tmp_path / f"{name}.json"
        path.write_text(
            json.dumps(_bundle(_shard_ids(name, size)), ensure_ascii=False), encoding="utf-8"
        )
        sources.append(ShardSource(shard_id=name, bundle=path))

    result = collect_sharded_capture_set(
        shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
    )

    assert result.merged.loaded_count == TOTAL
    assert result.merged.is_complete is True


def test_missing_bundle_file_fails_with_filename_only(tmp_path) -> None:
    sources = _sources()
    sources[0] = ShardSource(shard_id="东校园", bundle=tmp_path / "not-there.json")

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    message = str(excinfo.value)
    assert "not-there.json" in message
    # ⛔ 不暴露完整路径
    assert str(tmp_path) not in message


def test_unparsable_bundle_file_error_does_not_leak_path(tmp_path) -> None:
    """下层 JSON 解析错误带本地路径 → 编排层擦成文件名（⛔ 不泄漏目录）。"""

    bad = tmp_path / "bad-bundle.json"
    bad.write_text("{ not json", encoding="utf-8")

    sources = _sources()
    sources[0] = ShardSource(shard_id="东校园", bundle=bad)

    with pytest.raises(ShardedCaptureError) as excinfo:
        collect_sharded_capture_set(
            shard_sources=sources, baseline=_baseline(), expected_semester=SEMESTER
        )

    message = str(excinfo.value)
    assert "bad-bundle.json" in message
    assert str(tmp_path) not in message
    assert tmp_path.name not in message


def test_capture_format_constant_is_unchanged() -> None:
    """⛔ 本轮**未改** Capture Bundle format。"""

    assert CAPTURE_FORMAT == "sysu-opening-courses-capture-v1"
    assert _CAPTURE_FORMAT_CHECK == CAPTURE_FORMAT
