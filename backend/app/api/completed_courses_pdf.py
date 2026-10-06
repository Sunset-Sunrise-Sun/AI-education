"""`POST /api/v1/completed-courses/import-pdf`：成绩单 PDF 摄取入口（Case A 主路径）。

```text
POST /api/v1/completed-courses/import-pdf
  Content-Type: application/pdf （或 application/octet-stream）
  Content-Length: <必填>
  body: 原始成绩单 PDF 字节（⛔ 不使用 multipart，⛔ 不读文件名）
        ↓
  已归一化的已修课程事实 + 可直接作为 `completed` 输入的 case fragment
```

## 为什么和 XLSX 入口分开

- 两个入口的**输入格式与失败原因完全不同**，混在一个端点会让调用方无法判断
  "是 PDF 版面不符，还是工作簿布局不符"；
- XLSX 入口（`/completed-courses/import`）**保持不变**，仍是兼容的次要路径；
- 本入口是**成绩单 PDF 主路径**：只支持已核验的中山大学本科成绩单版面。

## 错误语义（⛔ 不含任何输入取值 / 路径 / stacktrace）

| 状态码 | `detail.error` | 含义 |
| --- | --- | --- |
| 415 | `completed_courses_pdf_upload_unsupported_media_type` | 不是受支持的 PDF 媒体类型 |
| 411 | `completed_courses_pdf_upload_length_required` | 缺少 / 非法 `Content-Length` |
| 413 | `completed_courses_pdf_upload_too_large` | 声明或实际字节数超限 |
| 400 | `completed_courses_pdf_upload_length_mismatch` | 字节数与声明长度不一致 |
| 400 | `completed_courses_pdf_upload_empty` | 空文件 |
| 400 | `completed_courses_pdf_invalid` | 不是合格的成绩单 PDF / 版面不符 / 损坏 |
| 400 | `completed_courses_pdf_empty` | 版面正确但没有任何课程行 |
| 400 | `completed_courses_pdf_too_many_records` | 课程条数超过上限 |

⛔ 上述任一路径都**不得**返回 500，也⛔ 不得回退到任何演示数据。

## 为什么导入结果是 `pending`

成绩单**不提供**官方课程号。响应里的每条记录都是
`course_id: null` + `course_id_status: "pending"`，
由既有的 Curriculum 匹配逻辑按"身份未确认"保守处理
（⛔ 不会因为课程名相似而自动抵认）。

⚠️ 本接口是**通用摄取能力**：它把 PDF 变成课程事实，但⛔ 不接入已冻结的 Case A
fixed-case runtime；Case A 的固定 case 仍由 `app/services/planning_runtime.py` 装配。
⛔ 未修改任何 `/schemas/*.schema.json`（响应模型定义在本模块内）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.api.completed_courses import (
    CompletedCourseRecord,
    CompletedCoursesCaseInput,
)
from app.services.completed_courses_ingest import (
    ERROR_TOO_LARGE as SHARED_ERROR_TOO_LARGE,
    MAX_UPLOAD_BYTES,
    CompletedCoursesImportRejected,
    parse_declared_content_length,
)
from app.services.completed_courses_pdf_ingest import (
    ERROR_EMPTY_UPLOAD,
    ERROR_INVALID,
    ERROR_LENGTH_MISMATCH,
    ERROR_LENGTH_REQUIRED,
    ERROR_NO_RECORDS,
    ERROR_TOO_LARGE,
    ERROR_TOO_MANY_RECORDS,
    ERROR_UNSUPPORTED_MEDIA_TYPE,
    CompletedCoursesPdfImport,
    import_completed_courses_pdf_bytes,
    normalize_pdf_media_type,
)
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["curriculum"])

_STATUS_BY_CODE: dict[str, int] = {
    ERROR_UNSUPPORTED_MEDIA_TYPE: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    ERROR_LENGTH_REQUIRED: status.HTTP_411_LENGTH_REQUIRED,
    ERROR_LENGTH_MISMATCH: status.HTTP_400_BAD_REQUEST,
    # 413：不同 Starlette 版本的常量名不同，直接用标准码，避免把接口行为绑在依赖版本上。
    ERROR_TOO_LARGE: 413,
    ERROR_EMPTY_UPLOAD: status.HTTP_400_BAD_REQUEST,
    ERROR_INVALID: status.HTTP_400_BAD_REQUEST,
    ERROR_NO_RECORDS: status.HTTP_400_BAD_REQUEST,
    ERROR_TOO_MANY_RECORDS: status.HTTP_400_BAD_REQUEST,
}

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    code: {"description": "成绩单 PDF 导入被拒绝（fail closed）"}
    for code in sorted(set(_STATUS_BY_CODE.values()))
}


class TranscriptTermSummary(BaseModel):
    """成绩单里出现的学期（已归一化文本），供前端展示"识别到几个学期"。"""

    model_config = ConfigDict(extra="forbid")

    term_count: int
    terms: list[str]


class CompletedCoursesPdfImportResponse(BaseModel):
    """一次成功的成绩单导入：版面统计 + 可回灌 Curriculum 的 case fragment。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    artifact_sha256: str
    page_count: int
    columns_seen: int
    record_count: int
    term_count: int
    terms: list[str]
    skipped_footer_lines: int
    confirmed_course_id_count: int
    pending_course_id_count: int
    passed_count: int
    completed_input: CompletedCoursesCaseInput


def _reject(code: str, message: str) -> None:
    raise HTTPException(
        status_code=_STATUS_BY_CODE[code],
        detail={"error": code, "message": message},
    )


def _declared_length(request: Request) -> int:
    """读 `Content-Length`；⛔ 缺失 / 非法 ⇒ 411，⛔ 超限 ⇒ 413（都在读 body 之前）。

    ⚠️ 解析共用 XLSX 入口的严格实现（纯 ASCII 十进制、位数先于 `int()` 判定），
    但把它的错误码**逐个映射**到本入口自己的错误码——⛔ 不能把它们合并成一种，
    否则"格式非法"与"超过大小上限"对调用方就不可区分了。
    """

    try:
        return parse_declared_content_length(request.headers.get("content-length"))
    except CompletedCoursesImportRejected as exc:
        if exc.code == SHARED_ERROR_TOO_LARGE:
            _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")
        _reject(ERROR_LENGTH_REQUIRED, "上传必须显式声明合法的 Content-Length。")


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
    "/completed-courses/import-pdf",
    response_model=CompletedCoursesPdfImportResponse,
    summary="导入中山大学本科成绩单 PDF（通用摄取，不做课程认定）",
    description=(
        "把已核验版面的成绩单 PDF 归一化成 Curriculum 既有的已修课程输入，"
        "并返回可直接回灌 curriculum case `completed` 的片段。"
        "成绩单没有官方课程号，因此结果全部是 `course_id: null` + `pending`，"
        "由既有匹配逻辑保守处理。"
        "⛔ 不做课程认定 / 等价性 / 优先级判断；⛔ 失败时给出明确错误码，不回退到演示数据。"
    ),
    responses=_ERROR_RESPONSES,
)
async def import_completed_courses_pdf(request: Request) -> CompletedCoursesPdfImportResponse:
    """上传字节 → 已归一化的已修课程事实（⛔ 不接触文件名 / 不做认定）。"""

    # ⚠️ 顺序很重要：媒体类型 → 声明长度 → 流式读取（全程限长）→ 解析。
    try:
        normalize_pdf_media_type(request.headers.get("content-type"))
    except CompletedCoursesImportRejected as exc:
        _reject(exc.code, exc.message)

    declared = _declared_length(request)
    payload = await _read_limited_body(request)

    try:
        imported: CompletedCoursesPdfImport = import_completed_courses_pdf_bytes(
            payload, declared_length=declared, media_type=request.headers.get("content-type")
        )
    except CompletedCoursesImportRejected as exc:
        _reject(exc.code, exc.message)

    return CompletedCoursesPdfImportResponse(
        source_id=imported.source_id,
        artifact_sha256=imported.artifact_sha256,
        page_count=imported.page_count,
        columns_seen=imported.columns_seen,
        record_count=imported.record_count,
        term_count=imported.term_count,
        terms=list(imported.terms),
        skipped_footer_lines=imported.skipped_footer_lines,
        confirmed_course_id_count=imported.confirmed_course_id_count,
        pending_course_id_count=imported.pending_course_id_count,
        passed_count=imported.passed_count,
        completed_input=CompletedCoursesCaseInput(
            source_id=imported.source_id,
            records=[
                CompletedCourseRecord(**record) for record in imported.case_records()
            ],
        ),
    )
