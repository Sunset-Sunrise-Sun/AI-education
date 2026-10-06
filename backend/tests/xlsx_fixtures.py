"""Gate F 的 **synthetic** XLSX fixtures（全部人工构造，⛔ 不含任何真实学生数据）。

只生成最小可用的 OOXML 部件（`[Content_Types].xml` / `_rels/.rels` / `xl/workbook.xml` /
`xl/_rels/workbook.xml.rels` / `xl/worksheets/*.xml` / 可选 `xl/sharedStrings.xml`），
因此既不依赖 openpyxl，也不需要真实 Excel 产出的文件。

⚠️ 这些 fixture 只用于**测试**：⛔ 不得提交任何真实成绩单 / 学生材料。
"""

from __future__ import annotations

import io
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

__all__ = [
    "APPROVED_SHEET",
    "HEADERS",
    "duplicate_rows_bytes",
    "empty_sheet_bytes",
    "formula_cell_bytes",
    "macro_parts",
    "malformed_bytes",
    "missing_course_id_bytes",
    "mixed_cell_types_bytes",
    "numeric_course_id_bytes",
    "oversized_part_bytes",
    "private_marker_bytes",
    "record_row",
    "sheet_with_records",
    "valid_bytes",
    "workbook_bytes",
    "wrong_headers_bytes",
]

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

APPROVED_SHEET = "已修课程_脱敏"
OTHER_SHEET = "其它工作表"

HEADERS = (
    "序号",
    "course_id",
    "course_name",
    "credit",
    "semester",
    "passed",
    "course_type",
    "course_id_status",
    "id_match_source",
    "备注",
)


def _q(name: str) -> str:
    return f"{{{MAIN_NS}}}{name}"


def _cell(reference: str, value: object, *, kind: str | None = None) -> ET.Element:
    cell = ET.Element(_q("c"), r=reference)
    if value is None:
        return cell
    resolved = kind or (
        "b" if isinstance(value, bool) else "n" if isinstance(value, (int, float)) else "inlineStr"
    )
    cell.set("t", resolved)
    if resolved == "inlineStr":
        inline = ET.SubElement(cell, _q("is"))
        ET.SubElement(inline, _q("t")).text = str(value)
    elif resolved == "str":
        ET.SubElement(cell, _q("v")).text = str(value)
    else:
        ET.SubElement(cell, _q("v")).text = (
            "1" if value is True else "0" if value is False else str(value)
        )
    return cell


def _formula_cell(reference: str, formula: str, cached: str) -> ET.Element:
    """构造一个**公式**单元格（`<f>`）——reader 必须直接拒绝，⛔ 绝不求值。"""

    cell = ET.Element(_q("c"), r=reference)
    ET.SubElement(cell, _q("f")).text = formula
    ET.SubElement(cell, _q("v")).text = cached
    return cell


def _sheet(rows: list[list[object]], *, headers: tuple[object, ...] = HEADERS) -> bytes:
    root = ET.Element(_q("worksheet"))
    data = ET.SubElement(root, _q("sheetData"))
    header = ET.SubElement(data, _q("row"), r="1")
    for column, value in enumerate(headers):
        header.append(_cell(f"{chr(65 + column)}1", value))
    for offset, values in enumerate(rows, start=2):
        row = ET.SubElement(data, _q("row"), r=str(offset))
        for column, value in enumerate(values):
            row.append(_cell(f"{chr(65 + column)}{offset}", value))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def record_row(
    sequence: int,
    *,
    course_id: object = "DEMO-COURSE-01",
    course_name: object = "示例课程一",
    credit: object = 3,
    semester: object = "2026-1",
    passed: object = True,
    course_type: object = "示例必修",
    course_id_status: object = "已确认",
    id_match_source: object = "示例来源",
    notes: object = "示例备注",
) -> list[object]:
    return [
        sequence,
        course_id,
        course_name,
        credit,
        semester,
        passed,
        course_type,
        course_id_status,
        id_match_source,
        notes,
    ]


def workbook_bytes(
    *,
    sheet_xml: bytes | None = None,
    selected_sheet_name: str = APPROVED_SHEET,
    extra_parts: dict[str, bytes] | None = None,
    include_content_types: bool = True,
) -> bytes:
    """把部件打包成一个 `.xlsx`（zip）并返回字节。"""

    workbook = ET.Element(_q("workbook"))
    sheets = ET.SubElement(workbook, _q("sheets"))
    ET.SubElement(
        sheets, _q("sheet"), name=OTHER_SHEET, sheetId="1",
        **{f"{{{DOC_REL_NS}}}id": "rId1"},
    )
    ET.SubElement(
        sheets, _q("sheet"), name=selected_sheet_name, sheetId="2",
        **{f"{{{DOC_REL_NS}}}id": "rId2"},
    )
    relationships = ET.Element(f"{{{REL_NS}}}Relationships")
    ET.SubElement(
        relationships, f"{{{REL_NS}}}Relationship", Id="rId1",
        Type=f"{DOC_REL_NS}/worksheet", Target="worksheets/sheet1.xml",
    )
    ET.SubElement(
        relationships, f"{{{REL_NS}}}Relationship", Id="rId2",
        Type=f"{DOC_REL_NS}/worksheet", Target="worksheets/sheet2.xml",
    )
    content_types = ET.Element(f"{{{CONTENT_TYPES_NS}}}Types")
    ET.SubElement(
        content_types, f"{{{CONTENT_TYPES_NS}}}Default", Extension="xml",
        ContentType="application/xml",
    )
    ET.SubElement(
        content_types, f"{{{CONTENT_TYPES_NS}}}Override", PartName="/xl/workbook.xml",
        ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    )

    parts: dict[str, bytes] = {
        "xl/workbook.xml": ET.tostring(workbook, encoding="utf-8", xml_declaration=True),
        "xl/_rels/workbook.xml.rels": ET.tostring(
            relationships, encoding="utf-8", xml_declaration=True
        ),
        "xl/worksheets/sheet1.xml": _sheet([]),
        "xl/worksheets/sheet2.xml": sheet_xml if sheet_xml is not None else _sheet([]),
    }
    if include_content_types:
        parts["[Content_Types].xml"] = ET.tostring(
            content_types, encoding="utf-8", xml_declaration=True
        )
    parts.update(extra_parts or {})

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# F4 要求的 fixture 矩阵
# --------------------------------------------------------------------------- #


def sheet_with_records(
    rows: list[list[object]], *, headers: tuple[object, ...] = HEADERS
) -> bytes:
    """用给定数据行（`record_row(...)`）生成已批准布局的工作表。"""

    return _sheet(rows, headers=headers)


def valid_bytes() -> bytes:
    """合法：两条已确认记录 + 一条待确认（无 course_id）记录 + Unicode 课程名。"""

    return workbook_bytes(
        sheet_xml=_sheet(
            [
                record_row(1, course_name="示例课程一", credit=3, notes="示例备注一"),
                record_row(
                    2,
                    course_id=None,
                    course_name="待确认课程（Unicode ✓ 中文）",
                    credit=2.5,
                    course_id_status="待确认",
                    id_match_source=None,
                    notes=None,
                ),
                record_row(
                    3,
                    course_id="DEMO-COURSE-03",
                    course_name="示例课程三 ✓",
                    credit=1,
                    passed=False,
                    notes="示例备注三",
                ),
            ]
        )
    )


def empty_sheet_bytes() -> bytes:
    """只有表头、没有任何数据行。"""

    return workbook_bytes(sheet_xml=_sheet([]))


def wrong_headers_bytes() -> bytes:
    """表头被改名（结构校验必须拒绝）。"""

    headers = list(HEADERS)
    headers[2] = "课程名字"
    return workbook_bytes(sheet_xml=_sheet([record_row(1)], headers=tuple(headers)))


def duplicate_rows_bytes() -> bytes:
    """序号重复（完整性校验必须拒绝重复序号）。"""

    return workbook_bytes(
        sheet_xml=_sheet([record_row(1), record_row(1, course_id="DEMO-COURSE-02")])
    )


def missing_course_id_bytes() -> bytes:
    """`course_id` 为空但状态声明为"已确认"（自相矛盾 ⇒ 必须拒绝）。"""

    return workbook_bytes(
        sheet_xml=_sheet([record_row(1, course_id=None, id_match_source=None)])
    )


def formula_cell_bytes(*, private_marker: str = "PRIVATE-FORMULA-MARKER") -> bytes:
    """含公式单元格（`<f>`）的工作表：⛔ 绝不求值，直接拒绝。"""

    root = ET.Element(_q("worksheet"))
    data = ET.SubElement(root, _q("sheetData"))
    header = ET.SubElement(data, _q("row"), r="1")
    for column, value in enumerate(HEADERS):
        header.append(_cell(f"{chr(65 + column)}1", value))
    row = ET.SubElement(data, _q("row"), r="2")
    row.append(_formula_cell("A2", f"{private_marker}()", private_marker))
    for column, value in enumerate(record_row(1)[1:], start=1):
        row.append(_cell(f"{chr(65 + column)}2", value))
    return workbook_bytes(sheet_xml=ET.tostring(root, encoding="utf-8", xml_declaration=True))


def malformed_bytes() -> bytes:
    """完全不是 zip 的字节（malformed workbook ⇒ fail closed）。"""

    return b"NOT-A-ZIP-WORKBOOK"


def oversized_part_bytes(*, megabytes: int = 17) -> bytes:
    """某个 XML 部件超过 reader 的单部件上限（16 MiB），但压缩后很小。"""

    padding = " " * (megabytes * 1024 * 1024)
    sheet = ET.fromstring(_sheet([record_row(1)]))
    holder = ET.SubElement(sheet, _q("extLst"))
    holder.text = padding
    return workbook_bytes(
        sheet_xml=ET.tostring(sheet, encoding="utf-8", xml_declaration=True)
    )


def macro_parts() -> dict[str, bytes]:
    """额外的宏部件（`vbaProject.bin`）：必须被**忽略**且⛔ 永不执行。"""

    return {
        "xl/vbaProject.bin": b"\xd0\xcf\x11\xe0DEMO-VBA-MARKER",
        "xl/_rels/vbaProject.bin.rels": b"<Relationships/>",
    }


def mixed_cell_types_bytes() -> bytes:
    """同一行混用 numeric / boolean / inlineStr / `t="str"` 单元格（合法输入）。"""

    root = ET.Element(_q("worksheet"))
    data = ET.SubElement(root, _q("sheetData"))
    header = ET.SubElement(data, _q("row"), r="1")
    for column, value in enumerate(HEADERS):
        header.append(_cell(f"{chr(65 + column)}1", value))
    row = ET.SubElement(data, _q("row"), r="2")
    row.append(_cell("A2", 1))                                  # number
    row.append(_cell("B2", "DEMO-COURSE-01", kind="str"))       # t="str"
    row.append(_cell("C2", "示例课程一（混合类型）"))             # inlineStr
    row.append(_cell("D2", 2.5))                                # number
    row.append(_cell("E2", "2026-1"))                           # inlineStr
    row.append(_cell("F2", True))                               # boolean
    row.append(_cell("G2", "示例必修"))
    row.append(_cell("H2", "已确认"))
    row.append(_cell("I2", "示例来源"))
    row.append(_cell("J2", None))                               # 空单元格
    return workbook_bytes(sheet_xml=ET.tostring(root, encoding="utf-8", xml_declaration=True))


def numeric_course_id_bytes() -> bytes:
    """`course_id` 写成数字：⛔ 不得静默转成文本。"""

    return workbook_bytes(sheet_xml=_sheet([record_row(1, course_id=12345)]))


def private_marker_bytes(marker: str) -> bytes:
    """把隐私标记塞进多个单元格，同时制造一个**必然失败**的结构错误。

    用于证明：错误响应里⛔ 不出现任何单元格取值 / 原始 XML / 本地路径。
    """

    headers = list(HEADERS)
    headers[2] = marker  # 错误的表头（同时出现在错误定位行里）
    return workbook_bytes(
        sheet_xml=_sheet(
            [record_row(1, course_name=marker, notes=f"备注-{marker}")], headers=tuple(headers)
        )
    )


def write(tmp_path: Path, payload: bytes, name: str = "fixture.xlsx") -> Path:
    """把字节落到磁盘（仅用于与路径版 reader 做等价性对比）。"""

    path = tmp_path / name
    path.write_bytes(payload)
    return path
