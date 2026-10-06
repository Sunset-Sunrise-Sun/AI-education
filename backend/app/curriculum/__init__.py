"""Internal Curriculum facts; no public Schema or school recognition rules."""

from app.curriculum.completed_courses import (
    CompletedCourse,
    CourseIdStatus,
    normalize_completed_courses,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedElectiveSelection,
    ConfirmedGroupScopeDecision,
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CurriculumDiff,
    CurriculumResultProvider,
    MakeupScope,
    MatchingRules,
    build_curriculum_diff,
    project_courses,
    project_makeup_tasks,
)
from app.curriculum.terms import (
    SCOPE_FUTURE,
    SCOPE_HISTORICAL,
    SCOPE_UNRESOLVED,
    AcademicTerm,
    ConfirmedScopeDecision,
    ScopeDecision,
    classify_term,
    parse_academic_term,
    scope_decisions,
)
from app.curriculum.requirements import (
    CurriculumCourse,
    CurriculumGroup,
    CurriculumVersion,
    RequirementKind,
    normalize_curriculum_version,
)
from app.curriculum.academic import (
    AcademicAnalysis,
    AcademicIssue,
    PriorityPolicy,
    analyze_academic_path,
)
from app.curriculum.case import (
    CurriculumCase,
    CurriculumCaseProvider,
    load_curriculum_case,
    normalize_curriculum_case,
)
from app.curriculum.docx_reader import (
    DocxCourseRow,
    DocxImportIssue,
    DocxImportResult,
    load_curriculum_docx,
)
from app.curriculum.pdf_reader import (
    TranscriptParse,
    TranscriptRecord,
    load_completed_courses_pdf,
    parse_transcript_pdf,
    parse_transcript_pdf_bytes,
)

__all__ = [
    "CompletedCourse",
    "CourseIdStatus",
    "CurriculumNormalizationError",
    "normalize_completed_courses",
    "CurriculumCourse",
    "CurriculumGroup",
    "CurriculumVersion",
    "RequirementKind",
    "normalize_curriculum_version",
    "ConfirmedMissingRequirement",
    "ConfirmedElectiveSelection",
    "ConfirmedRecognition",
    "CurriculumDiff",
    "CurriculumResultProvider",
    "MakeupScope",
    "ConfirmedGroupScopeDecision",
    "build_curriculum_diff",
    "project_courses",
    "project_makeup_tasks",
    "MatchingRules",
    "SCOPE_FUTURE",
    "SCOPE_HISTORICAL",
    "SCOPE_UNRESOLVED",
    "AcademicTerm",
    "ConfirmedScopeDecision",
    "ScopeDecision",
    "classify_term",
    "parse_academic_term",
    "scope_decisions",
    "AcademicAnalysis",
    "AcademicIssue",
    "PriorityPolicy",
    "analyze_academic_path",
    "CurriculumCase",
    "CurriculumCaseProvider",
    "load_curriculum_case",
    "normalize_curriculum_case",
    "DocxCourseRow",
    "DocxImportIssue",
    "DocxImportResult",
    "load_curriculum_docx",
    "TranscriptParse",
    "TranscriptRecord",
    "load_completed_courses_pdf",
    "parse_transcript_pdf",
    "parse_transcript_pdf_bytes",
]
