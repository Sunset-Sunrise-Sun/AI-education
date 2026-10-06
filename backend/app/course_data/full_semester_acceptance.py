"""Five-shard **full-semester** Course Data acceptance orchestration（内部，**零网络**）。

## 为什么需要它

`sharded_capture.collect_sharded_capture_set()` 已经是「五 shard → 合并快照」的编排层，
但它要求调用方提供一份 **complete 的 baseline `OfferingSnapshot`**：
那意味着"我们手里已经有一份完整的全学期快照"，而真实采集侧**没有**这种东西 ——
浏览器 collector 只有两个**总量证据**：

```text
baseline_before total   （采集窗口开始前接口报告的全量总数）
baseline_after  total   （采集窗口结束后接口报告的全量总数）
```

因此本模块是**更高一层**的 acceptance orchestration：

```text
5 份 raw campus Capture Bundle（各自真实捕获，⛔ 不入 Git）
        ↓  每个 raw-byte SHA-256                （本模块；exact-byte identity）
        ↓  exact five-shard 身份校验            （本模块；无缺 / 无多 / 无重 / 无别名）
        ↓  load_capture_bundle + collect_captured_pages_snapshot（**现有入口**）
   5 个 campus OfferingSnapshot（各自必须 complete）
        ↓  baseline_before == baseline_after    （本模块；snapshot window 稳定性）
        ↓  Σ shard reported_total == baseline   （本模块；shard coverage）
        ↓  merge_offering_snapshots(...)        （**上一轮已 Review 通过的底层函数**）
   merged complete OfferingSnapshot
        ↓  canonical manifest + manifest SHA-256（本模块；acceptance identity）
   full_semester acceptance record
```

## 边界（硬）

- ⛔ **不改** `merge_offering_snapshots()` 的通用低层语义（它继续信任调用方给出的
  `baseline_total`）；本模块只**新增高层 orchestration**，并在其之上做独立复核；
- ⛔ **不改** Capture Bundle format、⛔ 不重编号 / 不重切分 / 不生成伪连续全局 pages；
- ⛔ **零网络**：没有 endpoint、没有 Cookie / Session / Token、没有 crawler；
- ⛔ **不猜** scope / semester / baseline：全部由调用方显式给出；
- ⛔ **不新增公共 Schema**：manifest 是本模块的**内部**对象，
  不进 `schemas/`、不进 `docs/interfaces/`、不进 Provider / API。

## baseline 的两个 total **不是** baseline OfferingSnapshot

真实采集侧的证据只有"总数"：

```text
baseline_before == baseline_after       否则 snapshot_window_unstable（fail closed）
Σ shard reported_total == 稳定 baseline 否则 shard_coverage_mismatch（fail closed）
```

⛔ **禁止**用 `page_count`（已捕获页数）推导 completeness：
`complete` 只由**现有**的分页证据链（`pagination.py`）判定。

## 逃生参数：没有

本模块⛔ **不提供** `--skip-north` / `--allow-partial-semester` / `--force-complete`
这类绕过参数。缺少任一已批准 shard ⇒ **整体失败**。

⚠️ 代码本身**可以**接受一份未来合法取得的 North bundle（North 当前
`operational: false` / HTTP 600 未解决，因此**真实数据阶段拿不到**）：
本模块不知道"当前是否 suspended"，它只认「五份都有且都合格」这一件事。
真正的 fail closed 发生在**没有 North artifact 就没有第五份输入**这一点上。

## `manifest_sha256` 的口径（⛔ 不得改动）

```text
manifest SHA-256 = acceptance record identity / integrity
                 ≠ school acquisition provenance proof
```

每个 shard 的 `raw_bundle_sha256` 才是"那批原始捕获字节没变过"的证据；
manifest 只把它们**绑在一起**。⛔ manifest **不含**认证 token / 用户信息 / raw row /
课程取值，只有结构性计数与摘要。

## 隐私

错误信息只暴露**结构性**内容：shard 名、`identity`（`semester` + `course_id` +
`class_id`）、计数、**文件名**（⛔ 不含完整路径）。
"""

from __future__ import annotations

import hashlib
import json
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
from app.course_data.store import SCOPE_KIND_FULL_SEMESTER, SnapshotScope
from app.models.contracts import CourseOffering

__all__ = [
    "APPROVED_FULL_SEMESTER_SHARDS",
    "FULL_SEMESTER_ACCEPTANCE_FORMAT",
    "FULL_SEMESTER_ACCEPTANCE_TOOL",
    "FULL_SEMESTER_ACCEPTANCE_VERSION",
    "FullSemesterAcceptance",
    "FullSemesterAcceptanceError",
    "FullSemesterShard",
    "FullSemesterShardRecord",
    "ShardArtifact",
    "accept_full_semester_capture_set",
    "canonical_manifest_bytes",
    "compute_manifest_sha256",
    "full_semester_scope",
    "full_semester_source",
]

#: manifest 的格式标识（v1，**内部格式**，⛔ 不进 `schemas/`）。
FULL_SEMESTER_ACCEPTANCE_FORMAT = "sysu-course-data-full-semester-acceptance-v1"

#: 产出 manifest 的工具名 / 版本（写进 manifest，便于审计时定位）。
FULL_SEMESTER_ACCEPTANCE_TOOL = "tools/accept_full_semester_course_data.py"
FULL_SEMESTER_ACCEPTANCE_VERSION = 1


@dataclass(frozen=True)
class FullSemesterShard:
    """一个**已批准**的校区 shard 身份。

    - `shard_id` —— 采集侧的 stable slug（例如 `east-campus`），
      ⛔ 不接受任意字符串、⛔ 不接受别名、⛔ 不接受中文校区名冒充；
    - `opening_school_number` —— 学校接口的 `openingSchoolNumber`（真实取证值）。
    """

    shard_id: str
    opening_school_number: str


#: 已批准的 **exact five-shard** 集合（顺序 = manifest 顺序 = 合并顺序，稳定可复现）。
#:
#: ⚠️ 号码与 `tools/sysu_course_offering_collector.js` 的 `APPROVED_SHARDS` 必须一致；
#: 两侧一致性由 `backend/tests/test_course_data_full_semester_acceptance.py::
#: test_approved_full_semester_shards_match_the_collector_table` 强制
#: （⛔ 不允许两边各写一份却悄悄漂移）。
APPROVED_FULL_SEMESTER_SHARDS: tuple[FullSemesterShard, ...] = (
    FullSemesterShard("east-campus", "5063559"),
    FullSemesterShard("south-campus", "5062201"),
    FullSemesterShard("shenzhen-campus", "333291143"),
    FullSemesterShard("zhuhai-campus", "5062203"),
    FullSemesterShard("north-campus", "5062202"),
)

#: shard_id → 批准身份（唯一真源）。
_SHARDS_BY_ID: Mapping[str, FullSemesterShard] = {
    shard.shard_id: shard for shard in APPROVED_FULL_SEMESTER_SHARDS
}

#: 各失败类别的**机器可读**取值（调用方 / CLI 按类别映射退出码，⛔ 不解析文本）。
CATEGORY_INVALID_SEMESTER = "invalid_semester"
CATEGORY_INVALID_BASELINE = "invalid_baseline"
CATEGORY_DUPLICATE_SHARD = "duplicate_shard"
CATEGORY_UNKNOWN_SHARD = "unknown_shard"
CATEGORY_MISSING_SHARD = "missing_shard"
CATEGORY_BUNDLE_READ_FAILED = "bundle_read_failed"
CATEGORY_BUNDLE_CHANGED = "bundle_changed_during_acceptance"
CATEGORY_BUNDLE_DIGEST_MISMATCH = "bundle_digest_mismatch"
CATEGORY_INVALID_BUNDLE = "invalid_capture_bundle"
CATEGORY_SEMESTER_MISMATCH = "semester_mismatch"
CATEGORY_SHARD_NOT_COMPLETE = "shard_not_complete"
CATEGORY_EMPTY_SHARD = "empty_shard"
CATEGORY_SNAPSHOT_WINDOW_UNSTABLE = "snapshot_window_unstable"
CATEGORY_SHARD_COVERAGE_MISMATCH = "shard_coverage_mismatch"
CATEGORY_DUPLICATE_IDENTITY = "duplicate_identity_across_shards"
CATEGORY_CONFLICTING_IDENTITY = "conflicting_identity_across_shards"
CATEGORY_MERGE_FAILED = "merge_failed"
CATEGORY_MERGED_COUNT_MISMATCH = "merged_count_mismatch"


class FullSemesterAcceptanceError(CourseDataNormalizationError):
    """full-semester acceptance 失败（继承统一错误类型，便于调用方一处捕获）。

    `category` 是**机器可读**的失败类别（见本模块 `CATEGORY_*` 常量）：
    CLI 按它映射退出码，⛔ 不解析错误文本。

    `shard_id`（可选）是**结构性**定位信息（已批准 slug）：
    只有在失败可归因到某一个 shard 时才带上，⛔ 不含任何取值 / 路径。
    """

    def __init__(
        self, message: str, *, category: str, shard_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.category = category
        self.shard_id = shard_id


@dataclass(frozen=True)
class ShardArtifact:
    """一个 shard 的**本地 raw bundle 路径**（以及可选的人工记录摘要）。

    ⚠️ 只接受**文件路径**：本模块必须能对**原始字节**计算 SHA-256，
    因此⛔ 不接受"已经在内存里的 bundle"（那没有可核对的 raw bytes）。

    `expected_sha256`（可选）是负责人**事先记录**的该 artifact 原始字节摘要：
    给出时必须完全一致，否则 `bundle_digest_mismatch`（fail closed）。
    """

    shard_id: str
    bundle_path: str | Path
    expected_sha256: str | None = None


@dataclass(frozen=True)
class FullSemesterShardRecord:
    """manifest 中**一个 shard** 的审计记录（⛔ 不含任何课程取值）。"""

    shard_id: str
    opening_school_number: str
    raw_bundle_sha256: str
    page_count: int
    loaded_count: int
    reported_total: int


@dataclass(frozen=True)
class FullSemesterAcceptance:
    """full-semester acceptance 的结果（**内部对象**，不进 `schemas/`）。

    - `merged` —— 合并后的 `complete` `OfferingSnapshot`（唯一维度
      `(semester, course_id, class_id)`）；
    - `shards` —— 每个 shard 的审计记录（顺序 = 已批准顺序）；
    - `baseline_before` / `baseline_after` —— 采集窗口前后的**总量证据**（必须相等）；
    - `manifest` —— canonical manifest（只含结构性计数与摘要）；
    - `manifest_sha256` —— canonical manifest **字节**的 SHA-256 = acceptance identity。
    """

    semester: str
    merged: OfferingSnapshot
    shards: tuple[FullSemesterShardRecord, ...]
    baseline_before: int
    baseline_after: int
    manifest: Mapping[str, object]
    manifest_sha256: str

    @property
    def scope(self) -> SnapshotScope:
        """本 acceptance 的 scope（**固定** `full_semester` / `scope_id = semester`）。"""

        return full_semester_scope(self.semester)

    @property
    def source(self) -> str:
        """本 acceptance 的 source audit label。"""

        return full_semester_source(self.semester)

    @property
    def merged_offering_count(self) -> int:
        return len(self.merged.offerings)


def full_semester_scope(semester: str) -> SnapshotScope:
    """`full_semester` 的 scope：`scope_id` **必须等于** semester（⛔ 不接受其它值）。"""

    if not isinstance(semester, str) or not semester.strip():
        raise FullSemesterAcceptanceError(
            "semester 必须是非空字符串", category=CATEGORY_INVALID_SEMESTER
        )

    resolved = semester.strip()

    return SnapshotScope(scope_kind=SCOPE_KIND_FULL_SEMESTER, scope_id=resolved)


def full_semester_source(semester: str) -> str:
    """`full_semester` 的 source audit label（**由 semester 完全决定**，调用方无法自选）。

    ```text
    capture://sysu/<semester>/full-semester/<semester>
    ```

    ⚠️ 与 campus 模板 `capture://sysu/<semester>/campus/<openingSchoolNumber>` 平行：
    它是**审计标签**，⛔ 不是采集来源的合规证明。
    """

    if not isinstance(semester, str) or not semester.strip():
        raise FullSemesterAcceptanceError(
            "semester 必须是非空字符串", category=CATEGORY_INVALID_SEMESTER
        )

    resolved = semester.strip()

    return f"capture://sysu/{resolved}/full-semester/{resolved}"


def canonical_manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    """canonical 序列化（键排序 + 紧凑分隔符 + UTF-8）—— ⛔ 不得改动。

    只有**确定性**的序列化才能让 `manifest_sha256` 成为可复现的 acceptance identity。
    """

    if not isinstance(manifest, Mapping):
        raise FullSemesterAcceptanceError(
            f"manifest 必须是对象，实际是 {type(manifest).__name__}",
            category=CATEGORY_MERGED_COUNT_MISMATCH,
        )

    return json.dumps(
        dict(manifest),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_manifest_sha256(manifest: Mapping[str, object]) -> str:
    """canonical manifest 字节的 SHA-256（十六进制小写）—— acceptance identity。"""

    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def _require_non_negative_int(value: object, *, category: str, name: str) -> int:
    """baseline total 必须是**非负整数**（`bool` 不算整数）。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise FullSemesterAcceptanceError(
            f"{name} 必须是整数，实际是 {type(value).__name__}",
            category=category,
        )
    if value < 0:
        raise FullSemesterAcceptanceError(
            f"{name} 不能为负：{value}", category=category
        )
    return value


def _offering_fingerprint(offering: CourseOffering) -> str:
    """一条教学班的**全部公共字段**指纹（用于区分"重复"与"冲突"）。

    ⛔ 只在内存中比较，⛔ 不写进 manifest、⛔ 不进错误信息。
    """

    return json.dumps(
        offering.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _reportable_identity(offering: CourseOffering) -> str:
    """跨 shard 重复 / 冲突时**只报告最小 identity**（⛔ 不回显任何取值）。"""

    return (
        f"semester={offering.semester} "
        f"course_id={offering.course_id} "
        f"class_id={offering.class_id}"
    )


def _ordered_artifacts(
    shard_artifacts: Sequence[ShardArtifact],
) -> tuple[ShardArtifact, ...]:
    """校验 shard 集合**恰好等于**已批准五校区，并按已批准顺序返回。

    ⛔ 无缺 shard、⛔ 无未批准 shard、⛔ 无重复 shard、⛔ 无别名
    （`shard_id` 必须精确等于批准的 slug）。
    """

    if isinstance(shard_artifacts, (str, bytes)) or not isinstance(
        shard_artifacts, Sequence
    ):
        # ⚠️ `str` 本身也是 `Sequence`：这里显式拦下，避免"逐字符迭代"这种荒谬路径。
        #    （即使去掉前半句，下面的元素类型检查也会以同一 category 拒绝 —— 冗余但保留。）
        raise FullSemesterAcceptanceError(
            f"shard_artifacts 必须是 ShardArtifact 序列，实际是 "
            f"{type(shard_artifacts).__name__}",
            category=CATEGORY_UNKNOWN_SHARD,
        )

    seen: list[str] = []
    by_id: dict[str, ShardArtifact] = {}

    for index, artifact in enumerate(shard_artifacts):
        if not isinstance(artifact, ShardArtifact):
            raise FullSemesterAcceptanceError(
                f"shard_artifacts[{index}] 必须是 ShardArtifact，实际是 "
                f"{type(artifact).__name__}",
                category=CATEGORY_UNKNOWN_SHARD,
            )

        shard_id = artifact.shard_id

        if not isinstance(shard_id, str) or shard_id not in _SHARDS_BY_ID:
            # ⛔ 不回显传入值以外的判定：这里只报"未批准"，不接受别名。
            raise FullSemesterAcceptanceError(
                f"出现未批准的 shard（位置 {index}）；已批准集合是 "
                f"{[shard.shard_id for shard in APPROVED_FULL_SEMESTER_SHARDS]}",
                category=CATEGORY_UNKNOWN_SHARD,
            )

        if shard_id in by_id:
            raise FullSemesterAcceptanceError(
                f"重复的 shard：{shard_id}", category=CATEGORY_DUPLICATE_SHARD
            )

        seen.append(shard_id)
        by_id[shard_id] = artifact

    missing = [
        shard.shard_id
        for shard in APPROVED_FULL_SEMESTER_SHARDS
        if shard.shard_id not in by_id
    ]
    if missing:
        raise FullSemesterAcceptanceError(
            f"缺少已批准 shard：{missing}；full-semester acceptance 要求 "
            f"exact five-shard 集合（⛔ 无跳过参数、⛔ 不允许部分学期）",
            category=CATEGORY_MISSING_SHARD,
        )

    return tuple(by_id[shard.shard_id] for shard in APPROVED_FULL_SEMESTER_SHARDS)


def _read_shard_bundle(
    artifact: ShardArtifact, *, label: str
) -> tuple[bytes, str, Mapping[str, object], int]:
    """读取一个 shard 的 raw bytes → SHA-256 → 已校验 bundle（含读回重验）。"""

    path = Path(artifact.bundle_path)

    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 bundle（{path.name}）无法读取",
            category=CATEGORY_BUNDLE_READ_FAILED,
            shard_id=label,
        ) from exc

    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    expected = artifact.expected_sha256
    if expected is not None:
        if (
            not isinstance(expected, str)
            or expected.strip().lower() != raw_sha256
        ):
            raise FullSemesterAcceptanceError(
                f"shard {label} 的 bundle（{path.name}）原始字节 SHA-256 与"
                f"事先记录的摘要不一致",
                category=CATEGORY_BUNDLE_DIGEST_MISMATCH,
                shard_id=label,
            )

    try:
        bundle = load_capture_bundle(path)
    except CourseDataNormalizationError as exc:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 bundle（{path.name}）不是合法的 Capture Bundle",
            category=CATEGORY_INVALID_BUNDLE,
            shard_id=label,
        ) from exc

    # ⛔ 复读：摘要不能描述"另一批字节"（采集期间被改写的 artifact 不得被接受）。
    try:
        bytes_after = path.read_bytes()
    except OSError as exc:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 bundle（{path.name}）在验收期间无法复读",
            category=CATEGORY_BUNDLE_READ_FAILED,
            shard_id=label,
        ) from exc

    if bytes_after != raw_bytes:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 bundle（{path.name}）在验收期间发生变化",
            category=CATEGORY_BUNDLE_CHANGED,
            shard_id=label,
        )

    pages = bundle["pages"]
    page_count = len(pages) if isinstance(pages, Sequence) else 0

    return raw_bytes, raw_sha256, bundle, page_count


def accept_full_semester_capture_set(
    *,
    expected_semester: str,
    baseline_before: int,
    baseline_after: int,
    shard_artifacts: Sequence[ShardArtifact],
) -> FullSemesterAcceptance:
    """把**五个已批准校区**的 raw Capture Bundle 验收成一份 full-semester acceptance。

    校验顺序（任一不满足 → `FullSemesterAcceptanceError`，fail closed）：

    ```text
     1. expected_semester 非空
     2. baseline_before / baseline_after 是非负整数
     3. shard 集合 exact five-shard（无缺 / 无多 / 无重 / 无别名）
     4. baseline_before == baseline_after             （snapshot window 稳定）
     5. 每个 shard：raw bytes → SHA-256 → 合法 bundle → semester 一致
     6. 每个 shard 快照 complete、计数自洽、**非空**
     7. Σ shard reported_total == 稳定 baseline        （shard coverage）
     8. 跨 shard identity 无重复 / 无冲突               （identity 口径独立于 scope）
     9. merge_offering_snapshots(...)（底层通用函数，语义未改）
    10. 合并结果**物化后重新计数** == baseline，且 unique identity == baseline
    11. canonical manifest + manifest SHA-256
    ```

    ⚠️ `identity = (semester, course_id, class_id)`：跨 shard 出现同一 identity 一律拒绝；
    载荷不一致时报 `conflicting_identity_across_shards`，完全一致时报
    `duplicate_identity_across_shards`（⛔ 都不静默去重）。

    ⚠️ 本函数**只读文件**：不联网、不写库、不写 manifest 文件（落盘由 CLI / 调用方决定）。
    """

    if not isinstance(expected_semester, str) or not expected_semester.strip():
        raise FullSemesterAcceptanceError(
            "expected_semester 必须是非空字符串", category=CATEGORY_INVALID_SEMESTER
        )
    semester = expected_semester.strip()

    resolved_before = _require_non_negative_int(
        baseline_before, category=CATEGORY_INVALID_BASELINE, name="baseline_before"
    )
    resolved_after = _require_non_negative_int(
        baseline_after, category=CATEGORY_INVALID_BASELINE, name="baseline_after"
    )

    ordered = _ordered_artifacts(shard_artifacts)

    if resolved_before != resolved_after:
        raise FullSemesterAcceptanceError(
            f"baseline_before({resolved_before}) != baseline_after({resolved_after})；"
            f"采集窗口内数据集合发生变化，拒绝生成 full-semester acceptance",
            category=CATEGORY_SNAPSHOT_WINDOW_UNSTABLE,
        )

    stable_baseline = resolved_before
    source = full_semester_source(semester)

    shard_snapshots: list[OfferingSnapshot] = []
    records: list[FullSemesterShardRecord] = []
    sum_shard_reported_total = 0
    total_loaded_rows = 0

    #: identity → (指纹, shard_id)，用于区分"重复"与"冲突"。
    seen_identity: dict[tuple[str, str, str], tuple[str, str]] = {}

    for artifact in ordered:
        approved = _SHARDS_BY_ID[artifact.shard_id]
        label = approved.shard_id

        _, raw_sha256, bundle, page_count = _read_shard_bundle(artifact, label=label)

        if bundle["semester"] != semester:
            raise FullSemesterAcceptanceError(
                f"shard {label} 的 bundle semester({bundle['semester']!r}) != "
                f"期望 semester({semester!r})",
                category=CATEGORY_SEMESTER_MISMATCH,
                shard_id=label,
            )

        try:
            snapshot = collect_captured_pages_snapshot(bundle, source=source)
        except CourseDataNormalizationError as exc:
            raise FullSemesterAcceptanceError(
                f"shard {label} 的 bundle 无法形成快照（分页证据链判定失败）",
                category=CATEGORY_INVALID_BUNDLE,
                shard_id=label,
            ) from exc

        if snapshot.semester != semester:
            raise FullSemesterAcceptanceError(
                f"shard {label} 的快照 semester({snapshot.semester!r}) != "
                f"期望 semester({semester!r})",
                category=CATEGORY_SEMESTER_MISMATCH,
                shard_id=label,
            )

        if not snapshot.is_complete or snapshot.reported_total != snapshot.loaded_count:
            # ⚠️ 后半句由 `OfferingSnapshot` 的 complete 不变量保证（complete ⇒
            #    reported_total == loaded_count）：冗余但保留为纵深防御。
            raise FullSemesterAcceptanceError(
                f"shard {label} 不是 complete 快照（completeness="
                f"{snapshot.completeness!r}，loaded_count={snapshot.loaded_count}，"
                f"reported_total={snapshot.reported_total}）",
                category=CATEGORY_SHARD_NOT_COMPLETE,
                shard_id=label,
            )

        if snapshot.loaded_count == 0:
            # ⛔ 任一已批准校区返回 0 条都视为采集失败：五个校区的真实取证规模均 > 0。
            #    空 shard 会让"总和 == baseline"这一条件在错误数据上仍然成立。
            raise FullSemesterAcceptanceError(
                f"shard {label} 的载荷为空（loaded_count=0）；"
                f"已批准校区不可能是空集，拒绝接受",
                category=CATEGORY_EMPTY_SHARD,
                shard_id=label,
            )

        for offering in snapshot.offerings:
            identity = _class_key(offering)
            fingerprint = _offering_fingerprint(offering)
            previous = seen_identity.get(identity)

            if previous is not None:
                previous_fingerprint, previous_shard = previous
                if previous_fingerprint == fingerprint:
                    raise FullSemesterAcceptanceError(
                        f"跨 shard 出现重复教学班 identity：{_reportable_identity(offering)}"
                        f"（同时出现在 {previous_shard} 与 {label}）；"
                        f"校区 shard 应互斥，拒绝静默去重后继续",
                        category=CATEGORY_DUPLICATE_IDENTITY,
                        shard_id=label,
                    )
                raise FullSemesterAcceptanceError(
                    f"跨 shard 出现**内容冲突**的同一教学班 identity："
                    f"{_reportable_identity(offering)}"
                    f"（同时出现在 {previous_shard} 与 {label}，且载荷不一致）；"
                    f"无法判定哪一份正确，拒绝继续",
                    category=CATEGORY_CONFLICTING_IDENTITY,
                    shard_id=label,
                )

            seen_identity[identity] = (fingerprint, label)

        shard_reported_total = int(snapshot.reported_total)  # complete ⇒ 非 None
        sum_shard_reported_total += shard_reported_total
        total_loaded_rows += snapshot.loaded_count

        shard_snapshots.append(snapshot)
        records.append(
            FullSemesterShardRecord(
                shard_id=label,
                opening_school_number=approved.opening_school_number,
                raw_bundle_sha256=raw_sha256,
                page_count=page_count,
                loaded_count=snapshot.loaded_count,
                reported_total=shard_reported_total,
            )
        )

    if sum_shard_reported_total != stable_baseline:
        raise FullSemesterAcceptanceError(
            f"各 shard reported_total 之和({sum_shard_reported_total}) != "
            f"稳定 baseline({stable_baseline})；分片未覆盖全体或与基线不一致",
            category=CATEGORY_SHARD_COVERAGE_MISMATCH,
        )

    try:
        merged = merge_offering_snapshots(
            shard_snapshots, baseline_total=stable_baseline
        )
    except CourseDataNormalizationError as exc:
        raise FullSemesterAcceptanceError(
            "合并五个 shard 快照失败（底层 merge_offering_snapshots 判定不满足）",
            category=CATEGORY_MERGE_FAILED,
        ) from exc

    merged_loaded = merged.loaded_count
    unique_identity_count = len({_class_key(offering) for offering in merged.offerings})

    if not merged.is_complete:
        # ⚠️ `merge_offering_snapshots()` 一定返回 complete 快照：冗余但保留为纵深防御。
        raise FullSemesterAcceptanceError(
            "合并结果不是 complete 快照", category=CATEGORY_MERGED_COUNT_MISMATCH
        )

    if merged_loaded != total_loaded_rows or merged_loaded != stable_baseline:
        # ⚠️ 后半句在"每个 shard loaded == reported"已成立时等价于前半句：冗余但保留。
        raise FullSemesterAcceptanceError(
            f"合并后物化行数({merged_loaded}) != 各 shard 已加载行数之和"
            f"({total_loaded_rows}) 或 != baseline({stable_baseline})",
            category=CATEGORY_MERGED_COUNT_MISMATCH,
        )

    if unique_identity_count != stable_baseline:
        # ⚠️ 底层 merge（条件 8）+ `OfferingSnapshot` 去重不变量已经保证这一点：
        #    冗余但保留 —— 这里数的是**最终物化结果**，不采信下层自报数字。
        raise FullSemesterAcceptanceError(
            f"合并后 unique identity 数({unique_identity_count}) != "
            f"baseline({stable_baseline})",
            category=CATEGORY_MERGED_COUNT_MISMATCH,
        )

    manifest: dict[str, object] = {
        "format": FULL_SEMESTER_ACCEPTANCE_FORMAT,
        "manifest_version": FULL_SEMESTER_ACCEPTANCE_VERSION,
        "tool": FULL_SEMESTER_ACCEPTANCE_TOOL,
        "semester": semester,
        "scope_kind": SCOPE_KIND_FULL_SEMESTER,
        "scope_id": semester,
        "source": source,
        "baseline_before": resolved_before,
        "baseline_after": resolved_after,
        "merged_offering_count": merged_loaded,
        "shards": [
            {
                "shard_id": record.shard_id,
                "scope_id": record.opening_school_number,
                "raw_bundle_sha256": record.raw_bundle_sha256,
                "page_count": record.page_count,
                "loaded_count": record.loaded_count,
                "reported_total": record.reported_total,
            }
            for record in records
        ],
        "manifest_sha256_semantics": (
            "acceptance_record_identity_and_integrity_not_acquisition_provenance_proof"
        ),
        "raw_bundle_sha256_semantics": "exact_bytes_of_that_campus_artifact",
        "source_semantics": "audit_label_only_not_provenance_proof",
        "baseline_semantics": (
            "collector_reported_total_before_and_after_the_capture_window"
        ),
        "completeness_semantics": "full_semester_complete_within_declared_scope",
        "page_count_semantics": "captured_pages_only_never_used_to_derive_completeness",
    }

    return FullSemesterAcceptance(
        semester=semester,
        merged=merged,
        shards=tuple(records),
        baseline_before=resolved_before,
        baseline_after=resolved_after,
        manifest=manifest,
        manifest_sha256=compute_manifest_sha256(manifest),
    )
