"""**合成 PDF 生成器**（测试专用，⛔ 不引入第二个 PDF 库）。

为什么自己写：仓库内 **0 个 `.pdf`**，真实培养方案 PDF 不在仓库里（⛔ 也不应进仓库）。
测试需要"结构已知"的 PDF 来验证：表头识别、行级 issue、跨页、扫描件拒绝、
损坏文件、非 PDF 伪装、超大文件。

因此这里用**最小 PDF 写入器**（只写需要的对象，正文用 `Tj` 文本算子），
⛔ 不依赖任何第三方库、⛔ 不联网。它只服务测试，⛔ 不是产品代码。

⚠️ 中文字符需要嵌入 CJK 字体，那会让这个生成器复杂到失去意义。
因此合成 PDF 里的**课程号与表头**用 ASCII（真实培养方案里课程号本来就是
`MAR103` / `CSE323` / `n08120200` 这类 ASCII），中文**名称**用 ASCII 占位（如 `Course-A`）。
真实中文名称的解析由"文本层存在 + 表头匹配"这条路径覆盖，
真正的中文端到端验收依赖**两份真实 PDF**（见 `PDF_IMPORT_REPORT.md` 的 BLOCKED 段）。
"""

from __future__ import annotations

import zlib

__all__ = ["build_pdf", "build_table_pdf", "build_scanned_pdf"]


def _escape(text: str) -> str:
    """PDF 字面量字符串转义（ASCII 子集）。"""

    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(pages: list[list[tuple[float, float, str]]]) -> bytes:
    """用"每页一组 `(x, y, text)`"生成一份最小 PDF。

    ⚠️ 坐标系是 PDF 原生坐标（**左下角**为原点，y 向上）。
    调用方给的是"行号 → y"的直觉值，见 `build_table_pdf`。
    """

    if not pages:
        raise ValueError("build_pdf: at least one page is required")

    objects: list[bytes] = []

    def add(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    # 1: Catalog, 2: Pages, 3: Font —— 预留，先占位再回填。
    catalog_id = add(b"")
    pages_id = add(b"")
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_ids: list[int] = []
    for items in pages:
        content_lines = ["BT", "/F1 10 Tf", "12 TL"]
        for x, y, text in items:
            content_lines.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
            content_lines.append(f"({_escape(text)}) Tj")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("ascii")
        compressed = zlib.compress(stream)
        content_id = add(
            b"<< /Length " + str(len(compressed)).encode() + b" /Filter /FlateDecode >>\nstream\n"
            + compressed + b"\nendstream"
        )
        page_ids.append(add(
            b"<< /Type /Page /Parent " + str(pages_id).encode() + b" 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 " + str(font_id).encode() + b" 0 R >> >> "
            b"/Contents " + str(content_id).encode() + b" 0 R >>"
        ))

    kids = b" ".join(str(pid).encode() + b" 0 R" for pid in page_ids)
    objects[pages_id - 1] = (
        b"<< /Type /Pages /Count " + str(len(page_ids)).encode() + b" /Kids [" + kids + b"] >>"
    )
    objects[catalog_id - 1] = (
        b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + payload + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode()
        + b" /Root " + str(catalog_id).encode() + b" 0 R >>\n"
        + b"startxref\n" + str(xref_at).encode() + b"\n%%EOF\n"
    )
    return bytes(out)


def build_table_pdf(
    rows: list[list[str]], *, title: str = "Training Program", extra_pages: int = 0,
) -> bytes:
    """生成"一页、一张**有边框**的表"的 PDF。

    ⚠️ 为什么必须画边框：PyMuPDF 的 `find_tables()` 依赖**线 / 矩形**来判定表格。
    已实测：无边框（仅靠文本对齐）的合成 PDF **识别不出表格**（`tables found: 0`）。
    这与真实情况一致——教务网页重排导出的培养方案 PDF 通常保留表格线。
    这份夹具因此**显式画表格线**，以覆盖"表格可识别"这一条主路径；
    "没有表格线"的情形由 `pdf_reader` 的 `table_not_found` issue 如实报告
    （⛔ 不猜测、⛔ 不退回按位置硬套）。
    """

    if not rows:
        raise ValueError("build_table_pdf: at least one row is required")

    # ⚠️ 两个**实测**约束（违反任一都会让 `find_tables()` 静默丢列）：
    #    1. 所有表线必须落在页面内（A4 宽 595）——超出页面时最后一列会被丢掉；
    #    2. 列间距太小会把相邻列并成一格。
    column_x = [56.0, 140.0, 230.0, 320.0, 410.0, 500.0]
    top_y = 760.0
    line_height = 16.0
    width = len(column_x)  # ⚠️ 图表宽固定：列太少时 `find_tables()` 会合并相邻列

    items: list[tuple[float, float, str]] = [(56.0, top_y + 64.0, title)]
    for row_index, row in enumerate(rows):
        y = top_y - row_index * line_height
        for column_index, value in enumerate(row):
            if value and column_index < width:
                items.append((column_x[column_index], y, value))

    # 表格线：竖线按列起点 + 右边界；横线按行上下边界。
    # ⚠️ 上下要留足余量：已实测，边界贴着最后一行文字时 `find_tables()`
    #    会把**最后一行漏掉**（识别到的行数与画出的行数不符）。
    graphics: list[str] = ["0.5 w", "0 0 0 RG"]
    pad = line_height * 0.9
    top_edge = top_y + pad
    bottom_edge = top_y - (len(rows) - 1) * line_height - pad
    right_edge = 560.0
    for x in (*column_x[:width], right_edge):
        graphics.append(f"{x:.2f} {bottom_edge:.2f} m {x:.2f} {top_edge:.2f} l S")
    for row_index in range(len(rows) + 1):
        y = top_y + pad - row_index * line_height
        graphics.append(
            f"{column_x[0]:.2f} {y:.2f} m {right_edge:.2f} {y:.2f} l S"
        )

    pages: list[tuple[list[tuple[float, float, str]], list[str]]] = [(items, graphics)]
    for filler in range(extra_pages):
        pages.append(([(60.0, 760.0, f"Appendix page {filler + 1}")], []))
    return _build_pdf(pages)


def _build_pdf(
    pages: list[tuple[list[tuple[float, float, str]], list[str]]],
) -> bytes:
    """`(文本项, 图形指令)` → 最小 PDF 字节。"""

    if not pages:
        raise ValueError("_build_pdf: at least one page is required")

    objects: list[bytes] = []

    def add(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    catalog_id = add(b"")
    pages_id = add(b"")
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_ids: list[int] = []
    for items, graphics in pages:
        content_lines: list[str] = list(graphics)
        if items:
            content_lines += ["BT", "/F1 10 Tf", "12 TL"]
            for x, y, text in items:
                content_lines.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
                content_lines.append(f"({_escape(text)}) Tj")
            content_lines.append("ET")
        stream = "\n".join(content_lines).encode("ascii")
        compressed = zlib.compress(stream)
        content_id = add(
            b"<< /Length " + str(len(compressed)).encode() + b" /Filter /FlateDecode >>\nstream\n"
            + compressed + b"\nendstream"
        )
        page_ids.append(add(
            b"<< /Type /Page /Parent " + str(pages_id).encode() + b" 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 " + str(font_id).encode() + b" 0 R >> >> "
            b"/Contents " + str(content_id).encode() + b" 0 R >>"
        ))

    kids = b" ".join(str(pid).encode() + b" 0 R" for pid in page_ids)
    objects[pages_id - 1] = (
        b"<< /Type /Pages /Count " + str(len(page_ids)).encode() + b" /Kids [" + kids + b"] >>"
    )
    objects[catalog_id - 1] = (
        b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + payload + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode()
        + b" /Root " + str(catalog_id).encode() + b" 0 R >>\n"
        + b"startxref\n" + str(xref_at).encode() + b"\n%%EOF\n"
    )
    return bytes(out)


def build_textonly_pdf(text: str = "No table here") -> bytes:
    """生成"一页、无表格线"的 PDF：用于验证**没有表格时如实报告**而非猜测。"""

    return _build_pdf([([(60.0, 760.0, text)], [])])


def build_scanned_pdf(*, pages: int = 2) -> bytes:
    """生成"**没有文本层**"的 PDF（模拟扫描件）：只有图形、没有可提取文字。"""

    if pages < 1:
        raise ValueError("build_scanned_pdf: at least one page is required")

    objects: list[bytes] = []

    def add(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    catalog_id = add(b"")
    pages_id = add(b"")
    page_ids: list[int] = []
    for _ in range(pages):
        # 一条纯图形指令：画一个大方块，⛔ 没有任何 BT/Tj 文本算子。
        stream = b"0.2 0.2 0.2 rg\n50 50 500 700 re\nf\n"
        content_id = add(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
        page_ids.append(add(
            b"<< /Type /Page /Parent " + str(pages_id).encode() + b" 0 R /MediaBox [0 0 595 842] "
            b"/Resources << >> /Contents " + str(content_id).encode() + b" 0 R >>"
        ))
    kids = b" ".join(str(pid).encode() + b" 0 R" for pid in page_ids)
    objects[pages_id - 1] = (
        b"<< /Type /Pages /Count " + str(len(page_ids)).encode() + b" /Kids [" + kids + b"] >>"
    )
    objects[catalog_id - 1] = (
        b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + payload + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode()
        + b" /Root " + str(catalog_id).encode() + b" 0 R >>\nstartxref\n"
        + str(xref_at).encode() + b"\n%%EOF\n"
    )
    return bytes(out)
