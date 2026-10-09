"""QA 夹具自检：把 qa_demo_data.json 喂给真实受限 Planner，确认能产生候选。

用法（在 backend/ 下）：`python tests/qa_browser_e2e/verify_seed.py`

它验证的是浏览器 E2E 的前提：**夹具 + 真实 Planner = 一个真实的候选**。
⛔ 它不调用任何模型，也⛔ 不代表真实教务数据。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models.contracts import (  # noqa: E402
    CourseOffering,
    MakeupTask,
    PlanResult,
    Preference,
)
from app.planner import RestrictedPlannerProvider  # noqa: E402

SEED = Path(__file__).resolve().parent / "qa_demo_data.json"


def main() -> int:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    tasks = [MakeupTask.model_validate(row) for row in seed["makeup_tasks"]]
    offerings = [CourseOffering.model_validate(row) for row in seed["course_offerings"]]
    base = PlanResult.model_validate(seed["plan_result"])
    preference = Preference.model_validate(seed["preference"])

    selected = {(item.course_id, item.class_id) for item in base.selected_classes}
    current = [
        item for item in offerings if (item.course_id, item.class_id) in selected
    ]
    print(f"makeup_tasks={len(tasks)} offerings={len(offerings)} selected={len(selected)}")
    print(f"current_schedule matched from offerings = {len(current)}")
    missing = selected - {(item.course_id, item.class_id) for item in current}
    if missing:
        print(f"⚠️ 以下已选班次在 offerings 中找不到：{sorted(missing)}")
        return 1

    result = RestrictedPlannerProvider().plan(
        makeup_tasks=tasks, offerings=offerings, current_schedule=current,
        preference=preference,
    )
    print(f"planner status = {result.status.value}")
    print(f"selected       = {[(s.course_id, s.class_id) for s in result.selected_classes]}")
    print(f"changes        = {[(c.course_id, c.to_class) for c in result.changes]}")
    added = sorted(
        (s.course_id, s.class_id) for s in result.selected_classes
    ) != sorted(selected)
    print(f"produces a diff = {added}")
    for item in result.unresolved:
        print(f"  unresolved[{item.type}] {item.message[:60]}")
    if not added:
        print("❌ 夹具不能产生候选：浏览器 E2E 的'候选对比'路径将无法执行")
        return 1
    print("✅ 夹具可产生真实候选（由受限 Planner 计算）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
