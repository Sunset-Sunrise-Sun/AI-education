"""Internal Curriculum facts; no public Schema or school recognition rules."""

from app.curriculum.completed_courses import (
    CompletedCourse,
    CourseIdStatus,
    normalize_completed_courses,
)
from app.curriculum.errors import CurriculumNormalizationError

__all__ = [
    "CompletedCourse",
    "CourseIdStatus",
    "CurriculumNormalizationError",
    "normalize_completed_courses",
]
