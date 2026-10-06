#!/usr/bin/env python3
"""Case A scoped（南校园 + 深圳校区）课程数据 + 当前课表 + Planner 连通性 CLI。

```text
本地 Course Data 库里**已正式验收**的两个 campus acceptance
  （south-campus   5062201
    shenzhen-campus 333291143）
        ↓  build_case_a_dataset(...)            ← 复用既有 campus acceptance 信任链
Case A scoped 教学班数据集（**demo scope**，⛔ 不是 full_semester）
        ↓  CaseAScopedCourseDataProvider.get_course_offerings(semester)
CourseOffering[]  ──┬──  verify   只打印 scope / 计数 / digest（⛔ 不导出取值）
                    ├──  export   写出自带 scope 标签的 Case A 数据集 JSON
                    └──  smoke    与手工 current_schedule + Preference 一起交给 RestrictedPlanner
```

## 这是什么，不是什么（⛔ 措辞是契约的一部分）

```text
是：  Case A scoped South + Shenzhen teaching-class data（demo scope）
不是：full_semester / whole school / all campus / complete SYSU database
      / LEVEL2 real dataset / 五校区完整供给
```

## 硬边界

- ⛔ 本工具**只读** Course Data 库：不建表、不导入、不接受任何新 artifact、不写 acceptance；
- ⛔ 不联网、⛔ 不读凭据、⛔ 不发起任何学校请求（真实采集由负责人用已批准的浏览器采集器执行）；
- ⛔ **不改** full_semester acceptance 语义：本工具**不调用** `accept_full_semester_capture_set()`，
  也⛔ **不写** `full_semester` scope 的任何行；
- ⛔ 不新增公共 Schema：输出仍然是公共 `CourseOffering[]`；
- ⛔ 没有 Mock fallback、没有单校区 fallback、没有"缺一个校区就凑合"的降级：
  任一校区缺 acceptance / 不唯一 / 内容绑定不符 ⇒ 直接失败；
- ⛔ `export` 写出的 JSON 含真实教学班取值 ⇒ **不得提交 Git**（默认写到仓库外或已忽略路径）；
  `verify` / `smoke` 的**标准输出只含结构性信息**，可以贴进交接记录。

## 用法

```bash
cd backend

# 1) 只验证两个校区 acceptance 能否构造出 Case A scoped 数据集（不导出取值）
python ../tools/case_a_course_data.py verify \
    --store /path/to/course_data.sqlite3 --semester 2026-1

# 2) 导出带 scope 标签的 Case A 数据集 JSON（含真实取值，⛔ 不入 Git）
python ../tools/case_a_course_data.py export \
    --store /path/to/course_data.sqlite3 --semester 2026-1 \
    --out /path/outside/repo/case_a_course_data.json

# 3) Planner 连通性 smoke（用负责人手工录入的当前课表）
python ../tools/case_a_course_data.py smoke \
    --store /path/to/course_data.sqlite3 --semester 2026-1 \
    --current-schedule /path/outside/repo/current_schedule.json \
    --makeup-tasks /path/outside/repo/makeup_tasks.json \
    --preference /path/outside/repo/preference.json
```

`smoke` **不经过 HTTP**，也**不装配** production runtime：它在进程内用
`CurriculumCaseProvider（由 APP_* 环境变量装配的真实 runtime 提供）`
+ `CaseAScopedCourseDataProvider`（本工具构造）
+ `RestrictedPlannerProvider`
组成一个 `PlanningOrchestrator` 调用一次。⛔ 不改 Planner、⛔ 不改 runtime。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"

# 让 `python tools/case_a_course_data.py` 与 `python -m ...` 都能 import 到 app.*
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.course_data.case_a_scope import (  # noqa: E402
    CASE_A_CAMPUS_SHARD_IDS,
    CaseADataset,
    CaseAScopeError,
    CaseAScopedCourseDataProvider,
    build_case_a_dataset,
    serialize_case_a_dataset,
)
from app.course_data.errors import CourseDataNormalizationError  # noqa: E402
from app.integration import PlanningOrchestrator  # noqa: E402
from app.models.contracts import CourseOffering, Preference  # noqa: E402
from app.planner.provider import RestrictedPlannerProvider  # noqa: E402
from app.services.planning_runtime import build_curriculum_provider  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CASE_SCOPE = 3
EXIT_INPUT = 4


class _ArgumentParser(argparse.ArgumentParser):
    """参数错误不回声调用方给的文件路径 / 取值。"""

    def error(self, message: str) -> None:  # pragma: no cover - argparse 回调
        self.exit(EXIT_USAGE, "参数无效，请运行 --help 查看用法。\n")


def _fail(message: str, *, code: int) -> int:
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    return code


def _read_json_object(path_text: str, *, label: str) -> object:
    """只读调用方**显式给出**的本地 UTF-8 JSON（⛔ 不扫描目录、⛔ 不猜路径）。"""

    if not isinstance(path_text, str) or not path_text.strip():
        raise ValueError(f"{label} 路径必须是非空字符串")

    path = Path(path_text)
    if not path.is_file():
        raise ValueError(f"{label} 文件不存在或不是普通文件")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} 不是可读取的 UTF-8 JSON（{type(exc).__name__}）") from exc


def _require_list_of_objects(value: object, *, label: str) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是 JSON 数组")
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{label} 第 {index} 项必须是对象")
    return value


def _load_current_schedule(path_text: str) -> list[CourseOffering]:
    """把负责人手工录入的当前课表读成公共 `CourseOffering[]`。

    ⛔ 不做任何补默认值：`data_source` 必须**显式**给出（由录入方对来源负责），
    字段形状由公共 Pydantic 契约校验。空数组是合法输入（当前课表可以为空）。
    """

    raw = _require_list_of_objects(
        _read_json_object(path_text, label="current_schedule"), label="current_schedule"
    )
    try:
        return [CourseOffering.model_validate(item) for item in raw]
    except Exception as exc:  # pydantic.ValidationError（不回显取值）
        raise ValueError(
            f"current_schedule 中有教学班不符合公共 CourseOffering 契约（{type(exc).__name__}）"
        ) from None


def _load_preference(path_text: str) -> Preference:
    raw = _read_json_object(path_text, label="preference")
    if not isinstance(raw, dict):
        raise ValueError("preference 必须是 JSON 对象")
    try:
        return Preference.model_validate(raw)
    except Exception as exc:
        raise ValueError(
            f"preference 不符合公共 Preference 契约（{type(exc).__name__}）"
        ) from None


def _load_makeup_tasks(path_text: str):
    """读取 public `MakeupTask[]`（由 Curriculum 负责产出，本工具⛔不生成、⛔不推断）。"""

    from app.models.contracts import MakeupTask

    raw = _require_list_of_objects(
        _read_json_object(path_text, label="makeup_tasks"), label="makeup_tasks"
    )
    try:
        return [MakeupTask.model_validate(item) for item in raw]
    except Exception as exc:
        raise ValueError(
            f"makeup_tasks 中有任务不符合公共 MakeupTask 契约（{type(exc).__name__}）"
        ) from None


def _dataset_summary(dataset: CaseADataset) -> dict[str, object]:
    """结构性摘要：scope 标签 + 计数 + digest（⛔ 不含任何教学班取值）。"""

    return {
        "semester": dataset.scope.semester,
        "scope_kind": dataset.scope.scope_kind,
        "scope_label": dataset.scope.scope_label,
        "scope_id": dataset.scope.scope_id,
        "scope_semantics": dataset.scope.scope_semantics,
        "is_full_semester": dataset.is_full_semester,
        "is_whole_school": dataset.is_whole_school,
        "campuses": [
            {
                "shard_id": record.shard_id,
                "openingSchoolNumber": record.opening_school_number,
                "campus_acceptance_sha256": record.campus_acceptance_sha256,
                "offering_count": record.offering_count,
                "offering_set_sha256": record.offering_set_sha256,
            }
            for record in dataset.campuses
        ],
        "merged_offering_count": dataset.merged_offering_count,
        "merged_offering_set_sha256": dataset.merged_offering_set_sha256,
        "duplicate_identity_deduped": dataset.duplicate_identity_deduped,
    }


def _require_expected_campus_digests(value: object) -> dict[str, str] | None:
    """`--expected-campus-sha256` 的可选人工门（`shard_id → campus acceptance SHA-256`）。"""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("expected_campus_sha256 必须是 JSON 对象（shard_id → SHA-256）")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str) or not item.strip():
            raise ValueError("expected_campus_sha256 的键与值都必须是非空字符串")
        result[key] = item
    return result


def _command_verify(args: argparse.Namespace) -> int:
    dataset = build_case_a_dataset(
        args.store,
        semester=args.semester,
        expected_campus_sha256=_require_expected_campus_digests(args.expected_campus_sha256),
    )
    provider = CaseAScopedCourseDataProvider(dataset)
    # ⛔ 显式断言：这个 Provider 永远不是 full_semester。
    assert provider.is_full_semester is False
    offerings = provider.get_course_offerings(args.semester)

    summary = _dataset_summary(dataset)
    summary["provider_offering_count"] = len(offerings)
    summary["provider_is_full_semester"] = provider.is_full_semester
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_OK


def _command_export(args: argparse.Namespace) -> int:
    dataset = build_case_a_dataset(
        args.store,
        semester=args.semester,
        expected_campus_sha256=_require_expected_campus_digests(args.expected_campus_sha256),
    )
    document = serialize_case_a_dataset(dataset)

    target = Path(args.out)
    if target.exists() and not args.force:
        return _fail("输出文件已存在；⛔ 不覆盖（需要时显式加 --force）", code=EXIT_INPUT)
    if not target.parent.is_dir():
        return _fail("输出文件的父目录不存在；⛔ 不自动创建目录", code=EXIT_INPUT)

    try:
        target.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        return _fail(f"无法写出 Case A 数据集（{type(exc).__name__}）", code=EXIT_INPUT)

    summary = _dataset_summary(dataset)
    summary["written"] = True
    summary["written_file_name"] = target.name
    summary["note"] = (
        "该文件含真实教学班取值：⛔ 不得提交 Git、⛔ 不得放入 mock_data、"
        "⛔ 不得作为测试 fixture。"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_OK


def _command_smoke(args: argparse.Namespace) -> int:
    """Case A scoped offerings + 手工 current_schedule + Preference → RestrictedPlanner。"""

    dataset = build_case_a_dataset(
        args.store,
        semester=args.semester,
        expected_campus_sha256=_require_expected_campus_digests(args.expected_campus_sha256),
    )
    course_data = CaseAScopedCourseDataProvider(dataset)

    current_schedule = _load_current_schedule(args.current_schedule)
    preference = _load_preference(args.preference)

    curriculum, makeup_source = _resolve_curriculum(args)

    orchestrator = PlanningOrchestrator(
        curriculum=curriculum,
        # ⚠️ 这里**故意**不是 StoreBackedCourseDataProvider（那是 production full_semester 路径）：
        #    smoke 绑定的是 Case A scoped（南 + 深圳）demo 数据集。
        course_data=course_data,
        planner=RestrictedPlannerProvider(),
    )

    result = orchestrator.build_plan(
        semester=args.semester,
        current_schedule=current_schedule,
        preference=preference,
    )

    print(json.dumps({
        "scope_label": course_data.scope.scope_label,
        "is_full_semester": course_data.is_full_semester,
        "offerings_from_case_a_scope": len(course_data.get_course_offerings(args.semester)),
        "makeup_tasks_source": makeup_source,
        "makeup_task_count": len(curriculum.get_makeup_tasks()),
        "current_schedule_count": len(current_schedule),
        "plan_status": result.status.value,
        # ⚠️ 下面三项是**既有 RestrictedPlanner 的原样输出**，本工具⛔ 不解释、⛔ 不改写：
        #    - selected_classes 是**建议**课表（含学生当前已选班 + 本次可加入的 CLEAR 班），
        #      ⛔ 不是"已完成选课 / 已注册"；
        #    - changes 中新增 required 任务是 Planner 的既定语义（唯一 CLEAR 班才自动加入），
        #      ⛔ 本工具不参与该判断；
        #    - unresolved 里可能包含"Preference 字段口径待确认"，
        #      即 ⛔ **并非**每个偏好都被完全执行。
        "selected_classes": [item.model_dump() for item in result.selected_classes],
        "changes": [item.model_dump() for item in result.changes],
        "risk_count": len(result.risks),
        "unresolved": [item.model_dump() for item in result.unresolved],
        "planner_output_note": (
            "selected_classes 是建议（⛔ 不是已完成选课）；Planner 为受限确定性规划，"
            "⛔ 不是全局最优、⛔ 不自动注册；未能完全执行的偏好会在 unresolved 中如实列出。"
        ),
    }, ensure_ascii=False, indent=2))
    return EXIT_OK


class _FixedMakeupTasksProvider:
    """把调用方显式给出的 public `MakeupTask[]` 包成冻结的 `CurriculumProvider` 形状。

    ⛔ 不推断、⛔ 不生成、⛔ 不修改任务语义；仅原样交给 Planner。
    ⛔ 本类**不是** Curriculum 实现：MakeupTask 的语义仍然只由 Curriculum 拥有。
    """

    def __init__(self, tasks: list) -> None:
        self._tasks = list(tasks)

    def get_makeup_tasks(self) -> list:
        return list(self._tasks)


def _resolve_curriculum(args: argparse.Namespace):
    """取得补修任务来源：显式交接文件优先，否则复用 runtime 的 Curriculum 装配。

    ⛔ 本工具**不**生成、**不**推断、**不**改写任何补修任务；
    ⛔ 没有 Mock fallback：两条路都不通就直接失败。
    """

    if args.makeup_tasks is not None:
        return _FixedMakeupTasksProvider(_load_makeup_tasks(args.makeup_tasks)), "explicit_file"

    case_path = _environment().get("APP_CASE_A_CURRICULUM_CASE_PATH", "").strip()
    if not case_path:
        raise ValueError(
            "缺少补修任务来源：请提供 --makeup-tasks（Curriculum 交接的 public MakeupTask[] JSON），"
            "或设置 APP_CASE_A_CURRICULUM_CASE_PATH 以复用 runtime 的 Curriculum 装配；"
            "⛔ 本工具不生成补修任务，也⛔ 不 fallback 到 Mock"
        )

    from app.curriculum.errors import CurriculumNormalizationError

    try:
        return build_curriculum_provider(case_path), "runtime_curriculum_provider"
    except CurriculumNormalizationError:
        raise ValueError(
            "APP_CASE_A_CURRICULUM_CASE_PATH 指向的 Case A case 未通过 Curriculum 受控校验；"
            "⛔ 不 fallback 到 Mock（具体原因请用 Curriculum 侧工具查看）"
        ) from None


def _environment() -> dict[str, str]:
    import os

    return {key: value for key, value in os.environ.items()}


def _add_dataset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store", required=True, help="本地 Course Data SQLite 库路径（只读）")
    parser.add_argument("--semester", required=True, help="Case A 目标学期，例如 2026-1")
    parser.add_argument(
        "--expected-campus-sha256",
        help=(
            "可选的人工门：JSON 对象（shard_id → campus acceptance SHA-256），"
            f"键只能是 {list(CASE_A_CAMPUS_SHARD_IDS)}"
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="case_a_course_data.py",
        description="Case A scoped（南校园 + 深圳校区）课程数据 / 当前课表 / Planner 连通性。",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify", help="只打印 scope / 计数 / digest（⛔ 不导出取值）")
    _add_dataset_arguments(verify)
    verify.set_defaults(handler=_command_verify)

    export = commands.add_parser("export", help="导出带 scope 标签的 Case A 数据集 JSON")
    _add_dataset_arguments(export)
    export.add_argument("--out", required=True, help="输出 JSON 路径（⛔ 不要写进仓库）")
    export.add_argument("--force", action="store_true", help="显式允许覆盖已存在的输出文件")
    export.set_defaults(handler=_command_export)

    smoke = commands.add_parser("smoke", help="Case A offerings + 手工课表 → RestrictedPlanner")
    _add_dataset_arguments(smoke)
    smoke.add_argument("--current-schedule", required=True, help="手工录入的 CourseOffering[] JSON")
    smoke.add_argument("--preference", required=True, help="public Preference JSON")
    smoke.add_argument(
        "--makeup-tasks",
        help=(
            "Curriculum 交接的 public MakeupTask[] JSON；缺省时复用 runtime 的 Curriculum 装配"
            "（APP_CASE_A_CURRICULUM_CASE_PATH）"
        ),
    )
    smoke.set_defaults(handler=_command_smoke)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except CaseAScopeError as exc:
        # 错误类别是机器可读的；消息只含结构性定位信息。
        return _fail(
            f"Case A scoped 数据集无法安全构造（category={exc.category}"
            + (f" shard={exc.shard_id}" if exc.shard_id else "")
            + "）",
            code=EXIT_CASE_SCOPE,
        )
    except CourseDataNormalizationError as exc:
        return _fail(f"Course Data 领域错误（{type(exc).__name__}）", code=EXIT_CASE_SCOPE)
    except ValueError as exc:
        return _fail(str(exc), code=EXIT_INPUT)
    except OSError:
        return _fail("本地文件读写失败（不回显路径）", code=EXIT_INPUT)


if __name__ == "__main__":
    raise SystemExit(main())
