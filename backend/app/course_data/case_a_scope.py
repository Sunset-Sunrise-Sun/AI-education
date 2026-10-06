"""Case A **scoped**（南校园 + 深圳校区）教学班数据集 —— 派生、只读、**demo scope**。

```text
已正式验收的 campus acceptance 记录（南校园 5062201 / 深圳校区 333291143）
        ↓  load_accepted_offerings(scope = campus / <number>)     ← 复用既有信任链
两个 campus acceptance（各自 content-bound，逐行内容指纹已核对）
        ↓  canonical identity 合并（(semester, course_id, class_id)）
Case A scoped 教学班数据集（CaseADataset）
        ↓  CaseAScopedCourseDataProvider.get_course_offerings(semester)
list[CourseOffering]  →  demo / planner smoke（⛔ 不进 production Provider）
```

## 这是什么，不是什么（⛔ 措辞是契约的一部分）

```text
是：   Case A scoped South + Shenzhen teaching-class data（demo scope）
       case_scoped / south+shenzhen / demo scope
不是： full_semester
       whole school / all campus / complete SYSU database
       LEVEL2 real dataset
       五校区完整供给
```

## 为什么这样最小

1. **不改** `full_semester` acceptance 的任何语义：本模块**不调用**
   `accept_full_semester_capture_set()`，**不产生** manifest，
   **不写** `full_semester` scope 的任何行；
2. **不新增信任框架**：每个校区的可信性仍然来自既有 campus acceptance
   （`load_accepted_offerings()`：acceptance 平面 + 历史导入平面 + membership +
   逐行 `offering_payload_sha256` + 整批 `offering_set_sha256`）；
3. **不新增公共 Schema**：输出仍然是公共 `CourseOffering[]`；
4. **不写库**：本模块只读。Case A 数据集**不落进** production trust store，
   因此不可能被误当成"某次 acceptance 绑定的行"；
5. 排序 / 合并口径复用 `offering_digest.offering_identity()` 与
   `offering_digest.offering_set_sha256()`（⛔ 不按 `course_id` 去重）。

## 校区白名单（单一真源）

South / Shenzhen 的 `openingSchoolNumber` **不在这里重复写死**：
本模块从 `full_semester_acceptance.APPROVED_FULL_SEMESTER_SHARDS`
按 `shard_id` 过滤得到，因此两侧不可能漂移。

## 合并规则（与 full_semester merge 的**显式差异**）

`merge_offering_snapshots()`（full_semester 路径）把校区 shard 视为**互斥分区**：
跨 shard 重复 identity 一律 fail closed。

Case A scoped 合并**不修改**那个函数，而是另有一条明确规则：

```text
同一 identity + canonical payload 完全相同  → 去重（计数并如实报告）
同一 identity + canonical payload 不同      → fail closed（conflicting_identity）
```

这样"两个校区确实收录了同一教学班"这一**观测事实**不会被误当成数据损坏，
而任何真正的冲突仍然 fail closed（⛔ 不静默取第一条）。

## 边界（硬）

- ⛔ 不联网、⛔ 不读凭据、⛔ 不写库、⛔ 不建表、⛔ 不导出 raw row；
- ⛔ 不改 `StoreBackedCourseDataProvider`、⛔ 不改 `SnapshotCourseDataProvider`、
  ⛔ 不改 `merge_offering_snapshots`、⛔ 不改 `planning_runtime.py` 的装配口径
  （production runtime 仍然**只**认 full_semester acceptance）；
- ⛔ 本模块的错误信息只含最小 identity（`semester` / `course_id` / `class_id`），
  ⛔ 不回显课程名 / 教师 / 任何 raw 字段。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.course_data.errors import CourseDataNormalizationError
from app.course_data.full_semester_acceptance import (
    APPROVED_FULL_SEMESTER_SHARDS,
    FullSemesterShard,
)
from app.course_data.offering_digest import (
    OfferingIdentity,
    canonical_offering_payload,
    offering_identity,
    offering_set_sha256,
)
from app.course_data.store import (
    SCOPE_KIND_CAMPUS,
    CourseDataStoreError,
    SnapshotScope,
    load_accepted_offerings,
    load_course_data_acceptances,
)
from app.models.contracts import CourseOffering

__all__ = [
    "CASE_A_CAMPUS_SHARD_IDS",
    "CASE_A_DATASET_FORMAT",
    "CASE_A_DATASET_VERSION",
    "CASE_A_SCOPE_KIND",
    "CASE_A_SCOPE_LABEL",
    "CASE_A_SCOPE_SEMANTICS",
    "CASE_A_TOOL",
    "CATEGORY_CAMPUS_ACCEPTANCE_AMBIGUOUS",
    "CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH",
    "CATEGORY_CAMPUS_ACCEPTANCE_MISSING",
    "CATEGORY_CASE_SCOPE_EMPTY",
    "CATEGORY_CONFLICTING_IDENTITY",
    "CATEGORY_SEMESTER_MISMATCH",
    "CATEGORY_STORE_ERROR",
    "CaseACampusRecord",
    "CaseADataset",
    "CaseAScope",
    "CaseAScopeError",
    "CaseAScopedCourseDataProvider",
    "case_a_campuses",
    "case_a_scope",
    "build_case_a_dataset",
    "serialize_case_a_dataset",
]


#: Case A 今晚只需要这两个校区 shard（`shard_id` 与 full_semester 已批准集合同名）。
CASE_A_CAMPUS_SHARD_IDS: tuple[str, ...] = ("south-campus", "shenzhen-campus")

#: scope kind **标签**（⚠️ 只用于本模块的输出/审计标签）。
#:
#: ⛔ **绝不**传给 `SnapshotScope`：`store.ALLOWED_SCOPE_KINDS` 明确不收录
#: case-scoped 取值（其 id 语义尚未确证），本模块也不写库，因此两者不会相遇。
CASE_A_SCOPE_KIND = "case_scoped"

#: 人类可读的 scope 标签（写进所有输出的同一份字符串）。
CASE_A_SCOPE_LABEL = "case-a-scoped:south+shenzhen"

#: scope 语义（机器与操作员共用同一份定义；⛔ 与 full_semester 明确互斥）。
CASE_A_SCOPE_SEMANTICS = (
    "case_a_scoped_south_plus_shenzhen_teaching_class_data_demo_scope_only;"
    "not_full_semester;not_whole_school;not_all_campus;not_complete_sysu_database;"
    "not_level2_real_dataset;not_a_five_campus_supply"
)

#: 产出 Case A 数据集的工具名（写进输出，便于审计时定位）。
CASE_A_TOOL = "tools/case_a_course_data.py"

#: Case A 数据集导出格式（**内部 / demo 交换格式**，⛔ 不进 `schemas/`）。
CASE_A_DATASET_FORMAT = "sysu-case-a-course-data-scope-v1"
CASE_A_DATASET_VERSION = 1

#: 失败类别（机器可读；CLI 按类别映射退出码，⛔ 不解析错误文本）。
CATEGORY_STORE_ERROR = "store_error"
CATEGORY_CAMPUS_ACCEPTANCE_MISSING = "campus_acceptance_missing"
CATEGORY_CAMPUS_ACCEPTANCE_AMBIGUOUS = "campus_acceptance_ambiguous"
CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH = "campus_acceptance_mismatch"
CATEGORY_CASE_SCOPE_EMPTY = "case_scope_empty"
CATEGORY_CONFLICTING_IDENTITY = "conflicting_identity_across_case_a_campuses"
CATEGORY_SEMESTER_MISMATCH = "semester_mismatch"


class CaseAScopeError(CourseDataNormalizationError):
    """Case A scoped 数据集无法安全构造（fail closed）。

    `category` 是**机器可读**的失败类别；`shard_id`（可选）是**结构性**定位信息。
    """

    def __init__(
        self, message: str, *, category: str, shard_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.category = category
        self.shard_id = shard_id


def case_a_campuses() -> tuple[FullSemesterShard, ...]:
    """Case A 的两个已批准校区（号码的唯一真源是 full_semester 已批准集合）。"""

    by_id = {shard.shard_id: shard for shard in APPROVED_FULL_SEMESTER_SHARDS}
    missing = [shard_id for shard_id in CASE_A_CAMPUS_SHARD_IDS if shard_id not in by_id]
    if missing:  # pragma: no cover - 结构性防御（已批准集合是常量）
        raise CaseAScopeError(
            f"已批准校区集合中缺少 Case A 需要的 shard：{missing}",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISSING,
        )
    return tuple(by_id[shard_id] for shard_id in CASE_A_CAMPUS_SHARD_IDS)


@dataclass(frozen=True, slots=True)
class CaseAScope:
    """Case A 数据集的作用域声明（⛔ 与 full_semester 互斥的**显式**标签）。"""

    semester: str
    campuses: tuple[FullSemesterShard, ...]

    @property
    def scope_kind(self) -> str:
        return CASE_A_SCOPE_KIND

    @property
    def scope_label(self) -> str:
        return CASE_A_SCOPE_LABEL

    @property
    def scope_id(self) -> str:
        """本 scope 的稳定 id（审计标签；⛔ 不是学期，也⛔ 不是校区号）。"""

        return f"{CASE_A_SCOPE_LABEL}@{self.semester}"

    @property
    def scope_semantics(self) -> str:
        return CASE_A_SCOPE_SEMANTICS

    @property
    def is_full_semester(self) -> bool:
        """⛔ 永远为 `False`：本数据集**不是** full_semester acceptance。"""

        return False

    @property
    def is_whole_school(self) -> bool:
        """⛔ 永远为 `False`：两个校区 ≠ 全校 / 五校区完整供给。"""

        return False

    @property
    def opening_school_numbers(self) -> tuple[str, ...]:
        return tuple(shard.opening_school_number for shard in self.campuses)

    @property
    def shard_ids(self) -> tuple[str, ...]:
        return tuple(shard.shard_id for shard in self.campuses)


def case_a_scope(semester: str) -> CaseAScope:
    """构造 Case A scope（⛔ 不接受调用方自定义校区集合）。"""

    if not isinstance(semester, str) or not semester.strip():
        raise CaseAScopeError(
            "semester 必须是非空字符串（例如 '2026-1'）",
            category=CATEGORY_SEMESTER_MISMATCH,
        )
    return CaseAScope(semester=semester.strip(), campuses=case_a_campuses())


@dataclass(frozen=True, slots=True)
class CaseACampusRecord:
    """Case A 数据集里**一个校区**的 acceptance 证据（⛔ 不含任何教学班取值）。"""

    shard_id: str
    opening_school_number: str
    campus_acceptance_sha256: str
    source: str | None
    offering_count: int
    offering_set_sha256: str

    def summary(self) -> dict[str, object]:
        return {
            "shard_id": self.shard_id,
            "openingSchoolNumber": self.opening_school_number,
            "campus_acceptance_sha256": self.campus_acceptance_sha256,
            "campus_acceptance_sha256_semantics": (
                "campus_artifact_exact_byte_identity_not_acquisition_provenance_proof"
            ),
            "source": self.source,
            "source_semantics": "audit_label_only_not_provenance_proof",
            "offering_count": self.offering_count,
            "offering_set_sha256": self.offering_set_sha256,
        }


@dataclass(frozen=True, slots=True)
class CaseADataset:
    """Case A scoped 教学班数据集（**派生、只读、demo scope**）。

    - `scope` —— Case A scope 声明（`is_full_semester` 恒为 `False`）；
    - `offerings` —— 公共 `CourseOffering[]`（按 `(course_id, class_id)` 稳定排序）；
    - `campuses` —— 每个校区的 campus acceptance 证据；
    - `duplicate_identity_deduped` —— 两校区同 identity **且内容相同**的去重条数；
    - `merged_offering_set_sha256` —— 合并后整批内容的确定性 digest。

    ⛔ `is_full_semester` / `is_whole_school` 恒为 `False`：这不是、
    也永远不会被当作 full_semester acceptance 或全校完整供给。
    """

    scope: CaseAScope
    offerings: tuple[CourseOffering, ...]
    campuses: tuple[CaseACampusRecord, ...]
    duplicate_identity_deduped: int
    merged_offering_set_sha256: str

    @property
    def merged_offering_count(self) -> int:
        return len(self.offerings)

    @property
    def is_full_semester(self) -> bool:
        return False

    @property
    def is_whole_school(self) -> bool:
        return False


def _accepted_campus_record(
    sqlite_path: str | Path,
    *,
    semester: str,
    shard: FullSemesterShard,
) -> tuple[CaseACampusRecord, tuple[CourseOffering, ...]]:
    """读回**一个**校区已正式验收的 campus acceptance（复用既有信任链）。

    ⛔ 没有 fallback：没有记录 / 记录不唯一 / scope 不是 campus /
    scope_id 不是已批准号码 / 不是 complete / 计数不自洽 / 内容被替换
    ⇒ 一律 `CaseAScopeError`（⛔ 不返回空列表，⛔ 不退化成本学期任意行）。
    """

    number = shard.opening_school_number
    label = shard.shard_id

    try:
        acceptances = load_course_data_acceptances(sqlite_path, semester=semester)
    except CourseDataStoreError as exc:
        raise CaseAScopeError(
            f"无法读取本地 Course Data 库的 acceptance 记录（shard {label}）",
            category=CATEGORY_STORE_ERROR,
            shard_id=label,
        ) from exc

    matching = [
        record
        for record in acceptances
        if record.scope_kind == SCOPE_KIND_CAMPUS and record.scope_id == number
    ]

    if not matching:
        raise CaseAScopeError(
            f"本地库中没有 {label}（openingSchoolNumber={number}）的 campus acceptance 记录；"
            f"⛔ 必须先以 campus scope 正式接受该校区 artifact（⛔ 不 fallback、不猜）",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISSING,
            shard_id=label,
        )

    if len(matching) != 1:
        raise CaseAScopeError(
            f"{label} 出现 {len(matching)} 条 campus acceptance 记录；"
            f"⛔ 无法确定哪一批行算数，拒绝继续",
            category=CATEGORY_CAMPUS_ACCEPTANCE_AMBIGUOUS,
            shard_id=label,
        )

    record = matching[0]
    scope = SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id=number)

    try:
        dataset = load_accepted_offerings(
            sqlite_path,
            semester=semester,
            acceptance_sha256=record.artifact_sha256,
            scope=scope,
        )
    except CourseDataStoreError as exc:
        raise CaseAScopeError(
            f"{label} 的 campus acceptance 无法通过内容绑定校验"
            f"（acceptance / membership / 逐行内容指纹 / 整批 digest 任一不符）；拒绝继续",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            shard_id=label,
        ) from exc

    if dataset.acceptance.scope_id != number:
        raise CaseAScopeError(
            f"{label} 的 acceptance scope_id 与已批准 openingSchoolNumber 不一致；拒绝继续",
            category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            shard_id=label,
        )

    return (
        CaseACampusRecord(
            shard_id=label,
            opening_school_number=number,
            campus_acceptance_sha256=dataset.acceptance.artifact_sha256,
            source=dataset.acceptance.source,
            offering_count=dataset.acceptance.offering_count,
            offering_set_sha256=dataset.acceptance.offering_set_sha256,
        ),
        dataset.offerings,
    )


def _merge_case_a_offerings(
    per_campus: Sequence[tuple[CaseACampusRecord, Sequence[CourseOffering]]],
) -> tuple[tuple[CourseOffering, ...], int]:
    """按 canonical identity 合并各校区教学班（⛔ 不按 `course_id` 去重）。

    ```text
    同一 identity + canonical payload 相同 → 去重（如实计数）
    同一 identity + canonical payload 不同 → fail closed
    ```
    """

    by_identity: dict[OfferingIdentity, tuple[CourseOffering, str]] = {}
    deduped = 0

    for record, offerings in per_campus:
        for offering in offerings:
            identity = offering_identity(offering)
            payload = canonical_offering_payload(offering)
            existing = by_identity.get(identity)

            if existing is None:
                by_identity[identity] = (offering, payload)
                continue

            if existing[1] == payload:
                deduped += 1
                continue

            # ⛔ 只报告最小 identity，⛔ 不回显课程名 / 教师 / 任何 raw 取值。
            raise CaseAScopeError(
                f"Case A 两个校区在同一教学班 identity 上出现**不同内容**："
                f"semester={identity[0]} course_id={identity[1]} class_id={identity[2]}"
                f"（shard {record.shard_id}）；⛔ 拒绝静默取第一条",
                category=CATEGORY_CONFLICTING_IDENTITY,
                shard_id=record.shard_id,
            )

    merged = sorted(
        (item[0] for item in by_identity.values()),
        key=lambda offering: (offering.course_id, offering.class_id),
    )

    return tuple(merged), deduped


def build_case_a_dataset(
    sqlite_path: str | Path,
    *,
    semester: str,
    expected_campus_sha256: Mapping[str, str] | None = None,
) -> CaseADataset:
    """从本地库的**两个** campus acceptance 派生 Case A scoped 教学班数据集。

    - `sqlite_path` —— 持有 campus acceptance 记录的本地 Course Data 库（只读）；
    - `semester` —— 两个校区必须同属该学期；
    - `expected_campus_sha256` —— 可选的 `shard_id → campus acceptance SHA-256`
      人工/记录门（与磁盘上被接受的那批字节逐校区对账）。

    ⛔ 本函数**不写库**：Case A 数据集不落进 production trust store，
    因此不可能被 `StoreBackedCourseDataProvider`（只认 full_semester acceptance）
    误读为 production 供给。
    """

    scope = case_a_scope(semester)

    if expected_campus_sha256 is not None:
        if not isinstance(expected_campus_sha256, Mapping):
            raise CaseAScopeError(
                f"expected_campus_sha256 必须是映射，实际是 "
                f"{type(expected_campus_sha256).__name__}",
                category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            )
        unknown = sorted(
            key for key in expected_campus_sha256 if key not in CASE_A_CAMPUS_SHARD_IDS
        )
        if unknown:
            raise CaseAScopeError(
                f"expected_campus_sha256 出现未批准的 shard 键（{len(unknown)} 个）；"
                f"Case A 只接受 {list(CASE_A_CAMPUS_SHARD_IDS)}",
                category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
            )

    per_campus: list[tuple[CaseACampusRecord, tuple[CourseOffering, ...]]] = []

    for shard in scope.campuses:
        record, offerings = _accepted_campus_record(
            sqlite_path, semester=scope.semester, shard=shard
        )

        if expected_campus_sha256 is not None and shard.shard_id in expected_campus_sha256:
            expected = expected_campus_sha256[shard.shard_id]
            if (
                not isinstance(expected, str)
                or not expected.strip()
                or expected.strip().lower() != record.campus_acceptance_sha256
            ):
                raise CaseAScopeError(
                    f"{shard.shard_id} 的 campus acceptance digest 与调用方给出的期望值不一致；"
                    f"⛔ 拒绝把自己声明的 digest 当成证据",
                    category=CATEGORY_CAMPUS_ACCEPTANCE_MISMATCH,
                    shard_id=shard.shard_id,
                )

        per_campus.append((record, offerings))

    total_rows = sum(record.offering_count for record, _rows in per_campus)
    if total_rows == 0:
        raise CaseAScopeError(
            "Case A 两个 campus acceptance 合计 0 行；⛔ 拒绝产出空数据集",
            category=CATEGORY_CASE_SCOPE_EMPTY,
        )

    merged, deduped = _merge_case_a_offerings(per_campus)

    if not merged:
        raise CaseAScopeError(
            "Case A 合并后 0 行；⛔ 拒绝产出空数据集",
            category=CATEGORY_CASE_SCOPE_EMPTY,
        )

    return CaseADataset(
        scope=scope,
        offerings=merged,
        campuses=tuple(record for record, _rows in per_campus),
        duplicate_identity_deduped=deduped,
        merged_offering_set_sha256=offering_set_sha256(merged),
    )


def serialize_case_a_dataset(dataset: CaseADataset) -> dict[str, object]:
    """把 Case A 数据集序列化成**自带 scope 标签**的导出文档。

    ⛔ 输出里**同时**出现正向标签与反向断言（`is_full_semester: false` 等），
    使下游无法只截取一半就把它当成 full_semester / 全校数据。
    """

    if not isinstance(dataset, CaseADataset):
        raise CaseAScopeError(
            f"serialize_case_a_dataset 只接受 CaseADataset，实际是 "
            f"{type(dataset).__name__}",
            category=CATEGORY_STORE_ERROR,
        )

    return {
        "format": CASE_A_DATASET_FORMAT,
        "dataset_version": CASE_A_DATASET_VERSION,
        "tool": CASE_A_TOOL,
        "semester": dataset.scope.semester,
        "scope_kind": dataset.scope.scope_kind,
        "scope_label": dataset.scope.scope_label,
        "scope_id": dataset.scope.scope_id,
        "scope_semantics": dataset.scope.scope_semantics,
        "scope_semantics_note": (
            "本文件是 Case A scoped（南校园 + 深圳校区）教学班数据，"
            "仅用于比赛 Case A 演示；⛔ 不代表全学期 / 全校 / 五校区完整供给，"
            "⛔ 不是 LEVEL2 real dataset。"
        ),
        "is_full_semester": False,
        "is_whole_school": False,
        "is_all_campus": False,
        "is_level2_real_dataset": False,
        "openingSchoolNumbers": list(dataset.scope.opening_school_numbers),
        "campuses": [record.summary() for record in dataset.campuses],
        "merged_offering_count": dataset.merged_offering_count,
        "merged_offering_set_sha256": dataset.merged_offering_set_sha256,
        "merged_offering_set_sha256_semantics": (
            "exact_normalized_offering_content_of_this_case_scoped_dataset"
        ),
        "duplicate_identity_deduped": dataset.duplicate_identity_deduped,
        "duplicate_identity_deduped_semantics": (
            "same_identity_and_identical_canonical_payload_found_in_both_campuses"
            "_deduplicated_and_reported;conflicting_content_is_rejected"
        ),
        "offerings": [
            offering.model_dump(mode="json") for offering in dataset.offerings
        ],
    }


class CaseAScopedCourseDataProvider:
    """把 Case A scoped 数据集**只读**地暴露成 `CourseDataProvider` 形状。

    ⚠️ 本类是 **demo / smoke 用**的派生 Provider：

    - 结构上满足冻结的 `CourseDataProvider`（`get_course_offerings(semester)`），
      ⛔ 不继承、⛔ 不修改该 Protocol；
    - ⛔ **不是** production Provider：`app/main.py` 的真实规划链路仍然只认
      `StoreBackedCourseDataProvider`（full_semester acceptance）；
    - ⛔ **不 fallback**：学期不匹配 ⇒ `CaseAScopeError`（fail closed），
      ⛔ 不返回空列表、⛔ 不退化成本学期任意行；
    - ⛔ 不缓存 / 不改写 / 不补默认值：返回数据集里的**同一批**公共对象副本。
    """

    def __init__(self, dataset: CaseADataset) -> None:
        if not isinstance(dataset, CaseADataset):
            raise CaseAScopeError(
                f"CaseAScopedCourseDataProvider 只接受 CaseADataset，实际是 "
                f"{type(dataset).__name__}",
                category=CATEGORY_STORE_ERROR,
            )
        self._dataset = dataset

    @property
    def dataset(self) -> CaseADataset:
        return self._dataset

    @property
    def scope(self) -> CaseAScope:
        return self._dataset.scope

    @property
    def is_full_semester(self) -> bool:
        """⛔ 永远为 `False`（便于调用方在装配处显式断言）。"""

        return False

    @property
    def campuses(self) -> tuple[CaseACampusRecord, ...]:
        return self._dataset.campuses

    def get_course_offerings(self, semester: str) -> list[CourseOffering]:
        """返回 Case A scoped 教学班；学期不匹配 ⇒ fail closed。

        ⚠️ 返回值是**副本列表**，但元素是数据集里的同一批（不可变）公共对象。
        """

        if not isinstance(semester, str) or semester != self._dataset.scope.semester:
            raise CaseAScopeError(
                f"该 Case A scoped Provider 只绑定 semester="
                f"{self._dataset.scope.semester!r}；⛔ 拒绝其它学期的请求"
                f"（不返回空列表、不 fallback）",
                category=CATEGORY_SEMESTER_MISMATCH,
            )

        return list(self._dataset.offerings)
