/**
 * 成绩单**图片**识别接口调用（`POST /api/v1/transcript-images/recognize`）。
 *
 * ⚠️ 本接口**只产出课程候选**：
 *   ⛔ 不推断课程号、⛔ 不做等价性判断、⛔ 不产生任何 `satisfied`。
 *   识别结果必须经用户在确认页逐条确认后，才能通过 `/case-a-demo/plan`
 *   的 `confirmed_completed_courses` 进入匹配。
 *
 * ⛔ 图片只发往**本项目后端**（本地 OCR）；⛔ 不上传任何第三方。
 */

import { TRANSCRIPT_IMAGES_ENDPOINT } from '../config'

/** 一条待用户确认的课程候选。 */
export interface RecognizedCourseCandidate {
  readonly row_id: string
  readonly course_name: string
  readonly credit: number | null
  readonly score_text: string | null
  readonly semester_text: string | null
  readonly course_attribute: string | null
  /** ⛔ 仅用于提示用户核对，⛔ 不参与任何判定。 */
  readonly confidence: number
  /** 为什么仍需用户确认（后端给出的如实说明）。 */
  readonly unconfirmed: readonly string[]
}

/** 识别结果（全部为候选）。 */
export interface TranscriptImageRecognition {
  readonly source_id: string
  readonly artifact_sha256: string
  readonly media_type: string
  readonly width: number
  readonly height: number
  readonly block_count: number
  /** 被隐私规则丢弃的文本块**数量**（⛔ 后端不回传其内容）。 */
  readonly redacted_block_count: number
  readonly column_groups: number
  readonly candidates: readonly RecognizedCourseCandidate[]
  readonly unrecognized: readonly string[]
}

/** 识别失败的可判别错误。 */
export class TranscriptImageApiError extends Error {
  readonly status: number | null
  readonly code: string | null

  constructor(message: string, status: number | null, code: string | null) {
    super(message)
    this.name = 'TranscriptImageApiError'
    this.status = status
    this.code = code
  }

  /** 本地 OCR 运行时不可用（503）。 */
  get isOcrUnavailable(): boolean {
    return this.code === 'transcript_ocr_not_configured'
  }

  /** 版面无法解析 / 未识别出课程行。 */
  get isUnreadable(): boolean {
    return this.code === 'transcript_image_no_records'
  }

  /** 网络层失败（没有 HTTP 响应）。 */
  get isNetworkFailure(): boolean {
    return this.status === null
  }
}

/** 允许的图片类型（与后端一致）。 */
export const ACCEPTED_IMAGE_TYPES = 'image/png,image/jpeg,image/webp'

/** 图片大小上限（与后端 `MAX_IMAGE_BYTES` 一致）。 */
export const MAX_IMAGE_BYTES = 8 * 1024 * 1024

async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  const chunk = 0x8000
  for (let start = 0; start < bytes.length; start += chunk) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunk))
  }
  return btoa(binary)
}

/** 调用识别接口；失败时抛出可判别错误（⛔ 不回退演示数据）。 */
export async function recognizeTranscriptImage(
  file: File,
): Promise<TranscriptImageRecognition> {
  let response: Response
  try {
    response = await fetch(TRANSCRIPT_IMAGES_ENDPOINT, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_base64: await fileToBase64(file),
        media_type: file.type,
      }),
    })
  } catch {
    throw new TranscriptImageApiError('识别请求失败：无法连接后端。', null, null)
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail
    const code =
      detail && typeof detail === 'object' && 'error' in detail
        ? String((detail as { error?: unknown }).error ?? '') || null
        : null
    const message =
      detail && typeof detail === 'object' && 'message' in detail
        ? String((detail as { message?: unknown }).message ?? '')
        : `识别失败（HTTP ${response.status}）`
    throw new TranscriptImageApiError(message, response.status, code)
  }
  const payload = body as TranscriptImageRecognition | null
  if (!payload || !Array.isArray(payload.candidates)) {
    throw new TranscriptImageApiError('识别返回格式异常。', response.status, 'invalid_payload')
  }
  return payload
}

/* -------------------------------------------------------------------------- *
 * 确认结果 → 提交用的课程记录（`completed.records` 形状）
 * -------------------------------------------------------------------------- */

/**
 * 提交给 `POST /case-a-demo/plan` 的一条已修课程记录。
 *
 * ⚠️ 这正是后端 `completed.records` 的输入形状 —— 与成绩单 PDF 入口
 * **完全同形状**，因此两条入口必然进入同一个匹配引擎。
 */
export interface ConfirmedCompletedCourseRecord {
  readonly course_id: null
  readonly course_name: string
  readonly credit: number
  readonly semester: string
  readonly passed: boolean
  readonly course_type: null
  readonly course_id_status: 'pending'
  readonly id_match_source: null
  readonly source_record: string
}

/** 用户在确认页上确认/编辑后的一行。 */
export interface ConfirmedCourseRow {
  readonly rowId: string
  readonly courseName: string
  readonly credit: number | null
  readonly scoreText: string | null
  readonly semesterText: string | null
  readonly passed: boolean
}

/**
 * 把**已确认**的行转换成后端可接受的课程记录。
 *
 * ⛔ 硬边界：
 *   - `course_id` 恒 `null`（图片没有官方课程号，⛔ 不推断）；
 *   - `course_id_status` 恒 `'pending'`（⇒ 后端不可能据此自动认定）；
 *   - `source_record` 用 `img:<rowId>`，与 PDF 入口的 `pdf:<n>` 对称。
 */
export function toConfirmedRecords(
  rows: readonly ConfirmedCourseRow[],
): ConfirmedCompletedCourseRecord[] {
  return rows.map((row) => ({
    course_id: null,
    course_name: row.courseName.trim(),
    // 未填学分按 0.0 提交，并在课程名后不附加任何猜测；后端会按事实处理。
    credit: row.credit ?? 0,
    semester: row.semesterText?.trim() || 'unknown',
    passed: row.passed,
    course_type: null,
    course_id_status: 'pending',
    id_match_source: null,
    source_record: `img:${row.rowId}`,
  }))
}

/** 由候选构造初始确认行（默认**全部未确认**，需用户逐条勾选）。 */
export function toCandidateRow(candidate: RecognizedCourseCandidate): ConfirmedCourseRow {
  return {
    rowId: candidate.row_id,
    courseName: candidate.course_name,
    credit: candidate.credit,
    scoreText: candidate.score_text,
    semesterText: candidate.semester_text,
    // ⚠️ 成绩读不出时按"未通过"处理（保守），用户可在确认页修正。
    //    但⛔ 这类行本身是"未识别"的（见 `candidateRecognitionStatus`），不可被确认。
    passed: candidate.score_text !== null && !/^(NP|不合格|不及格|不通过)$/.test(candidate.score_text),
  }
}

/* -------------------------------------------------------------------------- *
 * OCR 候选**识别状态**（前端派生，⛔ 不改后端 schema）
 * -------------------------------------------------------------------------- */

/**
 * 候选的识别状态。
 *
 * ⚠️ 存在的理由（业务闭环要求）：
 *   「未识别的候选**只能展示**，⛔ 不得进入 `confirmed_completed_courses`」。
 *   识别层没有布尔字段，因此这里由**识别结果本身**派生：
 *   ⛔ 不用课程名过滤（那是猜测），只用识别出来/没识别出来这一事实。
 */
export type CandidateStatus = 'recognized' | 'unrecognized'

/** 识别状态的中文原因（页面如实展示，⛔ 不含任何猜测）。 */
export const CANDIDATE_STATUS_REASON: Readonly<Record<'no_name' | 'no_score', string>> = {
  no_name: '未识别到课程名',
  no_score: '未识别到成绩（无法判断是否通过）',
}

/** 逐条给出不可确认的原因；可确认时返回空数组。 */
export function candidateUnrecognizedReasons(
  candidate: RecognizedCourseCandidate,
): ('no_name' | 'no_score')[] {
  const reasons: ('no_name' | 'no_score')[] = []
  if ((candidate.course_name ?? '').trim() === '') reasons.push('no_name')
  // ⛔ 成绩读不出 ⇒ 无法判断是否通过 ⇒ 不可确认（用户不能凭空断言）
  if (candidate.score_text === null || candidate.score_text.trim() === '') reasons.push('no_score')
  return reasons
}

/**
 * 候选的识别状态。
 *
 * ```text
 * recognized    识别到课程名 + 成绩 ⇒ 可被用户确认
 * unrecognized  缺课程名或缺成绩   ⇒ ⛔ 只能展示，不得进入 confirmed 记录
 * ```
 */
export function candidateRecognitionStatus(
  candidate: RecognizedCourseCandidate,
): CandidateStatus {
  return candidateUnrecognizedReasons(candidate).length === 0 ? 'recognized' : 'unrecognized'
}
