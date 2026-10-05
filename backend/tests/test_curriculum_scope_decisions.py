"""Round 2: explicit scope decisions, satisfied semantics, and group scope.

Covers the three Architecture Review findings:

A. ``ConfirmedScopeDecision`` — an evidence-backed, per-requirement-entry human
   range decision that discharges an otherwise *unresolved* term, without ever
   silently overriding an unambiguous source term.
B. ``future`` filtering applies only to unmet/pending requirements; an entry
   already confirmed ``satisfied`` keeps its existing public output semantics.
C. Course groups are scope-aware: future-only groups cannot block the historical
   projection, historical-only groups keep their original strict behaviour, and
   a mixed group needs an explicit credit split instead of an invented one.

All data here is artificial Mock data. No school policy, transfer date, term
split, or course equivalence is asserted anywhere.
"""

from __future__ import annotations

import json

import pytest

from app.curriculum.case import DEMO_CASE_PATH, CurriculumCaseProvider, normalize_curriculum_case
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    GROUP_SCOPE_FUTURE,
    GROUP_SCOPE_HISTORICAL,
    GROUP_SCOPE_MIXED,
    ConfirmedGroupScopeDecision,
    MakeupScope,
    build_curriculum_diff,
)
from app.curriculum.requirements import normalize_curriculum_version
from app.curriculum.terms import ConfirmedScopeDecision, scope_decisions

SCOPED_CASE_PATH = DEMO_CASE_PATH.parent / "scoped_case.json"


def _course(course_id, name, credit, requirement="required", group_id=None, term=None):
    record = {
        "course_id": course_id, "course_name": name, "credit": credit,
        "requirement": requirement, "source_record": f"row:{course_id}",
        "prerequisites": [],
    }
    if group_id is not None:
        record["group_id"] = group_id
    if term is not None:
        record["recommended_term_text"] = term
    return record


def _group(group_id="GROUP-A", minimum=6):
    return {"group_id": group_id, "name": "示例选修池", "minimum_credit": minimum,
            "source_record": f"group:{group_id}"}


def _payload(*, new_courses, groups=(), completed=(), selections=(), decisions=(), group_decisions=(),
             as_of="2025-2"):
    return {
        "data_source": "mock",
        "old": {"version_id": "mock-old", "major": "old", "cohort": "c",
                "source_id": "mock://r2/old", "complete": True,
                "completeness_evidence": "mock://r2/old/complete",
                "course_records": [_course("OLD1", "old course", 3, term="2025-1")]},
        "new": {"version_id": "mock-new", "major": "new", "cohort": "c",
                "source_id": "mock://r2/new", "complete": True,
                "completeness_evidence": "mock://r2/new/complete",
                "course_records": list(new_courses),
                "group_records": list(groups)},
        "completed": {"source_id": "mock://r2/completed", "complete": True,
                      "completeness_evidence": "mock://r2/completed/complete",
                      "records": list(completed)},
        "rules": {"target_version_id": "mock-new", "completed_source_id": "mock://r2/completed",
                  "evidence": "mock://r2/rules", "allow_exact_match": True,
                  "allow_confirmed_absence": True},
        "elective_selections": list(selections),
        "makeup_scope": {"target_version_id": "mock-new", "as_of_term": as_of,
                         "evidence": "mock://r2/as-of"},
        "confirmed_scope_decisions": list(decisions),
        "confirmed_group_scope_decisions": list(group_decisions),
    }


def _decision(course_id, decision, *, term_record=None, version="mock-new",
              evidence="mock://r2/confirmed-scope", **overrides):
    record = {"target_version_id": version, "target_source_record": term_record or f"row:{course_id}",
              "target_course_id": course_id, "decision": decision, "evidence": evidence}
    record.update(overrides)
    return record


def _provider(payload):
    return CurriculumCaseProvider(normalize_curriculum_case(payload))


def _ids(payload):
    return [task.course_id for task in _provider(payload).get_makeup_tasks()]


def _completed(course_id, name, credit, passed=True):
    return {"course_id": course_id, "course_name": name, "credit": credit, "semester": "2025-1",
            "passed": passed, "course_type": "示例必修", "course_id_status": "已确认",
            "id_match_source": "mock://r2/id-evidence", "source_record": f"crow:{course_id}"}


# ==========================================================================
# A. ConfirmedScopeDecision
# ==========================================================================

AMBIGUOUS_TERMS = ["2025-1~2025-2", "2025-1~2028-2", "未知", "空", "", "not-a-term"]


@pytest.mark.parametrize("term", AMBIGUOUS_TERMS)
def test_uninterpretable_term_still_blocks_without_a_decision(term) -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term=term)],
                       completed=[_completed("A1", "a1", 3, passed=False)])
    payload["makeup_scope"]["as_of_term"] = "2025-2"
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "unresolved"
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        provider.get_makeup_tasks()
    if term:
        assert term not in "makeup scope: target entries have no confirmable arrangement term"


@pytest.mark.parametrize("term", AMBIGUOUS_TERMS)
def test_historical_decision_discharges_an_unresolved_term(term) -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term=term)],
                       completed=[_completed("A1", "a1", 3, passed=False)],
                       decisions=[_decision("A1", "historical")])
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "historical"
    assert [(t.course_id, t.status.value) for t in provider.get_makeup_tasks()] == [("A1", "required")]
    assert "mock://r2/confirmed-scope" in provider.get_makeup_tasks()[0].source_evidence


@pytest.mark.parametrize("term", AMBIGUOUS_TERMS)
def test_future_decision_discharges_an_unresolved_term(term) -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term=term)],
                       completed=[_completed("A1", "a1", 3, passed=False)],
                       decisions=[_decision("A1", "future")])
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "future"
    assert provider.get_makeup_tasks() == []


def test_decision_evidence_is_added_to_task_source_evidence() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       decisions=[_decision("A1", "historical",
                                            evidence="mock://r2/human-range-confirmation")])
    task = _provider(payload).get_makeup_tasks()[0]
    assert "mock://r2/human-range-confirmation" in task.source_evidence


def test_decision_evidence_does_not_leak_private_fields() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       decisions=[_decision("A1", "historical")])
    for task in _provider(payload).get_makeup_tasks():
        assert "DEMO-PRIVATE" not in task.source_evidence


def test_decision_targets_a_specific_requirement_entry_not_a_course_id() -> None:
    """Same course_id twice in different contexts: the entry decides."""

    first = _course("DUP", "dup one", 3, group_id="GROUP-A", term="2025-1~2025-2")
    second = _course("DUP", "dup two", 3, group_id="GROUP-A", term="2025-1~2028-2")
    second["source_record"] = "row:DUP-2"
    payload = _payload(
        new_courses=[_course("A1", "a1", 6, group_id="GROUP-A", term="2025-1"), first, second],
        groups=[_group(minimum=6)],
        decisions=[_decision("DUP", "historical", term_record="row:DUP-2")],
        group_decisions=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                          "historical_minimum_credit": 9, "evidence": "mock://r2/group-split"}],
    )
    version = normalize_curriculum_version(
        version_id="mock-new", major="new", cohort="c", source_id="mock://r2/new", complete=True,
        completeness_evidence="mock://r2/new/complete", course_records=payload["new"]["course_records"],
        group_records=payload["new"]["group_records"],
    )
    decisions = scope_decisions(version, "2025-2", [ConfirmedScopeDecision(
        target_version_id="mock-new", target_source_record="row:DUP-2", target_course_id="DUP",
        decision="historical", evidence="mock://r2/confirmed-scope")])
    by_record = {decision.source_record: decision.bucket for decision in decisions}
    assert by_record["row:DUP"] == "unresolved"
    assert by_record["row:DUP-2"] == "historical"


@pytest.mark.parametrize("mutate, label", [
    (lambda records: records + [records[0]], "duplicate decision"),
    (lambda records: [dict(records[0], target_source_record="row:NOT-THERE")], "unknown entry"),
    (lambda records: [dict(records[0], target_version_id="DEMO-OTHER")], "wrong version"),
    (lambda records: [dict(records[0], decision="maybe")], "invalid decision"),
    (lambda records: [dict(records[0], evidence="   ")], "empty evidence"),
    (lambda records: [dict(records[0], target_course_id="OTHER")], "course mismatch"),
])
def test_invalid_confirmed_scope_decisions_are_rejected(mutate, label) -> None:
    base = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                    decisions=[_decision("A1", "historical")])
    base["confirmed_scope_decisions"] = mutate(list(base["confirmed_scope_decisions"]))
    with pytest.raises(CurriculumNormalizationError):
        _provider(base)


def test_confirmed_scope_decision_rejects_extra_fields() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       decisions=[_decision("A1", "historical")])
    payload["confirmed_scope_decisions"][0]["DEMO-PRIVATE-FIELD"] = "DEMO-PRIVATE-VALUE"
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _provider(payload)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_decisions_without_a_scope_are_rejected() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       decisions=[_decision("A1", "historical")])
    del payload["makeup_scope"]
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        _provider(payload)


def test_real_case_rejects_mock_decision_evidence() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       decisions=[_decision("A1", "historical")])
    payload["data_source"] = "real"
    for key in ("old", "new"):
        payload[key]["source_id"] = "DEMO-REAL-SOURCE"
        payload[key]["completeness_evidence"] = "DEMO-REAL-COMPLETE"
    payload["completed"]["source_id"] = "DEMO-REAL-COMPLETED"
    payload["completed"]["completeness_evidence"] = "DEMO-REAL-COMPLETE"
    payload["rules"]["completed_source_id"] = "DEMO-REAL-COMPLETED"
    payload["rules"]["evidence"] = "DEMO-REAL-RULE"
    payload["makeup_scope"]["evidence"] = "DEMO-REAL-ASOF"
    payload["confirmed_scope_decisions"][0]["evidence"] = "说明: MoCk://DEMO-PRIVATE-SCOPE"
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        _provider(payload)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_mock_case_allows_mock_decision_evidence() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       decisions=[_decision("A1", "historical")])
    assert [(t.course_id, t.status.value) for t in _provider(payload).get_makeup_tasks()] == [("A1", "required")]


# ==========================================================================
# B. A confirmed decision may never override an unambiguous source term
# ==========================================================================

@pytest.mark.parametrize("term, decision", [("2026-1", "historical"), ("2025-1", "future")])
def test_decision_conflicting_with_an_unambiguous_term_is_rejected(term, decision) -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term=term)],
                       decisions=[_decision("A1", decision)])
    with pytest.raises(CurriculumNormalizationError, match="conflict"):
        _provider(payload)


def test_conflicting_decision_is_not_silently_ignored() -> None:
    """The unambiguous source fact stands only after the conflict is reported."""

    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2026-1")])
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "future"
    with pytest.raises(CurriculumNormalizationError):
        _provider(_payload(new_courses=[_course("A1", "a1", 3, term="2026-1")],
                           decisions=[_decision("A1", "historical")]))


# ==========================================================================
# C. satisfied semantics
# ==========================================================================

def test_historical_satisfied_is_output() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1")],
                       completed=[_completed("A1", "a1", 3)])
    assert [(t.course_id, t.status.value) for t in _provider(payload).get_makeup_tasks()] == [("A1", "satisfied")]


def test_future_satisfied_keeps_its_existing_output_semantics() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2026-1")],
                       completed=[_completed("A1", "a1", 3)])
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "future"
    assert [(t.course_id, t.status.value) for t in provider.get_makeup_tasks()] == [("A1", "satisfied")]


def test_unresolved_term_does_not_block_an_already_satisfied_item() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       completed=[_completed("A1", "a1", 3)])
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "unresolved"
    assert [(t.course_id, t.status.value) for t in provider.get_makeup_tasks()] == [("A1", "satisfied")]


def test_unresolved_term_still_blocks_when_the_item_is_unmet() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       completed=[_completed("A1", "a1", 3, passed=False)])
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        _provider(payload).get_makeup_tasks()


@pytest.mark.parametrize("status, expected", [
    ("required", []),
    ("possibly_equivalent", []),
    ("manual_confirmation", []),
])
def test_future_unmet_states_are_not_output(status, expected) -> None:
    if status == "required":
        courses = [_course("A1", "a1", 3, term="2026-1")]
        completed = [_completed("A1", "a1", 3, passed=False)]
    elif status == "possibly_equivalent":
        # Same name, different (pending) identity -> name candidate only.
        courses = [_course("A1", "a1", 3, term="2026-1")]
        completed = [dict(_completed("OTHER", "a1", 3), course_id="", course_id_status="待确认")]
    else:  # manual_confirmation via unknown prerequisites
        record = _course("A1", "a1", 3, term="2026-1")
        record["prerequisites"] = None
        courses = [record]
        completed = []
    payload = _payload(new_courses=courses, completed=completed)
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket_for_entry("row:A1") == "future"
    assert [t.course_id for t in provider.get_makeup_tasks()] == expected


def test_historical_unmet_states_are_output() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1")],
                       completed=[_completed("A1", "a1", 3, passed=False)])
    assert [(t.course_id, t.status.value) for t in _provider(payload).get_makeup_tasks()] == [("A1", "required")]


# ==========================================================================
# D. Course groups
# ==========================================================================

def _group_payload(*, members, minimum, completed=(), selections=(), decisions=(), group_decisions=(),
                   extra=()):
    return _payload(
        new_courses=list(members) + list(extra),
        groups=[_group(minimum=minimum)],
        completed=list(completed),
        selections=list(selections),
        decisions=list(decisions),
        group_decisions=list(group_decisions),
    )


def test_future_only_group_does_not_block_historical_projection() -> None:
    """A group arranged entirely after the scope states no historical need."""
    payload = _group_payload(
        members=[_course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1"),
                 _course("F2", "f2", 3, "elective", "GROUP-A", term="2026-2")],
        minimum=6,
    )
    provider = _provider(payload)
    gaps = provider.get_curriculum_diff().group_gaps
    assert all(gap.scope == GROUP_SCOPE_FUTURE for gap in gaps)
    assert [task.course_id for task in provider.get_makeup_tasks()] == []


def test_future_only_group_with_historical_required_course_still_projects_it() -> None:
    payload = _group_payload(
        members=[_course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1"),
                 _course("F2", "f2", 3, "elective", "GROUP-A", term="2026-2")],
        minimum=6,
        extra=[_course("R1", "r1", 3, "required", term="2025-1")],
        completed=[_completed("R1", "r1", 3, passed=False)],
    )
    assert [(t.course_id, t.status.value) for t in _provider(payload).get_makeup_tasks()] == [("R1", "required")]


def test_historical_only_group_keeps_the_original_blocking_behaviour() -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2")],
        minimum=6,
    )
    provider = _provider(payload)
    gap = provider.get_curriculum_diff().group_gaps[0]
    assert gap.scope == GROUP_SCOPE_HISTORICAL and gap.remaining_credit == 6
    with pytest.raises(CurriculumNormalizationError, match="group"):
        provider.get_makeup_tasks()


def test_historical_only_group_projects_with_a_confirmed_selection() -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2")],
        minimum=6,
        selections=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                     "course_ids": ["H1", "H2"], "evidence": "mock://r2/selection"}],
    )
    assert _ids(payload) == ["H1", "H2"]


def test_mixed_group_without_a_split_blocks_projection() -> None:
    """The historical share of the minimum is unstated: never invent a split."""
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
                 _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1"),
                 _course("F2", "f2", 3, "elective", "GROUP-A", term="2026-2")],
        minimum=12,
    )
    provider = _provider(payload)
    gap = provider.get_curriculum_diff().group_gaps[0]
    assert gap.scope == GROUP_SCOPE_MIXED and gap.historical_ambiguous
    assert gap.remaining_credit == 12  # total bar, not a proportional guess
    with pytest.raises(CurriculumNormalizationError, match="mixed group"):
        provider.get_makeup_tasks()


def test_mixed_group_is_not_split_proportionally_by_member_count() -> None:
    """Two historical + two future members must not imply half the minimum."""
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
                 _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1"),
                 _course("F2", "f2", 3, "elective", "GROUP-A", term="2026-2")],
        minimum=12,
    )
    gap = _provider(payload).get_curriculum_diff().group_gaps[0]
    assert gap.historical_minimum_credit is None
    assert gap.remaining_credit not in (0.0, 6.0)


def test_mixed_group_with_an_explicit_split_projects() -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
                 _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1"),
                 _course("F2", "f2", 3, "elective", "GROUP-A", term="2026-2")],
        minimum=12,
        selections=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                     "course_ids": ["H1", "H2"], "evidence": "mock://r2/selection"}],
        group_decisions=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                          "historical_minimum_credit": 6, "evidence": "mock://r2/historical-share"}],
    )
    provider = _provider(payload)
    gap = provider.get_curriculum_diff().group_gaps[0]
    assert gap.historical_minimum_credit == 6 and gap.scope == GROUP_SCOPE_MIXED
    assert [t.course_id for t in provider.get_makeup_tasks()] == ["H1", "H2"]


def test_mixed_group_split_below_the_historical_need_still_blocks() -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
                 _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1")],
        minimum=9,
        group_decisions=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                          "historical_minimum_credit": 6, "evidence": "mock://r2/historical-share"}],
    )
    with pytest.raises(CurriculumNormalizationError, match="group"):
        _provider(payload).get_makeup_tasks()


@pytest.mark.parametrize("mutate", [
    lambda records: records + [records[0]],
    lambda records: [dict(records[0], group_id="GROUP-MISSING")],
    lambda records: [dict(records[0], historical_minimum_credit=99)],
    lambda records: [dict(records[0], historical_minimum_credit=-1)],
    lambda records: [dict(records[0], evidence="")],
    lambda records: [dict(records[0], target_version_id="DEMO-OTHER")],
])
def test_invalid_group_scope_decisions_are_rejected(mutate) -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1")],
        minimum=6,
        group_decisions=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                          "historical_minimum_credit": 3, "evidence": "mock://r2/historical-share"}],
    )
    payload["confirmed_group_scope_decisions"] = mutate(list(payload["confirmed_group_scope_decisions"]))
    with pytest.raises(CurriculumNormalizationError):
        _provider(payload)


def test_group_split_is_refused_for_a_non_mixed_group() -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2")],
        minimum=6,
        group_decisions=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                          "historical_minimum_credit": 6, "evidence": "mock://r2/historical-share"}],
    )
    with pytest.raises(CurriculumNormalizationError, match="mixed group"):
        _provider(payload)


def test_future_elective_selection_does_not_satisfy_a_historical_group() -> None:
    """A future pool choice must not be counted toward the historical bar."""
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1")],
        minimum=6,
        selections=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                     "course_ids": ["F1"], "evidence": "mock://r2/selection"}],
    )
    provider = _provider(payload)
    with pytest.raises(CurriculumNormalizationError, match="mixed group"):
        provider.get_makeup_tasks()


def test_historical_satisfied_credits_still_cover_a_historical_group() -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2")],
        minimum=6,
        completed=[_completed("H1", "h1", 3), _completed("H2", "h2", 3)],
    )
    provider = _provider(payload)
    assert provider.get_curriculum_diff().group_gaps == ()
    assert [(t.course_id, t.status.value) for t in provider.get_makeup_tasks()] == [
        ("H1", "satisfied"), ("H2", "satisfied"),
    ]


def test_unscoped_group_behaviour_is_unchanged() -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2026-1")],
        minimum=6,
    )
    del payload["makeup_scope"]
    provider = _provider(payload)
    gap = provider.get_curriculum_diff().group_gaps[0]
    assert gap.scope == "unscoped" and gap.historical_minimum_credit is None
    assert gap.remaining_credit == 6
    with pytest.raises(CurriculumNormalizationError, match="group"):
        provider.get_makeup_tasks()


def test_group_scope_decision_requires_an_explicit_scope() -> None:
    payload = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1")],
        minimum=6,
        group_decisions=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                          "historical_minimum_credit": 3, "evidence": "mock://r2/historical-share"}],
    )
    del payload["makeup_scope"]
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        _provider(payload)


def test_group_scope_decision_type_is_validated() -> None:
    with pytest.raises(CurriculumNormalizationError):
        ConfirmedGroupScopeDecision(target_version_id="mock-new", group_id="GROUP-A",
                                    historical_minimum_credit=-1, evidence="mock://r2/e")
    with pytest.raises(CurriculumNormalizationError):
        ConfirmedGroupScopeDecision(target_version_id="mock-new", group_id="GROUP-A",
                                    historical_minimum_credit=3, evidence="  ")


def test_build_diff_requires_a_scope_for_scope_decisions() -> None:
    old = normalize_curriculum_version(
        version_id="mock-old", major="m", cohort="c", source_id="mock://r2/old", complete=True,
        completeness_evidence="mock://r2/old/complete",
        course_records=[_course("OLD1", "old", 3, term="2025-1")])
    new = normalize_curriculum_version(
        version_id="mock-new", major="m", cohort="c", source_id="mock://r2/new", complete=True,
        completeness_evidence="mock://r2/new/complete",
        course_records=[_course("A1", "a1", 3, term="2025-1")])
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        build_curriculum_diff(old, new, (), confirmed_scope_decisions=[
            ConfirmedScopeDecision(target_version_id="mock-new", target_source_record="row:A1",
                                   target_course_id="A1", decision="historical", evidence="mock://r2/e")])


def test_makeup_scope_object_is_validated() -> None:
    with pytest.raises(CurriculumNormalizationError):
        MakeupScope(target_version_id="mock-new", as_of_term="2025-2", evidence="")


# ==========================================================================
# Round 3 / Blocker A: scope lookup is per requirement entry, not course_id
# ==========================================================================

def _dup_payload(*, term_a, term_b, decisions=(), extra=()):
    first = _course("DUP", "dup historical row", 3, term=term_a)
    second = _course("DUP", "dup future row", 3, term=term_b)
    second["source_record"] = "row:DUP-B"
    return _payload(new_courses=[first, second] + list(extra), decisions=list(decisions))


def test_same_course_id_entries_do_not_share_a_scope_bucket() -> None:
    payload = _dup_payload(term_a="2025-1", term_b="2026-1")
    diff = _provider(payload).get_curriculum_diff()
    assert diff.scope_bucket_for_entry("row:DUP") == "historical"
    assert diff.scope_bucket_for_entry("row:DUP-B") == "future"


def test_same_course_id_entries_project_independently() -> None:
    """The two entries keep independent buckets; the future one is not emitted.

    A repeated course_id already blocks public projection by the pre-existing
    duplicate guard (locked by other tests, unchanged this round), so the
    end-to-end assertion checks the classification and that the refusal is for
    the duplicate reason rather than a scope reason.
    """
    payload = _dup_payload(
        term_a="2025-1", term_b="2026-1",
        extra=[_course("KEEP", "keep", 3, term="2025-1")],
    )
    provider = _provider(payload)
    diff = provider.get_curriculum_diff()
    assert diff.scope_bucket_for_entry("row:DUP") == "historical"
    assert diff.scope_bucket_for_entry("row:DUP-B") == "future"
    assert diff.unresolved_scope_entries() == ()
    with pytest.raises(CurriculumNormalizationError, match="duplicate"):
        provider.get_makeup_tasks()


def test_future_entry_alone_does_not_hide_a_historical_sibling_with_the_same_id() -> None:
    """A future row must never change the historical row's classification."""
    payload = _dup_payload(term_a="2025-1", term_b="2026-1")
    diff = _provider(payload).get_curriculum_diff()
    assert diff.scope_bucket_for_entry("row:DUP") == "historical"
    assert diff.scope_bucket_for_entry("row:DUP-B") == "future"
    assert diff.unresolved_scope_entries() == ()


def test_same_course_id_evidence_does_not_cross_between_entries() -> None:
    """A decision recorded for one entry is never applied to another entry."""
    payload = _dup_payload(
        term_a="2025-1", term_b="2025-1~2028-2",
        decisions=[_decision("DUP", "future", term_record="row:DUP-B",
                             evidence="mock://r3/only-for-dup-b")],
    )
    diff = _provider(payload).get_curriculum_diff()
    assert diff.scope_bucket_for_entry("row:DUP-B") == "future"
    assert diff.scope_evidence_for_entry("row:DUP-B") == "mock://r3/only-for-dup-b"
    # The sibling kept its automatic classification and carries no evidence.
    assert diff.scope_bucket_for_entry("row:DUP") == "historical"
    assert diff.scope_evidence_for_entry("row:DUP") is None


def test_scope_evidence_does_not_cross_between_entries_of_one_group() -> None:
    """Entry-level evidence stays on the entry that owns the decision."""
    payload = _payload(
        new_courses=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                     _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-1~2025-2")],
        groups=[_group("GROUP-A", minimum=6)],
        completed=[_completed("H1", "h1", 3)],
        decisions=[_decision("H2", "historical", evidence="mock://r3/only-for-h2")],
        selections=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                     "course_ids": ["H2"], "evidence": "mock://r3/selection"}],
    )
    tasks = {task.course_id: task for task in _provider(payload).get_makeup_tasks()}
    assert "mock://r3/only-for-h2" in tasks["H2"].source_evidence
    assert "mock://r3/only-for-h2" not in tasks["H1"].source_evidence


def test_a_discharged_entry_still_loses_to_its_unresolved_sibling() -> None:
    """Discharging one unresolved row does not excuse another unresolved row."""
    payload = _dup_payload(
        term_a="2025-1~2025-2", term_b="2025-1~2028-2",
        decisions=[_decision("DUP", "historical", term_record="row:DUP-B",
                             evidence="mock://r3/only-for-dup-b")],
    )
    provider = _provider(payload)
    diff = provider.get_curriculum_diff()
    assert diff.scope_bucket_for_entry("row:DUP") == "unresolved"
    assert diff.scope_bucket_for_entry("row:DUP-B") == "historical"
    assert diff.unresolved_scope_entries() == ("row:DUP",)
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        provider.get_makeup_tasks()


def test_one_decision_does_not_discharge_a_second_unresolved_entry_of_the_same_course() -> None:
    payload = _dup_payload(
        term_a="2025-1~2025-2", term_b="2025-1~2028-2",
        decisions=[_decision("DUP", "historical", term_record="row:DUP")],
    )
    provider = _provider(payload)
    diff = provider.get_curriculum_diff()
    assert diff.scope_bucket_for_entry("row:DUP") == "historical"
    # The other row is still unresolved, so its own entry keeps failing closed.
    assert diff.unresolved_scope_entries() == ("row:DUP-B",)
    with pytest.raises(CurriculumNormalizationError, match="scope"):
        provider.get_makeup_tasks()


def test_entry_level_lookup_rejects_unknown_or_unscoped_entries() -> None:
    payload = _dup_payload(term_a="2025-1", term_b="2026-1")
    diff = _provider(payload).get_curriculum_diff()
    with pytest.raises(CurriculumNormalizationError):
        diff.scope_bucket_for_entry("row:NOT-IN-PLAN")
    unscoped = _group_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1")], minimum=3)
    del unscoped["makeup_scope"]
    assert _provider(unscoped).get_curriculum_diff().scope_bucket_for_entry("row:H1") is None


def test_scope_lookup_api_is_entry_level_only() -> None:
    """Regression guard: the entry-level API must not fall back to course_id."""
    source = (DEMO_CASE_PATH.parents[2] / "backend/app/curriculum/matching.py").read_text(encoding="utf-8")
    assert "def scope_bucket_for_entry(self, source_record: str)" in source
    assert "def scope_bucket(self, course_id" not in source


# ==========================================================================
# Round 3 / Blocker B: mixed-group historical credit excludes future courses
# ==========================================================================

def _mixed_split_payload(*, members, completed=(), historical_split=6, minimum=12):
    return _payload(
        new_courses=list(members),
        groups=[_group(minimum=minimum)],
        completed=list(completed),
        group_decisions=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                          "historical_minimum_credit": historical_split,
                          "evidence": "mock://r3/group-split"}],
    )


def test_mixed_group_history_not_covered_by_a_future_satisfied_course() -> None:
    """Test A: future satisfied credit must not fill the historical quota."""
    payload = _mixed_split_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
                 _course("F1", "f1", 6, "elective", "GROUP-A", term="2026-1")],
        completed=[_completed("F1", "f1", 6)],
    )
    gap = _provider(payload).get_curriculum_diff().group_gaps[0]
    assert gap.scope == GROUP_SCOPE_MIXED
    assert gap.historical_minimum_credit == 6
    assert gap.remaining_credit == 6  # NOT 0


def test_mixed_group_history_counts_only_historical_satisfied_credits() -> None:
    """Test B: only the historical 3 credits count, so 3 remain."""
    payload = _mixed_split_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
                 _course("F1", "f1", 6, "elective", "GROUP-A", term="2026-1")],
        completed=[_completed("H1", "h1", 3), _completed("F1", "f1", 6)],
    )
    assert _provider(payload).get_curriculum_diff().group_gaps[0].remaining_credit == 3


def test_mixed_group_history_cleared_only_by_historical_satisfied_credits() -> None:
    """Test C: cleared by the historical 6 credits, with future credit also present."""
    payload = _mixed_split_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
                 _course("F1", "f1", 6, "elective", "GROUP-A", term="2026-1")],
        completed=[_completed("H1", "h1", 3), _completed("H2", "h2", 3), _completed("F1", "f1", 6)],
    )
    provider = _provider(payload)
    assert provider.get_curriculum_diff().group_gaps == ()
    assert {task.course_id for task in provider.get_makeup_tasks()} == {"H1", "H2", "F1"}


def test_mixed_group_history_is_covered_by_satisfied_members() -> None:
    """The historical bar is met by historical satisfied credits (not by future ones)."""
    payload = _mixed_split_payload(
        members=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                 _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
                 _course("F1", "f1", 6, "elective", "GROUP-A", term="2026-1")],
        completed=[_completed("H1", "h1", 3), _completed("H2", "h2", 3), _completed("F1", "f1", 6)],
    )
    assert _provider(payload).get_curriculum_diff().group_gaps == ()


def test_mixed_group_unmet_elective_does_not_silently_cover_the_bar() -> None:
    """An unmet historical elective still blocks: it needs an explicit choice."""
    payload = _mixed_split_payload(
        members=[_course("H1", "h1", 6, "elective", "GROUP-A", term="2025-1"),
                 _course("F1", "f1", 6, "elective", "GROUP-A", term="2026-1")],
        historical_split=6,
    )
    with pytest.raises(CurriculumNormalizationError, match="group"):
        _provider(payload).get_makeup_tasks()


def test_future_elective_selection_still_cannot_cover_the_historical_quota() -> None:
    """Test D (kept from the previous round)."""
    payload = _payload(
        new_courses=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                     _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1")],
        groups=[_group(minimum=6)],
        selections=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                     "course_ids": ["F1"], "evidence": "mock://r3/selection"}],
    )
    with pytest.raises(CurriculumNormalizationError, match="mixed group"):
        _provider(payload).get_makeup_tasks()


# ==========================================================================
# Round 3 / Blocker C: group decision evidence propagation
# ==========================================================================

def _two_group_payload(*, required_extra=()):
    """Two mixed groups, each with its own confirmed historical credit split."""
    return _payload(
        new_courses=[
            _course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
            _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2"),
            _course("F1", "f1", 3, "elective", "GROUP-A", term="2026-1"),
            _course("H3", "h3", 3, "elective", "GROUP-B", term="2025-1"),
            _course("F2", "f2", 3, "elective", "GROUP-B", term="2026-1"),
        ] + list(required_extra),
        groups=[_group("GROUP-A", minimum=9), _group("GROUP-B", minimum=6)],
        completed=[_completed("H1", "h1", 3), _completed("H2", "h2", 3), _completed("H3", "h3", 3)],
        group_decisions=[
            {"target_version_id": "mock-new", "group_id": "GROUP-A",
             "historical_minimum_credit": 6, "evidence": "source://group-a-confirmed"},
            {"target_version_id": "mock-new", "group_id": "GROUP-B",
             "historical_minimum_credit": 3, "evidence": "source://group-b-confirmed"},
        ],
    )


def test_group_decision_evidence_reaches_its_own_group_tasks() -> None:
    tasks = {task.course_id: task for task in _provider(_two_group_payload()).get_makeup_tasks()}
    assert {"H1", "H2", "H3"}.issubset(set(tasks))
    assert "source://group-a-confirmed" in tasks["H1"].source_evidence
    assert "source://group-a-confirmed" in tasks["H2"].source_evidence


def test_group_decision_evidence_does_not_leak_to_another_group() -> None:
    """Test B/D: each group's evidence stays on its own tasks."""
    tasks = {task.course_id: task for task in _provider(_two_group_payload()).get_makeup_tasks()}
    assert "source://group-b-confirmed" not in tasks["H1"].source_evidence
    assert "source://group-b-confirmed" not in tasks["H2"].source_evidence
    assert "source://group-b-confirmed" in tasks["H3"].source_evidence
    assert "source://group-a-confirmed" not in tasks["H3"].source_evidence


def test_group_decision_evidence_skips_non_group_courses() -> None:
    """Test C: an unrelated mandatory course carries no group evidence."""
    provider = _provider(_two_group_payload(
        required_extra=[_course("PLAIN", "plain", 3, term="2025-1")]))
    tasks = {task.course_id: task for task in provider.get_makeup_tasks()}
    assert tasks["PLAIN"].status.value == "required"
    assert "source://group-a-confirmed" not in tasks["PLAIN"].source_evidence
    assert "source://group-b-confirmed" not in tasks["PLAIN"].source_evidence


def test_group_without_a_decision_gets_no_group_evidence() -> None:
    payload = _payload(
        new_courses=[_course("H1", "h1", 3, "elective", "GROUP-A", term="2025-1"),
                     _course("H2", "h2", 3, "elective", "GROUP-A", term="2025-2")],
        groups=[_group("GROUP-A", minimum=6)],
        selections=[{"target_version_id": "mock-new", "group_id": "GROUP-A",
                     "course_ids": ["H1", "H2"], "evidence": "mock://r3/selection"}],
    )
    tasks = _provider(payload).get_makeup_tasks()
    assert tasks
    assert all("课程组历史额度确认依据" not in task.source_evidence for task in tasks)


def test_group_evidence_mapping_is_per_group() -> None:
    diff = _provider(_two_group_payload()).get_curriculum_diff()
    assert diff.confirmed_group_scope_evidence() == {
        "GROUP-A": "source://group-a-confirmed",
        "GROUP-B": "source://group-b-confirmed",
    }
