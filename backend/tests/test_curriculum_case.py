"""Local structured cases and artificial Demo data only."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.curriculum.case import (
    DEMO_CASE_PATH,
    CurriculumCaseProvider,
    demo_output,
    load_curriculum_case,
    load_demo_case,
    normalize_curriculum_case,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.integration.orchestrator import PlanningOrchestrator
from app.integration.ports import CurriculumProvider
from app.models.contracts import PlanResult, Preference


def _input():
    return json.loads(DEMO_CASE_PATH.read_text(encoding="utf-8"))


def test_demo_calculates_four_statuses_without_per_course_decisions() -> None:
    payload = _input()
    assert not payload.get("recognitions") and not payload.get("missing_requirements")
    result = demo_output()
    assert result["data_source"] == "mock"
    assert [t["status"] for t in result["makeup_tasks"]] == [
        "satisfied", "required", "possibly_equivalent", "manual_confirmation", "manual_confirmation",
    ]
    assert all("mock://" in t["source_evidence"] for t in result["makeup_tasks"])
    schema = json.loads((DEMO_CASE_PATH.parents[2] / "schemas/makeup_task.schema.json").read_text())
    for task in result["makeup_tasks"]:
        Draft202012Validator(schema).validate(task)
        assert "priority" not in task and "rules" not in task


def test_saved_demo_output_matches_the_runtime_result() -> None:
    expected = json.loads((DEMO_CASE_PATH.parent / "makeup_tasks.json").read_text())
    assert demo_output()["makeup_tasks"] == expected


def test_saved_elective_demo_computes_only_the_confirmed_remaining_selection() -> None:
    provider = CurriculumCaseProvider(load_curriculum_case(DEMO_CASE_PATH.parent / "elective_case.json"))
    expected = json.loads((DEMO_CASE_PATH.parent / "elective_makeup_tasks.json").read_text())
    tasks = provider.get_makeup_tasks()
    assert [task.model_dump(mode="json") for task in tasks] == expected
    assert [task.course_id for task in tasks] == ["DEMO101", "DEMO-E1", "DEMO-E2"]
    assert [task.status.value for task in tasks] == ["satisfied", "satisfied", "required"]
    assert provider.get_curriculum_diff().group_gaps[0].remaining_credit == 2
    assert provider.get_academic_analysis().priority_order == ("DEMO-E2",)


def test_real_case_cannot_reuse_mock_elective_selection_evidence() -> None:
    payload = json.loads((DEMO_CASE_PATH.parent / "elective_case.json").read_text())

    def replace_mock(value):
        if isinstance(value, str):
            return value.replace("mock://", "confirmed-local://")
        if isinstance(value, list):
            return [replace_mock(item) for item in value]
        if isinstance(value, dict):
            return {key: replace_mock(item) for key, item in value.items()}
        return value

    payload = replace_mock(payload)
    payload["data_source"] = "real"
    payload["elective_selections"][0]["evidence"] = "mock://DEMO-PRIVATE-SELECTION"
    with pytest.raises(CurriculumNormalizationError) as error:
        normalize_curriculum_case(payload)
    assert "Mock" in str(error.value) and "DEMO-PRIVATE" not in str(error.value)


def test_demo_recalculates_modified_artificial_input_instead_of_replaying_output(tmp_path, monkeypatch) -> None:
    payload = _input()
    payload["new"]["course_records"][0]["credit"] = 4
    path = tmp_path / "mock-case.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr("app.curriculum.case.DEMO_CASE_PATH", path)
    assert demo_output()["makeup_tasks"][0]["status"] == "manual_confirmation"


def test_provider_is_callable_and_isolates_context_and_results() -> None:
    payload = _input()
    provider = CurriculumCaseProvider(normalize_curriculum_case(payload))
    assert isinstance(provider, CurriculumProvider)
    assert list(inspect.signature(provider.get_makeup_tasks).parameters) == []
    payload["new"]["course_records"].clear()
    first = provider.get_makeup_tasks()
    first[0].course_name = "DEMO-CALLER-MUTATION"
    first[1].prerequisites.clear()
    second = provider.get_makeup_tasks()
    assert len(second) == 5 and second[0].course_name != "DEMO-CALLER-MUTATION"
    assert second[1].prerequisites == ["DEMO101"]
    assert provider.get_academic_analysis().priority_order is None


def test_integration_consumes_computed_curriculum_tasks_without_internal_models() -> None:
    provider = CurriculumCaseProvider(load_demo_case())
    observed = []
    result = PlanResult(status="partially_feasible", selected_classes=[], changes=[], risks=[], unresolved=[])

    class DataSpy:
        def get_course_offerings(self, semester):
            observed.append(semester)
            return []

    class PlannerSpy:
        def plan(self, *, makeup_tasks, offerings, current_schedule, preference):
            observed.append([task.status.value for task in makeup_tasks])
            return result

    orchestrator = PlanningOrchestrator(provider, DataSpy(), PlannerSpy())
    assert orchestrator.build_plan(semester="DEMO-TERM", current_schedule=[], preference=Preference()) is result
    assert observed[0] == "DEMO-TERM" and observed[1][:3] == ["satisfied", "required", "possibly_equivalent"]


@pytest.mark.parametrize("location", ["case", "curriculum", "completed", "rules", "record"])
def test_extra_fields_do_not_leak_or_enter_case(location: str) -> None:
    payload = _input()
    target = {
        "case": payload, "curriculum": payload["new"], "completed": payload["completed"],
        "rules": payload["rules"], "record": payload["completed"]["records"][0],
    }[location]
    target["DEMO-PRIVATE-UNKNOWN-FIELD"] = "DEMO-PRIVATE-VALUE"
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        normalize_curriculum_case(payload)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


@pytest.mark.parametrize("body", ["{DEMO-PRIVATE-TEXT", '{"value": NaN}', '{"value": Infinity}'])
def test_invalid_case_file_has_fixed_errors_and_no_fallback(tmp_path: Path, body: str) -> None:
    path = tmp_path / "DEMO-PRIVATE-PATH.json"
    path.write_text(body)
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_case(path)
    assert str(excinfo.value) == "case: invalid or unreadable JSON"
    assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_unreadable_file_does_not_echo_path_or_return_demo(tmp_path: Path) -> None:
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_case(tmp_path / "DEMO-PRIVATE-MISSING.json")
    assert "DEMO-PRIVATE" not in str(excinfo.value)


@pytest.mark.parametrize("source", [None, True, "DEMO-PRIVATE-SOURCE", {}])
def test_data_source_must_be_explicit(source: object) -> None:
    payload = _input()
    payload["data_source"] = source
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        normalize_curriculum_case(payload)
    assert str(excinfo.value) == "data_source: expected mock or real"


def test_no_rules_does_not_silently_adopt_demo_rules() -> None:
    payload = _input()
    del payload["rules"]
    tasks = CurriculumCaseProvider(normalize_curriculum_case(payload)).get_makeup_tasks()
    assert tasks[0].status.value == "manual_confirmation"
    assert tasks[1].status.value == "manual_confirmation"


def test_scope_and_priority_policy_are_bound_to_the_case() -> None:
    payload = _input()
    payload["rules"]["completed_source_id"] = "DEMO-OTHER-SOURCE"
    with pytest.raises(CurriculumNormalizationError):
        normalize_curriculum_case(payload)
    payload = _input()
    payload["priority_policy"] = {"target_version_id": "DEMO-OTHER-VERSION", "evidence": "mock://policy"}
    with pytest.raises(CurriculumNormalizationError):
        normalize_curriculum_case(payload)


def test_demo_refuses_real_classification_before_export(monkeypatch) -> None:
    payload = _input()
    payload["data_source"] = "real"
    payload["old"]["source_id"] = "DEMO-REAL-OLD-SOURCE"
    payload["new"]["source_id"] = "DEMO-REAL-NEW-SOURCE"
    payload["completed"]["source_id"] = "DEMO-REAL-COMPLETED-SOURCE"
    payload["rules"]["completed_source_id"] = "DEMO-REAL-COMPLETED-SOURCE"
    payload["rules"]["evidence"] = "DEMO-REAL-RULE-EVIDENCE"
    payload["old"]["completeness_evidence"] = "DEMO-REAL-OLD-COMPLETENESS"
    payload["new"]["completeness_evidence"] = "DEMO-REAL-NEW-COMPLETENESS"
    payload["completed"]["completeness_evidence"] = "DEMO-REAL-COMPLETED-COMPLETENESS"
    for row in payload["completed"]["records"]:
        row["id_match_source"] = "DEMO-REAL-ID-EVIDENCE"
    case = normalize_curriculum_case(payload)
    monkeypatch.setattr("app.curriculum.case.load_curriculum_case", lambda path: case)
    with pytest.raises(CurriculumNormalizationError, match="Mock"):
        demo_output()


def test_known_mock_sources_cannot_be_reclassified_as_real() -> None:
    payload = _input()
    payload["data_source"] = "real"
    with pytest.raises(CurriculumNormalizationError, match="Mock"):
        normalize_curriculum_case(payload)


@pytest.mark.parametrize("field", ["old_completeness", "new_completeness", "completed_completeness", "id_match_source"])
def test_real_classification_rejects_remaining_mock_identity_or_completeness(field) -> None:
    payload = _input()
    payload["data_source"] = "real"
    for version in (payload["old"], payload["new"]):
        version["source_id"] = "DEMO-REAL-SOURCE"
        version["completeness_evidence"] = "DEMO-REAL-COMPLETE"
    payload["completed"]["source_id"] = "DEMO-REAL-COMPLETED"
    payload["completed"]["completeness_evidence"] = "DEMO-REAL-COMPLETE"
    payload["rules"]["completed_source_id"] = "DEMO-REAL-COMPLETED"
    payload["rules"]["evidence"] = "DEMO-REAL-RULE"
    for row in payload["completed"]["records"]:
        row["id_match_source"] = "DEMO-REAL-ID-EVIDENCE"
    target = {
        "old_completeness": (payload["old"], "completeness_evidence"),
        "new_completeness": (payload["new"], "completeness_evidence"),
        "completed_completeness": (payload["completed"], "completeness_evidence"),
        "id_match_source": (payload["completed"]["records"][0], "id_match_source"),
    }[field]
    target[0][target[1]] = "说明: MoCk://DEMO-PRIVATE-EVIDENCE"
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        normalize_curriculum_case(payload)
    assert "DEMO-PRIVATE" not in str(excinfo.value)


@pytest.mark.parametrize("field", ["passed", "rules", "data_source"])
def test_duplicate_json_fields_cannot_override_source_or_pass_facts(tmp_path, field) -> None:
    payload = _input()
    if field == "passed":
        body = json.dumps(payload).replace('"passed": true', '"passed": false, "passed": true', 1)
    else:
        pairs = list(payload.items()) + [(field, payload[field])]
        body = "{" + ",".join(json.dumps(key) + ":" + json.dumps(value) for key, value in pairs) + "}"
    path = tmp_path / "DEMO-PRIVATE-DUPLICATE.json"
    path.write_text(body)
    with pytest.raises(CurriculumNormalizationError) as excinfo:
        load_curriculum_case(path)
    assert str(excinfo.value) == "case: invalid or unreadable JSON"
    assert "DEMO-PRIVATE" not in str(excinfo.value)


def test_explicit_decisions_and_priority_policy_round_trip() -> None:
    payload = _input()
    payload["recognitions"] = [{
        "target_version_id": "mock-new", "target_course_id": "DEMO404",
        "completed_source_id": "mock://curriculum-demo/completed", "completed_source_record": "row:3",
        "recognized_credit": 3, "evidence": "mock://explicit-credit-conversion",
    }]
    payload["priority_policy"] = {"target_version_id": "mock-new", "evidence": "mock://priority", "deadline_first": True}
    provider = CurriculumCaseProvider(normalize_curriculum_case(payload))
    assert provider.get_makeup_tasks()[3].status.value == "satisfied"
    assert provider.get_academic_analysis().priority_order is None  # Unknown prerequisite facts remain unknown.


def test_case_with_unrepresentable_group_gap_fails_without_a_fake_task() -> None:
    payload = _input()
    payload["new"]["group_records"] = [{
        "group_id": "DEMO-GROUP", "name": "DEMO Pool", "minimum_credit": 9, "source_record": "group:1",
    }]
    payload["new"]["course_records"][0]["group_id"] = "DEMO-GROUP"
    provider = CurriculumCaseProvider(normalize_curriculum_case(payload))
    with pytest.raises(CurriculumNormalizationError, match="group"):
        provider.get_makeup_tasks()
