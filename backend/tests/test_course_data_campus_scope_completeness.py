"""校区范围 vs 学期完整性（Phase 5 审计；**纯 synthetic、零网络**）。

本文件锁定 Architecture Review 要求的**语义边界**：

```text
East / South / Shenzhen / Zhuhai 四个校区 complete
        ≠  full semester complete
```

只要 **North campus 处于 suspended**（真实 `HTTP 600` 证据、⛔ 不绕过），
就**不能**声称 semester 级完整 —— 除非 Architecture Review 另有正式裁定。

⛔ 本文件不访问网络、⛔ 不使用真实采集产物、⛔ 不新增 production API；
所有 row / 校区 / 计数均为人工虚构。

⚠️ 入口级的"缺 shard / 多 shard / 部分 shard"fail-closed 行为由既有
`test_course_data_sharded_capture.py` 覆盖；本文件只补**范围与完整性语义**。
"""

from __future__ import annotations

import pathlib

from app.course_data import OfferingSnapshot, merge_offering_snapshots
from app.course_data.store import (
    SnapshotScope,
    import_offering_snapshot,
    load_course_data_provenance,
    load_course_offerings,
)
from app.models.contracts import CourseOffering, DataSource

SEMESTER = "2026-1"

#: 已批准**五个** shard（⛔ suspended 的 North **仍在**已批准集合里）。
APPROVED_SHARD_IDS = ("东校园", "北校园", "南校园", "深圳校区", "珠海校区")

#: 当前**可采集**的四个校区（North suspended）。
CAPTURABLE_SHARD_IDS = ("东校园", "南校园", "深圳校区", "珠海校区")

SHARDED_CAPTURE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "app" / "course_data" / "sharded_capture.py"
)


def _offering(course_id: str, class_id: str) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name="示例课程",
        class_id=class_id,
        semester=SEMESTER,
        credit=3,
        meetings=[],
        data_source=DataSource.REAL,
    )


def _snapshot(shard_name: str, count: int, *, start: int = 0) -> OfferingSnapshot:
    offerings = tuple(
        _offering(f"C{start + index:04d}", f"{shard_name}-A{index:04d}")
        for index in range(count)
    )
    return OfferingSnapshot(
        semester=SEMESTER,
        offerings=offerings,
        completeness="complete",
        reported_total=count,
    )


def test_merge_lower_level_trusts_the_caller_baseline() -> None:
    """⚠️ **低层** `merge_offering_snapshots()` 信任调用方给出的 baseline。

    四个校区 + `baseline_total = Σ(4)` 在低层会被接受 ⇒
    "四个校区 == 完整学期"**不能**靠低层函数把关，
    必须走**已批准五 shard** 的入口 `collect_sharded_capture_set()`。
    本用例把这个 hazard 显式锁住（⛔ 不改变低层语义）。
    """

    four = [
        _snapshot(name, 3, start=index * 100)
        for index, name in enumerate(CAPTURABLE_SHARD_IDS)
    ]
    four_total = sum(item.reported_total or 0 for item in four)

    merged_four = merge_offering_snapshots(four, baseline_total=four_total)

    assert merged_four.is_complete is True  # ⚠️ 低层只看 baseline，**不知道** North 是否存在
    assert merged_four.loaded_count == four_total


def test_sharded_entry_point_has_no_suspended_or_skip_concept() -> None:
    """⛔ 已批准入口**没有**"跳过 / suspended"概念 ⇒ 四个校区无法升级为学期完整。"""

    source = SHARDED_CAPTURE_PATH.read_text(encoding="utf-8")

    for forbidden in ("suspended", "skip", "跳过", "optional_shard"):
        assert forbidden not in source, f"⛔ sharded 入口不得引入：{forbidden}"

    # 五个已批准 shard 仍然是入口的硬要求（缺一即 fail closed）
    assert "APPROVED_SHARD_IDS" in source
    assert len(APPROVED_SHARD_IDS) == 5
    assert "北校园" in APPROVED_SHARD_IDS


def test_campus_scoped_snapshot_is_complete_for_that_campus_only(tmp_path) -> None:
    """校区范围 artifact：`complete` **只对该校区成立**，不是学期级完整。"""

    store_path = tmp_path / "course-data.sqlite"
    campus = _snapshot("东校园", 4)

    import_offering_snapshot(
        store_path,
        campus,
        artifact_sha256="a" * 64,
        scope=SnapshotScope(scope_kind="campus", scope_id="5063559"),
    )

    offerings = load_course_offerings(store_path, semester=SEMESTER)
    assert len(offerings) == 4

    provenance = load_course_data_provenance(store_path)
    assert len(provenance) == 1
    assert provenance[0].scope_kind == "campus"
    assert provenance[0].scope_id == "5063559"
    # ⛔ provenance 只记录**声明式** scope，不产生任何"学期完整"结论
    assert provenance[0].scope_kind != "full_semester"


def test_four_campus_artifacts_never_claim_full_semester(tmp_path) -> None:
    """⛔ 四个校区 artifact 并排入库之后，仍然**没有**任何"学期完整"标记。"""

    store_path = tmp_path / "course-data.sqlite"

    for index, scope_id in enumerate(("5063559", "5062201", "333291143", "5062203")):
        import_offering_snapshot(
            store_path,
            _snapshot(f"campus-{index}", 2, start=index * 100),
            artifact_sha256=chr(ord("b") + index) * 64,
            scope=SnapshotScope(scope_kind="campus", scope_id=scope_id),
        )

    provenance = load_course_data_provenance(store_path)

    assert len(provenance) == 4
    assert {item.scope_kind for item in provenance} == {"campus"}
    assert {item.scope_id for item in provenance} == {
        "5063559",
        "5062201",
        "333291143",
        "5062203",
    }
    # ⛔ 四个 campus artifact 既不是 full_semester，也不产生任何全局 complete 声明
    assert all(item.scope_kind != "full_semester" for item in provenance)
    assert len(load_course_offerings(store_path, semester=SEMESTER)) == 8


def test_full_semester_scope_still_requires_explicit_declaration(tmp_path) -> None:
    """✅ `full_semester` 只能是**显式声明**；⛔ 不从 source / 文件名 / 校区数推断。"""

    store_path = tmp_path / "course-data.sqlite"

    import_offering_snapshot(
        store_path,
        _snapshot("全量", 5),
        artifact_sha256="f" * 64,
        scope=SnapshotScope(scope_kind="full_semester", scope_id=SEMESTER),
    )

    provenance = load_course_data_provenance(store_path)
    assert provenance[0].scope_kind == "full_semester"
    assert provenance[0].scope_id == SEMESTER
    # ⚠️ 这是**调用方声明**，不是"North 已被采集"的证据
    assert len(APPROVED_SHARD_IDS) == 5
