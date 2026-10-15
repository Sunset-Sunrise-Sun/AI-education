/**
 * 成绩单**已修课程**读取（前端集成层）。
 *
 * ## 为什么要调这个接口
 *
 * 未来学习路径必须**扣除学生已修课程**，否则已满足的课会再次出现在未来规划里
 * （Review 发现的业务错误）。而 `POST /api/v1/case-a-demo/plan` 的响应里
 * **只有成绩单摘要**（`record_count` 等），**不返回已修课程明细** ——
 * 因此前端无从扣除。
 *
 * 这里复用**既有**的通用摄取接口：
 *
 * ```text
 * POST /api/v1/completed-courses/import-pdf
 *   → completed_input.records[]   （课程名 / 学分 / 是否通过 / 课程号状态）
 * ```
 *
 * ⚠️ 边界（很重要）：
 * - ⛔ **不是**新接口：该 endpoint 早已在 main 上实现，只是前端此前没有调用；
 * - ⛔ 不新增 / 不修改任何后端 schema、字段或路径；
 * - ⛔ 本模块**不做课程认定**：只把成绩单事实读回来，判定逻辑在
 *   `utils/futureRoadmap.ts`，且只用于"同名且通过 ⇒ 已满足"这一条规则；
 * - ⛔ 不回退到演示数据：失败时如实抛错，由调用方降级并**如实告知**用户。
 */

import { COMPLETED_COURSES_PDF_ENDPOINT } from '../config'
import type { CompletedCourseRecord } from '../utils/futureRoadmap'

/** 接口失败的**可判别**错误（与其它 api 模块风格一致）。 */
export class CompletedCoursesApiError extends Error {
  readonly status: number | null
  readonly code: string | null

  constructor(message: string, status: number | null, code: string | null) {
    super(message)
    this.name = 'CompletedCoursesApiError'
    this.status = status
    this.code = code
  }

  /** 请求根本没拿到 HTTP 响应（网络层失败）。 */
  get isNetworkFailure(): boolean {
    return this.status === null
  }
}

/** 后端响应里我们真正用到的部分。 */
interface PreviewResponse {
  record_count?: number
  passed_count?: number
  completed_input?: {
    source_id?: string
    records?: {
      course_name?: unknown
      credit?: unknown
      passed?: unknown
    }[]
  }
}

/**
 * 读取成绩单 PDF 里的**已修课程明细**。
 *
 * ⚠️ 只读：不写任何状态、不改 demo 上下文、不触发匹配。
 * 失败时抛出 `CompletedCoursesApiError`，⛔ 不返回伪造数据。
 */
export async function loadCompletedCourses(
  file: File,
): Promise<CompletedCourseRecord[]> {
  let response: Response
  try {
    response = await fetch(COMPLETED_COURSES_PDF_ENDPOINT, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/pdf',
      },
      body: file,
    })
  } catch {
    throw new CompletedCoursesApiError('成绩单已修课程请求失败：无法连接后端。', null, null)
  }

  const body = (await response.json().catch(() => null)) as
    | { detail?: { error?: unknown } }
    | PreviewResponse
    | null

  if (!response.ok) {
    const detail = (body as { detail?: { error?: unknown } } | null)?.detail
    const code =
      detail && typeof detail === 'object' && 'error' in detail
        ? String(detail.error ?? '') || null
        : null
    throw new CompletedCoursesApiError(
      `成绩单已修课程请求失败（HTTP ${response.status}）。`,
      response.status,
      code,
    )
  }

  const records = (body as PreviewResponse)?.completed_input?.records ?? []
  const parsed: CompletedCourseRecord[] = []
  for (const record of records) {
    // ⚠️ 字段形状不符就**跳过该条**，⛔ 不猜、⛔ 不用默认值补齐
    if (typeof record.course_name !== 'string' || record.course_name.trim() === '') continue
    parsed.push({
      course_name: record.course_name,
      credit: typeof record.credit === 'number' ? record.credit : null,
      passed: record.passed === true,
    })
  }
  return parsed
}
