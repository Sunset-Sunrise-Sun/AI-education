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
    assert provider.get_curriculum_diff().scope_bucket("A1") == "unresolved"
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
    assert provider.get_curriculum_diff().scope_bucket("A1") == "historical"
    assert [(t.course_id, t.status.value) for t in provider.get_makeup_tasks()] == [("A1", "required")]
    assert "mock://r2/confirmed-scope" in provider.get_makeup_tasks()[0].source_evidence


@pytest.mark.parametrize("term", AMBIGUOUS_TERMS)
def test_future_decision_discharges_an_unresolved_term(term) -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term=term)],
                       completed=[_completed("A1", "a1", 3, passed=False)],
                       decisions=[_decision("A1", "future")])
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket("A1") == "future"
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
    assert provider.get_curriculum_diff().scope_bucket("A1") == "future"
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
    assert provider.get_curriculum_diff().scope_bucket("A1") == "future"
    assert [(t.course_id, t.status.value) for t in provider.get_makeup_tasks()] == [("A1", "satisfied")]


def test_unresolved_term_does_not_block_an_already_satisfied_item() -> None:
    payload = _payload(new_courses=[_course("A1", "a1", 3, term="2025-1~2025-2")],
                       completed=[_completed("A1", "a1", 3)])
    provider = _provider(payload)
    assert provider.get_curriculum_diff().scope_bucket("A1") == "unresolved"
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
    assert provider.get_curriculum_diff().scope_bucket("A1") == "future"
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
