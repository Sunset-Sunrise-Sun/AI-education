"""**共享 profile 注册表**与文档类型判定的回归测试（要求 1、2、3、10）。

本文件的核心断言：

| 断言 | 为什么重要 |
| --- | --- |
| CLI 与 HTTP 用**同一份** profile | 第 3 轮审核提出的集成缺口：两套规则会漂移 |
| HTTP **不接收**列位映射 | 调用方⛔ 不能提交任意课程列位 |
| 文档类型**只由内容结构**判定 | ⛔ 不由专业名 / 文件名 / 角色决定真实性 |
| 断言类型与内容不符即拒绝 | 防"填一个专业名就当成真数据" |
| 未知 / 空 / 非字符串类型即拒绝 | fail closed |

⚠️ 真实 PDF **不进仓库**，因此涉及真实文件的用例在文件不存在时 **skip**；
CI 上会 skip，本地有材料时会全跑（`pdf_profiles_acceptance`）。
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from app.curriculum import pdf_profiles
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_profiles import (
    DOCUMENT_TYPES,
    detect_document_type,
    fingerprint_sha256,
    list_document_types,
    load_curriculum_pdf_verified,
    profile_for,
    verify_document_type,
)
from app.services import curriculum_pdf_ingest as ingest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

#: 真实文件的**磁盘路径**（percent-encoded 文件名）与期望特征。
REAL_FILES: dict[str, tuple[Path, int, int, int]] = {
    "yuangan-2025": (
        Path(
            r"D:\webDownload\%E9%81%A5%E6%84%9F%E7%A7%91%E5%AD%A6%E4%B8%8E%E6%8A%80%E6%9C%AF"
            r"_2025%E7%BA%A7_%E5%9F%B9%E5%85%BB%E6%96%B9%E6%A1%88.pdf"
        ),
        8,
        84,
        2,
    ),
    "netsec-2025": (
        Path(
            r"D:\webDownload\%E7%BD%91%E7%BB%9C%E7%A9%BA%E9%97%B4%E5%AE%89%E5%85%A8"
            r"_2025%E7%BA%A7_%E5%9F%B9%E5%85%BB%E6%96%B9%E6%A1%88.pdf"
        ),
        9,
        89,
        6,
    ),
}


def _real_bytes(key: str) -> bytes:
    path = REAL_FILES[key][0]
    if not path.is_file():
        pytest.skip(f"real PDF not available on this machine: {key}")
    return path.read_bytes()


# --------------------------------------------------------------------------- #
# 注册表本身
# --------------------------------------------------------------------------- #

def test_registry_has_exactly_the_two_verified_documents() -> None:
    keys = {item.key for item in DOCUMENT_TYPES}
    assert keys == {"yuangan-2025", "netsec-2025"}


def test_registry_is_public_safe() -> None:
    """给前端的清单⛔ 不含任何列位映射（只有说明性字段）。"""

    for item in list_document_types():
        assert set(item) == {
            "key", "major", "cohort", "label", "verified_pages", "declared_tables",
        }
        assert item["declared_tables"] > 0


def test_every_declared_header_has_a_column_index() -> None:
    """结构指纹的前提：`expected_headers` 的每个键都要在 `columns` 里有列号。"""

    for document in DOCUMENT_TYPES:
        for spec in document.tables:
            assert set(spec["expected_headers"]) <= set(spec["columns"]), document.key


def test_declared_pages_are_within_the_verified_page_count() -> None:
    for document in DOCUMENT_TYPES:
        for spec in document.tables:
            for page in spec["pages"]:
                assert 1 <= page <= document.verified_pages, document.key


def test_two_documents_have_different_fingerprints() -> None:
    """两份文件必须能被结构指纹区分（否则判定必然歧义）。"""

    prints = {fingerprint_sha256(item) for item in DOCUMENT_TYPES}
    assert len(prints) == 2


def test_fingerprints_do_not_leak_major_name() -> None:
    """指纹只由"页号 + 表序号 + 表头文字"决定，⛔ 与专业名无关。"""

    for document in DOCUMENT_TYPES:
        source = inspect.getsource(pdf_profiles._fingerprint)
        assert "major" not in source
        assert "label" not in source


# --------------------------------------------------------------------------- #
# profile_for / 类型合法性（fail closed）
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad", ["", "   ", "bogus", "yuangan", None, 123, True, ["yuangan-2025"]])
def test_unknown_or_invalid_document_type_is_rejected(bad: object) -> None:
    with pytest.raises(CurriculumNormalizationError):
        profile_for(bad)


def test_profile_for_accepts_a_known_key() -> None:
    assert profile_for("yuangan-2025").major == "遥感科学与技术"
    assert profile_for(" netsec-2025 ").key == "netsec-2025"


# --------------------------------------------------------------------------- #
# CLI 与 HTTP 共用同一份 profile（**第 3 轮审核的核心缺口**）
# --------------------------------------------------------------------------- #

def test_cli_and_http_share_one_profile_source() -> None:
    """结构断言：两条路径都必须经由 `load_curriculum_pdf_verified`。

    ⛔ 只要有一边自己留了一份默认声明，这个测试就该失败 ——
    上一轮的缺口正是"CLI 用真实 profile、HTTP 用猜出来的默认声明"。
    """

    cli_source = (
        REPOSITORY_ROOT / "backend" / "tools" / "parse_curriculum_pdf.py"
    ).read_text(encoding="utf-8")
    api_ingest_source = (
        REPOSITORY_ROOT / "backend" / "app" / "services" / "curriculum_pdf_ingest.py"
    ).read_text(encoding="utf-8")

    for name, source in (("cli", cli_source), ("http-ingest", api_ingest_source)):
        assert "load_curriculum_pdf_verified" in source, name
        # ⛔ 不得再出现本地写死的表格声明
        assert "DEFAULT_TABLES" not in source, name
        assert "_install_pdf_tables" not in source, name
        assert '"expected_headers"' not in source, name


def test_http_api_has_no_private_table_declaration() -> None:
    api_source = (
        REPOSITORY_ROOT / "backend" / "app" / "api" / "curriculum_import.py"
    ).read_text(encoding="utf-8")
    assert "_install_pdf_tables" not in api_source
    assert '"expected_headers"' not in api_source
    # 文档类型清单端点存在，且只暴露注册表内容
    assert "list_document_types" in api_source
    assert "curriculum-import/document-types" in api_source


def test_http_ingest_signature_rejects_arbitrary_mappings() -> None:
    """⛔ HTTP 摄取入口**不接受** `tables` 参数 —— 调用方无法提交列位映射。"""

    parameters = set(inspect.signature(ingest.ingest_pdf_upload).parameters)
    assert "tables" not in parameters
    assert "document_type" in parameters


def test_upload_outcome_kind_is_the_document_type() -> None:
    """响应里的 `kind` 来自注册表 key，⛔ 不是写死的 "tables"。"""

    source = (
        REPOSITORY_ROOT / "backend" / "app" / "services" / "curriculum_pdf_ingest.py"
    ).read_text(encoding="utf-8")
    assert "kind=document.key" in source


# --------------------------------------------------------------------------- #
# 真实文件：类型判定与解析数量（本地有材料时全跑，CI 上 skip）
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", sorted(REAL_FILES))
def test_real_pdf_is_detected_by_structure(key: str) -> None:
    data = _real_bytes(key)
    detected, report = detect_document_type(data)
    expected_pages = REAL_FILES[key][1]
    assert detected == key
    assert report["page_count"] == expected_pages
    assert report["scanned_suspected"] is False


@pytest.mark.parametrize("key", sorted(REAL_FILES))
def test_real_pdf_parses_to_the_verified_counts(key: str) -> None:
    data = _real_bytes(key)
    _pages, expected_rows, expected_unresolved = REAL_FILES[key][1:]
    document, result = load_curriculum_pdf_verified(data, source_id=f"sha256:{key}")
    assert document.key == key
    assert len(result.rows) == expected_rows + expected_unresolved
    assert len(result.issues) == 0

    resolved = [row for row in result.rows if not row.issues]
    unresolved = [row for row in result.rows if row.issues]
    assert len(resolved) == expected_rows
    assert len(unresolved) == expected_unresolved
    # 取值完整：课程号 / 名称 / 学分 / 开课学期一个都不缺
    for row in resolved:
        assert row.course_id and row.course_name and row.credit is not None
        assert row.recommended_term_text
    # 可追溯定位唯一
    records = [row.source_record for row in result.rows]
    assert len(set(records)) == len(records)


@pytest.mark.parametrize("key", sorted(REAL_FILES))
def test_real_pdf_rejects_the_other_document_type(key: str) -> None:
    """断言错误的类型必须被拒绝 —— ⛔ 不能靠填一个 key 就"通过"。"""

    wrong = "netsec-2025" if key == "yuangan-2025" else "yuangan-2025"
    data = _real_bytes(key)
    with pytest.raises(CurriculumNormalizationError):
        verify_document_type(data, wrong)
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_pdf_verified(data, source_id="x", document_key=wrong)


@pytest.mark.parametrize("key", sorted(REAL_FILES))
def test_real_pdf_declared_sha256_matches_the_registry(key: str) -> None:
    """注册表里登记的验收摘要必须与实际文件一致（防材料被替换后无人察觉）。"""

    data = _real_bytes(key)
    assert hashlib.sha256(data).hexdigest() == profile_for(key).verified_sha256


def test_detection_ignores_caller_supplied_identity() -> None:
    """结构判定的签名里**没有**任何"专业名 / 文件名 / 角色"参数。"""

    parameters = set(inspect.signature(detect_document_type).parameters)
    assert parameters == {"data"}


def test_major_and_filename_cannot_change_the_result() -> None:
    """篡改专业名 / 文件名后，`source_id` 与解析条数都不变。"""

    data = _real_bytes("yuangan-2025")
    first = ingest.ingest_pdf_upload(
        data, declared_length=str(len(data)), media_type="application/pdf",
        file_name="a.pdf", role="origin", major="遥感科学与技术", cohort="2025",
        source="s",
    )
    second = ingest.ingest_pdf_upload(
        data, declared_length=str(len(data)), media_type="application/pdf",
        file_name="完全不同的名字.pdf", role="target", major="毫不相干的专业",
        cohort="2099", source="t",
    )
    assert first.source_id == second.source_id
    assert first.kind == second.kind == "yuangan-2025"
    assert len(first.draft.course_records) == len(second.draft.course_records)


def test_requirement_stays_unknown_and_is_reported() -> None:
    """要求 6：已识别课程里 `requirement=UNKNOWN` 必须如实呈现。"""

    data = _real_bytes("yuangan-2025")
    outcome = ingest.ingest_pdf_upload(
        data, declared_length=str(len(data)), media_type="application/pdf",
        file_name="a.pdf", role="origin", major="遥感科学与技术", cohort="2025",
        source="s",
    )
    records = list(outcome.draft.course_records)
    assert records, "没有解析出课程"
    assert all(item["requirement"] == "unknown" for item in records)
    fields = {item["field"] for item in outcome.draft.human_required}
    assert "group_records" in fields
    # ⛔ 未声明 requirement 列，因此不应把每一行都算成"未解析"
    assert len(outcome.draft.unresolved_rows) == 2


def test_duplicate_course_ids_keep_their_own_locations() -> None:
    """要求 7：重复课程编码继续保留来源定位，⛔ 不自动去重。"""

    data = _real_bytes("yuangan-2025")
    outcome = ingest.ingest_pdf_upload(
        data, declared_length=str(len(data)), media_type="application/pdf",
        file_name="a.pdf", role="origin", major="遥感科学与技术", cohort="2025",
        source="s",
    )
    ids = [item["course_id"] for item in outcome.draft.course_records]
    duplicated = {value for value in ids if ids.count(value) > 1}
    assert duplicated, "真实文件里应当存在重复课程编码"
    # 每条记录都还在，且定位唯一
    records = [item["source_record"] for item in outcome.draft.course_records]
    assert len(set(records)) == len(records)
    fields = {item["field"] for item in outcome.draft.human_required}
    assert "duplicate_course_id" in fields


def test_draft_never_claims_verification() -> None:
    """要求 9：⛔ 不写批准锚点、⛔ 不标已核验、⛔ 不写正式目录。"""

    data = _real_bytes("yuangan-2025")
    outcome = ingest.ingest_pdf_upload(
        data, declared_length=str(len(data)), media_type="application/pdf",
        file_name="a.pdf", role="origin", major="遥感科学与技术", cohort="2025",
        source="s",
    )
    summary = ingest.describe_outcome(outcome, source="s")
    assert summary["verification"] == {"verified": False, "evidence": None}
    assert summary["complete"] is False
    assert summary["is_official_school_pdf"] is False
    assert summary["review_conclusion"] == ingest.PENDING_REVIEW_CONCLUSION
    assert outcome.draft.group_records == ()
    assert json.dumps(summary, ensure_ascii=False)  # 可序列化、无异常对象


# --------------------------------------------------------------------------- #
# 真实文件经由 **HTTP 端点**（要求 4、5）的端到端断言
# --------------------------------------------------------------------------- #

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


PARSE = "/api/v1/curriculum-import/parse-pdf"


def _post_real(client, body: bytes, *, major: str, role: str, document_type=None,
               file_name: str = "curriculum.pdf"):
    params = {"role": role, "major": major, "cohort": "2025", "source": "真实材料验收"}
    if document_type is not None:
        params["document_type"] = document_type
    return client.post(
        PARSE, content=body,
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(body)),
            "X-File-Name": file_name,
        },
        params=params,
    )


def test_http_endpoint_lists_only_verified_document_types(client) -> None:
    response = client.get("/api/v1/curriculum-import/document-types")
    assert response.status_code == 200
    keys = {item["key"] for item in response.json()["document_types"]}
    assert keys == {"yuangan-2025", "netsec-2025"}
    # ⛔ 清单里不得出现任何列位映射
    text = response.text
    assert "expected_headers" not in text
    assert "columns" not in text


@pytest.mark.parametrize("key", sorted(REAL_FILES))
def test_http_endpoint_parses_the_real_pdf(client, key: str) -> None:
    """**HTTP 上传真实 PDF**：自动判定 + 断言正确类型都必须成功，条数一致。"""

    data = _real_bytes(key)
    _pages, expected_rows, expected_unresolved = REAL_FILES[key][1:]

    auto = _post_real(client, data, major="任意专业名", role="origin")
    assert auto.status_code == 200, auto.text
    payload = auto.json()
    assert payload["source"]["kind"] == key
    assert len(payload["draft"]["course_records"]) == expected_rows
    assert len(payload["draft"]["unresolved_rows"]) == expected_unresolved
    assert payload["draft"]["document_issues"] == []
    assert payload["source"]["review_conclusion"] == "pending_group_lead_review"
    assert payload["source"]["verification_verified"] is False
    assert payload["source"]["is_official_school_pdf"] is False

    declared = _post_real(client, data, major="任意专业名", role="origin",
                          document_type=key)
    assert declared.status_code == 200
    assert declared.json()["source_id"] == payload["source_id"]


@pytest.mark.parametrize("key", sorted(REAL_FILES))
def test_http_endpoint_rejects_the_other_document_type(client, key: str) -> None:
    wrong = "netsec-2025" if key == "yuangan-2025" else "yuangan-2025"
    data = _real_bytes(key)
    response = _post_real(client, data, major="M", role="origin", document_type=wrong)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "pdf_import_unparsable"


def test_http_endpoint_rejects_an_unknown_document_type(client) -> None:
    data = _real_bytes("yuangan-2025")
    response = _post_real(client, data, major="M", role="origin",
                          document_type="not-a-real-type")
    assert response.status_code == 422


def test_http_endpoint_never_leaks_paths_and_writes_nothing(
    client, tmp_path: Path, monkeypatch,
) -> None:
    """要求 9：真实文件经由端点上传后，⛔ 不写目录、⛔ 不写锚点、⛔ 不回显路径。"""

    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    anchor = tmp_path / "trust-anchor.json"
    monkeypatch.setenv("APP_PERSONAL_CATALOG_DIR", str(catalog_dir))
    monkeypatch.setenv("APP_TRUST_ANCHOR_PATH", str(anchor))

    data = _real_bytes("yuangan-2025")
    response = _post_real(
        client, data, major="遥感科学与技术", role="origin",
        file_name=r"C:\Users\someone\private\curriculum.pdf",
    )
    assert response.status_code == 200, response.text

    assert list(catalog_dir.iterdir()) == []
    assert not anchor.exists()

    text = response.text
    for forbidden in ("C:\\", "Users", "private"):
        assert forbidden not in text, forbidden
    assert response.json()["source"]["file_name"] == "curriculum.pdf"


def test_http_endpoint_reports_requirement_unknown_and_pending_items(client) -> None:
    """要求 6：`requirement=UNKNOWN` 如实呈现，并明确不能直接进入正式补修分析。"""

    data = _real_bytes("yuangan-2025")
    response = _post_real(client, data, major="遥感科学与技术", role="origin")
    payload = response.json()
    assert all(item["requirement"] == "unknown" for item in payload["draft"]["course_records"])

    fields = {item["field"] for item in payload["draft"]["human_required"]}
    # ⛔ 课程组学分要求必须人工核验；⛔ 上传不构成来源核验
    assert {"group_records", "verification"} <= fields
    # 重复课程编码仍然只做提示，⛔ 不自动去重
    assert "duplicate_course_id" in fields
    # 结构完整的行不会被误算成"未解析"
    assert len(payload["draft"]["unresolved_rows"]) == 2
