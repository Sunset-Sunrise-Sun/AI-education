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

- ⛔ **不判断 completeness**：只接受上游已经判定为 `complete` 的 `OfferingSnapshot`
  （`is_complete == false` → 拒绝写入 approved 路径），
  也⛔ **不**在库里写任何"这份数据完整"的自我声明；
- ⛔ 不接触 Capture Bundle / `captured_pages.py` / `sharded_capture.py` /
  collector / `planning_runtime.py` / PR #39 / `schemas/**` / Planner / Curriculum / frontend；
- ⛔ 不联网、不读取 / 不保存任何认证材料；
- ⛔ **不新增公共 Schema**：只持久化公共 `CourseOffering` **已有**的字段。

## `artifact_sha256` 的口径（⛔ 不得改动）

```text
SHA-256 = artifact identity / integrity
        ≠ acquisition provenance proof
```

它只说明"这份 artifact 的字节没变"，
⛔ **不证明**它是什么时候、由谁、在什么授权状态下采集的，
也⛔ 不得被当作采集来源的合规证明。本模块只是**如实记录**调用方给出的这个值。

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
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.course_data.errors import CourseDataNormalizationError
from app.course_data.snapshot import OfferingSnapshot
from app.models.contracts import CourseOffering, DataSource, Meeting

__all__ = [
    "ARTIFACT_SHA256_PATTERN",
    "COURSE_OFFERING_TABLE",
    "IMPORT_RECORD_TABLE",
    "CourseDataImport",
    "CourseDataProvenance",
    "CourseDataStoreError",
    "compute_artifact_sha256",
    "import_offering_snapshot",
    "initialize_course_data_store",
    "load_course_data_provenance",
    "load_course_offerings",
]

#: 教学班表（identity 是主键：⛔ 不允许按 `course_id` 覆盖不同教学班）。
COURSE_OFFERING_TABLE = "course_offering"

#: 导入记录表（artifact 级 provenance；同一 artifact 只记首次导入）。
IMPORT_RECORD_TABLE = "course_data_import"

#: `artifact_sha256` 的形状：64 位十六进制（大小写都接受，落库统一小写）。
ARTIFACT_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

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
    PRIMARY KEY (semester, course_id, class_id)
);

CREATE TABLE IF NOT EXISTS {IMPORT_RECORD_TABLE} (
    artifact_sha256     TEXT    NOT NULL,
    semester            TEXT    NOT NULL,
    source              TEXT,
    imported_at         TEXT    NOT NULL,
    completeness        TEXT    NOT NULL,
    loaded_count        INTEGER NOT NULL,
    reported_total      INTEGER,
    offering_count      INTEGER NOT NULL,
    PRIMARY KEY (artifact_sha256, semester)
);
"""

_REQUIRED_TABLES = (COURSE_OFFERING_TABLE, IMPORT_RECORD_TABLE)


class CourseDataStoreError(CourseDataNormalizationError):
    """本地 Course Data 库读写失败（继承统一错误类型，便于调用方一处捕获）。"""


@dataclass(frozen=True)
class CourseDataImport:
    """一次导入的**结果**（⛔ 不含任何教学班取值）。

    - `inserted` / `updated` / `unchanged` 按**数据列**统计：
      `unchanged` 表示该 identity 已存在且数据完全一致
      （provenance 列仍会刷新为本次导入，见 `import_offering_snapshot()`）；
    - `already_imported` —— 同一个 `(artifact_sha256, semester)` **此前已导入过**。
    """

    artifact_sha256: str
    semester: str
    imported_at: str
    inserted: int
    updated: int
    unchanged: int
    already_imported: bool


@dataclass(frozen=True)
class CourseDataProvenance:
    """artifact 级 provenance 记录（本地库的审计信息）。"""

    artifact_sha256: str
    semester: str
    source: str | None
    imported_at: str
    completeness: str
    loaded_count: int
    reported_total: int | None
    offering_count: int


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


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_DDL)


def _require_schema(connection: sqlite3.Connection) -> None:
    """读之前先确认这是本层的库（⛔ 不静默把别的 SQLite 当成 Course Data 库）。"""

    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    existing = {row["name"] for row in rows}

    missing = [name for name in _REQUIRED_TABLES if name not in existing]
    if missing:
        raise CourseDataStoreError(
            f"该 SQLite 文件不是 Course Data 本地库（缺少表：{missing}）"
        )


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
) -> CourseDataImport:
    """把一份**已判定 complete** 的 `OfferingSnapshot` upsert 进本地库。

    ⛔ 本层**不判断 completeness**，只按上游结论把关：

    ```text
    snapshot.is_complete == False → 拒绝写入 approved 路径（fail closed）
    snapshot.is_complete == True  → 逐条 upsert
    ```

    identity = `(semester, course_id, class_id)`：

    - 同一 artifact 重复导入**幂等**（第二次 `inserted=0 / updated=0`）；
    - ⛔ 不同 `class_id` 的同一门课**各自成行**，⛔ 绝不互相覆盖；
    - 已存在且数据列一致时仍然刷新 provenance
      （`artifact_sha256` / `imported_at` 指向**本次**导入）。

    `artifact_sha256` 由调用方显式给出（可用 `compute_artifact_sha256()`
    对原始 artifact 字节计算）；⛔ 本层不去读 Capture Bundle。

    ⚠️ 口径不变：`SHA-256 = artifact identity/integrity ≠ acquisition provenance proof`。
    """

    if not isinstance(snapshot, OfferingSnapshot):
        raise CourseDataStoreError(
            f"import_offering_snapshot 只接受 OfferingSnapshot，"
            f"实际是 {type(snapshot).__name__}"
        )

    digest = _require_sha256(artifact_sha256)

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

    inserted = 0
    updated = 0
    unchanged = 0

    with _open_store(path, must_exist=False, ensure_schema=True) as connection:
        already_imported = (
            connection.execute(
                f"SELECT 1 FROM {IMPORT_RECORD_TABLE} "
                "WHERE artifact_sha256 = ? AND semester = ?",
                (digest, semester),
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
                    artifact_sha256, imported_at
                ) VALUES (?, ?, ?, {placeholders}, ?, ?)
                ON CONFLICT (semester, course_id, class_id) DO UPDATE SET
                    {', '.join(f'{column} = excluded.{column}' for column in _DATA_COLUMNS)},
                    artifact_sha256 = excluded.artifact_sha256,
                    imported_at = excluded.imported_at
                """,
                (
                    semester,
                    offering.course_id,
                    offering.class_id,
                    *payload,
                    digest,
                    imported_at,
                ),
            )

        # 同一 artifact 只保留**首次**导入记录（幂等，且不覆盖原始时间）。
        connection.execute(
            f"""
            INSERT OR IGNORE INTO {IMPORT_RECORD_TABLE} (
                artifact_sha256, semester, source, imported_at, completeness,
                loaded_count, reported_total, offering_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest,
                semester,
                record_source,
                imported_at,
                snapshot.completeness,
                snapshot.loaded_count,
                snapshot.reported_total,
                len(snapshot.offerings),
            ),
        )

    return CourseDataImport(
        artifact_sha256=digest,
        semester=semester,
        imported_at=imported_at,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        already_imported=already_imported,
    )


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


def load_course_data_provenance(
    path: str | Path,
    *,
    semester: str | None = None,
) -> list[CourseDataProvenance]:
    """读回 artifact 级 provenance 记录（审计用；⛔ 不含任何教学班取值）。

    - `semester=None` → 全部学期的导入记录；
    - 顺序：`ORDER BY imported_at, artifact_sha256`（确定、可复现）。
    """

    parameters: list[object] = []
    where = ""

    if semester is not None:
        where = "WHERE semester = ?"
        parameters.append(_require_semester(semester))

    with _open_store(path, must_exist=True, ensure_schema=False) as connection:
        rows = connection.execute(
            "SELECT artifact_sha256, semester, source, imported_at, completeness, "
            "loaded_count, reported_total, offering_count "
            f"FROM {IMPORT_RECORD_TABLE} {where} ORDER BY imported_at, artifact_sha256",
            parameters,
        ).fetchall()

    return [
        CourseDataProvenance(
            artifact_sha256=row["artifact_sha256"],
            semester=row["semester"],
            source=row["source"],
            imported_at=row["imported_at"],
            completeness=row["completeness"],
            loaded_count=row["loaded_count"],
            reported_total=row["reported_total"],
            offering_count=row["offering_count"],
        )
        for row in rows
    ]
