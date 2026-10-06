"""比赛演示用 **Synthetic** 教学班快照生成器（Course Data 输入侧，仅演示）。

## 这个工具做什么

生成五个校区的 **Capture Bundle**（`sysu-opening-courses-capture-v1` 形状），
供既有整学期验收链路（`tools/prepare_real_case_a_runtime.py`）使用：

```text
本工具：合成 5 个 campus bundle + 披露文件（Synthetic 演示快照）
   ↓  （既有、未修改的验收链路）
tools/prepare_real_case_a_runtime.py  →  整学期 acceptance  →  SQLite  →  runtime env
   ↓
POST /api/v1/plan（真实链路：Curriculum Case A → Diff → MakeupTask → Planner → PlanResult）
```

## 边界（很重要，⛔）

- ⛔ **不产生任何真实数据**：行内容全部由本脚本按确定性规则合成，
  教学班号统一带 `DEMO-` 前缀、场地标注 `DEMO`，不可能被误认为真实教学班；
- ⛔ **不写库、不产生 acceptance、不声称 ready**：库与 runtime env 一律由既有验收链路生成；
- ⛔ **不改任何 frozen 语义**：不碰 `backend/app/course_data/**`、
  `backend/app/services/planning_runtime.py`、Course Data trust chain、公共 Schema；
- ⛔ **不绕过完整性**：仍然要求**全部五个已批准校区**都有行，
  并且仍然必须通过既有 full-semester acceptance 才会被运行时读取；
- ⛔ **不冒充真实来源**：披露文件里显式记录 `synthetic: true`、
  以及课程号来源（真实 Case A manifest / 显式课程号自检），
  ⛔ 不包含任何本地路径、不包含任何学生数据。

## 课程号从哪里来

- `--case <已批准 Case A manifest>`（**推荐**）：调用**既有** Curriculum 装载与
  `CurriculumCaseProvider.get_makeup_tasks()`，把「除 `satisfied` 之外的评估条目」的课程号
  作为演示教学班的课程号 —— 这样演示快照与真实培养方案分析结果是对齐的，
  课程号映射不是本工具自己发明的；
- `--course-id <课程号>`（可重复；**仅用于离线自检**）：不读 Case，直接为给定课程号生成行。

⚠️ 当 `--case` 指向的 manifest 自身 `data_source != "real"`（例如仓库内的 Mock 演示 case）时，
本工具**照常生成快照**，但在披露文件中如实记录 `case_data_source`，
并在 stderr 警告「Curriculum 侧不是真实来源」——⛔ 不会把它包装成真实来源。

## 确定性

同一组输入（`--semester` + 课程号集合 + `--classes-per-course`）⇒ **逐字节相同**的输出：
⛔ 不使用随机数、⛔ 不写入时间戳、行与键顺序固定。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 快照与披露文件已写出 |
| 2 | 参数非法（学期形态 / 输出目录 / 课程号来源冲突） |
| 3 | 课程号来源非法（Case 不可读 / 不可解析 / 无可用课程号） |
| 4 | 校区覆盖无法满足（可用课程号少于已批准校区数） |
| 5 | 目标文件已存在（⛔ 不静默覆盖；需显式 `--overwrite`）或写入失败 |
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import NoReturn, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.course_data import (  # noqa: E402
    APPROVED_FULL_SEMESTER_SHARDS,
    campus_source_label,
)

EXIT_OK = 0
EXIT_ARGUMENTS = 2
EXIT_COURSE_SOURCE = 3
EXIT_SHARD_COVERAGE = 4
EXIT_OUTPUT = 5

#: 输出 bundle 的格式名（与既有捕获 bundle 完全一致；⛔ 不新造格式）。
BUNDLE_FORMAT = "sysu-opening-courses-capture-v1"

#: 披露文件格式 / 版本（本地演示产物，⛔ 不是公共 API Schema）。
DISCLOSURE_FORMAT = "xuehang-competition-demo-snapshot-v1"
DISCLOSURE_VERSION = 1

#: 必须逐字出现在披露文件与前端上的标签。
DISCLOSURE_LABEL = "教学班数据：演示快照（Synthetic）"

#: 披露文件里的「不是」清单（⛔ 避免任何过度声明）。
DISCLOSURE_NOT_CLAIMS: tuple[str, ...] = (
    "不是真实教务系统数据，也不是真实教务系统抓取结果",
    "不构成任何选课 / 注册 / 可执行性依据",
    "不代表 Real E2E（LEVEL2 / LEVEL3）证据；它只是被明确标识的演示快照",
    "不表示任何校区（尤其北校园）的采集能力已可用",
)

#: 学期形态与前端一致（`^\\d{4}-[12]$`）。
_SEMESTER_RE = re.compile(r"\A\d{4}-[12]\Z")

#: 教学班号 / 场地的合成标记（⛔ 保证任何一行都能被一眼识别为演示数据）。
CLASS_PREFIX = "DEMO-"
LOCATION_TOKEN = "DEMO"

#: 合成上课时间使用的星期 token（⛔ 只使用 schedule parser 的已批准白名单写法）。
_WEEKDAYS: tuple[str, ...] = ("星期一", "星期二", "星期三", "星期四", "星期五")

#: 合成上课时间使用的节次 token（`第N-M节` 形状，与真实证据一致）。
_SECTIONS: tuple[str, ...] = ("第1-2节", "第3-4节", "第5-6节", "第7-8节")

#: 每周次数量（`N-M周` 形状）。
_WEEKS = "1-16周"

#: 校区展示名（仅用于合成排课字符串里的地点 token，⛔ 不代表采集范围变化）。
_CAMPUS_LABEL: dict[str, str] = {
    "east-campus": "东校园",
    "south-campus": "南校园",
    "shenzhen-campus": "深圳校区",
    "zhuhai-campus": "珠海校区",
    "north-campus": "北校园",
}

#: 每 N 行省略 `teachingTimePlaceStr`（→ `meetings = []`，演示「当前数据中无排课信息」）。
_UNSCHEDULED_EVERY = 4


class CliArgumentError(RuntimeError):
    """argparse 失败被规范化成结构化、不回显输入的 CLI 错误。"""


class SnapshotFailure(Exception):
    """结构化失败：退出码 + 不回显敏感内容的最小 category。"""

    def __init__(self, exit_code: int, category: str, *, detail: dict[str, object] | None = None) -> None:
        super().__init__(category)
        self.exit_code = exit_code
        self.payload: dict[str, object] = {"status": "failed", "category": category}
        if detail:
            self.payload.update(detail)


class SafeArgumentParser(argparse.ArgumentParser):
    """把 argparse 的报错转成 `CliArgumentError`（⛔ 不回显用户输入）。"""

    def error(self, message: str) -> NoReturn:  # noqa: ARG002 - intentionally suppressed
        raise CliArgumentError("invalid arguments")


def _build_parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(
        description=(
            "Generate a deterministic, explicitly-labeled SYNTHETIC CourseOffering demo snapshot "
            "(five campus bundles) for the competition demo. This tool never writes a store, never "
            "produces an acceptance, and never claims readiness."
        )
    )
    parser.add_argument("--out-dir", required=True, help="output directory (created when absent)")
    parser.add_argument("--semester", required=True, help="target semester, e.g. 2026-1")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--case",
        help="approved Case A manifest path: course ids come from its makeup-task projection",
    )
    source.add_argument(
        "--course-id",
        action="append",
        default=None,
        help="explicit course id (repeatable; offline self-check only, no Case is read)",
    )
    parser.add_argument(
        "--classes-per-course",
        type=int,
        default=2,
        help="number of synthetic classes per course (default: 2)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing output files (default: refuse, so a stale snapshot cannot be reused)",
    )
    parser.add_argument("--quiet", action="store_true", help="print only the JSON summary")
    return parser


def _fail(exit_code: int, category: str, *, detail: dict[str, object] | None = None) -> NoReturn:
    raise SnapshotFailure(exit_code, category, detail=detail)


def _courses_from_case(case_path: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    """用**既有** Curriculum 装载与投影取出课程号（⛔ 本工具不复刻培养方案语义）。"""

    try:
        from app.curriculum.case import CurriculumCaseProvider, load_curriculum_case
    except ImportError:  # pragma: no cover - 只在环境损坏时发生
        _fail(EXIT_COURSE_SOURCE, "curriculum_module_unavailable")

    if not case_path.is_file():
        _fail(EXIT_COURSE_SOURCE, "case_manifest_missing")

    try:
        case = load_curriculum_case(case_path)
    except Exception:  # noqa: BLE001 - 装载失败一律归为课程号来源不可用（⛔ 不回显异常文本）
        _fail(EXIT_COURSE_SOURCE, "case_manifest_unreadable")

    try:
        tasks = list(CurriculumCaseProvider(case).get_makeup_tasks())
    except Exception:  # noqa: BLE001 - 投影失败同上
        _fail(EXIT_COURSE_SOURCE, "case_projection_failed")

    courses: dict[str, dict[str, str]] = {}
    status_counts: dict[str, int] = {}
    for task in tasks:
        status = getattr(task.status, "value", str(task.status))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "satisfied":
            # ⛔ 已满足的条目不需要教学班供给：只为「仍需处理」的条目生成演示班级。
            continue
        course_id = str(task.course_id)
        courses.setdefault(
            course_id,
            {
                "course_id": course_id,
                "course_name": str(task.course_name),
                "credit": f"{float(task.credit):g}",
            },
        )

    if not courses:
        _fail(EXIT_COURSE_SOURCE, "no_courses_after_projection", detail={"status_counts": status_counts})

    case_meta: dict[str, object] = {
        "kind": "case_manifest",
        "case_artifact_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
        "case_data_source": str(getattr(case.data_source, "value", case.data_source)),
        "makeup_task_status_counts": dict(sorted(status_counts.items())),
        "courses_included": "status != satisfied",
    }
    return [courses[key] for key in sorted(courses)], case_meta


def _courses_from_ids(course_ids: Sequence[str]) -> tuple[list[dict[str, str]], dict[str, object]]:
    unique = sorted({value.strip() for value in course_ids if value.strip()})
    if not unique:
        _fail(EXIT_COURSE_SOURCE, "no_course_ids_given")
    courses = [
        {"course_id": course_id, "course_name": f"演示课程 {course_id}", "credit": "3"}
        for course_id in unique
    ]
    return courses, {
        "kind": "explicit_course_ids",
        "courses_included": "explicitly listed",
        "self_check_only": True,
    }


def _meeting(course_index: int, class_index: int, campus_label: str) -> str:
    """合成一段可被既有 schedule parser 解析的排课字符串（形如 5 字段 A）。"""

    weekday = _WEEKDAYS[(course_index + class_index) % len(_WEEKDAYS)]
    sections = _SECTIONS[(course_index * 2 + class_index) % len(_SECTIONS)]
    # weeks / weekday / sections / location / activity（与真实 5 字段 A 同构）
    return f"{_WEEKS}/{weekday}/{sections}/{LOCATION_TOKEN}{campus_label}/DEMO演示环节,"


def _row(
    course: dict[str, str],
    *,
    course_index: int,
    class_index: int,
    campus_label: str,
    scheduled: bool,
) -> dict[str, object]:
    limit_number = 60 + (course_index % 5) * 10
    row: dict[str, object] = {
        "courseNum": course["course_id"],
        "courseName": course["course_name"],
        "classNumber": f"{CLASS_PREFIX}{course['course_id']}-{class_index + 1}",
        "yearTerm": None,  # 由调用方填入 semester（保持键顺序稳定）
        "score": course["credit"],
        "limitNumber": limit_number,
        "selectedNumber": max(limit_number - 5 - (course_index % 3), 0),
    }
    if scheduled:
        row["teachingTimePlaceStr"] = _meeting(course_index, class_index, campus_label)
    return row


def _bundle(semester: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "format": BUNDLE_FORMAT,
        "semester": semester,
        "first_page_no": 1,
        "page_size": 200,
        "pages": [
            {
                "page_no": 1,
                "response": {"code": 200, "data": {"total": len(rows), "rows": rows}},
            }
        ],
    }


def _dumps(document: object) -> bytes:
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write(path: Path, payload: bytes, *, overwrite: bool) -> str:
    if path.exists() and not overwrite:
        _fail(EXIT_OUTPUT, "output_file_already_exists", detail={"file_name": path.name})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except OSError:
        _fail(EXIT_OUTPUT, "output_write_failed", detail={"file_name": path.name})
    return hashlib.sha256(payload).hexdigest()


def _next_commands(
    *,
    semester: str,
    baseline: int,
    bundle_names: dict[str, str],
    shard_numbers: dict[str, str],
) -> list[str]:
    """生成下一步命令；⛔ 一律使用 `<OUT_DIR>` 占位符，不把本地绝对路径写进产物。"""

    draft_inventory = "<OUT_DIR>/capture-inventory.draft.json"
    shard_args = " ".join(
        f"{option} <OUT_DIR>/{name}" for _shard_id, option, name in _shard_argv(bundle_names)
    )
    validate = [
        "# 第 0 步（可选）：离线校验 5 个 bundle（source label 为 campus 的 canonical 值）",
        *[
            "python tools/validate_course_data_artifact.py "
            f"--bundle <OUT_DIR>/{bundle_names[shard_id]} --expected-semester {semester} "
            f"--scope-id {shard_numbers[shard_id]} "
            f"--source {campus_source_label(semester, shard_numbers[shard_id])}"
            for shard_id in bundle_names
        ],
    ]
    return validate + [
        "# 第 1 步：生成草稿 capture inventory（与真实两步流程一致）",
        "python tools/prepare_real_case_a_runtime.py "
        f"--semester {semester} --baseline-before {baseline} --baseline-after {baseline} "
        f"{shard_args} --draft-inventory-out {draft_inventory} "
        "--campus-store <OUT_DIR>/campus-acceptances.sqlite3 --sqlite <OUT_DIR>/course-data.sqlite3",
        "# 第 2 步：用草稿 inventory 跑正式 acceptance（真实 Curriculum 侧由操作者提供）",
        "python tools/prepare_real_case_a_runtime.py "
        f"--semester {semester} --baseline-before {baseline} --baseline-after {baseline} "
        f"{shard_args} --inventory {draft_inventory} "
        "--campus-store <OUT_DIR>/campus-acceptances.sqlite3 --sqlite <OUT_DIR>/course-data.sqlite3 "
        "--curriculum-case <已批准 Case A manifest> --curriculum-provenance <已批准 provenance.json> "
        "--env-out <OUT_DIR>/runtime.env",
        "# ⛔ 没有已批准 Curriculum provenance 时 status 只会是 partial_ready，"
        "此时不得启动真实运行时；教学班侧仍为 Synthetic 演示快照。",
    ]


def _shard_argv(bundle_names: dict[str, str]) -> list[tuple[str, str, str]]:
    option_by_shard = {
        "east-campus": "--east",
        "south-campus": "--south",
        "shenzhen-campus": "--shenzhen",
        "zhuhai-campus": "--zhuhai",
        "north-campus": "--north",
    }
    return [
        (shard.shard_id, option_by_shard[shard.shard_id], bundle_names[shard.shard_id])
        for shard in APPROVED_FULL_SEMESTER_SHARDS
    ]


def _generate(args: argparse.Namespace) -> dict[str, object]:
    semester = (args.semester or "").strip()
    if not _SEMESTER_RE.match(semester):
        _fail(EXIT_ARGUMENTS, "invalid_semester")

    classes_per_course = args.classes_per_course
    if not isinstance(classes_per_course, int) or classes_per_course < 1 or classes_per_course > 20:
        _fail(EXIT_ARGUMENTS, "invalid_classes_per_course")

    out_dir = Path(args.out_dir)
    if args.case:
        courses, case_meta = _courses_from_case(Path(args.case))
    else:
        courses, case_meta = _courses_from_ids(args.course_id or [])

    shards = list(APPROVED_FULL_SEMESTER_SHARDS)
    if len(courses) < len(shards):
        _fail(
            EXIT_SHARD_COVERAGE,
            "insufficient_courses_for_all_campuses",
            detail={"course_count": len(courses), "required_campus_count": len(shards)},
        )

    assignments: dict[str, list[dict[str, str]]] = {shard.shard_id: [] for shard in shards}
    for index, course in enumerate(courses):
        assignments[shards[index % len(shards)].shard_id].append(course)

    bundle_names = {shard.shard_id: f"{shard.shard_id}.json" for shard in shards}
    files: dict[str, str] = {}
    shard_summary: list[dict[str, object]] = []
    row_counter = 0
    course_index = 0
    total_rows = 0

    for shard in shards:
        campus_label = _CAMPUS_LABEL[shard.shard_id]
        rows: list[dict[str, object]] = []
        course_count = 0
        for course in assignments[shard.shard_id]:
            course_count += 1
            for class_index in range(classes_per_course):
                scheduled = (row_counter + 1) % _UNSCHEDULED_EVERY != 0
                row = _row(
                    course,
                    course_index=course_index,
                    class_index=class_index,
                    campus_label=campus_label,
                    scheduled=scheduled,
                )
                row["yearTerm"] = semester
                rows.append(row)
                row_counter += 1
            course_index += 1
        payload = _dumps(_bundle(semester, rows))
        digest = _write(out_dir / bundle_names[shard.shard_id], payload, overwrite=bool(args.overwrite))
        files[bundle_names[shard.shard_id]] = digest
        total_rows += len(rows)
        shard_summary.append(
            {
                "shard_id": shard.shard_id,
                "opening_school_number": shard.opening_school_number,
                "source_label": campus_source_label(semester, shard.opening_school_number),
                "bundle_file": bundle_names[shard.shard_id],
                "bundle_sha256": digest,
                "row_count": len(rows),
                "course_count": course_count,
                "reported_total": len(rows),
            }
        )

    baseline = total_rows
    disclosure: dict[str, object] = {
        "snapshot_format": DISCLOSURE_FORMAT,
        "snapshot_version": DISCLOSURE_VERSION,
        "synthetic": True,
        "disclosure_label": DISCLOSURE_LABEL,
        "disclosure_notice": (
            "本文件描述的教学班数据由 tools/generate_competition_demo_snapshot.py 确定性合成，"
            "仅用于比赛演示；不是真实教务系统数据，也不构成任何选课 / 注册依据。"
        ),
        "semester": semester,
        "generated_by": "tools/generate_competition_demo_snapshot.py",
        "generator_version": 1,
        "deterministic": True,
        "course_source": case_meta,
        "classes_per_course": classes_per_course,
        "row_synthetic_markers": {"class_number_prefix": CLASS_PREFIX, "location_token": LOCATION_TOKEN},
        "shards": shard_summary,
        "totals": {"row_count": total_rows, "course_count": len(courses), "baseline_total": baseline},
        "not_claims": list(DISCLOSURE_NOT_CLAIMS),
        "still_required": (
            "快照必须通过既有整学期 acceptance（tools/prepare_real_case_a_runtime.py）之后才会被运行时读取；"
            "本工具不写库、不产生 acceptance、不声称 ready。"
        ),
        "bundle_sha256": dict(sorted(files.items())),
        "next_commands": _next_commands(
            semester=semester,
            baseline=baseline,
            bundle_names=bundle_names,
            shard_numbers={
                item["shard_id"]: str(item["opening_school_number"]) for item in shard_summary
            },
        ),
    }
    _write(out_dir / "DEMO_SNAPSHOT_DISCLOSURE.json", _dumps(disclosure), overwrite=bool(args.overwrite))

    return {
        "status": "synthetic_snapshot_written",
        "synthetic": True,
        "disclosure_label": DISCLOSURE_LABEL,
        "semester": semester,
        "out_dir": out_dir.as_posix(),
        "row_count": total_rows,
        "course_count": len(courses),
        "baseline_total": baseline,
        "case_data_source": case_meta.get("case_data_source"),
        "shard_row_counts": {item["shard_id"]: item["row_count"] for item in shard_summary},
        "bundle_sha256": dict(sorted(files.items())),
        "next_commands": disclosure["next_commands"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        summary = _generate(args)
    except CliArgumentError:
        print(
            json.dumps({"status": "invalid_arguments"}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return EXIT_ARGUMENTS
    except SnapshotFailure as failure:
        print(json.dumps(failure.payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return failure.exit_code

    if summary.get("case_data_source") not in (None, "real"):
        print(
            json.dumps(
                {
                    "warning": "curriculum_side_is_not_real",
                    "case_data_source": summary.get("case_data_source"),
                    "note": (
                        "the course ids came from a manifest that is NOT marked real: "
                        "the teaching-class side is synthetic and the curriculum side is not real"
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )

    if not args.quiet:
        print(f"✅ 已写出 Synthetic 教学班演示快照：{summary['out_dir']}")
        print(f"   披露标签：{DISCLOSURE_LABEL}")
        print(f"   学期：{summary['semester']}｜教学班行：{summary['row_count']}｜课程数：{summary['course_count']}")
        print(f"   各校区行数：{json.dumps(summary['shard_row_counts'], ensure_ascii=False)}")
        print("   下一步（⛔ 本工具不写库、不声称 ready）：")
        for line in summary["next_commands"]:  # type: ignore[union-attr]
            print(f"     {line.replace('<OUT_DIR>', str(summary['out_dir']))}")

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
