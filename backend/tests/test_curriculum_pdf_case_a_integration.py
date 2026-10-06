"""Prove the transcript PDF actually drives the existing Case A Curriculum analysis.

```text
成绩单 PDF → CompletedCourse[] → 既有 Curriculum 匹配 / 投影 → MakeupTask[]
```

⛔ 本测试⛔ 不重写任何匹配规则：它只把 PDF 放进既有 `completed` 输入位，
其余全部交给 `app/curriculum` 的既有实现。
⛔ 所有课程 / 学期 / 成绩都是虚构的（见 `pdf_fixtures.py`）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.curriculum.case import CurriculumCaseProvider, load_curriculum_case
from app.curriculum.completed_courses import CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import MakeupStatus
from app.curriculum.pdf_reader import load_completed_courses_pdf
from tests import pdf_fixtures as fixtures

#: Case A 语境（2025 级 遥感科学与技术 → 网络空间安全），但课程数据全部虚构。
OLD_MAJOR = "示例原专业（遥感类）"
NEW_MAJOR = "示例目标专业（网络空间安全类）"
COHORT = "2025"
COMPLETED_SOURCE = "demo://case-a/pdf-transcript"


def _course(
    course_id: str,
    name: str,
    credit: float,
    *,
    requirement: str = "required",
    prerequisites: list[str] | None = None,
) -> dict[str, object]:
    return {
        "course_id": course_id,
        "course_name": name,
        "credit": credit,
        "requirement": requirement,
        "source_record": f"row:{course_id}",
        "prerequisites": prerequisites,
        "deadline_semester": 5,
        "recommended_semester": 3,
    }


def _case_payload(pdf_path: Path | None, *, completed_complete: bool = True) -> dict[str, object]:
    completed: dict[str, object] = {
        "source_id": COMPLETED_SOURCE,
        "complete": completed_complete,
        "completeness_evidence": "demo://case-a/pdf-transcript/完整范围说明",
    }
    if pdf_path is not None:
        completed["pdf"] = {"path": pdf_path.name}
    else:
        completed["records"] = []

    return {
        "data_source": "mock",
        "old": {
            "version_id": "demo-old",
            "major": OLD_MAJOR,
            "cohort": COHORT,
            "source_id": "demo://case-a/old",
            "complete": True,
            "completeness_evidence": "demo://case-a/old/完整范围说明",
            "course_records": [
                _course("DEMO-OLD-101", "示例旧专业基础课", 3.0),
            ],
        },
        "new": {
            "version_id": "demo-new",
            "major": NEW_MAJOR,
            "cohort": COHORT,
            "source_id": "demo://case-a/new",
            "complete": True,
            "completeness_evidence": "demo://case-a/new/完整范围说明",
            "course_records": [
                # 与成绩单**同名同学分**：成绩单没有课程号 ⇒ 不得自动抵认。
                _course("TGT-ALG", "示例线性代数", 3.0),
                # 成绩单里只修了 2 学分，目标要求 3 学分 ⇒ 不得自动抵认。
                _course("TGT-PHY", "示例大学物理", 3.0),
                # 成绩单里完全没有 ⇒ 缺课。
                _course("TGT-NET", "示例网络原理", 4.0),
            ],
        },
        "completed": completed,
    }


def _write_case(tmp_path: Path, payload: dict[str, object], name: str = "case.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _tasks_by_name(case) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {task.course_name: task for task in CurriculumCaseProvider(case).get_makeup_tasks()}


# --- PDF 真的进入了既有管线 ---


def test_pdf_completed_courses_reach_the_existing_curriculum_matcher(tmp_path: Path) -> None:
    fixtures.build_case_a_transcript_pdf(tmp_path / "DEMO-transcript.pdf")
    case = load_curriculum_case(_write_case(tmp_path, _case_payload(tmp_path / "DEMO-transcript.pdf")))

    assert len(case.completed) == 4
    assert all(record.course_id is None for record in case.completed)
    assert all(
        record.course_id_status is CourseIdStatus.PENDING for record in case.completed
    )

    tasks = CurriculumCaseProvider(case).get_makeup_tasks()
    assert tasks, "PDF 已修课程必须真正参与 Case A 分析并产出补修任务"
    assert {task.course_name for task in tasks} == {
        "示例线性代数", "示例大学物理", "示例网络原理",
    }


def test_pdf_input_changes_the_projection_evidence(tmp_path: Path) -> None:
    """同一份培养方案，PDF 与空已修记录必须给出**不同**的判定依据。"""

    fixtures.build_case_a_transcript_pdf(tmp_path / "DEMO-transcript.pdf")
    with_pdf = load_curriculum_case(
        _write_case(tmp_path, _case_payload(tmp_path / "DEMO-transcript.pdf"), "with-pdf.json")
    )
    empty = load_curriculum_case(_write_case(tmp_path, _case_payload(None), "no-pdf.json"))

    pdf_tasks = _tasks_by_name(with_pdf)
    empty_tasks = _tasks_by_name(empty)
    assert set(pdf_tasks) == set(empty_tasks)

    referenced = [
        name for name, task in pdf_tasks.items()
        if task.source_evidence and COMPLETED_SOURCE in task.source_evidence
    ]
    assert referenced, "补修任务必须带上成绩单来源引用，否则无法证明 PDF 参与了分析"
    assert "示例线性代数" in referenced or "示例大学物理" in referenced
    # 空已修记录里没有任何成绩单修读记录可引用。
    assert all(
        COMPLETED_SOURCE not in (task.source_evidence or "") or "pdf:" not in (task.source_evidence or "")
        for task in empty_tasks.values()
    )


# --- 保守语义（⛔ 不做模糊姓名自动抵认） ---


def test_same_name_without_course_id_is_not_auto_satisfied(tmp_path: Path) -> None:
    fixtures.build_case_a_transcript_pdf(tmp_path / "DEMO-transcript.pdf")
    case = load_curriculum_case(_write_case(tmp_path, _case_payload(tmp_path / "DEMO-transcript.pdf")))
    tasks = _tasks_by_name(case)

    # 姓名完全相同的 `示例线性代数` ⛔ 不得因为名字相似就变成 satisfied。
    assert tasks["示例线性代数"].status is MakeupStatus.MANUAL_CONFIRMATION
    assert tasks["示例大学物理"].status is MakeupStatus.MANUAL_CONFIRMATION
    assert all(task.status is not MakeupStatus.SATISFIED for task in tasks.values())


def test_passed_course_is_never_marked_as_required_makeup(tmp_path: Path) -> None:
    """成绩单里已通过的课不得被直接判成"必须补修"。"""

    fixtures.build_case_a_transcript_pdf(tmp_path / "DEMO-transcript.pdf")
    case = load_curriculum_case(_write_case(tmp_path, _case_payload(tmp_path / "DEMO-transcript.pdf")))
    tasks = _tasks_by_name(case)
    for name in ("示例线性代数", "示例大学物理"):
        assert tasks[name].status is not MakeupStatus.REQUIRED


def test_pdf_only_course_does_not_create_a_makeup_task(tmp_path: Path) -> None:
    """成绩单里有、但目标方案没有的课（示例观测实践）不得凭空生成补修任务。"""

    fixtures.build_case_a_transcript_pdf(tmp_path / "DEMO-transcript.pdf")
    case = load_curriculum_case(_write_case(tmp_path, _case_payload(tmp_path / "DEMO-transcript.pdf")))
    assert "示例观测实践" not in _tasks_by_name(case)


# --- seam 行为 ---


def test_seam_is_exclusive_and_requires_a_real_path(tmp_path: Path) -> None:
    fixtures.build_case_a_transcript_pdf(tmp_path / "DEMO-transcript.pdf")
    payload = _case_payload(tmp_path / "DEMO-transcript.pdf")
    assert isinstance(payload["completed"], dict)
    payload["completed"]["records"] = []  # type: ignore[index]
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_case(_write_case(tmp_path, payload, "both.json"))


def test_missing_pdf_file_fails_closed(tmp_path: Path) -> None:
    payload = _case_payload(tmp_path / "DEMO-absent.pdf")
    with pytest.raises(CurriculumNormalizationError):
        load_curriculum_case(_write_case(tmp_path, payload, "absent.json"))


def test_xlsx_path_still_available_and_unrelated_to_pdf(tmp_path: Path) -> None:
    """XLSX 仍是兼容的次要路径：`completed` 的三种输入形式互斥且都合法。"""

    from tests import xlsx_fixtures

    workbook = xlsx_fixtures.write(tmp_path, xlsx_fixtures.valid_bytes())
    payload = _case_payload(None)
    assert isinstance(payload["completed"], dict)
    payload["completed"].pop("records")
    payload["completed"]["xlsx"] = {"path": workbook.name}
    case = load_curriculum_case(_write_case(tmp_path, payload, "xlsx.json"))
    assert len(case.completed) == 3


# --- 与解析层一致 ---


def test_completed_records_match_the_parsed_transcript(tmp_path: Path) -> None:
    path = fixtures.build_case_a_transcript_pdf(tmp_path / "DEMO-transcript.pdf")
    courses = load_completed_courses_pdf(path, source_id=COMPLETED_SOURCE)
    case = load_curriculum_case(_write_case(tmp_path, _case_payload(path)))

    assert [(c.course_name, c.credit, c.semester) for c in case.completed] == [
        (c.course_name, c.credit, c.semester) for c in courses
    ]
    assert {c.semester for c in case.completed} == {
        fixtures.TERM_ONE.replace(" ", ""), fixtures.TERM_TWO.replace(" ", ""),
    }
