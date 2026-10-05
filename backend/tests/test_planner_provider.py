"""受限 Provider 正式测试。所有教学班为合成 Mock，不是学校数据。"""

from copy import deepcopy
from inspect import Parameter, signature
from itertools import permutations, product

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.integration import PlanningOrchestrator, PlannerProvider
from app.models.contracts import CourseOffering, MakeupTask, Meeting, Preference
from app.planner import RestrictedPlannerProvider, repair_target_section
from app.planner.conflicts import ConflictState
from app.planner.feasibility import combination_state


def section(cid="A", class_id="a", day=1, *, unknown=False, **fields):
    return CourseOffering(
        course_id=cid, course_name=f"Mock {cid}", class_id=class_id, semester="2026-1",
        meetings=[] if unknown else [Meeting(weekday=day, start_section=1, end_section=2, weeks=[1, 3])],
        data_source="mock", **fields,
    )


def task(cid="A", **fields):
    return MakeupTask(course_id=cid, course_name=f"Mock {cid}", credit=3, status=fields.pop("status", "required"), **fields)


def run(tasks=None, offerings=None, current=None, preference=None):
    return RestrictedPlannerProvider().plan(
        makeup_tasks=tasks or [], offerings=offerings or [],
        current_schedule=current or [], preference=preference or Preference(),
    )


def ids(result):
    return [(item.course_id, item.class_id) for item in result.selected_classes]


def types(result):
    return {item.type for item in result.unresolved}


def test_frozen_protocol_signature():
    provider = RestrictedPlannerProvider()
    assert isinstance(provider, PlannerProvider)
    parameters = signature(provider.plan).parameters
    assert list(parameters) == ["makeup_tasks", "offerings", "current_schedule", "preference"]
    assert all(p.kind is Parameter.KEYWORD_ONLY for p in parameters.values())


def test_unique_addition_keeps_full_current_schedule_and_records_change():
    result = run([task()], [section()], [section("B", "b", 2)])
    assert result.status.value == "partially_feasible"
    assert ids(result) == [("B", "b"), ("A", "a")]
    assert len(result.changes) == 1
    change = result.changes[0]
    assert (change.course_id, change.from_class, change.to_class) == ("A", None, "a")
    assert result.risks == []
    assert any("缺失推荐/截止学期" in item.message for item in result.unresolved)


@pytest.mark.parametrize("unknown_first", [True, False])
def test_unused_unknown_does_not_downgrade_unique_known(unknown_first):
    offers = [section(class_id="unknown", unknown=True), section()]
    if not unknown_first:
        offers.reverse()
    result = run([task()], offers)
    assert result.status.value == "partially_feasible"  # 学期要求未知，非未用 UNKNOWN 导致。
    assert ids(result) == [("A", "a")]
    assert "schedule_unknown" not in types(result)


def test_unknown_only_required_is_partial_never_selected():
    result = run([task()], [section(unknown=True)])
    assert result.status.value == "partially_feasible"
    assert ids(result) == [] and result.changes == []
    assert "schedule_unknown" in types(result)
    message = next(item.message for item in result.unresolved if item.type == "schedule_unknown")
    assert "当前来源快照" in message
    assert "尚未排课" not in message


def test_current_unknown_is_retained_and_blocks_known_addition():
    result = run([task()], [section()], [section("B", "b", unknown=True)])
    assert result.status.value == "partially_feasible"
    assert ids(result) == [("B", "b")]
    assert "schedule_unknown" in types(result)
    assert result.changes == []


@pytest.mark.parametrize("current", [[], [section()], [section(unknown=True)]])
def test_no_tasks_certifies_or_reports_current_state(current):
    result = run(current=current)
    assert ids(result) == [(s.course_id, s.class_id) for s in current]
    assert result.changes == []
    assert result.status.value == ("partially_feasible" if current and not current[0].meetings else "feasible")


@pytest.mark.parametrize("count", [2, 3])
def test_multiple_clear_require_selection_even_if_only_one_global_combination(count):
    offers = [section(class_id=f"a{i}", day=i+1) for i in range(count)]
    # B makes all but a0 incompatible as a joint combination; A still has multiple CLEAR.
    if count == 2:
        offers.append(section("B", "b", 2))
        tasks = [task(), task("B")]
    else:
        tasks = [task()]
    result = run(tasks, offers)
    assert result.status.value == "partially_feasible"
    assert "selection_required" in types(result)
    assert ("A", "a0") not in ids(result)


def test_clear_original_preserved_without_duplicate_or_change():
    result = run([task()], [section(class_id="alt", day=2)], [section()])
    assert result.status.value == "feasible"
    assert ids(result) == [("A", "a")]
    assert result.changes == []


@pytest.mark.parametrize("unknown", [False, True])
@pytest.mark.parametrize("alternatives", [1, 2])
def test_existing_target_never_automatically_repaired(unknown, alternatives):
    original = section(unknown=unknown)
    blocker = section("B", "b", 1)
    offers = [section(class_id=f"alt{i}", day=3+i) for i in range(alternatives)]
    result = run([task()], offers, [original] if unknown else [original, blocker])
    assert result.status.value == "partially_feasible"
    assert ids(result)[0] == ("A", "a")
    assert "selection_required" in types(result)
    assert result.changes == []


def test_current_original_is_authoritative_over_offerings_snapshot():
    result = run([task()], [section(unknown=True)], [section()])
    assert result.status.value == "feasible"
    assert "schedule_unknown" not in types(result)


def test_explicit_repair_remains_independent_and_plan_does_not_invent_history():
    current = [section(), section("B", "b")]
    offers = [section(class_id="alt", day=3)]
    repair = repair_target_section(course_id="A", current_class_id="a", semester="2026-1",
                                   offerings=offers, current_schedule=current, replacement_class_id="alt")
    assert len(repair.changes) == 1
    result = run([task()], offers, list(repair.new_schedule))
    assert result.status.value == "feasible"
    assert ids(result) == [("A", "alt"), ("B", "b")]
    assert result.changes == []  # 与本次 current_schedule 比较，不能伪造之前的 replacement。


@pytest.mark.parametrize("unknown_alternative", [False, True])
def test_joint_unique_additions_conflict_without_order_based_sacrifice(unknown_alternative):
    offers = [section(), section("B", "b")]
    if unknown_alternative:
        offers.append(section("B", "unknown", unknown=True))
    results = [run(list(order), offers) for order in permutations([task(), task("B")])]
    assert results[0].model_dump() == results[1].model_dump()
    assert ids(results[0]) == [] and results[0].changes == []
    assert results[0].status.value == "partially_feasible"  # 新增目标的本学期必达性未知。
    assert any("本学期必达" in item.message for item in results[0].unresolved)


def test_complete_joint_proof_requires_all_combinations_not_greedy_failure():
    offers = [section(class_id="a1"), section(class_id="a2", day=2), section("B", "b1"), section("B", "b2", 2)]
    result = run([task(), task("B")], offers)
    assert result.status.value == "partially_feasible"  # 两个跨天组合存在但必须明确选择。
    assert "selection_required" in types(result)
    assert ids(result) == []


def test_all_known_combinations_impossible_is_infeasible():
    offers = [section(class_id="a1"), section(class_id="a2"), section("B", "b1"), section("B", "b2")]
    # 已选课程保留目标确定；缺省学期的新任务不能作为必达证明夹具。
    result = run([task(), task("B")], offers, [section(), section("B", "b")])
    assert result.status.value == "infeasible"
    assert "selection_required" not in types(result)  # 实际没有可明确选择的 CLEAR 替代班。
    assert any("全部原班" in u.message for u in result.unresolved)


@pytest.mark.parametrize("unknown_escape", [False, True])
def test_three_required_tasks_pairwise_possible_but_jointly_impossible(unknown_escape):
    # 任意两任务可分配到两天，但三任务不可能同时占用两个时段。
    offers = [section(cid, f"{cid}{day}", day) for cid in ["A", "B", "C"] for day in [1, 2]]
    if unknown_escape:
        offers.append(section("C", "c-unknown", unknown=True))
    current = [section(cid, f"{cid}-current", day=1) for cid in ["A", "B", "C"]]
    result = run([task(cid) for cid in ["A", "B", "C"]], offers, current)
    assert result.status.value == ("partially_feasible" if unknown_escape else "infeasible")
    assert ids(result) == [(item.course_id, item.class_id) for item in current]
    assert result.changes == []


def test_retains_independent_unique_addition_when_other_tasks_await_selection():
    result = run([task(), task("B")], [section(), section("B", "b1", 2), section("B", "b2", 3)])
    assert result.status.value == "partially_feasible"
    assert ids(result) == [("A", "a")]
    assert len(result.changes) == 1 and result.changes[0].course_id == "A"


def test_known_joint_failure_does_not_select_only_one_of_colliding_requireds():
    result = run([task(), task("B"), task("C")], [section(), section("B", "b"), section("C", "c", 3)])
    assert result.status.value == "partially_feasible"  # 未选任务学期要求均未知。
    assert ids(result) == [("C", "c")]
    assert [c.course_id for c in result.changes] == ["C"]


def test_summary_reports_mock_scope_without_claiming_real_validation():
    result = run([task()], [section()])
    assert "mock" in result.objective_summary
    assert "不代表完整 Planner MVP" in result.objective_summary


def test_uncertain_existing_target_not_frozen_for_false_impossibility_proof():
    result = run([task(recommended_semester=2), task("B")],
                 [section(class_id="alt", day=3), section("B", "b")], [section()])
    assert result.status.value == "partially_feasible"


def test_full_known_proof_overrides_unrelated_unknown():
    result = run([task("C", recommended_semester=2)], current=[section(), section("B", "b"), section("C", "c", unknown=True)])
    assert result.status.value == "infeasible"
    assert "schedule_unknown" in types(result)


def test_unknown_alternative_prevents_candidate_failure_becoming_global_proof():
    result = run([task()], [section(), section(class_id="unknown", unknown=True)], [section("B", "b")])
    assert result.status.value == "partially_feasible"
    assert "schedule_unknown" in types(result)


def test_partial_snapshot_absence_does_not_prove_school_has_no_offering():
    result = run([task()])
    assert result.status.value == "partially_feasible"
    assert "missing_data" in types(result)
    assert any("本学期" in u.message for u in result.unresolved)


def test_missing_other_task_does_not_erase_independent_impossibility_proof():
    result = run([task("MISSING")], current=[section(), section("B", "b")])
    assert result.status.value == "infeasible"
    assert "missing_data" in types(result)


@pytest.mark.parametrize("field", ["recommended_semester", "deadline_semester"])
def test_relative_semester_unknown_prevents_required_joint_impossibility(field):
    result = run([task(), task("B", **{field: 3})], [section(), section("B", "b")])
    assert result.status.value == "partially_feasible"
    assert any("本学期完成" in u.message for u in result.unresolved)


def test_fixed_current_conflict_is_known_failure_without_automatic_repair():
    result = run(current=[section(), section("B", "b")])
    assert result.status.value == "infeasible"
    assert len(ids(result)) == 2 and result.changes == []


def test_required_current_alternative_can_make_joint_goal_possible():
    result = run([task(), task("B")], [section(class_id="alt", day=2), section("B", "b")], [section()])
    assert result.status.value == "partially_feasible"
    assert ids(result) == [("A", "a")]
    assert result.changes == []  # 不隐式换 A 后再加 B。


@pytest.mark.parametrize("status", ["satisfied", "possibly_equivalent", "manual_confirmation"])
def test_task_status_not_upgraded_to_required(status):
    record = task(status=status)
    result = run([record], [section()])
    assert ids(result) == [] and result.changes == []
    assert result.status.value == ("feasible" if status == "satisfied" else "partially_feasible")


def test_prerequisite_not_assumed_passed_even_when_satisfied_task_exists():
    satisfied = task("P", status="satisfied")
    result = run([task(prerequisites=["P"]), satisfied], [section()])
    assert result.status.value == "partially_feasible"
    assert any("先修" in u.message for u in result.unresolved)


@pytest.mark.parametrize("preference", [
    Preference(max_credit=0), Preference(max_credit=18), Preference(avoid_cross_campus=True),
    Preference(preferred_courses=["A"]), Preference(notes="周五必须空出来"),
    Preference(avoid_times=[dict(weekday=1, start_section=1, end_section=2)]),
])
def test_unconfirmed_preferences_do_not_filter_score_or_make_infeasible(preference):
    result = run([task()], [section()], preference=preference)
    assert result.status.value == "partially_feasible"
    assert ids(result) == [("A", "a")]
    assert types(result) == {"manual_confirmation"}


@pytest.mark.parametrize("capacity", [0, 1, 100])
def test_capacity_has_no_invented_threshold(capacity):
    result = run([task()], [section(remaining_capacity=capacity)])
    assert result.status.value == "partially_feasible"
    assert ids(result) == [("A", "a")]
    assert any("容量" in u.message for u in result.unresolved)


def test_unused_capacity_and_campus_metadata_does_not_downgrade():
    irrelevant = section("X", "x", remaining_capacity=0)
    irrelevant.meetings[0].campus = "Mock南"
    result = run([task()], [section(), irrelevant], [section()])
    assert result.status.value == "feasible"


def test_multiple_campuses_need_commute_confirmation():
    a, b = section(), section("B", "b", 2)
    a.meetings[0].campus, b.meetings[0].campus = "Mock东", "Mock南"
    result = run([task()], [a], [b])
    assert result.status.value == "partially_feasible"
    assert any("通勤" in u.message for u in result.unresolved)


@pytest.mark.parametrize("weeks", [[1, 3], [2, 4]])
def test_later_meeting_conflict_and_disjoint_weeks(weeks):
    a = section(day=2)
    a.meetings.append(Meeting(weekday=1, start_section=1, end_section=2, weeks=weeks))
    result = run([task()], [a], [section("B", "b")])
    assert result.status.value == "partially_feasible"
    assert ids(result) == ([("B", "b")] if weeks == [1, 3] else [("B", "b"), ("A", "a")])


def test_input_and_output_are_isolated_and_provider_has_no_session_state():
    tasks, offers, current, pref = [task()], [section()], [section("B", "b", 2)], Preference()
    args = dict(makeup_tasks=tasks, offerings=offers, current_schedule=current, preference=pref)
    before = deepcopy(args)
    provider = RestrictedPlannerProvider()
    first = provider.plan(**args)
    assert args == before
    first.selected_classes[0].class_id = "mutated"
    first.changes[0].reason = "mutated"
    assert args == before
    assert provider.plan(**args).selected_classes[0].class_id == "b"


@pytest.mark.parametrize("field", ["makeup_tasks", "offerings", "current_schedule"])
@pytest.mark.parametrize("bad", [None, {}, "bad", [None]])
def test_invalid_lists_are_errors_not_infeasible(field, bad):
    args = dict(makeup_tasks=[], offerings=[], current_schedule=[], preference=Preference())
    args[field] = bad
    with pytest.raises(TypeError):
        RestrictedPlannerProvider().plan(**args)


@pytest.mark.parametrize("bad", [None, {}, "bad"])
def test_invalid_preference_is_error(bad):
    with pytest.raises(TypeError):
        RestrictedPlannerProvider().plan(makeup_tasks=[], offerings=[], current_schedule=[], preference=bad)


@pytest.mark.parametrize("where", ["offerings", "current_schedule"])
def test_duplicate_identity_rejected(where):
    args = dict(makeup_tasks=[], offerings=[], current_schedule=[], preference=Preference())
    args[where] = [section(), section()]
    with pytest.raises(ValueError, match="重复"):
        RestrictedPlannerProvider().plan(**args)


def test_duplicate_task_rejected():
    with pytest.raises(ValueError, match="重复"):
        run([task(), task()])


def test_multiple_current_sections_same_course_requires_explicit_input():
    with pytest.raises(ValueError, match="多个"):
        run(current=[section(), section(class_id="second", day=2)])


@pytest.mark.parametrize("where", ["offerings", "current_schedule"])
def test_mixed_semester_is_error(where):
    changed = section("B", "b", 2)
    changed.semester = "2026-2"
    args = dict(makeup_tasks=[], offerings=[section()], current_schedule=[], preference=Preference())
    args[where] = [section(), changed]
    with pytest.raises(ValueError, match="学期"):
        RestrictedPlannerProvider().plan(**args)


@pytest.mark.parametrize("where", ["offerings", "current_schedule"])
def test_mutated_meeting_revalidated(where):
    invalid = section()
    invalid.meetings[0].weekday = 9
    args = dict(makeup_tasks=[], offerings=[], current_schedule=[], preference=Preference())
    args[where] = [invalid]
    with pytest.raises(ValidationError):
        RestrictedPlannerProvider().plan(**args)


@pytest.mark.parametrize("where", ["offerings", "current_schedule"])
def test_reversed_sections_rejected_even_with_unknown(where):
    invalid = section()
    # 公共模型允许正整数，采用 3->2 倒置以命中算法校验。
    invalid.meetings[0].start_section, invalid.meetings[0].end_section = 3, 2
    args = dict(makeup_tasks=[], offerings=[], current_schedule=[], preference=Preference())
    args[where] = [section("U", "u", unknown=True), invalid]
    with pytest.raises(ValueError, match="区间"):
        RestrictedPlannerProvider().plan(**args)


def test_reversed_preference_time_is_error():
    pref = Preference(avoid_times=[dict(weekday=1, start_section=3, end_section=2)])
    with pytest.raises(ValueError, match="倒置"):
        run(preference=pref)


@pytest.mark.parametrize("case", ["feasible", "partial", "infeasible", "unknown"])
def test_all_result_states_validate_against_unchanged_json_schema(case, load_schema):
    if case == "feasible":
        result = run([task()], current=[section()])
    elif case == "partial":
        result = run([task()], [section(), section(class_id="alt", day=2)])
    elif case == "unknown":
        result = run([task()], [section(unknown=True)])
    else:
        result = run(current=[section(), section("B", "b")])
    assert result.status.value == ({"partial": "partially_feasible", "unknown": "partially_feasible"}.get(case, case))
    Draft202012Validator(load_schema("plan_result.schema.json")).validate(result.model_dump(mode="json"))


def test_real_provider_can_be_injected_without_modifying_orchestrator():
    class Curriculum:
        def get_makeup_tasks(self):
            return [task()]

    class Data:
        def get_course_offerings(self, semester):
            assert semester == "2026-1"
            return [section()]

    class RecordingPlanner(RestrictedPlannerProvider):
        def plan(self, **kwargs):
            self.result = super().plan(**kwargs)
            return self.result

    provider = RecordingPlanner()
    result = PlanningOrchestrator(Curriculum(), Data(), provider).build_plan(
        semester="2026-1", current_schedule=[], preference=Preference())
    assert result is provider.result
    assert result.status.value == "partially_feasible"
    assert ids(result) == [("A", "a")]
    assert any("本学期" in item.message for item in result.unresolved)


@pytest.mark.parametrize("days", list(product([1, 2], repeat=4)))
def test_exhaustive_known_combination_proof_matches_independent_slot_oracle(days):
    # 独立 oracle：这组固定同周同节案例，两门课仅在 weekday 不同时可同时安排。
    domains = [[section(class_id="a1", day=days[0]), section(class_id="a2", day=days[1])],
               [section("B", "b1", days[2]), section("B", "b2", days[3])]]
    expected = any(a != b for a in days[:2] for b in days[2:])
    assert combination_state([], domains) is (ConflictState.CLEAR if expected else ConflictState.CONFLICT)


def test_unknown_combinations_and_missing_domains_are_not_known_unsat():
    assert combination_state([], [[section()], [section("B", "u", unknown=True)]]) is ConflictState.UNKNOWN
    assert combination_state([], [[]]) is ConflictState.UNKNOWN


@pytest.mark.parametrize("current_status", [None, "required", "satisfied", "manual_confirmation"])
@pytest.mark.parametrize("semester_fields", [{}, {"recommended_semester": 2}, {"deadline_semester": 3}])
def test_any_current_course_explicit_repair_path_prevents_false_infeasible(current_status, semester_fields):
    current = [section("B", "b"), section("C", "c")]
    offers = [section("B", "b-alt", 2), section(day=3)]
    tasks = [task()]
    if current_status is not None:
        tasks.append(task("B", status=current_status, **semester_fields))
    before = deepcopy(current)
    result = run(tasks, offers, current)
    assert result.status.value == "partially_feasible"
    assert ids(result) == [("B", "b"), ("C", "c")]
    assert result.changes == [] and current == before
    assert "selection_required" in types(result)
    # 用冻结阶段2实际执行行为独立验证该显式修复路径，Provider 不代为执行。
    repaired = repair_target_section(
        course_id="B", current_class_id="b", semester="2026-1", offerings=offers,
        current_schedule=current, replacement_class_id="b-alt",
    )
    assert repaired.outcome.value == "replaced"
    assert [(s.course_id, s.class_id) for s in repaired.new_schedule] == [("B", "b-alt"), ("C", "c")]
    after = run([task()], offers, list(repaired.new_schedule))
    assert ids(after) == [("B", "b-alt"), ("C", "c"), ("A", "a")]
    assert [(change.course_id, change.from_class) for change in after.changes] == [("A", None)]


@pytest.mark.parametrize("semester_fields", [
    {}, {"deadline_semester": None}, {"recommended_semester": None},
    {"deadline_semester": None, "recommended_semester": None},
])
def test_missing_semester_fields_never_prove_new_goal_due_this_term(semester_fields):
    record = task(**semester_fields)
    blocked = run([record], [section()], [section("B", "b")])
    assert blocked.status.value == "partially_feasible"
    assert ids(blocked) == [("B", "b")] and blocked.changes == []
    assert any("是否必须本学期完成未知" in item.message for item in blocked.unresolved)
    assert not any("完整目标无解" in item.message for item in blocked.unresolved)
    suggested = run([record], [section()], [section("B", "b", 2)])
    assert suggested.status.value == "partially_feasible"
    assert ids(suggested) == [("B", "b"), ("A", "a")]
    assert any("本学期必达" in item.message for item in suggested.unresolved)


@pytest.mark.parametrize("related", [True, False])
@pytest.mark.parametrize("uncertain_selected", [False, True])
def test_related_unknown_escape_vs_unrelated_unknown_independent_proof(related, uncertain_selected):
    current = [section(), section("B", "b"), section("U", "u", unknown=True)]
    offers = [section("A" if related else "U", "unknown-alt", unknown=True)]
    tasks = [task("U", recommended_semester=2)] if uncertain_selected else []
    result = run(tasks, offers, current)
    assert result.status.value == ("partially_feasible" if related else "infeasible")
    assert "schedule_unknown" in types(result)
    assert ids(result) == [("A", "a"), ("B", "b"), ("U", "u")]
    assert result.changes == []
    assert any("完整目标无解" in item.message for item in result.unresolved) is (not related)


@pytest.mark.parametrize("days", list(product([1, 2, None], repeat=4)))
def test_unknown_prefix_search_matches_independent_exhaustive_oracle(days):
    domains = [[section("A", f"a{i}", day or 1, unknown=day is None) for i, day in enumerate(days[:2])],
               [section("B", f"b{i}", day or 1, unknown=day is None) for i, day in enumerate(days[2:])]]
    # 独立按时段计算：两已知同天为冲突，含 None 是未知，已知异天为 CLEAR。
    states = [ConflictState.UNKNOWN if a is None or b is None else
              ConflictState.CLEAR if a != b else ConflictState.CONFLICT
              for a, b in product(days[:2], days[2:])]
    expected = (ConflictState.CLEAR if ConflictState.CLEAR in states else
                ConflictState.UNKNOWN if ConflictState.UNKNOWN in states else ConflictState.CONFLICT)
    assert combination_state([], domains) is expected
    assert combination_state([], list(reversed(domains))) is expected


def test_incremental_prefix_prunes_billions_of_conflicting_suffixes(monkeypatch):
    import app.planner.feasibility as feasibility

    domains = [[section(str(i), f"{i}-{j}") for j in range(2)] for i in range(36)]
    calls = []
    original = feasibility.check_conflict

    def counted(left, right):
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(feasibility, "check_conflict", counted)
    assert combination_state([], domains) is ConflictState.CONFLICT
    # 2**36 完整组合不能遍历；任意前两个班冲突，全部后缀必须被跳过。
    assert len(calls) == 4


def test_pair_cache_reuses_checks_across_prefixes_and_unknown_search(monkeypatch):
    import app.planner.feasibility as feasibility

    fixed = [section("F", "f", 3)]
    domains = [[section("A", "a1"), section("A", "a2", 2)],
               [section("B", "b1"), section("B", "b2", 2)],
               [section("C", "c1"), section("C", "c2", 2), section("C", "cu", unknown=True)]]
    seen = set()
    original = feasibility.check_conflict

    def counted(left, right):
        key = tuple(sorted((id(left), id(right))))
        assert key not in seen, "同次证明不得重复计算同一对 Section"
        seen.add(key)
        return original(left, right)

    monkeypatch.setattr(feasibility, "check_conflict", counted)
    assert combination_state(fixed, domains) is ConflictState.UNKNOWN
    assert seen


@pytest.mark.parametrize("unrelated_unknown", [False, True])
def test_fixed_precheck_independent_conflict_skips_candidate_search(monkeypatch, unrelated_unknown):
    import app.planner.feasibility as feasibility

    fixed = [section(), section("B", "b")]
    if unrelated_unknown:
        fixed.insert(0, section("U", "u", unknown=True))
    original = feasibility.check_conflict

    def checked(left, right):
        assert left.course_id != "C" and right.course_id != "C"
        return original(left, right)

    monkeypatch.setattr(feasibility, "check_conflict", checked)
    assert combination_state(fixed, [[section("C", "c1"), section("C", "cu", unknown=True)]]) is ConflictState.CONFLICT


def test_fixed_schedule_excludes_whole_domain_despite_unrelated_unknown():
    fixed = [section("F", "f"), section("U", "u", unknown=True)]
    assert combination_state(fixed, [[section(), section(class_id="a2")]]) is ConflictState.CONFLICT
    assert combination_state(fixed, [[section(), section(class_id="au", unknown=True)]]) is ConflictState.UNKNOWN


def test_large_all_unknown_domains_find_possible_combination_without_exhausting_product():
    domains = [[section(str(i), f"{i}-{j}", unknown=True) for j in range(2)] for i in range(36)]
    assert combination_state([], domains) is ConflictState.UNKNOWN


def test_search_detection_failure_is_error_never_unsat_certificate(monkeypatch):
    import app.planner.feasibility as feasibility

    def fail(left, right):
        raise RuntimeError("搜索未完成")

    monkeypatch.setattr(feasibility, "check_conflict", fail)
    with pytest.raises(RuntimeError, match="未完成"):
        run(current=[section(), section("B", "b")])
