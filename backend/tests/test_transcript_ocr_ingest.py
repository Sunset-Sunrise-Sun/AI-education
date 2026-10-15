"""成绩单图片识别适配器测试（Phase 5）。

真实 OCR 推理很慢且依赖模型文件，因此这里**不跑真实 OCR**：
用合成文本块直接验证**几何与语义逻辑**（列网格、行聚类、名称合并、脱敏），
再加上一层**接口边界**测试（媒体类型 / 长度 / 空文件 / 不可解码）。

⛔ 全部测试都不注入"假识别结果"：要么构造文本块做逻辑验证，
   要么验证 fail-closed 边界。
"""

from __future__ import annotations

import pytest

from app.services.transcript_ocr_ingest import (
    ERROR_LENGTH_MISMATCH,
    ERROR_LENGTH_REQUIRED,
    ERROR_TOO_LARGE,
    ERROR_UNSUPPORTED_MEDIA_TYPE,
    JPEG_MEDIA_TYPE,
    MAX_IMAGE_BYTES,
    OCRBlock,
    PNG_MEDIA_TYPE,
    TranscriptImageRejected,
    _build_candidates,
    _classify_row,
    _clean_name,
    _detect_grid,
    _group_rows,
    _is_footer,
    _is_pii,
    _split_leading_continuation,
    normalize_image_media_type,
    validate_image_bytes,
)


def block(
    text: str,
    x: float,
    y: float,
    *,
    width: float = 40.0,
    height: float = 12.0,
    confidence: float = 0.9,
) -> OCRBlock:
    """构造一个文本块（包围盒以中心为准）。"""

    return OCRBlock(
        text=text,
        confidence=confidence,
        center_x=x,
        center_y=y,
        left=x - width / 2,
        top=y - height / 2,
        right=x + width / 2,
        bottom=y + height / 2,
    )


# --------------------------------------------------------------------------- #
# 一、接口边界（fail closed）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", [None, "", "   ", "image/gif", "application/pdf", "text/plain"])
def test_unsupported_media_types_are_rejected(value: object) -> None:
    with pytest.raises(TranscriptImageRejected) as error:
        normalize_image_media_type(value)
    assert error.value.code == ERROR_UNSUPPORTED_MEDIA_TYPE


@pytest.mark.parametrize("value", [PNG_MEDIA_TYPE, JPEG_MEDIA_TYPE, "image/webp", "image/png; charset=x"])
def test_supported_media_types_are_accepted(value: str) -> None:
    assert normalize_image_media_type(value)


def test_missing_declared_length_is_rejected() -> None:
    with pytest.raises(TranscriptImageRejected) as error:
        validate_image_bytes(b"x", declared_length=None, media_type=PNG_MEDIA_TYPE)
    assert error.value.code == ERROR_LENGTH_REQUIRED


def test_length_mismatch_is_rejected() -> None:
    with pytest.raises(TranscriptImageRejected) as error:
        validate_image_bytes(b"xyz", declared_length=2, media_type=PNG_MEDIA_TYPE)
    assert error.value.code == ERROR_LENGTH_MISMATCH


def test_oversized_declared_length_is_rejected_before_reading() -> None:
    with pytest.raises(TranscriptImageRejected) as error:
        validate_image_bytes(
            b"", declared_length=MAX_IMAGE_BYTES + 1, media_type=PNG_MEDIA_TYPE
        )
    assert error.value.code == ERROR_TOO_LARGE


# --------------------------------------------------------------------------- #
# 二、隐私边界
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        "姓名：王靖贻",
        "学号：25303069",
        "学院：网络空间安全学院",
        "专业：25级网络空间安全（网络空间安全学院）",
        "年级：2025",
        "入校时间：2025-08",
        "离校时间：",
        "学制：4",
    ],
)
def test_personal_identity_blocks_are_detected(text: str) -> None:
    assert _is_pii(text)


@pytest.mark.parametrize("text", ["线性代数", "军事课", "程序设计", "大学英语"])
def test_course_names_are_not_treated_as_pii(text: str) -> None:
    assert not _is_pii(text)


@pytest.mark.parametrize(
    "text",
    ["学分20.5(必修)1(专选）", "绩点(必、专选)3.6", "4.0-5.0（优秀4.5)", "2026年10月07日印制"],
)
def test_summary_and_footer_lines_are_rejected(text: str) -> None:
    assert _is_footer(text)


# --------------------------------------------------------------------------- #
# 三、列网格推断（由数据行几何推导）
# --------------------------------------------------------------------------- #


def _transcript_blocks() -> list[OCRBlock]:
    """构造一份**结构等价于真实成绩单**的文本块集合。

    列位置与真实卷面同量级：名称 ~62、学分 ~349、成绩 ~439、属性 ~530。
    """

    blocks: list[OCRBlock] = []
    # 表头（含属性标题）
    blocks += [
        block("课程名称", 168, 193),
        block("学分", 349, 193),
        block("成绩", 439, 193),
        block("属性", 530, 207),
    ]
    # 学期行
    blocks.append(block("2025-2026学年第一学期", 288, 230, width=200))
    rows = [
        ("线性代数", None, "97", "专必", 254),
        ("高等数学一（I）", None, "82", "专必", 276),
        ("三维遥感技术导论", "1. 5", "87", "专必", 300),
        ("军事课", "4", "82", "公必", 392),
    ]
    for name, credit, grade, attribute, y in rows:
        blocks.append(block(name, 62, y, width=max(len(name) * 14, 40)))
        if credit is not None:
            blocks.append(block(credit, 349, y))
        blocks.append(block(grade, 439, y))
        blocks.append(block(attribute, 530, y))
    return blocks


def test_grid_is_derived_from_data_rows() -> None:
    grid = _detect_grid(_transcript_blocks())
    assert grid is not None
    # 列顺序必须是 名称 < 学分 < 成绩 < 属性
    assert grid.name_x < grid.grade_x < grid.attribute_x
    if grid.credit_x is not None:
        assert grid.name_x < grid.credit_x < grid.grade_x


def test_grid_requires_attribute_anchor() -> None:
    """⛔ 没有属性标记就无法定位行边界 ⇒ 判为版面不可解析，⛔ 不猜。"""

    blocks = [
        block("课程名称", 168, 193),
        block("学分", 349, 193),
        block("成绩", 439, 193),
        block("线性代数", 62, 254),
    ]
    assert _detect_grid(blocks) is None


# --------------------------------------------------------------------------- #
# 四、行分类与候选构造（内容语义，⛔ 不靠 x 容差）
# --------------------------------------------------------------------------- #


def test_row_with_attribute_is_a_course_row() -> None:
    grid = _detect_grid(_transcript_blocks())
    assert grid is not None
    row = [block("线性代数", 62, 254), block("97", 439, 254), block("专必", 530, 254)]
    kind, names, credit, grade, term = _classify_row(row, grid)
    assert kind == "course"
    assert "".join(b.text for b in names) == "线性代数"
    assert grade is not None and grade.text == "97"
    assert credit is None
    assert term is None


def test_credit_is_the_number_left_of_the_grade() -> None:
    grid = _detect_grid(_transcript_blocks())
    assert grid is not None
    row = [
        block("三维遥感技术导论", 62, 300),
        block("1. 5", 349, 300),
        block("87", 439, 300),
        block("专必", 530, 300),
    ]
    kind, _, credit, grade, _ = _classify_row(row, grid)
    assert kind == "course"
    assert credit is not None and credit.text == "1. 5"
    assert grade is not None and grade.text == "87"


def test_name_only_row_is_a_continuation() -> None:
    grid = _detect_grid(_transcript_blocks())
    assert grid is not None
    row = [block("发现", 42, 136)]
    kind, names, _, _, _ = _classify_row(row, grid)
    assert kind == "continuation"
    assert [b.text for b in names] == ["发现"]


def test_term_row_is_recognized() -> None:
    grid = _detect_grid(_transcript_blocks())
    assert grid is not None
    row = [block("2025-2026学年第一学期", 288, 230, width=200)]
    kind, _, _, _, term = _classify_row(row, grid)
    assert kind == "term"
    assert term == "2025-2026学年第一学期"


def test_leading_short_fragment_is_split_off() -> None:
    """`发现` + `四史 (新中国史)` 同行 ⇒ 前者是上一门课的折断残片。"""

    leading, name = _split_leading_continuation(
        [block("发现", 42, 350), block("四史 (新中国史)", 92, 350, width=120)]
    )
    assert leading == "发现"
    assert name == "四史 (新中国史)"


def test_numeric_tail_fragment_is_dropped_from_name() -> None:
    """页脚分档（`60-69`）会被 OCR 归到名称列尾部，必须剔除。"""

    _, name = _split_leading_continuation(
        [block("多元风格下的吉他音乐导赏", 134, 900, width=200), block("60-69", 300, 900)]
    )
    assert name == "多元风格下的吉他音乐导赏"


def test_clean_name_removes_glued_digits_but_keeps_chinese() -> None:
    assert _clean_name("遇见人工智能-01") == "遇见人工智能"
    assert _clean_name("线性代数") == "线性代数"
    assert _clean_name("大学英语") == "大学英语"


def test_build_candidates_merges_name_continuation() -> None:
    """数据行之后的续行必须并入前一条候选（否则课程名被截断）。"""

    grid = _detect_grid(_transcript_blocks())
    assert grid is not None
    rows = _group_rows(_transcript_blocks())
    candidates, _ = _build_candidates(rows, grid)
    names = [item.course_name for item in candidates]
    assert "线性代数" in names
    assert "三维遥感技术导论" in names


def test_candidates_never_carry_course_id_or_status() -> None:
    """⛔ 硬约束：识别层不产出课程号，也不产出任何 MakeupStatus。"""

    grid = _detect_grid(_transcript_blocks())
    assert grid is not None
    candidates, _ = _build_candidates(_group_rows(_transcript_blocks()), grid)
    for item in candidates:
        assert not hasattr(item, "course_id")
        assert not hasattr(item, "status")
        # 每条候选都必须带上"为什么仍需确认"
        assert item.unconfirmed


def test_candidate_marks_missing_credit_as_unconfirmed() -> None:
    grid = _detect_grid(_transcript_blocks())
    assert grid is not None
    candidates, _ = _build_candidates(_group_rows(_transcript_blocks()), grid)
    linear = next(item for item in candidates if item.course_name == "线性代数")
    assert linear.credit is None
    assert any("学分" in reason for reason in linear.unconfirmed)
