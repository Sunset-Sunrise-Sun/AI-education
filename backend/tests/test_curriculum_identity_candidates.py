"""Course-identity candidates: exact-name matching, evidence, and the safety boundary.

Covers the nine required situations and, most importantly, proves that this module is
**identity only**: it never recognises credit, never satisfies a requirement, and never
constructs a recognition decision.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from app.curriculum.completed_courses import CompletedCourse, CourseIdStatus
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.identity_candidates import (
    IdentityCandidate,
    IdentityCandidateSet,
    IdentityMatchMethod,
    IdentityStatus,
    build_identity_candidates,
    normalize_course_name,
)
from app.curriculum.requirements import CurriculumCourse, CurriculumVersion, RequirementKind

VERSION = "DEMO-VERSION-NEW"


def _course(
    course_id: str, course_name: str, *,
    requirement: RequirementKind = RequirementKind.REQUIRED,
    credit: float = 3.0,
    source_record: str | None = None,
) -> CurriculumCourse:
    return CurriculumCourse(
        course_id=course_id,
        course_name=course_name,
        credit=credit,
        requirement=requirement,
        source_record=source_record or f"DEMO-CATALOG#{course_id}",
        prerequisites=(),
    )


def _catalog(courses: tuple[CurriculumCourse, ...], *, version_id: str = VERSION) -> CurriculumVersion:
    return CurriculumVersion(
        version_id=version_id,
        major="DEMO Major",
        cohort="DEMO Cohort",
        source_id="DEMO-CATALOG-SOURCE",
        courses=courses,
        complete=True,
        completeness_evidence="DEMO-CATALOG-COMPLETE",
    )


def _record(
    course_name: str, *, row: int = 1, passed: bool = True,
    course_id: str | None = None, source_id: str = "DEMO-COMPLETED",
) -> CompletedCourse:
    return CompletedCourse(
        course_id=course_id,
        course_name=course_name,
        credit=3.0,
        semester="DEMO-ACTUAL-TERM",
        passed=passed,
        course_type="DEMO Context",
        course_id_status=CourseIdStatus.PENDING if course_id is None else CourseIdStatus.CONFIRMED,
        id_match_source=None if course_id is None else "DEMO-ID-EVIDENCE",
        source_id=source_id,
        source_record=f"pdf:{row}",
    )


# ---------------------------------------------------------------- 1. unique match


def test_exact_match_yields_exactly_one_candidate() -> None:
    catalog = _catalog((_course("DCS101", "线性代数"), _course("DCS102", "高等数学")))
    record = _record("线性代数")

    sets = build_identity_candidates((record,), catalog, target_version_id=VERSION)

    assert len(sets) == 1
    item = sets[0]
    assert item.status is IdentityStatus.CANDIDATES_FOUND
    assert len(item.candidates) == 1
    candidate = item.candidates[0]
    assert candidate.course_id == "DCS101"
    assert candidate.course_name == "线性代数"
    assert candidate.match_method is IdentityMatchMethod.EXACT_NORMALIZED_NAME
    assert candidate.source_version_id == VERSION
    assert candidate.target_version_id == VERSION
    # Evidence is always present and names the version.
    assert candidate.evidence and VERSION in candidate.evidence
    # Still needs a human: identity is not equivalence and not credit.
    assert item.needs_confirmation is True
    assert "授权依据" in item.pending_reason


def test_normalisation_ignores_case_width_and_whitespace() -> None:
    catalog = _catalog((_course("X1", "Linear Algebra"),))
    for variant in ("linear algebra", "LINEAR ALGEBRA", "Linear  Algebra", "Ｌｉｎｅａｒ Ａｌｇｅｂｒａ"):
        sets = build_identity_candidates((_record(variant),), catalog, target_version_id=VERSION)
        assert sets[0].status is IdentityStatus.CANDIDATES_FOUND, variant
        assert sets[0].candidates[0].course_id == "X1", variant


def test_normalize_course_name_rejects_blank() -> None:
    for blank in ("", "   ", "\u3000"):
        with pytest.raises(CurriculumNormalizationError):
            normalize_course_name(blank)


# ------------------------------------------------------------ 2. multiple matches


def test_multiple_exact_matches_are_all_kept_and_none_is_chosen() -> None:
    catalog = _catalog((
        _course("DCS101", "线性代数"),
        _course("MTH101", "线性代数"),
        _course("PHY101", "线性代数"),
    ))
    sets = build_identity_candidates((_record("线性代数"),), catalog, target_version_id=VERSION)

    item = sets[0]
    assert item.status is IdentityStatus.AMBIGUOUS
    assert [c.course_id for c in item.candidates] == ["DCS101", "MTH101", "PHY101"]
    assert all(c.match_method is IdentityMatchMethod.EXACT_NORMALIZED_NAME for c in item.candidates)
    assert "3" in item.pending_reason
    assert item.needs_confirmation is True


# ----------------------------------------------------------------- 3. no match


def test_no_match_is_reported_as_unresolved_without_inventing_an_identity() -> None:
    catalog = _catalog((_course("DCS101", "线性代数"),))
    sets = build_identity_candidates((_record("完全不存在的课程"),), catalog, target_version_id=VERSION)

    item = sets[0]
    assert item.status is IdentityStatus.UNRESOLVED
    assert item.candidates == ()
    assert item.needs_confirmation is True
    assert "无法确定" in item.pending_reason
    # No course number may be invented from a name.
    assert not hasattr(item, "course_id")


# --------------------------------------------- 4. duplicate transcript records


def test_two_transcript_rows_with_the_same_name_are_reported_separately() -> None:
    catalog = _catalog((_course("PED101", "体育"),))
    sets = build_identity_candidates(
        (_record("体育", row=7), _record("体育", row=19)), catalog, target_version_id=VERSION
    )

    assert len(sets) == 2
    assert sets[0].record_reference == ("DEMO-COMPLETED", "pdf:7")
    assert sets[1].record_reference == ("DEMO-COMPLETED", "pdf:19")
    assert sets[0].record_reference != sets[1].record_reference
    for item in sets:
        assert len(item.candidates) == 1
        assert item.candidates[0].completed_source_record in ("pdf:7", "pdf:19")
        # Each candidate is bound to its own record, never merged.
        assert item.candidates[0].record_reference == item.record_reference


def test_records_are_returned_in_input_order_including_repeats() -> None:
    catalog = _catalog((_course("A", "甲"), _course("B", "乙")))
    sets = build_identity_candidates(
        (_record("甲", row=1), _record("乙", row=2), _record("甲", row=3)),
        catalog, target_version_id=VERSION,
    )
    assert [s.record_reference for s in sets] == [
        ("DEMO-COMPLETED", "pdf:1"),
        ("DEMO-COMPLETED", "pdf:2"),
        ("DEMO-COMPLETED", "pdf:3"),
    ]


# ------------------------------------------------- 5. missing source / version


def test_missing_target_version_is_rejected() -> None:
    catalog = _catalog((_course("A", "甲"),))
    for bad in ("", "   "):
        with pytest.raises(CurriculumNormalizationError):
            build_identity_candidates((_record("甲"),), catalog, target_version_id=bad)


def test_catalog_version_must_match_the_requested_target_version() -> None:
    catalog = _catalog((_course("A", "甲"),), version_id="DEMO-VERSION-OLD")
    with pytest.raises(CurriculumNormalizationError):
        build_identity_candidates((_record("甲"),), catalog, target_version_id=VERSION)


def test_non_catalog_input_is_rejected() -> None:
    with pytest.raises(CurriculumNormalizationError):
        build_identity_candidates((_record("甲"),), object(), target_version_id=VERSION)  # type: ignore[arg-type]


def test_unexpected_record_type_is_rejected() -> None:
    catalog = _catalog((_course("A", "甲"),))
    with pytest.raises(CurriculumNormalizationError):
        build_identity_candidates((object(),), catalog, target_version_id=VERSION)  # type: ignore[arg-type]


# ------------------------------------------------------- 6. identity already unique


def test_already_confirmed_record_yields_no_candidate() -> None:
    catalog = _catalog((_course("DCS101", "线性代数"),))
    record = _record("线性代数", course_id="DCS101")

    sets = build_identity_candidates((record,), catalog, target_version_id=VERSION)

    item = sets[0]
    assert item.status is IdentityStatus.ALREADY_CONFIRMED
    assert item.candidates == ()
    assert item.needs_confirmation is False
    # Nothing is re-derived from the name for an already-identified record.
    assert "无需" in item.pending_reason


# --------------------------------------------- 7. candidate source vs target version


def test_every_candidate_carries_both_source_and_target_version() -> None:
    catalog = _catalog((_course("DCS101", "线性代数"), _course("DCS102", "线性代数")))
    sets = build_identity_candidates((_record("线性代数"),), catalog, target_version_id=VERSION)
    for candidate in sets[0].candidates:
        assert candidate.source_version_id == VERSION
        assert candidate.target_version_id == VERSION
        assert candidate.source_version_id == candidate.target_version_id


def test_candidate_from_a_foreign_version_cannot_be_constructed() -> None:
    """A candidate whose source version differs from its target version is invalid."""
    with pytest.raises(CurriculumNormalizationError):
        IdentityCandidate(
            source_version_id="OTHER-VERSION",
            target_version_id=VERSION,
            course_id="X",
            course_name="甲",
            course_requirement="required",
            match_method=IdentityMatchMethod.EXACT_NORMALIZED_NAME,
            evidence="e",
            catalog_source_record="c",
            catalog_entry_ordinal=0,
            completed_source_id="s",
            completed_source_record="pdf:1",
            completed_course_name="甲",
            completed_passed=True,
        )


def test_entries_sharing_a_course_id_get_distinct_identities() -> None:
    """The real 体育 shape: one course id, six catalogue entries.

    ``CurriculumVersion`` guarantees a unique ``source_record`` while allowing a
    repeated ``course_id``, so identity must include the catalogue record (and the
    ordinal) — a bare course id would collapse all six into one choice.
    """
    catalog = _catalog(tuple(
        _course("PE101", "体育", source_record=f"DEMO-CATALOG#PE101-{n}")
        for n in range(6)
    ))

    sets = build_identity_candidates((_record("体育"),), catalog, target_version_id=VERSION)

    item = sets[0]
    assert item.status is IdentityStatus.AMBIGUOUS
    assert len(item.candidates) == 6
    identities = [c.identity for c in item.candidates]
    assert len(set(identities)) == 6, "each entry needs a distinct identity"
    # All six share the course id, so that alone could not identify a choice.
    assert {c.course_id for c in item.candidates} == {"PE101"}
    assert [c.catalog_entry_ordinal for c in item.candidates] == [0, 1, 2, 3, 4, 5]
    assert len({c.catalog_source_record for c in item.candidates}) == 6


def test_candidate_identity_exposes_version_course_source_and_ordinal() -> None:
    catalog = _catalog((_course("DCS101", "线性代数"),))
    candidate = build_identity_candidates(
        (_record("线性代数"),), catalog, target_version_id=VERSION
    )[0].candidates[0]
    assert candidate.identity == (VERSION, "DCS101", "DEMO-CATALOG#DCS101", 0)


def test_negative_or_boolean_entry_ordinal_is_rejected() -> None:
    for bad in (-1, True):
        with pytest.raises(CurriculumNormalizationError):
            IdentityCandidate(
                source_version_id=VERSION, target_version_id=VERSION,
                course_id="X", course_name="甲", course_requirement="required",
                match_method=IdentityMatchMethod.EXACT_NORMALIZED_NAME,
                evidence="e", catalog_source_record="c", catalog_entry_ordinal=bad,
                completed_source_id="s", completed_source_record="pdf:1",
                completed_course_name="甲", completed_passed=True,
            )


# ------------------------------------------------- 8. failed record -> candidates only


def test_failed_record_still_yields_candidates_but_no_recognition() -> None:
    catalog = _catalog((_course("DCS101", "线性代数"),))
    sets = build_identity_candidates(
        (_record("线性代数", passed=False),), catalog, target_version_id=VERSION
    )

    item = sets[0]
    assert item.completed_passed is False
    assert item.status is IdentityStatus.CANDIDATES_FOUND
    assert len(item.candidates) == 1
    assert item.candidates[0].completed_passed is False
    assert any(note.startswith("record_not_passed:") for note in item.notes)
    # No credit is asserted anywhere for a failed record.
    assert not hasattr(item.candidates[0], "recognized_credit")


# ------------------------------------ 9. no recognition / SATISFIED / credit leakage


def test_module_never_touches_recognition_machinery() -> None:
    """The module may *describe* the boundary in prose but must not import or use it.

    The module docstring deliberately names the machinery it refuses to touch, so the
    check strips **every** docstring from the parsed module and searches the remaining
    code + message literals. Otherwise the documentation explaining the boundary would
    itself trip the guard.
    """
    import ast

    module = __import__("app.curriculum.identity_candidates", fromlist=["x"])
    tree = ast.parse(inspect.getsource(module))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        # A module's docstring is its first statement, even after __future__ imports
        # it is still statement 0 of the module body.
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body.pop(0)

    code = ast.unparse(tree)
    for banned in (
        "ConfirmedRecognition",
        "ConfirmedMissingRequirement",
        "ConfirmedElectiveSelection",
        "ConfirmedGroupScopeDecision",
        "MatchingRules",
        "build_curriculum_diff",
        "MakeupStatus",
        "MakeupTask",
        "recognized_credit",
        "SATISFIED",
        "case_a_decisions",
        "CurriculumCase",
        "get_makeup_tasks",
    ):
        assert banned not in code, f"identity module must not reference {banned}"


def test_no_output_object_exposes_credit_or_status_recognition() -> None:
    catalog = _catalog((_course("DCS101", "线性代数"),))
    sets = build_identity_candidates((_record("线性代数"),), catalog, target_version_id=VERSION)

    fields = {f.name for f in dataclasses.fields(IdentityCandidate)}
    fields |= {f.name for f in dataclasses.fields(IdentityCandidateSet)}
    for banned in ("recognized_credit", "credit", "status_recognition", "satisfied", "recognition"):
        assert banned not in fields, banned
    # No enum member may report a recognition outcome.
    assert {s.value for s in IdentityStatus} == {
        "candidates_found", "ambiguous", "unresolved", "already_confirmed",
    }
    assert all("recogni" not in s.value for s in IdentityStatus)
    assert all(c.match_method is IdentityMatchMethod.EXACT_NORMALIZED_NAME
               for s in sets for c in s.candidates)


def test_only_exact_normalized_equality_is_implemented() -> None:
    """No fuzzy behaviour: near names, substrings and abbreviations must not match."""
    catalog = _catalog((_course("DCS101", "数据结构与算法"),))
    for near in (
        "数据结构",             # substring
        "数据结构与算法实验",     # longer
        "数据结构算法",          # missing a character
        "数据结构与算祛",         # one wrong character
        "DS & Algorithms",      # abbreviation
    ):
        sets = build_identity_candidates((_record(near),), catalog, target_version_id=VERSION)
        assert sets[0].status is IdentityStatus.UNRESOLVED, near
        assert sets[0].candidates == (), near


def test_objects_are_immutable() -> None:
    catalog = _catalog((_course("DCS101", "线性代数"),))
    item = build_identity_candidates((_record("线性代数"),), catalog, target_version_id=VERSION)[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.status = IdentityStatus.UNRESOLVED  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.candidates[0].course_id = "OTHER"  # type: ignore[misc]


def test_status_must_agree_with_candidate_payload() -> None:
    """A set cannot claim a unique match while carrying two candidates."""
    catalog = _catalog((_course("A", "甲"),))
    good = build_identity_candidates((_record("甲"),), catalog, target_version_id=VERSION)[0]
    with pytest.raises(CurriculumNormalizationError):
        IdentityCandidateSet(
            completed_source_id=good.completed_source_id,
            completed_source_record=good.completed_source_record,
            completed_course_name=good.completed_course_name,
            completed_passed=True,
            target_version_id=VERSION,
            status=IdentityStatus.CANDIDATES_FOUND,
            candidates=(good.candidates[0], good.candidates[0]),
            pending_reason="x",
        )


def test_empty_completed_input_yields_no_sets() -> None:
    catalog = _catalog((_course("A", "甲"),))
    assert build_identity_candidates((), catalog, target_version_id=VERSION) == ()


# ------------------------------------------- input identifier integrity (review fix)


def test_duplicate_record_identity_is_rejected_not_deduplicated() -> None:
    """One (source_id, source_record) cannot denote two rows.

    The input is not silently de-duplicated: that would hide the malformed row a
    reviewer needs to see.
    """
    catalog = _catalog((_course("A", "甲"),))
    first = _record("甲", row=5)
    same_again = _record("甲", row=5)

    assert first == same_again  # identical identifier AND identical content
    with pytest.raises(CurriculumNormalizationError) as error:
        build_identity_candidates((first, same_again), catalog, target_version_id=VERSION)
    assert "duplicate record identity" in str(error.value)


def test_duplicate_record_identity_is_rejected_even_when_content_differs() -> None:
    """Same identifier but different content is still an error, never a merge."""
    catalog = _catalog((_course("甲", "甲"), _course("乙", "乙")))
    one = _record("甲", row=9)
    conflicting = _record("乙", row=9)  # same source_record, different course name

    with pytest.raises(CurriculumNormalizationError) as error:
        build_identity_candidates((one, conflicting), catalog, target_version_id=VERSION)
    assert "duplicate record identity" in str(error.value)


def test_duplicate_identity_error_lists_the_offending_reference_only() -> None:
    """The error names the identifier, never the record's course name or content."""
    catalog = _catalog((_course("甲", "甲"),))
    with pytest.raises(CurriculumNormalizationError) as error:
        build_identity_candidates(
            (_record("甲", row=3), _record("甲", row=3)), catalog, target_version_id=VERSION
        )
    message = str(error.value)
    assert "pdf:3" in message
    assert "DEMO-COMPLETED" in message
    assert "甲" not in message


def test_same_name_with_distinct_source_records_stays_separate() -> None:
    """The legitimate real-transcript shape: two 体育 rows are two records."""
    catalog = _catalog((_course("PED101", "体育"),))
    sets = build_identity_candidates(
        (_record("体育", row=7), _record("体育", row=18)), catalog, target_version_id=VERSION
    )

    assert len(sets) == 2
    assert [s.record_reference for s in sets] == [
        ("DEMO-COMPLETED", "pdf:7"),
        ("DEMO-COMPLETED", "pdf:18"),
    ]
    assert all(s.status is IdentityStatus.CANDIDATES_FOUND for s in sets)


def test_mixing_two_source_ids_in_one_call_is_rejected() -> None:
    """Case A works within one transcript artifact; artifacts must not be mixed."""
    catalog = _catalog((_course("A", "甲"),))

    with pytest.raises(CurriculumNormalizationError) as error:
        build_identity_candidates(
            (_record("甲", row=1), _record("甲", row=2, source_id="DEMO-OTHER-SOURCE")),
            catalog,
            target_version_id=VERSION,
        )
    assert "more than one source_id" in str(error.value)


def test_mixing_source_ids_is_rejected_even_when_record_ids_do_not_clash() -> None:
    """Distinct source_records across distinct sources is still a mixed input."""
    catalog = _catalog((_course("甲", "甲"), _course("乙", "乙")))
    with pytest.raises(CurriculumNormalizationError):
        build_identity_candidates(
            (
                _record("甲", row=1),
                _record("乙", row=1, source_id="upload:pdf:sha256:otherdigest"),
            ),
            catalog,
            target_version_id=VERSION,
        )


def test_a_mixed_input_is_rejected_before_any_candidate_is_built() -> None:
    """The integrity check runs first, so no partial result can escape."""
    catalog = _catalog((_course("A", "甲"),))
    with pytest.raises(CurriculumNormalizationError):
        build_identity_candidates(
            (_record("甲", row=1, source_id="S1"), _record("甲", row=2, source_id="S2")),
            catalog,
            target_version_id=VERSION,
        )


def test_single_source_id_input_is_accepted() -> None:
    """The check must not reject the ordinary single-artifact input."""
    catalog = _catalog((_course("A", "甲"), _course("B", "乙")))
    sets = build_identity_candidates(
        (_record("甲", row=1), _record("乙", row=2)), catalog, target_version_id=VERSION
    )
    assert len(sets) == 2
    assert {s.completed_source_id for s in sets} == {"DEMO-COMPLETED"}
