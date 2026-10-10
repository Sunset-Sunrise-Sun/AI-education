"""从培养方案 PDF 中提取**课程分类证据**，并生成**审核建议**（⛔ 不是批准结果）。

```text
PDF bytes + 已验收 profile
      │
      ├─ ① 课程明细表（table_purpose=course_detail）──► 课程行（沿用 pdf_reader）
      │
      ├─ ② 类别学分要求表（category_credit_requirement）──► 每个类别的最低学分原文
      │                                                      （⛔ 绝不求和成员学分）
      ├─ ③ 实践教学附表（practice_appendix）───────────► 课程编码 → 类别代号（课程级证据）
      └─ ④ 明细表小节标题行（section_header）──────────► 该行之后的课程属于哪个小节
      ▼
CategoryCandidate[]  ← 候选分类 + 逐条原文证据 + status
```

## ⛔ 本模块**不做**的事（逐条对应任务书 §三、§五）

| ⛔ 不做 | 由什么保证 |
| --- | --- |
| 把候选写成正式批准结果 | 本模块只产出 `CategoryCandidate`；⛔ 没有任何字段叫 `verified` / `approved` |
| 一对多 / 冲突时自动取舍 | `status=conflicting` ⇒ 候选为 `UNKNOWN`，**双方证据都保留** |
| 无证据时猜一个类别 | `status=no_evidence` ⇒ 候选为 `UNKNOWN` |
| 用成员学分求和凑组要求 | 最低学分**只**来自声明表里的原文数字；本模块不计算任何学分和 |
| 判定跨专业课程等价 | 本模块**完全不涉及**等价性；跨表关联只用于生成审核建议 |
| 把候选交给 Planner | 本模块⛔ 不 import `app.planner` / `matching.py`（有测试断言） |
| 在代码里写中文类别分支 | 归一化走 profile 的**声明式** `category_values`；未声明的代号 ⇒ `UNKNOWN` |

## 证据的三种来源（均已用真实文件核实存在）

| 来源 | 形态 | 给出什么 |
| --- | --- | --- |
| 类别学分要求表 | 6 列：`课程类别/课程细类` \\| `细类学分要求` \\| `类别学分要求` \\| … | 类别代号 + **最低学分原文** |
| 实践教学附表 | 8 列：`序号` \\| `课程编码` \\| … \\| `课程类别` \\| … | 课程编码 → 类别代号（**课程级**） |
| 小节标题行 | 明细表首列合并单元格，仅在小节首行有值 | 该小节内课程的**范围级**类别 |
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_reader import (
    DocxCourseRow,
    _cell,
    _open_document,
    _table_rows,
)
from app.curriculum.requirements import RequirementKind

__all__ = [
    "CategoryCandidate",
    "CategoryEvidence",
    "CategoryRequirement",
    "CourseClassificationReport",
    "build_classification_report",
    "extract_evidence",
]

#: 证据种类（⛔ 只用固定码，⛔ 不拼接自由文本）。
EVIDENCE_TABLE = "credit_requirement_table"
EVIDENCE_APPENDIX = "practice_appendix"
EVIDENCE_SECTION = "section_header"

#: 候选状态（⛔ 只用固定码）。
STATUS_SINGLE = "single_source"
STATUS_CONFLICTING = "conflicting"
STATUS_NO_EVIDENCE = "no_evidence"


@dataclass(frozen=True, slots=True)
class CategoryEvidence:
    """一条**原文**分类证据（⛔ 不含任何推断出来的描述性文字）。"""

    kind: str
    category_code: str | None
    requirement: RequirementKind
    source_record: str
    raw_text: str
    minimum_credit: float | None = None

    def to_payload(self) -> dict:
        return {
            "kind": self.kind,
            "category_code": self.category_code,
            "requirement": self.requirement.value,
            "source_record": self.source_record,
            "raw_text": self.raw_text,
            "minimum_credit": self.minimum_credit,
        }


@dataclass(frozen=True, slots=True)
class CategoryRequirement:
    """某个类别的**最低学分要求原文**（来自声明表，⛔ 不是成员学分求和）。"""

    category_code: str
    requirement: RequirementKind
    minimum_credit: float | None
    source_record: str
    raw_text: str

    def to_payload(self) -> dict:
        return {
            "category_code": self.category_code,
            "requirement": self.requirement.value,
            "minimum_credit": self.minimum_credit,
            "source_record": self.source_record,
            "raw_text": self.raw_text,
        }


@dataclass(frozen=True, slots=True)
class CategoryCandidate:
    """一门课的**候选**分类 + 证据（⛔ 不是批准结果）。"""

    course_id: str
    source_record: str
    proposed_requirement: RequirementKind
    proposed_category_code: str | None
    status: str
    evidence: tuple[CategoryEvidence, ...] = ()
    #: 是否已有**课程级**（精确匹配课程编码）的决定性证据。
    #: ⚠️ 只有小节级证据时为 `False`：小节是范围证据，⛔ 不等于该课程的编码级依据。
    evidence_complete: bool = False

    def to_payload(self) -> dict:
        return {
            "course_id": self.course_id,
            "source_record": self.source_record,
            "proposed_requirement": self.proposed_requirement.value,
            "proposed_category_code": self.proposed_category_code,
            "status": self.status,
            "evidence_complete": self.evidence_complete,
            "evidence": [item.to_payload() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class CourseClassificationReport:
    """一次分类证据提取的完整结果。"""

    candidates: tuple[CategoryCandidate, ...]
    category_requirements: tuple[CategoryRequirement, ...]
    #: 未能识别为课程的模块小节标题行（⛔ 不能当成课程）。
    section_rows: tuple[dict, ...] = ()
    #: 声明表里未出现过的类别代号 ⇒ 必须人工确认（⛔ 不猜成必修/选修）。
    unmapped_category_codes: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
    #: 分类证据声明里声明了、但在 PDF 里找不到（或表头不匹配）的表 ⇒ 如实报告。
    unmatched_evidence_tables: tuple[str, ...] = ()

    def statistics(self) -> dict:
        counts: dict[str, int] = {
            STATUS_SINGLE: 0, STATUS_CONFLICTING: 0, STATUS_NO_EVIDENCE: 0,
        }
        by_requirement = {kind.value: 0 for kind in RequirementKind}
        section_only = 0
        for item in self.candidates:
            counts[item.status] = counts.get(item.status, 0) + 1
            by_requirement[item.proposed_requirement.value] += 1
            if item.status == STATUS_SINGLE and not item.evidence_complete:
                section_only += 1
        return {
            "total_course_rows": len(self.candidates),
            "unique_course_ids": len({item.course_id for item in self.candidates}),
            "by_status": counts,
            "by_requirement": by_requirement,
            "section_only_candidates": section_only,
            "category_requirements": len(self.category_requirements),
            "section_rows": len(self.section_rows),
            "unmapped_category_codes": list(self.unmapped_category_codes),
            "with_evidence": counts.get(STATUS_SINGLE, 0) + counts.get(STATUS_CONFLICTING, 0),
            "without_evidence": counts.get(STATUS_NO_EVIDENCE, 0),
        }


# --------------------------------------------------------------------------- #
# profile 扩展：表用途与类别映射
# --------------------------------------------------------------------------- #

#: 表用途（⛔ 只有这些取值）。
PURPOSE_COURSE_DETAIL = "course_detail"
PURPOSE_CATEGORY_REQUIREMENT = "category_credit_requirement"
PURPOSE_PRACTICE_APPENDIX = "practice_appendix"

_TABLE_PURPOSES = frozenset({
    PURPOSE_COURSE_DETAIL, PURPOSE_CATEGORY_REQUIREMENT, PURPOSE_PRACTICE_APPENDIX,
})

#: `category_values` 里允许的归一化目标（⛔ 不允许写 `unknown`：那是"没映射上"）。
_CATEGORY_TARGETS = {RequirementKind.REQUIRED, RequirementKind.ELECTIVE}


def _category_mapping(raw: object) -> dict[str, RequirementKind]:
    """把 profile 的 `category_values` 声明解析成映射；⛔ 非法声明即拒绝。"""

    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise CurriculumNormalizationError(
            "pdf category evidence: category_values must be a mapping"
        )
    mapping: dict[str, RequirementKind] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise CurriculumNormalizationError(
                "pdf category evidence: category code must be non-empty text"
            )
        try:
            target = RequirementKind(value)
        except ValueError:
            raise CurriculumNormalizationError(
                "pdf category evidence: unsupported category mapping target"
            ) from None
        if target not in _CATEGORY_TARGETS:
            raise CurriculumNormalizationError(
                "pdf category evidence: category mapping must resolve to required or elective"
            )
        mapping[key.strip()] = target
    return mapping


def _number(raw: object) -> float | None:
    """只解析**纯数字**；⛔ 不解析 `247.0+2周` 这类复合值（那是学时汇总，不是学分）。"""

    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _spec_purpose(spec: Mapping[str, object], label: str) -> str:
    purpose = spec.get("table_purpose", PURPOSE_COURSE_DETAIL)
    if purpose not in _TABLE_PURPOSES:
        raise CurriculumNormalizationError(
            f"pdf category evidence: unsupported table_purpose for {label}"
        )
    return str(purpose)


# --------------------------------------------------------------------------- #
# 证据提取
# --------------------------------------------------------------------------- #

def extract_evidence(
    data: bytes, *, tables: Sequence[Mapping[str, object]],
) -> tuple[tuple[CategoryRequirement, ...], dict[str, tuple[CategoryEvidence, ...]], tuple[dict, ...], tuple[str, ...]]:
    """从 PDF 中提取类别要求、课程级类别证据、小节标题行与未映射代号。

    返回 `(类别要求, {课程编码: 证据}, 小节标题行, 未映射代号)`。
    ⛔ 只读：不写文件、⛔ 不产出课程行、⛔ 不做任何等价性判断。
    """

    if not isinstance(data, bytes) or not data:
        raise CurriculumNormalizationError("pdf category evidence: expected non-empty bytes")
    if isinstance(tables, (str, bytes, bytearray)) or not isinstance(tables, Sequence):
        raise CurriculumNormalizationError("pdf category evidence: expected table declarations")

    category_values = _category_mapping(_profile_category_values(tables))

    document = _open_document(data)
    try:
        requirements: list[CategoryRequirement] = []
        by_code: dict[str, list[CategoryEvidence]] = {}
        sections: list[dict] = []
        unmapped: set[str] = set()

        page_count = int(document.page_count)
        for page_index in range(page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            tables_on_page = list((page.find_tables().tables) or ())

            for spec in tables:
                purpose = _spec_purpose(spec, "declaration")
                pages = spec.get("pages") or []
                if pages and page_number not in pages:
                    continue
                table_index = spec.get("table_index")
                if not isinstance(table_index, int) or table_index < 1:
                    raise CurriculumNormalizationError(
                        "pdf category evidence: table_index must be a positive integer"
                    )
                if table_index > len(tables_on_page):
                    continue
                grid = _table_rows(tables_on_page[table_index - 1], page) or []
                if not grid:
                    continue

                if purpose == PURPOSE_CATEGORY_REQUIREMENT:
                    requirements.extend(
                        _read_category_requirements(
                            grid, spec, page_number, category_values, unmapped,
                        )
                    )
                elif purpose == PURPOSE_PRACTICE_APPENDIX:
                    _read_appendix(
                        grid, spec, page_number, category_values, by_code, unmapped,
                    )
                elif purpose == PURPOSE_COURSE_DETAIL:
                    sections.extend(_read_section_rows(grid, spec, page_number))

        frozen: dict[str, tuple[CategoryEvidence, ...]] = {
            code: tuple(items) for code, items in by_code.items()
        }
        return tuple(requirements), frozen, tuple(sections), tuple(sorted(unmapped))
    finally:
        document.close()


def _profile_category_values(tables: Sequence[Mapping[str, object]]) -> Mapping:
    """从表声明里取 `category_values`。

    ⚠️ 允许两种放置方式：每条声明各带一份，或在**任意一条**声明上给一次。
    ⛔ 多处给出**不同**映射即拒绝（避免"哪一份生效"变成隐式规则）。
    """

    found: Mapping | None = None
    for spec in tables:
        if not isinstance(spec, Mapping):
            raise CurriculumNormalizationError(
                "pdf category evidence: each declaration must be a mapping"
            )
        raw = spec.get("category_values")
        if raw is None:
            continue
        if found is not None and raw != found:
            raise CurriculumNormalizationError(
                "pdf category evidence: conflicting category_values declarations"
            )
        found = raw
    return found if found is not None else {}


def _require_columns(spec: Mapping[str, object], purpose: str) -> Mapping:
    columns = spec.get("columns")
    if not isinstance(columns, Mapping) or not columns:
        raise CurriculumNormalizationError(
            f"pdf category evidence: {purpose} table requires explicit columns"
        )
    return columns


def _require_headers(spec: Mapping[str, object], purpose: str) -> Mapping:
    headers = spec.get("expected_headers")
    if not isinstance(headers, Mapping) or set(headers) != set(
        _require_columns(spec, purpose)
    ):
        raise CurriculumNormalizationError(
            f"pdf category evidence: {purpose} table requires expected_headers "
            "covering exactly its mapped columns"
        )
    return headers


def _at(row: Sequence[str | None], position: int) -> str | None:
    """取第 `position` 列（**1 起**，与 profile 声明一致；grid 是 0 起）。

    ⚠️ 声明里的列号一律 1 起。这里集中做一次换算，
    ⛔ 不允许各读取函数各自 `row[position]`（实测因此整体错位一列，
    把开课学期当成了课程类别）。
    """

    index = position - 1
    if index < 0 or index >= len(row):
        return None
    return _cell(row[index])


def _require_position(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CurriculumNormalizationError(
            f"pdf category evidence: {label} must be a positive column index"
        )
    return value


def _header_candidates(
    entry: object, label: str, *, header_rows: int,
) -> tuple[tuple[str, ...], ...]:
    """把声明的表头候选归一成 `((逐行文字), …)`。

    ⚠️ **列表的含义取决于表头行数**（与 `pdf_reader` 的既有语义一致）：

    | 表头行数 | 写法 | 含义 |
    | --- | --- | --- |
    | 1 | `"序号"` | 一个写法 |
    | 1 | `["A", "B"]` | **两个**写法（⛔ 不是"同一写法的两段文字"） |
    | 2 | `[["A1","A2"], ["B1","B2"]]` | 两个写法，每个写法 2 行文字 |

    实测教训：把单行表头的 `["A", "B"]` 当成"一个两行写法"，
    会让这两个写法都永远比不上（表格只取第 0 行时读到的是 `A`）。
    """

    if isinstance(entry, str):
        return ((entry.strip(),),)
    if isinstance(entry, (bytes, bytearray)) or not isinstance(entry, Sequence):
        raise CurriculumNormalizationError(
            f"pdf category evidence: {label} must be text or a list of candidates"
        )
    items = list(entry)
    if not items:
        raise CurriculumNormalizationError(
            f"pdf category evidence: {label} needs at least one candidate"
        )

    def row_of(value: object) -> tuple[str, ...]:
        """把一个写法归一成"逐行文字"元组。"""

        if isinstance(value, str):
            return (value.strip(),)
        if isinstance(value, (bytes, bytearray)) or not isinstance(value, Sequence):
            raise CurriculumNormalizationError(
                f"pdf category evidence: {label} must contain text or lists of text"
            )
        parts = list(value)
        texts: list[str] = []
        for part in parts:
            if part is None:
                texts.append("")
            elif isinstance(part, str):
                texts.append(part.strip())
            else:
                raise CurriculumNormalizationError(
                    f"pdf category evidence: {label} header text must be a string or null"
                )
        return tuple(texts)

    if header_rows == 1:
        # 单行表头：列表里的**每一项**都是一个独立写法
        candidates = tuple(row_of(item) for item in items)
    else:
        # 多行表头：列表里的每一项是一个"逐行文字"序列；也允许外层直接给单个写法
        if all(isinstance(item, str) for item in items):
            # 形如 ["A", "B"] 在多行语义下 = 一个写法的两行文字
            candidates = (row_of(items),)
        else:
            candidates = tuple(row_of(item) for item in items)

    for candidate in candidates:
        if len(candidate) != header_rows:
            raise CurriculumNormalizationError(
                f"pdf category evidence: {label} candidate must give exactly "
                f"{header_rows} header row(s)"
            )
    if len(set(candidates)) != len(candidates):
        raise CurriculumNormalizationError(
            f"pdf category evidence: {label} has duplicate candidates"
        )
    return candidates


def _header_matches(grid: Sequence[Sequence[str | None]], spec: Mapping, purpose: str) -> bool:
    """表头**逐行精确匹配**；⛔ 不匹配即不使用该表（fail closed，⛔ 不猜列位）。

    ⚠️ 与 `pdf_reader._spec_header_shape` 同一套语义：
    逐行比较、逐列比较，⛔ 不做模糊匹配（唯一规范化是首尾空白 `strip()`）。
    """

    columns = _require_columns(spec, purpose)
    headers = _require_headers(spec, purpose)
    header_rows = int(spec.get("header_rows", 1))
    if len(grid) < header_rows:
        return False

    def cell_at(row: Sequence[str | None], position: int) -> str:
        """取第 `position` 列（**1 起**，与 profile 声明一致；grid 是 0 起）。"""

        index = position - 1
        if index < 0 or index >= len(row):
            return ""
        return (row[index] or "").strip()

    # 列号 → 字段名（按**物理列序**比对整行表头）
    field_by_position = {int(position): key for key, position in columns.items()}
    for row_index in range(header_rows):
        for position in sorted(field_by_position):
            key = field_by_position[position]
            candidates = _header_candidates(
                headers[key], f"expected_headers.{key}", header_rows=header_rows,
            )
            if not any(
                cell_at(grid[row_index], position)
                == (candidate[row_index] if row_index < len(candidate) else "")
                for candidate in candidates
            ):
                return False
    return True


def _read_category_requirements(
    grid, spec, page_number: int, category_values: Mapping[str, RequirementKind],
    unmapped: set[str],
) -> list[CategoryRequirement]:
    """读"类别学分要求表"：类别代号 + **最低学分原文**。"""

    purpose = PURPOSE_CATEGORY_REQUIREMENT
    if not _header_matches(grid, spec, purpose):
        return []
    columns = _require_columns(spec, purpose)
    header_rows = int(spec.get("header_rows", 1))
    code_pos = _require_position(columns["category_code"], "category_code")
    credit_pos = _require_position(columns["minimum_credit"], "minimum_credit")

    results: list[CategoryRequirement] = []
    for offset, row in enumerate(grid[header_rows:], start=1):
        code = _at(row, code_pos)
        credit_raw = _at(row, credit_pos)
        if not code:
            continue
        requirement = category_values.get(code)
        if requirement is None:
            unmapped.add(code)
            continue
        results.append(CategoryRequirement(
            category_code=code,
            requirement=requirement,
            minimum_credit=_number(credit_raw),
            source_record=f"page:{page_number}!table:{int(spec['table_index'])}!row:{offset}",
            raw_text=" | ".join(
                str(value) for value in (code, credit_raw) if value is not None
            ),
        ))
    return results


def _read_appendix(
    grid, spec, page_number: int, category_values: Mapping[str, RequirementKind],
    by_code: dict[str, list[CategoryEvidence]], unmapped: set[str],
) -> None:
    """读"实践教学附表"：**课程编码 → 类别代号**（课程级证据）。"""

    purpose = PURPOSE_PRACTICE_APPENDIX
    if not _header_matches(grid, spec, purpose):
        return
    columns = _require_columns(spec, purpose)
    header_rows = int(spec.get("header_rows", 1))
    code_pos = _require_position(columns["course_id"], "course_id")
    category_pos = _require_position(columns["category"], "category")

    for offset, row in enumerate(grid[header_rows:], start=1):
        code = _at(row, code_pos)
        category = _at(row, category_pos)
        if not code or not category:
            continue
        requirement = category_values.get(category)
        if requirement is None:
            unmapped.add(category)
            continue
        evidence = CategoryEvidence(
            kind=EVIDENCE_APPENDIX,
            category_code=category,
            requirement=requirement,
            source_record=f"page:{page_number}!table:{int(spec['table_index'])}!row:{offset}",
            raw_text=" | ".join((str(code), str(category))),
        )
        by_code.setdefault(str(code), []).append(evidence)


def _spec_section_columns(spec: Mapping[str, object]) -> tuple[int, ...]:
    """读取声明里"小节标题行所在的列"（**1 起**）。⛔ 未声明即空元组（不识别小节行）。"""

    raw = spec.get("section_columns")
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence):
        raise CurriculumNormalizationError(
            "pdf category evidence: section_columns must be a list of column indices"
        )
    values: list[int] = []
    for item in raw:
        values.append(_require_position(item, "section_columns"))
    if len(set(values)) != len(values):
        raise CurriculumNormalizationError(
            "pdf category evidence: duplicate section_columns entry"
        )
    return tuple(values)


def _read_section_rows(grid, spec, page_number: int) -> list[dict]:
    """识别明细表里的**模块小节标题行**（⛔ 它们不是课程）。

    判据（⛔ 不是"猜"）：该行的课程编码格为空，但**小节列**有文字。
    小节列由 profile 的 `section_columns` 显式声明。
    """

    columns = spec.get("columns")
    if not isinstance(columns, Mapping) or "course_id" not in columns:
        return []
    section_columns = _spec_section_columns(spec)
    header_rows = int(spec.get("header_rows", 1))
    code_pos = _require_position(columns["course_id"], "course_id")

    results: list[dict] = []
    for offset, row in enumerate(grid[header_rows:], start=1):
        code = _at(row, code_pos)
        if code:
            # 有课程编码 ⇒ 是课程行，⛔ 不是小节标题行
            continue
        labels = []
        for position in section_columns:
            text = _at(row, position)
            if text:
                labels.append(text)
        # ⚠️ 判据只看"没有课程编码"：实测 `专业提升课` 那一行在序号列**有**文字，
        #    因此⛔ 不能要求"其余列全空"，否则会漏掉它。
        if labels:
            results.append({
                "source_record": (
                    f"page:{page_number}!table:{int(spec['table_index'])}!row:{offset}"
                ),
                "raw_text": " / ".join(labels),
                "labels": list(labels),
            })
    return results


# --------------------------------------------------------------------------- #
# 候选分类（本模块的判定核心）
# --------------------------------------------------------------------------- #

def build_classification_report(
    rows: Sequence[DocxCourseRow],
    *,
    category_requirements: Sequence[CategoryRequirement],
    appendix_evidence: Mapping[str, Sequence[CategoryEvidence]],
    sections: Sequence[Mapping[str, object]],
    category_values: Mapping[str, RequirementKind],
    unmapped_category_codes: Sequence[str] = (),
    unmatched_evidence_tables: Sequence[str] = (),
) -> CourseClassificationReport:
    """把课程行 + 三类证据合成**候选分类**（⛔ 不是批准结果）。

    判定规则见模块 docstring；核心是：**冲突与无证据一律不猜**。

    ⚠️ 小节归属按 **(表, 行号) 顺序**推导：对每张表，先按行号顺序排好"小节标题行"，
    再让每一门课取**同一张表里、位于它之前最近**的那个小节。
    ⛔ 不做任何子串匹配（如 `"选修" in title`），小节文字必须先命中声明映射。
    """

    # 小节标题行：按 (表定位, 行号) 建立有序索引
    def _split(source_record: str) -> tuple[str, int]:
        """把 `page:N!table:T!row:R` 拆成 (表定位, 行号)。"""

        parts = source_record.split("!")
        if len(parts) != 3 or not parts[2].startswith("row:"):
            return (source_record, 0)
        try:
            return ("!".join(parts[:2]), int(parts[2].split(":", 1)[1]))
        except ValueError:
            return (source_record, 0)

    section_labels_by_table: dict[str, list[tuple[int, str]]] = {}
    for row in sections:
        record = str(row.get("source_record", ""))
        table_key, row_number = _split(record)
        for label in row.get("labels", ()):  # type: ignore[union-attr]
            section_labels_by_table.setdefault(table_key, []).append(
                (row_number, str(label))
            )
    for items in section_labels_by_table.values():
        items.sort()

    def section_for(source_record: str) -> tuple[str | None, str | None]:
        """返回该课程行所属的 (小节原文, 类别)。

        ⛔ 小节文字必须在 `category_values` 里有声明，否则视为**没有**类别含义
        （仍然记录原文，但不据此推断类别）。
        """

        table_key, row_number = _split(source_record)
        chosen: str | None = None
        for section_row_number, label in section_labels_by_table.get(table_key, ()):
            if section_row_number < row_number:
                chosen = label
            else:
                break
        if chosen is None:
            return (None, None)
        requirement = category_values.get(chosen)
        return (chosen, requirement.value if requirement is not None else None)

    candidates: list[CategoryCandidate] = []
    for row in rows:
        if row.course_id is None:
            continue
        code = row.course_id
        appendix = tuple(appendix_evidence.get(code, ()))
        section_text, section_value = section_for(row.source_record)
        section_requirement: RequirementKind | None = (
            RequirementKind(section_value) if section_value is not None else None
        )

        evidence: list[CategoryEvidence] = list(appendix)
        if section_text is not None:
            evidence.append(CategoryEvidence(
                kind=EVIDENCE_SECTION,
                category_code=None,
                requirement=(
                    section_requirement
                    if section_requirement is not None else RequirementKind.UNKNOWN
                ),
                source_record=row.source_record,
                raw_text=section_text,
            ))

        appendix_kinds = {item.requirement for item in appendix}
        if len(appendix_kinds) > 1:
            # ② 同一编码在附表里出现 ≥2 种类别 ⇒ 冲突，⛔ 不取舍。
            candidates.append(CategoryCandidate(
                course_id=code,
                source_record=row.source_record,
                proposed_requirement=RequirementKind.UNKNOWN,
                proposed_category_code=None,
                status=STATUS_CONFLICTING,
                evidence=tuple(evidence),
                evidence_complete=False,
            ))
            continue

        if appendix_kinds:
            appendix_kind = next(iter(appendix_kinds))
            if section_requirement is not None and section_requirement != appendix_kind:
                # ③ 课程级与小节级不一致 ⇒ 冲突，⛔ 不取舍。
                candidates.append(CategoryCandidate(
                    course_id=code,
                    source_record=row.source_record,
                    proposed_requirement=RequirementKind.UNKNOWN,
                    proposed_category_code=None,
                    status=STATUS_CONFLICTING,
                    evidence=tuple(evidence),
                    evidence_complete=False,
                ))
                continue
            # ① 课程级唯一命中（且与小节不冲突）⇒ 候选成立。
            codes = {item.category_code for item in appendix if item.category_code}
            candidates.append(CategoryCandidate(
                course_id=code,
                source_record=row.source_record,
                proposed_requirement=appendix_kind,
                proposed_category_code=next(iter(codes)) if len(codes) == 1 else None,
                status=STATUS_SINGLE,
                evidence=tuple(evidence),
                evidence_complete=True,
            ))
            continue

        if section_requirement is not None:
            # ④ 只有小节级证据 ⇒ 候选成立，但 evidence_complete=False。
            candidates.append(CategoryCandidate(
                course_id=code,
                source_record=row.source_record,
                proposed_requirement=section_requirement,
                proposed_category_code=None,
                status=STATUS_SINGLE,
                evidence=tuple(evidence),
                evidence_complete=False,
            ))
            continue

        # ⑤ 无任何证据 ⇒ UNKNOWN，如实记录。
        candidates.append(CategoryCandidate(
            course_id=code,
            source_record=row.source_record,
            proposed_requirement=RequirementKind.UNKNOWN,
            proposed_category_code=None,
            status=STATUS_NO_EVIDENCE,
            evidence=(),
            evidence_complete=False,
        ))

    return CourseClassificationReport(
        candidates=tuple(candidates),
        category_requirements=tuple(category_requirements),
        section_rows=tuple(dict(item) for item in sections),
        unmapped_category_codes=tuple(unmapped_category_codes),
        unmatched_evidence_tables=tuple(unmatched_evidence_tables),
        notes=(
            "候选分类只是**审核建议**，⛔ 不是学校认定，也⛔ 不是批准结果。",
            "跨表关联只用于生成建议，⛔ 不代表学校已认定课程等价或学分。",
            "课程组最低学分只取自文档原文，⛔ 绝不用成员学分求和。",
        ),
    )
