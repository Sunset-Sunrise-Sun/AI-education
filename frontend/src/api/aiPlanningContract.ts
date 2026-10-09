/**
 * AI 规划接口的**后端真实契约**类型与解析器。
 *
 * 单一契约来源：`feature/deepseek-planning-controller` 分支的
 * `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md`
 * （与 `backend/app/api/ai_planning.py` 同一提交，逐字段对应）。
 *
 * ⚠️ 这不是公共契约：`/schemas/` 与 `/docs/interfaces/` 未被修改。
 *
 * 五条与旧预期不同的关键事实（PR #65 Architecture Review BLOCKER）：
 *
 * 1. `interpret` **请求**只有 `context` + `user_message`：
 *    `plan_digest` 由**后端**根据上下文计算，前端⛔ 不发送、只**原样回传**；
 * 2. `solve` 的成功状态是 **`candidate_ready`**（另有 `no_feasible_candidate` / `blocked`），
 *    不是 `candidate`；
 * 3. `adopt` 返回 `accepted` / `state` / `adopted_version` / `adopted_version_scope`，
 *    **不返回 `adopted_plan`** —— 前端⛔ 不得伪造方案体，只能采用内存中已有的候选；
 * 4. `adopted_version_scope = process_local_session` 表示**进程内会话状态**，
 *    不是持久保存、更不是教务系统选课成功；
 * 5. `generator_kind` 只有三种：`deepseek_live` / `test_double` / `unavailable`。
 */

import type {
  CourseOffering,
  MakeupTask,
  PlanResult,
  Preference,
} from '../types/contracts'

/** 后端固定前缀。 */
export const AI_PLANNING_PREFIX = '/api/v1/ai-planning'

/** `generator_kind`：后端只有这三种取值（⛔ 不得新增或改写）。 */
export const GENERATOR_KINDS = ['deepseek_live', 'test_double', 'unavailable'] as const
export type AiGeneratorKind = (typeof GENERATOR_KINDS)[number]

/** `data_source`：由**教学班自身**的 data_source 判定，与页面模式无关。 */
export const DATA_SOURCES = ['real', 'mock', 'mixed', 'unknown'] as const
export type AiDataSource = (typeof DATA_SOURCES)[number]

/** `solve` 的固定状态取值。 */
export const SOLVE_STATUSES = ['candidate_ready', 'no_feasible_candidate', 'blocked'] as const
export type AiSolveStatus = (typeof SOLVE_STATUSES)[number]

/** `adopt` 的状态取值。 */
export type AiAdoptState = 'adopted' | 'rejected'

/** 调整范围：当前后端只支持当前学期。 */
export const ADJUSTMENT_SCOPE_CURRENT_SEMESTER = 'current_semester'
export const ADJUSTMENT_SCOPE_UNSUPPORTED = 'future_semesters'

/** `adopted_version_scope`：唯一已知取值（进程内会话）。 */
export const ADOPTED_VERSION_SCOPE_PROCESS_LOCAL = 'process_local_session'

/** 硬约束 / 软偏好的 `kind` 白名单。 */
export const HARD_CONSTRAINT_KINDS = [
  'max_credit_limit',
  'lock_course',
  'exclude_course',
] as const
export const SOFT_PREFERENCE_KINDS = [
  'avoid_weekday',
  'prefer_fewer_credits',
  'prefer_keep_prerequisites',
] as const

/** 后端固定歧义码（用于把"必须由用户回答"的问题显示清楚）。 */
export const AMBIGUITY_CODES = [
  'credit_limit_missing_evidence',
  'credit_limit_conflicts_with_declared_max',
  'locked_course_unknown',
  'target_course_unknown',
  'target_class_unknown',
  'adjustment_scope_ambiguous',
  'adjustment_scope_unsupported',
  'constraint_kind_unknown',
  'soft_preference_not_executable',
  'no_adjustable_target',
] as const

/** 固定 `blocked_reason` 前缀（后端可能带上下文后缀，例如 `: ValueError`）。 */
export const BLOCKED_REASONS = [
  'planner_not_configured',
  'planner_rejected_input',
  'locked_course_would_change',
  'candidate_references_unavailable_class',
  'exclude_course_hard_constraint_not_supported_by_frozen_planner',
  'cross_semester_adjustment_not_supported',
] as const

// --------------------------------------------------------------------------- //
// 请求
// --------------------------------------------------------------------------- //

/** `POST /interpret` 的 `context`：只打包**现有公共对象**。 */
export interface AiPlanContext {
  semester: string
  base_plan: PlanResult
  makeup_tasks: MakeupTask[]
  course_offerings: CourseOffering[]
  preference: Preference
}

/**
 * `POST /interpret` 请求体。
 *
 * ⚠️ **没有** `plan_digest`：它由后端按上下文计算（后端 `extra=forbid`，
 * 多传字段会被 422 拒绝）。
 */
export interface AiInterpretRequest {
  context: AiPlanContext
  user_message: string
}

/** 一条硬约束（`kind` 必须在白名单内；`max_credit_limit` 必须带 `evidence`）。 */
export interface AiHardConstraint {
  kind: string
  value: number | string | null
  evidence?: string
}

export interface AiSoftPreference {
  kind: string
  value: number | string | null
  note?: string | null
}

export interface AiLockedCourse {
  course_id: string
  class_id: string
  reason: string
}

/** `interpret` 响应中的 `parsed_intent`（草稿）。 */
export interface AiParsedIntentDraft {
  summary: string
  scope: string
  target_semester: string | null
  hard_constraints: AiHardConstraint[]
  soft_preferences: AiSoftPreference[]
  locked_courses: AiLockedCourse[]
  confidence: number
  notes: string[]
  ambiguities: AiAmbiguity[]
}

export interface AiAmbiguity {
  code: string
  question: string
  detail: string | null
}

export interface AiTokenUsageEstimate {
  prompt: number
  completion: number
  total: number
}

/** `POST /interpret` 响应。 */
export interface AiInterpretResponse {
  intent_id: string
  /** 后端计算；前端只保存并**原样回传**，⛔ 不解析、不重算。 */
  plan_digest: string
  parsed_intent: AiParsedIntentDraft
  ambiguities: AiAmbiguity[]
  data_source: AiDataSource
  generator_kind: AiGeneratorKind
  generator_note: string
  model_id: string
  can_confirm: boolean
  state: string
  token_usage_estimate: AiTokenUsageEstimate
  message: string
}

/** 前端可编辑后回传的"已确认意图"（后端 `ConfirmedIntent` 的线格式）。 */
export interface AiConfirmedIntent {
  plan_digest: string
  semester: string
  scope: string
  target_semester: string | null
  hard_constraints: AiHardConstraint[]
  soft_preferences: AiSoftPreference[]
  locked_courses: AiLockedCourse[]
  user_note?: string | null
}

/** `POST /solve` 请求体（只有用户确认后才调用）。 */
export interface AiSolveRequest {
  intent_id: string
  plan_digest: string
  confirmed_intent: AiConfirmedIntent
}

/** `diff`：由后端**确定性**计算（⛔ 不来自模型）。 */
export interface AiPlanDiffEntry {
  course_id: string
  class_id: string
}

export interface AiPlanDiff {
  added: AiPlanDiffEntry[]
  removed: AiPlanDiffEntry[]
  replaced: AiPlanDiffEntry[]
  kept: AiPlanDiffEntry[]
  base_credit: number | null
  candidate_credit: number | null
  credit_delta: number | null
  credit_unknown_course_ids: string[]
  empty: boolean
}

/** `POST /solve` 响应。 */
export interface AiSolveResponse {
  candidate_id: string | null
  status: AiSolveStatus
  /** `PlanResult` 或 `none`。 */
  plan_kind: string
  /** 只有 `status=candidate_ready` 时非 null。 */
  candidate_plan: PlanResult | null
  diff: AiPlanDiff | null
  /** ⚠️ 字符串数组（不是对象数组）。 */
  risks: string[]
  unresolved: string[]
  message: string
  blocked_reason: string | null
  data_source: AiDataSource
  generator_kind: AiGeneratorKind
  plan_digest: string
}

/** `POST /adopt` 请求体（⛔ 没有 `candidate_digest`）。 */
export interface AiAdoptRequest {
  candidate_id: string
  plan_digest: string
  accept: boolean
}

/**
 * `POST /adopt` 响应。
 *
 * ⚠️ **没有** `adopted_plan`：被采用的方案体必须来自前端内存中
 * `/solve` 已返回的候选；⛔ 不得伪造、⛔ 不得用原方案冒充候选。
 */
export interface AiAdoptResponse {
  candidate_id: string
  accepted: boolean
  state: AiAdoptState
  /** 进程内会话版本号（int）。 */
  adopted_version: number
  /** `process_local_session`：仅进程内有效，未持久化。 */
  adopted_version_scope: string
  original_plan_unchanged: boolean
  plan_digest: string
  message: string
}

/** `GET /status` 响应（⛔ 不含密钥）。 */
export interface AiPlanningStatusResponse {
  enabled: boolean
  live_model_available: boolean
  api_key_configured: boolean
  model: string
  base_url: string
  max_calls_per_request: number
  request_timeout_seconds: number
  adopt_ttl_seconds: number
  generator_kind_when_live: string
  data_source_note: string
}

// --------------------------------------------------------------------------- //
// 解析（严格：缺字段 / 类型不符 / 枚举越界 ⇒ 抛 ContractViolation）
// --------------------------------------------------------------------------- //

/** 响应形状不符合后端契约（**不可**补默认值）。 */
export class ContractViolation extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ContractViolation'
  }
}

function asObject(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ContractViolation(`${field} 必须是对象`)
  }
  return value as Record<string, unknown>
}

function asString(value: unknown, field: string): string {
  if (typeof value !== 'string') {
    throw new ContractViolation(`${field} 必须是字符串`)
  }
  return value
}

function asNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new ContractViolation(`${field} 必须是数字`)
  }
  return value
}

function asBoolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') {
    throw new ContractViolation(`${field} 必须是布尔值`)
  }
  return value
}

function asNullableNumber(value: unknown, field: string): number | null {
  if (value === null || value === undefined) {
    return null
  }
  return asNumber(value, field)
}

function asStringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) {
    throw new ContractViolation(`${field} 必须是数组`)
  }
  return value.map((item, index) => asString(item, `${field}[${index}]`))
}

function asObjectArray(value: unknown, field: string): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    throw new ContractViolation(`${field} 必须是数组`)
  }
  return value.map((item, index) => asObject(item, `${field}[${index}]`))
}

function asEnum<T extends string>(value: unknown, field: string, allowed: readonly T[]): T {
  const text = asString(value, field)
  if (!(allowed as readonly string[]).includes(text)) {
    throw new ContractViolation(`${field} 取值越界（后端契约只允许 ${allowed.join(' / ')}）`)
  }
  return text as T
}

/** 解析 `generator_kind`（⛔ 未知取值拒绝，避免把未知状态显示成"AI 已接入"）。 */
export function parseGeneratorKind(value: unknown): AiGeneratorKind {
  return asEnum(value, 'generator_kind', GENERATOR_KINDS)
}

export function parseDataSource(value: unknown): AiDataSource {
  return asEnum(value, 'data_source', DATA_SOURCES)
}

function parseAmbiguity(row: Record<string, unknown>, index: number): AiAmbiguity {
  return {
    code: asString(row['code'], `ambiguities[${index}].code`),
    question: asString(row['question'], `ambiguities[${index}].question`),
    detail:
      row['detail'] === null || row['detail'] === undefined
        ? null
        : asString(row['detail'], `ambiguities[${index}].detail`),
  }
}

function parseHardConstraint(row: Record<string, unknown>, index: number): AiHardConstraint {
  const value = row['value']
  if (value !== null && value !== undefined && typeof value !== 'number' && typeof value !== 'string') {
    throw new ContractViolation(`hard_constraints[${index}].value 类型非法`)
  }
  const evidence = row['evidence']
  if (evidence !== null && evidence !== undefined && typeof evidence !== 'string') {
    throw new ContractViolation(`hard_constraints[${index}].evidence 类型非法`)
  }
  return {
    kind: asString(row['kind'], `hard_constraints[${index}].kind`),
    value: (value ?? null) as number | string | null,
    ...(evidence === null || evidence === undefined ? {} : { evidence: evidence as string }),
  }
}

function parseSoftPreference(row: Record<string, unknown>, index: number): AiSoftPreference {
  const value = row['value']
  if (value !== null && value !== undefined && typeof value !== 'number' && typeof value !== 'string') {
    throw new ContractViolation(`soft_preferences[${index}].value 类型非法`)
  }
  const note = row['note']
  if (note !== null && note !== undefined && typeof note !== 'string') {
    throw new ContractViolation(`soft_preferences[${index}].note 类型非法`)
  }
  return {
    kind: asString(row['kind'], `soft_preferences[${index}].kind`),
    value: (value ?? null) as number | string | null,
    note: (note ?? null) as string | null,
  }
}

function parseLockedCourse(row: Record<string, unknown>, index: number): AiLockedCourse {
  return {
    course_id: asString(row['course_id'], `locked_courses[${index}].course_id`),
    class_id: asString(row['class_id'], `locked_courses[${index}].class_id`),
    reason: asString(row['reason'], `locked_courses[${index}].reason`),
  }
}

/** 解析 `parsed_intent`（草稿）。 */
export function parseParsedIntent(value: unknown): AiParsedIntentDraft {
  const record = asObject(value, 'parsed_intent')
  const targetSemester = record['target_semester']
  if (targetSemester !== null && targetSemester !== undefined && typeof targetSemester !== 'string') {
    throw new ContractViolation('parsed_intent.target_semester 类型非法')
  }
  return {
    summary: asString(record['summary'], 'parsed_intent.summary'),
    scope: asString(record['scope'], 'parsed_intent.scope'),
    target_semester: (targetSemester ?? null) as string | null,
    hard_constraints: asObjectArray(record['hard_constraints'], 'parsed_intent.hard_constraints').map(
      parseHardConstraint,
    ),
    soft_preferences: asObjectArray(
      record['soft_preferences'],
      'parsed_intent.soft_preferences',
    ).map(parseSoftPreference),
    locked_courses: asObjectArray(record['locked_courses'], 'parsed_intent.locked_courses').map(
      parseLockedCourse,
    ),
    confidence: asNumber(record['confidence'], 'parsed_intent.confidence'),
    notes: asStringArray(record['notes'], 'parsed_intent.notes'),
    ambiguities: asObjectArray(record['ambiguities'], 'parsed_intent.ambiguities').map(
      parseAmbiguity,
    ),
  }
}

/** 解析 `POST /interpret` 响应。 */
export function parseInterpretResponse(payload: unknown): AiInterpretResponse {
  const record = asObject(payload, 'interpret 响应')
  const usage = asObject(record['token_usage_estimate'], 'token_usage_estimate')
  return {
    intent_id: asString(record['intent_id'], 'intent_id'),
    plan_digest: asString(record['plan_digest'], 'plan_digest'),
    parsed_intent: parseParsedIntent(record['parsed_intent']),
    ambiguities: asObjectArray(record['ambiguities'], 'ambiguities').map(parseAmbiguity),
    data_source: parseDataSource(record['data_source']),
    generator_kind: parseGeneratorKind(record['generator_kind']),
    generator_note: asString(record['generator_note'], 'generator_note'),
    model_id: asString(record['model_id'], 'model_id'),
    can_confirm: asBoolean(record['can_confirm'], 'can_confirm'),
    state: asString(record['state'], 'state'),
    token_usage_estimate: {
      prompt: asNumber(usage['prompt'], 'token_usage_estimate.prompt'),
      completion: asNumber(usage['completion'], 'token_usage_estimate.completion'),
      total: asNumber(usage['total'], 'token_usage_estimate.total'),
    },
    message: asString(record['message'], 'message'),
  }
}

function parseDiffEntry(row: Record<string, unknown>, index: number, field: string): AiPlanDiffEntry {
  return {
    course_id: asString(row['course_id'], `${field}[${index}].course_id`),
    class_id: asString(row['class_id'], `${field}[${index}].class_id`),
  }
}

/** 解析 `diff`。 */
export function parsePlanDiff(value: unknown): AiPlanDiff {
  const record = asObject(value, 'diff')
  return {
    added: asObjectArray(record['added'], 'diff.added').map((row, i) =>
      parseDiffEntry(row, i, 'diff.added'),
    ),
    removed: asObjectArray(record['removed'], 'diff.removed').map((row, i) =>
      parseDiffEntry(row, i, 'diff.removed'),
    ),
    replaced: asObjectArray(record['replaced'], 'diff.replaced').map((row, i) =>
      parseDiffEntry(row, i, 'diff.replaced'),
    ),
    kept: asObjectArray(record['kept'], 'diff.kept').map((row, i) =>
      parseDiffEntry(row, i, 'diff.kept'),
    ),
    base_credit: asNullableNumber(record['base_credit'], 'diff.base_credit'),
    candidate_credit: asNullableNumber(record['candidate_credit'], 'diff.candidate_credit'),
    credit_delta: asNullableNumber(record['credit_delta'], 'diff.credit_delta'),
    credit_unknown_course_ids: asStringArray(
      record['credit_unknown_course_ids'] ?? [],
      'diff.credit_unknown_course_ids',
    ),
    empty: asBoolean(record['empty'], 'diff.empty'),
  }
}

/** 解析 `POST /solve` 响应，并校验"状态与内容必须一致"。 */
export function parseSolveResponse(payload: unknown): AiSolveResponse {
  const record = asObject(payload, 'solve 响应')
  const status = asEnum(record['status'], 'status', SOLVE_STATUSES)
  const candidateIdRaw = record['candidate_id']
  const candidateId =
    candidateIdRaw === null || candidateIdRaw === undefined
      ? null
      : asString(candidateIdRaw, 'candidate_id')
  const candidatePlanRaw = record['candidate_plan']
  const candidatePlan =
    candidatePlanRaw === null || candidatePlanRaw === undefined
      ? null
      : (asObject(candidatePlanRaw, 'candidate_plan') as unknown as PlanResult)
  const diffRaw = record['diff']
  const diff = diffRaw === null || diffRaw === undefined ? null : parsePlanDiff(diffRaw)
  const blockedRaw = record['blocked_reason']

  const response: AiSolveResponse = {
    candidate_id: candidateId,
    status,
    plan_kind: asString(record['plan_kind'], 'plan_kind'),
    candidate_plan: candidatePlan,
    diff,
    risks: asStringArray(record['risks'] ?? [], 'risks'),
    unresolved: asStringArray(record['unresolved'] ?? [], 'unresolved'),
    message: asString(record['message'], 'message'),
    blocked_reason:
      blockedRaw === null || blockedRaw === undefined ? null : asString(blockedRaw, 'blocked_reason'),
    data_source: parseDataSource(record['data_source']),
    generator_kind: parseGeneratorKind(record['generator_kind']),
    plan_digest: asString(record['plan_digest'], 'plan_digest'),
  }

  // ⚠️ 状态与内容一致性：⛔ 不接受"有候选但状态不是 candidate_ready"，
  //    也⛔ 不接受"candidate_ready 却没有候选 / diff"。
  if (status === 'candidate_ready') {
    if (candidateId === null || candidatePlan === null || diff === null) {
      throw new ContractViolation(
        '后端 status=candidate_ready 但缺少 candidate_id / candidate_plan / diff',
      )
    }
  } else if (candidatePlan !== null) {
    throw new ContractViolation(`后端 status=${status} 却带有 candidate_plan（状态与内容矛盾）`)
  }

  return response
}

/** 解析 `POST /adopt` 响应。 */
export function parseAdoptResponse(payload: unknown): AiAdoptResponse {
  const record = asObject(payload, 'adopt 响应')
  const scope = asString(record['adopted_version_scope'], 'adopted_version_scope')
  if (scope !== ADOPTED_VERSION_SCOPE_PROCESS_LOCAL) {
    throw new ContractViolation(
      `adopted_version_scope 取值越界（后端当前只返回 ${ADOPTED_VERSION_SCOPE_PROCESS_LOCAL}）`,
    )
  }
  return {
    candidate_id: asString(record['candidate_id'], 'candidate_id'),
    accepted: asBoolean(record['accepted'], 'accepted'),
    state: asEnum(record['state'], 'state', ['adopted', 'rejected'] as const),
    adopted_version: asNumber(record['adopted_version'], 'adopted_version'),
    adopted_version_scope: scope,
    original_plan_unchanged: asBoolean(
      record['original_plan_unchanged'],
      'original_plan_unchanged',
    ),
    plan_digest: asString(record['plan_digest'], 'plan_digest'),
    message: asString(record['message'], 'message'),
  }
}

/** 解析 `GET /status` 响应（⛔ 响应里没有密钥）。 */
export function parseStatusResponse(payload: unknown): AiPlanningStatusResponse {
  const record = asObject(payload, 'status 响应')
  return {
    enabled: asBoolean(record['enabled'], 'enabled'),
    live_model_available: asBoolean(record['live_model_available'], 'live_model_available'),
    api_key_configured: asBoolean(record['api_key_configured'], 'api_key_configured'),
    model: asString(record['model'], 'model'),
    base_url: asString(record['base_url'], 'base_url'),
    max_calls_per_request: asNumber(record['max_calls_per_request'], 'max_calls_per_request'),
    request_timeout_seconds: asNumber(record['request_timeout_seconds'], 'request_timeout_seconds'),
    adopt_ttl_seconds: asNumber(record['adopt_ttl_seconds'], 'adopt_ttl_seconds'),
    generator_kind_when_live: asString(
      record['generator_kind_when_live'],
      'generator_kind_when_live',
    ),
    data_source_note: asString(record['data_source_note'], 'data_source_note'),
  }
}

/** 把草稿解析成**可回传**的 `ConfirmedIntent`（前端只做结构搬运与本地编辑合并）。 */
export function parseConfirmedIntent(
  draft: AiParsedIntentDraft,
  overrides: {
    planDigest: string
    semester: string
    creditLimit?: number | null
    userNote?: string | null
  },
): AiConfirmedIntent {
  const hard = draft.hard_constraints
    .filter((item) => item.kind !== 'max_credit_limit')
    .map((item) => ({ ...item }))

  // ⚠️ 学分上限只能由**用户明确给出数字**：这里只接受 overrides 的值，
  //    ⛔ 不从 summary / 软偏好里猜，⛔ 不沿用模型自己编的数字。
  if (overrides.creditLimit !== null && overrides.creditLimit !== undefined) {
    hard.push({
      kind: 'max_credit_limit',
      value: overrides.creditLimit,
      evidence: '用户在确认面板填写',
    })
  }

  return {
    plan_digest: overrides.planDigest,
    semester: overrides.semester,
    scope: ADJUSTMENT_SCOPE_CURRENT_SEMESTER,
    target_semester: draft.target_semester ?? overrides.semester,
    hard_constraints: hard,
    soft_preferences: draft.soft_preferences.map((item) => ({ ...item })),
    locked_courses: draft.locked_courses.map((item) => ({ ...item })),
    user_note: overrides.userNote ?? null,
  }
}
