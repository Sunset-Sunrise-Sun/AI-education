"""把**培养方案 PDF** 的表格结构转成既有的 `DocxImportResult`（= 审核草稿的输入契约）。

```text
PDF bytes
   │  ① 结构校验（%PDF- magic / 大小 / 页数上限 / 加密）
   │  ② 文本层探测（扫描件 ⇒ fail closed，⛔ 不自动 OCR）
   │  ③ 表格识别（PyMuPDF `find_tables()`）
   ▼
声明式 profile（`mode="tables"`）：**表头精确匹配** → 声明列位
   ▼
DocxCourseRow（含唯一 `source_record = "page:{n}!row:{i}"`）+ DocxImportIssue
   ▼
DocxImportResult  ← 与 DOCX 路径**完全相同**的类型
   ▼
（零改动复用）catalog_draft → catalog.json → 审核 → provenance 门禁 → 个人规划
```

## 为什么输出的是 `DocxImportResult`

因为它就是"解析出来的课程行 + 问题清单"这一层的既有契约：
`catalog_draft.py` / `catalog.py` / `review_real_data.py` **完全不知道 docx 的存在**，
只消费这些 dataclass 的**属性**。因此 PDF 路径只要产出同一类型，下游全部免费复用，
⛔ 不需要（也⛔ 不允许）复制任何草稿 / 目录 / 门禁逻辑。

> ⚠️ 命名说明：`Docx*` 前缀是**历史包袱**（它先被 DOCX 用到）。
> 本模块**不改名**——改名会波及 `catalog_draft.py` 等已验收代码，
> 而那属于"为当前实现方便而改动其他模块"，本轮的取舍是**保持既有契约、不重构**。

## ⛔ 本模块**不**做的事（硬边界）

| ⛔ 不做 | 由什么保证 |
| --- | --- |
| 从课程名称猜课程号 | 只读**声明列位/表头**里的课程号单元格；缺失即 `unresolved_course_id`。本模块不存在任何"名称→编号"映射表 |
| 用成员学分求和猜课程组最低要求 | 本模块**完全不产出** `group_records`（那是人工填写项，见 `catalog_draft._HUMAN_REQUIRED_FIELDS`） |
| 自动判定跨专业课程等价 | 不产出任何等价关系 |
| 对扫描型 PDF 做 OCR | 文本层缺失 ⇒ `scanned_pdf_text_layer_missing` 整体 fail closed |
| 猜测无法识别的行 | 无法确定取值的行**仍然产出**（带 `issues`），⛔ 不静默丢弃 |
| 把 PDF 写成"学校正式签发" | 本模块只读字节；来源标注由调用方传入，⛔ 本模块不写任何"正式"字样 |
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.curriculum.docx_reader import (
    _CREDIT,
    _UNKNOWN_IDS,
    DocxCourseRow,
    DocxImportIssue,
    DocxImportResult,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.requirements import RequirementKind

__all__ = [
    "MAX_PDF_BYTES",
    "MAX_PDF_PAGES",
    "MIN_TEXT_CHARS_PER_PAGE",
    "PDF_PROFILE_FIELDS",
    "load_curriculum_pdf",
]

# --------------------------------------------------------------------------- #
# 硬上界（⛔ 不因调用方传入而放宽）
# --------------------------------------------------------------------------- #

#: 单份 PDF 的字节上限（与 `docx_reader._MAX_FILE_BYTES` 同量级：32 MiB）。
MAX_PDF_BYTES = 32 * 1024 * 1024

#: 页数上限：培养方案是几页到几十页；超出即视为"不是培养方案"或异常输入。
MAX_PDF_PAGES = 200

#: 扫描件判定阈值：每页平均可提取字符数低于该值 ⇒ 认为**没有文本层**。
#: ⚠️ 保守取 20：宁可把可疑 PDF 判为"不支持"（fail closed），
#: 也⛔ 不冒险把 OCR 出来的猜测当成课程数据。
MIN_TEXT_CHARS_PER_PAGE = 20

#: `tables` profile 允许的字段（与 `docx_reader._FIELDS` **同一集合**）。
PDF_PROFILE_FIELDS = frozenset({
    "course_id", "course_name", "credit", "recommended_term_text", "requirement", "sequence",
})

#: `tables` profile 允许声明的键。
#: ⛔ 只支持这一种模式：先按**表头文字精确匹配**定位列，再按声明列位取值。
#: ⛔ 不支持"按固定序号猜列"——PDF 没有稳定的列序保证，猜列就是猜数据。
_PDF_PROFILE_FIELDS = frozenset({
    "mode", "table_index", "columns", "expected_headers",
    "requirement", "course_type", "group_id", "requirement_values",
})

_PDF_MAGIC = b"%PDF-"

#: PDF 里数字后面可能跟着单位（`3 学分` / `3学分` / `3 credits`），
#: 但⚠️ **只剥掉单位**，⛔ 不从区间里挑一个（`3-4` 必须留空 + `unresolved_credit`）。
_CREDIT_UNIT = re.compile(r"[\s\u3000]*(?:学分|分|credits?|points?)?[\s\u3000]*\Z", re.IGNORECASE)


class _PdfProfileError(CurriculumNormalizationError):
    """profile 声明非法（与既有 `document profile:` 前缀同风格）。"""


@dataclass(frozen=True, slots=True)
class _TableProfile:
    """一个已校验的 PDF 表格声明。"""

    table_index: int
    columns: tuple[tuple[str, int], ...]
    expected_headers: tuple[tuple[str, tuple[str, ...]], ...]
    requirement: RequirementKind
    fixed_requirement: bool
    course_type: str | None
    group_id: str | None
    requirement_values: tuple[tuple[str, RequirementKind], ...]


# --------------------------------------------------------------------------- #
# profile 校验（与 docx_reader 同风格：⛔ 缺字段即 fail closed）
# --------------------------------------------------------------------------- #

def _fail(message: str) -> None:
    raise CurriculumNormalizationError(f"pdf profile: {message}")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label}: expected non-empty text")
    return value.strip()


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(f"{label}: expected a positive integer")
    return value


def _header_candidates(value: object, label: str) -> tuple[str, ...]:
    """一个映射列可以接受**若干种精确写法**（如中文表头 + 英文表头）。

    ⛔ 仍然是**精确匹配**：每个候选都要与单元格文字**完全相等**。
    ⛔ 不做模糊匹配、⛔ 不做包含匹配、⛔ 不做大小写折叠——
    那些都会让"这一列到底是什么"变成猜测。
    """

    if isinstance(value, str):
        return (_text(value, label),)
    if isinstance(value, (bytes, bytearray)) or not isinstance(value, Sequence):
        _fail(f"{label}: expected text or a list of texts")
    candidates = tuple(_text(item, label) for item in value)
    if not candidates:
        _fail(f"{label}: expected at least one candidate")
    if len(set(candidates)) != len(candidates):
        _fail(f"{label}: duplicate candidate")
    return candidates


def _requirement_kind(value: object) -> RequirementKind:
    try:
        return RequirementKind(value)
    except ValueError:
        _fail("requirement: expected one of required / elective / unknown")


def _profile(spec: Mapping[str, object]) -> _TableProfile:
    if not isinstance(spec, Mapping):
        _fail("expected a mapping")
    unknown = set(spec) - _PDF_PROFILE_FIELDS
    if unknown:
        _fail("unsupported field")
    if spec.get("mode") != "tables":
        # ⛔ 只有一种模式：PDF 的"位置"必须由**表头文字**锚定。
        _fail('mode: only "tables" is supported for PDF')

    columns = spec.get("columns")
    if not isinstance(columns, Mapping) or not {"course_id", "course_name", "credit"} <= set(columns):
        _fail("core course columns are required")
    if set(columns) - PDF_PROFILE_FIELDS:
        _fail("unsupported column field")
    positions = tuple(_positive_int(value, "column_index") for value in columns.values())
    if len(set(positions)) != len(positions):
        _fail("invalid or duplicate column index")

    raw_headers = spec.get("expected_headers")
    if not isinstance(raw_headers, Mapping):
        _fail("expected_headers: required for PDF tables")
    # ⛔ 表头必须**恰好**覆盖所有映射列：多一个少一个都会让列位含义漂移。
    if set(raw_headers) != set(columns):
        _fail("expected_headers: must cover exactly the mapped columns")
    expected = tuple(
        (key, _header_candidates(raw_headers[key], f"expected_headers.{key}")) for key in columns
    )

    mapping = spec.get("requirement_values", {})
    if not isinstance(mapping, Mapping) or (mapping and "requirement" not in columns):
        _fail("invalid requirement mapping")
    values = tuple(
        (_text(key, "requirement_values"), _requirement_kind(value)) for key, value in mapping.items()
    )

    course_type = spec.get("course_type")
    group_id = spec.get("group_id")
    return _TableProfile(
        table_index=_positive_int(spec.get("table_index"), "table_index"),
        columns=tuple((str(key), int(value)) for key, value in columns.items()),
        expected_headers=expected,
        requirement=_requirement_kind(spec.get("requirement", RequirementKind.UNKNOWN)),
        fixed_requirement="requirement" in spec,
        course_type=None if course_type is None else _text(course_type, "course_type"),
        group_id=None if group_id is None else _text(group_id, "group_id"),
        requirement_values=values,
    )


def _profiles(tables: Sequence[Mapping[str, object]]) -> tuple[_TableProfile, ...]:
    if isinstance(tables, (str, bytes, bytearray)) or not isinstance(tables, Sequence):
        _fail("expected a sequence of table declarations")
    if not tables:
        _fail("at least one table declaration is required")
    if len(tables) > 128:
        _fail("too many table declarations")
    result = tuple(_profile(spec) for spec in tables)
    indices = [item.table_index for item in result]
    if len(set(indices)) != len(indices):
        _fail("duplicate table_index")
    return result


# --------------------------------------------------------------------------- #
# 单元格取值（⛔ 只做"取值"，⛔ 不做"猜语义"）
# --------------------------------------------------------------------------- #

def _cell(value: object) -> str | None:
    """把一个表格单元格归一成文本；⛔ 空即 `None`，⛔ 不填充占位符。"""

    if value is None:
        return None
    text = str(value).replace("\u00a0", " ").replace("\u3000", " ")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines) or None


def _course_id(raw: str | None) -> str | None:
    """课程号：⛔ 只接受非空的**原文**；占位符 / 待确认字样一律视为"未确定"。"""

    if raw is None:
        return None
    text = raw.strip()
    if not text or text in _UNKNOWN_IDS or text.lower() in _UNKNOWN_IDS:
        return None
    # ⛔ 不做任何"从名称里提取编号"的推断：这里只接受单元格自己写的东西。
    return text


def _credit(raw: str | None) -> float | None:
    """学分：⛔ 只接受可解析的**单个数字**；⛔ 不猜、⛔ 不取区间里的某一个。"""

    if raw is None:
        return None
    text = raw.strip()
    # 先剥单位（`3 学分` / `3 credits` / `3分`），再要求剩下的是**纯数字**。
    stripped = _CREDIT_UNIT.sub("", text)
    for candidate_text in (stripped, text):
        if candidate_text and _CREDIT.fullmatch(candidate_text):
            candidate = float(candidate_text.lstrip("+"))
            return candidate if candidate >= 0 else None
    return None


def _requirement(raw: str | None, profile: _TableProfile) -> tuple[RequirementKind, bool]:
    """返回 `(requirement, 是否未映射)`。

    ⛔ 未声明的取值 → `UNKNOWN` + `unmapped_requirement`（⛔ 不猜成必修/选修）。
    """

    if "requirement" not in dict(profile.columns):
        return (profile.requirement, False)
    mapping = dict(profile.requirement_values)
    text = (raw or "").strip()
    if text in mapping:
        return (mapping[text], False)
    declared = {kind.value for kind in RequirementKind}
    if text in declared:
        return (RequirementKind(text), False)
    if not text and not profile.fixed_requirement:
        # 列存在但单元格为空：保留表级声明，⛔ 不算"未映射"。
        return (profile.requirement, False)
    return (RequirementKind.UNKNOWN, True)


# --------------------------------------------------------------------------- #
# 表格 → 行
# --------------------------------------------------------------------------- #

def _header_index(row: Sequence[str | None]) -> dict[str, int]:
    """表头行 → `{表头文字: 列号}`；重复表头文字会被**降级**为不可用。"""

    index: dict[str, int] = {}
    duplicated: set[str] = set()
    for position, value in enumerate(row):
        text = (value or "").strip()
        if not text:
            continue
        if text in index:
            duplicated.add(text)
            continue
        index[text] = position
    for text in duplicated:
        index.pop(text, None)
    return index


def _rows_from_table(
    table: object, profile: _TableProfile, page_number: int, *, issues: list[DocxImportIssue],
) -> list[DocxCourseRow]:
    """把一张已识别的表转成课程行；⛔ 任何不确定都产出行级 issue。"""

    extracted = getattr(table, "extract", None)
    if not callable(extracted):
        issues.append(DocxImportIssue("table_extraction_unavailable", profile.table_index, 0))
        return []
    raw_rows = extracted()
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
        issues.append(DocxImportIssue("table_extraction_unavailable", profile.table_index, 0))
        return []
    normalized = [[_cell(value) for value in row] for row in raw_rows]
    if not normalized:
        issues.append(DocxImportIssue("empty_table", profile.table_index, 0))
        return []

    header = _header_index(normalized[0])
    # ⛔ 每个映射列都必须命中它声明的**某一种**精确写法；否则整表拒绝
    #    （⛔ 不按位置硬套、⛔ 不做模糊匹配）。
    resolved: dict[str, int] = {}
    for key, candidates in profile.expected_headers:
        hit = next((header[text] for text in candidates if text in header), None)
        if hit is None:
            issues.append(DocxImportIssue("table_header_mismatch", profile.table_index, 0))
            return []
        resolved[key] = hit
    if len(set(resolved.values())) != len(resolved):
        # 两个映射列命中同一物理列 ⇒ 声明有歧义，整表拒绝。
        issues.append(DocxImportIssue("table_header_ambiguous", profile.table_index, 0))
        return []

    column_of = resolved

    rows: list[DocxCourseRow] = []
    for offset, values in enumerate(normalized[1:], start=1):
        if not any(value is not None for value in values):
            # 全空行：PDF 表格常见，⛔ 不算未识别，直接跳过。
            continue
        # ⚠️ **不**因"行比映射列窄"而跳过整行：真实 PDF 的表格经常**省略行尾空格**
        #    （某一列没有内容时连单元格都不画），把它当结构错误会误杀正常数据。
        #    缺失的单元格由 `_optional_get` 返回 `None`，随后**逐字段**产出
        #    `unresolved_*` / `missing_*` issue —— 行仍然产出，⛔ 不静态丢弃、⛔ 不猜值。
        raw_id = _optional_get(values, column_of["course_id"])
        raw_name = _optional_get(values, column_of["course_name"])
        raw_credit = _optional_get(values, column_of["credit"])
        raw_term = (
            _optional_get(values, column_of["recommended_term_text"])
            if "recommended_term_text" in column_of else None
        )
        raw_requirement = (
            _optional_get(values, column_of["requirement"])
            if "requirement" in column_of else None
        )

        course_id = _course_id(raw_id)
        course_name = raw_name.strip() if raw_name is not None else None
        course_name = course_name or None
        credit = _credit(raw_credit)
        requirement, unmapped = _requirement(raw_requirement, profile)

        row_issues: list[DocxImportIssue] = []
        if course_id is None:
            row_issues.append(DocxImportIssue(
                "unresolved_course_id", profile.table_index, offset, "course_id",
                column_of.get("course_id"),
            ))
        if course_name is None:
            row_issues.append(DocxImportIssue(
                "missing_course_name", profile.table_index, offset, "course_name",
                column_of.get("course_name"),
            ))
        if credit is None:
            row_issues.append(DocxImportIssue(
                "unresolved_credit", profile.table_index, offset, "credit",
                column_of.get("credit"),
            ))
        if unmapped:
            row_issues.append(DocxImportIssue(
                "unmapped_requirement", profile.table_index, offset, "requirement",
                column_of.get("requirement"),
            ))
        if profile.fixed_requirement and requirement != profile.requirement:
            row_issues.append(DocxImportIssue(
                "conflicting_requirement", profile.table_index, offset, "requirement",
                column_of.get("requirement"),
            ))

        rows.append(DocxCourseRow(
            table_index=profile.table_index,
            row_index=offset,
            course_id=course_id,
            course_name=course_name,
            credit=credit,
            requirement=requirement,
            # ⛔ 唯一且可追溯：页码 + 表内行号（与 DOCX 的 `table:T!row:R` 同构）。
            source_record=f"page:{page_number}!row:{offset}",
            course_type=profile.course_type,
            group_id=profile.group_id,
            recommended_term_text=(raw_term.strip() or None) if raw_term is not None else None,
            raw_values=tuple(
                (key, _optional_get(values, position))
                for key, position in sorted(column_of.items(), key=lambda item: item[1])
            ),
            issues=tuple(row_issues),
        ))
    return rows


def _optional_get(values: Sequence[str | None], position: int) -> str | None:
    if position < 0 or position >= len(values):
        return None
    return values[position]


# --------------------------------------------------------------------------- #
# 公开入口
# --------------------------------------------------------------------------- #

def load_curriculum_pdf(
    data: bytes, *, source_id: str, tables: Sequence[Mapping[str, object]],
) -> DocxImportResult:
    """把 PDF 字节解析成 `DocxImportResult`（= 审核草稿的输入契约）。

    ⛔ 失败即 `CurriculumNormalizationError`（fail closed）；⛔ 从不返回"部分猜测"的结果。
    ⛔ 不写任何文件、⛔ 不联网、⛔ 不调用 OCR。
    """

    if not isinstance(data, bytes):
        raise CurriculumNormalizationError("pdf import: expected bytes")
    if not data:
        raise CurriculumNormalizationError("pdf import: empty input")
    if len(data) > MAX_PDF_BYTES:
        raise CurriculumNormalizationError("pdf import: file is too large")
    # ⛔ magic 校验：PDF 头必须出现在**最前面**（允许少量前导空白/BOM 不符合 PDF 规范，故不接受）。
    if not data.startswith(_PDF_MAGIC):
        raise CurriculumNormalizationError("pdf import: not a PDF (missing %PDF- header)")

    profiles = _profiles(tables)

    try:
        import pymupdf
    except ImportError:  # pragma: no cover - 依赖缺失是部署问题，不是数据问题
        raise CurriculumNormalizationError(
            "pdf import: PDF support is unavailable in this environment"
        ) from None

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        # ⛔ 不把底层异常文本冒出去（可能含路径 / 库版本信息）。
        raise CurriculumNormalizationError("pdf import: file is damaged or unreadable") from None

    try:
        if document.needs_pass:
            # ⛔ 加密 PDF 不尝试破解（也不接受调用方传密码）。
            raise CurriculumNormalizationError("pdf import: encrypted PDF is not supported")
        page_count = int(document.page_count)
        if page_count < 1:
            raise CurriculumNormalizationError("pdf import: empty document")
        if page_count > MAX_PDF_PAGES:
            raise CurriculumNormalizationError("pdf import: too many pages")

        issues: list[DocxImportIssue] = []
        rows: list[DocxCourseRow] = []
        total_chars = 0

        for page_index in range(page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            text = page.get_text("text") or ""
            total_chars += len(text.strip())

            # ⚠️ `find_tables()` 只调用**一次**：它是概率性识别，
            #    重复调用可能给出不同结果，那会让行号失去可追溯性。
            found = page.find_tables()
            tables_on_page = list(getattr(found, "tables", ()) or ())

            by_index: dict[int, list[DocxCourseRow]] = {}
            for profile in profiles:
                if profile.table_index > len(tables_on_page):
                    issues.append(DocxImportIssue(
                        "table_not_found", profile.table_index, page_number,
                    ))
                    continue
                by_index.setdefault(profile.table_index, []).extend(
                    _rows_from_table(
                        tables_on_page[profile.table_index - 1], profile, page_number,
                        issues=issues,
                    )
                )
            for index in sorted(by_index):
                rows.extend(by_index[index])

        # ⛔ 扫描件判定：没有文本层就**明确不支持**，⛔ 绝不用版面猜测凑数据。
        if total_chars < MIN_TEXT_CHARS_PER_PAGE * page_count:
            raise CurriculumNormalizationError(
                "pdf import: no extractable text layer (scanned PDF is not supported; "
                "manual handling required)"
            )

        return DocxImportResult(
            source_id=_text(source_id, "source_id"),
            rows=tuple(rows),
            issues=tuple(issues),
        )
    finally:
        document.close()
