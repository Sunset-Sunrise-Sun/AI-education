/**
 * 当前课表**批量录入** UX（Phase 1）测试。
 *
 * 覆盖范围（与任务书逐条对应）：
 * - 搜索结果可**多选** + `[批量加入当前课表]`；
 * - 同一门课多个教学班 → **fail closed**（⛔ 不自动替用户挑一个）；
 * - 已在课表中的教学班 → 跳过，⛔ 不重复加入；
 * - 批量加入成功后**清空选择**；
 * - 汇总文案：`已加入 N 门 · 预计 XX 学分`；学分缺失 → `部分课程学分待核验`，
 *   ⛔ **绝不**把缺失学分当 0 求和；
 * - 搜索支持**空格分词**（`数据 结构` 命中 `数据结构`），⛔ 无拼音 / 无语义扩展；
 * - `[查看全部]` 与 `[清空当前课表]`（**二次确认**）；
 * - 清空 / 移除会**作废手工确认**（经 `invalidateManualAttestation`）；
 * - 截图识别入口：**只有外壳**，⛔ 不上传、⛔ 不 OCR、⛔ 不调用模型、⛔ 不发请求。
 */

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import CurrentScheduleEditor from '@/components/CurrentScheduleEditor.vue'
import { createManualScheduleEntry, buildOfferingFromManualEntry } from '@/state/manualSchedule'
import {
  applyManualAttestation,
  createDefaultUserInputForm,
  invalidateManualAttestation,
  type UserInputForm,
} from '@/state/userInput'
import { matchesSearchTokens, summarizeCredits } from '@/utils/courseSearch'
import { applyBatchAdd, describeConflicts, evaluateBatchAdd } from '@/utils/scheduleBulkAdd'
import type { CourseOffering } from '@/types/contracts'

const SEMESTER = '2026-1'

function offering(overrides: Partial<CourseOffering> = {}): CourseOffering {
  return {
    course_id: 'CS1000',
    course_name: '数据结构',
    class_id: 'CLASS-1',
    semester: SEMESTER,
    teacher: '教师甲',
    credit: 3,
    meetings: [
      {
        weekday: 1,
        start_section: 3,
        end_section: 4,
        weeks: [1, 2, 3, 4],
        campus: '深圳校区',
        classroom: '教学楼A305',
      },
    ],
    source: 'capture://case-a',
    data_source: 'real',
    ...overrides,
  }
}

/** 手工录入条目 → 公共 `CourseOffering`（用于验证 attestation 语义）。 */
function manualOffering(): CourseOffering {
  const entry = {
    ...createManualScheduleEntry(SEMESTER),
    courseId: 'SEC1001',
    courseName: '信息安全导论',
    classId: '01',
    weekday: 2,
    startSection: 3,
    endSection: 4,
    weeksText: '1-16',
    campus: '深圳校区',
    classroom: '教学楼B201',
  }
  const { offering, errors } = buildOfferingFromManualEntry(entry)
  if (!offering) throw new Error(`手工条目应能构建为 CourseOffering：${JSON.stringify(errors)}`)
  return offering
}

function mountEditor(options: {
  offerings?: CourseOffering[]
  currentSchedule?: CourseOffering[]
} = {}) {
  return mount(CurrentScheduleEditor, {
    props: {
      offerings: options.offerings ?? [],
      currentSchedule: options.currentSchedule ?? [],
      semester: SEMESTER,
      attestationNotice: '',
    },
  })
}

type EditorWrapper = ReturnType<typeof mountEditor>

function lastSchedule(wrapper: EditorWrapper): CourseOffering[] {
  const events = wrapper.emitted('update:currentSchedule') ?? []
  return (events[events.length - 1]?.[0] ?? []) as CourseOffering[]
}

function testId(wrapper: EditorWrapper, id: string) {
  return wrapper.get(`[data-testid="${id}"]`)
}

/* ------------------------------------------------------------------ 纯函数层 */

describe('空格分词搜索（纯函数）', () => {
  it('每个词都必须字面命中真实字段', () => {
    const item = offering()
    expect(matchesSearchTokens(item, '数据 结构')).toBe(true)
    expect(matchesSearchTokens(item, 'CS1000 CLASS-1')).toBe(true)
    expect(matchesSearchTokens(item, '教师甲')).toBe(true)
    // 顺序无关，但顺序不改变"每个词都要命中"的口径
    expect(matchesSearchTokens(item, '结构 数据')).toBe(true)
  })

  it('⛔ 不做语义 / 拼音扩展：没有字面命中就不算命中', () => {
    const item = offering()
    expect(matchesSearchTokens(item, '数据结构 图论')).toBe(false)
    expect(matchesSearchTokens(item, 'shujujiegou')).toBe(false)
    expect(matchesSearchTokens(item, '数据库')).toBe(false)
    expect(matchesSearchTokens(item, '')).toBe(false)
  })
})

describe('当前课表学分汇总（纯函数）', () => {
  it('全部学分可知才给总学分', () => {
    expect(summarizeCredits([offering(), offering({ class_id: 'C2', credit: 2 })])).toEqual({
      count: 2,
      total: 5,
      hasUnknownCredit: false,
      unknownCount: 0,
    })
  })

  it('⛔ 只要有一条缺学分就不给总学分、也不把缺失当 0', () => {
    const summary = summarizeCredits([offering(), offering({ class_id: 'C2', credit: null })])
    expect(summary.total).toBeNull()
    expect(summary.hasUnknownCredit).toBe(true)
    expect(summary.unknownCount).toBe(1)
    expect(summary.count).toBe(2)
  })
})

describe('批量加入评估（纯函数，fail closed）', () => {
  it('批次内同一门课的多个教学班 → 整门失败，不挑一个', () => {
    const first = offering({ class_id: 'CLASS-1' })
    const second = offering({ class_id: 'CLASS-2' })
    const evaluation = evaluateBatchAdd([], [first, second])

    expect(evaluation.acceptable).toEqual([])
    expect(evaluation.conflicts).toHaveLength(1)
    expect(evaluation.conflicts[0].courseId).toBe('CS1000')
    expect(evaluation.conflicts[0].rejectedClassIds).toEqual(['CLASS-1', 'CLASS-2'])
    expect(evaluation.conflicts[0].keptClassId).toBeNull()
    expect(describeConflicts(evaluation.conflicts)).toContain('同一门课只能保留一个教学班')
  })

  it('课表已有该课、本次选了另一个教学班 → 也失败，保留原有教学班', () => {
    const kept = offering({ class_id: 'CLASS-1' })
    const other = offering({ class_id: 'CLASS-2' })
    const evaluation = evaluateBatchAdd([kept], [other])

    expect(evaluation.acceptable).toEqual([])
    expect(evaluation.conflicts[0].keptClassId).toBe('CLASS-1')
    expect(evaluation.conflicts[0].rejectedClassIds).toEqual(['CLASS-2'])
    expect(describeConflicts(evaluation.conflicts)).toContain('当前课表已保留教学班 CLASS-1')
  })

  it('已在课表中的教学班算 alreadyPresent，⛔ 不重复加入、不算冲突', () => {
    const kept = offering({ class_id: 'CLASS-1' })
    const evaluation = evaluateBatchAdd([kept], [kept])

    expect(evaluation.acceptable).toEqual([])
    expect(evaluation.conflicts).toEqual([])
    expect(evaluation.alreadyPresent).toHaveLength(1)
  })

  it('不同学期的同名课程号互不冲突', () => {
    const current = offering({ semester: '2026-1', class_id: 'CLASS-1' })
    const nextTerm = offering({ semester: '2026-2', class_id: 'CLASS-2' })
    const evaluation = evaluateBatchAdd([current], [nextTerm])
    expect(evaluation.conflicts).toEqual([])
  })

  it('多条不同课程可以一起加入，且顺序稳定', () => {
    const a = offering({ course_id: 'CS1000', class_id: 'CLASS-1' })
    const b = offering({ course_id: 'MA2001', course_name: '高等代数', class_id: 'CLASS-9' })
    const added = applyBatchAdd([], evaluateBatchAdd([], [a, b]).acceptable, [a, b])
    expect(added.map((item) => item.course_id)).toEqual(['CS1000', 'MA2001'])
  })
})

/* ------------------------------------------------------------------ 组件层 */

describe('当前课表批量录入组件', () => {
  it('未输入关键词时不铺开结果', () => {
    const wrapper = mountEditor({ offerings: Array.from({ length: 40 }, (_, i) =>
      offering({ class_id: `CLASS-${i}` }),
    ) })
    expect(wrapper.findAll('[data-testid="case-a-search-result"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('支持空格分词')
  })

  it('搜索结果可多选，批量加入后清空选择', async () => {
    const targets = [offering({ class_id: 'CLASS-1' }), offering({ class_id: 'CLASS-2' })]
    const wrapper = mountEditor({
      offerings: [
        ...targets,
        offering({ course_id: 'MA2001', course_name: '高等代数', class_id: 'CLASS-9' }),
      ],
    })

    await testId(wrapper, 'case-a-offering-search').setValue('数据结构')
    expect(wrapper.findAll('[data-testid="case-a-search-result"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="case-a-batch-bar"]').exists()).toBe(false)

    const boxes = wrapper.findAll('[data-testid="case-a-result-checkbox"]')
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    expect(testId(wrapper, 'case-a-batch-bar').text()).toContain('已选择 2 个教学班')

    // 同一门课两个教学班 → fail closed，不加入任何一条
    await testId(wrapper, 'case-a-batch-add').trigger('click')
    expect(wrapper.find('[data-testid="case-a-batch-conflict"]').exists()).toBe(true)
    expect(wrapper.emitted('update:currentSchedule')).toBeUndefined()
    // 冲突未被自动解决：选择保留，交回用户决定
    expect(testId(wrapper, 'case-a-batch-bar').text()).toContain('已选择 2 个教学班')
  })

  it('多选不同课程 → 批量加入成功，选择被清空', async () => {
    const a = offering({ course_id: 'CS1000', class_id: 'CLASS-1' })
    const b = offering({ course_id: 'MA2001', course_name: '高等代数', class_id: 'CLASS-9' })
    const wrapper = mountEditor({ offerings: [a, b] })

    await testId(wrapper, 'case-a-offering-search').setValue('CLASS')
    const boxes = wrapper.findAll('[data-testid="case-a-result-checkbox"]')
    expect(boxes).toHaveLength(2)
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    await testId(wrapper, 'case-a-batch-add').trigger('click')

    expect(lastSchedule(wrapper).map((item) => item.course_id)).toEqual(['CS1000', 'MA2001'])
    expect(testId(wrapper, 'case-a-batch-notice').text()).toContain('已批量加入 2 个教学班')
    expect(wrapper.find('[data-testid="case-a-batch-bar"]').exists()).toBe(false)
  })

  it('已在课表中的教学班不会被重复加入', async () => {
    const kept = offering({ class_id: 'CLASS-1' })
    const wrapper = mountEditor({ offerings: [kept], currentSchedule: [kept] })

    await testId(wrapper, 'case-a-offering-search').setValue('数据结构')
    await testId(wrapper, 'case-a-result-add').trigger('click')

    expect(wrapper.find('[data-testid="case-a-batch-conflict"]').exists()).toBe(false)
    expect(wrapper.emitted('update:currentSchedule')).toBeUndefined()
  })

  it('同一门课已有另一个教学班时，单条加入 fail closed', async () => {
    const kept = offering({ class_id: 'CLASS-1' })
    const other = offering({ class_id: 'CLASS-2' })
    const wrapper = mountEditor({ offerings: [other], currentSchedule: [kept] })

    await testId(wrapper, 'case-a-offering-search').setValue('数据结构')
    await testId(wrapper, 'case-a-result-add').trigger('click')

    expect(testId(wrapper, 'case-a-batch-conflict').text()).toContain('当前课表已保留教学班 CLASS-1')
    expect(wrapper.emitted('update:currentSchedule')).toBeUndefined()
  })

  it('汇总显示门数与预计学分；学分缺失时只报待核验', () => {
    const full = mountEditor({
      offerings: [],
      currentSchedule: [offering(), offering({ class_id: 'CLASS-2', course_id: 'MA2001', credit: 2 })],
    })
    expect(testId(full, 'case-a-schedule-summary').text()).toContain('已加入 2 门 · 预计 5 学分')
    expect(full.find('[data-testid="case-a-credit-unknown"]').exists()).toBe(false)

    const partial = mountEditor({
      offerings: [],
      currentSchedule: [offering(), offering({ class_id: 'CLASS-2', credit: null })],
    })
    const summaryText = testId(partial, 'case-a-schedule-summary').text()
    expect(summaryText).toContain('已加入 2 门')
    expect(summaryText).not.toContain('预计')
    expect(testId(partial, 'case-a-credit-unknown').text()).toContain('部分课程学分待核验')
  })

  it('默认紧凑展示，[查看全部] 可展开完整列表', async () => {
    const schedule = Array.from({ length: 5 }, (_, i) =>
      offering({ class_id: `CLASS-${i}`, course_id: `CS100${i}` }),
    )
    const wrapper = mountEditor({ offerings: [], currentSchedule: schedule })

    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(3)
    await testId(wrapper, 'case-a-schedule-view-all').trigger('click')
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(5)
    await testId(wrapper, 'case-a-schedule-view-all').trigger('click')
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(3)
  })

  it('清空需要二次确认，取消不改变课表', async () => {
    const wrapper = mountEditor({ offerings: [], currentSchedule: [offering()] })

    await testId(wrapper, 'case-a-schedule-clear').trigger('click')
    expect(testId(wrapper, 'case-a-clear-confirm').text()).toContain('确定清空')
    await testId(wrapper, 'case-a-clear-cancel').trigger('click')
    expect(wrapper.find('[data-testid="case-a-clear-confirm"]').exists()).toBe(false)
    expect(wrapper.emitted('update:currentSchedule')).toBeUndefined()

    await testId(wrapper, 'case-a-schedule-clear').trigger('click')
    await testId(wrapper, 'case-a-clear-confirm-button').trigger('click')
    expect(lastSchedule(wrapper)).toEqual([])
    expect(testId(wrapper, 'case-a-batch-notice').text()).toContain('当前课表已清空')
  })

  it('移除单条课程会发出新数组', async () => {
    const kept = offering({ class_id: 'CLASS-1' })
    const other = offering({ class_id: 'CLASS-2', course_id: 'MA2001' })
    const wrapper = mountEditor({ offerings: [], currentSchedule: [kept, other] })

    await wrapper.findAll('[data-testid="case-a-current-schedule-remove"]')[0].trigger('click')
    expect(lastSchedule(wrapper).map((item) => item.class_id)).toEqual(['CLASS-2'])
  })

  it('截图识别入口只有外壳：不渲染文件上传，也不发任何请求', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const xhrSpy = vi.spyOn(globalThis.XMLHttpRequest.prototype, 'open')

    const wrapper = mountEditor({ offerings: [], currentSchedule: [] })
    await testId(wrapper, 'case-a-screenshot-entry').trigger('click')

    const dialog = testId(wrapper, 'case-a-screenshot-dialog')
    expect(dialog.text()).toContain('本轮不会上传任何图片')
    expect(dialog.find('input[type="file"]').exists()).toBe(false)
    expect(dialog.html()).not.toContain('已支持截图识别')
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(xhrSpy).not.toHaveBeenCalled()

    await testId(wrapper, 'case-a-screenshot-close').trigger('click')
    expect(wrapper.find('[data-testid="case-a-screenshot-dialog"]').exists()).toBe(false)

    fetchSpy.mockRestore()
    xhrSpy.mockRestore()
  })
})

/* -------------------------------------------------- 与手工确认（attestation）的联动 */

describe('课表改动 → 手工确认作废', () => {
  function attestedForm(): UserInputForm {
    const base = createDefaultUserInputForm()
    const withManual: UserInputForm = {
      ...base,
      semester: SEMESTER,
      currentSchedule: [manualOffering()],
    }
    const attested = applyManualAttestation(withManual, true)
    expect(attested.manualAttestation.attested).toBe(true)
    return attested
  }

  it('清空当前课表会作废已有手工确认，并告知需要重新确认', async () => {
    const form = attestedForm()
    const wrapper = mount(CurrentScheduleEditor, {
      props: {
        offerings: [],
        currentSchedule: form.currentSchedule,
        semester: form.semester,
        attestationNotice: '当前课表在上次确认之后被改动，之前的确认已作废；请重新确认手工录入信息后再提交。',
      },
    })

    await testId(wrapper, 'case-a-schedule-clear').trigger('click')
    await testId(wrapper, 'case-a-clear-confirm-button').trigger('click')

    const next = lastSchedule(wrapper)
    const updated = invalidateManualAttestation(form, next).form
    expect(updated.currentSchedule).toEqual([])
    expect(updated.manualAttestation.attested).toBe(false)
    expect(updated.manualAttestation.invalidated).toBe(true)
    expect(testId(wrapper, 'case-a-attestation-notice').text()).toContain('之前的确认已作废')
  })

  it('移除操作同样走作废逻辑（⛔ 旧确认不覆盖新数据）', async () => {
    const form = attestedForm()
    const wrapper = mount(CurrentScheduleEditor, {
      props: {
        offerings: [],
        currentSchedule: form.currentSchedule,
        semester: form.semester,
        attestationNotice: '',
      },
    })

    await testId(wrapper, 'case-a-current-schedule-remove').trigger('click')
    const updated = invalidateManualAttestation(form, lastSchedule(wrapper)).form
    expect(updated.currentSchedule).toEqual([])
    expect(updated.manualAttestation.invalidated).toBe(true)
  })
})
