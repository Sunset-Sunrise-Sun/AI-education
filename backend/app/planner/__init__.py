"""Planner 内部算法；不定义公共 Schema，也尚未实现 PlannerProvider。"""

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
