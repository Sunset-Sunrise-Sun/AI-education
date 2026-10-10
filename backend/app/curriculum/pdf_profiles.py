"""**经过真实文件验收的培养方案 profile 注册表**（CLI 与 HTTP 共用的唯一来源）。

```text
                  ┌──────────────────────────────┐
   PDF bytes ────► │ app/curriculum/pdf_profiles  │ ◄──── CLI  --document-type
                  │  · 已验收 profile（照抄真实表头）│
                  │  · 按**内容结构**判定文档类型    │
                  └──────────────────────────────┘
                                │
                    profile 列表 └──► pdf_reader.load_curriculum_pdf()
```

## 为什么要有这个模块（第 3 轮架构审核提出的集成缺口）

CLI 的真实 profile 原先只存在于验收目录，HTTP 端点却还用 `_install_pdf_tables()` 里
那份**旧的、猜出来的**默认声明 —— 两套规则必然漂移。现在**只有一个来源**：本模块。
`tools/parse_curriculum_pdf.py` 与 `api/curriculum_import.py` 都从这里取。

## ⛔ 文档类型判定**只依赖内容结构**

`detect_document_type()` 完全不看专业名、文件名、角色、Content-Type：
它把每个已验收类型的"每页每表的**完整表头文字**"与 PDF 实测表头逐格比对，
要求**声明的每一张表都命中**（完全覆盖），命中的类型必须**唯一**；
0 个或 ≥2 个都 fail closed。

调用方给出的类型只是**断言**：`verify_document_type()` 会与内容判定结果对照，
**不一致即拒绝**。因此⛔ 不可能"仅凭用户输入的专业名/文件名/角色"决定数据真实性。

## ⚠️ 这些声明是**照抄真实表头**得到的，⛔ 不是猜的

每一项 `expected_headers` 都来自 `tools/parse_curriculum_pdf.py --inspect` 的输出；
合并单元格在第 2 行是 `null`（⛔ 不是 `""`），跨两列合并的单元格（如"学时"）
两半都要声明。两份文件形态相似但**分布不同**：
遥感第 5 页第 1 张是 5 列汇总表，网络空间安全第 5 页第 1 张是 10 列课程表。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_reader import inspect_curriculum_pdf, load_curriculum_pdf

__all__ = [
    "DOCUMENT_TYPES",
    "DocumentType",
    "detect_document_type",
    "fingerprint_sha256",
    "list_document_types",
    "load_curriculum_pdf_verified",
    "profile_for",
    "verify_document_type",
]


# --------------------------------------------------------------------------- #
# 表头声明（覆盖**整张表的全部列**，照抄真实表头）
# --------------------------------------------------------------------------- #
#
# ⚠️ 覆盖全部列而不是只覆盖取值列，有两个原因：
#   ① 更安全：声明越完整，"表头是否真的匹配"就越严格；
#   ② 文档类型判定需要**整行表头**才能与实测表头逐格比对（见 `_spec_header_shape`）。

#: 9 列课程明细表。
_DETAIL_9COL_HEADERS = {
    "course_category": [["课程类别", "课程细类"]],
    "course_module": [[None, "课程模块"]],
    "sequence": [["序号", None]],
    "course_id": [["课程编码", None]],
    "course_name": [["课程名称/英文名称", None]],
    "credit": [["总学分", None]],
    # 「学时」跨两列合并：左半格第 1 行是"学时"，右半格第 1 行为空。
    "theory_hours": [["学时", "理论学时"]],
    "practice_hours": [[None, "实践（含实验）"]],
    "recommended_term_text": [["开课学期", None]],
}

#: 10 列课程明细表（比 9 列多一列"是否基础课程权重制课程"）。
_DETAIL_10COL_HEADERS = {
    **_DETAIL_9COL_HEADERS,
    "weighted_course": [["是否基础课程权重制课程", None]],
}

#: 8 列课程明细表（没有"课程类别/课程模块"，第 1 列是"课程细类"）。
_DETAIL_8COL_HEADERS = {
    "course_category": [["课程细类", None]],
    "sequence": [["序号", None]],
    "course_id": [["课程编码", None]],
    "course_name": [["课程名称/英文名称", None]],
    "credit": [["总学分", None]],
    "theory_hours": [["学时", "理论学时"]],
    "practice_hours": [[None, "实践（含实验）"]],
    "recommended_term_text": [["开课学期", None]],
}

#: `columns` 给出**每一列的物理列号**（1 起）。
#: ⚠️ 取值只读 `sequence / course_id / course_name / credit / recommended_term_text`；
#:    其余列（类别、模块、学时、权重制）**只参与表头精确校验**。
_COLUMNS_9COL = {
    "course_category": 1,
    "course_module": 2,
    "sequence": 3,
    "course_id": 4,
    "course_name": 5,
    "credit": 6,
    "theory_hours": 7,
    "practice_hours": 8,
    "recommended_term_text": 9,
}

_COLUMNS_10COL = {**_COLUMNS_9COL, "weighted_course": 10}

_COLUMNS_8COL = {
    "course_category": 1,
    "sequence": 2,
    "course_id": 3,
    "course_name": 4,
    "credit": 5,
    "theory_hours": 6,
    "practice_hours": 7,
    "recommended_term_text": 8,
}


def _declaration(
    *, table_index: int, pages: list[int], headers: dict, columns: dict,
) -> dict:
    return {
        "mode": "tables",
        "table_index": table_index,
        "pages": pages,
        "header_rows": 2,
        "columns": columns,
        "expected_headers": headers,
    }


# --------------------------------------------------------------------------- #
# 文档类型定义
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class DocumentType:
    """一个**已验收**的培养方案文档类型。"""

    key: str
    major: str
    cohort: str
    #: 人类可读说明（会返回给前端展示）。
    label: str
    #: 已验收文件的 SHA-256（**仅用于自检与审计**，⛔ 不参与类型判定）。
    verified_sha256: str
    #: 已验收文件实测页数。
    verified_pages: int
    #: 表格声明（照抄真实表头）。
    tables: tuple[Mapping[str, object], ...]

    def to_public_dict(self) -> dict:
        """给前端的**安全摘要**（⛔ 不含任何列位映射）。"""

        return {
            "key": self.key,
            "major": self.major,
            "cohort": self.cohort,
            "label": self.label,
            "verified_pages": self.verified_pages,
            "declared_tables": len(self.tables),
        }


#: ⚠️ 只有**经过真实文件验收**的文档类型才会出现在这里。
#: ⛔ 不要为了"支持更多专业"往这里加没有验收过的条目。
DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType(
        key="yuangan-2025",
        major="遥感科学与技术",
        cohort="2025",
        label="遥感科学与技术 2025级 培养方案（8 页，已验收）",
        verified_sha256=(
            "deed8a61cdb73ed03566c199ff506bd1c95e5a500b6929127cfbddea6931e35f"
        ),
        verified_pages=8,
        tables=(
            # 第 2、3 页第 1 张：9 列
            _declaration(
                table_index=1, pages=[2, 3],
                headers=_DETAIL_9COL_HEADERS, columns=_COLUMNS_9COL,
            ),
            # 第 3 页第 3 张：10 列
            _declaration(
                table_index=3, pages=[3],
                headers=_DETAIL_10COL_HEADERS, columns=_COLUMNS_10COL,
            ),
            # 第 4 页第 1 张：10 列
            _declaration(
                table_index=1, pages=[4],
                headers=_DETAIL_10COL_HEADERS, columns=_COLUMNS_10COL,
            ),
            # 第 5 页第 2 张：8 列
            _declaration(
                table_index=2, pages=[5],
                headers=_DETAIL_8COL_HEADERS, columns=_COLUMNS_8COL,
            ),
            # 第 6 页第 1、3 张：8 列
            _declaration(
                table_index=1, pages=[6],
                headers=_DETAIL_8COL_HEADERS, columns=_COLUMNS_8COL,
            ),
            _declaration(
                table_index=3, pages=[6],
                headers=_DETAIL_8COL_HEADERS, columns=_COLUMNS_8COL,
            ),
        ),
    ),
    DocumentType(
        key="netsec-2025",
        major="网络空间安全",
        cohort="2025",
        label="网络空间安全 2025级 培养方案（9 页，已验收）",
        verified_sha256=(
            "17773b2583fa20e25761ed95435144b59b1b8229eb55b1370bf4cb3e676457d2"
        ),
        verified_pages=9,
        tables=(
            _declaration(
                table_index=1, pages=[2, 3],
                headers=_DETAIL_9COL_HEADERS, columns=_COLUMNS_9COL,
            ),
            _declaration(
                table_index=3, pages=[3],
                headers=_DETAIL_10COL_HEADERS, columns=_COLUMNS_10COL,
            ),
            # ⚠️ 与遥感**不同**：网络空间安全第 4、5 页第 1 张都是 10 列课程表
            #    （遥感第 5 页第 1 张是 5 列学分汇总表）。
            _declaration(
                table_index=1, pages=[4, 5],
                headers=_DETAIL_10COL_HEADERS, columns=_COLUMNS_10COL,
            ),
            _declaration(
                table_index=3, pages=[5],
                headers=_DETAIL_8COL_HEADERS, columns=_COLUMNS_8COL,
            ),
            _declaration(
                table_index=1, pages=[6],
                headers=_DETAIL_8COL_HEADERS, columns=_COLUMNS_8COL,
            ),
        ),
    ),
)

_BY_KEY: dict[str, DocumentType] = {item.key: item for item in DOCUMENT_TYPES}


def list_document_types() -> tuple[dict, ...]:
    """给前端的**受支持文档类型**清单（⛔ 不含任何列位映射）。"""

    return tuple(item.to_public_dict() for item in DOCUMENT_TYPES)


def profile_for(key: object) -> DocumentType:
    """按 `key` 取已验收文档类型；⛔ 未知 key / 非字符串即拒绝。"""

    if not isinstance(key, str) or not key.strip():
        raise CurriculumNormalizationError("pdf profile: document type is required")
    item = _BY_KEY.get(key.strip())
    if item is None:
        raise CurriculumNormalizationError("pdf profile: unknown document type")
    return item


# --------------------------------------------------------------------------- #
# 结构指纹与类型判定
# --------------------------------------------------------------------------- #

def _spec_header_shape(spec: Mapping[str, object]) -> tuple[str, ...]:
    """把一条声明折成"**按物理列序**排列的整行表头元组"，与实测表头逐格比对。

    ⚠️ 三条硬要求（前两条本轮实测都踩过）：
    ① 必须按**物理列号**排序（`columns` 的列号就是列位置）；按字典顺序排永远比不上；
    ② 必须包含**整张表的所有列** —— 否则两侧长度不同
       （实测：声明侧 18 格 vs 实测侧 20 格），指纹永远命中不了；
    ③ `expected_headers` 的每个键都必须出现在 `columns` 里（哪怕取值用不到）——
       "键名 → 列号"推不出来，只能由人声明。
       ⛔ 这是声明式的代价，也正是它的价值：列位永远有明确来源。
    """

    columns = spec["columns"]
    expected = spec["expected_headers"]
    header_rows = int(spec["header_rows"])
    missing = set(expected) - set(columns)  # type: ignore[arg-type]
    if missing:
        raise CurriculumNormalizationError(
            "pdf profile: every expected header must also declare its column index"
        )
    field_by_position = {
        int(position): key for key, position in columns.items()  # type: ignore[union-attr]
    }
    flattened: list[str] = []
    for row_index in range(header_rows):
        for position in sorted(field_by_position):
            key = field_by_position[position]
            candidates = expected[key]  # type: ignore[index]
            # 每个字段可以有多种写法；结构比对只认**第一种**（主写法）。
            candidate = candidates[0]
            text = candidate[row_index] if row_index < len(candidate) else ""
            flattened.append("" if text is None else str(text))
    return tuple(flattened)


def _fingerprint(
    document: DocumentType,
) -> frozenset[tuple[int, int, int, tuple[str, ...]]]:
    """结构指纹：`{(页号, table_index, header_rows, 整行表头文字)}`。

    ⛔ 不含专业名 / 文件名 —— 只看"**哪一页上的第几张表，表头写着什么字**"。

    ⚠️ 为什么必须带页号：两份已验收文件的**表头文字高度重合**
    （同样的 9 列 / 10 列 / 8 列课程表），只凭"表长什么样"区分不开。
    差异在**分布**上：遥感第 5 页第 1 张是 5 列汇总表、网络空间安全是 10 列课程表。
    """

    marks: set[tuple[int, int, int, tuple[str, ...]]] = set()
    for spec in document.tables:
        shape = _spec_header_shape(spec)
        for page in spec.get("pages", []):  # type: ignore[union-attr]
            marks.add((int(page), int(spec["table_index"]), int(spec["header_rows"]), shape))
    return frozenset(marks)


def fingerprint_sha256(document: DocumentType) -> str:
    """结构指纹摘要（审计用；⛔ 与文件内容无关）。"""

    payload = "|".join(
        f"{page}:{index}:{rows}:{','.join(text)}"
        for page, index, rows, text in sorted(_fingerprint(document))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _observed_marks(report: Mapping[str, object]) -> set[tuple[int, int, int, tuple[str, ...]]]:
    """把结构检查报告折成与 `_fingerprint` 同构的集合。"""

    marks: set[tuple[int, int, int, tuple[str, ...]]] = set()
    for page in report["pages"]:  # type: ignore[index]
        for table in page["tables"]:
            header_rows = table["header_rows"]
            if len(header_rows) < 2:
                continue
            flattened = tuple(
                "" if value is None else value
                for row in header_rows[:2]
                for value in row
            )
            marks.add((page["page"], table["table_index"], 2, flattened))
    return marks


def detect_document_type(data: bytes) -> tuple[str, dict]:
    """按**内容结构**判定文档类型；⛔ 命中不唯一即 fail closed。

    ⛔ 本函数**不接收**专业名 / 文件名 / 角色 / Content-Type ——
    调用方给什么都不可能影响判定结果。
    """

    report = inspect_curriculum_pdf(data)
    observed = _observed_marks(report)

    matched: list[str] = []
    for document in DOCUMENT_TYPES:
        fingerprint = _fingerprint(document)
        # ⚠️ 判据是"**声明的每一张表都在该页以相同的表头出现**"（完全覆盖），
        #    ⛔ 不是"有交集就算"：两份文件共享大量相同表头，
        #    只要有交集就会双双命中 ⇒ 实测直接判成歧义。
        if fingerprint and fingerprint <= observed:
            matched.append(document.key)

    if not matched:
        raise CurriculumNormalizationError(
            "pdf profile: no verified document type matches this file's structure"
        )
    if len(matched) > 1:
        # 多份已验收类型都完全覆盖 ⇒ 只凭结构区分不了 ⇒ fail closed
        # （⛔ 不回退去用专业名 / 文件名 / 角色猜）。
        raise CurriculumNormalizationError(
            "pdf profile: document type is ambiguous for this file's structure"
        )
    return matched[0], report


def verify_document_type(data: bytes, declared_key: object) -> DocumentType:
    """校验调用方**断言**的类型与内容结构判定结果是否一致；⛔ 不一致即拒绝。"""

    document = profile_for(declared_key)
    detected, _ = detect_document_type(data)
    if detected != document.key:
        raise CurriculumNormalizationError(
            "pdf profile: declared document type does not match the file's structure"
        )
    return document


def load_curriculum_pdf_verified(
    data: bytes, *, source_id: str, document_key: object = None,
) -> tuple[DocumentType, object]:
    """**CLI 与 HTTP 共用的入口**：解析一份已验收的培养方案 PDF。

    ```text
    document_key 给了 → 先按内容结构核对（不一致即拒绝），再用该类型的 profile
    document_key 没给 → 按内容结构判定类型，再用它的 profile
    ```

    返回 `(文档类型, DocxImportResult)`。
    ⛔ 不写文件、⛔ 不联网、⛔ 不写目录、⛔ 不写批准锚点。
    """

    if document_key is None:
        detected, _ = detect_document_type(data)
        document = profile_for(detected)
    else:
        document = verify_document_type(data, document_key)

    result = load_curriculum_pdf(data, source_id=source_id, tables=document.tables)
    return document, result
