"""成绩单 PDF 导入适配器：只做**摄取 + 归一化**，⛔ 不做课程认定。

```text
上传字节
  ↓ 媒体类型 / 声明长度 / 实际大小 / 空文件 校验（与 XLSX 入口共用同一套判定）
app/curriculum/pdf_reader.py（版面校验 + 字段抽取 + normalize_completed_courses）
CompletedCourse 元组（= Curriculum 既有内部输入）
```

## 与 XLSX 入口的关系

- XLSX 入口（`app/services/completed_courses_ingest.py`）**保持不变**，仍是兼容的次要路径；
- 本模块是**成绩单 PDF 主路径**（Case A 样本已核验版面）；
- 两者共用 `parse_declared_content_length()` 与 `normalize_media_type()` 的实现，
  但**错误码分离**：PDF 的错误码带 `_pdf`，调用方不会把两种路径的失败混为一谈。

## 硬边界

- ⛔ 不实现 Curriculum Diff / equivalence / recognition / priority —— 全部继续由
  `app/curriculum` 的既有实现负责；
- ⛔ 不信任文件名：不接受文件名 / 路径参数，`source_id` 由**内容摘要**派生；
- ⛔ 不写任何临时文件：PDF 在内存中解析（与 XLSX 需要 seekable 文件不同）；
- ⛔ 不打印任何行内容：错误信息只含固定通用文案。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_reader import parse_transcript_pdf_bytes
from app.services.completed_courses_ingest import (
    MAX_COMPLETED_RECORDS,
    MAX_UPLOAD_BYTES,
    OCTET_STREAM_MEDIA_TYPE,
    CompletedCoursesImportRejected,
    normalize_media_type as _normalize_shared_media_type,
    parse_declared_content_length,
)

__all__ = [
    "ALLOWED_PDF_MEDIA_TYPES",
    "PDF_MEDIA_TYPE",
    "SOURCE_ID_PREFIX",
    "CompletedCoursesPdfImport",
    "import_completed_courses_pdf_bytes",
    "normalize_pdf_media_type",
    "parse_declared_content_length",
]

#: 官方 PDF 媒体类型。
PDF_MEDIA_TYPE = "application/pdf"

#: 只允许这两种媒体类型（⛔ 不接受 `text/plain`、`multipart/*` 等）。
ALLOWED_PDF_MEDIA_TYPES = frozenset({PDF_MEDIA_TYPE, OCTET_STREAM_MEDIA_TYPE})

#: `source_id` 前缀：由**内容摘要**派生，⛔ 不来自文件名 / 调用方字符串。
SOURCE_ID_PREFIX = "upload:pdf:sha256:"
_SOURCE_ID_DIGEST_LENGTH = 16

# --- 错误码（与 XLSX 入口分开，便于调用方区分路径） --- #
ERROR_UNSUPPORTED_MEDIA_TYPE = "completed_courses_pdf_upload_unsupported_media_type"
ERROR_LENGTH_REQUIRED = "completed_courses_pdf_upload_length_required"
ERROR_LENGTH_MISMATCH = "completed_courses_pdf_upload_length_mismatch"
ERROR_TOO_LARGE = "completed_courses_pdf_upload_too_large"
ERROR_EMPTY_UPLOAD = "completed_courses_pdf_upload_empty"
ERROR_INVALID = "completed_courses_pdf_invalid"
ERROR_NO_RECORDS = "completed_courses_pdf_empty"
ERROR_TOO_MANY_RECORDS = "completed_courses_pdf_too_many_records"


def _reject(code: str, message: str) -> None:
    raise CompletedCoursesImportRejected(code, message)


def normalize_pdf_media_type(value: object) -> str:
    """把 `Content-Type` 归一化，并只接受 PDF / 通用二进制流。"""

    if not isinstance(value, str) or not value.strip():
        _reject(ERROR_UNSUPPORTED_MEDIA_TYPE, "必须显式声明受支持的 PDF 媒体类型。")
    media_type = value.split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_PDF_MEDIA_TYPES:
        _reject(
            ERROR_UNSUPPORTED_MEDIA_TYPE,
            "只接受成绩单 PDF；其它媒体类型一律拒绝。",
        )
    return media_type


@dataclass(frozen=True, slots=True)
class CompletedCoursesPdfImport:
    """一次成功的成绩单 PDF 导入（均为**已归一化**的事实，⛔ 未做任何认定）。"""

    source_id: str
    artifact_sha256: str
    page_count: int
    columns_seen: int
    terms: tuple[str, ...]
    skipped_footer_lines: int
    courses: tuple[CompletedCourse, ...]

    @property
    def record_count(self) -> int:
        return len(self.courses)

    @property
    def confirmed_course_id_count(self) -> int:
        # 成绩单不提供官方课程号，因此这里恒为 0。
        return sum(
            course.course_id_status is CourseIdStatus.CONFIRMED for course in self.courses
        )

    @property
    def pending_course_id_count(self) -> int:
        return self.record_count - self.confirmed_course_id_count

    @property
    def passed_count(self) -> int:
        return sum(course.passed for course in self.courses)

    @property
    def term_count(self) -> int:
        return len(self.terms)

    def case_records(self) -> tuple[dict[str, object], ...]:
        """返回**恰好**是 `completed.records` 输入形状的映射序列。

        ⚠️ 刻意**不导出 `notes`** 自由文本：成绩单导入的 notes 只承载原始成绩文本，
        与 Curriculum 的认定无关，因此导出层直接丢弃。
        """

        return tuple(
            {
                "course_id": course.course_id,
                "course_name": course.course_name,
                "credit": course.credit,
                "semester": course.semester,
                "passed": course.passed,
                "course_type": course.course_type,
                "course_id_status": course.course_id_status.value,
                "id_match_source": course.id_match_source,
                "source_record": course.source_record,
            }
            for course in self.courses
        )


def import_completed_courses_pdf_bytes(
    payload: object,
    *,
    declared_length: object,
    media_type: object,
) -> CompletedCoursesPdfImport:
    """把上传字节变成**已归一化**的已修课程事实（⛔ 不做任何认定）。

    - 媒体类型 / 声明长度 / 实际大小 / 空文件 均在解析**之前**校验；
    - 版面不符 / 损坏 PDF ⇒ `completed_courses_pdf_invalid`（fail closed）；
    - ⛔ 不回退到任何演示数据、⛔ 不部分输出。
    """

    normalize_pdf_media_type(media_type)

    if not isinstance(payload, (bytes, bytearray)):
        _reject(ERROR_INVALID, "上传内容无法读取。")
    body = bytes(payload)

    if isinstance(declared_length, bool) or not isinstance(declared_length, int):
        _reject(ERROR_LENGTH_REQUIRED, "上传必须声明 Content-Length。")
    if declared_length > MAX_UPLOAD_BYTES:
        _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")
    if declared_length != len(body):
        _reject(ERROR_LENGTH_MISMATCH, "上传字节数与声明的 Content-Length 不一致。")
    if not body:
        _reject(ERROR_EMPTY_UPLOAD, "上传文件为空。")
    if len(body) > MAX_UPLOAD_BYTES:
        _reject(ERROR_TOO_LARGE, "上传文件超过大小上限。")

    digest = hashlib.sha256(body).hexdigest()
    source_id = f"{SOURCE_ID_PREFIX}{digest[:_SOURCE_ID_DIGEST_LENGTH]}"

    try:
        parsed = parse_transcript_pdf_bytes(body)
    except CurriculumNormalizationError as exc:
        # reader 的文案只含固定通用描述；⛔ 不含路径、课程名、成绩或学生信息。
        _reject(ERROR_INVALID, str(exc))

    if not parsed.records:
        _reject(ERROR_NO_RECORDS, "成绩单中没有可导入的课程记录。")
    if len(parsed.records) > MAX_COMPLETED_RECORDS:
        _reject(ERROR_TOO_MANY_RECORDS, "成绩单中的课程条数超过上限。")

    from app.curriculum.completed_courses import normalize_completed_courses
    from app.curriculum.pdf_reader import completed_records_for

    courses = normalize_completed_courses(
        completed_records_for(parsed), source_id=source_id
    )

    return CompletedCoursesPdfImport(
        source_id=source_id,
        artifact_sha256=digest,
        page_count=parsed.page_count,
        columns_seen=parsed.columns_seen,
        terms=parsed.terms,
        skipped_footer_lines=parsed.skipped_footer_lines,
        courses=tuple(courses),
    )
