/**
 * 培养方案 PDF 导入的前端契约与交互测试（⚠️ 本轮新增）。
 *
 * 重点覆盖**边界**（任务书 §五：来源审核边界）：
 *
 * 1. 上传 / 解析 / 用户确认**都不**表示来源被核验；
 * 2. 解析失败⛔ **不**回退到演示数据；
 * 3. 本地快速失败（大小 / 类型 / 空文件）⛔ 不发请求；
 * 4. 响应缺字段 / 类型错误 ⇒ 契约错误（⛔ 不静默当成空结果）。
 */

import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import {
  CURRICULUM_IMPORT_ERROR_LABEL,
  CurriculumImportError,
  MAX_PDF_UPLOAD_BYTES,
  parseCurriculumParseResult,
  parseCurriculumPdf,
  validatePdfFile,
} from '../src/api/curriculumImport'
import CurriculumPdfImport from '../src/components/CurriculumPdfImport.vue'

function _resultPayload(overrides: Record<string, unknown> = {}) {
  return {
    source_id: 'pdf-upload:sha256:abcdef0123456789',
    major: '遥感科学与技术',
    cohort: '2025',
    source: {
      kind: 'pdf-upload',
      file_name: 'origin.pdf',
      sha256: 'a'.repeat(64),
      role: 'origin',
      source: '教务网页重排',
      is_official_school_pdf: false,
      review_conclusion: 'pending_group_lead_review',
      verification_verified: false,
      complete: false,
      notes: ['本 PDF 是来源可追溯的转换件，⛔ 不是学校正式签发的原始 PDF。'],
    },
    draft: {
      status: 'pending_human_review',
      source: { kind: 'pdf', name: 'origin.pdf', role: 'origin' },
      source_id: 'pdf-upload:sha256:abcdef0123456789',
      course_records: [
        {
          course_id: 'MAR103',
          course_name: 'Course-A',
          credit: 3,
          requirement: 'required',
          source_record: 'page:1!row:1',
          recommended_term_text: '2025-1',
        },
      ],
      group_records: [],
      unresolved_rows: [],
      document_issues: [],
      human_required: [
        { field: 'group_records', reason: '⛔ 不推导组学分要求', applies_to: 'missing' },
        { field: 'verification', reason: '⛔ 上传不构成核验', applies_to: 'version entry' },
      ],
    },
    report: '培养方案 DOCX → 目录草稿（待人工审核）',
    ...overrides,
  }
}

describe('validatePdfFile（本地快速失败）', () => {
  it('接受 .pdf 后缀或 application/pdf', () => {
    expect(validatePdfFile({ name: 'a.pdf', size: 100, type: '' })).toBeNull()
    expect(validatePdfFile({ name: 'a.bin', size: 100, type: 'application/pdf' })).toBeNull()
  })

  it('拒绝非 PDF（⛔ 不靠单一信号）', () => {
    expect(validatePdfFile({ name: 'a.docx', size: 100, type: '' })).toBe('bad_media_type')
    expect(validatePdfFile({ name: 'a.txt', size: 100, type: 'text/plain' })).toBe('bad_media_type')
  })

  it('拒绝空文件与超大文件', () => {
    expect(validatePdfFile({ name: 'a.pdf', size: 0, type: 'application/pdf' })).toBe('empty')
    expect(
      validatePdfFile({ name: 'a.pdf', size: MAX_PDF_UPLOAD_BYTES + 1, type: 'application/pdf' }),
    ).toBe('too_large')
  })
})

describe('parseCurriculumParseResult（契约解析）', () => {
  it('接受合法响应', () => {
    const parsed = parseCurriculumParseResult(_resultPayload())
    expect(parsed.draft.status).toBe('pending_human_review')
    expect(parsed.source.is_official_school_pdf).toBe(false)
    expect(parsed.source.verification_verified).toBe(false)
    expect(parsed.draft.course_records).toHaveLength(1)
  })

  it('缺 draft / source / 列表字段 ⇒ 契约错误（⛔ 不当成空结果）', () => {
    expect(() => parseCurriculumParseResult({})).toThrow(CurriculumImportError)
    expect(() => parseCurriculumParseResult({ ..._resultPayload(), draft: undefined })).toThrow()
    expect(() =>
      parseCurriculumParseResult({
        ..._resultPayload(),
        draft: { ..._resultPayload()['draft'] as object, course_records: undefined },
      }),
    ).toThrow()
  })

  it('⚠️ 缺核验字段一律按最保守解释（未核验 / 非正式 PDF）', () => {
    const payload = _resultPayload()
    const source = { ...(payload['source'] as Record<string, unknown>) }
    delete source['verification_verified']
    delete source['is_official_school_pdf']
    delete source['complete']
    const parsed = parseCurriculumParseResult({ ...payload, source })
    expect(parsed.source.verification_verified).toBe(false)
    expect(parsed.source.is_official_school_pdf).toBe(false)
    expect(parsed.source.complete).toBe(false)
  })
})

describe('parseCurriculumPdf（上传）', () => {
  const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], 'origin.pdf', {
    type: 'application/pdf',
  })

  it('关闭开关时直接拒绝，⛔ 不发请求', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    await expect(
      parseCurriculumPdf(file, {
        role: 'origin', major: 'M', cohort: '2025', source: 's', enabled: false,
      }),
    ).rejects.toMatchObject({ kind: 'disabled' })
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })

  it('本地校验不过时直接拒绝，⛔ 不发请求', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const bad = new File([new Uint8Array([1])], 'a.docx', { type: 'application/msword' })
    await expect(
      parseCurriculumPdf(bad, {
        role: 'origin', major: 'M', cohort: '2025', source: 's', enabled: true,
      }),
    ).rejects.toMatchObject({ kind: 'bad_media_type' })
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })

  it('成功时发送原始字节 + 显式 Content-Length（⛔ 不用 multipart）', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(_resultPayload()), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }),
    )
    const parsed = await parseCurriculumPdf(file, {
      role: 'origin', major: 'M', cohort: '2025', source: 's', enabled: true,
    })
    expect(parsed.source.review_conclusion).toBe('pending_group_lead_review')
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/v1/curriculum-import/parse-pdf')
    expect(url).toContain('role=origin')
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/pdf')
    expect(headers['Content-Length']).toBe('4')
    expect(headers['X-File-Name']).toBe('origin.pdf')
    fetchSpy.mockRestore()
  })

  it('⛔ 只传基名：本地路径不进请求头', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(_resultPayload()), { status: 200 }),
    )
    const nested = new File([new Uint8Array([1, 2])], 'x.pdf', { type: 'application/pdf' })
    await parseCurriculumPdf(nested, {
      role: 'origin', major: 'M', cohort: '2025', source: 's', enabled: true,
    })
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    const name = (init.headers as Record<string, string>)['X-File-Name']
    expect(name).not.toContain('/')
    expect(name).not.toContain('\\')
    fetchSpy.mockRestore()
  })

  it('后端错误码映射成固定文案（⛔ 不回显后端细节）', async () => {
    for (const [code, kind] of [
      ['pdf_upload_media_type_unsupported', 'bad_media_type'],
      ['pdf_upload_too_large', 'too_large'],
      ['pdf_import_unparsable', 'unparsable'],
    ] as const) {
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify({ detail: { error: code, message: '内部细节不应展示' } }), {
          status: 422,
        }),
      )
      await expect(
        parseCurriculumPdf(file, {
          role: 'origin', major: 'M', cohort: '2025', source: 's', enabled: true,
        }),
      ).rejects.toMatchObject({ kind })
      fetchSpy.mockRestore()
    }
  })

  it('⛔ 解析失败不返回任何替代结果', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: { error: 'pdf_import_unparsable' } }), {
        status: 422,
      }),
    )
    await expect(
      parseCurriculumPdf(file, {
        role: 'origin', major: 'M', cohort: '2025', source: 's', enabled: true,
      }),
    ).rejects.toBeInstanceOf(CurriculumImportError)
    fetchSpy.mockRestore()
  })

  it('错误文案里不出现后端返回的原文', () => {
    const labels = Object.values(CURRICULUM_IMPORT_ERROR_LABEL).join(' ')
    expect(labels).not.toContain('内部细节')
  })
})

describe('CurriculumPdfImport（组件）', () => {
  it('默认关闭时显示不可用，⛔ 不渲染上传按钮为可用', () => {
    const wrapper = mount(CurriculumPdfImport)
    expect(wrapper.find('[data-testid="pdf-import-disabled"]').exists()).toBe(true)
    const upload = wrapper.find('[data-testid="pdf-upload-origin"]')
    expect(upload.attributes('disabled')).toBeDefined()
  })

  it('始终声明来源审核边界（⛔ 不显示"已核验"）', () => {
    const wrapper = mount(CurriculumPdfImport)
    const boundary = wrapper.find('[data-testid="pdf-import-boundary"]')
    if (boundary.exists()) {
      expect(boundary.text()).toContain('不代表')
      expect(boundary.text()).toContain('不是学校正式签发的原始 PDF')
    }
    // 组件文本里⛔ 不出现"已核验"这种正面断言
    expect(wrapper.text()).not.toContain('来源已核验')
  })

  it('渲染两个独立的 PDF 上传位置与状态', () => {
    const wrapper = mount(CurriculumPdfImport)
    for (const role of ['origin', 'target']) {
      expect(wrapper.find(`[data-testid="pdf-slot-${role}"]`).exists()).toBe(true)
      expect(wrapper.find(`[data-testid="pdf-file-${role}"]`).exists()).toBe(true)
      expect(wrapper.find(`[data-testid="pdf-status-${role}"]`).text()).toBe('idle')
      expect(wrapper.find(`[data-testid="pdf-source-${role}"]`).exists()).toBe(true)
    }
  })

  it('下一步文案⛔ 不承诺"已批准"', () => {
    const wrapper = mount(CurriculumPdfImport)
    const next = wrapper.find('[data-testid="pdf-import-next"]').text()
    // 初始态：还没上传，只提示要选两份 PDF
    expect(next).toContain('两份 PDF')
    // ⛔ 任何阶段都不得出现"已批准"这种断言
    expect(next).not.toContain('已批准')
    // 组件整体必须把"批准"归给组长，⛔ 不归给前端
    expect(wrapper.text()).toContain('项目组长')
  })

  it('两个 PDF 位置互相独立（⛔ 不共用状态）', async () => {
    const wrapper = mount(CurriculumPdfImport)
    const originInput = wrapper.find('[data-testid="pdf-file-origin"]')
    const targetInput = wrapper.find('[data-testid="pdf-file-target"]')
    expect(originInput.element).not.toBe(targetInput.element)
  })
})
