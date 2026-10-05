"""A consumed exact/identity match must leave the later name-candidate pool.

Real Case A symptom (D4 handoff): the record ``PE102 体育`` matched the target
requirement ``PE102`` by identity, and the *same* record was then offered again as
a fuzzy name candidate for ``PE201 / PE202 / PE305 / PE302`` (all named 体育),
producing four false ``possibly_equivalent`` results.

The rule fixed here is narrow and one-directional:

    deterministic confirmed exact/identity match
        -> that completed record leaves the LATER fuzzy name-candidate pool

It is deliberately NOT a general "one completed record matches only one target"
rule: unresolved-identity records, records consumed by an explicit
``ConfirmedRecognition``, and records that merely act as name candidates keep
their previous behaviour. Identity matching itself is untouched, so a record can
still satisfy a target whose course_id it actually carries.
"""

from __future__ import annotations

from app.curriculum.matching import MatchingRules
from app.models.contracts import MakeupStatus

from tests.test_curriculum_matching import (  # noqa: E402
    _attempt,
    _diff,
    _recognition,
    _target,
)


def _case_rules(**changes) -> MatchingRules:
    """Rules bound to the case that ``tests.test_curriculum_matching._diff`` builds."""
    return MatchingRules(**{
        "target_version_id": "DEMO-VERSION-NEW",
        "completed_source_id": "DEMO-COMPLETED",
        "evidence": "mock://DEMO-case-rules",
        "allow_exact_match": True,
        "allow_confirmed_absence": True,
        **changes,
    })


def _case(*targets, completed, **overrides):
    """Case-scoped matching with deterministic exact matches enabled.

    This mirrors the real Case A configuration, where ``allow_exact_match`` is on;
    without it no identity match is confirmed and nothing can be consumed.
    """
    overrides.setdefault("rules", _case_rules())
    return _diff(tuple(targets), completed, **overrides)


def _status(diff, course_id: str) -> MakeupStatus:
    return next(m for m in diff.matches if m.target.course_id == course_id).status


def _candidates(diff, course_id: str) -> tuple:
    match = next(m for m in diff.matches if m.target.course_id == course_id)
    return tuple((c.source_id, c.source_record) for c in match.candidates)


# --------------------------------------------------------------------------
# 1. the real PE102 / PE2xx scenario
# --------------------------------------------------------------------------

def test_identity_matched_record_is_not_reused_as_a_name_candidate() -> None:
    """PE102 is satisfied by identity; its record must not feed PE201's pool."""
    pe102 = _target("PE102", course_name="体育", credit=1)
    pe201 = _target("PE201", course_name="体育", credit=0.5)
    record = _attempt("PE102", row=1, course_name="体育", credit=1)
    diff = _case(pe102, pe201, completed=(record,))

    assert _status(diff, "PE102") is MakeupStatus.SATISFIED
    # The consumed record is gone from the fuzzy pool, so PE201 has no candidate.
    assert _candidates(diff, "PE201") == ()
    assert _status(diff, "PE201") is not MakeupStatus.POSSIBLY_EQUIVALENT


def test_all_four_same_name_targets_lose_the_consumed_record() -> None:
    """The exact real symptom: PE201 / PE202 / PE305 / PE302 must not be flagged."""
    targets = [
        _target("PE102", course_name="体育", credit=1),
        _target("PE201", course_name="体育", credit=0.5),
        _target("PE202", course_name="体育", credit=0.5),
        _target("PE305", course_name="体育", credit=0.5),
        _target("PE302", course_name="体育", credit=0.5),
    ]
    record = _attempt("PE102", row=1, course_name="体育", credit=1)
    diff = _case(*targets, completed=(record,))

    assert _status(diff, "PE102") is MakeupStatus.SATISFIED
    for course_id in ("PE201", "PE202", "PE305", "PE302"):
        assert _candidates(diff, course_id) == (), course_id
        assert _status(diff, course_id) is not MakeupStatus.POSSIBLY_EQUIVALENT, course_id
    assert not any(
        match.status is MakeupStatus.POSSIBLY_EQUIVALENT for match in diff.matches
    )


def test_consumed_record_keeps_its_own_identity_satisfaction() -> None:
    """Consumption must not weaken the identity match that consumed it."""
    record = _attempt("PE102", row=1, course_name="体育", credit=1)
    diff = _case(
        _target("PE102", course_name="体育", credit=1),
        _target("PE201", course_name="体育", credit=0.5),
        completed=(record,),
    )
    pe102 = next(m for m in diff.matches if m.target.course_id == "PE102")
    assert pe102.status is MakeupStatus.SATISFIED
    assert record in pe102.candidates


# --------------------------------------------------------------------------
# 2. unresolved-identity records keep their name-candidate behaviour
# --------------------------------------------------------------------------

def test_unresolved_identity_record_is_never_consumed() -> None:
    """A pending-identity record has no confirmed id, so it stays available.

    A pending record sharing the consumed record's name would (by pre-existing
    case-rule semantics) block that exact match, so the two live in separate name
    groups here: the confirmed record is consumed, and the pending record in a
    different group remains a candidate.
    """
    pe102 = _target("PE102", course_name="体育", credit=1)
    other = _target("DEMO-Z", course_name="篮球", credit=2)
    confirmed = _attempt("PE102", row=1, course_name="体育", credit=1)
    pending = _attempt(None, row=2, course_name="篮球", credit=2)
    diff = _case(pe102, other, completed=(confirmed, pending))

    # The confirmed record was deterministically consumed...
    assert _status(diff, "PE102") is MakeupStatus.SATISFIED
    # ...while the pending-identity record is untouched and still offered.
    assert _candidates(diff, "DEMO-Z") == (("DEMO-COMPLETED", "DEMO-SHEET!row:2"),)


def test_unresolved_identity_record_still_reports_a_name_candidate() -> None:
    """Without any deterministic match, the pending record is still offered."""
    target = _target("PE201", course_name="体育", credit=0.5)
    pending = _attempt(None, row=1, course_name="体育", credit=0.5)
    diff = _case(target, completed=(pending,))
    match = diff.matches[0]
    assert match.candidates == (pending,)


def test_a_name_only_match_consumes_nothing() -> None:
    """Being a name candidate is not a deterministic match; nothing is consumed."""
    first = _target("DEMO-A", course_name="DEMO Shared Name")
    second = _target("DEMO-B", course_name="DEMO Shared Name")
    pending = _attempt(None, row=1, course_name="DEMO Shared Name")
    diff = _case(first, second, completed=(pending,))
    assert all(pending in match.candidates for match in diff.matches)


# --------------------------------------------------------------------------
# 3. two independent records: only the consumed one is removed
# --------------------------------------------------------------------------

def test_only_the_consumed_record_leaves_the_name_pool() -> None:
    """A consumed record of the same name is removed; an untouched one stays."""
    pe102 = _target("PE102", course_name="体育", credit=1)
    pe201 = _target("PE201", course_name="体育", credit=0.5)
    demo_a = _target("DEMO-A", course_name="体育", credit=1)
    shared = _attempt("PE102", row=1, course_name="体育", credit=1)
    independent = _attempt("DEMO-A", row=2, course_name="体育", credit=1)
    diff = _case(pe102, pe201, demo_a, completed=(shared, independent))

    # Both records are consumed by their own identity match...
    assert _status(diff, "PE102") is MakeupStatus.SATISFIED
    assert _status(diff, "DEMO-A") is MakeupStatus.SATISFIED
    # ...so neither is offered as a fuzzy name candidate for PE201.
    assert _candidates(diff, "PE201") == ()


def test_an_untouched_same_name_record_keeps_its_candidate_role() -> None:
    """Only *consumed* records are filtered; an untouched confirmed one is not."""
    pe201 = _target("PE201", course_name="体育", credit=0.5)
    untouched = _attempt("PE900", row=3, course_name="体育", credit=0.5)
    diff = _case(pe201, completed=(untouched,))
    assert ("DEMO-COMPLETED", "DEMO-SHEET!row:3") in _candidates(diff, "PE201")


def test_consumed_and_untouched_records_keep_distinct_provenance() -> None:
    """The consumed record's reference must not leak onto the other target."""
    pe102 = _target("PE102", course_name="体育", credit=1)
    pe201 = _target("PE201", course_name="体育", credit=0.5)
    consumed = _attempt("PE102", row=1, course_name="体育", credit=1)
    untouched = _attempt("PE900", row=3, course_name="体育", credit=0.5)
    diff = _case(pe102, pe201, completed=(consumed, untouched))

    pe201_match = next(m for m in diff.matches if m.target.course_id == "PE201")
    candidate_evidence = " ".join(
        f"{c.source_id}#{c.source_record}" for c in pe201_match.candidates
    )
    assert "DEMO-SHEET!row:3" in candidate_evidence
    assert "DEMO-SHEET!row:1" not in candidate_evidence

    # And the consumed record is still attributed to the target that consumed it.
    pe102_match = next(m for m in diff.matches if m.target.course_id == "PE102")
    assert consumed in pe102_match.candidates


# --------------------------------------------------------------------------
# 4. explicit ConfirmedRecognition must not regress
# --------------------------------------------------------------------------

def test_explicit_recognition_does_not_consume_the_record() -> None:
    """Recognition is its own path; the record keeps its name-candidate role."""
    recognised = _target("DEMO-A", course_name="DEMO Shared Name")
    peer = _target("DEMO-B", course_name="DEMO Shared Name")
    record = _attempt("DEMO-X", row=1, course_name="DEMO Shared Name")
    diff = _case(
        recognised, peer, completed=(record,),
        recognitions=(_recognition(recognised, record),),
    )
    assert _status(diff, "DEMO-A") is MakeupStatus.SATISFIED
    assert ("DEMO-COMPLETED", "DEMO-SHEET!row:1") in _candidates(diff, "DEMO-B")


def test_recognised_target_keeps_its_own_candidate_evidence() -> None:
    recognised = _target("DEMO-A", course_name="DEMO Shared Name")
    peer = _target("DEMO-B", course_name="DEMO Shared Name")
    record = _attempt("DEMO-X", row=1, course_name="DEMO Shared Name")
    diff = _case(
        recognised, peer, completed=(record,),
        recognitions=(_recognition(recognised, record),),
    )
    first = next(m for m in diff.matches if m.target.course_id == "DEMO-A")
    assert record in first.candidates


# --------------------------------------------------------------------------
# 5. confirmed same-ID semantics are untouched
# --------------------------------------------------------------------------

def test_confirmed_same_id_match_is_unchanged() -> None:
    target = _target("DEMO-A")
    record = _attempt("DEMO-A", row=1)
    diff = _case(target, completed=(record,))
    match = diff.matches[0]
    assert match.status is MakeupStatus.SATISFIED
    assert match.candidates == (record,)


def test_identity_matching_still_works_after_a_record_was_consumed() -> None:
    """Exclusion applies only to the fuzzy pool, never to identity matching."""
    first = _target("PE102", course_name="体育", credit=1)
    second = _target("DEMO-A")
    first_record = _attempt("PE102", row=1, course_name="体育", credit=1)
    second_record = _attempt("DEMO-A", row=2)
    diff = _case(first, second, completed=(first_record, second_record))
    assert _status(diff, "PE102") is MakeupStatus.SATISFIED
    assert _status(diff, "DEMO-A") is MakeupStatus.SATISFIED
    assert second_record in next(
        m for m in diff.matches if m.target.course_id == "DEMO-A"
    ).candidates
