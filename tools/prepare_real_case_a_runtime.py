#!/usr/bin/env python3
"""把**五个已批准校区的 raw Capture Bundle** 一路准备成可启动的 Real Case A runtime。

```text
五个 campus raw bundle
  ↓  tools/validate_course_data_artifact.py   （逐校区：exact-byte 校验 + campus acceptance + 导入）
campus acceptance store（五个 campus 记录）
  ↓  （可选）--draft-inventory-out：产出 canonical inventory **草稿**，人工批准后才继续
approved capture inventory
  ↓  tools/accept_full_semester_course_data.py （full-semester acceptance + 导入 + read-back）
新的本地 Course Data SQLite（含 immutable acceptance + membership + rows）
  ↓  StoreBackedCourseDataProvider.get_course_offerings()   （本工具额外做一次 provider 级 read-back）
runtime 环境变量值（可直接启动 backend）
```

## 本工具**只做编排**

- ⛔ 不重新实现 parser / bundle 校验 / completeness / acceptance / 持久化：
  全部调用既有模块与既有 CLI 的**工作函数**（同进程，⛔ 不复制它们的逻辑）；
- ⛔ 不弱化任何验收规则：inventory / campus binding / 计数 / 内容指纹全部照旧；
- ⛔ 不推断 provenance：校区 source label 由 `campus_source_label(semester, number)` 计算，
  inventory 只能来自 `--inventory`（已批准）或 `--draft-inventory-out`（草稿，需人工批准）；
- ⛔ 不抓取学校数据、⛔ 不存凭据、⛔ 不联网；
- ⛔ 不覆盖已有数据库：目标 SQLite / campus store 已存在时必须显式 `--allow-existing-store`
  （即便允许，`immutable acceptance` 规则仍然生效：同 identity 幂等，不同 identity 冲突 fail closed）；
- ⛔ 不写 public Schema，⛔ 不改 frozen Provider contract。

## 两种模式

```text
真实模式（默认）
    python tools/prepare_real_case_a_runtime.py \
        --semester 2026-1 \
        --baseline-before <N> --baseline-after <N> \
        --east  <east.json>  --south <south.json> --shenzhen <shenzhen.json> \
        --zhuhai <zhuhai.json> --north <north.json> \
        --draft-inventory-out <inventory.draft.json>        # 第一步：产出草稿后停止
    # 人工批准草稿（out-of-band；本工具无法证明任何 inventory 被批准）
    python tools/prepare_real_case_a_runtime.py ... --inventory <inventory.json> \
        --campus-store <campus-acceptances.sqlite3> --sqlite <course-data.sqlite3> \
        --output-manifest <manifest.json> --env-out <runtime.env>

合成 preflight（LEVEL1；⛔ 不是 Real E2E）
    python tools/prepare_real_case_a_runtime.py --preflight
```

⚠️ 本工具**不产出** `APP_CASE_A_CURRICULUM_CASE_PATH`（Curriculum case 属另一条已审核输入）。
传入 `--curriculum-case` 只是把它**原样回显**进 env 输出，本工具⛔ 不读取、不校验它。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
for _path in (BACKEND_ROOT, TOOLS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.course_data import (  # noqa: E402
    APPROVED_FULL_SEMESTER_SHARDS,
    CourseDataStoreError,
    StoreBackedCourseDataProvider,
    campus_source_label,
    load_accepted_offerings,
)

EXIT_OK = 0
EXIT_ARGUMENTS = 2
EXIT_STORE_TARGET = 3
EXIT_CAMPUS_STAGE = 4
EXIT_ACCEPTANCE_STAGE = 5
EXIT_PROVIDER_READBACK = 6
EXIT_ENV_OUTPUT = 7

#: shard slug → CLI 选项名（与既有 acceptance CLI 一致；⛔ 不接受别名）。
_SHARD_OPTIONS: tuple[tuple[str, str], ...] = (
    ("east-campus", "--east"),
    ("south-campus", "--south"),
    ("shenzhen-campus", "--shenzhen"),
    ("zhuhai-campus", "--zhuhai"),
    ("north-campus", "--north"),
)

#: preflight 使用的**合成学期**（⛔ 不是真实学期，避免与真实数据混淆）。
PREFLIGHT_SEMESTER = "2099-1"

#: preflight 每个校区生成的 synthetic 行数。
PREFLIGHT_ROWS_PER_SHARD = 3

#: preflight 使用的合成上课时间字符串（⛔ 不含任何真实教学班信息）。
PREFLIGHT_SCHEDULE = "1-16周/星期一/第1-2节/DEMO/示例环节,"


class CliArgumentError(ValueError):
    """CLI 形状非法；⛔ 不回显任何调用方取值。"""


class StageFailure(Exception):
    """某个既有 CLI 阶段失败；携带其退出码与**聚合**输出。"""

    def __init__(self, exit_code: int, payload: dict[str, object], *, stage: str) -> None:
        super().__init__(stage)
        self.exit_code = exit_code
        self.payload = payload
        self.stage = stage


class SafeArgumentParser(argparse.ArgumentParser):
    """argparse 失败 → 结构化、不回显取值的失败。"""

    def error(self, message: str) -> NoReturn:  # noqa: ARG002 - intentionally suppressed
        raise CliArgumentError("invalid arguments")


def _load_tool(name: str, file_name: str) -> ModuleType:
    """按路径加载既有 CLI（⛔ 不修改它们，只复用它们的工作函数）。"""

    spec = importlib.util.spec_from_file_location(name, TOOLS_ROOT / file_name)
    if spec is None or spec.loader is None:  # pragma: no cover - 结构性防御
        raise CliArgumentError(f"Cannot load {file_name}")
    module = importlib.util.module_from_spec(spec)
    # ⚠️ 必须先登记进 sys.modules：`@dataclass` 会通过 `sys.modules[cls.__module__]`
    #    解析类型注解，未登记会在装饰器阶段抛 AttributeError。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_VALIDATE_TOOL = _load_tool("_readiness_validate_tool", "validate_course_data_artifact.py")
_ACCEPT_TOOL = _load_tool("_readiness_accept_tool", "accept_full_semester_course_data.py")


def _payload(**fields: object) -> dict[str, object]:
    return {"status": "failed", **fields}


def _fail(exit_code: int, payload: dict[str, object]) -> NoReturn:
    raise StageFailure(exit_code, payload, stage=str(payload.get("stage", "unknown")))


def _build_parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(
        description=(
            "Prepare a Real Case A runtime from five approved campus Capture Bundles: "
            "campus acceptance -> full-semester acceptance -> SQLite -> provider read-back "
            "-> runtime environment values. Zero network; no credentials; no rule weakening."
        )
    )
    parser.add_argument("--semester", help="acceptance semester, e.g. 2026-1")
    parser.add_argument("--baseline-before", help="collector reported total before the window")
    parser.add_argument("--baseline-after", help="collector reported total after the window")
    for shard_id, option in _SHARD_OPTIONS:
        parser.add_argument(option, metavar="BUNDLE", help=f"raw Capture Bundle for {shard_id}")
    parser.add_argument("--inventory", help="approved capture inventory JSON (approval is out of band)")
    parser.add_argument(
        "--draft-inventory-out",
        help="write the canonical inventory DRAFT from the five bundles and stop",
    )
    parser.add_argument("--campus-store", help="SQLite store for the five campus acceptances")
    parser.add_argument("--sqlite", help="NEW Course Data SQLite path for the acceptance")
    parser.add_argument("--output-manifest", help="where to write the canonical manifest")
    parser.add_argument(
        "--env-out", help="optional local runtime env file (no secrets; never overwritten silently)"
    )
    parser.add_argument(
        "--curriculum-case",
        help="optional curriculum case path; echoed into the env output, never read here",
    )
    parser.add_argument(
        "--allow-existing-store",
        action="store_true",
        help=(
            "allow reusing an existing target --sqlite (immutability rules still apply: "
            "identical acceptance is idempotent, different content fails closed). "
            "The intermediate --campus-store may always be reused."
        ),
    )
    parser.add_argument("--force", action="store_true", help="allow overwriting --env-out")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="synthetic LEVEL1 preflight: generate five synthetic bundles and run the whole chain",
    )
    parser.add_argument("--keep-dir", action="store_true", help="keep the preflight directory")
    parser.add_argument("--quiet", action="store_true", help="do not print the per-stage payloads")
    return parser


# --------------------------------------------------------------------------- #
# synthetic preflight fixtures（⛔ 仅用于证明链路可用；不是 parser / 不是业务逻辑）
# --------------------------------------------------------------------------- #


def _synthetic_row(shard_id: str, index: int, *, with_schedule: bool) -> dict[str, object]:
    row: dict[str, object] = {
        "courseNum": f"PREFLIGHT-{shard_id.upper()}-{index:03d}",
        "courseName": f"合成课程 {shard_id} #{index}",
        "classNumber": f"{shard_id}-{index:03d}",
        "yearTerm": PREFLIGHT_SEMESTER,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
    }
    if with_schedule:
        row["teachingTimePlaceStr"] = PREFLIGHT_SCHEDULE
    return row


def _synthetic_bundle(rows: list[dict[str, object]]) -> dict[str, object]:
    """与 `sysu-opening-courses-capture-v1` 同形状的**合成** bundle。"""

    return {
        "format": "sysu-opening-courses-capture-v1",
        "semester": PREFLIGHT_SEMESTER,
        "first_page_no": 1,
        "page_size": 200,
        "pages": [
            {
                "page_no": 1,
                "response": {
                    "code": 200,
                    "data": {"total": len(rows), "rows": rows},
                },
            }
        ],
    }


def _write_synthetic_bundles(directory: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for shard in APPROVED_FULL_SEMESTER_SHARDS:
        rows = [
            _synthetic_row(shard.shard_id, index, with_schedule=index != PREFLIGHT_ROWS_PER_SHARD - 1)
            for index in range(PREFLIGHT_ROWS_PER_SHARD)
        ]
        path = directory / f"{shard.shard_id}.json"
        path.write_text(
            json.dumps(_synthetic_bundle(rows), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        paths[shard.shard_id] = path
    return paths


# --------------------------------------------------------------------------- #
# stages（全部复用既有 CLI 的工作函数）
# --------------------------------------------------------------------------- #


def _campus_acceptances(
    *,
    semester: str,
    bundles: dict[str, Path],
    campus_store: Path,
) -> list[dict[str, object]]:
    """逐校区：exact-byte 校验 + campus acceptance + 导入（复用 validate CLI）。

    ⚠️ campus store 是**中间产物**：同一个 store 会被两步流程（draft → 批准 → accept）复用，
    因此这里不禁止已存在的 campus store。安全性由后续 full-semester acceptance 保证：
    它按**已批准 inventory 的 raw_bundle_sha256** 逐校区绑定 campus 记录，不匹配即 fail closed；
    同一 artifact 重复导入在 store 层是幂等的（`unchanged`）。
    """

    summaries: list[dict[str, object]] = []
    for shard in APPROVED_FULL_SEMESTER_SHARDS:
        argv = [
            "--bundle",
            str(bundles[shard.shard_id]),
            "--expected-semester",
            semester,
            "--scope-id",
            shard.opening_school_number,
            "--source",
            campus_source_label(semester, shard.opening_school_number),
            "--sqlite",
            str(campus_store),
        ]
        try:
            args = _VALIDATE_TOOL._build_parser().parse_args(argv)
            result = _VALIDATE_TOOL.accept_artifact(args)
        except _VALIDATE_TOOL.AcceptanceFailure as failure:
            # ⚠️ 保留底层 CLI 自己的 `stage` / `category`（更精确），只**追加**编排层上下文。
            _fail(
                EXIT_CAMPUS_STAGE,
                {**failure.payload, "orchestration_stage": "campus_acceptance", "shard_id": shard.shard_id},
            )
        except CliArgumentError:
            _fail(
                EXIT_CAMPUS_STAGE,
                _payload(
                    stage="campus_acceptance",
                    shard_id=shard.shard_id,
                    category="invalid_arguments",
                ),
            )
        summaries.append(
            {
                "shard_id": shard.shard_id,
                "openingSchoolNumber": shard.opening_school_number,
                "status": result.get("status"),
                "raw_bundle_sha256": result.get("artifact_sha256"),
                "campus_acceptance_sha256": result.get("campus_acceptance_sha256"),
                "offering_count": result.get("offering_count"),
                "loaded_count": result.get("loaded_count"),
                "reported_total": result.get("reported_total"),
                "snapshot_complete": result.get("snapshot.is_complete"),
            }
        )
    return summaries


def _acceptance_argv(
    *,
    semester: str,
    baseline_before: object,
    baseline_after: object,
    bundles: dict[str, Path],
    inventory: Path | None,
    draft_inventory_out: Path | None,
    campus_store: Path,
    sqlite: Path,
    output_manifest: Path | None,
) -> list[str]:
    argv = [
        "--semester",
        semester,
        "--baseline-before",
        str(baseline_before),
        "--baseline-after",
        str(baseline_after),
    ]
    for shard_id, option in _SHARD_OPTIONS:
        argv += [option, str(bundles[shard_id])]
    if draft_inventory_out is not None:
        argv += ["--draft-inventory", str(draft_inventory_out)]
    if inventory is not None:
        argv += ["--inventory", str(inventory)]
    argv += ["--campus-store", str(campus_store), "--sqlite", str(sqlite)]
    if output_manifest is not None:
        argv += ["--output-manifest", str(output_manifest)]
    return argv


def _run_acceptance(argv: list[str]) -> dict[str, object]:
    try:
        args = _ACCEPT_TOOL._build_parser().parse_args(argv)
        return _ACCEPT_TOOL.accept_full_semester(args)
    except _ACCEPT_TOOL.AcceptanceFailure as failure:
        _fail(
            EXIT_ACCEPTANCE_STAGE,
            {**failure.payload, "orchestration_stage": "acceptance"},
        )
    except CliArgumentError:
        _fail(
            EXIT_ACCEPTANCE_STAGE,
            _payload(stage="acceptance", category="invalid_arguments"),
        )


def _provider_read_back(
    *, sqlite: Path, semester: str, acceptance_sha256: str, merged_offering_count: object
) -> dict[str, object]:
    """用**冻结的** Store-backed Provider 再读一次：证明 runtime 读到的就是被验收的行。"""

    try:
        provider = StoreBackedCourseDataProvider(
            sqlite_path=sqlite,
            semester=semester,
            acceptance_sha256=acceptance_sha256,
        )
        offerings = provider.get_course_offerings(semester)
        dataset = load_accepted_offerings(sqlite, semester=semester, acceptance_sha256=acceptance_sha256)
    except CourseDataStoreError as exc:
        # ⛔ 只捕获**领域失败**（含 CourseDataAcceptanceError）：其它异常是程序缺陷，
        #    必须原样上抛，⛔ 不伪装成"数据未就绪"。
        _fail(
            EXIT_PROVIDER_READBACK,
            _payload(
                stage="provider_readback",
                category="provider_readback_failed",
                exception_type=type(exc).__name__,
            ),
        )

    if not isinstance(merged_offering_count, int) or len(offerings) != merged_offering_count:
        _fail(
            EXIT_PROVIDER_READBACK,
            _payload(
                stage="provider_readback",
                category="provider_offering_count_mismatch",
                provider_offering_count=len(offerings),
                merged_offering_count=merged_offering_count,
            ),
        )

    return {
        "provider_offering_count": len(offerings),
        "provider_acceptance_sha256": provider.acceptance_sha256,
        "provider_expected_offering_count": provider.expected_offering_count,
        "readback_offering_count": len(dataset.offerings),
        "readback_member_count": dataset.member_count,
        "readback_manifest_sha256": dataset.acceptance.canonical_manifest_sha256,
        "readback_offering_set_sha256": dataset.acceptance.offering_set_sha256,
    }


def _runtime_environment(
    *, sqlite: Path, semester: str, acceptance_sha256: str, curriculum_case: str | None
) -> dict[str, str]:
    environment = {
        "APP_REAL_CASE_A_ENABLED": "1",
        "APP_COURSE_DATA_SQLITE_PATH": str(sqlite),
        "APP_COURSE_DATA_SEMESTER": semester,
        "APP_COURSE_DATA_ACCEPTANCE_SHA256": acceptance_sha256,
    }
    if curriculum_case:
        environment["APP_CASE_A_CURRICULUM_CASE_PATH"] = curriculum_case
    return environment


def _write_env_file(path: Path, environment: dict[str, str], *, force: bool) -> None:
    if path.exists() and not force:
        _fail(
            EXIT_ENV_OUTPUT,
            _payload(
                stage="env_output",
                category="env_out_already_exists",
                message="refusing to overwrite an existing env file without --force",
            ),
        )
    lines = [
        "# 本文件由 tools/prepare_real_case_a_runtime.py 生成：⛔ 不含任何凭据。",
        "# ⛔ 不要提交到仓库；真实 artifact 与本地路径都不入库。",
        *(f"{name}={value}" for name, value in environment.items()),
        "",
    ]
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        _fail(
            EXIT_ENV_OUTPUT,
            _payload(stage="env_output", category="env_out_write_failed", exception_type=type(exc).__name__),
        )


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #


def _orchestrate(
    *,
    semester: str,
    baseline_before: object,
    baseline_after: object,
    bundles: dict[str, Path],
    inventory: Path | None,
    draft_inventory_out: Path | None,
    campus_store: Path,
    sqlite: Path,
    output_manifest: Path | None,
    env_out: Path | None,
    curriculum_case: str | None,
    allow_existing_store: bool,
    force: bool,
) -> dict[str, object]:
    if sqlite.exists() and not allow_existing_store:
        _fail(
            EXIT_STORE_TARGET,
            _payload(
                stage="store_target",
                category="sqlite_already_exists",
                message=(
                    "target SQLite already exists; pass --allow-existing-store to reuse it "
                    "(identical acceptance stays idempotent; different content fails closed)"
                ),
            ),
        )
    # ⚠️ 刻意**不**自动创建父目录：与 store 层"⛔ 不猜路径 / ⛔ 不静默建目录"保持一致。

    campus = _campus_acceptances(
        semester=semester,
        bundles=bundles,
        campus_store=campus_store,
    )

    draft = _run_acceptance(
        _acceptance_argv(
            semester=semester,
            baseline_before=baseline_before,
            baseline_after=baseline_after,
            bundles=bundles,
            inventory=None,
            draft_inventory_out=draft_inventory_out,
            campus_store=campus_store,
            sqlite=sqlite,
            output_manifest=None,
        )
    ) if draft_inventory_out is not None else None

    if draft is not None:
        return {
            "status": "draft_inventory_written",
            "level": "draft_only_no_acceptance",
            "acceptance_performed": False,
            "semester": semester,
            "campus_acceptances": campus,
            "draft_inventory": draft,
            "next_step": (
                "review/approve the draft inventory out of band, then rerun with "
                "--inventory <approved.json> (this tool cannot prove any approval)"
            ),
        }

    if inventory is None:
        _fail(
            EXIT_ARGUMENTS,
            _payload(
                stage="arguments",
                category="inventory_invalid",
                message="an approved --inventory is required (or use --draft-inventory-out first)",
            ),
        )

    acceptance = _run_acceptance(
        _acceptance_argv(
            semester=semester,
            baseline_before=baseline_before,
            baseline_after=baseline_after,
            bundles=bundles,
            inventory=inventory,
            draft_inventory_out=None,
            campus_store=campus_store,
            sqlite=sqlite,
            output_manifest=output_manifest,
        )
    )

    manifest_sha256 = acceptance.get("manifest_sha256")
    if not isinstance(manifest_sha256, str):
        _fail(
            EXIT_ACCEPTANCE_STAGE,
            _payload(stage="acceptance", category="manifest_invalid"),
        )

    readback = _provider_read_back(
        sqlite=sqlite,
        semester=semester,
        acceptance_sha256=manifest_sha256,
        merged_offering_count=acceptance.get("merged_offering_count"),
    )

    environment = _runtime_environment(
        sqlite=sqlite,
        semester=semester,
        acceptance_sha256=manifest_sha256,
        curriculum_case=curriculum_case,
    )
    if env_out is not None:
        _write_env_file(env_out, environment, force=force)

    return {
        "status": "ready",
        "level": "runtime_inputs_prepared",
        "acceptance_performed": True,
        "semester": semester,
        "campus_acceptances": campus,
        "acceptance": acceptance,
        "provider_read_back": readback,
        "runtime_environment": environment,
        "env_out": str(env_out) if env_out is not None else None,
        "next_steps": [
            "APP_CASE_A_CURRICULUM_CASE_PATH must be the already-approved curriculum case",
            "start backend: (cd backend && python -m uvicorn app.main:app --port 8000)",
            "probe: curl -sS -o /dev/null -w '%{http_code}' -X POST "
            "http://127.0.0.1:8000/api/v1/plan -H 'Content-Type: application/json' "
            f"-d '{{\"semester\":\"{semester}\",\"current_schedule\":[],\"preference\":{{}}}}'",
            "expect HTTP 200 (503 means one of the five env vars is missing/mismatched)",
        ],
    }


def _preflight_payload(directory: Path, result: dict[str, object]) -> dict[str, object]:
    return {
        **result,
        "level": "LEVEL1-synthetic-preflight",
        "synthetic": True,
        "preflight_dir": str(directory),
        "note": (
            "synthetic inputs only: this proves the operational chain, it is NOT Real E2E "
            "(no school data, no real acceptance, no LEVEL2/LEVEL3 claim)"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    preflight_dir: Path | None = None
    keep_dir = False
    try:
        args = parser.parse_args(argv)
        keep_dir = bool(args.keep_dir)

        if args.preflight:
            preflight_dir = Path(tempfile.mkdtemp(prefix="real-case-a-preflight-"))
            bundles = _write_synthetic_bundles(preflight_dir)
            semester = PREFLIGHT_SEMESTER
            baseline_before = baseline_after = PREFLIGHT_ROWS_PER_SHARD * len(
                APPROVED_FULL_SEMESTER_SHARDS
            )
            inventory = None
            draft_inventory_out = preflight_dir / "capture-inventory.draft.json"
            campus_store = preflight_dir / "campus-acceptances.sqlite3"
            sqlite = preflight_dir / "course-data.sqlite3"
            output_manifest = preflight_dir / "manifest.json"
            env_out = None
            curriculum_case = None
            allow_existing_store = False
            force = False
        else:
            semester = (args.semester or "").strip()
            if not semester:
                _fail(EXIT_ARGUMENTS, _payload(stage="arguments", category="invalid_semester"))
            missing = [
                option
                for shard_id, option in _SHARD_OPTIONS
                if not getattr(args, option.lstrip("-").replace("-", "_"))
            ]
            if missing:
                _fail(
                    EXIT_ARGUMENTS,
                    _payload(stage="arguments", category="missing_shard_bundle", shard_options=missing),
                )
            if not args.campus_store:
                _fail(EXIT_ARGUMENTS, _payload(stage="arguments", category="missing_campus_store"))
            if not args.sqlite:
                _fail(EXIT_ARGUMENTS, _payload(stage="arguments", category="missing_sqlite"))
            bundles = {
                shard_id: Path(getattr(args, option.lstrip("-").replace("-", "_")))
                for shard_id, option in _SHARD_OPTIONS
            }
            baseline_before = args.baseline_before
            baseline_after = args.baseline_after
            inventory = Path(args.inventory) if args.inventory else None
            draft_inventory_out = (
                Path(args.draft_inventory_out) if args.draft_inventory_out else None
            )
            if inventory is None and draft_inventory_out is None:
                _fail(
                    EXIT_ARGUMENTS,
                    _payload(stage="arguments", category="inventory_invalid", message="--inventory or --draft-inventory-out is required"),
                )
            campus_store = Path(args.campus_store)
            sqlite = Path(args.sqlite)
            output_manifest = Path(args.output_manifest) if args.output_manifest else None
            env_out = Path(args.env_out) if args.env_out else None
            curriculum_case = args.curriculum_case
            allow_existing_store = args.allow_existing_store
            force = args.force

        # preflight 也需要 inventory：先生成草稿，再用它跑正式 acceptance（同真实两步流程）。
        if args.preflight:
            draft = _run_acceptance(
                _acceptance_argv(
                    semester=semester,
                    baseline_before=baseline_before,
                    baseline_after=baseline_after,
                    bundles=bundles,
                    inventory=None,
                    draft_inventory_out=draft_inventory_out,
                    campus_store=campus_store,
                    sqlite=sqlite,
                    output_manifest=None,
                )
            )
            inventory = draft_inventory_out
            if not args.quiet:
                print(json.dumps({"preflight_draft": draft}, ensure_ascii=False, sort_keys=True), file=sys.stderr)

        result = _orchestrate(
            semester=semester,
            baseline_before=baseline_before,
            baseline_after=baseline_after,
            bundles=bundles,
            inventory=inventory,
            draft_inventory_out=None if args.preflight else draft_inventory_out,
            campus_store=campus_store,
            sqlite=sqlite,
            output_manifest=output_manifest,
            env_out=env_out,
            curriculum_case=curriculum_case,
            allow_existing_store=allow_existing_store,
            force=force,
        )
    except StageFailure as failure:
        print(json.dumps(failure.payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return failure.exit_code
    except CliArgumentError:
        print(
            json.dumps(
                {"status": "invalid_arguments", "stage": "arguments", "category": "invalid_arguments"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_ARGUMENTS
    finally:
        if preflight_dir is not None and not keep_dir:
            shutil.rmtree(preflight_dir, ignore_errors=True)

    if args.preflight:
        result = _preflight_payload(
            preflight_dir if keep_dir and preflight_dir is not None else Path("(removed)"),
            result,
        )

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
