"""培养方案 PDF 导入端点（⚠️ **模块内私有 API 包络**）。

```text
POST /api/v1/curriculum-import/parse-pdf
  Content-Type:  application/pdf | application/octet-stream
  Content-Length: <必须显式声明>
  body:          原始 PDF 字节（⛔ 不用 multipart）
  query:
    role=origin|target      必填：这份培养方案是原专业还是目标专业
    major=<专业名>          必填（⛔ 不从 PDF 推断）
    cohort=<年级>           必填（⛔ 不从 PDF 推断）
    source=<来源说明>        必填（由提交者提供，组长核对）
```

返回：解析草稿 + 安全摘要 + **审核结论占位**。⛔ 不写盘、⛔ 不建目录、⛔ 不碰批准锚点。

## 接口边界（⚠️ 如实声明）

- 本文件的请求 / 响应模型是**这个模块自己的私有包络**：
  ⛔ 不新增、⛔ 不修改 `/schemas/*.schema.json`；
  ⛔ 不修改 `/docs/interfaces/**`。
- 但它确实是一条**新增的公共 HTTP 表面**，已在 PR 说明里显式写出。
- 做法沿用 `api/personal_plan.py` 与 `api/completed_courses.py` 的既有先例
  （两者都只往 `main.py` 加一行 `include_router`）。

## ⛔ 这个端点**不能**做的事

| ⛔ 不能 | 为什么 |
| --- | --- |
| 把解析结果写进 `APP_PERSONAL_CATALOG_DIR` | 目录只能由人放置；上传路径只返回内存里的 payload |
| 写批准锚点 | 只有组长明确授权后的独立受控流程能写（`app/provenance`） |
| 把 `verification.verified` 置 true | 上传 / 解析 / 用户点击确认**都不是**来源核验 |
| 声称是学校正式签发的 PDF | 响应里恒有 `is_official_school_pdf: false` |
| 在没有文本层时返回猜测结果 | 扫描件在解析层 fail closed |
"""

from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.curriculum.catalog_draft import render_draft_report
from app.curriculum.errors import CurriculumNormalizationError
from app.services.curriculum_pdf_ingest import (
    ERROR_DECLARED_LENGTH_MISMATCH,
    ERROR_EMPTY_UPLOAD,
    ERROR_LENGTH_REQUIRED,
    ERROR_MEDIA_TYPE_UNSUPPORTED,
    ERROR_TOO_LARGE,
    MAX_UPLOAD_BYTES,
    PdfUploadError,
    describe_outcome,
    ingest_pdf_upload,
)

__all__ = ["router"]

router = APIRouter(tags=["curriculum-import"])

#: 读取请求体时的分块大小（与既有上传端点同量级）。
_CHUNK = 64 * 1024

#: 错误码 → HTTP 状态（⛔ 全部 4xx，⛔ 没有 500 兜底）。
_STATUS_BY_CODE: dict[str, int] = {
    ERROR_MEDIA_TYPE_UNSUPPORTED: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    ERROR_LENGTH_REQUIRED: status.HTTP_411_LENGTH_REQUIRED,
    ERROR_TOO_LARGE: 413,
    ERROR_DECLARED_LENGTH_MISMATCH: status.HTTP_400_BAD_REQUEST,
    ERROR_EMPTY_UPLOAD: status.HTTP_400_BAD_REQUEST,
}

#: 解析阶段失败 → 422（数据不可用，不是服务器错误）。
_UNPROCESSABLE = 422


class PdfImportSource(BaseModel):
    """来源与审核状态（⛔ 不含本地路径）。"""

    model_config = ConfigDict(extra="forbid")

    kind: str
    file_name: str
    sha256: str
    role: str
    source: str
    is_official_school_pdf: bool
    review_conclusion: str
    verification_verified: bool
    complete: bool
    notes: list[str]


class PdfImportParseResponse(BaseModel):
    """解析结果（⛔ 不含原始单元格文本之外的任何私有信息）。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    major: str
    cohort: str
    source: PdfImportSource
    draft: dict[str, Any]
    report: str


def _install_pdf_tables() -> list[dict[str, Any]]:
    """本端点的**默认表格声明**。

    ⚠️ 这是"从哪一列取值"的**声明**，⛔ 不是"猜哪一列是课程号"：
    每一个映射列都要求文档表头**精确等于**声明的文字，不匹配即整表拒绝。

    ⚠️ 真实培养方案的表头文字与表格位置需要按材料确认；本默认值覆盖
    "序号 / 课程号 / 课程名称 / 学分 / 课程类别 / 建议学期"这一常见形态，
    **同时接受对应的英文表头**（有些导出件是英文列名）。
    每个候选都必须与单元格文字**完全相等**；全部不匹配即整表拒绝
    （⛔ 不硬套列位、⛔ 不做模糊匹配、⛔ 不退回按位置猜）。
    """

    return [{
        "mode": "tables",
        "table_index": 1,
        "columns": {
            "sequence": 1, "course_id": 2, "course_name": 3,
            "credit": 4, "requirement": 5, "recommended_term_text": 6,
        },
        "expected_headers": {
            "sequence": ["序号", "No.", "No", "Seq", "Sequence"],
            "course_id": ["课程号", "课程编号", "Course Code", "Course No.", "Code"],
            "course_name": ["课程名称", "课程名", "Course Name", "Course Title", "Title"],
            "credit": ["学分", "Credit", "Credits"],
            "requirement": ["课程类别", "课程性质", "必修/选修", "Category", "Type", "Kind"],
            "recommended_term_text": ["建议学期", "开课学期", "修读学期", "Term", "Semester", "When"],
        },
        "requirement_values": {
            "必修": "required", "选修": "elective",
            "required": "required", "elective": "elective",
        },
    }]


def _reject(code: str, message: str, http_status: int) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"detail": {"error": code, "message": message}},
    )


async def _read_limited_body(request: Request) -> bytes:
    """**流式**限长读取：⛔ 不信任 `Content-Length` 声明值。"""

    total = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise PdfUploadError(ERROR_TOO_LARGE, "上传文件超过大小上限。")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/curriculum-import/parse-pdf",
    response_model=PdfImportParseResponse,
    responses={
        400: {"description": "空文件 / 声明长度与实际不符"},
        411: {"description": "缺少或非法的 Content-Length"},
        413: {"description": "超过大小上限"},
        415: {"description": "不支持的媒体类型"},
        422: {"description": "PDF 无法解析（损坏 / 扫描件 / 表头不匹配 / 无表格）"},
    },
)
async def parse_curriculum_pdf(
    request: Request,
    role: Annotated[str, Query(description="origin 或 target")],
    major: Annotated[str, Query(description="专业名（由提交者给出，⛔ 不从 PDF 推断）")],
    cohort: Annotated[str, Query(description="年级（由提交者给出，⛔ 不从 PDF 推断）")],
    source: Annotated[str, Query(description="来源说明（提交者提供，组长核对）")],
) -> Any:
    """把一份培养方案 PDF 解析成**待组长审核**的草稿。"""

    try:
        body = await _read_limited_body(request)
    except PdfUploadError as error:
        return _reject(error.code, error.message, _STATUS_BY_CODE[error.code])

    try:
        outcome = ingest_pdf_upload(
            body,
            declared_length=request.headers.get("content-length"),
            media_type=request.headers.get("content-type"),
            file_name=request.headers.get("x-file-name") or "curriculum.pdf",
            role=role, major=major, cohort=cohort, source=source,
            tables=_install_pdf_tables(),
        )
    except PdfUploadError as error:
        return _reject(error.code, error.message, _STATUS_BY_CODE[error.code])
    except CurriculumNormalizationError as error:
        # 解析阶段失败：固定文案 + 固定状态码（⛔ 不冒 500、⛔ 不回显私有文本）。
        return _reject("pdf_import_unparsable", str(error), _UNPROCESSABLE)

    summary = describe_outcome(outcome, source=source)
    draft_payload = outcome.draft.to_payload()
    return {
        "source_id": outcome.source_id,
        "major": outcome.major,
        "cohort": outcome.cohort,
        "source": {
            "kind": "pdf-upload",
            "file_name": summary["file_name"],
            "sha256": summary["sha256"],
            "role": summary["role"],
            "source": summary["source"],
            # ⛔ 硬编码 false：本轮 PDF 是**由教务网页重排生成的转换件**，
            #    ⛔ 不得当作学校正式签发的原始 PDF。
            "is_official_school_pdf": False,
            "review_conclusion": summary["review_conclusion"],
            "verification_verified": False,
            "complete": False,
            "notes": [
                "本 PDF 是**来源可追溯的转换件**（由已保存的教务网页重排生成），"
                "⛔ 不是学校正式签发的原始 PDF。",
                "上传成功、文本提取成功、用户点击确认，**都不构成**来源核验。",
                "草稿的 verification.verified 恒为 false、complete 恒为 false，"
                "在组长批准前⛔ 不会被任何真实规划使用。",
                "课程组学分要求**未**从 PDF 推导；⛔ 不得用成员学分求和代替。",
            ],
        },
        "draft": draft_payload,
        "report": render_draft_report(outcome.draft),
    }
