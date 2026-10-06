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
默认且**唯一**的行为：目标不存在 ⇒ 原子独占创建成功；目标已存在 ⇒ fail closed
（⛔ 不静默覆盖、⛔ 无 TOCTOU 预检、⛔ **不存在**任何 overwrite 选项）
实现：同目录临时文件写全量 + fsync，再用 `os.link` **无覆盖**发布（不支持时退回 O_EXCL 独占创建）
     发布失败 / 中途失败 ⇒ 清理临时文件，绝不留下"看起来有效"的半截 env 文件
父目录不存在 ⇒ 直接失败（⛔ 不自动创建目录）
需要重新生成 ⇒ 操作员自己挑一个**新路径**，或**在工具之外**手动删除旧文件
```

## READY 的**最后一步**：发布之后再验证一次

```text
写 env 文件（若有）之后，ready 之前，必须：
  1. 从**刚写入的 env 文件**里解析 DB 路径 / acceptance SHA / semester
  2. 断言它们与已验证 store 一致（路径解析后相等、SHA 相等）
  3. **重新打开该 store** 并再次跑 provider 级权威验证（行数 / membership / trust chain）
  4. 任何在"验证之后、ready 之前"发生的库篡改 ⇒ ⛔ 不输出 ready
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

**批准元数据是硬门**：`handoff_state=approved` 还不够 —— `approved_by` 必须是非空字符串
（strip 后非空）、`approved_at` 必须是**带时区**的 RFC3339/ISO8601 时间戳；
否则即使数据链路 ready，也会得到 `level2_eligible: false` 与明确 blocker：

```text
handoff_approval_identity_missing      approved_by 缺失 / 空 / 纯空白
handoff_approval_timestamp_missing     approved_at 缺失 / 空
handoff_approval_timestamp_invalid     approved_at 不可解析 / 无时区
```

## Curriculum real-source evidence（BLOCKER 2B）

LEVEL2 还必须绑定**runtime 实际消费的 Curriculum 输入**（`APP_CASE_A_CURRICULUM_CASE_PATH`）：

```text
--draft-curriculum-provenance-out  → 草稿（curriculum_artifact_sha256 = **本地计算**的 case 文件 SHA-256）
人工批准（approval_state=approved + approved_by/approved_at）
--curriculum-provenance <approved.json> + --curriculum-case <同一个 case 文件>
  → 工具对**该文件**重新计算 SHA-256 并与记录比对（⛔ 不靠 data_source / case 名 / 自由文本）
```

Curriculum 门不成立（缺席 / 未批准 / synthetic / digest 缺失或不符 / 批准元数据无效）⇒
`level2_eligible = false`（`curriculum_*` blockers）。

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
import re
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
EXIT_CURRICULUM_PROVENANCE = 10
EXIT_CURRICULUM_BINDING = 11

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

#: LEVEL2 的 Course Data real-source 证据门（六条）。
COURSE_DATA_GATE_CONDITIONS: tuple[str, ...] = (
    "approved_real_capture_handoff_exists",
    "handoff_semester_matches_acceptance_semester",
    "handoff_contains_exactly_the_approved_five_shards",
    "handoff_raw_bundle_sha256_matches_campus_acceptance_inputs",
    "handoff_marked_approved_and_not_synthetic",
    "no_north_skip",
)

#: LEVEL2 的 Curriculum real-source 证据门（六条）。
CURRICULUM_GATE_CONDITIONS: tuple[str, ...] = (
    "approved_curriculum_provenance_exists",
    "curriculum_is_case_a_and_not_synthetic",
    "curriculum_provenance_approved",
    "curriculum_approval_identity_and_timestamp_valid",
    "curriculum_artifact_sha256_present_and_well_formed",
    "curriculum_artifact_sha256_matches_the_case_consumed_by_runtime",
)

#: 批准元数据的 blocker 码（⛔ 空 / 非法批准元数据绝不允许 level2_eligible=true）。
BLOCKER_APPROVAL_IDENTITY_MISSING = "handoff_approval_identity_missing"
BLOCKER_APPROVAL_TIMESTAMP_MISSING = "handoff_approval_timestamp_missing"
BLOCKER_APPROVAL_TIMESTAMP_INVALID = "handoff_approval_timestamp_invalid"

#: curriculum provenance（本地证据产物；⛔ 不是公共 API Schema）。
CURRICULUM_PROVENANCE_FORMAT = "sysu-real-curriculum-provenance-v1"
CURRICULUM_PROVENANCE_VERSION = 1
CURRICULUM_APPROVAL_STATE_APPROVED = "approved"

_CURRICULUM_PROVENANCE_KEYS = frozenset(
    {
        "curriculum_provenance_format",
        "curriculum_provenance_version",
        "curriculum_source_kind",
        "curriculum_case_id",
        "curriculum_target_version_id",
        "curriculum_applicable_term",
        "curriculum_artifact_sha256",
        "curriculum_format",
        "curriculum_format_version",
        "loader_commit",
        "synthetic",
        "approval_state",
        "approved_by",
        "approved_at",
        "approval_note",
    }
)
_CURRICULUM_REQUIRED_TEXT_KEYS = (
    "curriculum_source_kind",
    "curriculum_case_id",
    "curriculum_target_version_id",
    "curriculum_applicable_term",
    "curriculum_format",
    "curriculum_format_version",
)
_SHA256_HEX = re.compile(r"\A[0-9a-f]{64}\Z")


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
        help=(
            "the approved Case A curriculum case path. It is hashed (and echoed into the env "
            "output as its resolved absolute path) so the curriculum provenance digest can be "
            "compared with the exact input consumed by runtime"
        ),
    )
    parser.add_argument(
        "--curriculum-provenance",
        help=(
            "approved curriculum provenance JSON (approval_state=approved, synthetic=false); "
            "required for LEVEL2 eligibility"
        ),
    )
    parser.add_argument(
        "--draft-curriculum-provenance-out",
        help="write the curriculum provenance DRAFT (digest computed locally) and stop",
    )
    parser.add_argument("--curriculum-case-id", help="Case A identifier recorded in the provenance draft")
    parser.add_argument(
        "--curriculum-target-version-id", help="target curriculum version id (e.g. case-a-new)"
    )
    parser.add_argument(
        "--curriculum-applicable-term", help="the applicable term recorded in the provenance draft"
    )
    parser.add_argument("--curriculum-format", help="curriculum case document format (recorded as-is)")
    parser.add_argument("--curriculum-format-version", help="curriculum case document format version")
    parser.add_argument("--loader-commit", help="optional curriculum loader/parser commit to record")
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


def _parse_rfc3339(value: object) -> datetime | None:
    """解析**带时区**的 RFC3339 / ISO8601 时间戳；⛔ 天真（naive）时间戳不接受。"""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text[-1] in {"Z", "z"}:
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        return None
    return parsed


def _approval_blockers(
    *, approved_by: object, approved_at: object, prefix: str
) -> list[str]:
    """批准元数据硬门：⛔ 空 approver / 缺失或非法时间戳都产生明确 blocker。"""

    blockers: list[str] = []
    if not isinstance(approved_by, str) or not approved_by.strip():
        blockers.append(
            BLOCKER_APPROVAL_IDENTITY_MISSING if prefix == "" else f"{prefix}_identity_missing"
        )
    if not isinstance(approved_at, str) or not approved_at.strip():
        blockers.append(
            BLOCKER_APPROVAL_TIMESTAMP_MISSING if prefix == "" else f"{prefix}_timestamp_missing"
        )
    elif _parse_rfc3339(approved_at) is None:
        blockers.append(
            BLOCKER_APPROVAL_TIMESTAMP_INVALID if prefix == "" else f"{prefix}_timestamp_invalid"
        )
    return blockers


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
        # ⛔ 批准元数据是硬门：空 approver / 缺失或非法（含无时区）时间戳都进 blockers。
        "approval_blockers": _approval_blockers(
            approved_by=handoff["approved_by"], approved_at=handoff["approved_at"], prefix=""
        ),
    }


# --------------------------------------------------------------------------- #
# curriculum real-source provenance（BLOCKER 2B：本地证据产物，⛔ 不加公共 Schema）
# --------------------------------------------------------------------------- #


def _build_curriculum_provenance(
    *,
    case_path: Path,
    case_id: str,
    target_version_id: str,
    applicable_term: str,
    curriculum_format: str,
    curriculum_format_version: str,
    loader_commit: str | None,
    approval_state: str = "draft",
    approved_by: str | None = None,
    approved_at: str | None = None,
    approval_note: str | None = None,
) -> dict[str, object]:
    """构造 curriculum provenance 文档；digest 由**本地**对该 case 文件求 SHA-256 得到。"""

    return {
        "curriculum_provenance_format": CURRICULUM_PROVENANCE_FORMAT,
        "curriculum_provenance_version": CURRICULUM_PROVENANCE_VERSION,
        "curriculum_source_kind": "case_a_approved_case_json",
        "curriculum_case_id": case_id,
        "curriculum_target_version_id": target_version_id,
        "curriculum_applicable_term": applicable_term,
        "curriculum_artifact_sha256": _sha256_file(case_path),
        "curriculum_format": curriculum_format,
        "curriculum_format_version": curriculum_format_version,
        "loader_commit": loader_commit,
        "synthetic": False,
        "approval_state": approval_state,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "approval_note": approval_note,
    }


def _validate_curriculum_provenance(
    document: object, *, case_path: Path | None
) -> tuple[dict[str, object], list[str], "VerifiedCurriculum | None"]:
    """Curriculum real-source 门：返回 (summary, blockers, verified)。

    ⛔ `verified` **只**在记录结构合法、无 blocker、且 `case_path` 存在时构建；
    它是 env 里 curriculum 路径的**唯一来源**（外部无法再注入第二个路径 / digest）。
    ⛔ 结构与格式错误才硬失败（exit 10）。
    """

    if not isinstance(document, dict):
        _fail(
            EXIT_CURRICULUM_PROVENANCE,
            _payload(
                stage="curriculum_provenance",
                category="curriculum_provenance_invalid",
                message="curriculum provenance must be a JSON object",
            ),
        )
    unknown = set(document) - _CURRICULUM_PROVENANCE_KEYS
    if unknown:
        # ⛔ 未知键可能夹带凭据 / 原始文档 / 个人数据（不回显键名）。
        _fail(
            EXIT_CURRICULUM_PROVENANCE,
            _payload(
                stage="curriculum_provenance",
                category="curriculum_provenance_shape_invalid",
                unknown_key_count=len(unknown),
            ),
        )
    if (
        document.get("curriculum_provenance_format") != CURRICULUM_PROVENANCE_FORMAT
        or document.get("curriculum_provenance_version") != CURRICULUM_PROVENANCE_VERSION
    ):
        _fail(
            EXIT_CURRICULUM_PROVENANCE,
            _payload(stage="curriculum_provenance", category="curriculum_provenance_format_unsupported"),
        )

    blockers: list[str] = []

    for key in _CURRICULUM_REQUIRED_TEXT_KEYS:
        value = document.get(key)
        if not isinstance(value, str) or not value.strip():
            blockers.append(f"curriculum_field_missing::{key}")

    digest = document.get("curriculum_artifact_sha256")
    if not isinstance(digest, str) or not digest.strip():
        blockers.append("curriculum_digest_missing")
    elif _SHA256_HEX.fullmatch(digest.strip()) is None:
        blockers.append("curriculum_digest_invalid")
    elif case_path is None:
        blockers.append("curriculum_case_path_missing")
    elif _sha256_file(case_path) != digest.strip():
        blockers.append("curriculum_digest_mismatch")

    if document.get("synthetic") is not False:
        blockers.append("curriculum_evidence_synthetic")
    if document.get("approval_state") != CURRICULUM_APPROVAL_STATE_APPROVED:
        blockers.append("curriculum_evidence_not_approved")
    blockers.extend(
        _approval_blockers(
            approved_by=document.get("approved_by"),
            approved_at=document.get("approved_at"),
            prefix="curriculum",
        )
    )

    summary = {
        "curriculum_provenance_format": document.get("curriculum_provenance_format"),
        "curriculum_provenance_version": document.get("curriculum_provenance_version"),
        "curriculum_source_kind": document.get("curriculum_source_kind"),
        "curriculum_case_id": document.get("curriculum_case_id"),
        "curriculum_target_version_id": document.get("curriculum_target_version_id"),
        "curriculum_applicable_term": document.get("curriculum_applicable_term"),
        "curriculum_artifact_sha256": digest.strip() if isinstance(digest, str) else None,
        "curriculum_consumed_case_sha256": _sha256_file(case_path) if case_path is not None else None,
        "curriculum_format": document.get("curriculum_format"),
        "curriculum_format_version": document.get("curriculum_format_version"),
        "loader_commit": document.get("loader_commit"),
        "synthetic": document.get("synthetic"),
        "approval_state": document.get("approval_state"),
        "approved_by": document.get("approved_by"),
        "approved_at": document.get("approved_at"),
        "approval_note": document.get("approval_note"),
        "curriculum_blockers": blockers,
    }

    verified: VerifiedCurriculum | None = None
    if not blockers and case_path is not None and isinstance(digest, str):
        verified = VerifiedCurriculum(
            resolved_path=case_path,
            artifact_sha256=digest.strip(),
            case_id=str(document.get("curriculum_case_id")),
            target_version_id=str(document.get("curriculum_target_version_id")),
            applicable_term=str(document.get("curriculum_applicable_term")),
            curriculum_format=str(document.get("curriculum_format")),
            curriculum_format_version=str(document.get("curriculum_format_version")),
            loader_commit=document.get("loader_commit") if isinstance(document.get("loader_commit"), str) else None,
            approval_state=str(document.get("approval_state")),
            approved_by=str(document.get("approved_by")),
            approved_at=str(document.get("approved_at")),
            synthetic=document.get("synthetic") is True,
        )
    return summary, blockers, verified


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


@dataclass(frozen=True, slots=True)
class VerifiedCurriculum:
    """**刚通过 provenance 门**的 Curriculum 输入（env 里 curriculum 路径的唯一来源）。

    ⛔ READY 语义：env 里出现的 curriculum 路径必须能**再次**解析到同一个 canonical 文件、
    且该文件此刻的字节摘要仍等于 `artifact_sha256`（见 `_final_readiness_verification`）。
    """

    resolved_path: Path
    artifact_sha256: str
    case_id: str
    target_version_id: str
    applicable_term: str
    curriculum_format: str
    curriculum_format_version: str
    loader_commit: str | None
    approval_state: str
    approved_by: str
    approved_at: str
    synthetic: bool

    def summary(self) -> dict[str, object]:
        return {
            "resolved_path": str(self.resolved_path),
            "artifact_sha256": self.artifact_sha256,
            "case_id": self.case_id,
            "target_version_id": self.target_version_id,
            "applicable_term": self.applicable_term,
            "curriculum_format": self.curriculum_format,
            "curriculum_format_version": self.curriculum_format_version,
            "loader_commit": self.loader_commit,
            "approval_state": self.approval_state,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "synthetic": self.synthetic,
        }

    def approval_blockers(self) -> list[str]:
        return _approval_blockers(
            approved_by=self.approved_by, approved_at=self.approved_at, prefix="curriculum"
        )


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
    *, store: VerifiedStore, curriculum: VerifiedCurriculum | None
) -> dict[str, str]:
    """从**已验证对象**派生 env（⛔ 不存在第二个 DB / curriculum 路径或 digest 参数）。

    ⛔ `APP_CASE_A_CURRICULUM_CASE_PATH` **只**在存在 `VerifiedCurriculum` 时才出现：
    env 里绝不会出现"未被 provenance 门验证过"的 curriculum 路径。
    """

    environment = {
        "APP_REAL_CASE_A_ENABLED": "1",
        "APP_COURSE_DATA_SQLITE_PATH": str(store.path),
        "APP_COURSE_DATA_SEMESTER": store.semester,
        "APP_COURSE_DATA_ACCEPTANCE_SHA256": store.acceptance_sha256,
    }
    if curriculum is not None:
        environment["APP_CASE_A_CURRICULUM_CASE_PATH"] = str(curriculum.resolved_path)
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


def _write_env_file(path: Path, environment: dict[str, str]) -> None:
    """原子写 env 文件：**只**独占创建（已存在 ⇒ fail closed），⛔ 不留半截文件。

    ⛔ 不存在任何 overwrite 选项：需要重新生成时，操作员必须挑一个新路径，
    或在**工具之外**手动删除旧文件 —— READY 语义不允许"替换已发布配置"。
    """

    lines = [
        "# 本文件由 tools/prepare_real_case_a_runtime.py 生成：⛔ 不含任何凭据。",
        "# ⛔ 不要提交到仓库；真实 artifact 与本地路径都不入库。",
        f"# verified_store_path={environment.get('APP_COURSE_DATA_SQLITE_PATH', '<unset>')}",
        *(f"{name}={value}" for name, value in environment.items()),
        "",
    ]
    content = "\n".join(lines).encode("utf-8")

    _write_bytes_exclusive(
        path, content, exit_code=EXIT_ENV_OUTPUT, already_exists_category="env_out_already_exists"
    )


def _read_env_bindings(path: Path) -> dict[str, str]:
    """读回**刚写入的** env 文件并解析成键值（⛔ 不信任内存里的副本）。"""

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
    return parsed


def _final_readiness_verification(
    *,
    store: VerifiedStore,
    curriculum: VerifiedCurriculum | None,
    semester: str,
    env_path: Path | None,
) -> dict[str, object]:
    """ready 之前的**最后一步**（BLOCKER 1 + 最终 Curriculum TOCTOU 修复）。

    ```text
    Store 半边：
      1. 若有 env 文件：从**文件**里解析 DB 路径 / acceptance SHA / semester
      2. 断言文件里的绑定 == 已验证 store
      3. **重新打开该 store**，再跑一次 provider 级权威验证
    Curriculum 半边（仅当有 VerifiedCurriculum；即 env 里确实带了 curriculum 路径）：
      4. 从**刚写出的 env 文件**重新读出 APP_CASE_A_CURRICULUM_CASE_PATH
      5. **再次解析**该路径（follow symlink）并与已验证的 canonical 路径比较
      6. 断言文件仍存在且是常规文件
      7. 对**当前该路径下真实可达的字节**重算 SHA-256，与已批准 provenance digest 比较
      8. 重新评估批准门（non-synthetic / approved / approver / 带时区时间戳 / 格式版本）
    ⛔ 任何一步不成立 ⇒ fail closed（⛔ 不输出 ready）。
    ```
    """

    if env_path is not None:
        parsed = _read_env_bindings(env_path)
        file_db_path = parsed.get("APP_COURSE_DATA_SQLITE_PATH", "")
        file_sha = parsed.get("APP_COURSE_DATA_ACCEPTANCE_SHA256", "")
        file_semester = parsed.get("APP_COURSE_DATA_SEMESTER", "")
        if not file_db_path or _resolve(file_db_path) != store.path:
            _fail(
                EXIT_STORE_BINDING,
                _payload(stage="env_output", category="env_file_db_path_not_verified_store"),
            )
        if file_sha != store.acceptance_sha256:
            _fail(
                EXIT_STORE_BINDING,
                _payload(stage="env_output", category="env_file_acceptance_sha_not_verified"),
            )
        if file_semester != semester:
            _fail(
                EXIT_STORE_BINDING,
                _payload(stage="env_output", category="env_file_semester_mismatch"),
            )
        target_path = _resolve(file_db_path)
        file_curriculum_path = parsed.get("APP_CASE_A_CURRICULUM_CASE_PATH")
    else:
        target_path = store.path
        file_curriculum_path = None

    # ⛔ 发布之后再验证一次：此刻库若被篡改 / 破坏，必须 fail closed。
    recheck = _provider_read_back(
        sqlite=target_path,
        semester=semester,
        acceptance_sha256=store.acceptance_sha256,
        merged_offering_count=store.offering_count,
    )
    if (
        recheck.path != store.path
        or recheck.acceptance_sha256 != store.acceptance_sha256
        or recheck.offering_count != store.offering_count
        or recheck.member_count != store.member_count
    ):
        _fail(
            EXIT_STORE_BINDING,
            _payload(stage="ready_binding", category="final_store_reverification_mismatch"),
        )

    # ---- Curriculum 半边：路径重绑定 / 字节替换 / 批准证据失效 ⇒ 无 ready ---- #
    final_curriculum_reverified = False
    final_curriculum_path: str | None = None
    final_curriculum_sha256: str | None = None

    if curriculum is None:
        if file_curriculum_path is not None:
            # env 里出现了**未被 provenance 门验证过**的 curriculum 路径 ⇒ 拒绝。
            _fail(
                EXIT_CURRICULUM_BINDING,
                _payload(
                    stage="curriculum_final",
                    category="curriculum_final_path_mismatch",
                    message="env carries a curriculum path that was never verified",
                ),
            )
    else:
        if env_path is not None:
            if not file_curriculum_path:
                _fail(
                    EXIT_CURRICULUM_BINDING,
                    _payload(stage="curriculum_final", category="curriculum_final_path_missing"),
                )
            candidate = _resolve(file_curriculum_path)
            if candidate != curriculum.resolved_path:
                # symlink 重定向 / 目录重绑定 / env 路径被改写都会落在这里。
                _fail(
                    EXIT_CURRICULUM_BINDING,
                    _payload(
                        stage="curriculum_final",
                        category="curriculum_final_path_mismatch",
                        resolved_path_matches_verified=False,
                    ),
                )
        else:
            candidate = curriculum.resolved_path

        if not candidate.is_file():
            _fail(
                EXIT_CURRICULUM_BINDING,
                _payload(stage="curriculum_final", category="curriculum_final_path_missing"),
            )

        current_digest = _sha256_file(candidate)
        if current_digest != curriculum.artifact_sha256:
            _fail(
                EXIT_CURRICULUM_BINDING,
                _payload(
                    stage="curriculum_final",
                    category="curriculum_final_digest_mismatch",
                    digest_matches_approved_provenance=False,
                ),
            )

        if (
            curriculum.synthetic
            or curriculum.approval_state != CURRICULUM_APPROVAL_STATE_APPROVED
            or curriculum.approval_blockers()
            or not curriculum.curriculum_format.strip()
            or not curriculum.curriculum_format_version.strip()
            or not curriculum.case_id.strip()
            or not curriculum.target_version_id.strip()
            or not curriculum.applicable_term.strip()
        ):
            _fail(
                EXIT_CURRICULUM_BINDING,
                _payload(stage="curriculum_final", category="curriculum_final_approval_invalid"),
            )

        final_curriculum_reverified = True
        final_curriculum_path = str(candidate)
        final_curriculum_sha256 = current_digest

    return {
        "final_store_reverified": True,
        "final_store_path": str(recheck.path),
        "final_store_acceptance_sha256": recheck.acceptance_sha256,
        "final_store_offering_count": recheck.offering_count,
        "final_curriculum_reverified": final_curriculum_reverified,
        "final_curriculum_path": final_curriculum_path,
        "final_curriculum_sha256": final_curriculum_sha256,
        "env_file_read_back": env_path is not None,
        "readiness_scope": (
            "course_data_and_curriculum" if curriculum is not None else "course_data_only"
        ),
    }


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
    curriculum_provenance: Path | None,
    draft_curriculum_provenance_out: Path | None,
    collector_commit: str | None,
    loader_commit: str | None,
    curriculum_identity: dict[str, str | None],
    capture_window: tuple[str | None, str | None],
    campus_store: Path,
    sqlite: Path,
    output_manifest: Path | None,
    env_out: Path | None,
    curriculum_case: str | None,
    allow_existing_store: bool,
) -> dict[str, object]:
    # ⚠️ 所有 store 路径在这里**解析一次**，之后全链路只用解析后的绝对路径。
    resolved_sqlite = _resolve(sqlite)
    resolved_campus_store = _resolve(campus_store)
    # ⚠️ curriculum case 路径同样解析一次：digest 与 env 都指向**同一个**被解析文件。
    resolved_curriculum_case = _resolve(curriculum_case) if curriculum_case else None

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
    if (
        draft_inventory_out is not None
        or draft_handoff_out is not None
        or draft_curriculum_provenance_out is not None
    ):
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

        if draft_curriculum_provenance_out is not None:
            if resolved_curriculum_case is None or not resolved_curriculum_case.is_file():
                _fail(
                    EXIT_ARGUMENTS,
                    _payload(
                        stage="arguments",
                        category="curriculum_case_path_missing",
                        message="--draft-curriculum-provenance-out requires an existing --curriculum-case",
                    ),
                )
            missing_identity = [
                flag
                for flag, value in (
                    ("--curriculum-case-id", curriculum_identity["case_id"]),
                    ("--curriculum-target-version-id", curriculum_identity["target_version_id"]),
                    ("--curriculum-applicable-term", curriculum_identity["applicable_term"]),
                    ("--curriculum-format", curriculum_identity["curriculum_format"]),
                    ("--curriculum-format-version", curriculum_identity["format_version"]),
                )
                if not value or not str(value).strip()
            ]
            if missing_identity:
                _fail(
                    EXIT_ARGUMENTS,
                    _payload(
                        stage="arguments",
                        category="curriculum_identity_incomplete",
                        missing_flags=missing_identity,
                    ),
                )
            document = _build_curriculum_provenance(
                case_path=resolved_curriculum_case,
                case_id=str(curriculum_identity["case_id"]),
                target_version_id=str(curriculum_identity["target_version_id"]),
                applicable_term=str(curriculum_identity["applicable_term"]),
                curriculum_format=str(curriculum_identity["curriculum_format"]),
                curriculum_format_version=str(curriculum_identity["format_version"]),
                loader_commit=loader_commit,
            )
            _write_json_document(
                draft_curriculum_provenance_out,
                document,
                exit_code=EXIT_CURRICULUM_PROVENANCE,
                already_exists_category="curriculum_provenance_draft_already_exists",
            )
            draft_payload["draft_curriculum_provenance"] = {
                "curriculum_provenance_format": document["curriculum_provenance_format"],
                "curriculum_case_id": document["curriculum_case_id"],
                "curriculum_artifact_sha256": document["curriculum_artifact_sha256"],
                "approval_state": document["approval_state"],
                "path": str(draft_curriculum_provenance_out),
            }

        if inventory is None:
            draft_payload["next_step"] = (
                "approve the draft(s) out of band (handoff: handoff_state=approved + approved_by/"
                "approved_at; curriculum provenance: approval_state=approved + approved_by/"
                "approved_at), then rerun with --inventory, --handoff and --curriculum-provenance "
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

    # ---- curriculum provenance 预检（同样在被接受数据之前 fail closed） -- #
    curriculum_summary: dict[str, object] | None = None
    curriculum_document: object | None = None
    if curriculum_provenance is not None:
        try:
            curriculum_document = json.loads(Path(curriculum_provenance).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _fail(
                EXIT_CURRICULUM_PROVENANCE,
                _payload(stage="curriculum_provenance", category="curriculum_provenance_unreadable"),
            )
        if not isinstance(curriculum_document, dict) or (
            curriculum_document.get("curriculum_provenance_format") != CURRICULUM_PROVENANCE_FORMAT
        ):
            _fail(
                EXIT_CURRICULUM_PROVENANCE,
                _payload(
                    stage="curriculum_provenance",
                    category="curriculum_provenance_format_unsupported",
                ),
            )
        unknown = set(curriculum_document) - _CURRICULUM_PROVENANCE_KEYS
        if unknown:
            _fail(
                EXIT_CURRICULUM_PROVENANCE,
                _payload(
                    stage="curriculum_provenance",
                    category="curriculum_provenance_shape_invalid",
                    unknown_key_count=len(unknown),
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

    curriculum_blockers: list[str] = []
    verified_curriculum: VerifiedCurriculum | None = None
    if curriculum_document is None:
        curriculum_blockers.append("curriculum_provenance_missing")
    else:
        (
            curriculum_summary,
            curriculum_blockers,
            verified_curriculum,
        ) = _validate_curriculum_provenance(
            curriculum_document, case_path=resolved_curriculum_case
        )

    environment = _runtime_environment(store=store, curriculum=verified_curriculum)

    # ---- READY 绑定断言（⛔ 在任何 ready 输出 / env 写入之前） ------------ #
    _assert_ready_binding(
        store=store,
        environment=environment,
        acceptance_manifest_sha256=manifest_sha256,
        semester=semester,
    )

    # ---- env 独占创建（⛔ 无 overwrite 选项） --------------------------- #
    env_written = False
    if env_out is not None:
        _write_env_file(env_out, environment)
        env_written = True

    # ---- ready 之前的**最后一步**：从文件读回 + 重新打开 store 再验证 --- #
    final_verification = _final_readiness_verification(
        store=store,
        curriculum=verified_curriculum,
        semester=semester,
        env_path=env_out if env_written else None,
    )

    blockers: list[str] = []
    if handoff_summary is None:
        blockers.append("real_source_handoff_missing")
    else:
        blockers.extend(handoff_summary.get("approval_blockers", []))  # type: ignore[arg-type]
    blockers.extend(curriculum_blockers)
    if store.offering_count <= 0:
        blockers.append("no_accepted_offerings")
    level2_eligible = bool(
        blockers == [] and final_verification["final_curriculum_reverified"]
    )

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
        "curriculum_binding": {
            "resolved_curriculum_case_path": (
                str(verified_curriculum.resolved_path) if verified_curriculum is not None else None
            ),
            "curriculum_path_emitted": verified_curriculum is not None,
            "env_curriculum_case_path_equals_resolved_input": verified_curriculum is not None,
            "curriculum_case_digest_bound_to_evidence": verified_curriculum is not None,
            "curriculum_case_path_semantics": (
                "resolved_once_from_verified_curriculum_only_and_final_reverified"
            ),
        },
        "readiness_scope": final_verification["readiness_scope"],
        "final_readiness_verification": final_verification,
        "runtime_environment": environment,
        "env_out": str(env_out) if env_out is not None else None,
        # ⛔ 不存在 overwrite 选项：env 只能"独占创建"，已存在即 fail closed。
        "env_out_semantics": "created_atomically_and_only_if_absent_no_overwrite_option",
        "real_source_provenance": handoff_summary,
        "curriculum_provenance": curriculum_summary,
        "level2_gate_conditions": {
            "course_data": list(COURSE_DATA_GATE_CONDITIONS),
            "curriculum": list(CURRICULUM_GATE_CONDITIONS),
        },
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
        curriculum_provenance = (
            Path(args.curriculum_provenance) if args.curriculum_provenance else None
        )
        draft_curriculum_provenance_out = (
            Path(args.draft_curriculum_provenance_out)
            if args.draft_curriculum_provenance_out
            else None
        )
        collector_commit = args.collector_commit
        loader_commit = args.loader_commit
        curriculum_identity = {
            "case_id": args.curriculum_case_id,
            "target_version_id": args.curriculum_target_version_id,
            "applicable_term": args.curriculum_applicable_term,
            "curriculum_format": args.curriculum_format,
            "format_version": args.curriculum_format_version,
        }
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
            curriculum_provenance=curriculum_provenance,
            draft_curriculum_provenance_out=draft_curriculum_provenance_out,
            collector_commit=collector_commit,
            loader_commit=loader_commit,
            curriculum_identity=curriculum_identity,
            capture_window=capture_window,
            campus_store=campus_store,
            sqlite=sqlite,
            output_manifest=output_manifest,
            env_out=env_out,
            curriculum_case=curriculum_case,
            allow_existing_store=allow_existing_store,
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
