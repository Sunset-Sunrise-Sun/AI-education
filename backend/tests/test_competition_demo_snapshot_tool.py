"""`tools/generate_competition_demo_snapshot.py` 的 synthetic 测试（⛔ 零网络、⛔ 真实数据）。

覆盖：
- 确定性：同一输入 ⇒ 逐字节相同的五个 campus bundle；
- 完整性：五个**已批准**校区都必须有行，baseline == 行数合计；
- 诚实性：披露文件必须显式 `synthetic: true`、逐字标签、`not_claims` 齐全，
  且⛔ 不泄漏任何本地绝对路径；
- 真实性边界：`--course-id` 自检模式⛔ 不得声称课程号来自真实 Case；
- 安全性：⛔ 不静默覆盖既有文件、⛔ 无网络 / SQLite 依赖、⛔ 不自己写库；
- 兼容性：生成的 bundle 必须能通过**既有** artifact validator（既有解析与完整性规则）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPOSITORY_ROOT / "tools" / "generate_competition_demo_snapshot.py"
VALIDATOR_PATH = REPOSITORY_ROOT / "tools" / "validate_course_data_artifact.py"
SEMESTER = "2026-1"
COURSE_IDS = ("CSE101", "CSE102", "CSE103", "CSE104", "CSE105", "CSE106")


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load(TOOL_PATH, "generate_competition_demo_snapshot")
VALIDATOR = _load(VALIDATOR_PATH, "validate_course_data_artifact")


def _run(tmp_path: Path, out_name: str = "snapshot", *extra: str) -> tuple[int, dict[str, object]]:
    out_dir = tmp_path / out_name
    argv = [
        "--out-dir",
        str(out_dir),
        "--semester",
        SEMESTER,
        *[item for course_id in COURSE_IDS for item in ("--course-id", course_id)],
        "--quiet",
        *extra,
    ]
    code = TOOL.main(argv)
    assert code in (TOOL.EXIT_OK, TOOL.EXIT_OUTPUT, TOOL.EXIT_ARGUMENTS, TOOL.EXIT_SHARD_COVERAGE)
    disclosure = out_dir / "DEMO_SNAPSHOT_DISCLOSURE.json"
    summary: dict[str, object] = {}
    if disclosure.is_file():
        summary = json.loads(disclosure.read_text(encoding="utf-8"))
    return code, summary


def test_generation_is_deterministic_and_covers_all_approved_campuses(tmp_path: Path) -> None:
    first_code, first = _run(tmp_path, "first")
    second_code, second = _run(tmp_path, "second")

    assert first_code == TOOL.EXIT_OK
    assert second_code == TOOL.EXIT_OK
    assert first["bundle_sha256"] == second["bundle_sha256"]

    shards = first["shards"]
    assert [shard["shard_id"] for shard in shards] == [
        "east-campus",
        "south-campus",
        "shenzhen-campus",
        "zhuhai-campus",
        "north-campus",
    ]
    for shard in shards:
        assert shard["row_count"] > 0
        assert shard["reported_total"] == shard["row_count"]
        assert shard["source_label"].startswith(f"capture://sysu/{SEMESTER}/campus/")
    assert first["totals"]["baseline_total"] == sum(shard["row_count"] for shard in shards)


def test_disclosure_is_explicitly_synthetic_and_leaks_no_local_path(tmp_path: Path) -> None:
    code, disclosure = _run(tmp_path)
    assert code == TOOL.EXIT_OK

    assert disclosure["synthetic"] is True
    assert disclosure["disclosure_label"] == "教学班数据：演示快照（Synthetic）"
    assert disclosure["not_claims"]
    assert "不构成任何选课 / 注册 / 可执行性依据" in disclosure["not_claims"]
    assert "not_a_real_capture" not in json.dumps(disclosure)
    assert "本工具不写库、不产生 acceptance、不声称 ready" in disclosure["still_required"]

    raw = json.dumps(disclosure, ensure_ascii=False)
    assert str(tmp_path) not in raw
    assert "Users" not in raw and "C:\\" not in raw


def test_self_check_mode_never_claims_a_real_case(tmp_path: Path) -> None:
    code, disclosure = _run(tmp_path)
    assert code == TOOL.EXIT_OK

    source = disclosure["course_source"]
    assert source["kind"] == "explicit_course_ids"
    assert source["self_check_only"] is True
    assert "case_data_source" not in source
    assert disclosure["row_synthetic_markers"] == {"class_number_prefix": "DEMO-", "location_token": "DEMO"}


def test_generated_bundles_pass_the_existing_artifact_validator(tmp_path: Path) -> None:
    code, disclosure = _run(tmp_path)
    assert code == TOOL.EXIT_OK
    out_dir = tmp_path / "snapshot"

    for shard in disclosure["shards"]:
        validator_code = VALIDATOR.main(
            [
                "--bundle",
                str(out_dir / shard["bundle_file"]),
                "--expected-semester",
                SEMESTER,
                "--scope-id",
                shard["opening_school_number"],
                "--source",
                shard["source_label"],
            ]
        )
        assert validator_code == 0, shard["shard_id"]


def test_rows_are_marked_synthetic_and_include_the_neutral_no_schedule_case(tmp_path: Path) -> None:
    code, disclosure = _run(tmp_path)
    assert code == TOOL.EXIT_OK
    out_dir = tmp_path / "snapshot"

    rows = []
    for shard in disclosure["shards"]:
        bundle = json.loads((out_dir / shard["bundle_file"]).read_text(encoding="utf-8"))
        assert bundle["format"] == "sysu-opening-courses-capture-v1"
        assert bundle["semester"] == SEMESTER
        page = bundle["pages"][0]
        assert page["response"]["data"]["total"] == shard["row_count"]
        rows.extend(page["response"]["data"]["rows"])

    assert rows, "至少要有合成行"
    for row in rows:
        assert row["classNumber"].startswith("DEMO-")
        assert row["yearTerm"] == SEMESTER
        if "teachingTimePlaceStr" in row:
            assert "/DEMO" in row["teachingTimePlaceStr"]
    # 每第 4 行省略 teachingTimePlaceStr ⇒ 规范化后 meetings=[]（演示中性「无排课信息」状态）
    assert any("teachingTimePlaceStr" not in row for row in rows)


def test_existing_output_is_not_overwritten_without_the_flag(tmp_path: Path) -> None:
    assert _run(tmp_path)[0] == TOOL.EXIT_OK

    code, _ = _run(tmp_path)
    assert code == TOOL.EXIT_OUTPUT

    code, _ = _run(tmp_path, "snapshot", "--overwrite")
    assert code == TOOL.EXIT_OK


def test_invalid_semester_and_argument_shape_are_rejected(tmp_path: Path) -> None:
    out_dir = tmp_path / "bad"
    assert TOOL.main(["--out-dir", str(out_dir), "--semester", "26-1", "--course-id", "A"]) == TOOL.EXIT_ARGUMENTS
    assert TOOL.main(["--out-dir", str(out_dir), "--semester", SEMESTER]) == TOOL.EXIT_ARGUMENTS
    assert (
        TOOL.main(
            ["--out-dir", str(out_dir), "--semester", SEMESTER, "--course-id", "A", "--classes-per-course", "0"]
        )
        == TOOL.EXIT_ARGUMENTS
    )
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_fewer_courses_than_approved_campuses_is_refused(tmp_path: Path) -> None:
    code = TOOL.main(
        [
            "--out-dir",
            str(tmp_path / "short"),
            "--semester",
            SEMESTER,
            "--course-id",
            "A",
            "--course-id",
            "B",
            "--quiet",
        ]
    )
    assert code == TOOL.EXIT_SHARD_COVERAGE
    assert not (tmp_path / "short").exists()


def test_tool_has_no_network_or_store_write_surface() -> None:
    source = TOOL_PATH.read_text(encoding="utf-8")

    for forbidden in ("import sqlite3", "import requests", "import urllib", "http.client", "socket"):
        assert forbidden not in source
    # ⛔ 只复用既有 Curriculum 装载与投影；⛔ 不复刻培养方案语义
    assert "from app.curriculum.case import CurriculumCaseProvider, load_curriculum_case" in source
    assert "get_makeup_tasks" in source


def test_mock_ci_fixture_case_cannot_cover_all_campuses(tmp_path: Path) -> None:
    """仓库内 Mock 演示 case 只投影出 4 条可处理条目 ⇒ 必须按覆盖规则拒绝（⛔ 不补造课程）。"""

    case_path = REPOSITORY_ROOT / "mock_data" / "curriculum_demo" / "case.json"
    if not case_path.is_file():  # pragma: no cover - 仓库形状变化时跳过
        pytest.skip("committed mock curriculum case is absent")

    code = TOOL.main(
        [
            "--out-dir",
            str(tmp_path / "from-mock-case"),
            "--semester",
            SEMESTER,
            "--case",
            str(case_path),
            "--quiet",
        ]
    )
    assert code == TOOL.EXIT_SHARD_COVERAGE
