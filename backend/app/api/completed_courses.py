"""`POST /api/v1/completed-courses/import`：通用已修课程 XLSX 摄取入口（Gate F）。

```text
POST /api/v1/completed-courses/import
  Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
                （或 application/octet-stream）
  Content-Length: <必填>
  body: 原始 .xlsx 字节（⛔ 不使用 multipart，⛔ 不读文件名）
        ↓
  已归一化的已修课程事实 + 可直接作为 `completed` 输入的 case fragment
```

## 为什么是"原始字节 + 显式 Content-Length"

- ⛔ 不使用 multipart：不引入 `python-multipart` 运行期依赖，也不解析文件名 / 表单字段；
- ⛔ **不信任文件名**：整个请求里没有任何"文件名"参与判定，`source_id` 由**内容摘要**派生；
- 显式 `Content-Length` 让"超大上传"在**读 body 之前**就被拒绝；
  读取过程仍按块计数（⛔ 即使声明值撒谎也不会无界读取）。

## 错误语义（⛔ 不含任何输入值 / 路径 / stacktrace）

| 状态码 | `detail.error` | 含义 |
| --- | --- | --- |
| 415 | `completed_courses_upload_unsupported_media_type` | 不是受支持的 XLSX 媒体类型 |
| 411 | `completed_courses_upload_length_required` | 缺少 / 非法 `Content-Length` |
| 400 | `completed_courses_upload_length_mismatch` | 字节数与声明长度不一致 |
| 413 | `completed_courses_upload_too_large` | 超过上传大小上限 |
| 400 | `completed_courses_upload_empty` | 空文件 |
| 400 | `completed_courses_invalid` | 不是合格的工作簿 / 布局不符 / 含公式单元格 |
| 400 | `completed_courses_empty` | 工作簿里没有任何数据行 |
| 400 | `completed_courses_too_many_records` | 记录条数超过上限 |

⚠️ 本接口是**通用摄取能力**，⛔ 不接入已冻结的 Case A fixed-case runtime；
⛔ 未修改任何 `/schemas/*.schema.json`（新接口的响应模型定义在本模块内）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.services.completed_courses_ingest import (
    ERROR_EMPTY_UPLOAD,
    ERROR_INVALID,
    ERROR_LENGTH_MISMATCH,
    ERROR_LENGTH_REQUIRED,
    ERROR_NO_RECORDS,
    ERROR_TOO_LARGE,
    ERROR_TOO_MANY_RECORDS,
    ERROR_UNSUPPORTED_MEDIA_TYPE,
    MAX_UPLOAD_BYTES,
    CompletedCoursesImportRejected,
    import_completed_courses_xlsx_bytes,
    normalize_media_type,
)

router = APIRouter(tags=["curriculum"])

_STATUS_BY_CODE: dict[str, int] = {
    ERROR_UNSUPPORTED_MEDIA_TYPE: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    ERROR_LENGTH_REQUIRED: status.HTTP_411_LENGTH_REQUIRED,
    ERROR_LENGTH_MISMATCH: status.HTTP_400_BAD_REQUEST,
    # 413：不同 Starlette 版本的常量名不同（`HTTP_413_CONTENT_TOO_LARGE` 与旧名），
    # 这里直接用标准码，避免把接口行为绑在依赖版本上。
    ERROR_TOO_LARGE: 413,
    ERROR_EMPTY_UPLOAD: status.HTTP_400_BAD_REQUEST,
    ERROR_INVALID: status.HTTP_400_BAD_REQUEST,
    ERROR_NO_RECORDS: status.HTTP_400_BAD_REQUEST,
    ERROR_TOO_MANY_RECORDS: status.HTTP_400_BAD_REQUEST,
}

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    code: {"description": "已修课程导入被拒绝（fail closed）"} for code in sorted(set(_STATUS_BY_CODE.values()))
}


class CompletedCourseRecord(BaseModel):
    """`completed.records` 元素的**导出投影**（字段名与 Curriculum 输入完全一致）。

    ⚠️ 刻意**不含** `notes`：唯一可能夹带个人信息的自由文本字段由服务端保留、⛔ 不回传；
    其余字段与 `app/curriculum/completed_courses.py` 的输入契约一一对应。
    """

    model_config = ConfigDict(extra="forbid")

    course_id: str | None
    course_name: str
    credit: float
    semester: str
    passed: bool
    course_type: str | None
    course_id_status: str
    id_match_source: str | None
    source_record: str


class CompletedCoursesCaseInput(BaseModel):
    """可直接放进 curriculum case `completed` 字段的输入片段（`records` 形式）。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    records: list[CompletedCourseRecord]


class CompletedCoursesImportResponse(BaseModel):
    """一次成功导入的结果：统计 + 可回灌 Curriculum 的 case fragment。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    artifact_sha256: str
    worksheet: str
    record_count: int
    confirmed_course_id_count: int
    pending_course_id_count: int
    passed_count: int
    distinct_course_count: int
    notes_present_count: int
    completed_input: CompletedCoursesCaseInput


def _reject(code: str, message: str) -> None:
    raise HTTPException(
        status_code=_STATUS_BY_CODE[code],
        detail={"error": code, "message": message},
    )


def _declared_length(request: Request) -> int:
    """读 `Content-Length`；⛔ 缺失 / 非法 ⇒ 411，⛔ 超限 ⇒ 413（都在读 body 之前）。"""

    raw = request.headers.get("content-length")
    if raw is None or not raw.strip().isdigit():
        _reject(ERROR_LENGTH_REQUIRED, "上传必须显式声明 Content-Length。")
    declared = int(raw.strip())
    if declared > MAX_UPLOAD_BYTES:
        _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")
    return declared


async def _read_limited_body(request: Request) -> bytes:
    """按块读取请求体并**始终**受 `MAX_UPLOAD_BYTES` 约束（⛔ 不信任声明的长度）。"""

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/completed-courses/import",
    response_model=CompletedCoursesImportResponse,
    summary="导入已修课程 XLSX（通用摄取，不做课程认定）",
    description=(
        "把已批准的脱敏交接 XLSX 归一化成 Curriculum 既有的已修课程输入，"
        "并返回可直接回灌 curriculum case `completed` 的片段。"
        "⛔ 不做课程认定 / 等价性 / 优先级判断；⛔ 失败时给出明确错误码，不回退到任何演示数据。"
    ),
    responses=_ERROR_RESPONSES,
)
async def import_completed_courses(request: Request) -> CompletedCoursesImportResponse:
    """上传字节 → 已归一化的已修课程事实（⛔ 不接触文件名 / 不做认定）。"""

    # ⚠️ 顺序很重要：媒体类型 → 声明长度 → 流式读取（全程限长）→ 解析。
    try:
        normalize_media_type(request.headers.get("content-type"))
    except CompletedCoursesImportRejected as exc:
        _reject(exc.code, exc.message)

    declared = _declared_length(request)
    payload = await _read_limited_body(request)

    try:
        imported = import_completed_courses_xlsx_bytes(
            payload, declared_length=declared, media_type=request.headers.get("content-type")
        )
    except CompletedCoursesImportRejected as exc:
        _reject(exc.code, exc.message)

    return CompletedCoursesImportResponse(
        source_id=imported.source_id,
        artifact_sha256=imported.artifact_sha256,
        worksheet=imported.worksheet,
        record_count=imported.record_count,
        confirmed_course_id_count=imported.confirmed_course_id_count,
        pending_course_id_count=imported.pending_course_id_count,
        passed_count=imported.passed_count,
        distinct_course_count=imported.distinct_course_count,
        notes_present_count=imported.notes_present_count,
        completed_input=CompletedCoursesCaseInput(
            source_id=imported.source_id,
            records=[
                CompletedCourseRecord(**record) for record in imported.case_records()
            ],
        ),
    )
