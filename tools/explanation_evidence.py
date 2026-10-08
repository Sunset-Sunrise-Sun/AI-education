"""仓库根目录脚本：用**已存在的真实 Mock 数据**跑一次解释接口并打印复现证据。

用途（Final Upgrade · Agent B 交付证据）：
- 不修改任何数据、不写文件、不联网；
- 只用 FastAPI TestClient 调用 `POST /api/v1/explanation/plan`；
- 打印：解释条目、生成方式、来源概况、方案指纹、待人工确认数量。

运行（在 `backend/` 目录下）：
    python ../tools/explanation_evidence.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import mock_service  # noqa: E402

EXPLANATION_PATH = "/api/v1/explanation/plan"


def build_payload() -> dict[str, object]:
    return {
        "plan_result": mock_service.load_plan_result().model_dump(mode="json"),
        "makeup_tasks": [
            task.model_dump(mode="json") for task in mock_service.load_makeup_tasks()
        ],
        "course_offerings": [
            offering.model_dump(mode="json") for offering in mock_service.load_course_offerings()
        ],
    }


def main() -> int:
    payload = build_payload()

    with TestClient(app) as client:
        response = client.post(EXPLANATION_PATH, json=payload)
        # 只读性：同一请求重复调用必须完全一致（解释不携带任何随机性 / 不修改输入）
        second = client.post(EXPLANATION_PATH, json=payload)

    print(f"POST {EXPLANATION_PATH} -> HTTP {response.status_code}")
    if response.status_code != 200:
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
        return 1

    body = response.json()
    print(f"contract_version      : {body['contract_version']}")
    print(f"plan_result_digest    : {body['plan_result_digest']}")
    print(f"generator_kind        : {body['generation']['generator_kind']}")
    print(f"model_configured      : {body['generation']['model_configured']}")
    print(f"makeup_task_count     : {body['source_summary']['makeup_task_count']}")
    print(f"course_offering_count : {body['source_summary']['course_offering_count']}")
    print(f"contains_mock_marker  : {body['source_summary']['contains_mock_marker']}")
    print(f"warnings              : {len(body['warnings'])}")
    print(f"items                 : {len(body['items'])}")
    print(f"repeatable            : {body == second.json()}")

    print("\n--- items ---")
    for item in body["items"]:
        confirmations = len(item["requires_human_confirmation"])
        strong = len(item["strong_evidence"])
        premise = len(item["premise_evidence"])
        print(
            f"[{item['kind']:<14}] {item['code']:<38} "
            f"strong={strong} premise={premise} confirm={confirmations} "
            f"generator={item['generation']['generator_kind']}"
        )
        print(f"    {item['title']}")
        print(f"    {item['answer'][:160]}")

    print("\n--- evidence sample (first item) ---")
    for reference in body["items"][0]["strong_evidence"] + body["items"][0]["premise_evidence"]:
        print(
            f"    {reference['kind']:<12} {reference['source_object']}.{reference['source_field']}"
            f" = {reference['raw_value'][:80]}"
        )

    print("\n--- confirmations sample (first item) ---")
    for requirement in body["items"][0]["requires_human_confirmation"]:
        print(f"    {requirement['reason']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
