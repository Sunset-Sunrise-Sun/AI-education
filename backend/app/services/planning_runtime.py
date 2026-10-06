"""Case A 真实规划链路的显式、fail-closed 装配边界（**PR #39 的替代实现**）。

```text
APP_REAL_CASE_A_ENABLED=1
APP_CASE_A_CURRICULUM_CASE_PATH=<real Case A case JSON>
APP_COURSE_DATA_SQLITE_PATH=<local SQLite course data store>
APP_COURSE_DATA_SEMESTER=<semester bound by the approved acceptance>
APP_COURSE_DATA_ACCEPTANCE_SHA256=<approved full-semester manifest SHA-256>
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
from collections.abc import Mapping
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
    is_supported_scope_decision_set,
)
from app.integration import PlanningOrchestrator
from app.planner import RestrictedPlannerProvider
from app.models.contracts import DataSource

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


def build_curriculum_provider(case_path: str) -> CurriculumCaseProvider:
    """从调用方**显式指定**的 Case A manifest 构造真实 Curriculum Provider。

    受控条件（与 PR #39 相同的一套 Curriculum 侧校验）：

    ```text
    case.data_source                == real
    case.new.version_id             == CASE_TARGET_VERSION_ID
    case.makeup_scope.as_of_term    == AS_OF_TERM
    case.confirmed_scope_decisions  == 已批准的决策集合
    provider.get_makeup_tasks()     构造期即可成功（⛔ 不推迟到请求中才发现未就绪）
    ```
    """

    case = load_curriculum_case(case_path)

    if case.data_source is not DataSource.REAL:
        raise _RuntimeSourceUnavailable("curriculum case is not marked real")
    if case.new.version_id != CASE_TARGET_VERSION_ID:
        raise _RuntimeSourceUnavailable("curriculum case is not Case A")
    if case.makeup_scope is None or case.makeup_scope.as_of_term != AS_OF_TERM:
        raise _RuntimeSourceUnavailable("curriculum case has the wrong scope cut-off")
    if not is_supported_scope_decision_set(case.confirmed_scope_decisions):
        raise _RuntimeSourceUnavailable("curriculum case decisions are not approved")

    provider = CurriculumCaseProvider(case)
    # 构造期即验证 projection；⛔ 不等到请求中再发现 case 未就绪。
    provider.get_makeup_tasks()
    return provider


def build_course_data_provider(
    sqlite_path: str,
    *,
    semester: str,
    approved_acceptance_sha256: str,
) -> StoreBackedCourseDataProvider:
    """从**已正式验收**的 full_semester SQLite 记录构造 Course Data Provider。

    ⛔ 这里**没有** campus / 单 bundle / "库里有一些行"的退化路径：
    绑定与全部计数校验都由 `StoreBackedCourseDataProvider` 在构造期 fail closed 完成。
    """

    return StoreBackedCourseDataProvider(
        sqlite_path=sqlite_path,
        semester=semester,
        acceptance_sha256=approved_acceptance_sha256,
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
        curriculum = build_curriculum_provider(case_path.strip())
    except (
        # ⛔ 只捕获**显式领域失败**：case loader / normalizer 已经把
        #    OSError / ValueError / RuntimeError 规范化成 CurriculumNormalizationError；
        #    因此这里再捕泛型异常只会吞掉程序缺陷。
        CurriculumNormalizationError,
        _RuntimeSourceUnavailable,
    ):
        return PlanningRuntimeInspection(None, "curriculum_not_ready")

    try:
        course_data = build_course_data_provider(
            sqlite_path.strip(),
            semester=semester.strip(),
            approved_acceptance_sha256=normalized_digest,
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
