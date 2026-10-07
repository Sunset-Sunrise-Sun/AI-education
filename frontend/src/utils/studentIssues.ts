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
  /** 涉及教学班号（用于**区分同课程的不同教学班**，可空）。 */
  classId: string | null
}

const ISSUE_LABEL: Record<IssueKind, string> = {
  repair_choice: '可以换班',
  // ⚠️ 与 `humanizeIssueCode('no_alternatives')` 保持**同一措辞**（全局唯一口径）
  no_alternatives: '暂未找到可替代的同课程教学班',
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
 * 把后端机器取值翻译成面向学生的中文。
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
      return '排课信息暂不完整，需要进一步确认'
    case 'no_alternatives':
      return '暂未找到可替代的同课程教学班'
    case 'all_conflict':
      return '现有的候选教学班都与你的课表冲突'
    case 'manual_confirmation':
      return '这项认定需要人工确认'
    case 'possibly_equivalent':
      return '这门课可能与已修课程相同，需要人工确认后才能认定'
    case 'selection_required':
      return '有多个可选教学班，需要你选择'
    case 'satisfied':
      return '已确认满足'
    case '':
      return '需要进一步确认'
    default:
      // ⛔ 不把未知机器码当成中文文案展示
      return '该事项需要进一步确认'
  }
}

/**
 * 内部机器取值 → 中文。**只替换整词**（词边界），⛔ 不做子串替换。
 *
 * ⚠️ 为什么需要它：后端会把内部取值拼进**面向用户的句子**里，例如
 * `…… 状态为 CONFLICT（no_alternatives）` 或 `recommended_semester=4 不在……`。
 * 这些字符串以前被原样渲染到主界面。本表把它们就地翻成中文。
 *
 * ⛔ 未登记的取值**不得**原样显示：调用方必须先跑 `humanizeIssueCode` 兜底，
 * 未识别时整段回退为中性中文（见 `normalizeRawText`）。
 */
const RAW_TOKEN_LABELS: Record<string, string> = {
  schedule_unknown: '排课信息暂不完整',
  // ⚠️ 统一口径：详情/摘要里也必须与 `humanizeIssueCode('no_alternatives')` 完全一致
  no_alternatives: '暂未找到可替代的同课程教学班',
  all_conflict: '候选教学班均有冲突',
  selection_required: '有多个可选教学班，需要你选择',
  manual_confirmation: '需要人工确认',
  possibly_equivalent: '可能与已修课程相同，需要人工确认',
  missing_data: '缺少必要数据',
  missing_schedule: '排课信息缺失',
  recommended_semester: '培养方案建议学期',
  deadline_semester: '截止学期',
  credit_budget: '学分预算',
  deferred_for_credit_budget: '因学分负荷顺延',
  prerequisite_order: '先修顺序',
  required_by_recommended_term: '按建议学期安排',
  completed_binding: '已修绑定',
}

/** 命中该模式的整段文本判定为"纯内部取值/键值对"，不进主界面。 */
const RAW_IDENTIFIER = /^[a-z][a-z0-9_]*$/i
const RAW_KEY_VALUE = /\b([a-z][a-z0-9_]*)\s*=\s*([A-Za-z0-9_.:-]+)/gi

/**
 * 把一段可能含机器取值的文本转成可读中文。
 *
 * 规则：
 * 1. 已登记的整词取值 → 中文（词边界匹配）；
 * 2. `key=value` → `中文键名：value`（value 视为数据，保留）；
 * 3. 其它 `snake_case` 整词 → 中性中文（⛔ 不回显）；
 * 4. 结果里不留任何 `type:` 前缀或未登记机器码。
 */
export function normalizeRawText(text: string): string {
  const trimmed = (text ?? '').trim()
  if (!trimmed) return ''

  // 整段就是一个内部取值 ⇒ 直接中文化
  if (RAW_IDENTIFIER.test(trimmed)) {
    return RAW_TOKEN_LABELS[trimmed.toLowerCase()] ?? humanizeIssueCode(trimmed)
  }

  let out = trimmed
  // key=value 先处理（值保留为数据）
  out = out.replace(RAW_KEY_VALUE, (whole, key: string, value: string) => {
    const label = RAW_TOKEN_LABELS[key.toLowerCase()]
    return label ? `${label}：${value}` : whole
  })
  // 再按词边界替换已登记取值
  out = out.replace(/\b[a-z][a-z0-9_]*\b/gi, (token) => {
    const label = RAW_TOKEN_LABELS[token.toLowerCase()]
    if (label) return label
    // ⛔ 未登记的 snake_case 不回显；普通英文单词（无下划线）保持原样
    return token.includes('_') ? humanizeIssueCode(token) : token
  })
  return out.replace(/\s+/g, ' ').trim()
}

/** 去掉面向用户的主文案里可能残留的技术前缀（例如 `type:`）。 */
function stripTechnicalPrefix(text: string): string {
  return text.replace(/\btype\s*[:：]\s*/gi, '').trim()
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
  /** `roadmap.warnings`（同样可能含内部取值）。 */
  roadmapWarnings?: string[]
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

/**
 * 从一段自由文本里提取课程号（仅用于分组/去重，⛔ 不构造业务事实）。
 *
 * ⚠️ 必须是**大写字母开头**（`CSE204` / `MAR108` / `AA1006`）。
 * 早期版本用了大小写不敏感的模式，结果把 `schedule_unknown` 这类**小写机器码**
 * 当成了课程号，导致同一门课的问题无法跨来源合并（重复显示）。
 * ⛔ 不要再放宽大小写。
 */
function extractCourseId(text: string): string | null {
  const match = /\b([A-Z]{2,}[0-9]{2,}[A-Z]?)\b/.exec(text)
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

/** 次级信息：课程号 + （有则）教学班号。 */
function detailFor(courseId: string | null, classId: string | null): string {
  if (classId && courseId) return `${courseId} · 教学班 ${classId}`
  if (classId) return `教学班 ${classId}`
  return courseId ?? ''
}

/**
 * 保守的**语义判别式**：只在拿不到课程/教学班身份时使用。
 *
 * 做且只做稳定、无损的归一化：
 * - 大小写归一、统一全角/半角标点、折叠空白、去掉结尾句号；
 * - 机器取值按同一张表翻成中文（与主文案口径一致）。
 *
 * ⛔ 不做：删大段语义、模糊匹配、相似度、LLM、substring 去重。
 * ⛔ 不同的事项必须得到**不同**的判别式；无法确定同一时，宁可两者都留。
 */
function semanticDiscriminator(text: string): string {
  return normalizeRawText(text ?? '')
    .toLowerCase()
    .replace(/[，。、；：！？,.;:!?]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/[。.\s]+$/g, '')
    .trim()
}

/**
 * 去重键。
 *
 * ```text
 * 有 course_id / class_id ⇒ kind + courseId + classId        （⛔ 不含任何文案）
 * 完全没有身份            ⇒ kind + 语义判别式
 * ```
 *
 * ⚠️ 两条不同的原则，故意分开：
 *
 * - **有身份**时键里**不放文案**。因为同一件事在不同来源里措辞必然不同
 *   （`plan_result` 说「排课信息缺失」，`roadmap` 说「……（schedule_unknown）」），
 *   一旦把文案进键，真正重复的事项就永远合并不了（这正是 Case A 跨来源去重的目的）。
 *   代价是同课程同教学班下不同类别的问题会合并 —— 可接受的权衡：
 *   它们通常由同一次冲突引发，且属同一门课的教学班，合并如实的类别文案即可。
 * - **无身份**时用**各条自己的归一化语义**。多个不同的 plan 级
 *   `manual_confirmation` 往往都没有课程号/教学班号，若只按 `kind::''` 分桶
 *   会把它们全部压成一条，**静默丢掉真实待办**（禁止）。
 *
 * 原则：**宁可重复显示，不允许静默丢失真实事项**。
 */
function issueKey(
  kind: IssueKind,
  courseId: string | null,
  classId: string | null,
  discriminator: string,
): string {
  const hasIdentity = Boolean(courseId || classId)
  return hasIdentity
    ? `${kind}::${courseId ?? ''}::${classId ?? ''}`
    : `${kind}::${discriminator}`
}

/** 每个类别的规范中文判别式（⛔ 与用户可见文案口径一致，不含机器码）。 */
function canonicalLabelFor(kind: IssueKind): string {
  switch (kind) {
    case 'no_alternatives':
      return humanizeIssueCode('no_alternatives')
    case 'all_conflict':
      return humanizeIssueCode('all_conflict')
    case 'schedule_unknown':
      return humanizeIssueCode('schedule_unknown')
    case 'makeup_confirmation':
      return humanizeIssueCode('manual_confirmation')
    case 'selection_required':
      return humanizeIssueCode('selection_required')
    default:
      return kind
  }
}

/** 结构化 `unresolved[].type` → 类别。 */
function issueKindFromCode(rawType: string): IssueKind {
  const value = (rawType ?? '').trim().toLowerCase()
  if (value === 'schedule_unknown' || value === 'unknown') return 'schedule_unknown'
  if (value === 'selection_required') return 'selection_required'
  if (value === 'manual_confirmation') return 'makeup_confirmation'
  if (value === 'no_alternatives') return 'no_alternatives'
  if (value === 'all_conflict') return 'all_conflict'
  if (value === 'possibly_equivalent') return 'makeup_confirmation'
  return 'other'
}

/**
 * 自由文本 → 类别。⛔ 只做保守关键词判定（无模糊匹配、无相似度）。
 *
 * ⚠️ 必须同时看**原文**与**归一化后**的文本：原文可能带机器码
 * （`（schedule_unknown）`），归一化后则变成中文。
 *
 * ⚠️ 关键词**按特异性排序**，而不是先命中谁算谁：
 * `冲突` 是极其宽泛的词，几乎会出现在所有排课类消息里
 * （例如「排课信息尚未同步，暂时无法判断**是否冲突**」——真正的问题是
 * **排课信息缺失**，不是候选冲突）。因此：
 *
 * 1. 证据不足 / possibly_equivalent  ⇒ 需人工确认（最明确）
 * 2. 排课信息缺失类                  ⇒ schedule_unknown（原因明确且唯一）
 * 3. 没有替代班类                    ⇒ no_alternatives
 * 4. 冲突类                          ⇒ all_conflict（最宽泛，最后判定）
 * 5. 其它                            ⇒ other
 *
 * ⛔ 不得把「人工确认」这种到处都是的措辞当作判据。
 */
function issueKindFromText(text: string): IssueKind {
  const raw = (text ?? '').toLowerCase()
  const normalized = normalizeRawText(text ?? '').toLowerCase()
  const both = `${raw} ${normalized}`

  if (both.includes('possibly_equivalent') || both.includes('证据不足')) {
    return 'makeup_confirmation'
  }
  // ⚠️ 必须早于"冲突"判定：原因明确的信号优先
  if (
    both.includes('schedule_unknown') ||
    both.includes('排课信息') ||
    both.includes('时间安排')
  ) {
    return 'schedule_unknown'
  }
  if (
    both.includes('no_alternatives') ||
    both.includes('替代') ||
    both.includes('没有可确认无冲突')
  ) {
    return 'no_alternatives'
  }
  if (both.includes('all_conflict') || both.includes('冲突')) return 'all_conflict'
  if (both.includes('manual_confirmation')) return 'makeup_confirmation'
  return 'other'
}

/**
 * 统一入口：判定一条事项的类别。
 *
 * ⚠️ 优先级规则（重要）：
 *
 * 1. `plan_result.unresolved[].type` 是冻结 Schema 的**权威字段**，默认直接采用；
 * 2. **例外**：`manual_confirmation` 是后端使用的**兜底大桶**，同一个取值会承载
 *    很多互不相同的问题（"证据不足"、"已知时间冲突导致无解"、"容量规则未确认"…）。
 *    当文本能给出**更具体**的类别时，采用文本类别。
 *    否则同一条消息经 plan（有 type）与 roadmap（纯文本）进来会得到不同 kind，
 *    去重键不同 ⇒ 跨来源重复合并失败。
 * 3. `type` 缺失或未登记时，一律退回文本判定。
 * 4. 文本也只给出 `other` 时，保留兜底桶的类别（`makeup_confirmation`）。
 */
function resolveIssueKind(rawType: string, text: string): IssueKind {
  const value = (rawType ?? '').trim().toLowerCase()
  const fromText = issueKindFromText(text)
  if (!value) return fromText

  const fromCode = issueKindFromCode(value)
  if (fromCode === 'other') return fromText

  // 兜底大桶：优先采用文本给出的**更具体**类别
  const isGenericBucket = fromCode === 'makeup_confirmation'
  if (isGenericBucket && fromText !== 'other') return fromText

  return fromCode
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
      // 课程级入口：具体候选由「需要你处理」里的换班区域逐条列出
      classId: null,
    })
  }

  // 2) 计划未决事项（冻结契约）
  for (const item of input.planUnresolved ?? []) {
    const rawType = (item.type ?? '').trim()
    const message = (item.message ?? '').trim()
    // ⚠️ 冻结契约里 `Unresolved` **只有** `type` + `message`
    //    （`schemas/plan_result.schema.json` 为 `additionalProperties: false`，
    //     后端模型也是 `extra="forbid"`）。⛔ 不得假装它还有 `course_id`：
    //     身份一律从 `message` 文本里保守提取。
    const courseId = extractCourseId(message)
    const lower = rawType.toLowerCase()

    // ⛔ 已有可操作换班候选时，`selection_required` 不再单独占一条（同一件事）
    if (lower === 'selection_required' && courseId && proposalsByCourse.has(courseId)) {
      continue
    }

    const kind: IssueKind = resolveIssueKind(rawType, message)
    const human = humanizeIssueCode(rawType)
    const classId = extractClassId(message)
    // `other` 类型没有稳定中文文案 ⇒ 用归一化后的文本，⛔ 不含机器码
    const body = message ? stripTechnicalPrefix(normalizeRawText(message)) : ''
    const display = kind === 'other' && body ? body : human
    // ⚠️ 判别式取**原文**的归一化结果（而非 display）：即使类别文案相同，
    //    不同的原文也应得到不同判别式，从而**不会**被合并掉。
    const discriminator = semanticDiscriminator(message) || human
    push({
      id: issueKey(kind, courseId, classId, discriminator),
      kind,
      title: titleFor(courseId, nameById),
      detail: detailFor(courseId, classId),
      message: display,
      rawCode: rawType || null,
      rawMessage: message || null,
      sourceEvidence: [],
      actionable: kind === 'selection_required',
      courseId,
      classId,
    })
  }

  // 3) 路线图未决 / 警告（字符串；后端把内部取值拼进了句子里）
  for (const message of [...(input.roadmapUnresolved ?? []), ...(input.roadmapWarnings ?? [])]) {
    const text = (message ?? '').trim()
    if (!text) continue
    const courseId = extractCourseId(text)
    const classId = extractClassId(text)
    const kind = resolveIssueKind('', text)
    // ⚠️ 归一化后可能只剩中性中文；此时用类别文案兜底，保证主界面一定有可读中文
    const normalized = stripTechnicalPrefix(normalizeRawText(text))
    const fallback = humanizeIssueCode(kind === 'schedule_unknown' ? 'schedule_unknown' : '')
    const display = normalized || fallback
    push({
      // ⚠️ 判别式用**归一化后**的文本：跨来源（plan / roadmap）对同一件事的措辞
      //    差异（例如 `（schedule_unknown）` 后缀）会被同一张表吸收，从而正确合并。
      id: issueKey(kind, courseId, classId, semanticDiscriminator(text)),
      kind,
      title: titleFor(courseId, nameById),
      detail: detailFor(courseId, classId),
      message: display,
      rawCode: null,
      rawMessage: text,
      sourceEvidence: [],
      actionable: false,
      courseId,
      classId,
    })
  }

  // 4) 换班建议未决（字符串）
  for (const message of input.repairUnresolved ?? []) {
    const text = (message ?? '').trim()
    if (!text) continue
    const courseId = extractCourseId(text)
    const classId = extractClassId(text)
    const kind = resolveIssueKind('', text)
    const human =
      kind === 'no_alternatives'
        ? humanizeIssueCode('no_alternatives')
        : kind === 'all_conflict'
          ? humanizeIssueCode('all_conflict')
          : humanizeIssueCode('schedule_unknown')
    push({
      // ⚠️ 去重键带上**教学班身份**：同一门课的不同教学班是**不同**待办，⛔ 不得合并
      id: issueKey(kind, courseId, classId, semanticDiscriminator(text)),
      kind,
      title: titleFor(courseId, nameById),
      detail: detailFor(courseId, classId),
      message: human,
      rawCode: null,
      rawMessage: text,
      sourceEvidence: [],
      actionable: false,
      courseId,
      classId,
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

/**
 * 把归一化问题分成主界面上的**三个**分组。
 *
 * ⛔ 这些分组必须来自同一个 `normalizedIssues` view model，
 * 不允许各子组件再各自解析 raw unresolved。
 */
export interface IssueGroups {
  /** 需要你决定的（可操作）。 */
  actionable: NormalizedIssue[]
  /** 需要进一步确认的课程/认定。 */
  needsConfirmation: NormalizedIssue[]
  /** 数据暂不完整（排课信息缺失等）。 */
  incompleteData: NormalizedIssue[]
}

export function groupIssues(issues: readonly NormalizedIssue[], limit = 3): IssueGroups {
  const cap = (list: NormalizedIssue[]) => list.slice(0, limit)
  return {
    actionable: cap(issues.filter((issue) => issue.actionable)),
    needsConfirmation: cap(
      issues.filter(
        (issue) =>
          !issue.actionable &&
          (issue.kind === 'makeup_confirmation' || issue.kind === 'binding_provenance'),
      ),
    ),
    incompleteData: cap(
      issues.filter(
        (issue) =>
          !issue.actionable &&
          issue.kind !== 'makeup_confirmation' &&
          issue.kind !== 'binding_provenance',
      ),
    ),
  }
}

