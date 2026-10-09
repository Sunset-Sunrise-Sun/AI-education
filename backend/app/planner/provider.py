"""冻结四参数接口的受限 Planner；无网络、排名或自动替换。

2026-10-05 负责人裁决：selected_classes 是完整本学期建议课表；
新增 required 仅唯一 CLEAR 可加入，已有班替换仍需显式选择。
selection_required 为本次确认的输出约定，不是旧 Schema 枚举。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from app.models.contracts import (
    Change, CourseOffering, MakeupStatus, MakeupTask, PlanResult,
    PlanStatus, Preference, SelectedClass, Unresolved,
)
from app.planner.conflicts import ConflictState, check_conflict, check_schedule_conflict
from app.planner.credit_limit import (
    CREDIT_STATE_OVER_LIMIT,
    CREDIT_STATE_UNVERIFIABLE,
    credit_ledger,
    credit_state as credit_state_for,
    task_credit_map,
)
from app.planner.feasibility import combination_state, schedule_state
from app.planner.section_repair import find_alternative_sections


ModelT = TypeVar("ModelT", bound=BaseModel)


def _copy_models(values: list[ModelT], model: type[ModelT], name: str) -> list[ModelT]:
    if not isinstance(values, list):
        raise TypeError(f"{name} 必须是列表。")
    copied = []
    for value in values:
        if not isinstance(value, model):
            raise TypeError(f"{name} 中的对象类型非法。")
        copied.append(model.model_validate(value.model_dump()))
    return copied


def _key(offering: CourseOffering) -> tuple[str, str, str]:
    return offering.semester, offering.course_id, offering.class_id


def _validate_offerings(values: list[CourseOffering], name: str) -> None:
    keys = [_key(item) for item in values]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{name} 存在重复教学班身份。")
    for item in values:
        check_schedule_conflict(item, [])


class RestrictedPlannerProvider:
    """仅执行已确认时间规则；非时间语义未确认时显式待确认。"""

    def plan(
        self,
        *,
        makeup_tasks: list[MakeupTask],
        offerings: list[CourseOffering],
        current_schedule: list[CourseOffering],
        preference: Preference,
    ) -> PlanResult:
        tasks = _copy_models(makeup_tasks, MakeupTask, "makeup_tasks")
        available = _copy_models(offerings, CourseOffering, "offerings")
        current = _copy_models(current_schedule, CourseOffering, "current_schedule")
        if not isinstance(preference, Preference):
            raise TypeError("preference 必须是 Preference。")
        pref = Preference.model_validate(preference.model_dump())
        for block in pref.avoid_times:
            if block.end_section < block.start_section:
                raise ValueError("avoid_times 节次区间倒置。")
        _validate_offerings(available, "offerings")
        _validate_offerings(current, "current_schedule")
        if len({task.course_id for task in tasks}) != len(tasks):
            raise ValueError("makeup_tasks 存在重复 course_id。")
        semesters = {item.semester for item in [*available, *current]}
        if len(semesters) > 1:
            raise ValueError("单学期 Planner 输入不能混合学期。")
        if len({item.course_id for item in current}) != len(current):
            raise ValueError("current_schedule 同一课程存在多个已选班，需先明确输入。")

        unresolved: list[Unresolved] = []

        def issue(kind: str, message: str) -> None:
            item = Unresolved(type=kind, message=message)
            if item not in unresolved:
                unresolved.append(item)

        required = sorted(
            (task for task in tasks if task.status is MakeupStatus.REQUIRED),
            key=lambda task: task.course_id,
        )  # 仅稳定报告/枚举顺序，不是学业优先级；不按此顺序分配班。
        originals = {item.course_id: item for item in current}
        additions: list[CourseOffering] = []
        for item in current:
            if not item.meetings:
                issue("schedule_unknown", self._unknown_message(item))
            # 所有当前班都有相同的显式修复资格，不按 required 区分。
            search = find_alternative_sections(
                course_id=item.course_id, current_class_id=item.class_id,
                semester=item.semester, offerings=available, current_schedule=current,
            )
            if search.original_state is not ConflictState.CLEAR:
                if search.clear_candidates:
                    issue("selection_required", f"课程 {item.course_id} 已有 CLEAR 替代班 {', '.join(alt.class_id for alt in search.clear_candidates)}，仍需调用方明确选择；本次保留原班，不执行替换。")
                elif search.unknown_candidates:
                    issue("schedule_unknown", f"课程 {item.course_id} 的替代班无法完成完整时间冲突确认，需要人工核验。")

        for task in tasks:
            if task.status in (MakeupStatus.POSSIBLY_EQUIVALENT, MakeupStatus.MANUAL_CONFIRMATION):
                issue("manual_confirmation", f"课程 {task.course_id} 的补修认定仍需人工确认，不自动新增。")

        for task in required:
            cid = task.course_id
            original = originals.get(cid)
            candidates = sorted(
                (item for item in available if item.course_id == cid),
                key=lambda item: item.class_id,
            )
            if task.prerequisites:
                issue("manual_confirmation", f"课程 {cid} 的权威先修边为 {', '.join(task.prerequisites)}；当前接口未提供已修通过/并修许可的完整证据，先修满足情况待确认。")
            if task.deadline_semester is not None or task.recommended_semester is not None:
                issue("manual_confirmation", f"课程 {cid} 的推荐/截止学期为学生相对学期编号；与本次学期的映射及是否必须本学期完成待确认。")
            elif original is None:
                issue("manual_confirmation", f"课程 {cid} 缺失推荐/截止学期；是否必须本学期完成未知，不作为本学期必达目标的无解证据。")
            if original is not None:
                continue

            if not candidates:
                issue("missing_data", f"课程 {cid} 在本次输入中没有候选教学班；供给完整性/开课情况待核验，不推断学校未开课。")
                continue
            assessments = [(item, check_schedule_conflict(item, current)) for item in candidates]
            clear = [item for item, state in assessments if state is ConflictState.CLEAR]
            if len(clear) == 1:
                additions.append(clear[0])
            elif len(clear) > 1:
                issue("selection_required", f"课程 {cid} 存在多个 CLEAR 候选 {', '.join(item.class_id for item in clear)}，需明确选择，本次不自动加入。")
            elif any(state is ConflictState.UNKNOWN for _, state in assessments):
                issue("schedule_unknown", f"课程 {cid} 的候选或当前课表在当前来源快照中没有可用排课信息，无法完成完整时间冲突确认，需要人工核验。")
            else:
                issue("manual_confirmation", f"课程 {cid} 的候选与当前课表存在已知时间冲突；需结合完整候选组合判定，不自动调整当前班。")

        # 联合失败的班全部暂不加入，绝不按任务顺序牺牲另一 required。
        colliding: set[str] = set()
        for index, item in enumerate(additions):
            for other in additions[index + 1:]:
                if check_conflict(item, other) is ConflictState.CONFLICT:
                    colliding.update((item.course_id, other.course_id))
        if colliding:
            issue("manual_confirmation", f"新增任务 {', '.join(sorted(colliding))} 的唯一 CLEAR 班彼此冲突，不能同时加入；不自动选择牺牲任何任务。")
        proposed = [item for item in additions if item.course_id not in colliding]
        if schedule_state(current) is ConflictState.CONFLICT:
            issue("manual_confirmation", "当前课表含已知时间冲突，仍保留当前选择事实；未认证为可执行课表。")
            proposed = []
        # 学分上限（学生本人显式声明的 `Preference.max_credit`）：
        # 新增彼此不冲突 ≠ 本次建议仍符合学生自己声明的上限。
        # 只校验**原课表 + 累计新增**这一整集合；⛔ 不排序、⛔ 不挑选牺牲哪一门。
        proposed = self._apply_credit_limit(current, proposed, tasks, pref, issue)
        selected = [*current, *proposed]

        # 四参数契约没有本次学期与相对学期的映射；required != 本学期必达。
        # 仅当前已选课程的保留目标确定，新增建议不能反向变为必达证据。
        # 无解证明采用保守放宽：每个当前课程均保留原班及全部同课同学期
        # 输入候选，包括当前尚不满足显式 repair 条件的候选/UNKNOWN。
        # 这覆盖阶段2仍允许的修复可能，放宽域也无解才证明实际允许域无解；
        # 找到放宽域组合不代表它可执行，绝不授权连锁换班或自动 repair。
        fixed: list[CourseOffering] = []
        repair_domains: list[list[CourseOffering]] = []
        for original in current:
            domain = [original, *[
                item for item in available
                if item.course_id == original.course_id
                and item.semester == original.semester and _key(item) != _key(original)
            ]]
            if len(domain) == 1:
                fixed.append(original)
            else:
                repair_domains.append(domain)
        proof = combination_state(fixed, repair_domains)
        proven_impossible = proof is ConflictState.CONFLICT
        if proven_impossible:
            issue("manual_confirmation", "当前已选课程的全部原班/同课同学期输入候选组合（含 UNKNOWN 可能组合）已被已知时间冲突排除；即使放宽至全部这些候选，也无法同时保留当前课程，因此本次完整目标无解。证明仅限本次输入及保留课程范围，不推断学校全部供给。")

        self._pending_non_time(selected, pref, issue)
        if proven_impossible:
            status = PlanStatus.INFEASIBLE
        elif unresolved or schedule_state(selected) is not ConflictState.CLEAR:
            status = PlanStatus.PARTIALLY_FEASIBLE
        else:
            status = PlanStatus.FEASIBLE
        changes = [Change(
            course_id=item.course_id, from_class=None, to_class=item.class_id,
            reason="新增 required 任务仅有一个与当前课表及本次其他新增班确认无时间冲突的 CLEAR 教学班，加入建议课表；不执行学校选课。",
        ) for item in proposed]
        sources = "/".join(sorted({item.data_source.value for item in [*available, *current]})) or "无教学班输入"
        return PlanResult(
            status=status,
            selected_classes=[SelectedClass(course_id=item.course_id, class_id=item.class_id) for item in selected],
            changes=changes, risks=[], unresolved=unresolved,
            objective_summary=(
                f"受限 Planner 本学期建议课表：保留 {len(current)} 个当前班，建议新增 {len(proposed)} 个班。"
                f"输入教学班数据标记：{sources}。"
                "执行确定性时间认证；非时间规则仅在已有明确执行语义时认证，待确认项见 unresolved。"
                "不自动替换、不自动选多个 CLEAR、不执行学校选课；不代表完整 Planner MVP 已交付。"
            ),
        )

    @staticmethod
    def _apply_credit_limit(
        current: list[CourseOffering],
        proposed: list[CourseOffering],
        tasks: list[MakeupTask],
        pref: Preference,
        issue: Callable[[str, str], None],
    ) -> list[CourseOffering]:
        """把学生自己声明的学分上限变成对候选集合的确定性接纳判断。

        - 已声明学分合计**可证明超限** → 本次不加入任何新增（⛔ 不排序、⛔ 不牺牲某门）；
        - 有课程没有声明学分 → 上限是否满足**无法证明**，明确要求人工核验，
          并且**不**把新增当成"已通过学分校验"；
        - 原课表本身已超限 → 只提示，⛔ 不篡改学生已选事实。

        ⛔ 本函数不发明上限、⛔ 不折算学分、⛔ 不改变任何冲突判定或学业优先级。
        """

        if pref.max_credit is None:
            return proposed
        credits = task_credit_map(tasks)
        ledger = credit_ledger([*current, *proposed], task_credits=credits)
        state = credit_state_for(pref, ledger)
        current_ledger = credit_ledger(current, task_credits=credits)
        original_over_limit = (
            current_ledger.complete and current_ledger.declared_total > pref.max_credit
        )
        if state is CREDIT_STATE_OVER_LIMIT:
            if original_over_limit and not proposed:
                # 超限**完全来自学生已选的课表**：只提示，⛔ 不篡改已选事实。
                issue(
                    "manual_confirmation",
                    f"当前课表已声明学分合计 {current_ledger.declared_total:g} 本身已超过"
                    f"学生声明的学分上限 {pref.max_credit:g}；保留当前选择事实，"
                    "不自动删除或替换任何当前班，也不据此判定本次建议不可执行。",
                )
                return proposed
            issue(
                "manual_confirmation",
                f"本次建议课表（原课表 {len(current)} 个班 + 新增 {len(proposed)} 个班）"
                f"已声明学分合计 {ledger.declared_total:g} 超过学生声明的学分上限 "
                f"{pref.max_credit:g}；本次不自动加入新增，也不折算或删除任何课程。",
            )
            return []
        if state is CREDIT_STATE_UNVERIFIABLE:
            issue(
                "manual_confirmation",
                "本次建议课表中有教学班没有声明学分（"
                + "、".join(sorted(ledger.unknown_course_ids))
                + "），因此是否超过学生声明的学分上限无法证明，需要人工核验；"
                "本次仍列出已确认无时间冲突的唯一 CLEAR 新增，但不认证其学分合规性。",
            )
        if original_over_limit:
            issue(
                "manual_confirmation",
                f"当前课表已声明学分合计 {current_ledger.declared_total:g} 本身已超过"
                f"学生声明的学分上限 {pref.max_credit:g}；保留当前选择事实，"
                "不自动删除或替换任何当前班。",
            )
        else:
            # 已校验通过时也**逐字回报本次真正使用的输入**：
            # 这样"Planner 收到了调用方真实的 max_credit，而不是悄悄丢弃 / 改写"
            # 这件事是可复核的，而不是只靠"没有报错"。
            issue(
                "manual_confirmation",
                f"本次建议课表已声明学分合计 {ledger.declared_total:g} 未超过"
                f"学生声明的学分上限 {pref.max_credit:g}；学分上限仅用于本次接纳判断，"
                "不改变任何学业优先级、必修要求或学校规则。",
            )
        return proposed

    @staticmethod
    def _unknown_message(item: CourseOffering) -> str:
        return f"当前班 {item.course_id}/{item.class_id} 在当前来源快照中没有可用排课信息，无法完成完整时间冲突确认，需要人工核验；保留当前选择不代表 CLEAR。"

    @staticmethod
    def _pending_non_time(
        selected: list[CourseOffering], preference: Preference,
        issue: Callable[[str, str], None],
    ) -> None:
        # `max_credit` 由 `_apply_credit_limit` 单独处理（见上），这里不重复报告：
        # 它已经从"语义未确认"变成一次显式的确定性接纳判断。
        active = [
            name for name, value in preference.model_dump().items()
            if name != "max_credit" and value is not None and value is not False
            and value != [] and value != ""
        ]
        if active:
            issue("manual_confirmation", f"Preference 字段 {', '.join(active)} 的硬/软分类或执行口径尚未完整确认；不据此筛班、评分或证明无解，影响可执行性/需求满足情况待确认。")
        # 不把供给里的未用班状态带入方案，也不把容量字段默认升级为硬规则。
        if any(item.capacity is not None or item.remaining_capacity is not None for item in selected):
            issue("manual_confirmation", "建议课表包含容量信息；容量快照、已有选课与新增选课的处理规则尚未确认，不能认证学校实际可选性，不自动过滤。")
        campuses = {meeting.campus for item in selected for meeting in item.meetings if meeting.campus}
        if len(campuses) > 1:
            issue("manual_confirmation", "建议课表涉及多个校区；最小通勤时间及执行规则待确认，不能仅凭时间无重叠认证跨校区可执行性。")
