"""Internal Curriculum validation errors with no student data in messages."""

__all__ = ["CurriculumNormalizationError"]


class CurriculumNormalizationError(ValueError):
    """A supplied completed-course record cannot be normalized safely."""
