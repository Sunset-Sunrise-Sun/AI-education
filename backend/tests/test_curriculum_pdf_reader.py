"""Exercise the verified SYSU transcript PDF reader with synthetic documents.

⛔ 全部课程 / 成绩 / 学期 / 学生信息都是**虚构的**（见 `pdf_fixtures.py`），
只验证版面解析与 fail-closed 行为，⛔ 不代表任何真实成绩单数据。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.curriculum.completed_courses import CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_reader import (
    load_completed_courses_pdf,
    parse_transcript_pdf,
    parse_transcript_pdf_bytes,
)
from tests import pdf_fixtures as fixtures

TERM_ONE = fixtures.TERM_ONE
TERM_TWO = fixtures.TERM_TWO


def _parse(tmp_path: Path, **kwargs: object):
    path = fixtures.build_transcript_pdf(
        tmp_path / "DEMO-transcript.pdf", bands=fixtures.fictional_transcript(), **kwargs
    )
    return parse_transcript_pdf(path)


# --- 正常路径 ---


def test_verified_layout_yields_term_course_credit_grade_and_attribute(tmp_path: Path) -> None:
    parsed = _parse(tmp_path)
    assert [record.course_name for record in parsed.records] == [
        "示例线性代数", "示例高等数学", "示例实践课：综合观测与探究方法",
        "示例大学英语", "示例程序设计", "示例通识课",
    ]
    assert [record.credit for record in parsed.records] == [3.0, 5.0, 1.5, 2.0, 2.0, 1.0]
    assert [record.grade for record in parsed.records] == ["97", "82", "87", "P", "95", "NP"]
    assert [record.course_attribute for record in parsed.records] == [
        "专必", "专必", "专选", "公必", "专必", "公选",
    ]
    assert parsed.page_count == 1
    assert parsed.columns_seen == 4


def test_wrapped_course_name_is_rejoined(tmp_path: Path) -> None:
    parsed = _parse(tmp_path)
    names = [record.course_name for record in parsed.records]
    assert "示例实践课：综合观测与探究方法" in names
    # 续行不得变成一门单独的课。
    assert "方法" not in names
    wrapped = next(record for record in parsed.records if record.course_name.endswith("方法"))
    assert (wrapped.credit, wrapped.grade) == (1.5, "87")


def test_decimal_credit_is_preserved(tmp_path: Path) -> None:
    parsed = _parse(tmp_path)
    decimal = [record for record in parsed.records if record.credit == 1.5]
    assert len(decimal) == 1
    assert decimal[0].course_name == "示例实践课：综合观测与探究方法"


def test_numeric_and_pass_fail_grades_are_kept_verbatim(tmp_path: Path) -> None:
    parsed = _parse(tmp_path)
    by_name = {record.course_name: record.grade for record in parsed.records}
    assert by_name["示例线性代数"] == "97"
    assert by_name["示例大学英语"] == "P"
    assert by_name["示例通识课"] == "NP"


def test_multiple_terms_are_grouped_in_reading_order(tmp_path: Path) -> None:
    parsed = _parse(tmp_path)
    assert parsed.terms == (
        TERM_ONE.replace(" ", ""),
        TERM_TWO.replace(" ", ""),
    )
    first_term = [r for r in parsed.records if r.term == TERM_ONE.replace(" ", "")]
    second_term = [r for r in parsed.records if r.term == TERM_TWO.replace(" ", "")]
    assert [r.course_name for r in first_term] == [
        "示例线性代数", "示例高等数学", "示例实践课：综合观测与探究方法", "示例大学英语",
    ]
    assert [r.course_name for r in second_term] == ["示例程序设计", "示例通识课"]


# --- 汇总行 / 页脚必须被拒绝 ---


def test_footer_summary_and_statistics_are_never_courses(tmp_path: Path) -> None:
    parsed = _parse(tmp_path, extra_footer_lines=("国家学生体质健康标准：合格",))
    names = [record.course_name for record in parsed.records]
    joined = "".join(names)
    for forbidden in (
        "毕业论文", "毕业应得", "实得学分", "平均绩点", "评分体系", "审核人",
        "体质健康", "必修", "专选",
    ):
        assert forbidden not in joined, f"页脚 / 汇总文本被当成了课程：{forbidden}"
    assert parsed.skipped_footer_lines > 0


def test_per_term_summary_line_is_not_a_course(tmp_path: Path) -> None:
    parsed = _parse(tmp_path)
    assert all("学分" not in record.course_name for record in parsed.records)
    assert all("绩点" not in record.course_name for record in parsed.records)


def test_numeric_footer_row_does_not_become_a_course(tmp_path: Path) -> None:
    parsed = _parse(tmp_path, extra_footer_lines=("12 34 56 78",))
    assert all(record.course_name != "12" for record in parsed.records)


# --- fail closed ---


def test_malformed_pdf_fails_closed() -> None:
    with pytest.raises(CurriculumNormalizationError):
        parse_transcript_pdf_bytes(b"%PDF-1.7\nthis is not a real pdf")


def test_empty_and_non_pdf_input_fail_closed() -> None:
    with pytest.raises(CurriculumNormalizationError):
        parse_transcript_pdf_bytes(b"")
    with pytest.raises(CurriculumNormalizationError):
        parse_transcript_pdf_bytes(b"not a pdf at all")
    with pytest.raises(CurriculumNormalizationError):
        parse_transcript_pdf_bytes("a string, not bytes")


def test_missing_course_table_fails_closed(tmp_path: Path) -> None:
    import pymupdf

    path = tmp_path / "DEMO-no-table.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "中山大学本科生成绩单", fontname="china-s", fontsize=10)
    page.insert_text((72, 96), "示例说明文字，没有课程表格。", fontname="china-s", fontsize=10)
    document.save(str(path))
    document.close()

    with pytest.raises(CurriculumNormalizationError) as error:
        parse_transcript_pdf(path)
    assert "header" in str(error.value)


def test_pdf_without_transcript_title_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "DEMO-other.pdf"
    fixtures.build_transcript_pdf(
        path, bands=fixtures.fictional_transcript(), student_block=False
    )
    with pytest.raises(CurriculumNormalizationError) as error:
        parse_transcript_pdf(path)
    assert "title" in str(error.value) or "layout" in str(error.value)


def test_unreadable_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError):
        parse_transcript_pdf(tmp_path / "DEMO-does-not-exist.pdf")
    with pytest.raises(CurriculumNormalizationError):
        parse_transcript_pdf(12345)


# --- 隐私 ---


def test_student_identity_and_gpa_are_never_returned(tmp_path: Path) -> None:
    parsed = _parse(tmp_path)
    blob = json.dumps(
        [[r.term, r.course_name, r.credit, r.grade, r.course_attribute] for r in parsed.records],
        ensure_ascii=False,
    )
    for secret in (
        fixtures.DEMO_STUDENT_NAME,
        fixtures.DEMO_STUDENT_NUMBER,
        "示例学院",
        "示例专业",
        "绩点",
        "3.6",
    ):
        assert secret not in blob, f"个人信息 / 绩点出现在解析结果中：{secret}"


def test_errors_never_echo_input_values(tmp_path: Path) -> None:
    path = tmp_path / "DEMO-broken.pdf"
    # 一个带有人名与学号、但并非合格版面的 PDF。
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), f"姓名: {fixtures.DEMO_STUDENT_NAME}", fontname="china-s", fontsize=10)
    page.insert_text((72, 96), f"学号: {fixtures.DEMO_STUDENT_NUMBER}", fontname="china-s", fontsize=10)
    document.save(str(path))
    document.close()

    with pytest.raises(CurriculumNormalizationError) as error:
        parse_transcript_pdf(path)
    message = str(error.value)
    assert fixtures.DEMO_STUDENT_NAME not in message
    assert fixtures.DEMO_STUDENT_NUMBER not in message
    assert str(path) not in message
    assert "Traceback" not in message


# --- CompletedCourse 投影 ---


def test_projection_never_invents_course_ids(tmp_path: Path) -> None:
    path = fixtures.build_transcript_pdf(
        tmp_path / "DEMO-transcript.pdf", bands=fixtures.fictional_transcript()
    )
    courses = load_completed_courses_pdf(path, source_id="DEMO-TRANSCRIPT-01")
    assert len(courses) == 6
    for course in courses:
        assert course.course_id is None
        assert course.course_id_status is CourseIdStatus.PENDING
        assert course.id_match_source is None
        assert course.source_id == "DEMO-TRANSCRIPT-01"


def test_projection_maps_terms_attributes_and_pass_facts(tmp_path: Path) -> None:
    path = fixtures.build_transcript_pdf(
        tmp_path / "DEMO-transcript.pdf", bands=fixtures.fictional_transcript()
    )
    courses = load_completed_courses_pdf(path, source_id="DEMO-TRANSCRIPT-01")
    by_name = {course.course_name: course for course in courses}

    assert by_name["示例线性代数"].semester == TERM_ONE.replace(" ", "")
    assert by_name["示例线性代数"].course_type == "专必"
    assert by_name["示例线性代数"].credit == 3.0
    assert by_name["示例线性代数"].passed is True
    assert by_name["示例大学英语"].passed is True
    # NP ⇒ 未通过；⛔ 不推断其它原因。
    assert by_name["示例通识课"].passed is False
    assert by_name["示例程序设计"].semester == TERM_TWO.replace(" ", "")
    assert [course.source_record for course in courses] == [f"pdf:{i}" for i in range(1, 7)]


def test_projection_requires_a_source_id(tmp_path: Path) -> None:
    path = fixtures.build_transcript_pdf(
        tmp_path / "DEMO-transcript.pdf", bands=fixtures.fictional_transcript()
    )
    with pytest.raises(CurriculumNormalizationError):
        load_completed_courses_pdf(path, source_id="")
