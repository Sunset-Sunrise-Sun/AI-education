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
import inspect
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

    code, payload, _out, _err = _run_capture(capsys, argv)
    return code, payload


def _run_capture(capsys, argv: list[str]) -> tuple[int, dict, str, str]:
    """同上，但**同时**返回 stdout / stderr 原文（用于断言"绝不输出 ready"）。"""

    code = TOOL.main(argv)
    captured = capsys.readouterr()
    text = captured.out.strip() or captured.err.strip()
    payload = json.loads(text) if text else {}
    return code, payload, captured.out, captured.err


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
        capsys, [*common, "--sqlite", str(tmp_path / "third.sqlite3"), "--overwrite-env"]
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


# --------------------------------------------------------------------------- #
# BLOCKER 1：env 输出必须绑定到**刚验证过的**那一个 SQLite
# --------------------------------------------------------------------------- #


def _verified_store(*, path: Path, sha: str = "a" * 64, semester: str = SEMESTER) -> object:
    return TOOL.VerifiedStore(
        path=path.resolve(),
        acceptance_sha256=sha,
        semester=semester,
        offering_count=1,
        member_count=1,
        offering_set_sha256="b" * 64,
        expected_offering_count=1,
    )


def test_runtime_environment_has_no_independent_store_inputs() -> None:
    """结构性：env 只能由**已验证 store 对象**派生（⛔ 不存在第二个 DB 路径 / SHA 参数）。"""

    parameters = set(inspect.signature(TOOL._runtime_environment).parameters)
    assert parameters == {"store", "curriculum_case"}
    assert "sqlite" not in parameters and "acceptance_sha256" not in parameters


def test_assert_ready_binding_rejects_a_different_store_path(tmp_path: Path) -> None:
    """单元级：env 指向 B.sqlite 而验证的是 A.sqlite ⇒ 必须 fail closed。"""

    store = _verified_store(path=tmp_path / "a.sqlite3")
    environment = {
        "APP_REAL_CASE_A_ENABLED": "1",
        "APP_COURSE_DATA_SQLITE_PATH": str(tmp_path / "b.sqlite3"),
        "APP_COURSE_DATA_SEMESTER": SEMESTER,
        "APP_COURSE_DATA_ACCEPTANCE_SHA256": store.acceptance_sha256,
    }

    code, payload = _expect_stage_failure(
        lambda: TOOL._assert_ready_binding(
            store=store,
            environment=environment,
            acceptance_manifest_sha256=store.acceptance_sha256,
            semester=SEMESTER,
        )
    )

    assert code == TOOL.EXIT_STORE_BINDING
    assert payload["category"] == "env_db_path_not_the_verified_store"


def test_assert_ready_binding_rejects_a_mismatched_acceptance_sha(tmp_path: Path) -> None:
    store = _verified_store(path=tmp_path / "a.sqlite3")
    environment = {
        "APP_REAL_CASE_A_ENABLED": "1",
        "APP_COURSE_DATA_SQLITE_PATH": str(store.path),
        "APP_COURSE_DATA_SEMESTER": SEMESTER,
        "APP_COURSE_DATA_ACCEPTANCE_SHA256": "c" * 64,  # ⛔ 与已验证 store 不符
    }

    code, payload = _expect_stage_failure(
        lambda: TOOL._assert_ready_binding(
            store=store,
            environment=environment,
            acceptance_manifest_sha256=store.acceptance_sha256,
            semester=SEMESTER,
        )
    )

    assert code == TOOL.EXIT_STORE_BINDING
    assert payload["category"] == "env_acceptance_sha_not_verified"


def _expect_stage_failure(call) -> tuple[int, dict]:
    with pytest.raises(TOOL.StageFailure) as failure:
        call()
    return failure.value.exit_code, failure.value.payload


def test_env_file_binds_to_the_resolved_verified_store(capsys, tmp_path: Path) -> None:
    """env 文件里的 DB 路径 == 已验证 store 的**解析后**路径（含 `..` 也归一化）。"""

    bundles = _write_bundles(tmp_path)
    (tmp_path / "sub").mkdir()
    unresolved = tmp_path / "sub" / ".." / "course-data.sqlite3"
    env_out = tmp_path / "runtime.env"
    manifest = tmp_path / "manifest.json"

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(unresolved), "--inventory", str(_approved_inventory(capsys, tmp_path, bundles)),
         "--output-manifest", str(manifest), "--env-out", str(env_out)],
    )

    assert code == TOOL.EXIT_OK, payload
    resolved = unresolved.resolve()
    assert payload["store_binding"]["resolved_verified_store_path"] == str(resolved)
    assert payload["store_binding"]["env_db_path_equals_verified_store"] is True
    assert payload["runtime_environment"]["APP_COURSE_DATA_SQLITE_PATH"] == str(resolved)
    assert payload["provider_read_back"]["verified_store_path"] == str(resolved)

    text = env_out.read_text(encoding="utf-8")
    assert f"APP_COURSE_DATA_SQLITE_PATH={resolved}" in text
    assert f"APP_COURSE_DATA_ACCEPTANCE_SHA256={payload['acceptance']['manifest_sha256']}" in text
    assert str(unresolved) not in text  # ⛔ 不能写未解析路径


def test_forced_env_db_path_mismatch_fails_before_ready(capsys, tmp_path, monkeypatch) -> None:
    """对抗性：验证 A.sqlite 但把 env 强行指向 B.sqlite ⇒ 绝不输出 ready。"""

    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    original = TOOL._runtime_environment

    def _redirected(*, store, curriculum_case):
        environment = original(store=store, curriculum_case=curriculum_case)
        environment["APP_COURSE_DATA_SQLITE_PATH"] = str(tmp_path / "b.sqlite3")
        return environment

    monkeypatch.setattr(TOOL, "_runtime_environment", _redirected)

    code, payload, out, _err = _run_capture(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "a.sqlite3"), "--inventory", str(inventory)],
    )

    assert code == TOOL.EXIT_STORE_BINDING
    assert payload["category"] == "env_db_path_not_the_verified_store"
    assert '"status": "ready"' not in out


def test_forced_env_acceptance_sha_mismatch_fails_before_ready(capsys, tmp_path, monkeypatch) -> None:
    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    original = TOOL._runtime_environment

    def _redirected(*, store, curriculum_case):
        environment = original(store=store, curriculum_case=curriculum_case)
        environment["APP_COURSE_DATA_ACCEPTANCE_SHA256"] = "d" * 64
        return environment

    monkeypatch.setattr(TOOL, "_runtime_environment", _redirected)

    code, payload, out, _err = _run_capture(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "a.sqlite3"), "--inventory", str(inventory)],
    )

    assert code == TOOL.EXIT_STORE_BINDING
    assert payload["category"] == "env_acceptance_sha_not_verified"
    assert '"status": "ready"' not in out


def test_env_file_redirected_after_verification_fails_before_ready(capsys, tmp_path, monkeypatch) -> None:
    """对抗性：写 env 文件时把 DB 路径改到别处 ⇒ 读回文件即 fail closed。"""

    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    env_out = tmp_path / "runtime.env"
    other = (tmp_path / "b.sqlite3").resolve()
    original_writer = TOOL._write_env_file

    def _tampered_writer(path, environment, *, overwrite):
        tampered = dict(environment)
        tampered["APP_COURSE_DATA_SQLITE_PATH"] = str(other)
        original_writer(path, tampered, overwrite=False)

    monkeypatch.setattr(TOOL, "_write_env_file", _tampered_writer)

    code, payload, out, _err = _run_capture(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "a.sqlite3"), "--inventory", str(inventory),
         "--env-out", str(env_out)],
    )

    assert code == TOOL.EXIT_STORE_BINDING
    assert payload["category"] == "env_file_db_path_not_verified_store"
    assert '"status": "ready"' not in out


# --------------------------------------------------------------------------- #
# BLOCKER 2：env 文件的原子无覆盖创建
# --------------------------------------------------------------------------- #


def test_env_write_is_atomic_exclusive_create(tmp_path: Path) -> None:
    """默认路径：独占创建 + 无覆盖发布（`os.link` 无覆盖语义）。"""

    path = tmp_path / "runtime.env"
    TOOL._write_env_file(path, {"APP_REAL_CASE_A_ENABLED": "1"}, overwrite=False)
    first = path.read_text(encoding="utf-8")
    assert "APP_REAL_CASE_A_ENABLED=1" in first

    code, payload = _expect_stage_failure(
        lambda: TOOL._write_env_file(path, {"APP_REAL_CASE_A_ENABLED": "0"}, overwrite=False)
    )
    assert code == TOOL.EXIT_ENV_OUTPUT
    assert payload["category"] == "env_out_already_exists"
    assert path.read_text(encoding="utf-8") == first  # ⛔ 未被覆盖


def test_competitor_creating_the_env_file_at_publish_boundary_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    """发布边界竞争：对手在 `os.link` 之前创建目标 ⇒ fail closed，对手文件不被覆盖。"""

    path = tmp_path / "runtime.env"
    real_link = TOOL.os.link
    competitor = b"COMPETITOR=1\n"

    def _racing_link(source, destination, *args, **kwargs):
        Path(destination).write_bytes(competitor)  # 对手抢先创建
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(TOOL.os, "link", _racing_link)

    code, payload = _expect_stage_failure(
        lambda: TOOL._write_env_file(path, {"APP_REAL_CASE_A_ENABLED": "1"}, overwrite=False)
    )

    assert code == TOOL.EXIT_ENV_OUTPUT
    assert payload["category"] == "env_out_already_exists"
    assert path.read_bytes() == competitor  # ⛔ 不覆盖对手写入的内容
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_partial_env_write_failure_leaves_no_misleading_file(tmp_path: Path, monkeypatch) -> None:
    """中途失败（fsync 抛错）⇒ 目标不存在、⛔ 不留半截 env、⛔ 不留临时文件。"""

    path = tmp_path / "runtime.env"

    def _broken_fsync(fd):  # noqa: ARG001
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(TOOL.os, "fsync", _broken_fsync)

    code, payload = _expect_stage_failure(
        lambda: TOOL._write_env_file(path, {"APP_REAL_CASE_A_ENABLED": "1"}, overwrite=False)
    )

    assert code == TOOL.EXIT_ENV_OUTPUT
    assert payload["category"] == "document_write_failed"
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []  # 临时文件也被清理


def test_missing_parent_directory_fails_without_creating_directories(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist" / "runtime.env"

    code, payload = _expect_stage_failure(
        lambda: TOOL._write_env_file(missing, {"APP_REAL_CASE_A_ENABLED": "1"}, overwrite=False)
    )

    assert code == TOOL.EXIT_ENV_OUTPUT
    assert payload["category"] == "parent_directory_missing"
    assert not missing.parent.exists()  # ⛔ 不自动建目录


# --------------------------------------------------------------------------- #
# BLOCKER 3：real-capture handoff 证据门
# --------------------------------------------------------------------------- #


def _approved_inventory(capsys, tmp_path: Path, bundles: dict[str, Path]) -> Path:
    draft = tmp_path / "inventory.draft.json"
    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "draft-only.sqlite3"), "--draft-inventory-out", str(draft)],
    )
    assert code == TOOL.EXIT_OK, payload
    return draft


def _write_handoff(
    tmp_path: Path,
    bundles: dict[str, Path],
    *,
    semester: str = SEMESTER,
    state: str = TOOL.HANDOFF_STATE_APPROVED,
    synthetic: bool = False,
    mutate=None,
    name: str = "handoff.json",
) -> Path:
    document = TOOL._build_handoff(
        semester=semester,
        bundles=bundles,
        baseline_before=ROWS_PER_SHARD * len(SHARDS),
        baseline_after=ROWS_PER_SHARD * len(SHARDS),
        state=state,
        synthetic=synthetic,
        collector_commit="demo-commit",
        window_started_at=None,
        window_ended_at=None,
        diagnostics_path=None,
        approved_by="demo-operator" if state == TOOL.HANDOFF_STATE_APPROVED else None,
        approved_at="2026-10-06T00:00:00+00:00" if state == TOOL.HANDOFF_STATE_APPROVED else None,
    )
    if mutate is not None:
        mutate(document)
    path = tmp_path / name
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def test_handoff_contains_only_safe_metadata(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    draft = tmp_path / "handoff.draft.json"

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "s.sqlite3"), "--draft-inventory-out", str(tmp_path / "i.json"),
         "--draft-handoff-out", str(draft)],
    )

    assert code == TOOL.EXIT_OK, payload
    assert payload["status"] in {"draft_inventory_written", "draft_handoff_written"}
    assert "draft_handoff" in payload
    document = json.loads(draft.read_text(encoding="utf-8"))
    assert set(document) == TOOL._HANDOFF_KEYS  # ⛔ 未知键一律不允许（防夹带凭据/个人数据）
    assert document["handoff_state"] == TOOL.HANDOFF_STATE_DRAFT
    assert document["synthetic"] is False
    assert document["semester"] == SEMESTER
    assert len(document["shards"]) == len(SHARDS)
    for shard in document["shards"]:
        assert set(shard) == TOOL._HANDOFF_SHARD_KEYS
        raw = (tmp_path / f"{shard['shard_id']}.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == shard["raw_bundle_sha256"]

    text = draft.read_text(encoding="utf-8").lower()
    for forbidden in ("cookie", "token", "authorization", "student", "学号", "姓名", "成绩"):
        assert forbidden not in text


def test_unapproved_handoff_cannot_authorize_acceptance(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    draft_handoff = _write_handoff(
        tmp_path, bundles, state=TOOL.HANDOFF_STATE_DRAFT, name="handoff.draft.json"
    )
    sqlite = tmp_path / "s.sqlite3"

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(sqlite), "--inventory", str(inventory), "--handoff", str(draft_handoff)],
    )

    assert code == TOOL.EXIT_HANDOFF
    assert payload["category"] == "handoff_not_approved"
    assert not sqlite.exists()  # fail closed 发生在 acceptance 之前


def test_synthetic_handoff_can_never_satisfy_the_real_gate(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    synthetic = _write_handoff(
        tmp_path,
        bundles,
        state=TOOL.HANDOFF_STATE_APPROVED,
        synthetic=True,
        name="handoff.synthetic.json",
    )

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "s.sqlite3"), "--inventory", str(inventory),
         "--handoff", str(synthetic)],
    )

    assert code == TOOL.EXIT_HANDOFF
    assert payload["category"] == "handoff_not_approved"


def test_handoff_bundle_digest_mismatch_fails_closed(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    handoff = _write_handoff(
        tmp_path,
        bundles,
        mutate=lambda document: document["shards"][0].__setitem__("raw_bundle_sha256", "e" * 64),
    )

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "s.sqlite3"), "--inventory", str(inventory),
         "--handoff", str(handoff)],
    )

    assert code == TOOL.EXIT_HANDOFF
    assert payload["category"] == "handoff_bundle_digest_mismatch"


def test_handoff_semester_mismatch_fails_closed(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    handoff = _write_handoff(tmp_path, bundles, semester="2027-1", name="handoff.other-term.json")

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "s.sqlite3"), "--inventory", str(inventory),
         "--handoff", str(handoff)],
    )

    assert code == TOOL.EXIT_HANDOFF
    assert payload["category"] == "handoff_semester_mismatch"


def test_handoff_with_unknown_key_is_rejected(capsys, tmp_path: Path) -> None:
    """⛔ 未知键 ⇒ 拒绝（防止把凭据 / 原始响应体 / 个人数据夹带进证据文件）。"""

    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    handoff = _write_handoff(tmp_path, bundles, mutate=lambda document: document.update({"session_cookie": "x"}))

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "s.sqlite3"), "--inventory", str(inventory),
         "--handoff", str(handoff)],
    )

    assert code == TOOL.EXIT_HANDOFF
    assert payload["category"] == "handoff_shape_invalid"


def test_approved_handoff_enables_level2_eligibility(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)
    handoff = _write_handoff(tmp_path, bundles)

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "s.sqlite3"), "--inventory", str(inventory),
         "--handoff", str(handoff)],
    )

    assert code == TOOL.EXIT_OK, payload
    assert payload["level2_eligible"] is True
    assert payload["level2_blockers"] == []
    assert payload["real_source_provenance"]["handoff_state"] == "approved"
    assert payload["real_source_provenance"]["synthetic"] is False
    # handoff 的五个 digest 必须与 acceptance 记录的 campus artifact digest 逐条一致
    recorded = payload["real_source_provenance"]["raw_bundle_sha256_by_shard"]
    for shard in payload["acceptance"]["shards"]:
        assert recorded[shard["shard_id"]] == shard["raw_bundle_sha256"]
    assert set(payload["level2_gate_conditions"]) == set(TOOL.LEVEL2_GATE_CONDITIONS)


def test_acceptance_without_handoff_is_ready_but_not_level2(capsys, tmp_path: Path) -> None:
    bundles = _write_bundles(tmp_path)
    inventory = _approved_inventory(capsys, tmp_path, bundles)

    code, payload = _run(
        capsys,
        [*_base_argv(tmp_path, bundles=bundles), "--campus-store", str(tmp_path / "campus.sqlite3"),
         "--sqlite", str(tmp_path / "s.sqlite3"), "--inventory", str(inventory)],
    )

    assert code == TOOL.EXIT_OK, payload
    assert payload["status"] == "ready"
    assert payload["level2_eligible"] is False
    assert "real_source_handoff_missing" in payload["level2_blockers"]
    assert payload["real_source_provenance"] is None


def test_preflight_handoff_is_synthetic_and_cannot_satisfy_the_real_gate(capsys, tmp_path: Path) -> None:
    code, payload, out, _err = _run_capture(capsys, ["--preflight", "--keep-dir", "--quiet"])

    assert code == TOOL.EXIT_OK, payload
    assert payload["level"] == "LEVEL1-synthetic-preflight"
    assert payload["level2_eligible"] is False
    assert "synthetic_preflight_handoff" in payload["level2_blockers"]

    directory = Path(payload["preflight_dir"])
    handoff_path = directory / "capture-handoff.synthetic.json"
    try:
        document = json.loads(handoff_path.read_text(encoding="utf-8"))
        assert document["handoff_state"] == TOOL.HANDOFF_STATE_SYNTHETIC
        assert document["synthetic"] is True

        # ⛔ 把 synthetic handoff 拿去当"已批准的真实 handoff"必须被拒。
        code, failure = _run(
            capsys,
            [*_base_argv(tmp_path, bundles=_write_bundles(tmp_path)),
             "--campus-store", str(tmp_path / "campus.sqlite3"),
             "--sqlite", str(tmp_path / "s.sqlite3"),
             "--inventory", str(_approved_inventory(capsys, tmp_path, _write_bundles(tmp_path))),
             "--handoff", str(handoff_path)],
        )
        assert code == TOOL.EXIT_HANDOFF
        assert failure["category"] in {"handoff_not_approved", "handoff_is_synthetic", "handoff_semester_mismatch"}
    finally:
        import shutil

        shutil.rmtree(directory, ignore_errors=True)
