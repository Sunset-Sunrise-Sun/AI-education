"""个人规划计算入口（**非公共契约**；只编排，不重写任何业务规则）。

```text
PersonalPlanRequest（old_version_id + target_version_id + 本人输入）
        ↓  目录解析（两侧版本都必须**可选**，否则明确拒绝）
        ↓  独立组装本学生的 CurriculumCase（⛔ 不复用任何 case 文件）
        ↓  既有 CurriculumCaseProvider.get_makeup_tasks()  → MakeupTask[]
        ↓  （可选）既有 PlanningOrchestrator/PlannerProvider.plan(...) → PlanResult
PersonalPlanResult（版本元信息 + 补修任务 + 可选规划结果 + 来源说明）
```

## 硬边界

- ⛔ **不改公共 Schema / 公共接口**：本模块只消费既有 `MakeupTask` / `PlanResult`
  与既有 Provider 签名；
- ⛔ **不在 Planner 内另写认定**：认定 / 匹配 / 组学分 / scope 全部由既有
  `app.curriculum` 计算；
- ⛔ **不复用其他学生的已修事实或个案结论**：旧 / 目标两个版本都必须由本学生
  输入显式给出，且全部认定必须属于**本人**来源；
- ⛔ **不伪造培养方案**：版本只能来自 `app.curriculum.catalog` 中**已核验且可选**
  的条目；不可选 / 未核验 / 未知版本一律明确拒绝，⛔ 不回退到 Case A；
- ⛔ **不把"未找到记录"当成确证缺口**：是否缺口由既有 matching 规则决定，
  本模块只**透传**其状态与依据。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.curriculum.case import CurriculumCase, CurriculumCaseProvider
from app.curriculum.catalog import CurriculumCatalog, resolve_catalog_version
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.requirements import CurriculumVersion
from app.integration import PlannerProvider
from app.models.contracts import CourseOffering, DataSource, MakeupTask, PlanResult
from app.personal.student_input import StudentInput, normalize_student_input

__all__ = [
    "PERSONAL_PLAN_REQUEST_FIELDS",
    "PersonalPlanRequest",
    "PersonalPlanResult",
    "build_personal_plan",
    "normalize_personal_plan_request",
    "personal_curriculum_case",
]

#: 一次个人规划请求接受的字段（⛔ 未知字段直接拒绝）。
PERSONAL_PLAN_REQUEST_FIELDS = (
    "old_version_id",
    "target_version_id",
    "student",
    "data_source",
    "semester",
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"{field}: expected a nonempty string")
    return value


@dataclass(frozen=True, slots=True)
class PersonalPlanRequest:
    """一次个人规划请求（已归一化）。

    ``semester`` 只表示"若要把结果排进某个学期"，⛔ 不参与任何认定判断；
    为空时不调用 Planner，只返回补修任务。
    """

    old_version_id: str
    target_version_id: str
    student: StudentInput
    data_source: DataSource
    semester: str | None = None

    def __post_init__(self) -> None:
        _text(self.old_version_id, "old_version_id")
        _text(self.target_version_id, "target_version_id")
        if not isinstance(self.student, StudentInput):
            raise CurriculumNormalizationError("student: expected normalized student input")
        if not isinstance(self.data_source, DataSource):
            raise CurriculumNormalizationError("data_source: expected an explicit data source")
        if self.data_source is not self.student.data_source:
            raise CurriculumNormalizationError("data_source: request and student input disagree")
        if self.semester is not None:
            _text(self.semester, "semester")


@dataclass(frozen=True, slots=True)
class PersonalPlanResult:
    """个人规划结果：**分开**报告事实与规划，便于前端与人工核对来源。"""

    old_version: dict
    target_version: dict
    data_source: DataSource
    completed_source_id: str
    completed_record_count: int
    makeup_tasks: tuple[MakeupTask, ...]
    planning: PlanResult | None
    planning_skipped_reason: str | None
    assuming_course_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        for label, value in (("old_version", self.old_version), ("target_version", self.target_version)):
            if not isinstance(value, Mapping):
                raise CurriculumNormalizationError(f"{label}: expected version metadata")
        if not isinstance(self.data_source, DataSource):
            raise CurriculumNormalizationError("data_source: expected an explicit data source")
        _text(self.completed_source_id, "completed_source_id")
        if isinstance(self.completed_record_count, bool) or not isinstance(self.completed_record_count, int):
            raise CurriculumNormalizationError("completed_record_count: expected an integer")
        object.__setattr__(self, "makeup_tasks", tuple(self.makeup_tasks))
        if any(not isinstance(task, MakeupTask) for task in self.makeup_tasks):
            raise CurriculumNormalizationError("makeup_tasks: unexpected item type")
        if self.planning is not None and not isinstance(self.planning, PlanResult):
            raise CurriculumNormalizationError("planning: unexpected type")
        if self.planning is None and self.planning_skipped_reason is None:
            raise CurriculumNormalizationError(
                "planning_skipped_reason: required when no planning result is returned"
            )
        if self.planning is not None and self.planning_skipped_reason is not None:
            raise CurriculumNormalizationError(
                "planning_skipped_reason: must be absent when a planning result is returned"
            )
        object.__setattr__(self, "assuming_course_ids", tuple(self.assuming_course_ids))
        object.__setattr__(self, "notes", tuple(self.notes))
        if self.planning is None:
            return
        planned = {item.course_id for item in self.planning.selected_classes}
        produced = {task.course_id for task in self.makeup_tasks}
        if planned - produced:
            # Planner 只能消费本次个人计算得到的任务；多出来的课程必须先被看到。
            raise CurriculumNormalizationError(
                "planning: result references courses outside this student's makeup tasks"
            )


def _assemble_case(
    old: CurriculumVersion,
    target: CurriculumVersion,
    student: StudentInput,
) -> CurriculumCase:
    """用**既有** `CurriculumCase` 校验与计算路径组装本学生的 case。

    ⛔ 不在这里重写匹配、组学分或 scope 规则；这些全部由既有
    `build_curriculum_diff` 完成。本函数只做"把本人输入接上既有入口"这件事。
    """

    return CurriculumCase(
        data_source=student.data_source,
        old=old,
        new=target,
        completed=student.completed,
        completed_source_id=student.completed_source_id,
        completed_complete=student.completed_complete,
        completed_completeness_evidence=student.completed_completeness_evidence,
        rules=student.rules,
        recognitions=student.recognitions,
        missing_requirements=student.missing_requirements,
        priority_policy=None,
        elective_selections=student.elective_selections,
        makeup_scope=student.makeup_scope,
        confirmed_scope_decisions=student.confirmed_scope_decisions,
        confirmed_group_scope_decisions=student.confirmed_group_scope_decisions,
    )


def personal_curriculum_case(
    catalog: CurriculumCatalog,
    *,
    old_version_id: str,
    target_version_id: str,
    student: StudentInput,
) -> CurriculumCase:
    """解析两侧版本并组装**本学生**的 case（公开给测试与联调复用）。"""

    if not isinstance(catalog, CurriculumCatalog):
        raise CurriculumNormalizationError("catalog: expected a CurriculumCatalog")
    if not isinstance(student, StudentInput):
        raise CurriculumNormalizationError("student: expected normalized student input")
    old = resolve_catalog_version(catalog, old_version_id)
    target = resolve_catalog_version(catalog, target_version_id)
    if old.version_id == target.version_id:
        raise CurriculumNormalizationError(
            "curriculum version: source and target must be two different versions"
        )
    return _assemble_case(old, target, student)


def _assumption_notes(student: StudentInput, tasks: Sequence[MakeupTask]) -> tuple[str, ...]:
    """把**明确标注的规划假设**接到与之相关的任务依据上（⛔ 不改变任何状态）。"""

    produced = {task.course_id for task in tasks}
    notes = []
    for course_id in student.assumption_course_ids:
        if course_id in produced:
            notes.append(
                f"{course_id}：本次结果中该课程仍按既有规则判定；"
                "学生给出的规划假设未作为认定依据。"
            )
        else:
            notes.append(
                f"{course_id}：学生给出的规划假设指向的课程不在本次补修任务中；"
                "该假设未被采用，也不代表学校认定。"
            )
    return tuple(notes)


def build_personal_plan(
    catalog: CurriculumCatalog,
    request: PersonalPlanRequest,
    *,
    planner: PlannerProvider | None = None,
    offerings: Sequence[CourseOffering] | None = None,
) -> PersonalPlanResult:
    """本学生独立计算：Curriculum → MakeupTask[]（→ 可选 Planner）。

    为什么直接调用冻结的 `PlannerProvider.plan()` 而不是 `PlanningOrchestrator`：
    Orchestrator 只能从它自己持有的 `CurriculumProvider` 取 `MakeupTask[]`，
    而个人规划的 `MakeupTask[]` 必须来自**本学生**的 case；
    把本学生 case 伪装成一个 provider 塞进 Orchestrator 只会制造假的边界。
    因此这里显式使用**同一个已冻结的** `PlannerProvider.plan(...)` 四参数签名，
    ⛔ 不新增参数、⛔ 不改返回类型、⛔ 不复制任何 Planner 逻辑。

    - ``planner`` 与 ``offerings`` 必须**同时**给出才调用 Planner；
      只给其中之一属于装配错误，明确报错（⛔ 不静默降级、⛔ 不回退到 Mock）；
    - 二者都为 `None` 时仍然返回补修任务，并把跳过的**具体原因**写进结果，
      而不是留空让人误解为"没有结果"。
    """

    if not isinstance(catalog, CurriculumCatalog):
        raise CurriculumNormalizationError("catalog: expected a CurriculumCatalog")
    if not isinstance(request, PersonalPlanRequest):
        raise CurriculumNormalizationError("request: expected a PersonalPlanRequest")
    if (planner is None) != (offerings is None):
        raise CurriculumNormalizationError(
            "planning assembly: provide both a planner and its offerings, or neither"
        )

    case = personal_curriculum_case(
        catalog,
        old_version_id=request.old_version_id,
        target_version_id=request.target_version_id,
        student=request.student,
    )
    provider = CurriculumCaseProvider(case)
    tasks = provider.get_makeup_tasks()

    old_metadata = catalog.inspection.metadata_for(request.old_version_id)
    target_metadata = catalog.inspection.metadata_for(request.target_version_id)
    if old_metadata is None or target_metadata is None:
        # `personal_curriculum_case` 已经解析成功，所以这里只可能是目录被并发替换。
        raise CurriculumNormalizationError("catalog: version metadata is no longer available")

    planning: PlanResult | None = None
    skipped: str | None = None
    if planner is None:
        skipped = (
            "no_course_data: 本次未提供真实教学班供给，因此没有调用 Planner；"
            "补修任务仍然有效，但⛔ 不代表任何可执行课表。"
        )
    elif request.semester is None:
        skipped = (
            "no_semester: 本次未指定要把结果排进哪个学期，因此没有调用 Planner。"
        )
    else:
        planning = planner.plan(
            makeup_tasks=list(tasks),
            offerings=list(offerings),
            current_schedule=list(request.student.current_schedule),
            preference=request.student.preference,
        )

    return PersonalPlanResult(
        old_version=old_metadata,
        target_version=target_metadata,
        data_source=request.data_source,
        completed_source_id=request.student.completed_source_id,
        completed_record_count=len(request.student.completed),
        makeup_tasks=tuple(tasks),
        planning=planning,
        planning_skipped_reason=skipped,
        assuming_course_ids=request.student.assumption_course_ids,
        notes=_assumption_notes(request.student, tasks),
    )


def normalize_personal_plan_request(
    payload: object,
    *,
    catalog: CurriculumCatalog,
    data_source: DataSource,
    completed_source_id: str,
) -> PersonalPlanRequest:
    """校验并归一化一次个人规划请求。

    ``completed_source_id`` 由服务端给出（例如内容摘要），⛔ 不取请求里的值；
    这样"另一个来源的已修记录"无法冒充成本人的材料。
    """

    if not isinstance(catalog, CurriculumCatalog):
        raise CurriculumNormalizationError("catalog: expected a CurriculumCatalog")
    if not isinstance(payload, Mapping):
        raise CurriculumNormalizationError("request: expected an object")
    if any(key not in PERSONAL_PLAN_REQUEST_FIELDS for key in payload):
        raise CurriculumNormalizationError("request: unexpected record field")

    old_version_id = _text(payload.get("old_version_id"), "old_version_id")
    target_version_id = _text(payload.get("target_version_id"), "target_version_id")

    # 先解析两侧版本：不可选版本必须在读取任何学生数据之前被拒绝。
    old = resolve_catalog_version(catalog, old_version_id)
    target = resolve_catalog_version(catalog, target_version_id)
    if old.version_id == target.version_id:
        raise CurriculumNormalizationError(
            "curriculum version: source and target must be two different versions"
        )

    student = normalize_student_input(
        payload.get("student", {}),
        target_version_id=target.version_id,
        completed_source_id=completed_source_id,
        data_source=data_source,
    )
    semester = payload.get("semester")
    if semester is not None:
        semester = _text(semester, "semester")

    return PersonalPlanRequest(
        old_version_id=old.version_id,
        target_version_id=target.version_id,
        student=student,
        data_source=data_source,
        semester=semester,
    )
