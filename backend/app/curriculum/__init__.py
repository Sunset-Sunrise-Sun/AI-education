"""Internal Curriculum facts; no public Schema or school recognition rules."""

from app.curriculum.completed_courses import (
    CompletedCourse,
    CourseIdStatus,
    normalize_completed_courses,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.matching import (
    ConfirmedMissingRequirement,
    ConfirmedRecognition,
    CurriculumDiff,
    CurriculumResultProvider,
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
    "ConfirmedRecognition",
    "CurriculumDiff",
    "CurriculumResultProvider",
    "build_curriculum_diff",
    "project_courses",
    "project_makeup_tasks",
]
