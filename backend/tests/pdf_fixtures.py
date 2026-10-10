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

    # ⚠️ 三个**实测**约束（违反任一会让 `find_tables()` 静默丢列/丢行，
    #    或让行框切到表格上下的正文里）：
    #    1. 所有表线必须落在页面内（A4 宽 595）——超出页面时最后一列会被丢掉；
    #    2. 列间距太小会把相邻列并成一格；
    #    3. 行边界必须落在**两行文字中间**，且标题要离表格足够远
    #       —— 否则行框会切进标题的字形（实测会把标题最后一个字母
    #       'g' / 'q' 吃进数据格）。
    column_x = [56.0, 140.0, 230.0, 320.0, 410.0, 500.0]
    top_y = 700.0
    line_height = 20.0
    width = len(column_x)  # ⚠️ 图表宽固定：列太少时 `find_tables()` 会合并相邻列

    # 标题离表格上边界至少半个行高 + 字形余量（PDF 原生坐标：y 向上为正）。
    items: list[tuple[float, float, str]] = [(56.0, top_y + line_height * 2.0, title)]
    for row_index, row in enumerate(rows):
        y = top_y - row_index * line_height
        for column_index, value in enumerate(row):
            if value and column_index < width:
                items.append((column_x[column_index], y, value))

    # 表格线：竖线按列起点 + 右边界；横线落在**行间隙正中**。
    graphics: list[str] = ["0.5 w", "0 0 0 RG"]
    top_edge = top_y + line_height / 2
    bottom_edge = top_y - (len(rows) - 1) * line_height - line_height / 2
    right_edge = 560.0
    for x in (*column_x[:width], right_edge):
        graphics.append(f"{x:.2f} {bottom_edge:.2f} m {x:.2f} {top_edge:.2f} l S")
    for row_index in range(len(rows) + 1):
        y = top_edge - row_index * line_height
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


def build_two_row_header_pdf(
    header_rows: list[list[str | None]], data_rows: list[list[str | None]], *,
    column_count: int = 6,
) -> bytes:
    """生成"**双行表头 + 合并单元格 + 中文表头**"的表格 PDF（真实培养方案的常见形态）。

    ⚠️ 为什么这里改用 PyMuPDF 而不是本文件的纯 ASCII 写入器：
    真实表头是中文（"序号 / 课程号 / 课程名称 / 学分 / 建议学期"），
    中文需要**嵌入 CJK 字体**并做 Identity-H 编码。自建的最小写入器只处理
    Latin-1 字面量字符串，硬塞 UTF-16BE 十六进制串要另写一套字体嵌入器 ——
    那已经不是"最小写入器"，而是重造一个 PDF 库。
    因此这里用**项目已采用的** PyMuPDF 自己嵌字与排版（⛔ 不引入第二个库）；
    ASCII 用例仍走上面的纯标准库写入器。

    ⚠️ 合并单元格：`None` / `""` 表示该格为空，不产出任何文字。
    实测 `find_tables()` 对无内容格子的输出就是 `None`（**不是** `""`）。

    ⚠️ 对齐：逐格用 `font.text_length()` 量宽，**按文本宽度累加**推算 x 与竖线位置，
    因此中文/拉丁混排也能对齐（不依赖等宽字体）。
    列间留出 `COLUMN_GAP`，否则相邻格会被并成一列。
    """

    try:
        import pymupdf
    except ImportError:  # pragma: no cover - 测试依赖缺失
        raise RuntimeError("build_two_row_header_pdf requires pymupdf") from None

    width, height = 595.0, 842.0
    font_size = 10.0
    row_height = 26.0
    column_gap = 28.0
    margin_x = 40.0
    top_y = 700.0

    font = pymupdf.Font("china-s")

    def text_width(value: str) -> float:
        return font.text_length(value, fontsize=font_size)

    all_rows = [*header_rows, *data_rows]
    columns = max(column_count, max((len(row) for row in all_rows), default=0))

    # 每列内容宽度 = 该列所有格子里最宽的那个（表头与数据一起算，保证同宽）。
    column_widths: list[float] = []
    for position in range(columns):
        widest = 0.0
        for row in all_rows:
            if position < len(row) and row[position]:
                widest = max(widest, text_width(str(row[position])))
        column_widths.append(widest)

    column_x: list[float] = []
    cursor = margin_x
    for position in range(columns):
        column_x.append(cursor)
        cursor += column_widths[position] + column_gap
    right_edge = cursor - column_gap + 14.0

    # 表头/数据的文字基线（屏幕式坐标：y 向下增，见上）。
    baselines = [top_y + index * row_height for index in range(len(all_rows))]
    # 竖线范围：文字上下各外扩一点，否则首/末行会被"裁"出表格。
    top_edge = baselines[0] - row_height * 0.55
    bottom_edge = baselines[-1] + row_height * 0.55
    # 横线：表格上边界 + 每行下边界。
    boundaries = [top_edge, *[baseline + row_height * 0.45 for baseline in baselines]]

    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.insert_font(fontname="F1", fontbuffer=font.buffer)

    # --- 表格线 ---
    # 竖线：只画在**表头区与数据区**，右边界收在最后一个字的右边。
    for position in range(columns):
        left = column_x[position] - 8.0
        page.draw_line(pymupdf.Point(left, top_edge), pymupdf.Point(left, bottom_edge))
    page.draw_line(pymupdf.Point(right_edge, top_edge), pymupdf.Point(right_edge, bottom_edge))
    # 横线：表格上边界 + 每行下边界（屏幕式坐标：y 向下增）。
    boundaries = [top_edge, *[baseline + row_height * 0.45 for baseline in baselines]]
    for y in boundaries:
        page.draw_line(pymupdf.Point(margin_x - 8.0, y), pymupdf.Point(right_edge, y))

    # --- 文字 ---
    for row_index, row in enumerate(all_rows):
        baseline = baselines[row_index]
        for position in range(columns):
            if position >= len(row) or not row[position]:
                continue
            page.insert_text(
                (column_x[position], baseline), str(row[position]),
                fontname="F1", fontsize=font_size,
            )

    data = document.tobytes()
    document.close()
    return data


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
