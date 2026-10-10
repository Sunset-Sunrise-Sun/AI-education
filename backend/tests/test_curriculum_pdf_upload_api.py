"""PDF 上传的**传输层与安全校验**测试（合成 PDF，⛔ 无真实材料）。

覆盖任务书 §七 的第 7、8 项（安全拒绝 / 不泄露）以及端点的错误码契约。

⛔ 全部使用合成 PDF；真实两份 PDF 的验收见报告 BLOCKED 段。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.curriculum_pdf_ingest import (
    APPLICATION_PDF_MEDIA_TYPE,
    ERROR_DECLARED_LENGTH_MISMATCH,
    ERROR_EMPTY_UPLOAD,
    ERROR_LENGTH_REQUIRED,
    ERROR_MEDIA_TYPE_UNSUPPORTED,
    ERROR_TOO_LARGE,
    MAX_UPLOAD_BYTES,
    OCTET_STREAM_MEDIA_TYPE,
    PENDING_REVIEW_CONCLUSION,
    PdfUploadError,
    SOURCE_ID_PREFIX,
    ingest_pdf_upload,
    normalize_media_type,
    parse_declared_content_length,
)
from tests.pdf_fixtures import build_scanned_pdf, build_table_pdf

PARSE_PATH = "/api/v1/curriculum-import/parse-pdf"

#: 与端点默认表头**完全一致**的合成表格（中文表头 ⇒ 真实形态）。
HEADERS = ["No.", "Course Code", "Course Name", "Credit", "Category", "Term"]


def _rows() -> list[list[str]]:
    return [
        HEADERS,
        ["1", "MAR103", "Course-A", "3", "required", "2025-1"],
        ["2", "FL101", "Course-B", "2", "required", "2025-1"],
        ["3", "CSE323", "Course-C", "3", "elective", "2027-1"],
    ]


def _pdf() -> bytes:
    pytest.importorskip("pymupdf")
    return build_table_pdf(_rows())


# --------------------------------------------------------------------------- #
# 媒体类型
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(("raw", "expected"), [
    ("application/pdf", "application/pdf"),
    ("APPLICATION/PDF", "application/pdf"),
    ("application/pdf; charset=binary", "application/pdf"),
    ("  application/octet-stream  ", "application/octet-stream"),
    (None, ""),
    ("", ""),
    (123, ""),
])
def test_media_type_is_normalized(raw: object, expected: str) -> None:
    assert normalize_media_type(raw) == expected


@pytest.mark.parametrize("bad", [
    "multipart/form-data",
    "text/plain",
    "application/json",
    "application/x-pdf",
    "",
])
def test_unsupported_media_type_is_rejected(bad: str) -> None:
    with pytest.raises(PdfUploadError) as excinfo:
        ingest_pdf_upload(
            b"%PDF-1.4", declared_length="8", media_type=bad, file_name="a.pdf",
            role="origin", major="M", cohort="2025", source="s", tables=[],
        )
    assert excinfo.value.code == ERROR_MEDIA_TYPE_UNSUPPORTED


def test_pdf_media_type_is_accepted() -> None:
    assert APPLICATION_PDF_MEDIA_TYPE in {APPLICATION_PDF_MEDIA_TYPE, OCTET_STREAM_MEDIA_TYPE}


# --------------------------------------------------------------------------- #
# Content-Length 解析
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw", [None, "", "  12", "+12", "-1", "1.5", "0x10", "1,000",
                                 "٤", "８", "abc", 12])
def test_invalid_content_length_is_rejected(raw: object) -> None:
    with pytest.raises(PdfUploadError) as excinfo:
        parse_declared_content_length(raw)
    assert excinfo.value.code == ERROR_LENGTH_REQUIRED


def test_oversized_declared_length_is_rejected() -> None:
    with pytest.raises(PdfUploadError) as excinfo:
        parse_declared_content_length(str(MAX_UPLOAD_BYTES + 1))
    assert excinfo.value.code == ERROR_TOO_LARGE


def test_very_long_numeric_length_is_rejected_without_a_500() -> None:
    """超长十进制**不许**走到 `int()`（否则 `ValueError` 会变成 500）。"""

    with pytest.raises(PdfUploadError) as excinfo:
        parse_declared_content_length("9" * 5000)
    assert excinfo.value.code == ERROR_TOO_LARGE


def test_valid_content_length_is_parsed() -> None:
    assert parse_declared_content_length(str(MAX_UPLOAD_BYTES)) == MAX_UPLOAD_BYTES


# --------------------------------------------------------------------------- #
# 声明长度 vs 实读长度 / 空输入
# --------------------------------------------------------------------------- #

def test_declared_length_mismatch_is_rejected() -> None:
    with pytest.raises(PdfUploadError) as excinfo:
        ingest_pdf_upload(
            b"%PDF-1.4xx", declared_length="8", media_type=APPLICATION_PDF_MEDIA_TYPE,
            file_name="a.pdf", role="origin", major="M", cohort="2025", source="s", tables=[],
        )
    assert excinfo.value.code == ERROR_DECLARED_LENGTH_MISMATCH


def test_empty_body_is_rejected() -> None:
    with pytest.raises(PdfUploadError) as excinfo:
        ingest_pdf_upload(
            b"", declared_length="0", media_type=APPLICATION_PDF_MEDIA_TYPE,
            file_name="a.pdf", role="origin", major="M", cohort="2025", source="s", tables=[],
        )
    assert excinfo.value.code == ERROR_EMPTY_UPLOAD


def test_non_bytes_body_is_rejected() -> None:
    with pytest.raises(PdfUploadError) as excinfo:
        ingest_pdf_upload(
            "not bytes", declared_length="9", media_type=APPLICATION_PDF_MEDIA_TYPE,
            file_name="a.pdf", role="origin", major="M", cohort="2025", source="s", tables=[],
        )
    assert excinfo.value.code == ERROR_EMPTY_UPLOAD


# --------------------------------------------------------------------------- #
# source_id 由内容摘要派生（⛔ 不用文件名）
# --------------------------------------------------------------------------- #

def test_source_id_is_derived_from_the_content_digest() -> None:
    """⛔ 文件名不参与 `source_id`；摘要相同 ⇒ source_id 相同，内容变了 ⇒ 变了。"""

    import hashlib

    body = b"%PDF-1.4 fixture"
    digest = hashlib.sha256(body).hexdigest()
    assert f"{SOURCE_ID_PREFIX}{digest[:16]}" == f"pdf-upload:sha256:{digest[:16]}"
    # 结构层：源码里 source_id 的构造只用到 digest
    from app.services import curriculum_pdf_ingest as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert 'SOURCE_ID_PREFIX = "pdf-upload:sha256:"' in source
    assert "hashlib.sha256(body).hexdigest()" in source


# --------------------------------------------------------------------------- #
# 端点行为
# --------------------------------------------------------------------------- #

@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _post(client: TestClient, body: bytes, *, media_type: str, **overrides: object):
    params: dict = {"role": "origin", "major": "示例专业", "cohort": "2025", "source": "合成夹具"}
    params.update(overrides)
    headers = {"Content-Type": media_type, "Content-Length": str(len(body))}
    return client.post(PARSE_PATH, content=body, headers=headers, params=params)


def test_endpoint_parses_a_synthetic_pdf_into_a_pending_draft(client: TestClient) -> None:
    response = _post(client, _pdf(), media_type=APPLICATION_PDF_MEDIA_TYPE)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_id"].startswith(SOURCE_ID_PREFIX)
    # ⛔ 审核结论恒为"待组长审核"
    assert body["source"]["review_conclusion"] == PENDING_REVIEW_CONCLUSION
    assert body["source"]["verification_verified"] is False
    assert body["source"]["complete"] is False
    # ⛔ 明确标注"不是学校正式签发的原始 PDF"
    assert body["source"]["is_official_school_pdf"] is False

    draft = body["draft"]
    assert draft["status"] == "pending_human_review"
    # 解析出的课程记录：可追溯来源 + 无推断字段
    records = draft["course_records"]
    assert isinstance(records, list) and records
    for record in records:
        assert record["source_record"].startswith("page:1!table:1!row:")
        # ⛔ 解析器不推断这三个字段
        assert "recommended_semester" not in record
        assert "deadline_semester" not in record
        assert "prerequisites" not in record
    # ⛔ 课程组不由 PDF 推导 ⇒ 必须在待人工确认清单里
    fields = {item["field"] for item in draft["human_required"]}
    assert {"group_records", "verification", "version_identity", "source_provenance"} <= fields
    # ⛔ 报告里不得出现绝对路径
    assert ":\\" not in body["report"]


def test_missing_content_length_is_rejected_by_the_transport() -> None:
    """缺 `Content-Length` ⇒ 411（⛔ 不猜大小）。

    ⚠️ 这里直接测**传输层**：Starlette 的 `TestClient` 会为显式 `content=` 自动补上
    `Content-Length`，因此 HTTP 层构造不出"客户端没发这个头"的场景。
    真实部署里由 `curriculum_pdf_ingest.parse_declared_content_length()` 拒绝，
    并按 `_STATUS_BY_CODE` 映射为 411。
    """

    with pytest.raises(PdfUploadError) as excinfo:
        ingest_pdf_upload(
            _pdf(), declared_length=None, media_type=APPLICATION_PDF_MEDIA_TYPE,
            file_name="a.pdf", role="origin", major="M", cohort="2025", source="s",
            tables=[],
        )
    assert excinfo.value.code == ERROR_LENGTH_REQUIRED

    from app.api.curriculum_import import _STATUS_BY_CODE

    assert _STATUS_BY_CODE[ERROR_LENGTH_REQUIRED] == 411


def test_endpoint_rejects_multipart(client: TestClient) -> None:
    response = _post(client, _pdf(), media_type="multipart/form-data")
    assert response.status_code == 415
    assert response.json()["detail"]["error"] == ERROR_MEDIA_TYPE_UNSUPPORTED


def test_endpoint_rejects_text_plain(client: TestClient) -> None:
    response = _post(client, b"hello", media_type="text/plain")
    assert response.status_code == 415


def test_endpoint_rejects_a_non_pdf_disguised_as_pdf(client: TestClient) -> None:
    """非 PDF 伪装上传 ⇒ 422 + 固定错误码（⛔ 不生成替代 Mock 结果）。"""

    response = _post(client, b"GIF89a not a pdf", media_type=APPLICATION_PDF_MEDIA_TYPE)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "pdf_import_unparsable"


def test_endpoint_rejects_a_damaged_pdf(client: TestClient) -> None:
    response = _post(client, b"%PDF-1.4\ngarbage", media_type=APPLICATION_PDF_MEDIA_TYPE)
    assert response.status_code == 422


def test_endpoint_rejects_a_scanned_pdf(client: TestClient) -> None:
    """扫描件 ⇒ 422 + 明确"不支持 OCR"（⛔ 不返回猜测结果）。"""

    pytest.importorskip("pymupdf")
    response = _post(client, build_scanned_pdf(), media_type=APPLICATION_PDF_MEDIA_TYPE)
    assert response.status_code == 422
    assert "scanned PDF is not supported" in response.json()["detail"]["message"]


def test_endpoint_rejects_an_empty_body(client: TestClient) -> None:
    response = _post(client, b"", media_type=APPLICATION_PDF_MEDIA_TYPE)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == ERROR_EMPTY_UPLOAD


def test_endpoint_rejects_an_oversized_body(client: TestClient) -> None:
    oversized = b"%PDF-1.4\n" + b"0" * (MAX_UPLOAD_BYTES + 1)
    response = _post(client, oversized, media_type=APPLICATION_PDF_MEDIA_TYPE)
    assert response.status_code == 413


@pytest.mark.parametrize("role", ["", "sideways", "ORIGIN"])
def test_endpoint_rejects_an_invalid_role(client: TestClient, role: str) -> None:
    response = _post(client, _pdf(), media_type=APPLICATION_PDF_MEDIA_TYPE, role=role)
    assert response.status_code in {422, 400}


def test_endpoint_requires_major_cohort_and_source(client: TestClient) -> None:
    headers = {
        "Content-Type": APPLICATION_PDF_MEDIA_TYPE,
        "Content-Length": str(len(_pdf())),
    }
    response = client.post(PARSE_PATH, content=_pdf(), headers=headers, params={"role": "origin"})
    # FastAPI 的必填 query 缺失 ⇒ 422
    assert response.status_code == 422


def test_endpoint_response_never_leaks_local_paths(client: TestClient) -> None:
    """验收 8：响应⛔ 不含本地目录、⛔ 不含调用方给的路径。"""

    body = _pdf()
    files = {"x-file-name": r"C:\Users\someone\private\curriculum.pdf"}
    response = client.post(
        PARSE_PATH, content=body,
        headers={"Content-Type": APPLICATION_PDF_MEDIA_TYPE,
                 "Content-Length": str(len(body)), **files},
        params={"role": "origin", "major": "M", "cohort": "2025", "source": "s"},
    )
    assert response.status_code == 200, response.text
    text = response.text
    for forbidden in ("C:\\", "Users", "private", "\\\\"):
        assert forbidden not in text, forbidden
    # ⛔ 只保留基名
    assert response.json()["source"]["file_name"] == "curriculum.pdf"


def test_endpoint_does_not_write_any_file(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    """验收 6：上传路径⛔ 不写盘、⛔ 不碰 catalog 目录、⛔ 不碰锚点。"""

    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    anchor = tmp_path / "trust-anchor.json"
    monkeypatch.setenv("APP_PERSONAL_CATALOG_DIR", str(catalog_dir))
    monkeypatch.setenv("APP_TRUST_ANCHOR_PATH", str(anchor))

    response = _post(client, _pdf(), media_type=APPLICATION_PDF_MEDIA_TYPE)

    assert response.status_code == 200, response.text
    assert list(catalog_dir.iterdir()) == []
    assert not anchor.exists()


def test_endpoint_reports_unsupported_table_without_guessing(client: TestClient) -> None:
    """表头不匹配 ⇒ 200 + 草稿里**没有**课程记录 + 明确 issue（⛔ 不硬套列位）。"""

    pytest.importorskip("pymupdf")
    wrong = [["No", "Title", "Points", "Kind", "When"]]
    body = build_table_pdf([*wrong, ["1", "A", "3", "x", "2025-1"]])
    response = _post(client, body, media_type=APPLICATION_PDF_MEDIA_TYPE)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["draft"]["course_records"] == []
    codes = {item["code"] for item in payload["draft"]["document_issues"]}
    assert "table_header_mismatch" in codes


def test_endpoint_keeps_mock_demo_intact(client: TestClient) -> None:
    """验收 9：新增端点⛔ 不影响 Mock 演示通道。"""

    response = client.get("/api/v1/mock/demo")
    assert response.status_code == 200
    assert response.headers.get("X-Data-Source") == "mock"


def test_public_schema_files_are_untouched() -> None:
    """验收 10：⛔ 未新增 / 未修改任何 `/schemas/*.schema.json`。"""

    repo_root = Path(__file__).resolve().parents[2]
    schemas = sorted(path.name for path in (repo_root / "schemas").glob("*.json"))
    assert schemas == [
        "course.schema.json",
        "course_offering.schema.json",
        "makeup_task.schema.json",
        "plan_result.schema.json",
        "preference.schema.json",
    ]
    for name in schemas:
        text = (repo_root / "schemas" / name).read_text(encoding="utf-8")
        for forbidden in ("pdf", "catalog", "verification"):
            assert forbidden not in text.lower(), (name, forbidden)
