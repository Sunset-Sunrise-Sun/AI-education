"""培养方案 PDF 上传的**传输层与安全校验**（⛔ 不做任何 Web 框架调用）。

```text
HTTP 原始字节 + Content-Type + Content-Length
      │  ① 媒体类型白名单（⛔ 不接受 multipart / text/plain）
      │  ② Content-Length 严格解析（位数先于 int()，缺失/非法 ⇒ 411）
      │  ③ 声明长度必须等于实读长度（⇒ 400）
      │  ④ 空文件拒绝（⇒ 400）
      ▼
curriculum_pdf_ingest_bytes()          ← 本模块
      │  ⑤ %PDF- magic + 大小上限（在解析层再查一次）
      │  ⑥ SHA-256（**内容摘要** ⇒ source_id，⛔ 不用文件名）
      │  ⑦ 调用 pdf_reader 解析
      ▼
PDFImportOutcome（draft payload + 来源摘要 + 审核结论占位）
```

## 为什么参数化 `kind="tables"`

XLSX 上传用 "媒体类型白名单 + 显式 Content-Length + 原始字节" 这一套范式，
本模块**照抄同一套范式**并复用同一批常量口径（8 MiB 上限、`upload:sha256:` 前缀），
理由：⛔ 不引入 `python-multipart` 运行期依赖，也⛔ 不解析文件名 / 表单字段。

## ⛔ 本模块**不**做的事

| ⛔ 不做 | 说明 |
| --- | --- |
| 写任何文件 | 上传只产出**内存里的** payload；写盘由人执行 |
| 写 `APP_PERSONAL_CATALOG_DIR` / 批准锚点 | 那里只能由组长明确授权的独立受控流程写 |
| 把草稿标成已核验 | 结论字段恒为 `pending_group_lead_review`；`verification.verified=false` |
| 从文件名推断专业 / 版本 / 学期 | `source_id` 只来自内容摘要；专业与年级由调用方**显式**给出 |
| 调用 OCR | 扫描件在解析层即 fail closed |
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.curriculum.catalog_draft import CatalogDraftInput
from app.curriculum.docx_reader import DocxImportIssue, DocxImportResult
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_profiles import load_curriculum_pdf_verified
from app.curriculum.pdf_reader import MAX_PDF_BYTES
from app.curriculum.requirements import RequirementKind

__all__ = [
    "APPLICATION_PDF_MEDIA_TYPE",
    "ERROR_DECLARED_LENGTH_MISMATCH",
    "ERROR_EMPTY_UPLOAD",
    "ERROR_LENGTH_REQUIRED",
    "ERROR_MEDIA_TYPE_UNSUPPORTED",
    "ERROR_TOO_LARGE",
    "MAX_UPLOAD_BYTES",
    "OCTET_STREAM_MEDIA_TYPE",
    "PENDING_REVIEW_CONCLUSION",
    "PdfUploadError",
    "SOURCE_ID_PREFIX",
    "build_draft_from_result",
    "ingest_pdf_upload",
    "normalize_media_type",
    "parse_declared_content_length",
]

#: 唯一被接受的媒体类型。
APPLICATION_PDF_MEDIA_TYPE = "application/pdf"

#: 通用二进制流；浏览器 `fetch(url, {body: file})` 在部分环境会用它。
OCTET_STREAM_MEDIA_TYPE = "application/octet-stream"

#: ⛔ 只允许这两种（⛔ 不接受 `multipart/form-data`、`text/plain` 等）。
ALLOWED_MEDIA_TYPES = frozenset({APPLICATION_PDF_MEDIA_TYPE, OCTET_STREAM_MEDIA_TYPE})

#: 上传字节上限。⚠️ 与解析层的 `MAX_PDF_BYTES` **同值**：
#: 两层都查，任一层单独失效都不会放行超大输入。
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

if MAX_UPLOAD_BYTES > MAX_PDF_BYTES:  # pragma: no cover - 结构性断言
    raise AssertionError("upload limit must not exceed the parser limit")

#: `source_id` 前缀：由**内容摘要**派生，⛔ 不来自文件名 / 调用方字符串。
SOURCE_ID_PREFIX = "pdf-upload:sha256:"
_SOURCE_ID_DIGEST_LENGTH = 16

#: ⛔ 结论字段**只能**是这个值；批准与否不是上传/解析能决定的。
PENDING_REVIEW_CONCLUSION = "pending_group_lead_review"

#: 固定错误码（⛔ 不回显调用方字符串、⛔ 不含路径）。
ERROR_MEDIA_TYPE_UNSUPPORTED = "pdf_upload_media_type_unsupported"
ERROR_LENGTH_REQUIRED = "pdf_upload_length_required"
ERROR_TOO_LARGE = "pdf_upload_too_large"
ERROR_DECLARED_LENGTH_MISMATCH = "pdf_upload_declared_length_mismatch"
ERROR_EMPTY_UPLOAD = "pdf_upload_empty"

#: `Content-Length` 的**最大位数**。
#: ⚠️ 先比位数再 `int()`：CPython 对超长十进制字符串的 `int()` 会抛 `ValueError`，
#: 那会变成 500，违反 fail-closed 约定。
_MAX_LENGTH_DIGITS = len(str(MAX_UPLOAD_BYTES))


class PdfUploadError(Exception):
    """上传被拒绝（固定错误码 + 面向用户的固定文案）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_media_type(raw: object) -> str:
    """媒体类型归一化：小写化并丢弃参数（`application/pdf; charset=x` → `application/pdf`）。"""

    if not isinstance(raw, str) or not raw.strip():
        return ""
    return raw.split(";", 1)[0].strip().lower()


def parse_declared_content_length(raw: object) -> int:
    """把 `Content-Length` 解析成字节数；⛔ 任何异常输入都 fail closed。

    接受格式**仅限**纯 ASCII 十进制数字（⛔ 无前后空白、⛔ 无符号、⛔ 无小数点、
    ⛔ 无 Unicode 数字如全角 `８`）。

    ⚠️ 位数先于 `int()` 判定：超长纯数字**直接**判超限，
    ⛔ 不构造任意大整数、⛔ 不冒 `ValueError` 变成 500。
    """

    if not isinstance(raw, str) or not raw:
        raise PdfUploadError(ERROR_LENGTH_REQUIRED, "上传必须显式声明 Content-Length。")
    if not raw.isascii() or not raw.isdigit():
        raise PdfUploadError(
            ERROR_LENGTH_REQUIRED,
            "Content-Length 必须是纯 ASCII 十进制数字（⛔ 不接受空白 / 符号 / 小数 / Unicode 数字）。",
        )
    if len(raw) > _MAX_LENGTH_DIGITS:
        raise PdfUploadError(ERROR_TOO_LARGE, "上传文件超过大小上限。")
    value = int(raw)
    if value > MAX_UPLOAD_BYTES:
        raise PdfUploadError(ERROR_TOO_LARGE, "上传文件超过大小上限。")
    return value


@dataclass(frozen=True, slots=True)
class PdfUploadOutcome:
    """一次上传解析的结果（⛔ 不含任何文件路径）。"""

    source_id: str
    sha256: str
    file_name: str
    role: str
    kind: str
    major: str
    cohort: str
    draft: CatalogDraftInput
    result: DocxImportResult = field(repr=False)
    #: 已验收文档类型（含分类证据表声明）。供审核层读取；
    #: ⛔ 它不参与任何"数据真实性"判定（那条只由内容结构决定）。
    document: object = None
    review_conclusion: str = PENDING_REVIEW_CONCLUSION

    @property
    def row_count(self) -> int:
        return len(self.draft.course_records)

    @property
    def unresolved_count(self) -> int:
        return len(self.draft.unresolved_rows)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumNormalizationError(f"pdf upload: {label} must be non-empty text")
    return value.strip()


def _row_payload(row: object) -> dict:
    """把一行投影成 catalog course_record（⛔ 不增字段、⛔ 不推断）。"""

    payload: dict = {
        "course_id": row.course_id,  # type: ignore[attr-defined]
        "course_name": row.course_name,  # type: ignore[attr-defined]
        "credit": row.credit,  # type: ignore[attr-defined]
        "requirement": row.requirement.value,  # type: ignore[attr-defined]
        "source_record": row.source_record,  # type: ignore[attr-defined]
    }
    for key in ("course_type", "group_id", "recommended_term_text"):
        value = getattr(row, key)
        if value is not None:
            payload[key] = value
    return payload


def _issue_payload(issue: DocxImportIssue) -> dict:
    return {
        "code": issue.code,
        "table_index": issue.table_index,
        "row_index": issue.row_index,
        "field": issue.field,
        "column_index": issue.column_index,
    }


def _is_resolved(row: object) -> bool:
    """这一行的**取值**是否完整（`requirement` 只在被声明时才参与判断）。

    `row.raw_values` 只包含 profile **实际映射**的列，
    因此 `"requirement" in raw_values` 就等于"profile 声明了 requirement 列"。
    """

    mapped = {key for key, _value in getattr(row, "raw_values", ())}
    resolved = (
        not row.issues  # type: ignore[attr-defined]
        and row.course_id is not None  # type: ignore[attr-defined]
        and row.course_name is not None  # type: ignore[attr-defined]
        and row.credit is not None  # type: ignore[attr-defined]
    )
    if "requirement" in mapped:
        resolved = resolved and row.requirement != RequirementKind.UNKNOWN  # type: ignore[attr-defined]
    return resolved


def _duplicate_course_ids(result: DocxImportResult) -> dict[str, tuple[str, ...]]:
    """找出**同一课程号出现多次**的情况（返回 `{课程号: (定位, …)}`）。

    ⚠️ 这是真实培养方案里确实存在的形态：同一门课会**同时列在多个课程模块下**
    （例如"专业必修"与"本研贯通"各列一次），学分与开课学期完全一致。

    ⛔ 本模块**不去重**：`source_record` 是唯一性主键，合并两处出现等于
    擅自判定"这两条是同一门课"，那属于**课程认定**——必须由人决定。
    ⛔ 也不静默丢弃重复项：它们既不是"无法识别"，也不能被悄悄删掉。
    因此这里只做**如实统计**，由调用方写进待人工确认清单。
    """

    seen: dict[str, list[str]] = {}
    for row in result.rows:
        if row.course_id is None:
            continue
        seen.setdefault(row.course_id, []).append(row.source_record)
    return {key: tuple(value) for key, value in seen.items() if len(value) > 1}


def build_draft_from_result(
    result: DocxImportResult, *, role: str, file_name: str, source_id: str,
) -> CatalogDraftInput:
    """把解析结果组装成**审核草稿**（复用既有 `CatalogDraftInput` 形状）。

    ⛔ 与 `catalog_draft._HUMAN_REQUIRED_FIELDS` **同一张**待确认清单：
    这里**不新增**任何"人工必须确认"的字段（那属于业务规则，需人工批准）；
    只把**本次解析实际观察到**的问题追加进去。
    """

    from app.curriculum.catalog_draft import _HUMAN_REQUIRED_FIELDS

    resolved: list[dict] = []
    unresolved: list[dict] = []
    for row in result.rows:
        payload = _row_payload(row)
        payload["issues"] = [_issue_payload(issue) for issue in row.issues]
        (resolved if _is_resolved(row) else unresolved).append(payload)

    human_required = [
        {"field": name, "reason": reason, "applies_to": "each course_record"}
        for name, reason in _HUMAN_REQUIRED_FIELDS
    ]
    if unresolved:
        human_required.append({
            "field": "unresolved_rows",
            "reason": "文档里有未能确定取值的行：必须人工判定后再决定是否进入正式目录。",
            "applies_to": f"{len(unresolved)} row(s)",
        })
    duplicates = _duplicate_course_ids(result)
    if duplicates:
        human_required.append({
            "field": "duplicate_course_id",
            "reason": (
                "同一课程号在文档中**出现多次**（真实培养方案会把同一门课列在多个课程模块下）。"
                "⛔ 解析器不去重、⛔ 不合并：是否视为同一门课属于**课程认定**，"
                "必须由人判定后再决定保留哪一条或如何归并。"
            ),
            "applies_to": "、".join(
                f"{key}×{len(value)}" for key, value in sorted(duplicates.items())
            ),
        })
    # ⛔ PDF **不产出** group_records：课程组学分要求必须来自文档明示数值，
    #    且⛔ 不得用成员学分求和代替。缺失即明确要求人工填写。
    human_required.append({
        "field": "group_records",
        "reason": (
            "PDF 解析⛔ 不推导课程组学分要求（文档明示数值须人工填写，"
            "⛔ 不得用成员学分求和代替）。"
        ),
        "applies_to": "missing",
    })
    human_required.append({
        "field": "verification",
        "reason": "⛔ 上传与解析都不构成来源核验：必须由组长给出 verified=true 与非空 evidence。",
        "applies_to": "version entry",
    })
    human_required.append({
        "field": "version_identity",
        "reason": "version_id / major / cohort 必须由人确认（version_id 重复会让该 id 整体不可选）。",
        "applies_to": "version entry",
    })
    human_required.append({
        "field": "source_provenance",
        "reason": (
            "本轮 PDF 是**由教务网页重排生成的转换件**，⛔ 不得当作学校正式签发的原始 PDF；"
            "来源说明必须与提交者所述一致。"
        ),
        "applies_to": "source",
    })

    return CatalogDraftInput(
        source_id=source_id,
        docx_name=file_name,
        role=role,
        course_records=tuple(resolved),
        group_records=(),
        unresolved_rows=tuple(unresolved),
        document_issues=tuple(_issue_payload(issue) for issue in result.issues),
        human_required=tuple(human_required),
    )


def ingest_pdf_upload(
    payload: object,
    *,
    declared_length: object,
    media_type: object,
    file_name: object,
    role: object,
    major: object,
    cohort: object,
    source: object,
    document_type: object = None,
) -> PdfUploadOutcome:
    """校验并解析一次 PDF 上传；⛔ 失败即抛错，⛔ 从不返回"猜测的结果"。

    ⚠️ **profile 不再由调用方提供**：本函数从
    `app/curriculum/pdf_profiles.py`（已验收注册表）取，
    与 `tools/parse_curriculum_pdf.py` 共用同一份声明，⛔ 不会漂移。

    `document_type` 只是**断言**：会与"按内容结构判定的结果"核对，
    不一致即拒绝。⛔ 因此不可能仅凭专业名 / 文件名 / 角色决定数据真实性。

    ⛔ 不写文件、⛔ 不联网、⛔ 不把任何调用方字符串当作路径。
    """

    normalized = normalize_media_type(media_type)
    if normalized not in ALLOWED_MEDIA_TYPES:
        raise PdfUploadError(
            ERROR_MEDIA_TYPE_UNSUPPORTED,
            "只接受 application/pdf 或 application/octet-stream（⛔ 不接受 multipart / text/plain）。",
        )

    declared = parse_declared_content_length(declared_length)

    if not isinstance(payload, (bytes, bytearray)) or isinstance(payload, str):
        raise PdfUploadError(ERROR_EMPTY_UPLOAD, "上传内容必须是原始字节。")
    body = bytes(payload)
    if len(body) != declared:
        raise PdfUploadError(
            ERROR_DECLARED_LENGTH_MISMATCH,
            "Content-Length 与**实际读取**的字节数不一致。",
        )
    if not body:
        raise PdfUploadError(ERROR_EMPTY_UPLOAD, "上传文件为空。")
    if len(body) > MAX_UPLOAD_BYTES:
        raise PdfUploadError(ERROR_TOO_LARGE, "上传文件大小超过上限。")

    digest = hashlib.sha256(body).hexdigest()
    # ⛔ `source_id` 只由**内容摘要**决定：文件名与调用方字符串都不参与。
    source_id = f"{SOURCE_ID_PREFIX}{digest[:_SOURCE_ID_DIGEST_LENGTH]}"

    role_text = _require_text(role, "role")
    if role_text not in {"origin", "target"}:
        raise CurriculumNormalizationError("pdf upload: role must be origin or target")

    # ⚠️ 已验收文档类型的解析入口（CLI 与 HTTP 共用）。
    #    专业名 / 年级 / 角色都**不参与** profile 选择与真实性判定。
    document, result = load_curriculum_pdf_verified(
        body, source_id=source_id, document_key=document_type,
    )

    draft = build_draft_from_result(
        result,
        role=role_text,
        file_name=_safe_file_name(file_name),
        source_id=source_id,
    )
    return PdfUploadOutcome(
        source_id=source_id,
        sha256=digest,
        file_name=_safe_file_name(file_name),
        role=role_text,
        kind=document.key,
        document=document,
        major=_require_text(major, "major"),
        cohort=_require_text(cohort, "cohort"),
        draft=draft,
        result=result,
    )


def _safe_file_name(raw: object) -> str:
    """只保留**基名**：⛔ 不把调用方给的路径写进任何输出（防目录结构泄漏）。"""

    if not isinstance(raw, str) or not raw.strip():
        return "curriculum.pdf"
    cleaned = raw.strip().replace("\\", "/")
    base = cleaned.rsplit("/", 1)[-1]
    return base or "curriculum.pdf"


def describe_outcome(outcome: PdfUploadOutcome, *, source: str) -> dict:
    """给前端的**安全摘要**（⛔ 不含本地路径、⛔ 不含原始单元格文本）。"""

    return {
        "source_id": outcome.source_id,
        "sha256": outcome.sha256,
        "file_name": outcome.file_name,
        "role": outcome.role,
        "major": outcome.major,
        "cohort": outcome.cohort,
        "source": source,
        "row_count": outcome.row_count,
        "unresolved_count": outcome.unresolved_count,
        "issue_count": len(outcome.draft.document_issues),
        "review_conclusion": outcome.review_conclusion,
        "verification": {"verified": False, "evidence": None},
        "complete": False,
        "is_official_school_pdf": False,
    }
