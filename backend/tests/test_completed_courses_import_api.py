"""Gate F：已修课程 XLSX 导入 API 的**安全 / 隐私 / 集成**回归。

```text
XLSX → POST /api/v1/completed-courses/import
     → 已归一化的已修课程（复用 Curriculum 既有 reader / normalization）
     → 可直接回灌 curriculum case 的 `completed.records` 片段
     → 既有 Curriculum pipeline（normalize_curriculum_case → CurriculumCaseProvider）
```

全部输入都是**人工构造**的 synthetic 工作簿（`xlsx_fixtures`）；
⛔ 本文件不含、也不得包含任何真实成绩单 / 学生材料。
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import xlsx_fixtures as fx
from app.curriculum.case import (
    DEMO_CASE_PATH,
    CurriculumCaseProvider,
    normalize_curriculum_case,
)
from app.curriculum.completed_courses import CourseIdStatus, normalize_completed_courses
from app.curriculum.xlsx_reader import load_completed_courses_xlsx
from app.main import app
from app.services import completed_courses_ingest as ingest

IMPORT_PATH = "/api/v1/completed-courses/import"
XLSX_TYPE = "application/octet-stream"
OFFICIAL_XLSX_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
RECORD_FIELDS = {
    "course_id",
    "course_name",
    "credit",
    "semester",
    "passed",
    "course_type",
    "course_id_status",
    "id_match_source",
    "source_record",
}


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def _post(
    client: TestClient,
    payload: bytes,
    *,
    content_type: str = XLSX_TYPE,
    headers: dict[str, str] | None = None,
):
    request_headers = {"Content-Type": content_type}
    request_headers.update(headers or {})
    return client.post(IMPORT_PATH, content=payload, headers=request_headers)


def _error(response) -> str:
    return response.json()["detail"]["error"]


# --------------------------------------------------------------------------- #
# F1：成功路径
# --------------------------------------------------------------------------- #


def test_valid_workbook_is_normalized_and_returned_as_case_input(client) -> None:
    payload = fx.valid_bytes()

    response = _post(client, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["worksheet"] == fx.APPROVED_SHEET
    assert body["artifact_sha256"] == hashlib.sha256(payload).hexdigest()
    # source_id 由**内容摘要**派生（⛔ 与文件名无关）。
    assert body["source_id"] == f"{ingest.SOURCE_ID_PREFIX}{body['artifact_sha256'][:16]}"
    assert body["record_count"] == 3
    assert body["confirmed_course_id_count"] == 2
    assert body["pending_course_id_count"] == 1
    assert body["passed_count"] == 2
    assert body["distinct_course_count"] == 2
    assert body["notes_present_count"] == 2

    fragment = body["completed_input"]
    assert fragment["source_id"] == body["source_id"]
    assert len(fragment["records"]) == 3
    for record in fragment["records"]:
        assert set(record) == RECORD_FIELDS  # ⛔ 不含 notes 自由文本
    assert fragment["records"][1]["course_id"] is None
    assert fragment["records"][1]["course_id_status"] == CourseIdStatus.PENDING.value
    # Unicode 课程名原样保留。
    assert fragment["records"][1]["course_name"] == "待确认课程（Unicode ✓ 中文）"


def test_official_xlsx_media_type_is_accepted(client) -> None:
    response = _post(client, fx.valid_bytes(), content_type=OFFICIAL_XLSX_TYPE)

    assert response.status_code == 200, response.text
    assert response.json()["record_count"] == 3


def test_mixed_cell_types_are_normalized_without_coercion(client) -> None:
    response = _post(client, fx.mixed_cell_types_bytes())

    assert response.status_code == 200, response.text
    record = response.json()["completed_input"]["records"][0]
    assert record["course_id"] == "DEMO-COURSE-01"
    assert record["credit"] == 2.5
    assert record["passed"] is True
    assert record["semester"] == "2026-1"


def test_numeric_course_id_is_rejected_instead_of_being_coerced(client) -> None:
    response = _post(client, fx.numeric_course_id_bytes())

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


# --------------------------------------------------------------------------- #
# F2：文件安全（媒体类型 / 长度 / 大小 / 空文件 / 结构）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("content_type", ["text/plain", "application/json", "multipart/form-data", ""])
def test_unsupported_media_types_are_rejected(client, content_type: str) -> None:
    response = _post(client, fx.valid_bytes(), content_type=content_type)

    assert response.status_code == 415
    assert _error(response) == ingest.ERROR_UNSUPPORTED_MEDIA_TYPE


def test_missing_content_length_is_rejected(client) -> None:
    """分块传输（无 Content-Length）⇒ 411，且⛔ 不读 body。"""

    response = client.post(
        IMPORT_PATH,
        content=iter([fx.valid_bytes()]),
        headers={"Content-Type": XLSX_TYPE},
    )

    assert response.status_code == 411
    assert _error(response) == ingest.ERROR_LENGTH_REQUIRED


def test_lying_content_length_is_rejected(client) -> None:
    response = _post(
        client, fx.valid_bytes(), headers={"Content-Length": "999999"}
    )

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_LENGTH_MISMATCH


def test_declared_length_over_the_limit_is_rejected(client) -> None:
    response = _post(
        client,
        b"x",
        headers={"Content-Length": str(ingest.MAX_UPLOAD_BYTES + 1)},
    )

    assert response.status_code == 413
    assert _error(response) == ingest.ERROR_TOO_LARGE


def test_actual_body_over_the_limit_is_rejected(client) -> None:
    """即使声明的长度撒谎，流式读取也会在上限处截断并 413。"""

    response = _post(client, b"\x00" * (ingest.MAX_UPLOAD_BYTES + 1024))

    assert response.status_code == 413
    assert _error(response) == ingest.ERROR_TOO_LARGE


def test_empty_upload_is_rejected(client) -> None:
    response = _post(client, b"")

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_EMPTY_UPLOAD


def test_malformed_workbook_is_rejected(client) -> None:
    response = _post(client, fx.malformed_bytes())

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


def test_wrong_headers_are_rejected(client) -> None:
    response = _post(client, fx.wrong_headers_bytes())

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


def test_duplicate_sequence_numbers_are_rejected(client) -> None:
    response = _post(client, fx.duplicate_rows_bytes())

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


def test_missing_course_id_with_confirmed_status_is_rejected(client) -> None:
    response = _post(client, fx.missing_course_id_bytes())

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


def test_header_only_workbook_is_rejected_as_empty(client) -> None:
    response = _post(client, fx.empty_sheet_bytes())

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_NO_RECORDS


def test_unexpected_worksheet_selection_is_rejected(client) -> None:
    payload = fx.workbook_bytes(
        sheet_xml=fx.sheet_with_records([fx.record_row(1)]),
        selected_sheet_name="未批准的工作表",
    )

    response = _post(client, payload)

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


def test_oversized_worksheet_part_is_rejected(client) -> None:
    response = _post(client, fx.oversized_part_bytes())

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


def test_formula_cells_are_rejected_and_never_evaluated(client) -> None:
    response = _post(client, fx.formula_cell_bytes(private_marker="PRIVATE-FORMULA-MARKER"))

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID
    assert "formula" in response.text
    # ⛔ 绝不出现在响应里（既不求值，也不回显）。
    assert "PRIVATE-FORMULA-MARKER" not in response.text


def test_macro_parts_are_ignored_and_never_executed(client) -> None:
    payload = fx.workbook_bytes(
        sheet_xml=fx.sheet_with_records([fx.record_row(1)]),
        extra_parts=fx.macro_parts(),
    )

    response = _post(client, payload)

    assert response.status_code == 200, response.text
    assert response.json()["record_count"] == 1
    assert "DEMO-VBA-MARKER" not in response.text


def test_filename_headers_are_never_trusted(client) -> None:
    payload = fx.valid_bytes()

    response = _post(
        client,
        payload,
        headers={
            "Content-Disposition": 'attachment; filename="../../../etc/passwd.xlsx"',
            "X-File-Name": "../../../etc/passwd.xlsx",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_id"].startswith(ingest.SOURCE_ID_PREFIX)
    assert "passwd" not in response.text
    assert "etc" not in json.dumps(body["source_id"])


def test_temp_file_is_removed_after_success_and_failure(client, monkeypatch) -> None:
    """受控临时文件的**生命周期**：请求结束（成功与失败）后都必须不存在。"""

    created: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def _recording_mkstemp(*args: object, **kwargs: object):
        descriptor, name = real_mkstemp(*args, **kwargs)  # type: ignore[arg-type]
        created.append(name)
        return descriptor, name

    monkeypatch.setattr(ingest.tempfile, "mkstemp", _recording_mkstemp)

    assert _post(client, fx.valid_bytes()).status_code == 200
    assert _post(client, fx.malformed_bytes()).status_code == 400

    assert created, "expected the adapter to use a controlled temporary file"
    for name in created:
        assert not Path(name).exists(), f"temporary file leaked: {name}"


# --------------------------------------------------------------------------- #
# F5：隐私（错误响应 / 日志面）
# --------------------------------------------------------------------------- #


def test_error_responses_never_leak_cell_values_or_raw_xml(client) -> None:
    marker = "PRIVATE-STUDENT-MARKER"

    response = _post(client, fx.private_marker_bytes(marker))

    assert response.status_code == 400
    assert marker not in response.text
    assert "备注-PRIVATE" not in response.text
    assert "<worksheet" not in response.text
    assert "<row" not in response.text


def test_error_responses_never_leak_paths_or_stacktraces(client) -> None:
    for payload in (fx.malformed_bytes(), fx.wrong_headers_bytes(), b""):
        response = _post(client, payload)
        text = response.text
        assert "Traceback" not in text
        assert "File \"" not in text
        assert "completed-courses-upload-" not in text
        assert ".xlsx" not in text
        assert "C:\\" not in text and "/tmp/" not in text


def test_success_response_does_not_echo_notes_free_text(client) -> None:
    marker = "PRIVATE-NOTE-MARKER"
    payload = fx.workbook_bytes(
        sheet_xml=fx.sheet_with_records([fx.record_row(1, notes=marker)])
    )

    response = _post(client, payload)

    assert response.status_code == 200, response.text
    assert response.json()["notes_present_count"] == 1  # 服务端知道有备注…
    assert marker not in response.text  # …但⛔ 不回传自由文本


# --------------------------------------------------------------------------- #
# F3 / F6：复用 Curriculum normalization + 接入既有 Curriculum pipeline
# --------------------------------------------------------------------------- #


def test_imported_fragment_round_trips_through_curriculum_normalization(client) -> None:
    """导出的 `completed_input.records` 必须**恰好**是 Curriculum 的合法输入。"""

    body = _post(client, fx.valid_bytes()).json()
    fragment = body["completed_input"]

    courses = normalize_completed_courses(
        fragment["records"], source_id=fragment["source_id"]
    )

    assert len(courses) == body["record_count"]
    assert [course.course_id for course in courses] == [
        "DEMO-COURSE-01",
        None,
        "DEMO-COURSE-03",
    ]


def test_import_path_matches_the_curriculum_reader_exactly(client, tmp_path: Path) -> None:
    """API 的归一化结果必须与 Curriculum 既有的**路径版** reader 完全一致。"""

    payload = fx.valid_bytes()
    body = _post(client, payload).json()

    from_path = load_completed_courses_xlsx(
        fx.write(tmp_path, payload), source_id=body["source_id"]
    )

    assert [course.course_name for course in from_path] == [
        record["course_name"] for record in body["completed_input"]["records"]
    ]
    assert [course.source_record for course in from_path] == [
        record["source_record"] for record in body["completed_input"]["records"]
    ]


def test_imported_records_drive_the_existing_curriculum_pipeline(client) -> None:
    """F6 闭环：synthetic XLSX → 归一化 → **既有** Curriculum pipeline。

    做法：把 demo case 的已修课程事实写成 XLSX 上传，再用**同一条**既有管线
    （`normalize_curriculum_case` → `CurriculumCaseProvider`）计算补修任务；
    结果必须与直接用 `records` 的原生 demo case 完全一致。
    """

    demo_payload = json.loads(DEMO_CASE_PATH.read_text(encoding="utf-8"))
    native_tasks = CurriculumCaseProvider(
        normalize_curriculum_case(deepcopy(demo_payload))
    ).get_makeup_tasks()
    assert native_tasks

    rows = [
        fx.record_row(
            index,
            course_id=record["course_id"],
            course_name=record["course_name"],
            credit=record["credit"],
            semester=record["semester"],
            passed=record["passed"],
            course_type=record["course_type"],
            course_id_status=record["course_id_status"],
            id_match_source=record["id_match_source"],
        )
        for index, record in enumerate(demo_payload["completed"]["records"], start=1)
    ]
    response = _post(client, fx.workbook_bytes(sheet_xml=fx.sheet_with_records(rows)))
    assert response.status_code == 200, response.text
    body = response.json()

    imported_payload = deepcopy(demo_payload)
    imported_payload["completed"] = {
        **demo_payload["completed"],
        "source_id": body["source_id"],
        "records": body["completed_input"]["records"],
    }
    imported_payload["rules"] = {
        **demo_payload["rules"],
        "completed_source_id": body["source_id"],
    }

    imported_tasks = CurriculumCaseProvider(
        normalize_curriculum_case(imported_payload)
    ).get_makeup_tasks()

    assert [(task.course_id, task.status.value) for task in imported_tasks] == [
        (task.course_id, task.status.value) for task in native_tasks
    ]


def test_case_a_runtime_is_not_dynamically_wired_to_the_upload_adapter() -> None:
    """⛔ 已冻结的 Case A runtime 不得接入上传适配器（fixed case 与通用摄取分离）。"""

    runtime_source = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "planning_runtime.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "completed_courses_ingest",
        "completed-courses/import",
        "import_completed_courses_xlsx_bytes",
    ):
        assert forbidden not in runtime_source


def test_plan_endpoint_contract_is_unchanged() -> None:
    """⛔ 未改动 `/api/v1/plan` 的请求契约，新接口只是**新增**。"""

    schema = app.openapi()
    assert IMPORT_PATH in schema["paths"]

    plan_schema = schema["paths"]["/api/v1/plan"]["post"]
    reference = plan_schema["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    model = schema["components"]["schemas"][reference.rsplit("/", 1)[-1]]
    assert set(model["properties"]) == {"semester", "current_schedule", "preference"}
    assert model.get("additionalProperties") is False
