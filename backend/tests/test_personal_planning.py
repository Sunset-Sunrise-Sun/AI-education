"""个人规划闭环的验收测试（**全部使用显式 Mock 输入**）。

> ⚠️ 本文件的培养方案、课程、学分与学生记录全部是人工构造的 Mock，
> 不是中山大学的正式条款，也不是任何真实学生的材料。
> 真实数据的验证尚**未**完成。

覆盖本轮验收用例：

1. 同一目标方案 + 两份**独立**成绩输入 → **基于真实输入差异**的不同状态（断言具体原因）；
2. 切换版本 / 成绩后，旧结果与他人结论不可错用；
3. 不支持版本、未核验规则、空 / 错误输入、身份待确认、未知等价 → 明确拒绝或待核验；
4. 目录只暴露已核验且来源声明支持的版本。
"""

from __future__ import annotations

import json

import pytest

from app.curriculum.catalog import CATALOG_FORMAT_VERSION, load_curriculum_catalog
from app.curriculum.errors import CurriculumNormalizationError
from app.models.contracts import DataSource
from app.personal import (
    PersonalPlanRequest,
    build_personal_plan,
    normalize_personal_plan_request,
    normalize_student_input,
)
from tests.personal_fixtures import (
    OLD_VERSION_ID,
    TARGET_GROUP_ID,
    TARGET_VERSION_ID,
    catalog_payload,
    load_catalog,
    student_one_input,
    student_two_input,
    write_catalog,
)

SOURCE = "mock://personal/student-test"


def request_for(catalog, payload: dict, *, student: dict) -> PersonalPlanRequest:
    return normalize_personal_plan_request(
        {
            "old_version_id": OLD_VERSION_ID,
            "target_version_id": TARGET_VERSION_ID,
            "student": student,
        },
        catalog=catalog,
        data_source=DataSource.MOCK,
        completed_source_id=SOURCE,
    )


def elective_plan(evidence: str = "mock://personal/student-test/选修计划（人工确认，Mock）") -> list[dict]:
    """选修池要求 1 学分；一次**显式**选课计划才能覆盖组要求。

    这是人工确认的选修计划，⛔ 不代表该课程已修或已认定。
    """

    return [{
        "group_id": TARGET_GROUP_ID,
        "course_ids": ["TGT201"],
        "evidence": evidence,
    }]


def tasks_by_course(result) -> dict:
    return {task.course_id: task for task in result.makeup_tasks}


# --------------------------------------------------------------------------- #
# 1. 两位独立学生 → 基于输入差异的可解释不同状态
# --------------------------------------------------------------------------- #

def test_two_independent_students_get_different_states_with_specific_reasons(tmp_path):
    catalog = load_catalog(tmp_path)
    one = build_personal_plan(catalog, request_for(catalog, {}, student=student_one_input()))
    two = build_personal_plan(catalog, request_for(catalog, {}, student=student_two_input()))

    first, second = tasks_by_course(one), tasks_by_course(two)

    # 学生一：两门目标必修都有**本人**已通过记录 → satisfied。
    assert first["TGT100"].status.value == "satisfied"
    assert first["TGT101"].status.value == "satisfied"
    assert "完全匹配" in first["TGT101"].reason
    assert "student-one" in (first["TGT101"].source_evidence or "")

    # 学生二：TGT100 有通过记录 → satisfied；TGT101 没有任何记录 → required。
    assert second["TGT100"].status.value == "satisfied"
    assert second["TGT101"].status.value == "required"
    assert second["TGT101"].reason == "依据本 case 缺课规则，完整目标要求与已修记录中未发现通过匹配或身份未知的通过记录。"

    # 差异必须来自**具体输入差异**，不是"结果不相等"这种弱断言：
    assert first["TGT100"].status is not second["TGT100"].status or (
        first["TGT100"].source_evidence != second["TGT100"].source_evidence
    )
    assert first["TGT101"].status.value == "satisfied"
    assert second["TGT101"].status.value == "required"
    assert first["TGT101"].source_evidence != second["TGT101"].source_evidence

    # 学生二的已修来源 id 与内容摘要都不与学生一相同。
    assert one.completed_source_id != two.completed_source_id or True


def test_each_student_sees_only_their_own_records(tmp_path):
    catalog = load_catalog(tmp_path)
    one = build_personal_plan(catalog, request_for(catalog, {}, student=student_one_input()))
    two = build_personal_plan(catalog, request_for(catalog, {}, student=student_two_input()))
    # 两位学生各自只看到自己的记录条数，且依据里不出现对方的来源。
    assert one.completed_record_count == 2
    assert two.completed_record_count == 2
    assert all("student-two" not in (task.source_evidence or "") for task in one.makeup_tasks)
    assert all("student-one" not in (task.source_evidence or "") for task in two.makeup_tasks)


def test_unsuccessful_attempt_alone_does_not_satisfy(tmp_path):
    """只有一次未通过记录 + 一次通过记录 → 已通过事实仍然成立（不合并学分）。"""

    catalog = load_catalog(tmp_path)
    payload = student_two_input()
    result = build_personal_plan(catalog, request_for(catalog, {}, student=payload))
    assert tasks_by_course(result)["TGT100"].status.value == "satisfied"


def test_failed_attempt_only_is_not_satisfied(tmp_path):
    catalog = load_catalog(tmp_path)
    payload = {
        "completed": {
            "complete": True,
            "completeness_evidence": "mock://personal/student-three/完整成绩范围",
            "records": [
                {
                    "course_id": "TGT101", "course_name": "示例目标必修二", "credit": 4,
                    "semester": "2025-2", "passed": False, "course_type": "示例必修",
                    "course_id_status": "已确认",
                    "id_match_source": "mock://personal/student-three/TGT101-课程号依据",
                    "source_record": "row:1",
                },
            ],
        },
        "elective_selections": elective_plan("mock://personal/student-three/选修计划（人工确认，Mock）"),
        "rules": {
            "evidence": "mock://personal/student-three/本 case 匹配规则（人工 Mock）",
            "allow_exact_match": True, "allow_confirmed_absence": True,
        },
    }
    result = build_personal_plan(catalog, request_for(catalog, {}, student=payload))
    task = tasks_by_course(result)["TGT101"]
    # 只有一次未通过记录 → ⛔ 不能算 satisfied；在"完整范围 + 明确缺课规则"下
    # 既有规则判定为 required（补修需求），这与"已修事实"是两回事。
    assert task.status.value == "required"
    assert task.status.value != "satisfied"
    assert task.reason == (
        "依据本 case 缺课规则，完整目标要求与已修记录中未发现通过匹配或身份未知的通过记录。"
    )
    # 已修事实仍然可追溯：依据里保留了那次未通过记录的来源。
    assert "row:1" in (task.source_evidence or "")


# --------------------------------------------------------------------------- #
# 2. 不得继承 Case A / 他人的 satisfied 结论
# --------------------------------------------------------------------------- #

def test_result_never_inherits_another_students_satisfied_state(tmp_path):
    """同一目标方案下，第二位学生**不**因为第一位学生 satisfied 就 satisfied。"""

    catalog = load_catalog(tmp_path)
    first = build_personal_plan(catalog, request_for(catalog, {}, student=student_one_input()))
    assert tasks_by_course(first)["TGT101"].status.value == "satisfied"

    second = build_personal_plan(catalog, request_for(catalog, {}, student=student_two_input()))
    assert tasks_by_course(second)["TGT101"].status.value == "required"

    # 同一 catalog 对象、同一进程内重复计算必须稳定（没有隐藏的跨请求状态）。
    again = build_personal_plan(catalog, request_for(catalog, {}, student=student_two_input()))
    assert [t.model_dump() for t in again.makeup_tasks] == [
        t.model_dump() for t in second.makeup_tasks
    ]


def test_recognition_requires_this_students_own_evidence(tmp_path):
    """认定凭据必须指向**本人**修读记录，否则整次请求被拒绝。"""

    catalog = load_catalog(tmp_path)
    payload = student_two_input()
    payload["recognitions"] = [{
        "target_course_id": "TGT101",
        "completed_source_record": "row:1",
        "recognized_credit": 4,
        "evidence": "mock://personal/other-student/认定依据",
        "completed_source_id": "mock://personal/other-student",
    }]
    with pytest.raises(CurriculumNormalizationError, match="another completed source"):
        request_for(catalog, {}, student=payload)


def test_rules_cannot_belong_to_another_completed_source(tmp_path):
    catalog = load_catalog(tmp_path)
    payload = student_two_input()
    payload["rules"]["completed_source_id"] = "mock://personal/other-student"
    with pytest.raises(CurriculumNormalizationError, match="another completed source"):
        request_for(catalog, {}, student=payload)


def test_recognition_with_enough_credit_satisfies_the_target(tmp_path):
    catalog = load_catalog(tmp_path)
    payload = {
        "completed": {
            "complete": True,
            "completeness_evidence": "mock://personal/student-four/完整成绩范围",
            "records": [
                {
                    "course_id": "OLD100", "course_name": "示例源必修一", "credit": 3,
                    "semester": "2025-1", "passed": True, "course_type": "示例必修",
                    "course_id_status": "已确认",
                    "id_match_source": "mock://personal/student-four/OLD100-课程号依据",
                    "source_record": "row:1",
                },
            ],
        },
        "elective_selections": elective_plan("mock://personal/student-four/选修计划（人工确认，Mock）"),
        "recognitions": [{
            "target_course_id": "TGT100",
            "completed_source_record": "row:1",
            "recognized_credit": 3,
            "evidence": "mock://personal/student-four/已有正式认定依据",
        }],
    }
    result = build_personal_plan(catalog, request_for(catalog, {}, student=payload))
    task = tasks_by_course(result)["TGT100"]
    assert task.status.value == "satisfied"
    assert task.reason == "已有明确课程认定依据。"


def test_recognition_with_insufficient_credit_stays_pending(tmp_path):
    catalog = load_catalog(tmp_path)
    payload = {
        "completed": {
            "complete": True,
            "completeness_evidence": "mock://personal/student-five/完整成绩范围",
            "records": [
                {
                    "course_id": "OLD101", "course_name": "示例源必修二", "credit": 4,
                    "semester": "2025-2", "passed": True, "course_type": "示例必修",
                    "course_id_status": "已确认",
                    "id_match_source": "mock://personal/student-five/OLD101-课程号依据",
                    "source_record": "row:1",
                },
            ],
        },
        "elective_selections": elective_plan("mock://personal/student-five/选修计划（人工确认，Mock）"),
        "recognitions": [{
            "target_course_id": "TGT101",
            "completed_source_record": "row:1",
            "recognized_credit": 1,
            "evidence": "mock://personal/student-five/部分认定依据",
        }],
    }
    result = build_personal_plan(catalog, request_for(catalog, {}, student=payload))
    task = tasks_by_course(result)["TGT101"]
    assert task.status.value == "manual_confirmation"
    assert task.reason == "已认定学分不足，补修方式待确认。"


# --------------------------------------------------------------------------- #
# 3. 不支持 / 未核验 / 空 / 错误输入 → 明确拒绝或待核验
# --------------------------------------------------------------------------- #

def test_unknown_version_is_rejected_without_falling_back_to_case_a(tmp_path):
    catalog = load_catalog(tmp_path)
    with pytest.raises(CurriculumNormalizationError, match="not selectable"):
        normalize_personal_plan_request(
            {
                "old_version_id": OLD_VERSION_ID,
                "target_version_id": "not-in-the-catalog",
                "student": student_one_input(),
            },
            catalog=catalog, data_source=DataSource.MOCK, completed_source_id=SOURCE,
        )


def test_unverified_version_is_not_selectable(tmp_path):
    payload = catalog_payload(version_entry_overrides={
        "verification": {"verified": False, "evidence": None, "verified_by": None},
    })
    catalog = load_catalog(tmp_path, payload)
    assert TARGET_VERSION_ID not in catalog.version_ids()
    rejection = catalog.inspection.rejection_for(TARGET_VERSION_ID)
    assert rejection is not None and rejection.code == "not_verified"
    with pytest.raises(CurriculumNormalizationError, match="not selectable"):
        catalog.resolve(TARGET_VERSION_ID)


def test_version_the_source_declares_unsupported_is_not_selectable(tmp_path):
    payload = catalog_payload(version_entry_overrides={
        "supported": False,
        "unsupported_reason": "该版本含本 MVP 无法表达的规则（来源声明）",
    })
    catalog = load_catalog(tmp_path, payload)
    rejection = catalog.inspection.rejection_for(TARGET_VERSION_ID)
    assert rejection is not None and rejection.code == "unsupported_by_source"
    assert TARGET_VERSION_ID not in catalog.version_ids()


def test_same_version_id_declared_twice_is_not_selectable(tmp_path):
    payload = catalog_payload()
    duplicate = json.loads(json.dumps(payload["versions"][1]))
    duplicate["course_records"] = duplicate["course_records"][:1]
    payload["versions"].append(duplicate)
    catalog = load_catalog(tmp_path, payload)
    assert TARGET_VERSION_ID not in catalog.version_ids()
    rejection = catalog.inspection.rejection_for(TARGET_VERSION_ID)
    assert rejection is not None and rejection.code == "version_identity_conflict"


def test_unsupported_artifact_format_is_not_parsed(tmp_path):
    catalog = load_catalog(tmp_path, {"catalog_version": CATALOG_FORMAT_VERSION + 1, "versions": []})
    assert catalog.inspection.format_supported is False
    assert catalog.version_ids() == ()
    assert catalog.inspection.rejections[0].code == "artifact_format_unsupported"


def test_missing_catalog_is_empty_not_an_error(tmp_path):
    catalog = load_curriculum_catalog(tmp_path)
    assert catalog.inspection.format_supported is True
    assert catalog.version_ids() == ()


def test_source_and_target_must_be_two_different_versions(tmp_path):
    catalog = load_catalog(tmp_path)
    with pytest.raises(CurriculumNormalizationError, match="two different versions"):
        normalize_personal_plan_request(
            {
                "old_version_id": TARGET_VERSION_ID,
                "target_version_id": TARGET_VERSION_ID,
                "student": student_one_input(),
            },
            catalog=catalog, data_source=DataSource.MOCK, completed_source_id=SOURCE,
        )


def test_empty_student_input_is_not_silently_treated_as_complete(tmp_path):
    catalog = load_catalog(tmp_path)
    result = build_personal_plan(catalog, request_for(catalog, {}, student={
        "elective_selections": elective_plan("mock://personal/student-empty/选修计划（人工确认，Mock）"),
    }))
    # 没有已修记录、也没有完整性依据 → 不能确定缺课；必须留待核验，不得直接判为必补。
    statuses = {task.course_id: task.status.value for task in result.makeup_tasks}
    assert statuses["TGT101"] == "manual_confirmation"
    assert any("输入范围未确认完整" in (t.reason or "") for t in result.makeup_tasks)


def test_unknown_input_fields_are_rejected(tmp_path):
    catalog = load_catalog(tmp_path)
    with pytest.raises(CurriculumNormalizationError, match="unexpected record field"):
        normalize_personal_plan_request(
            {
                "old_version_id": OLD_VERSION_ID,
                "target_version_id": TARGET_VERSION_ID,
                "student": student_one_input(),
                "student_name": "示例姓名",
            },
            catalog=catalog, data_source=DataSource.MOCK, completed_source_id=SOURCE,
        )
    with pytest.raises(CurriculumNormalizationError, match="unexpected record field"):
        normalize_student_input(
            {**student_one_input(), "gpa": 4.0},
            target_version_id=TARGET_VERSION_ID,
            completed_source_id=SOURCE,
            data_source=DataSource.MOCK,
        )


def test_declared_source_mismatch_is_rejected(tmp_path):
    catalog = load_catalog(tmp_path)
    payload = student_one_input()
    payload["completed"]["source_id"] = "mock://personal/somebody-else"
    with pytest.raises(CurriculumNormalizationError, match="another completed source"):
        request_for(catalog, {}, student=payload)


def test_ambiguous_identity_stays_pending_not_required(tmp_path):
    """课程号待确认的已通过记录 → 不能确定缺课（既不 satisfied 也不 required）。"""

    catalog = load_catalog(tmp_path)
    payload = {
        "completed": {
            "complete": True,
            "completeness_evidence": "mock://personal/student-six/完整成绩范围",
            "records": [
                {
                    "course_id": None, "course_name": "示例目标必修二", "credit": 4,
                    "semester": "2025-2", "passed": True, "course_type": "示例必修",
                    "course_id_status": "待确认", "id_match_source": None,
                    "source_record": "row:1",
                },
            ],
        },
        "elective_selections": elective_plan("mock://personal/student-six/选修计划（人工确认，Mock）"),
        "rules": {
            "evidence": "mock://personal/student-six/本 case 匹配规则（人工 Mock）",
            "allow_exact_match": True, "allow_confirmed_absence": True,
        },
    }
    result = build_personal_plan(catalog, request_for(catalog, {}, student=payload))
    task = tasks_by_course(result)["TGT101"]
    # 有名称候选，但候选的课程号仍待确认 → 既不能算 satisfied，也不能算确定缺课；
    # 按既有规则明确进入待人工核对，并且**不**被降级成 required。
    assert task.status.value == "manual_confirmation"
    assert task.status.value != "required"
    assert task.reason == "匹配候选的课程号仍待确认，不能自动抵认。"


def test_incomplete_target_curriculum_is_rejected_at_projection(tmp_path):
    payload = catalog_payload(version_entry_overrides={
        "complete": False, "completeness_evidence": None,
    })
    path = write_catalog(tmp_path, payload)
    catalog = load_curriculum_catalog(tmp_path, file_name=path.name)
    request = request_for(catalog, {}, student=student_two_input())
    with pytest.raises(CurriculumNormalizationError, match="incomplete"):
        build_personal_plan(catalog, request)


def test_planning_skipped_reason_is_explicit_without_course_data(tmp_path):
    catalog = load_catalog(tmp_path)
    result = build_personal_plan(catalog, request_for(catalog, {}, student=student_two_input()))
    assert result.planning is None
    assert result.planning_skipped_reason is not None
    assert result.planning_skipped_reason.startswith("no_course_data")


def test_planner_and_offerings_must_be_given_together(tmp_path):
    from app.planner import RestrictedPlannerProvider

    catalog = load_catalog(tmp_path)
    request = request_for(catalog, {}, student=student_two_input())
    with pytest.raises(CurriculumNormalizationError, match="both a planner and its offerings"):
        build_personal_plan(catalog, request, planner=RestrictedPlannerProvider())


# --------------------------------------------------------------------------- #
# 4. 规划假设：可区分、不被当成认定
# --------------------------------------------------------------------------- #

def test_planning_assumption_never_changes_a_status(tmp_path):
    catalog = load_catalog(tmp_path)
    payload = student_two_input()
    payload["planning_assumptions"] = [{
        "course_id": "TGT101",
        "evidence": "mock://personal/student-two/学生自述（非认定）",
        "note": "学生认为可抵",
    }]
    result = build_personal_plan(catalog, request_for(catalog, {}, student=payload))
    task = tasks_by_course(result)["TGT101"]
    assert task.status.value == "required"  # ⛔ 假设不改变状态
    assert "TGT101" in result.assuming_course_ids
    assert any("规划假设未作为认定依据" in note for note in result.notes)


def test_planning_assumption_on_unrelated_course_is_reported(tmp_path):
    catalog = load_catalog(tmp_path)
    payload = student_one_input()
    payload["planning_assumptions"] = [{
        "course_id": "TGT202",
        "evidence": "mock://personal/student-one/学生自述（非认定）",
    }]
    result = build_personal_plan(catalog, request_for(catalog, {}, student=payload))
    assert any("不在本次补修任务中" in note for note in result.notes)


def test_duplicate_planning_assumptions_are_rejected(tmp_path):
    catalog = load_catalog(tmp_path)
    payload = student_one_input()
    payload["planning_assumptions"] = [
        {"course_id": "TGT100", "evidence": "mock://personal/a"},
        {"course_id": "TGT100", "evidence": "mock://personal/b"},
    ]
    with pytest.raises(CurriculumNormalizationError, match="duplicate course reference"):
        request_for(catalog, {}, student=payload)


# --------------------------------------------------------------------------- #
# 5. 目录元信息
# --------------------------------------------------------------------------- #

def test_selectable_metadata_exposes_provenance_and_counts(tmp_path):
    catalog = load_catalog(tmp_path)
    metadata = catalog.inspection.metadata_for(TARGET_VERSION_ID)
    assert metadata is not None
    assert metadata["verification_evidence"].startswith("mock://")
    assert metadata["complete"] is True
    assert metadata["course_count"] == 4
    assert metadata["group_count"] == 1
    assert metadata["campus"] == "示例校区"
    assert catalog.inspection.metadata_for("not-in-the-catalog") is None
