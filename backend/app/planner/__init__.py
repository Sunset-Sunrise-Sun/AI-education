"""Planner 内部算法及受限 Provider；不定义或修改公共 Schema。"""

from app.planner.provider import RestrictedPlannerProvider

from app.planner.conflicts import (
    ConflictState,
    check_conflict,
    check_schedule_conflict,
)

from app.planner.section_repair import (
    AlternativeSearchResult,
    CandidateAssessment,
    RepairOutcome,
    SearchOutcome,
    SectionRepairResult,
    find_alternative_sections,
    repair_target_section,
)

__all__ = [
    "RestrictedPlannerProvider",
    "AlternativeSearchResult",
    "CandidateAssessment",
    "ConflictState",
    "RepairOutcome",
    "SearchOutcome",
    "SectionRepairResult",
    "check_conflict",
    "check_schedule_conflict",
    "find_alternative_sections",
    "repair_target_section",
]
