"""专业与培养方案只读服务（**独立于 case-a-demo**）。

```text
GET /api/v1/majors                  → 可用专业列表
GET /api/v1/study-plans/{major_id}  → 该专业的培养方案（要求 + 选修池）
```

## 为什么单独一层

Case A 的 `/case-a-demo/*` 是**一个固定 case 的闭环演示**：它把"目标专业"
写死在 `APP_CASE_A_DEMO_CURRICULUM_CASE_PATH` 指向的 case 文件里。
产品流程需要的是「**选择专业 → 加载培养方案 → 触发匹配**」，
这是通用的、按 `major_id` 寻址的只读资源，⛔ 不应绑定在某个 case 上。

因此本模块：

- ✅ 从**专业注册表**（`APP_MAJORS_REGISTRY_PATH`）按 `major_id` 定位培养方案来源；
- ✅ 复用既有 `CurriculumCase` 装载能力（docx 定位由 case 文件描述，⛔ 不新增解析器）；
- ⛔ 不引入 `case-a-demo` 的任何常量、⛔ 不读 `case_a_decisions`、⛔ 不做范围裁定。

## Fail closed

注册表缺失 / 不合法 / 任一专业装载失败 ⇒ 整体不可用（空注册表），
⛔ 不用演示数据补齐，⛔ 不部分返回。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.curriculum import (
    CurriculumNormalizationError,
    CurriculumVersion,
    RequirementKind,
    load_curriculum_case,
)
from app.curriculum.json_reader import load_json_input, resolve_local_input

__all__ = [
    "MAX_REQUIREMENTS",
    "REGISTRY_PATH_ENV",
    "MajorRecord",
    "MajorStudyPlan",
    "StudyPlanError",
    "StudyPlanRuntime",
    "build_study_plan_runtime",
    "get_study_plan_runtime",
]

#: 注册表路径环境变量。
REGISTRY_PATH_ENV = "APP_MAJORS_REGISTRY_PATH"

#: 一个专业最多允许的培养方案要求数量（防御性上限）。
MAX_REQUIREMENTS = 2000

_REQUIRED_MAJOR_FIELDS = ("id", "name", "cohort", "curriculum_case_path")
_ALLOWED_MAJOR_FIELDS = frozenset(_REQUIRED_MAJOR_FIELDS) | {"note"}


class StudyPlanError(ValueError):
    """A study-plan request failed a safe boundary."""


@dataclass(frozen=True, slots=True)
class MajorRecord:
    """注册表里的一条专业定义（已校验）。"""

    major_id: str
    name: str
    cohort: str
    version_id: str
    source_id: str
    curriculum_case_path: str


@dataclass(frozen=True, slots=True)
class MajorStudyPlan:
    """一个专业的培养方案（只读投影）。"""

    major: MajorRecord
    version: CurriculumVersion


@dataclass(frozen=True, slots=True)
class StudyPlanRuntime:
    """已装载的培养方案集合；按 `major_id` 服务只读请求。"""

    plans: dict[str, MajorStudyPlan]

    @property
    def available(self) -> bool:
        return bool(self.plans)

    def list_majors(self) -> list[MajorRecord]:
        """按注册表顺序返回全部可用专业。"""

        return [plan.major for plan in self.plans.values()]

    def require(self, major_id: str) -> MajorStudyPlan:
        plan = self.plans.get(major_id)
        if plan is None:
            raise StudyPlanError("unknown_major")
        return plan


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StudyPlanError(f"{field}: expected a nonempty string")
    return value.strip()


def _load_registry(path: str, *, directory: Path) -> tuple[MajorRecord, ...]:
    payload = load_json_input(path, label="majors registry")
    if not isinstance(payload, Mapping):
        raise StudyPlanError("majors registry: expected an object")
    if set(payload) - {"majors", "note"}:
        raise StudyPlanError("majors registry: unexpected field")
    entries = payload.get("majors")
    if not isinstance(entries, list):
        raise StudyPlanError("majors registry: expected a majors array")

    records: list[MajorRecord] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise StudyPlanError("majors registry: expected major objects")
        if set(entry) - _ALLOWED_MAJOR_FIELDS:
            raise StudyPlanError("majors registry: unexpected major field")
        for field in _REQUIRED_MAJOR_FIELDS:
            if field not in entry:
                raise StudyPlanError(f"majors registry: major is missing {field}")
        major_id = _require_text(entry["id"], "major id")
        if major_id in seen:
            raise StudyPlanError("majors registry: duplicate major id")
        seen.add(major_id)
        case_path = resolve_local_input(
            _require_text(entry["curriculum_case_path"], "curriculum_case_path"),
            directory=directory,
            label="curriculum_case_path",
        )
        records.append(
            MajorRecord(
                major_id=major_id,
                name=_require_text(entry["name"], "major name"),
                cohort=_require_text(entry["cohort"], "major cohort"),
                version_id="",
                source_id="",
                curriculum_case_path=str(case_path),
            )
        )
    return tuple(records)


def build_study_plan_runtime(environment: Mapping[str, str]) -> StudyPlanRuntime:
    """装载注册表里**全部**专业；任一条目不可解析即整体不可用（fail closed）。"""

    raw_path = (environment.get(REGISTRY_PATH_ENV) or "").strip()
    if not raw_path:
        return StudyPlanRuntime(plans={})

    registry_path = Path(raw_path)
    try:
        directory = registry_path.resolve().parent
        records = _load_registry(raw_path, directory=directory)
    except (StudyPlanError, CurriculumNormalizationError, OSError, ValueError):
        return StudyPlanRuntime(plans={})

    plans: dict[str, MajorStudyPlan] = {}
    for record in records:
        try:
            case = load_curriculum_case(record.curriculum_case_path)
        except (CurriculumNormalizationError, OSError, ValueError):
            # 任一专业的培养方案不可解析 ⇒ 整体不可用，⛔ 不返回半个注册表。
            return StudyPlanRuntime(plans={})
        version = case.new
        if not version.courses or len(version.courses) > MAX_REQUIREMENTS:
            return StudyPlanRuntime(plans={})
        plans[record.major_id] = MajorStudyPlan(
            major=MajorRecord(
                major_id=record.major_id,
                name=record.name,
                cohort=record.cohort,
                version_id=version.version_id,
                source_id=version.source_id,
                curriculum_case_path=record.curriculum_case_path,
            ),
            version=version,
        )
    return StudyPlanRuntime(plans=plans)


def get_study_plan_runtime() -> StudyPlanRuntime:
    return build_study_plan_runtime(os.environ)


# --------------------------------------------------------------------------- #
# 只读投影（→ API 响应形状）
#
# ⚠️ 这些函数**只**把已有的培养方案事实摊平成 JSON，
#   ⛔ 不判定课程等价、⛔ 不计算缺口、⛔ 不决定谁该补修
#   （"缺什么"仍由 matching engine 在 /plan 里给出）。
# --------------------------------------------------------------------------- #


def to_major_summary(record: MajorRecord) -> dict[str, object]:
    """`GET /api/v1/majors` 列表项。"""

    return {
        "major_id": record.major_id,
        "name": record.name,
        "cohort": record.cohort,
        "version_id": record.version_id,
        "source_id": record.source_id,
    }


def to_course_entry(course: object) -> dict[str, object]:
    """一条培养方案要求。

    `credit_hours` / `lab_hours` 等**不在** `CurriculumCourse` 里，因此不出现；
    ⛔ 不推断缺失字段。
    """

    return {
        "course_id": course.course_id,
        "course_name": course.course_name,
        "credit": course.credit,
        "requirement": course.requirement.value,
        "course_type": course.course_type,
        "group_id": course.group_id,
        "recommended_term_text": course.recommended_term_text,
        # `prerequisites is None` 表示**未知**（⛔ 不是"无先修"）；
        # `[]` 表示来源明确写了无先修。二者必须区分，因此这里原样透出。
        "prerequisites": None if course.prerequisites is None else list(course.prerequisites),
        "prerequisites_known": course.prerequisites is not None,
        "source_record": course.source_record,
    }


def to_study_plan_payload(plan: MajorStudyPlan) -> dict[str, object]:
    """`GET /api/v1/study-plans/{major_id}` 响应体。"""

    version = plan.version
    required = [c for c in version.courses if c.requirement is RequirementKind.REQUIRED]
    electives = [c for c in version.courses if c.requirement is RequirementKind.ELECTIVE]
    unknown = [c for c in version.courses if c.requirement is RequirementKind.UNKNOWN]

    return {
        "major_id": plan.major.major_id,
        "name": plan.major.name,
        "cohort": plan.major.cohort,
        "version_id": version.version_id,
        "source_id": version.source_id,
        "complete": version.complete,
        "completeness_evidence": version.completeness_evidence,
        "total_credit": version.total_credit,
        "counts": {
            "total": len(version.courses),
            "required": len(required),
            "elective": len(electives),
            "unknown": len(unknown),
            # ⚠️ 先修关系未知的条目数。真实培养方案 docx **没有先修列**，
            #   因此这里通常是"全部"——它如实说明当前匹配为什么保守。
            "prerequisites_unknown": sum(
                1 for c in version.courses if c.prerequisites is None
            ),
        },
        "requirements": [to_course_entry(c) for c in version.courses],
        "elective_pool": {
            "groups": [
                {
                    "group_id": group.group_id,
                    "name": group.name,
                    "minimum_credit": group.minimum_credit,
                    "source_record": group.source_record,
                }
                for group in version.groups
            ],
            "courses": [to_course_entry(c) for c in electives],
        },
    }
