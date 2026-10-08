/**
 * AI 规划接口的**前端契约类型**（typed adapter 的唯一类型来源）。
 *
 * ⚠️ 这不是公共契约：`/schemas/` 与 `/docs/interfaces/` 未被修改。
 * 本文件只是一个**可能尚不存在**的后端接口的形状假设，逐字段说明见
 * `docs/final_upgrade/FRONTEND_AI_API_EXPECTATIONS.md`。
 *
 * 三条硬边界：
 * 1. 前端**不计算**规划：不做冲突检测、不选教学班、不生成候选；
 * 2. 前端**不伪造**成功：后端未实现 / 失败 / 过期时都如实显示，⛔ 不 fallback 到 fixture；
 * 3. 前端**不推断**未知字段：契约里没有的字段不会被"自动适配"出来。
 */

/** 数据来源标记：与后端风格一致（`mock` / `real`）。 */
export type AiPlanningDataSource = 'mock' | 'real'

/**
 * 文本生成方式。
 *
 * ⚠️ 取值与既有解释服务（`explanation-v1`）保持一致，避免两套词汇：
 * 未调用模型时必须是 `rule_based_template`，界面**不得**显示为 AI 生成。
 */
export type AiGeneratorKind =
  | 'model'
  | 'rule_based_template'
  | 'model_unavailable_fell_back_to_template'

/** 硬约束类型：不可协商（例如"某门课必须保留"）。 */
export interface AiHardConstraint {
  /** 机器可读的约束码，例如 `keep_course` / `complete_before` / `avoid_campus`。 */
  code: string
  /** 关联课程号；与课程无关的约束为 null。 */
  course_id: string | null
  course_name: string | null
  /** 用户原话片段（用于"这句话是从哪来的"）。 */
  raw_text: string
  /** 证据来源，例如 `utterance`（学生原话）。 */
  evidence: string
  /** 0..1；后端给出的解析置信度。 */
  confidence: number
}

/** 软偏好：可协商，求解时尽量满足。 */
export interface AiSoftPreference {
  code: string
  raw_text: string
  evidence: string
  confidence: number
}

/** 解析出的范围（时间 / 目标边界）。 */
export interface AiIntentScope {
  /** 本次调整针对的学期。 */
  semester: string
  /** `before_year_3` / `within_semester` / `unknown`（开放字符串，前端原样展示）。 */
  horizon: string
  raw_text: string
}

/** 解析不出来 / 需要学生补充的信息。 */
export interface AiIntentUnknown {
  topic: string
  detail: string
  needs_user_input: boolean
}

/**
 * 解析出的意图草稿（**第一次确认**的可编辑对象）。
 *
 * ⚠️ `credit_limit` 为 `null` 表示"用户没说"：界面必须显示"未指定"并要求确认，
 * ⛔ 前端不代填默认值（那会变成前端猜规则）。
 */
export interface AiParsedIntent {
  hard_constraints: AiHardConstraint[]
  soft_preferences: AiSoftPreference[]
  credit_limit: number | null
  locked_course_ids: string[]
  scope: AiIntentScope
  unknowns: AiIntentUnknown[]
}

/** 需要学生裁决的歧义 / 冲突。 */
export interface AiIntentAmbiguity {
  code: string
  detail: string
  options: string[]
}

export interface AiInterpretRequest {
  utterance: string
  /** 当前被调整方案的指纹；后端必须回显一致，否则视为过期。 */
  plan_digest: string
  target_semester: string
  /** 抽屉聚焦某门课时携带的课程上下文。 */
  focus_course_id?: string | null
  /**
   * ⚠️ 只传**计数**，不传课表明细：
   * 解析意图不需要把学生的整份课表送到模型侧。
   */
  current_schedule_count?: number
  locale?: string
}

export interface AiInterpretResponse {
  intent_id: string
  plan_digest: string
  data_source: AiPlanningDataSource
  generator_kind: AiGeneratorKind
  /** `false` ⇒ 前端**禁止**进入求解（解析不足）。 */
  can_confirm: boolean
  parsed_intent: AiParsedIntent
  ambiguities: AiIntentAmbiguity[]
  message: string
}

export interface AiSolveRequest {
  intent_id: string
  plan_digest: string
  /** 用户**第一次确认**之后的最终意图（可能被编辑过）。 */
  confirmed_intent: AiParsedIntent
  semester: string
}

/** 候选与原方案的差异。 */
export interface AiPlanDiffEntry {
  course_id: string
  course_name: string
  class_id: string
  credit: number
}

export interface AiPlanDiffMove {
  course_id: string
  from_class: string | null
  to_class: string | null
  reason: string
}

export interface AiHardConstraintCheck {
  code: string
  course_id: string | null
  satisfied: boolean
  detail: string
}

export interface AiPlanDiff {
  added: AiPlanDiffEntry[]
  removed: AiPlanDiffEntry[]
  moved: AiPlanDiffMove[]
  credit_delta: number
  hard_constraint_checks: AiHardConstraintCheck[]
}

/**
 * 求解状态（前端必须分别显示，⛔ 不得都写成"没生成"）。
 *
 * - `candidate`：成功，有候选方案；
 * - `infeasible`：当前约束下**无解**；
 * - `unavailable`：缺少必要条件（课表 / Planner / 模型不可用）；
 * - `rejected`：输入被拒绝（意图过期 / 违反硬约束）。
 */
export type AiSolveStatus = 'candidate' | 'infeasible' | 'unavailable' | 'rejected'

/** 候选方案里的计划，形状与公共 `PlanResult` 一致（前端不重新解释它）。 */
export interface AiCandidatePlan {
  status: string
  selected_classes: { course_id: string; class_id: string }[]
  changes: {
    course_id: string
    from_class?: string | null
    to_class?: string | null
    reason: string
  }[]
  risks: { course_id?: string | null; level: string; reason: string }[]
  unresolved: { type: string; message: string }[]
  objective_summary?: string | null
}

export interface AiSolveResponse {
  candidate_id: string | null
  status: AiSolveStatus
  /** 仅 `status = candidate` 时非 null。 */
  candidate_plan: AiCandidatePlan | null
  plan_digest: string
  candidate_digest: string | null
  diff: AiPlanDiff | null
  risks: { course_id?: string | null; level: string; reason: string }[]
  unresolved: { type: string; message: string }[]
  message: string
  /** ISO8601 或 null；非空且已过期时 adopt 必须回答 `stale_candidate`。 */
  expires_at: string | null
}

export interface AiAdoptRequest {
  candidate_id: string
  plan_digest: string
  candidate_digest: string
  /** `true` = 采用候选；`false` = 明确保留原方案（仍由后端确认）。 */
  accept: boolean
}

/** 采用状态：只有 `adopted` 才允许刷新当前方案。 */
export type AiAdoptStatus = 'adopted' | 'rejected' | 'stale_candidate' | 'unavailable'

export interface AiAdoptResponse {
  status: AiAdoptStatus
  adopted_plan: AiCandidatePlan | null
  adopted_digest: string | null
  result_version: string | null
  message: string
}

/** 请求失败分类；UI 只按 `kind` 分支。 */
export type AiPlanningErrorKind =
  | 'disabled'
  | 'not_configured'
  | 'input'
  | 'conflict'
  | 'unavailable'
  | 'server'
  | 'network'
  | 'unexpected'

/** 适配层返回的成功结果：附带**数据是否来自前端预览 fixture**的明确标记。 */
export interface AiPlanningEnvelope<T> {
  data: T
  /** `preview_fixture` 表示"仅前端预览"，界面必须醒目标注。 */
  source: 'backend' | 'preview_fixture'
  /** 预览模式下的固定说明文案。 */
  previewNotice: string | null
}
