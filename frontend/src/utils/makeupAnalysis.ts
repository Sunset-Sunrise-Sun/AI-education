/**
 * **补修分析视图模型**：把后端**真实的** `MakeupTask[]` 映射成页面三状态。
 *
 * ⚠️ 本模块是 `caseAStudyPlan.ts` 的**替代真源**。
 *   旧配置层在前端自造培养方案与匹配结果（前端 config 里的课程号/学分与学校
 *   真实培养方案并不一致），已降级为「离线演示回退」，⛔ 不再参与真实匹配。
 *
 * ## 数据来源
 *
 * ```text
 * POST /api/v1/case-a-demo/plan
 *   └── makeup_tasks[]  （后端已完成的真实匹配结果）
 *         course_id / course_name / credit
 *         status          ← 后端判定，前端⛔ 不重新判定
 *         reason          ← 后端生成的「为什么」+ 不确定性分类
 *         source_evidence ← 后端生成的可审计依据
 * ```
 *
 * ## 硬边界
 *
 * - ⛔ 不在前端判定课程等价、⛔ 不重新计算缺口、⛔ 不伪造课程；
 * - ⛔ 不把 `satisfied` 说成"系统自动认定"，因为本样本里它只来自**学生自己确认**；
 * - `MakeupTask` 公共 Schema 没有"是否实际开课"字段，因此教学状态只能由
 *   `/case-a-demo/offerings` 的课程号在本学期是否出现来推断，
 *   并**如实**标注它是前端推断而非后端结论。
 */

import type { MakeupTask } from '../types/contracts'

/** 页面三状态（与后端 `MakeupStatus` 的映射关系见 `toViewStatus`）。 */
export type ViewStatus =
  /** 培养要求已满足 → ⛔ 不进补修、⛔ 不进推荐。 */
  | 'satisfied'
  /** 成绩单存在记录，但等价关系需人工确认。 */
  | 'need_confirmation'
  /** 培养方案要求，成绩单未发现对应记录。 */
  | 'missing'

/** 不确定性分类（与后端 `matching.py` 的 `UNCERTAINTY_*` 常量一致）。 */
export type UncertaintyCode =
  | 'course_id_missing'
  | 'name_mismatch'
  | 'credit_mismatch'
  | 'manual_rule_required'

/** 分类的中文说明；⛔ 仅展示用。 */
export const UNCERTAINTY_LABEL: Readonly<Record<UncertaintyCode, string>> = {
  course_id_missing: '成绩单未包含官方课程号',
  name_mismatch: '课程名称与培养方案不一致',
  credit_mismatch: '学分与培养方案要求不一致',
  manual_rule_required: '需要人工确认课程完成情况',
}

/**
 * 后端 `MakeupStatus` → 页面三状态。
 *
 * ⚠️ 这是**唯一**的映射位置。⛔ 组件内不得再写状态判断分支。
 *
 * ```text
 * satisfied            -> satisfied           已满足
 * possibly_equivalent  -> need_confirmation   名称候选，等价关系待确认
 * manual_confirmation  -> need_confirmation   成绩单有记录/信息不足，需人工确认
 * required             -> missing             明确的培养缺口
 * ```
 */
export function toViewStatus(status: MakeupTask['status']): ViewStatus {
  switch (status) {
    case 'satisfied':
      return 'satisfied'
    case 'possibly_equivalent':
    case 'manual_confirmation':
      return 'need_confirmation'
    case 'required':
      return 'missing'
    default:
      // ⚠️ 后端新增取值时**不得**猜测其含义：按"最需要用户注意"的一类展示。
      return 'need_confirmation'
  }
}

/** 一条补修分析条目（由一条真实 `MakeupTask` 派生）。 */
export interface MakeupAnalysisItem {
  readonly courseId: string
  readonly courseName: string
  readonly credit: number
  /** 页面三状态。 */
  readonly status: ViewStatus
  /** 后端原始 `MakeupTask.status`，便于追溯。 */
  readonly sourceStatus: MakeupTask['status']
  /** 后端给出的「为什么」。 */
  readonly reason: string
  /** 后端给出的可审计依据（含成绩单行号与培养方案行号）。 */
  readonly sourceEvidence: string
  /** 从 reason 中解析出的不确定性分类；解析不到为 `null`。 */
  readonly uncertainty: UncertaintyCode | null
  /**
   * 本学期是否有教学班。
   *
   * ⚠️ 这是**前端由教学班数据推断**（按课程号是否存在），
   *   ⛔ 不是后端结论；公共 `MakeupTask` 没有开课字段。
   */
  readonly openedThisSemester: boolean
  /** 学生是否已确认该课程的等价转换（本地确认态）。 */
  readonly studentConfirmed: boolean
}

/** 从后端 reason 中解析「原因分类：<code>」。解析不到返回 `null`。 */
export function parseUncertainty(reason: string): UncertaintyCode | null {
  const matched = /原因分类：([a-z_]+)/.exec(reason ?? '')
  if (!matched) return null
  const code = matched[1] as UncertaintyCode
  return code in UNCERTAINTY_LABEL ? code : null
}

/**
 * 由真实 `makeup_tasks` 构造补修分析条目。
 *
 * @param tasks      后端真实返回的补修任务
 * @param offeredCourseIds 本学期**真实**教学班中出现过的课程号
 * @param confirmedCourseIds 学生在本页面上已确认可转换的课程号（本地状态）
 */
export function toMakeupAnalysis(
  tasks: readonly MakeupTask[],
  offeredCourseIds: ReadonlySet<string>,
  confirmedCourseIds: readonly string[] = [],
): MakeupAnalysisItem[] {
  const confirmed = new Set(confirmedCourseIds)
  return tasks.map((task) => {
    const studentConfirmed = confirmed.has(task.course_id)
    return {
      courseId: task.course_id,
      courseName: task.course_name,
      credit: task.credit,
      // ⚠️ 学生确认后视为已满足 —— 这是**学生本人的确认**，⛔ 不是系统自动认定。
      status: studentConfirmed ? 'satisfied' : toViewStatus(task.status),
      sourceStatus: task.status,
      reason: task.reason ?? '',
      sourceEvidence: task.source_evidence ?? '',
      uncertainty: parseUncertainty(task.reason ?? ''),
      openedThisSemester: offeredCourseIds.has(task.course_id),
      studentConfirmed,
    }
  })
}

/** 按三状态分组（保持后端返回顺序）。 */
export function groupByStatus(items: readonly MakeupAnalysisItem[]): {
  satisfied: MakeupAnalysisItem[]
  needConfirmation: MakeupAnalysisItem[]
  missing: MakeupAnalysisItem[]
} {
  return {
    satisfied: items.filter((item) => item.status === 'satisfied'),
    needConfirmation: items.filter((item) => item.status === 'need_confirmation'),
    missing: items.filter((item) => item.status === 'missing'),
  }
}

/**
 * **必须补修**的课程号集合 —— 推荐的第一来源。
 *
 * ⚠️ 只有 `missing` 才进这里：`need_confirmation` 在用户确认前**不是**缺口，
 *   `satisfied` 更不是。⛔ 不从 `makeup_tasks` 的其它取值里凑数。
 */
export function missingCourseIds(items: readonly MakeupAnalysisItem[]): string[] {
  return items.filter((item) => item.status === 'missing').map((item) => item.courseId)
}

/** 三状态的展示文案。 */
export const VIEW_STATUS_LABEL: Readonly<Record<ViewStatus, string>> = {
  satisfied: '已满足',
  need_confirmation: '待确认',
  missing: '缺失',
}

/** 三状态的含义说明（告诉学生这一步在回答什么）。 */
export const VIEW_STATUS_HINT: Readonly<Record<ViewStatus, string>> = {
  satisfied: '该培养要求已满足，不会进入补修，也不会被推荐。',
  need_confirmation: '成绩单中存在相关记录，但无法自动确认能否抵扣，需要你确认。',
  missing: '培养方案要求该课程，成绩单中未发现对应记录，转专业后需要补修。',
}
