"""Real Case A scope decisions: range-term requirement entries, case-by-case.

The target plan (网络空间安全) prints some arrangement terms as ranges, which the
strict term parser deliberately refuses to interpret. Case A fixes the cut-off at
``as_of_term = "2025-2"`` by **case-owner confirmation** (the student transfers
after 2025-2 and follows the target plan from 2026-1) - this is NOT a school
official transfer policy.

Each entry below is decided only from the wording of its own range plus, where the
range crosses the cut-off, an explicit case-owner ruling:

- a range that lies **entirely after** the cut-off is ``future``;
- a range that lies **entirely at or before** the cut-off is ``historical``;
- a range that **crosses** the cut-off is decided ``future`` in Case A by explicit
  case-owner confirmation (see ``CASE_OWNER_FUTURE_RATIONALE``); without such a
  ruling it stays undecided rather than being guessed.

A decision answers **only** the scope question "historical or future?". It never
establishes course equivalence, course identity, completed-course recognition, or
automatic satisfaction, and it never supplies a course id.

These are case data, not algorithm rules: another transfer student with the same
plan but a different transfer term needs a different decision set, and no scope
algorithm changes. No names, student numbers, marks, GPAs or private documents
appear here - only plan structure, which is already structural information.
"""

from __future__ import annotations

from app.curriculum.terms import ConfirmedScopeDecision

__all__ = [
    "AS_OF_TERM",
    "CASE_OWNER_FUTURE_RATIONALE",
    "CASE_OWNER_HISTORICAL_RATIONALE",
    "CASE_TARGET_VERSION_ID",
    "CONFIRMED_SCOPE_DECISION_KEYS",
    "CONFIRMED_SCOPE_DECISIONS",
    "DECISION_EVIDENCE",
    "LEGACY_SCOPE_DECISION_KEYS",
    "SUPPORTED_SCOPE_DECISION_KEYS",
    "confirmed_scope_decisions",
]

#: Why the crossing range is still ``future`` in this case (case-owner ruling,
#: not a general rule and not school policy).
CASE_OWNER_FUTURE_RATIONALE = (
    "该培养方案安排窗口横跨 as_of_term=2025-2 且持续至 2028-2，"
    "没有证据表明必须在转专业时点前完成，也没有阶段性拆分规则；"
    "为避免把仍有后续履行窗口的要求误判成历史欠修，本 Case 按 future 处理。"
)

#: Why the three ranges ending at the cut-off are ``historical`` (case-owner
#: ruling, not a general rule and not school policy). These three entries used to
#: be left undecided on the reasoning "already satisfied needs no decision"; that
#: reasoning depended on the **completed-course identity** (a confirmed course id),
#: which a transcript PDF does not carry. Scope must not depend on recognition, so
#: the scope question is now answered explicitly and on its own evidence.
CASE_OWNER_HISTORICAL_RATIONALE = (
    "该三条安排区间整体落在 as_of_term=2025-2 **当日或之前**（2025-1~2025-2），"
    "属转专业时点之前的历史安排窗口；按本 Case 的 scope 口径记为 historical。"
    "该裁定**只回答 historical / future**，不表示课程等价、不确认课程身份、"
    "不构成已修课认定，也不使任何要求自动满足。"
)

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

#: One range **crosses** the cut-off: 2025-1~2028-2 starts before the transfer and
#: continues well after it. The case owner confirmed it as ``future`` for Case A:
#: the plan's arrangement window still runs to 2028-2, nothing shows the
#: requirement had to be finished before the transfer point, and there is no
#: staged-split rule - so treating it as a historical shortfall would be wrong.
#: This is a case-owner-confirmed Case A input only: it is neither a general scope
#: rule nor school policy, and a different transfer term would decide it afresh.
_CASE_OWNER_CONFIRMED_CROSSING: tuple[tuple[str, str, str], ...] = (
    ("table:2!row:11", "PUB178", "2025-1~2028-2"),
)

#: Everything decided ``future`` for Case A, decided ranges first.
_CONFIRMED_FUTURE_ALL: tuple[tuple[str, str, str], ...] = (
    *_CONFIRMED_FUTURE,
    *_CASE_OWNER_CONFIRMED_CROSSING,
)

#: Ranges that lie **entirely at or before** ``as_of_term``: the historical
#: window that precedes the transfer point. Deciding these ``historical`` is a
#: pure scope statement - it does **not** say the requirement is met, does not
#: recognize any completed course, and supplies no course id. Matching therefore
#: still decides satisfaction on its own evidence, exactly as before.
_CONFIRMED_HISTORICAL: tuple[tuple[str, str, str], ...] = (
    ("table:2!row:8", "MAR116", "2025-1~2025-2"),
    ("table:2!row:9", "PSY199", "2025-1~2025-2"),
    ("table:2!row:10", "PUB1991", "2025-1~2025-2"),
)

#: The decisions as plain data, so they can be reviewed without reading code.
#: ``historical`` decisions come first, then ``future`` ones; every entry is bound
#: to its own requirement ``source_record``.
CONFIRMED_SCOPE_DECISIONS: tuple[dict, ...] = tuple(
    [
        {
            "target_version_id": CASE_TARGET_VERSION_ID,
            "target_source_record": source_record,
            "target_course_id": course_id,
            "decision": "historical",
            "evidence": DECISION_EVIDENCE,
            "recommended_term_text": term,
        }
        for source_record, course_id, term in _CONFIRMED_HISTORICAL
    ]
    + [
        {
            "target_version_id": CASE_TARGET_VERSION_ID,
            "target_source_record": source_record,
            "target_course_id": course_id,
            "decision": "future",
            "evidence": DECISION_EVIDENCE,
            "recommended_term_text": term,
        }
        for source_record, course_id, term in _CONFIRMED_FUTURE_ALL
    ]
)

#: The ``(target_source_record, decision, evidence)`` identity of every approved
#: decision. ``evidence`` is part of the identity on purpose: an artifact may not
#: keep an approved entry but swap in a different provenance reference.
CONFIRMED_SCOPE_DECISION_KEYS: frozenset[tuple[str, str, str]] = frozenset(
    (record["target_source_record"], record["decision"], record["evidence"])
    for record in CONFIRMED_SCOPE_DECISIONS
)

#: The four ``future``-only decisions that were shipped before the historical
#: ruling was added. A private case artifact built at that revision carries exactly
#: these; an artifact rebuilt after the ruling carries ``CONFIRMED_SCOPE_DECISION_KEYS``.
LEGACY_SCOPE_DECISION_KEYS: frozenset[tuple[str, str, str]] = frozenset(
    (source_record, "future", DECISION_EVIDENCE)
    for source_record, _course_id, _term in _CONFIRMED_FUTURE_ALL
)

#: Accepted decision sets during the rollout of the historical ruling. ⛔ Neither
#: set may be *extended* or re-evidenced by an artifact: a decision that is not one
#: of the approved entries is still rejected, so this is a compatibility window,
#: not a relaxation of "only approved decisions".
SUPPORTED_SCOPE_DECISION_KEYS: tuple[frozenset[tuple[str, str, str]], ...] = (
    CONFIRMED_SCOPE_DECISION_KEYS,
    LEGACY_SCOPE_DECISION_KEYS,
)


def decision_keys(
    decisions: object,
) -> frozenset[tuple[str, str, str]] | None:
    """Return the approved-identity set of ``decisions``, or ``None`` if malformed."""

    if not isinstance(decisions, (tuple, list)):
        return None
    keys: list[tuple[str, str, str]] = []
    for decision in decisions:
        source_record = getattr(decision, "target_source_record", None)
        value = getattr(decision, "decision", None)
        evidence = getattr(decision, "evidence", None)
        if not isinstance(source_record, str) or not isinstance(value, str):
            return None
        if not isinstance(evidence, str):
            return None
        keys.append((source_record, value, evidence))
    return frozenset(keys)


def is_supported_scope_decision_set(decisions: object) -> bool:
    """Whether this decision set is one of the approved Case A decision sets."""

    keys = decision_keys(decisions)
    return keys is not None and keys in SUPPORTED_SCOPE_DECISION_KEYS


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
