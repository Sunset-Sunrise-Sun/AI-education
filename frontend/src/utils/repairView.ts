/**
 * 换班建议的**课程级**视图模型。
 *
 * 人工验收发现的两个严重问题：
 *
 * 1. 「可确认的换班建议（60 项）」把**同一门课**的 60 个候选班铺成 60 张卡片
 *    （例：劳动教育 PUB178 出现 60 次）；
 * 2. 「无法给出换班建议的课程（11 项）」把 11 门课各铺一张大卡片，
 *    主文案还是 `UNKNOWN` / `schedule_unknown`。
 *
 * 本模块把它们归一成：
 *
 * ```text
 * 一门课 = 一张卡片
 *   候选数 / 可确认无冲突数 / 待核验数 / 已知冲突数
 *   默认只显示前 3 个候选，其余折叠
 * ```
 *
 * 边界：
 * - ⛔ 后端原始 `reason` 文本只放进「技术详情」，⛔ 不作为主文案；
 * - ⛔ 排序只用**确定性**规则（CLEAR > UNKNOWN > CONFLICT，再按教学班号），
 *   ⛔ 不伪造任何评分 / 概率 / 推荐度；
 * - ⛔ 没有 CLEAR 候选时**不叫**「可确认的换班建议」，改叫「可考虑的替代教学班」。
 */

export type CandidateState = 'CLEAR' | 'UNKNOWN' | 'CONFLICT'

export interface RawRepairProposal {
  proposal_id: string
  course_id: string
  current_class_id: string
  candidate_class_id: string
  /** 原班状态（`CONFLICT` / `UNKNOWN`）。 */
  original_state?: string
  /** 候选状态；只有 CLEAR 的候选才会被后端放进建议里。 */
  candidate_state?: string
  reason?: string
}

export interface RepairCandidate {
  classId: string
  state: CandidateState
  /** 与课表的冲突状态是否**已确认无冲突**。 */
  confirmedClear: boolean
}

export interface CourseRepairGroup {
  courseId: string
  courseName: string
  /** 该课程在 `current_schedule` 里的教学班（可能为空）。 */
  currentClassId: string | null
  candidates: RepairCandidate[]
  clearCount: number
  unknownCount: number
  knownConflictCount: number
  /** 有 CLEAR 候选时为 true ⇒ 文案才可以用「可确认」。 */
  hasConfirmableCandidate: boolean
  /** 面向用户的标题级别文案。 */
  headline: string
  /** 面向用户的补充说明（中文化）。 */
  note: string
}

/** 无法给出建议的一门课（`repair unresolved` 聚合后）。 */
export interface CourseRepairBlocker {
  courseId: string
  courseName: string
  currentClassId: string | null
  reasonKind: 'unknown_schedule' | 'all_conflict' | 'no_alternatives' | 'other'
  /** 中文原因。 */
  reasonLabel: string
  /** 后端原文（技术详情）。 */
  rawMessage: string
}

export interface RepairView {
  groups: CourseRepairGroup[]
  blockers: CourseRepairBlocker[]
  /** 「有 N 门课程暂时无法生成可靠的换班建议」的摘要分类。 */
  blockerSummary: { kind: CourseRepairBlocker['reasonKind']; label: string; count: number }[]
}

const BLOCKER_LABEL: Record<CourseRepairBlocker['reasonKind'], string> = {
  unknown_schedule: '排课信息不完整',
  all_conflict: '候选教学班均有冲突',
  no_alternatives: '没有同课程替代班',
  other: '其它原因',
}

/**
 * 从文本里提取课程号（仅用于分组，⛔ 不构造业务事实）。
 *
 * ⚠️ 必须**大写字母开头**：`schedule_unknown` 这类小写机器码不得被当成课程号。
 */
function courseIdFrom(text: string): string | null {
  const match = /\b([A-Z]{2,}[0-9]{2,}[A-Z]?)\b/.exec(text)
  return match ? match[1] : null
}

function classIdFrom(text: string): string | null {
  const match = /教学班\s*(\d{4,})/.exec(text)
  return match ? match[1] : null
}

/** 从后端未决文本里判定原因类别（⛔ 只看后端已给出的取值）。 */
function blockerKindFrom(text: string): CourseRepairBlocker['reasonKind'] {
  const lower = text.toLowerCase()
  if (lower.includes('no_alternatives')) return 'no_alternatives'
  if (lower.includes('all_conflict')) return 'all_conflict'
  if (lower.includes('unknown') || text.includes('排课信息')) return 'unknown_schedule'
  if (text.includes('没有') || text.includes('无')) return 'no_alternatives'
  if (text.includes('冲突')) return 'all_conflict'
  return 'other'
}

function candidateStateFrom(proposal: RawRepairProposal): CandidateState {
  const value = (proposal.candidate_state ?? '').toUpperCase()
  if (value === 'CLEAR') return 'CLEAR'
  if (value === 'CONFLICT') return 'CONFLICT'
  return 'UNKNOWN'
}

/**
 * 组装课程级换班视图。
 *
 * @param proposals 后端结构化换班建议
 * @param unresolved 后端"无法给出建议"的字符串列表
 * @param courseNameById 课程号 → 课程名（课程名优先展示）
 * @param maxInitialCandidates 每门课默认展示的候选数（默认 3）
 */
export function buildRepairView(
  proposals: readonly RawRepairProposal[],
  unresolved: readonly string[],
  courseNameById: Record<string, string> = {},
  maxInitialCandidates = 3,
): RepairView {
  const byCourse = new Map<string, RawRepairProposal[]>()
  for (const proposal of proposals) {
    const list = byCourse.get(proposal.course_id) ?? []
    list.push(proposal)
    byCourse.set(proposal.course_id, list)
  }

  const groups: CourseRepairGroup[] = []
  for (const [courseId, list] of byCourse) {
    const candidates: RepairCandidate[] = list.map((proposal) => {
      const state = candidateStateFrom(proposal)
      return {
        classId: proposal.candidate_class_id,
        state,
        confirmedClear: state === 'CLEAR',
      }
    })
    // 确定性排序：CLEAR > UNKNOWN > CONFLICT，同级按教学班号升序。
    const rank: Record<CandidateState, number> = { CLEAR: 0, UNKNOWN: 1, CONFLICT: 2 }
    candidates.sort(
      (a, b) => rank[a.state] - rank[b.state] || a.classId.localeCompare(b.classId),
    )
    const clearCount = candidates.filter((c) => c.state === 'CLEAR').length
    const unknownCount = candidates.filter((c) => c.state === 'UNKNOWN').length
    const knownConflictCount = candidates.filter((c) => c.state === 'CONFLICT').length
    const name = courseNameById[courseId] ?? courseId
    const hasConfirmable = clearCount > 0
    groups.push({
      courseId,
      courseName: name,
      currentClassId: list[0]?.current_class_id ?? null,
      candidates,
      clearCount,
      unknownCount,
      knownConflictCount,
      hasConfirmableCandidate: hasConfirmable,
      // ⛔ 没有 CLEAR 时不得使用"可确认"字样
      headline: hasConfirmable ? '可以换班' : '可考虑的替代教学班',
      note: hasConfirmable
        ? `找到 ${candidates.length} 个同学期教学班，其中 ${clearCount} 个已确认与你的课表不冲突。`
        : `找到 ${candidates.length} 个同学期教学班，但排课信息仍需核验，无法确认是否冲突。`,
    })
  }
  groups.sort((a, b) => a.courseId.localeCompare(b.courseId))

  const blockers: CourseRepairBlocker[] = []
  for (const message of unresolved) {
    const text = message.trim()
    if (!text) continue
    const courseId = courseIdFrom(text) ?? ''
    const kind = blockerKindFrom(text)
    blockers.push({
      courseId,
      courseName: courseNameById[courseId] ?? courseId,
      currentClassId: classIdFrom(text),
      reasonKind: kind,
      reasonLabel: BLOCKER_LABEL[kind],
      rawMessage: text,
    })
  }
  blockers.sort(
    (a, b) => a.reasonKind.localeCompare(b.reasonKind) || a.courseId.localeCompare(b.courseId),
  )

  const counts = new Map<CourseRepairBlocker['reasonKind'], number>()
  for (const blocker of blockers) {
    counts.set(blocker.reasonKind, (counts.get(blocker.reasonKind) ?? 0) + 1)
  }
  const blockerSummary = [...counts.entries()]
    .map(([kind, count]) => ({ kind, label: BLOCKER_LABEL[kind], count }))
    .sort((a, b) => b.count - a.count || a.kind.localeCompare(b.kind))

  void maxInitialCandidates
  return { groups, blockers, blockerSummary }
}

/** 每门课默认展示的候选数（供组件复用，避免魔法数字散落）。 */
export const MAX_INITIAL_CANDIDATES = 3
