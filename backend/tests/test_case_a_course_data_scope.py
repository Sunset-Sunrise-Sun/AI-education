"""Case A scoped（南校园 + 深圳校区）课程数据 + 当前课表 CLI 测试。

**纯 synthetic、零网络、零真实数据**：所有课程号 / 课程名 / 教学班号 / 教师均为人工虚构，
⛔ 不读取任何真实 Capture Bundle、⛔ 不访问学校系统、⛔ 不导入真实 artifact。

覆盖（对齐本次任务范围）：

```text
South + Shenzhen scope 不被误标成 full_semester / 全校
两个校区已验收 campus acceptance 可以直接复用（不新增信任框架）
canonical identity 去重（同 identity 同内容 → 去重并如实计数）
canonical identity 冲突（同 identity 不同内容 → fail closed）
缺一个校区 / 校区 acceptance 不唯一 → fail closed（⛔ 没有单校区 fallback）
semester 不匹配 → fail closed
Provider 只返回该学期数据集的同一批行
Case A 数据集不写回 production trust store
verify / export / smoke 三个 CLI 子命令的输出与失败码
手工 current_schedule 的合法 / 非法输入
Planner 收到的就是 Case A scoped offerings 与手工 current_schedule 原样
```
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.course_data import (
    SCOPE_KIND_CAMPUS,
    SCOPE_KIND_FULL_SEMESTER,
    CaseACampusRecord,
    CaseAScopeError,
    OfferingSnapshot,
    SnapshotScope,
    build_case_a_dataset,
    case_a_campuses,
    compute_artifact_sha256,
    import_offering_snapshot,
    initialize_course_data_store,
    load_course_data_acceptances,
)
from app.models.contracts import CourseOffering, DataSource, Meeting, Preference
from app.planner.provider import RestrictedPlannerProvider

SEMESTER = "2026-1"
OTHER_SEMESTER = "2026-2"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPOSITORY_ROOT / "tools" / "case_a_course_data.py"

SOUTH = "5062201"
SHENZHEN = "333291143"

#: ⛔ 这些号码的唯一真源是 full_semester 已批准集合；测试只断言"没有被本地复制一份"。
APPROVED_NUMBERS = {shard.shard_id: shard.opening_school_number for shard in case_a_campuses()}


def _load_cli(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli() -> ModuleType:
    return _load_cli("case_a_course_data_cli", CLI_PATH)


# ---------------------------------------------------------------------------
# synthetic fixtures（⛔ 全部人工虚构）
# ---------------------------------------------------------------------------


def _meeting(
    weekday: int = 1,
    start_section: int = 1,
    end_section: int = 2,
    weeks: tuple[int, ...] = (1, 2, 3),
    *,
    campus: str | None = "示例校区",
    classroom: str | None = "示例楼101",
) -> Meeting:
    return Meeting(
        weekday=weekday,
        start_section=start_section,
        end_section=end_section,
        weeks=list(weeks),
        campus=campus,
        classroom=classroom,
    )


def _offering(
    course_id: str = "SYN-A-0001",
    class_id: str = "01",
    *,
    semester: str = SEMESTER,
    course_name: str = "示例课程",
    meetings: list[Meeting] | None = None,
    credit: float | None = 3.0,
) -> CourseOffering:
    return CourseOffering(
        course_id=course_id,
        course_name=course_name,
        class_id=class_id,
        semester=semester,
        teacher=None,
        credit=credit,
        meetings=[_meeting()] if meetings is None else meetings,
        capacity=60,
        remaining_capacity=10,
        source="capture://synthetic/case-a",
        data_source=DataSource.REAL,
    )


def _import_campus(path: Path, *, number: str, offerings: list[CourseOffering]) -> str:
    """把一份 synthetic 校区快照声明成 `campus / <openingSchoolNumber>` 的 acceptance。"""

    snapshot = OfferingSnapshot(
        semester=SEMESTER,
        offerings=tuple(offerings),
        completeness="complete",
        reported_total=len(offerings),
    )
    artifact = compute_artifact_sha256(
        f"synthetic-campus-{number}".encode("utf-8")
    )
    import_offering_snapshot(
        path,
        snapshot,
        artifact_sha256=artifact,
        scope=SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id=number),
    )
    return artifact


@pytest.fixture()
def store_path(tmp_path: Path) -> Path:
    path = tmp_path / "course_data.sqlite3"
    initialize_course_data_store(path)
    return path


@pytest.fixture()
def two_campus_store(store_path: Path) -> Path:
    """两个校区各自的 synthetic campus acceptance（⛔ 校区之间**不共享**任何 identity）。

    ⚠️ **为什么这里刻意不塞一条"两校区都出现的同一教学班"**：
    `course_offering` 的主键是 `(semester, course_id, class_id)`（**不含 scope**），
    后一次导入会刷新该行的 `scope_kind` / `scope_id` / `artifact_sha256`。
    因此"同一个教学班同时属于两个 campus acceptance"在真实信任链里**不成立**，
    硬造这种 fixture 只会让 `load_accepted_offerings()` 的 membership 计数校验失败
    （acceptance 声明 3 行、按该 scope 只回读到 2 行 ⇒ fail closed，这是**正确**行为）。

    跨校区 canonical identity 去重的规则由 `_merge_case_a_offerings()` 负责，
    由 `test_merge_deduplicates_identical_identity_and_rejects_conflicting_content` 直接覆盖。
    """

    _import_campus(
        store_path,
        number=SOUTH,
        offerings=[
            _offering("SYN-A-0001", "01", course_name="示例课程甲"),
            _offering("SYN-A-0002", "01", course_name="示例课程乙"),
        ],
    )
    _import_campus(
        store_path,
        number=SHENZHEN,
        offerings=[
            _offering("SYN-A-0003", "01", course_name="示例课程丙"),
            _offering("SYN-A-0003", "02", course_name="示例课程丙"),
        ],
    )
    return store_path


# ---------------------------------------------------------------------------
# scope 语义：两个校区 ≠ full_semester / 全校
# ---------------------------------------------------------------------------


def test_dataset_is_labeled_case_scoped_and_never_full_semester(
    two_campus_store: Path,
) -> None:
    dataset = build_case_a_dataset(two_campus_store, semester=SEMESTER)

    assert dataset.is_full_semester is False
    assert dataset.is_whole_school is False
    assert dataset.scope.is_full_semester is False
    assert dataset.scope.is_whole_school is False

    assert dataset.scope.scope_kind == "case_scoped"
    assert dataset.scope.scope_kind != SCOPE_KIND_FULL_SEMESTER
    assert dataset.scope.scope_kind != SCOPE_KIND_CAMPUS
    assert dataset.scope.scope_label == "case-a-scoped:south+shenzhen"
    assert dataset.scope.shard_ids == ("south-campus", "shenzhen-campus")
    assert dataset.scope.opening_school_numbers == (SOUTH, SHENZHEN)

    semantics = dataset.scope.scope_semantics
    for forbidden in (
        "not_full_semester",
        "not_whole_school",
        "not_all_campus",
        "not_complete_sysu_database",
        "not_level2_real_dataset",
    ):
        assert forbidden in semantics


def test_campus_numbers_come_from_the_approved_full_semester_set() -> None:
    assert APPROVED_NUMBERS["south-campus"] == SOUTH
    assert APPROVED_NUMBERS["shenzhen-campus"] == SHENZHEN


def test_serialized_dataset_carries_positive_and_negative_scope_labels(
    two_campus_store: Path,
) -> None:
    from app.course_data import serialize_case_a_dataset

    document = serialize_case_a_dataset(
        build_case_a_dataset(two_campus_store, semester=SEMESTER)
    )

    assert document["is_full_semester"] is False
    assert document["is_whole_school"] is False
    assert document["is_all_campus"] is False
    assert document["is_level2_real_dataset"] is False
    assert document["scope_kind"] == "case_scoped"
    assert document["openingSchoolNumbers"] == [SOUTH, SHENZHEN]
    assert document["merged_offering_count"] == len(document["offerings"])
    # ⛔ 导出的 JSON 里不得出现任何 full_semester 断言。
    text = json.dumps(document, ensure_ascii=False)
    assert '"is_full_semester": true' not in text


# ---------------------------------------------------------------------------
# canonical identity 合并 / 去重 / 冲突
# ---------------------------------------------------------------------------


def test_identical_identity_across_campuses_is_deduplicated_and_reported() -> None:
    """跨校区 canonical identity 去重：同 identity **且内容相同** → 去重并如实计数。

    ⚠️ 直接调用合并函数（而不是走 Store）：`course_offering` 的 identity 不含 scope，
    所以"同一个教学班同时被两个 campus acceptance 收录"在真实信任链里无法表示
    （后导入会刷新该行的 scope → 前一个 acceptance 的 membership 计数不再自洽）。
    合并规则本身仍然必须被严格验证，因此在这里直接驱动它。
    """

    from app.course_data.case_a_scope import _merge_case_a_offerings

    south = CaseACampusRecord(
        shard_id="south-campus",
        opening_school_number=SOUTH,
        campus_acceptance_sha256="a" * 64,
        source="capture://synthetic/south",
        offering_count=2,
        offering_set_sha256="b" * 64,
    )
    shenzhen = CaseACampusRecord(
        shard_id="shenzhen-campus",
        opening_school_number=SHENZHEN,
        campus_acceptance_sha256="c" * 64,
        source="capture://synthetic/shenzhen",
        offering_count=2,
        offering_set_sha256="d" * 64,
    )

    merged, deduped = _merge_case_a_offerings(
        [
            (
                south,
                [
                    _offering("SYN-A-0001", "01", course_name="示例课程甲"),
                    _offering("SYN-A-0002", "01", course_name="示例课程乙"),
                ],
            ),
            (
                shenzhen,
                [
                    # 与 south 同一 identity、canonical 内容完全一致 → 去重。
                    _offering("SYN-A-0001", "01", course_name="示例课程甲"),
                    _offering("SYN-A-0003", "02", course_name="示例课程丙"),
                ],
            ),
        ]
    )

    assert deduped == 1
    identities = [
        (offering.semester, offering.course_id, offering.class_id) for offering in merged
    ]
    assert len(identities) == 3
    assert len(identities) == len(set(identities))
    # 稳定排序：按 (course_id, class_id)。
    assert identities == sorted(identities)


def test_same_identity_with_different_content_fails_closed() -> None:
    """同 identity + 不同 canonical 内容 → fail closed（⛔ 不静默取第一条）。"""

    from app.course_data.case_a_scope import _merge_case_a_offerings

    record = CaseACampusRecord(
        shard_id="shenzhen-campus",
        opening_school_number=SHENZHEN,
        campus_acceptance_sha256="c" * 64,
        source="capture://synthetic/shenzhen",
        offering_count=1,
        offering_set_sha256="d" * 64,
    )

    with pytest.raises(CaseAScopeError) as error:
        _merge_case_a_offerings(
            [
                (record, [_offering("SYN-A-0001", "01", course_name="示例课程甲")]),
                # 同一 identity、不同内容。
                (record, [_offering("SYN-A-0001", "01", course_name="另一个示例课程")]),
            ]
        )

    assert error.value.category == "conflicting_identity_across_case_a_campuses"
    # ⛔ 错误信息只含最小 identity，不回显课程名。
    assert "另一个示例课程" not in str(error.value)
    assert "示例课程甲" not in str(error.value)


def test_different_class_ids_of_the_same_course_are_not_merged(
    two_campus_store: Path,
) -> None:
    """同一门课的不同教学班各自成行（⛔ 不按 course_id 去重）。"""

    dataset = build_case_a_dataset(two_campus_store, semester=SEMESTER)

    assert dataset.duplicate_identity_deduped == 0
    assert dataset.merged_offering_count == 4
    assert sorted(item.class_id for item in dataset.offerings) == ["01", "01", "01", "02"]


# ---------------------------------------------------------------------------
# fail closed：没有单校区 / 空数据 fallback
# ---------------------------------------------------------------------------


def test_missing_campus_acceptance_fails_closed_without_fallback(store_path: Path) -> None:
    _import_campus(store_path, number=SOUTH, offerings=[_offering()])

    with pytest.raises(CaseAScopeError) as error:
        build_case_a_dataset(store_path, semester=SEMESTER)

    assert error.value.category == "campus_acceptance_missing"
    assert error.value.shard_id == "shenzhen-campus"


def test_ambiguous_campus_acceptance_fails_closed(store_path: Path) -> None:
    _import_campus(store_path, number=SOUTH, offerings=[_offering()])
    # 第二个 south artifact（不同字节 ⇒ 不同 acceptance identity）⇒ 记录不唯一。
    second = OfferingSnapshot(
        semester=SEMESTER,
        offerings=(_offering("SYN-A-0009", "01"),),
        completeness="complete",
        reported_total=1,
    )
    import_offering_snapshot(
        store_path,
        second,
        artifact_sha256=compute_artifact_sha256(b"synthetic-south-second"),
        scope=SnapshotScope(scope_kind=SCOPE_KIND_CAMPUS, scope_id=SOUTH),
    )
    _import_campus(store_path, number=SHENZHEN, offerings=[_offering("SYN-A-0003", "01")])

    with pytest.raises(CaseAScopeError) as error:
        build_case_a_dataset(store_path, semester=SEMESTER)

    assert error.value.category == "campus_acceptance_ambiguous"
    assert error.value.shard_id == "south-campus"


def test_other_semester_has_no_case_a_campus_records(two_campus_store: Path) -> None:
    with pytest.raises(CaseAScopeError) as error:
        build_case_a_dataset(two_campus_store, semester=OTHER_SEMESTER)

    assert error.value.category == "campus_acceptance_missing"


def test_expected_campus_digest_mismatch_fails_closed(two_campus_store: Path) -> None:
    with pytest.raises(CaseAScopeError) as error:
        build_case_a_dataset(
            two_campus_store,
            semester=SEMESTER,
            expected_campus_sha256={"south-campus": "0" * 64},
        )

    assert error.value.category == "campus_acceptance_mismatch"
    assert error.value.shard_id == "south-campus"


def test_unknown_shard_key_in_expected_digests_is_rejected(two_campus_store: Path) -> None:
    with pytest.raises(CaseAScopeError) as error:
        build_case_a_dataset(
            two_campus_store,
            semester=SEMESTER,
            expected_campus_sha256={"north-campus": "0" * 64},
        )

    assert error.value.category == "campus_acceptance_mismatch"


def test_expected_campus_digest_match_is_accepted(two_campus_store: Path) -> None:
    acceptances = load_course_data_acceptances(two_campus_store, semester=SEMESTER)
    expected = {
        "south-campus": next(
            item.artifact_sha256 for item in acceptances if item.scope_id == SOUTH
        ),
        "shenzhen-campus": next(
            item.artifact_sha256 for item in acceptances if item.scope_id == SHENZHEN
        ),
    }

    dataset = build_case_a_dataset(
        two_campus_store, semester=SEMESTER, expected_campus_sha256=expected
    )
    assert dataset.merged_offering_count == 4


# ---------------------------------------------------------------------------
# Provider：只返回该学期的同一批行
# ---------------------------------------------------------------------------


def test_provider_returns_the_same_rows_and_rejects_other_semesters(
    two_campus_store: Path,
) -> None:
    from app.course_data import CaseAScopedCourseDataProvider

    dataset = build_case_a_dataset(two_campus_store, semester=SEMESTER)
    provider = CaseAScopedCourseDataProvider(dataset)

    offerings = provider.get_course_offerings(SEMESTER)
    assert provider.is_full_semester is False
    assert [item.class_id for item in offerings] == [
        item.class_id for item in dataset.offerings
    ]

    with pytest.raises(CaseAScopeError) as error:
        provider.get_course_offerings(OTHER_SEMESTER)
    assert error.value.category == "semester_mismatch"


# ---------------------------------------------------------------------------
# ⛔ 只读：Case A 数据集不落进 production trust store
# ---------------------------------------------------------------------------


def test_building_the_case_a_dataset_does_not_write_to_the_store(
    two_campus_store: Path,
) -> None:
    before = two_campus_store.read_bytes()
    acceptances_before = load_course_data_acceptances(two_campus_store, semester=SEMESTER)

    dataset = build_case_a_dataset(two_campus_store, semester=SEMESTER)
    assert dataset.merged_offering_count == 4

    assert two_campus_store.read_bytes() == before
    acceptances_after = load_course_data_acceptances(two_campus_store, semester=SEMESTER)
    assert [item.artifact_sha256 for item in acceptances_after] == [
        item.artifact_sha256 for item in acceptances_before
    ]
    # ⛔ 库里不得出现任何 full_semester scope 的记录。
    assert all(item.scope_kind == SCOPE_KIND_CAMPUS for item in acceptances_after)


# ---------------------------------------------------------------------------
# 手工 current_schedule：结构化输入（⛔ 不需要用户写裸 JSON 才有此路径）
# ---------------------------------------------------------------------------


def _write_schedule(path: Path, items: list[object]) -> Path:
    path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return path


def test_manual_current_schedule_enters_the_planner_unchanged(
    two_campus_store: Path, tmp_path: Path
) -> None:
    """Case A scoped offerings + 手工课表 → RestrictedPlanner（⛔ 不改 Planner）。"""

    from app.course_data import CaseAScopedCourseDataProvider

    dataset = build_case_a_dataset(two_campus_store, semester=SEMESTER)
    provider = CaseAScopedCourseDataProvider(dataset)
    offerings = provider.get_course_offerings(SEMESTER)

    manual = CourseOffering(
        course_id="SYN-A-0001",
        course_name="示例课程甲",
        class_id="01",
        semester=SEMESTER,
        teacher=None,
        credit=3.0,
        meetings=[
            Meeting(
                weekday=2,
                start_section=3,
                end_section=4,
                weeks=[1, 2, 3],
                campus="示例校区",
                classroom="示例楼201",
            )
        ],
        data_source=DataSource.REAL,
        source="manual://case-a/current-schedule",
    )

    result = RestrictedPlannerProvider().plan(
        makeup_tasks=[],
        offerings=offerings,
        current_schedule=[manual],
        preference=Preference(),
    )

    # 手工录入的当前班必须被 Planner 收到（原样语义），而不是被丢弃或替换。
    assert manual.course_id in {item.course_id for item in offerings}
    assert result.status.value in {"feasible", "partially_feasible", "infeasible"}
    assert all(item.course_id != manual.course_id for item in result.changes)


def test_manual_schedule_loader_accepts_structured_entries(
    cli: ModuleType, tmp_path: Path
) -> None:
    entry = {
        "course_id": "SYN-A-0001",
        "course_name": "示例课程甲",
        "class_id": "01",
        "semester": SEMESTER,
        "meetings": [
            {
                "weekday": 2,
                "start_section": 3,
                "end_section": 4,
                "weeks": [1, 2, 3],
                "campus": "示例校区",
            }
        ],
        "data_source": "real",
    }
    path = _write_schedule(tmp_path / "current_schedule.json", [entry])

    loaded = cli._load_current_schedule(str(path))
    assert len(loaded) == 1
    assert loaded[0].course_id == "SYN-A-0001"
    assert loaded[0].meetings[0].weekday == 2
    assert loaded[0].meetings[0].weeks == [1, 2, 3]


def test_empty_manual_schedule_is_legal(cli: ModuleType, tmp_path: Path) -> None:
    path = _write_schedule(tmp_path / "current_schedule.json", [])
    assert cli._load_current_schedule(str(path)) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"course_id": "SYN-A-0001"},  # 不是数组
        [{"course_id": "SYN-A-0001"}],  # 缺必需字段
        [{"course_id": "SYN-A-0001", "course_name": "示例", "class_id": "01",
          "semester": SEMESTER, "meetings": [{"weekday": 8, "start_section": 1,
          "end_section": 2, "weeks": [1]}], "data_source": "real"}],  # weekday 越界
        [{"course_id": "SYN-A-0001", "course_name": "示例", "class_id": "01",
          "semester": SEMESTER, "meetings": [], "data_source": "synthetic"}],  # 非法来源
        ["not-an-object"],
    ],
)
def test_malformed_manual_schedule_is_rejected(
    cli: ModuleType, tmp_path: Path, payload: object
) -> None:
    path = tmp_path / "current_schedule.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError):
        cli._load_current_schedule(str(path))


def test_missing_manual_schedule_file_is_rejected(cli: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        cli._load_current_schedule(str(tmp_path / "absent.json"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_verify_command_prints_only_structural_summary(
    cli: ModuleType, two_campus_store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        [
            "verify",
            "--store",
            str(two_campus_store),
            "--semester",
            SEMESTER,
        ]
    )
    assert code == cli.EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["is_full_semester"] is False
    assert payload["is_whole_school"] is False
    assert payload["provider_is_full_semester"] is False
    assert payload["scope_kind"] == "case_scoped"
    assert payload["merged_offering_count"] == 4
    assert payload["duplicate_identity_deduped"] == 0
    assert payload["provider_offering_count"] == 4
    assert [item["openingSchoolNumber"] for item in payload["campuses"]] == [
        SOUTH,
        SHENZHEN,
    ]
    # ⛔ 结构性摘要不得包含教学班取值。
    assert "offerings" not in payload
    assert "示例课程甲" not in json.dumps(payload, ensure_ascii=False)


def test_export_command_writes_scope_labeled_dataset(
    cli: ModuleType, two_campus_store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "case_a_course_data.json"
    code = cli.main(
        [
            "export",
            "--store",
            str(two_campus_store),
            "--semester",
            SEMESTER,
            "--out",
            str(out),
        ]
    )
    assert code == cli.EXIT_OK

    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["is_full_semester"] is False
    assert document["scope_kind"] == "case_scoped"
    assert len(document["offerings"]) == 4

    summary = json.loads(capsys.readouterr().out)
    assert summary["written"] is True
    assert "不得提交 Git" in summary["note"]


def test_export_refuses_to_overwrite_without_force(
    cli: ModuleType, two_campus_store: Path, tmp_path: Path
) -> None:
    out = tmp_path / "case_a_course_data.json"
    out.write_text("{}", encoding="utf-8")

    code = cli.main(
        ["export", "--store", str(two_campus_store), "--semester", SEMESTER, "--out", str(out)]
    )
    assert code == cli.EXIT_INPUT
    assert out.read_text(encoding="utf-8") == "{}"


def test_verify_reports_a_machine_readable_category_on_missing_campus(
    cli: ModuleType, store_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["verify", "--store", str(store_path), "--semester", SEMESTER])
    assert code == cli.EXIT_CASE_SCOPE

    payload = json.loads(capsys.readouterr().err)
    assert "campus_acceptance_missing" in payload["error"]
    # ⛔ 错误信息不回显存储路径。
    assert str(store_path) not in payload["error"]


def test_smoke_requires_a_makeup_task_source_without_mock_fallback(
    cli: ModuleType, two_campus_store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_CASE_A_CURRICULUM_CASE_PATH", raising=False)
    schedule = _write_schedule(
        tmp_path / "current_schedule.json",
        [
            {
                "course_id": "SYN-A-0001",
                "course_name": "示例课程甲",
                "class_id": "01",
                "semester": SEMESTER,
                "meetings": [
                    {
                        "weekday": 2,
                        "start_section": 3,
                        "end_section": 4,
                        "weeks": [1, 2, 3],
                    }
                ],
                "data_source": "real",
            }
        ],
    )
    preference = tmp_path / "preference.json"
    preference.write_text(json.dumps({"avoid_cross_campus": True}), encoding="utf-8")

    code = cli.main(
        [
            "smoke",
            "--store",
            str(two_campus_store),
            "--semester",
            SEMESTER,
            "--current-schedule",
            str(schedule),
            "--preference",
            str(preference),
        ]
    )
    assert code == cli.EXIT_INPUT
    payload = json.loads(capsys.readouterr().err)
    assert "Mock" in payload["error"]


def test_smoke_runs_the_planner_with_the_case_scoped_offerings(
    cli: ModuleType, two_campus_store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    schedule = _write_schedule(
        tmp_path / "current_schedule.json",
        [
            {
                "course_id": "SYN-A-0001",
                "course_name": "示例课程甲",
                "class_id": "01",
                "semester": SEMESTER,
                "meetings": [
                    {
                        "weekday": 2,
                        "start_section": 3,
                        "end_section": 4,
                        "weeks": [1, 2, 3],
                    }
                ],
                "data_source": "real",
            }
        ],
    )
    preference = tmp_path / "preference.json"
    preference.write_text(
        json.dumps(
            {
                "max_credit": 20,
                "avoid_cross_campus": True,
                "preferred_courses": ["SYN-A-0002"],
                "avoid_times": [{"weekday": 5, "start_section": 1, "end_section": 2}],
                "notes": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    makeup = tmp_path / "makeup_tasks.json"
    makeup.write_text(
        json.dumps(
            [
                {
                    "course_id": "SYN-A-0003",
                    "course_name": "示例课程丙",
                    "credit": 3.0,
                    "status": "required",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    code = cli.main(
        [
            "smoke",
            "--store",
            str(two_campus_store),
            "--semester",
            SEMESTER,
            "--current-schedule",
            str(schedule),
            "--preference",
            str(preference),
            "--makeup-tasks",
            str(makeup),
        ]
    )
    assert code == cli.EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["is_full_semester"] is False
    assert payload["scope_label"] == "case-a-scoped:south+shenzhen"
    assert payload["offerings_from_case_a_scope"] == 4
    assert payload["makeup_tasks_source"] == "explicit_file"
    assert payload["makeup_task_count"] == 1
    assert payload["current_schedule_count"] == 1
    assert payload["plan_status"] in {"feasible", "partially_feasible", "infeasible"}
    assert payload["planner_output_note"]

    # Planner 原样收到了手工录入的当前班（⛔ 未丢弃、⛔ 未被改写）。
    assert {"course_id": "SYN-A-0001", "class_id": "01"} in payload["selected_classes"]

    # Preference 未完全执行的字段必须**如实出现在** unresolved 中（⛔ 不静默忽略）。
    unresolved_text = " ".join(item["message"] for item in payload["unresolved"])
    assert "max_credit" in unresolved_text
    assert "avoid_cross_campus" in unresolved_text


def test_export_command_output_never_claims_full_semester(
    cli: ModuleType, two_campus_store: Path, tmp_path: Path
) -> None:
    out = tmp_path / "case_a_course_data.json"
    assert (
        cli.main(
            [
                "export",
                "--store",
                str(two_campus_store),
                "--semester",
                SEMESTER,
                "--out",
                str(out),
            ]
        )
        == cli.EXIT_OK
    )
    text = out.read_text(encoding="utf-8")
    assert "case-scoped" in text or "case_scoped" in text
    assert "全学期" not in text or "不代表全学期" in text
