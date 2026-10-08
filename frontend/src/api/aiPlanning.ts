/**
 * AI 规划 typed adapter（**唯一出口**）。
 *
 * 设计要点：
 * 1. **可替换**：真实后端（Agent A）尚未实现；本文件是前端唯一知道
 *    `/api/v1/ai-planning/*` 的地方，替换后端只需改这里；
 * 2. **不伪造**：任何非 2xx / 结构不符都抛 `AiPlanningApiError`；
 *    ⛔ 不存在"失败时返回 fixture"的分支；
 * 3. **预览隔离**：只有 `VITE_AI_PLANNING_PREVIEW=true` 时才读 fixture，
 *    并在返回值里标记 `source: 'preview_fixture'`，由界面醒目标注；
 * 4. **不推断**：契约里没有的字段不会被补默认值（缺失即视为 `unexpected`）。
 *
 * 逐字段假设见 `docs/final_upgrade/FRONTEND_AI_API_EXPECTATIONS.md`。
 */

import { AI_PLANNING_API_ENABLED, AI_PLANNING_ENDPOINTS, AI_PLANNING_PREVIEW } from '../config'
import {
  AI_PREVIEW_NOTICE,
  PREVIEW_ADOPT_ADOPTED,
  PREVIEW_ADOPT_KEPT,
  PREVIEW_ADOPT_REJECTED,
  PREVIEW_ADOPT_STALE,
  PREVIEW_INTERPRET_LOW_CONFIDENCE,
  PREVIEW_INTERPRET_OK,
  PREVIEW_NOT_CONFIGURED_MESSAGE,
  PREVIEW_SOLVE_CANDIDATE,
  PREVIEW_SOLVE_INFEASIBLE,
  PREVIEW_SOLVE_UNAVAILABLE,
} from './aiPlanningFixtures'
import type {
  AiAdoptRequest,
  AiAdoptResponse,
  AiInterpretRequest,
  AiInterpretResponse,
  AiPlanningEnvelope,
  AiPlanningErrorKind,
  AiSolveRequest,
  AiSolveResponse,
} from './aiPlanningTypes'

/** 预览 / 测试场景选择（仅影响 fixture，不影响真实请求）。 */
export type AiPreviewScenario =
  | 'ok'
  | 'low_confidence'
  | 'candidate'
  | 'infeasible'
  | 'unavailable'
  | 'adopted'
  | 'stale'
  | 'rejected'
  | 'kept'

const PREVIEW_SCENARIOS: {
  interpret: Partial<Record<AiPreviewScenario, AiInterpretResponse>>
  solve: Partial<Record<AiPreviewScenario, AiSolveResponse>>
  adopt: Partial<Record<AiPreviewScenario, AiAdoptResponse>>
} = {
  interpret: {
    ok: PREVIEW_INTERPRET_OK,
    low_confidence: PREVIEW_INTERPRET_LOW_CONFIDENCE,
    candidate: PREVIEW_INTERPRET_OK,
    infeasible: PREVIEW_INTERPRET_OK,
    unavailable: PREVIEW_INTERPRET_OK,
    adopted: PREVIEW_INTERPRET_OK,
    stale: PREVIEW_INTERPRET_OK,
    rejected: PREVIEW_INTERPRET_OK,
    kept: PREVIEW_INTERPRET_OK,
  },
  solve: {
    ok: PREVIEW_SOLVE_CANDIDATE,
    candidate: PREVIEW_SOLVE_CANDIDATE,
    infeasible: PREVIEW_SOLVE_INFEASIBLE,
    unavailable: PREVIEW_SOLVE_UNAVAILABLE,
    adopted: PREVIEW_SOLVE_CANDIDATE,
    stale: PREVIEW_SOLVE_CANDIDATE,
    rejected: PREVIEW_SOLVE_INFEASIBLE,
    kept: PREVIEW_SOLVE_CANDIDATE,
  },
  adopt: {
    ok: PREVIEW_ADOPT_ADOPTED,
    candidate: PREVIEW_ADOPT_ADOPTED,
    adopted: PREVIEW_ADOPT_ADOPTED,
    stale: PREVIEW_ADOPT_STALE,
    rejected: PREVIEW_ADOPT_REJECTED,
    kept: PREVIEW_ADOPT_KEPT,
  },
}

/** 当前预览场景；测试可调用 `setAiPreviewScenario()` 覆盖。 */
let previewScenario: AiPreviewScenario = 'ok'

/** 设置预览场景（仅测试 / 演示用；不影响真实请求路径）。 */
export function setAiPreviewScenario(scenario: AiPreviewScenario): void {
  previewScenario = scenario
}

/** 读取当前预览场景（供调试面板展示）。 */
export function currentAiPreviewScenario(): AiPreviewScenario {
  return previewScenario
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

export const AI_PLANNING_NOT_CONFIGURED =
  'AI 调整接口尚未配置或未启用；当前不会调用规划器，也不会生成候选方案。'

function messageFor(kind: AiPlanningErrorKind, status: number | null, code: string | null): string {
  switch (kind) {
    case 'disabled':
      return AI_PLANNING_NOT_CONFIGURED
    case 'not_configured':
      return 'AI 调整接口尚未在服务端实现（HTTP 404 / 501）。页面不会伪造解析或候选方案。'
    case 'input':
      return 'AI 调整请求未通过服务端校验（HTTP 422）：请检查语句、学期与课程上下文。'
    case 'conflict':
      return '本次意图或候选已经过期（HTTP 409）：原方案保持不变，请重新解析后再试。'
    case 'unavailable':
      return `缺少必要条件，后端无法求解（HTTP ${status ?? 503}）${
        code ? `：${code}` : ''
      }。原方案保持不变。`
    case 'server':
      return `AI 调整服务端错误（HTTP ${status ?? '5xx'}）。页面不会显示任何伪造候选。`
    case 'network':
      return `无法连接 AI 调整接口（${AI_PLANNING_ENDPOINTS.interpret} 等）。请确认后端已启动。`
    default:
      return `AI 调整接口返回 HTTP ${status ?? '?'}。`
  }
}

function classifyStatus(status: number): AiPlanningErrorKind {
  if (status === 404 || status === 501) {
    return 'not_configured'
  }
  if (status === 422) {
    return 'input'
  }
  if (status === 409) {
    return 'conflict'
  }
  if (status === 503 || status === 502 || status === 504) {
    return 'unavailable'
  }
  if (status >= 500) {
    return 'server'
  }
  return 'network'
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

/**
 * 统一 POST：分类错误、阻止 fallback、把 JSON 原样返回。
 *
 * ⛔ 本函数**没有**任何 fixture / Mock 回退分支。
 */
async function postJson(url: string, body: unknown, signal?: AbortSignal): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new AiPlanningApiError('network', messageFor('network', null, null))
  }

  if (!response.ok) {
    const parsed = parseAiPlanningErrorBody(await readBodySafely(response))
    const kind = classifyStatus(response.status)
    throw new AiPlanningApiError(kind, messageFor(kind, response.status, parsed.code), {
      status: response.status,
      code: parsed.code,
      detail: parsed.detail,
    })
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new AiPlanningApiError(
      'unexpected',
      'AI 调整接口返回的内容不是合法 JSON，已停止渲染（不会显示伪造候选）。',
      { status: response.status },
    )
  }
  return payload
}

function requireObject(payload: unknown): Record<string, unknown> {
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new AiPlanningApiError('unexpected', 'AI 调整接口返回的数据结构不符合预期。')
  }
  return payload as Record<string, unknown>
}

function requireString(payload: Record<string, unknown>, field: string): string {
  const value = payload[field]
  if (typeof value !== 'string') {
    throw new AiPlanningApiError(
      'unexpected',
      `AI 调整响应缺少必需字段 ${field}；已停止渲染（不会补默认值）。`,
    )
  }
  return value
}

function requireBoolean(payload: Record<string, unknown>, field: string): boolean {
  const value = payload[field]
  if (typeof value !== 'boolean') {
    throw new AiPlanningApiError(
      'unexpected',
      `AI 调整响应缺少必需字段 ${field}；已停止渲染（不会补默认值）。`,
    )
  }
  return value
}

function requireObjectField(payload: Record<string, unknown>, field: string): Record<string, unknown> {
  return requireObject(payload[field])
}

function requireArrayField(payload: Record<string, unknown>, field: string): unknown[] {
  const value = payload[field]
  if (!Array.isArray(value)) {
    throw new AiPlanningApiError('unexpected', `AI 调整响应缺少必需数组字段 ${field}。`)
  }
  return value
}

/**
 * 解析 intent：把自然语言变成**待确认草稿**。
 *
 * ⛔ 本调用不求解、不产生候选方案。
 */
export async function interpretIntent(
  request: AiInterpretRequest,
  options: { signal?: AbortSignal } = {},
): Promise<AiPlanningEnvelope<AiInterpretResponse>> {
  if (AI_PLANNING_PREVIEW) {
    const scenario = PREVIEW_SCENARIOS.interpret[previewScenario] ?? PREVIEW_INTERPRET_OK
    return previewEnvelope(scenario)
  }
  if (!AI_PLANNING_API_ENABLED) {
    throw new AiPlanningApiError('disabled', messageFor('disabled', null, null))
  }

  const payload = requireObject(
    await postJson(AI_PLANNING_ENDPOINTS.interpret, request, options.signal),
  )

  const response: AiInterpretResponse = {
    intent_id: requireString(payload, 'intent_id'),
    plan_digest: requireString(payload, 'plan_digest'),
    data_source: requireString(payload, 'data_source') as AiInterpretResponse['data_source'],
    generator_kind: requireString(
      payload,
      'generator_kind',
    ) as AiInterpretResponse['generator_kind'],
    can_confirm: requireBoolean(payload, 'can_confirm'),
    parsed_intent: requireObjectField(payload, 'parsed_intent') as unknown as AiInterpretResponse['parsed_intent'],
    ambiguities: requireArrayField(payload, 'ambiguities') as AiInterpretResponse['ambiguities'],
    message: requireString(payload, 'message'),
  }

  // 方案指纹必须回显一致，否则视为"原方案已变化"（防串案）。
  if (response.plan_digest !== request.plan_digest) {
    throw new AiPlanningApiError(
      'conflict',
      '原方案已发生变化（后端返回的方案指纹与请求不一致）；请重新解析意图。',
      { code: 'stale_plan' },
    )
  }

  return backendEnvelope(response)
}

/** 在**已确认**意图上求解候选方案。 */
export async function solvePlan(
  request: AiSolveRequest,
  options: { signal?: AbortSignal } = {},
): Promise<AiPlanningEnvelope<AiSolveResponse>> {
  if (AI_PLANNING_PREVIEW) {
    const scenario = PREVIEW_SCENARIOS.solve[previewScenario] ?? PREVIEW_SOLVE_CANDIDATE
    return previewEnvelope(scenario)
  }
  if (!AI_PLANNING_API_ENABLED) {
    throw new AiPlanningApiError('disabled', messageFor('disabled', null, null))
  }

  const payload = requireObject(
    await postJson(AI_PLANNING_ENDPOINTS.solve, request, options.signal),
  )

  const status = requireString(payload, 'status') as AiSolveResponse['status']
  const candidateId = payload['candidate_id']
  const candidateDigest = payload['candidate_digest']
  const candidatePlan = payload['candidate_plan']
  const diff = payload['diff']

  const response: AiSolveResponse = {
    status,
    candidate_id: typeof candidateId === 'string' ? candidateId : null,
    candidate_plan:
      candidatePlan === null || candidatePlan === undefined
        ? null
        : (candidatePlan as AiSolveResponse['candidate_plan']),
    plan_digest: requireString(payload, 'plan_digest'),
    candidate_digest: typeof candidateDigest === 'string' ? candidateDigest : null,
    diff: diff === null || diff === undefined ? null : (diff as AiSolveResponse['diff']),
    risks: (payload['risks'] ?? []) as AiSolveResponse['risks'],
    unresolved: (payload['unresolved'] ?? []) as AiSolveResponse['unresolved'],
    message: requireString(payload, 'message'),
    expires_at: typeof payload['expires_at'] === 'string' ? payload['expires_at'] : null,
  }

  // 契约要求：只有 candidate 状态才带候选；反之必须为 null（⛔ 不接受"有候选但状态不是 candidate"）。
  if (status === 'candidate') {
    if (!response.candidate_id || !response.candidate_plan || !response.diff) {
      throw new AiPlanningApiError(
        'unexpected',
        '后端声称生成了候选，但缺少 candidate_id / candidate_plan / diff；已停止渲染。',
      )
    }
  } else if (response.candidate_plan !== null) {
    throw new AiPlanningApiError(
      'unexpected',
      `后端返回 status=${status} 却带有候选方案；状态与内容矛盾，已停止渲染。`,
    )
  }

  return backendEnvelope(response)
}

/**
 * **第二次确认**：采用候选或明确保留原方案。
 *
 * ⛔ 只有后端回答 `adopted` 才允许刷新当前方案。
 */
export async function adoptCandidate(
  request: AiAdoptRequest,
  options: { signal?: AbortSignal } = {},
): Promise<AiPlanningEnvelope<AiAdoptResponse>> {
  if (AI_PLANNING_PREVIEW) {
    const scenario = request.accept
      ? (PREVIEW_SCENARIOS.adopt[previewScenario] ?? PREVIEW_ADOPT_ADOPTED)
      : PREVIEW_ADOPT_KEPT
    return previewEnvelope(scenario)
  }
  if (!AI_PLANNING_API_ENABLED) {
    throw new AiPlanningApiError('disabled', messageFor('disabled', null, null))
  }

  const payload = requireObject(
    await postJson(AI_PLANNING_ENDPOINTS.adopt, request, options.signal),
  )

  const status = requireString(payload, 'status') as AiAdoptResponse['status']
  const adoptedPlan = payload['adopted_plan']

  const response: AiAdoptResponse = {
    status,
    adopted_plan:
      adoptedPlan === null || adoptedPlan === undefined
        ? null
        : (adoptedPlan as AiAdoptResponse['adopted_plan']),
    adopted_digest: typeof payload['adopted_digest'] === 'string' ? payload['adopted_digest'] : null,
    result_version:
      typeof payload['result_version'] === 'string' ? payload['result_version'] : null,
    message: requireString(payload, 'message'),
  }

  if (status === 'adopted' && request.accept && response.adopted_plan === null) {
    throw new AiPlanningApiError(
      'unexpected',
      '后端声称已采用候选，但没有返回 adopted_plan；已停止刷新当前方案。',
    )
  }

  return backendEnvelope(response)
}

/** 当前适配层的能力状态（供界面显示"未配置 / 预览 / 真实"）。 */
export function aiPlanningCapability(): {
  mode: 'disabled' | 'preview' | 'backend'
  notice: string
} {
  if (AI_PLANNING_PREVIEW) {
    return { mode: 'preview', notice: AI_PREVIEW_NOTICE }
  }
  if (!AI_PLANNING_API_ENABLED) {
    return { mode: 'disabled', notice: PREVIEW_NOT_CONFIGURED_MESSAGE }
  }
  return { mode: 'backend', notice: '已连接到真实 AI 调整接口。' }
}

/**
 * 预览 fixture 解析器（**导出以便测试直接验证"预览不伪造"**）。
 *
 * ⚠️ 这些函数只服务预览模式；真实请求路径**不会**调用它们。
 */
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
    return PREVIEW_SCENARIOS.adopt[scenario] ?? PREVIEW_ADOPT_ADOPTED
  },
}

/** 实时读取适配层开关（测试可 stub `import.meta.env` 后调用）。 */
export function aiPlanningFlags(): { apiEnabled: boolean; preview: boolean } {
  return { apiEnabled: AI_PLANNING_API_ENABLED, preview: AI_PLANNING_PREVIEW }
}
