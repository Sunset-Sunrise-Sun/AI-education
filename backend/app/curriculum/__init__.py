"""Internal Curriculum facts; no public Schema or school recognition rules."""

from app.curriculum.completed_courses import (
    CompletedCourse,
    CourseIdStatus,
    normalize_completed_courses,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedElectiveSelection,
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CurriculumDiff,
    CurriculumResultProvider,
    MatchingRules,
    build_curriculum_diff,
    project_courses,
    project_makeup_tasks,
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
    "build_curriculum_diff",
    "project_courses",
    "project_makeup_tasks",
    "MatchingRules",
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
]
