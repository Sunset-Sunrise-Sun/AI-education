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

import asyncio
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


# --------------------------------------------------------------------------- #
# Content-Length 严格校验（PR #47 BLOCK：⛔ 任何输入都不得 500）
#
# 约定（与 `docs/data/XLSX_COMPLETED_COURSES_IMPORT.md` 一致）：
#   缺失 / 非 ASCII / 非纯数字（空白 · 符号 · 小数 · 指数 · 十六进制 · 逗号 · Unicode 数字）
#       ⇒ 411 completed_courses_upload_length_required
#   纯 ASCII 十进制但位数超长或数值 > 8 MiB        ⇒ 413 completed_courses_upload_too_large
#   实际 streamed 字节数 > 8 MiB                    ⇒ 413
#   声明长度 ≠ 实际字节数                            ⇒ 400 length_mismatch
# ⚠️ 位数判定**先于** int()：超长十进制串⛔ 不触发 CPython 的
#    `ValueError: Exceeds the limit (4300 digits)`（那会变成 500）。
# --------------------------------------------------------------------------- #

INVALID_CONTENT_LENGTHS = [
    pytest.param(" 32", id="leading-space"),
    pytest.param("32 ", id="trailing-space"),
    pytest.param("\t32", id="tab"),
    pytest.param("+123", id="plus-sign"),
    pytest.param("-1", id="minus-sign"),
    pytest.param("1.0", id="decimal"),
    pytest.param("1e3", id="exponent"),
    pytest.param("0x20", id="hex"),
    pytest.param("1,000", id="comma"),
    pytest.param("1_000", id="underscore"),
    pytest.param("", id="empty-string"),
    pytest.param("32abc", id="trailing-letters"),
]


def _post_via_raw_asgi(value: str, body: bytes = b"x") -> tuple[int, str]:
    """直接用**裸 ASGI** 调 app（绕过任何客户端 header 编码限制）。

    ⚠️ 这是"ASGI app 必须自身安全"的证明：即使客户端/服务器把非法 header
    原样送来，app 也必须返回稳定状态码，⛔ 不得抛异常变成 500。
    """

    headers = [
        (b"host", b"testserver"),
        (b"content-type", XLSX_TYPE.encode("ascii")),
        (b"content-length", value.encode("latin-1", "replace")),
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": IMPORT_PATH,
        "raw_path": IMPORT_PATH.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    messages: list[dict] = [{"type": "http.request", "body": body, "more_body": False}]
    sent: list[dict] = []

    async def receive() -> dict:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))

    start = next(message for message in sent if message["type"] == "http.response.start")
    payload = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return int(start["status"]), payload.decode("utf-8", "replace")


def test_probe_1_missing_content_length_is_411(client) -> None:
    """probe 1：分块传输（无 `Content-Length`）⇒ 411，⛔ 不读 body。"""

    response = client.post(
        IMPORT_PATH,
        content=iter([fx.valid_bytes()]),
        headers={"Content-Type": XLSX_TYPE},
    )

    assert response.status_code == 411
    assert _error(response) == ingest.ERROR_LENGTH_REQUIRED


def test_probe_2_normal_valid_length_still_succeeds(client) -> None:
    """probe 2：合法长度不受影响（回归）。"""

    response = _post(client, fx.valid_bytes())

    assert response.status_code == 200, response.text
    assert response.json()["record_count"] == 3


def test_probe_3_exactly_max_size_is_not_rejected_as_too_large(client) -> None:
    """probe 3：**恰好等于** 8 MiB 的实际上传不被判 413（边界本身合法）。"""

    payload = b"\x00" * ingest.MAX_UPLOAD_BYTES  # 内容不是工作簿 ⇒ 后续 400，但⛔ 不是 413

    response = _post(client, payload)

    assert response.status_code == 400
    assert _error(response) == ingest.ERROR_INVALID


@pytest.mark.parametrize("extra", [1, 1024])
def test_probe_4_max_plus_one_is_413(client, extra: int) -> None:
    """probe 4：超过上限一个字节即 413。"""

    response = _post(client, b"\x00" * (ingest.MAX_UPLOAD_BYTES + extra))

    assert response.status_code == 413
    assert _error(response) == ingest.ERROR_TOO_LARGE


def test_probe_5_very_long_ascii_digits_is_413_not_500(client) -> None:
    """probe 5：数千位纯 ASCII 数字 ⇒ 413，⛔ 不得 500。

    修复前实测：endpoint 返回 `500 Internal Server Error`，
    且异常 `ValueError: Exceeds the limit (4300 digits) for integer string conversion`
    直接从 ASGI app 抛出。
    """

    digits = "9" * 5000

    response = _post(client, b"x", headers={"Content-Length": digits})
    assert response.status_code == 413, response.text
    assert _error(response) == ingest.ERROR_TOO_LARGE

    raw_status, raw_body = _post_via_raw_asgi(digits)
    assert raw_status == 413, raw_body
    assert "Exceeds the limit" not in raw_body


@pytest.mark.parametrize(
    "digits",
    [
        pytest.param("８３８８６０９", id="full-width"),
        pytest.param("١٢٣٤٥", id="arabic-indic"),
        pytest.param("٣٢", id="arabic-indic-short"),
        pytest.param("９" * 100, id="full-width-long"),
    ],
)
def test_probe_6_7_unicode_digits_fail_closed(digits: str) -> None:
    """probe 6/7：Unicode 数字（全角 / 阿拉伯-印度）必须 fail closed。

    ⚠️ 这里直接喂**生产解析函数**（不经 httpx 的 header 编码），
    因此不受客户端编码限制影响：Unicode 数字⛔ 不被当成合法长度。
    """

    with pytest.raises(ingest.CompletedCoursesImportRejected) as error:
        ingest.parse_declared_content_length(digits)

    assert error.value.code == ingest.ERROR_LENGTH_REQUIRED

    # 同一字符串走**裸 ASGI** 也必须 fail closed 且⛔ 不 500。
    status, body = _post_via_raw_asgi(digits)
    assert status == 411, body
    assert "length_required" in body


def test_probe_6_7_unicode_digits_via_endpoint_fail_closed(client) -> None:
    """probe 6/7（endpoint 侧）：能到达 app 的 Unicode 数字同样 fail closed。"""

    with pytest.raises(UnicodeEncodeError):
        # httpx 自身拒绝非 ASCII header：客户端侧就失败，⛔ 不会产生 500 响应。
        _post(client, b"x", headers={"Content-Length": "８３８８６０９"})


@pytest.mark.parametrize("value", INVALID_CONTENT_LENGTHS)
def test_probe_8_to_11_malformed_content_length_is_411(client, value: str) -> None:
    """probe 8–11：空白 / 符号 / 小数 / 指数 / 十六进制 / 逗号 一律 411（⛔ 不 500）。"""

    response = _post(client, b"x", headers={"Content-Length": value})

    assert response.status_code == 411, response.text
    assert _error(response) == ingest.ERROR_LENGTH_REQUIRED

    raw_status, raw_body = _post_via_raw_asgi(value)
    assert raw_status == 411, raw_body


def test_probe_12_actual_body_over_limit_with_lower_declared_length_is_413(client) -> None:
    """probe 12：声明长度撒谎（更小）但实际 body 超限 ⇒ 流式上限先判 413。"""

    response = _post(
        client,
        b"\x00" * (ingest.MAX_UPLOAD_BYTES + 4096),
        headers={"Content-Length": "16"},
    )

    assert response.status_code == 413, response.text
    assert _error(response) == ingest.ERROR_TOO_LARGE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", 0),
        ("32", 32),
        ("0000007", 7),
        (str(ingest.MAX_UPLOAD_BYTES), ingest.MAX_UPLOAD_BYTES),
    ],
)
def test_content_length_validator_accepts_only_bounded_ascii_decimals(
    raw: str, expected: int
) -> None:
    """正向：合法 ASCII 十进制（含前导零）按字面解析；位数有界时才 int()。"""

    assert ingest.parse_declared_content_length(raw) == expected


@pytest.mark.parametrize("raw", ["", None, 32, b"32", "8" * 4301])
def test_content_length_validator_rejects_non_string_and_over_long_inputs(raw) -> None:
    """非字符串 / 空串 / 超过最大位数的输入 ⇒ 明确拒绝（⛔ 无异常泄漏）。"""

    with pytest.raises(ingest.CompletedCoursesImportRejected) as error:
        ingest.parse_declared_content_length(raw)

    assert error.value.code in {
        ingest.ERROR_LENGTH_REQUIRED,
        ingest.ERROR_TOO_LARGE,
    }


def test_content_length_digit_boundary_matches_the_documented_length() -> None:
    """位数阈值必须与 `MAX_UPLOAD_BYTES` 的十进制位数一致（⛔ 不写死字面量）。"""

    assert ingest._MAX_LENGTH_DIGITS == len(str(ingest.MAX_UPLOAD_BYTES))

    # 最大合法位数、但数值超限 ⇒ 413（仍走有界 int()）。
    over = str(ingest.MAX_UPLOAD_BYTES + 1)
    assert len(over) == ingest._MAX_LENGTH_DIGITS
    with pytest.raises(ingest.CompletedCoursesImportRejected) as error:
        ingest.parse_declared_content_length(over)
    assert error.value.code == ingest.ERROR_TOO_LARGE
