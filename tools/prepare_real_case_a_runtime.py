#!/usr/bin/env python3
"""把**五个已批准校区的 raw Capture Bundle** 一路准备成可启动的 Real Case A runtime。

```text
五个 campus raw bundle
  ↓  tools/validate_course_data_artifact.py   （逐校区：exact-byte 校验 + campus acceptance + 导入）
campus acceptance store（五个 campus 记录）
  ↓  （可选）--draft-inventory-out / --draft-handoff-out：产出**草稿**，人工批准后才继续
approved capture inventory + approved real-capture handoff
  ↓  tools/accept_full_semester_course_data.py （full-semester acceptance + 导入 + read-back）
新的本地 Course Data SQLite（含 immutable acceptance + membership + rows）
  ↓  StoreBackedCourseDataProvider.get_course_offerings()   （provider 级 read-back）
runtime 环境变量值（可直接启动 backend）
```

## 硬边界

- ⛔ 不重新实现 parser / bundle 校验 / completeness / acceptance / 持久化：
  全部调用既有模块与既有 CLI 的**工作函数**（同进程，⛔ 不复制它们的逻辑）；
- ⛔ 不弱化任何验收规则：inventory / campus binding / 计数 / 内容指纹全部照旧；
- ⛔ 不推断 provenance：校区 source label 由 `campus_source_label(semester, number)` 计算；
  inventory 只能来自 `--inventory`（已批准）或 `--draft-inventory-out`（草稿）；
  **real-capture handoff** 只能来自 `--handoff`（已批准）或 `--draft-handoff-out`（草稿）；
- ⛔ 不抓取学校数据、⛔ 不存凭据、⛔ 不联网；
- ⛔ 不覆盖已有数据库：目标 SQLite / campus store 已存在时必须显式 `--allow-existing-store`
  （即便允许，`immutable acceptance` 规则仍然生效：同 identity 幂等，不同 identity 冲突 fail closed）；
- ⛔ 不写 public Schema，⛔ 不改 frozen Provider contract。

## READY 的精确含义（BLOCKER 1）

```text
status = "ready"  当且仅当：
  runtime env 里输出的 APP_COURSE_DATA_SQLITE_PATH
    == **同一个**刚被创建/打开并验证过的 SQLite 的**解析后绝对路径**
    == provider read-back 成功的那一个 store
    == 持有 env 中那个 acceptance SHA 的 store
```

⛔ **不存在**"单独的 env DB 路径参数"：env 值只能由**已验证 store 对象**派生
（`_runtime_environment(store=...)`），且在返回 ready 之前会**再次断言**
（`_assert_ready_binding`）。写 env 文件**不得**改变 DB 路径或 acceptance digest。

## env 文件写入（BLOCKER 2）

```text
默认：目标不存在 ⇒ 原子独占创建成功；目标已存在 ⇒ fail closed（⛔ 不静默覆盖、⛔ 无 TOCTOU 预检）
实现：同目录临时文件写全量 + fsync，再用 `os.link` **无覆盖**发布（不支持时退回 O_EXCL 独占创建）
     发布失败 / 中途失败 ⇒ 清理临时文件，绝不留下"看起来有效"的半截 env 文件
父目录不存在 ⇒ 直接失败（⛔ 不自动创建目录）
--overwrite-env ⇒ 显式操作员动作（原子 replace）；⛔ 默认不开启
```

## real-capture handoff（BLOCKER 3）

`--draft-handoff-out` 产出一份**只有安全元数据**的 handoff 草稿
（semester / 五校区号 / 五个 raw bundle SHA / baseline / 采集窗口 / collector commit /
本地生成的 session id / `authorized_user_session: true`），
⛔ 不含凭据 / 浏览器会话标识 / auth header / 原始响应体 / 学生个人数据。

人工批准（唯一需要人工编辑的内容：`handoff_state` → `approved` + `approved_by`/`approved_at`）
之后用 `--handoff` 交回。工具会断言：

```text
handoff.semester == acceptance.semester
handoff.shards == 恰好已批准五校区（shard_id + openingSchoolNumber）
handoff.shards[].raw_bundle_sha256 == 磁盘上该 bundle 的 SHA-256
handoff.shards[].raw_bundle_sha256 == acceptance 记录里的 campus artifact digest
handoff.synthetic == false 且 handoff.handoff_state == "approved"
handoff.authorized_user_session == true
```

只有全部成立，输出里才会出现 `level2_eligible: true`；否则 `level2_eligible: false`
并给出 `level2_blockers`。⛔ 本工具**不创造** "real provenance"：
它只把人工批准的 handoff 与**被接受**的 artifact digest 绑定/对账；
⛔ synthetic handoff 永远无法满足 real-source gate。

## 两种模式

```text
真实模式（默认）
    python tools/prepare_real_case_a_runtime.py \
        --semester 2026-1 --baseline-before <N> --baseline-after <N> \
        --east <east.json> --south <south.json> --shenzhen <sz.json> \
        --zhuhai <zh.json> --north <north.json> \
        --campus-store <campus.sqlite3> --sqlite <course-data.sqlite3> \
        --draft-inventory-out <inventory.draft.json> \
        --draft-handoff-out <handoff.draft.json>          # 第一步：产出两份草稿后停止
    # 人工批准两份草稿（out-of-band；本工具无法证明任何批准）
    python tools/prepare_real_case_a_runtime.py ... \
        --inventory <inventory.json> --handoff <handoff.json> \
        --sqlite <course-data.sqlite3> --output-manifest <manifest.json> \
        --env-out <runtime.env>

合成 preflight（LEVEL1；⛔ 不是 Real E2E，handoff 显式 synthetic）
    python tools/prepare_real_case_a_runtime.py --preflight
```

⚠️ 本工具**不产出** `APP_CASE_A_CURRICULUM_CASE_PATH`（Curriculum case 属另一条已审核输入）。
传入 `--curriculum-case` 只是把它**原样回显**进 env 输出，本工具⛔ 不读取、不校验它。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import NoReturn, Sequence

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
EXIT_STORE_BINDING = 8
EXIT_HANDOFF = 9

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

#: real-capture handoff 文档格式 / 版本（本地证据产物，⛔ 不是公共 API Schema）。
HANDOFF_FORMAT = "sysu-real-capture-handoff-v1"
HANDOFF_VERSION = 1
HANDOFF_STATE_DRAFT = "draft"
HANDOFF_STATE_APPROVED = "approved"
HANDOFF_STATE_SYNTHETIC = "synthetic"

#: handoff 允许的**精确**键集合（⛔ 未知键 ⇒ 拒绝：防止夹带凭据 / 个人数据 / 原始响应体）。
_HANDOFF_KEYS = frozenset(
    {
        "handoff_format",
        "handoff_version",
        "handoff_id",
        "handoff_state",
        "synthetic",
        "semester",
        "capture_session_id",
        "collector_tool",
        "collector_commit",
        "capture_window",
        "baseline_before",
        "baseline_after",
        "shards",
        "diagnostics_sha256",
        "authorized_user_session",
        "approved_by",
        "approved_at",
        "approval_note",
    }
)
_HANDOFF_SHARD_KEYS = frozenset({"shard_id", "openingSchoolNumber", "raw_bundle_sha256"})
_HANDOFF_WINDOW_KEYS = frozenset({"started_at", "ended_at"})

#: LEVEL2 的 real-source 证据门（六条；缺一即 `level2_eligible = false`）。
LEVEL2_GATE_CONDITIONS: tuple[str, ...] = (
    "approved_real_capture_handoff_exists",
    "handoff_semester_matches_acceptance_semester",
    "handoff_contains_exactly_the_approved_five_shards",
    "handoff_raw_bundle_sha256_matches_campus_acceptance_inputs",
    "handoff_marked_approved_and_not_synthetic",
    "no_north_skip",
)


class CliArgumentError(ValueError):
    """CLI 形状非法；⛔ 不回显任何调用方取值。"""


class StageFailure(Exception):
    """某个阶段失败；携带退出码与**聚合**输出（⛔ 不含输入取值）。"""

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


def _resolve(path: str | Path) -> Path:
    """把调用方路径解析成**绝对**路径（READY 绑定只认解析后的路径）。"""

    return Path(path).expanduser().resolve()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_document(
    path: Path, document: dict[str, object], *, exit_code: int, already_exists_category: str
) -> None:
    """写一份本地 JSON 证据产物（独占创建；已存在 ⇒ fail closed）。"""

    content = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    _write_bytes_exclusive(
        path, content, exit_code=exit_code, already_exists_category=already_exists_category
    )


def _write_bytes_exclusive(
    path: Path, content: bytes, *, exit_code: int, already_exists_category: str
) -> None:
    """原子独占写入：⛔ 不覆盖已存在文件、⛔ 不留半截内容、⛔ 不自动建目录。"""

    directory = path.parent
    if not directory.is_dir():
        _fail(
            exit_code,
            _payload(
                stage="document_output",
                category="parent_directory_missing",
                message="parent directory must exist; this tool never creates directories",
            ),
        )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
    temporary = Path(temporary_name)

    def _already_exists() -> NoReturn:
        _fail(
            exit_code,
            _payload(
                stage="document_output",
                category=already_exists_category,
                message="refusing to overwrite an existing document",
            ),
        )

    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # ⛔ 无覆盖发布：`os.link` 在目标已存在时抛 FileExistsError（"创建即检查"）。
            os.link(temporary, path)
        except FileExistsError:
            _already_exists()
        except OSError:
            # 平台不支持硬链接 ⇒ 退回 O_EXCL 独占创建（仍然是"创建即检查"）。
            try:
                claim = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                _already_exists()
            except OSError as exc:
                _fail(
                    exit_code,
                    _payload(
                        stage="document_output",
                        category="document_write_failed",
                        exception_type=type(exc).__name__,
                    ),
                )
            try:
                os.write(claim, content)
                os.fsync(claim)
            except OSError as exc:
                os.close(claim)
                try:
                    os.unlink(path)
                except OSError:
                    pass
                _fail(
                    exit_code,
                    _payload(
                        stage="document_output",
                        category="document_write_failed",
                        exception_type=type(exc).__name__,
                    ),
                )
            os.close(claim)
    except StageFailure:
        raise
    except OSError as exc:
        _fail(
            exit_code,
            _payload(
                stage="document_output",
                category="document_write_failed",
                exception_type=type(exc).__name__,
            ),
        )
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _build_parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(
        description=(
            "Prepare a Real Case A runtime from five approved campus Capture Bundles: "
            "campus acceptance -> full-semester acceptance -> SQLite -> provider read-back "
            "-> runtime environment values bound to that exact verified store. "
            "Zero network; no credentials; no rule weakening."
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
    parser.add_argument(
        "--handoff",
        help=(
            "approved real-capture handoff JSON (handoff_state=approved, synthetic=false); "
            "required for LEVEL2 eligibility"
        ),
    )
    parser.add_argument(
        "--draft-handoff-out",
        help="write the real-capture handoff DRAFT (safe metadata only) and stop",
    )
    parser.add_argument("--collector-commit", help="optional collector commit/version to record in the handoff")
    parser.add_argument("--capture-window-start", help="optional capture window start (operator recorded)")
    parser.add_argument("--capture-window-end", help="optional capture window end (operator recorded)")
    parser.add_argument("--campus-store", help="SQLite store for the five campus acceptances")
    parser.add_argument("--sqlite", help="NEW Course Data SQLite path for the acceptance")
    parser.add_argument("--output-manifest", help="where to write the canonical manifest")
    parser.add_argument(
        "--env-out",
        help=(
            "optional local runtime env file (no secrets). The DB path inside it is ALWAYS the "
            "resolved verified store path; created atomically and never overwritten by default"
        ),
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
    parser.add_argument(
        "--overwrite-env",
        action="store_true",
        help=(
            "EXPLICIT operator action: replace an existing --env-out atomically. "
            "Off by default; the default is fail closed when the env file already exists."
        ),
    )
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
# real-capture handoff（BLOCKER 3：只含安全元数据的本地证据产物）
# --------------------------------------------------------------------------- #


def _build_handoff(
    *,
    semester: str,
    bundles: dict[str, Path],
    baseline_before: object,
    baseline_after: object,
    state: str,
    synthetic: bool,
    collector_commit: str | None,
    window_started_at: str | None,
    window_ended_at: str | None,
    diagnostics_path: Path | None,
    approved_by: str | None = None,
    approved_at: str | None = None,
    approval_note: str | None = None,
) -> dict[str, object]:
    """构造 handoff 文档（⛔ 只含安全元数据：digest / 计数 / 枚举 / 时间）。"""

    return {
        "handoff_format": HANDOFF_FORMAT,
        "handoff_version": HANDOFF_VERSION,
        "handoff_id": uuid.uuid4().hex,
        "handoff_state": state,
        "synthetic": synthetic,
        "semester": semester,
        "capture_session_id": f"local-session-{uuid.uuid4().hex[:12]}",
        "collector_tool": "tools/sysu_course_offering_collector.js",
        "collector_commit": collector_commit,
        "capture_window": {"started_at": window_started_at, "ended_at": window_ended_at},
        "baseline_before": baseline_before,
        "baseline_after": baseline_after,
        "shards": [
            {
                "shard_id": shard.shard_id,
                "openingSchoolNumber": shard.opening_school_number,
                "raw_bundle_sha256": _sha256_file(bundles[shard.shard_id]),
            }
            for shard in APPROVED_FULL_SEMESTER_SHARDS
        ],
        "diagnostics_sha256": _sha256_file(diagnostics_path) if diagnostics_path else None,
        "authorized_user_session": True,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "approval_note": approval_note,
    }


def _require_handoff_shape(document: object) -> dict[str, object]:
    if not isinstance(document, dict):
        _fail(
            EXIT_HANDOFF,
            _payload(stage="handoff", category="handoff_invalid", message="handoff must be a JSON object"),
        )
    unknown = set(document) - _HANDOFF_KEYS
    missing = _HANDOFF_KEYS - set(document)
    if unknown or missing:
        # ⛔ 未知键可能夹带凭据 / 个人数据 / 原始响应体 ⇒ 直接拒绝（不回显键名）。
        _fail(
            EXIT_HANDOFF,
            _payload(
                stage="handoff",
                category="handoff_shape_invalid",
                unknown_key_count=len(unknown),
                missing_key_count=len(missing),
            ),
        )
    if document["handoff_format"] != HANDOFF_FORMAT or document["handoff_version"] != HANDOFF_VERSION:
        _fail(
            EXIT_HANDOFF,
            _payload(stage="handoff", category="handoff_format_unsupported"),
        )
    window = document["capture_window"]
    if not isinstance(window, dict) or set(window) != _HANDOFF_WINDOW_KEYS:
        _fail(EXIT_HANDOFF, _payload(stage="handoff", category="handoff_shape_invalid"))
    return document


def _validate_handoff(
    document: object,
    *,
    semester: str,
    bundles: dict[str, Path],
    acceptance_shards: object,
) -> dict[str, object]:
    """把已批准 handoff 与**本次**被接受的 artifact digest 逐条对账。"""

    handoff = _require_handoff_shape(document)

    if handoff["synthetic"] is not False:
        _fail(
            EXIT_HANDOFF,
            _payload(stage="handoff", category="handoff_is_synthetic", message="synthetic handoff cannot authorize real capture"),
        )
    if handoff["handoff_state"] != HANDOFF_STATE_APPROVED:
        _fail(
            EXIT_HANDOFF,
            _payload(
                stage="handoff",
                category="handoff_not_approved",
                message="handoff_state must be 'approved' (draft/synthetic never satisfies the real-source gate)",
            ),
        )
    if handoff["authorized_user_session"] is not True:
        _fail(
            EXIT_HANDOFF,
            _payload(stage="handoff", category="handoff_authorized_session_missing"),
        )
    if handoff["semester"] != semester:
        _fail(
            EXIT_HANDOFF,
            _payload(stage="handoff", category="handoff_semester_mismatch"),
        )

    shards = handoff["shards"]
    if not isinstance(shards, list) or len(shards) != len(APPROVED_FULL_SEMESTER_SHARDS):
        _fail(
            EXIT_HANDOFF,
            _payload(stage="handoff", category="handoff_shard_set_mismatch"),
        )

    accepted_by_id: dict[str, object] = {}
    if isinstance(acceptance_shards, list):
        for record in acceptance_shards:
            if isinstance(record, dict) and isinstance(record.get("shard_id"), str):
                accepted_by_id[record["shard_id"]] = record.get("raw_bundle_sha256")

    for approved in APPROVED_FULL_SEMESTER_SHARDS:
        matches = [
            shard
            for shard in shards
            if isinstance(shard, dict) and shard.get("shard_id") == approved.shard_id
        ]
        if len(matches) != 1:
            _fail(
                EXIT_HANDOFF,
                _payload(stage="handoff", category="handoff_shard_set_mismatch", shard_id=approved.shard_id),
            )
        shard = matches[0]
        if set(shard) != _HANDOFF_SHARD_KEYS:
            _fail(
                EXIT_HANDOFF,
                _payload(stage="handoff", category="handoff_shape_invalid", shard_id=approved.shard_id),
            )
        if shard["openingSchoolNumber"] != approved.opening_school_number:
            _fail(
                EXIT_HANDOFF,
                _payload(stage="handoff", category="handoff_shard_number_mismatch", shard_id=approved.shard_id),
            )
        recorded = shard["raw_bundle_sha256"]
        if not isinstance(recorded, str) or not recorded:
            _fail(
                EXIT_HANDOFF,
                _payload(stage="handoff", category="handoff_shape_invalid", shard_id=approved.shard_id),
            )
        # (1) handoff 必须与**磁盘上**这一份 bundle 对得上
        if recorded != _sha256_file(bundles[approved.shard_id]):
            _fail(
                EXIT_HANDOFF,
                _payload(stage="handoff", category="handoff_bundle_digest_mismatch", shard_id=approved.shard_id),
            )
        # (2) handoff 必须与**被接受的** campus artifact digest 对得上
        if accepted_by_id.get(approved.shard_id) != recorded:
            _fail(
                EXIT_HANDOFF,
                _payload(
                    stage="handoff",
                    category="handoff_acceptance_digest_mismatch",
                    shard_id=approved.shard_id,
                ),
            )

    return {
        "handoff_format": handoff["handoff_format"],
        "handoff_version": handoff["handoff_version"],
        "handoff_id": handoff["handoff_id"],
        "handoff_state": handoff["handoff_state"],
        "synthetic": handoff["synthetic"],
        "semester": handoff["semester"],
        "capture_session_id": handoff["capture_session_id"],
        "collector_tool": handoff["collector_tool"],
        "collector_commit": handoff["collector_commit"],
        "capture_window": handoff["capture_window"],
        "baseline_before": handoff["baseline_before"],
        "baseline_after": handoff["baseline_after"],
        "raw_bundle_sha256_by_shard": {
            str(shard["shard_id"]): shard["raw_bundle_sha256"] for shard in shards if isinstance(shard, dict)
        },
        "diagnostics_sha256": handoff["diagnostics_sha256"],
        "authorized_user_session": handoff["authorized_user_session"],
        "approved_by": handoff["approved_by"],
        "approved_at": handoff["approved_at"],
        "approval_note": handoff["approval_note"],
    }


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

    ⚠️ campus store 是**中间产物**：两步流程（draft → 批准 → accept）会复用它；
    安全性由 full-semester acceptance 保证（按已批准 inventory 的 raw_bundle_sha256 逐校区绑定）。
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


@dataclass(frozen=True, slots=True)
class VerifiedStore:
    """**刚被验证过**的那一个 store（READY 绑定的唯一来源）。"""

    path: Path
    acceptance_sha256: str
    semester: str
    offering_count: int
    member_count: int
    offering_set_sha256: str
    expected_offering_count: int

    def summary(self) -> dict[str, object]:
        return {
            # 绑定字段（READY 断言使用的**同一个**来源）
            "verified_store_path": str(self.path),
            "verified_acceptance_sha256": self.acceptance_sha256,
            "verified_semester": self.semester,
            # 与 read-back 观测对应的兼容字段
            "provider_offering_count": self.offering_count,
            "provider_acceptance_sha256": self.acceptance_sha256,
            "provider_expected_offering_count": self.expected_offering_count,
            "readback_offering_count": self.offering_count,
            "readback_member_count": self.member_count,
            "readback_manifest_sha256": self.acceptance_sha256,
            "readback_offering_set_sha256": self.offering_set_sha256,
        }


def _provider_read_back(
    *, sqlite: Path, semester: str, acceptance_sha256: str, merged_offering_count: object
) -> VerifiedStore:
    """用**冻结的** Store-backed Provider 再读一次：证明 runtime 读到的就是被验收的行。

    ⚠️ `sqlite` 必须是**解析后的绝对路径**；返回的 `VerifiedStore` 就是 READY 绑定的对象。
    """

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

    return VerifiedStore(
        path=sqlite,
        acceptance_sha256=provider.acceptance_sha256,
        semester=semester,
        offering_count=len(offerings),
        member_count=dataset.member_count,
        offering_set_sha256=dataset.acceptance.offering_set_sha256,
        expected_offering_count=provider.expected_offering_count,
    )


def _runtime_environment(
    *, store: VerifiedStore, curriculum_case: str | None
) -> dict[str, str]:
    """从**已验证 store 对象**派生 env（⛔ 不存在第二个 DB 路径 / SHA 参数）。"""

    environment = {
        "APP_REAL_CASE_A_ENABLED": "1",
        "APP_COURSE_DATA_SQLITE_PATH": str(store.path),
        "APP_COURSE_DATA_SEMESTER": store.semester,
        "APP_COURSE_DATA_ACCEPTANCE_SHA256": store.acceptance_sha256,
    }
    if curriculum_case:
        environment["APP_CASE_A_CURRICULUM_CASE_PATH"] = curriculum_case
    return environment


def _assert_ready_binding(
    *,
    store: VerifiedStore,
    environment: dict[str, str],
    acceptance_manifest_sha256: object,
    semester: str,
) -> None:
    """READY 之前必须成立的绑定（任一不成立 ⇒ fail closed，⛔ 绝不输出 ready）。

    ```text
    env 里的 DB 路径（解析后） == 已验证 store 路径
    env 里的 acceptance SHA    == 已验证 store 的 acceptance SHA
    已验证 store 的 SHA        == acceptance 阶段算出的 manifest SHA
    再次从**该路径**读回该 acceptance 成功（证明文件里就是这条记录）
    学期一致
    ```
    """

    if not isinstance(acceptance_manifest_sha256, str) or not acceptance_manifest_sha256:
        _fail(
            EXIT_STORE_BINDING,
            _payload(stage="ready_binding", category="acceptance_manifest_missing"),
        )

    env_db_path = environment.get("APP_COURSE_DATA_SQLITE_PATH")
    env_sha = environment.get("APP_COURSE_DATA_ACCEPTANCE_SHA256")
    env_semester = environment.get("APP_COURSE_DATA_SEMESTER")

    if not isinstance(env_db_path, str) or _resolve(env_db_path) != store.path:
        _fail(
            EXIT_STORE_BINDING,
            _payload(
                stage="ready_binding",
                category="env_db_path_not_the_verified_store",
                env_db_path_is_verified_store=False,
            ),
        )
    if env_sha != store.acceptance_sha256 or env_sha != acceptance_manifest_sha256:
        _fail(
            EXIT_STORE_BINDING,
            _payload(
                stage="ready_binding",
                category="env_acceptance_sha_not_verified",
                env_sha_matches_verified_store=env_sha == store.acceptance_sha256,
                env_sha_matches_acceptance_manifest=env_sha == acceptance_manifest_sha256,
            ),
        )
    if env_semester != semester or store.semester != semester:
        _fail(
            EXIT_STORE_BINDING,
            _payload(stage="ready_binding", category="semester_binding_mismatch"),
        )

    try:
        dataset = load_accepted_offerings(
            store.path, semester=semester, acceptance_sha256=store.acceptance_sha256
        )
    except CourseDataStoreError as exc:
        _fail(
            EXIT_STORE_BINDING,
            _payload(
                stage="ready_binding",
                category="acceptance_not_readable_from_verified_store",
                exception_type=type(exc).__name__,
            ),
        )

    if dataset.acceptance.canonical_manifest_sha256 != acceptance_manifest_sha256:
        _fail(
            EXIT_STORE_BINDING,
            _payload(stage="ready_binding", category="stored_manifest_sha_mismatch"),
        )
    if len(dataset.offerings) != store.offering_count:
        _fail(
            EXIT_STORE_BINDING,
            _payload(stage="ready_binding", category="stored_offering_count_mismatch"),
        )


def _write_env_file(path: Path, environment: dict[str, str], *, overwrite: bool) -> None:
    """原子写 env 文件：默认**独占创建**（已存在 ⇒ fail closed），⛔ 不留半截文件。"""

    lines = [
        "# 本文件由 tools/prepare_real_case_a_runtime.py 生成：⛔ 不含任何凭据。",
        "# ⛔ 不要提交到仓库；真实 artifact 与本地路径都不入库。",
        f"# verified_store_path={environment.get('APP_COURSE_DATA_SQLITE_PATH', '<unset>')}",
        *(f"{name}={value}" for name, value in environment.items()),
        "",
    ]
    content = "\n".join(lines).encode("utf-8")

    if overwrite:
        _replace_bytes_atomically(path, content)
        return

    _write_bytes_exclusive(
        path, content, exit_code=EXIT_ENV_OUTPUT, already_exists_category="env_out_already_exists"
    )


def _assert_env_file_binding(*, path: Path, store: VerifiedStore, semester: str) -> None:
    """**读回**刚写入的 env 文件，断言它指向同一个已验证 store 与同一个 acceptance digest。"""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(
            EXIT_ENV_OUTPUT,
            _payload(
                stage="env_output",
                category="env_out_unreadable",
                exception_type=type(exc).__name__,
            ),
        )

    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        parsed[name.strip()] = value.strip()

    if _resolve(parsed.get("APP_COURSE_DATA_SQLITE_PATH", "")) != store.path:
        _fail(
            EXIT_STORE_BINDING,
            _payload(stage="env_output", category="env_file_db_path_not_verified_store"),
        )
    if parsed.get("APP_COURSE_DATA_ACCEPTANCE_SHA256") != store.acceptance_sha256:
        _fail(
            EXIT_STORE_BINDING,
            _payload(stage="env_output", category="env_file_acceptance_sha_not_verified"),
        )
    if parsed.get("APP_COURSE_DATA_SEMESTER") != semester:
        _fail(
            EXIT_STORE_BINDING,
            _payload(stage="env_output", category="env_file_semester_mismatch"),
        )


def _replace_bytes_atomically(path: Path, content: bytes) -> None:
    """显式 `--overwrite-env` 路径：同目录临时文件 + 原子 replace。"""

    directory = path.parent
    if not directory.is_dir():
        _fail(
            EXIT_ENV_OUTPUT,
            _payload(
                stage="env_output",
                category="parent_directory_missing",
                message="parent directory must exist; this tool never creates directories",
            ),
        )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        _fail(
            EXIT_ENV_OUTPUT,
            _payload(
                stage="env_output",
                category="env_out_write_failed",
                exception_type=type(exc).__name__,
            ),
        )
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


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
    handoff: Path | None,
    draft_handoff_out: Path | None,
    collector_commit: str | None,
    capture_window: tuple[str | None, str | None],
    campus_store: Path,
    sqlite: Path,
    output_manifest: Path | None,
    env_out: Path | None,
    curriculum_case: str | None,
    allow_existing_store: bool,
    overwrite_env: bool,
) -> dict[str, object]:
    # ⚠️ 所有 store 路径在这里**解析一次**，之后全链路只用解析后的绝对路径。
    resolved_sqlite = _resolve(sqlite)
    resolved_campus_store = _resolve(campus_store)

    if resolved_sqlite.exists() and not allow_existing_store:
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
        campus_store=resolved_campus_store,
    )

    # ---- 草稿步骤（产出草稿；没有已批准 inventory 时到此为止） ---------- #
    if draft_inventory_out is not None or draft_handoff_out is not None:
        draft_payload: dict[str, object] = {
            "status": (
                "draft_inventory_written"
                if draft_inventory_out is not None
                else "draft_handoff_written"
            ),
            "level": "draft_only_no_acceptance",
            "acceptance_performed": False,
            "semester": semester,
            "campus_acceptances": campus,
        }
        if draft_inventory_out is not None:
            draft_payload["draft_inventory"] = _run_acceptance(
                _acceptance_argv(
                    semester=semester,
                    baseline_before=baseline_before,
                    baseline_after=baseline_after,
                    bundles=bundles,
                    inventory=None,
                    draft_inventory_out=draft_inventory_out,
                    campus_store=resolved_campus_store,
                    sqlite=resolved_sqlite,
                    output_manifest=None,
                )
            )
        if draft_handoff_out is not None:
            document = _build_handoff(
                semester=semester,
                bundles=bundles,
                baseline_before=baseline_before,
                baseline_after=baseline_after,
                state=(
                    HANDOFF_STATE_SYNTHETIC if semester == PREFLIGHT_SEMESTER else HANDOFF_STATE_DRAFT
                ),
                synthetic=semester == PREFLIGHT_SEMESTER,
                collector_commit=collector_commit,
                window_started_at=capture_window[0],
                window_ended_at=capture_window[1],
                diagnostics_path=None,
            )
            _write_json_document(
                draft_handoff_out,
                document,
                exit_code=EXIT_HANDOFF,
                already_exists_category="handoff_draft_already_exists",
            )
            draft_payload["draft_handoff"] = {
                "handoff_id": document["handoff_id"],
                "handoff_state": document["handoff_state"],
                "synthetic": document["synthetic"],
                "path": str(draft_handoff_out),
                "raw_bundle_sha256_by_shard": {
                    str(shard["shard_id"]): shard["raw_bundle_sha256"]
                    for shard in document["shards"]  # type: ignore[index]
                },
            }

        if inventory is None:
            draft_payload["next_step"] = (
                "approve the draft(s) out of band (handoff: set handoff_state=approved and fill "
                "approved_by/approved_at), then rerun with --inventory and --handoff "
                "(this tool cannot prove any approval)"
            )
            return draft_payload

    if inventory is None:
        _fail(
            EXIT_ARGUMENTS,
            _payload(
                stage="arguments",
                category="inventory_invalid",
                message="an approved --inventory is required (or use --draft-inventory-out first)",
            ),
        )

    # ---- handoff 预检（在被接受数据产生之前就 fail closed） -------------- #
    handoff_summary: dict[str, object] | None = None
    if handoff is not None:
        try:
            document = json.loads(Path(handoff).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _fail(EXIT_HANDOFF, _payload(stage="handoff", category="handoff_unreadable"))
        _require_handoff_shape(document)
        if document["handoff_state"] != HANDOFF_STATE_APPROVED or document["synthetic"] is not False:
            _fail(
                EXIT_HANDOFF,
                _payload(
                    stage="handoff",
                    category="handoff_not_approved",
                    message="handoff must be approved and non-synthetic",
                ),
            )
        if document["semester"] != semester:
            _fail(EXIT_HANDOFF, _payload(stage="handoff", category="handoff_semester_mismatch"))

    acceptance = _run_acceptance(
        _acceptance_argv(
            semester=semester,
            baseline_before=baseline_before,
            baseline_after=baseline_after,
            bundles=bundles,
            inventory=inventory,
            draft_inventory_out=None,
            campus_store=resolved_campus_store,
            sqlite=resolved_sqlite,
            output_manifest=output_manifest,
        )
    )

    manifest_sha256 = acceptance.get("manifest_sha256")
    if not isinstance(manifest_sha256, str):
        _fail(
            EXIT_ACCEPTANCE_STAGE,
            _payload(stage="acceptance", category="manifest_invalid"),
        )

    store = _provider_read_back(
        sqlite=resolved_sqlite,
        semester=semester,
        acceptance_sha256=manifest_sha256,
        merged_offering_count=acceptance.get("merged_offering_count"),
    )

    if handoff is not None:
        handoff_summary = _validate_handoff(
            document,
            semester=semester,
            bundles=bundles,
            acceptance_shards=acceptance.get("shards"),
        )

    environment = _runtime_environment(store=store, curriculum_case=curriculum_case)

    # ---- READY 绑定断言（⛔ 在任何 ready 输出 / env 写入之前） ------------ #
    _assert_ready_binding(
        store=store,
        environment=environment,
        acceptance_manifest_sha256=manifest_sha256,
        semester=semester,
    )

    if env_out is not None:
        _write_env_file(env_out, environment, overwrite=overwrite_env)
        # ⛔ 写文件**不得**改变 DB 路径或 acceptance digest ⇒ 读回文件再断言一次。
        _assert_env_file_binding(path=env_out, store=store, semester=semester)

    blockers: list[str] = []
    if handoff_summary is None:
        blockers.append("real_source_handoff_missing")
    if store.offering_count <= 0:
        blockers.append("no_accepted_offerings")
    level2_eligible = not blockers

    return {
        "status": "ready",
        "level": "runtime_inputs_prepared",
        "acceptance_performed": True,
        "semester": semester,
        "campus_acceptances": campus,
        "acceptance": acceptance,
        "provider_read_back": store.summary(),
        "store_binding": {
            "resolved_verified_store_path": str(store.path),
            "env_db_path_equals_verified_store": True,
            "env_acceptance_sha_equals_verified_store": True,
            "env_db_path_semantics": "derived_from_the_verified_store_never_caller_supplied",
        },
        "runtime_environment": environment,
        "env_out": str(env_out) if env_out is not None else None,
        "env_out_semantics": (
            "created_atomically_and_only_if_absent" if not overwrite_env else "atomically_replaced_by_explicit_--overwrite-env"
        ),
        "real_source_provenance": handoff_summary,
        "level2_gate_conditions": list(LEVEL2_GATE_CONDITIONS),
        "level2_eligible": level2_eligible,
        "level2_blockers": blockers,
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
        # ⛔ synthetic handoff 永远不能满足 real-source gate。
        "level2_eligible": False,
        "level2_blockers": ["synthetic_preflight_handoff", "not_a_real_capture"],
        "preflight_dir": str(directory),
        "note": (
            "synthetic inputs only: this proves the operational chain, it is NOT Real E2E "
            "(no school data, no real acceptance, synthetic handoff, no LEVEL2/LEVEL3 claim)"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    preflight_dir: Path | None = None
    keep_dir = False
    try:
        args = parser.parse_args(argv)
        keep_dir = bool(args.keep_dir)

        handoff = Path(args.handoff) if args.handoff else None
        draft_handoff_out = Path(args.draft_handoff_out) if args.draft_handoff_out else None
        collector_commit = args.collector_commit
        capture_window = (args.capture_window_start, args.capture_window_end)

        if args.preflight:
            preflight_dir = Path(tempfile.mkdtemp(prefix="real-case-a-preflight-"))
            bundles = _write_synthetic_bundles(preflight_dir)
            semester = PREFLIGHT_SEMESTER
            baseline_before = baseline_after = PREFLIGHT_ROWS_PER_SHARD * len(
                APPROVED_FULL_SEMESTER_SHARDS
            )
            inventory = None
            draft_inventory_out = preflight_dir / "capture-inventory.draft.json"
            draft_handoff_out = preflight_dir / "capture-handoff.synthetic.json"
            campus_store = preflight_dir / "campus-acceptances.sqlite3"
            sqlite = preflight_dir / "course-data.sqlite3"
            output_manifest = preflight_dir / "manifest.json"
            env_out = None
            curriculum_case = None
            allow_existing_store = False
            overwrite_env = False
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
                    _payload(
                        stage="arguments",
                        category="inventory_invalid",
                        message="--inventory or --draft-inventory-out is required",
                    ),
                )
            campus_store = Path(args.campus_store)
            sqlite = Path(args.sqlite)
            output_manifest = Path(args.output_manifest) if args.output_manifest else None
            env_out = Path(args.env_out) if args.env_out else None
            curriculum_case = args.curriculum_case
            allow_existing_store = args.allow_existing_store
            overwrite_env = args.overwrite_env

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
                    campus_store=_resolve(campus_store),
                    sqlite=_resolve(sqlite),
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
            handoff=handoff,
            draft_handoff_out=draft_handoff_out,
            collector_commit=collector_commit,
            capture_window=capture_window,
            campus_store=campus_store,
            sqlite=sqlite,
            output_manifest=output_manifest,
            env_out=env_out,
            curriculum_case=curriculum_case,
            allow_existing_store=allow_existing_store,
            overwrite_env=overwrite_env,
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
