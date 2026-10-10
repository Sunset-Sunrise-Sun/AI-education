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
from app.curriculum.pdf_evidence import build_classification_report, extract_evidence
from app.curriculum.pdf_profiles import (
    category_values_for,
    list_document_types,
)
from app.curriculum.requirements import RequirementKind
from app.services.curriculum_review import ReviewStoreError, get_review_store
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

#: 与 main.py 一致的 API 前缀（仅用于在响应里回填审核端点的**相对**路径）。
API_V1_PREFIX = "/api/v1"

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
    #: 审核会话（本轮新增）。⚠️ 只增不改：既有字段语义一字未改。
    review: dict[str, Any] | None = None


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


class PdfDocumentType(BaseModel):
    """一个**已验收**的文档类型（⛔ 不含任何列位映射）。"""

    model_config = ConfigDict(extra="forbid")

    key: str
    major: str
    cohort: str
    label: str
    verified_pages: int
    declared_tables: int


class PdfDocumentTypesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_types: list[PdfDocumentType]


@router.get(
    "/curriculum-import/document-types",
    response_model=PdfDocumentTypesResponse,
    summary="列出已验收的培养方案文档类型",
)
async def list_curriculum_document_types() -> Any:
    """返回**已验收**的文档类型清单。

    ⚠️ 前端只能从这里选择，⛔ 不能提交任何课程列位映射：
    profile 由后端注册表给出，⛔ 调用方无法影响"哪一列是课程编码"。
    """

    return {"document_types": list(list_document_types())}


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
    document_type: Annotated[
        str | None,
        Query(description=(
            "已验收文档类型的 key（可选）。⚠️ 它只是**断言**："
            "会与按内容结构判定的结果核对，不一致即 422。省略时按内容结构自动判定。"
        )),
    ] = None,
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
            document_type=document_type,
        )
    except PdfUploadError as error:
        return _reject(error.code, error.message, _STATUS_BY_CODE[error.code])
    except CurriculumNormalizationError as error:
        # 解析阶段失败：固定文案 + 固定状态码（⛔ 不冒 500、⛔ 不回显私有文本）。
        return _reject("pdf_import_unparsable", str(error), _UNPROCESSABLE)

    summary = describe_outcome(outcome, source=source)
    draft_payload = outcome.draft.to_payload()

    # --- 分类证据 + 审核会话（本轮新增）---
    # ⚠️ 证据与候选都在**服务端**生成并保管；客户端只能拿到 `review_id`。
    review_payload: dict[str, Any] | None = None
    try:
        requirements, appendix, sections, unmapped = extract_evidence(
            body, tables=outcome.document.tables,
        )
        report = build_classification_report(
            outcome.result.rows,
            category_requirements=requirements,
            appendix_evidence=appendix,
            sections=sections,
            category_values={
                code: RequirementKind(value)
                for code, value in category_values_for(outcome.document).items()
            },
            unmapped_category_codes=unmapped,
        )
        session = get_review_store().create(
            document_key=outcome.document.key,
            major=outcome.major,
            cohort=outcome.cohort,
            role=outcome.role,
            file_name=summary["file_name"],
            source_id=outcome.source_id,
            source_sha256=summary["sha256"],
            report=report,
        )
        review_payload = {
            "review_id": session.review_id,
            "expires_in_seconds": max(0, int(session.expires_at - session.created_at)),
            "statistics": report.statistics(),
            "progress": session.progress(),
            "endpoints": {
                "status": f"{API_V1_PREFIX}/curriculum-review/{session.review_id}",
                "decisions": (
                    f"{API_V1_PREFIX}/curriculum-review/{session.review_id}/decisions"
                ),
                "export": f"{API_V1_PREFIX}/curriculum-review/{session.review_id}/export",
            },
            "notes": list(report.notes),
        }
    except ReviewStoreError as error:
        # ⛔ 会话建不出来时**明确告知**，⛔ 不静默返回一个"没有审核入口"的成功响应
        review_payload = {
            "review_id": None,
            "error": error.code,
            "message": error.message,
        }
    except CurriculumNormalizationError as error:
        review_payload = {
            "review_id": None,
            "error": "review_evidence_unavailable",
            "message": str(error),
        }

    return {
        "source_id": outcome.source_id,
        "major": outcome.major,
        "cohort": outcome.cohort,
        "source": {
            "kind": outcome.kind,
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
        "review": review_payload,
    }
