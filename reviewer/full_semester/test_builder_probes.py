"""Run against Builder c01b7c9 archive; these reproduce hazards, not acceptance passes.

PYTHONPATH=/tmp/ai-education-builder-review/backend <venv>/bin/python -m pytest this_file
No production files are patched. All fixture input is generated in tmp_path.
"""
import importlib.util
import json
from pathlib import Path

import pytest

import app.course_data.full_semester_acceptance as target


@pytest.fixture
def fixtures():
    root = Path(target.__file__).parents[2]
    spec = importlib.util.spec_from_file_location(
        "builder_synthetic_fixtures", root / "tests/test_course_data_full_semester_acceptance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shard_labels_are_not_bound_to_actual_capture_scope(tmp_path, fixtures):
    paths = fixtures._write_shards(tmp_path)
    east, south = fixtures.SHARD_IDS[:2]
    # Swap the exact original campus files without modifying any bytes or rows.
    paths[east], paths[south] = paths[south], paths[east]
    acceptance = target.accept_full_semester_capture_set(
        expected_semester=fixtures.SEMESTER, baseline_before=5, baseline_after=5,
        shard_artifacts=fixtures._artifacts(paths))
    assert acceptance.merged_offering_count == 5
    assert acceptance.shards[0].shard_id == east
    assert south.upper() in acceptance.merged.offerings[0].course_id


def test_digest_and_parsed_rows_can_describe_different_bytes(tmp_path, fixtures, monkeypatch):
    paths = fixtures._write_shards(tmp_path)
    east_path = paths[fixtures.SHARD_IDS[0]]
    original_loader = target.load_capture_bundle

    def swap_during_parse(path):
        path = Path(path)
        if path != east_path:
            return original_loader(path)
        original = path.read_bytes()
        alternate = json.loads(original)
        alternate["pages"][0]["response"]["data"]["rows"][0]["courseName"] = "synthetic altered content"
        try:
            path.write_text(json.dumps(alternate), encoding="utf-8")
            return original_loader(path)
        finally:
            path.write_bytes(original)

    first = target.accept_full_semester_capture_set(
        expected_semester=fixtures.SEMESTER, baseline_before=5, baseline_after=5,
        shard_artifacts=fixtures._artifacts(paths))
    monkeypatch.setattr(target, "load_capture_bundle", swap_during_parse)
    second = target.accept_full_semester_capture_set(
        expected_semester=fixtures.SEMESTER, baseline_before=5, baseline_after=5,
        shard_artifacts=fixtures._artifacts(paths))
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.merged.offerings[0].course_name != second.merged.offerings[0].course_name
