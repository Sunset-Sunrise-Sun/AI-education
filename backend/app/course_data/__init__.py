"""Course Data 内部实现包（2B-2A 内核 + 2B-2B parser / importer + 2B-2C0 分页 + 2B-2C1A Capture Bridge）。

```text
已登录浏览器（用户显式触发）→ tools/sysu_course_offering_collector.js
        ↓  本地 Capture Bundle（Real Sanitized Capture，不入 Git）
        ↓  captured_pages：CapturedPagesFetcher（只回放，零网络）
        ↓  pagination：串行取页（fetch_page 由外部提供）
        ↓  teachingTimePlaceStr parser
ParsedScheduleSegment[]
        ↓  extract_meetings()
Meeting[]
        ↓  build_course_offering()
CourseOffering[]
        ↓
OfferingSnapshot（带 completeness 证据链）
        ↓
CourseDataProvider.get_course_offerings(semester)
```

⚠️ **本地持久化（MVP 课程数据库，SQLite）**：已判定 `complete` 的快照可以落到本地库，
供后续 Planner / Provider 读取（⛔ 本层**不**判断 completeness，也⛔ **不**改 Provider）：

```text
OfferingSnapshot（上游已判定 complete）
        ↓  store.import_offering_snapshot(path, snapshot, artifact_sha256=...)
本地 SQLite（identity = (semester, course_id, class_id)，重复导入幂等）
        ↓  store.load_course_offerings(path, semester, course_ids=[...])
list[CourseOffering]
```

⚠️ **2026-1 深分页异常 → 校区 shard 合并路径**（Architecture Review 裁定方案 B）：
学校接口在 **offset >= 6500** 稳定 `HTTP 600`，因此**按已确认校区维度分片**捕获
（⛔ 不重编号、⛔ 不重切分、⛔ 不拼伪单流、⛔ 不改 Capture Bundle format）：

```text
5 份独立 Capture Bundle（各自真实捕获，⛔ 不入 Git）
        ↓  各自 collect_captured_pages_snapshot()
   5 个 OfferingSnapshot（各自必须 complete）
        ↓  sharded_capture.collect_sharded_capture_set(...)   ← 编排 + fail closed
   合并后的 complete OfferingSnapshot（唯一维度 = (semester, course_id, class_id)）
```

⚠️ **full-semester acceptance（Gate A）**：`sharded_capture` 要求调用方提供**一份
complete 的 baseline 快照**，而真实采集侧只有**总量证据**。因此在其之上新增
**更高层** orchestration（⛔ 未改动 `merge_offering_snapshots()` 的低层语义）：

```text
5 份 raw Capture Bundle + baseline_before/baseline_after（总量证据）
        ↓  exact five-shard 校验 + 每个 raw-byte SHA-256
        ↓  baseline_before == baseline_after（否则 snapshot_window_unstable）
        ↓  Σ shard reported_total == 稳定 baseline（否则 shard_coverage_mismatch）
        ↓  merge_offering_snapshots(...)
   merged complete OfferingSnapshot + canonical manifest + manifest SHA-256
```

`manifest_sha256 = acceptance record identity / integrity ≠ acquisition provenance proof`；
⛔ 没有 `--skip-north` / `--allow-partial-semester` / `--force-complete` 这类逃生参数。

⚠️ **本包是 Course Data 的内部实现，不是跨模块公共契约。**

- 公共边界**只有** `CourseDataProvider.get_course_offerings(semester)`
  （见 `docs/interfaces/integration.md`，Phase 2B-1 已冻结）；
  本包的 `SnapshotCourseDataProvider` **结构上满足**它，但**不继承、不修改**它。
- 本包**不修改** `schemas/`、`docs/interfaces/`、`integration/`。
- `ParsedScheduleSegment`、`OfferingSnapshot`、`OpeningCoursesPageFetcher`、
  `CapturedPagesFetcher` 与 Capture Bundle **都是内部对象 / 内部接口 / 内部格式**，
  不会成为新的跨模块 Schema，也**不加入** Integration。

⚠️ **零网络**：本包没有 endpoint、没有 Cookie / Session / Token、没有 crawler、
没有 Playwright / Selenium、不 import `mock_service`，**也不会自动 fallback 到 Mock**。
分页核心的 `fetch_page` **由调用方提供**；
真实取数由**浏览器侧**在用户本人已登录、已有权限的页面上显式触发
（`tools/sysu_course_offering_collector.js`），本包只回放其**已脱敏**产物。

当前阶段边界：

- ✅ 已完成：已确认字段的确定性映射 / 校验、周次展开、`teachingTimePlaceStr` parser、
  纯本地 Raw-response import adapter、带 completeness 的内部快照、Provider 最小落点、
  零网络分页采集核心（含 completeness 证据链）、
  **浏览器端授权采集器代码 + Capture Bridge**、
  **多 shard Capture Bundle 的内部合并编排（`sharded_capture`，纯 synthetic 验证）**；
- ⏳ 未执行：**真实完整学期程序化采集**（由负责人在 Reviewer 合并后手动 smoke run），
  因此**尚未取得 complete semester snapshot**；
- ⛔ **不做**：`weekDay → weekday`、`openingSchoolName → campus`
  （`weekday` 一律来自 segment 自身；`campus` 只来自 segment 的 location 字段）；
- ⛔ meeting 级教师关联仍是 **known deferred representation gap**：
  parser **内部保留** `teacher`（`ParsedScheduleSegment.teacher`，**可为 `None`** ——
  2026-1 真实证据已确认 teacher 并不总在 `teachingTimePlaceStr` 中出现），
  但**不进入公共 `Meeting`**，**不修改任何 Schema**；
- ⛔ `max_pages` 截断产生的 `partial` snapshot **不得**接入 Integration / Planner 产品链路；
- ⚠️ **non-concrete schedule segment**（2026-1 真实证据）：
  两种形态都没有 weekday / sections / 具体地点，因此 `meeting = None`
  （⛔ 不生成公共 `Meeting`）：
  - `12-19周校外/实验实践环节`（2 字段 qualified）与
    `1-17周/实验实践环节`（2 字段 plain）：**都没有** teacher 字段，
    qualifier 分别存入 `schedule_qualifier`（plain 为 `None`）；
    ⛔ **不得把 row 级 `teachingName` 注入 `segment.teacher`**
    （row 级信息与 segment 内是否有 teacher 无对应关系）；
  - `1-17周/龙霞/实验实践环节`（3 字段 = `weeks / teacher / activity`）：
    teacher 存入 `ParsedScheduleSegment.teacher`（**脱敏由 collector 负责**），
    `schedule_qualifier = None`；
  - `16-16周校内(户外)/龙霞/实验实践环节`（3 字段 = `weeks<qualifier> / teacher / activity`）：
    qualifier 存入 `schedule_qualifier`（⛔ **不当作 `campus`**），teacher 同上；
    ⚠️ qualifier 是**白名单**（当前 `校外`、`校内(户外)`），新增需真实证据；
  两者的已展开周次都存入 **`ParsedScheduleSegment.schedule_weeks`**
  （⛔ 否则 `meeting is None` 时周次会永久丢失）。
  `extract_meetings()` 不投影它们，但 segment 本身**仍保留**。
  只有这类段的 `CourseOffering` → `meetings == []` → 按 **DG-07** 视为 **schedule UNKNOWN**。
"""

from __future__ import annotations

from app.course_data.captured_pages import (
    CAPTURE_FORMAT,
    CapturedPagesFetcher,
    collect_captured_pages_snapshot,
    load_capture_bundle,
    load_capture_bundle_bytes,
    validate_capture_bundle,
)
from app.course_data.errors import CourseDataNormalizationError
from app.course_data.case_a_scope import (
    CASE_A_CAMPUS_SHARD_IDS,
    CASE_A_DATASET_FORMAT,
    CASE_A_DATASET_VERSION,
    CASE_A_SCOPE_KIND,
    CASE_A_SCOPE_LABEL,
    CASE_A_SCOPE_SEMANTICS,
    CASE_A_TOOL,
    CaseACampusRecord,
    CaseADataset,
    CaseAScope,
    CaseAScopeError,
    CaseAScopedCourseDataProvider,
    build_case_a_dataset,
    case_a_campuses,
    case_a_scope,
    serialize_case_a_dataset,
)
from app.course_data.store_provider import (
    CourseDataAcceptanceError,
    StoreBackedCourseDataProvider,
)
from app.course_data.full_semester_acceptance import (
    APPROVED_FULL_SEMESTER_SHARDS,
    CAPTURE_INVENTORY_FORMAT,
    CAPTURE_INVENTORY_VERSION,
    FULL_SEMESTER_ACCEPTANCE_FORMAT,
    FULL_SEMESTER_ACCEPTANCE_TOOL,
    FULL_SEMESTER_ACCEPTANCE_VERSION,
    CaptureInventory,
    FullSemesterAcceptance,
    FullSemesterAcceptanceError,
    FullSemesterShard,
    FullSemesterShardRecord,
    InventoryShard,
    ShardArtifact,
    accept_full_semester_capture_set,
    build_capture_inventory,
    campus_source_label,
    canonical_inventory_bytes,
    canonical_manifest_bytes,
    capture_inventory_bytes,
    compute_manifest_sha256,
    full_semester_scope,
    full_semester_source,
    load_capture_inventory,
    validate_full_semester_manifest_bytes,
)
from app.course_data.importer import import_opening_courses_response
from app.course_data.normalization import build_course_offering, expand_weeks
from app.course_data.offering_digest import (
    canonical_offering_payload,
    offering_identity,
    offering_payload_sha256,
    offering_set_sha256,
)
from app.course_data.pagination import (
    OpeningCoursesPageFetcher,
    collect_opening_courses_snapshot,
)
from app.course_data.schedule_parser import (
    ParsedScheduleSegment,
    extract_meetings,
    parse_sections,
    parse_teaching_time_place,
    parse_weekday,
)
from app.course_data.sharded_capture import (
    APPROVED_SHARD_IDS,
    SHARDED_CAPTURE_SOURCE,
    ShardedCaptureError,
    ShardedCaptureSet,
    ShardSource,
    collect_sharded_capture_set,
)
from app.course_data.snapshot import (
    OfferingSnapshot,
    SnapshotCourseDataProvider,
    merge_offering_snapshots,
)
from app.course_data.store import (
    ACCEPTANCE_MEMBER_TABLE,
    ACCEPTANCE_TABLE,
    ALLOWED_SCOPE_KINDS,
    SCOPE_KIND_CAMPUS,
    SCOPE_KIND_FULL_SEMESTER,
    AcceptedDataset,
    CourseDataAcceptance,
    CourseDataImport,
    CourseDataProvenance,
    CourseDataStoreError,
    ImmutableAcceptanceConflictError,
    SnapshotScope,
    compute_artifact_sha256,
    compute_manifest_sha256,
    import_offering_snapshot,
    initialize_course_data_store,
    load_accepted_offerings,
    load_course_data_acceptances,
    load_course_data_provenance,
    load_course_offerings,
    load_course_offerings_for_acceptance,
)

__all__ = [
    "ACCEPTANCE_MEMBER_TABLE",
    "ACCEPTANCE_TABLE",
    "ALLOWED_SCOPE_KINDS",
    "APPROVED_FULL_SEMESTER_SHARDS",
    "APPROVED_SHARD_IDS",
    "CAPTURE_FORMAT",
    "CAPTURE_INVENTORY_FORMAT",
    "CAPTURE_INVENTORY_VERSION",
    "CASE_A_CAMPUS_SHARD_IDS",
    "CASE_A_DATASET_FORMAT",
    "CASE_A_DATASET_VERSION",
    "CASE_A_SCOPE_KIND",
    "CASE_A_SCOPE_LABEL",
    "CASE_A_SCOPE_SEMANTICS",
    "CASE_A_TOOL",
    "AcceptedDataset",
    "CaptureInventory",
    "CapturedPagesFetcher",
    "CaseACampusRecord",
    "CaseADataset",
    "CaseAScope",
    "CaseAScopeError",
    "CaseAScopedCourseDataProvider",
    "CourseDataAcceptance",
    "CourseDataAcceptanceError",
    "CourseDataImport",
    "CourseDataNormalizationError",
    "CourseDataProvenance",
    "CourseDataStoreError",
    "FULL_SEMESTER_ACCEPTANCE_FORMAT",
    "FULL_SEMESTER_ACCEPTANCE_TOOL",
    "FULL_SEMESTER_ACCEPTANCE_VERSION",
    "FullSemesterAcceptance",
    "FullSemesterAcceptanceError",
    "FullSemesterShard",
    "FullSemesterShardRecord",
    "ImmutableAcceptanceConflictError",
    "InventoryShard",
    "OfferingSnapshot",
    "OpeningCoursesPageFetcher",
    "ParsedScheduleSegment",
    "SCOPE_KIND_CAMPUS",
    "SCOPE_KIND_FULL_SEMESTER",
    "SHARDED_CAPTURE_SOURCE",
    "ShardArtifact",
    "ShardedCaptureError",
    "ShardedCaptureSet",
    "ShardSource",
    "SnapshotCourseDataProvider",
    "SnapshotScope",
    "StoreBackedCourseDataProvider",
    "accept_full_semester_capture_set",
    "build_capture_inventory",
    "build_course_offering",
    "campus_source_label",
    "canonical_inventory_bytes",
    "canonical_manifest_bytes",
    "canonical_offering_payload",
    "capture_inventory_bytes",
    "collect_captured_pages_snapshot",
    "collect_opening_courses_snapshot",
    "collect_sharded_capture_set",
    "compute_artifact_sha256",
    "compute_manifest_sha256",
    "expand_weeks",
    "extract_meetings",
    "full_semester_scope",
    "full_semester_source",
    "import_offering_snapshot",
    "import_opening_courses_response",
    "initialize_course_data_store",
    "load_accepted_offerings",
    "load_capture_bundle",
    "load_capture_bundle_bytes",
    "load_capture_inventory",
    "load_course_data_acceptances",
    "load_course_data_provenance",
    "load_course_offerings",
    "load_course_offerings_for_acceptance",
    "merge_offering_snapshots",
    "offering_identity",
    "offering_payload_sha256",
    "offering_set_sha256",
    "parse_sections",
    "parse_teaching_time_place",
    "parse_weekday",
    "validate_capture_bundle",
    "validate_full_semester_manifest_bytes",
]
