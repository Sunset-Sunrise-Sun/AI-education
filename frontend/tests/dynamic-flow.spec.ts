/**
 * 动态交互链路测试（**后端 `makeup_tasks` → 三状态 → 推荐 → 课表**）。
 *
 * ```text
 * 后端 makeup_tasks（真实匹配结果：status + reason + source_evidence）
 *   → satisfied / need_confirmation / missing
 *   → 推荐 = missing 课程对应的真实教学班
 *   → 确认可转换 → 该课程消失（satisfied）
 *   → 加入本学期方案 → 课表实时更新
 * ```
 *
 * ⚠️ 本文件于本轮**重写 fixture 与断言**：
 *   旧版让测试自己去构造「前端演示培养方案」的课程号，测的是前端配置层；
 *   现在三状态完全由后端 `status` 映射而来（`utils/makeupAnalysis.ts`），
 *   因此 fixture 必须**像后端那样**提供 `makeup_tasks`。
 *   不变量本身（缺失才推荐、确认后消失、课表实时合并、⛔ 全程不发第二次请求）保持不变。
 *
 * ⛔ 全程不发后端请求；⛔ 不放宽 data_source 门禁。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import type { CourseOffering, MakeupTask } from '@/types/contracts'

const load = vi.fn()
const runPlan = vi.fn()
vi.mock('@/api/caseADemo', async () => ({
  ...(await vi.importActual<typeof import('@/api/caseADemo')>('@/api/caseADemo')),
  loadCaseAOfferings: (...args: unknown[]) => load(...args),
  runCaseADemo: (...args: unknown[]) => runPlan(...args),
}))

const run = runPlan

function offering(
  courseId: string,
  classId: string,
  name: string,
  weekday = 2,
  startSection = 3,
): CourseOffering {
  return {
    course_id: courseId,
    course_name: name,
    class_id: classId,
    semester: '2026-1',
    meetings: [
      {
        weekday,
        start_section: startSection,
        end_section: startSection + 1,
        weeks: [1, 2, 3],
        campus: '深圳校区',
        classroom: 'A101',
      },
    ],
    teacher: null,
    credit: 3,
    source: 'capture://sysu/2026-1',
    data_source: 'real',
  }
}

/**
 * 教学班 fixture —— 课程号与下面的 `makeup_tasks` 保持一致。
 *
 * 刻意包含 `CSE303`（对应 `need_confirmation`）：它**不得**出现在推荐里。
 */
const OFFERINGS: CourseOffering[] = [
  offering('CSE303', 'C1', '操作系统实验', 1, 3),
  offering('CSE101', 'C1', '程序设计I', 2, 3),
  offering('CSE201', 'C1', '程序设计II', 3, 3),
  offering('CSE209', 'C1', '离散数学', 4, 3),
  offering('MA184', 'C1', '概率统计（理工类）', 5, 3),
]

/**
 * 后端 `makeup_tasks` fixture —— 覆盖三种 `MakeupStatus`。
 *
 * `reason` 的**格式必须与后端一致**（含 `原因分类：<code>`），
 * 因为前端就是从这段文案里解析不确定性分类的。
 */
function makeupTask(
  courseId: string,
  courseName: string,
  status: MakeupTask['status'],
  reason: string,
): MakeupTask {
  return {
    course_id: courseId,
    course_name: courseName,
    credit: 3,
    status,
    deadline_semester: null,
    recommended_semester: null,
    prerequisites: [],
    reason,
    source_evidence: 'case-owner-confirmed://case-a/target-plan#table:2!row:4；upload:pdf:sha256:abc#pdf:22',
  }
}

const MAKEUP_TASKS: MakeupTask[] = [
  makeupTask(
    'PE101',
    '体育',
    'satisfied',
    '已有明确课程认定依据。',
  ),
  makeupTask(
    'CSE303',
    '操作系统实验',
    'manual_confirmation',
    '成绩单课程 「操作系统实验」 与培养方案要求「操作系统实验」名称一致，'
      + '但成绩单未包含官方课程号，等价关系待人工确认，不能自动认定两者是同一门课程。'
      + '（原因分类：course_id_missing — 成绩单未包含官方课程号）',
  ),
  makeupTask(
    'CSE101',
    '程序设计I',
    'required',
    '培养方案要求「程序设计I」，在成绩单中未发现同名或名称相近的课程记录；'
      + '由于成绩单不含官方课程号，该要求是否已完成待人工确认。'
      + '（原因分类：manual_rule_required — 需要人工确认课程完成情况）',
  ),
  makeupTask(
    'CSE201',
    '程序设计II',
    'required',
    '培养方案要求「程序设计II」，在成绩单中未发现同名或名称相近的课程记录。'
      + '（原因分类：manual_rule_required — 需要人工确认课程完成情况）',
  ),
  makeupTask(
    'CSE209',
    '离散数学',
    'required',
    '培养方案要求「离散数学」，在成绩单中未发现同名或名称相近的课程记录。'
      + '（原因分类：manual_rule_required — 需要人工确认课程完成情况）',
  ),
  makeupTask(
    'MA184',
    '概率统计（理工类）',
    'required',
    '培养方案要求「概率统计（理工类）」，成绩单中没有同名课程，'
      + '但存在名称相近的课程 「概率统计」，是否可以抵扣待人工确认。'
      + '（原因分类：name_mismatch — 课程名称与培养方案不一致）',
  ),
]

function response() {
  return {
    transcript: {
      source_id: 's',
      artifact_sha256: 'a'.repeat(64),
      record_count: 24,
      term_count: 2,
      terms: ['2025-2026学年第一学期'],
      pending_course_id_count: 24,
    },
    makeup_tasks: MAKEUP_TASKS,
    course_offerings: OFFERINGS,
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

async function mountWithResult() {
  load.mockReset().mockResolvedValue(OFFERINGS)
  const wrapper = mount(CaseADemoView)
  await flushPromises()
  const file = new File(['%PDF-1.7'], 'transcript.pdf', { type: 'application/pdf' })
  Object.defineProperty(wrapper.get('[data-testid="case-a-pdf"]').element, 'files', {
    value: [file],
    configurable: true,
  })
  await wrapper.get('[data-testid="case-a-pdf"]').trigger('change')
  await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
  await flushPromises()
  return wrapper
}

const recNames = (wrapper: ReturnType<typeof mount>) =>
  wrapper
    .findAll('[data-testid="case-a-recommend-card"] strong.recommend-card__name')
    .map((n) => n.text())

const cardNames = (wrapper: ReturnType<typeof mount>) =>
  wrapper
    .findAll('[data-testid="case-a-makeup-card"] strong.match-card__name')
    .map((n) => n.text())

const missingNames = (wrapper: ReturnType<typeof mount>) =>
  wrapper
    .findAll('[data-testid="case-a-makeup-gap-item"] .match__name')
    .map((n) => n.text())

const satisfiedNames = (wrapper: ReturnType<typeof mount>) =>
  wrapper
    .findAll('[data-testid="case-a-makeup-satisfied-item"] .match__name')
    .map((n) => n.text())

describe('三状态完全由后端 makeup_tasks 决定', () => {
  it('结果页同时渲染补修 → 推荐 → 课表，顺序正确', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    const html = wrapper.html()
    const iMatch = html.indexOf('case-a-makeup-gap')
    const iRec = html.indexOf('case-a-recommend"')
    const iWeek = html.indexOf('case-a-weekly-schedule')
    expect(iMatch).toBeGreaterThanOrEqual(0)
    expect(iRec).toBeGreaterThan(iMatch)
    expect(iWeek).toBeGreaterThan(iRec)
  })

  it('摘要按后端 status 分组为 已满足 / 待确认 / 缺失', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    // 后端 fixture：1 satisfied、1 manual_confirmation、4 required
    const summary = wrapper.get('[data-testid="case-a-makeup-summary"]').text()
    expect(summary).toContain('已满足 1')
    expect(summary).toContain('待确认 1')
    expect(summary).toContain('缺失 4')

    expect(satisfiedNames(wrapper)).toEqual(['体育'])
    expect(cardNames(wrapper)).toEqual(['操作系统实验'])
    expect(missingNames(wrapper)).toEqual([
      '程序设计I',
      '程序设计II',
      '离散数学',
      '概率统计（理工类）',
    ])
  })

  it('展示后端给出的原因与不确定性分类，⛔ 不在前端编造', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    const reasons = wrapper
      .findAll('[data-testid="case-a-makeup-reason"]')
      .map((n) => n.text().replace(/\s+/g, ''))
    // 后端原文必须出现（含培养方案课程名与「等价关系待人工确认」）
    expect(reasons.join('|')).toContain('等价关系待人工确认')
    expect(reasons.join('|')).toContain('成绩单未包含官方课程号')

    const causes = wrapper
      .findAll('[data-testid="case-a-makeup-cause"]')
      .map((n) => n.text())
    expect(causes).toContain('原因分类：成绩单未包含官方课程号')

    // 判定依据（后端 source_evidence）逐字可见
    expect(wrapper.get('[data-testid="case-a-makeup-evidence"]').text()).toContain(
      'case-owner-confirmed://case-a/target-plan',
    )
  })
})

describe('推荐只来自 missing', () => {
  it('缺失课程对应的真实教学班进入推荐', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    expect(recNames(wrapper)).toEqual([
      '程序设计I',
      '程序设计II',
      '离散数学',
      '概率统计（理工类）',
    ])
  })

  it('⛔ 待确认（need_confirmation）的课程不得进入推荐', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    const names = recNames(wrapper)
    expect(names).not.toContain('操作系统实验')
    // 已满足的更不得进入推荐
    expect(names).not.toContain('体育')
  })

  it('⛔ 推荐不是"任意教学班列表"：没有 makeup_tasks 就没有推荐', async () => {
    run.mockResolvedValue({ ...response(), makeup_tasks: [] } as never)
    const wrapper = await mountWithResult()

    expect(wrapper.findAll('[data-testid="case-a-recommend-card"]')).toHaveLength(0)
    expect(wrapper.find('[data-testid="case-a-recommend-empty"]').exists()).toBe(true)
  })

  it('推荐理由引用了后端对该缺口的判定说明', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    const reasons = wrapper
      .findAll('[data-testid="case-a-recommend-reason"]')
      .map((n) => n.text().replace(/\s+/g, ' ').trim())
    expect(reasons.length).toBeGreaterThan(0)
    for (const reason of reasons) {
      expect(reason.length).toBeGreaterThan(20)
      expect(reason).not.toBe('推荐原因：')
    }
    expect(reasons.some((r) => r.includes('缺口'))).toBe(true)
    // 后端判定说明被带上，学生可以核对为什么需要补修
    expect(reasons.some((r) => r.includes('培养方案判定说明'))).toBe(true)
  })
})

describe('确认可转换 → 已满足 → ⛔ 不再推荐（且不重新请求后端）', () => {
  it('确认一门课程后它进入「已满足」并从推荐消失', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    const before = recNames(wrapper)
    const card = wrapper.findAll('[data-testid="case-a-makeup-card"]').at(0)
    expect(card).toBeTruthy()
    const courseName = card!.find('strong.match-card__name').text().trim()
    expect(courseName).toBe('操作系统实验')

    await card!.find('[data-testid="case-a-makeup-convert"]').trigger('click')
    await flushPromises()

    // ⛔ 确认只是本地状态：不得触发第二次 planner 请求
    expect(run).toHaveBeenCalledTimes(1)
    expect(satisfiedNames(wrapper)).toContain(courseName)
    expect(cardNames(wrapper)).not.toContain(courseName)
    expect(recNames(wrapper)).not.toContain(courseName)
    expect(recNames(wrapper).length).toBeLessThanOrEqual(before.length)
  })

  it('撤销后回到待确认列表', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    const cardsBefore = wrapper.findAll('[data-testid="case-a-makeup-card"]').length
    await wrapper.findAll('[data-testid="case-a-makeup-convert"]').at(0)!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="case-a-makeup-card"]')).toHaveLength(cardsBefore - 1)

    await wrapper.get('[data-testid="case-a-makeup-undo"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="case-a-makeup-card"]')).toHaveLength(cardsBefore)
  })
})

describe('加入本学期方案 → 课表实时更新', () => {
  it('加入推荐课程后课表立即出现课块，且 ⛔ 不写 currentSchedule', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    const before = wrapper.findAll('[data-testid="case-a-weekly-block"]').length
    const requestBefore = JSON.stringify(run.mock.calls[0][0])

    await wrapper.findAll('[data-testid="case-a-recommend-add"]').at(0)!.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid="case-a-weekly-block"]').length).toBeGreaterThan(before)
    const origins = wrapper.findAll('[data-testid="case-a-weekly-origin"]').map((n) => n.text())
    expect(origins).toContain('本学期方案')
    expect(run).toHaveBeenCalledTimes(1)
    expect(JSON.stringify(run.mock.calls[0][0])).toBe(requestBefore)
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(0)
  })

  it('移除已加入的课程后课表同步移除', async () => {
    run.mockResolvedValue(response() as never)
    const wrapper = await mountWithResult()

    const before = wrapper.findAll('[data-testid="case-a-weekly-block"]').length
    await wrapper.findAll('[data-testid="case-a-recommend-add"]').at(0)!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="case-a-weekly-block"]').length).toBeGreaterThan(before)

    await wrapper.get('[data-testid="case-a-recommend-remove"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="case-a-weekly-block"]')).toHaveLength(before)
  })
})
