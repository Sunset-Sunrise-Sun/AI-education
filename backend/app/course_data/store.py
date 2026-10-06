"""Course Data **本地持久化层**（SQLite，标准库 `sqlite3`，**零网络**）。

```text
Capture Bundle
        ↓  load_capture_bundle() / collect_captured_pages_snapshot()   （现有入口，本模块⛔不碰）
OfferingSnapshot（completeness 已由上游判定）
        ↓  import_offering_snapshot(...)                                （本模块）
本地 SQLite Course Data 库
        ↓  load_course_offerings(...)                                   （本模块）
list[CourseOffering]（公共契约对象）
```

这是**比赛 MVP 的本地课程数据库**，不是实时爬虫：
采集仍然由浏览器侧显式触发，本模块只负责"把已经标准化的结果落到本地、再读出来"。

## 本模块做什么

- 把**已经标准化**的公共 `CourseOffering` 落进本地 SQLite；
- 按 identity `(semester, course_id, class_id)` **upsert**：
  同一 artifact 重复导入**幂等**，⛔ **不会按 `course_id` 单独覆盖不同教学班**；
- 记录 provenance：`source` / `imported_at` / `artifact_sha256`；
- 提供两种查询：按 `semester` 取全部、按 `semester` + `course_id` 集合取候选教学班
  （Case A / Planner 主要用第二种）。

## 本模块**不**做什么（硬边界）

- ⛔ **不判断 completeness**：只接受上游已经判定为 `complete`（**在其声明 scope 内**）的
  `OfferingSnapshot`（`is_complete == false` → 拒绝写入 approved 路径），
  也⛔ **不**在库里写任何"这份数据完整"的自我声明；
- ⛔ 不接触 Capture Bundle / `captured_pages.py` / `sharded_capture.py` /
  collector / `planning_runtime.py` / PR #39 / `schemas/**` / Planner / Curriculum / frontend；
- ⛔ 不联网、不读取 / 不保存任何认证材料；
- ⛔ **不新增公共 Schema**：只持久化公共 `CourseOffering` **已有**的字段。

## scope：`complete` **只在声明的 scope 内**成立（⛔ 不得改成全局含义）

同一份 `is_complete == True` 可能是三种完全不同的东西，
因此 import **必须由调用方显式声明 scope**（`SnapshotScope`）：

```text
campus        / <openingSchoolNumber>   某个校区 shard（例如 5062202）
full_semester / <semester>              整个学期（例如 2026-1）
```

```text
is_complete == complete **within the declared scope**
```

⛔ `complete` **不得**被解释为"全学期完整"：
一个 `campus` 快照完整只说明**那个校区**在本次采集内取满了；
本层⛔ 不产生任何 global completeness 暗示，也⛔ 不从
`source` / 文件名 / rows **推断** scope —— 只如实记录调用方声明的那一个。

⚠️ 按 case 裁剪的 scope（Case-A-scoped）的 id 语义尚未确证，
因此**暂不在白名单内**（见 `ALLOWED_SCOPE_KINDS`）：这类快照当前会被明确拒绝，
而不是被塞进一个含糊的 kind。

## `artifact_sha256` 的口径（⛔ 不得改动）

```text
SHA-256 = artifact identity / integrity
        ≠ acquisition provenance proof
```

它只说明"这份 artifact 的字节没变"，
⛔ **不证明**它是什么时候、由谁、在什么授权状态下采集的，
也⛔ 不得被当作采集来源的合规证明。本模块只是**如实记录**调用方给出的这个值。

## 两个平面（⛔ 不得混同）

```text
声明平面 / 历史审计：course_data_import          —— 调用方声明"以哪个 scope 导入了什么"
content-bound 平面： course_data_acceptance      —— 同一份声明 + 整批内容 digest
                     course_data_acceptance_member —— 逐 identity 的内容指纹
```

- 两个平面在**同一次 import 事务**里写入；
- ⛔ "import 成功"**不等于**"可以拿来当 production readiness"：
  只有 `load_accepted_offerings()`（同时核对两个平面 + membership + 逐行内容指纹 +
  整批 digest）通过，才说明"当前 rows 仍精确等于被接受的那批内容"；
- ⛔ 只比较 `offering_count` / identity 集合**不够**：同数量、同身份的"内容替换"
  必须被发现（见 `offering_digest.py`）。

## 数据边界（⛔ 只存已标准化的公共对象）

不存：Cookie / token / 登录信息 / 原始完整 response / 教师隐私扩展字段 / 学生信息。
公共 `CourseOffering.teacher` 是**公共契约字段**，按原值保存；
真实链路里 collector 已把教师脱敏为 `REDACTED`，因此本层不会引入新的个人信息。

## 与 Provider 的关系

⛔ 本模块**不**改 `SnapshotCourseDataProvider`、⛔ 也**不**改
`CourseDataProvider` 公共边界（`docs/interfaces/integration.md` 已冻结）。
"是否把 Provider 接到 SQLite" 是后续独立的 Architecture 决策。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.course_data.errors import CourseDataNormalizationError
from app.course_data.offering_digest import (
    offering_identity,
    offering_payload_sha256,
    offering_set_sha256,
)
from app.course_data.snapshot import OfferingSnapshot
from app.models.contracts import CourseOffering, DataSource, Meeting

__all__ = [
    "ACCEPTANCE_MEMBER_TABLE",
    "ACCEPTANCE_TABLE",
    "ALLOWED_SCOPE_KINDS",
    "ARTIFACT_SHA256_PATTERN",
    "COURSE_OFFERING_TABLE",
    "IMPORT_RECORD_TABLE",
    "SCOPE_KIND_CAMPUS",
    "SCOPE_KIND_FULL_SEMESTER",
    "AcceptedDataset",
    "CourseDataAcceptance",
    "CourseDataImport",
    "CourseDataProvenance",
    "CourseDataStoreError",
    "SnapshotScope",
    "compute_artifact_sha256",
    "import_offering_snapshot",
    "initialize_course_data_store",
    "load_accepted_offerings",
    "load_course_data_acceptances",
    "load_course_data_provenance",
    "load_course_offerings",
    "load_course_offerings_for_acceptance",
]

#: 教学班表（identity 是主键：⛔ 不允许按 `course_id` 覆盖不同教学班）。
COURSE_OFFERING_TABLE = "course_offering"

#: 导入记录表（artifact 级 provenance；同一 artifact **在同一 scope 下**只记首次导入）。
IMPORT_RECORD_TABLE = "course_data_import"

#: **acceptance 元数据表**（content-bound 平面）：一次被接受的 artifact 的
#: scope / 计数 / **整批内容 digest**（`offering_set_sha256`）。
ACCEPTANCE_TABLE = "course_data_acceptance"

#: **acceptance membership 表**：逐 identity 记录该 acceptance 接受了哪些教学班，
#: 以及每行的内容指纹（`offering_payload_sha256`）。
ACCEPTANCE_MEMBER_TABLE = "course_data_acceptance_member"

#: `artifact_sha256` 的形状：64 位十六进制（大小写都接受，落库统一小写）。
ARTIFACT_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

#: scope 的一个 kind：**校区 shard** 快照，`scope_id` = 该校区的 `openingSchoolNumber`。
SCOPE_KIND_CAMPUS = "campus"

#: scope 的一个 kind：**全学期**快照，`scope_id` = 该学期（必须等于快照 semester）。
SCOPE_KIND_FULL_SEMESTER = "full_semester"

#: 允许声明的 scope kind **白名单**（⛔ 不猜、⛔ 不放开为任意字符串）。
#:
#: ⚠️ Case-A-scoped（按某个 case 的课程集合裁剪）的 `scope_id` 取形**尚未确证**，
#: 因此**暂不在白名单内**：这类快照当前会被明确拒绝，而不是被塞进一个含糊的 kind。
#: 需要时请先给出它的 id 语义（case id？课程集合摘要？），再按流程加入。
ALLOWED_SCOPE_KINDS: tuple[str, ...] = (SCOPE_KIND_CAMPUS, SCOPE_KIND_FULL_SEMESTER)

#: 教学班表的**数据列**（参与"内容是否变化"的比较；provenance 列不参与）。
_DATA_COLUMNS = (
    "course_name",
    "teacher",
    "credit",
    "capacity",
    "remaining_capacity",
    "source",
    "data_source",
    "meetings_json",
)

#: 读回来时用于重建 `CourseOffering` 的列顺序。
_LOAD_COLUMNS = ("semester", "course_id", "class_id", *_DATA_COLUMNS)

_DDL = f"""
CREATE TABLE IF NOT EXISTS {COURSE_OFFERING_TABLE} (
    semester            TEXT    NOT NULL,
    course_id           TEXT    NOT NULL,
    class_id            TEXT    NOT NULL,
    course_name         TEXT    NOT NULL,
    teacher             TEXT,
    credit              REAL,
    capacity            INTEGER,
    remaining_capacity  INTEGER,
    source              TEXT,
    data_source         TEXT    NOT NULL,
    meetings_json       TEXT    NOT NULL,
    artifact_sha256     TEXT    NOT NULL,
    imported_at         TEXT    NOT NULL,
    scope_kind          TEXT    NOT NULL,
    scope_id            TEXT    NOT NULL,
    PRIMARY KEY (semester, course_id, class_id)
);

CREATE TABLE IF NOT EXISTS {IMPORT_RECORD_TABLE} (
    artifact_sha256     TEXT    NOT NULL,
    semester            TEXT    NOT NULL,
    scope_kind          TEXT    NOT NULL,
    scope_id            TEXT    NOT NULL,
    source              TEXT,
    imported_at         TEXT    NOT NULL,
    completeness        TEXT    NOT NULL,
    loaded_count        INTEGER NOT NULL,
    reported_total      INTEGER,
    offering_count      INTEGER NOT NULL,
    PRIMARY KEY (artifact_sha256, semester, scope_kind, scope_id)
);

CREATE TABLE IF NOT EXISTS {ACCEPTANCE_TABLE} (
    artifact_sha256      TEXT    NOT NULL,
    semester             TEXT    NOT NULL,
    scope_kind           TEXT    NOT NULL,
    scope_id             TEXT    NOT NULL,
    source               TEXT,
    imported_at          TEXT    NOT NULL,
    completeness         TEXT    NOT NULL,
    loaded_count         INTEGER NOT NULL,
    reported_total       INTEGER,
    offering_count       INTEGER NOT NULL,
    offering_set_sha256  TEXT    NOT NULL,
    canonical_manifest_json TEXT,
    PRIMARY KEY (artifact_sha256, semester, scope_kind, scope_id)
);

CREATE TABLE IF NOT EXISTS {ACCEPTANCE_MEMBER_TABLE} (
    artifact_sha256          TEXT NOT NULL,
    semester                 TEXT NOT NULL,
    scope_kind               TEXT NOT NULL,
    scope_id                 TEXT NOT NULL,
    course_id                TEXT NOT NULL,
    class_id                 TEXT NOT NULL,
    offering_payload_sha256  TEXT NOT NULL,
    PRIMARY KEY (
        artifact_sha256, semester, scope_kind, scope_id, course_id, class_id
    )
);
"""

_REQUIRED_TABLES = (
    COURSE_OFFERING_TABLE,
    IMPORT_RECORD_TABLE,
    ACCEPTANCE_TABLE,
    ACCEPTANCE_MEMBER_TABLE,
)

#: 当前 schema 的列清单（用于识别**过旧**的本地库并给出明确提示，⛔ 不自动迁移）。
_EXPECTED_COLUMNS: dict[str, tuple[str, ...]] = {
    COURSE_OFFERING_TABLE: (
        "semester",
        "course_id",
        "class_id",
        "course_name",
        "teacher",
        "credit",
        "capacity",
        "remaining_capacity",
        "source",
        "data_source",
        "meetings_json",
        "artifact_sha256",
        "imported_at",
        "scope_kind",
        "scope_id",
    ),
    IMPORT_RECORD_TABLE: (
        "artifact_sha256",
        "semester",
        "scope_kind",
        "scope_id",
        "source",
        "imported_at",
        "completeness",
        "loaded_count",
        "reported_total",
        "offering_count",
    ),
    ACCEPTANCE_TABLE: (
        "artifact_sha256",
        "semester",
        "scope_kind",
        "scope_id",
        "source",
        "imported_at",
        "completeness",
        "loaded_count",
        "reported_total",
        "offering_count",
        "offering_set_sha256",
        "canonical_manifest_json",
    ),
    ACCEPTANCE_MEMBER_TABLE: (
        "artifact_sha256",
        "semester",
        "scope_kind",
        "scope_id",
        "course_id",
        "class_id",
        "offering_payload_sha256",
    ),
}


class CourseDataStoreError(CourseDataNormalizationError):
    """本地 Course Data 库读写失败（继承统一错误类型，便于调用方一处捕获）。"""


class ImmutableAcceptanceConflictError(CourseDataStoreError):
    """同一个 acceptance identity（SHA）被以**不同语义内容**再次提交。

    ```text
    acceptance_sha256 X 一旦落库，就永久绑定：
      semester / scope / baseline / shard acceptance identities / raw shard digests /
      offering_set_sha256 / counts / membership（identity + 逐行内容指纹）
    ```

    ⛔ 因此**不存在**"用同一个 X 再导入一次 Dataset B"这条路径：
    语义内容不同一律 fail closed（`immutable_acceptance_conflict`），
    ⛔ 绝不刷新既有 acceptance / membership 的 digest。
    """


#: `course_data_acceptance` 的 canonical manifest 列允许的最小字段集。
#: ⛔ 这些字段必须与列式 metadata 完全一致（见 `_require_manifest_matches_metadata`）。
_MANIFEST_REQUIRED_KEYS = (
    "format",
    "manifest_version",
    "semester",
    "scope_kind",
    "scope_id",
    "inventory_sha256",
    "baseline_before",
    "baseline_after",
    "merged_offering_count",
    "merged_offering_set_sha256",
    "shards",
)

#: canonical manifest 允许出现的**全部**字段（⛔ 未知字段一律拒绝）。
_MANIFEST_ALLOWED_KEYS = frozenset(
    {
        *_MANIFEST_REQUIRED_KEYS,
        "tool",
        "source",
        "manifest_sha256_semantics",
        "raw_bundle_sha256_semantics",
        "offering_set_sha256_semantics",
        "campus_acceptance_semantics",
        "source_semantics",
        "baseline_semantics",
        "completeness_semantics",
        "page_count_semantics",
    }
)


def canonical_manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    """canonical manifest 序列化（⛔ 与 acceptance 层必须**字节一致**）。

    口径固定：`sort_keys=True` + `ensure_ascii=False` + `separators=(",", ":")`
    + `allow_nan=False` + UTF-8。因此

    ```text
    SHA256(canonical_manifest_bytes(manifest)) == acceptance_sha256
    ```

    是一个**可重算**的不变量，而不是"数据库自己派生出来的数字"。
    """

    if not isinstance(manifest, Mapping):
        raise CourseDataStoreError(
            f"canonical manifest 必须是对象，实际是 {type(manifest).__name__}"
        )

    try:
        return json.dumps(
            dict(manifest),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CourseDataStoreError(
            "canonical manifest 无法序列化（可能存在 NaN / Infinity 或非 JSON 值）"
        ) from exc


def compute_manifest_sha256(manifest: Mapping[str, object]) -> str:
    """canonical manifest 字节的 SHA-256（= acceptance identity）。"""

    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def _require_stored_manifest_shape(manifest: object) -> Mapping[str, object]:
    """严格校验 manifest 形状（⛔ 未知字段 / 缺字段 / 类型错误一律拒绝）。"""

    if not isinstance(manifest, Mapping):
        raise CourseDataStoreError(
            f"stored canonical manifest 必须是对象，实际是 {type(manifest).__name__}"
        )

    missing = [key for key in _MANIFEST_REQUIRED_KEYS if key not in manifest]
    if missing:
        raise CourseDataStoreError(f"stored canonical manifest 缺少字段：{missing}")

    unknown = sorted(set(manifest) - _MANIFEST_ALLOWED_KEYS)
    if unknown:
        raise CourseDataStoreError(f"stored canonical manifest 出现未知字段：{unknown}")

    for name in (
        "baseline_before",
        "baseline_after",
        "merged_offering_count",
    ):
        value = manifest[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CourseDataStoreError(
                f"stored canonical manifest 的 {name} 必须是非负整数"
            )

    for name in ("inventory_sha256", "merged_offering_set_sha256"):
        value = manifest[name]
        if not isinstance(value, str) or ARTIFACT_SHA256_PATTERN.match(value) is None:
            raise CourseDataStoreError(
                f"stored canonical manifest 的 {name} 必须是 64 位十六进制摘要"
            )

    shards = manifest["shards"]
    if not isinstance(shards, list) or not shards:
        raise CourseDataStoreError("stored canonical manifest 的 shards 必须是非空数组")

    return dict(manifest)


def _require_manifest_matches_metadata(
    manifest: Mapping[str, object],
    *,
    digest: str,
    semester: str,
    scope: SnapshotScope,
    completeness: str,
    loaded_count: int,
    reported_total: int | None,
    offering_count: int,
    set_digest: str,
) -> None:
    """canonical manifest 的语义字段必须与列式 metadata / 本次快照**完全一致**。"""

    # 1) identity：SHA256(canonical manifest) 必须等于本次 acceptance SHA。
    if compute_manifest_sha256(manifest) != digest:
        raise CourseDataStoreError(
            "canonical manifest 的 SHA-256 与 acceptance identity（artifact_sha256）不一致；"
            "⛔ 拒绝把一份 manifest 声明成另一个 identity"
        )

    # 2) 语义字段逐项一致。
    if manifest["semester"] != semester:
        raise CourseDataStoreError("canonical manifest 的 semester 与本次导入不一致")
    if manifest["scope_kind"] != scope.scope_kind or manifest["scope_id"] != scope.scope_id:
        raise CourseDataStoreError("canonical manifest 的 scope 与本次导入不一致")
    if manifest["merged_offering_count"] != offering_count:
        raise CourseDataStoreError(
            "canonical manifest 的 merged_offering_count 与快照不一致"
        )
    if manifest["merged_offering_set_sha256"] != set_digest:
        raise CourseDataStoreError(
            "canonical manifest 的 merged_offering_set_sha256 与快照内容不一致"
        )
    if manifest["baseline_before"] != manifest["baseline_after"]:
        raise CourseDataStoreError(
            "canonical manifest 的 baseline_before != baseline_after"
        )
    if manifest["baseline_before"] != reported_total:
        raise CourseDataStoreError(
            "canonical manifest 的 baseline 与快照 reported_total 不一致"
        )
    if completeness != "complete" or loaded_count != offering_count:
        # ⚠️ 由构造不可达（import 已拒绝非 complete 快照；`OfferingSnapshot` 保证
        #    complete ⇒ reported_total == loaded_count == len(offerings)）：
        #    保留为纵深防御，⛔ 不删除。
        raise CourseDataStoreError(
            "canonical manifest 只能绑定 complete 且计数自洽的快照"
        )


@dataclass(frozen=True)
class SnapshotScope:
    """一份快照的**采集 scope**（调用方**显式声明**，⛔ 绝不从 source / 文件名 / rows 推断）。

    ```text
    campus        / <openingSchoolNumber>   校区 shard
    full_semester / <semester>              全学期
    ```

    ⚠️ **语义（Data Gate 口径，⛔ 不得改动）**：

    ```text
    is_complete == complete **within the declared scope**
    ```

    ⛔ `completeness == "complete"` **不得**被解释为"全学期完整"：
    一个 `campus` 快照完整只说明**那个校区**在本次采集内取满了，
    ⛔ 不说明整个学期完整。本层只**如实记录**调用方声明的 scope，
    ⛔ 不据此生成任何 global completeness 暗示。
    """

    scope_kind: str
    scope_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope_kind, str) or self.scope_kind not in ALLOWED_SCOPE_KINDS:
            raise CourseDataStoreError(
                f"scope_kind 必须是已确认的取值之一 {list(ALLOWED_SCOPE_KINDS)}，"
                f"实际是 {self.scope_kind!r}（⛔ 不接受未确认的 scope，也不从其它字段推断）"
            )

        if not isinstance(self.scope_id, str) or not self.scope_id.strip():
            raise CourseDataStoreError(
                f"scope_id 必须是非空字符串（{self.scope_kind} 的 id 形态见 SnapshotScope 文档）"
            )

        object.__setattr__(self, "scope_id", self.scope_id.strip())


@dataclass(frozen=True)
class CourseDataImport:
    """一次导入的**结果**（⛔ 不含任何教学班取值）。

    - `inserted` / `updated` / `unchanged` 按**数据列**统计：
      `unchanged` 表示该 identity 已存在且数据完全一致
      （provenance 列仍会刷新为本次导入，见 `import_offering_snapshot()`）；
    - `already_imported` —— 同一个 `(artifact_sha256, semester, scope)` **此前已导入过**。
    """

    artifact_sha256: str
    semester: str
    scope_kind: str
    scope_id: str
    imported_at: str
    inserted: int
    updated: int
    unchanged: int
    already_imported: bool


@dataclass(frozen=True)
class CourseDataProvenance:
    """artifact 级 provenance 记录（本地库的审计信息）。

    ⚠️ `scope_kind` / `scope_id` 是**声明值**：它说明这份 artifact
    是在**哪个 scope 内**被判定 complete，⛔ 不是"全学期完整"的声明。
    """

    artifact_sha256: str
    semester: str
    scope_kind: str
    scope_id: str
    source: str | None
    imported_at: str
    completeness: str
    loaded_count: int
    reported_total: int | None
    offering_count: int


@dataclass(frozen=True)
class CourseDataAcceptance:
    """**content-bound acceptance** 元数据（⛔ 不含任何教学班取值）。

    与 `CourseDataProvenance`（声明平面 / 历史审计记录）的区别：

    ```text
    provenance  = 调用方声明"这份 artifact 是以哪个 scope 导入的"
    acceptance  = 同样声明 + **整批内容 digest**（offering_set_sha256）
                  + 逐 identity / 逐行内容指纹的 membership
    ```

    ⚠️ `offering_set_sha256` 是"**这一批规范化后的教学班内容**"的确定性指纹，
    ⛔ 不是 artifact 字节摘要（后者见 `artifact_sha256`），
    ⛔ 也不是 acquisition provenance proof。
    """

    artifact_sha256: str
    semester: str
    scope_kind: str
    scope_id: str
    source: str | None
    imported_at: str
    completeness: str
    loaded_count: int
    reported_total: int | None
    offering_count: int
    offering_set_sha256: str
    canonical_manifest_sha256: str | None = None


@dataclass(frozen=True)
class AcceptedDataset:
    """一次 **完整校验通过** 的 acceptance 读取结果（⛔ 内部对象）。

    - `acceptance` —— 元数据（含 `offering_set_sha256`）；
    - `offerings` —— **恰好**该 acceptance 接受的规范化教学班（已逐行核对内容指纹）；
    - `member_count` —— membership 表的行数（应与 `offering_count` 相等）。
    """

    acceptance: CourseDataAcceptance
    offerings: tuple[CourseOffering, ...]
    member_count: int


def compute_artifact_sha256(data: bytes) -> str:
    """对一个 artifact 的**原始字节**计算 SHA-256（十六进制小写）。

    ⚠️ 口径固定（⛔ 不得改动）：

    ```text
    SHA-256 = artifact identity / integrity
            ≠ acquisition provenance proof
    ```

    ⛔ 它**不证明**采集时间 / 采集者 / 授权状态，
    只是"这段字节没变过"的完整性标识。
    """

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise CourseDataStoreError(
            f"compute_artifact_sha256 只接受 bytes，实际是 {type(data).__name__}"
        )

    return hashlib.sha256(bytes(data)).hexdigest()


def _require_sha256(value: object) -> str:
    """校验调用方给出的 `artifact_sha256`（⛔ 不接受空 / 猜值）。"""

    if not isinstance(value, str) or not value.strip():
        raise CourseDataStoreError(
            "artifact_sha256 必须由调用方显式给出（64 位十六进制字符串）"
        )

    normalized = value.strip().lower()

    if ARTIFACT_SHA256_PATTERN.match(normalized) is None:
        raise CourseDataStoreError(
            "artifact_sha256 必须是 64 位十六进制字符串（⛔ 不接受截断 / 其它算法 / 任意字符串）"
        )

    return normalized


def _require_semester(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CourseDataStoreError("semester 必须是非空字符串（例如 '2026-1'）")

    return value.strip()


def _require_scope(scope: object, *, semester: str) -> SnapshotScope:
    """校验调用方**显式声明**的 scope（⛔ 缺失 / 非法一律拒绝，⛔ 不从其它字段推断）。

    - 必须是 `SnapshotScope`（构造时已白名单校验 kind / id）；
    - `full_semester` 的 `scope_id` 必须**等于**快照的 semester
      （否则就是一条自相矛盾的审计记录）；
    - `campus` 的 `scope_id` 是校区 `openingSchoolNumber`：
      本层⛔ **不**保存 / 不校验那张校区号表（唯一真源在采集侧），
      只要求它是非空 id。
    """

    if not isinstance(scope, SnapshotScope):
        raise CourseDataStoreError(
            "必须显式传入 SnapshotScope（scope_kind + scope_id）；"
            f"实际是 {type(scope).__name__}。"
            "⛔ 不允许从 source / 文件名 / rows 推断 scope"
        )

    if scope.scope_kind == SCOPE_KIND_FULL_SEMESTER and scope.scope_id != semester:
        raise CourseDataStoreError(
            f"full_semester 的 scope_id({scope.scope_id!r}) 必须等于快照 semester"
            f"({semester!r})；否则该审计记录自相矛盾"
        )

    return scope


def _require_store_path(path: object, *, must_exist: bool) -> Path:
    """解析并校验本地库路径（⛔ 不猜路径、⛔ 不静默建目录）。"""

    if isinstance(path, (str, Path)):
        candidate = Path(path)
    else:
        raise CourseDataStoreError(
            f"Course Data 库路径必须是 str 或 Path，实际是 {type(path).__name__}"
        )

    if candidate.exists() and candidate.is_dir():
        raise CourseDataStoreError(f"Course Data 库路径指向目录而不是文件：{candidate}")

    if must_exist:
        if not candidate.is_file():
            raise CourseDataStoreError(
                f"Course Data 库不存在：{candidate}（请先用 initialize_course_data_store 建立）"
            )
        return candidate

    parent = candidate.parent
    if not parent.exists() or not parent.is_dir():
        raise CourseDataStoreError(
            f"Course Data 库的父目录不存在：{parent}（⛔ 本层不自动创建目录）"
        )

    return candidate


def _meetings_to_json(meetings: Sequence[Meeting]) -> str:
    """把 `meetings` 序列化成**稳定** JSON（键排序 + 紧凑分隔符，可重复比对）。"""

    return json.dumps(
        [meeting.model_dump() for meeting in meetings],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _offering_payload(offering: CourseOffering) -> tuple[object, ...]:
    """一条教学班的**数据列**取值（顺序与 `_DATA_COLUMNS` 一致）。"""

    return (
        offering.course_name,
        offering.teacher,
        offering.credit,
        offering.capacity,
        offering.remaining_capacity,
        offering.source,
        offering.data_source.value,
        _meetings_to_json(offering.meetings),
    )


def _column_names(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]


def _require_current_columns(connection: sqlite3.Connection) -> None:
    """确认本地库的 schema 是**当前版本**（⛔ 不做自动迁移，⛔ 不静默降级读取）。"""

    for table, expected in _EXPECTED_COLUMNS.items():
        existing = _column_names(connection, table)
        missing = [name for name in expected if name not in existing]

        if missing:
            raise CourseDataStoreError(
                f"本地库的 {table} 表缺少列：{missing}；"
                f"该库由更早的 schema 建立（例如尚没有 scope 列）。"
                f"⛔ 本层不自动迁移，请重建本地库后重新导入"
            )


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_DDL)
    _require_current_columns(connection)


def _require_schema(connection: sqlite3.Connection) -> None:
    """读之前先确认这是本层的库（⛔ 不静默把别的 SQLite 当成 Course Data 库）。"""

    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    existing = {row["name"] for row in rows}

    missing = [name for name in _REQUIRED_TABLES if name not in existing]
    if missing:
        # ⚠️ 区分"根本不是 Course Data 库"与"是本层更早版本建立的库"：
        #    后者只有旧表 ⇒ 必须明确要求重建，⛔ 不自动迁移、⛔ 不降级读取。
        if COURSE_OFFERING_TABLE in existing:
            raise CourseDataStoreError(
                f"本地库缺少 acceptance 表：{missing}；该库由更早的版本建立"
                f"（尚没有 content-bound acceptance 平面，可能也缺少 scope 列 /"
                f" canonical manifest 列）。"
                f"⛔ 本层不自动迁移，请重建本地库后重新导入"
            )
        raise CourseDataStoreError(
            f"该 SQLite 文件不是 Course Data 本地库（缺少表：{missing}）"
        )

    _require_current_columns(connection)


@contextmanager
def _open_store(path: object, *, must_exist: bool, ensure_schema: bool) -> Iterator[sqlite3.Connection]:
    """打开本地库（短连接）：成功提交、失败回滚，并把 `sqlite3.Error` 转成清晰错误。"""

    resolved = _require_store_path(path, must_exist=must_exist)

    try:
        connection = sqlite3.connect(str(resolved))
    except sqlite3.Error as exc:
        raise CourseDataStoreError(f"无法打开 Course Data 库：{resolved}（{exc}）") from exc

    try:
        connection.row_factory = sqlite3.Row

        if ensure_schema:
            _ensure_schema(connection)
        else:
            _require_schema(connection)

        yield connection
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise CourseDataStoreError(
            f"Course Data 库操作失败：{resolved}（{exc}）"
        ) from exc
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_course_data_store(path: str | Path) -> Path:
    """建立（或复用）本地 Course Data 库，返回解析后的路径。

    - 幂等：已存在且结构正确时**不重建、不清空**；
    - ⛔ 不自动创建父目录（父目录不存在 → fail closed）；
    - ⛔ 不联网、⛔ 不导入任何数据。
    """

    with _open_store(path, must_exist=False, ensure_schema=True):
        pass

    return _require_store_path(path, must_exist=True)


def import_offering_snapshot(
    path: str | Path,
    snapshot: OfferingSnapshot,
    *,
    artifact_sha256: str,
    scope: SnapshotScope,
    canonical_manifest: Mapping[str, object] | None = None,
) -> CourseDataImport:
    """把一份**已判定 complete（在其声明 scope 内）**的 `OfferingSnapshot` upsert 进本地库。

    ⛔ 本层**不判断 completeness**，只按上游结论把关：

    ```text
    snapshot.is_complete == False → 拒绝写入 approved 路径（fail closed）
    snapshot.is_complete == True  → 逐条 upsert
    ```

    ⚠️ **scope 必须由调用方显式声明**（`scope_kind` + `scope_id`）：

    ```text
    is_complete == complete **within the declared scope**
    ```

    ⛔ `complete` **不得**被解释为"全学期完整"：
    `campus` 快照完整只说明**该校区**在本次采集内取满了。
    ⛔ 本层**不**从 `source` / 文件名 / rows 推断 scope，也⛔ 不生成任何
    global completeness 暗示；它只是**如实记录**调用方声明的那一个 scope。

    identity = `(semester, course_id, class_id)`（⛔ 与 scope 无关）：

    - 同一 `(artifact, semester, scope)` 重复导入**幂等**（第二次 `inserted=0 / updated=0`）；
    - ⛔ 不同 `class_id` 的同一门课**各自成行**，⛔ 绝不互相覆盖；
    - 已存在且数据列一致时仍然刷新 provenance（含 scope）指向**本次**导入。

    `artifact_sha256` 由调用方显式给出（可用 `compute_artifact_sha256()`
    对原始 artifact 字节计算）；⛔ 本层不去读 Capture Bundle。

    ## acceptance identity 是**不可变**的（⛔ 不存在语义 upsert）

    `canonical_manifest`（可选的内部 canonical manifest）：

    - 给出时必须满足 `SHA256(canonical_manifest_bytes(manifest)) == artifact_sha256`
      且语义字段与本次快照 / scope / 计数 / 内容 digest 完全一致；
    - 给出时会被**原样持久化**（`canonical_manifest_json`），
      使 Provider 可以在**每次读取**时重算
      `SHA256(canonical stored manifest) == acceptance_sha256`；
    - ⛔ 没有 canonical manifest 的 `full_semester` acceptance 只能作为原始导入记录存在，
      **Provider 会拒绝服务它**（无法重算 identity ⇒ 无法建立 trust chain）。

    同一个 `(artifact_sha256, semester, scope)` 再次导入时：

    ```text
    语义内容 + membership（identity + 逐行内容指纹）完全一致 → 幂等 no-op
    任一不同（manifest / counts / source / offering_set_sha256 / member 集合 / 逐行指纹）
        → ImmutableAcceptanceConflictError（immutable_acceptance_conflict，fail closed）
    ```

    ⛔ **绝不**用 `ON CONFLICT DO UPDATE` 刷新 semantic content，
    ⛔ **绝不**用"先删成员再插入"的方式改写 membership：
    那会让"同一个 acceptance SHA 指向不同 Dataset"成为可能
    （Forward Red-Team：immutable acceptance identity blocker）。

    ⚠️ 口径不变：`SHA-256 = artifact identity/integrity ≠ acquisition provenance proof`。
    """

    if not isinstance(snapshot, OfferingSnapshot):
        raise CourseDataStoreError(
            f"import_offering_snapshot 只接受 OfferingSnapshot，"
            f"实际是 {type(snapshot).__name__}"
        )

    digest = _require_sha256(artifact_sha256)
    declared_scope = _require_scope(scope, semester=snapshot.semester)

    if not snapshot.is_complete:
        raise CourseDataStoreError(
            f"拒绝导入非 complete 快照（completeness={snapshot.completeness!r}，"
            f"loaded_count={snapshot.loaded_count}，reported_total={snapshot.reported_total}）；"
            f"approved 路径只接受上游已判定 complete 的快照"
        )

    semester = _require_semester(snapshot.semester)
    imported_at = datetime.now(timezone.utc).isoformat()

    sources = {offering.source for offering in snapshot.offerings}
    record_source = sources.pop() if len(sources) == 1 else None

    # ⛔ content binding：整批内容 digest + 逐行内容指纹。
    #    它们与 rows 在**同一个事务**里写入，读回时按它们复核（见 `load_accepted_offerings`）。
    set_digest = offering_set_sha256(snapshot.offerings)
    member_digests = [
        (
            digest,
            semester,
            declared_scope.scope_kind,
            declared_scope.scope_id,
            offering.course_id,
            offering.class_id,
            offering_payload_sha256(offering),
        )
        for offering in snapshot.offerings
    ]

    manifest_json: str | None = None
    if canonical_manifest is not None:
        manifest = _require_stored_manifest_shape(canonical_manifest)
        _require_manifest_matches_metadata(
            manifest,
            digest=digest,
            semester=semester,
            scope=declared_scope,
            completeness=snapshot.completeness,
            loaded_count=snapshot.loaded_count,
            reported_total=snapshot.reported_total,
            offering_count=len(snapshot.offerings),
            set_digest=set_digest,
        )
        manifest_json = canonical_manifest_bytes(manifest).decode("utf-8")

    inserted = 0
    updated = 0
    unchanged = 0

    with _open_store(path, must_exist=False, ensure_schema=True) as connection:
        already_imported = (
            connection.execute(
                f"SELECT 1 FROM {IMPORT_RECORD_TABLE} "
                "WHERE artifact_sha256 = ? AND semester = ? "
                "AND scope_kind = ? AND scope_id = ?",
                (digest, semester, declared_scope.scope_kind, declared_scope.scope_id),
            ).fetchone()
            is not None
        )

        placeholders = ", ".join("?" for _ in _DATA_COLUMNS)

        for offering in snapshot.offerings:
            payload = _offering_payload(offering)

            existing = connection.execute(
                f"SELECT {', '.join(_DATA_COLUMNS)} FROM {COURSE_OFFERING_TABLE} "
                "WHERE semester = ? AND course_id = ? AND class_id = ?",
                (semester, offering.course_id, offering.class_id),
            ).fetchone()

            if existing is None:
                inserted += 1
            elif tuple(existing) == payload:
                unchanged += 1
            else:
                updated += 1

            connection.execute(
                f"""
                INSERT INTO {COURSE_OFFERING_TABLE} (
                    semester, course_id, class_id, {', '.join(_DATA_COLUMNS)},
                    artifact_sha256, imported_at, scope_kind, scope_id
                ) VALUES (?, ?, ?, {placeholders}, ?, ?, ?, ?)
                ON CONFLICT (semester, course_id, class_id) DO UPDATE SET
                    {', '.join(f'{column} = excluded.{column}' for column in _DATA_COLUMNS)},
                    artifact_sha256 = excluded.artifact_sha256,
                    imported_at = excluded.imported_at,
                    scope_kind = excluded.scope_kind,
                    scope_id = excluded.scope_id
                """,
                (
                    semester,
                    offering.course_id,
                    offering.class_id,
                    *payload,
                    digest,
                    imported_at,
                    declared_scope.scope_kind,
                    declared_scope.scope_id,
                ),
            )

        # 同一 (artifact, semester, scope) 只保留**首次**导入记录（幂等，不覆盖原始时间）。
        # ⚠️ scope 参与主键：同一份 artifact 若以**不同 scope** 声明，会各自留一条审计记录，
        #    ⛔ 而不是被静默合并成一条含义不明的记录。
        connection.execute(
            f"""
            INSERT OR IGNORE INTO {IMPORT_RECORD_TABLE} (
                artifact_sha256, semester, scope_kind, scope_id, source, imported_at,
                completeness, loaded_count, reported_total, offering_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest,
                semester,
                declared_scope.scope_kind,
                declared_scope.scope_id,
                record_source,
                imported_at,
                snapshot.completeness,
                snapshot.loaded_count,
                snapshot.reported_total,
                len(snapshot.offerings),
            ),
        )

        # ---- content-bound acceptance 平面（与 rows 同一事务） -----------------
        # ⛔ **不可变**：同一个 acceptance identity 只允许"完全相同"的重复提交。
        #    语义内容或 membership 任一不同 ⇒ ImmutableAcceptanceConflictError。
        existing_acceptance = connection.execute(
            f"SELECT scope_kind, scope_id, source, completeness, loaded_count, "
            f"reported_total, offering_count, offering_set_sha256, canonical_manifest_json "
            f"FROM {ACCEPTANCE_TABLE} WHERE artifact_sha256 = ? AND semester = ? "
            "AND scope_kind = ? AND scope_id = ?",
            (digest, semester, declared_scope.scope_kind, declared_scope.scope_id),
        ).fetchone()

        if existing_acceptance is None:
            connection.execute(
                f"""
                INSERT INTO {ACCEPTANCE_TABLE} (
                    artifact_sha256, semester, scope_kind, scope_id, source, imported_at,
                    completeness, loaded_count, reported_total, offering_count,
                    offering_set_sha256, canonical_manifest_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    digest,
                    semester,
                    declared_scope.scope_kind,
                    declared_scope.scope_id,
                    record_source,
                    imported_at,
                    snapshot.completeness,
                    snapshot.loaded_count,
                    snapshot.reported_total,
                    len(snapshot.offerings),
                    set_digest,
                    manifest_json,
                ),
            )

            connection.executemany(
                f"""
                INSERT INTO {ACCEPTANCE_MEMBER_TABLE} (
                    artifact_sha256, semester, scope_kind, scope_id,
                    course_id, class_id, offering_payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                member_digests,
            )
        else:
            _require_identical_acceptance(
                connection,
                existing=existing_acceptance,
                digest=digest,
                semester=semester,
                scope=declared_scope,
                source=record_source,
                completeness=snapshot.completeness,
                loaded_count=snapshot.loaded_count,
                reported_total=snapshot.reported_total,
                offering_count=len(snapshot.offerings),
                set_digest=set_digest,
                manifest_json=manifest_json,
                member_digests=member_digests,
            )

    return CourseDataImport(
        artifact_sha256=digest,
        semester=semester,
        scope_kind=declared_scope.scope_kind,
        scope_id=declared_scope.scope_id,
        imported_at=imported_at,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        already_imported=already_imported,
    )


def _require_identical_acceptance(
    connection: sqlite3.Connection,
    *,
    existing: sqlite3.Row,
    digest: str,
    semester: str,
    scope: SnapshotScope,
    source: str | None,
    completeness: str,
    loaded_count: int,
    reported_total: int | None,
    offering_count: int,
    set_digest: str,
    manifest_json: str | None,
    member_digests: list[tuple[str, str, str, str, str, str, str]],
) -> None:
    """同一 acceptance identity 的重复提交**必须完全相同**（否则 fail closed）。

    比较项（⛔ 任一不同即 `ImmutableAcceptanceConflictError`）：

    ```text
    列式 metadata：scope（已由查询条件固定）/ source / completeness /
                   loaded_count / reported_total / offering_count / offering_set_sha256
    canonical manifest：已持久化的 canonical_manifest_json 必须与本次**字节相同**
                        （⛔ 不允许"同一个 SHA 换一份 manifest"）
    membership：identity 集合 + 逐行 offering_payload_sha256（+1 / -1 / 替换 / 内容变化全拒绝）
    ```

    ⛔ 本函数**只读**：不写库、不清空、不刷新任何 digest。
    """

    conflicts: list[str] = []

    if existing["source"] != source:
        conflicts.append("source")
    if existing["completeness"] != completeness:
        conflicts.append("completeness")
    if existing["loaded_count"] != loaded_count:
        conflicts.append("loaded_count")
    if existing["reported_total"] != reported_total:
        conflicts.append("reported_total")
    if existing["offering_count"] != offering_count:
        conflicts.append("offering_count")
    if existing["offering_set_sha256"] != set_digest:
        conflicts.append("offering_set_sha256")
    if existing["canonical_manifest_json"] != manifest_json:
        conflicts.append("canonical_manifest_json")

    stored_members = connection.execute(
        "SELECT course_id, class_id, offering_payload_sha256 "
        f"FROM {ACCEPTANCE_MEMBER_TABLE} WHERE artifact_sha256 = ? AND semester = ? "
        "AND scope_kind = ? AND scope_id = ? ORDER BY course_id, class_id",
        (digest, semester, scope.scope_kind, scope.scope_id),
    ).fetchall()

    stored_pairs = [
        (row["course_id"], row["class_id"], row["offering_payload_sha256"])
        for row in stored_members
    ]
    incoming_pairs = sorted(
        (course_id, class_id, payload_sha256)
        for _digest, _semester, _kind, _scope_id, course_id, class_id, payload_sha256
        in member_digests
    )

    if stored_pairs != incoming_pairs:
        conflicts.append("membership")

    if conflicts:
        raise ImmutableAcceptanceConflictError(
            f"acceptance identity {digest[:12]}… 已存在且**不可变**，"
            f"但本次提交的 {sorted(set(conflicts))} 与之不同；"
            f"⛔ 拒绝用同一个 acceptance SHA 改写语义内容 / membership"
            f"（immutable_acceptance_conflict）"
        )


def _require_manifest_trust_chain(
    raw_manifest: object,
    *,
    digest: str,
    semester: str,
    scope: SnapshotScope,
    completeness: str,
    loaded_count: int,
    reported_total: int | None,
    offering_count: int,
    set_digest: str,
) -> str:
    """重算并核对**已持久化**的 canonical manifest（⛔ 不信任 DB 自报的 digest）。

    返回重算出的 `SHA256(canonical stored manifest)`。

    ```text
    stored bytes → strict parse（未知字段 / 缺字段 / 类型错误一律拒绝）
                 → SHA256(canonical bytes) 必须 == configured acceptance SHA
                 → 语义字段必须 == 列式 metadata
    ```

    ⚠️ 攻击场景：DB 里的 acceptance 记录与 digest 被**一起** rewrite 时，
    列式 metadata 自洽但 `SHA256(canonical stored manifest)` 不再等于
    configured SHA ⇒ 这里 fail closed。
    """

    if not isinstance(raw_manifest, str):
        raise CourseDataStoreError("stored canonical manifest 必须是 JSON 文本")

    try:
        manifest = json.loads(raw_manifest)
    except json.JSONDecodeError as exc:
        raise CourseDataStoreError(
            f"stored canonical manifest 不是合法 JSON（第 {exc.lineno} 行）"
        ) from exc

    validated = _require_stored_manifest_shape(manifest)

    # canonical 形式必须稳定：字节 → 对象 → 字节 必须完全相同。
    if canonical_manifest_bytes(validated).decode("utf-8") != raw_manifest:
        raise CourseDataStoreError(
            "stored canonical manifest 不是 canonical 形式（键顺序 / 空白不同）"
        )

    recomputed = compute_manifest_sha256(validated)
    if recomputed != digest:
        raise CourseDataStoreError(
            "重算的 SHA256(canonical stored manifest) 与 configured acceptance identity 不一致；"
            "⛔ 该 acceptance 记录（含 digest）可能被整体 rewrite 过"
        )

    _require_manifest_matches_metadata(
        validated,
        digest=digest,
        semester=semester,
        scope=scope,
        completeness=completeness,
        loaded_count=loaded_count,
        reported_total=reported_total,
        offering_count=offering_count,
        set_digest=set_digest,
    )

    return recomputed


def _row_to_offering(row: sqlite3.Row) -> CourseOffering:
    """把一行还原成公共 `CourseOffering`（⛔ 不猜、⛔ 不补默认值）。"""

    raw_data_source = row["data_source"]

    if raw_data_source != DataSource.REAL.value:
        raise CourseDataStoreError(
            f"本地库里 {row['semester']} / {row['course_id']} / {row['class_id']} 的 "
            f"data_source={raw_data_source!r} 不是 'real'；"
            f"真实链路只应出现 real，拒绝把它当作真实教学班加载"
        )

    try:
        raw_meetings = json.loads(row["meetings_json"])
    except json.JSONDecodeError as exc:
        raise CourseDataStoreError(
            f"本地库里 {row['semester']} / {row['course_id']} / {row['class_id']} 的 "
            f"meetings 不是合法 JSON（本地库可能被外部修改）"
        ) from exc

    if not isinstance(raw_meetings, list):
        raise CourseDataStoreError(
            f"本地库里 {row['semester']} / {row['course_id']} / {row['class_id']} 的 "
            f"meetings 不是数组（本地库可能被外部修改）"
        )

    try:
        meetings = [Meeting.model_validate(item) for item in raw_meetings]
    except ValidationError as exc:
        raise CourseDataStoreError(
            f"本地库里 {row['semester']} / {row['course_id']} / {row['class_id']} 的 "
            f"meetings 不符合公共契约（本地库可能被外部修改）"
        ) from exc

    return CourseOffering(
        course_id=row["course_id"],
        course_name=row["course_name"],
        class_id=row["class_id"],
        semester=row["semester"],
        teacher=row["teacher"],
        credit=row["credit"],
        meetings=meetings,
        capacity=row["capacity"],
        remaining_capacity=row["remaining_capacity"],
        source=row["source"],
        data_source=DataSource.REAL,
    )


def load_course_offerings(
    path: str | Path,
    semester: str,
    *,
    course_ids: Sequence[str] | None = None,
) -> list[CourseOffering]:
    """按学期读回教学班；可选按 `course_id` 集合筛选候选教学班。

    - `course_ids=None` → 该学期**全部**；
    - `course_ids=[]` → **空集合** ⇒ 返回空列表（⛔ 不是"不筛"）；
    - 返回顺序确定：`ORDER BY course_id, class_id`；
    - ⛔ 只读，⛔ 不写库、⛔ 不判断完整性。
    """

    target_semester = _require_semester(semester)

    parameters: list[object] = [target_semester]
    where = "semester = ?"
    wanted: list[str] = []

    if course_ids is not None:
        if isinstance(course_ids, (str, bytes)) or not isinstance(course_ids, Sequence):
            raise CourseDataStoreError(
                f"course_ids 必须是字符串序列或 None，实际是 {type(course_ids).__name__}"
            )

        for value in course_ids:
            if not isinstance(value, str) or not value.strip():
                raise CourseDataStoreError("course_ids 的元素必须是非空字符串")
            wanted.append(value.strip())

        if wanted:
            where += f" AND course_id IN ({', '.join('?' for _ in wanted)})"
            parameters.extend(wanted)

    with _open_store(path, must_exist=True, ensure_schema=False) as connection:
        # ⛔ 空集合也要先确认库本身合法（坏路径不能被"空筛选"掩盖）。
        if course_ids is not None and not wanted:
            return []

        rows = connection.execute(
            f"SELECT {', '.join(_LOAD_COLUMNS)} FROM {COURSE_OFFERING_TABLE} "
            f"WHERE {where} ORDER BY course_id, class_id",
            parameters,
        ).fetchall()

    return [_row_to_offering(row) for row in rows]


def load_course_data_acceptances(
    path: str | Path,
    *,
    semester: str | None = None,
) -> list[CourseDataAcceptance]:
    """读回 **content-bound acceptance** 元数据（⛔ 不含任何教学班取值）。

    - `semester=None` → 全部学期的 acceptance；
    - 顺序：`ORDER BY imported_at, artifact_sha256, scope_kind, scope_id`（确定、可复现）；
    - ⚠️ 这是**元数据**，不足以证明"当前 rows 仍等于被接受的内容"；
      要证明这一点必须用 `load_accepted_offerings()`（它在一次读事务里同时核对
      membership 与逐行内容指纹）。
    """

    parameters: list[object] = []
    where = ""

    if semester is not None:
        where = "WHERE semester = ?"
        parameters.append(_require_semester(semester))

    with _open_store(path, must_exist=True, ensure_schema=False) as connection:
        rows = connection.execute(
            "SELECT artifact_sha256, semester, scope_kind, scope_id, source, imported_at, "
            "completeness, loaded_count, reported_total, offering_count, offering_set_sha256, "
            f"canonical_manifest_json FROM {ACCEPTANCE_TABLE} {where} "
            "ORDER BY imported_at, artifact_sha256, scope_kind, scope_id",
            parameters,
        ).fetchall()

    return [
        CourseDataAcceptance(
            artifact_sha256=row["artifact_sha256"],
            semester=row["semester"],
            scope_kind=row["scope_kind"],
            scope_id=row["scope_id"],
            source=row["source"],
            imported_at=row["imported_at"],
            completeness=row["completeness"],
            loaded_count=row["loaded_count"],
            reported_total=row["reported_total"],
            offering_count=row["offering_count"],
            offering_set_sha256=row["offering_set_sha256"],
            canonical_manifest_sha256=(
                hashlib.sha256(
                    str(row["canonical_manifest_json"]).encode("utf-8")
                ).hexdigest()
                if row["canonical_manifest_json"] is not None
                else None
            ),
        )
        for row in rows
    ]


def load_accepted_offerings(
    path: str | Path,
    *,
    semester: str,
    acceptance_sha256: str,
    scope: SnapshotScope | None = None,
) -> AcceptedDataset:
    """在一次**一致读事务**里完整校验并物化一个 acceptance 接受的教学班。

    `scope=None` ⇒ 默认 `full_semester / <semester>`（production Provider 语义）；
    campus acceptance 的调用方（campus CLI 回读）显式传入 `campus / <number>`。

    校验（任一不满足 ⇒ `CourseDataStoreError`，fail closed）：

    ```text
     0. **immutable acceptance identity trust chain**（本轮 BLOCK 的修复点）：
        configured SHA
          → 已持久化的 canonical_manifest_json
          → SHA256(canonical bytes) == configured SHA      （可重算，⛔ 不靠 DB 自报）
          → manifest 语义字段 == 列式 metadata（semester / scope / counts /
            offering_set_sha256 / baseline）
        ⇒ full_semester acceptance 没有 canonical manifest 时**拒绝服务**
          （没有它就无法重算 identity）；campus acceptance 不要求 manifest。
     1. acceptance 元数据行存在，且 (semester, scope_kind, scope_id, artifact_sha256)
        精确匹配
     2. 与历史审计记录（course_data_import）**同时存在且计数一致**
        （⛔ 两个平面任何一边被删除 / 改写都视为不可信）
     3. completeness == complete；loaded_count == reported_total == offering_count > 0
     4. membership 行数 == offering_count
     5. membership 的 identity 集合 == 实际读到的 rows 的 identity 集合
        （⛔ 既不缺行，也不多行 ⇒ 陈旧 campus 行无法混入）
     6. 每一行的 `offering_payload_sha256` == membership 记录的内容指纹
     7. 重算整批 `offering_set_sha256` == 元数据里的 `offering_set_sha256`
     8. 每行的行级 provenance 仍指向**本次 acceptance**
        （declaration 平面与内容平面必须一致）
    ```

    ⚠️ 第 5/6/7 条是 BLOCK B3 的修复点：**同数量 / 同身份的"内容替换"无法逃过**；
    第 1/2 条是 BLOCK B4 的修复点：acceptance 被删除 / 改写后**每一次读取都会重新失败**；
    第 0 条是 **immutable acceptance identity** 的修复点：即使记录与 digest 一起被
    rewrite，重算 `SHA256(canonical stored manifest)` 也**对不上** configured SHA。

    - 只读、一次性事务；⛔ 不写库、⛔ 不建表、⛔ 不联网；
    - 返回顺序确定：`ORDER BY course_id, class_id`。
    """

    target_semester = _require_semester(semester)
    digest = _require_sha256(acceptance_sha256)

    if scope is None:
        wanted_scope = SnapshotScope(
            scope_kind=SCOPE_KIND_FULL_SEMESTER, scope_id=target_semester
        )
    else:
        if not isinstance(scope, SnapshotScope):
            raise CourseDataStoreError(
                f"scope 必须是 SnapshotScope 或 None，实际是 {type(scope).__name__}"
            )
        wanted_scope = _require_scope(scope, semester=target_semester)

    with _open_store(path, must_exist=True, ensure_schema=False) as connection:
        acceptance_row = connection.execute(
            "SELECT artifact_sha256, semester, scope_kind, scope_id, source, imported_at, "
            "completeness, loaded_count, reported_total, offering_count, offering_set_sha256, "
            f"canonical_manifest_json FROM {ACCEPTANCE_TABLE} "
            "WHERE artifact_sha256 = ? AND semester = ? "
            "AND scope_kind = ? AND scope_id = ?",
            (digest, target_semester, wanted_scope.scope_kind, wanted_scope.scope_id),
        ).fetchone()

        if acceptance_row is None:
            raise CourseDataStoreError(
                "本地库中没有与该 acceptance identity 对应的 content-bound 记录；"
                "⛔ 拒绝退化为『该学期任意行』"
            )

        # ---- 0. immutable acceptance identity trust chain -------------------
        manifest_sha256: str | None = None
        raw_manifest = acceptance_row["canonical_manifest_json"]
        if raw_manifest is not None:
            manifest_sha256 = _require_manifest_trust_chain(
                raw_manifest,
                digest=digest,
                semester=target_semester,
                scope=wanted_scope,
                completeness=acceptance_row["completeness"],
                loaded_count=acceptance_row["loaded_count"],
                reported_total=acceptance_row["reported_total"],
                offering_count=acceptance_row["offering_count"],
                set_digest=acceptance_row["offering_set_sha256"],
            )
        elif wanted_scope.scope_kind == SCOPE_KIND_FULL_SEMESTER:
            raise CourseDataStoreError(
                "该 full_semester acceptance 没有持久化的 canonical manifest；"
                "⛔ 无法重算 acceptance identity ⇒ 拒绝服务（campus acceptance 不受此限）"
            )

        provenance_row = connection.execute(
            "SELECT offering_count, completeness, loaded_count, reported_total "
            f"FROM {IMPORT_RECORD_TABLE} WHERE artifact_sha256 = ? AND semester = ? "
            "AND scope_kind = ? AND scope_id = ?",
            (digest, target_semester, wanted_scope.scope_kind, wanted_scope.scope_id),
        ).fetchone()

        if provenance_row is None:
            raise CourseDataStoreError(
                "该 acceptance 缺少历史导入记录（两个平面不一致）；拒绝继续"
            )

        acceptance = CourseDataAcceptance(
            artifact_sha256=acceptance_row["artifact_sha256"],
            semester=acceptance_row["semester"],
            scope_kind=acceptance_row["scope_kind"],
            scope_id=acceptance_row["scope_id"],
            source=acceptance_row["source"],
            imported_at=acceptance_row["imported_at"],
            completeness=acceptance_row["completeness"],
            loaded_count=acceptance_row["loaded_count"],
            reported_total=acceptance_row["reported_total"],
            offering_count=acceptance_row["offering_count"],
            offering_set_sha256=acceptance_row["offering_set_sha256"],
            canonical_manifest_sha256=manifest_sha256,
        )

        if (
            provenance_row["offering_count"] != acceptance.offering_count
            or provenance_row["completeness"] != acceptance.completeness
            or provenance_row["loaded_count"] != acceptance.loaded_count
            or provenance_row["reported_total"] != acceptance.reported_total
        ):
            raise CourseDataStoreError(
                "该 acceptance 的两个平面（导入记录 / content-bound 记录）计数不一致；"
                "本地库可能被外部修改，拒绝继续"
            )

        if acceptance.completeness != "complete":
            raise CourseDataStoreError(
                f"该 acceptance 不是 complete（completeness={acceptance.completeness!r}）；"
                f"⛔ partial 数据不得进入 production 链路"
            )

        if (
            acceptance.reported_total is None
            or acceptance.loaded_count != acceptance.reported_total
            or acceptance.loaded_count != acceptance.offering_count
        ):
            raise CourseDataStoreError(
                f"该 acceptance 计数不自洽（loaded_count={acceptance.loaded_count}，"
                f"reported_total={acceptance.reported_total}，"
                f"offering_count={acceptance.offering_count}）；拒绝继续"
            )

        if acceptance.offering_count <= 0:
            raise CourseDataStoreError(
                f"该 acceptance 的 offering_count({acceptance.offering_count}) 必须 > 0；"
                f"⛔ 空 acceptance 不得装配 production Provider"
            )

        members = connection.execute(
            "SELECT course_id, class_id, offering_payload_sha256 "
            f"FROM {ACCEPTANCE_MEMBER_TABLE} WHERE artifact_sha256 = ? AND semester = ? "
            "AND scope_kind = ? AND scope_id = ? ORDER BY course_id, class_id",
            (
                digest,
                target_semester,
                wanted_scope.scope_kind,
                wanted_scope.scope_id,
            ),
        ).fetchall()

        if len(members) != acceptance.offering_count:
            raise CourseDataStoreError(
                f"acceptance membership 行数({len(members)}) != "
                f"offering_count({acceptance.offering_count})；拒绝继续"
            )

        rows = connection.execute(
            f"SELECT {', '.join(_LOAD_COLUMNS)} FROM {COURSE_OFFERING_TABLE} "
            "WHERE semester = ? AND artifact_sha256 = ? AND scope_kind = ? AND scope_id = ? "
            "ORDER BY course_id, class_id",
            (target_semester, digest, wanted_scope.scope_kind, wanted_scope.scope_id),
        ).fetchall()

        if len(rows) != len(members):
            raise CourseDataStoreError(
                f"属于该 acceptance 的行数({len(rows)}) != membership 行数"
                f"({len(members)})；⛔ 不接受部分行，也⛔ 不接受多余行"
            )

        offerings: list[CourseOffering] = []
        for row, member in zip(rows, members, strict=True):
            offering = _row_to_offering(row)
            identity = offering_identity(offering)
            if (identity[1], identity[2]) != (member["course_id"], member["class_id"]):
                raise CourseDataStoreError(
                    "acceptance membership 与实际行不一致（identity 不匹配）；拒绝继续"
                )
            computed = offering_payload_sha256(offering)
            # ⚠️ 与下面的整批 digest 复核互为冗余：任一句都能发现内容替换，
            #    这里保留是为了给出**逐行**定位。
            if computed != member["offering_payload_sha256"]:
                raise CourseDataStoreError(
                    f"教学班 {offering.course_id}/{offering.class_id} 的**内容**与"
                    f"acceptance membership 记录不一致（同 identity 内容被替换）；拒绝继续"
                )
            offerings.append(offering)

        recomputed_set = offering_set_sha256(offerings)
        # ⚠️ 与上面的逐行指纹复核互为冗余（纵深防御，⛔ 不删除）。
        if recomputed_set != acceptance.offering_set_sha256:
            raise CourseDataStoreError(
                "重算的整批内容 digest 与 acceptance 记录不一致；拒绝继续"
            )

    return AcceptedDataset(
        acceptance=acceptance,
        offerings=tuple(offerings),
        member_count=len(members),
    )


def load_course_offerings_for_acceptance(
    path: str | Path,
    *,
    semester: str,
    acceptance_sha256: str,
) -> list[CourseOffering]:
    """按**行级 provenance（声明平面）**筛选属于某次 full_semester 导入的行。

    ⚠️ **这不是权威读取路径**（Forward Red-Team BLOCK B3）：
    它只按 `(semester, scope_kind=full_semester, scope_id=semester, artifact_sha256)`
    过滤行级 provenance，**不核对内容**，因此无法发现"同数量 / 同身份的替换"。
    权威读取是 `load_accepted_offerings()`（content-bound 平面 + membership +
    逐行内容指纹 + 整批 digest）；本函数仅保留给诊断 / 兼容用途。

    - 返回顺序确定：`ORDER BY course_id, class_id`；
    - ⛔ 只读；⛔ 不写库、⛔ 不判断完整性、⛔ 不 fallback 到整学期查询。
    """

    target_semester = _require_semester(semester)
    digest = _require_sha256(acceptance_sha256)

    with _open_store(path, must_exist=True, ensure_schema=False) as connection:
        rows = connection.execute(
            f"SELECT {', '.join(_LOAD_COLUMNS)} FROM {COURSE_OFFERING_TABLE} "
            "WHERE semester = ? AND scope_kind = ? AND scope_id = ? "
            "AND artifact_sha256 = ? ORDER BY course_id, class_id",
            (target_semester, SCOPE_KIND_FULL_SEMESTER, target_semester, digest),
        ).fetchall()

    return [_row_to_offering(row) for row in rows]


def load_course_data_provenance(
    path: str | Path,
    *,
    semester: str | None = None,
) -> list[CourseDataProvenance]:
    """读回 artifact 级 provenance 记录（审计用；⛔ 不含任何教学班取值）。

    - `semester=None` → 全部学期的导入记录；
    - 顺序：`ORDER BY imported_at, artifact_sha256, scope_kind, scope_id`（确定、可复现）；
    - ⚠️ 每条记录都带**声明 scope**：`completeness == "complete"` 只在
      该 scope 内成立，⛔ 不是"全学期完整"的声明。
    """

    parameters: list[object] = []
    where = ""

    if semester is not None:
        where = "WHERE semester = ?"
        parameters.append(_require_semester(semester))

    with _open_store(path, must_exist=True, ensure_schema=False) as connection:
        rows = connection.execute(
            "SELECT artifact_sha256, semester, scope_kind, scope_id, source, imported_at, "
            "completeness, loaded_count, reported_total, offering_count "
            f"FROM {IMPORT_RECORD_TABLE} {where} "
            "ORDER BY imported_at, artifact_sha256, scope_kind, scope_id",
            parameters,
        ).fetchall()

    return [
        CourseDataProvenance(
            artifact_sha256=row["artifact_sha256"],
            semester=row["semester"],
            scope_kind=row["scope_kind"],
            scope_id=row["scope_id"],
            source=row["source"],
            imported_at=row["imported_at"],
            completeness=row["completeness"],
            loaded_count=row["loaded_count"],
            reported_total=row["reported_total"],
            offering_count=row["offering_count"],
        )
        for row in rows
    ]
