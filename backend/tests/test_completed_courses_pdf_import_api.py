"""`POST /api/v1/completed-courses/import-pdf` 的接口测试。

⛔ 所有 fixture 都是虚构课程 / 学期 / 成绩（见 `pdf_fixtures.py`）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.curriculum.case import CurriculumCaseProvider, normalize_curriculum_case
from app.services import completed_courses_pdf_ingest as ingest
from tests import pdf_fixtures as fixtures

IMPORT_PATH = "/api/v1/completed-courses/import-pdf"
PDF_TYPE = "application/pdf"
OCTET_TYPE = "application/octet-stream"

_OTHER_PATHS = [
    "/api/v1/completed-courses/import",  # XLSX 旧入口必须仍然存在
]


@pytest.fixture(scope="module")
def transcript_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    directory = tmp_path_factory.mktemp("pdf-api")
    path = fixtures.build_case_a_transcript_pdf(directory / "DEMO-transcript.pdf")
    return path.read_bytes()


def _post(client: TestClient, body: bytes, content_type: str = PDF_TYPE, length: object = None):
    headers = {"Content-Type": content_type}
    if length is not None:
        headers["Content-Length"] = str(length)
    else:
        headers["Content-Length"] = str(len(body))
    return client.post(IMPORT_PATH, content=body, headers=headers)


def _error(response) -> str:  # type: ignore[no-untyped-def]
    return response.json()["detail"]["error"]


# --- 成功路径 ---


def test_pdf_import_returns_normalized_completed_courses(
    client: TestClient, transcript_bytes: bytes
) -> None:
    response = _post(client, transcript_bytes)
    assert response.status_code == 200
    payload = response.json()

    assert payload["record_count"] == 4
    assert payload["page_count"] == 1
    assert payload["columns_seen"] == 4
    assert payload["term_count"] == 2
    assert payload["terms"] == [
        fixtures.TERM_ONE.replace(" ", ""),
        fixtures.TERM_TWO.replace(" ", ""),
    ]
    assert payload["confirmed_course_id_count"] == 0
    assert payload["pending_course_id_count"] == 4
    assert payload["source_id"].startswith("upload:pdf:sha256:")

    records = payload["completed_input"]["records"]
    assert [record["course_name"] for record in records] == [
        "示例线性代数", "示例大学物理", "示例观测实践", "示例程序设计",
    ]
    for record in records:
        assert record["course_id"] is None
        assert record["course_id_status"] == "pending"
        assert record["id_match_source"] is None


def test_octet_stream_media_type_is_accepted(client: TestClient, transcript_bytes: bytes) -> None:
    response = _post(client, transcript_bytes, content_type=OCTET_TYPE)
    assert response.status_code == 200


def test_source_id_is_derived_from_content_not_filename(
    client: TestClient, transcript_bytes: bytes
) -> None:
    first = _post(client, transcript_bytes).json()
    second = _post(client, transcript_bytes).json()
    assert first["source_id"] == second["source_id"]
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["source_id"] not in transcript_bytes.decode("latin-1")


def test_same_layout_with_different_courses_gives_a_different_source_id(
    client: TestClient, transcript_bytes: bytes, tmp_path: Path
) -> None:
    other = fixtures.build_transcript_pdf(
        tmp_path / "DEMO-other.pdf",
        bands=[[(fixtures.TERM_ONE, [
            {"name": "示例另一门课", "credit": "1", "grade": "90", "attribute": "公必"},
        ])]],
    )
    response = _post(client, other.read_bytes())
    assert response.status_code == 200
    assert response.json()["source_id"] != _post(client, transcript_bytes).json()["source_id"]


# --- 错误语义 ---


@pytest.mark.parametrize("content_type", [
    "text/plain", "application/json", "multipart/form-data",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "",
])
def test_unsupported_media_types_are_rejected(
    client: TestClient, transcript_bytes: bytes, content_type: str
) -> None:
    headers = {"Content-Type": content_type} if content_type else {}
    headers["Content-Length"] = str(len(transcript_bytes))
    response = client.post(IMPORT_PATH, content=transcript_bytes, headers=headers)
    assert response.status_code == 415
    assert _error(response) == ingest.ERROR_UNSUPPORTED_MEDIA_TYPE


def test_missing_content_length_is_rejected(client: TestClient) -> None:
    response = client.post(
        IMPORT_PATH,
        content=b"%PDF-1.7",
        headers={"Content-Type": PDF_TYPE, "Content-Length": ""},
    )
    assert response.status_code == 411
    assert _error(response) == ingest.ERROR_LENGTH_REQUIRED


@pytest.mark.parametrize("value", ["abc", "1.5", "-1", " 12 ", "0x10"])
def test_malformed_content_length_is_rejected(
    client: TestClient, transcript_bytes: bytes, value: str
) -> None:
    response = client.post(
        IMPORT_PATH,
        content=transcript_bytes,
        headers={"Content-Type": PDF_TYPE, "Content-Length": value},
    )
    assert response.status_code == 411
    assert _error(response) == ingest.ERROR_LENGTH_REQUIRED


def test_oversized_declared_length_is_rejected(client: TestClient) -> None:
    response = client.post(
        IMPORT_PATH,
        content=b"%PDF-1.7",
        headers={"Content-Type": PDF_TYPE, "Content-Length": str(9 * 1024 * 1024)},
    )
    assert response.status_code == 413
    assert _error(response) == ingest.ERROR_TOO_LARGE


def test_declared_length_with_too_many_digits_is_rejected(client: TestClient) -> None:
    """超长数字串必须先比位数再转整数，⛔ 不得冒 ValueError 变成 500。"""

    response = client.post(
        IMPORT_PATH,
        content=b"%PDF-1.7",
        headers={"Content-Type": PDF_TYPE, "Content-Length": "9" * 5000},
    )
    assert response.status_code == 413
    assert _error(response) == ingest.ERROR_TOO_LARGE


def test_length_mismatch_is_rejected(client: TestClient, transcript_bytes: bytes) -> None:
    response = _post(client, transcript_bytes, length=len(transcript_bytes) + 5)
    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_LENGTH_MISMATCH


def test_empty_upload_is_rejected(client: TestClient) -> None:
    response = _post(client, b"")
    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_EMPTY_UPLOAD


def test_malformed_pdf_is_rejected(client: TestClient) -> None:
    response = _post(client, b"%PDF-1.7 not really a pdf")
    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


def test_pdf_without_the_verified_layout_is_rejected(client: TestClient) -> None:
    response = _post(client, b"not a pdf at all")
    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


def test_error_responses_never_leak_values_paths_or_stacktraces(
    client: TestClient, tmp_path: Path
) -> None:
    path = tmp_path / "DEMO-private.pdf"
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), f"姓名: {fixtures.DEMO_STUDENT_NAME}", fontname="china-s")
    page.insert_text((72, 96), f"学号: {fixtures.DEMO_STUDENT_NUMBER}", fontname="china-s")
    document.save(str(path))
    document.close()

    response = _post(client, path.read_bytes())
    assert response.status_code == 400
    text = response.text
    for secret in (
        fixtures.DEMO_STUDENT_NAME,
        fixtures.DEMO_STUDENT_NUMBER,
        str(path),
        "Traceback",
        "pypdf",
        "pymupdf",
    ):
        assert secret not in text


# --- XLSX 旧入口未被破坏 ---


def test_xlsx_endpoint_still_exists_and_rejects_pdf_bytes(
    client: TestClient, transcript_bytes: bytes
) -> None:
    from app.services import completed_courses_ingest as xlsx_ingest

    response = client.post(
        "/api/v1/completed-courses/import",
        content=transcript_bytes,
        headers={"Content-Type": OCTET_TYPE, "Content-Length": str(len(transcript_bytes))},
    )
    assert response.status_code == 400
    assert _error(response) == xlsx_ingest.ERROR_INVALID


def test_xlsx_endpoint_declares_its_own_media_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/completed-courses/import",
        content=b"x",
        headers={"Content-Type": PDF_TYPE, "Content-Length": "1"},
    )
    assert response.status_code == 415


# --- 响应片段可以真正回灌 Curriculum ---


def test_response_fragment_drives_the_curriculum_case(
    client: TestClient, transcript_bytes: bytes
) -> None:
    """HTTP 响应里的 `completed_input` 必须能被 Curriculum case 直接消费。"""

    payload = _post(client, transcript_bytes).json()
    case_payload = {
        "data_source": "mock",
        "old": {
            "version_id": "demo-old",
            "major": "示例原专业",
            "cohort": "2025",
            "source_id": "demo://api/old",
            "complete": True,
            "completeness_evidence": "demo://api/old/完整范围",
            "course_records": [{
                "course_id": "DEMO-OLD-1",
                "course_name": "示例旧课",
                "credit": 3.0,
                "requirement": "required",
                "source_record": "row:DEMO-OLD-1",
                "prerequisites": [],
            }],
        },
        "new": {
            "version_id": "demo-new",
            "major": "示例目标专业",
            "cohort": "2025",
            "source_id": "demo://api/new",
            "complete": True,
            "completeness_evidence": "demo://api/new/完整范围",
            "course_records": [{
                "course_id": "TGT-1",
                "course_name": "示例线性代数",
                "credit": 3.0,
                "requirement": "required",
                "source_record": "row:TGT-1",
                "prerequisites": [],
            }, {
                "course_id": "TGT-2",
                "course_name": "示例网络原理",
                "credit": 4.0,
                "requirement": "required",
                "source_record": "row:TGT-2",
                "prerequisites": [],
            }],
        },
        "completed": {
            "source_id": payload["source_id"],
            "complete": True,
            "completeness_evidence": "demo://api/completed/完整范围",
            "records": payload["completed_input"]["records"],
        },
    }

    case = normalize_curriculum_case(json.loads(json.dumps(case_payload)))
    assert len(case.completed) == 4
    tasks = CurriculumCaseProvider(case).get_makeup_tasks()
    assert {task.course_name for task in tasks} == {"示例线性代数", "示例网络原理"}
    by_name = {task.course_name: task for task in tasks}

    # ⛔ 没有任何自动抵认：同名课程没有课程号，必须留待人工确认。
    assert all(task.status.value != "satisfied" for task in tasks)
    # 同名候选 ⇒ 可能的等价关系，仍待人工确认。
    assert by_name["示例线性代数"].status.value == "possibly_equivalent"
    assert "待人工确认" in (by_name["示例线性代数"].reason or "")
    # 目标方案里存在、成绩单里没有的课 ⇒ 因仍有课程号待确认的已修记录，不能确定缺课。
    assert by_name["示例网络原理"].status.value == "manual_confirmation"
    # 补修任务的来源引用必须真的指向成绩单记录。
    assert "pdf:" in (by_name["示例线性代数"].source_evidence or "")
