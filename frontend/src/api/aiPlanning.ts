/**
 * AI 规划 typed adapter（**唯一出口**）。
 *
 * 契约来源：后端分支 `feature/deepseek-planning-controller` 的
 * `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md`
 * （与 `backend/app/api/ai_planning.py` 同一提交）。
 *
 * ```text
 * GET  /api/v1/ai-planning/status     如实报告可用状态（⛔ 不含密钥）
 * POST /api/v1/ai-planning/interpret  自然语言 → 意图草稿（只读；digest 由后端计算）
 * POST /api/v1/ai-planning/solve      已确认意图 → 候选（status=candidate_ready 才算有效）
 * POST /api/v1/ai-planning/adopt      二次确认 → adopted / rejected（**不返回方案体**）
 * ```
 *
 * 硬边界：
 * - ⛔ 不发送 `plan_digest` 到 `/interpret`（后端自己算，多传字段会 422）；
 * - ⛔ 不伪造 `adopted_plan`：`/adopt` 不返回方案体，前端只能采用内存中**已由后端返回**的候选；
 * - ⛔ 不把 `test_double` 说成"DeepSeek 已接入"；
 * - ⛔ 真实请求失败**没有**任何 fixture 回退分支（预览模式是独立开关）。
 */

import { AI_PLANNING_API_ENABLED, AI_PLANNING_ENDPOINTS, AI_PLANNING_PREVIEW } from '../config'
import {
  ContractViolation,
  parseAdoptResponse,
  parseInterpretResponse,
  parseSolveResponse,
  parseStatusResponse,
  type AiAdoptRequest,
  type AiAdoptResponse,
  type AiInterpretRequest,
  type AiInterpretResponse,
  type AiPlanningStatusResponse,
  type AiSolveRequest,
  type AiSolveResponse,
} from './aiPlanningContract'
import {
  AI_PREVIEW_NOTICE,
  PREVIEW_ADOPT_ACCEPTED,
  PREVIEW_ADOPT_KEPT,
  PREVIEW_ADOPT_REJECTED,
  PREVIEW_INTERPRET_OK,
  PREVIEW_INTERPRET_WITH_AMBIGUITIES,
  PREVIEW_NOT_CONFIGURED_MESSAGE,
  PREVIEW_SOLVE_BLOCKED,
  PREVIEW_SOLVE_CANDIDATE,
  PREVIEW_SOLVE_NO_FEASIBLE,
  PREVIEW_STATUS_DISABLED,
  PREVIEW_STATUS_LIVE,
  PREVIEW_STATUS_TEST_DOUBLE,
} from './aiPlanningFixtures'

/** 预览 / 测试场景（只影响 fixture，不影响真实请求）。 */
export type AiPreviewScenario =
  | 'ok'
  | 'ambiguous'
  | 'candidate'
  | 'no_feasible'
  | 'blocked'
  | 'adopted'
  | 'rejected'
  | 'kept'
  | 'status_disabled'
  | 'status_live'

type PreviewTables = {
  interpret: Partial<Record<AiPreviewScenario, AiInterpretResponse>>
  solve: Partial<Record<AiPreviewScenario, AiSolveResponse>>
  adopt: Partial<Record<AiPreviewScenario, AiAdoptResponse>>
  status: Partial<Record<AiPreviewScenario, AiPlanningStatusResponse>>
}

const PREVIEW_SCENARIOS: PreviewTables = {
  interpret: {
    ok: PREVIEW_INTERPRET_OK,
    candidate: PREVIEW_INTERPRET_OK,
    no_feasible: PREVIEW_INTERPRET_OK,
    blocked: PREVIEW_INTERPRET_OK,
    adopted: PREVIEW_INTERPRET_OK,
    rejected: PREVIEW_INTERPRET_OK,
    kept: PREVIEW_INTERPRET_OK,
    ambiguous: PREVIEW_INTERPRET_WITH_AMBIGUITIES,
  },
  solve: {
    ok: PREVIEW_SOLVE_CANDIDATE,
    candidate: PREVIEW_SOLVE_CANDIDATE,
    adopted: PREVIEW_SOLVE_CANDIDATE,
    rejected: PREVIEW_SOLVE_CANDIDATE,
    kept: PREVIEW_SOLVE_CANDIDATE,
    ambiguous: PREVIEW_SOLVE_CANDIDATE,
    no_feasible: PREVIEW_SOLVE_NO_FEASIBLE,
    blocked: PREVIEW_SOLVE_BLOCKED,
  },
  adopt: {
    ok: PREVIEW_ADOPT_ACCEPTED,
    adopted: PREVIEW_ADOPT_ACCEPTED,
    kept: PREVIEW_ADOPT_KEPT,
    ambiguous: PREVIEW_ADOPT_KEPT,
    rejected: PREVIEW_ADOPT_REJECTED,
  },
  status: {
    ok: PREVIEW_STATUS_TEST_DOUBLE,
    ambiguous: PREVIEW_STATUS_TEST_DOUBLE,
    candidate: PREVIEW_STATUS_TEST_DOUBLE,
    no_feasible: PREVIEW_STATUS_TEST_DOUBLE,
    blocked: PREVIEW_STATUS_TEST_DOUBLE,
    rejected: PREVIEW_STATUS_TEST_DOUBLE,
    kept: PREVIEW_STATUS_TEST_DOUBLE,
    status_live: PREVIEW_STATUS_LIVE,
    status_disabled: PREVIEW_STATUS_DISABLED,
  },
}

let previewScenario: AiPreviewScenario = 'ok'

/** 设置预览场景（仅测试 / 演示用）。 */
export function setAiPreviewScenario(scenario: AiPreviewScenario): void {
  previewScenario = scenario
}

/** 读取当前预览场景。 */
export function currentAiPreviewScenario(): AiPreviewScenario {
  return previewScenario
}

/**
 * 失败分类（与后端 HANDOFF 的错误码表一一对应）。
 *
 * ⚠️ 注意：`404` **不再**意味着"接口未配置"，而是 `ai_planning_session_not_found`
 * （进程重启 / 会话被淘汰）；"接口尚未部署"由 `GET /status` 的 404 判定为 `absent`。
 */
export type AiPlanningErrorKind =
  | 'disabled' // 503 ai_planning_disabled
  | 'model_unavailable' // 503 ai_planning_model_unavailable
  | 'message_rejected' // 400 ai_planning_message_rejected
  | 'model_output_invalid' // 422 ai_planning_model_output_invalid
  | 'intent_invalid' // 422 ai_planning_intent_invalid
  | 'plan_context_invalid' // 422 ai_planning_plan_context_invalid
  | 'intent_not_confirmable' // 409 ai_planning_intent_not_confirmable
  | 'adoption_conflict' // 409 ai_planning_adoption_conflict
  | 'session_not_found' // 404 ai_planning_session_not_found
  | 'session_expired' // 410 ai_planning_session_expired
  | 'solve_unsupported' // 501 ai_planning_solve_unsupported
  | 'candidate_invalid' // 502 ai_planning_candidate_invalid
  | 'budget_exceeded' // 429 ai_planning_budget_exceeded
  | 'absent' // 该私有前缀尚未部署（/status 404/405）
  | 'server' // 其它 5xx
  | 'network' // 请求根本没完成
  | 'unexpected' // 2xx 但响应形状不符合契约

/** 错误码 → 分类（后端固定码表）。 */
export const ERROR_CODE_TO_KIND: Record<string, AiPlanningErrorKind> = {
  ai_planning_disabled: 'disabled',
  ai_planning_model_unavailable: 'model_unavailable',
  ai_planning_message_rejected: 'message_rejected',
  ai_planning_model_output_invalid: 'model_output_invalid',
  ai_planning_intent_invalid: 'intent_invalid',
  ai_planning_plan_context_invalid: 'plan_context_invalid',
  ai_planning_intent_not_confirmable: 'intent_not_confirmable',
  ai_planning_adoption_conflict: 'adoption_conflict',
  ai_planning_session_not_found: 'session_not_found',
  ai_planning_session_expired: 'session_expired',
  ai_planning_solve_unsupported: 'solve_unsupported',
  ai_planning_candidate_invalid: 'candidate_invalid',
  ai_planning_budget_exceeded: 'budget_exceeded',
}

/** HTTP 状态码 → 兜底分类（只在错误体没有可识别 code 时使用）。 */
const STATUS_FALLBACK: Record<number, AiPlanningErrorKind> = {
  400: 'message_rejected',
  404: 'session_not_found',
  409: 'adoption_conflict',
  410: 'session_expired',
  422: 'intent_invalid',
  429: 'budget_exceeded',
  501: 'solve_unsupported',
  502: 'candidate_invalid',
  503: 'model_unavailable',
}

/** 请求失败时抛出的错误；UI 只按 `kind` 分支。 */
export class AiPlanningApiError extends Error {
  readonly kind: AiPlanningErrorKind
  readonly status: number | null
  readonly code: string | null
  readonly detail: string | null

  constructor(
    kind: AiPlanningErrorKind,
    message: string,
    options: { status?: number | null; code?: string | null; detail?: string | null } = {},
  ) {
    super(message)
    this.name = 'AiPlanningApiError'
    this.kind = kind
    this.status = options.status ?? null
    this.code = options.code ?? null
    this.detail = options.detail ?? null
  }
}

export const AI_PLANNING_NOT_CONFIGURED = PREVIEW_NOT_CONFIGURED_MESSAGE

function messageFor(kind: AiPlanningErrorKind, detail: string | null): string {
  switch (kind) {
    case 'disabled':
      return 'AI 调整未启用（服务器未开启 AI_PLANNING_ENABLED）；本次不解析意图，也不回退到任何演示模型。'
    case 'model_unavailable':
      return '模型暂不可用（无密钥 / 超时 / 上游错误）；原方案保持不变，请稍后再试。'
    case 'message_rejected':
      return (
        detail ??
        '这条说明被服务器拒绝（空 / 超长 / 疑似包含个人信息）。请改为只描述选课需求，不要填写姓名、学号或联系方式。'
      )
    case 'model_output_invalid':
      return 'AI 未能理解这句话（输出未通过结构校验）。请换一种说法再试。'
    case 'intent_invalid':
      return detail ?? '确认意图不合法（例如学分上限缺少依据）。请回到确认面板修正。'
    case 'plan_context_invalid':
      return '方案上下文自相矛盾（学期不一致 / 缺字段 / 重复身份）。请重新加载当前方案。'
    case 'intent_not_confirmable':
      return '意图中仍有必须由你回答的歧义，无法进入求解。请先回答下面的问题。'
    case 'adoption_conflict':
      return '该候选已经被采用或拒绝过（重复操作被拒绝）；请刷新候选状态。'
    case 'session_not_found':
      return '本次意图 / 候选已不存在（服务可能已重启）。请重新解析意图后再试。'
    case 'session_expired':
      return '方案指纹已变化或候选已过期。请重新解析意图或重新求解。'
    case 'solve_unsupported':
      return '当前冻结的 Planner 无法表达该意图（当前只支持当前学期调整）。'
    case 'candidate_invalid':
      return '服务器内部错误：Planner 返回的对象不是合法方案。这是服务端问题，请勿重试。'
    case 'budget_exceeded':
      return '本次请求的模型调用次数超出上限，请稍后再试。'
    case 'absent':
      return AI_PLANNING_NOT_CONFIGURED
    case 'server':
      return 'AI 调整服务端错误。页面不会显示任何伪造候选，原方案保持不变。'
    case 'network':
      return `无法连接 AI 调整接口（${AI_PLANNING_ENDPOINTS.status}）。请确认后端已启动。`
    default:
      return 'AI 调整接口返回的数据结构不符合后端契约，已停止渲染（不会补默认值）。'
  }
}

/** 把 HTTP 状态码 + 错误体翻译成分类。 */
export function classifyAiPlanningError(status: number, code: string | null): AiPlanningErrorKind {
  if (code !== null && code in ERROR_CODE_TO_KIND) {
    return ERROR_CODE_TO_KIND[code] as AiPlanningErrorKind
  }
  const fallback = STATUS_FALLBACK[status]
  if (fallback !== undefined) {
    return fallback
  }
  if (status >= 500) {
    return 'server'
  }
  return 'unexpected'
}

function safeText(value: unknown, maxLength = 300): string | null {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed === '') {
      return null
    }
    return trimmed.length > maxLength ? `${trimmed.slice(0, maxLength)}…` : trimmed
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return null
}

/** 尽力解析后端错误体（⛔ 不假设一定存在统一形状）。 */
export function parseAiPlanningErrorBody(rawBody: unknown): {
  code: string | null
  detail: string | null
} {
  if (rawBody === null || typeof rawBody !== 'object') {
    return { code: null, detail: safeText(rawBody) }
  }
  const detail = (rawBody as { detail?: unknown }).detail

  if (detail !== null && typeof detail === 'object' && !Array.isArray(detail)) {
    const record = detail as Record<string, unknown>
    return {
      code: safeText(record.error) ?? safeText(record.code),
      detail: safeText(record.message) ?? safeText(record.detail),
    }
  }
  if (Array.isArray(detail)) {
    const first = detail.find(
      (item): item is Record<string, unknown> => item !== null && typeof item === 'object',
    )
    if (first === undefined) {
      return { code: null, detail: null }
    }
    return { code: safeText(first.type), detail: safeText(first.msg) }
  }
  return { code: null, detail: safeText(detail) }
}

/** 成功结果包裹：明确标注是否来自**前端预览 fixture**。 */
export interface AiPlanningEnvelope<T> {
  data: T
  source: 'backend' | 'preview_fixture'
  previewNotice: string | null
}

function previewEnvelope<T>(data: T): AiPlanningEnvelope<T> {
  return { data, source: 'preview_fixture', previewNotice: AI_PREVIEW_NOTICE }
}

function backendEnvelope<T>(data: T): AiPlanningEnvelope<T> {
  return { data, source: 'backend', previewNotice: null }
}

async function readBodySafely(response: Response): Promise<unknown> {
  try {
    const text = await response.text()
    if (text.trim() === '') {
      return null
    }
    try {
      return JSON.parse(text)
    } catch {
      return null
    }
  } catch {
    return null
  }
}

interface RequestOptions {
  signal?: AbortSignal
}

/**
 * **测试 / 联调用**强制开关：置为 `true` 时忽略预览 fixture，只走真实网络路径。
 *
 * ⚠️ 只在 `vitest` 里由契约测试打开；生产代码不会调用它。
 * 真实失败仍然**不会**回退到 fixture（预览分支与真实分支互斥）。
 */
let forceRealRequests = false

/** 打开 / 关闭"强制真实请求"（仅供联调契约测试使用）。 */
export function setAiPlanningForceReal(force: boolean): void {
  forceRealRequests = force
}

/** 是否走真实网络路径。 */
function realModeActive(_options: RequestOptions): boolean {
  if (forceRealRequests) {
    return true
  }
  return !AI_PLANNING_PREVIEW
}

async function request(url: string, init: RequestInit, options: RequestOptions): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, { ...init, signal: options.signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new AiPlanningApiError('network', messageFor('network', null))
  }

  if (!response.ok) {
    const parsed = parseAiPlanningErrorBody(await readBodySafely(response))
    const kind = classifyAiPlanningError(response.status, parsed.code)
    throw new AiPlanningApiError(kind, messageFor(kind, parsed.detail), {
      status: response.status,
      code: parsed.code,
      detail: parsed.detail,
    })
  }

  try {
    return await response.json()
  } catch {
    throw new AiPlanningApiError(
      'unexpected',
      'AI 调整接口返回的内容不是合法 JSON，已停止渲染（不会显示伪造候选）。',
      { status: response.status },
    )
  }
}

function wrapContractError(error: unknown): never {
  if (error instanceof ContractViolation) {
    throw new AiPlanningApiError(
      'unexpected',
      `AI 调整响应不符合后端契约：${error.message}。已停止渲染（不会补默认值）。`,
      { code: 'contract_violation' },
    )
  }
  throw error
}

function requireApiEnabled(): void {
  if (forceRealRequests) {
    // 契约测试显式要求走真实路径：跳过前端开关，直接请求后端
    // （失败仍按真实 HTTP 语义分类，⛔ 不 fallback 到 fixture）。
    return
  }
  if (!AI_PLANNING_API_ENABLED) {
    throw new AiPlanningApiError('absent', messageFor('absent', null))
  }
}

/**
 * 读取 AI 规划控制器的可用状态。
 *
 * ⚠️ 该私有前缀**尚未部署**时返回 404/405 ⇒ `absent`：
 * 这与"后端已实现但未启用（503 ai_planning_disabled）"是**两件事**。
 */
export async function fetchAiPlanningStatus(
  options: RequestOptions = {},
): Promise<AiPlanningEnvelope<AiPlanningStatusResponse>> {
  if (!realModeActive(options)) {
    const scenario = PREVIEW_SCENARIOS.status[previewScenario] ?? PREVIEW_STATUS_TEST_DOUBLE
    return previewEnvelope(scenario)
  }
  requireApiEnabled()

  let payload: unknown
  try {
    payload = await request(AI_PLANNING_ENDPOINTS.status, { method: 'GET' }, options)
  } catch (error) {
    // 只有"路由根本不存在"（无结构化错误码）才翻译成 absent。
    if (
      error instanceof AiPlanningApiError &&
      (error.status === 404 || error.status === 405) &&
      error.code === null
    ) {
      throw new AiPlanningApiError('absent', messageFor('absent', null), { status: error.status })
    }
    throw error
  }

  try {
    return backendEnvelope(parseStatusResponse(payload))
  } catch (error) {
    wrapContractError(error)
  }
}

/**
 * 解析自然语言 → 意图草稿（**只读**）。
 *
 * ⚠️ 请求体只有 `context` + `user_message`；`plan_digest` 由后端计算并返回，
 * 前端**只保存、只回传**。
 */
export async function interpretIntent(
  requestBody: AiInterpretRequest,
  options: RequestOptions = {},
): Promise<AiPlanningEnvelope<AiInterpretResponse>> {
  if (!realModeActive(options)) {
    const scenario = PREVIEW_SCENARIOS.interpret[previewScenario] ?? PREVIEW_INTERPRET_OK
    return previewEnvelope(scenario)
  }
  requireApiEnabled()

  const payload = await request(
    AI_PLANNING_ENDPOINTS.interpret,
    {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    },
    options,
  )

  try {
    return backendEnvelope(parseInterpretResponse(payload))
  } catch (error) {
    wrapContractError(error)
  }
}

/** 对**已确认**意图调用受控 Planner 生成候选。 */
export async function solvePlan(
  requestBody: AiSolveRequest,
  options: RequestOptions = {},
): Promise<AiPlanningEnvelope<AiSolveResponse>> {
  if (!realModeActive(options)) {
    const scenario = PREVIEW_SCENARIOS.solve[previewScenario] ?? PREVIEW_SOLVE_CANDIDATE
    return previewEnvelope(scenario)
  }
  requireApiEnabled()

  const payload = await request(
    AI_PLANNING_ENDPOINTS.solve,
    {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    },
    options,
  )

  try {
    return backendEnvelope(parseSolveResponse(payload))
  } catch (error) {
    wrapContractError(error)
  }
}

/**
 * 二次确认：采用 / 拒绝候选。
 *
 * ⚠️ 响应**不含方案体**：调用方必须使用 `/solve` 已返回、并**由后端产生**的候选。
 */
export async function adoptCandidate(
  requestBody: AiAdoptRequest,
  options: RequestOptions = {},
): Promise<AiPlanningEnvelope<AiAdoptResponse>> {
  if (!realModeActive(options)) {
    const scenario = requestBody.accept
      ? (PREVIEW_SCENARIOS.adopt[previewScenario] ?? PREVIEW_ADOPT_KEPT)
      : PREVIEW_ADOPT_KEPT
    return previewEnvelope(scenario)
  }
  requireApiEnabled()

  const payload = await request(
    AI_PLANNING_ENDPOINTS.adopt,
    {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    },
    options,
  )

  try {
    return backendEnvelope(parseAdoptResponse(payload))
  } catch (error) {
    wrapContractError(error)
  }
}

/** 适配层能力状态（供界面显示"离线预览 / 未启用 / 已启用"）。 */
export function aiPlanningCapability(): {
  mode: 'preview' | 'api_disabled' | 'api_enabled'
  notice: string
} {
  if (AI_PLANNING_PREVIEW) {
    return { mode: 'preview', notice: AI_PREVIEW_NOTICE }
  }
  if (!AI_PLANNING_API_ENABLED) {
    return { mode: 'api_disabled', notice: PREVIEW_NOT_CONFIGURED_MESSAGE }
  }
  return { mode: 'api_enabled', notice: '已启用真实 AI 调整接口（可用性以 /status 为准）。' }
}

/** 实时读取适配层开关（测试可 `vi.stubEnv` 后调用）。 */
export function aiPlanningFlags(): { apiEnabled: boolean; preview: boolean } {
  return { apiEnabled: AI_PLANNING_API_ENABLED, preview: AI_PLANNING_PREVIEW }
}

/** 预览 fixture 解析器（导出以便测试直接验证"预览不伪造"）。 */
export const previewResolvers = {
  interpret(scenario: AiPreviewScenario = previewScenario): AiInterpretResponse {
    return PREVIEW_SCENARIOS.interpret[scenario] ?? PREVIEW_INTERPRET_OK
  },
  solve(scenario: AiPreviewScenario = previewScenario): AiSolveResponse {
    return PREVIEW_SCENARIOS.solve[scenario] ?? PREVIEW_SOLVE_CANDIDATE
  },
  adopt(accept: boolean, scenario: AiPreviewScenario = previewScenario): AiAdoptResponse {
    if (!accept) {
      return PREVIEW_ADOPT_KEPT
    }
    return PREVIEW_SCENARIOS.adopt[scenario] ?? PREVIEW_ADOPT_KEPT
  },
  status(scenario: AiPreviewScenario = previewScenario): AiPlanningStatusResponse {
    return PREVIEW_SCENARIOS.status[scenario] ?? PREVIEW_STATUS_TEST_DOUBLE
  },
}
