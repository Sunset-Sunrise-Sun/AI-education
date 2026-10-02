"""Run an artificial Demo or inspect private Curriculum inputs using counts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from app.curriculum import CourseIdStatus, CurriculumNormalizationError
from app.curriculum.case import CurriculumCaseProvider, demo_output, load_curriculum_case
from app.curriculum.json_reader import load_json_input
from app.curriculum.xlsx_reader import load_completed_courses_xlsx


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # Argument errors may otherwise echo private file paths from argv.
        self.exit(2, "参数无效，请运行 --help 查看用法。\n")


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(prog="python -m app.curriculum", description="运行 Curriculum Demo 或检查本地输入。")
    parser.add_argument("path", nargs="?", help="仓库外的私有 D4 XLSX 路径")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="计算人工案例，输出 Mock 任务")
    mode.add_argument("--case", dest="case_path", help="检查本地结构化 JSON case，只输出统计")
    mode.add_argument("--inspect-case", dest="inspect_path", help="检查待确认 case 的内部问题，只输出统计")
    mode.add_argument("--docx", dest="docx_path", help="按明确列映射检查本地 Word 表格，只输出统计")
    parser.add_argument("--profile", help="Word 列映射 JSON，包含 source_id 和 tables")
    parser.add_argument("--source-id", help="D4 交接来源编号")
    args = parser.parse_args(argv)
    if args.docx_path is not None:
        if args.path is not None or args.source_id is not None or args.profile is None:
            parser.error("docx profile is required")
    elif args.demo or args.case_path is not None or args.inspect_path is not None:
        if args.path is not None or args.source_id is not None or args.profile is not None:
            parser.error("mixed input modes")
    elif args.path is None or args.source_id is None or args.profile is not None:
        parser.error("D4 path and source are required")

    try:
        if args.demo:
            print(json.dumps(demo_output(), ensure_ascii=False, indent=2))
            return 0
        if args.docx_path is not None:
            from app.curriculum.docx_reader import load_curriculum_docx

            profile = load_json_input(args.profile, label="docx profile")
            if not isinstance(profile, dict) or set(profile) != {"source_id", "tables"}:
                raise CurriculumNormalizationError("docx profile: expected source_id and tables")
            result = load_curriculum_docx(args.docx_path, **profile)
            print(json.dumps({
                "rows": len(result.rows),
                "unresolved_rows": sum(bool(row.issues) for row in result.rows),
                "issue_counts": dict(Counter(issue.code for issue in result.issues)),
                "conversion_ready": not result.issues,
            }, ensure_ascii=False))
            return 0
        if args.inspect_path is not None:
            provider = CurriculumCaseProvider(load_curriculum_case(args.inspect_path))
            print(json.dumps(provider.get_validation_summary(), ensure_ascii=False))
            return 0
        if args.case_path is not None:
            case = load_curriculum_case(args.case_path)
            tasks = CurriculumCaseProvider(case).get_makeup_tasks()
            print(json.dumps({
                "data_source": case.data_source.value,
                "completed_records": len(case.completed),
                "makeup_task_count": len(tasks),
                "status_counts": dict(Counter(task.status.value for task in tasks)),
            }, ensure_ascii=False))
            return 0
        courses = load_completed_courses_xlsx(args.path, source_id=args.source_id)
    except CurriculumNormalizationError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    confirmed = sum(course.course_id_status is CourseIdStatus.CONFIRMED for course in courses)
    print(json.dumps({
        "records": len(courses),
        "confirmed_course_ids": confirmed,
        "pending_course_ids": len(courses) - confirmed,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
