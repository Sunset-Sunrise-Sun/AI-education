/**
 * 未来学习路径规划（Phase 7 · 完善版）—— **前端派生**的课程完成路径。
 *
 * ## ⛔ 这不是什么（边界，必须先读）
 *
 * - ⛔ **不是未来选课预测**：不预测教师、时间地点，不生成教学班
 *   （`FutureRoadmapCourse` 刻意不含 `class_id` / `teacher` / `weekday` / `section` / `classroom`）。
 * - ⛔ 不改 `matching` 引擎、⛔ 不改推荐算法、⛔ 不改 OCR、⛔ 不改后端 schema。
 * - ⛔ 不引入任何 Mock 数据、⛔ 不生成不存在的课程。
 * - ⛔ 不把 `need_confirmation` 自动当 `satisfied`（那要学生本人确认）。
 * - ⛔ 不用**课程名模糊猜测**完成情况（只做归一化后的**同名**判定）。
 * - 本文件只做**分组与排期派生**，不新增任何课程认定结论。
 *
 * ## 数据来源（全部来自真实后端结果或已有输入）
 *
 * | 用途 | 来源 |
 * |---|---|
 * | 培养要求（课程 / 类型 / 学分 / 推荐学期 / 先修） | `GET /api/v1/study-plans/{major_id}` |
 * | 匹配结果（status） | `POST /api/v1/case-a-demo/plan` → `makeup_tasks[]` |
 * | **已修课程**（判定"已完成"的唯一依据） | `POST /api/v1/completed-courses/import-pdf` |
 * | **当前课表**（判定"进行中"的唯一依据） | 用户输入（原始课表 / 手动加入） |
 * | 专业选修学分要求 | 培养方案 `elective_pool.groups[].minimum_credit` + 后端 `elective_progress[]` |
 * | 学生确认（本地状态） | `confirmedMakeupCourseIds`（与 `makeupAnalysis` **同一**状态源） |
 * | 当前学期 | 请求参数 `semester` |
 *
 * ## 🔴 状态闭环（必须与 `utils/makeupAnalysis.ts` 保持一致）
 *
 * 学生在「补修缺口分析」里确认某门课可转换后，`makeupAnalysis` 会把它归入
 * `satisfied`。**未来路径必须同步重算**，否则学生确认完，旧规划还挂着那门课。
 *
 * 因此本模块接收 `confirmedCourseIds`，并按与 `toMakeupAnalysis` **相同**的口径
 * 先应用学生确认，再分类：
 *
 * ```text
 * 后端 status          + 学生确认        ⇒ 有效状态
 * satisfied            —               ⇒ 已完成（后端判定）
 * manual_confirmation  已确认           ⇒ 已完成（学生确认）
 * manual_confirmation  未确认           ⇒ 待确认   ⛔ 不排期
 * possibly_equivalent  已确认           ⇒ 已完成（学生确认）
 * possibly_equivalent  未确认           ⇒ 待确认   ⛔ 不排期
 * required             —               ⇒ 待补修   ✅ 排期
 * ```
 *
 * ## 课程完成度五状态（页面必须分开体现）
 *
 * ```text
 * 已完成            ← 成绩单同名且通过 / 后端 satisfied / 学生本人确认
 * 进行中            ← 出现在**当前课表**里（⛔ 进行中 ≠ 已完成）
 * 明确缺口          ← 后端判定 required（**系统明确了**这是缺口）   ✅ 进入未来规划
 * 待确认            ← 后端 manual_confirmation / possibly_equivalent，未确认  ⛔ 不排期
 * 培养要求待覆盖    ← 培养方案要求存在，但当前成绩单/课表/匹配结果
 *                      **不足以判断是否需要补修**                    ✅ 进入未来规划
 * ```
 *
 * ## 📐 排期规则（本轮重新设计：**不复制培养方案的推荐学期**）
 *
 * ⚠️ 旧实现把课程放进培养方案写的 `recommended_term_text`，导致"后续学期个位数
 *   学分"（实测 `2027秋 4 学分`、`2028春 4 学分`）—— 那是**培养方案的原始排课**，
 *   不是转专业学生的实际规划场景。转专业学生需要在剩余学期里**把剩余要求修完**。
 *
 * 新规则（只调整前端 roadmap planner，⛔ 不动 matching / 后端）：
 *
 * ```text
 * 1. 当前学期课程          ⇒ 不进入未来（已在修）
 * 2. 已完成课程            ⇒ 不进入未来
 * 3. 待确认课程            ⇒ 不自动排期
 * 4. 明确缺口 + 培养要求待覆盖 ⇒ 进入**候选池**，在剩余学期里重新分配
 * 5. 每学期学分 <= 35；除**最后毕业学期**外尽量 >= 15
 * 6. 毕业论文 / 毕业设计    ⇒ 固定放**最后一个学期**
 * 7. 推荐学期只作为**同分时的稳定排序参考**（不再决定学期）
 * ```
 *
 * 学期数**按剩余学分推导**（`ceil(剩余 / 35)`），⛔ 不再固定 4~5 个学期。
 *
 * ## ⚠️ 语义收敛：为什么叫「培养要求待覆盖」而不是"待判定缺口"
 *
 * 后端对这 57 门课**从未下过任何结论**（`makeup_tasks` 里根本没有它们）。
 * 若把它们叫"缺口"，就是在**暗示系统已经判断学生缺这些课** —— 那是不实陈述。
 *
 * 因此：
 *
 * - 页面文案统一为「**培养要求待覆盖**」；
 * - 说明语固定为：
 *   > 目标培养方案要求存在，但当前成绩单/课表/匹配结果不足以判断是否需要补修。
 * - ⛔ 不出现"缺课""缺失判定"等暗示系统已判定的措辞。
 *
 * ⚠️ 但为了让不确定性**可见而非被隐藏**，它仍**单独计数、单独列出**，
 *   与「明确缺口」「待确认」三者严格区分。
 *
 * ## ⚠️ 重要说明：为什么"培养要求待覆盖"也必须进入未来规划
 *
 * **实测真实数据**：`/case-a-demo/plan` 的 23 条 `makeup_tasks` **全部是
 * `manual_confirmation`，`required` 数量为 0**；而培养方案 57 门必修里
 * 有大量课程（操作系统、现代密码学、信号与系统…）**根本没有出现**在任务里。
 *
 * 也就是说：
 *
 * - 若**只**排后端 `required` 的课程 ⇒ 本样本的未来路径**永远是空的**，
 *   无法回答"我还缺什么、未来该修什么"（即本次要解决的核心问题）；
 * - 把这些课排进去，其依据**不是**前端在推断缺口，而是：
 *   1. 它**写在目标专业培养方案里**（`requirement = required`）；
 *   2. 成绩单里**没有**同名且通过的记录；
 *   3. 当前课表里**没有**它；
 *   4. 后端也没有 `satisfied` 判定。
 *
 *   ⇒ 这是"**培养方案要求、且没有任何已完成证据**"的确定集合，
 *     ⛔ 不是"算出来的毕业缺口"，页面也**不据此给出毕业结论**。
 *
 * ⚠️ 为了让不确定性**可见而非被隐藏**，「待判定」在页面上**单独计数、单独列出**，
 *   与「待补修」严格区分（后端从未对它们下过结论）。
 */

import type { FutureRoadmapCourse, FutureRoadmapSemester } from '../types/caseAPlanning'
import type { MakeupTask } from '../types/contracts'
import type { ElectiveProgress, StudyPlan, StudyPlanRequirement } from '../types/studyPlan'

/** 每学期学分**上限**（Review 指定硬规则）。 */
export const MAX_CREDIT_PER_TERM = 35

/** 除**最后毕业学期**外的学期，学分**尽量不低于**此值。 */
export const MIN_CREDIT_PER_TERM = 15

/** 安全阀：学期窗口最多扩展到这么多个学期。 */
const MAX_TERMS = 12

/**
 * 成绩单里的一条已修记录（`completed_input.records[]` 的最小子集）。
 *
 * ⚠️ 只取判定所需的三个字段；⛔ 不保留 `notes`（后端也已刻意不回传）。
 */
export interface CompletedCourseRecord {
  readonly course_name: string
  readonly credit: number | null
  readonly passed: boolean
}

/** 一门"正在修"的课（当前课表里的课程；课名用于兜底匹配）。 */
export interface InProgressCourse {
  readonly course_id: string
  readonly course_name?: string | null
}

/** 课程完成度五状态（⛔ 文案与语义见文件头「语义收敛」）。 */
export type CourseState =
  | 'completed'
  | 'in_progress'
  /** 后端明确判定为缺口（`required`）。 */
  | 'missing'
  /** 后端说需要人工确认。 */
  | 'need_confirmation'
  /**
   * **培养要求待覆盖**：培养方案要求存在，但当前成绩单/课表/匹配结果
   * **不足以判断是否需要补修**。⛔ 不代表系统已判断缺课。
   */
  | 'pending_coverage'

/** 每个状态的一行统计（课程数 + 学分）。 */
export interface CourseStateSummary {
  readonly state: CourseState
  readonly courseCount: number
  /** 已知学分之和；存在学分未知条目时为 `null`（⛔ 不用 0 冒充）。 */
  readonly credit: number | null
  /** 该状态里学分未知的条目数。 */
  readonly unknownCreditCount: number
  /** 是否进入未来学期排期。 */
  readonly scheduled: boolean
}

/** 按培养方案 `course_type` 归并的三类要求统计。 */
export interface CategorySummary {
  readonly key: 'required' | 'elective' | 'general'
  readonly label: string
  readonly totalCount: number
  readonly completedCount: number
  /** 专业选修按**学分**统计（培养方案给的是学分下限）。 */
  readonly requiredCredit: number | null
  readonly completedCredit: number | null
}

/**
 * 学分对账（Task 2 / 测试要求）。
 *
 * ⚠️ 只做**内部一致性核对**，⛔ 不代表学校认可的毕业结论。
 *
 * ⚠️ 语义收敛：**「待确认」与「待覆盖」必须分开计数**，
 *   ⛔ 不得合并成一个"待确认/待判定"数字 —— 两者含义不同：
 *   - 待确认：后端说需要人工确认（成绩单有记录/信息不足）；
 *   - 待覆盖：培养方案要求存在，但**当前依据不足以判断是否要补修**。
 */
export interface CreditReconciliation {
  readonly requiredTotalCredit: number | null
  readonly completedCredit: number | null
  readonly inProgressCredit: number | null
  /** 明确缺口（后端 `required`）。 */
  readonly missingCredit: number | null
  /** 待确认（后端 `manual_confirmation` / `possibly_equivalent`，未确认）。 */
  readonly needConfirmationCredit: number | null
  /** 培养要求待覆盖（成绩单/课表/匹配结果都不足以判断）。 */
  readonly pendingCoverageCredit: number | null
  /** 本轮**实际排入**未来学期的学分（= 明确缺口 + 待覆盖）。 */
  readonly plannedCredit: number | null
  /** `completed + inProgress + missing + needConfirmation + pendingCoverage`；缺数据时为 `null`。 */
  readonly accountedCredit: number | null
  /** 对账是否成立（差额为 0）。 */
  readonly balanced: boolean
  /** ⛔ 如实说明为什么对不上/对不上多少。 */
  readonly note: string | null
}

/** 派生结果。 */
export interface FutureRoadmapResult {
  /** 未来学期排期（课程级）。 */
  readonly semesters: FutureRoadmapSemester[]
  /** 被判定为**已完成**（因此排除在未来规划之外）的课程名。 */
  readonly satisfiedCourseNames: string[]
  /** 学生**当前课表里正在修**、因此排除在未来规划之外的课程名。 */
  readonly inProgressCourseNames: string[]
  /** 归类为"待确认"、因此**未排入任何学期**的课程。 */
  readonly needConfirmationCourses: FutureRoadmapCourse[]
  /** 归类为"培养要求待覆盖"、**已排入**未来学期的课程 —— 单独列出以保持透明。 */
  readonly pendingCoverageCourses: FutureRoadmapCourse[]
  /** 未来路径的起点学期（= 当前学期之后的第一个学期）。 */
  readonly startsFromTerm: string | null
  /** 当前学期代码（用于页面说明"当前学期不计入未来规划"）。 */
  readonly currentTerm: string
  /** 五状态统计（页面完成度展示的数据源）。 */
  readonly states: CourseStateSummary[]
  /** 分类别要求统计（毕业要求闭环摘要）。 */
  readonly categories: CategorySummary[]
  /** 学分对账。 */
  readonly reconciliation: CreditReconciliation
  /** 预计完成学期（最后一个有排期的学期）；无排期时为 `null`。 */
  readonly expectedCompletionTerm: string | null
  /** 排期口径说明（先修信息缺失时必须如实说明）。 */
  readonly orderingNote: string
  /**
   * 学分口径说明（Review：**保留精确值**，但对 0.5 学分课程给出解释）。
   *
   * 例：`体育` / `形势与政策` 按 0.5 学分计，因此学期合计会出现 19.5 这样的精确值。
   */
  readonly creditNote: string
}

/** 内部工作项。 */
interface PendingCourse {
  readonly course: FutureRoadmapCourse
  readonly requirement: StudyPlanRequirement
  /** `missing` = 后端明确判定缺口；`pending_coverage` = 培养要求待覆盖。 */
  readonly status: 'missing' | 'pending_coverage'
  /** 课程层级（同学期内排序用；⛔ 与先修无关）。 */
  readonly tier: CourseTier
}

/** 学期代码 `YYYY-N` → 中文标签（`2026-2` → 「2026秋」）。 */
export function termLabel(term: string): string {
  const match = /^(\d{4})-([12])(?:$)/.exec(term.trim())
  if (!match) return term
  const [, year, half] = match
  return `${year}${half === '1' ? '春' : '秋'}`
}

/**
 * 课程名归一化（**仅用于"同名"判定**，⛔ 不做等价性 / 学分 / 课程号判断）。
 *
 * 处理：全角括号 → 半角、罗马数字 → ASCII、去空白、去末尾"实验/实践"后缀、统一大小写。
 *
 * ⚠️ 只消除**纯格式差异**（`程序设计I` vs `程序设计Ⅰ`）；
 *   ⛔ 不做模糊匹配、⛔ 不做包含匹配 —— 那会制造错误的"已完成"。
 */
export function normalizeCourseName(name: string): string {
  return name
    .trim()
    .toUpperCase()
    .replace(/[（(]/g, '(')
    .replace(/[）)]/g, ')')
    .replace(/Ⅰ/g, 'I')
    .replace(/Ⅱ/g, 'II')
    .replace(/Ⅲ/g, 'III')
    .replace(/Ⅳ/g, 'IV')
    .replace(/\s+/g, '')
    .replace(/\((实验|实践)\)$/, '')
    .replace(/(实验|实践)$/, '')
}

/** 成绩单里"已通过"的课程名集合（归一化后）。 */
export function satisfiedNamesOf(completed: readonly CompletedCourseRecord[]): Set<string> {
  const names = new Set<string>()
  for (const record of completed) {
    // ⛔ 只有真的通过了才算已修；未通过的成绩单记录不构成"已完成"。
    if (!record.passed) continue
    names.add(normalizeCourseName(record.course_name))
  }
  return names
}

/** 把 `2026-1` 归一成 `{ year, half }`；无法解析时返回 null（⛔ 不猜学期）。 */
function parseTerm(term: string | null | undefined): { year: number; half: number } | null {
  if (typeof term !== 'string') return null
  const match = /^(\d{4})-([12])$/.exec(term.trim())
  if (!match) return null
  return { year: Number(match[1]), half: Number(match[2]) }
}

/** 求下一个学期代码（`2026-1` → `2026-2`）。 */
function nextTerm(term: string): string {
  const parsed = parseTerm(term)
  if (!parsed) return ''
  return parsed.half === 1 ? `${parsed.year}-2` : `${parsed.year + 1}-1`
}

/** 从 `start` 起生成 `count` 个连续学期。 */
function futureTerms(start: string, count: number): string[] {
  const parsed = parseTerm(start)
  if (!parsed) return []
  const terms: string[] = []
  let { year, half } = parsed
  for (let index = 0; index < count; index += 1) {
    terms.push(`${year}-${half}`)
    if (half === 1) half = 2
    else {
      half = 1
      year += 1
    }
  }
  return terms
}

/**
 * 按学期排期（确定性）。
 *
 * 顺序优先级（Task 5）：
 * 1. **大学分优先**（先放大课，避免小课塞满学期导致大课无处可放）；
 * 2. 同分时 `专业课`（专业核心）先于 `公必`（基础必修）；
 * 3. 再按课程号稳定排序。
 *
 * ⚠️ **先修关系**：真实培养方案**没有先修列**（`prerequisites_known=false`），
 *   因此⛔ 不按先修排 —— 这一点必须由 `orderingNote` 如实告知用户。
 *
 * 学期分配：有**仍在未来**的推荐学期 ⇒ 优先归位；否则放进"加上它之后负荷最轻、
 * 且不超上限"的学期；一个学期都放不下 ⇒ 继续往后开新学期（⛔ 绝不突破上限）。
 */
/**
 * 课程**层级**（用于同一学期内的顺序优化）。
 *
 * ⚠️ 层级**全部来自培养方案已有字段**，⛔ 不含任何先修假设：
 *
 * ```text
 * foundation  基础课程    ← course_type = 公必
 * core        核心专业课  ← course_type = 专业课
 * advanced    高级选修    ← requirement = elective（course_type = 专业选修课模块）
 * graduation  毕业环节    ← 课程名含 毕业论文 / 毕业设计 / 毕业实践
 * ```
 *
 * ⚠️ 培养方案**没有先修列**（`prerequisites_known` 全为 false），
 *   因此这里的顺序**只按课程类型**，⛔ 不代表先修关系；页面必须如实说明。
 */
export type CourseTier = 'foundation' | 'core' | 'advanced' | 'graduation'

/** 层级的展示顺序（数字越小越先修）。 */
const TIER_ORDER: Readonly<Record<CourseTier, number>> = {
  foundation: 0,
  core: 1,
  advanced: 2,
  graduation: 3,
}

/** 判定一门课程的层级。 */
export function courseTierOf(courseName: string, courseType: string | null, isElective: boolean): CourseTier {
  if (isGraduationCourse(courseName)) return 'graduation'
  if (isElective || courseType === '专业选修课模块') return 'advanced'
  if (courseType === '公必') return 'foundation'
  return 'core'
}

/**
 * 判定是否**毕业学期课程**（毕业论文 / 毕业设计 / 毕业实践）。
 *
 * ⚠️ 只按培养方案里的**课程名**识别这一件事（⛔ 不用于判定完成情况）。
 */
export function isGraduationCourse(courseName: string): boolean {
  return /毕业(论文|设计|实践)/.test(courseName ?? '')
}

/**
 * 重新分配剩余培养要求到未来学期（**不复制培养方案推荐学期**）。
 *
 * ## 算法（确定性）
 *
 * ```text
 * ① 候选池 = 明确缺口 + 培养要求待覆盖（学分已知者；⛔ 待确认不进池）
 * ② 毕业课（毕业论文/设计）单独取出，固定放最后一个学期
 * ③ 学期数 t 从 1 起尝试，取**最小**满足下列两条件的 t：
 *      上限：非毕业学分 <= t*MAX_CREDIT
 *      下限：(t-1) 个学期的容量 (t-1)*MAX_CREDIT 必须 >= 非毕业学分
 *            （否则比 t-1 个学期更集中于">= 15"目标，却被上限挡住）
 *    ⇒ 结果学期数最少，且每学期更容易达到 >= MIN_CREDIT_PER_TERM
 * ④ 均匀铺开：按学分降序，每次放入"当前负荷最轻"的学期（上限 35）
 * ⑤ 毕业课放进最后一个学期（该学期允许低于 15 学分）
 * ```
 *
 * ⚠️ 推荐学期 `recommended_term_text` **不再决定学期**，只在同分时作为稳定排序参考。
 */
function scheduleBalanced(
  start: string,
  courses: readonly PendingCourse[],
  maxCredit: number,
  minCredit: number,
): Map<string, PendingCourse[]> {
  const buckets = new Map<string, PendingCourse[]>()
  if (courses.length === 0) return buckets

  const graduation = courses.filter((item) => isGraduationCourse(item.course.course_name))
  const normal = courses.filter((item) => !isGraduationCourse(item.course.course_name))
  const normalCredit = normal.reduce((sum, item) => sum + (item.course.credit ?? 0), 0)

  // ③ 推导**最小学期数**：
  //    - 非毕业课需要 `ceil(非毕业学分 / 上限)` 个学期；
  //    - 毕业课单独占用最后一个学期（⛔ 不与普通课混在同一学期）。
  const normalTermCount =
    normalCredit === 0 ? 0 : Math.min(Math.max(Math.ceil(normalCredit / maxCredit), 1), MAX_TERMS)
  const hasGraduationTerm = graduation.length > 0
  const termCount = Math.min(
    Math.max(normalTermCount + (hasGraduationTerm ? 1 : 0), 1),
    MAX_TERMS,
  )

  const allTerms = futureTerms(start, termCount)
  if (allTerms.length === 0) return buckets
  // 毕业学期 = 最后一项；普通课只在前 `normalTermCount` 项里铺
  const graduationTerm = hasGraduationTerm ? allTerms[allTerms.length - 1] : null
  const normalTerms =
    graduationTerm === null ? allTerms : allTerms.slice(0, allTerms.length - 1)

  for (const term of allTerms) buckets.set(term, [])
  const loads = new Map<string, number>(allTerms.map((term) => [term, 0]))

  // ④ 非毕业课：大学分优先，放进"加上它不超上限、且当前最轻"的学期
  for (const item of [...normal].sort(compareCourses)) {
    const weight = item.course.credit ?? 0
    const roomy = normalTerms.filter((term) => (loads.get(term) ?? 0) + weight <= maxCredit)
    const target =
      roomy.sort(
        (left, right) =>
          (loads.get(left) ?? 0) - (loads.get(right) ?? 0) || (left < right ? -1 : 1),
      )[0] ??
      // 兜底：单课就超上限 ⇒ 仍放最轻的学期（⛔ 不丢课程）
      [...normalTerms].sort(
        (left, right) =>
          (loads.get(left) ?? 0) - (loads.get(right) ?? 0) || (left < right ? -1 : 1),
      )[0]
    buckets.get(target)!.push(item)
    loads.set(target, (loads.get(target) ?? 0) + weight)
  }

  // ⑤ 毕业课固定**最后学期**（该学期允许低于 `minCredit`）
  if (graduationTerm !== null) {
    for (const item of [...graduation].sort(compareCourses)) {
      buckets.get(graduationTerm)!.push(item)
      loads.set(graduationTerm, (loads.get(graduationTerm) ?? 0) + (item.course.credit ?? 0))
    }
  }

  void minCredit
  return buckets
}

/**
 * 课程排序比较器（Review 优化：**弱课程排序**）。
 *
 * 优先级（⛔ 只按课程类型，**不涉及先修关系**）：
 *
 * ```text
 * 基础课程 > 核心专业课 > 高级选修 > 毕业环节
 * ```
 *
 * 同层内：学分降序 → 课程号升序（保证**稳定**、可复核）。
 */
function compareCourses(left: PendingCourse, right: PendingCourse): number {
  const byTier = TIER_ORDER[left.tier] - TIER_ORDER[right.tier]
  if (byTier !== 0) return byTier
  const byCredit = (right.course.credit ?? 0) - (left.course.credit ?? 0)
  if (byCredit !== 0) return byCredit
  return left.course.course_id.localeCompare(right.course.course_id)
}

/** 裁成对外的课程级条目（⛔ 只保留课程号 / 课程名 / 学分）。 */
function toRoadmapCourse(course: FutureRoadmapCourse): FutureRoadmapCourse {
  return { course_id: course.course_id, course_name: course.course_name, credit: course.credit }
}

/** 已知学分之和；存在学分未知条目时为 `null`（⛔ 不用 0 冒充）。 */
function knownCreditOf(courses: readonly { credit?: number | null }[]): number | null {
  const credits = courses.map((course) => course.credit)
  if (credits.some((value) => typeof value !== 'number')) return null
  return (credits as number[]).reduce((sum, value) => sum + value, 0)
}

function unknownCreditCountOf(courses: readonly { credit?: number | null }[]): number {
  return courses.filter((course) => typeof course.credit !== 'number').length
}

const EMPTY_RESULT: FutureRoadmapResult = {
  semesters: [],
  satisfiedCourseNames: [],
  inProgressCourseNames: [],
  needConfirmationCourses: [],
  pendingCoverageCourses: [],
  startsFromTerm: null,
  currentTerm: '',
  states: [],
  categories: [],
  reconciliation: {
    requiredTotalCredit: null,
    completedCredit: null,
    inProgressCredit: null,
    missingCredit: null,
    needConfirmationCredit: null,
    pendingCoverageCredit: null,
    plannedCredit: null,
    accountedCredit: null,
    balanced: false,
    note: '缺少培养方案或学期信息，无法对账。',
  },
  expectedCompletionTerm: null,
  orderingNote: '',
  creditNote: '',
}

/**
 * 派生未来学习路径。
 *
 * @param plan               目标专业培养方案
 * @param makeupTasks        后端匹配结果
 * @param electiveProgress   后端选修组学分进度
 * @param currentSemester    当前学期代码（如 `2026-1`）
 * @param completed          成绩单已修课程（判定"已完成"的依据之一）
 * @param inProgress         当前课表里正在修的课程（⛔ 不等于已完成，但同样不重复排期）
 * @param confirmedCourseIds 学生**本人已确认**可转换的课程号（与 `makeupAnalysis` 同源）
 */
export function deriveFutureRoadmap(
  plan: StudyPlan | null,
  makeupTasks: readonly MakeupTask[],
  electiveProgress: readonly ElectiveProgress[],
  currentSemester: string,
  completed: readonly CompletedCourseRecord[] = [],
  inProgress: readonly InProgressCourse[] = [],
  confirmedCourseIds: readonly string[] = [],
): FutureRoadmapResult {
  const start = parseTerm(currentSemester)
  if (!plan || !start) return EMPTY_RESULT

  const satisfiedNames = satisfiedNamesOf(completed)
  const confirmed = new Set(confirmedCourseIds)
  const taskByCourseId = new Map(makeupTasks.map((task) => [task.course_id, task]))
  const inProgressIds = new Set(inProgress.map((item) => item.course_id))
  const inProgressNames = new Set(
    inProgress
      .map((item) => (item.course_name ? normalizeCourseName(item.course_name) : ''))
      .filter((name) => name !== ''),
  )

  /* ---------------------------------------------------------------------- *
   * ① 逐条培养要求分类（必修类）。
   * ---------------------------------------------------------------------- */
  const missing: PendingCourse[] = []
  const needConfirmation: FutureRoadmapCourse[] = []
  const pendingCoverageCourses: FutureRoadmapCourse[] = []
  const satisfiedCourseNames: string[] = []
  const inProgressCourseNames: string[] = []
  /** 分类用：courseId → 状态（选修也记，供分类别统计）。 */
  const stateByCourseId = new Map<string, CourseState>()

  for (const requirement of plan.requirements) {
    const isElective = requirement.requirement === 'elective'

    // 学分以**后端匹配结果**为准（那是这次判定用的学分）；
    // 没有任务时才退回培养方案上写的学分。
    // ⛔ 不能用培养方案的学分覆盖 `null` —— 那会把"学分未知"伪装成已知。
    const task = taskByCourseId.get(requirement.course_id)
    const credit = task ? task.credit : requirement.credit
    const entry: FutureRoadmapCourse = {
      course_id: requirement.course_id,
      course_name: requirement.course_name,
      credit,
    }
    // 课程层级（Review 优化）：只按培养方案已有字段判定，⛔ 不含先修假设。
    const tier = courseTierOf(requirement.course_name, requirement.course_type, isElective)

    // 优先级 1：已完成。
    // ⚠️ 学生本人确认（`confirmedCourseIds`）与 `makeupAnalysis` 同口径 ⇒ 视为已完成。
    const isSatisfied =
      satisfiedNames.has(normalizeCourseName(requirement.course_name)) ||
      task?.status === 'satisfied' ||
      confirmed.has(requirement.course_id)

    if (isSatisfied) {
      satisfiedCourseNames.push(requirement.course_name)
      stateByCourseId.set(requirement.course_id, 'completed')
      continue
    }

    // 优先级 2：进行中（已在本学期课表里）⇒ ⛔ 不重复排期。
    if (
      inProgressIds.has(requirement.course_id) ||
      inProgressNames.has(normalizeCourseName(requirement.course_name))
    ) {
      inProgressCourseNames.push(requirement.course_name)
      stateByCourseId.set(requirement.course_id, 'in_progress')
      continue
    }

    // 优先级 3：待确认（后端说需要人工确认，且学生还没确认）。
    if (task?.status === 'manual_confirmation' || task?.status === 'possibly_equivalent') {
      needConfirmation.push(entry)
      stateByCourseId.set(requirement.course_id, 'need_confirmation')
      continue
    }

    // 优先级 4：明确缺口（后端判定 required）。
    if (task?.status === 'required') {
      stateByCourseId.set(requirement.course_id, 'missing')
      if (!isElective) missing.push({ course: entry, requirement, status: 'missing', tier })
      continue
    }

    // 优先级 5：**培养要求待覆盖** —— 培养方案要求存在，但当前成绩单/课表/匹配结果
    // 「不足以判断是否需要补修」。⛔ 这不是"系统判断缺课"，只是"尚无依据"。
    // ⚠️ 它仍需按培养方案完成，因此进入排期；页面上单独计数、单独列出。
    pendingCoverageCourses.push(entry)
    stateByCourseId.set(requirement.course_id, 'pending_coverage')
    if (!isElective) missing.push({ course: entry, requirement, status: 'pending_coverage', tier })
  }

  /* ---------------------------------------------------------------------- *
   * ② 排期（**重新分配**，⛔ 不复制培养方案推荐学期）。
   *
   * 候选池 = 明确缺口 + 培养要求待覆盖（学分已知者）。
   * ⛔ 已完成 / 进行中 / 待确认都不进池（前两者已在前面被排除，待确认单独归类）。
   * ---------------------------------------------------------------------- */
  const firstTerm = nextTerm(currentSemester)
  // ⛔ 学分未知的课程**不排期**：不猜学分，也不让它静默占掉学期额度。
  //    （它们仍计入"待覆盖/缺口"的学分口径，只是不进学期。）
  const schedulable = missing.filter((item) => typeof item.course.credit === 'number')
  const buckets =
    parseTerm(firstTerm) === null
      ? new Map<string, PendingCourse[]>()
      : scheduleBalanced(firstTerm, schedulable, MAX_CREDIT_PER_TERM, MIN_CREDIT_PER_TERM)

  /* ---------------------------------------------------------------------- *
   * ③ 专业选修学分要求（口径见下）。
   * ---------------------------------------------------------------------- */
  // 「要多少」= 培养方案写明的选修组学分下限（**整份**方案额度）；
  // 「还缺多少」= 目标 − 后端 `elective_progress` 的已修学分。
  // 转专业时点前该组没有历史额度时，后端给 `required_credit=0 / remaining_credit=0`
  // 并附 `scope_note` —— 那是"该时点没有历史额度"，⛔ **不等于"已修满"**。
  const electiveTarget = plan.elective_pool.groups
    .map((group) => group.minimum_credit)
    .filter((value): value is number => typeof value === 'number' && value > 0)
    .reduce((sum, value) => sum + value, 0)
  const electiveEarned = electiveProgress
    .map((item) => item.earned_credit)
    .filter((value): value is number => typeof value === 'number')
    .reduce((sum, value) => sum + value, 0)
  const electiveRemaining = Math.max(electiveTarget - electiveEarned, 0)
  const hasElectiveGroup = plan.elective_pool.groups.length > 0

  /* ---------------------------------------------------------------------- *
   * ④ 组装学期排期。
   * ---------------------------------------------------------------------- */
  const semesters: FutureRoadmapSemester[] = []
  const termList = [...buckets.keys()]
  const lastTerm = termList[termList.length - 1]
  for (const term of termList) {
    const items = buckets.get(term) ?? []
    // ⚠️ 学期内按**课程层级**排序（基础 > 核心 > 高级选修 > 毕业环节），
    //    同层内学分降序、课程号升序 ⇒ 顺序稳定可复核。
    const ordered = [...items].sort(compareCourses)
    // ⚠️ 组内如实区分来源：后端判定的"缺失"与"无依据的待覆盖"⛔ 不混为一谈。
    const requiredCourses = ordered
      .filter((item) => item.status === 'missing')
      .map((item) => toRoadmapCourse(item.course))
    const pendingCoverageInTerm = ordered
      .filter((item) => item.status === 'pending_coverage')
      .map((item) => toRoadmapCourse(item.course))
    const total = knownCreditOf([...requiredCourses, ...pendingCoverageInTerm])
    const goals: string[] = []
    if (items.length > 0) goals.push(`完成 ${items.length} 门培养要求课程`)
    if (total !== null) goals.push(`修读约 ${total} 学分`)
    // ⚠️ 选修目标挂在**实际渲染的最后一个学期**（而不是窗口最后一项）。
    if (hasElectiveGroup && term === lastTerm) {
      goals.push(
        `专业选修组累计达到 ${electiveTarget} 学分（当前尚缺 ${electiveRemaining} 学分）`,
      )
    }
    semesters.push({
      semester: term,
      required: requiredCourses,
      pendingCoverage: pendingCoverageInTerm,
      makeup: [],
      expected_credit: total,
      completion_goals: goals,
    })
  }

  /* ---------------------------------------------------------------------- *
   * ⑤ 五状态统计 + 分类别要求统计 + 学分对账。
   * ---------------------------------------------------------------------- */
  const scheduledIds = new Set(
    [...buckets.values()].flat().map((item) => item.course.course_id),
  )
  const creditById = new Map<string, number | null>()
  for (const requirement of plan.requirements) {
    const task = taskByCourseId.get(requirement.course_id)
    creditById.set(requirement.course_id, task ? task.credit : requirement.credit)
  }
  const coursesOfState = (state: CourseState): StudyPlanRequirement[] =>
    plan.requirements.filter((requirement) => stateByCourseId.get(requirement.course_id) === state)

  const buildState = (state: CourseState, scheduled: boolean): CourseStateSummary => {
    const items = coursesOfState(state).map((requirement) => ({
      credit: creditById.get(requirement.course_id) ?? null,
    }))
    return {
      state,
      courseCount: items.length,
      credit: knownCreditOf(items),
      unknownCreditCount: unknownCreditCountOf(items),
      scheduled,
    }
  }

  const states: CourseStateSummary[] = [
    buildState('completed', false),
    buildState('in_progress', false),
    // 明确缺口：后端判定 required
    buildState('missing', true),
    // 待确认：后端说需要人工确认 ⇒ ⛔ 不排期
    buildState('need_confirmation', false),
    // 培养要求待覆盖：⛔ 不是"系统判断缺课"，而是"依据不足以判断"，因此仍需按方案完成
    buildState('pending_coverage', true),
  ]

  const requiredRequirements = plan.requirements.filter(
    (requirement) => requirement.requirement !== 'elective',
  )
  const categoryOf = (requirement: StudyPlanRequirement): CategorySummary['key'] =>
    requirement.course_type === '公必' ? 'general' : 'required'

  const categories: CategorySummary[] = [
    {
      key: 'required',
      label: '专业必修',
      totalCount: requiredRequirements.filter((item) => categoryOf(item) === 'required').length,
      completedCount: requiredRequirements.filter(
        (item) => categoryOf(item) === 'required' && stateByCourseId.get(item.course_id) === 'completed',
      ).length,
      requiredCredit: knownCreditOf(
        requiredRequirements.filter((item) => categoryOf(item) === 'required'),
      ),
      completedCredit: knownCreditOf(
        requiredRequirements
          .filter(
            (item) => categoryOf(item) === 'required' && stateByCourseId.get(item.course_id) === 'completed',
          )
          .map((item) => ({ credit: creditById.get(item.course_id) ?? null })),
      ),
    },
    {
      key: 'general',
      label: '公共必修',
      totalCount: requiredRequirements.filter((item) => categoryOf(item) === 'general').length,
      completedCount: requiredRequirements.filter(
        (item) => categoryOf(item) === 'general' && stateByCourseId.get(item.course_id) === 'completed',
      ).length,
      requiredCredit: knownCreditOf(
        requiredRequirements.filter((item) => categoryOf(item) === 'general'),
      ),
      completedCredit: knownCreditOf(
        requiredRequirements
          .filter(
            (item) => categoryOf(item) === 'general' && stateByCourseId.get(item.course_id) === 'completed',
          )
          .map((item) => ({ credit: creditById.get(item.course_id) ?? null })),
      ),
    },
    {
      key: 'elective',
      label: '专业选修',
      totalCount: plan.elective_pool.courses.length,
      completedCount: coursesOfState('completed').filter(
        (item) => item.requirement === 'elective',
      ).length,
      // ⚠️ 选修按**学分**考核，培养方案给的是学分下限（⛔ 不是课程门数）。
      requiredCredit: hasElectiveGroup ? electiveTarget : null,
      completedCredit: electiveProgress.length > 0 ? electiveEarned : null,
    },
  ]

  /*
   * ⚠️ 学分对账**只对必修类**（`requirement !== 'elective'`）。
   *    专业选修是按**学分下限**考核的另一个维度（见 `categories.elective`），
   *    把选修课学分混进必修口径会产生无意义的差额（实测踩过：差 4 学分）。
   */
  const requiredOnly = <T extends { course_id: string }>(items: T[]): T[] =>
    items.filter(
      (item) =>
        plan.requirements.find((entry) => entry.course_id === item.course_id)?.requirement !==
        'elective',
    )

  const creditOfCourses = (items: { course_id: string }[]): number | null =>
    knownCreditOf(
      requiredOnly(items).map((item) => ({ credit: creditById.get(item.course_id) ?? null })),
    )

  const requiredTotalCredit = knownCreditOf(requiredRequirements)
  const completedCredit = creditOfCourses(coursesOfState('completed'))
  const inProgressCredit = creditOfCourses(coursesOfState('in_progress'))
  // 明确缺口：后端判定 required（学分待核验的未排期，但仍属"缺口"口径）
  const missingCredit = creditOfCourses(coursesOfState('missing'))
  // 待确认：后端说需要人工确认 ⇒ ⛔ 不排期
  const needConfirmationCredit = creditOfCourses(coursesOfState('need_confirmation'))
  // 培养要求待覆盖：依据不足以判断 ⇒ 仍需按方案完成，已排期
  const pendingCoverageCredit = creditOfCourses(coursesOfState('pending_coverage'))
  // ⚠️ 「未来计划」= **实际排入学期**的学分 = 明确缺口 + 待覆盖
  //    （⛔ 不含待确认 —— 它没有依据、未排期）
  const plannedCredit = knownCreditOf(
    requiredOnly([...coursesOfState('missing'), ...coursesOfState('pending_coverage')])
      .filter((item) => scheduledIds.has(item.course_id))
      .map((item) => ({ credit: creditById.get(item.course_id) ?? null })),
  )

  // ⚠️ 对账口径 = 五种状态各算一次，⛔ 不重复计入学分待核验的未排期条目
  //    （它们已包含在 `missingCredit` / `pendingCoverageCredit` 里）。
  const parts = [
    completedCredit,
    inProgressCredit,
    missingCredit,
    needConfirmationCredit,
    pendingCoverageCredit,
  ]
  const accountedCredit = parts.some((value) => value === null)
    ? null
    : (parts as number[]).reduce((sum, value) => sum + value, 0)

  const reconciliationNote = ((): string | null => {
    if (requiredTotalCredit === null || accountedCredit === null) {
      return '部分课程学分待核验，因此无法给出学分对账（⛔ 不用 0 补齐）。'
    }
    const diff = Number((accountedCredit - requiredTotalCredit).toFixed(4))
    if (diff === 0) return null
    return `学分对账差额 ${diff} 学分：培养方案的学分可能包含未在本次判定范围内的条目，⛔ 不据此推断毕业结论。`
  })()

  const reconciliation: CreditReconciliation = {
    requiredTotalCredit,
    completedCredit,
    inProgressCredit,
    missingCredit,
    needConfirmationCredit,
    pendingCoverageCredit,
    plannedCredit,
    accountedCredit,
    balanced:
      requiredTotalCredit !== null &&
      accountedCredit !== null &&
      Math.abs(accountedCredit - requiredTotalCredit) < 1e-6,
    note: reconciliationNote,
  }

  /* ---------------------------------------------------------------------- *
   * ⑥ 排期口径说明（先修信息缺失时必须如实说明）。
   * ---------------------------------------------------------------------- */
  const prerequisitesKnown = plan.requirements.some(
    (requirement) => requirement.prerequisites_known,
  )
  const orderingNote = prerequisitesKnown
    ? '学期内顺序按课程层级（基础课程 > 核心专业课 > 高级选修 > 毕业环节）排列，并参考培养方案的先修关系。'
    : '培养方案未提供先修关系，仅按课程类型优化顺序：基础课程 > 核心专业课 > 高级选修 > 毕业环节。'

  // 学分口径：保留精确值；对 0.5 学分课程给出解释（⛔ 不做四舍五入，避免与对账不符）。
  const scheduledCourses = [...buckets.values()].flat().map((item) => item.course)
  const halfCreditCount = scheduledCourses.filter((course) => course.credit === 0.5).length
  const creditNote =
    halfCreditCount > 0
      ? `学分为培养方案原始精确值，未做四舍五入；其中 ${halfCreditCount} 门课程按 0.5 学分计（如体育、形势与政策类），因此学期合计可能出现 19.5 这样的数值。`
      : '学分为培养方案原始精确值，未做四舍五入。'

  return {
    semesters,
    satisfiedCourseNames,
    inProgressCourseNames,
    needConfirmationCourses: needConfirmation,
    pendingCoverageCourses,
    startsFromTerm: firstTerm,
    currentTerm: currentSemester,
    states,
    categories,
    reconciliation,
    expectedCompletionTerm: lastTerm ?? null,
    orderingNote,
    creditNote,
  }
}
