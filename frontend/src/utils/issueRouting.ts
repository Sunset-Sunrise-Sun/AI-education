/**
 * 议题归属（issue ownership）视图模型。
 *
 * 产品最终形态**没有**独立的「需要你处理」区块：每个议题都必须落到它所属的
 * 产品区块里，⛔ 不允许静默消失。
 *
 * 归属规则（与独立 Review 的结论一致）：
 *
 * ```text
 * 认定 / 补修 / 可能等同      -> 补修缺口分析
 * 选修成员 / 选修选择 / 未知   -> 本学期专业选修建议
 * 冲突 / 换班 / 容量 / 排课    -> 本学期推荐课表
 * 未来排课 / 预算 / 未决       -> 未来学期修读路径
 * 依据 / 技术细节             -> 详细依据
 * ```
 *
 * ⚠️ 归不到区块的议题**不会**被丢掉：它们进入 `detailedEvidence`（详细依据，
 *    默认折叠），保证"宁可重复显示，也不静默丢失"。
 */

import type { IssueKind, NormalizedIssue } from './studentIssues'

/** 议题所属的产品区块。 */
export type IssueOwner =
  | 'makeup' // 补修缺口分析
  | 'elective' // 本学期专业选修建议
  | 'timetable' // 本学期推荐课表
  | 'roadmap' // 未来学期修读路径
  | 'detailedEvidence' // 详细依据（兜底 + 技术细节）

const KIND_OWNER: Record<IssueKind, IssueOwner> = {
  makeup_confirmation: 'makeup',
  binding_provenance: 'makeup',
  elective_selection: 'elective',
  repair_choice: 'timetable',
  selection_required: 'timetable',
  schedule_unknown: 'timetable',
  all_conflict: 'timetable',
  no_alternatives: 'timetable',
  // 未来学期相关（`other` 里的路线图说明）默认进未来路径；
  // 若其文本明显属于其它区块，`ownerFor` 会再修正。
  other: 'roadmap',
}

/** 关键词修正：`other` 类议题可能其实属于别的区块。 */
function refineOwner(issue: NormalizedIssue, fallback: IssueOwner): IssueOwner {
  const text = `${issue.message} ${issue.rawMessage ?? ''}`
  if (/先修|培养方案课程中|学分预算|顺延/.test(text)) return 'roadmap'
  if (/选修/.test(text)) return 'elective'
  if (/排课信息|冲突|换班|容量/.test(text)) return 'timetable'
  if (/补修|认定|证据不足/.test(text)) return 'makeup'
  return fallback
}

export function ownerFor(issue: NormalizedIssue): IssueOwner {
  const base = KIND_OWNER[issue.kind] ?? 'detailedEvidence'
  if (issue.kind === 'other') return refineOwner(issue, base)
  return base
}

export interface RoutedIssues {
  makeup: NormalizedIssue[]
  elective: NormalizedIssue[]
  timetable: NormalizedIssue[]
  roadmap: NormalizedIssue[]
  detailedEvidence: NormalizedIssue[]
}

/**
 * 把归一化议题分配到所属区块。
 *
 * ⚠️ **不丢失保证**：返回的五个数组长度之和 === 输入长度。
 *    这一条由单元测试锁定（每个议题至少被渲染一次）。
 */
export function routeIssues(issues: readonly NormalizedIssue[]): RoutedIssues {
  const routed: RoutedIssues = {
    makeup: [],
    elective: [],
    timetable: [],
    roadmap: [],
    detailedEvidence: [],
  }
  for (const issue of issues) {
    routed[ownerFor(issue)].push(issue)
  }
  return routed
}

/** 供应区块渲染的就绪条目（已确保每条都属于该区块）。 */
export function issuesForOwner(
  issues: readonly NormalizedIssue[],
  owner: IssueOwner,
): NormalizedIssue[] {
  return routeIssues(issues)[owner]
}

/**
 * 归属不变式：所有议题都必须被**恰好**归属一次。
 *
 * 返回未被归属的议题 id（正常应为空数组）。
 */
export function unownedIssueIds(issues: readonly NormalizedIssue[]): string[] {
  const routed = routeIssues(issues)
  const total =
    routed.makeup.length +
    routed.elective.length +
    routed.timetable.length +
    routed.roadmap.length +
    routed.detailedEvidence.length
  if (total === issues.length) return []
  const kept = new Set(
    [
      ...routed.makeup,
      ...routed.elective,
      ...routed.timetable,
      ...routed.roadmap,
      ...routed.detailedEvidence,
    ].map((issue) => issue.id),
  )
  return issues.filter((issue) => !kept.has(issue.id)).map((issue) => issue.id)
}
