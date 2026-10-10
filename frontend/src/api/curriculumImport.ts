/**
 * 培养方案 PDF 导入客户端（⚠️ 本轮新增）。
 *
 * ```text
 * 选择文件 → 读取为 ArrayBuffer → POST 原始字节（⛔ 不用 multipart）
 *          → 后端安全校验 + 表格解析 → **待组长审核**的草稿
 * ```
 *
 * ## 边界（⛔ 前端做不到、也不该做的事）
 *
 * | ⛔ 不能 | 为什么 |
 * | --- | --- |
 * | 把草稿当成"已核验培养方案" | 核验只能由组长签发的批准锚点决定 |
 * | 「用户确认解析正确」改写任何锚点 | 那是**两个不同的问题**（见下） |
 * | 解析失败时回退到 Mock 结果 | ⛔ 不允许伪造解析成功 |
 *
 * ## 「用户确认解析正确」≠「组长批准真实来源」
 *
 * - **用户确认**：这份 PDF 被**正确读成了课程表**（这一份文件→这一份草稿的映射对不对）；
 * - **组长批准**：这份材料的**来源可信**（它是不是学校/学院正式提供、版本学期对不对）。
 *
 * 前端只能表达前者，⛔ 永远不能表达后者。
 */

import { CURRICULUM_IMPORT_ENDPOINTS } from '../config'

/** 原专业 / 目标专业。 */
export type CurriculumRole = 'origin' | 'target'

/** 一个**已验收**的文档类型（由后端注册表给出，⛔ 前端不得自定义列位映射）。 */
export interface CurriculumDocumentType {
  key: string
  major: string
  cohort: string
  label: string
  verified_pages: number
  declared_tables: number
}

/** 上传前的本地校验上限（与后端 `MAX_UPLOAD_BYTES` 一致：8 MiB）。 */
export const MAX_PDF_UPLOAD_BYTES = 8 * 1024 * 1024

/** ⛔ 只接受 PDF：扩展名与 MIME 双重判断（⛔ 不靠单一信号）。 */
export const PDF_MIME_TYPE = 'application/pdf'

/** 后端错误码（⛔ 前端只展示固定文案，⛔ 不回显后端细节）。 */
export type CurriculumImportErrorKind =
  | 'disabled'
  | 'bad_media_type'
  | 'missing_length'
  | 'too_large'
  | 'empty'
  | 'length_mismatch'
  | 'unparsable'
  | 'network'
  | 'contract'

const ERROR_KIND_BY_CODE: Record<string, CurriculumImportErrorKind> = {
  pdf_upload_media_type_unsupported: 'bad_media_type',
  pdf_upload_length_required: 'missing_length',
  pdf_upload_too_large: 'too_large',
  pdf_upload_empty: 'empty',
  pdf_upload_declared_length_mismatch: 'length_mismatch',
  pdf_import_unparsable: 'unparsable',
}

/** 错误码 → 面向用户的固定文案。⛔ 不拼接后端返回的 message（可能含私有文本）。 */
export const CURRICULUM_IMPORT_ERROR_LABEL: Record<CurriculumImportErrorKind, string> = {
  disabled: '培养方案导入通道未启用（VITE_CURRICULUM_IMPORT_API_ENABLED=false）。',
  bad_media_type: '只接受 PDF 文件（⛔ 不接受其它格式）。',
  missing_length: '上传缺少长度声明，已被拒绝。',
  too_large: `文件超过上限（${Math.round(MAX_PDF_UPLOAD_BYTES / 1024 / 1024)} MiB）。`,
  empty: '文件为空。',
  length_mismatch: '上传内容不完整（声明长度与实际不一致）。',
  unparsable:
    '这份 PDF 无法解析：可能是损坏文件、扫描件（无文本层，本项目⛔ 不做 OCR），'
    + '或表格结构与预期不符。请转人工处理，⛔ 不会用演示数据替代。',
  network: '请求失败：无法连接后端。',
  contract: '后端响应不符合约定的契约。',
}

/**
 * 拉取**已验收**的文档类型清单。
 *
 * ⛔ 前端只能从这个清单里选，⛔ 不能提交任何课程列位映射 ——
 * profile 由后端注册表给出，调用方无法影响"哪一列是课程编码"。
 */
export async function fetchCurriculumDocumentTypes(
  options: { enabled: boolean },
): Promise<CurriculumDocumentType[]> {
  if (!options.enabled) {
    throw new CurriculumImportError('disabled')
  }
  let response: Response
  try {
    response = await fetch(CURRICULUM_IMPORT_ENDPOINTS.documentTypes, { method: 'GET' })
  } catch {
    throw new CurriculumImportError('network')
  }
  if (!response.ok) {
    throw new CurriculumImportError('contract')
  }
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new CurriculumImportError('contract')
  }
  const list = (payload as { document_types?: unknown })?.document_types
  if (!Array.isArray(list)) {
    throw new CurriculumImportError('contract')
  }
  return list.map((item) => {
    const record = item as Record<string, unknown>
    if (typeof record['key'] !== 'string' || typeof record['label'] !== 'string') {
      throw new CurriculumImportError('contract')
    }
    return {
      key: record['key'],
      major: String(record['major'] ?? ''),
      cohort: String(record['cohort'] ?? ''),
      label: record['label'],
      verified_pages: Number(record['verified_pages'] ?? 0),
      declared_tables: Number(record['declared_tables'] ?? 0),
    }
  })
}

export class CurriculumImportError extends Error {
  readonly kind: CurriculumImportErrorKind

  constructor(kind: CurriculumImportErrorKind) {
    super(CURRICULUM_IMPORT_ERROR_LABEL[kind])
    this.name = 'CurriculumImportError'
    this.kind = kind
  }
}

/** 一条待人工确认项。 */
export interface CurriculumHumanRequired {
  field: string
  reason: string
  applies_to: string
}

/** 一条解析出的课程记录。 */
export interface CurriculumCourseRecord {
  course_id: string | null
  course_name: string | null
  credit: number | null
  requirement: string
  source_record: string
  course_type?: string | null
  group_id?: string | null
  recommended_term_text?: string | null
  issues?: { code: string; row_index: number; field: string | null }[]
}

/** 解析草稿（**永远**是待审核状态）。 */
export interface CurriculumDraft {
  status: string
  source: { kind: string; name: string; role: string }
  source_id: string
  course_records: CurriculumCourseRecord[]
  group_records: Record<string, unknown>[]
  unresolved_rows: CurriculumCourseRecord[]
  document_issues: { code: string; table_index: number; row_index: number }[]
  human_required: CurriculumHumanRequired[]
}

/** 来源与审核状态说明。 */
export interface CurriculumSourceNote {
  kind: string
  file_name: string
  sha256: string
  role: CurriculumRole
  source: string
  is_official_school_pdf: boolean
  review_conclusion: string
  verification_verified: boolean
  complete: boolean
  notes: string[]
}

/**
 * 解析响应里的**审核会话**摘要（本轮新增）。
 *
 * ⚠️ 只带 `review_id` 与统计；⛔ 证据与候选由服务端保管，前端按需拉取。
 */
export interface CurriculumReviewSummary {
  review_id: string | null
  expires_in_seconds?: number
  statistics?: Record<string, unknown>
  progress?: Record<string, unknown>
  endpoints?: Record<string, string>
  notes?: string[]
  error?: string
  message?: string
}

export interface CurriculumParseResult {
  source_id: string
  major: string
  cohort: string
  source: CurriculumSourceNote
  draft: CurriculumDraft
  report: string
  /** 审核会话；`review_id` 为 `null` 表示会话未建立（⛔ 前端不伪造）。 */
  review?: CurriculumReviewSummary | null
}

/**
 * 把响应体解析成 `CurriculumParseResult`。
 *
 * ⚠️ 用**显式**字段检查而不是 `as`：后端契约变化必须**报错**，
 * ⛔ 不能悄悄把缺字段当成「空结果」继续往下走。
 */
export function parseCurriculumParseResult(payload: unknown): CurriculumParseResult {
  if (typeof payload !== 'object' || payload === null) {
    throw new CurriculumImportError('contract')
  }
  const record = payload as Record<string, unknown>
  const draft = record['draft']
  const source = record['source']
  if (typeof draft !== 'object' || draft === null) {
    throw new CurriculumImportError('contract')
  }
  if (typeof source !== 'object' || source === null) {
    throw new CurriculumImportError('contract')
  }
  const draftRecord = draft as Record<string, unknown>
  const sourceRecord = source as Record<string, unknown>
  if (!Array.isArray(draftRecord['course_records'])) {
    throw new CurriculumImportError('contract')
  }
  if (!Array.isArray(draftRecord['human_required'])) {
    throw new CurriculumImportError('contract')
  }
  if (typeof record['source_id'] !== 'string') {
    throw new CurriculumImportError('contract')
  }
  return {
    source_id: record['source_id'],
    major: typeof record['major'] === 'string' ? record['major'] : '',
    cohort: typeof record['cohort'] === 'string' ? record['cohort'] : '',
    source: {
      kind: String(sourceRecord['kind'] ?? ''),
      file_name: String(sourceRecord['file_name'] ?? ''),
      sha256: String(sourceRecord['sha256'] ?? ''),
      role: sourceRecord['role'] === 'target' ? 'target' : 'origin',
      source: String(sourceRecord['source'] ?? ''),
      // ⚠️ 默认按**最保守**解释：缺字段即视为"不是学校正式签发"。
      is_official_school_pdf: sourceRecord['is_official_school_pdf'] === true,
      review_conclusion: String(sourceRecord['review_conclusion'] ?? ''),
      verification_verified: sourceRecord['verification_verified'] === true,
      complete: sourceRecord['complete'] === true,
      notes: Array.isArray(sourceRecord['notes'])
        ? (sourceRecord['notes'] as unknown[]).map((item) => String(item))
        : [],
    },
    draft: {
      status: String(draftRecord['status'] ?? ''),
      source: (draftRecord['source'] ?? {}) as CurriculumDraft['source'],
      source_id: String(draftRecord['source_id'] ?? ''),
      course_records: draftRecord['course_records'] as CurriculumCourseRecord[],
      group_records: Array.isArray(draftRecord['group_records'])
        ? (draftRecord['group_records'] as Record<string, unknown>[])
        : [],
      unresolved_rows: Array.isArray(draftRecord['unresolved_rows'])
        ? (draftRecord['unresolved_rows'] as CurriculumCourseRecord[])
        : [],
      document_issues: Array.isArray(draftRecord['document_issues'])
        ? (draftRecord['document_issues'] as CurriculumDraft['document_issues'])
        : [],
      human_required: draftRecord['human_required'] as CurriculumHumanRequired[],
    },
    report: typeof record['report'] === 'string' ? record['report'] : '',
    review: _parseReviewSummary(record['review']),
  }
}

/** 解析 `review` 段；⛔ 缺字段时返回 `null`，⛔ 不编造 review_id。 */
function _parseReviewSummary(raw: unknown): CurriculumReviewSummary | null {
  if (typeof raw !== 'object' || raw === null) {
    return null
  }
  const record = raw as Record<string, unknown>
  const reviewId = record['review_id']
  return {
    review_id: typeof reviewId === 'string' && reviewId ? reviewId : null,
    expires_in_seconds:
      typeof record['expires_in_seconds'] === 'number' ? record['expires_in_seconds'] : undefined,
    statistics: (record['statistics'] ?? undefined) as Record<string, unknown> | undefined,
    progress: (record['progress'] ?? undefined) as Record<string, unknown> | undefined,
    endpoints: (record['endpoints'] ?? undefined) as Record<string, string> | undefined,
    notes: Array.isArray(record['notes'])
      ? (record['notes'] as unknown[]).map((item) => String(item))
      : undefined,
    error: typeof record['error'] === 'string' ? record['error'] : undefined,
    message: typeof record['message'] === 'string' ? record['message'] : undefined,
  }
}

/** 上传前的**本地**校验（⛔ 只是快速失败，权威校验在后端）。 */
export function validatePdfFile(file: { name: string; size: number; type: string }):
  CurriculumImportErrorKind | null {
  if (file.size === 0) {
    return 'empty'
  }
  if (file.size > MAX_PDF_UPLOAD_BYTES) {
    return 'too_large'
  }
  const looksPdf = file.name.toLowerCase().endsWith('.pdf')
    || file.type === PDF_MIME_TYPE
  return looksPdf ? null : 'bad_media_type'
}

/** 读取文件字节；⛔ 不做任何解码（PDF 是二进制）。 */
async function readBytes(file: File): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === 'function') {
    return new Uint8Array(await file.arrayBuffer())
  }
  // 某些运行环境（jsdom 的旧版本 / 极老的浏览器）没有 `File.arrayBuffer`。
  return await new Promise<Uint8Array>((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new CurriculumImportError('network'))
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer))
    reader.readAsArrayBuffer(file)
  })
}

/**
 * 上传一份培养方案 PDF 并取回**待审核**草稿。
 *
 * ⛔ 不做任何"成功不了的降级"：失败就抛 `CurriculumImportError`，⛔ 不返回假结果。
 */
export async function parseCurriculumPdf(
  file: File,
  options: {
    role: CurriculumRole
    major: string
    cohort: string
    source: string
    enabled: boolean
    /**
     * ⚠️ 已验收文档类型的 key —— 它只是**断言**：
     * 后端会与"按内容结构判定的结果"核对，不一致即 422。
     * ⛔ 它**不是**列位映射，前端无法用它改变"哪一列是课程编码"。
     */
    documentType?: string | undefined
  },
): Promise<CurriculumParseResult> {
  if (!options.enabled) {
    throw new CurriculumImportError('disabled')
  }
  const local = validatePdfFile(file)
  if (local !== null) {
    throw new CurriculumImportError(local)
  }

  const bytes = await readBytes(file)
  // ⚠️ 转成普通 `ArrayBuffer`：TS 的 `BodyInit` 不接受 `Uint8Array<ArrayBufferLike>`。
  const body = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
  const query = new URLSearchParams({
    role: options.role,
    major: options.major,
    cohort: options.cohort,
    source: options.source,
  })
  if (options.documentType) {
    query.set('document_type', options.documentType)
  }

  let response: Response
  try {
    response = await fetch(`${CURRICULUM_IMPORT_ENDPOINTS.parsePdf}?${query.toString()}`, {
      method: 'POST',
      headers: {
        // ⚠️ 显式声明类型与长度：后端**要求** Content-Length（缺失 ⇒ 411）。
        'Content-Type': PDF_MIME_TYPE,
        'Content-Length': String(body.byteLength),
        // ⛔ 只传**基名**：不把本地路径交给后端。
        'X-File-Name': file.name.split(/[\\/]/).pop() ?? 'curriculum.pdf',
      },
      body,
    })
  } catch {
    throw new CurriculumImportError('network')
  }

  if (!response.ok) {
    let code = ''
    try {
      const detail = (await response.json()) as { detail?: { error?: unknown } }
      code = typeof detail.detail?.error === 'string' ? detail.detail.error : ''
    } catch {
      code = ''
    }
    throw new CurriculumImportError(ERROR_KIND_BY_CODE[code] ?? 'unparsable')
  }

  return parseCurriculumParseResult(await response.json())
}
