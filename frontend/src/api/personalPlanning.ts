/**
 * 个人规划接口客户端（`/api/v1/personal-planning/*`）—— **已存在**的后端契约。
 *
 * 与 AI 规划适配层的区别：
 * - 这两个路径**已经在后端实现**（Agent A），因此前端按**真实 readiness** 接入；
 * - ⛔ 目录未配置（503 `personal_catalog_not_configured`）时**不退回固定 Case A**、
 *   ⛔ `planning = null` 时**不显示"已排好课"**；
 * - ⛔ 请求体不包含姓名 / 学号 / 成绩单原文 / 任何凭据。
 */

import { PERSONAL_PLANNING_API_ENABLED, PERSONAL_PLANNING_ENDPOINTS } from '../config'
import type { CourseOffering, MakeupTask, PlanResult } from '../types/contracts'

/** 一个**可选**培养方案版本的元信息（与后端 `CurriculumVersionMetadata` 对齐）。 */
export interface CurriculumVersionMetadata {
  version_id: string
  major: string
  cohort: string
  campus?: string | null
  track?: string | null
  source_id: string
  verification_evidence: string
  verified_by?: string | null
  complete: boolean
  completeness_evidence?: string | null
  total_credit?: number | null
  practice_credit?: number | null
  study_years?: number | null
  course_count: number
  group_count: number
}

/** 一个**不可选**的版本及固定原因码。 */
export interface RejectedVersion {
  version_id: string
  code: string
  detail: string
}

export interface CurriculumVersionList {
  catalog_ready: boolean
  catalog_reason: string
  selectable_count: number
  versions: CurriculumVersionMetadata[]
  rejected: RejectedVersion[]
}

/** 个人规划请求体（⛔ 只有这些键；后端 `extra="forbid"`）。 */
export interface PersonalPlanRequest {
  old_version_id: string
  target_version_id: string
  semester?: string | null
  /** 本学生输入：只放**已脱敏**的课程级事实。 */
  student: {
    completed?: {
      complete?: boolean
      completeness_evidence?: string | null
      records?: {
        course_id?: string | null
        course_name: string
        credit: number
        semester: string
        passed: boolean
        course_type?: string | null
        course_id_status?: string
        id_match_source?: string | null
        source_record?: string
      }[]
    }
    preference?: {
      max_credit?: number | null
      avoid_cross_campus?: boolean
      preferred_courses?: string[]
      avoid_times?: unknown[]
      notes?: string | null
    }
  }
  preference?: {
    max_credit?: number | null
    avoid_cross_campus?: boolean
    preferred_courses?: string[]
    avoid_times?: unknown[]
    notes?: string | null
  } | null
  current_schedule?: CourseOffering[]
}

/** 个人规划结果（与后端 `PersonalPlanResponse` 对齐）。 */
export interface PersonalPlanResult {
  old_version: CurriculumVersionMetadata
  target_version: CurriculumVersionMetadata
  data_source: string
  completed_source_id: string
  completed_record_count: number
  input_summary: Record<string, number>
  makeup_tasks: MakeupTask[]
  status_counts: Record<string, number>
  /** ⚠️ `null` 表示**没有排课**：界面必须显示原因，⛔ 不得显示"已排好课"。 */
  planning: PlanResult | null
  planning_skipped_reason: string | null
  planning_skipped_code: string | null
  assuming_course_ids: string[]
  notes: string[]
}

export type PersonalPlanningErrorKind =
  | 'disabled'
  | 'not_configured'
  | 'input'
  | 'not_projectable'
  | 'unavailable'
  | 'server'
  | 'network'
  | 'unexpected'

export class PersonalPlanningApiError extends Error {
  readonly kind: PersonalPlanningErrorKind
  readonly status: number | null
  readonly code: string | null
  readonly detail: string | null

  constructor(
    kind: PersonalPlanningErrorKind,
    message: string,
    options: { status?: number | null; code?: string | null; detail?: string | null } = {},
  ) {
    super(message)
    this.name = 'PersonalPlanningApiError'
    this.kind = kind
    this.status = options.status ?? null
    this.code = options.code ?? null
    this.detail = options.detail ?? null
  }
}

export const PERSONAL_CATALOG_NOT_CONFIGURED = 'personal_catalog_not_configured'

function messageFor(kind: PersonalPlanningErrorKind, code: string | null): string {
  switch (kind) {
    case 'disabled':
      return '个人规划通道未启用（VITE_PERSONAL_PLANNING_API_ENABLED 未开启）；当前不会请求个人规划接口。'
    case 'not_configured':
      return code === PERSONAL_CATALOG_NOT_CONFIGURED
        ? '当前没有已核验的培养方案版本目录，因此个人规划入口没有可选版本。页面不会退回固定 Case A 冒充个人结果。'
        : '个人规划接口尚未配置（HTTP 404 / 501）。页面不会伪造个人结果。'
    case 'input':
      return '个人规划输入未通过校验（HTTP 422）：请检查版本选择与已修课程记录。'
    case 'not_projectable':
      return '本次输入无法投影（HTTP 422 personal_plan_not_projectable）：这是既有 Curriculum 规则的结论，不是页面错误。'
    case 'unavailable':
      return code === 'personal_plan_course_data_unavailable'
        ? '真实教学班供给当前不可用（acceptance 已失效或不再匹配）；本次不返回任何规划结果。'
        : '个人规划所需的服务端条件未就绪；本次不返回任何规划结果。'
    case 'server':
      return '个人规划服务端错误，请稍后重试。页面不会伪造结果。'
    case 'network':
      return '无法连接个人规划接口。请确认后端已启动。'
    default:
      return '个人规划接口返回的数据结构不符合预期，已停止渲染。'
  }
}

function classify(status: number): PersonalPlanningErrorKind {
  if (status === 404 || status === 501) {
    return 'not_configured'
  }
  if (status === 422) {
    return 'input'
  }
  if (status === 503) {
    return 'unavailable'
  }
  if (status >= 500) {
    return 'server'
  }
  return 'network'
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

function parseErrorBody(rawBody: unknown): { code: string | null; detail: string | null } {
  if (rawBody === null || typeof rawBody !== 'object') {
    return { code: null, detail: null }
  }
  const detail = (rawBody as { detail?: unknown }).detail
  if (detail !== null && typeof detail === 'object' && !Array.isArray(detail)) {
    const record = detail as Record<string, unknown>
    const code = typeof record.error === 'string' ? record.error : null
    const message = typeof record.message === 'string' ? record.message : null
    return { code, detail: message }
  }
  if (Array.isArray(detail)) {
    const first = detail.find(
      (item): item is Record<string, unknown> => item !== null && typeof item === 'object',
    )
    if (first === undefined) {
      return { code: null, detail: null }
    }
    return {
      code: typeof first.type === 'string' ? first.type : null,
      detail: typeof first.msg === 'string' ? first.msg : null,
    }
  }
  return { code: null, detail: typeof detail === 'string' ? detail : null }
}

async function getJson(url: string, signal?: AbortSignal): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' }, signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new PersonalPlanningApiError('network', messageFor('network', null))
  }
  if (!response.ok) {
    const parsed = parseErrorBody(await readBodySafely(response))
    const kind = classify(response.status)
    const finalKind =
      kind === 'input' && parsed.code === 'personal_plan_not_projectable'
        ? 'not_projectable'
        : kind
    throw new PersonalPlanningApiError(finalKind, messageFor(finalKind, parsed.code), {
      status: response.status,
      code: parsed.code,
      detail: parsed.detail,
    })
  }
  return response.json()
}

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
    throw new PersonalPlanningApiError('network', messageFor('network', null))
  }
  if (!response.ok) {
    const parsed = parseErrorBody(await readBodySafely(response))
    const kind = classify(response.status)
    const finalKind =
      kind === 'input' && parsed.code === 'personal_plan_not_projectable'
        ? 'not_projectable'
        : kind
    throw new PersonalPlanningApiError(finalKind, messageFor(finalKind, parsed.code), {
      status: response.status,
      code: parsed.code,
      detail: parsed.detail,
    })
  }
  return response.json()
}

/** 列出可选版本；目录未配置时抛 `not_configured`（⛔ 不返回假版本列表）。 */
export async function fetchCurriculumVersions(
  options: { enabled?: boolean; signal?: AbortSignal } = {},
): Promise<CurriculumVersionList> {
  if (options.enabled === false || !PERSONAL_PLANNING_API_ENABLED) {
    throw new PersonalPlanningApiError('disabled', messageFor('disabled', null))
  }
  const payload = (await getJson(PERSONAL_PLANNING_ENDPOINTS.versions, options.signal)) as
    | CurriculumVersionList
    | null
  if (payload === null || typeof payload !== 'object') {
    throw new PersonalPlanningApiError('unexpected', messageFor('unexpected', null))
  }
  return payload
}

/** 提交个人规划；`planning = null` 是**合法结果**（表示没有排课能力），不是错误。 */
export async function submitPersonalPlan(
  request: PersonalPlanRequest,
  options: { enabled?: boolean; signal?: AbortSignal } = {},
): Promise<PersonalPlanResult> {
  if (options.enabled === false || !PERSONAL_PLANNING_API_ENABLED) {
    throw new PersonalPlanningApiError('disabled', messageFor('disabled', null))
  }
  const payload = (await postJson(PERSONAL_PLANNING_ENDPOINTS.plan, request, options.signal)) as
    | PersonalPlanResult
    | null
  if (payload === null || typeof payload !== 'object') {
    throw new PersonalPlanningApiError('unexpected', messageFor('unexpected', null))
  }
  return payload
}
