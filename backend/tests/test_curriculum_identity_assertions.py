"""Student identity assertions: the three statements a student may make, and the guards.

The most important tests here are the negative ones. An assertion must never become a
recognition, never write ``course_id_status``, never yield credit, and must be rejected
outright once the transcript or the catalogue version has moved on.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect

import pytest

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.identity_assertions import (
    STUDENT_ASSERTION_SOURCE,
    StudentIdentityAssertion,
    StudentIdentityDecision,
    assertions_for_record,
    validate_identity_assertions,
)
from app.curriculum.identity_candidates import (
    IdentityCandidate,
    IdentityCandidateSet,
    IdentityStatus,
    build_identity_candidates,
)
from app.curriculum.requirements import CurriculumCourse, CurriculumVersion, RequirementKind

VERSION = "DEMO-VERSION-NEW"
SOURCE = "upload:pdf:sha256:demodigest"


def _course(course_id: str, course_name: str, *, source_record: str | None = None,
            requirement: RequirementKind = RequirementKind.REQUIRED) -> CurriculumCourse:
    return CurriculumCourse(
        course_id=course_id, course_name=course_name, credit=3.0, requirement=requirement,
        source_record=source_record or f"DEMO-CATALOG#{course_id}", prerequisites=(),
    )


def _catalog(courses: tuple[CurriculumCourse, ...], *, version_id: str = VERSION) -> CurriculumVersion:
    return CurriculumVersion(
        version_id=version_id, major="DEMO Major", cohort="DEMO Cohort",
        source_id="DEMO-CATALOG-SOURCE", courses=courses, complete=True,
        completeness_evidence="DEMO-CATALOG-COMPLETE",
    )


def _record(course_name: str, *, row: int = 1, passed: bool = True,
            source_id: str = SOURCE) -> CompletedCourse:
    return CompletedCourse(
        course_id=None, course_name=course_name, credit=3.0, semester="DEMO-ACTUAL-TERM",
        passed=passed, course_type="DEMO Context", course_id_status=CourseIdStatus.PENDING,
        id_match_source=None, source_id=source_id, source_record=f"pdf:{row}",
    )


def _setup(names: tuple[str, ...] = ("线性代数",)) -> tuple[tuple[IdentityCandidateSet, ...], CurriculumVersion]:
    catalog = _catalog(tuple(_course(f"C{index}", name) for index, name in enumerate(names)))
    records = tuple(_record(name, row=index + 1) for index, name in enumerate(names))
    return build_identity_candidates(records, catalog, target_version_id=VERSION), catalog


def _assertion(sets, *, row: int = 1, decision=StudentIdentityDecision.SELECTED,
               candidate: IdentityCandidate | None = None, **overrides) -> StudentIdentityAssertion:
    item = next(s for s in sets if s.completed_source_record == f"pdf:{row}")
    chosen = candidate if candidate is not None else (item.candidates[0] if item.candidates else None)
    payload = {
        "completed_source_id": item.completed_source_id,
        "completed_source_record": item.completed_source_record,
        "target_version_id": VERSION,
        "decision": decision,
        "assertion_source": STUDENT_ASSERTION_SOURCE,
        "selected_candidate": chosen if decision is StudentIdentityDecision.SELECTED else None,
    }
    payload.update(overrides)
    return StudentIdentityAssertion(**payload)


def _validate(sets, assertions):
    return validate_identity_assertions(
        sets, assertions, current_source_id=SOURCE, current_target_version_id=VERSION
    )


# ------------------------------------------------- 1. selecting a unique candidate


def test_selecting_the_only_candidate_is_accepted() -> None:
    sets, _ = _setup()
    assertion = _assertion(sets)
    out = _validate(sets, [assertion])
    assert len(out) == 1
    assert out[0].decision is StudentIdentityDecision.SELECTED
    assert out[0].selected_candidate is not None
    assert out[0].selected_candidate.course_id == "C0"
    # Explicitly not a recognition.
    assert out[0].is_a_recognition is False


# ------------------------------------------- 2. choosing among many candidates


def test_selecting_a_specific_entry_among_many_is_accepted() -> None:
    catalog = _catalog(tuple(
        _course("PE101", "体育", source_record=f"DEMO-CATALOG#PE101-{n}") for n in range(6)
    ))
    sets = build_identity_candidates((_record("体育"),), catalog, target_version_id=VERSION)
    assert sets[0].status is IdentityStatus.AMBIGUOUS

    third = sets[0].candidates[2]
    out = _validate(sets, [_assertion(sets, candidate=third)])

    chosen = out[0].selected_candidate
    assert chosen is not None
    # The exact displayed entry is identifiable, even though all six share a course id.
    assert chosen.identity == (VERSION, "PE101", "DEMO-CATALOG#PE101-2", 2)
    assert chosen.catalog_entry_ordinal == 2
    assert sum(1 for c in sets[0].candidates if c.course_id == "PE101") == 6


def test_a_bare_course_id_cannot_be_expressed_as_a_selection() -> None:
    """A selection always carries the whole candidate, never just a course number."""
    fields = {f.name for f in dataclasses.fields(StudentIdentityAssertion)}
    assert "selected_candidate" in fields
    for banned in ("selected_course_id", "course_id", "candidate_course_id"):
        assert banned not in fields, banned


# ------------------------------------------- 3. choosing a non-existent candidate


def test_selecting_a_candidate_that_does_not_exist_is_rejected() -> None:
    sets, _ = _setup()
    invented = IdentityCandidate(
        source_version_id=VERSION, target_version_id=VERSION,
        course_id="GHOST", course_name="伪造课程", course_requirement="required",
        match_method=sets[0].candidates[0].match_method,
        evidence="伪造", catalog_source_record="DEMO-CATALOG#GHOST",
        catalog_entry_ordinal=99,
        completed_source_id=SOURCE, completed_source_record="pdf:1",
        completed_course_name="线性代数", completed_passed=True,
    )
    with pytest.raises(CurriculumNormalizationError) as error:
        _validate(sets, [_assertion(sets, candidate=invented)])
    assert "not in this record's candidates" in str(error.value)


def test_selecting_for_a_record_with_no_candidates_is_rejected() -> None:
    catalog = _catalog((_course("C0", "线性代数"),))
    sets = build_identity_candidates((_record("完全不存在"),), catalog, target_version_id=VERSION)
    assert sets[0].status is IdentityStatus.UNRESOLVED

    # Build a candidate shape by hand; the record still has none to choose from.
    forged = IdentityCandidate(
        source_version_id=VERSION, target_version_id=VERSION,
        course_id="C0", course_name="线性代数", course_requirement="required",
        match_method=sets[0].candidates[0].match_method if sets[0].candidates else
        __import__("app.curriculum.identity_candidates", fromlist=["x"]).IdentityMatchMethod.EXACT_NORMALIZED_NAME,
        evidence="e", catalog_source_record="DEMO-CATALOG#C0", catalog_entry_ordinal=0,
        completed_source_id=SOURCE, completed_source_record="pdf:1",
        completed_course_name="完全不存在", completed_passed=True,
    )
    with pytest.raises(CurriculumNormalizationError) as error:
        _validate(sets, [_assertion(sets, candidate=forged)])
    assert "no candidates" in str(error.value)


# ------------------------------------------- 4. choosing another record's candidate


def test_selecting_another_records_candidate_is_rejected() -> None:
    sets, _ = _setup(("线性代数", "高等数学"))
    other = next(s for s in sets if s.completed_source_record == "pdf:2")
    other_candidate = other.candidates[0]

    with pytest.raises(CurriculumNormalizationError) as error:
        _validate(sets, [_assertion(sets, row=1, candidate=other_candidate)])
    assert "belongs to another record" in str(error.value)


# ------------------------------------------------- 5 & 6. rejected and deferred


def test_rejecting_all_candidates_is_accepted() -> None:
    sets, _ = _setup(("线性代数",))
    out = _validate(sets, [_assertion(sets, decision=StudentIdentityDecision.REJECTED)])
    assert out[0].decision is StudentIdentityDecision.REJECTED
    assert out[0].selected_candidate is None


def test_deferring_is_accepted() -> None:
    sets, _ = _setup()
    out = _validate(sets, [_assertion(sets, decision=StudentIdentityDecision.DEFERRED)])
    assert out[0].decision is StudentIdentityDecision.DEFERRED
    assert out[0].selected_candidate is None


def test_rejected_must_not_carry_a_candidate() -> None:
    sets, _ = _setup()
    with pytest.raises(CurriculumNormalizationError):
        StudentIdentityAssertion(
            completed_source_id=SOURCE, completed_source_record="pdf:1",
            target_version_id=VERSION, decision=StudentIdentityDecision.REJECTED,
            assertion_source=STUDENT_ASSERTION_SOURCE,
            selected_candidate=sets[0].candidates[0],
        )


def test_deferred_must_not_carry_a_candidate() -> None:
    sets, _ = _setup()
    with pytest.raises(CurriculumNormalizationError):
        StudentIdentityAssertion(
            completed_source_id=SOURCE, completed_source_record="pdf:1",
            target_version_id=VERSION, decision=StudentIdentityDecision.DEFERRED,
            assertion_source=STUDENT_ASSERTION_SOURCE,
            selected_candidate=sets[0].candidates[0],
        )


def test_selected_requires_a_candidate() -> None:
    with pytest.raises(CurriculumNormalizationError):
        StudentIdentityAssertion(
            completed_source_id=SOURCE, completed_source_record="pdf:1",
            target_version_id=VERSION, decision=StudentIdentityDecision.SELECTED,
            assertion_source=STUDENT_ASSERTION_SOURCE, selected_candidate=None,
        )


def test_unknown_decision_is_rejected() -> None:
    sets, _ = _setup()
    with pytest.raises(CurriculumNormalizationError):
        _assertion(sets, decision="maybe")


def test_non_student_assertion_source_is_rejected() -> None:
    """This object may not be used to claim an authorised decision."""
    for bad in ("school", "authorised-reviewer", "admin", ""):
        with pytest.raises(CurriculumNormalizationError):
            _assertion(sets=_setup()[0], assertion_source=bad)


# ------------------------------------------------- 7. duplicate / conflicting


def test_two_decisions_for_one_record_are_rejected() -> None:
    sets, _ = _setup()
    first = _assertion(sets)
    second = _assertion(sets, decision=StudentIdentityDecision.REJECTED)
    with pytest.raises(CurriculumNormalizationError) as error:
        _validate(sets, [first, second])
    assert "already has a" in str(error.value)


def test_identical_duplicate_decisions_are_also_rejected() -> None:
    sets, _ = _setup()
    first = _assertion(sets)
    with pytest.raises(CurriculumNormalizationError):
        _validate(sets, [first, first])


def test_deferred_then_decided_for_one_record_is_rejected() -> None:
    sets, _ = _setup()
    deferred = _assertion(sets, decision=StudentIdentityDecision.DEFERRED)
    decided = _assertion(sets)
    with pytest.raises(CurriculumNormalizationError):
        _validate(sets, [deferred, decided])


def test_deferred_repeated_is_rejected_because_it_is_still_a_second_statement() -> None:
    """Duplicates are strict: the server never picks a winner by submission order."""
    sets, _ = _setup()
    with pytest.raises(CurriculumNormalizationError):
        _validate(sets, [
            _assertion(sets, decision=StudentIdentityDecision.DEFERRED),
            _assertion(sets, decision=StudentIdentityDecision.DEFERRED),
        ])


def test_two_records_may_each_be_decided() -> None:
    sets, _ = _setup(("线性代数", "高等数学"))
    out = _validate(sets, [_assertion(sets, row=1), _assertion(sets, row=2)])
    assert len(out) == 2
    assert {a.record_reference for a in out} == {(SOURCE, "pdf:1"), (SOURCE, "pdf:2")}


# ------------------------------------------------- 8. transcript source changed


def test_a_changed_transcript_invalidates_old_assertions() -> None:
    sets, catalog = _setup()
    old = _assertion(sets)
    # Re-upload the same content? No: a changed artifact yields a new digest.
    new_source = "upload:pdf:sha256:differentdigest"
    new_sets = build_identity_candidates((_record("线性代数", source_id=new_source),),
                                        catalog, target_version_id=VERSION)
    with pytest.raises(CurriculumNormalizationError) as error:
        validate_identity_assertions(
            new_sets, [old], current_source_id=new_source, current_target_version_id=VERSION
        )
    assert "does not match the current transcript" in str(error.value)


def test_assertion_whose_source_differs_from_context_is_rejected() -> None:
    sets, _ = _setup()
    with pytest.raises(CurriculumNormalizationError):
        validate_identity_assertions(
            sets, [_assertion(sets)],
            current_source_id="upload:pdf:sha256:another", current_target_version_id=VERSION,
        )


# ------------------------------------------------- 9. catalogue version changed


def test_a_changed_catalogue_version_invalidates_old_assertions() -> None:
    sets, _ = _setup()
    old = _assertion(sets)
    with pytest.raises(CurriculumNormalizationError) as error:
        validate_identity_assertions(
            sets, [old], current_source_id=SOURCE, current_target_version_id="DEMO-VERSION-OTHER"
        )
    assert "does not match the current catalogue" in str(error.value)


def test_record_from_another_transcript_is_rejected() -> None:
    sets, _ = _setup()
    foreign = StudentIdentityAssertion(
        completed_source_id="upload:pdf:sha256:other", completed_source_record="pdf:1",
        target_version_id=VERSION, decision=StudentIdentityDecision.REJECTED,
        assertion_source=STUDENT_ASSERTION_SOURCE,
    )
    with pytest.raises(CurriculumNormalizationError):
        _validate(sets, [foreign])


def test_unknown_record_reference_is_rejected() -> None:
    sets, _ = _setup()
    missing = StudentIdentityAssertion(
        completed_source_id=SOURCE, completed_source_record="pdf:999",
        target_version_id=VERSION, decision=StudentIdentityDecision.REJECTED,
        assertion_source=STUDENT_ASSERTION_SOURCE,
    )
    with pytest.raises(CurriculumNormalizationError) as error:
        _validate(sets, [missing])
    assert "not part of the current transcript" in str(error.value)


def test_records_are_never_located_by_name_or_index() -> None:
    """Only (source_id, source_record) identifies a record."""
    sets, _ = _setup(("线性代数", "高等数学"))
    by_name = StudentIdentityAssertion(
        completed_source_id=SOURCE, completed_source_record="线性代数",
        target_version_id=VERSION, decision=StudentIdentityDecision.REJECTED,
        assertion_source=STUDENT_ASSERTION_SOURCE,
    )
    with pytest.raises(CurriculumNormalizationError):
        _validate(sets, [by_name])
    by_index = StudentIdentityAssertion(
        completed_source_id=SOURCE, completed_source_record="0",
        target_version_id=VERSION, decision=StudentIdentityDecision.REJECTED,
        assertion_source=STUDENT_ASSERTION_SOURCE,
    )
    with pytest.raises(CurriculumNormalizationError):
        _validate(sets, [by_index])


# ------------------------------------------- 10. same name, different records


def test_two_records_with_the_same_name_are_asserted_separately() -> None:
    catalog = _catalog((_course("PE101", "体育"),))
    records = (_record("体育", row=7), _record("体育", row=18))
    sets = build_identity_candidates(records, catalog, target_version_id=VERSION)

    out = _validate(sets, [_assertion(sets, row=7), _assertion(sets, row=18)])

    assert len(out) == 2
    assert [a.completed_source_record for a in out] == ["pdf:7", "pdf:18"]
    assert len({a.record_reference for a in out}) == 2


def test_assertions_for_record_selects_only_that_record() -> None:
    catalog = _catalog((_course("PE101", "体育"),))
    sets = build_identity_candidates(
        (_record("体育", row=7), _record("体育", row=18)), catalog, target_version_id=VERSION
    )
    assertions = _validate(sets, [_assertion(sets, row=7), _assertion(sets, row=18)])
    only = assertions_for_record(assertions, source_id=SOURCE, source_record="pdf:18")
    assert len(only) == 1
    assert only[0].completed_source_record == "pdf:18"


# ------------------------------------------------- 11. evidence-free assertion


def test_assertion_requires_a_nonempty_source_and_reference() -> None:
    for overrides in (
        {"assertion_source": ""},
        {"completed_source_id": ""},
        {"completed_source_record": "   "},
        {"target_version_id": ""},
    ):
        with pytest.raises(CurriculumNormalizationError):
            _assertion(_setup()[0], **overrides)


def test_note_is_optional_but_must_be_text() -> None:
    sets, _ = _setup()
    assert _assertion(sets).note is None
    assert _assertion(sets, note="  手写备注  ").note == "手写备注"
    with pytest.raises(CurriculumNormalizationError):
        _assertion(sets, note=123)


# ------------------------------------------- 12. no recognition / credit leakage


def test_assertions_never_produce_a_recognition_or_credit() -> None:
    sets, _ = _setup(("线性代数", "高等数学", "大学物理"))
    assertions = _validate(sets, [
        _assertion(sets, row=1),
        _assertion(sets, row=2, decision=StudentIdentityDecision.REJECTED),
        _assertion(sets, row=3, decision=StudentIdentityDecision.DEFERRED),
    ])
    for assertion in assertions:
        assert assertion.is_a_recognition is False
        for banned in ("recognized_credit", "credit", "satisfied", "recognition",
                       "makeup_status", "course_id_status"):
            assert not hasattr(assertion, banned), banned
    fields = {f.name for f in dataclasses.fields(StudentIdentityAssertion)}
    assert fields.isdisjoint({"recognized_credit", "credit", "satisfied", "recognition"})


def test_assertions_do_not_mutate_the_completed_records() -> None:
    """A student pick must never become an authoritative identity on the record."""
    catalog = _catalog((_course("C0", "线性代数"),))
    record = _record("线性代数", row=1)
    sets = build_identity_candidates((record,), catalog, target_version_id=VERSION)
    _validate(sets, [_assertion(sets)])

    # The original frozen record is untouched: identity is still pending.
    assert record.course_id is None
    assert record.course_id_status is CourseIdStatus.PENDING
    assert record.id_match_source is None


def test_module_never_touches_the_recognition_machinery() -> None:
    """Docstrings may name the boundary; imports and code may not cross it."""
    module = __import__("app.curriculum.identity_assertions", fromlist=["x"])
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body.pop(0)
    code = ast.unparse(tree)
    for banned in (
        "ConfirmedRecognition", "ConfirmedMissingRequirement", "ConfirmedElectiveSelection",
        "ConfirmedGroupScopeDecision", "MatchingRules", "build_curriculum_diff",
        "MakeupStatus", "MakeupTask", "recognized_credit", "SATISFIED",
        "case_a_decisions", "CurriculumCase", "get_makeup_tasks",
        "CourseIdStatus.CONFIRMED",
    ):
        assert banned not in code, f"assertion module must not reference {banned}"


def test_the_two_decision_objects_are_distinct_types() -> None:
    from app.curriculum import identity_assertions as module
    from app.curriculum import matching as matching_module

    assert set(module.__all__) == {
        "StudentIdentityDecision", "StudentIdentityAssertion",
        "validate_identity_assertions", "assertions_for_record",
    }
    # The student object is a real type, and is not any recognition type.
    assert isinstance(StudentIdentityAssertion, type)
    assert StudentIdentityAssertion is not matching_module.ConfirmedRecognition
    assert not issubclass(StudentIdentityAssertion, matching_module.ConfirmedRecognition)
    assert not issubclass(matching_module.ConfirmedRecognition, StudentIdentityAssertion)


def test_recognition_classes_are_not_subclasses_of_the_assertion() -> None:
    from app.curriculum import matching as matching_module

    for cls in (matching_module.ConfirmedRecognition,
                matching_module.ConfirmedMissingRequirement,
                matching_module.ConfirmedElectiveSelection):
        assert not issubclass(cls, StudentIdentityAssertion)


def test_empty_inputs_are_accepted() -> None:
    sets, _ = _setup()
    assert _validate(sets, []) == ()
    assert validate_identity_assertions(
        (), [], current_source_id=SOURCE, current_target_version_id=VERSION
    ) == ()


# ------------------------------- stale candidate sets (rejected even with no assertions)


def test_stale_candidate_set_is_rejected_even_with_no_assertions() -> None:
    """Candidate sets from another transcript must not pass as an empty input."""
    sets, _ = _setup()
    assert _validate(sets, []) == ()  # the matching context is fine

    with pytest.raises(CurriculumNormalizationError) as error:
        validate_identity_assertions(
            sets, [], current_source_id="upload:pdf:sha256:changed",
            current_target_version_id=VERSION,
        )
    assert "candidate_sets: record source does not match" in str(error.value)


def test_stale_catalogue_candidate_set_is_rejected_even_with_no_assertions() -> None:
    sets, _ = _setup()
    with pytest.raises(CurriculumNormalizationError) as error:
        validate_identity_assertions(
            sets, [], current_source_id=SOURCE,
            current_target_version_id="DEMO-VERSION-OTHER",
        )
    assert "candidate_sets: target version does not match" in str(error.value)


def test_stale_candidate_set_is_rejected_before_assertions_are_examined() -> None:
    """The set check runs first, so a stale set fails even alongside a valid assertion."""
    sets, _ = _setup()
    good_assertion = _assertion(sets)
    with pytest.raises(CurriculumNormalizationError) as error:
        validate_identity_assertions(
            sets, [good_assertion], current_source_id="upload:pdf:sha256:changed",
            current_target_version_id=VERSION,
        )
    assert "candidate_sets:" in str(error.value)


def test_partially_mixed_sources_are_rejected() -> None:
    """One stale set among valid ones is enough to reject the whole call."""
    catalog = _catalog((_course("C0", "线性代数"), _course("C1", "高等数学")))
    records = (
        _record("线性代数", row=1),
        _record("高等数学", row=2),
        _record("线性代数", row=3, source_id="upload:pdf:sha256:stale"),
    )
    with pytest.raises(CurriculumNormalizationError):
        build_identity_candidates(records, catalog, target_version_id=VERSION)

    # Build each set separately so a mixed collection can be assembled by hand.
    fresh = build_identity_candidates(
        (_record("线性代数", row=1),), catalog, target_version_id=VERSION
    )
    stale = build_identity_candidates(
        (_record("线性代数", row=3, source_id="upload:pdf:sha256:stale"),),
        catalog, target_version_id=VERSION,
    )
    assert fresh[0].completed_source_id != stale[0].completed_source_id

    with pytest.raises(CurriculumNormalizationError) as error:
        validate_identity_assertions(
            (*fresh, *stale), [], current_source_id=SOURCE,
            current_target_version_id=VERSION,
        )
    assert "candidate_sets: record source does not match" in str(error.value)


def test_partially_mixed_versions_are_rejected() -> None:
    catalog = _catalog((_course("C0", "线性代数"),))
    other = _catalog((_course("C0", "线性代数"),), version_id="DEMO-VERSION-OTHER")
    fresh = build_identity_candidates((_record("线性代数", row=1),), catalog,
                                      target_version_id=VERSION)
    stale = build_identity_candidates((_record("线性代数", row=2),), other,
                                      target_version_id="DEMO-VERSION-OTHER")
    # Different records, so identity is not what trips the check.
    assert fresh[0].record_reference != stale[0].record_reference
    assert fresh[0].target_version_id != stale[0].target_version_id

    with pytest.raises(CurriculumNormalizationError) as error:
        validate_identity_assertions(
            (*fresh, *stale), [], current_source_id=SOURCE, current_target_version_id=VERSION,
        )
    assert "candidate_sets: target version does not match" in str(error.value)


def test_matching_candidate_sets_with_no_assertions_still_pass() -> None:
    """The regression guard: legitimate empty input must keep working."""
    sets, _ = _setup(("线性代数", "高等数学"))
    assert validate_identity_assertions(
        sets, [], current_source_id=SOURCE, current_target_version_id=VERSION
    ) == ()
    # And with assertions, the ordinary path is unaffected.
    out = _validate(sets, [_assertion(sets, row=1)])
    assert len(out) == 1


def test_duplicate_record_identity_in_supplied_sets_is_rejected() -> None:
    sets, _ = _setup()
    with pytest.raises(CurriculumNormalizationError):
        _validate([sets[0], sets[0]], [])
