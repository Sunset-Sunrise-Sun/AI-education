"""Case A 真实规划链路的显式、fail-closed 装配边界（**PR #39 的替代实现**）。

```text
APP_REAL_CASE_A_ENABLED=1
APP_CASE_A_CURRICULUM_CASE_PATH=<real Case A case JSON>
APP_COURSE_DATA_SQLITE_PATH=<local SQLite course data store>
APP_COURSE_DATA_SEMESTER=<semester bound by the approved acceptance>
APP_COURSE_DATA_ACCEPTANCE_SHA256=<approved full-semester manifest SHA-256>
APP_TRUST_ANCHOR_PATH=<由负责人带外提供的批准锚点；缺它即 provenance_not_verified>
        ↓  build_planning_runtime(environment)
CurriculumCaseProvider  +  StoreBackedCourseDataProvider  +  RestrictedPlannerProvider
        ↓
PlanningOrchestrator（或 None ⇒ API 503 `real_pipeline_not_configured`）
```

## 与 PR #39 的关系（⛔ 不合并 #39）

PR #39（`feature/case-a-runtime-wiring`）的 Course Data 侧装载模型是
**"一个 Capture Bundle + 一个 bytes digest + 一个内存快照"**。真实数据已经变成

```text
五个校区 artifact → full-semester acceptance（manifest SHA-256）→ SQLite
```

而单份 campus bundle **不能**证明 whole-semester 完整性
（`campus complete != full semester complete`）。因此本模块把 Course Data 侧换成
**SQLite + 显式 full_semester acceptance**：

```text
PR #39 as-is  = FROZEN / DO NOT MERGE（其装载模型已被本模块取代）
本模块        = PR #39 的 successor（Curriculum / Planner 侧保持同一套受控校验）
```

⛔ **没有 campus fallback**：本模块只认上面五个变量；
PR #39 的单 bundle 装载模型（一个 artifact 路径 + 一个 bytes digest）已**冻结停用**，
本模块⛔ 不读取它的任何变量名，也⛔ 不接受任何 campus-scope 数据；
⛔ **没有 Mock fallback**：任何一步失败 ⇒ runtime 不可用 ⇒ API 503。

## fail closed 与诊断码

`build_planning_runtime()` 只在**全部**条件满足时返回 orchestrator，否则返回
`PlanningRuntimeInspection(orchestrator=None, reason=<code>)`。诊断码**不含路径、
不含配置取值、不含任何输入内容**：

```text
runtime_disabled               未启用（缺省即关闭）
invalid_runtime_configuration  开关值非 0/1，或 semester / digest 形态非法
curriculum_not_ready           case 缺失 / 非法 / 未标记 real / 不是 Case A
                               / scope 决策未获批准 / projection 失败
course_data_not_ready          SQLite 缺失 / 不是 Course Data 库 / 无匹配的
                               full_semester acceptance / 计数不符 / 行被覆盖
ready                          production runtime 可用
```

⛔ 每次 `get_planning_orchestrator()` 都会**重新**装配（不缓存 orchestrator）：
acceptance 绑定、行数与 case 就绪状态都在**每个请求**上重新验证，
因此启动之后被改写 / 被覆盖的库不会继续被使用。

## 异常边界（硬：⛔ 不得吞掉程序缺陷）

只有**显式领域失败**可以被翻译成"未装配"，其它一切异常必须**原样冒出**：

```text
→ 503 real_pipeline_not_configured（就绪性 / 配置失败）
    _RuntimeSourceUnavailable              curriculum source 不满足受控条件
    _RuntimeConfigurationInvalid           配置值形态非法
    CurriculumNormalizationError           case 缺失 / 不可读 / 非法 / 未批准
                                           （loader 自己已把 OSError / ValueError /
                                            RuntimeError 规范化成这一个领域异常）
    CourseDataStoreError                   store 领域失败基类
      ├── CourseDataAcceptanceError        acceptance 缺失 / 失效 / 不匹配
      └── ImmutableAcceptanceConflictError 同 SHA 的语义冲突（导入期）

→ 500（未预期内部 / 程序错误：⛔ 不捕获、⛔ 不翻译）
    ValueError    RuntimeError（非上述显式类型）    KeyError
    AttributeError    TypeError    OSError（未经 loader 规范化）
    以及其它任何异常
```

⛔ **不得**捕获 `Exception` / `ValueError` / `RuntimeError` / `OSError` 这类泛型异常：
一个无关的 `ValueError` 若被这里吞掉，程序缺陷就会伪装成"未配置"（503），
掩盖真实故障。请求期间的 `CourseDataAcceptanceError` 仍由 `app/main.py` 的显式
异常处理器映射成同一个 503（⛔ 其它异常不在那里被捕获）。

## 边界（硬）

- ⛔ **不改** `CourseDataProvider` / `CurriculumProvider` / `PlannerProvider` 三个
  Protocol（`docs/interfaces/integration.md` 已冻结）与 `PlanningOrchestrator`；
- ⛔ 不实现业务算法、⛔ 不扫描文件系统猜输入、⛔ 不读 `mock_data`、⛔ 不联网；
- ⛔ 本模块不打印任何配置取值 / 路径（诊断只走 reason code）。
"""

from __future__ import annotations

import os
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from app.course_data import CourseDataStoreError, StoreBackedCourseDataProvider
from app.curriculum import (
    CurriculumCaseProvider,
    CurriculumNormalizationError,
    load_curriculum_case,
)
from app.curriculum.case_a_decisions import (
    AS_OF_TERM,
    CASE_TARGET_VERSION_ID,
    confirmed_scope_decisions,
)
from app.integration import PlanningOrchestrator
from app.planner import RestrictedPlannerProvider
from app.models.contracts import DataSource
from app.provenance import (
    APPROVAL_KIND_COURSE_DATA_MANIFEST,
    APPROVAL_KIND_CURRICULUM_CASE,
    ProvenanceDenied,
    ProvenanceReason,
    TrustAnchor,
    TrustAnchorUnavailable,
    load_trust_anchor,
    sha256_file,
    verify_approval,
)

__all__ = [
    "PlanningRuntimeInspection",
    "PlanningRuntimeNotConfigured",
    "build_course_data_provider",
    "build_curriculum_provider",
    "build_planner_provider",
    "build_planning_runtime",
    "get_planning_orchestrator",
    "inspect_planning_runtime",
]

#: 总开关：缺省（未设置）即**关闭**。
_ENABLED = "APP_REAL_CASE_A_ENABLED"

#: 真实 Case A manifest 的本地路径。
_CURRICULUM_CASE_PATH = "APP_CASE_A_CURRICULUM_CASE_PATH"

#: 本地 Course Data SQLite 路径。
_COURSE_DATA_SQLITE_PATH = "APP_COURSE_DATA_SQLITE_PATH"

#: 该 acceptance 绑定的学期（必须与 approval 指向的 acceptance 一致）。
_COURSE_DATA_SEMESTER = "APP_COURSE_DATA_SEMESTER"

#: **正式** full-semester acceptance 的 manifest SHA-256。
_COURSE_DATA_ACCEPTANCE_SHA256 = "APP_COURSE_DATA_ACCEPTANCE_SHA256"

#: 带外批准锚点文件的本地路径（⚠️ 本轮新增，F-01/F-02/F-03）。
#:
#: 缺省 / 不可读 / 版本不符 / 结构非法 / 自签 ⇒ `provenance_not_verified`。
#: 规范定义在 `app.provenance.TRUST_ANCHOR_ENV`，这里保留同名常量，
#: 使"runtime 读取哪些环境变量"在本模块内是**自解释**的（与运维手册交叉核对）。
_TRUST_ANCHOR_PATH = "APP_TRUST_ANCHOR_PATH"

_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


class PlanningRuntimeNotConfigured(RuntimeError):
    """真实 Curriculum / Course Data / Planner 尚未完成装配。"""


class _RuntimeSourceUnavailable(RuntimeError):
    """一个显式配置的 runtime source 尚不能安全进入 production 链路。"""


class _RuntimeConfigurationInvalid(RuntimeError):
    """Runtime 配置值存在格式错误。"""


@dataclass(frozen=True, slots=True)
class PlanningRuntimeInspection:
    """Runtime factory 的最小诊断结果；⛔ 不含路径或输入内容。"""

    orchestrator: PlanningOrchestrator | None
    reason: str

    @property
    def ready(self) -> bool:
        """production runtime 是否可用。"""

        return self.orchestrator is not None


def build_curriculum_provider(
    case_path: str,
    *,
    anchor: TrustAnchor | None = None,
) -> CurriculumCaseProvider:
    """从调用方**显式指定**的 Case A manifest 构造真实 Curriculum Provider。

    受控条件：

    ```text
    case.data_source                == real          （⚠️ 仅自述，不再单独采信）
    case.new.version_id             == CASE_TARGET_VERSION_ID
    case.makeup_scope.as_of_term    == AS_OF_TERM
    case.confirmed_scope_decisions  == 已批准的决策集合
    ★ case 文件摘要必须出现在**带外批准锚点**的 curriculum_case 记录里（本轮新增）
    provider.get_makeup_tasks()     构造期即可成功（⛔ 不推迟到请求中才发现未就绪）
    ```

    ⚠️ **本轮的修复（F-02）**：`case.data_source == real` 与"来源真实"无关——
    它只是 case JSON 里的一个自述字段，而唯一的旧守卫是 `"mock://"` 子串扫描。
    因此这里新增**摘要 + 身份**批准门：`case_path` 的**文件字节** SHA-256
    必须与锚点里 `curriculum_case` 记录的 `artifact_sha256` 一致，
    且记录的身份（`target_version_id` / `as_of_term`）与 case 内容一致。
    ⛔ `anchor` 为 `None` ⇒ 抛 `_RuntimeSourceUnavailable`（fail closed），
    ⛔ 不会退回"只看 data_source"的旧行为。
    """

    case = load_curriculum_case(case_path)

    if case.data_source is not DataSource.REAL:
        raise _RuntimeSourceUnavailable("curriculum case is not marked real")
    if case.new.version_id != CASE_TARGET_VERSION_ID:
        raise _RuntimeSourceUnavailable("curriculum case is not Case A")
    if case.makeup_scope is None or case.makeup_scope.as_of_term != AS_OF_TERM:
        raise _RuntimeSourceUnavailable("curriculum case has the wrong scope cut-off")
    if case.confirmed_scope_decisions != confirmed_scope_decisions():
        raise _RuntimeSourceUnavailable("curriculum case decisions are not approved")

    # ---- 独立批准门（F-02）------------------------------------------------
    if anchor is None:
        raise _RuntimeSourceUnavailable("curriculum case has no approved provenance anchor")
    # `sha256_file` 已经把 OSError 规范化成 TrustAnchorUnavailable（显式领域异常），
    # 因此本模块⛔ 不需要捕获 OSError。
    case_digest = sha256_file(case_path, reason=ProvenanceReason.ANCHOR_UNREADABLE)
    decision = verify_approval(
        kind=APPROVAL_KIND_CURRICULUM_CASE,
        identity={
            "target_version_id": case.new.version_id,
            "as_of_term": case.makeup_scope.as_of_term,
        },
        artifact_sha256=case_digest,
        anchor=anchor,
    )
    if not decision.verified:
        raise _RuntimeSourceUnavailable(
            f"curriculum case provenance is not approved ({decision.reason})"
        )

    provider = CurriculumCaseProvider(case)
    # 构造期即验证 projection；⛔ 不等到请求中再发现 case 未就绪。
    provider.get_makeup_tasks()
    return provider


def build_course_data_provider(
    sqlite_path: str,
    *,
    semester: str,
    approved_acceptance_sha256: str,
    approved_manifest_sha256: Collection[str] = (),
) -> StoreBackedCourseDataProvider:
    """从**已正式验收**的 full_semester SQLite 记录构造 Course Data Provider。

    `approved_manifest_sha256` 必须来自**带外批准锚点**
    （`app.provenance`，`APP_TRUST_ANCHOR_PATH`）。
    ⛔ 缺省空集合 ⇒ 构造期即拒绝：本地库自报的 `real` 不构成"已核验真实来源"。

    ⛔ 这里**没有** campus / 单 bundle / "库里有一些行"的退化路径：
    绑定、全部计数校验与摘要批准门都由 `StoreBackedCourseDataProvider`
    在构造期 fail closed 完成，并在**每次读取**时重跑。
    """

    return StoreBackedCourseDataProvider(
        sqlite_path=sqlite_path,
        semester=semester,
        acceptance_sha256=approved_acceptance_sha256,
        approved_manifest_sha256=tuple(approved_manifest_sha256),
    )


def build_planner_provider() -> RestrictedPlannerProvider:
    """实例化当前已审核的 deterministic restricted Planner。"""

    return RestrictedPlannerProvider()


def _required(environment: Mapping[str, str], name: str) -> str | None:
    """读取必填配置；缺失 / 纯空白 ⇒ None（⛔ 不猜默认值）。"""

    value = environment.get(name)
    if value is None or not value.strip():
        return None
    return value


def _normalize_sha256(value: str) -> str:
    normalized = value.strip()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        raise _RuntimeConfigurationInvalid(
            "approved full-semester acceptance SHA-256 must be exactly 64 hex characters"
        )
    return normalized.lower()


def build_planning_runtime(
    environment: Mapping[str, str],
) -> PlanningRuntimeInspection:
    """按**显式**环境配置构造 production runtime，并以诊断码 fail closed。"""

    enabled = environment.get(_ENABLED)
    if enabled is None or enabled == "0":
        return PlanningRuntimeInspection(None, "runtime_disabled")
    if enabled != "1":
        return PlanningRuntimeInspection(None, "invalid_runtime_configuration")

    # ---- 独立批准锚点（本轮新增，F-01/F-02/F-03）--------------------------
    # ⚠️ 这是**先决条件**：读不到锚点 ⇒ 无法证明任何来源已被批准 ⇒
    # 直接判 `provenance_not_verified`，⛔ 不继续往下装配。
    # ⛔ 不缓存：每次装配重新读文件，避免"启动时通过、之后被换掉"。
    try:
        anchor = load_trust_anchor(environment)
    except TrustAnchorUnavailable:
        # ⛔ 只捕这一个显式领域异常：锚点缺失 / 不可读 / 版本不符 / 结构非法 /
        #    自签，全部归为"来源未经独立核验"。
        #    ⛔ 不捕泛型异常——锚点装载里的程序缺陷必须冒到 API 层。
        return PlanningRuntimeInspection(None, "provenance_not_verified")

    case_path = _required(environment, _CURRICULUM_CASE_PATH)
    if case_path is None:
        return PlanningRuntimeInspection(None, "curriculum_not_ready")

    sqlite_path = _required(environment, _COURSE_DATA_SQLITE_PATH)
    semester = _required(environment, _COURSE_DATA_SEMESTER)
    approved_sha256 = _required(environment, _COURSE_DATA_ACCEPTANCE_SHA256)
    if sqlite_path is None or semester is None or approved_sha256 is None:
        return PlanningRuntimeInspection(None, "course_data_not_ready")

    try:
        normalized_digest = _normalize_sha256(approved_sha256)
    except _RuntimeConfigurationInvalid:
        return PlanningRuntimeInspection(None, "invalid_runtime_configuration")

    try:
        curriculum = build_curriculum_provider(case_path.strip(), anchor=anchor)
    except (
        # ⛔ 只捕获**显式领域失败**：case loader / normalizer 已经把
        #    OSError / ValueError / RuntimeError 规范化成 CurriculumNormalizationError；
        #    `sha256_file` 也把 OSError 规范化成 TrustAnchorUnavailable。
        #    因此这里再捕泛型异常只会吞掉程序缺陷。
        CurriculumNormalizationError,
        TrustAnchorUnavailable,
        _RuntimeSourceUnavailable,
    ):
        return PlanningRuntimeInspection(None, "curriculum_not_ready")

    # 课程数据侧的批准摘要：只取锚点里与该学期 + acceptance 身份匹配的记录。
    approved_manifests = tuple(
        item.artifact_sha256
        for item in anchor.matching(APPROVAL_KIND_COURSE_DATA_MANIFEST)
        if item.identity_map() == {
            "semester": semester.strip(),
            "acceptance_sha256": normalized_digest,
        }
    )
    if not approved_manifests:
        return PlanningRuntimeInspection(None, "provenance_not_verified")

    try:
        course_data = build_course_data_provider(
            sqlite_path.strip(),
            semester=semester.strip(),
            approved_acceptance_sha256=normalized_digest,
            approved_manifest_sha256=approved_manifests,
        )
    except CourseDataStoreError:
        # ⛔ store 领域失败基类（含 CourseDataAcceptanceError /
        #    ImmutableAcceptanceConflictError）。⛔ 不捕 ValueError / OSError：
        #    无关的构造期 ValueError 必须冒到 API 层变成 500。
        return PlanningRuntimeInspection(None, "course_data_not_ready")

    return PlanningRuntimeInspection(
        PlanningOrchestrator(
            curriculum=curriculum,
            course_data=course_data,
            planner=build_planner_provider(),
        ),
        "ready",
    )


def inspect_planning_runtime() -> PlanningRuntimeInspection:
    """检查**当前进程环境**中的 production runtime（⛔ 不打印任何配置取值）。"""

    return build_planning_runtime(os.environ)


def get_planning_orchestrator() -> PlanningOrchestrator | None:
    """FastAPI dependency：可用时返回 production orchestrator，否则返回 ``None``。

    ⛔ 返回 ``None`` 时 API 会明确 503（`real_pipeline_not_configured`），
    ⛔ **不会**回退到 Mock，也⛔ 不会退回单 campus 数据。

    ⚠️ 每次调用都重新装配：acceptance 绑定与 case 就绪状态在**每个请求**上重新验证。
    """

    return inspect_planning_runtime().orchestrator
