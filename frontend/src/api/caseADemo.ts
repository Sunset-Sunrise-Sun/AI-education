import { CASE_A_DEMO_OFFERINGS_ENDPOINT, CASE_A_DEMO_PLAN_ENDPOINT } from '../config'
// ⚠️ roadmap 是**前端集成类型**（见 caseAPlanning.ts），⛔ 不是公共契约。
import type { FutureRoadmap } from '../types/caseAPlanning'
import type { CourseOffering, MakeupTask, PlanResult, Preference } from '../types/contracts'
import type { ElectiveProgress } from '../types/studyPlan'
import type { ConfirmedCompletedCourseRecord } from './transcriptImages'

export interface CaseADemoResponse {
  transcript: {
    source_id: string
    artifact_sha256: string
    record_count: number
    term_count: number
    terms: string[]
    pending_course_id_count: number
  }
  makeup_tasks: MakeupTask[]
  course_offerings: CourseOffering[]
  preference: Preference
  plan_result: PlanResult
  /**
   * 课程组学分进度（Phase 4）。
   *
   * ⚠️ 由后端 matching 层计算并下发，⛔ 前端不得自行计算剩余学分。
   * 可选：未提供课程组的方案不会带该字段。
   */
  elective_progress?: ElectiveProgress[]
  provenance: {
    transcript: string
    curriculum: string
    course_data: string
    current_schedule: string
    planner: string
    is_full_semester: boolean
  }
  /**
   * 未来学期修读路径（**可选**）。
   *
   * ⚠️ 后端当前**不返回**该字段。前端只在它真的存在且含学期数据时渲染，
   * ⛔ 缺省时整块不渲染、⛔ 不补任何假数据。
   */
  roadmap?: FutureRoadmap | null
}

/**
 * Case A 接口失败的**可判别**错误。
 *
 * ⚠️ 存在的理由：页面必须能区分"**运行时未配置**"与"网络/其它失败"，
 * 才能在**没有可信证据**时使用中性表述，而不是无条件宣称"已加载真实数据"。
 * ⛔ 本类只做错误归类，⛔ 不改变任何请求或数据结构。
 */
export class CaseAApiError extends Error {
  readonly status: number | null
  /** 后端 `detail.error` 的固定错误码（若提供）。 */
  readonly code: string | null

  constructor(message: string, status: number | null, code: string | null) {
    super(message)
    this.name = 'CaseAApiError'
    this.status = status
    this.code = code
  }

  /** 运行时**未配置**（后端 503 + `case_a_demo_not_configured`）。 */
  get isNotConfigured(): boolean {
    return this.code === 'case_a_demo_not_configured'
  }

  /** 请求根本没拿到 HTTP 响应（网络层失败）。 */
  get isNetworkFailure(): boolean {
    return this.status === null
  }
}

async function checkedJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    // 尽量取出后端的固定错误码；⛔ 取不到就如实留空，⛔ 不猜测
    const detail = (body as { detail?: unknown } | null)?.detail
    const code =
      detail && typeof detail === 'object' && 'error' in detail
        ? String((detail as { error?: unknown }).error ?? '') || null
        : null
    throw new CaseAApiError(
      `Case A demo request failed (HTTP ${response.status}).`,
      response.status,
      code,
    )
  }
  return body as T
}

export async function loadCaseAOfferings(semester: string): Promise<CourseOffering[]> {
  const url = `${CASE_A_DEMO_OFFERINGS_ENDPOINT}?semester=${encodeURIComponent(semester)}`
  let response: Response
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' } })
  } catch {
    // 网络层失败：⛔ 没有 HTTP 响应 ⇒ 如实标为网络失败，⛔ 不编造状态码
    throw new CaseAApiError('教学班数据请求失败：无法连接后端。', null, null)
  }
  return checkedJson<CourseOffering[]>(response)
}

async function fileBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  const chunk = 0x8000
  for (let start = 0; start < bytes.length; start += chunk) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunk))
  }
  return btoa(binary)
}

export async function runCaseADemo(input: {
  /** 成绩单 PDF 文件；与 `confirmedCourses` **二选一**。 */
  file?: File | null
  /** 用户确认后的图片识别课程记录；与 `file` **二选一**。 */
  confirmedCourses?: readonly ConfirmedCompletedCourseRecord[] | null
  semester: string
  currentSchedule: CourseOffering[]
  manualScheduleAttested: boolean
  preference: Preference
}): Promise<CaseADemoResponse> {
  const hasFile = input.file != null
  const hasConfirmed = (input.confirmedCourses?.length ?? 0) > 0
  if (hasFile === hasConfirmed) {
    // ⛔ 前端就挡住：两条入口必须恰好提供一个（后端也会拒绝）。
    throw new CaseAApiError(
      '请恰好提供一种成绩单输入（PDF 或图片确认结果）。',
      null,
      'transcript_input_ambiguous',
    )
  }

  const body: Record<string, unknown> = {
    semester: input.semester,
    current_schedule: input.currentSchedule,
    manual_schedule_attested: input.manualScheduleAttested,
    preference: input.preference,
  }
  if (hasFile) {
    body.transcript_pdf_base64 = await fileBase64(input.file as File)
  } else {
    // ⚠️ 只提交**用户已确认**的记录；⛔ OCR 原始候选结构（row_id/confidence）
    //    不会出现在这里（后端 `extra="forbid"` 也会拒绝）。
    body.confirmed_completed_courses = input.confirmedCourses
  }

  return checkedJson<CaseADemoResponse>(
    await fetch(CASE_A_DEMO_PLAN_ENDPOINT, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}
