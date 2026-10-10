"""把**培养方案 PDF** 的表格结构转成既有的 `DocxImportResult`（= 审核草稿的输入契约）。

```text
PDF bytes
   │  ① 结构校验（%PDF- magic / 大小 / 页数上限 / 加密）
   │  ② 文本层探测（扫描件 ⇒ fail closed，⛔ 不自动 OCR）
   │  ③ 表格识别（PyMuPDF `find_tables()`）
   ▼
声明式 profile（`mode="tables"`）：**逐行表头精确匹配** → 声明列位
   │  ⚠️ 支持 `header_rows`：真实培养方案常见**双行表头 + 合并单元格**
   ▼
DocxCourseRow（含唯一 `source_record = "page:{n}!row:{i}"`）+ DocxImportIssue
   ▼
DocxImportResult  ← 与 DOCX 路径**完全相同**的类型
   ▼
（零改动复用）catalog_draft → catalog.json → 审核 → provenance 门禁 → 个人规划
```

**写 profile 之前先跑 `inspect_curriculum_pdf()`**（CLI：`--inspect`）：
它逐页给出表格数量、列数、行数与**逐行表头原文**，⛔ 不猜任何列位。
profile 的 `expected_headers` 必须**照抄**那里的表头文字。

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
    "inspect_curriculum_pdf",
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

#: `tables` profile 允许的字段。
#: 前 6 个与 `docx_reader._FIELDS` **同一集合**（真正会被取值的字段）；
#: 后面几个是**只参与表头校验**的列（⛔ 不会被取值、⛔ 不影响任何输出）：
#: 真实培养方案的表格有 8~10 列，把整行表头都声明出来才能做**完整**的匹配校验，
#: 文档类型判定也需要整行表头（见 `app/curriculum/pdf_profiles.py`）。
PDF_PROFILE_FIELDS = frozenset({
    "course_id", "course_name", "credit", "recommended_term_text", "requirement", "sequence",
    # 以下仅用于表头校验（⛔ 不产生任何课程字段）
    "course_category", "course_module", "theory_hours", "practice_hours", "weighted_course",
})

#: `tables` profile 允许声明的键。
#: ⛔ 只支持这一种模式：先按**表头文字精确匹配**定位列，再按声明列位取值。
#: ⛔ 不支持"按固定序号猜列"——PDF 没有稳定的列序保证，猜列就是猜数据。
_PDF_PROFILE_FIELDS = frozenset({
    "mode", "table_index", "pages", "columns", "expected_headers", "header_rows",
    "requirement", "course_type", "group_id", "requirement_values",
    # 表用途与小节列：由课程明细表声明；证据表（类别学分要求表 / 实践附表）
    # 由 pdf_evidence 消费，⛔ 不产出课程行。
    "table_purpose", "section_columns",
    # 证据表专用（course_detail 不会用到，但同一份 profile 里要允许出现）
    "category_values",
})

#: 表用途码（与 `app/curriculum/pdf_evidence.py` **同一套**取值）。
#: ⛔ 只有 `course_detail` 会产出课程行；其余用途只产出**证据**。
_PURPOSE_COURSE_DETAIL = "course_detail"
_TABLE_PURPOSES = frozenset({
    _PURPOSE_COURSE_DETAIL, "category_credit_requirement", "practice_appendix",
})

#: 表头行数上限（真实培养方案常见 1–2 行；⛔ 不给"随便多写几行"的空间）。
_MAX_HEADER_ROWS = 3

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
    #: 该声明适用的页码集合；空元组 = **所有页**。
    #: ⚠️ 真实培养方案同一份文件里会有多种表：课程明细表、学分汇总表、
    #:    学期学分分布表、实践教学附表。按页限定可以**只**声明要导入的那几张，
    #:    ⛔ 不需要（也不允许）用"表头里有没有某几个字"之类的规则去猜。
    pages: tuple[int, ...]
    columns: tuple[tuple[str, int], ...]
    #: `expected_headers[列名] = (候选1, 候选2, …)`，每个候选是**逐行表头文字**的元组。
    #: 单行表头 ⇒ 每个候选是 1 元组；双行表头 ⇒ 2 元组。
    expected_headers: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]
    header_rows: int
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


def _header_text(value: object, label: str, *, allow_null: bool) -> str:
    """一行表头文字：字符串，或（`allow_null` 时）`None` 表示该格为空。"""

    if value is None:
        if allow_null:
            return ""
        _fail(f"{label}: expected text")
    if not isinstance(value, str):
        _fail(f"{label}: expected text")
    return value.strip()


def _header_candidates(value: object, label: str, *, rows: int) -> tuple[tuple[str, ...], ...]:
    """一个映射列可以接受**若干种精确写法**；每种写法是**逐行表头文字**的元组。

    单行表头（`rows=1`）两种等价写法：

    ```json
    "expected_headers": { "course_id": "课程号" }
    "expected_headers": { "course_id": ["课程号", "Course Code"] }
    ```

    双行表头（`rows=2`）必须给出"每行一个候选"的列表；`null` = 该行这一格为空：

    ```json
    "expected_headers": { "credit": [["学分", null], ["Credit", "Credits"]] }
    ```

    ⚠️ 实测结论：**合并单元格不会产生 `""`**，而是 `null`（或横线渲染出的 `"-----"`）。
    因此 `null` 表示"该行这一格为空"，而 `""` **永远匹配不上**——
    这正是我们想要的：⛔ 不允许"向上填充"式的宽松匹配。

    ⛔ 仍然是**逐行精确匹配**：每一行的单元格文字都要与对应候选**完全相等**。
    ⛔ 不做模糊匹配、⛔ 不做包含匹配、⛔ 不做大小写折叠——
    那些都会让"这一列到底是什么"变成猜测。
    """

    if isinstance(value, (bytes, bytearray)):
        _fail(f"{label}: expected text or a list of texts")

    if rows == 1:
        if isinstance(value, str):
            return ((value.strip(),),)
        if not isinstance(value, Sequence):
            _fail(f"{label}: expected text or a list of texts")
        candidates: list[tuple[str, ...]] = []
        for item in value:
            if isinstance(item, str):
                candidates.append((item.strip(),))
            elif isinstance(item, Sequence):
                entry = tuple(item)
                if len(entry) != 1:
                    # 单行表头不能接受"多行候选"。
                    _fail(f"{label}: single-row header expects one text per candidate")
                candidates.append((_header_text(entry[0], label, allow_null=True),))
            else:
                _fail(f"{label}: expected text or a list of texts")
        if not candidates:
            _fail(f"{label}: expected at least one candidate")
        if len(set(candidates)) != len(candidates):
            _fail(f"{label}: duplicate candidate")
        return tuple(candidates)

    if isinstance(value, str) or not isinstance(value, Sequence):
        _fail(f"{label}: a {rows}-row header expects a list of candidates")
    multi: list[tuple[str, ...]] = []
    for item in value:
        if isinstance(item, str) or not isinstance(item, Sequence):
            _fail(f"{label}: a {rows}-row header expects a list of candidates")
        entry = tuple(item)
        if len(entry) != rows:
            _fail(f"{label}: each candidate must give exactly {rows} header row(s)")
        multi.append(tuple(_header_text(part, label, allow_null=True) for part in entry))
    if not multi:
        _fail(f"{label}: expected at least one candidate")
    if len(set(multi)) != len(multi):
        _fail(f"{label}: duplicate candidate")
    return tuple(multi)


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

    header_rows = spec.get("header_rows", 1)
    if isinstance(header_rows, bool) or not isinstance(header_rows, int) \
            or not 1 <= header_rows <= _MAX_HEADER_ROWS:
        _fail("header_rows: expected an integer between 1 and 3")

    expected = tuple(
        (key, _header_candidates(raw_headers[key], f"expected_headers.{key}", rows=header_rows))
        for key in columns
    )

    mapping = spec.get("requirement_values", {})
    if not isinstance(mapping, Mapping) or (mapping and "requirement" not in columns):
        _fail("invalid requirement mapping")
    values = tuple(
        (_text(key, "requirement_values"), _requirement_kind(value)) for key, value in mapping.items()
    )

    course_type = spec.get("course_type")
    group_id = spec.get("group_id")
    raw_pages = spec.get("pages")
    if raw_pages is None:
        pages: tuple[int, ...] = ()
    elif isinstance(raw_pages, (str, bytes, bytearray)) or not isinstance(raw_pages, Sequence):
        _fail("pages: expected a list of positive integers")
    else:
        pages = tuple(_positive_int(value, "pages") for value in raw_pages)
        if len(set(pages)) != len(pages):
            _fail("pages: duplicate page number")
    return _TableProfile(
        table_index=_positive_int(spec.get("table_index"), "table_index"),
        pages=pages,
        columns=tuple((str(key), int(value)) for key, value in columns.items()),
        expected_headers=expected,
        header_rows=header_rows,
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
    # ⛔ 每个声明都必须是 mapping；⛔ 用途码必须合法
    #    （写错用途就静默忽略是最危险的行为，所以未知用途直接拒绝）。
    for spec in tables:
        if not isinstance(spec, Mapping):
            _fail("each table declaration must be a mapping")
        purpose = spec.get("table_purpose", "course_detail")
        if purpose not in _TABLE_PURPOSES:
            _fail("unsupported table_purpose")
    # ⚠️ 只处理**课程明细表**：一份 profile 里会同时带着"分类证据表"
    #    （类别学分要求表 / 实践教学附表）。⛔ 那些表绝不能产出课程行 ——
    #    否则学分汇总表会被当成课程导入（PR #75 已确立的边界）。
    detail = [
        spec for spec in tables
        if spec.get("table_purpose", "course_detail") == _PURPOSE_COURSE_DETAIL
    ]
    if not detail:
        _fail("at least one course_detail table declaration is required")
    result = tuple(_profile(spec) for spec in detail)
    # ⛔ 同一 `table_index` 只有在**页范围互不重叠**时才能重复声明：
    #    真实培养方案里"第 1 张表"在不同页可能是完全不同的表
    #    （课程明细表 vs 学分汇总表），所以按页区分是必要的；
    #    但两页若都覆盖同一页，同一张表就会有两条互相矛盾的声明 ⇒ 拒绝。
    seen: list[tuple[int, tuple[int, ...]]] = []
    for item in result:
        for index, pages in seen:
            if index != item.table_index:
                continue
            if not pages or not item.pages:
                # 至少有一条是"所有页" ⇒ 必然重叠。
                _fail("duplicate table_index")
            if set(pages) & set(item.pages):
                _fail("duplicate table_index")
        seen.append((item.table_index, item.pages))
    return result


# --------------------------------------------------------------------------- #
# 单元格取值（⛔ 只做"取值"，⛔ 不做"猜语义"）
# --------------------------------------------------------------------------- #

def _cell(value: object) -> str | None:
    """把一个表格单元格归一成文本；⛔ 空即 `None`，⛔ 不填充占位符。

    ⚠️ 结论（实测）：**合并单元格不会产生 `""`**。`find_tables()` 对没有内容的格子
    要么给出 `None`，要么给出一条横线渲染成的 `"-----"`（长度 > 0）。
    因此 profile 里只有两种写法有实际意义：**正常表头文字**，或 **`null`**（该格为空）。
    写成 `""` 永远匹配不上——那正是我们想要的：⛔ 不允许"填充式"的宽松匹配。
    """

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

def _geometry_grid(table: object, page: object) -> list[list[str | None]] | None:
    """按**库给出的行/列几何**重建表格网格；⛔ 不信任 `extract()` 的行序。

    ⚠️ 为什么必须自己重建（**实测缺陷**）：
    `table.extract()` 返回的行序**不是**页面上从上到下的顺序。实测一份
    4 行表格（表头 2 行 + 数据 2 行）时，`extract()` 把**最后一行放在最前面**，
    而依此写出的 `source_record = page:{n}!row:{i}` 也就**指错了行**——
    人工拿它去 PDF 里核对会对不上，可追溯性直接失效。

    ✅ 而 `table.rows[i].bbox` 的**顺序是对的**（实测：y0 递增 = 从上到下）。
    因此这里以行 bbox 为行、以 `table.header.cells` 给出的列 bbox 的中点为列，
    逐格 `page.get_text("text", clip=…)` 取文字。

    ⛔ 取值一律不推断：格子里没有文字就是 `None`。
    ⛔ 几何不可用时返回 `None`，由调用方 fail closed（⛔ 不"猜一个顺序"）。
    """

    rows = getattr(table, "rows", None)
    header = getattr(table, "header", None)
    if not rows or header is None or page is None:
        return None
    column_cells = getattr(header, "cells", None)
    if not column_cells:
        return None

    def bounds(cell: object) -> tuple[float, float, float, float] | None:
        if not isinstance(cell, Sequence) or len(cell) != 4:
            return None
        try:
            x0, y0, x1, y1 = (float(value) for value in cell)
        except (TypeError, ValueError):
            return None
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1, y1)

    column_boxes: list[tuple[float, float, float, float]] = []
    for cell in column_cells:
        box = bounds(cell)
        if box is None:
            return None
        column_boxes.append(box)

    grid: list[list[str | None]] = []
    for row in rows:
        row_box = bounds(getattr(row, "bbox", None))
        if row_box is None:
            return None
        _, row_top, _, row_bottom = row_box
        values: list[str | None] = []
        for (col_left, _, col_right, _) in column_boxes:
            # ⚠️ 横向用**整列**范围（列中点会把跨列文字切碎），
            #    纵向用**该行**的上下界 —— 这样既不会吃到相邻列的边，
            #    也不会吃到表格上下的正文（例如标题）。
            text = page.get_text("text", clip=(col_left, row_top, col_right, row_bottom))
            values.append(_cell(text))
        grid.append(values)
    return grid


def _table_rows(table: object, page: object = None) -> list[list[str | None]] | None:
    """取表格的二维文本网格（**按页面阅读顺序**）；无法确定时返回 `None`。"""

    grid = _geometry_grid(table, page)
    if grid is not None:
        return grid
    # 回退：库自己的输出顺序（⚠️ 顺序不可靠，但至少能解析；由结构 issue 提示）。
    extracted = getattr(table, "extract", None)
    if not callable(extracted):
        return None
    raw_rows = extracted()
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
        return None
    return [[_cell(value) for value in row] for row in raw_rows]


def _multi_row_header_columns(
    header_rows: Sequence[Sequence[str | None]], column_count: int,
) -> list[tuple[str, ...]]:
    """把 N 行表头**按列**折成 N 元组序列：`[(第1行, 第2行, …), …]`。

    ⚠️ 合并单元格在网格里表现为 `None`（实测：**不是** `""`）：
    双行表头中第一行的"学分"往往跨两列合并，第二行才是"必修/选修"。
    因此这里**逐列**取 N 行的文字，⛔ 不做任何"向上填充"，
    匹配仍然要求声明的候选**逐行完全相等**（`null` 表示该行为空）。
    """

    columns: list[tuple[str, ...]] = []
    for position in range(column_count):
        entry: list[str] = []
        for row in header_rows:
            text = ""
            if position < len(row):
                text = (row[position] or "").strip()
            entry.append(text)
        columns.append(tuple(entry))
    return columns


def _rows_from_table(
    table: object, profile: _TableProfile, page_number: int, *,
    issues: list[DocxImportIssue], page: object = None,
) -> list[DocxCourseRow]:
    """把一张已识别的表转成课程行；⛔ 任何不确定都产出行级 issue。"""

    normalized = _table_rows(table, page)
    if normalized is None:
        issues.append(DocxImportIssue("table_extraction_unavailable", profile.table_index, 0))
        return []
    if not normalized:
        issues.append(DocxImportIssue("empty_table", profile.table_index, 0))
        return []

    header_rows = profile.header_rows
    if len(normalized) < header_rows + 1:
        # 连表头都读不全：⛔ 不猜，直接报结构不匹配。
        issues.append(DocxImportIssue("table_header_mismatch", profile.table_index, 0))
        return []

    column_count = max((len(row) for row in normalized), default=0)
    folded = _multi_row_header_columns(normalized[:header_rows], column_count)
    # ⛔ 每个映射列都必须命中它声明的**某一种**精确写法（逐行比较）；
    #    否则整表拒绝（⛔ 不按位置硬套、⛔ 不做模糊匹配）。
    resolved: dict[str, int] = {}
    for key, candidates in profile.expected_headers:
        hit = next(
            (position for position, value in enumerate(folded) if value in candidates),
            None,
        )
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
    # ⚠️ 数据行从**表头之后**开始；行号相对**数据区第一行**计数，
    #    这样表头有几行都不会改变 `source_record` 的含义。
    for offset, values in enumerate(normalized[header_rows:], start=1):
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
            # ⛔ 唯一性：`source_record` 是 `CurriculumVersion` 的唯一性主键。
            #    一页上可能有多张表（真实培养方案第 6 页就有 4 张），
            #    因此必须带上**表序号**，否则不同表的第 1 行会撞成同一个定位。
            source_record=f"page:{page_number}!table:{profile.table_index}!row:{offset}",
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

def _open_document(data: bytes):
    """共用的结构校验 + 打开；⛔ 失败即固定文案、⛔ 不泄漏底层异常文本。"""

    if not isinstance(data, bytes):
        raise CurriculumNormalizationError("pdf import: expected bytes")
    if not data:
        raise CurriculumNormalizationError("pdf import: empty input")
    if len(data) > MAX_PDF_BYTES:
        raise CurriculumNormalizationError("pdf import: file is too large")
    # ⛔ magic 校验：PDF 头必须出现在**最前面**。
    if not data.startswith(_PDF_MAGIC):
        raise CurriculumNormalizationError("pdf import: not a PDF (missing %PDF- header)")

    try:
        import pymupdf
    except ImportError:  # pragma: no cover - 依赖缺失是部署问题，不是数据问题
        raise CurriculumNormalizationError(
            "pdf import: PDF support is unavailable in this environment"
        ) from None

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
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
    except Exception:
        document.close()
        raise
    return document


def inspect_curriculum_pdf(data: bytes) -> dict:
    """逐页**只读**检查：表格数量、列数、行数、**逐行表头原文**。

    ⛔ 不猜列位、⛔ 不解析课程、⛔ 不写文件。它唯一的用途是让人**照着**写 profile：
    `expected_headers` 必须与这里打印的表头文字**逐字相同**。

    ⛔ 扫描件与损坏文件在这里也 fail closed（与解析路径同一套校验）。
    """

    document = _open_document(data)
    try:
        pages: list[dict] = []
        for page_index in range(int(document.page_count)):
            page = document.load_page(page_index)
            text = page.get_text("text") or ""
            # ⚠️ 只调用一次 `find_tables()`（概率性识别；重复调用行号会失去可追溯性）。
            tables = list((page.find_tables().tables) or ())
            entries: list[dict] = []
            for order, table in enumerate(tables, start=1):
                rows = _table_rows(table, page) or []
                column_count = max((len(row) for row in rows), default=0)
                # 逐行原文表头（最多前 3 行）——profile 要照抄的就是它。
                header_rows = [row[:column_count] for row in rows[:3]]
                entries.append({
                    "table_index": order,
                    "column_count": column_count,
                    "data_row_count": max(0, len(rows) - 1),
                    "header_rows": header_rows,
                })
            pages.append({
                "page": page_index + 1,
                "text_chars": len(text.strip()),
                "table_count": len(tables),
                "tables": entries,
            })
        total_chars = sum(page["text_chars"] for page in pages)
        return {
            "page_count": len(pages),
            "total_text_chars": total_chars,
            "scanned_suspected": total_chars < MIN_TEXT_CHARS_PER_PAGE * max(1, len(pages)),
            "pages": pages,
        }
    finally:
        document.close()


def load_curriculum_pdf(
    data: bytes, *, source_id: str, tables: Sequence[Mapping[str, object]],
) -> DocxImportResult:
    """把 PDF 字节解析成 `DocxImportResult`（= 审核草稿的输入契约）。

    ⛔ 失败即 `CurriculumNormalizationError`（fail closed）；⛔ 从不返回"部分猜测"的结果。
    ⛔ 不写任何文件、⛔ 不联网、⛔ 不调用 OCR。
    """

    document = _open_document(data)
    page_count = int(document.page_count)
    profiles = _profiles(tables)

    try:
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
                # ⛔ 页限定：不在声明页上的表格**不声明**，因此不会被误解析。
                #    ⚠️ 注意这里**只跳过该条声明**，不能跳过 `find_tables()`
                #    ——曾因把 `continue` 放在识别之前，导致未声明页上的表格
                #    连"表头不匹配"都报不出来（静默丢失）。
                if profile.pages and page_number not in profile.pages:
                    continue
                if profile.table_index > len(tables_on_page):
                    issues.append(DocxImportIssue(
                        "table_not_found", profile.table_index, page_number,
                    ))
                    continue
                by_index.setdefault(profile.table_index, []).extend(
                    _rows_from_table(
                        tables_on_page[profile.table_index - 1], profile, page_number,
                        issues=issues, page=page,
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
