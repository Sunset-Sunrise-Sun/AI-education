"""Real Case A scope decisions: range terms decided per requirement entry.

The target plan prints some arrangement terms as ranges, which the strict parser
refuses to interpret. Case A fixes ``as_of_term = "2025-2"`` by **case-owner
confirmation** (not school policy), and each range-term entry is decided on its
own wording:

- a range entirely after the cut-off -> ``future``;
- a range crossing the cut-off -> undecided, needs business confirmation;
- a range-term entry that is already satisfied needs no decision at all.

These are case data, never algorithm rules: no course id, term string or major
name is hard-coded anywhere in the scope machinery.

Existing coverage is reused rather than duplicated: ``test_curriculum_scope_decisions.py``
already proves that unresolved+undecided blocks, that a decision discharges an
unresolved entry in both directions, that satisfied+unresolved does not block,
``target_source_record`` binding, the single-term conflict, and invalid-decision
rejection. This module adds the Case A decision set itself plus the integration
properties it must not disturb.
"""

from __future__ import annotations

import pytest

from app.curriculum.case_a_decisions import (
    AS_OF_TERM,
    CASE_TARGET_VERSION_ID,
    CONFIRMED_SCOPE_DECISIONS,
    DECISION_EVIDENCE,
    SATISFIED_UNRESOLVED_NO_DECISION,
    UNDECIDED_CROSSING_CUTOFF,
    confirmed_scope_decisions,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.plan_profiles import ELECTIVE_POOL_GROUP_ID, plan_group_records

from tests.test_curriculum_scope_decisions import _completed, _course, _payload, _provider

# --------------------------------------------------------------------------
# The decision set itself (declarative, reviewable without reading the document)
# --------------------------------------------------------------------------


def test_case_a_cutoff_is_the_owner_confirmed_term() -> None:
    assert AS_OF_TERM == "2025-2"


def test_only_ranges_entirely_after_the_cutoff_are_decided_future() -> None:
    assert len(CONFIRMED_SCOPE_DECISIONS) == 3
    for record in CONFIRMED_SCOPE_DECISIONS:
        assert record["decision"] == "future"
        start, end = record["recommended_term_text"].split("~")
        assert start > AS_OF_TERM and end > AS_OF_TERM, record


def test_the_crossing_range_is_deliberately_undecided() -> None:
    """2025-1~2028-2 spans the cut-off, so no decision may be recorded for it."""
    crossing = UNDECIDED_CROSSING_CUTOFF
    start, end = crossing["recommended_term_text"].split("~")
    assert start <= AS_OF_TERM < end, "the undecided entry must actually cross"
    decided_ids = {record["target_course_id"] for record in CONFIRMED_SCOPE_DECISIONS}
    assert crossing["course_id"] not in decided_ids
    assert crossing["question"]


def test_satisfied_range_terms_need_no_decision() -> None:
    satisfied_ids = {
        course_id for _record, course_id, _term, _name in SATISFIED_UNRESOLVED_NO_DECISION
    }
    decided_ids = {record["target_course_id"] for record in CONFIRMED_SCOPE_DECISIONS}
    assert satisfied_ids and not (satisfied_ids & decided_ids)


def test_decisions_carry_case_owner_evidence_bound_to_the_target_version() -> None:
    for record in CONFIRMED_SCOPE_DECISIONS:
        assert record["target_version_id"] == CASE_TARGET_VERSION_ID
        assert record["evidence"] == DECISION_EVIDENCE
        assert record["evidence"].startswith("case-owner-confirmed://")
        assert "official-policy://" not in record["evidence"]
        assert record["target_source_record"]  # bound to a requirement entry


def test_decisions_build_into_internal_objects() -> None:
    built = confirmed_scope_decisions()
    assert len(built) == len(CONFIRMED_SCOPE_DECISIONS)
    assert {decision.decision for decision in built} == {"future"}
    assert {decision.target_source_record for decision in built} == {
        record["target_source_record"] for record in CONFIRMED_SCOPE_DECISIONS
    }


# --------------------------------------------------------------------------
# Integration: what a Case A style decision must and must not disturb
# --------------------------------------------------------------------------

def _decision_payload(**overrides):
    """A synthetic case carrying one Case A style future decision."""
    defaults = {
        "new_courses": [_course("A1", "a1", 3, term="2026-1~2026-2")],
        "decisions": [{
            "target_version_id": "mock-new",
            "target_source_record": "row:A1",
            "target_course_id": "A1",
            "decision": "future",
            "evidence": DECISION_EVIDENCE,
        }],
    }
    defaults.update(overrides)
    return _payload(**defaults)


def test_case_a_decisions_do_not_disturb_the_elective_group() -> None:
    """Deciding range terms must not touch the target plan's group model."""
    records = plan_group_records("target")
    assert len(records) == 1
    assert records[0]["group_id"] == ELECTIVE_POOL_GROUP_ID
    assert records[0]["minimum_credit"] == 23
    assert all(
        record["target_course_id"] != ELECTIVE_POOL_GROUP_ID
        for record in CONFIRMED_SCOPE_DECISIONS
    )


def test_decisions_are_bound_to_the_requirement_entry_not_the_course_id() -> None:
    """Two entries sharing a course_id: only the decided entry is discharged."""
    first = _course("A1", "a1", 3, term="2025-1~2025-2")
    second = _course("A1", "a1b", 3, term="2025-1~2028-2")
    second["source_record"] = "row:A1-B"
    payload = _payload(
        new_courses=[first, second],
        decisions=[{
            "target_version_id": "mock-new", "target_source_record": "row:A1-B",
            "target_course_id": "A1", "decision": "future", "evidence": DECISION_EVIDENCE,
        }],
    )
    provider = _provider(payload)
    diff = provider.get_curriculum_diff()
    assert diff.scope_bucket_for_entry("row:A1-B") == "future"
    # The sibling row is untouched and still blocks.
    assert diff.scope_bucket_for_entry("row:A1") == "unresolved"
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        provider.get_makeup_tasks()


def test_case_a_style_decisions_do_not_change_exact_matching() -> None:
    """A scope decision never turns a satisfied identity match into something else."""
    payload = _payload(
        new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
        completed=[_completed("A1", "a1", 3)],
        decisions=[{
            "target_version_id": "mock-new", "target_source_record": "row:A1",
            "target_course_id": "A1", "decision": "future", "evidence": DECISION_EVIDENCE,
        }],
    )
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "future"
    # The satisfied identity match keeps its status even though the entry is future.
    assert [(task.course_id, task.status.value) for task in provider.get_makeup_tasks()] == [
        ("A1", "satisfied"),
    ]


def test_future_unmet_requirement_is_absent_from_the_projected_tasks() -> None:
    """Deciding an unmet entry 'future' must remove it from the makeup output."""
    provider = _provider(_decision_payload())
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "future"
    assert provider.get_makeup_tasks() == []


def test_deciding_one_entry_does_not_excuse_another() -> None:
    """Case A's remaining crossing range must still block on its own."""
    payload = _payload(
        new_courses=[_course("A1", "a1", 3, term="2026-1~2026-2"),
                     _course("A2", "a2", 3, term="2025-1~2028-2")],
        decisions=[{
            "target_version_id": "mock-new", "target_source_record": "row:A1",
            "target_course_id": "A1", "decision": "future", "evidence": DECISION_EVIDENCE,
        }],
    )
    provider = _provider(payload)
    diff = provider.get_curriculum_diff()
    assert diff.scope_bucket_for_entry("row:A1") == "future"
    assert diff.unresolved_scope_entries() == ("row:A2",)
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        provider.get_makeup_tasks()


def test_satisfied_range_term_alone_does_not_block_projection() -> None:
    """Case A's three already-satisfied range entries need no decision."""
    payload = _payload(
        new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
        completed=[_completed("A1", "a1", 3)],
    )
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "unresolved"
    assert [(task.course_id, task.status.value) for task in provider.get_makeup_tasks()] == [
        ("A1", "satisfied"),
    ]
