"""Internal Curriculum validation errors with no student data in messages."""

__all__ = ["CurriculumNormalizationError"]


class CurriculumNormalizationError(ValueError):
    """A supplied Curriculum input cannot be normalized or projected safely."""
