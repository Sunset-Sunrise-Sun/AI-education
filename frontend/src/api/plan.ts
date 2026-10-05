/**
 * 目标 Real 接口 `POST /api/v1/plan` 的客户端。
 *
 * 边界（硬要求）：
 * - 请求体**只有** `semester` / `current_schedule` / `preference` 三个字段；
 * - 响应按公共 `PlanResult` 处理，严格符合 `schemas/plan_result.schema.json`；
 * - ⛔ **绝不 fallback 到 `/api/v1/mock/demo`**：
 *   这个文件不 import 任何 Mock 通道代码，失败时只如实抛出错误；
 * - 本轮**不解析 XLSX、不做 Curriculum Diff、不做课程等价判定、不做冲突求解**：
 *   它只是把用户已经录入的输入交给后端。
 *
 * ⚠️ **不假设后端一定返回统一 error schema**：
 * 已知的 503 形状是 `{"detail": {"error": "real_pipeline_not_configured", "message": ...}}`，
 * 422 是 FastAPI 标准校验形状 `{"detail": [...]}`，
 * 但解析器对**未知形状保持宽容**，只做"能认出来就分类、认不出来就按状态码分类"。
 */

import { PLAN_ENDPOINT } from '../config'
import type { CourseOffering, PlanResult, Preference } from '../types/contracts'

/** Real Planning 请求体；字段与后端约定一一对应，不含任何额外键。 */
export interface RealPlanRequest {
  semester: string
  current_schedule: CourseOffering[]
  preference: Preference
}

/**
 * 失败类型。
 *
 * 语义**互斥且穷尽**，UI 只按 `kind` 分支，不需要再判断状态码：
 * - `not_configured`：**503 且 `detail.error === "real_pipeline_not_configured"`**，
 *   或 503 但响应体**无法解析 / 无可识别信息** ——
 *   表示**真实规划运行时尚未完成装配**，是"当前正确状态"，不是系统故障；
 *   ⚠️ 若 503 的响应体**明确给出了其它错误**，则归为 `server`，不得误报成"未装配"；
 * - `input`：422 —— 服务端**输入 / provenance** 校验未通过；
 * - `server`：5xx（503 之外的）—— 服务端错误；
 * - `network`：请求**根本没能完成**（连不上 / 连接被重置等）；
 * - `http`：其它非 2xx 状态码；
 * - `unexpected`：2xx 但响应体不是合法 `PlanResult` 对象。
 */
export type PlanErrorKind =
  | 'not_configured'
  | 'input'
  | 'server'
  | 'network'
  | 'http'
  | 'unexpected'

/** 后端 503 已知的稳定错误码（前端按它识别"未装配"，同时不依赖其一定存在）。 */
export const REAL_PIPELINE_NOT_CONFIGURED = 'real_pipeline_not_configured'

/** 请求失败时抛出的错误；消息面向非专业用户，不含堆栈或敏感信息。 */
export class PlanApiError extends Error {
  /** 失败类型；UI 只按这个分支。 */
  readonly kind: PlanErrorKind
  /** HTTP 状态码；网络错误时为 `null`。 */
  readonly status: number | null
  /** 后端返回的机器可读错误码（如 `real_pipeline_not_configured`）；没有则为 `null`。 */
  readonly code: string | null
  /** 后端返回的原始 detail 文本（已裁剪、仅用于展示/调试）；没有则为 `null`。 */
  readonly detail: string | null

  constructor(
    kind: PlanErrorKind,
    message: string,
    options: { status?: number | null; code?: string | null; detail?: string | null } = {},
  ) {
    super(message)
    this.name = 'PlanApiError'
    this.kind = kind
    this.status = options.status ?? null
    this.code = options.code ?? null
    this.detail = options.detail ?? null
  }
}

/** 把任意值安全地压成一段短文本（不 dump 整个对象、不回显敏感内容）。 */
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

/**
 * 从错误响应体中**尽力**提取 `{ code, detail }`。
 *
 * ⚠️ 刻意不做严格 schema 假设：
 * - 已知 503 形状 `{detail: {error, message}}` → 取 `error` / `message`；
 * - FastAPI 422 形状 `{detail: [{loc, msg, type}]}` → 取 `type` / `msg`；
 * - `{detail: "文本"}` → 取该文本；
 * - 其它形状 → 返回 `null`，由调用方按状态码分类。
 */
export function parsePlanErrorBody(rawBody: unknown): {
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
      detail: safeText(record.message) ?? safeText(record.detail) ?? safeText(record.error),
    }
  }

  if (Array.isArray(detail)) {
    const first = detail.find(
      (item): item is Record<string, unknown> => item !== null && typeof item === 'object',
    )
    if (first === undefined) {
      return { code: null, detail: null }
    }
    return {
      code: safeText(first.type),
      detail: safeText(first.msg),
    }
  }

  return { code: null, detail: safeText(detail) }
}

/** 读取响应体文本并尽力解析为 JSON；任何失败都返回 `null`（不抛错）。 */
async function readBodySafely(response: Response): Promise<unknown> {
  try {
    const text = await response.text()
    if (text.trim() === '') {
      return null
    }
    try {
      return JSON.parse(text)
    } catch {
      // 非 JSON 响应体：不假装能解析，交给按状态码分类的路径。
      return null
    }
  } catch {
    return null
  }
}

/**
 * 把错误响应分类为 `PlanErrorKind`。
 *
 * **503 的收紧规则**（本轮要求）：
 * 1. `real_pipeline_not_configured`（无论状态码）→ `not_configured`；
 * 2. 503 且**无法解析 / 无可识别信息** → `not_configured`
 *    （宁可如实说"未装配"，也不要凭空断言是服务端错误）；
 * 3. 503 但 body **明确给出其它错误** → `server`
 *    （⛔ 不能把已知的其它故障误报成"运行时尚未装配"）。
 */
export function classifyPlanError(input: {
  status: number
  code: string | null
  detail: string | null
}): PlanErrorKind {
  if (input.code === REAL_PIPELINE_NOT_CONFIGURED) {
    return 'not_configured'
  }

  if (input.status === 503) {
    const statedReason =
      (input.code !== null && input.code.trim() !== '') ||
      (input.detail !== null && input.detail.trim() !== '')
    return statedReason ? 'server' : 'not_configured'
  }

  if (input.status === 422) {
    return 'input'
  }

  if (input.status >= 500) {
    return 'server'
  }

  return 'http'
}

/** 按状态码 + 已解析出的 code 生成面向用户的消息。 */
function messageFor(
  kind: PlanErrorKind,
  status: number | null,
  statusText: string,
  code: string | null,
): string {
  switch (kind) {
    case 'not_configured':
      return '真实规划运行时尚未完成装配（真实 Curriculum / Course Data / Planner 尚未接入）。'
    case 'input':
      return '请求未被接受：当前输入（尤其是当前课表的来源）不满足 Real Planning 的要求。'
    case 'server':
      // 503 被归为服务端错误时，必须说清"这不是未装配"，避免误报
      if (status === 503) {
        return (
          'Real Planning 服务端错误（HTTP 503）' +
          `${code ? `：${code}` : ''}。` +
          '后端明确给出了其它错误原因，因此这**不是**"运行时尚未装配"。'
        )
      }
      return `Real Planning 服务端错误（HTTP ${status ?? '5xx'}）。`
    case 'network':
      return `无法连接 Real Planning 接口（请求地址：${PLAN_ENDPOINT}）。`
    default:
      return (
        `Real Planning 接口返回 HTTP ${status ?? '?'}` +
        `${statusText ? ` ${statusText}` : ''}。`
      )
  }
}

/**
 * 调用 Real Planning 接口。
 *
 * 只做：发请求、按状态分类错误、把 JSON 原样返回。
 * 不做数据加工、不补默认值、失败时**不返回兜底方案**。
 */
export async function fetchRealPlan(
  request: RealPlanRequest,
  signal?: AbortSignal,
): Promise<PlanResult> {
  let response: Response

  try {
    response = await fetch(PLAN_ENDPOINT, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new PlanApiError(
      'network',
      '无法连接 Real Planning 接口（请求地址：' +
        `${PLAN_ENDPOINT}）。请确认后端已启动，且前端是通过 npm run dev / npm run preview 打开的。`,
    )
  }

  if (!response.ok) {
    const body = await readBodySafely(response)
    const { code, detail } = parsePlanErrorBody(body)

    const kind = classifyPlanError({ status: response.status, code, detail })

    throw new PlanApiError(kind, messageFor(kind, response.status, response.statusText, code), {
      status: response.status,
      code,
      detail,
    })
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new PlanApiError(
      'unexpected',
      'Real Planning 接口返回的内容不是合法 JSON，无法解析为 PlanResult。',
      { status: response.status },
    )
  }

  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new PlanApiError(
      'unexpected',
      'Real Planning 接口返回的数据结构不是预期对象，已停止渲染。',
      { status: response.status },
    )
  }

  return payload as PlanResult
}
