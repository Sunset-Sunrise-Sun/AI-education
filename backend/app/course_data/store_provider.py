"""SQLite 支撑的 production `CourseDataProvider`（Course Data **内部**实现，**零网络**）。

```text
SQLite（只接受**已正式验收**的 full_semester 记录）
        ↓  构造时 fail closed 校验（acceptance identity + scope + 计数）
StoreBackedCourseDataProvider
        ↓  get_course_offerings(semester)
list[CourseOffering]   →  Integration / PlanningOrchestrator
```

## 为什么需要它

`SnapshotCourseDataProvider`（`snapshot.py`）持有的是**一份内存快照**；
真实链路的数据落在 SQLite 里（五 shard merge → full_semester acceptance → import）。
本模块把"**哪一批行算数**"从"整个学期的所有行"收紧到
"**被某一次 full_semester acceptance 绑定的那批行**"。

## 构造时必须成立（任一不满足 ⇒ `CourseDataAcceptanceError`，fail closed）

```text
恰好一条 provenance 记录匹配 (semester, scope_kind=full_semester, scope_id=semester, sha)
  completeness   == "complete"
  loaded_count   == reported_total == offering_count > 0
  实际绑定行数    == provenance.offering_count        （⛔ 不采信自报数字）
```

⛔ **不 fallback**：没有记录、SHA 不对、scope 不对、campus-only 库、空表、
零行、被篡改的库一律**构造失败**；⛔ 不"有行就先用"。

## `get_course_offerings(semester)`

- `semester` 必须**精确等于**构造时绑定的 semester，否则 **fail closed**
  （⛔ 不返回空列表、⛔ 不 fallback 到别的学期）；
- 每次调用都**重新按 acceptance 绑定读回**并复核行数：如果构造之后有别的
  import 覆盖了其中某些行的 provenance（或库被外部修改），行数不再相等 ⇒
  **fail closed**，⛔ 不会静默返回"少了几行"的数据；
- 返回顺序确定（`ORDER BY course_id, class_id`）；
- ⛔ 只读；⛔ 不联网、⛔ 不读认证材料、⛔ 不写库。

## 边界（硬）

- ⛔ **不改** `CourseDataProvider` Protocol（`docs/interfaces/integration.md` 已冻结）：
  本类只是**结构上满足**它；
- ⛔ **不改** `CourseOffering` 公共 Schema、⛔ 不新增公共字段；
- ⛔ 不 import Integration / API / Planner；
- ⛔ 不需要新增表：行级 provenance 列（`artifact_sha256` / `scope_kind` / `scope_id`）
  已经足以绑定 acceptance（见 `load_course_offerings_for_acceptance()`）。
"""

from __future__ import annotations

from pathlib import Path

from app.course_data.store import (
    SCOPE_KIND_FULL_SEMESTER,
    CourseDataProvenance,
    CourseDataStoreError,
    _require_sha256,
    _require_semester,
    load_course_data_provenance,
    load_course_offerings_for_acceptance,
)
from app.models.contracts import CourseOffering

__all__ = [
    "CourseDataAcceptanceError",
    "StoreBackedCourseDataProvider",
]


class CourseDataAcceptanceError(CourseDataStoreError):
    """本地库与所配置的 full_semester acceptance **不完全对应**（fail closed）。"""


def _require_acceptance_record(
    path: str | Path,
    *,
    semester: str,
    acceptance_sha256: str,
) -> CourseDataProvenance:
    """找出**恰好一条**匹配的 provenance 记录，并逐项核对计数。"""

    records = [
        record
        for record in load_course_data_provenance(path, semester=semester)
        # ⚠️ 三个条件各自都是必需的（少一个都会被对应用例打红）；筛选本身不 fallback。
        if record.artifact_sha256 == acceptance_sha256
        and record.scope_kind == SCOPE_KIND_FULL_SEMESTER
        and record.scope_id == semester
    ]

    if not records:
        # ⚠️ 与下面的 `len(records) != 1` 对"零条"互为冗余（纵深防御）。
        raise CourseDataAcceptanceError(
            f"本地库中没有匹配的 full_semester acceptance 记录"
            f"（semester={semester!r}）；"
            f"⛔ 拒绝退化为『该学期任意行』或 campus-only 数据"
        )

    if len(records) != 1:
        # 主键 (artifact_sha256, semester, scope_kind, scope_id) 保证匹配记录至多一条，
        # 因此本句只在"调用方传入被篡改的库"这种异常形态下才有额外意义。
        raise CourseDataAcceptanceError(
            f"匹配的 acceptance 记录有 {len(records)} 条（期望恰好 1 条）；拒绝继续"
        )

    record = records[0]

    if record.completeness != "complete":
        raise CourseDataAcceptanceError(
            f"acceptance 记录不是 complete（completeness={record.completeness!r}）；"
            f"⛔ partial 数据不得进入 production Provider"
        )

    if record.reported_total is None or record.loaded_count != record.reported_total:
        raise CourseDataAcceptanceError(
            f"acceptance 记录的 loaded_count({record.loaded_count}) != "
            f"reported_total({record.reported_total})；计数不自洽，拒绝继续"
        )

    if record.loaded_count != record.offering_count:
        # ⚠️ 构造时还会**重新数一遍实际绑定的行**并与 offering_count 比对，
        #    因此本句在正常形态下与那次对账互为冗余（纵深防御）。
        raise CourseDataAcceptanceError(
            f"acceptance 记录的 loaded_count({record.loaded_count}) != "
            f"offering_count({record.offering_count})；计数不自洽，拒绝继续"
        )

    if record.offering_count <= 0:
        # ⚠️ 同上：非正数的 offering_count 也会被行数对账拦下（冗余但保留，
        #    以便在**尚未读行**时就能给出明确错误）。
        raise CourseDataAcceptanceError(
            f"acceptance 记录的 offering_count({record.offering_count}) 必须 > 0；"
            f"⛔ 空 acceptance 不得装配 production Provider"
        )

    return record


class StoreBackedCourseDataProvider:
    """只读、fail-closed 的 SQLite `CourseDataProvider` 实现（**内部**）。

    构造即绑定：

    ```text
    sqlite path + semester + approved full-semester acceptance SHA-256
    ```

    并在构造时完成全部校验（⛔ 失败的 Provider 不会被交出去）。
    结构上满足冻结的 `CourseDataProvider`，但**不继承、不修改**该 Protocol。
    """

    def __init__(
        self,
        *,
        sqlite_path: str | Path,
        semester: str,
        acceptance_sha256: str,
    ) -> None:
        resolved_semester = _require_semester(semester)
        resolved_sha256 = _require_sha256(acceptance_sha256)

        if not isinstance(sqlite_path, (str, Path)):
            raise CourseDataAcceptanceError(
                f"sqlite_path 必须是 str 或 Path，实际是 {type(sqlite_path).__name__}"
            )

        record = _require_acceptance_record(
            sqlite_path,
            semester=resolved_semester,
            acceptance_sha256=resolved_sha256,
        )

        # ⛔ 重新数一遍**实际绑定的行**，不采信 provenance 自报的 offering_count。
        bound_offerings = load_course_offerings_for_acceptance(
            sqlite_path,
            semester=resolved_semester,
            acceptance_sha256=resolved_sha256,
        )

        if len(bound_offerings) != record.offering_count:
            raise CourseDataAcceptanceError(
                f"绑定到该 acceptance 的实际行数({len(bound_offerings)}) != "
                f"provenance.offering_count({record.offering_count})；"
                f"本地库可能被外部修改，或该批行已被后来的 import 覆盖；拒绝装配"
            )

        self._sqlite_path = sqlite_path
        self._semester = resolved_semester
        self._acceptance_sha256 = resolved_sha256
        self._provenance = record
        self._expected_offering_count = record.offering_count

    @property
    def semester(self) -> str:
        """构造时绑定的学期（唯一允许请求的 semester）。"""

        return self._semester

    @property
    def acceptance_sha256(self) -> str:
        """构造时绑定的 full-semester acceptance identity。"""

        return self._acceptance_sha256

    @property
    def provenance(self) -> CourseDataProvenance:
        """匹配到的 provenance 记录（⛔ 只含计数与 scope，不含任何教学班取值）。"""

        return self._provenance

    @property
    def expected_offering_count(self) -> int:
        """该 acceptance 绑定的行数（构造时已核对）。"""

        return self._expected_offering_count

    def get_course_offerings(self, semester: str) -> list[CourseOffering]:
        """返回**该 acceptance 绑定**的教学班列表。

        学期不匹配 ⇒ `CourseDataAcceptanceError`（fail closed）：
        ⛔ **不**返回空列表、⛔ **不** fallback 到其它学期或 Mock。
        """

        if not isinstance(semester, str) or semester != self._semester:
            raise CourseDataAcceptanceError(
                f"该 Provider 只绑定 semester={self._semester!r}；"
                f"⛔ 拒绝其它学期的请求（不返回空列表、不 fallback）"
            )

        offerings = load_course_offerings_for_acceptance(
            self._sqlite_path,
            semester=self._semester,
            acceptance_sha256=self._acceptance_sha256,
        )

        if len(offerings) != self._expected_offering_count:
            raise CourseDataAcceptanceError(
                f"该 acceptance 绑定的行数发生变化"
                f"（期望 {self._expected_offering_count}，实际 {len(offerings)}）；"
                f"本地库可能被外部修改或该批行被覆盖；拒绝返回部分数据"
            )

        return offerings
