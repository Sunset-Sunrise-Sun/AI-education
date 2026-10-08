"""可复现演示：同一已支持目标方案 + 两份**独立** Mock 成绩输入 → 不同状态。

用法（在 `backend/` 下）：

    $env:PYTHONUTF8 = "1"
    python tools/repro_personal_planning.py

它证明的是"**输入差异 → 可解释的不同状态**"这件事本身：

- 学生一：TGT100 / TGT101 都有本人已通过记录 → `satisfied`；
- 学生二：只有 TGT100 → TGT101 是 `required`（并给出具体原因文本）；
- 两位学生的 `completed_source_id` 不同（由请求体内容派生）。

⚠️ 全部输入为人工构造的 Mock（`tests/personal_fixtures.py`），
不是学校正式条款，也不是任何真实学生的材料。
**当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.contracts import DataSource  # noqa: E402
from app.personal import build_personal_plan, normalize_personal_plan_request  # noqa: E402
from tests.personal_fixtures import (  # noqa: E402
    OLD_VERSION_ID,
    TARGET_VERSION_ID,
    load_catalog,
    student_one_input,
    student_two_input,
)


def run(label: str, student: dict, catalog) -> None:
    request = normalize_personal_plan_request(
        {
            "old_version_id": OLD_VERSION_ID,
            "target_version_id": TARGET_VERSION_ID,
            "student": student,
        },
        catalog=catalog,
        data_source=DataSource.MOCK,
        completed_source_id=f"mock://repro/{label}",
    )
    result = build_personal_plan(catalog, request)
    print(f"--- {label} ---")
    print(f"completed_source_id : {result.completed_source_id}")
    print(f"completed records   : {result.completed_record_count}")
    for task in result.makeup_tasks:
        print(f"  {task.course_id}  {task.status.value:<20} {task.reason}")
    print(f"planning skipped    : {result.planning_skipped_reason}")
    print()


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="personal-repro-"))
    catalog = load_catalog(tmp)
    print("selectable versions:", catalog.version_ids())
    print()
    run("student-one", student_one_input(), catalog)
    run("student-two", student_two_input(), catalog)


if __name__ == "__main__":
    main()
