"""真实培养方案 / 已修课程数据接入后的**一键端到端验收**脚本。

```text
用法（在 backend/ 目录下，需要先用 APP_PERSONAL_CATALOG_DIR 指定目录）：

# A. 合成（默认）：用仓库内的人工构造夹具，⛔ 不代表真实数据
python -m tests.verify_real_data_e2e --mode synthetic

# B. 已核验真实数据：指向负责人交付的目录
python -m tests.verify_real_data_e2e --mode verified --catalog-dir <目录> --student <student.json>
```

## 这个脚本做什么

它**只发真实 HTTP 请求**给正在运行的后端，逐步检查"数据接入是否真的打通"：

1. `GET  /api/v1/personal-planning/curriculum-versions` —— 目录是否被读到、有哪些可选版本；
2. `POST /api/v1/personal-planning/plan` —— 已修记录能否变成 `MakeupTask[]`；
3. 报告 `planning` / `planning_skipped_code` —— 课程数据（教学班）是否也已接入。

## ⛔ 边界（不允许多走一步）

- ⛔ 不伪造学校正式培养方案；
- ⛔ 不编造学生已修课程；
- ⛔ 不把合成数据标成真实数据：`--mode synthetic` 的输出里会显式打印
  `CLAIM LEVEL: SYNTHETIC`，并在发现 `mock://` 标记时把它列为"不得当作真实结果"的证据；
- ⛔ 不修改 `App` 的任何状态，也不引入"没有数据就回退 Case A"的行为。

## 与既有测试的关系

`tests/test_synthetic_production_e2e.py` 覆盖**同一条链路的进程内**合成验证
（含 Capture Bundle → 校区验收 → 全学期验收 → SQLite → `/api/v1/plan`）。
本脚本是它的**对外可执行对照**：站在"数据刚到、要验收"的人的角度，
用 HTTP + 命令行把同一件事跑一遍，并且**明确标出哪一步在用合成数据**。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# 允许直接 `python tests/verify_real_data_e2e.py`
try:
    from tests import personal_fixtures
except ImportError:  # pragma: no cover - 直接运行脚本时的兜底
    sys.path.insert(0, str(_BACKEND_ROOT))
    from tests import personal_fixtures  # type: ignore[no-redef]

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_MOCK_MARKER = "mock://"
_SYNTHETIC_NOTE = (
    "本目录的 source_id / evidence 含 mock:// 标记：**人工构造数据**，"
    "⛔ 不得作为真实教务数据或真实课程认定结果展示。"
)


class VerificationError(RuntimeError):
    """验收失败（面向操作者的可读信息，不含任何个人数据）。"""


def _get(base_url: str, path: str) -> tuple[int, object]:
    request = urllib.request.Request(f"{base_url}{path}", method="GET")
    return _send(request)


def _post(base_url: str, path: str, payload: dict) -> tuple[int, object]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    return _send(request)


def _send(request: urllib.request.Request) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, {"raw": body[:400]}


def _contains_mock_marker(payload: object) -> bool:
    return _MOCK_MARKER in json.dumps(payload, ensure_ascii=False)


def _load_catalog_payload(catalog_dir: Path) -> dict:
    path = catalog_dir / "catalog.json"
    if not path.is_file():
        raise VerificationError(
            f"目录里没有 catalog.json：{catalog_dir}（请先按接入指南放置已核验目录）"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VerificationError("catalog.json 顶层必须是对象")
    return payload


def _run_check(
    *,
    base_url: str,
    old_version_id: str,
    target_version_id: str,
    student: dict,
    label: str,
    semester: str | None,
) -> dict:
    """对一位学生跑一次个人规划，返回结论字典。"""

    payload = {
        "old_version_id": old_version_id,
        "target_version_id": target_version_id,
        "semester": semester,
        "student": student,
        "current_schedule": [],
    }
    status, body = _post(base_url, "/api/v1/personal-planning/plan", payload)
    if status != 200:
        raise VerificationError(f"[{label}] 个人规划返回 HTTP {status}：{json.dumps(body, ensure_ascii=False)[:300]}")
    if not isinstance(body, dict):
        raise VerificationError(f"[{label}] 个人规划响应不是对象")

    makeup_tasks = body.get("makeup_tasks") or []
    status_counts = body.get("status_counts") or {}
    planning = body.get("planning")
    skipped = body.get("planning_skipped_code") or body.get("planning_skipped_reason")

    task_ids = {task.get("course_id") for task in makeup_tasks if isinstance(task, dict)}
    if not makeup_tasks:
        raise VerificationError(f"[{label}] 没有产出任何 MakeupTask —— 数据可能没被真正读到")

    return {
        "label": label,
        "http_status": status,
        "data_source": body.get("data_source"),
        "completed_source_id": body.get("completed_source_id"),
        "makeup_task_count": len(makeup_tasks),
        "makeup_course_ids": sorted(item for item in task_ids if item),
        "status_counts": status_counts,
        "planning_ready": planning is not None,
        "planning_skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真实数据接入后的端到端验收")
    parser.add_argument("--mode", choices=("synthetic", "verified"), default="synthetic")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--catalog-dir", default=None, help="verified 模式：catalog.json 所在目录")
    parser.add_argument("--student", action="append", default=[], help="verified 模式：student.json（可多个）")
    parser.add_argument("--semester", default=None, help="可选：用于触发 Planner 的学期")
    args = parser.parse_args(argv)

    print("=" * 72)
    print("个人规划真实数据接入验收")
    print(f"模式：{args.mode}")
    print(f"后端：{args.base_url}")
    print("=" * 72)

    if args.mode == "synthetic":
        # ⚠️ 合成模式必须把目录接到**后端正在用的那个目录**上，
        # 否则验收会因为"目录里没有 catalog.json"而空跑（本轮真实踩到过）。
        tmp_dir = Path(args.catalog_dir) if args.catalog_dir else Path(_REPO_ROOT) / "backend" / "tests" / "_tmp_verify"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        catalog_dir = personal_fixtures.write_catalog(tmp_dir, name="catalog.json").parent
        students = [
            ("student-one", personal_fixtures.student_one_input()),
            ("student-two", personal_fixtures.student_two_input()),
        ]
        old_version_id = personal_fixtures.OLD_VERSION_ID
        target_version_id = personal_fixtures.TARGET_VERSION_ID
        print("CLAIM LEVEL: SYNTHETIC —— 以下全部为人工构造数据，⛔ 不代表真实教务数据")
    else:
        if not args.catalog_dir:
            raise SystemExit("--mode verified 需要 --catalog-dir")
        if not args.student:
            raise SystemExit("--mode verified 需要至少一个 --student")
        catalog_dir = Path(args.catalog_dir)
        students = []
        for index, path in enumerate(args.student, start=1):
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            students.append((f"student-{index}", payload))
        old_version_id = ""
        target_version_id = ""
        print("CLAIM LEVEL: VERIFIED-INPUT —— 输入的来源由负责人保证，⛔ 本脚本不自行认定")

    catalog_payload = _load_catalog_payload(catalog_dir)
    if _contains_mock_marker(catalog_payload):
        print(f"\n⚠️  {_SYNTHETIC_NOTE}")
    if args.mode == "verified":
        versions = catalog_payload.get("versions") or []
        if len(versions) != 2:
            raise SystemExit(
                f"verified 模式需要正好 2 个版本（源专业 + 目标专业），当前 {len(versions)} 个"
            )
        old_version_id = str(versions[0].get("version_id") or "")
        target_version_id = str(versions[1].get("version_id") or "")
        for entry in versions:
            verification = entry.get("verification") or {}
            if verification.get("verified") is not True:
                raise SystemExit(
                    f"版本 {entry.get('version_id')!r} 的 verification.verified 不是 true —— "
                    "⛔ 未核验的目录不得进入验收"
                )

    print(f"\n目录：{catalog_dir}")
    print(f"源版本：{old_version_id}")
    print(f"目标版本：{target_version_id}")

    # ---- 步骤 1：目录是否被后端读到 ----
    print("\n[1/3] GET /api/v1/personal-planning/curriculum-versions")
    status, body = _get(args.base_url, "/api/v1/personal-planning/curriculum-versions")
    if status != 200:
        detail = json.dumps(body, ensure_ascii=False)
        raise SystemExit(
            f"❌ HTTP {status} —— 后端没有读到目录。{detail[:300]}\n"
            "   请确认后端进程的 APP_PERSONAL_CATALOG_DIR 指向该目录后重启。"
        )
    version_ids = [item.get("version_id") for item in (body or {}).get("versions", [])]
    print(f"    ✅ 可选版本 {len(version_ids)} 个：{version_ids}")
    if old_version_id not in version_ids or target_version_id not in version_ids:
        raise SystemExit(
            "❌ 期望的两个版本不在可选列表里；检查 version_id 与目录内容是否一致"
        )

    # ---- 步骤 2：已修记录 → MakeupTask ----
    print("\n[2/3] POST /api/v1/personal-planning/plan（逐位学生）")
    results = []
    for label, student in students:
        result = _run_check(
            base_url=args.base_url,
            old_version_id=old_version_id,
            target_version_id=target_version_id,
            student=student,
            label=label if isinstance(label, str) else label.__name__,
            semester=args.semester,
        )
        results.append(result)
        print(
            f"    ✅ {result['label']}：{result['makeup_task_count']} 个补修任务 "
            f"（{', '.join(result['makeup_course_ids'])}），"
            f"status_counts={result['status_counts']}"
        )

    # ---- 步骤 3：课程数据（教学班）是否也已接入 ----
    print("\n[3/3] 检查规划是否真的执行（课程数据 / Planner）")
    for result in results:
        if result["planning_ready"]:
            print(f"    ✅ {result['label']}：已产出规划结果（教学班数据已接入）")
        else:
            print(
                f"    ⚠️  {result['label']}：补修任务正常，但**没有**规划结果"
                f"（planning_skipped_code={result['planning_skipped']}）"
            )
            print(
                "       这属于**如实失败**：课程数据（教学班）尚未接入，"
                "需要先完成五校区采集与全学期验收。"
            )

    print("\n" + "=" * 72)
    print("结论")
    print("=" * 72)
    print(json.dumps({"mode": args.mode, "results": results}, ensure_ascii=False, indent=2))
    if args.mode == "synthetic":
        print(f"\n{_SYNTHETIC_NOTE}")
    print("提醒：本脚本 ⛔ 不判定课程认定是否成立、⛔ 不替代人工确认。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
