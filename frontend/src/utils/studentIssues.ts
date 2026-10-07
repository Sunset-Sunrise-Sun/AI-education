/**
 * 统一的「需要你处理」视图模型 —— 前端**唯一**的待确认事项来源。
 *
 * 背景（人工验收发现的问题）：
 * 同一件事曾同时出现在「待你确认的调整」「其他待确认事项」「补修任务待人工确认」
 * 与「无法给出换班建议」里，用户看到 2–3 遍；而且内部取值
 * （`schedule_unknown` / `UNKNOWN` / `manual_confirmation` / `no_alternatives` …）
 * 被直接当成主文案显示。
 *
 * 本模块只做**纯函数式**归一化：
 *
 * ```text
 * plan_result.unresolved  ┐
 * roadmap.unresolved      ├─→ normalizedIssues() → 去重 → 分组 → 中文化 → 排序
 * repair_proposals.       │
 *   unresolved            ┘
 * ```
 *
 * 边界：
 * - ⛔ 不新增业务结论、⛔ 不猜测后端没给的事实；
 * - ⛔ 不把机器码当主文案（机器码只放进「技术详情」）；
 * - ⛔ 不发明"确认已满足"这类会改变 satisfaction 的动作；
 * - 同样的 `(kind, course_id, identity)` 只保留**一条**。
 */

/** 归一化后的问题类别。 */
export type IssueKind =
  | 'repair_choice' // 有可确认的换班候选（可操作）
  | 'no_alternatives' // 找不到可靠的替代教学班
  | 'schedule_unknown' // 排课信息缺失 ⇒ 无法判断冲突
  | 'all_conflict' // 候选教学班都有冲突
  | 'makeup_confirmation' // 补修认定需要人工确认（⛔ 系统不代为认定）
  | 'selection_required' // 需要用户明确选择教学班
  | 'elective_selection' // 本学期有可选专业选修，等你决定
  | 'binding_provenance' // 上传成绩单未参与满足判定（provenance 说明）
  | 'other' // 后端给出的其它未决事项（保留原文）

/** 一条归一化后的问题（页面只渲染这个）。 */
export interface NormalizedIssue {
  /** 稳定去重键。 */
  id: string
  kind: IssueKind
  /** 主标题：课程名优先，其次课程号，最后才是通用标题。 */
  title: string
  /** 次级信息：课程号 / 教学班等。 */
  detail: string
  /** 面向用户的中文说明。 */
  message: string
  /** 原始机器取值（只在「查看技术详情」里展示）。 */
  rawCode: string | null
  /** 后端原始文本（技术详情）。 */
  rawMessage: string | null
  /** 依据来源（默认折叠展示）。 */
  sourceEvidence: string[]
  /** 是否真的需要用户**动作**（而不是"知悉"）。 */
  actionable: boolean
  /** 涉及课程号（用于分组与去重，可空）。 */
  courseId: string | null
}

const ISSUE_LABEL: Record<IssueKind, string> = {
  repair_choice: '可以换班',
  no_alternatives: '没有可用的替代教学班',
  schedule_unknown: '排课信息待确认',
  all_conflict: '候选教学班都有冲突',
  makeup_confirmation: '补修认定需要人工确认',
  selection_required: '需要你选择教学班',
  elective_selection: '本学期可选专业选修',
  binding_provenance: '成绩单未参与已修判定',
  other: '需要确认',
}

export function issueLabel(kind: IssueKind): string {
  return ISSUE_LABEL[kind]
}

/**
 * 把后端/前端的内部取值翻译成面向学生的中文。
 *
 * ⛔ 返回值里**不得**出现机器码；未知取值回退到中性中文，并把原文放进技术详情。
 */
export function humanizeIssueCode(code: string | null | undefined): string {
  const value = (code ?? '').trim().toLowerCase()
  switch (value) {
    case 'schedule_unknown':
    case 'unknown':
    case 'missing_schedule':
    case 'missing_data':
      return '排课信息尚未同步，暂时无法判断是否冲突'
    case 'no_alternatives':
      return '暂时没有该课程的其他教学班可选'
    case 'all_conflict':
      return '现有的候选教学班都与你的课表冲突'
    case 'manual_confirmation':
      return '这门课的补修认定需要人工确认'
    case 'possibly_equivalent':
      return '这门课可能与已修课程相同，需要人工确认后才能认定'
    case 'selection_required':
      return '有多个可选教学班，需要你决定用哪一个'
    case 'satisfied':
      return '已确认满足'
    case '':
      return '需要确认'
    default:
      // ⛔ 不把未知机器码当成中文文案展示
      return '需要确认'
  }
}

interface RawUnresolved {
  type?: string
  message?: string
  course_id?: string
}

export interface NormalizeInput {
  /** `plan_result.unresolved`（冻结契约里的未决事项）。 */
  planUnresolved?: RawUnresolved[]
  /** `roadmap.unresolved`（未来学期路线图的字符串说明）。 */
  roadmapUnresolved?: string[]
  /** `repair_proposals.unresolved`（换班建议的字符串说明）。 */
  repairUnresolved?: string[]
  /** 课程号 → 课程名（用于"课程名优先"）。 */
  courseNameById?: Record<string, string>
  /** 已确认的换班建议（可操作项）。 */
  repairProposals?: {
    proposal_id: string
    course_id: string
    current_class_id: string
    candidate_class_id: string
    reason: string
    candidate_state?: string
  }[]
}

/** 从一段自由文本里尽力提取课程号（仅用于分组/去重，⛔ 不构造业务事实）。 */
function extractCourseId(text: string): string | null {
  const match = /([A-Z]{2,}[A-Z0-9]*\d{2,}[A-Z]?)/.exec(text)
  return match ? match[1] : null
}

/**
 * 从文本里提取**教学班号**（仅用于去重键，⛔ 不构造业务事实）。
 *
 * ⚠️ 为什么必须进去重键：同一门课的**不同教学班**可能各自产生一条问题。
 * 如果键里只有 `kind + course_id`，就会把两个**不同的教学班问题**错误合并成一条，
 * 用户会因此丢掉一条真实待办。因此键里带上教学班身份。
 */
function extractClassId(text: string): string | null {
  const match = /教学班\s*(\d{4,})/.exec(text)
  return match ? match[1] : null
}

function titleFor(courseId: string | null, nameById: Record<string, string>): string {
  if (!courseId) return '需要你确认'
  const name = nameById[courseId]
  return name ? name : courseId
}

/**
 * 归一化 + 去重 + 中文化。
 *
 * 去重键 = `kind + courseId + 归一化后的 detail`。
 * 同一件事无论从哪个后端列表来，只会出现一次。
 */
export function normalizedIssues(input: NormalizeInput): NormalizedIssue[] {
  const nameById = input.courseNameById ?? {}
  const byId = new Map<string, NormalizedIssue>()

  function push(issue: NormalizedIssue) {
    if (!byId.has(issue.id)) byId.set(issue.id, issue)
  }

  // 1) 可操作的换班候选（按**课程**聚合由 UI 负责，这里一门课先合成一条入口）
  const proposalsByCourse = new Map<string, typeof input.repairProposals>()
  for (const proposal of input.repairProposals ?? []) {
    const list = proposalsByCourse.get(proposal.course_id) ?? []
    list.push(proposal)
    proposalsByCourse.set(proposal.course_id, list)
  }
  for (const [courseId, proposals] of proposalsByCourse) {
    const count = proposals?.length ?? 0
    if (count === 0) continue
    const clearest = (proposals ?? []).find((p) => (p.candidate_state ?? '') === 'CLEAR')
    push({
      id: `repair_choice::${courseId}`,
      kind: 'repair_choice',
      title: titleFor(courseId, nameById),
      detail: courseId,
      message:
        clearest !== undefined
          ? `找到 ${count} 个同学期教学班，其中至少一个已确认与你的课表不冲突，等你确认后才会调整。`
          : `找到 ${count} 个同学期教学班，但排课信息仍需核验。`,
      rawCode: null,
      rawMessage: proposals?.[0]?.reason ?? null,
      sourceEvidence: [],
      actionable: true,
      courseId,
    })
  }

  // 2) 计划未决事项（冻结契约）
  for (const item of input.planUnresolved ?? []) {
    const rawType = (item.type ?? '').trim()
    const message = (item.message ?? '').trim()
    const courseId = item.course_id ?? extractCourseId(message)
    const lower = rawType.toLowerCase()

    // ⛔ 已有可操作换班候选时，`selection_required` 不再单独占一条（同一件事）
    if (lower === 'selection_required' && courseId && proposalsByCourse.has(courseId)) {
      continue
    }

    const kind: IssueKind =
      lower === 'schedule_unknown' || lower === 'unknown'
        ? 'schedule_unknown'
        : lower === 'selection_required'
          ? 'selection_required'
          : lower === 'manual_confirmation'
            ? 'makeup_confirmation'
            : lower === 'no_alternatives'
              ? 'no_alternatives'
              : lower === 'all_conflict'
                ? 'all_conflict'
                : 'other'

    const human = humanizeIssueCode(rawType)
    push({
      id: `${kind}::${courseId ?? ''}::${human}`,
      kind,
      title: titleFor(courseId, nameById),
      detail: courseId ?? '',
      message: message && kind === 'other' ? message : human,
      rawCode: rawType || null,
      rawMessage: message || null,
      sourceEvidence: [],
      actionable: kind === 'selection_required',
      courseId,
    })
  }

  // 3) 路线图未决（字符串）
  for (const message of input.roadmapUnresolved ?? []) {
    const text = message.trim()
    if (!text) continue
    const courseId = extractCourseId(text)
    // 机器码判定：文本里出现已知内部取值时按对应类别归一
    const lower = text.toLowerCase()
    const kind: IssueKind = lower.includes('证据不足')
      ? 'makeup_confirmation'
      : lower.includes('先修')
        ? 'other'
        : lower.includes('学分负荷') || lower.includes('预算')
          ? 'other'
          : 'other'
    const human = lower.includes('证据不足')
      ? '部分认定证据不足，需要人工确认'
      : text
    push({
      id: `${kind}::${courseId ?? ''}::${human.slice(0, 40)}`,
      kind,
      title: titleFor(courseId, nameById),
      detail: courseId ?? '',
      message: human,
      rawCode: null,
      rawMessage: text,
      sourceEvidence: [],
      actionable: false,
      courseId,
    })
  }

  // 4) 换班建议未决（字符串）
  for (const message of input.repairUnresolved ?? []) {
    const text = message.trim()
    if (!text) continue
    const courseId = extractCourseId(text)
    const classId = extractClassId(text)
    const lower = text.toLowerCase()
    const kind: IssueKind = lower.includes('没有其他') || lower.includes('没有可')
      ? 'no_alternatives'
      : 'all_conflict'
    const human = kind === 'no_alternatives'
      ? '暂时没有该课程的其他教学班可选'
      : '现有的候选教学班都与你的课表冲突'
    push({
      // ⚠️ 去重键带上**教学班身份**：同一门课的不同教学班是**不同**待办，⛔ 不得合并
      id: `${kind}::${courseId ?? ''}::${classId ?? ''}::${human}`,
      kind,
      title: titleFor(courseId, nameById),
      detail: classId ? `${courseId ?? ''} · 教学班 ${classId}` : (courseId ?? ''),
      message: human,
      rawCode: null,
      rawMessage: text,
      sourceEvidence: [],
      actionable: false,
      courseId,
    })
  }

  // 排序：可操作优先 → 类别稳定序 → 课程号稳定序
  const order: IssueKind[] = [
    'repair_choice',
    'selection_required',
    'elective_selection',
    'makeup_confirmation',
    'schedule_unknown',
    'all_conflict',
    'no_alternatives',
    'binding_provenance',
    'other',
  ]
  return [...byId.values()].sort((a, b) => {
    if (a.actionable !== b.actionable) return a.actionable ? -1 : 1
    const byKind = order.indexOf(a.kind) - order.indexOf(b.kind)
    if (byKind !== 0) return byKind
    return (a.courseId ?? '').localeCompare(b.courseId ?? '')
  })
}

/** 按类别汇总计数（用于"有 N 门课程暂时无法生成可靠的换班建议"这类摘要）。 */
export function summarizeByKind(
  issues: readonly NormalizedIssue[],
): { kind: IssueKind; label: string; count: number }[] {
  const counts = new Map<IssueKind, number>()
  for (const issue of issues) {
    counts.set(issue.kind, (counts.get(issue.kind) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([kind, count]) => ({ kind, label: issueLabel(kind), count }))
    .sort((a, b) => b.count - a.count || a.kind.localeCompare(b.kind))
}
