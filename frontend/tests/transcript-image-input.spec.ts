/**
 * Phase 5：成绩单**图片**输入链测试。
 *
 * ```text
 * 图片上传 → OCR（mock）→ 用户确认 → plan 请求 → matching → 补修分析
 * ```
 *
 * 必须验证的不变量：
 *   1. ⛔ **OCR 结果不直接决定 status**：识别层只产出候选，不产生任何 MakeupStatus；
 *   2. ⛔ **未确认的课程不能进入 matching**（不在 plan 请求体里）；
 *   3. ✅ plan 请求次数正确（确认是本地状态，不重新请求）；
 *   4. ⛔ 统一入口下 PDF 与图片**不会并存**（选 PDF 会清空图片状态）；
 *   5. ⛔ 不伪造课程号 / 不自动 satisfied。
 *
 * ⛔ 全程不发真实网络请求。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import TranscriptImageImport from '@/components/TranscriptImageImport.vue'
import {
  TranscriptImageApiError,
  toConfirmedRecords,
  type RecognizedCourseCandidate,
  type TranscriptImageRecognition,
} from '@/api/transcriptImages'

const loadOfferings = vi.fn()
const runPlan = vi.fn()
const recognize = vi.fn()

vi.mock('@/api/caseADemo', async () => ({
  ...(await vi.importActual<typeof import('@/api/caseADemo')>('@/api/caseADemo')),
  loadCaseAOfferings: (...args: unknown[]) => loadOfferings(...args),
  runCaseADemo: (...args: unknown[]) => runPlan(...args),
}))

vi.mock('@/api/transcriptImages', async () => {
  const actual = await vi.importActual<typeof import('@/api/transcriptImages')>(
    '@/api/transcriptImages',
  )
  return { ...actual, recognizeTranscriptImage: (...args: unknown[]) => recognize(...args) }
})

vi.mock('@/api/studyPlan', async () => {
  const actual = await vi.importActual<typeof import('@/api/studyPlan')>('@/api/studyPlan')
  return {
    ...actual,
    // ⚠️ 本 spec 不关心培养方案：返回**空列表**（⛔ 不能返回 undefined，
    //    否则复用该模块的组件会在读取 .length 时抛错）。
    loadMajors: vi.fn(async () => []),
    loadStudyPlan: vi.fn(async () => {
      throw new actual.StudyPlanApiError('本 spec 未配置培养方案', 503, 'majors_not_configured')
    }),
  }
})

function candidate(
  rowId: string,
  name: string,
  score: string | null,
  credit: number | null = null,
): RecognizedCourseCandidate {
  return {
    row_id: rowId,
    course_name: name,
    credit,
    score_text: score,
    semester_text: '2025-2026学年第一学期',
    course_attribute: '公必',
    confidence: 0.66,
    unconfirmed: [
      '图片未包含官方课程号，需人工确认课程身份。',
      ...(credit === null ? ['未识别到学分，需人工补填。'] : []),
      '该行识别置信度偏低，请核对课程名与成绩。',
    ],
  }
}

const RECOGNITION: TranscriptImageRecognition = {
  source_id: 'upload:image:sha256:abc',
  artifact_sha256: 'a'.repeat(64),
  media_type: 'image/png',
  width: 2198,
  height: 1489,
  block_count: 128,
  redacted_block_count: 9,
  column_groups: 1,
  candidates: [
    candidate('img:1', '线性代数', '97'),
    candidate('img:2', '大学英语', '82'),
    candidate('img:3', '程序设计', '95'),
  ],
  unrecognized: ['(空课程名)'],
}

function imageFile(): File {
  return new File(['fake-png-bytes'], 'transcript.png', { type: 'image/png' })
}

/**
 * 把图片送入**图片确认组件**（组件内已无自己的 file input）。
 *
 * ⚠️ Phase 6 统一入口后，文件由父级统一控件派发到 `acceptFile()`。
 */
async function attachImage(wrapper: { vm: unknown }): Promise<void> {
  await (
    wrapper.vm as unknown as { acceptFile: (f: File | null) => Promise<void> }
  ).acceptFile(imageFile())
  await flushPromises()
}

/** 通过父级**统一入口**选择图片（与用户真实操作一致）。 */
async function chooseImageViaUnifiedEntry(wrapper: ReturnType<typeof mount>): Promise<void> {
  const imageImport = wrapper.findComponent(TranscriptImageImport)
  await (
    imageImport.vm as unknown as { acceptFile: (f: File | null) => Promise<void> }
  ).acceptFile(imageFile())
  await flushPromises()
}

function planResponse() {
  return {
    transcript: {
      source_id: 's',
      artifact_sha256: 'a'.repeat(64),
      record_count: 1,
      term_count: 1,
      terms: ['2025-2026学年第一学期'],
      pending_course_id_count: 1,
    },
    makeup_tasks: [],
    course_offerings: [],
    preference: {},
    plan_result: {
      status: 'partially_feasible',
      selected_classes: [],
      changes: [],
      risks: [],
      unresolved: [],
    },
    provenance: {},
  }
}

beforeEach(() => {
  // jsdom 没有 createObjectURL：本机预览在测试中替换为占位实现。
  URL.createObjectURL = vi.fn(() => 'blob:mock-preview')
  URL.revokeObjectURL = vi.fn()

  loadOfferings.mockReset().mockResolvedValue([])
  runPlan.mockReset().mockResolvedValue(planResponse() as never)
  recognize.mockReset().mockResolvedValue(RECOGNITION)
})

/* -------------------------------------------------------------------------- *
 * 一、识别层：只产出候选，⛔ 不产生任何判定
 * -------------------------------------------------------------------------- */

describe('OCR 只产出候选（⛔ 不产生 status）', () => {
  it('上传图片后展示候选，且每条都带「为什么需要确认」', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)

    expect(recognize).toHaveBeenCalledTimes(1)
    const items = wrapper.findAll('[data-testid="case-a-transcript-image-candidate"]')
    expect(items).toHaveLength(3)
    expect(wrapper.get('[data-testid="case-a-transcript-image-summary"]').text()).toContain('识别出')
    const reasons = wrapper.findAll('[data-testid="case-a-transcript-image-unconfirmed"]')
    expect(reasons).toHaveLength(3)
    for (const node of reasons) {
      expect(node.text()).toContain('官方课程号')
    }
  })

  it('⛔ 识别结果里不含任何课程状态字眼', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)
    const text = wrapper.text()
    expect(text).not.toContain('已满足')
    expect(text).not.toContain('需要确认可转换')
  })

  it('⛔ 未确认前不发出任何 confirmed 记录', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)
    const emitted = wrapper.emitted('update:confirmed') ?? []
    const last = emitted.at(-1)?.[0] as unknown[] | undefined
    expect(last ?? []).toHaveLength(0)
    expect(wrapper.find('[data-testid="case-a-transcript-image-confirmed"]').exists()).toBe(false)
  })

  it('识别失败时如实报错，⛔ 不用演示数据顶替', async () => {
    recognize.mockRejectedValue(
      new TranscriptImageApiError(
        '未能在图片中定位成绩单表格的列结构。',
        422,
        'transcript_image_no_records',
      ),
    )
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)

    expect(wrapper.get('[data-testid="case-a-transcript-image-error"]').text()).toContain('列结构')
    expect(wrapper.find('[data-testid="case-a-transcript-image-candidate"]').exists()).toBe(false)
  })

  it('OCR 不可用时如实报错', async () => {
    recognize.mockRejectedValue(
      new TranscriptImageApiError('引擎未安装', 503, 'transcript_ocr_not_configured'),
    )
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)
    expect(wrapper.get('[data-testid="case-a-transcript-image-error"]').text()).toContain('不可用')
  })

  it('展示隐私过滤数量（⛔ 不回传被丢弃内容）', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)
    const privacy = wrapper.get('[data-testid="case-a-transcript-image-privacy"]').text()
    expect(privacy).toContain('9')
    expect(privacy).toContain('个人身份信息')
  })

  it('⛔ 未选择文件时不渲染任何上传入口（统一入口在父级）', () => {
    const wrapper = mount(TranscriptImageImport)
    expect(wrapper.find('[data-testid="case-a-transcript-image-input"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-transcript-image-result"]').exists()).toBe(false)
  })
})

/* -------------------------------------------------------------------------- *
 * 🔴 Review：未识别的候选**只能展示**，⛔ 不得进入 confirmed 记录
 * -------------------------------------------------------------------------- */

describe('🔴 未识别候选不得进入 confirmed_completed_courses', () => {
  /** 识别状态为 `unrecognized` 的候选（⛔ 没有成绩，无法判断是否通过）。 */
  function unrecognizedCandidate(rowId: string, name: string): RecognizedCourseCandidate {
    return { ...candidate(rowId, name, null), confidence: 0.4 }
  }

  function withUnrecognized() {
    recognize.mockResolvedValue({
      ...RECOGNITION,
      candidates: [
        candidate('img:1', '线性代数', '97'),
        unrecognizedCandidate('img:2', '成绩读不出的课'),
        candidate('img:3', '大学英语', '82'),
      ],
    })
    return mount(TranscriptImageImport)
  }

  it('未识别候选只展示：⛔ 无确认按钮、⛔ 无"是否通过"下拉', async () => {
    const wrapper = withUnrecognized()
    await attachImage(wrapper)

    const rows = wrapper.findAll('[data-testid="case-a-transcript-image-candidate"]')
    expect(rows).toHaveLength(3)
    // 可确认的只有 2 条 ⇒ 只有 2 个确认按钮
    expect(wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]')).toHaveLength(2)
    // 未识别那行有明确标注，且没有通过下拉
    expect(
      wrapper.findAll('[data-testid="case-a-transcript-image-row-unrecognized"]'),
    ).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="case-a-transcript-image-passed"]')).toHaveLength(2)
    // 摘要如实拆分
    const summary = wrapper.get('[data-testid="case-a-transcript-image-summary"]').text()
    expect(summary).toContain('未识别')
  })

  it('⛔ 点「确认全部已识别」不会把未识别候选写进 confirmed', async () => {
    const wrapper = withUnrecognized()
    await attachImage(wrapper)

    await wrapper.get('[data-testid="case-a-transcript-image-confirm-all"]').trigger('click')
    await flushPromises()

    const records = wrapper.emitted('update:confirmed')!.at(-1)![0] as { course_name: string }[]
    const names = records.map((item) => item.course_name)
    expect(names).toEqual(['线性代数', '大学英语'])
    // ⛔ 未识别的课程名绝不能出现（排除依据是**识别状态**，不是课程名）
    expect(names).not.toContain('成绩读不出的课')
    expect(records).toHaveLength(2)
  })

  it('缺课程名的候选同样不可确认', async () => {
    recognize.mockResolvedValue({
      ...RECOGNITION,
      candidates: [candidate('img:9', '', '88'), candidate('img:1', '线性代数', '97')],
    })
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)

    expect(wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]')).toHaveLength(1)
    await wrapper.get('[data-testid="case-a-transcript-image-confirm-all"]').trigger('click')
    await flushPromises()
    const records = wrapper.emitted('update:confirmed')!.at(-1)![0] as { course_name: string }[]
    expect(records.map((item) => item.course_name)).toEqual(['线性代数'])
  })

  it('全部候选都未识别时，批量确认按钮不可用且不发出任何记录', async () => {
    recognize.mockResolvedValue({
      ...RECOGNITION,
      candidates: [unrecognizedCandidate('img:1', '甲'), unrecognizedCandidate('img:2', '乙')],
    })
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)

    const button = wrapper.get('[data-testid="case-a-transcript-image-confirm-all"]')
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    await flushPromises()
    const records = (wrapper.emitted('update:confirmed')!.at(-1)![0] ?? []) as unknown[]
    expect(records).toHaveLength(0)
  })
})

/* -------------------------------------------------------------------------- *
 * 二、确认：只有确认过的行才进入提交内容
 * -------------------------------------------------------------------------- */

describe('用户确认 → confirmed_completed_courses', () => {
  it('确认一行后才产出该行记录，且 course_id 恒为 null', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)

    await wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]').at(0)!.trigger('click')
    await flushPromises()

    const records = wrapper.emitted('update:confirmed')!.at(-1)![0] as ReturnType<
      typeof toConfirmedRecords
    >
    expect(records).toHaveLength(1)
    expect(records[0].course_name).toBe('线性代数')
    // ⛔ 硬约束：不推断课程号
    expect(records[0].course_id).toBeNull()
    expect(records[0].course_id_status).toBe('pending')
    expect(records[0].id_match_source).toBeNull()
    expect(records[0].source_record).toBe('img:img:1')
  })

  it('⛔ 未确认的行不进入提交内容', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)
    await wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]').at(0)!.trigger('click')
    await flushPromises()

    const records = wrapper.emitted('update:confirmed')!.at(-1)![0] as { course_name: string }[]
    const names = records.map((item) => item.course_name)
    expect(names).toEqual(['线性代数'])
    expect(names).not.toContain('大学英语')
    expect(names).not.toContain('程序设计')
  })

  it('丢弃的行不进入提交内容', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)
    await wrapper.get('[data-testid="case-a-transcript-image-confirm-all"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:confirmed')!.at(-1)![0] as unknown[]).toHaveLength(3)

    await wrapper.findAll('[data-testid="case-a-transcript-image-discard"]').at(1)!.trigger('click')
    await flushPromises()
    const records = wrapper.emitted('update:confirmed')!.at(-1)![0] as { course_name: string }[]
    expect(records.map((item) => item.course_name)).not.toContain('大学英语')
  })

  it('用户可以修改课程名 / 补填学分后再确认', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)

    await wrapper.findAll('[data-testid="case-a-transcript-image-name"]').at(2)!.setValue('程序设计II')
    await wrapper.findAll('[data-testid="case-a-transcript-image-credit"]').at(2)!.setValue('3')
    await wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]').at(2)!.trigger('click')
    await flushPromises()

    const records = wrapper.emitted('update:confirmed')!.at(-1)![0] as {
      course_name: string
      credit: number
    }[]
    expect(records).toHaveLength(1)
    expect(records[0].course_name).toBe('程序设计II')
    expect(records[0].credit).toBe(3)
  })

  it('撤回确认后该行不再进入提交内容', async () => {
    const wrapper = mount(TranscriptImageImport)
    await attachImage(wrapper)
    await wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]').at(0)!.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:confirmed')!.at(-1)![0] as unknown[]).toHaveLength(1)

    await wrapper.get('[data-testid="case-a-transcript-image-undo"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:confirmed')!.at(-1)![0] as unknown[]).toHaveLength(0)
  })
})

/* -------------------------------------------------------------------------- *
 * 三、CaseADemoView 接线：图片 → plan 请求
 * -------------------------------------------------------------------------- */

describe('CaseADemoView：图片确认结果进入 plan 请求', () => {
  it('统一入口选图片 → 确认 → 请求体带 confirmed_completed_courses，⛔ 不带 PDF', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    await chooseImageViaUnifiedEntry(wrapper)

    await wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]').at(0)!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="case-a-transcript-image-confirmed-count"]').text()).toContain('1')

    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    expect(runPlan).toHaveBeenCalledTimes(1)
    const payload = runPlan.mock.calls[0][0] as {
      file: File | null
      confirmedCourses: { course_name: string }[] | null
    }
    expect(payload.file).toBeNull()
    expect(payload.confirmedCourses).toHaveLength(1)
    expect(payload.confirmedCourses![0].course_name).toBe('线性代数')
  })

  it('⛔ 未确认任何课程时不允许提交（不会把 OCR 结果当输入）', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    await chooseImageViaUnifiedEntry(wrapper)

    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    expect(runPlan).not.toHaveBeenCalled()
    expect(wrapper.get('.state--error').text()).toContain('请先上传成绩单')
  })

  it('✅ 统一入口：选 PDF 会清掉图片状态，PDF 优先', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    // 先确认一条图片记录
    await chooseImageViaUnifiedEntry(wrapper)
    await wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]').at(0)!.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="case-a-transcript-image-confirmed-count"]').exists()).toBe(true)

    // 再通过**同一个**入口选择 PDF：图片状态被清空，两者不并存
    const pdfInput = wrapper.get('[data-testid="case-a-pdf"]')
    Object.defineProperty(pdfInput.element, 'files', {
      value: [new File(['%PDF-1.7'], 'transcript.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await pdfInput.trigger('change')
    await flushPromises()

    expect(wrapper.get('[data-testid="case-a-transcript-pdf-selected"]').text()).toContain(
      'transcript.pdf',
    )
    expect(wrapper.find('[data-testid="case-a-transcript-image-confirmed-count"]').exists()).toBe(
      false,
    )
    expect(wrapper.find('[data-testid="case-a-transcript-image-result"]').exists()).toBe(false)
  })

  it('✅ plan 请求次数正确：确认/撤回都是本地状态，不重新请求', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    await chooseImageViaUnifiedEntry(wrapper)
    await wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]').at(0)!.trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()
    expect(runPlan).toHaveBeenCalledTimes(1)

    // 生成之后再确认一行：属于本地状态变更，⛔ 不得触发第二次请求
    await wrapper.findAll('[data-testid="case-a-transcript-image-confirm"]').at(1)!.trigger('click')
    await flushPromises()
    expect(runPlan).toHaveBeenCalledTimes(1)
  })
})
