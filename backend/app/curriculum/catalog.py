"""受核验培养方案版本目录（read-only，fail closed）。

```text
本地已核验 artifact 目录（由调用方**显式**给出）
        ↓  load_curriculum_catalog(directory)
只暴露 supported=True 且元信息完备的版本；其余一律 rejected（带原因码）
        ↓  resolve_curriculum_version(catalog, version_id)
CurriculumVersion（复用既有 normalize_curriculum_version / DOCX reader）
```

## 为什么需要它

个人规划入口必须先回答"**这位学生可以选哪些培养方案版本**"。
本模块把这个回答收敛成一条**只读、显式、不可猜**的路径：

- ⛔ **不扫描文件系统找默认目录**：目录必须由调用方显式给出；
- ⛔ **不联网**、⛔ **不读数据库**、⛔ **不写文件**、⛔ **不读 `mock_data`**；
- ⛔ **不解析非显式声明的格式**：artifact 必须是本模块声明的 JSON；
- ⛔ **不把未核验的东西变成可选项**：`supported` 为假、缺核验依据、
  或声明了本模块无法表达的规则 → 该版本**不进入可选择列表**；
- ⛔ **不解析 docx**：artifact 只能引用**已经**被既有 reader 支持的结构化 course
  records。真实培养方案 Word 的读取由既有 `app.curriculum` 入口负责，
  本模块不为个人入口新造一条解析路径。

## artifact 形态（本模块内部声明，**不是**公共 Schema）

```json
{
  "catalog_version": 1,
  "versions": [
    {
      "version_id": "example-target-2025",
      "major": "示例专业",
      "cohort": "2025",
      "campus": "示例校区",
      "track": "示例方向",
      "source_id": "verified-source://example/plan",
      "verification": {
        "verified": true,
        "evidence": "verified-source://example/plan/核验依据",
        "verified_by": "示例核验人"
      },
      "supported": true,
      "unsupported_reason": null,
      "complete": true,
      "completeness_evidence": "verified-source://example/plan/完整范围说明",
      "total_credit": 160,
      "practice_credit": 20,
      "study_years": 4,
      "group_records": [ ... CurriculumGroup 字段 ... ],
      "course_records": [ ... CurriculumCourse 字段 ... ]
    }
  ]
}
```

`unsupported_reason` 非空即"来源明确声明该版本**不能**由本入口支持"
（例如培养方案含本 MVP 无法表达的规则）。它**不**与"未核验"混用：
两者都不可选，但原因码不同，便于人工判断该补什么材料。

## 诊断边界

所有诊断只包含 **artifact 内的字段名 / 行号 / 版本 id 与固定原因码**，
⛔ **不含**目录路径、⛔ 不含任何学生数据。
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.json_reader import load_json_input
from app.curriculum.requirements import (
    CurriculumVersion,
    normalize_curriculum_version,
)

__all__ = [
    "CATALOG_FORMAT_VERSION",
    "CATALOG_REJECTED_CODES",
    "CatalogEntry",
    "CatalogInspection",
    "CatalogRejection",
    "CurriculumCatalog",
    "load_curriculum_catalog",
    "resolve_catalog_version",
]

#: 本模块唯一认识的 artifact 格式版本。⛔ 未知版本一律拒绝，不做向前兼容猜测。
CATALOG_FORMAT_VERSION = 1

#: 固定原因码（⛔ 不含路径 / 取值 / 学生数据）。
CATALOG_REJECTED_CODES = (
    "artifact_unreadable",
    "artifact_format_unsupported",
    "entry_invalid",
    "not_verified",
    "unsupported_by_source",
    "version_identity_conflict",
)

_CATALOG_REQUIRED = ("catalog_version", "versions")
_CATALOG_ALLOWED = frozenset(_CATALOG_REQUIRED)

_ENTRY_REQUIRED = (
    "version_id", "major", "cohort", "source_id", "verification",
    "supported", "complete",
)
_ENTRY_ALLOWED = frozenset(_ENTRY_REQUIRED) | {
    "campus", "track", "unsupported_reason", "completeness_evidence",
    "total_credit", "practice_credit", "study_years",
    "course_records", "group_records",
}

_VERIFICATION_REQUIRED = ("verified", "evidence")
_VERIFICATION_ALLOWED = frozenset(_VERIFICATION_REQUIRED) | {"verified_by"}


def _object(value: object, *, required: tuple[str, ...], allowed: frozenset[str], label: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise CurriculumNormalizationError(f"{label}: expected an object")
    if any(key not in allowed for key in value):
        # ⛔ 不回报未知键名：键名本身也可能夹带私有来源文本。
        raise CurriculumNormalizationError(f"{label}: unexpected record field")
    for field in required:
        if field not in value:
            raise CurriculumNormalizationError(f"{label}: missing field {field}")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CurriculumNormalizationError(f"{field}: expected a string or null")
    return value if value.strip() else None


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")
    return value


def _sequence(value: object, field: str) -> Sequence:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CurriculumNormalizationError(f"{field}: expected a sequence")
    return value


def _bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise CurriculumNormalizationError(f"{field}: expected a boolean")
    return value


def _optional_credit(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurriculumNormalizationError(f"{field}: expected a finite nonnegative number or null")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise CurriculumNormalizationError(f"{field}: expected a finite nonnegative number or null")
    return number


def _optional_year(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CurriculumNormalizationError(f"{field}: expected a positive integer or null")
    return value


@dataclass(frozen=True, slots=True)
class CatalogRejection:
    """一个**不可选**的目录条目及其固定原因码。"""

    version_id: str
    code: str
    detail: str

    def __post_init__(self) -> None:
        _text(self.version_id, "rejection version_id")
        if self.code not in CATALOG_REJECTED_CODES:
            raise CurriculumNormalizationError("rejection: unsupported reason code")
        _text(self.detail, "rejection detail")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """一个**可查询、可选择**的版本元信息（不暴露内部匹配实现）。"""

    version_id: str
    major: str
    cohort: str
    source_id: str
    campus: str | None
    track: str | None
    verification_evidence: str
    verified_by: str | None
    complete: bool
    completeness_evidence: str | None
    total_credit: float | None
    practice_credit: float | None
    study_years: int | None
    course_count: int
    group_count: int

    def __post_init__(self) -> None:
        for field in ("version_id", "major", "cohort", "source_id", "verification_evidence"):
            _text(getattr(self, field), field)
        for field in ("campus", "track", "verified_by", "completeness_evidence"):
            object.__setattr__(self, field, _optional_text(getattr(self, field), field))
        _bool(self.complete, "complete")
        if self.complete and self.completeness_evidence is None:
            raise CurriculumNormalizationError(
                "completeness_evidence: a complete version requires explicit evidence"
            )
        for field in ("total_credit", "practice_credit"):
            object.__setattr__(self, field, _optional_credit(getattr(self, field), field))
        object.__setattr__(self, "study_years", _optional_year(self.study_years, "study_years"))
        for field in ("course_count", "group_count"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CurriculumNormalizationError(f"{field}: expected a nonnegative integer")

    def to_metadata(self) -> dict:
        """对外可查询的元信息（⛔ 不含课程明细、不含内部匹配事实）。"""

        return {
            "version_id": self.version_id,
            "major": self.major,
            "cohort": self.cohort,
            "campus": self.campus,
            "track": self.track,
            "source_id": self.source_id,
            "verification_evidence": self.verification_evidence,
            "verified_by": self.verified_by,
            "complete": self.complete,
            "completeness_evidence": self.completeness_evidence,
            "total_credit": self.total_credit,
            "practice_credit": self.practice_credit,
            "study_years": self.study_years,
            "course_count": self.course_count,
            "group_count": self.group_count,
        }


@dataclass(frozen=True, slots=True)
class CatalogInspection:
    """一次目录装载的结果：可选版本 + 被拒条目 + 目录自身状态。"""

    format_supported: bool
    entries: tuple[CatalogEntry, ...]
    rejections: tuple[CatalogRejection, ...]

    def __post_init__(self) -> None:
        _bool(self.format_supported, "format_supported")
        object.__setattr__(self, "entries", tuple(self.entries))
        object.__setattr__(self, "rejections", tuple(self.rejections))
        if any(not isinstance(item, CatalogEntry) for item in self.entries):
            raise CurriculumNormalizationError("catalog: unexpected entry type")
        if any(not isinstance(item, CatalogRejection) for item in self.rejections):
            raise CurriculumNormalizationError("catalog: unexpected rejection type")
        ids = [item.version_id for item in self.entries]
        if len(set(ids)) != len(ids):
            raise CurriculumNormalizationError("catalog: duplicate selectable version id")

    @property
    def selectable(self) -> tuple[dict, ...]:
        """可直接返回给调用方的可选版本元信息列表。"""

        return tuple(entry.to_metadata() for entry in self.entries)

    def metadata_for(self, version_id: str) -> dict | None:
        """按 id 取**可选**版本的元信息；不可选 / 不存在返回 ``None``。"""

        if not isinstance(version_id, str):
            return None
        for entry in self.entries:
            if entry.version_id == version_id:
                return entry.to_metadata()
        return None

    def rejection_for(self, version_id: str) -> CatalogRejection | None:
        if not isinstance(version_id, str):
            return None
        for rejection in self.rejections:
            if rejection.version_id == version_id:
                return rejection
        return None


@dataclass(frozen=True, slots=True)
class CurriculumCatalog:
    """已装载目录：可选版本的**唯一**真源，同时持有构造好的内部版本对象。"""

    inspection: CatalogInspection
    _versions: tuple[tuple[str, CurriculumVersion], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.inspection, CatalogInspection):
            raise CurriculumNormalizationError("catalog: expected a CatalogInspection")
        pairs = tuple(self._versions)
        for pair in pairs:
            if (not isinstance(pair, tuple) or len(pair) != 2
                    or not isinstance(pair[0], str) or not isinstance(pair[1], CurriculumVersion)):
                raise CurriculumNormalizationError("catalog: unexpected version mapping")
        selectable = {entry.version_id for entry in self.inspection.entries}
        if {key for key, _ in pairs} != selectable:
            raise CurriculumNormalizationError("catalog: selectable entries and versions disagree")
        object.__setattr__(self, "_versions", pairs)

    def version_ids(self) -> tuple[str, ...]:
        return tuple(entry.version_id for entry in self.inspection.entries)

    def resolve(self, version_id: str) -> CurriculumVersion:
        """取一个**可选**版本的内部对象；不可选一律拒绝（⛔ 不回退任何默认版本）。"""

        for key, version in self._versions:
            if key == version_id:
                return version
        raise CurriculumNormalizationError(
            "curriculum version: not selectable in the loaded catalog"
        )


def _reject(version_id: str, code: str, detail: str) -> CatalogRejection:
    return CatalogRejection(version_id=version_id, code=code, detail=detail)


def _entry(
    record: object, *, row: int,
) -> tuple[CatalogEntry, CurriculumVersion] | CatalogRejection:
    """解析一个目录条目；任何不满足条件的条目都变成 reject，而不是被跳过。"""

    try:
        item = _object(
            record, required=_ENTRY_REQUIRED, allowed=_ENTRY_ALLOWED,
            label=f"versions row {row}",
        )
    except CurriculumNormalizationError:
        return _reject(f"row:{row}", "entry_invalid", "entry has an invalid shape")

    raw_id = item.get("version_id")
    version_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else f"row:{row}"

    try:
        verification = _object(
            item["verification"], required=_VERIFICATION_REQUIRED,
            allowed=_VERIFICATION_ALLOWED, label="verification",
        )
        verified = _bool(verification["verified"], "verified")
        evidence = _optional_text(verification["evidence"], "verification evidence")
        verified_by = _optional_text(verification.get("verified_by"), "verified_by")
        supported = _bool(item["supported"], "supported")
        unsupported_reason = _optional_text(item.get("unsupported_reason"), "unsupported_reason")
    except CurriculumNormalizationError:
        return _reject(version_id, "entry_invalid", "entry metadata is not usable")

    if not verified or evidence is None:
        # ⛔ 未核验的方案不进入可选择列表；也⛔ 不用 source_id 冒充核验依据。
        return _reject(version_id, "not_verified", "the version carries no verification evidence")
    if not supported:
        return _reject(
            version_id, "unsupported_by_source",
            unsupported_reason or "the version is declared unsupported by its source",
        )
    if unsupported_reason is not None:
        # 同时 supported=true 且给出不支持原因 = 自相矛盾的声明，fail closed。
        return _reject(version_id, "entry_invalid", "entry contradicts its own support flag")

    try:
        version = normalize_curriculum_version(
            version_id=_text(item["version_id"], "version_id"),
            major=_text(item["major"], "major"),
            cohort=_text(item["cohort"], "cohort"),
            source_id=_text(item["source_id"], "source_id"),
            course_records=item.get("course_records", ()),
            group_records=item.get("group_records", ()),
            complete=_bool(item["complete"], "complete"),
            completeness_evidence=_optional_text(
                item.get("completeness_evidence"), "completeness_evidence"
            ),
            total_credit=_optional_credit(item.get("total_credit"), "total_credit"),
            practice_credit=_optional_credit(item.get("practice_credit"), "practice_credit"),
            study_years=_optional_year(item.get("study_years"), "study_years"),
        )
    except CurriculumNormalizationError:
        return _reject(version_id, "entry_invalid", "the version records are not usable")

    entry = CatalogEntry(
        version_id=version.version_id,
        major=version.major,
        cohort=version.cohort,
        source_id=version.source_id,
        campus=_optional_text(item.get("campus"), "campus"),
        track=_optional_text(item.get("track"), "track"),
        verification_evidence=evidence,
        verified_by=verified_by,
        complete=version.complete,
        completeness_evidence=version.completeness_evidence,
        total_credit=version.total_credit,
        practice_credit=version.practice_credit,
        study_years=version.study_years,
        course_count=len(version.courses),
        group_count=len(version.groups),
    )
    return entry, version


def load_curriculum_catalog(directory: str | Path, *, file_name: str = "catalog.json") -> CurriculumCatalog:
    """从**调用方显式给出**的本地目录装载已核验版本目录。

    `file_name` 的相对值只在 `directory` **之内**解析（⛔ 不接受路径分隔符，
    避免用名字跳出调用方显式指定的目录）；绝对路径则按原样使用。

    - 目录 / artifact 缺失或不可读 → 空目录（`format_supported=True`, 无条目），
      **不是**异常：调用方据此明确回答"当前没有可选版本"，
      ⛔ 不猜任何默认版本；
    - artifact 存在但格式版本未知 → `format_supported=False` + 固定原因码，
      ⛔ 不做向前兼容解析。
    """

    if not isinstance(directory, (str, Path)):
        raise CurriculumNormalizationError("catalog: expected a local directory reference")
    if not isinstance(file_name, str) or not file_name.strip():
        raise CurriculumNormalizationError("catalog: expected an artifact file name")
    try:
        root = Path(directory)
        name = Path(file_name)
        # 相对名必须**就是**一个名字（不含任何路径分隔 / 上跳），绝对路径按原样使用。
        if not name.is_absolute() and name.name != file_name:
            raise CurriculumNormalizationError(
                "catalog: a relative artifact name must stay inside the given directory"
            )
        path = name if name.is_absolute() else root.joinpath(file_name)
    except CurriculumNormalizationError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise CurriculumNormalizationError("catalog: invalid local directory reference") from None

    try:
        exists = path.is_file()
    except (OSError, ValueError):
        exists = False
    if not exists:
        return CurriculumCatalog(CatalogInspection(True, (), ()))
    try:
        payload = load_json_input(path, label="catalog")
    except CurriculumNormalizationError:
        return CurriculumCatalog(CatalogInspection(
            True, (),
            (_reject("artifact", "artifact_unreadable", "the catalog artifact is not readable JSON"),),
        ))

    if not isinstance(payload, Mapping):
        return CurriculumCatalog(CatalogInspection(
            True, (),
            (_reject("artifact", "artifact_unreadable", "the catalog artifact is not an object"),),
        ))
    if any(key not in _CATALOG_ALLOWED for key in payload):
        return CurriculumCatalog(CatalogInspection(
            True, (),
            (_reject("artifact", "artifact_unreadable", "the catalog artifact has unexpected fields"),),
        ))
    if "catalog_version" not in payload or "versions" not in payload:
        return CurriculumCatalog(CatalogInspection(
            True, (),
            (_reject("artifact", "artifact_unreadable", "the catalog artifact is incomplete"),),
        ))

    format_version = payload["catalog_version"]
    if format_version != CATALOG_FORMAT_VERSION or isinstance(format_version, bool):
        return CurriculumCatalog(CatalogInspection(
            False, (),
            (_reject(
                "artifact", "artifact_format_unsupported",
                "the catalog artifact format version is not supported",
            ),),
        ))

    try:
        rows = _sequence(payload["versions"], "versions")
    except CurriculumNormalizationError:
        return CurriculumCatalog(CatalogInspection(
            True, (),
            (_reject("artifact", "artifact_unreadable", "the catalog versions are not a sequence"),),
        ))

    entries: list[CatalogEntry] = []
    versions: list[tuple[str, CurriculumVersion]] = []
    rejections: list[CatalogRejection] = []
    seen: set[str] = set()
    for row, record in enumerate(rows, start=1):
        outcome = _entry(record, row=row)
        if isinstance(outcome, CatalogRejection):
            rejections.append(outcome)
            continue
        entry, version = outcome
        if entry.version_id in seen:
            # 同一 version_id 出现多次：无法唯一确定该选哪一份，
            # 该 id 的**全部**条目都不可选（fail closed）。
            if not any(item.version_id == entry.version_id for item in rejections):
                rejections.append(_reject(
                    entry.version_id, "version_identity_conflict",
                    "the catalog declares the same version id more than once",
                ))
            entries = [item for item in entries if item.version_id != entry.version_id]
            versions = [item for item in versions if item[0] != entry.version_id]
            continue
        seen.add(entry.version_id)
        entries.append(entry)
        versions.append((entry.version_id, version))

    return CurriculumCatalog(
        CatalogInspection(True, tuple(entries), tuple(rejections)),
        tuple(versions),
    )


def resolve_catalog_version(catalog: CurriculumCatalog, version_id: str) -> CurriculumVersion:
    """公开的版本解析入口；不可选版本一律以明确错误拒绝。

    ⛔ 不回退到 Case A、⛔ 不回退到第一个可用版本、⛔ 不使用任何默认版本。
    """

    if not isinstance(catalog, CurriculumCatalog):
        raise CurriculumNormalizationError("catalog: expected a CurriculumCatalog")
    if not isinstance(version_id, str) or not version_id.strip():
        raise CurriculumNormalizationError("curriculum version: expected a version id")
    return catalog.resolve(version_id)
