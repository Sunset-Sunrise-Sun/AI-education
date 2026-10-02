"""Bounded local JSON reads with redacted diagnostics and unique fields."""

from __future__ import annotations

import json
from pathlib import Path

from app.curriculum.errors import CurriculumNormalizationError

MAX_JSON_BYTES = 8 * 1024 * 1024


def load_json_input(path: str | Path, *, label: str = "case") -> object:
    if not isinstance(path, (str, Path)):
        raise CurriculumNormalizationError(f"{label}: invalid input path")

    def invalid_constant(value: str):
        raise ValueError("non-finite JSON number")

    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise CurriculumNormalizationError(f"{label}: file size limit exceeded")
        return json.loads(raw.decode("utf-8"), parse_constant=invalid_constant,
                          object_pairs_hook=unique_fields)
    except CurriculumNormalizationError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise CurriculumNormalizationError(f"{label}: invalid or unreadable JSON") from None


def resolve_local_input(value: object, *, directory: Path, label: str) -> Path:
    """Resolve an explicitly named local input; never fetch remote documents."""
    if not isinstance(value, str) or not value.strip() or "://" in value:
        raise CurriculumNormalizationError(f"{label}: expected a local file reference")
    try:
        path = Path(value)
        return (path if path.is_absolute() else directory / path).resolve()
    except (OSError, ValueError, RuntimeError):
        raise CurriculumNormalizationError(f"{label}: invalid local file reference") from None
