"""Build synthetic SYSU-layout transcript PDFs for tests.

⛔ 这里的所有课程 / 学期 / 成绩都是**虚构的**，只用于验证版面解析；
⛔ 不包含、也⛔ 不代表任何真实学生的成绩单数据。

版面严格对齐**已核验**的中山大学本科成绩单 PDF：

```text
标题（中山大学本科生成绩单）
学生信息区块（姓名 / 学号 / 学院 / 专业 / 年级 …）   ← 解析器必须整体丢弃
表头第一行：课程名称  学分  成绩  课程   ×4 组
表头第二行：                        属性  ×4 组
term 行 → 课程数据行 → … → 每学期末 "学分 …" 汇总行
页脚：毕业论文题目 / 毕业应得学分 / 实得学分 / 平均绩点 / 评分体系 / 审核人
```

用 PyMuPDF 生成，因此这些 fixture 走的是与真实成绩单**同一条**解析路径。
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "BAND_NAME_X",
    "DEMO_STUDENT_NAME",
    "DEMO_STUDENT_NUMBER",
    "TERM_ONE",
    "TERM_TWO",
    "build_case_a_transcript_pdf",
    "build_transcript_pdf",
    "fictional_transcript",
]

#: 已核验版面的四个列组起点（PDF 用户单位），与真实成绩单一致。
_BAND_NAME_X = (52.36, 268.48, 484.61, 700.74)
BAND_NAME_X = _BAND_NAME_X
_CREDIT_OFFSET = 79.48
_GRADE_OFFSET = 115.50
_ATTRIBUTE_OFFSET = 151.52
_ROW_PITCH = 9.44

#: 表头两行的 y 基线。
_HEADER_MAIN_Y = 73.20
_HEADER_ATTRIBUTE_Y = 78.82
#: 第一张表行的 y 基线。
_FIRST_ROW_Y = 97.46
#: 标题与学生信息区块。
_TITLE_Y = 5.53
_INFO_Y = (39.95, 49.39)
#: 页脚各行的相对位置。
_FOOTER_GAP = 1.5

TERM_ONE = "2025-2026学年 第一学期"
TERM_TWO = "2025-2026学年 第二学期"

#: 虚构学生身份；测试用它证明解析结果**不含**个人信息。
DEMO_STUDENT_NAME = "示例学生甲"
DEMO_STUDENT_NUMBER = "2099000001"


def _write_text(page: object, x: float, y: float, text: str) -> None:
    page.insert_text((x, y), text, fontname="china-s", fontsize=8)  # type: ignore[attr-defined]


def _write_blank_cells(page: object, name_x: float, y: float) -> None:
    """已核验版面在**换行名称行**上仍会打印空的学分 / 成绩 / 属性单元格。

    这一点很关键：正是这些格子（本 fixture 用极细的占位竖线表示）让解析器能把该行
    识别为"无名称的数据行"，从而把下一行当作课程名的续行。
    """

    for offset in (_CREDIT_OFFSET, _GRADE_OFFSET, _ATTRIBUTE_OFFSET):
        page.draw_line(  # type: ignore[attr-defined]
            (name_x + offset, y), (name_x + offset, y + 0.4), width=0.4
        )


def _draw_header(page: object) -> None:
    for name_x in _BAND_NAME_X:
        _write_text(page, name_x, _HEADER_MAIN_Y, "课程名称")
        _write_text(page, name_x + _CREDIT_OFFSET, _HEADER_MAIN_Y, "学分")
        _write_text(page, name_x + _GRADE_OFFSET, _HEADER_MAIN_Y, "成绩")
        _write_text(page, name_x + _ATTRIBUTE_OFFSET, _HEADER_MAIN_Y, "课程")
        _write_text(page, name_x + _ATTRIBUTE_OFFSET, _HEADER_ATTRIBUTE_Y, "属性")


def _draw_student_block(page: object) -> None:
    _write_text(page, 336.9, _TITLE_Y, "中山大学本科生成绩单")
    _write_text(page, 9.2, _INFO_Y[0], f"姓名: {DEMO_STUDENT_NAME}")
    _write_text(page, 9.2, _INFO_Y[1], f"学号: {DEMO_STUDENT_NUMBER}")
    _write_text(page, 153.3, _INFO_Y[0], "学院: 示例学院")
    _write_text(page, 153.3, _INFO_Y[1], "专业: 示例专业")
    _write_text(page, 369.4, _INFO_Y[0], "年级: 2025")
    _write_text(page, 657.6, _INFO_Y[0], "入校时间: 2025-08    学制: 4")


def build_transcript_pdf(
    path: Path,
    *,
    bands: list[list[tuple[str, list[dict[str, object]]]]],
    footer: bool = True,
    extra_footer_lines: tuple[str, ...] = (),
    student_block: bool = True,
    draw_blank_cells: bool = True,
) -> Path:
    """Render one transcript page.

    ``bands`` 是**列组**列表，每个列组是 ``(term, courses)`` 列表；每个 course 是
    ``{"name": str, "credit": str, "grade": str, "attribute": str, "wrap": str}``。
    ``wrap`` 会作为课程名的**续行**画在数据行之下的另一条基线上（已核验版面行为），
    并在该行打印空的学分 / 成绩 / 属性单元格。
    """

    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=878.91, height=595.44)
    if student_block:
        _draw_student_block(page)
    _draw_header(page)

    # 每个列组独立排版：学期行 → 课程行 → 学期汇总行。
    for band_index, band in enumerate(bands):
        name_x = _BAND_NAME_X[band_index]
        y = _FIRST_ROW_Y
        for term, courses in band:
            _write_text(page, name_x + 22.0, y, term)
            y += _ROW_PITCH
            for course in courses:
                wrap = course.get("wrap")
                name_text = str(course["name"])
                if wrap:
                    # ⚠️ 已核验版面的换行课程名是**两行**：
                    # 名称前半 + 空数据格 → 数据行（名称格为空）→ 名称后半。
                    # 若把名称与数据画在同一行，正是真实成绩单**不会**出现的形态。
                    _write_text(page, name_x, y, name_text)
                    _write_blank_cells(page, name_x, y)
                    y += _ROW_PITCH
                    _write_text(page, name_x + _CREDIT_OFFSET, y, str(course["credit"]))
                    _write_text(page, name_x + _GRADE_OFFSET, y, str(course["grade"]))
                    _write_text(page, name_x + _ATTRIBUTE_OFFSET, y, str(course["attribute"]))
                    y += _ROW_PITCH
                    _write_text(page, name_x, y, str(wrap))
                    _write_blank_cells(page, name_x, y)
                else:
                    _write_text(page, name_x, y, name_text)
                    _write_text(page, name_x + _CREDIT_OFFSET, y, str(course["credit"]))
                    _write_text(page, name_x + _GRADE_OFFSET, y, str(course["grade"]))
                    _write_text(page, name_x + _ATTRIBUTE_OFFSET, y, str(course["attribute"]))
                y += _ROW_PITCH
            _write_text(page, name_x, y, "学分 0(必修)0(专选)")
            y += _ROW_PITCH

    if footer:
        base = _FIRST_ROW_Y + _ROW_PITCH * 33
        for step, text in enumerate((
            "毕业论文题目：",
            "毕业应得学分：153(总学分) 122(必修) 23(专选) 8(公选)",
            "实得学分：52(总学分) 46(必修) 1(专选) 5(公选)",
            "主修全部课程平均绩点：3.6         必修、专选课程平均绩点：3.6",
            "评分体系：90-100  4.0-5.0 (优秀 4.5)   60-69  1.0-1.9 (及格 1.5)",
            "P/NP  通过/不通过，不计绩点",
            "审核人: 示例学院 2026年 10月 07日 印制",
        )):
            _write_text(page, 9.2, base + step * (_ROW_PITCH + _FOOTER_GAP), text)
        for step, text in enumerate(extra_footer_lines):
            _write_text(page, 9.2, base + (len(extra_footer_lines) + step) * _ROW_PITCH, text)

    document.save(str(path))
    document.close()
    return path


def fictional_transcript() -> list[list[tuple[str, list[dict[str, object]]]]]:
    """A fully fictional transcript body in the verified layout."""

    return [[
        (TERM_ONE, [
            {"name": "示例线性代数", "credit": "3", "grade": "97", "attribute": "专必"},
            {"name": "示例高等数学", "credit": "5", "grade": "82", "attribute": "专必"},
            {"name": "示例实践课：综合观测与探究", "credit": "1.5", "grade": "87",
             "attribute": "专选", "wrap": "方法"},
            {"name": "示例大学英语", "credit": "2", "grade": "P", "attribute": "公必"},
        ]),
        (TERM_TWO, [
            {"name": "示例程序设计", "credit": "2", "grade": "95", "attribute": "专必"},
            {"name": "示例通识课", "credit": "1", "grade": "NP", "attribute": "公选"},
        ]),
    ]]


def build_case_a_transcript_pdf(path: Path) -> Path:
    """The Case A integration fixture: four terms/courses that exercise matching.

    - ``示例线性代数`` 与目标方案**同名**，但成绩单没有课程号
      ⇒ 必须保持人工确认，⛔ 不得自动抵认；
    - ``示例程序设计`` 同上；
    - ``示例观测实践`` 是目标方案里**不存在**的课 ⇒ 不得产生补修任务；
    - ``示例大学物理`` 只修了 2 学分，目标要求 3 学分 ⇒ 不得自动抵认。
    """

    return build_transcript_pdf(
        path,
        bands=[[
            (TERM_ONE, [
                {"name": "示例线性代数", "credit": "3", "grade": "97", "attribute": "专必"},
                {"name": "示例大学物理", "credit": "2", "grade": "88", "attribute": "专必"},
                {"name": "示例观测实践", "credit": "1.5", "grade": "P", "attribute": "公选"},
            ]),
            (TERM_TWO, [
                {"name": "示例程序设计", "credit": "2", "grade": "95", "attribute": "专必"},
            ]),
        ]],
        extra_footer_lines=("国家学生体质健康标准：合格",),
    )
