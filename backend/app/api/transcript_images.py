"""成绩单**图片**识别接口（`POST /api/v1/transcript-images/recognize`）。

⚠️ 本路由只做「图片 → 课程**候选**」，⛔ 不做任何课程认定：
   - 响应中**没有** `course_id`、**没有** `MakeupStatus`、**没有**等价关系；
   - 它**不**触发匹配：匹配仍由 `POST /api/v1/case-a-demo/plan` 在学生
     **逐条确认**之后执行（见 `docs/TRANSCRIPT_IMAGE_INPUT_DESIGN.md`）。

## 为什么单独一个端点

识别是**无状态转换**，不属于任何 case，也不产出任何判定。
把它与 `/plan` 分开，可以在**接口层**就保证"识别"与"认定"是两件事
（符合 `AGENTS.md`「OCR 只负责 图片 → 课程记录」）。

## 隐私

- ⛔ 图片不发往任何第三方（本地 ONNX 推理）；
- ⛔ 不落盘、⛔ 不打日志；
- 个人身份信息在服务层**进入聚类之前**被丢弃，响应只回传**丢弃数量**。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.services.transcript_ocr_ingest import (
    ERROR_EMPTY_UPLOAD,
    ERROR_INVALID,
    ERROR_LENGTH_MISMATCH,
    ERROR_LENGTH_REQUIRED,
    ERROR_NO_RECORDS,
    ERROR_OCR_UNAVAILABLE,
    ERROR_TOO_LARGE,
    ERROR_UNSUPPORTED_MEDIA_TYPE,
    MAX_IMAGE_BYTES,
    TranscriptImageRejected,
    recognize_transcript_image,
)

router = APIRouter(tags=["transcript-image"])

_STATUS_BY_CODE: dict[str, int] = {
    ERROR_UNSUPPORTED_MEDIA_TYPE: status.HTTP_400_BAD_REQUEST,
    ERROR_LENGTH_REQUIRED: status.HTTP_411_LENGTH_REQUIRED,
    ERROR_LENGTH_MISMATCH: status.HTTP_400_BAD_REQUEST,
    # 413：直接用标准码，避免把接口行为绑在 Starlette 版本常量名上。
    ERROR_TOO_LARGE: 413,
    ERROR_EMPTY_UPLOAD: status.HTTP_400_BAD_REQUEST,
    ERROR_INVALID: status.HTTP_400_BAD_REQUEST,
    ERROR_NO_RECORDS: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ERROR_OCR_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    code: {"description": "成绩单图片识别被拒绝（fail closed）"}
    for code in sorted(set(_STATUS_BY_CODE.values()))
}


class TranscriptImageRequest(BaseModel):
    """识别请求体（JSON，⛔ 不用 multipart）。"""

    model_config = ConfigDict(extra="forbid")

    image_base64: str = Field(min_length=1)
    media_type: str = Field(min_length=1)


class RecognizedCourseCandidateModel(BaseModel):
    """一条**待用户确认**的课程候选（⛔ 无课程号、⛔ 无任何认定）。"""

    model_config = ConfigDict(extra="forbid")

    row_id: str
    course_name: str
    credit: float | None
    score_text: str | None
    semester_text: str | None
    course_attribute: str | None
    #: ⛔ 仅用于交互（提示用户核对），⛔ 不参与任何判定。
    confidence: float
    unconfirmed: list[str]


class TranscriptImageResponse(BaseModel):
    """识别结果（全部为候选）。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    artifact_sha256: str
    media_type: str
    width: int
    height: int
    block_count: int
    #: 被隐私规则丢弃的文本块**数量**（⛔ 不回传其内容）。
    redacted_block_count: int
    column_groups: int
    candidates: list[RecognizedCourseCandidateModel]
    unrecognized: list[str]


@router.post(
    "/transcript-images/recognize",
    response_model=TranscriptImageResponse,
    summary="识别成绩单图片（只产出课程候选，⛔ 不做课程认定）",
    description=(
        "在**本地**对成绩单图片运行 OCR，返回待用户确认的课程候选。"
        "⛔ 不推断课程号、⛔ 不做等价性判断、⛔ 不产生任何 satisfied；"
        "⛔ 不联网、⛔ 不落盘；个人身份信息在聚类前丢弃。"
        "识别结果必须经用户逐条确认后，才可通过 `/case-a-demo/plan` 进入匹配。"
    ),
    responses=_ERROR_RESPONSES,
)
def recognize_transcript_image_endpoint(
    request: TranscriptImageRequest,
) -> TranscriptImageResponse:
    """上传图片字节（base64）→ 课程候选。⛔ 失败不回退任何演示数据。"""

    import base64
    import binascii

    # 长度上限在**解码之前**按 base64 长度粗判，避免为超大请求分配内存。
    if len(request.image_base64) > ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 4:
        raise HTTPException(
            status_code=413,
            detail={"error": ERROR_TOO_LARGE, "message": "上传图片超过大小上限。"},
        )
    try:
        payload = base64.b64decode(request.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=400,
            detail={"error": ERROR_INVALID, "message": "图片编码无法解析。"},
        ) from None

    try:
        recognition = recognize_transcript_image(
            payload,
            declared_length=len(payload),
            media_type=request.media_type,
        )
    except TranscriptImageRejected as exc:
        raise HTTPException(
            status_code=_STATUS_BY_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail={"error": exc.code, "message": exc.message},
        ) from None

    return TranscriptImageResponse(
        source_id=recognition.source_id,
        artifact_sha256=recognition.artifact_sha256,
        media_type=recognition.media_type,
        width=recognition.width,
        height=recognition.height,
        block_count=recognition.block_count,
        redacted_block_count=recognition.redacted_block_count,
        column_groups=recognition.column_groups,
        candidates=[
            RecognizedCourseCandidateModel(
                row_id=item.row_id,
                course_name=item.course_name,
                credit=item.credit,
                score_text=item.score_text,
                semester_text=item.semester_text,
                course_attribute=item.course_attribute,
                confidence=item.confidence,
                unconfirmed=list(item.unconfirmed),
            )
            for item in recognition.candidates
        ],
        unrecognized=list(recognition.unrecognized),
    )
