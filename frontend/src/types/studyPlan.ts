/**
 * **专业 / 培养方案**接口的响应类型（`/api/v1/majors`、`/api/v1/study-plans/{major_id}`）。
 *
 * ⚠️ 这是**前端集成类型**，对应后端 `app/api/study_plan.py` 的响应体，
 *   ⛔ 不是公共 `/schemas/*.schema.json` 契约的一部分
 *   （公共契约只有 Course / CourseOffering / MakeupTask / PlanResult / Preference）。
 */

/** `GET /api/v1/majors` 列表项。 */
export interface MajorSummary {
  readonly major_id: string
  readonly name: string
  readonly cohort: string
  readonly version_id: string
  readonly source_id: string
}

/** 一条培养方案要求。 */
export interface StudyPlanRequirement {
  readonly course_id: string
  readonly course_name: string
  readonly credit: number
  /** `required` = 必修；`elective` = 专业选修；`unknown` = 来源未标明。 */
  readonly requirement: 'required' | 'elective' | 'unknown'
  readonly course_type: string | null
  readonly group_id: string | null
  readonly recommended_term_text: string | null
  /** `null` 表示**来源没有先修信息** —— ⛔ 不等于"无先修"。 */
  readonly prerequisites: readonly string[] | null
  /** `false` 表示先修关系未知（真实 docx 无先修列时恒为 false）。 */
  readonly prerequisites_known: boolean
  readonly source_record: string
}

/** 专业选修组。 */
export interface StudyPlanElectiveGroup {
  readonly group_id: string
  readonly name: string
  readonly minimum_credit: number | null
  readonly source_record: string
}

/** `GET /api/v1/study-plans/{major_id}` 响应体。 */
export interface StudyPlan {
  readonly major_id: string
  readonly name: string
  readonly cohort: string
  readonly version_id: string
  readonly source_id: string
  readonly complete: boolean
  readonly completeness_evidence: string | null
  readonly total_credit: number | null
  readonly counts: {
    readonly total: number
    readonly required: number
    readonly elective: number
    readonly unknown: number
    /** 先修关系未知的条目数（⛔ 不是"无先修"）。 */
    readonly prerequisites_unknown: number
  }
  readonly requirements: readonly StudyPlanRequirement[]
  readonly elective_pool: {
    readonly groups: readonly StudyPlanElectiveGroup[]
    readonly courses: readonly StudyPlanRequirement[]
  }
}

/**
 * 课程组学分进度（Phase 4）。
 *
 * ⚠️ 由**后端 matching 层**下发（`/case-a-demo/plan` 的 `elective_progress`），
 *   ⛔ 前端不得自行计算剩余学分 —— 那是判定口径，必须与"谁该补修"同源。
 *
 * `undecided=true` 表示该组历史额度未确认，三个数字均为 `null`。
 */
export interface ElectiveProgress {
  readonly group_id: string
  readonly group_name: string
  readonly required_credit: number | null
  readonly earned_credit: number | null
  readonly remaining_credit: number | null
  readonly undecided: boolean
  /**
   * 为什么 `required_credit` 与培养方案写明的学分下限不同。
   *
   * ⚠️ 由**后端**给出（⛔ 不在前端硬编码解释）。
   * 例：该组课程全部安排在转专业时点之后 ⇒ 历史额度为 0。
   */
  readonly scope_note?: string | null
}

/** 接口失败的可判别错误。 */
export class StudyPlanApiError extends Error {
  readonly status: number | null
  readonly code: string | null

  constructor(message: string, status: number | null, code: string | null) {
    super(message)
    this.name = 'StudyPlanApiError'
    this.status = status
    this.code = code
  }

  /** 运行时未配置专业注册表（503 + `majors_not_configured`）。 */
  get isNotConfigured(): boolean {
    return this.code === 'majors_not_configured'
  }

  /** 请求的 major_id 不在注册表里。 */
  get isUnknownMajor(): boolean {
    return this.code === 'unknown_major'
  }

  /** 网络层失败（没有 HTTP 响应）。 */
  get isNetworkFailure(): boolean {
    return this.status === null
  }
}
