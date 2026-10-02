"""Read a private D4 workbook and print counts only."""

from __future__ import annotations

import argparse
import json
import sys

from app.curriculum import CourseIdStatus, CurriculumNormalizationError
from app.curriculum.xlsx_reader import load_completed_courses_xlsx


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # Argument errors may otherwise echo private file paths from argv.
        self.exit(2, "参数无效，请运行 --help 查看用法。\n")


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(prog="python -m app.curriculum", description="本地检查 D4 脱敏课程表。")
    parser.add_argument("path", help="仓库外的私有 XLSX 路径")
    parser.add_argument("--source-id", required=True, help="交接时提供的来源编号")
    args = parser.parse_args(argv)

    try:
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
