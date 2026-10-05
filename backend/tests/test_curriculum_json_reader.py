"""Bounded JSON imports must not read an entire oversized private input."""

import io

import pytest

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.json_reader import load_json_input, resolve_local_input


def test_oversized_input_is_read_only_up_to_the_limit_plus_one(monkeypatch, tmp_path):
    from app.curriculum import json_reader

    requested = []

    class Stream(io.BytesIO):
        def read(self, size=-1):
            requested.append(size)
            return super().read(size)

    monkeypatch.setattr(json_reader, "MAX_JSON_BYTES", 16)
    monkeypatch.setattr("pathlib.Path.open", lambda *args, **kwargs: Stream(b" " * 10000))
    with pytest.raises(CurriculumNormalizationError, match="file size limit"):
        load_json_input(tmp_path / "DEMO-PRIVATE-PATH.json")
    assert requested == [17]


@pytest.mark.parametrize("body", [b'{"x": NaN}', b'{"x": Infinity}', b'\xff', b'{bad'])
def test_invalid_json_does_not_expose_values_or_paths(tmp_path, body):
    path = tmp_path / "DEMO-PRIVATE-PATH.json"
    path.write_bytes(body)
    with pytest.raises(CurriculumNormalizationError) as error:
        load_json_input(path)
    assert str(error.value) == "case: invalid or unreadable JSON"


def test_deep_duplicate_field_is_rejected_instead_of_overriding_pass_fact(tmp_path):
    path = tmp_path / "DEMO-PRIVATE-PATH.json"
    path.write_text('{"records":[{"passed":false,"passed":true}]}')
    with pytest.raises(CurriculumNormalizationError, match="invalid or unreadable JSON"):
        load_json_input(path)


def test_local_references_are_resolved_relative_to_the_case_directory(tmp_path):
    assert resolve_local_input("subdir/document.docx", directory=tmp_path, label="docx") == (
        tmp_path / "subdir/document.docx"
    ).resolve()


@pytest.mark.parametrize("value", [None, "", "https://example.com/private.docx", "bad\x00path"])
def test_remote_or_invalid_local_references_have_redacted_errors(tmp_path, value):
    with pytest.raises(CurriculumNormalizationError) as error:
        resolve_local_input(value, directory=tmp_path, label="docx")
    assert "example.com" not in str(error.value) and "path" not in str(error.value)
