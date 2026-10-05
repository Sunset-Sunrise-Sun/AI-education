"""Case A 真实规划链路的显式、fail-closed 装配边界。

本模块只负责把已经存在的 production Provider 装进
``PlanningOrchestrator``。它不实现业务算法、不扫描文件系统，也不回退到
``mock_data``。真实运行时默认关闭；启用后缺少或损坏任一受控输入都会返回
unavailable，并可通过 ``inspect_planning_runtime()`` 取得不含私密路径的诊断码。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.course_data import (
    CourseDataNormalizationError,
    SnapshotCourseDataProvider,
    collect_captured_pages_snapshot,
    validate_capture_bundle,
)
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

_ENABLED = "APP_REAL_CASE_A_ENABLED"
_CURRICULUM_CASE_PATH = "APP_CASE_A_CURRICULUM_CASE_PATH"
_COURSE_SNAPSHOT_PATH = "APP_COURSE_SNAPSHOT_PATH"
_COURSE_SNAPSHOT_SOURCE = "APP_COURSE_SNAPSHOT_SOURCE"
_COURSE_SNAPSHOT_SHA256 = "APP_COURSE_SNAPSHOT_SHA256"
_CASE_A_PLANNING_SEMESTER = "2026-1"
_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


class PlanningRuntimeNotConfigured(RuntimeError):
    """真实 Curriculum / Course Data / Planner 尚未完成装配。"""


class _RuntimeSourceUnavailable(RuntimeError):
    """一个显式配置的 runtime source 尚不能安全进入 production 链路。"""


class _RuntimeConfigurationInvalid(RuntimeError):
    """Runtime 配置值存在格式错误。"""


@dataclass(frozen=True, slots=True)
class PlanningRuntimeInspection:
    """Runtime factory 的最小诊断结果；不含路径或输入内容。"""

    orchestrator: PlanningOrchestrator | None
    reason: str

    @property
    def ready(self) -> bool:
        return self.orchestrator is not None


def build_curriculum_provider(case_path: str) -> CurriculumCaseProvider:
    """从调用方明确指定的 Case A manifest 构造真实 Curriculum Provider。"""

    case = load_curriculum_case(case_path)
    if case.data_source.value != "real":
        raise _RuntimeSourceUnavailable("curriculum case is not marked real")
    if case.new.version_id != CASE_TARGET_VERSION_ID:
        raise _RuntimeSourceUnavailable("curriculum case is not Case A")
    if case.makeup_scope is None or case.makeup_scope.as_of_term != AS_OF_TERM:
        raise _RuntimeSourceUnavailable("curriculum case has the wrong scope cut-off")
    if case.confirmed_scope_decisions != confirmed_scope_decisions():
        raise _RuntimeSourceUnavailable("curriculum case decisions are not approved")

    provider = CurriculumCaseProvider(case)
    # 构造期即验证 projection；不得等到请求中再发现 case 未就绪。
    provider.get_makeup_tasks()
    return provider


def build_course_data_provider(
    snapshot_path: str,
    *,
    source: str,
    approved_sha256: str,
) -> SnapshotCourseDataProvider:
    """从经 exact-artifact digest 批准的 Capture Bundle 构造 Provider。"""

    if not source.strip() or source.strip().lower().startswith("mock://"):
        raise _RuntimeSourceUnavailable("course data source is not an explicit real source")

    normalized_digest = _normalize_sha256(approved_sha256)
    artifact_bytes = Path(snapshot_path).read_bytes()
    actual_digest = hashlib.sha256(artifact_bytes).hexdigest()
    if not hmac.compare_digest(actual_digest, normalized_digest):
        raise _RuntimeSourceUnavailable("course offering artifact digest mismatch")

    try:
        bundle = json.loads(artifact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CourseDataNormalizationError(
            "Capture Bundle 不是合法 UTF-8 JSON"
        ) from None
    validate_capture_bundle(bundle)
    if not isinstance(bundle, Mapping):
        raise CourseDataNormalizationError("Capture Bundle 必须是对象")

    snapshot = collect_captured_pages_snapshot(bundle, source=source)
    if snapshot.semester != _CASE_A_PLANNING_SEMESTER:
        raise _RuntimeSourceUnavailable("course offering snapshot is for another semester")
    if not snapshot.is_complete:
        raise _RuntimeSourceUnavailable("course offering snapshot is incomplete")
    if snapshot.loaded_count == 0:
        raise _RuntimeSourceUnavailable("course offering snapshot is empty")
    return SnapshotCourseDataProvider(snapshot)


def build_planner_provider() -> RestrictedPlannerProvider:
    """实例化当前已审核的 deterministic restricted Planner。"""

    return RestrictedPlannerProvider()


def _required(environment: Mapping[str, str], name: str) -> str | None:
    value = environment.get(name)
    if value is None or not value.strip():
        return None
    return value


def _normalize_sha256(value: str) -> str:
    normalized = value.strip()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        raise _RuntimeConfigurationInvalid(
            "approved course snapshot SHA-256 must be exactly 64 hexadecimal characters"
        )
    return normalized.lower()


def build_planning_runtime(
    environment: Mapping[str, str],
) -> PlanningRuntimeInspection:
    """按显式环境配置构造 production runtime，并以诊断码 fail closed。"""

    enabled = environment.get(_ENABLED)
    if enabled is None or enabled == "0":
        return PlanningRuntimeInspection(None, "runtime_disabled")
    if enabled != "1":
        return PlanningRuntimeInspection(None, "invalid_runtime_configuration")

    case_path = _required(environment, _CURRICULUM_CASE_PATH)
    if case_path is None:
        return PlanningRuntimeInspection(None, "curriculum_not_ready")

    snapshot_path = _required(environment, _COURSE_SNAPSHOT_PATH)
    snapshot_source = _required(environment, _COURSE_SNAPSHOT_SOURCE)
    approved_sha256 = _required(environment, _COURSE_SNAPSHOT_SHA256)
    if snapshot_path is None or snapshot_source is None or approved_sha256 is None:
        return PlanningRuntimeInspection(None, "course_data_not_ready")
    try:
        normalized_digest = _normalize_sha256(approved_sha256)
    except _RuntimeConfigurationInvalid:
        return PlanningRuntimeInspection(None, "invalid_runtime_configuration")

    try:
        curriculum = build_curriculum_provider(case_path)
    except (CurriculumNormalizationError, OSError, _RuntimeSourceUnavailable):
        return PlanningRuntimeInspection(None, "curriculum_not_ready")

    try:
        course_data = build_course_data_provider(
            snapshot_path,
            source=snapshot_source,
            approved_sha256=normalized_digest,
        )
    except (CourseDataNormalizationError, OSError, _RuntimeSourceUnavailable):
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
    """检查当前进程环境中的 production runtime，不打印任何输入内容。"""

    return build_planning_runtime(os.environ)


def get_planning_orchestrator() -> PlanningOrchestrator | None:
    """FastAPI dependency：可用时返回 production orchestrator，否则返回 ``None``。"""

    return inspect_planning_runtime().orchestrator
