"""`tools/prepare_real_case_a_runtime.py` 的 synthetic 端到端测试（⛔ 零网络、⛔ 真实数据）。

覆盖：
- `--preflight` 跑通「五 synthetic bundle → campus acceptance → full-semester acceptance
  → SQLite → provider read-back → runtime env」，并明确标注 LEVEL1；
- 真实模式的两步流程（draft inventory → 人工批准 → acceptance + import + env 输出）；
- fail closed：已有 DB 未显式允许 / bundle 被篡改 / campus 不完整 / env 文件已存在；
- 结构性保证：⛔ 不硬编码已批准校区号、⛔ 无网络与凭据面。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPOSITORY_ROOT / "tools" / "prepare_real_case_a_runtime.py"
SEMESTER = "2026-1"
SHARDS = (
    ("east-campus", "5063559", "--east"),
    ("south-campus", "5062201", "--south"),
    ("shenzhen-campus", "333291143", "--shenzhen"),
    ("zhuhai-campus", "5062203", "--zhuhai"),
    ("north-campus", "5062202", "--north"),
)
ROWS_PER_SHARD = 2


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prepare_real_case_a_runtime", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["prepare_real_case_a_runtime"] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def _row(shard_id: str, index: int) -> dict[str, object]:
    return {
        "courseNum": f"SYN-{shard_id.upper()}-{index:03d}",
        "courseName": f"示例课程 {shard_id} #{index}",
        "classNumber": f"{shard_id}-{index:03d}",
        "yearTerm": SEMESTER,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": "1-16周/星期一/第1-2节/DEMO/示例环节,",
    }


def _bundle(shard_id: str, *, total: int | None = None) -> dict[str, object]:
    rows = [_row(shard_id, index) for index in range(ROWS_PER_SHARD)]
    return {
        "format": "sysu-opening-courses-capture-v1",
        "semester": SEMESTER,
        "first_page_no": 1,
        "page_size": 200,
        "pages": [
            {
                "page_no": 1,
                "response": {
                    "code": 200,
                    "data": {"total": len(rows) if total is None else total, "rows": rows},
                },
            }
        ],
    }


def _write_bundles(directory: Path, *, total_override: dict[str, int] | None = None) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for shard_id, _number, _option in SHARDS:
        payload = _bundle(shard_id, total=(total_override or {}).get(shard_id))
        path = directory / f"{shard_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        paths[shard_id] = path
    return paths


def _base_argv(
    tmp_path: Path,
    *,
    semester: str = SEMESTER,
    bundles: dict[str, Path] | None = None,
    total_override: dict[str, int] | None = None,
) -> list[str]:
    paths = bundles if bundles is not None else _write_bundles(tmp_path, total_override=total_override)
    argv = ["--semester", semester, "--baseline-before", str(ROWS_PER_SHARD * len(SHARDS)),
            "--baseline-after", str(ROWS_PER_SHARD * len(SHARDS))]
    for shard_id, _number, option in SHARDS:
        argv += [option, str(paths[shard_id])]
    return argv


def _run(capsys, argv: list[str]) -> tuple[int, dict]:
    """跑 CLI 并把**聚合 JSON** 解析出来（成功在 stdout，失败在 stderr）。"""

    code = TOOL.main(argv)
    captured = capsys.readouterr()
    text = captured.out.strip() or captured.err.strip()
    payload = json.loads(text) if text else {}
    return code, payload


# --------------------------------------------------------------------------- #
# preflight（R5）
# --------------------------------------------------------------------------- #


def test_preflight_runs_the_whole_chain_and_cleans_up(capsys) -> None:
    code, payload = _run(capsys, ["--preflight", "--quiet"])

    assert code == TOOL.EXIT_OK, payload
    assert payload["status"] == "ready"
    assert payload["level"] == "LEVEL1-synthetic-preflight"
    assert payload["synthetic"] is True
    assert "NOT Real E2E" in payload["note"]
    assert payload["acceptance_performed"] is True

    acceptance = payload["acceptance"]
    assert acceptance["status"] == "imported"
    assert acceptance["sqlite_imported"] is True
    assert acceptance["shard_count"] == 5
    expected_rows = TOOL.PREFLIGHT_ROWS_PER_SHARD * len(SHARDS)
    assert acceptance["merged_offering_count"] == expected_rows
    assert acceptance["manifest_sha256"] == acceptance["provenance_canonical_manifest_sha256"]

    readback = payload["provider_read_back"]
    assert readback["provider_offering_count"] == acceptance["merged_offering_count"]
    assert readback["readback_offering_count"] == acceptance["merged_offering_count"]
    assert readback["readback_member_count"] == acceptance["merged_offering_count"]
    assert readback["provider_acceptance_sha256"] == acceptance["manifest_sha256"]

    environment = payload["runtime_environment"]
    assert environment["APP_REAL_CASE_A_ENABLED"] == "1"
    assert environment["APP_COURSE_DATA_SEMESTER"] == TOOL.PREFLIGHT_SEMESTER
    assert environment["APP_COURSE_DATA_ACCEPTANCE_SHA256"] == acceptance["manifest_sha256"]
    # ⛔ 本工具不产出 curriculum case 路径
    assert "APP_CASE_A_CURRICULUM_CASE_PATH" not in environment

    # 默认清理 preflight 目录
    assert payload["preflight_dir"] == "(removed)"


def test_preflight_keep_dir_produces_inspectable_artifacts(capsys, tmp_path: Path) -> None:
    code, payload = _run(capsys, ["--preflight", "--keep-dir", "--quiet"])

    assert code == TOOL.EXIT_OK, payload
    directory = Path(payload["preflight_dir"])
    try:
        assert directory.is_dir()
        assert (directory / "course-data.sqlite3").is_file()
        assert (directory / "campus-acceptances.sqlite3").is_file()
        assert (directory / "manifest.json").is_file()
        assert (directory / "capture-inventory.draft.json").is_file()
        assert len(list(directory.glob("*-campus.json"))) == 5
        # diagnostics 只作参考：preflight 的合成基线必须自洽
        assert payload["acceptance"]["baseline_stable"] is True
    finally:
        import shutil

        shutil.rmtree(directory, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 真实模式的两步流程（用 synthetic 输入驱动）
# --------------------------------------------------------------------------- #


def test_real_mode_draft_then_accept(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    campus_store = tmp_path / "campus.sqlite3"
    sqlite = tmp_path / "course-data.sqlite3"
    draft = tmp_path / "inventory.draft.json"
    manifest = tmp_path / "manifest.json"
    env_out = tmp_path / "runtime.env"

    draft_code, draft_payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(campus_store),
         "--sqlite", str(sqlite), "--draft-inventory-out", str(draft)],
    )
    assert draft_code == TOOL.EXIT_OK, draft_payload
    assert draft_payload["status"] == "draft_inventory_written"
    assert draft_payload["acceptance_performed"] is False
    assert draft_payload["draft_inventory"]["inventory_sha256_semantics"].startswith("draft_document")
    assert draft.is_file()
    # 第一步**不做** acceptance / import
    assert not sqlite.exists()

    accept_code, accept_payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(campus_store),
         "--sqlite", str(sqlite), "--inventory", str(draft),
         "--output-manifest", str(manifest), "--env-out", str(env_out),
         "--curriculum-case", "C:/approved/case-a.json"],
    )
    assert accept_code == TOOL.EXIT_OK, accept_payload
    assert accept_payload["status"] == "ready"
    assert accept_payload["acceptance"]["sqlite_imported"] is True
    assert accept_payload["provider_read_back"]["provider_offering_count"] == ROWS_PER_SHARD * len(SHARDS)

    assert manifest.is_file()
    manifest_document = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_document["format"] == "sysu-course-data-full-semester-acceptance-v1"
    assert set(manifest_document) >= {"semester", "scope_kind", "merged_offering_count", "shards"}

    env_text = env_out.read_text(encoding="utf-8")
    assert "APP_REAL_CASE_A_ENABLED=1" in env_text
    assert f"APP_COURSE_DATA_SEMESTER={SEMESTER}" in env_text
    assert f"APP_COURSE_DATA_ACCEPTANCE_SHA256={accept_payload['acceptance']['manifest_sha256']}" in env_text
    # ⛔ 不含任何凭据字样
    for forbidden in ("token", "cookie", "password", "secret"):
        assert forbidden not in env_text.lower()

    # 每个校区的 raw bundle digest 都能与磁盘字节对账
    for shard in accept_payload["acceptance"]["shards"]:
        raw = (tmp_path / f"{shard['shard_id']}.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == shard["raw_bundle_sha256"]


def test_tampered_bundle_fails_closed_at_the_acceptance_stage(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    campus_store = tmp_path / "campus.sqlite3"
    sqlite = tmp_path / "course-data.sqlite3"
    draft = tmp_path / "inventory.draft.json"

    code, _ = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(campus_store),
         "--sqlite", str(sqlite), "--draft-inventory-out", str(draft)],
    )
    assert code == TOOL.EXIT_OK

    # 批准之后、acceptance 之前：某个 shard 的字节被替换 ⇒ 必须 fail closed
    tampered = _bundle("east-campus")
    tampered["pages"][0]["response"]["data"]["rows"][0]["courseName"] = "被替换的课程名"  # type: ignore[index]
    bundles["east-campus"].write_text(
        json.dumps(tampered, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )

    code, _payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(campus_store),
         "--sqlite", str(sqlite), "--inventory", str(draft)],
    )
    assert code == TOOL.EXIT_ACCEPTANCE_STAGE
    # acceptance 失败 ⇒ ⛔ 不产生 Course Data 库
    assert not sqlite.exists()


def test_incomplete_campus_bundle_fails_at_the_campus_stage(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path, total_override={"north-campus": ROWS_PER_SHARD + 5})

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "course-data.sqlite3"), "--draft-inventory-out", str(tmp_path / "d.json")],
    )

    assert code == TOOL.EXIT_CAMPUS_STAGE
    assert payload["orchestration_stage"] == "campus_acceptance"
    assert payload["shard_id"] == "north-campus"
    # 底层 CLI 的**精确** stage / category 被完整保留（⛔ 不吞掉机器可读分类）
    assert payload["stage"] == "completeness_validation"
    assert payload["status"] == "incomplete_snapshot"


def test_existing_target_store_requires_an_explicit_flag(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    campus_store = tmp_path / "campus.sqlite3"
    sqlite = tmp_path / "course-data.sqlite3"
    draft = tmp_path / "inventory.draft.json"
    sqlite.write_bytes(b"")

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(campus_store),
         "--sqlite", str(sqlite), "--draft-inventory-out", str(draft)],
    )
    assert code == TOOL.EXIT_STORE_TARGET
    assert payload["category"] == "sqlite_already_exists"

    sqlite.unlink()
    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(campus_store),
         "--sqlite", str(sqlite), "--draft-inventory-out", str(draft)],
    )
    assert code == TOOL.EXIT_OK, payload


def test_env_out_is_never_overwritten_without_force(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    draft = tmp_path / "inventory.draft.json"

    first_code, _ = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "first.sqlite3"), "--draft-inventory-out", str(draft)],
    )
    assert first_code == TOOL.EXIT_OK

    env_out = tmp_path / "runtime.env"
    env_out.write_text("KEEP=1\n", encoding="utf-8")

    common = [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
              "--inventory", str(draft), "--env-out", str(env_out)]

    code, payload = _run(capsys, [*common, "--sqlite", str(tmp_path / "second.sqlite3")])
    assert code == TOOL.EXIT_ENV_OUTPUT
    assert payload["category"] == "env_out_already_exists"
    assert env_out.read_text(encoding="utf-8") == "KEEP=1\n"

    code, payload = _run(
        capsys, [*common, "--sqlite", str(tmp_path / "third.sqlite3"), "--force"]
    )
    assert code == TOOL.EXIT_OK, payload
    assert env_out.read_text(encoding="utf-8") != "KEEP=1\n"


# --------------------------------------------------------------------------- #
# 结构性保证
# --------------------------------------------------------------------------- #


def test_tool_does_not_hardcode_approved_shard_numbers() -> None:
    """已批准校区号只能来自 `APPROVED_FULL_SEMESTER_SHARDS`（⛔ 不复制常量）。"""

    source = TOOL_PATH.read_text(encoding="utf-8")
    for _shard_id, number, _option in SHARDS:
        assert number not in source, f"approved number {number} must not be hardcoded in the tool"
    for shard in TOOL.APPROVED_FULL_SEMESTER_SHARDS:
        assert shard.opening_school_number in {
            number for _shard_id, number, _option in SHARDS
        }


def test_tool_has_no_network_or_credential_surface() -> None:
    source = TOOL_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("requests", "urllib", "http.client", "socket", "cookie", "password", "token"):
        assert forbidden not in source


def test_tool_requires_an_inventory_or_draft_in_real_mode(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "c.sqlite3"),
         "--sqlite", str(tmp_path / "s.sqlite3")],
    )

    assert code == TOOL.EXIT_ARGUMENTS
    assert payload["category"] == "inventory_invalid"


@pytest.mark.parametrize("missing", ["--semester", "--campus-store", "--sqlite"])
def test_missing_required_real_mode_arguments_fail_closed(capsys, tmp_path: Path, missing: str) -> None:
    bundles = _write_bundles(tmp_path)
    argv = [
        *_base_argv(tmp_path, bundles=bundles),
        "--campus-store", str(tmp_path / "c.sqlite3"),
        "--sqlite", str(tmp_path / "s.sqlite3"),
        "--draft-inventory-out", str(tmp_path / "d.json"),
    ]
    # 去掉目标参数（flag + 其取值）
    index = argv.index(missing)
    del argv[index : index + 2]

    code, payload = _run(capsys, argv)

    assert code == TOOL.EXIT_ARGUMENTS
    assert payload["status"] == "failed"
