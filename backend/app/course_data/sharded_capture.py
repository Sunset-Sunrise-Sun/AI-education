"""Sharded Capture-Set Orchestration（Course Data **内部**能力，**零网络**）。

## 为什么需要它

2026-1 真实证据：学校接口在 **offset >= 6500** 稳定返回
`HTTP 600 {"code":50015000,"message":"系统异常"}`。
⇒ 不绕过深分页，改用**已确认的校区维度**分片；每个 shard 是**独立、真实捕获**的分页流。

Architecture Review 裁决（**方案 B**）：

```text
5 个独立 Capture Bundle（各自真实捕获，⛔ 不重编号 / 不重切分 / 不拼成伪单流）
        ↓  load_capture_bundle()            （现有入口）
        ↓  collect_captured_pages_snapshot()（现有入口）
   5 个 OfferingSnapshot（各自必须 complete）
        ↓  校验：恰好五个已批准校区 / 无缺 / 无多余 / semester 一致 / 基线与分片计数自洽
        ↓  merge_offering_snapshots(...)     （上一轮已 Review 通过）
   merged OfferingSnapshot
```

⛔ **本模块不改 Capture Bundle format**（它只**消费** bundle），
⛔ 不接触 `planning_runtime.py`，⛔ 不做 runtime manifest / provenance 格式设计
（那是后续独立决策）。

## 边界

- ✅ 负责：加载多个 bundle、校验 shard 集合与基线自洽、调用现有合并函数；
- ⛔ **不负责**：产出 runtime manifest、对 artifact 计算/校验 SHA-256 digest、
  决定谁有资格进入 production runtime（属 **PR #39 的 exact-artifact gate**）；
- ⛔ **不做**：重编号 / 重切分页码、retry、跳页、绕过深分页限制。

## 隐私

- ⛔ **不读取 / 不记录课程、教师、教室、学生任何取值**；
- 错误信息只暴露**结构性**内容：shard 名、`identity`（`semester` + `course_id` +
  `class_id`）、计数、以及 bundle 的**文件名**（⛔ 不含完整路径）；
- 下层（`captured_pages.py`）的错误信息可能带**本地文件路径**（那是给本地读取场景的），
  本层在转述前会把调用方给出的路径**擦成文件名**（见 `_scrub_paths()`），
  ⛔ 不让编排层的错误信息泄漏本机目录结构。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.course_data.captured_pages import (
    collect_captured_pages_snapshot,
    load_capture_bundle,
)
from app.course_data.errors import CourseDataNormalizationError
from app.course_data.snapshot import (
    OfferingSnapshot,
    _class_key,
    merge_offering_snapshots,
)
from app.models.contracts import CourseOffering

__all__ = [
    "APPROVED_SHARD_IDS",
    "SHARDED_CAPTURE_SOURCE",
    "ShardedCaptureError",
    "ShardedCaptureSet",
    "ShardSource",
    "collect_sharded_capture_set",
]

#: 分片来源标注（如实说明这批数据是**合并而来**，不是单次查询的产物）。
SHARDED_CAPTURE_SOURCE = "capture-set://sysu/2026-1/shards"

#: 已批准的五校区 shard（与真实取证一致；⛔ **不猜其它值**、⛔ 不自动读取下拉框）。
#:
#: 顺序即**合并顺序**（稳定、可复现）。
APPROVED_SHARD_IDS: tuple[str, ...] = (
    "东校园",
    "北校园",
    "南校园",
    "深圳校区",
    "珠海校区",
)


class ShardedCaptureError(CourseDataNormalizationError):
    """shard 采集集编排失败（继承统一错误类型，便于调用方一处捕获）。"""


@dataclass(frozen=True)
class ShardSource:
    """**一个** shard 的 bundle 来源。

    - `shard_id` —— 已批准校区名（见 `APPROVED_SHARD_IDS`）；
    - `bundle` —— 已加载的 bundle **或** bundle 的本地路径（`str` / `Path`）。
      ⛔ 本模块不提供"扫描目录自动发现"，调用方必须**显式**给出每一份。
    """

    shard_id: str
    bundle: Mapping[str, object] | str | Path


@dataclass(frozen=True)
class ShardedCaptureSet:
    """编排结果（**内部对象**，不进 `schemas/` / `docs/interfaces/`）。

    - `merged` —— 合并后的 `OfferingSnapshot`（`complete`）；
    - `shards` —— 每个 shard 的独立快照（用于对账 / 诊断）；
    - `baseline_loaded_count` / `baseline_reported_total` —— baseline 的两个计数；
    - `sum_shard_reported_total` / `total_loaded_rows` / `unique_identity_count` —— 对账用计数。

    ⚠️ 这些计数只是**结构化对账信息**；⛔ 不含任何课程 / 教师 / 学生取值。
    """

    merged: OfferingSnapshot
    shards: tuple[OfferingSnapshot, ...]
    baseline_loaded_count: int
    baseline_reported_total: int
    sum_shard_reported_total: int
    total_loaded_rows: int
    unique_identity_count: int


def _require_single_snapshot(
    label: str, snapshot: OfferingSnapshot, *, expected_semester: str
) -> int:
    """baseline / 单个 shard 必须是**自洽的 complete 快照**；返回其 `reported_total`。"""

    if not snapshot.is_complete:
        raise ShardedCaptureError(
            f"{label} 必须是 complete 快照"
            f"（completeness={snapshot.completeness!r}，"
            f"loaded_count={snapshot.loaded_count}，"
            f"reported_total={snapshot.reported_total}）"
        )

    if snapshot.reported_total is None or snapshot.loaded_count != snapshot.reported_total:
        raise ShardedCaptureError(
            f"{label} 的 loaded_count({snapshot.loaded_count}) != "
            f"reported_total({snapshot.reported_total})；基线不可信，拒绝继续"
        )

    if snapshot.semester != expected_semester:
        raise ShardedCaptureError(
            f"{label} 的 semester({snapshot.semester}) != "
            f"期望 semester({expected_semester})；拒绝继续"
        )

    return snapshot.reported_total


def _assert_no_duplicate_within_shard(shard_id: str, snapshot: OfferingSnapshot) -> None:
    """⛔ **同 shard 内**重复 identity → fail closed。

    注：`OfferingSnapshot.__post_init__` **已经**拒绝同 shard 内重复
    （`(semester, course_id, class_id)`），因此正常情况下到不了这里；
    本函数把它变成**编排层显式保证**，并让"同 shard 重复"与"跨 shard 重复"
    共用同一套 identity 口径，避免以后有人放宽上层校验后静默漏掉。
    """

    seen: set[tuple[str, str, str]] = set()

    for offering in snapshot.offerings:
        identity = _class_key(offering)
        if identity in seen:
            raise ShardedCaptureError(
                f"{shard_id} **内部**出现重复教学班 identity："
                f"{_reportable_identity(offering)}；拒绝继续"
            )
        seen.add(identity)


def _reportable_identity(offering: CourseOffering) -> str:
    """跨 / 同 shard 重复时**只报告最小 identity**（⛔ 不回显课程名等）。"""

    return (
        f"semester={offering.semester} "
        f"course_id={offering.course_id} "
        f"class_id={offering.class_id}"
    )


def _bundle_label(source: ShardSource) -> str:
    """错误信息里只暴露 bundle 的**文件名**（⛔ 不含完整路径）。"""

    bundle = source.bundle
    if isinstance(bundle, (str, Path)):
        return Path(bundle).name
    return "<in-memory bundle>"


def _path_forms(source: ShardSource) -> tuple[str, ...]:
    """调用方给出的路径的**各种字面形式**（用于擦除；长的先替换）。"""

    bundle = source.bundle
    if not isinstance(bundle, (str, Path)):
        return ()

    path = Path(bundle)
    forms = {str(path), path.as_posix()}
    if isinstance(bundle, str):
        forms.add(bundle)

    return tuple(sorted((form for form in forms if form), key=len, reverse=True))


def _scrub_paths(message: str, sources: Sequence[ShardSource]) -> str:
    """把下层错误信息里的**本地路径**擦成文件名（⛔ 不泄漏目录结构）。"""

    for source in sources:
        for form in _path_forms(source):
            message = message.replace(form, Path(form).name)

    return message


def _shard_order_label() -> str:
    """合并失败时把 `shard[i]` 位置还原成**校区名**（否则下标无法解读）。"""

    return "、".join(
        f"shard[{index}]={name}" for index, name in enumerate(APPROVED_SHARD_IDS)
    )


def _resolve_snapshot(source: ShardSource) -> OfferingSnapshot:
    """把一个 shard 的 bundle 变成 `OfferingSnapshot`（复用**现有**两个入口）。"""

    bundle = source.bundle
    if isinstance(bundle, (str, Path)):
        bundle = load_capture_bundle(bundle)

    return collect_captured_pages_snapshot(bundle, source=SHARDED_CAPTURE_SOURCE)


def collect_sharded_capture_set(
    *,
    shard_sources: Sequence[ShardSource],
    baseline: Sequence[OfferingSnapshot],
    expected_semester: str,
) -> ShardedCaptureSet:
    """把**多个 shard 的 Capture Bundle** 编排成一份合并后的 complete 快照。

    编排层负责（任一不满足 → `ShardedCaptureError`，fail closed）：

    ```text
    1. baseline 恰好一个快照，且自身 complete / 计数自洽 / semester 匹配
    2. shard 集合**恰好等于**已批准五校区：无缺 shard、无额外 shard、无重复 shard
    3. 每个 bundle 独立 complete（各自 complete / 计数自洽）
    4. 每个 shard semester == expected_semester（与条件 3 同一处强制，便于定位到 shard）
    5. 每个 shard **内部**无重复 identity（`OfferingSnapshot` 构造已强制；本层显式重申）
    6. Σ shard reported_total == baseline reported_total（分片覆盖全体、与基线一致）
    7. 合并结果**物化后重新计数**仍须 complete：
       行数 == Σ 各 shard 已加载行数 == baseline，且 unique identity 数 == baseline
       （⛔ 不采信下层自报数字：这里数的是**最终要交给 runtime 的那份数据**）
    8. 调用现有 merge_offering_snapshots()（它再保证**跨 shard** 无重复与
       unique == baseline；条件 7 是对其结果的独立复核）
    ```

    以上任一不满足 —— **包括条件 8 由下层抛出的错误** —— 都以
    `ShardedCaptureError`（`CourseDataNormalizationError` 的子类）抛出：
    调用方**一处捕获**即可。第 8 步的错误信息会附上
    `shard[i]=校区名` 的顺序表（下层只报位置下标），
    并把下层信息里的本地路径擦成文件名。

    ⚠️ `baseline_before == baseline_after` 的**对拍**发生在调用方（采集编排层）：
    本函数只接受**一个**已确认的 baseline。⛔ 本模块不接触网络。
    """

    if isinstance(shard_sources, (str, bytes)) or not isinstance(shard_sources, Sequence):
        raise ShardedCaptureError(
            f"shard_sources 必须是 ShardSource 序列，实际是 {type(shard_sources).__name__}"
        )
    if isinstance(baseline, (str, bytes)) or not isinstance(baseline, Sequence):
        raise ShardedCaptureError(
            f"baseline 必须是 OfferingSnapshot 序列，实际是 {type(baseline).__name__}"
        )
    if not isinstance(expected_semester, str) or not expected_semester.strip():
        raise ShardedCaptureError("expected_semester 必须是非空字符串")

    # ---- 条件 1：baseline 恰好一个且自洽 ------------------------------------
    baseline_list = list(baseline)
    if len(baseline_list) != 1:
        raise ShardedCaptureError(
            f"baseline 必须恰好包含一个快照，实际 {len(baseline_list)} 个"
        )

    baseline_snapshot = baseline_list[0]
    if not isinstance(baseline_snapshot, OfferingSnapshot):
        raise ShardedCaptureError(
            f"baseline 必须是 OfferingSnapshot，实际是 {type(baseline_snapshot).__name__}"
        )

    baseline_reported_total = _require_single_snapshot(
        "baseline", baseline_snapshot, expected_semester=expected_semester
    )

    # ---- 条件 2：shard 集合恰好等于已批准五校区 ----------------------------
    sources = list(shard_sources)
    seen_ids: list[str] = []

    for index, source in enumerate(sources):
        if not isinstance(source, ShardSource):
            raise ShardedCaptureError(
                f"shard_sources[{index}] 必须是 ShardSource，实际是 {type(source).__name__}"
            )
        if source.shard_id in seen_ids:
            raise ShardedCaptureError(f"重复的 shard：{source.shard_id}")
        seen_ids.append(source.shard_id)

    approved = set(APPROVED_SHARD_IDS)
    given = set(seen_ids)

    missing = [name for name in APPROVED_SHARD_IDS if name not in given]
    if missing:
        raise ShardedCaptureError(f"缺少已批准 shard：{missing}")

    unexpected = sorted(given - approved)
    if unexpected:
        raise ShardedCaptureError(f"出现未批准的 shard：{unexpected}")

    # 合并顺序固定为已批准顺序（与调用方传入顺序无关，保证可复现）。
    by_id = {source.shard_id: source for source in sources}
    ordered_sources = [by_id[name] for name in APPROVED_SHARD_IDS]

    # ---- 条件 3 / 4 / 5：逐 shard 独立校验 ---------------------------------
    shard_snapshots: list[OfferingSnapshot] = []
    sum_shard_reported_total = 0
    total_loaded_rows = 0

    for source in ordered_sources:
        try:
            snapshot = _resolve_snapshot(source)
        except CourseDataNormalizationError as exc:
            raise ShardedCaptureError(
                f"shard {source.shard_id} 的 bundle（{_bundle_label(source)}）"
                f"无法形成快照：{_scrub_paths(str(exc), ordered_sources)}"
            ) from exc

        shard_reported_total = _require_single_snapshot(
            f"shard {source.shard_id}", snapshot, expected_semester=expected_semester
        )
        _assert_no_duplicate_within_shard(source.shard_id, snapshot)

        sum_shard_reported_total += shard_reported_total
        total_loaded_rows += snapshot.loaded_count
        shard_snapshots.append(snapshot)

    # ---- 条件 6：分片覆盖全体且与 baseline 一致 ----------------------------
    if sum_shard_reported_total != baseline_reported_total:
        raise ShardedCaptureError(
            f"各 shard reported_total 之和({sum_shard_reported_total}) != "
            f"baseline({baseline_reported_total})；分片未覆盖全体或与基线不一致"
        )

    # ---- 条件 8：交给已 Review 通过的合并函数（跨 shard 重复 / unique 校验） ----
    try:
        merged = merge_offering_snapshots(
            shard_snapshots, baseline_total=baseline_reported_total
        )
    except CourseDataNormalizationError as exc:
        raise ShardedCaptureError(
            f"合并 {len(shard_snapshots)} 个 shard 快照失败"
            f"（顺序：{_shard_order_label()}）："
            f"{_scrub_paths(str(exc), ordered_sources)}"
        ) from exc

    # ---- 条件 7：对**物化结果**重新计数（⛔ 不采信下层自报数字） ----------
    merged_loaded = merged.loaded_count  # == len(merged.offerings)
    unique_identity_count = len({_class_key(o) for o in merged.offerings})

    if not merged.is_complete:
        raise ShardedCaptureError("合并结果不是 complete 快照")

    if merged_loaded != total_loaded_rows:
        raise ShardedCaptureError(
            f"合并后物化行数({merged_loaded}) != 各 shard 已加载行数之和"
            f"({total_loaded_rows})；合并过程疑似丢行或重复"
        )

    if merged_loaded != baseline_reported_total:
        raise ShardedCaptureError(
            f"合并后物化行数({merged_loaded}) != baseline({baseline_reported_total})"
        )

    if unique_identity_count != baseline_reported_total:
        raise ShardedCaptureError(
            f"合并后 unique identity 数({unique_identity_count}) != "
            f"baseline({baseline_reported_total})；存在重复教学班"
        )

    return ShardedCaptureSet(
        merged=merged,
        shards=tuple(shard_snapshots),
        baseline_loaded_count=baseline_snapshot.loaded_count,
        baseline_reported_total=baseline_reported_total,
        sum_shard_reported_total=sum_shard_reported_total,
        total_loaded_rows=total_loaded_rows,
        unique_identity_count=unique_identity_count,
    )
