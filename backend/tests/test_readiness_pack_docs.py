"""Readiness pack 的**机器可检**回归：文档必须与当前实现一致（⛔ 不许变成陈旧 worklog）。

覆盖：
- `docs/e2e/REAL_DATA_EXECUTION_MAP.md` 里的依赖图 JSON：11 个步骤、必需字段、
  工具路径真实存在、已批准五校区表与代码常量**逐项一致**；
- 历史基线计数必须显式标注"仅参考、不得硬编码"；
- North 的 4 条禁令必须存在；
- `REAL_CAPTURE_AND_RUNTIME_RUNBOOK.md`：runtime env 名与 `planning_runtime.py` 一致、
  三种 digest 命名齐全、前端开关名与 `frontend/src/config.ts` 一致；
- `REAL_CASE_A_ACCEPTANCE.md` ⛔ 不得再把已取代的 `SnapshotCourseDataProvider` 写成 production Course Data Provider。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.course_data import APPROVED_FULL_SEMESTER_SHARDS  # noqa: E402

E2E_DOCS = REPOSITORY_ROOT / "docs" / "e2e"
TOOL_PATH = REPOSITORY_ROOT / "tools" / "prepare_real_case_a_runtime.py"
EXECUTION_MAP = E2E_DOCS / "REAL_DATA_EXECUTION_MAP.md"
RUNBOOK = E2E_DOCS / "REAL_CAPTURE_AND_RUNTIME_RUNBOOK.md"
EVIDENCE_PROTOCOL = E2E_DOCS / "REAL_E2E_EVIDENCE_PROTOCOL.md"
DECISION_NOTES = E2E_DOCS / "READINESS_DECISION_NOTES.md"
ACCEPTANCE = E2E_DOCS / "REAL_CASE_A_ACCEPTANCE.md"

REQUIRED_STEP_IDS = (
    "capture",
    "validate",
    "campus_acceptance",
    "draft_inventory",
    "handoff",
    "curriculum_evidence",
    "accept",
    "import",
    "provenance_verification",
    "configure",
    "start",
    "probe",
    "frontend",
    "evidence",
)
REQUIRED_STEP_KEYS = {
    "id",
    "actor",
    "tool",
    "command",
    "inputs",
    "outputs",
    "invariant",
    "failure_mode",
    "user_interaction",
}
RUNTIME_ENV_NAMES = (
    "APP_REAL_CASE_A_ENABLED",
    "APP_CASE_A_CURRICULUM_CASE_PATH",
    "APP_COURSE_DATA_SQLITE_PATH",
    "APP_COURSE_DATA_SEMESTER",
    "APP_COURSE_DATA_ACCEPTANCE_SHA256",
    # ⚠️ 本轮新增（F-01/F-02/F-03）：带外批准锚点。
    # 缺它 ⇒ runtime 以 `provenance_not_verified` 拒绝装配。
    "APP_TRUST_ANCHOR_PATH",
)


def _json_block(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    assert match is not None, f"{path.name} 必须包含一个 ```json 依赖图块"
    return json.loads(match.group(1))


def test_execution_map_covers_the_whole_chain_with_required_fields() -> None:
    chain = _json_block(EXECUTION_MAP)

    steps = chain["steps"]
    assert [step["id"] for step in steps] == list(REQUIRED_STEP_IDS)

    for step in steps:
        assert REQUIRED_STEP_KEYS <= set(step), f"step {step['id']} 缺少字段"
        assert step["user_interaction"] in {"required", "none"}
        assert isinstance(step["inputs"], list) and step["inputs"]
        assert isinstance(step["outputs"], list) and step["outputs"]


def test_execution_map_tool_paths_exist() -> None:
    chain = _json_block(EXECUTION_MAP)

    for step in chain["steps"]:
        tool = step["tool"]
        assert (REPOSITORY_ROOT / tool).exists(), f"{step['id']} 指向不存在的工具：{tool}"


def test_execution_map_marks_which_steps_need_a_human() -> None:
    chain = _json_block(EXECUTION_MAP)
    by_id = {step["id"]: step for step in chain["steps"]}

    # 采集 / 批准 inventory / 批准 handoff / 批准 curriculum 证据 / 配置 env / 启动 / 探针 /
    # 前端 / 证据需要人工；其余全自动。
    for step_id in (
        "capture",
        "draft_inventory",
        "handoff",
        "curriculum_evidence",
        "configure",
        "start",
        "probe",
        "frontend",
        "evidence",
    ):
        assert by_id[step_id]["user_interaction"] == "required"
    for step_id in ("validate", "campus_acceptance", "accept", "import", "provenance_verification"):
        assert by_id[step_id]["user_interaction"] == "none", step_id


def test_execution_map_approved_shards_match_the_code_constant() -> None:
    text = EXECUTION_MAP.read_text(encoding="utf-8")

    for shard in APPROVED_FULL_SEMESTER_SHARDS:
        assert f"`{shard.shard_id}`" in text, shard.shard_id
        assert f"`{shard.opening_school_number}`" in text, shard.opening_school_number

    # 五校区必须齐全（exact five-shard），且 North 必须被标为 suspended
    assert text.count("`-campus`") + text.count("-campus`") >= len(
        APPROVED_FULL_SEMESTER_SHARDS
    )
    assert "suspended" in text


def test_historical_baselines_are_explicitly_marked_as_non_authoritative() -> None:
    text = EXECUTION_MAP.read_text(encoding="utf-8")

    assert "仅作参考" in text and "不得硬编码" in text
    # 历史计数可以出现，但必须与"必须使用本次 diagnostics"的约束同现
    assert "baseline_before" in text and "baseline_after" in text
    assert "6880" in text  # 历史合计只作为历史观测出现


def test_north_rules_are_all_present() -> None:
    text = EXECUTION_MAP.read_text(encoding="utf-8")

    for prohibition in ("不跳过 North", "不合成 North", "不推断 North", "不放宽任何验收规则"):
        assert prohibition in text, prohibition


def test_runbook_documents_the_runtime_environment_contract() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    runtime_source = (BACKEND_ROOT / "app" / "services" / "planning_runtime.py").read_text(
        encoding="utf-8"
    )

    for name in RUNTIME_ENV_NAMES:
        assert f'"{name}"' in runtime_source or f"'{name}'" in runtime_source, name
        assert name in runbook, f"runbook 未记录 {name}"

    # 三种 digest 必须被明确区分（⛔ 不笼统写 "SHA"）
    for label in ("raw campus bundle digest", "campus acceptance digest", "full-semester manifest"):
        assert label in runbook, label

    # 前端开关名必须与 config.ts 的实现一致
    config_source = (REPOSITORY_ROOT / "frontend" / "src" / "config.ts").read_text(encoding="utf-8")
    assert "VITE_PLAN_API_ENABLED" in config_source
    assert "VITE_PLAN_API_ENABLED" in runbook
    assert "VITE_PROXY_TARGET" in runbook


def test_runbook_failure_matrix_matches_the_runtime_classification() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    # readiness/领域失败 → 503；无关内部错误 → 500
    assert runbook.count("503") >= 6
    assert "500" in runbook
    assert "real_pipeline_not_configured" in runbook


def test_evidence_protocol_forbids_personal_data_and_defines_both_levels() -> None:
    protocol = EVIDENCE_PROTOCOL.read_text(encoding="utf-8")

    assert "LEVEL 2" in protocol and "LEVEL 3" in protocol
    assert "真实学生个人数据" in protocol and "不得" in protocol
    assert "L2-0" in protocol and "L2-10" in protocol and "L3-10" in protocol
    # ⛔ 证据协议必须被验收文档引用
    assert EVIDENCE_PROTOCOL.name in ACCEPTANCE.read_text(encoding="utf-8")


def test_evidence_protocol_has_the_real_source_provenance_gate() -> None:
    """LEVEL2 必须含两半硬门（Course Data + Curriculum），且 LEVEL3 继承。"""

    protocol = EVIDENCE_PROTOCOL.read_text(encoding="utf-8")

    assert "COURSE-DATA-REAL-SOURCE-PROVENANCE" in protocol
    assert "CURRICULUM-REAL-SOURCE-PROVENANCE" in protocol
    assert "level2_eligible" in protocol
    assert "L2-0A" in protocol and "L2-0B" in protocol
    for condition in (
        "handoff.semester == acceptance.semester",
        "已批准的五个 shard",
        "五个 raw bundle SHA-256",
        "non-synthetic",
        "没有跳过 North",
        "handoff_approval_identity_missing",
        "curriculum_artifact_sha256",
        "curriculum_digest_mismatch",
        # final Curriculum TOCTOU 硬门
        "final_curriculum_reverified",
        "curriculum_final_path_mismatch",
        "curriculum_final_digest_mismatch",
        "curriculum_final_path_missing",
        "curriculum_final_approval_invalid",
        "readiness_scope",
    ):
        assert condition in protocol, condition


def test_docs_define_the_ready_and_partial_ready_status_semantics() -> None:
    """状态语义必须被文档精确定义，且⛔ 不允许从 partial_ready 启动真实 runtime。"""

    runbook = RUNBOOK.read_text(encoding="utf-8")
    protocol = EVIDENCE_PROTOCOL.read_text(encoding="utf-8")

    for text in (runbook, protocol):
        assert "partial_ready" in text
        assert "final_store_reverified" in text and "final_curriculum_reverified" in text
        assert "course_data_only" in text

    assert "完整 runtime input readiness" in runbook
    assert "即 **`level2_eligible == true`**" in protocol or "level2_eligible == true" in protocol
    # ⛔ 操作指引不得从 partial_ready 启动真实 runtime
    assert "不要从 partial_ready 启动真实 runtime" in runbook
    assert "不可" in runbook

    # 结构性不变量在文档与实现中一致
    tool_source = TOOL_PATH.read_text(encoding="utf-8")
    assert "_require_ready_invariant" in tool_source
    assert "ready_without_both_final_verifications" in tool_source
    assert 'STATUS_READY = "ready"' in tool_source
    assert 'STATUS_PARTIAL_READY = "partial_ready"' in tool_source


def test_runbook_has_no_overwrite_option_and_documents_the_curriculum_gate() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    # ⛔ overwrite 选项已删除：文档不得再建议它
    assert "--overwrite-env" not in runbook
    assert "不存在** overwrite 选项" in runbook or "⛔ **不存在** overwrite 选项" in runbook
    assert "新路径" in runbook

    assert "--curriculum-provenance" in runbook
    assert "--draft-curriculum-provenance-out" in runbook
    assert "curriculum_artifact_sha256" in runbook or "case digest" in runbook
    assert "final_readiness_verification" in runbook
    assert "level2_eligible" in runbook


def test_tool_help_exposes_no_overwrite_option() -> None:
    """源码级：工具⛔ 不得再声明任何 overwrite / force 选项。"""

    source = TOOL_PATH.read_text(encoding="utf-8")
    assert '"--overwrite-env"' not in source
    assert '"--force"' not in source
    assert '"--overwrite"' not in source


def test_runbook_defines_sharded_before_first_use() -> None:
    """`sharded` 必须在首次出现前被定义，且命令与当前代码一致。"""

    runbook = RUNBOOK.read_text(encoding="utf-8")

    definition_index = runbook.index("sharded（五校区分片采集）")
    first_use = runbook.index("collectSharded")
    assert definition_index < first_use, "sharded 必须先定义再使用"

    # 命令必须与当前采集器一致
    assert 'window.XuehangSysuCollector.collectSharded({ semester: "2026-1", maxPages: 20 })' in runbook
    assert 'toShardJson(sharded, "东校园")' in runbook
    assert "toDiagnosticsJson(sharded)" in runbook
    assert "五个互相独立的 raw Capture Bundle" in runbook
    # ⛔ 明确禁止手工合并 / 改 label
    assert "不要**手工合并" in runbook or "⛔ **不要**手工合并" in runbook
    assert "改写 source label" in runbook


def test_runbook_documents_the_handoff_and_env_overwrite_semantics() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "--draft-handoff-out" in runbook and "--handoff" in runbook
    assert "handoff_state" in runbook and "approved" in runbook
    assert "独占创建" in runbook
    assert "level2_eligible" in runbook
    assert "store_binding" in runbook


def test_decision_notes_cover_both_hardening_items_and_north_stop_conditions() -> None:
    notes = DECISION_NOTES.read_text(encoding="utf-8")

    assert "completed-courses/import" in notes
    assert "X-Data-Source" in notes
    assert "是否阻塞 Real E2E 证据" in notes
    assert "停止条件" in notes
    assert "不得称为" in notes and "限流" in notes


def test_acceptance_doc_no_longer_claims_the_superseded_provider() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")

    # 已取代的实现类⛔ 不得再被写成 production Course Data Provider
    assert "CourseDataProvider` **= `StoreBackedCourseDataProvider`**" in text
    assert "CourseDataProvider` **= `SnapshotCourseDataDataProvider`**" not in text
    assert "旧的 `SnapshotCourseDataProvider`" in text
    assert "full-semester acceptance" in text
