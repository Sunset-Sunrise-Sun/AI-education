"""仅证明时间组合是否存在，不返回选班或优化结果。"""

from collections.abc import Sequence

from app.models.contracts import CourseOffering
from app.planner.conflicts import ConflictState, check_conflict


def schedule_state(schedule: Sequence[CourseOffering]) -> ConflictState:
    """整张课表认证；单独一个空 meetings 班同样为 UNKNOWN。"""
    result = ConflictState.CLEAR
    for index, offering in enumerate(schedule):
        if not offering.meetings:
            result = ConflictState.UNKNOWN
        for other in schedule[index + 1:]:
            state = check_conflict(offering, other)
            if state is ConflictState.CONFLICT:
                return state
            if state is ConflictState.UNKNOWN:
                result = state
    return result


def combination_state(
    fixed: Sequence[CourseOffering],
    domains: Sequence[Sequence[CourseOffering]],
) -> ConflictState:
    """穷尽域的存在性检查，UNKNOWN 作为可能解保留。

    CLEAR：至少一个时间已知的完整组合存在（不授权选择它）。
    UNKNOWN：没有认证组合，但有未被已知冲突排除的未知组合。
    CONFLICT：所有组合都被已知冲突排除；调用方仍需确认目标/域完整性。
    空域不构成无解证据，缺供给信息由 Provider 单独报告。
    """
    # 缓存限于本次调用，以对象身份区分同班号但不同来源的时间事实。
    # 保持输入对象引用直到搜索结束，避免身份重用或跨调用过期缓存。
    cache: dict[tuple[int, int], ConflictState] = {}

    def pair(left: CourseOffering, right: CourseOffering) -> ConflictState:
        key = tuple(sorted((id(left), id(right))))
        if key not in cache:
            cache[key] = check_conflict(left, right)
        return cache[key]

    fixed_unknown = any(not item.meetings for item in fixed)
    for index, item in enumerate(fixed):
        for other in fixed[index + 1:]:
            if pair(item, other) is ConflictState.CONFLICT:
                return ConflictState.CONFLICT  # 独立证明，不被无关 UNKNOWN 抹除。
    if any(not domain for domain in domains):
        return ConflictState.UNKNOWN

    prepared: list[list[tuple[CourseOffering, bool]]] = []
    for domain in domains:
        candidates = []
        for item in domain:
            unknown = not item.meetings
            for other in fixed:
                state = pair(item, other)
                if state is ConflictState.CONFLICT:
                    break
                unknown |= state is ConflictState.UNKNOWN
            else:
                candidates.append((item, unknown))
        if not candidates:
            return ConflictState.CONFLICT  # 固定课表排除了该目标的全部候选。
        prepared.append(candidates)

    def exists(allow_unknown: bool) -> bool:
        choices = [
            [item for item, unknown in domain if allow_unknown or not unknown]
            for domain in prepared
        ]
        if any(not domain for domain in choices):
            return False
        # 仅搜索顺序优化；不输出见证、不定义优先级、不据此自动选班。
        choices.sort(key=len)
        if not choices:
            return True
        prefix: list[CourseOffering] = []
        frames = [iter(choices[0])]
        # 显式栈避免任务数量较多时触发 Python 递归深度限制。
        while frames:
            try:
                candidate = next(frames[-1])
            except StopIteration:
                frames.pop()
                if prefix:
                    prefix.pop()
                continue
            for other in prefix:
                state = pair(candidate, other)
                if state is ConflictState.CONFLICT or (
                    state is ConflictState.UNKNOWN and not allow_unknown
                ):
                    break
            else:
                prefix.append(candidate)
                if len(prefix) == len(choices):
                    return True
                frames.append(iter(choices[len(prefix)]))
        return False

    # 先找已认证组合，再找未被已知冲突排除的可能组合。
    # 第二遍允许 UNKNOWN 作为可能性，绝不将其认证为 CLEAR。
    if not fixed_unknown and exists(allow_unknown=False):
        return ConflictState.CLEAR
    if exists(allow_unknown=True):
        return ConflictState.UNKNOWN
    # 无超时/节点数截断，只有完整排除全部可能组合才能返回 CONFLICT。
    # 若检测异常/搜索被中断则异常向上传播，不能转成无解证据。
    return ConflictState.CONFLICT
