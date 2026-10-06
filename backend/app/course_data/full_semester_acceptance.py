"""Five-shard **full-semester** Course Data acceptance orchestration（内部，**零网络**）。

## 为什么需要它

`sharded_capture.collect_sharded_capture_set()` 已经是「五 shard → 合并快照」的编排层，
但它要求调用方提供一份 **complete 的 baseline `OfferingSnapshot`**：
那意味着"我们手里已经有一份完整的全学期快照"，而真实采集侧**没有**这种东西 ——
浏览器 collector 只有两个**总量证据**：

```text
baseline_before total   （采集窗口开始前接口报告的全量总数）
baseline_after  total   （采集窗口结束后的全量总数）
```

因此本模块是**更高一层**的 acceptance orchestration：

```text
已批准 capture inventory（人工审核产物）
        +  5 份 raw campus Capture Bundle
        +  5 份**已导入的 campus acceptance 记录**（独立于 label 的 scope 绑定）
        ↓  每个 raw-byte SHA-256（⛔ 与"被解析的字节"**同一批**）
        ↓  exact five-shard + inventory digest 逐项匹配
        ↓  load_capture_bundle_bytes + collect_captured_pages_snapshot（**现有入口**）
   5 个 campus OfferingSnapshot（各自必须 complete 且非空）
        ↓  campus acceptance 记录核对：digest / scope_id / source / counts / 内容 digest
        ↓  baseline_before == baseline_after
        ↓  Σ shard reported_total == baseline
        ↓  merge_offering_snapshots(...)（**上一轮已 Review 通过的底层函数**）
   merged complete OfferingSnapshot
        ↓  canonical manifest（含整批内容 digest）+ manifest SHA-256
   full_semester acceptance record
```

## BLOCK 修复（Forward Red-Team，2026-10-06）

**B1 —— 被 hash 的字节 == 被解析的字节。**
`_read_shard_bundle()` 只 `read_bytes()` **一次**，digest 与 JSON 解析都吃这同一批 bytes
（`load_capture_bundle_bytes()`）；⛔ 不再为了 parse 重新打开路径。
文件复读只作为**额外的变动探测**，⛔ 不承担"digest 与 payload 同源"的职责。

**B2 —— artifact 与 campus scope 独立绑定。**
⛔ 不再"调用方说这是 East 就信这是 East"。正式 acceptance 要求：

```text
已批准 capture inventory：  (semester, shard_id, openingSchoolNumber, raw_bundle_sha256)
        ∧
campus acceptance 记录（SQLite content-bound 平面）：
        artifact_sha256 == raw bundle digest
        scope_kind      == campus
        scope_id        == inventory.openingSchoolNumber
        source          == capture://sysu/<semester>/campus/<openingSchoolNumber>
        offering_set_sha256 == 该 shard 解析结果的整批内容 digest
        membership identity 集合 == 该 shard 解析结果的 identity 集合
        counts          == 该 shard 解析结果的计数
```

⛔ 同一 digest 在同一学期内**只能**对应一个 campus acceptance（换 label 复用同一 artifact 被拒绝）；
⛔ 五个 raw digest 必须两两不同；⛔ 不从文件名推断 scope、⛔ 不从 rows 猜 campus、
⛔ 不把 source label 当 acquisition provenance proof。

**B3 —— exact accepted dataset 必须 content-bound。**
manifest 记录 `merged_offering_set_sha256`（与 `merged_offering_count`）：
`offering_digest.offering_set_sha256()` 对**全部公共字段**做 canonical 序列化后按
identity 稳定排序再取 SHA-256 ⇒ "同数量 / 同身份的内容替换"必然改变 digest。

## baseline 的两个 total **不是** baseline OfferingSnapshot

```text
baseline_before == baseline_after       否则 snapshot_window_unstable（fail closed）
Σ shard reported_total == 稳定 baseline 否则 shard_coverage_mismatch（fail closed）
```

⛔ **禁止**用 `page_count`（已捕获页数）推导 completeness。

## 逃生参数：没有

⛔ 不提供 `--skip-north` / `--allow-partial-semester` / `--force-complete`。

## 口径（⛔ 不得改动）

```text
raw_bundle_sha256        = 那份校区 artifact 的**原始字节**
campus_acceptance_sha256 = 同一次 campus acceptance 的 identity（= 该 raw bytes digest）
offering_set_sha256      = **规范化后的教学班内容**（不含字节层面的 whitespace 概念）
manifest_sha256          = acceptance record identity / integrity
四者都不是 acquisition provenance proof
```

## 隐私

错误信息只暴露**结构性**内容：shard 名、`identity`、计数、**文件名**（⛔ 不含完整路径）。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.course_data.captured_pages import (
    collect_captured_pages_snapshot,
    load_capture_bundle_bytes,
)
from app.course_data.errors import CourseDataNormalizationError
from app.course_data.offering_digest import offering_set_sha256
from app.course_data.snapshot import (
    OfferingSnapshot,
    _class_key,
    merge_offering_snapshots,
)
from app.course_data.store import (
    SCOPE_KIND_CAMPUS,
    SCOPE_KIND_FULL_SEMESTER,
    CourseDataStoreError,
    SnapshotScope,
    load_course_data_acceptances,
)
from app.models.contracts import CourseOffering

__all__ = [
    "APPROVED_FULL_SEMESTER_SHARDS",
    "CAPTURE_INVENTORY_FORMAT",
    "CAPTURE_INVENTORY_VERSION",
    "FULL_SEMESTER_ACCEPTANCE_FORMAT",
    "FULL_SEMESTER_ACCEPTANCE_TOOL",
    "FULL_SEMESTER_ACCEPTANCE_VERSION",
    "CaptureInventory",
    "FullSemesterAcceptance",
    "FullSemesterAcceptanceError",
    "FullSemesterShard",
    "FullSemesterShardRecord",
    "InventoryShard",
    "ShardArtifact",
    "accept_full_semester_capture_set",
    "build_capture_inventory",
    "campus_source_label",
    "canonical_inventory_bytes",
    "canonical_manifest_bytes",
    "capture_inventory_bytes",
    "compute_manifest_sha256",
    "full_semester_scope",
    "full_semester_source",
    "load_capture_inventory",
    "validate_full_semester_manifest_bytes",
]

#: manifest 的格式标识（**内部格式**，⛔ 不进 `schemas/`）。
FULL_SEMESTER_ACCEPTANCE_FORMAT = "sysu-course-data-full-semester-acceptance-v1"

#: manifest 版本：v2 = inventory-bound + content-bound（B2 / B3 修复后）。
FULL_SEMESTER_ACCEPTANCE_VERSION = 2

#: capture inventory 的格式标识（人工审核产物，**内部格式**）。
CAPTURE_INVENTORY_FORMAT = "sysu-course-data-capture-inventory-v1"
CAPTURE_INVENTORY_VERSION = 1

#: 产出 manifest 的工具名（写进 manifest，便于审计时定位）。
FULL_SEMESTER_ACCEPTANCE_TOOL = "tools/accept_full_semester_course_data.py"

_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class FullSemesterShard:
    """一个**已批准**的校区 shard 身份（slug + 学校接口号码）。"""

    shard_id: str
    opening_school_number: str


#: 已批准的 **exact five-shard** 集合（顺序 = manifest 顺序 = 合并顺序，稳定可复现）。
#:
#: ⚠️ 号码与 `tools/sysu_course_offering_collector.js` 的 `APPROVED_SHARDS` 必须一致；
#: 两侧一致性由 `backend/tests/test_course_data_full_semester_acceptance.py::
#: test_approved_full_semester_shards_match_the_collector_table` 强制。
APPROVED_FULL_SEMESTER_SHARDS: tuple[FullSemesterShard, ...] = (
    FullSemesterShard("east-campus", "5063559"),
    FullSemesterShard("south-campus", "5062201"),
    FullSemesterShard("shenzhen-campus", "333291143"),
    FullSemesterShard("zhuhai-campus", "5062203"),
    FullSemesterShard("north-campus", "5062202"),
)

_SHARDS_BY_ID: Mapping[str, FullSemesterShard] = {
    shard.shard_id: shard for shard in APPROVED_FULL_SEMESTER_SHARDS
}

#: 各失败类别的**机器可读**取值（CLI 按类别映射退出码，⛔ 不解析文本）。
CATEGORY_INVALID_SEMESTER = "invalid_semester"
CATEGORY_INVALID_BASELINE = "invalid_baseline"
CATEGORY_INVENTORY_INVALID = "inventory_invalid"
CATEGORY_INVENTORY_DIGEST_MISMATCH = "inventory_digest_mismatch"
CATEGORY_DUPLICATE_SHARD = "duplicate_shard"
CATEGORY_UNKNOWN_SHARD = "unknown_shard"
CATEGORY_MISSING_SHARD = "missing_shard"
CATEGORY_DUPLICATE_ARTIFACT = "duplicate_artifact_bytes"
CATEGORY_BUNDLE_READ_FAILED = "bundle_read_failed"
CATEGORY_BUNDLE_CHANGED = "bundle_changed_during_acceptance"
CATEGORY_BUNDLE_DIGEST_MISMATCH = "bundle_digest_mismatch"
CATEGORY_INVALID_BUNDLE = "invalid_capture_bundle"
CATEGORY_SEMESTER_MISMATCH = "semester_mismatch"
CATEGORY_SHARD_NOT_COMPLETE = "shard_not_complete"
CATEGORY_EMPTY_SHARD = "empty_shard"
CATEGORY_CAMPUS_ACCEPTANCE_MISSING = "campus_acceptance_missing"
CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH = "campus_acceptance_mismatch"
CATEGORY_SNAPSHOT_WINDOW_UNSTABLE = "snapshot_window_unstable"
CATEGORY_SHARD_COVERAGE_MISMATCH = "shard_coverage_mismatch"
CATEGORY_DUPLICATE_IDENTITY = "duplicate_identity_across_shards"
CATEGORY_CONFLICTING_IDENTITY = "conflicting_identity_across_shards"
CATEGORY_MERGE_FAILED = "merge_failed"
CATEGORY_MERGED_COUNT_MISMATCH = "merged_count_mismatch"
CATEGORY_MANIFEST_INVALID = "manifest_invalid"


class FullSemesterAcceptanceError(CourseDataNormalizationError):
    """full-semester acceptance 失败（继承统一错误类型，便于调用方一处捕获）。

    `category` 是**机器可读**的失败类别；`shard_id`（可选）是**结构性**定位信息。
    """

    def __init__(
        self, message: str, *, category: str, shard_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.category = category
        self.shard_id = shard_id


@dataclass(frozen=True)
class InventoryShard:
    """已批准 inventory 里**一个 shard** 的条目。"""

    shard_id: str
    opening_school_number: str
    raw_bundle_sha256: str


@dataclass(frozen=True)
class CaptureInventory:
    """**已批准**的 capture inventory（人工 / Review 在 acquisition 审核时形成）。

    ⚠️ 这是 B2 的独立信任来源：它把
    `(semester, shard_id, openingSchoolNumber, raw_bundle_sha256)` 钉在一起，
    因此**调用方单独声明 label 不再足够**。
    ⛔ 本模块**无法**证明某个 inventory 文件确实经过了人工批准；
    它只能保证"正式 acceptance 必须消费一个 inventory 产物"，
    且该产物与 artifact 字节、campus acceptance 记录逐项一致。
    """

    semester: str
    shards: tuple[InventoryShard, ...]
    canonical_sha256: str

    @property
    def by_id(self) -> Mapping[str, InventoryShard]:
        return {shard.shard_id: shard for shard in self.shards}


@dataclass(frozen=True)
class ShardArtifact:
    """一个 shard 的**本地 raw bundle 路径**（以及可选的额外人工记录摘要）。

    ⚠️ 只接受**文件路径**：本模块必须能对**原始字节**计算 SHA-256。

    `expected_sha256`（可选）是负责人**事先记录**的该 artifact 原始字节摘要；
    给出时必须与字节、以及已批准 inventory 的摘要三方一致。
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
    campus_acceptance_sha256: str
    campus_source: str
    campus_offering_set_sha256: str
    page_count: int
    loaded_count: int
    reported_total: int


@dataclass(frozen=True)
class FullSemesterAcceptance:
    """full-semester acceptance 的结果（**内部对象**，不进 `schemas/`）。"""

    semester: str
    merged: OfferingSnapshot
    shards: tuple[FullSemesterShardRecord, ...]
    baseline_before: int
    baseline_after: int
    inventory_sha256: str
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

    @property
    def merged_offering_set_sha256(self) -> str:
        """**整批规范化内容**的确定性 digest（B3 的 content binding）。"""

        return offering_set_sha256(self.merged.offerings)


def full_semester_scope(semester: str) -> SnapshotScope:
    """`full_semester` 的 scope：`scope_id` **必须等于** semester。"""

    if not isinstance(semester, str) or not semester.strip():
        raise FullSemesterAcceptanceError(
            "semester 必须是非空字符串", category=CATEGORY_INVALID_SEMESTER
        )

    return SnapshotScope(
        scope_kind=SCOPE_KIND_FULL_SEMESTER, scope_id=semester.strip()
    )


def full_semester_source(semester: str) -> str:
    """`full_semester` 的 source audit label（**由 semester 完全决定**）。"""

    if not isinstance(semester, str) or not semester.strip():
        raise FullSemesterAcceptanceError(
            "semester 必须是非空字符串", category=CATEGORY_INVALID_SEMESTER
        )

    resolved = semester.strip()

    return f"capture://sysu/{resolved}/full-semester/{resolved}"


def campus_source_label(semester: str, opening_school_number: str) -> str:
    """campus 的 canonical source label（与 campus CLI 的模板**同一处定义**）。"""

    if not isinstance(semester, str) or not semester.strip():
        raise FullSemesterAcceptanceError(
            "semester 必须是非空字符串", category=CATEGORY_INVALID_SEMESTER
        )
    if (
        not isinstance(opening_school_number, str)
        or not opening_school_number.strip()
    ):
        raise FullSemesterAcceptanceError(
            "opening_school_number 必须是非空字符串",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
        )

    return (
        f"capture://sysu/{semester.strip()}/campus/"
        f"{opening_school_number.strip()}"
    )


def canonical_manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    """canonical 序列化（键排序 + 紧凑分隔符 + UTF-8 + `allow_nan=False`）。"""

    if not isinstance(manifest, Mapping):
        raise FullSemesterAcceptanceError(
            f"manifest 必须是对象，实际是 {type(manifest).__name__}",
            category=CATEGORY_MANIFEST_INVALID,
        )

    return json.dumps(
        dict(manifest),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def compute_manifest_sha256(manifest: Mapping[str, object]) -> str:
    """canonical manifest 字节的 SHA-256（十六进制小写）—— acceptance identity。"""

    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def canonical_inventory_bytes(inventory: Mapping[str, object]) -> bytes:
    """inventory 的 canonical 序列化（⛔ `shards` 必须已经按批准顺序排列）。"""

    return canonical_manifest_bytes(inventory)


def capture_inventory_bytes(inventory: CaptureInventory) -> bytes:
    """把一个 `CaptureInventory` 对象序列化成 canonical 字节（写盘 / 复现 identity）。"""

    if not isinstance(inventory, CaptureInventory):
        raise FullSemesterAcceptanceError(
            f"必须是 CaptureInventory，实际是 {type(inventory).__name__}",
            category=CATEGORY_INVENTORY_INVALID,
        )

    return canonical_inventory_bytes(
        _inventory_document(
            inventory.semester,
            {shard.shard_id: shard.raw_bundle_sha256 for shard in inventory.shards},
        )
    )


def _require_text(value: object, *, category: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FullSemesterAcceptanceError(
            f"{name} 必须是非空字符串", category=category
        )
    return value


def _require_non_negative_int(value: object, *, category: str, name: str) -> int:
    """非负整数（`bool` ⛔ 不算整数）。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise FullSemesterAcceptanceError(
            f"{name} 必须是整数，实际是 {type(value).__name__}", category=category
        )
    if value < 0:
        raise FullSemesterAcceptanceError(
            f"{name} 不能为负：{value}", category=category
        )
    return value


def _require_sha256_text(value: object, *, category: str, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.match(value) is None:
        raise FullSemesterAcceptanceError(
            f"{name} 必须是 64 位小写十六进制 SHA-256", category=category
        )
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """⛔ 重复 JSON key 一律拒绝（`json.loads` 默认会静默保留最后一个）。"""

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FullSemesterAcceptanceError(
                f"JSON 中出现重复键：{key!r}", category=CATEGORY_MANIFEST_INVALID
            )
        result[key] = value
    return result


def _load_json_strict(raw: bytes, *, category: str) -> object:
    """严格 JSON 解析：UTF-8（⛔ 不接受 BOM）、⛔ 不接受重复键、⛔ 不接受 NaN/Infinity。"""

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise FullSemesterAcceptanceError(
            f"必须是 bytes，实际是 {type(raw).__name__}", category=category
        )

    data = bytes(raw)
    if data.startswith(b"\xef\xbb\xbf"):
        raise FullSemesterAcceptanceError(
            "⛔ 不接受带 BOM 的 JSON", category=category
        )

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FullSemesterAcceptanceError(
            f"不是合法 UTF-8（第 {exc.start} 字节处）", category=category
        ) from exc

    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                FullSemesterAcceptanceError(
                    f"⛔ 不接受 JSON 常量 {value}（NaN / Infinity 没有确定性表示）",
                    category=category,
                )
            ),
        )
    except FullSemesterAcceptanceError:
        raise
    except json.JSONDecodeError as exc:
        raise FullSemesterAcceptanceError(
            f"不是合法 JSON（第 {exc.lineno} 行第 {exc.colno} 列）", category=category
        ) from exc


# --------------------------------------------------------------------------- #
# capture inventory
# --------------------------------------------------------------------------- #


def _inventory_document(
    semester: str, digests: Mapping[str, str]
) -> dict[str, object]:
    """按批准顺序构造 inventory 文档（⛔ 未批准的 shard 一律不写入）。"""

    return {
        "format": CAPTURE_INVENTORY_FORMAT,
        "inventory_version": CAPTURE_INVENTORY_VERSION,
        "semester": semester,
        "shards": [
            {
                "shard_id": shard.shard_id,
                "openingSchoolNumber": shard.opening_school_number,
                "raw_bundle_sha256": digests[shard.shard_id],
            }
            for shard in APPROVED_FULL_SEMESTER_SHARDS
        ],
    }


def build_capture_inventory(
    semester: str, digests: dict[str, str] | Mapping[str, str]
) -> CaptureInventory:
    """由 `{shard_id: raw_bundle_sha256}` 构造一个 inventory 对象（用于**草稿**生成）。

    ⚠️ 由本函数生成的只是**草稿**：⛔ 它不代表任何人工 / Review 批准。
    """

    resolved_semester = _require_text(
        semester, category=CATEGORY_INVALID_SEMESTER, name="semester"
    )

    if not isinstance(digests, Mapping):
        raise FullSemesterAcceptanceError(
            "digests 必须是 shard_id → sha256 的映射",
            category=CATEGORY_INVENTORY_INVALID,
        )

    wanted = {shard.shard_id for shard in APPROVED_FULL_SEMESTER_SHARDS}
    missing = sorted(wanted - set(digests))
    unexpected = sorted(set(digests) - wanted)
    if missing or unexpected:
        raise FullSemesterAcceptanceError(
            f"inventory 草稿必须覆盖 exact five-shard（缺少 {missing}，多出 {unexpected}）",
            category=CATEGORY_INVENTORY_INVALID,
        )

    for shard_id, digest in digests.items():
        _require_sha256_text(
            digest,
            category=CATEGORY_INVENTORY_INVALID,
            name=f"shards[{shard_id}].raw_bundle_sha256",
        )

    document = _inventory_document(resolved_semester, digests)

    return load_capture_inventory_bytes(canonical_inventory_bytes(document))


def load_capture_inventory(path: str | Path) -> CaptureInventory:
    """从本地文件读取并**严格校验**已批准 capture inventory。"""

    file_path = Path(path)
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        raise FullSemesterAcceptanceError(
            f"inventory 文件无法读取：{file_path.name}",
            category=CATEGORY_INVENTORY_INVALID,
        ) from exc

    return load_capture_inventory_bytes(raw)


def load_capture_inventory_bytes(raw: bytes) -> CaptureInventory:
    """严格校验 inventory 字节：exact five-shard、批准号码、digest 形态、无未知字段。"""

    document = _load_json_strict(raw, category=CATEGORY_INVENTORY_INVALID)

    if not isinstance(document, Mapping):
        raise FullSemesterAcceptanceError(
            "inventory 必须是 JSON 对象", category=CATEGORY_INVENTORY_INVALID
        )

    allowed = {"format", "inventory_version", "semester", "shards"}
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise FullSemesterAcceptanceError(
            f"inventory 出现未知字段：{unknown}", category=CATEGORY_INVENTORY_INVALID
        )
    if document.get("format") != CAPTURE_INVENTORY_FORMAT:
        raise FullSemesterAcceptanceError(
            f"inventory format 必须是 {CAPTURE_INVENTORY_FORMAT}",
            category=CATEGORY_INVENTORY_INVALID,
        )
    if document.get("inventory_version") != CAPTURE_INVENTORY_VERSION:
        raise FullSemesterAcceptanceError(
            f"inventory_version 必须是 {CAPTURE_INVENTORY_VERSION}",
            category=CATEGORY_INVENTORY_INVALID,
        )

    semester = _require_text(
        document.get("semester"),
        category=CATEGORY_INVENTORY_INVALID,
        name="inventory.semester",
    )

    shards = document.get("shards")
    if not isinstance(shards, list) or not shards:
        raise FullSemesterAcceptanceError(
            "inventory.shards 必须是非空数组", category=CATEGORY_INVENTORY_INVALID
        )

    parsed: dict[str, InventoryShard] = {}
    for index, entry in enumerate(shards):
        if not isinstance(entry, Mapping):
            raise FullSemesterAcceptanceError(
                f"inventory.shards[{index}] 必须是对象",
                category=CATEGORY_INVENTORY_INVALID,
            )
        entry_allowed = {"shard_id", "openingSchoolNumber", "raw_bundle_sha256"}
        entry_unknown = sorted(set(entry) - entry_allowed)
        if entry_unknown:
            raise FullSemesterAcceptanceError(
                f"inventory.shards[{index}] 出现未知字段：{entry_unknown}",
                category=CATEGORY_INVENTORY_INVALID,
            )

        shard_id = entry.get("shard_id")
        if not isinstance(shard_id, str) or shard_id not in _SHARDS_BY_ID:
            raise FullSemesterAcceptanceError(
                f"inventory.shards[{index}] 出现未批准的 shard；已批准集合是 "
                f"{[shard.shard_id for shard in APPROVED_FULL_SEMESTER_SHARDS]}",
                category=CATEGORY_UNKNOWN_SHARD,
            )
        if shard_id in parsed:
            raise FullSemesterAcceptanceError(
                f"inventory 中出现重复 shard：{shard_id}",
                category=CATEGORY_DUPLICATE_SHARD,
            )

        approved = _SHARDS_BY_ID[shard_id]
        number = entry.get("openingSchoolNumber")
        if number != approved.opening_school_number:
            raise FullSemesterAcceptanceError(
                f"inventory 中 {shard_id} 的 openingSchoolNumber 不是已批准值",
                category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
                shard_id=shard_id,
            )

        digest = _require_sha256_text(
            entry.get("raw_bundle_sha256"),
            category=CATEGORY_INVENTORY_INVALID,
            name=f"inventory.shards[{index}].raw_bundle_sha256",
        )

        parsed[shard_id] = InventoryShard(
            shard_id=shard_id,
            opening_school_number=approved.opening_school_number,
            raw_bundle_sha256=digest,
        )

    missing = [
        shard.shard_id
        for shard in APPROVED_FULL_SEMESTER_SHARDS
        if shard.shard_id not in parsed
    ]
    if missing:
        raise FullSemesterAcceptanceError(
            f"inventory 缺少已批准 shard：{missing}", category=CATEGORY_MISSING_SHARD
        )

    ordered = tuple(
        parsed[shard.shard_id] for shard in APPROVED_FULL_SEMESTER_SHARDS
    )
    digests = [shard.raw_bundle_sha256 for shard in ordered]
    if len(set(digests)) != len(digests):
        raise FullSemesterAcceptanceError(
            "inventory 中不同 shard 的 raw_bundle_sha256 必须两两不同"
            "（同一批字节不得被声明成两个校区）",
            category=CATEGORY_DUPLICATE_ARTIFACT,
        )

    canonical = canonical_inventory_bytes(
        _inventory_document(
            semester, {shard.shard_id: shard.raw_bundle_sha256 for shard in ordered}
        )
    )

    # ⚠️ 语义规范化：⛔ 不接受"重排 / 多余空白"以外的东西 ——
    #    inventory 是人工审核产物，必须**已经**是 canonical 形式，
    #    这样它的 SHA-256 才能被当作稳定的审核身份。
    if canonical != bytes(raw):
        raise FullSemesterAcceptanceError(
            "inventory 不是 canonical 形式（键顺序 / 空白 / shard 顺序不同）；"
            "⛔ 请使用本工具生成的 canonical inventory 副本",
            category=CATEGORY_INVENTORY_INVALID,
        )

    return CaptureInventory(
        semester=semester,
        shards=ordered,
        canonical_sha256=hashlib.sha256(canonical).hexdigest(),
    )


# --------------------------------------------------------------------------- #
# manifest（严格校验）
# --------------------------------------------------------------------------- #

_MANIFEST_ALLOWED_KEYS = {
    "format",
    "manifest_version",
    "tool",
    "semester",
    "scope_kind",
    "scope_id",
    "source",
    "inventory_sha256",
    "baseline_before",
    "baseline_after",
    "merged_offering_count",
    "merged_offering_set_sha256",
    "shards",
    "manifest_sha256_semantics",
    "raw_bundle_sha256_semantics",
    "offering_set_sha256_semantics",
    "source_semantics",
    "baseline_semantics",
    "completeness_semantics",
    "page_count_semantics",
    "campus_acceptance_semantics",
}

_MANIFEST_SHARD_ALLOWED_KEYS = {
    "shard_id",
    "openingSchoolNumber",
    "raw_bundle_sha256",
    "campus_acceptance_sha256",
    "campus_source",
    "campus_offering_set_sha256",
    "page_count",
    "loaded_count",
    "reported_total",
}


def validate_full_semester_manifest_bytes(raw: bytes) -> Mapping[str, object]:
    """严格校验一个 manifest 文件，并返回**按批准顺序规范化后**的 manifest。

    校验（任一不满足 ⇒ `FullSemesterAcceptanceError`）：

    ```text
    1. 严格 JSON：UTF-8 无 BOM、⛔ 无重复键、⛔ 无 NaN / Infinity
    2. ⛔ 无未知字段 / 未知 shard 字段；format / version / scope 精确匹配
    3. shards 恰好是已批准五校区（⛔ 无缺 / 无多 / 无重 / 无别名）
    4. 各计数为**非负整数**（⛔ 不接受 bool / float）；digest 形态为 64 位小写 hex
    5. `merged_offering_set_sha256` / `merged_offering_count` 与 shards 一致
    6. 语义规范化：shard 数组按**已批准顺序**重排，其余字段原样
    ```

    ⚠️ 与"写出时要求字节完全一致"不同：这里返回的是**语义 identity**
    （合法等价的 key 顺序 / shard 顺序不应改变 acceptance identity）。
    """

    document = _load_json_strict(raw, category=CATEGORY_MANIFEST_INVALID)

    if not isinstance(document, Mapping):
        raise FullSemesterAcceptanceError(
            "manifest 必须是 JSON 对象", category=CATEGORY_MANIFEST_INVALID
        )

    unknown = sorted(set(document) - _MANIFEST_ALLOWED_KEYS)
    if unknown:
        raise FullSemesterAcceptanceError(
            f"manifest 出现未知字段：{unknown}", category=CATEGORY_MANIFEST_INVALID
        )

    if document.get("format") != FULL_SEMESTER_ACCEPTANCE_FORMAT:
        raise FullSemesterAcceptanceError(
            f"manifest format 必须是 {FULL_SEMESTER_ACCEPTANCE_FORMAT}",
            category=CATEGORY_MANIFEST_INVALID,
        )
    if document.get("manifest_version") != FULL_SEMESTER_ACCEPTANCE_VERSION:
        raise FullSemesterAcceptanceError(
            f"manifest_version 必须是 {FULL_SEMESTER_ACCEPTANCE_VERSION}",
            category=CATEGORY_MANIFEST_INVALID,
        )
    if document.get("scope_kind") != SCOPE_KIND_FULL_SEMESTER:
        raise FullSemesterAcceptanceError(
            "manifest scope_kind 必须是 full_semester",
            category=CATEGORY_MANIFEST_INVALID,
        )

    semester = _require_text(
        document.get("semester"),
        category=CATEGORY_MANIFEST_INVALID,
        name="manifest.semester",
    )
    if document.get("scope_id") != semester:
        raise FullSemesterAcceptanceError(
            "manifest scope_id 必须等于 semester",
            category=CATEGORY_MANIFEST_INVALID,
        )

    _require_sha256_text(
        document.get("inventory_sha256"),
        category=CATEGORY_MANIFEST_INVALID,
        name="manifest.inventory_sha256",
    )
    _require_sha256_text(
        document.get("merged_offering_set_sha256"),
        category=CATEGORY_MANIFEST_INVALID,
        name="manifest.merged_offering_set_sha256",
    )
    _require_non_negative_int(
        document.get("baseline_before"),
        category=CATEGORY_MANIFEST_INVALID,
        name="manifest.baseline_before",
    )
    _require_non_negative_int(
        document.get("baseline_after"),
        category=CATEGORY_MANIFEST_INVALID,
        name="manifest.baseline_after",
    )
    merged_count = _require_non_negative_int(
        document.get("merged_offering_count"),
        category=CATEGORY_MANIFEST_INVALID,
        name="manifest.merged_offering_count",
    )

    shards = document.get("shards")
    if not isinstance(shards, list) or not shards:
        raise FullSemesterAcceptanceError(
            "manifest.shards 必须是非空数组", category=CATEGORY_MANIFEST_INVALID
        )

    parsed: dict[str, Mapping[str, object]] = {}
    total_reported = 0
    for index, entry in enumerate(shards):
        if not isinstance(entry, Mapping):
            raise FullSemesterAcceptanceError(
                f"manifest.shards[{index}] 必须是对象",
                category=CATEGORY_MANIFEST_INVALID,
            )
        entry_unknown = sorted(set(entry) - _MANIFEST_SHARD_ALLOWED_KEYS)
        if entry_unknown:
            raise FullSemesterAcceptanceError(
                f"manifest.shards[{index}] 出现未知字段：{entry_unknown}",
                category=CATEGORY_MANIFEST_INVALID,
            )

        shard_id = entry.get("shard_id")
        if not isinstance(shard_id, str) or shard_id not in _SHARDS_BY_ID:
            raise FullSemesterAcceptanceError(
                f"manifest.shards[{index}] 出现未批准的 shard",
                category=CATEGORY_UNKNOWN_SHARD,
            )
        if shard_id in parsed:
            raise FullSemesterAcceptanceError(
                f"manifest 中出现重复 shard：{shard_id}",
                category=CATEGORY_DUPLICATE_SHARD,
            )

        approved = _SHARDS_BY_ID[shard_id]
        if entry.get("openingSchoolNumber") != approved.opening_school_number:
            raise FullSemesterAcceptanceError(
                f"manifest 中 {shard_id} 的 openingSchoolNumber 不是已批准值",
                category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
                shard_id=shard_id,
            )

        _require_sha256_text(
            entry.get("raw_bundle_sha256"),
            category=CATEGORY_MANIFEST_INVALID,
            name=f"manifest.shards[{index}].raw_bundle_sha256",
        )
        _require_sha256_text(
            entry.get("campus_acceptance_sha256"),
            category=CATEGORY_MANIFEST_INVALID,
            name=f"manifest.shards[{index}].campus_acceptance_sha256",
        )
        _require_sha256_text(
            entry.get("campus_offering_set_sha256"),
            category=CATEGORY_MANIFEST_INVALID,
            name=f"manifest.shards[{index}].campus_offering_set_sha256",
        )
        loaded = _require_non_negative_int(
            entry.get("loaded_count"),
            category=CATEGORY_MANIFEST_INVALID,
            name=f"manifest.shards[{index}].loaded_count",
        )
        reported = _require_non_negative_int(
            entry.get("reported_total"),
            category=CATEGORY_MANIFEST_INVALID,
            name=f"manifest.shards[{index}].reported_total",
        )
        _require_non_negative_int(
            entry.get("page_count"),
            category=CATEGORY_MANIFEST_INVALID,
            name=f"manifest.shards[{index}].page_count",
        )
        if loaded != reported:
            raise FullSemesterAcceptanceError(
                f"manifest 中 {shard_id} 的 loaded_count != reported_total",
                category=CATEGORY_SHARD_NOT_COMPLETE,
                shard_id=shard_id,
            )
        total_reported += reported
        parsed[shard_id] = entry

    missing = [
        shard.shard_id
        for shard in APPROVED_FULL_SEMESTER_SHARDS
        if shard.shard_id not in parsed
    ]
    if missing:
        raise FullSemesterAcceptanceError(
            f"manifest 缺少已批准 shard：{missing}", category=CATEGORY_MISSING_SHARD
        )

    if total_reported != merged_count:
        raise FullSemesterAcceptanceError(
            f"manifest 中 Σ shard reported_total({total_reported}) != "
            f"merged_offering_count({merged_count})",
            category=CATEGORY_MERGED_COUNT_MISMATCH,
        )

    normalized = dict(document)
    normalized["shards"] = [
        parsed[shard.shard_id] for shard in APPROVED_FULL_SEMESTER_SHARDS
    ]

    return normalized


# --------------------------------------------------------------------------- #
# acceptance
# --------------------------------------------------------------------------- #


def _offering_fingerprint(offering: CourseOffering) -> str:
    """一条教学班的**全部公共字段**指纹（用于区分"重复"与"冲突"）。

    ⚠️ **`source` 归一化**：每个 shard 的规范化内容带着**该校区自己的 campus
    source label**（B2 内容绑定需要），因此"同一教学班在两个 shard 出现"
    天然只有 `source` 不同。若把该标注差异当成"内容冲突"，就会失去
    "重复 identity" 这一独立信号。这里只对 `source` 归一化，
    ⛔ 其它任何公共字段差异仍然算冲突。

    ⛔ 只在内存中比较，⛔ 不写进 manifest、⛔ 不进错误信息。
    """

    payload = offering.model_dump(mode="json")
    payload["source"] = "<per-shard campus source label>"

    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
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
    """校验 shard 集合**恰好等于**已批准五校区，并按已批准顺序返回。"""

    if isinstance(shard_artifacts, (str, bytes)) or not isinstance(
        shard_artifacts, Sequence
    ):
        raise FullSemesterAcceptanceError(
            f"shard_artifacts 必须是 ShardArtifact 序列，实际是 "
            f"{type(shard_artifacts).__name__}",
            category=CATEGORY_UNKNOWN_SHARD,
        )

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
            raise FullSemesterAcceptanceError(
                f"出现未批准的 shard（位置 {index}）；已批准集合是 "
                f"{[shard.shard_id for shard in APPROVED_FULL_SEMESTER_SHARDS]}",
                category=CATEGORY_UNKNOWN_SHARD,
            )
        if shard_id in by_id:
            raise FullSemesterAcceptanceError(
                f"重复的 shard：{shard_id}", category=CATEGORY_DUPLICATE_SHARD
            )
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


def _read_shard_bundle_once(
    artifact: ShardArtifact, *, label: str
) -> tuple[bytes, str, Mapping[str, object], int]:
    """**一次**读取 → SHA-256 → 用**同一批字节**解析（B1）。

    ⚠️ 复读只作为**额外的变动探测**；"digest 与 payload 同源"由
    "只读一次 + `load_capture_bundle_bytes(raw)`"保证。
    """

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

    try:
        bundle = load_capture_bundle_bytes(raw_bytes)
    except CourseDataNormalizationError as exc:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 bundle（{path.name}）不是合法的 Capture Bundle",
            category=CATEGORY_INVALID_BUNDLE,
            shard_id=label,
        ) from exc

    # ⛔ 额外变动探测（**不**承担同源职责）：采集期间被改写的 artifact 不得被接受。
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


def _require_campus_acceptance(
    campus_store_path: str | Path,
    *,
    semester: str,
    inventory_shard: InventoryShard,
    snapshot: OfferingSnapshot,
    page_count: int,
) -> FullSemesterShardRecord:
    """B2：把该 shard 的 artifact 绑定到一个**独立**的 campus acceptance 记录。"""

    label = inventory_shard.shard_id
    digest = inventory_shard.raw_bundle_sha256
    expected_source = campus_source_label(semester, inventory_shard.opening_school_number)

    try:
        records = load_course_data_acceptances(campus_store_path, semester=semester)
    except CourseDataStoreError as exc:
        raise FullSemesterAcceptanceError(
            f"无法读取 campus acceptance 记录（shard {label}）",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISSING,
            shard_id=label,
        ) from exc

    matching = [record for record in records if record.artifact_sha256 == digest]

    if not matching:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 artifact digest 没有对应的已导入 campus acceptance 记录；"
            f"⛔ 必须先以 campus scope 正式接受该 artifact",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISSING,
            shard_id=label,
        )

    if len(matching) != 1:
        raise FullSemesterAcceptanceError(
            f"同一批字节在同一学期内出现了 {len(matching)} 条 acceptance 记录；"
            f"⛔ 一份 artifact 只能对应一个 campus scope",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            shard_id=label,
        )

    record = matching[0]

    if record.scope_kind != SCOPE_KIND_CAMPUS:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 acceptance 记录 scope_kind 不是 campus",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            shard_id=label,
        )
    if record.scope_id != inventory_shard.opening_school_number:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 acceptance scope_id 与已批准 openingSchoolNumber 不一致；"
            f"⛔ 拒绝「调用方自称的校区」",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            shard_id=label,
        )
    if record.source != expected_source:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 acceptance source label 不是 canonical campus label",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            shard_id=label,
        )
    if record.completeness != "complete":
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 campus acceptance 不是 complete",
            category=CATEGORY_SHARD_NOT_COMPLETE,
            shard_id=label,
        )
    if (
        record.reported_total is None
        or record.loaded_count != record.reported_total
        or record.loaded_count != record.offering_count
        or record.offering_count != snapshot.loaded_count
        or record.reported_total != snapshot.reported_total
    ):
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 campus acceptance 计数与该 artifact 解析结果不一致；"
            f"⛔ 不接受「行数碰巧相等」的替代记录",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            shard_id=label,
        )

    snapshot_set_digest = offering_set_sha256(snapshot.offerings)
    if record.offering_set_sha256 != snapshot_set_digest:
        raise FullSemesterAcceptanceError(
            f"shard {label} 的 campus acceptance 内容 digest 与本次解析结果不一致；"
            f"⛔ 同一批字节的内容被替换过",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            shard_id=label,
        )

    return FullSemesterShardRecord(
        shard_id=label,
        opening_school_number=inventory_shard.opening_school_number,
        raw_bundle_sha256=digest,
        campus_acceptance_sha256=record.artifact_sha256,
        campus_source=record.source or "",
        campus_offering_set_sha256=record.offering_set_sha256,
        page_count=page_count,
        loaded_count=snapshot.loaded_count,
        reported_total=int(snapshot.reported_total),
    )


def accept_full_semester_capture_set(
    *,
    expected_semester: str,
    baseline_before: int,
    baseline_after: int,
    shard_artifacts: Sequence[ShardArtifact],
    inventory: CaptureInventory,
    campus_store_path: str | Path,
) -> FullSemesterAcceptance:
    """把**五个已批准校区**的 raw Capture Bundle 验收成一份 full-semester acceptance。

    必需输入（⛔ 没有任何可选 / 跳过路径）：

    ```text
    expected_semester   目标学期
    baseline_before/after  采集窗口前后的**总量证据**（必须相等）
    shard_artifacts     exact five-shard 的 raw bundle 路径
    inventory           已批准 capture inventory（B2：独立 scope 绑定）
    campus_store_path   已导入 campus acceptance 记录的 SQLite 库（B2）
    ```
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

    if not isinstance(inventory, CaptureInventory):
        raise FullSemesterAcceptanceError(
            "必须提供已批准 CaptureInventory（⛔ 不接受「调用方自称的 label」）",
            category=CATEGORY_INVENTORY_INVALID,
        )
    if inventory.semester != semester:
        raise FullSemesterAcceptanceError(
            f"inventory semester({inventory.semester!r}) != 期望 semester({semester!r})",
            category=CATEGORY_SEMESTER_MISMATCH,
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
    inventory_by_id = inventory.by_id

    shard_snapshots: list[OfferingSnapshot] = []
    records: list[FullSemesterShardRecord] = []
    sum_shard_reported_total = 0
    total_loaded_rows = 0
    seen_identity: dict[tuple[str, str, str], tuple[str, str]] = {}
    seen_digests: set[str] = set()

    for artifact in ordered:
        approved = _SHARDS_BY_ID[artifact.shard_id]
        label = approved.shard_id
        inventory_shard = inventory_by_id[label]

        _, raw_sha256, bundle, page_count = _read_shard_bundle_once(
            artifact, label=label
        )

        # ---- B2：artifact 字节必须等于已批准 inventory 钉住的 digest -----------
        if raw_sha256 != inventory_shard.raw_bundle_sha256:
            raise FullSemesterAcceptanceError(
                f"shard {label} 的 artifact 原始字节与该 shard 已批准 inventory 的 "
                f"digest 不一致",
                category=CATEGORY_INVENTORY_DIGEST_MISMATCH,
                shard_id=label,
            )

        if artifact.expected_sha256 is not None:
            if (
                not isinstance(artifact.expected_sha256, str)
                or artifact.expected_sha256.strip().lower() != raw_sha256
            ):
                raise FullSemesterAcceptanceError(
                    f"shard {label} 的 bundle 原始字节 SHA-256 与事先记录的摘要不一致",
                    category=CATEGORY_BUNDLE_DIGEST_MISMATCH,
                    shard_id=label,
                )

        if raw_sha256 in seen_digests:
            # ⚠️ inventory 已经强制五个 digest 两两不同；本句是**纵深防御**
            #    （万一将来放宽 inventory 校验，这里仍然拦得住）。
            raise FullSemesterAcceptanceError(
                f"shard {label} 与其它 shard 的 artifact 字节完全相同；"
                f"⛔ 同一批字节不得被声明成两个校区",
                category=CATEGORY_DUPLICATE_ARTIFACT,
                shard_id=label,
            )
        seen_digests.add(raw_sha256)

        if bundle["semester"] != semester:
            raise FullSemesterAcceptanceError(
                f"shard {label} 的 bundle semester({bundle['semester']!r}) != "
                f"期望 semester({semester!r})",
                category=CATEGORY_SEMESTER_MISMATCH,
                shard_id=label,
            )

        # ⚠️ 每个 shard 先用**该校区自己的 campus source label** 解析：
        #    这样它与已导入的 campus acceptance 的规范化内容（含 `source` 字段）
        #    逐字节可比（B2 / B3 的内容绑定）。合并之后统一改写为 full-semester label。
        shard_source = campus_source_label(
            semester, inventory_shard.opening_school_number
        )
        try:
            snapshot = collect_captured_pages_snapshot(bundle, source=shard_source)
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
            # 后半句由 OfferingSnapshot 不变量保证（complete ⇒ loaded == reported）。
            raise FullSemesterAcceptanceError(
                f"shard {label} 不是 complete 快照（completeness="
                f"{snapshot.completeness!r}，loaded_count={snapshot.loaded_count}，"
                f"reported_total={snapshot.reported_total}）",
                category=CATEGORY_SHARD_NOT_COMPLETE,
                shard_id=label,
            )

        if snapshot.loaded_count == 0:
            raise FullSemesterAcceptanceError(
                f"shard {label} 的载荷为空（loaded_count=0）；"
                f"已批准校区不可能是空集，拒绝接受",
                category=CATEGORY_EMPTY_SHARD,
                shard_id=label,
            )

        # ---- B2：独立 campus acceptance 绑定 ---------------------------------
        record = _require_campus_acceptance(
            campus_store_path,
            semester=semester,
            inventory_shard=inventory_shard,
            snapshot=snapshot,
            page_count=page_count,
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

        shard_reported_total = int(snapshot.reported_total)
        sum_shard_reported_total += shard_reported_total
        total_loaded_rows += snapshot.loaded_count

        shard_snapshots.append(snapshot)
        records.append(record)

    if sum_shard_reported_total != stable_baseline:
        raise FullSemesterAcceptanceError(
            f"各 shard reported_total 之和({sum_shard_reported_total}) != "
            f"稳定 baseline({stable_baseline})；分片未覆盖全体或与基线不一致",
            category=CATEGORY_SHARD_COVERAGE_MISMATCH,
        )

    try:
        merged_shards = merge_offering_snapshots(
            shard_snapshots, baseline_total=stable_baseline
        )
    except CourseDataNormalizationError as exc:
        raise FullSemesterAcceptanceError(
            "合并五个 shard 快照失败（底层 merge_offering_snapshots 判定不满足）",
            category=CATEGORY_MERGE_FAILED,
        ) from exc

    # ⚠️ 合并后把每行的 `source` 统一改写为 full-semester audit label：
    #    merged 快照是**一次 full-semester acceptance 的产物**（单一 label），
    #    而每个 shard 的原始 campus label 已如实记录在 manifest 的
    #    `shards[].campus_source` 与 campus acceptance 记录里。
    merged = OfferingSnapshot(
        semester=merged_shards.semester,
        offerings=tuple(
            offering.model_copy(update={"source": source})
            for offering in merged_shards.offerings
        ),
        completeness=merged_shards.completeness,
        reported_total=merged_shards.reported_total,
    )

    merged_loaded = merged.loaded_count
    unique_identity_count = len({_class_key(offering) for offering in merged.offerings})

    if not merged.is_complete:
        raise FullSemesterAcceptanceError(
            "合并结果不是 complete 快照", category=CATEGORY_MERGED_COUNT_MISMATCH
        )

    if merged_loaded != total_loaded_rows or merged_loaded != stable_baseline:
        # ⚠️ 后半句与下面的 unique identity 复核互为冗余（正常形态下两者等价）：
        #    纵深防御，⛔ 不删除。
        raise FullSemesterAcceptanceError(
            f"合并后物化行数({merged_loaded}) != 各 shard 已加载行数之和"
            f"({total_loaded_rows}) 或 != baseline({stable_baseline})",
            category=CATEGORY_MERGED_COUNT_MISMATCH,
        )

    if unique_identity_count != stable_baseline:
        raise FullSemesterAcceptanceError(
            f"合并后 unique identity 数({unique_identity_count}) != "
            f"baseline({stable_baseline})",
            category=CATEGORY_MERGED_COUNT_MISMATCH,
        )

    merged_set_digest = offering_set_sha256(merged.offerings)

    manifest: dict[str, object] = {
        "format": FULL_SEMESTER_ACCEPTANCE_FORMAT,
        "manifest_version": FULL_SEMESTER_ACCEPTANCE_VERSION,
        "tool": FULL_SEMESTER_ACCEPTANCE_TOOL,
        "semester": semester,
        "scope_kind": SCOPE_KIND_FULL_SEMESTER,
        "scope_id": semester,
        "source": source,
        "inventory_sha256": inventory.canonical_sha256,
        "baseline_before": resolved_before,
        "baseline_after": resolved_after,
        "merged_offering_count": merged_loaded,
        "merged_offering_set_sha256": merged_set_digest,
        "shards": [
            {
                "shard_id": record.shard_id,
                "openingSchoolNumber": record.opening_school_number,
                "raw_bundle_sha256": record.raw_bundle_sha256,
                "campus_acceptance_sha256": record.campus_acceptance_sha256,
                "campus_source": record.campus_source,
                "campus_offering_set_sha256": record.campus_offering_set_sha256,
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
        "offering_set_sha256_semantics": (
            "exact_normalized_offering_content_of_the_accepted_dataset"
        ),
        "campus_acceptance_semantics": (
            "independently_imported_campus_scope_acceptance_for_the_same_bytes"
        ),
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
        inventory_sha256=inventory.canonical_sha256,
        manifest=manifest,
        manifest_sha256=compute_manifest_sha256(manifest),
    )
