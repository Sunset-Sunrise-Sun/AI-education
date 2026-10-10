"""SQLite 支撑的 production `CourseDataProvider`（Course Data **内部**实现，**零网络**）。

```text
SQLite（只接受**已正式验收**的 full_semester content-bound acceptance）
        ↓  每次读取都在一个一致读事务里重新校验
StoreBackedCourseDataProvider
        ↓  get_course_offerings(semester)
list[CourseOffering]   →  Integration / PlanningOrchestrator
```

## 为什么需要它

`SnapshotCourseDataProvider`（`snapshot.py`）持有的是**一份内存快照**；
真实链路的数据落在 SQLite 里（五 shard merge → full_semester acceptance → import）。
本模块把"**哪一批行算数**"从"整个学期的所有行"收紧到
"**被某一次 full_semester acceptance 绑定、且内容仍然一致的那批行**"。

## 持续验证（Forward Red-Team BLOCK B4）⛔ 不得退回"构造时校验一次"

```text
每一次 get_course_offerings(semester)
        ↓  同一个一致读事务（store.load_accepted_offerings）
acceptance 元数据仍然存在且精确匹配（semester / scope / digest）
两个平面（course_data_import / course_data_acceptance）一致
completeness == complete；loaded_count == reported_total == offering_count > 0
membership 数量与 identity 集合 == 实际读到的行
逐行 offering_payload_sha256 == membership 记录
重算的整批 offering_set_sha256 == 元数据
每行的行级 provenance 仍指向本 acceptance
        ↓  全部通过才返回 rows
```

- ⛔ **不缓存** metadata、⛔ **不缓存** rows：acceptance 被删除 / 改写、
  membership 被篡改、某一行内容被替换、出现陈旧 campus 行、
  同一批行被别的 acceptance 覆盖 —— 下一次读取都会 **fail closed**；
- ⛔ 不 fallback：没有记录、scope 不对、campus-only 库、零行、计数不符一律失败；
- 构造期也调用**同一条**校验路径（fail fast），但**不把结果当作此后读取的依据**。

## `get_course_offerings(semester)`

- `semester` 必须**精确等于**构造时绑定的学期，否则 **fail closed**
  （⛔ 不返回空列表、⛔ 不 fallback 到别的学期，也⛔ 不交给 Planner 当成"空供给"）；
- 返回顺序确定（`ORDER BY course_id, class_id`）；
- ⛔ 只读；⛔ 不联网、⛔ 不读认证材料、⛔ 不写库、⛔ 不建表。

## 边界（硬）

- ⛔ **不改** `CourseDataProvider` Protocol（`docs/interfaces/integration.md` 已冻结）：
  本类只是**结构上满足**它（签名仍是 `get_course_offerings(self, semester)`）；
- ⛔ **不改** `CourseOffering` 公共 Schema、⛔ 不新增公共字段；
- ⛔ 不 import Integration / API / Planner；
- ⛔ 不复用 PR #39 的单 bundle 装载模型（一个 artifact + 一个 bytes digest + 内存快照）。

## 与 runtime 的错误映射

`CourseDataAcceptanceError` 是**就绪性失败**（readiness failure）：
`app/main.py` 把它显式映射为 `503 real_pipeline_not_configured`
（⛔ 不是 500、⛔ 不是 Mock fallback）；其它未预期异常仍然保持 500。
"""

from __future__ import annotations

from pathlib import Path

from app.course_data.store import (
    ARTIFACT_SHA256_PATTERN,
    AcceptedDataset,
    CourseDataProvenance,
    CourseDataStoreError,
    _require_sha256,
    _require_semester,
    load_accepted_offerings,
)
from app.models.contracts import CourseOffering

__all__ = [
    "CourseDataAcceptanceError",
    "StoreBackedCourseDataProvider",
]


class CourseDataAcceptanceError(CourseDataStoreError):
    """本地库与所配置的 full_semester acceptance **不完全对应**（fail closed）。

    ⚠️ 这是**就绪性失败**：runtime 必须把它映射为
    `503 real_pipeline_not_configured`，⛔ 不得当成 500，也⛔ 不得 fallback。
    """


def _as_provenance(dataset: AcceptedDataset) -> CourseDataProvenance:
    """把 content-bound acceptance 元数据投影成历史 provenance 形状（只读展示）。"""

    acceptance = dataset.acceptance

    return CourseDataProvenance(
        artifact_sha256=acceptance.artifact_sha256,
        semester=acceptance.semester,
        scope_kind=acceptance.scope_kind,
        scope_id=acceptance.scope_id,
        source=acceptance.source,
        imported_at=acceptance.imported_at,
        completeness=acceptance.completeness,
        loaded_count=acceptance.loaded_count,
        reported_total=acceptance.reported_total,
        offering_count=acceptance.offering_count,
    )


class StoreBackedCourseDataProvider:
    """只读、**每次读取都重新验证**的 SQLite `CourseDataProvider` 实现（**内部**）。

    构造即绑定：

    ```text
    sqlite path + semester + approved full-semester acceptance SHA-256
    ```

    结构上满足冻结的 `CourseDataProvider`，但**不继承、不修改**该 Protocol。
    """

    def __init__(
        self,
        *,
        sqlite_path: str | Path,
        semester: str,
        acceptance_sha256: str,
        approved_manifest_sha256: tuple[str, ...] = (),
        require_approval: bool = True,
    ) -> None:
        resolved_semester = _require_semester(semester)
        resolved_sha256 = _require_sha256(acceptance_sha256)

        if not isinstance(sqlite_path, (str, Path)):
            raise CourseDataAcceptanceError(
                f"sqlite_path 必须是 str 或 Path，实际是 {type(sqlite_path).__name__}"
            )

        # ⚠️ 来源门：调用方必须给出**带外批准锚点**里记录的 manifest 摘要。
        # 没有它 ⇒ 构造期即 fail closed（⛔ 不允许"没有批准也能读"）。
        # `require_approval=False` 仅限**产出工具在批准之前**的自洽回读，
        # ⛔ production 构造路径保持默认 True。
        approved: tuple[str, ...] = ()
        for item in approved_manifest_sha256:
            if not ARTIFACT_SHA256_PATTERN.match(str(item).strip().lower()):
                raise CourseDataAcceptanceError(
                    "approved_manifest_sha256 里必须是 64 位小写十六进制摘要"
                )
            approved += (str(item).strip().lower(),)
        if require_approval and not approved:
            raise CourseDataAcceptanceError(
                "没有独立批准锚点记录的 manifest 摘要：⛔ 拒绝把本地库当作已核验真实来源"
            )

        self._sqlite_path = sqlite_path
        self._semester = resolved_semester
        self._acceptance_sha256 = resolved_sha256
        self._approved_manifest_sha256 = frozenset(approved)
        self._require_approval = bool(require_approval)

        # 构造期 fail fast：走**同一条**验证路径（⛔ 结果不作为此后读取的依据）。
        dataset = self._read_accepted_dataset()
        self._expected_offering_count = dataset.acceptance.offering_count
        self._acceptance_projection = _as_provenance(dataset)

    def _read_accepted_dataset(self) -> AcceptedDataset:
        """在一次一致读事务里完整校验并物化该 acceptance（⛔ 不缓存）。"""

        try:
            return load_accepted_offerings(
                self._sqlite_path,
                semester=self._semester,
                acceptance_sha256=self._acceptance_sha256,
                approved_manifest_sha256=self._approved_manifest_sha256,
                require_approval=self._require_approval,
            )
        except CourseDataStoreError as exc:
            # 统一成 readiness 语义（⛔ 不泄漏库内取值 / 路径）。
            raise CourseDataAcceptanceError(
                "本地库与所配置的 full_semester acceptance 不一致或已失效"
                f"（semester={self._semester!r}）；拒绝提供数据"
            ) from exc

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
        """构造时的 acceptance 元数据投影（⛔ 只读展示，⛔ 不代表当前仍然有效）。"""

        return self._acceptance_projection

    @property
    def expected_offering_count(self) -> int:
        """构造时该 acceptance 绑定的行数（⚠️ 每次读取仍会重新核对）。"""

        return self._expected_offering_count

    def get_course_offerings(self, semester: str) -> list[CourseOffering]:
        """返回**该 acceptance 绑定且内容仍然一致**的教学班列表。

        ⛔ 学期不匹配 ⇒ `CourseDataAcceptanceError`（fail closed）；
        ⛔ 每次调用都重新做完整校验（B4）：acceptance 记录 / membership /
        逐行内容指纹 / 整批 digest 任一变化都会失败。
        """

        if not isinstance(semester, str) or semester != self._semester:
            raise CourseDataAcceptanceError(
                f"该 Provider 只绑定 semester={self._semester!r}；"
                f"⛔ 拒绝其它学期的请求（不返回空列表、不 fallback）"
            )

        dataset = self._read_accepted_dataset()

        if dataset.acceptance.offering_count != self._expected_offering_count:
            # 防御性：acceptance 元数据在构造之后被改写。
            raise CourseDataAcceptanceError(
                "该 acceptance 记录在构造之后发生变化；拒绝返回数据"
            )

        return list(dataset.offerings)
