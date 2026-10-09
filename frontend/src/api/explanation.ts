/**
 * 解释接口 `POST /api/v1/explanation/plan` 的客户端（Final Upgrade · Agent B）。
 *
 * 边界（硬要求）：
 * - 只发送**已经存在**的公共对象：`plan_result`（必需）、`makeup_tasks` / `course_offerings`（可选）；
 * - ⛔ **绝不**发送成绩单、姓名、学号、GPA 或个人身份信息：本文件没有任何这类字段；
 * - ⛔ **绝不 fallback**：失败时如实抛出错误，不伪造解释、不回退到 Mock 通道；
 * - ⛔ 不在前端重算解释：解释文本与来源一律由后端返回，前端只做展示与筛选。
 *
 * ⚠️ 解释本身**不是**规划计算：它只读地解释已有 `PlanResult`，调用它不会改变方案。
 */

import { API_BASE_URL, EXPLANATION_ENDPOINT } from '../config'
import type { CourseOffering, MakeupTask, PlanResult } from '../types/contracts'

/** 解释请求体：字段与后端一一对应，不含任何额外键。 */
export interface ExplanationRequest {
  plan_result: PlanResult
  makeup_tasks: MakeupTask[]
  course_offerings: CourseOffering[]
}

/**
 * 证据性质（后端 `EvidenceKind`）。
 *
 * 前端**只按它选择展示文案**，不据此改变任何业务结论。
 */
export type EvidenceKind =
  | 'confirmed_rule'
  | 'student_input_or_assumption'
  | 'system_suggestion'
  | 'unknown'
  | 'absent'

export type EvidenceStrength = 'confirmed' | 'partial' | 'unknown' | 'absent'

/** 解释文本的**实际**生成方式；`rule_based_template` 明确表示不是 AI 模型生成。 */
export type GeneratorKind = 'model' | 'rule_based_template' | 'model_unavailable_fell_back_to_template'

export type ExplanationItemKind =
  | 'makeup_task'
  | 'selected_class'
  | 'change'
  | 'risk'
  | 'unresolved'
  | 'plan_status'

export interface EvidenceReference {
  kind: EvidenceKind
  strength: EvidenceStrength
  source_object: string
  source_field: string
  raw_value: string
  note: string
}

export interface ConfirmationRequirement {
  reason: string
  evidence: EvidenceReference | null
}

export interface ExplanationGeneration {
  generator_kind: GeneratorKind
  model_configured: boolean
  model_id: string | null
  fallback_reason: string | null
  disclaimer: string
}

export interface ExplanationSourceSummary {
  plan_result_digest: string
  context_digest: string
  makeup_task_count: number
  course_offering_count: number
  contains_mock_marker: boolean
  contains_real_offering: boolean
  notes: string[]
}

export interface ExplanationItem {
  item_id: string
  kind: ExplanationItemKind
  code: string
  target_course_id: string | null
  target_class_id: string | null
  title: string
  answer: string
  strong_evidence: EvidenceReference[]
  premise_evidence: EvidenceReference[]
  requires_human_confirmation: ConfirmationRequirement[]
  generation: ExplanationGeneration
}

export interface ExplanationPayload {
  contract_version: string
  plan_result_digest: string
  context_digest: string
  generation: ExplanationGeneration
  source_summary: ExplanationSourceSummary
  warnings: string[]
  items: ExplanationItem[]
}

/** 失败类型；UI 只按 `kind` 分支。 */
export type ExplanationErrorKind =
  | 'disabled'
  | 'input'
  | 'server'
  | 'network'
  | 'http'
  | 'unexpected'

/** 请求失败时抛出的错误；消息面向非专业用户，不含堆栈。 */
export class ExplanationApiError extends Error {
  readonly kind: ExplanationErrorKind
  readonly status: number | null

  constructor(kind: ExplanationErrorKind, message: string, status: number | null = null) {
    super(message)
    this.name = 'ExplanationApiError'
    this.kind = kind
    this.status = status
  }
}

function messageFor(kind: ExplanationErrorKind, status: number | null): string {
  switch (kind) {
    case 'disabled':
      return '当前页面未启用解释接口（VITE_EXPLANATION_API_ENABLED 未开启），因此不会发出任何解释请求。'
    case 'input':
      return '解释请求未通过服务端校验（HTTP 422）：可能是方案缺少必需字段，或上下文条目过多。'
    case 'server':
      return `解释服务暂时不可用（HTTP ${status ?? '5xx'}）。页面不会伪造解释内容。`
    case 'network':
      return `无法连接解释接口（${EXPLANATION_ENDPOINT}）。请确认后端已启动。`
    default:
      return `解释接口返回 HTTP ${status ?? '?'}。`
  }
}

/**
 * 判断一个未知值是否**看起来像**合法的解释响应。
 *
 * ⚠️ 刻意保持"结构最小校验"：只确认关键字段存在且类型正确，
 * 不去猜测缺失字段的默认值（不补默认值 = 不掩盖后端契约变化）。
 */
export function isExplanationPayload(value: unknown): value is ExplanationPayload {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }
  const record = value as Record<string, unknown>
  return (
    typeof record.contract_version === 'string' &&
    typeof record.plan_result_digest === 'string' &&
    typeof record.generation === 'object' &&
    record.generation !== null &&
    typeof record.source_summary === 'object' &&
    record.source_summary !== null &&
    Array.isArray(record.items) &&
    Array.isArray(record.warnings)
  )
}

/** 调用解释接口；成功返回解释响应，失败如实抛出 `ExplanationApiError`。 */
export async function fetchPlanExplanation(
  request: ExplanationRequest,
  options: { enabled?: boolean; signal?: AbortSignal } = {},
): Promise<ExplanationPayload> {
  if (options.enabled === false) {
    throw new ExplanationApiError('disabled', messageFor('disabled', null))
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/explanation/plan`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ExplanationApiError('network', messageFor('network', null))
  }

  if (!response.ok) {
    const kind: ExplanationErrorKind =
      response.status === 422 ? 'input' : response.status >= 500 ? 'server' : 'http'
    throw new ExplanationApiError(kind, messageFor(kind, response.status), response.status)
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new ExplanationApiError(
      'unexpected',
      '解释接口返回的内容不是合法 JSON，已停止渲染（不会显示任何伪造解释）。',
      response.status,
    )
  }

  if (!isExplanationPayload(payload)) {
    throw new ExplanationApiError(
      'unexpected',
      '解释接口返回的数据结构不符合预期，已停止渲染（不会显示任何伪造解释）。',
      response.status,
    )
  }

  return payload
}
