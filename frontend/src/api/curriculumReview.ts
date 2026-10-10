/**
 * 培养方案**课程分类审核**客户端（⚠️ 本轮新增）。
 *
 * ```text
 * 解析 PDF（已有）→ 拿到 review_id
 *      ↓
 * 取审核状态 → 逐条 确认 / 人工修改 / 暂缓 → 导出审核草稿
 * ```
 *
 * ## ⛔ 前端做不到、也不该做的事
 *
 * | ⛔ 不能 | 为什么 |
 * | --- | --- |
 * | 提交证据 / 课程原文 / SHA-256 | 这些只由服务端保管；提交会被 `extra="forbid"` 拒绝 |
 * | 一键确认冲突或无证据的候选 | 服务端 `review_confirm_not_allowed` |
 * | 无理由地人工修改类别 | 服务端 `review_override_requires_reason` |
 * | 用"拒绝"自动选相反类别 | ⛔ 没有 reject 动作；拒绝 = 暂缓 |
 * | 把审核结果说成"已认证 / 已完成课程认定" | 导出恒为草稿（`verified=false`） |
 */

import { CURRICULUM_REVIEW_ENDPOINTS } from '../config'

/** 审核动作（⛔ 只有三个；⛔ 没有「拒绝」这类会改判类别的动作）。 */
export type ReviewAction = 'confirm' | 'override' | 'defer'

/** 候选状态。 */
export type CandidateStatus = 'single_source' | 'conflicting' | 'no_evidence'

/** 一条原文证据（⛔ 由服务端给出，前端只展示）。 */
export interface ReviewEvidence {
  kind: string
  category_code: string | null
  requirement: string
  source_record: string
  raw_text: string
  minimum_credit: number | null
}

/** 一条分类候选。 */
export interface ReviewCandidate {
  course_id: string
  source_record: string
  proposed_requirement: string
  proposed_category_code: string | null
  status: CandidateStatus
  evidence_complete: boolean
  evidence: ReviewEvidence[]
  decision: ReviewDecisionRecord | null
  resubmissions: number
}

export interface ReviewDecisionRecord {
  source_record: string
  action: ReviewAction
  requirement: string | null
  reason: string | null
  revision: number
  /** ⚠️ 恒为 `reviewer_input_not_a_pdf_evidence`：标明这是**人工判断**。 */
  decided_by: string
}

export interface ReviewCategoryRequirement {
  category_code: string
  requirement: string
  minimum_credit: number | null
  source_record: string
  raw_text: string
}

export interface ReviewProgress {
  total_candidates: number
  confirmed: number
  overridden: number
  deferred: number
  undecided: number
  by_status: Record<string, number>
  conflicting: number
  no_evidence: number
  section_rows: number
  unmapped_category_codes: string[]
  verification_verified: boolean
  conclusion: string
}

export interface ReviewSession {
  review_id: string
  document: {
    key: string
    major: string
    cohort: string
    role: string
    file_name: string
    source_id: string
    source_sha256: string
  }
  candidates: ReviewCandidate[]
  category_requirements: ReviewCategoryRequirement[]
  section_rows: { source_record: string; raw_text: string }[]
  unmapped_category_codes: string[]
  progress: ReviewProgress
  expires_in_seconds: number
  notes: string[]
}

/** 审核错误：固定码 + 固定文案（⛔ 不回显后端细节）。 */
export type ReviewErrorKind =
  | 'disabled'
  | 'not_found'
  | 'capacity'
  | 'confirm_not_allowed'
  | 'override_requires_reason'
  | 'invalid_requirement'
  | 'unknown_source_record'
  | 'invalid_request'
  | 'network'
  | 'contract'

const ERROR_KIND_BY_CODE: Record<string, ReviewErrorKind> = {
  review_not_found: 'not_found',
  review_capacity_reached: 'capacity',
  review_confirm_not_allowed: 'confirm_not_allowed',
  review_override_requires_reason: 'override_requires_reason',
  review_override_requires_requirement: 'invalid_requirement',
  review_invalid_requirement: 'invalid_requirement',
  review_unknown_source_record: 'unknown_source_record',
  review_unknown_field: 'invalid_request',
  review_invalid_action: 'invalid_request',
  review_invalid_request: 'invalid_request',
  review_duplicate_in_request: 'invalid_request',
  review_too_many_decisions: 'invalid_request',
  review_reason_too_long: 'invalid_request',
}

export const REVIEW_ERROR_LABEL: Record<ReviewErrorKind, string> = {
  disabled: '课程分类审核通道未启用。',
  not_found: '该审核会话不存在或已过期（⛔ 不会自动新建）。',
  capacity: '审核会话数量已达上限，请稍后重试。',
  confirm_not_allowed:
    '该课程没有明确类别（冲突或无证据），⛔ 不能一键确认；请用「人工修改」并说明理由，或「暂缓」。',
  override_requires_reason:
    '人工修改必须填写审核理由（这条结论来自人工判断，⛔ 不是 PDF 原文证据）。',
  invalid_requirement: '人工修改的类别只能是「必修」或「选修」。',
  unknown_source_record: '该来源定位不在当前审核会话中。',
  invalid_request: '提交内容不符合审核接口约定。',
  network: '请求失败：无法连接后端。',
  contract: '后端响应不符合约定的契约。',
}

export class ReviewApiError extends Error {
  readonly kind: ReviewErrorKind

  constructor(kind: ReviewErrorKind) {
    super(REVIEW_ERROR_LABEL[kind])
    this.name = 'ReviewApiError'
    this.kind = kind
  }
}

function _errorKindFromBody(body: unknown): ReviewErrorKind | null {
  if (typeof body !== 'object' || body === null) {
    return null
  }
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'object' && detail !== null) {
    const code = (detail as { error?: unknown }).error
    if (typeof code === 'string' && code in ERROR_KIND_BY_CODE) {
      return ERROR_KIND_BY_CODE[code]!
    }
  }
  return null
}

/** 把响应体解析成 `ReviewSession`；缺字段即契约错误（⛔ 不当成空结果）。 */
export function parseReviewSession(payload: unknown): ReviewSession {
  if (typeof payload !== 'object' || payload === null) {
    throw new ReviewApiError('contract')
  }
  const record = payload as Record<string, unknown>
  if (typeof record['review_id'] !== 'string') {
    throw new ReviewApiError('contract')
  }
  if (!Array.isArray(record['candidates'])) {
    throw new ReviewApiError('contract')
  }
  if (typeof record['progress'] !== 'object' || record['progress'] === null) {
    throw new ReviewApiError('contract')
  }
  const document = (record['document'] ?? {}) as Record<string, unknown>
  return {
    review_id: record['review_id'],
    document: {
      key: String(document['key'] ?? ''),
      major: String(document['major'] ?? ''),
      cohort: String(document['cohort'] ?? ''),
      role: String(document['role'] ?? ''),
      file_name: String(document['file_name'] ?? ''),
      source_id: String(document['source_id'] ?? ''),
      source_sha256: String(document['source_sha256'] ?? ''),
    },
    candidates: record['candidates'] as ReviewCandidate[],
    category_requirements: Array.isArray(record['category_requirements'])
      ? (record['category_requirements'] as ReviewCategoryRequirement[])
      : [],
    section_rows: Array.isArray(record['section_rows'])
      ? (record['section_rows'] as { source_record: string; raw_text: string }[])
      : [],
    unmapped_category_codes: Array.isArray(record['unmapped_category_codes'])
      ? (record['unmapped_category_codes'] as unknown[]).map((item) => String(item))
      : [],
    progress: record['progress'] as ReviewProgress,
    expires_in_seconds: Number(record['expires_in_seconds'] ?? 0),
    notes: Array.isArray(record['notes'])
      ? (record['notes'] as unknown[]).map((item) => String(item))
      : [],
  }
}

async function _request(
  url: string, init: RequestInit, options: { enabled: boolean },
): Promise<Response> {
  if (!options.enabled) {
    throw new ReviewApiError('disabled')
  }
  try {
    return await fetch(url, init)
  } catch {
    throw new ReviewApiError('network')
  }
}

/** 取审核状态。 */
export async function fetchReviewSession(
  reviewId: string, options: { enabled: boolean },
): Promise<ReviewSession> {
  const response = await _request(
    `${CURRICULUM_REVIEW_ENDPOINTS.status}/${encodeURIComponent(reviewId)}`,
    { method: 'GET' },
    options,
  )
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    throw new ReviewApiError(_errorKindFromBody(body) ?? 'contract')
  }
  return parseReviewSession(await response.json())
}

/** 一条待提交的决策（⚠️ ⛔ 不含证据 / 原文 / 摘要）。 */
export interface ReviewDecisionInput {
  source_record: string
  action: ReviewAction
  requirement?: 'required' | 'elective'
  reason?: string
}

/** 提交决策（可批量）。 */
export async function submitReviewDecisions(
  reviewId: string,
  decisions: ReviewDecisionInput[],
  options: { enabled: boolean },
): Promise<ReviewSession> {
  const response = await _request(
    `${CURRICULUM_REVIEW_ENDPOINTS.status}/${encodeURIComponent(reviewId)}/decisions`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decisions }),
    },
    options,
  )
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    throw new ReviewApiError(_errorKindFromBody(body) ?? 'contract')
  }
  return parseReviewSession(await response.json())
}

/** 导出审核草稿（返回原始 JSON 对象；⛔ 前端不改写其中任何字段）。 */
export async function exportReviewDraft(
  reviewId: string, options: { enabled: boolean },
): Promise<Record<string, unknown>> {
  const response = await _request(
    `${CURRICULUM_REVIEW_ENDPOINTS.status}/${encodeURIComponent(reviewId)}/export`,
    { method: 'GET' },
    options,
  )
  if (!response.ok) {
    throw new ReviewApiError('not_found')
  }
  const body = await response.json()
  if (typeof body !== 'object' || body === null) {
    throw new ReviewApiError('contract')
  }
  return body as Record<string, unknown>
}

/** 候选状态 → 面向用户的固定文案。 */
export const CANDIDATE_STATUS_LABEL: Record<CandidateStatus, string> = {
  single_source: '有明确依据',
  conflicting: '依据冲突（需人工裁定）',
  no_evidence: '文档中无分类依据',
}

/** 归一化类别 → 中文（⚠️ 只用于展示，⛔ 不参与任何判断）。 */
export const REQUIREMENT_LABEL: Record<string, string> = {
  required: '必修',
  elective: '选修',
  unknown: '未确定',
}
