"""Integration 排编骨架测试（`PlanningOrchestrator` + 三个 Provider Protocol）。

本文件**只使用测试内部的 Fake / Spy Provider**，**不创建生产 Mock Provider**。

为什么不用 `mock_service` 做 Provider：
如果 `MockPlannerProvider.plan(...)` 无视输入、直接 `load_plan_result()`，
就会造成一种假的"完整 Integration 已经跑通"的错觉。
`/api/v1/mock/*` 与 `mock_service.py` 是**独立的永久 Mock 通道**，
Integration 与它之间**没有** fallback 关系（见 `test_integration_has_no_mock_fallback`）。

覆盖重点（对应任务第 11 节）：
1. 正常流程：Curriculum → MakeupTask[]、Course Data → CourseOffering[]、Planner → PlanResult；
   返回的对象**就是** Planner 给出的那一个；
2. `semester` 原样传递；
3. 四个入参**透明传递**（连对象身份都不变，Integration 没有重排 / 删减 / 生成）；
4. 空 `current_schedule` 可以继续下传，Integration 不自行报错；
5. 空 `offerings` 原样交给 Planner，是否 `infeasible` 由 Planner 决定；
6. Provider 异常**不吞、不 fallback、不切 Mock**，原样向上抛。
"""

from __future__ import annotations

import ast
import inspect

import pytest
from fastapi.testclient import TestClient

import app.integration as integration_package
from app.integration import (
    CourseDataProvider,
    CurriculumProvider,
    PlannerProvider,
    PlanningOrchestrator,
)
from app.integration import orchestrator as orchestrator_module
from app.integration import ports as ports_module
from app.models.contracts import (
    CourseOffering,
    MakeupTask,
    Meeting,
    PlanResult,
    Preference,
)

# ---------------------------------------------------------------------------
# 测试数据（全部来自公共契约模型，不使用 mock_data/）
# ---------------------------------------------------------------------------


def _task(course_id: str = "62001001") -> MakeupTask:
    return MakeupTask(
        course_id=course_id,
        course_name="离散数学",
        credit=3,
        status="required",
    )


def _offering(class_id: str = "6200100120260101") -> CourseOffering:
    return CourseOffering(
        course_id="62001001",
        course_name="离散数学",
        class_id=class_id,
        semester="2026-1",
        meetings=[
            Meeting(weekday=1, start_section=1, end_section=2, weeks=[1, 2, 3, 4]),
        ],
    )


def _plan_result(status: str = "feasible") -> PlanResult:
    return PlanResult(
        status=status,
        selected_classes=[],
        changes=[],
        risks=[],
        unresolved=[],
    )


class _BoomError(RuntimeError):
    """测试用异常：确认 Provider 的异常不会被吞掉。"""


# ---------------------------------------------------------------------------
# 测试内部 Fake / Spy Provider（**不是**生产 Mock Provider）
# ---------------------------------------------------------------------------


class SpyCurriculumProvider:
    """记录调用次数，返回事先给定的 `MakeupTask[]`。"""

    def __init__(self, tasks: list[MakeupTask], log: list[str] | None = None) -> None:
        self._tasks = tasks
        self._log = log
        self.calls = 0

    def get_makeup_tasks(self) -> list[MakeupTask]:
        self.calls += 1
        if self._log is not None:
            self._log.append("curriculum")
        return self._tasks


class SpyCourseDataProvider:
    """记录**实际收到的 semester**，返回事先给定的 `CourseOffering[]`。"""

    def __init__(self, offerings: list[CourseOffering], log: list[str] | None = None) -> None:
        self._offerings = offerings
        self._log = log
        self.semesters: list[str] = []

    def get_course_offerings(self, semester: str) -> list[CourseOffering]:
        self.semesters.append(semester)
        if self._log is not None:
            self._log.append("course_data")
        return self._offerings


class SpyPlannerProvider:
    """记录**实际收到的全部入参**（保留对象身份，便于断言透明传递）。"""

    def __init__(self, result: PlanResult, log: list[str] | None = None) -> None:
        self._result = result
        self._log = log
        self.received: list[dict[str, object]] = []

    def plan(
        self,
        *,
        makeup_tasks: list[MakeupTask],
        offerings: list[CourseOffering],
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult:
        self.received.append(
            {
                "makeup_tasks": makeup_tasks,
                "offerings": offerings,
                "current_schedule": current_schedule,
                "preference": preference,
            }
        )
        if self._log is not None:
            self._log.append("planner")
        return self._result


class ExplodingCourseDataProvider:
    """Course Data 抛异常：用于确认异常原样向上传递。"""

    def get_course_offerings(self, semester: str) -> list[CourseOffering]:
        raise _BoomError(f"course data failed for {semester}")


class ExplodingPlannerProvider:
    """Planner 抛异常：用于确认异常原样向上传递。"""

    def plan(
        self,
        *,
        makeup_tasks: list[MakeupTask],
        offerings: list[CourseOffering],
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult:
        raise _BoomError("planner failed")


class _Recorder:
    """共享调用顺序日志。"""

    def __init__(self) -> None:
        self.log: list[str] = []


def _build(
    *,
    tasks: list[MakeupTask] | None = None,
    offerings: list[CourseOffering] | None = None,
    result: PlanResult | None = None,
) -> tuple[PlanningOrchestrator, SpyCurriculumProvider, SpyCourseDataProvider, SpyPlannerProvider]:
    recorder = _Recorder()
    curriculum = SpyCurriculumProvider(tasks if tasks is not None else [_task()], recorder.log)
    course_data = SpyCourseDataProvider(
        offerings if offerings is not None else [_offering()], recorder.log
    )
    planner = SpyPlannerProvider(result if result is not None else _plan_result(), recorder.log)

    orchestrator = PlanningOrchestrator(
        curriculum=curriculum,
        course_data=course_data,
        planner=planner,
    )
    return orchestrator, curriculum, course_data, planner


# ---------------------------------------------------------------------------
# Protocol：契约形状（结构类型，不需要继承）
# ---------------------------------------------------------------------------


def test_fake_providers_satisfy_protocols() -> None:
    """测试用 Fake Provider 必须结构上满足三个 Protocol。

    这同时说明 Protocol 是"最小形状"而不是要求继承某个基类。
    """

    assert isinstance(SpyCurriculumProvider([_task()]), CurriculumProvider)
    assert isinstance(SpyCourseDataProvider([_offering()]), CourseDataProvider)
    assert isinstance(SpyPlannerProvider(_plan_result()), PlannerProvider)


def test_planner_port_does_not_take_priority_or_dependency_graph() -> None:
    """DG-05：Planner 插座不得私自接收 priority / dependency_graph / risk_scores。"""

    signature = inspect.signature(PlannerProvider.plan)

    assert set(signature.parameters) == {
        "self",
        "makeup_tasks",
        "offerings",
        "current_schedule",
        "preference",
    }


def test_orchestrator_holds_only_the_three_providers() -> None:
    """Orchestrator 只持有三个 Provider，不持有上下文 / 会话 / 缓存。"""

    fields = set(PlanningOrchestrator.__dataclass_fields__)

    assert fields == {"curriculum", "course_data", "planner"}


# ---------------------------------------------------------------------------
# 1. 正常流程
# ---------------------------------------------------------------------------


def test_build_plan_returns_the_planner_result_object() -> None:
    """返回的对象必须**就是** Planner 给出的那一个（不包装、不复制、不改写）。"""

    result = _plan_result()
    orchestrator, _curriculum, _course_data, planner = _build(result=result)

    returned = orchestrator.build_plan(
        semester="2026-1",
        current_schedule=[_offering("6200100120260102")],
        preference=Preference(max_credit=15),
    )

    assert returned is result
    assert len(planner.received) == 1


def test_build_plan_calls_every_provider_once_in_order() -> None:
    """调用顺序固定为 Curriculum → Course Data → Planner。"""

    recorder = _Recorder()
    orchestrator = PlanningOrchestrator(
        curriculum=SpyCurriculumProvider([_task()], recorder.log),
        course_data=SpyCourseDataProvider([_offering()], recorder.log),
        planner=SpyPlannerProvider(_plan_result(), recorder.log),
    )

    orchestrator.build_plan(
        semester="2026-1",
        current_schedule=[],
        preference=Preference(),
    )

    assert recorder.log == ["curriculum", "course_data", "planner"]


# ---------------------------------------------------------------------------
# 2. semester 传递
# ---------------------------------------------------------------------------


def test_semester_is_passed_through_unchanged() -> None:
    """`build_plan(semester="2026-1")` 后，Course Data 必须真的收到 `"2026-1"`。"""

    orchestrator, _curriculum, course_data, _planner = _build()

    orchestrator.build_plan(
        semester="2026-1",
        current_schedule=[],
        preference=Preference(),
    )

    assert course_data.semesters == ["2026-1"]


def test_semester_is_not_normalized_or_defaulted() -> None:
    """Integration 不改写 semester：原样传什么就是什么（不做任何规整）。"""

    orchestrator, _curriculum, course_data, _planner = _build()
    raw_semester = "2026-1  "  # 故意带上空格与非常规写法

    orchestrator.build_plan(
        semester=raw_semester,
        current_schedule=[],
        preference=Preference(),
    )

    assert course_data.semesters == [raw_semester]


# ---------------------------------------------------------------------------
# 3. 参数透明传递
# ---------------------------------------------------------------------------


def test_planner_receives_exactly_the_same_objects() -> None:
    """四个入参必须**按对象身份**原样到达 Planner：不重排、不删减、不生成。"""

    tasks = [_task("62001001"), _task("62001002")]
    offerings = [_offering("6200100120260101"), _offering("6200100120260102")]
    current_schedule = [_offering("6200100220260101")]
    preference = Preference(max_credit=18, avoid_cross_campus=True)

    orchestrator, _curriculum, _course_data, planner = _build(
        tasks=tasks, offerings=offerings
    )

    orchestrator.build_plan(
        semester="2026-1",
        current_schedule=current_schedule,
        preference=preference,
    )

    received = planner.received[0]

    assert received["makeup_tasks"] is tasks
    assert received["offerings"] is offerings
    assert received["current_schedule"] is current_schedule
    assert received["preference"] is preference

    # 顺序也不得被改动
    assert [t.course_id for t in received["makeup_tasks"]] == ["62001001", "62001002"]
    assert [o.class_id for o in received["offerings"]] == [
        "6200100120260101",
        "6200100120260102",
    ]


# ---------------------------------------------------------------------------
# 4. 空 current_schedule
# ---------------------------------------------------------------------------


def test_empty_current_schedule_is_passed_through() -> None:
    """`current_schedule=[]` 必须可以继续下传；Integration 不得因此自行报错。"""

    orchestrator, _curriculum, _course_data, planner = _build()
    empty_schedule: list[CourseOffering] = []

    result = orchestrator.build_plan(
        semester="2026-1",
        current_schedule=empty_schedule,
        preference=Preference(),
    )

    assert isinstance(result, PlanResult)
    assert planner.received[0]["current_schedule"] is empty_schedule
    assert planner.received[0]["current_schedule"] == []


# ---------------------------------------------------------------------------
# 5. 空 offerings：是否 infeasible 由 Planner 决定
# ---------------------------------------------------------------------------


def test_empty_offerings_are_passed_through_and_status_comes_from_planner() -> None:
    """Course Data 返回 `[]` 时，Integration 原样交给 Planner；

    方案是否 `infeasible` / `partially_feasible` **由 Planner 决定**，
    Integration 不得代替 Planner 判断。
    """

    planner_verdict = _plan_result("infeasible")
    empty_offerings: list[CourseOffering] = []

    orchestrator, _curriculum, _course_data, planner = _build(
        offerings=empty_offerings, result=planner_verdict
    )

    returned = orchestrator.build_plan(
        semester="2026-1",
        current_schedule=[],
        preference=Preference(),
    )

    assert planner.received[0]["offerings"] is empty_offerings
    assert returned is planner_verdict
    assert returned.status.value == "infeasible"


# ---------------------------------------------------------------------------
# 6. Provider 异常：不吞、不 fallback、不切 Mock
# ---------------------------------------------------------------------------


def test_course_data_error_propagates() -> None:
    """Course Data 抛异常：原样向上抛，且 Planner 不会被调用（没有 fallback 路径）。"""

    planner = SpyPlannerProvider(_plan_result())
    orchestrator = PlanningOrchestrator(
        curriculum=SpyCurriculumProvider([_task()]),
        course_data=ExplodingCourseDataProvider(),
        planner=planner,
    )

    with pytest.raises(_BoomError):
        orchestrator.build_plan(
            semester="2026-1",
            current_schedule=[],
            preference=Preference(),
        )

    assert planner.received == []


def test_planner_error_propagates() -> None:
    """Planner 抛异常：原样向上抛，不返回任何 fallback 结果。"""

    orchestrator = PlanningOrchestrator(
        curriculum=SpyCurriculumProvider([_task()]),
        course_data=SpyCourseDataProvider([_offering()]),
        planner=ExplodingPlannerProvider(),
    )

    with pytest.raises(_BoomError):
        orchestrator.build_plan(
            semester="2026-1",
            current_schedule=[],
            preference=Preference(),
        )


def test_integration_has_no_mock_fallback() -> None:
    """Integration 层不得引用 Mock 通道（否则就是"假跑通"）。

    用 **AST** 检查真实的 import 与函数调用，而不是查源码文本 ——
    文档里出现 `mock_service` 这类**说明性文字**是允许的
    （本包文档正是在声明"我们不会回退到它"），被禁止的是**真的导入或调用它**。

    一旦有人写了 `load_plan_result()` 之类的兜底，这条用例立刻失败。
    """

    mock_replay_calls = {
        "all_mock_data",
        "load_course_offerings",
        "load_makeup_tasks",
        "load_plan_result",
        "load_preference",
    }

    for module in (integration_package, ports_module, orchestrator_module):
        tree = ast.parse(inspect.getsource(module))

        imported: set[str] = set()
        called: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)

        forbidden_imports = {
            name
            for name in imported
            if name.startswith("app.services") or name == "mock_service"
        }
        assert not forbidden_imports, f"{module.__name__} 导入了 Mock 通道：{forbidden_imports}"

        assert not (called & mock_replay_calls), (
            f"{module.__name__} 直接回放了 Mock 结果：{called & mock_replay_calls}"
        )


def test_real_plan_endpoint_is_the_only_new_integration_api(client: TestClient) -> None:
    """真实规划入口已开放；未装配时由 API 明确返回 503。

    ⚠️ 下面是**显式白名单**：任何新增路由都必须在这里逐条登记（⛔ 不允许"顺手多挂"）。
    Gate F 只新增了一条：通用已修课程 XLSX 摄取入口
    `POST /api/v1/completed-courses/import`（见 `docs/data/XLSX_COMPLETED_COURSES_IMPORT.md`），
    它⛔ 不改 `/api/v1/plan` 契约，也⛔ 不接入 Case A fixed-case runtime。
    成绩单 PDF 主路径再新增一条：
    `POST /api/v1/completed-courses/import-pdf`（见 `docs/curriculum/PDF_TRANSCRIPT_INPUT.md`），
    同样⛔ 不改 `/api/v1/plan` 契约、⛔ 不接入 Case A fixed-case runtime；
    XLSX 入口保持原样，仍是兼容的次要路径。
    """

    paths = set(client.get("/openapi.json").json()["paths"])

    for forbidden in ("/plan", "/integration", "/api/v1/integration"):
        assert forbidden not in paths, f"不应暴露 {forbidden}"

    assert paths == {
        "/health",
        "/api/v1/health",
        "/api/v1/mock/makeup-tasks",
        "/api/v1/mock/course-offerings",
        "/api/v1/mock/preference",
        "/api/v1/mock/plan-result",
        "/api/v1/mock/demo",
        "/api/v1/plan",
        # Gate F（已授权的新增入口）：通用 XLSX 摄取，⛔ 不是 integration 数据通道。
        "/api/v1/completed-courses/import",
        # 成绩单 PDF 摄取（Case A 主路径），⛔ 不是 integration 数据通道。
        "/api/v1/completed-courses/import-pdf",
        # Distinct Case A demo path; it never changes production /api/v1/plan.
        "/api/v1/case-a-demo/offerings",
        "/api/v1/case-a-demo/plan",
    }
