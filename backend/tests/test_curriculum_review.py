"""审核会话与决策 API 的回归测试（本轮指令 §二.D 的 1–9 项）。

⛔ 真实 PDF 不进仓库：涉及真实文件的用例在材料不存在时 **skip**（CI 上 skip）。
其他用例全部使用**合成对象**（直接调用 `build_classification_report` / `ReviewSessionStore`），
因此可在任何环境稳定运行。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.curriculum.pdf_evidence import (
    STATUS_CONFLICTING,
    STATUS_NO_EVIDENCE,
    STATUS_SINGLE,
    CategoryCandidate,
    CategoryEvidence,
    CategoryRequirement,
    build_classification_report,
)
from app.curriculum.pdf_reader import DocxCourseRow
from app.curriculum.requirements import RequirementKind
from app.services.curriculum_review import (
    ACTION_CONFIRM,
    ACTION_DEFER,
    ACTION_OVERRIDE,
    MAX_DECISIONS_PER_REQUEST,
    ReviewSessionStore,
    ReviewStoreError,
    build_export,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 说明：这里的候选分类**不绑定任何真实文件**。
SOURCE_ID = "pdf-upload:sha256:reviewfixture"
SHA256 = "a" * 64

APPENDIX = CategoryEvidence(
    kind="practice_appendix",
    category_code="专必",
    requirement=RequirementKind.REQUIRED,
    source_record="page:8!table:1!row:1",
    raw_text="GST101 | 专必",
)
SECTION = CategoryEvidence(
    kind="section_header",
    category_code=None,
    requirement=RequirementKind.ELECTIVE,
    source_record="page:5!table:2!row:3",
    raw_text="专业选修课模块",
)


def _candidate(
    course_id: str, record: str, *, status: str, requirement: RequirementKind,
    evidence: tuple[CategoryEvidence, ...] = (), complete: bool = False,
) -> CategoryCandidate:
    return CategoryCandidate(
        course_id=course_id,
        source_record=record,
        proposed_requirement=requirement,
        proposed_category_code=None,
        status=status,
        evidence=evidence,
        evidence_complete=complete,
    )


def _report(candidates: list[CategoryCandidate]) -> object:
    return _build_report(candidates)


def _build_report(candidates):
    from app.curriculum.pdf_evidence import CourseClassificationReport

    return CourseClassificationReport(
        candidates=tuple(candidates),
        category_requirements=(
            CategoryRequirement(
                category_code="专必",
                requirement=RequirementKind.REQUIRED,
                minimum_credit=78.0,
                source_record="page:1!table:1!row:3",
                raw_text="专必 | 78",
            ),
        ),
        section_rows=({"source_record": "page:5!table:2!row:1", "raw_text": "专业选修课模块"},),
        unmapped_category_codes=("荣誉课程",),
    )


def _store(**kwargs) -> ReviewSessionStore:
    return ReviewSessionStore(**kwargs)


def _session(store: ReviewSessionStore, candidates: list[CategoryCandidate]):
    return store.create(
        document_key="yuangan-2025",
        major="遥感科学与技术",
        cohort="2025",
        role="origin",
        file_name="curriculum.pdf",
        source_id=SOURCE_ID,
        source_sha256=SHA256,
        report=_build_report(candidates),
    )


# --------------------------------------------------------------------------- #
# §二.D.1 冲突证据：双方全部保留，⛔ 不自动取舍
# --------------------------------------------------------------------------- #

def test_conflicting_course_level_evidence_keeps_both_sides() -> None:
    """同一编码出现两种类别 ⇒ 候选为 UNKNOWN，且**两条证据都保留**。"""

    second = CategoryEvidence(
        kind="practice_appendix",
        category_code="专选",
        requirement=RequirementKind.ELECTIVE,
        source_record="page:8!table:1!row:9",
        raw_text="GST101 | 专选",
    )
    row = DocxCourseRow(
        table_index=2, row_index=1, course_id="GST101", course_name="遥感原理与方法",
        credit=3.0, requirement=RequirementKind.UNKNOWN,
        source_record="page:5!table:2!row:2",
    )
    report = build_classification_report(
        [row],
        category_requirements=(),
        appendix_evidence={"GST101": (APPENDIX, second)},
        sections=(),
        category_values={},
    )
    candidate = report.candidates[0]
    assert candidate.status == STATUS_CONFLICTING
    assert candidate.proposed_requirement is RequirementKind.UNKNOWN
    assert candidate.evidence_complete is False
    # ⛔ 双方证据都必须还在，且各自带定位与原文
    assert len(candidate.evidence) == 2
    assert {item.category_code for item in candidate.evidence} == {"专必", "专选"}
    assert all(item.source_record and item.raw_text for item in candidate.evidence)


def test_course_level_conflicting_with_section_is_reported_not_resolved() -> None:
    """课程级（必修）与小节级（选修）冲突 ⇒ UNKNOWN，⛔ 不取舍。"""

    row = DocxCourseRow(
        table_index=2, row_index=2, course_id="GST101", course_name="遥感原理与方法",
        credit=3.0, requirement=RequirementKind.UNKNOWN,
        source_record="page:5!table:2!row:3",
    )
    report = build_classification_report(
        [row],
        category_requirements=(),
        appendix_evidence={"GST101": (APPENDIX,)},
        sections=({"source_record": "page:5!table:2!row:1", "labels": ["专业选修课模块"]},),
        category_values={"专业选修课模块": RequirementKind.ELECTIVE},
    )
    candidate = report.candidates[0]
    assert candidate.status == STATUS_CONFLICTING
    assert candidate.proposed_requirement is RequirementKind.UNKNOWN


# --------------------------------------------------------------------------- #
# §二.D.2 / D.3 无证据与"仅小节级"都不能算决定性证据
# --------------------------------------------------------------------------- #

def test_course_without_any_evidence_stays_unknown() -> None:
    row = DocxCourseRow(
        table_index=1, row_index=1, course_id="XXX999", course_name="未知课",
        credit=1.0, requirement=RequirementKind.UNKNOWN,
        source_record="page:2!table:1!row:1",
    )
    report = build_classification_report(
        [row], category_requirements=(), appendix_evidence={}, sections=(),
        category_values={},
    )
    candidate = report.candidates[0]
    assert candidate.status == STATUS_NO_EVIDENCE
    assert candidate.proposed_requirement is RequirementKind.UNKNOWN
    assert candidate.evidence == ()
    assert report.statistics()["without_evidence"] == 1


def test_section_level_only_evidence_is_not_decisive() -> None:
    """只有模块小节依据 ⇒ 候选成立但 `evidence_complete=False`（⛔ 非编码级证据）。"""

    row = DocxCourseRow(
        table_index=2, row_index=1, course_id="GST5210", course_name="遥感建模",
        credit=2.0, requirement=RequirementKind.UNKNOWN,
        source_record="page:5!table:2!row:4",
    )
    report = build_classification_report(
        [row], category_requirements=(), appendix_evidence={},
        sections=({"source_record": "page:5!table:2!row:1", "labels": ["专业选修课模块"]},),
        category_values={"专业选修课模块": RequirementKind.ELECTIVE},
    )
    candidate = report.candidates[0]
    assert candidate.status == STATUS_SINGLE
    assert candidate.proposed_requirement is RequirementKind.ELECTIVE
    assert candidate.evidence_complete is False
    assert report.statistics()["section_only_candidates"] == 1


def test_undeclared_category_code_is_never_guessed() -> None:
    """未在声明映射里的代号 ⇒ ⛔ 不猜成必修/选修。"""

    row = DocxCourseRow(
        table_index=1, row_index=1, course_id="HON001", course_name="荣誉课",
        credit=1.0, requirement=RequirementKind.UNKNOWN,
        source_record="page:2!table:1!row:1",
    )
    report = build_classification_report(
        [row], category_requirements=(),
        appendix_evidence={"HON001": (CategoryEvidence(
            kind="practice_appendix", category_code="荣誉课程",
            requirement=RequirementKind.UNKNOWN,
            source_record="page:8!table:1!row:1", raw_text="HON001 | 荣誉课程",
        ),)},
        sections=(), category_values={},
    )
    candidate = report.candidates[0]
    assert candidate.proposed_requirement is RequirementKind.UNKNOWN


# --------------------------------------------------------------------------- #
# §二.D.4 无效确认 / 无理由修改被拒绝
# --------------------------------------------------------------------------- #

def test_confirm_is_rejected_for_no_evidence_and_unknown() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
        _candidate("A2", "page:2!table:1!row:2", status=STATUS_CONFLICTING,
                   requirement=RequirementKind.UNKNOWN),
    ])
    for record in ("page:2!table:1!row:1", "page:2!table:1!row:2"):
        with pytest.raises(ReviewStoreError) as excinfo:
            store.submit(session.review_id, [{"source_record": record, "action": ACTION_CONFIRM}])
        assert excinfo.value.code == "review_confirm_not_allowed"


def test_confirm_is_allowed_for_a_clear_single_source_candidate() -> None:
    store = _store()
    session = _session(store, [
        _candidate("GST101", "page:5!table:2!row:2", status=STATUS_SINGLE,
                   requirement=RequirementKind.REQUIRED, evidence=(APPENDIX,), complete=True),
    ])
    updated = store.submit(session.review_id, [
        {"source_record": "page:5!table:2!row:2", "action": ACTION_CONFIRM},
    ])
    decision = updated.decisions["page:5!table:2!row:2"]
    assert decision.action == ACTION_CONFIRM
    assert decision.requirement is None


def test_override_without_reason_is_rejected() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    for payload in (
        {"source_record": "page:2!table:1!row:1", "action": ACTION_OVERRIDE,
         "requirement": "required"},
        {"source_record": "page:2!table:1!row:1", "action": ACTION_OVERRIDE,
         "requirement": "required", "reason": "   "},
        {"source_record": "page:2!table:1!row:1", "action": ACTION_OVERRIDE,
         "reason": "有理由但没选类别"},
    ):
        with pytest.raises(ReviewStoreError):
            store.submit(session.review_id, [payload])


def test_override_rejects_unknown_or_invalid_requirement() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    for target in ("unknown", "必修", "", "both"):
        with pytest.raises(ReviewStoreError) as excinfo:
            store.submit(session.review_id, [{
                "source_record": "page:2!table:1!row:1", "action": ACTION_OVERRIDE,
                "requirement": target, "reason": "理由",
            }])
        assert excinfo.value.code == "review_invalid_requirement"


def test_override_records_human_judgement_with_reason() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    updated = store.submit(session.review_id, [{
        "source_record": "page:2!table:1!row:1", "action": ACTION_OVERRIDE,
        "requirement": "elective", "reason": "按学院口径为选修",
    }])
    decision = updated.decisions["page:2!table:1!row:1"]
    assert decision.requirement is RequirementKind.ELECTIVE
    assert decision.reason == "按学院口径为选修"
    # ⛔ 必须标明这条结论来自**人工判断**，不是 PDF 原文证据
    assert decision.to_payload()["decided_by"] == "reviewer_input_not_a_pdf_evidence"


def test_defer_never_picks_the_opposite_category() -> None:
    """拒绝建议 = defer ⇒ 回到未确认，⛔ 绝不自动选相反类别。"""

    store = _store()
    session = _session(store, [
        _candidate("GST101", "page:5!table:2!row:2", status=STATUS_SINGLE,
                   requirement=RequirementKind.REQUIRED, evidence=(APPENDIX,), complete=True),
    ])
    updated = store.submit(session.review_id, [
        {"source_record": "page:5!table:2!row:2", "action": ACTION_DEFER,
         "reason": "依据不足，暂不确认"},
    ])
    decision = updated.decisions["page:5!table:2!row:2"]
    assert decision.action == ACTION_DEFER
    assert decision.requirement is None


def test_reject_action_does_not_exist() -> None:
    """结构断言：⛔ 不存在 `reject` 动作。"""

    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    with pytest.raises(ReviewStoreError) as excinfo:
        store.submit(session.review_id, [
            {"source_record": "page:2!table:1!row:1", "action": "reject"},
        ])
    assert excinfo.value.code == "review_invalid_action"


# --------------------------------------------------------------------------- #
# §二.D.5 重复课程编码对应不同定位，决策互不覆盖
# --------------------------------------------------------------------------- #

def test_duplicate_course_ids_have_independent_decisions() -> None:
    store = _store()
    session = _session(store, [
        _candidate("GST213", "page:4!table:1!row:2", status=STATUS_SINGLE,
                   requirement=RequirementKind.REQUIRED, evidence=(APPENDIX,), complete=True),
        _candidate("GST213", "page:6!table:3!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    updated = store.submit(session.review_id, [
        {"source_record": "page:4!table:1!row:2", "action": ACTION_CONFIRM},
        {"source_record": "page:6!table:3!row:1", "action": ACTION_DEFER, "reason": "待核"},
    ])
    assert updated.decisions["page:4!table:1!row:2"].action == ACTION_CONFIRM
    assert updated.decisions["page:6!table:3!row:1"].action == ACTION_DEFER
    # 决策表的键是定位，⛔ 不是课程编码
    assert "GST213" not in updated.decisions


def test_resubmission_overwrites_and_is_counted() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    store.submit(session.review_id, [
        {"source_record": "page:2!table:1!row:1", "action": ACTION_DEFER, "reason": "先看"},
    ])
    updated = store.submit(session.review_id, [
        {"source_record": "page:2!table:1!row:1", "action": ACTION_OVERRIDE,
         "requirement": "required", "reason": "确认为必修"},
    ])
    decision = updated.decisions["page:2!table:1!row:1"]
    assert decision.action == ACTION_OVERRIDE
    assert decision.revision == 2
    assert updated.resubmissions["page:2!table:1!row:1"] == 1


def test_duplicate_records_inside_one_request_are_rejected() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    with pytest.raises(ReviewStoreError) as excinfo:
        store.submit(session.review_id, [
            {"source_record": "page:2!table:1!row:1", "action": ACTION_DEFER},
            {"source_record": "page:2!table:1!row:1", "action": ACTION_DEFER},
        ])
    assert excinfo.value.code == "review_duplicate_in_request"


# --------------------------------------------------------------------------- #
# §二.D.6 会话过期 / 未知会话 / 资源限额
# --------------------------------------------------------------------------- #

def test_unknown_session_is_rejected() -> None:
    store = _store()
    for bad in ("nope", "", None, 123):
        with pytest.raises(ReviewStoreError) as excinfo:
            store.get(bad)
        assert excinfo.value.code == "review_not_found"
        assert excinfo.value.status == 404


def test_expired_session_is_rejected() -> None:
    store = _store(ttl_seconds=1)
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    # 直接把过期时间推到过去，避免测试里真的 sleep
    store._sessions[session.review_id] = type(session)(
        **{**session.__dict__} if hasattr(session, "__dict__") else {}
    ) if False else session
    object.__setattr__(session, "expires_at", time.time() - 1)
    with pytest.raises(ReviewStoreError) as excinfo:
        store.get(session.review_id)
    assert excinfo.value.code == "review_not_found"
    assert store.expired_total >= 1


def test_session_capacity_limit_is_enforced() -> None:
    store = _store(max_sessions=2)
    candidates = [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ]
    _session(store, candidates)
    _session(store, candidates)
    with pytest.raises(ReviewStoreError) as excinfo:
        _session(store, candidates)
    assert excinfo.value.code == "review_capacity_reached"
    assert excinfo.value.status == 503
    assert store.rejected_capacity_total == 1


def test_too_many_decisions_in_one_request_is_rejected() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    payload = [
        {"source_record": "page:2!table:1!row:1", "action": ACTION_DEFER}
        for _ in range(MAX_DECISIONS_PER_REQUEST + 1)
    ]
    with pytest.raises(ReviewStoreError) as excinfo:
        store.submit(session.review_id, payload)
    assert excinfo.value.code == "review_too_many_decisions"


def test_review_ids_are_random_and_not_guessable() -> None:
    store = _store()
    candidates = [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ]
    first = _session(store, candidates).review_id
    second = _session(store, candidates).review_id
    assert first != second
    assert len(first) >= 32


def test_new_parse_never_inherits_previous_decisions() -> None:
    """⛔ 不得通过提交新 PDF 或切换类型悄悄继承旧审核决定。"""

    store = _store()
    candidates = [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ]
    first = _session(store, candidates)
    store.submit(first.review_id, [
        {"source_record": "page:2!table:1!row:1", "action": ACTION_DEFER, "reason": "旧会话"},
    ])
    second = _session(store, candidates)
    assert second.review_id != first.review_id
    assert second.decisions == {}


# --------------------------------------------------------------------------- #
# §二.D.7 客户端伪造 SHA-256 / 证据 / 课程分类都不能绕过服务端
# --------------------------------------------------------------------------- #

def test_client_cannot_inject_evidence_or_digest() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_SINGLE,
                   requirement=RequirementKind.REQUIRED, evidence=(APPENDIX,), complete=True),
    ])
    for extra in (
        {"source_sha256": "deadbeef"},
        {"evidence": [{"raw_text": "伪造证据"}]},
        {"course_id": "OTHER"},
        {"proposed_requirement": "elective"},
        {"status": "single_source"},
        {"review_id": "x"},
    ):
        payload = {"source_record": "page:2!table:1!row:1", "action": ACTION_CONFIRM, **extra}
        with pytest.raises(ReviewStoreError) as excinfo:
            store.submit(session.review_id, [payload])
        assert excinfo.value.code == "review_unknown_field"


def test_session_digest_and_evidence_are_server_owned() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_SINGLE,
                   requirement=RequirementKind.REQUIRED, evidence=(APPENDIX,), complete=True),
    ])
    store.submit(session.review_id, [
        {"source_record": "page:2!table:1!row:1", "action": ACTION_CONFIRM},
    ])
    fresh = store.get(session.review_id)
    assert fresh.source_sha256 == SHA256
    assert fresh.candidates[0].evidence[0].raw_text == "GST101 | 专必"


def test_unknown_source_record_is_rejected_entirely() -> None:
    """未知定位 ⇒ 整批拒绝（⛔ 不做部分应用）。"""

    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    with pytest.raises(ReviewStoreError) as excinfo:
        store.submit(session.review_id, [
            {"source_record": "page:2!table:1!row:1", "action": ACTION_DEFER},
            {"source_record": "page:99!table:1!row:1", "action": ACTION_DEFER},
        ])
    assert excinfo.value.code == "review_unknown_source_record"
    assert store.get(session.review_id).decisions == {}


# --------------------------------------------------------------------------- #
# §二.D.8 导出：绑定摘要，区分人工修改与原文证据
# --------------------------------------------------------------------------- #

def test_export_binds_the_source_digest_and_stays_a_draft() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    store.submit(session.review_id, [
        {"source_record": "page:2!table:1!row:1", "action": ACTION_OVERRIDE,
         "requirement": "required", "reason": "人工判断为必修"},
    ])
    record = build_export(store.get(session.review_id))
    assert record["source"]["source_sha256"] == SHA256
    assert record["verification"] == {"verified": False, "evidence": None}
    assert record["complete"] is False
    assert record["conclusion"] == "pending_group_lead_review"
    assert record["identity_authentication"] == "not_performed"
    # 人工修改与原文证据必须可区分
    decision = record["decisions"][0]
    assert decision["decided_by"] == "reviewer_input_not_a_pdf_evidence"
    assert decision["reason"] == "人工判断为必修"
    # 未解决清单必须列出无证据项
    kinds = {item["kind"] for item in record["unresolved_items"]}
    assert "no_evidence" in kinds


def test_export_lists_duplicate_course_ids_with_all_locations() -> None:
    store = _store()
    session = _session(store, [
        _candidate("GST213", "page:4!table:1!row:2", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
        _candidate("GST213", "page:6!table:3!row:1", status=STATUS_NO_EVIDENCE,
                   requirement=RequirementKind.UNKNOWN),
    ])
    record = build_export(session)
    assert record["duplicate_course_ids"]["GST213"] == [
        "page:4!table:1!row:2", "page:6!table:3!row:1",
    ]


def test_export_includes_section_only_items_as_unresolved() -> None:
    store = _store()
    session = _session(store, [
        _candidate("GST5210", "page:5!table:2!row:4", status=STATUS_SINGLE,
                   requirement=RequirementKind.ELECTIVE, evidence=(SECTION,),
                   complete=False),
    ])
    record = build_export(session)
    kinds = {item["kind"] for item in record["unresolved_items"]}
    assert "section_level_only" in kinds


# --------------------------------------------------------------------------- #
# §二.D.9 审核草稿不得进入正式 Planner（结构 + 契约）
# --------------------------------------------------------------------------- #

def test_review_modules_never_import_the_planner() -> None:
    """⚠️ 只检查**可执行代码**：注释与文档字符串里出现"planner"是说明，不是依赖。

    用 `ast` 取真实 import 节点，⛔ 不用子串匹配整份源码
    （否则文档里写"本模块不 import planner"反而会把自己判失败）。
    """

    import ast

    for name in (
        "backend/app/services/curriculum_review.py",
        "backend/app/api/curriculum_review.py",
        "backend/app/curriculum/pdf_evidence.py",
    ):
        tree = ast.parse((REPO_ROOT / name).read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        for module in modules:
            assert not module.startswith("app.planner"), (name, module)
            assert not module.startswith("app.integration"), (name, module)
            assert not module.startswith("app.curriculum.matching"), (name, module)


def test_review_export_can_never_claim_verification() -> None:
    store = _store()
    session = _session(store, [
        _candidate("A1", "page:2!table:1!row:1", status=STATUS_SINGLE,
                   requirement=RequirementKind.REQUIRED, evidence=(APPENDIX,), complete=True),
    ])
    store.submit(session.review_id, [
        {"source_record": "page:2!table:1!row:1", "action": ACTION_CONFIRM},
    ])
    record = build_export(store.get(session.review_id))
    text = json.dumps(record, ensure_ascii=False)
    assert '"verified": true' not in text
    assert '"complete": true' not in text
    # 进度里也必须是 false
    assert store.get(session.review_id).progress()["verification_verified"] is False


# --------------------------------------------------------------------------- #
# API 契约与权限边界（本轮指令 §一.2 要求补）
# --------------------------------------------------------------------------- #

@pytest.fixture
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_review_routes_are_registered_exactly() -> None:
    from app.main import app

    paths = {
        path for path in app.openapi()["paths"] if "curriculum-review" in path
    }
    assert paths == {
        "/api/v1/curriculum-review/{review_id}",
        "/api/v1/curriculum-review/{review_id}/decisions",
        "/api/v1/curriculum-review/{review_id}/export",
    }


def test_api_rejects_forged_fields_with_422(client: TestClient) -> None:
    review_id = _seed_api_session(client)
    response = client.post(
        f"/api/v1/curriculum-review/{review_id}/decisions",
        json={"decisions": [{
            "source_record": "page:2!table:1!row:1", "action": "confirm",
            "source_sha256": "deadbeef",
        }]},
    )
    assert response.status_code == 422


def test_api_rejects_empty_decision_list(client: TestClient) -> None:
    review_id = _seed_api_session(client)
    response = client.post(
        f"/api/v1/curriculum-review/{review_id}/decisions", json={"decisions": []},
    )
    assert response.status_code == 422


def test_api_unknown_session_returns_404(client: TestClient) -> None:
    for path in (
        "/api/v1/curriculum-review/nope",
        "/api/v1/curriculum-review/nope/export",
    ):
        assert client.get(path).status_code == 404
    assert client.post(
        "/api/v1/curriculum-review/nope/decisions",
        json={"decisions": [{"source_record": "x", "action": "defer"}]},
    ).status_code == 404


def test_api_over_long_review_id_is_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/curriculum-review/" + "x" * 300).status_code == 404


def test_api_export_carries_draft_header(client: TestClient) -> None:
    review_id = _seed_api_session(client)
    response = client.get(f"/api/v1/curriculum-review/{review_id}/export")
    assert response.status_code == 200
    assert response.headers["X-Review-Status"] == "draft_not_approved"
    assert response.json()["conclusion"] == "pending_group_lead_review"


def _seed_api_session(client: TestClient) -> str:
    """在 API 层的会话存储里放一个确定性会话（⛔ 不需要真实 PDF）。"""

    from app.services.curriculum_review import get_review_store

    store = get_review_store()
    session = store.create(
        document_key="yuangan-2025",
        major="遥感科学与技术",
        cohort="2025",
        role="origin",
        file_name="curriculum.pdf",
        source_id=SOURCE_ID,
        source_sha256=SHA256,
        report=_build_report([
            _candidate("A1", "page:2!table:1!row:1", status=STATUS_NO_EVIDENCE,
                       requirement=RequirementKind.UNKNOWN),
        ]),
    )
    return session.review_id


# --------------------------------------------------------------------------- #
# §二.D.10 两份真实 PDF 的候选统计与证据回归（材料缺失时 skip）
# --------------------------------------------------------------------------- #

REAL_FILES = {
    "yuangan-2025": (
        Path(
            r"D:\webDownload\%E9%81%A5%E6%84%9F%E7%A7%91%E5%AD%A6%E4%B8%8E%E6%8A%80%E6%9C%AF"
            r"_2025%E7%BA%A7_%E5%9F%B9%E5%85%BB%E6%96%B9%E6%A1%88.pdf"
        ),
        # (有证据, 无证据, 小节行, 仅小节级)
        (59, 25, 2, 10),
    ),
    "netsec-2025": (
        Path(
            r"D:\webDownload\%E7%BD%91%E7%BB%9C%E7%A9%BA%E9%97%B4%E5%AE%89%E5%85%A8"
            r"_2025%E7%BA%A7_%E5%9F%B9%E5%85%BB%E6%96%B9%E6%A1%88.pdf"
        ),
        (57, 32, 6, 23),
    ),
}


@pytest.mark.parametrize("key", sorted(REAL_FILES))
def test_real_pdf_classification_regression(key: str) -> None:
    path, (with_evidence, without, sections, section_only) = REAL_FILES[key]
    if not path.is_file():
        pytest.skip(f"real PDF not available on this machine: {key}")
    from app.curriculum.pdf_evidence import extract_evidence
    from app.curriculum.pdf_profiles import (
        category_values_for,
        load_curriculum_pdf_verified,
        profile_for,
    )

    data = path.read_bytes()
    document, result = load_curriculum_pdf_verified(data, source_id="t")
    requirements, appendix, section_rows, unmapped = extract_evidence(
        data, tables=document.tables,
    )
    report = build_classification_report(
        result.rows,
        category_requirements=requirements,
        appendix_evidence=appendix,
        sections=section_rows,
        category_values={
            code: RequirementKind(value)
            for code, value in category_values_for(profile_for(key)).items()
        },
        unmapped_category_codes=unmapped,
    )
    stats = report.statistics()
    assert stats["with_evidence"] == with_evidence
    assert stats["without_evidence"] == without
    assert stats["section_rows"] == sections
    assert stats["section_only_candidates"] == section_only
    assert stats["category_requirements"] == 4
    # 类别最低学分必须带原文与定位
    for item in report.category_requirements:
        assert item.minimum_credit is not None
        assert item.source_record and item.raw_text
    # `荣誉课程` 永远是未映射（⛔ 不猜）
    assert "荣誉课程" in report.unmapped_category_codes
    # 每条候选的定位必须唯一
    records = [item.source_record for item in report.candidates]
    assert len(set(records)) == len(records)
