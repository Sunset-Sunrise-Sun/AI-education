"""Case A production runtime factory tests (synthetic, zero-network).

Covers the Gate C replacement of PR #39's single-bundle wiring:

```text
APP_REAL_CASE_A_ENABLED / APP_CASE_A_CURRICULUM_CASE_PATH
APP_COURSE_DATA_SQLITE_PATH / APP_COURSE_DATA_SEMESTER / APP_COURSE_DATA_ACCEPTANCE_SHA256
        → StoreBackedCourseDataProvider（full_semester acceptance 绑定）
        → PlanningOrchestrator 或 None（⇒ API 503）
```
"""

from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app.api.mock import MOCK_DATA_SOURCE_HEADER, MOCK_DATA_SOURCE_VALUE
from fastapi.testclient import TestClient
from app.course_data import (
    SCOPE_KIND_CAMPUS,
    SCOPE_KIND_FULL_SEMESTER,
    CourseDataAcceptanceError,
    CourseDataStoreError,
    ShardArtifact,
    SnapshotScope,
    StoreBackedCourseDataProvider,
    accept_full_semester_capture_set,
    build_capture_inventory,
    campus_source_label,
    capture_inventory_bytes,
    collect_captured_pages_snapshot,
    import_offering_snapshot,
    load_capture_bundle_bytes,
    load_capture_inventory,
)
from app.curriculum import CurriculumCaseProvider
from app.curriculum.case_a_decisions import (
    AS_OF_TERM,
    CASE_TARGET_VERSION_ID,
    CONFIRMED_SCOPE_DECISIONS,
)
from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.case import normalize_curriculum_case
from app.integration import PlanningOrchestrator
from app.main import app
from app.models.contracts import PlanResult, Preference
from app.planner import RestrictedPlannerProvider
from app.services import planning_runtime
from app.services.planning_runtime import (
    PlanningRuntimeInspection,
    build_planning_runtime,
    get_planning_orchestrator,
)

SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
VALID_SCHEDULE = "1-8周/星期五/第5-6节/REDACTED/示例环节,"
PLAN_PATH = "/api/v1/plan"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

SHARD_IDS = (
    "east-campus",
    "south-campus",
    "shenzhen-campus",
    "zhuhai-campus",
    "north-campus",
)

SHARD_NUMBERS = {
    "east-campus": "5063559",
    "south-campus": "5062201",
    "shenzhen-campus": "333291143",
    "zhuhai-campus": "5062203",
    "north-campus": "5062202",
}


# --------------------------------------------------------------------------- #
# synthetic inputs
# --------------------------------------------------------------------------- #


def _row(course_number: str, class_number: str) -> dict[str, object]:
    return {
        "courseNum": course_number,
        "courseName": "示例课程",
        "classNumber": class_number,
        "yearTerm": SEMESTER,
        "score": "3",
        "limitNumber": 90,
        "selectedNumber": 75,
        "teachingTimePlaceStr": VALID_SCHEDULE,
    }


def _write_bundle(directory: Path, shard_id: str) -> Path:
    path = directory / f"{shard_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(
            {
                "format": "sysu-opening-courses-capture-v1",
                "semester": SEMESTER,
                "first_page_no": 1,
                "page_size": 200,
                "pages": [
                    {
                        "page_no": 1,
                        "response": {
                            "code": 200,
                            "data": {
                                "total": 1,
                                "rows": [
                                    _row(
                                        f"SYN-{shard_id.upper()}",
                                        f"{shard_id}-000",
                                    )
                                ],
                            },
                        },
                    }
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return path


def _full_semester_store(tmp_path: Path) -> tuple[Path, object]:
    """造一份 synthetic full-semester acceptance 并导入 SQLite。

    ⚠️ 正式 acceptance 需要**已批准 inventory** + **campus acceptance 记录**
    （Forward Red-Team BLOCK B2），因此这里先把五个 shard 以 campus scope 入库。
    """

    captures = tmp_path / "captures"
    paths = {shard_id: _write_bundle(captures, shard_id) for shard_id in SHARD_IDS}

    digests = {
        shard_id: hashlib.sha256(path.read_bytes()).hexdigest()
        for shard_id, path in paths.items()
    }
    inventory = build_capture_inventory(SEMESTER, digests)
    inventory_path = tmp_path / "capture-inventory.json"
    inventory_path.write_bytes(capture_inventory_bytes(inventory))

    campus_store = tmp_path / "campus-acceptances.sqlite3"
    for shard_id, path in paths.items():
        number = SHARD_NUMBERS[shard_id]
        snapshot = collect_captured_pages_snapshot(
            load_capture_bundle_bytes(path.read_bytes()),
            source=campus_source_label(SEMESTER, number),
        )
        import_offering_snapshot(
            campus_store,
            snapshot,
            artifact_sha256=digests[shard_id],
            scope=SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id=number),
        )

    acceptance = accept_full_semester_capture_set(
        expected_semester=SEMESTER,
        baseline_before=5,
        baseline_after=5,
        shard_artifacts=[
            ShardArtifact(shard_id=shard_id, bundle_path=paths[shard_id])
            for shard_id in SHARD_IDS
        ],
        inventory=load_capture_inventory(inventory_path),
        campus_store_path=campus_store,
    )

    sqlite_path = tmp_path / "course-data.sqlite3"
    import_offering_snapshot(
        sqlite_path,
        acceptance.merged,
        artifact_sha256=acceptance.manifest_sha256,
        scope=acceptance.scope,
    )
    return sqlite_path, acceptance


def _campus_only_store(tmp_path: Path) -> Path:
    sqlite_path = tmp_path / "campus-only.sqlite3"
    bundle_path = _write_bundle(tmp_path / "campus", "east-campus")
    snapshot = collect_captured_pages_snapshot(
        load_capture_bundle_bytes(bundle_path.read_bytes()),
        source="capture://sysu/2026-1/campus/5063559",
    )
    import_offering_snapshot(
        sqlite_path,
        snapshot,
        artifact_sha256="c" * 64,
        scope=SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id="5063559"),
    )
    return sqlite_path


def _case_payload(*, with_decisions: bool = True) -> dict[str, object]:
    """synthetic Case A case（data_source=real，⛔ 不含任何真实学校材料）。"""

    new_courses: list[dict[str, object]] = [
        {
            "course_id": "SYN116",
            "course_name": "示例历史欠修课",
            "credit": 3,
            "requirement": "required",
            "source_record": "table:2!row:8",
            "recommended_term_text": "2025-1",
            "prerequisites": [],
        }
    ]
    for record in CONFIRMED_SCOPE_DECISIONS:
        new_courses.append(
            {
                "course_id": record["target_course_id"],
                "course_name": f"示例课程{record['target_course_id']}",
                "credit": 3,
                "requirement": "required",
                "source_record": record["target_source_record"],
                "recommended_term_text": record["recommended_term_text"],
                "prerequisites": [],
            }
        )

    decisions = [
        {
            "target_version_id": CASE_TARGET_VERSION_ID,
            "target_source_record": record["target_source_record"],
            "target_course_id": record["target_course_id"],
            "decision": record["decision"],
            "evidence": record["evidence"],
        }
        for record in CONFIRMED_SCOPE_DECISIONS
    ]

    return {
        "data_source": "real",
        "old": {
            "version_id": "case-a-synthetic-old",
            "major": "示例专业",
            "cohort": "示例年级",
            "source_id": "case-owner-confirmed://synthetic/old",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://synthetic/old/complete",
            "course_records": [],
        },
        "new": {
            "version_id": CASE_TARGET_VERSION_ID,
            "major": "示例专业",
            "cohort": "示例年级",
            "source_id": "case-owner-confirmed://synthetic/new",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://synthetic/new/complete",
            "course_records": new_courses,
            "group_records": [],
        },
        "completed": {
            "source_id": "case-owner-confirmed://synthetic/completed",
            "complete": True,
            "completeness_evidence": "case-owner-confirmed://synthetic/completed/complete",
            "records": [],
        },
        "rules": {
            "target_version_id": CASE_TARGET_VERSION_ID,
            "completed_source_id": "case-owner-confirmed://synthetic/completed",
            "evidence": "case-owner-confirmed://synthetic/rules",
            "allow_exact_match": True,
            "allow_confirmed_absence": True,
        },
        "makeup_scope": {
            "target_version_id": CASE_TARGET_VERSION_ID,
            "as_of_term": AS_OF_TERM,
            "evidence": "case-owner-confirmed://synthetic/as-of",
        },
        "confirmed_scope_decisions": decisions if with_decisions else [],
    }


def _write_case(directory: Path, *, with_decisions: bool = True) -> Path:
    path = directory / "case-a.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_case_payload(with_decisions=with_decisions), ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _environment(
    tmp_path: Path,
    *,
    sqlite_path: Path | None = None,
    case_path: Path | None = None,
    semester: str = SEMESTER,
    digest: str | None = None,
    enabled: str | None = "1",
    with_decisions: bool = True,
) -> dict[str, str]:
    if sqlite_path is None:
        sqlite_path, acceptance = _full_semester_store(tmp_path / "store")
        digest = acceptance.manifest_sha256  # type: ignore[attr-defined]
    if case_path is None:
        case_path = _write_case(tmp_path / "case", with_decisions=with_decisions)
    if digest is None:
        digest = "a" * 64

    environment: dict[str, str] = {}
    if enabled is not None:
        environment["APP_REAL_CASE_A_ENABLED"] = enabled
    environment["APP_CASE_A_CURRICULUM_CASE_PATH"] = str(case_path)
    environment["APP_COURSE_DATA_SQLITE_PATH"] = str(sqlite_path)
    environment["APP_COURSE_DATA_SEMESTER"] = semester
    environment["APP_COURSE_DATA_ACCEPTANCE_SHA256"] = digest
    return environment


def _install_environment(
    monkeypatch: pytest.MonkeyPatch, environment: dict[str, str]
) -> None:
    for name in (
        "APP_REAL_CASE_A_ENABLED",
        "APP_CASE_A_CURRICULUM_CASE_PATH",
        "APP_COURSE_DATA_SQLITE_PATH",
        "APP_COURSE_DATA_SEMESTER",
        "APP_COURSE_DATA_ACCEPTANCE_SHA256",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)


def _request_payload(semester: str = SEMESTER) -> dict[str, object]:
    return {"semester": semester, "current_schedule": [], "preference": {}}


# --------------------------------------------------------------------------- #
# factory: disabled / invalid configuration
# --------------------------------------------------------------------------- #


def test_runtime_is_disabled_when_not_configured() -> None:
    inspection = build_planning_runtime({})

    assert isinstance(inspection, PlanningRuntimeInspection)
    assert inspection.orchestrator is None
    assert inspection.ready is False
    assert inspection.reason == "runtime_disabled"


@pytest.mark.parametrize("value", ["0", None])
def test_explicit_disable_values(value: str | None) -> None:
    environment = {} if value is None else {"APP_REAL_CASE_A_ENABLED": value}
    assert build_planning_runtime(environment).reason == "runtime_disabled"


@pytest.mark.parametrize("value", ["2", "true", "TRUE", "yes", "", " 1"])
def test_non_binary_switch_values_are_invalid(value: str) -> None:
    inspection = build_planning_runtime({"APP_REAL_CASE_A_ENABLED": value})

    assert inspection.orchestrator is None
    assert inspection.reason == "invalid_runtime_configuration"


def test_curriculum_path_is_required(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment.pop("APP_CASE_A_CURRICULUM_CASE_PATH")

    assert build_planning_runtime(environment).reason == "curriculum_not_ready"


@pytest.mark.parametrize(
    "missing",
    [
        "APP_COURSE_DATA_SQLITE_PATH",
        "APP_COURSE_DATA_SEMESTER",
        "APP_COURSE_DATA_ACCEPTANCE_SHA256",
    ],
)
def test_course_data_configuration_is_required(tmp_path: Path, missing: str) -> None:
    environment = _environment(tmp_path)
    environment.pop(missing)

    assert build_planning_runtime(environment).reason == "course_data_not_ready"


@pytest.mark.parametrize(
    "digest", ["not-a-digest", "a" * 63, "z" * 64, "a" * 65, "0x" + "a" * 62]
)
def test_malformed_acceptance_digest_is_invalid(tmp_path: Path, digest: str) -> None:
    environment = _environment(tmp_path)
    environment["APP_COURSE_DATA_ACCEPTANCE_SHA256"] = digest

    assert (
        build_planning_runtime(environment).reason == "invalid_runtime_configuration"
    )


@pytest.mark.parametrize("digest", ["", "   "])
def test_blank_acceptance_digest_counts_as_missing(
    tmp_path: Path, digest: str
) -> None:
    environment = _environment(tmp_path)
    environment["APP_COURSE_DATA_ACCEPTANCE_SHA256"] = digest

    assert build_planning_runtime(environment).reason == "course_data_not_ready"


@pytest.mark.parametrize("semester", ["", "   "])
def test_blank_semester_is_course_data_not_ready(
    tmp_path: Path, semester: str
) -> None:
    environment = _environment(tmp_path, semester=semester)

    assert build_planning_runtime(environment).reason == "course_data_not_ready"


# --------------------------------------------------------------------------- #
# factory: curriculum gate
# --------------------------------------------------------------------------- #


def test_missing_or_mock_curriculum_case_is_not_ready(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["APP_CASE_A_CURRICULUM_CASE_PATH"] = str(tmp_path / "absent.json")
    assert build_planning_runtime(environment).reason == "curriculum_not_ready"

    mock_case = REPOSITORY_ROOT / "mock_data" / "curriculum_demo" / "scoped_case.json"
    environment["APP_CASE_A_CURRICULUM_CASE_PATH"] = str(mock_case)
    assert build_planning_runtime(environment).reason == "curriculum_not_ready"


def test_case_without_approved_scope_decisions_is_not_ready(tmp_path: Path) -> None:
    environment = _environment(tmp_path, with_decisions=False)

    assert build_planning_runtime(environment).reason == "curriculum_not_ready"


def test_case_for_another_target_version_is_not_ready(tmp_path: Path) -> None:
    payload = _case_payload()
    payload["new"]["version_id"] = "some-other-version"  # type: ignore[index]
    payload["rules"]["target_version_id"] = "some-other-version"  # type: ignore[index]
    payload["makeup_scope"]["target_version_id"] = "some-other-version"  # type: ignore[index]
    for decision in payload["confirmed_scope_decisions"]:  # type: ignore[union-attr]
        decision["target_version_id"] = "some-other-version"

    path = tmp_path / "case" / "other.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    environment = _environment(tmp_path, case_path=path)

    assert build_planning_runtime(environment).reason == "curriculum_not_ready"


# --------------------------------------------------------------------------- #
# factory: course data gate (no silent fallback)
# --------------------------------------------------------------------------- #


def test_missing_store_file_is_not_ready(tmp_path: Path) -> None:
    environment = _environment(tmp_path, sqlite_path=tmp_path / "absent.sqlite3")

    assert build_planning_runtime(environment).reason == "course_data_not_ready"


def test_campus_only_store_is_not_ready(tmp_path: Path) -> None:
    campus_store = _campus_only_store(tmp_path)
    environment = _environment(tmp_path, sqlite_path=campus_store, digest="c" * 64)

    inspection = build_planning_runtime(environment)

    assert inspection.orchestrator is None
    assert inspection.reason == "course_data_not_ready"


def test_wrong_acceptance_digest_is_not_ready(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["APP_COURSE_DATA_ACCEPTANCE_SHA256"] = "b" * 64

    assert build_planning_runtime(environment).reason == "course_data_not_ready"


def test_wrong_semester_is_not_ready(tmp_path: Path) -> None:
    environment = _environment(tmp_path, semester=OTHER_SEMESTER)

    assert build_planning_runtime(environment).reason == "course_data_not_ready"


def test_store_without_tables_is_not_ready(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.sqlite3"
    connection = sqlite3.connect(str(foreign))
    connection.execute("CREATE TABLE unrelated (id INTEGER)")
    connection.commit()
    connection.close()

    environment = _environment(tmp_path, sqlite_path=foreign)

    assert build_planning_runtime(environment).reason == "course_data_not_ready"


# --------------------------------------------------------------------------- #
# factory: ready
# --------------------------------------------------------------------------- #


def test_uppercase_acceptance_digest_is_accepted(tmp_path: Path) -> None:
    """负责人从别处复制 64 位 hex 时大小写都可能出现；digest 一律按小写规范化。"""

    store_root = tmp_path / "store"
    sqlite_path, acceptance = _full_semester_store(store_root)
    environment = _environment(
        tmp_path,
        sqlite_path=sqlite_path,
        digest=acceptance.manifest_sha256.upper(),  # type: ignore[attr-defined]
    )

    inspection = build_planning_runtime(environment)

    assert inspection.ready is True
    assert inspection.orchestrator is not None
    assert (
        inspection.orchestrator.course_data.acceptance_sha256
        == acceptance.manifest_sha256  # type: ignore[attr-defined]
    )


def _write_payload(directory: Path, name: str, payload: dict[str, object]) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_case_marked_mock_but_otherwise_valid_is_not_ready(tmp_path: Path) -> None:
    """唯一违规点 = `data_source != real`（其余全部合规）。"""

    payload = _case_payload()
    payload["data_source"] = "mock"
    case_path = _write_payload(tmp_path / "case", "mock-marked.json", payload)

    assert (
        build_planning_runtime(_environment(tmp_path, case_path=case_path)).reason
        == "curriculum_not_ready"
    )


def test_case_with_wrong_scope_cut_off_is_not_ready(tmp_path: Path) -> None:
    """唯一违规点 = `makeup_scope.as_of_term != AS_OF_TERM`。"""

    payload = _case_payload()
    payload["makeup_scope"]["as_of_term"] = "2026-1"  # type: ignore[index]
    case_path = _write_payload(tmp_path / "case", "wrong-cutoff.json", payload)

    assert (
        build_planning_runtime(_environment(tmp_path, case_path=case_path)).reason
        == "curriculum_not_ready"
    )


def test_case_with_unapproved_scope_decision_is_not_ready(tmp_path: Path) -> None:
    """唯一违规点 = 范围决策的 evidence 与已批准集合不同（决策本身仍是 `future`）。"""

    payload = _case_payload()
    payload["confirmed_scope_decisions"][0]["evidence"] = (  # type: ignore[index]
        "case-owner-confirmed://case-a/unapproved-variant"
    )
    case_path = _write_payload(tmp_path / "case", "unapproved.json", payload)

    # 该 case 自身合法（决策仍然成立、projection 仍可完成）。
    provider = CurriculumCaseProvider(
        normalize_curriculum_case(json.loads(case_path.read_text(encoding="utf-8")))
    )
    assert provider.get_makeup_tasks()

    assert (
        build_planning_runtime(_environment(tmp_path, case_path=case_path)).reason
        == "curriculum_not_ready"
    )


def test_case_version_gate_is_redundant_with_curriculum_validation(
    tmp_path: Path,
) -> None:
    """`new.version_id != CASE_TARGET_VERSION_ID` 时，case 自身就拒绝不一致组合。

    ⚠️ 这正是 runtime 里"版本必须等于 Case A 目标版本"那一句的**冗余性证据**：
    已批准的 scope 决策绑定在 `case-a-new` 上，版本被换掉后无论怎么摆都会在
    Curriculum 层被拒绝（因此那一句是纵深防御，不是唯一防线）。
    """

    mismatched_scope = _case_payload()
    mismatched_scope["new"]["version_id"] = "other-version"  # type: ignore[index]
    with pytest.raises(CurriculumNormalizationError):
        normalize_curriculum_case(mismatched_scope)

    foreign_decisions = _case_payload()
    foreign_decisions["new"]["version_id"] = "other-version"  # type: ignore[index]
    foreign_decisions["makeup_scope"]["target_version_id"] = "other-version"  # type: ignore[index]
    foreign_decisions["rules"]["target_version_id"] = "other-version"  # type: ignore[index]
    with pytest.raises(CurriculumNormalizationError):
        normalize_curriculum_case(foreign_decisions)


def test_ready_runtime_assembles_the_three_approved_providers(tmp_path: Path) -> None:
    inspection = build_planning_runtime(_environment(tmp_path))

    assert inspection.ready is True
    assert inspection.reason == "ready"

    orchestrator = inspection.orchestrator
    assert isinstance(orchestrator, PlanningOrchestrator)
    assert isinstance(orchestrator.curriculum, CurriculumCaseProvider)
    assert isinstance(orchestrator.course_data, StoreBackedCourseDataProvider)
    assert isinstance(orchestrator.planner, RestrictedPlannerProvider)

    # Provider 绑定到配置的学期，并且只返回被 acceptance 绑定的行。
    assert orchestrator.course_data.semester == SEMESTER
    offerings = orchestrator.course_data.get_course_offerings(SEMESTER)
    assert len(offerings) == 5
    assert {offering.semester for offering in offerings} == {SEMESTER}

    # Curriculum 侧真的投影出了 makeup task（Case A projection 在构造期已成功）。
    tasks = orchestrator.curriculum.get_makeup_tasks()
    assert [task.course_id for task in tasks] == ["SYN116"]


def test_ready_runtime_planner_receives_exactly_the_bound_offerings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class _RecordingPlanner(RestrictedPlannerProvider):
        def plan(self, *, makeup_tasks, offerings, current_schedule, preference):  # type: ignore[override]
            captured["offerings"] = list(offerings)
            captured["makeup_tasks"] = list(makeup_tasks)
            captured["current_schedule"] = list(current_schedule)
            captured["preference"] = preference
            return super().plan(
                makeup_tasks=makeup_tasks,
                offerings=offerings,
                current_schedule=current_schedule,
                preference=preference,
            )

    monkeypatch.setattr(
        planning_runtime, "build_planner_provider", lambda: _RecordingPlanner()
    )

    inspection = build_planning_runtime(_environment(tmp_path))
    assert inspection.orchestrator is not None

    preference = Preference(max_credit=18, notes="保留原始偏好")
    current = inspection.orchestrator.course_data.get_course_offerings(SEMESTER)[:1]
    result = inspection.orchestrator.build_plan(
        semester=SEMESTER, current_schedule=current, preference=preference
    )

    assert isinstance(result, PlanResult)
    offerings = captured["offerings"]
    assert isinstance(offerings, list) and len(offerings) == 5
    assert {offering.class_id for offering in offerings} == {
        f"{shard_id}-000" for shard_id in SHARD_IDS
    }
    assert captured["preference"] is preference
    assert [offering.class_id for offering in captured["current_schedule"]] == [  # type: ignore[union-attr]
        current[0].class_id
    ]
    assert captured["makeup_tasks"]  # type: ignore[truthy-bool]


def test_provider_failure_propagates_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _environment(tmp_path)
    inspection = build_planning_runtime(environment)
    assert inspection.orchestrator is not None

    # 启动之后库被改写：下一次请求必须 fail closed，⛔ 不回退到 Mock / 部分数据。
    sqlite_path = Path(environment["APP_COURSE_DATA_SQLITE_PATH"])
    connection = sqlite3.connect(str(sqlite_path))
    connection.execute(
        "UPDATE course_offering SET artifact_sha256 = ? WHERE class_id = ?",
        ("f" * 64, "east-campus-000"),
    )
    connection.commit()
    connection.close()

    with pytest.raises(CourseDataAcceptanceError):
        inspection.orchestrator.course_data.get_course_offerings(SEMESTER)

    # 重新装配也不会成功（每请求重新验证）。
    assert build_planning_runtime(environment).reason == "course_data_not_ready"


def test_requesting_another_semester_never_falls_back(tmp_path: Path) -> None:
    inspection = build_planning_runtime(_environment(tmp_path))
    assert inspection.orchestrator is not None

    with pytest.raises(CourseDataAcceptanceError):
        inspection.orchestrator.course_data.get_course_offerings(OTHER_SEMESTER)


# --------------------------------------------------------------------------- #
# process environment / FastAPI dependency
# --------------------------------------------------------------------------- #


def test_get_planning_orchestrator_reads_the_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_environment(monkeypatch, {})

    assert get_planning_orchestrator() is None

    _install_environment(monkeypatch, _environment(tmp_path))

    orchestrator = get_planning_orchestrator()
    assert isinstance(orchestrator, PlanningOrchestrator)


def test_request_time_readiness_failure_is_mapped_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """请求期间才发现的 acceptance 失效也必须映射成 503（⛔ 不是 500、⛔ 不是 Mock）。"""

    class _ExplodingCourseData:
        def get_course_offerings(self, semester: str) -> list[object]:
            raise CourseDataAcceptanceError("synthetic readiness failure")

    class _Curriculum:
        def get_makeup_tasks(self) -> list[object]:
            return []

    orchestrator = PlanningOrchestrator(
        curriculum=_Curriculum(),
        course_data=_ExplodingCourseData(),
        planner=RestrictedPlannerProvider(),
    )

    app.dependency_overrides[get_planning_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(PLAN_PATH, json=_request_payload())
    finally:
        app.dependency_overrides.pop(get_planning_orchestrator, None)

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
    assert MOCK_DATA_SOURCE_HEADER not in response.headers
    assert MOCK_DATA_SOURCE_VALUE not in response.text


def test_unexpected_store_failure_is_not_mapped_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ 其它未预期异常仍然保持 500：不把程序缺陷伪装成"未装配"。"""

    class _BrokenCourseData:
        def get_course_offerings(self, semester: str) -> list[object]:
            raise CourseDataStoreError("synthetic store corruption")

    class _Curriculum:
        def get_makeup_tasks(self) -> list[object]:
            return []

    orchestrator = PlanningOrchestrator(
        curriculum=_Curriculum(),
        course_data=_BrokenCourseData(),
        planner=RestrictedPlannerProvider(),
    )

    app.dependency_overrides[get_planning_orchestrator] = lambda: orchestrator
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(PLAN_PATH, json=_request_payload())
    finally:
        app.dependency_overrides.pop(get_planning_orchestrator, None)

    assert response.status_code == 500


def test_module_has_no_mock_or_single_bundle_fallback() -> None:
    module_path = (
        REPOSITORY_ROOT / "backend" / "app" / "services" / "planning_runtime.py"
    )
    source = module_path.read_text(encoding="utf-8")

    # 结构层：⛔ 不得 import Mock 回放通道，也不得 import 内存快照 Provider
    #（PR #39 的单 bundle 装载模型已被 full_semester acceptance 取代）。
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    for forbidden in (
        "app.services.mock_service",
        "app.api.mock",
        "app.course_data.snapshot",
        "requests",
        "httpx",
        "urllib",
    ):
        assert forbidden not in imported, f"planning_runtime must not import {forbidden}"

    # 旧的单 bundle 配置面⛔ 不存在（没有 campus / snapshot 退化路径）。
    assert "APP_COURSE_SNAPSHOT" not in source
    assert "SnapshotCourseDataProvider" not in source

    for required in (
        "APP_REAL_CASE_A_ENABLED",
        "APP_CASE_A_CURRICULUM_CASE_PATH",
        "APP_COURSE_DATA_SQLITE_PATH",
        "APP_COURSE_DATA_SEMESTER",
        "APP_COURSE_DATA_ACCEPTANCE_SHA256",
    ):
        assert required in source


def test_real_endpoint_returns_503_without_a_runtime(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_environment(monkeypatch, {})

    response = client.post(PLAN_PATH, json=_request_payload())

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
    assert MOCK_DATA_SOURCE_HEADER not in response.headers


def test_real_endpoint_returns_503_for_a_campus_only_store(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campus_store = _campus_only_store(tmp_path)
    _install_environment(
        monkeypatch,
        _environment(tmp_path, sqlite_path=campus_store, digest="c" * 64),
    )

    response = client.post(PLAN_PATH, json=_request_payload())

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "real_pipeline_not_configured"
    assert MOCK_DATA_SOURCE_HEADER not in response.headers


def test_real_endpoint_serves_a_synthetic_full_semester_runtime(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_schema
) -> None:
    _install_environment(monkeypatch, _environment(tmp_path))

    response = client.post(PLAN_PATH, json=_request_payload())

    assert response.status_code == 200
    payload = response.json()
    assert MOCK_DATA_SOURCE_HEADER not in response.headers
    assert MOCK_DATA_SOURCE_VALUE not in json.dumps(payload)

    schema = load_schema("plan_result.schema.json")
    import jsonschema

    jsonschema.validate(payload, schema)

    selected = {
        (item["course_id"], item["class_id"]) for item in payload["selected_classes"]
    }
    bound = {
        (f"SYN-{shard_id.upper()}", f"{shard_id}-000") for shard_id in SHARD_IDS
    }
    assert selected <= bound


def test_mock_channel_remains_separate_and_marked(client) -> None:
    response = client.get("/api/v1/mock/course-offerings")

    assert response.status_code == 200
    assert response.headers[MOCK_DATA_SOURCE_HEADER] == MOCK_DATA_SOURCE_VALUE


def test_unconfigured_runtime_never_serves_mock_data(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_environment(monkeypatch, {})

    response = client.post(PLAN_PATH, json=_request_payload())

    assert response.status_code == 503
    assert "selected_classes" not in response.text


def test_runtime_uses_the_full_semester_scope_constant() -> None:
    # scope 口径只来自 store 的常量，⛔ runtime 不自己造 scope。
    assert SCOPE_KIND_FULL_SEMESTER == "full_semester"
    assert SCOPE_KIND_CAMPUS == "campus"
