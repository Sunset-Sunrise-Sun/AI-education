"""Real Case A scope decisions: range-term requirement entries, case-by-case.

The target plan (网络空间安全) prints some arrangement terms as ranges, which the
strict term parser deliberately refuses to interpret. Case A fixes the cut-off at
``as_of_term = "2025-2"`` by **case-owner confirmation** (the student transfers
after 2025-2 and follows the target plan from 2026-1) - this is NOT a school
official transfer policy.

Each entry below is decided only from the wording of its own range:

- a range that lies **entirely after** the cut-off is ``future``
  (that part of the plan is the normal post-transfer curriculum);
- a range that lies **entirely at or before** the cut-off would be ``historical``;
- a range that **crosses** the cut-off cannot be classified from the text and is
  deliberately left undecided (see ``UNDECIDED_CROSSING_CUTOFF``).

These are case data, not algorithm rules: another transfer student with the same
plan but a different transfer term needs a different decision set, and no scope
algorithm changes. No names, student numbers, marks, GPAs or private documents
appear here - only plan structure, which is already structural information.
"""

from __future__ import annotations

from app.curriculum.terms import ConfirmedScopeDecision

__all__ = [
    "AS_OF_TERM",
    "CASE_TARGET_VERSION_ID",
    "CONFIRMED_SCOPE_DECISIONS",
    "DECISION_EVIDENCE",
    "SATISFIED_UNRESOLVED_NO_DECISION",
    "UNDECIDED_CROSSING_CUTOFF",
    "confirmed_scope_decisions",
]

#: The explicit case-owner cut-off term (not derived from the system date).
AS_OF_TERM = "2025-2"

#: The internal target-version id used for the real Case A target plan.
CASE_TARGET_VERSION_ID = "case-a-new"

#: Evidence type for every decision here: a case-owner confirmation, not policy.
DECISION_EVIDENCE = "case-owner-confirmed://case-a/range-term-scope"

#: Ranges that lie **entirely after** 2025-2, so the normal post-transfer plan
#: covers them: they are future requirements and must not be projected as current
#: makeup tasks.
_CONFIRMED_FUTURE: tuple[tuple[str, str, str], ...] = (
    ("table:2!row:19", "MAR117", "2026-1~2026-2"),
    ("table:2!row:24", "MAR118", "2027-1~2027-2"),
    ("table:2!row:26", "MAR119", "2028-1~2028-2"),
)

#: Ranges that cross the cut-off: 2025-1~2028-2 starts before the transfer and
#: continues after it. Whether the pre-transfer part is a historical makeup gap,
#: whether the requirement is meant to be split at the transfer point, or whether
#: the whole entry belongs to the post-transfer plan is a business question the
#: document does not answer. No decision is recorded for it.
UNDECIDED_CROSSING_CUTOFF: dict[str, str] = {
    "source_record": "table:2!row:11",
    "course_id": "PUB178",
    "recommended_term_text": "2025-1~2028-2",
    "question": (
        "劳动教育 2025-1~2028-2 横跨转专业时点：应作为历史缺口、按转专业时点拆分，"
        "还是整体归属转专业后的正常培养计划？"
    ),
}

#: Range-term entries that are already satisfied. Under the frozen scope rules an
#: unresolved entry that is already SATISFIED keeps its status and does not block
#: projection, so no decision is recorded for them either.
SATISFIED_UNRESOLVED_NO_DECISION: tuple[tuple[str, str, str, str], ...] = (
    ("table:2!row:8", "MAR116", "2025-1~2025-2", "形势与政策（一·走在前列的广东实践）"),
    ("table:2!row:9", "PSY199", "2025-1~2025-2", "心理健康教育"),
    ("table:2!row:10", "PUB1991", "2025-1~2025-2", "国家安全教育"),
)

#: The decisions as plain data, so they can be reviewed without reading code.
CONFIRMED_SCOPE_DECISIONS: tuple[dict, ...] = tuple(
    {
        "target_version_id": CASE_TARGET_VERSION_ID,
        "target_source_record": source_record,
        "target_course_id": course_id,
        "decision": "future",
        "evidence": DECISION_EVIDENCE,
        "recommended_term_text": term,
    }
    for source_record, course_id, term in _CONFIRMED_FUTURE
)


def confirmed_scope_decisions() -> tuple[ConfirmedScopeDecision, ...]:
    """The Case A decisions as internal objects, ready for ``CurriculumCase``."""
    return tuple(
        ConfirmedScopeDecision(
            target_version_id=record["target_version_id"],
            target_source_record=record["target_source_record"],
            target_course_id=record["target_course_id"],
            decision=record["decision"],
            evidence=record["evidence"],
        )
        for record in CONFIRMED_SCOPE_DECISIONS
    )
