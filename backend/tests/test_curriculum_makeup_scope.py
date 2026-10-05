"""Historical makeup scope: only explicit, evidence-backed term boundaries.

These tests lock the behaviour that distinguishes:

- courses the target curriculum expected before the confirmed transfer cut-off
  (historical gaps, candidates for ``MakeupTask``), from
- courses the target curriculum schedules afterwards (future normal plan, which
  must stay out of the current makeup list), from
- entries whose arrangement term cannot be interpreted (unresolved: fail closed,
  never guessed in either direction).

No test here consults the system date, invents a school policy, or approves a
course equivalence.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.curriculum.case import (
    DEMO_CASE_PATH,
    CurriculumCaseProvider,
    normalize_curriculum_case,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import MakeupScope, build_curriculum_diff
from app.curriculum.requirements import normalize_curriculum_version
from app.curriculum.terms import (
    SCOPE_FUTURE,
    SCOPE_HISTORICAL,
    SCOPE_UNRESOLVED,
    AcademicTerm,
    classify_term,
    parse_academic_term,
)

SCOPED_CASE_PATH = DEMO_CASE_PATH.parent / "scoped_case.json"


def _input() -> dict:
    return json.loads(SCOPED_CASE_PATH.read_text(encoding="utf-8"))


def _provider(payload: dict) -> CurriculumCaseProvider:
    return CurriculumCaseProvider(normalize_curriculum_case(payload))


def _tasks(payload: dict):
    return _provider(payload).get_makeup_tasks()


def _set_term(payload: dict, course_id: str, term) -> None:
    (record,) = [row for row in payload["new"]["course_records"] if row["course_id"] == course_id]
    record["recommended_term_text"] = term


def _stub_version(terms: list) -> object:
    return normalize_curriculum_version(
        version_id="scope-stub", major="stub", cohort="stub", source_id="mock://scope-stub",
        complete=True, completeness_evidence="mock://scope-stub/complete",
        course_records=[
            {
                "course_id": f"STUB{index}", "course_name": f"stub {index}", "credit": 1,
                "requirement": "required", "source_record": f"row:{index}",
                "recommended_term_text": term,
            }
            for index, term in enumerate(terms)
        ],
    )


# --------------------------------------------------------------------------
# Term parser / comparator
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["2025-1", "2025-2", "2026-1", "1999-2"])
def test_confirmed_canonical_terms_parse(text: str) -> None:
    assert str(parse_academic_term(text)) == text


@pytest.mark.parametrize("value", [
    None, "", "   ", "2025-1 ", " 2025-1", "2025-3", "2025-0", "25-1", "2025/1",
    "2025年第一学期", "未知", "空", "DEMO-PRIVATE-TERM", 2025, 20251, ["2025-1"], {"term": "2025-1"},
])
def test_unknown_blank_and_malformed_terms_never_parse(value) -> None:
    assert parse_academic_term(value) is None


@pytest.mark.parametrize("text", ["2025-1~2025-2", "2025-1~2028-2", "2025-1-2025-2", "2025-1、2025-2"])
def test_range_terms_are_not_silently_interpreted(text: str) -> None:
    """A range is not a single arrangement term; it must stay unresolved."""
    assert parse_academic_term(text) is None


def test_term_ordering_is_year_then_half() -> None:
    assert AcademicTerm(2025, 1).sort_key < AcademicTerm(2025, 2).sort_key
    assert AcademicTerm(2025, 2).sort_key < AcademicTerm(2026, 1).sort_key
    with pytest.raises(CurriculumNormalizationError):
        AcademicTerm(2025, 3)
    with pytest.raises(CurriculumNormalizationError):
        AcademicTerm(True, 1)


def test_boundary_term_is_inclusive_historical() -> None:
    """The as-of term itself counts as historical (documented boundary rule)."""
    as_of = AcademicTerm(2025, 2)
    assert classify_term(AcademicTerm(2025, 2), as_of) == SCOPE_HISTORICAL
    assert classify_term(AcademicTerm(2025, 1), as_of) == SCOPE_HISTORICAL
    assert classify_term(AcademicTerm(2026, 1), as_of) == SCOPE_FUTURE
    assert classify_term(None, as_of) == SCOPE_UNRESOLVED


def test_scope_decisions_never_move_a_course_out_of_unresolved() -> None:
    version = _stub_version(["2025-1", "2026-1", None, "2025-1~2025-2"])
    from app.curriculum.terms import scope_decisions

    decisions = scope_decisions(version, "2025-2")
    assert [decision.bucket for decision in decisions] == [
        SCOPE_HISTORICAL, SCOPE_FUTURE, SCOPE_UNRESOLVED, SCOPE_UNRESOLVED,
    ]
    assert decisions[0].recommended_term_text == "2025-1"


# --------------------------------------------------------------------------
# Historical / future behaviour through the provider
# --------------------------------------------------------------------------

def test_scoped_case_projects_only_the_historical_gap() -> None:
    tasks = _tasks(_input())
    assert [task.course_id for task in tasks] == ["SCOPE101", "SCOPE102"]
    assert [task.status.value for task in tasks] == ["required", "satisfied"]


def test_saved_scoped_output_matches_the_runtime_result() -> None:
    expected = json.loads((SCOPED_CASE_PATH.parent / "scoped_makeup_tasks.json").read_text(encoding="utf-8"))
    provider = CurriculumCaseProvider(normalize_curriculum_case(_input()))
    assert {"data_source": "mock", "makeup_tasks": [
        task.model_dump(mode="json") for task in provider.get_makeup_tasks()
    ]} == expected


def test_historical_required_unmet_is_still_required() -> None:
    tasks = _tasks(_input())
    unmet = [task for task in tasks if task.course_id == "SCOPE101"]
    assert [task.status.value for task in unmet] == ["required"]


def test_historical_required_satisfied_keeps_existing_semantics() -> None:
    tasks = _tasks(_input())
    met = [task for task in tasks if task.course_id == "SCOPE102"]
    assert [task.status.value for task in met] == ["satisfied"]


def test_future_required_unmet_never_becomes_a_current_makeup_task() -> None:
    tasks = _tasks(_input())
    future = [task for task in tasks if task.course_id in {"SCOPE201", "SCOPE202"}]
    assert future == []


def test_future_elective_unmet_never_becomes_a_current_makeup_task() -> None:
    tasks = _tasks(_input())
    assert [task for task in tasks if task.course_id == "SCOPE-E1"] == []


def test_future_required_course_keeps_its_scope_classification_internally() -> None:
    diff = _provider(_input()).get_curriculum_diff()
    assert diff.scope_bucket("SCOPE201") == SCOPE_FUTURE
    assert diff.scope_bucket("SCOPE101") == SCOPE_HISTORICAL
    assert diff.unresolved_scope_courses() == ()
    assert diff.makeup_scope is not None and diff.makeup_scope.as_of_term == "2025-2"


def test_exact_as_of_term_course_is_included() -> None:
    """Boundary case #5: a course recommended for the as-of term is historical."""
    payload = _input()
    _set_term(payload, "SCOPE201", "2025-2")
    diff = _provider(payload).get_curriculum_diff()
    assert diff.scope_bucket("SCOPE201") == SCOPE_HISTORICAL
    assert "SCOPE201" in [task.course_id for task in _tasks(payload)]


def test_one_term_later_than_as_of_excludes_the_course() -> None:
    payload = _input()
    _set_term(payload, "SCOPE101", "2026-1")
    assert "SCOPE101" not in [task.course_id for task in _tasks(payload)]


# --------------------------------------------------------------------------
# Fail-closed behaviour
# --------------------------------------------------------------------------

@pytest.mark.parametrize("term", [None, "", "未知", "空", "2025-1~2025-2", "2025-1~2028-2", "DEMO-PRIVATE-TERM"])
def test_unknown_or_range_arrangement_term_blocks_projection(term) -> None:
    """Cases #6 / #7 / #8: never silently historical and never silently future."""
    payload = _input()
    _set_term(payload, "SCOPE201", term)
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket("SCOPE201") == SCOPE_UNRESOLVED
    with pytest.raises(CurriculumNormalizationError, match="scope") as excinfo:
        provider.get_makeup_tasks()
    if isinstance(term, str) and term:
        assert term not in str(excinfo.value)


@pytest.mark.parametrize("as_of", [None, "", "2025-3", "2025-1~2025-2", "未知", 2025])
def test_unconfirmed_as_of_term_fails_closed(as_of) -> None:
    payload = _input()
    payload["makeup_scope"]["as_of_term"] = as_of
    with pytest.raises(CurriculumNormalizationError):
        _provider(payload)


def test_scope_must_target_the_supplied_curriculum() -> None:
    payload = _input()
    payload["makeup_scope"]["target_version_id"] = "DEMO-OTHER-VERSION"
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        _provider(payload)


def test_scope_input_must_be_complete_and_free_of_extra_fields() -> None:
    for mutate in (
        lambda scope: scope.pop("as_of_term"),
        lambda scope: scope.pop("evidence"),
        lambda scope: scope.__setitem__("DEMO-PRIVATE-FIELD", "DEMO-PRIVATE-VALUE"),
    ):
        payload = _input()
        mutate(payload["makeup_scope"])
        with pytest.raises(CurriculumNormalizationError) as excinfo:
            _provider(payload)
        assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_scope_evidence_is_traceable_in_task_provenance() -> None:
    payload = _input()
    payload["makeup_scope"]["evidence"] = "mock://curriculum-demo/scope-as-of-可追溯依据"
    tasks = _tasks(payload)
    assert tasks and all("mock://" in task.source_evidence for task in tasks)
    assert any(
        "mock://curriculum-demo/scope-as-of-可追溯依据" in task.source_evidence
        for task in tasks if task.status.value == "required"
    )


def test_makeup_scope_rejects_mock_evidence_in_a_real_case() -> None:
    payload = _input()
    payload["data_source"] = "real"
    for key in ("old", "new"):
        payload[key]["source_id"] = "DEMO-REAL-SOURCE"
        payload[key]["completeness_evidence"] = "DEMO-REAL-COMPLETE"
    payload["completed"]["source_id"] = "DEMO-REAL-COMPLETED"
    payload["completed"]["completeness_evidence"] = "DEMO-REAL-COMPLETE"
    payload["rules"]["completed_source_id"] = "DEMO-REAL-COMPLETED"
    payload["rules"]["evidence"] = "DEMO-REAL-RULE"
    payload["elective_selections"][0]["evidence"] = "DEMO-REAL-SELECTION"
    for row in payload["completed"]["records"]:
        row["id_match_source"] = "DEMO-REAL-ID-EVIDENCE"
    payload["makeup_scope"]["evidence"] = "说明: MoCk://DEMO-PRIVATE-SCOPE"
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _provider(payload)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


# --------------------------------------------------------------------------
# Compatibility: no scope supplied keeps the generic MVP behaviour
# --------------------------------------------------------------------------

def test_without_scope_every_target_entry_keeps_the_generic_behaviour() -> None:
    """Case #9: no scope -> original curriculum-diff behaviour, no date guessing."""
    payload = json.loads(DEMO_CASE_PATH.read_text(encoding="utf-8"))
    assert "makeup_scope" not in payload
    provider = CurriculumCaseProvider(normalize_curriculum_case(payload))
    assert provider.get_curriculum_diff().makeup_scope is None
    assert provider.get_curriculum_diff().scope_decisions == ()
    assert [task.status.value for task in provider.get_makeup_tasks()] == [
        "satisfied", "required", "possibly_equivalent", "manual_confirmation", "manual_confirmation",
    ]


def test_without_scope_term_text_alone_changes_nothing() -> None:
    """Recommended terms stay inert unless an explicit scope consumes them."""
    payload = json.loads(DEMO_CASE_PATH.read_text(encoding="utf-8"))
    for record in payload["new"]["course_records"]:
        record["recommended_term_text"] = "2026-2"
    tasks = CurriculumCaseProvider(normalize_curriculum_case(payload)).get_makeup_tasks()
    assert [task.status.value for task in tasks] == [
        "satisfied", "required", "possibly_equivalent", "manual_confirmation", "manual_confirmation",
    ]


def test_scope_decisions_require_an_explicit_scope() -> None:
    payload = json.loads(DEMO_CASE_PATH.read_text(encoding="utf-8"))
    old = normalize_curriculum_version(
        version_id="mock-old", major="m", cohort="c", source_id="mock://curriculum-demo/old",
        complete=True, completeness_evidence="mock://curriculum-demo/old/完整范围说明",
        course_records=payload["old"]["course_records"],
    )
    new = normalize_curriculum_version(
        version_id="mock-new", major="m", cohort="c", source_id="mock://curriculum-demo/new",
        complete=True, completeness_evidence="mock://curriculum-demo/new/完整范围说明",
        course_records=payload["new"]["course_records"],
    )
    diff = build_curriculum_diff(old, new, ())
    assert diff.makeup_scope is None
    assert diff.scope_bucket("DEMO101") is None
    assert diff.unresolved_scope_courses() == ()
    # Scope decisions cannot exist without the explicit scope that produced them.
    scope = MakeupScope(target_version_id="mock-new", as_of_term="2025-2", evidence="mock://scope-as-of")
    scoped = build_curriculum_diff(old, new, (), makeup_scope=scope)
    assert scoped.scope_decisions
    with pytest.raises(CurriculumNormalizationError, match="scope decisions"):
        replace(scoped, makeup_scope=None)


def test_public_provider_signature_is_unchanged() -> None:
    import inspect

    provider = _provider(_input())
    assert list(inspect.signature(provider.get_makeup_tasks).parameters) == []
    # The scope object is not part of the exported provider surface.
    from app.integration.ports import CurriculumProvider

    assert isinstance(provider, CurriculumProvider)
    assert not hasattr(provider, "makeup_scope")


def test_makeup_scope_is_internal_and_not_leaked_to_tasks() -> None:
    tasks = _tasks(_input())
    for task in tasks:
        dumped = task.model_dump(mode="json")
        assert "priority" not in dumped
        assert "makeup_scope" not in dumped
        assert "as_of_term" not in dumped
        assert set(dumped) == {
            "course_id", "course_name", "credit", "status", "deadline_semester",
            "recommended_semester", "prerequisites", "reason", "source_evidence",
        }


def test_makeup_scope_type_is_validated() -> None:
    with pytest.raises(CurriculumNormalizationError):
        MakeupScope(target_version_id="", as_of_term="2025-2", evidence="mock://evidence")
    with pytest.raises(CurriculumNormalizationError):
        MakeupScope(target_version_id="mock-scope-new", as_of_term="2025-2", evidence="   ")
