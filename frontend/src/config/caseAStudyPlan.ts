/**
 * ⛔⛔ **本文件已降级为「离线演示回退」，不再参与任何真实匹配。** ⛔⛔
 *
 * ## 为什么降级（本轮架构裁决）
 *
 * 真实业务链已接通后端：`POST /api/v1/case-a-demo/plan` 会返回后端对
 * **学校真实培养方案**（94 门课程，从 `网安方案.docx` 抽取）与**上传成绩单**
 * 逐项匹配后的 `makeup_tasks[]`，其中每条都带有：
 *
 * ```text
 * status           后端判定（satisfied / possibly_equivalent / manual_confirmation / required）
 * reason           为什么这样判定（含不确定性分类）
 * source_evidence  可审计依据（培养方案表格行号 + 成绩单 PDF 行号）
 * ```
 *
 * 页面三状态改由 `utils/makeupAnalysis.ts` 从上述后端结果映射而来。
 *
 * ⚠️ 本文件里的两套培养方案是**演示样本**，与学校真实培养方案**并不一致**
 *   （课程号、类别、学分均有出入，例如真实方案里 `CSE301` 是必修「操作系统」，
 *   而本文件把它写成专业选修「数据库系统原理」）。因此：
 *
 * - ⛔ 不得作为页面匹配真源；
 * - ⛔ 不得与后端真实结果混用；
 * - ✅ 仅保留给「后端未配置时的离线演示」使用，且使用时必须如实标注为演示数据。
 *
 * 保留原因：`isEarlyMorning` / `isCrossCampus` 等**纯事实工具函数**仍被页面使用。
 */
/**
 * Case A Demo **培养方案配置层**（⛔ 业务组件不得内嵌课程判断）。
 *
 * ⚠️ 为什么需要本文件：
 *   后端 `CaseADemoResponse` **不下发「目标专业培养方案要求课程列表」**，
 *   只下发 `makeup_tasks`（已是后端匹配后的补修任务）。
 *   用 `makeup_tasks` 反推"培养方案要求"是**错的** —— 它会让三状态匹配退化成
 *   "全命中/全缺口"两种极端，学生已修的课被误当缺口推荐出去。
 *
 *   因此在 Demo 阶段，把「培养方案要求」「专业选修池」「样本成绩单」集中放在本配置，
 *   由 `matchStudyPlan()` 做真正的三状态匹配。
 *
 * ✅ 替换数据时只改本文件；组件读的全是匹配函数的结果。
 * ⛔ 不在组件里写 `if (courseId === 'XXX')`；⛔ 不伪造后端数据。
 */

/** 一条培养方案要求。 */
export interface PlanRequirement {
  readonly courseId: string
  readonly name: string
  /** `required` = 必修；`elective` = 专业选修。 */
  readonly kind: 'required' | 'elective'
  readonly credit: number
  /**
   * 该要求是否**允许用成绩单课程抵扣**。
   *
   * ⚠️ 必修课（尤其是通识/思政/体育）通常可抵扣；
   *   而专业核心课可能需要重学 → 置 `false` 时即使成绩单有记录也仍需修读。
   */
  readonly transcriptCanSatisfy: boolean
  /**
   * 成绩单有记录时是否**仍需用户确认**。
   *
   * ⚠️ 通识 / 思政 / 体育类（公共必修）课名一致即可认定 → alse（直接已满足）；
   *   学科基础 / 专业核心课存在等价性差异（课程内容、学分、学时可能不同）
   *   → 	rue（必须人工确认）。
   */
  readonly requiresConfirmation: boolean
}

/**
 * **目标专业培养方案要求**（Demo 样本 · 网络空间安全 / 计算机方向）。
 *
 * 说明：本样本以"计算机科学与技术 / 网络空间安全方向"的培养要求为例，
 * 混合了通识必修、学科基础与专业选修，用于演示三状态匹配。
 */
const NETWORK_SECURITY_REQUIREMENTS: readonly PlanRequirement[] = [
  // ---- 通识 / 思政 / 体育：成绩单可抵扣 ----
  { courseId: 'PE101', name: '体育', kind: 'required', credit: 1, transcriptCanSatisfy: true, requiresConfirmation: false },
  { courseId: 'PUB121', name: '军事课', kind: 'required', credit: 4, transcriptCanSatisfy: true, requiresConfirmation: false },
  { courseId: 'PUB1991', name: '国家安全教育', kind: 'required', credit: 1, transcriptCanSatisfy: true, requiresConfirmation: false },
  { courseId: 'PSY199', name: '心理健康教育', kind: 'required', credit: 2, transcriptCanSatisfy: true, requiresConfirmation: false },
  { courseId: 'MAR103', name: '中国近现代史纲要', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: false },
  { courseId: 'MAR115', name: '习近平新时代中国特色社会主义思想概论', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: false },
  { courseId: 'MAR112', name: '思想道德与法治', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: false },

  // ---- 学科基础：成绩单可抵扣，但等价关系需人工确认 ----
  { courseId: 'MA179', name: '线性代数', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'CSE201', name: '程序设计II', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'CSE203', name: '程序设计II实验', kind: 'required', credit: 1, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'CSE209', name: '离散数学', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },

  // ---- 学科基础：成绩单**没有** → missing ----
  { courseId: 'MA184', name: '概率统计（理工类）', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'MA190', name: '高等数学一（II）', kind: 'required', credit: 5, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'PHY139', name: '大学物理（工）下', kind: 'required', credit: 4, transcriptCanSatisfy: true, requiresConfirmation: true },

  // ---- 专业选修：本轮新增的推荐来源 ----
  { courseId: 'CSE301', name: '数据库系统原理', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'CSE302', name: '计算机网络', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'CSE303', name: '操作系统', kind: 'elective', credit: 4, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'CSE304', name: '机器学习导论', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'CSE305', name: '密码学基础', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
  { courseId: 'CSE306', name: '软件工程', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
]

/**
 * **Demo 样本成绩单课程名**（未匹配前的原始输入）。
 *
 * ⚠️ 后端 `transcript` 只下发计数（`record_count` / `term_count` /
 *   `pending_course_id_count`），**不下发课程级明细**；而 `case_a_demo.py` 里
 *   `recognitions=()` 是刻意的。因此"成绩单里有哪些课程"由本样本配置提供。
 *
 * ✅ 后续替换：后端一旦下发明细，改为读 `result.transcript.records` 即可，
 *   匹配函数与组件无需改动。
 */
export const DEMO_TRANSCRIPT_COURSES: readonly string[] = [
  '大学英语',
  '大学英语（II）',
  '线性代数',
  '高等数学（I）',
  '高等数学（II）',
  '概率统计（理工类）',
  '大学物理（工）上',
  '大学物理（工）下',
  '程序设计I',
  '程序设计I实验',
  '程序设计II',
  '程序设计II实验',
  '离散数学',
  // 通识 / 思政 / 体育
  '体育',
  '军事课',
  '国家安全教育',
  '心理健康教育',
  '中国近现代史纲要',
  '习近平新时代中国特色社会主义思想概论',
  '思想道德与法治',
]

/**
 * **成绩单课程名 → 培养方案课程号** 的别名映射。
 *
 * ⚠️ 成绩单与培养方案的课程名并不逐字相同（"大学英语" vs "大学外语（I）"）。
 * ⛔ 不做模糊匹配，只按本表精确命中。
 */
export const TRANSCRIPT_COURSE_ALIASES: Readonly<Record<string, readonly string[]>> = {
  FL101: ['大学英语', '大学英语（I）'],
  FL102: ['大学英语（II）'],
  MA179: ['线性代数'],
  MA189: ['高等数学（I）'],
  MA190: ['高等数学（II）'],
  MA184: ['概率统计（理工类）'],
  PHY137: ['大学物理（工）上'],
  PHY139: ['大学物理（工）下'],
  CSE101: ['程序设计I'],
  CSE103: ['程序设计I实验'],
  CSE201: ['程序设计II'],
  CSE203: ['程序设计II实验'],
  CSE209: ['离散数学'],
  PE101: ['体育'],
  PE102: ['体育'],
  PUB121: ['军事课'],
  PUB1991: ['国家安全教育'],
  PSY199: ['心理健康教育'],
  MAR103: ['中国近现代史纲要'],
  MAR115: ['习近平新时代中国特色社会主义思想概论'],
  MAR112: ['思想道德与法治'],
}

/** 成绩单里是否出现过该培养方案课程（含别名）。 */
export function transcriptHasCourse(
  courseId: string,
  transcriptNames: readonly string[],
): boolean {
  const aliases = TRANSCRIPT_COURSE_ALIASES[courseId]
  if (!aliases) return false
  const set = new Set(transcriptNames.map((name) => name.trim()))
  return aliases.some((alias) => set.has(alias))
}

/* ====================================================================== *
 * **两个正交维度**（⛔ 不可混为一谈）
 *
 *   match_status        学生是否**满足培养要求** —— 只由"成绩单 × 培养方案"决定
 *   availability_status 本学期**是否有教学班** —— 只由教学班数据决定
 *
 * ⚠️ 关键纠正：**"本学期不开课"绝不能改变满足状态**。
 *   例：成绩单已有「程序设计II」但本学期不开 →
 *       match_status         = satisfied
 *       availability_status  = not_opened_this_semester
 *   ⛔ 不是 auto_matched；⛔ 也不能因为不开课就改变 match_status。
 * ====================================================================== */

/** 学生是否满足该培养要求。 */
export type MatchStatus =
  /** 已满足：成绩单有记录且可认定 → 不进补修、不进推荐。 */
  | 'satisfied'
  /** 成绩单存在，但等价关系需人工确认。 */
  | 'need_confirmation'
  /** 培养方案要求，成绩单不存在 → 推荐来源。 */
  | 'missing'

/** 本学期该课程是否有教学班（与满足状态无关）。 */
export type AvailabilityStatus = 'opened_this_semester' | 'not_opened_this_semester'

export interface PlanMatch {
  readonly requirement: PlanRequirement
  /** 学生是否满足培养要求（只由成绩单 + 培养方案决定）。 */
  readonly matchStatus: MatchStatus
  /** 本学期是否有教学班（只由教学班数据决定）。 */
  readonly availabilityStatus: AvailabilityStatus
}

/**
 * **成绩单 × 培养方案 匹配**（两个维度独立计算）。
 *
 * `match_status` 规则：
 *   - 成绩单无记录                          -> missing
 *   - 成绩单有记录 + 不允许抵扣             -> missing
 *   - 成绩单有记录 + requiresConfirmation   -> need_confirmation
 *   - 成绩单有记录 + 不需确认               -> satisfied
 *
 * `availability_status` 规则：
 *   - 本学期有教学班 -> opened_this_semester
 *   - 否则           -> not_opened_this_semester
 *
 * 注意：`availability_status` **不影响** `match_status`。
 */
export function matchStudyPlan(
  transcriptNames: readonly string[],
  offeredIds: ReadonlySet<string>,
  majorId: string = DEFAULT_MAJOR_ID,
): PlanMatch[] {
  return requirementsOf(majorId).map((requirement) => {
    const hasOffering = offeredIds.has(requirement.courseId)
    const inTranscript = transcriptHasCourse(requirement.courseId, transcriptNames)

    let matchStatus: MatchStatus
    if (!inTranscript || !requirement.transcriptCanSatisfy) {
      matchStatus = 'missing'
    } else if (requirement.requiresConfirmation) {
      matchStatus = 'need_confirmation'
    } else {
      matchStatus = 'satisfied'
    }

    return {
      requirement,
      matchStatus,
      availabilityStatus: hasOffering
        ? ('opened_this_semester' as const)
        : ('not_opened_this_semester' as const),
    }
  })
}

/** 满足状态的展示文案。 */
export const MATCH_STATE_LABEL: Readonly<Record<MatchStatus, string>> = {
  satisfied: '已满足',
  need_confirmation: '需要确认可转换',
  missing: '未满足',
}

/** 满足状态的说明（告诉用户该做什么）。 */
export const MATCH_STATE_HINT: Readonly<Record<MatchStatus, string>> = {
  satisfied: '你的成绩单中已有该课程记录，这条培养要求视为已满足，不会进入补修或推荐。',
  need_confirmation:
    '你的成绩单中存在相关课程记录，系统无法自动确认能否抵扣目标专业要求，需要你确认。',
  missing: '目标专业培养要求中你尚未完成该课程。',
}

/** 教学状态的展示文案（与满足状态无关）。 */
export const AVAILABILITY_LABEL: Readonly<Record<AvailabilityStatus, string>> = {
  opened_this_semester: '本学期有教学班',
  not_opened_this_semester: '本学期未开课',
}

/** 是否命中"避免早课"（第 1-2 节开始）。 */
export function isEarlyMorning(startSection: number): boolean {
  return startSection <= 2
}

/** 是否命中"避免跨校区"。 */
export function isCrossCampus(campus: string | null, primaryCampus: string | null): boolean {
  if (!campus || !primaryCampus) return false
  return campus !== primaryCampus
}

/** 推荐理由的事实输入。 */
export interface RecommendationFacts {
  readonly kind: 'required' | 'elective'
  readonly availability: AvailabilityStatus
  readonly earlyMorning: boolean
  readonly crossCampus: boolean
}

/** 推荐理由（按事实与偏好生成，⛔ 不是固定万能文案）。 */
export function recommendationReason(facts: RecommendationFacts): string {
  const parts: string[] = []
  parts.push(
    facts.kind === 'elective'
      ? '该课程属于目标专业的专业选修课，可计入你的选修学分'
      : '该课程属于目标专业培养要求中你尚未完成的必修课程',
  )
  parts.push(
    facts.availability === 'opened_this_semester'
      ? '本学期已有可用教学班'
      : '本学期暂无可用教学班',
  )
  if (facts.earlyMorning) parts.push('⚠️ 该教学班为第 1-2 节，与你"避免早课"的偏好不一致')
  if (facts.crossCampus) parts.push('⚠️ 该教学班在其他校区，与你"避免跨校区"的偏好不一致')
  return `${parts.join('；')}。`
}

/* ====================================================================== *
 * **专业注册表**（可扩展结构）
 *
 *   major → studyPlan → requirements / electives
 *
 * Demo 阶段提供两个专业以验证"切换专业 → 培养方案变化 → 匹配结果变化"。
 * ✅ 新增专业只需往 `MAJORS` 里加一条，⛔ 组件无需改动。
 * ====================================================================== */

export interface MajorStudyPlan {
  readonly id: string
  readonly name: string
  /** 培养方案版本标识（真实场景来自学校文件）。 */
  readonly version: string
  readonly requirements: readonly PlanRequirement[]
}

export const MAJORS: readonly MajorStudyPlan[] = [
  {
    id: 'network-security',
    name: '网络空间安全',
    version: 'demo-2025',
    requirements: NETWORK_SECURITY_REQUIREMENTS,
  },
  {
    id: 'computer-science',
    name: '计算机科学与技术',
    version: 'demo-2025',
    requirements: [
      // 通识 / 思政 / 体育（成绩单可抵扣）
      { courseId: 'PE101', name: '体育', kind: 'required', credit: 1, transcriptCanSatisfy: true, requiresConfirmation: false },
      { courseId: 'PUB121', name: '军事课', kind: 'required', credit: 4, transcriptCanSatisfy: true, requiresConfirmation: false },
      { courseId: 'PUB1991', name: '国家安全教育', kind: 'required', credit: 1, transcriptCanSatisfy: true, requiresConfirmation: false },
      { courseId: 'MAR103', name: '中国近现代史纲要', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: false },
      { courseId: 'MAR112', name: '思想道德与法治', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: false },
      // 学科基础（需人工确认）
      { courseId: 'MA179', name: '线性代数', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
      { courseId: 'CSE201', name: '程序设计II', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
      { courseId: 'CSE209', name: '离散数学', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
      // 未满足（成绩单没有）
      { courseId: 'MA184', name: '概率统计（理工类）', kind: 'required', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
      { courseId: 'PHY139', name: '大学物理（工）下', kind: 'required', credit: 4, transcriptCanSatisfy: true, requiresConfirmation: true },
      { courseId: 'CSE310', name: '计算机组成原理', kind: 'required', credit: 4, transcriptCanSatisfy: true, requiresConfirmation: true },
      // 专业选修
      { courseId: 'CSE401', name: '编译原理', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
      { courseId: 'CSE402', name: '人工智能导论', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
      { courseId: 'CSE403', name: '计算机图形学', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
      { courseId: 'CSE404', name: '分布式系统', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
      { courseId: 'CSE405', name: '自然语言处理', kind: 'elective', credit: 3, transcriptCanSatisfy: true, requiresConfirmation: true },
    ],
  },
]

/** 默认专业（Demo 入口初始选中）。 */
export const DEFAULT_MAJOR_ID = 'network-security'

/** 按 id 取专业；找不到时回退到默认专业。 */
export function findMajor(majorId: string): MajorStudyPlan {
  return MAJORS.find((major) => major.id === majorId)
    ?? MAJORS.find((major) => major.id === DEFAULT_MAJOR_ID)!
}

/** 取某专业的全部要求。 */
export function requirementsOf(majorId: string): readonly PlanRequirement[] {
  return findMajor(majorId).requirements
}

/** 取某专业的专业选修课（推荐来源之一）。 */
export function electivesOf(majorId: string): PlanRequirement[] {
  return requirementsOf(majorId).filter((requirement) => requirement.kind === 'elective')
}
