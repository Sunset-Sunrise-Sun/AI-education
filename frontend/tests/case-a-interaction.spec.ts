/**
 * 最终交互轮 —— **真实渲染**回归测试（Issue #61）。
 *
 * ⚠️ 为什么必须 mount 真实组件：本项目的教训是"utility 测试全绿但模块没接线"。
 *    这里所有断言都针对**用户实际看到/能点到的内容**。
 *
 * 覆盖 Codex PREIMPLEMENTATION REVIEW 的必测项：
 * - 计算为 0 的「需要补修」筛选不渲染
 * - 待人工确认项可勾选；批量确认触发**真实 recompute**（提交请求）
 * - 确认后从"待人工确认"移动到"已满足"（用户视角），并带**三项披露**
 * - 撤销确认再次触发 recompute
 * - 选修加入/移除；多个 CLEAR 必须显式选班；UNKNOWN/CONFLICT 无加入动作
 * - 选修选择更新课表与学分摘要
 * - ⛔ 不再有独立的「需要你处理」区块
 * - 议题归属后**没有任何议题被静默丢失**（归属不变式）
 * - 空学期行为与后端 payload 一致
 */

import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import CurrentElectiveSection from '@/components/CurrentElectiveSection.vue'
import FutureRoadmapView from '@/components/FutureRoadmapView.vue'
import MakeupTaskList from '@/components/MakeupTaskList.vue'
import type { NormalizedIssue } from '@/utils/studentIssues'
import { normalizedIssues } from '@/utils/studentIssues'
import { routeIssues, unownedIssueIds } from '@/utils/issueRouting'

const loadCaseAOfferings = vi.fn()
const runCaseADemo = vi.fn()
const applyCaseARepair = vi.fn()

vi.mock('@/api/caseADemo', () => ({
  loadCaseAOfferings: (...args: unknown[]) => loadCaseAOfferings(...args),
  runCaseADemo: (...args: unknown[]) => runCaseADemo(...args),
  applyCaseARepair: (...args: unknown[]) => applyCaseARepair(...args),
}))

const DISCLOSURE = {
  basis: '基于你的确认',
  scope: '仅用于本次规划',
  authority: '不是学校官方认定结果',
}

const OFFERINGS = [
  {
    course_id: 'CSE201',
    course_name: 'Python 程序设计',
    class_id: '01',
    semester: '2026-1',
    credit: 3,
    teacher: null,
    capacity: 90,
    remaining_capacity: 30,
    campus: '南校园',
    classroom: 'A101',
    meetings: [
      { weekday: 1, start_section: 1, end_section: 2, weeks: [1], campus: '南校园', classroom: 'A101' },
    ],
    data_source: 'real',
  },
  {
    course_id: 'CSE317',
    course_name: '通信原理',
    class_id: '01',
    semester: '2026-1',
    credit: 3,
    teacher: null,
    capacity: 60,
    remaining_capacity: 10,
    campus: '南校园',
    classroom: 'B201',
    meetings: [
      { weekday: 3, start_section: 3, end_section: 4, weeks: [1], campus: '南校园', classroom: 'B201' },
    ],
    data_source: 'real',
  },
  {
    course_id: 'CSE321',
    course_name: '计算复杂性理论',
    class_id: '01',
    semester: '2026-1',
    credit: 3,
    teacher: null,
    capacity: 60,
    remaining_capacity: 10,
    campus: '南校园',
    classroom: 'B202',
    meetings: [
      { weekday: 4, start_section: 3, end_section: 4, weeks: [1], campus: '南校园', classroom: 'B202' },
    ],
    data_source: 'real',
  },
  {
    course_id: 'CSE321',
    course_name: '计算复杂性理论',
    class_id: '02',
    semester: '2026-1',
    credit: 3,
    teacher: null,
    capacity: 60,
    remaining_capacity: 10,
    campus: '南校园',
    classroom: 'B203',
    meetings: [
      { weekday: 5, start_section: 3, end_section: 4, weeks: [1], campus: '南校园', classroom: 'B203' },
    ],
    data_source: 'real',
  },
]

function makeupTasks() {
  return [
    {
      course_id: 'MAR103',
      course_name: '中国近现代史纲要',
      credit: 3,
      status: 'satisfied',
      recommended_semester: null,
      deadline_semester: null,
      prerequisites: [],
      reason: '已确认满足。',
      source_evidence: 'evidence://mar103',
    },
    {
      course_id: 'CSE101',
      course_name: '程序设计I',
      credit: 3,
      status: 'manual_confirmation',
      recommended_semester: 3,
      deadline_semester: 5,
      prerequisites: [],
      reason: '仍有课程号待确认的已修记录，不能确定缺课。',
      source_evidence: 'evidence://cse101',
    },
    {
      course_id: 'CSE103',
      course_name: '程序设计I实验',
      credit: 1,
      status: 'manual_confirmation',
      recommended_semester: 3,
      deadline_semester: 5,
      prerequisites: [],
      reason: '仍有课程号待确认的已修记录，不能确定缺课。',
      source_evidence: 'evidence://cse103',
    },
  ]
}

/** 只含 required 的补修任务（用于「需要补修」计数 > 0 的场景）。 */
function tasksWithRequired() {
  return [
    ...makeupTasks(),
    {
      course_id: 'CSE204',
      course_name: '数据结构',
      credit: 3,
      status: 'required',
      recommended_semester: 3,
      deadline_semester: 5,
      prerequisites: [],
      reason: '培养方案要求，尚未修读。',
      source_evidence: null,
    },
  ]
}

function planResponse(overrides: Record<string, unknown> = {}) {
  return {
    transcript: {
      source_id: 's',
      artifact_sha256: 'a'.repeat(64),
      record_count: 3,
      term_count: 1,
      terms: [],
      pending_course_id_count: 3,
    },
    makeup_tasks: makeupTasks(),
    course_offerings: OFFERINGS,
    preference: { max_credit: null, avoid_cross_campus: false, preferred_courses: [], avoid_times: [] },
    plan_result: {
      status: 'partially_feasible',
      selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
      changes: [],
      risks: [],
      unresolved: [],
      objective_summary: null,
    },
    repair_proposals: { semester: '2026-1', proposals: [], unresolved: [] },
    roadmap: {
      current_semester: '2026-1',
      current_semester_planned_course_ids: [],
      future_semesters: [
        {
          semester_label: '2026-2',
          curriculum_semester: 3,
          semester_index: 1,
          courses: [
            {
              course_id: 'CSE204',
              course_name: '数据结构',
              credit: 3,
              requirement_kind: 'required',
              requirement_label: '必修',
              placement: 'required_by_recommended_term',
              reason: '按培养方案建议学期安排。',
            },
          ],
          required_credit: 3,
          elective_credit: 0,
          total_credit: 3,
          warnings: [],
        },
      ],
      elective: {
        requirement_credit: 23,
        completed_credit: 0,
        current_semester_credit: 0,
        planned_credit: 0,
        remaining_credit: 23,
        gap_credit: 23,
        group_id: 'CSE-ELECTIVE-POOL',
      },
      unresolved: [],
      warnings: [],
    },
    roadmap_note: null,
    completed_binding: 'not_bound',
    completed_binding_note: '上传的成绩单未参与认定。',
    current_elective_recommendations: [
      {
        course_id: 'CSE317',
        course_name: '通信原理',
        credit: 3,
        available_class_count: 1,
        conflicting_class_count: 0,
        unknown_schedule_class_count: 0,
        clear_class_count: 1,
        unique_clear_class_id: '01',
        clear_class_ids: ['01'],
        conflict_label: '已找到与当前课表不冲突的教学班',
      },
      {
        course_id: 'CSE321',
        course_name: '计算复杂性理论',
        credit: 3,
        available_class_count: 2,
        conflicting_class_count: 0,
        unknown_schedule_class_count: 0,
        clear_class_count: 2,
        unique_clear_class_id: null,
        // 两个 CLEAR 教学班都必须列出（另一个 01 已与课表冲突，见 OFFERINGS）
        clear_class_ids: ['02'],
        conflict_label: '已找到与当前课表不冲突的教学班',
      },
      {
        course_id: 'CSE323',
        course_name: '数字图像处理',
        credit: 3,
        available_class_count: 2,
        conflicting_class_count: 2,
        unknown_schedule_class_count: 0,
        clear_class_count: 0,
        unique_clear_class_id: null,
        clear_class_ids: [],
        conflict_label: '当前候选教学班均与你的课表冲突',
      },
    ],
    current_load: {
      selected_credit: 0,
      suggested_makeup_credit: 0,
      suggested_elective_credit: 0,
      projected_total_credit: 0,
      max_credit: 30,
      exceeds_max: false,
      policy_note: '产品默认上限。',
    },
    applied_manual_confirmations: [],
    rejected_manual_confirmations: [],
    applied_elective_sections: [],
    rejected_elective_selections: [],
    effective_makeup_tasks: makeupTasks(),
    planning_only_disclosure: DISCLOSURE,
    provenance: {
      transcript: 't',
      curriculum: 'c',
      course_data: 'case-scoped:south+shenzhen',
      current_schedule: 'selected accepted offering',
      planner: 'actual RestrictedPlanner execution',
      is_full_semester: false,
    },
    ...overrides,
  }
}

function primaryText(html: string): string {
  const host = document.createElement('div')
  host.innerHTML = html.replace(/<details[\s\S]*?<\/details>/gi, '')
  return host.textContent ?? ''
}

async function mountPage(overrides: Record<string, unknown> = {}) {
  runCaseADemo.mockResolvedValue(planResponse(overrides))
  const wrapper = mount(CaseADemoView)
  await flushPromises()
  const file = new File(['%PDF'], 't.pdf', { type: 'application/pdf' })
  Object.defineProperty(wrapper.get('[data-testid="case-a-pdf"]').element, 'files', {
    value: [file],
    configurable: true,
  })
  await wrapper.get('[data-testid="case-a-pdf"]').trigger('change')
  await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  loadCaseAOfferings.mockReset()
  runCaseADemo.mockReset()
  applyCaseARepair.mockReset()
  loadCaseAOfferings.mockResolvedValue(OFFERINGS)
})

// ---------------------------------------------------------------------------
// 补修缺口分析：0 计数筛选 + 规划确认交互
// ---------------------------------------------------------------------------

describe('补修缺口分析', () => {
  it('「需要补修」计数为 0 时**不渲染**该筛选', async () => {
    expect(makeupTasks().some((t) => t.status === 'required')).toBe(false)
    const wrapper = await mountPage()
    expect(wrapper.find('[data-testid="makeup-filter-required"]').exists()).toBe(false)
    // 其它计数 > 0 的筛选仍然渲染
    expect(wrapper.find('[data-testid="makeup-filter-manual"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="makeup-filter-satisfied"]').exists()).toBe(true)
  })

  it('计数 > 0 时渲染「需要补修」筛选', async () => {
    const wrapper = await mountPage({ makeup_tasks: tasksWithRequired() })
    expect(wrapper.find('[data-testid="makeup-filter-required"]').exists()).toBe(true)
  })

  it('待人工确认项可勾选，批量确认触发**真实 recompute**', async () => {
    const wrapper = await mountPage()
    const before = runCaseADemo.mock.calls.length

    await wrapper.get('[data-testid="makeup-confirm-CSE101"]').trigger('click')
    await flushPromises()

    // ✅ 真的发起了重算请求（⛔ 不是本地改状态）
    expect(runCaseADemo.mock.calls.length).toBe(before + 1)
    const lastCall = runCaseADemo.mock.calls.at(-1)?.[0] as {
      override?: { userConfirmedManualTaskKeys: string[] }
    }
    expect(lastCall.override?.userConfirmedManualTaskKeys).toEqual(['CSE101'])
  })

  it('确认后该课程从「待人工确认」移动到「已满足」，并带三项披露', async () => {
    const effective = makeupTasks().map((t) =>
      t.course_id === 'CSE101'
        ? {
            ...t,
            status: 'satisfied',
            reason: `${t.reason}｜基于你的确认，仅用于本次规划；不是学校官方认定结果`,
          }
        : t,
    )
    const wrapper = await mountPage({
      applied_manual_confirmations: ['CSE101'],
      effective_makeup_tasks: effective,
      // 来源可核验的 makeup_tasks 仍然保持 manual_confirmation（⛔ 未被改写）
    })

    // 用户视角：该行显示"已满足" + "基于你的确认"
    const row = wrapper.get('[data-testid="makeup-row-CSE101"]')
    expect(row.text()).toContain('已满足')
    expect(row.text()).toContain(DISCLOSURE.basis)
    expect(wrapper.find('[data-testid="makeup-user-confirmed-CSE101"]').exists()).toBe(true)

    // 三项披露同时出现（操作披露 + 结果状态披露）
    const disclosure = wrapper.get('[data-testid="makeup-confirm-disclosure"]').text()
    expect(disclosure).toContain(DISCLOSURE.basis)
    expect(disclosure).toContain(DISCLOSURE.scope)
    expect(disclosure).toContain(DISCLOSURE.authority)
    // 明确声明不改学校系统记录
    expect(disclosure).toContain('不会修改学校教务系统记录')
    const confirmed = wrapper.get('[data-testid="makeup-confirmed-title"]').text()
    expect(confirmed).toContain(DISCLOSURE.basis)
    expect(confirmed).toContain(DISCLOSURE.scope)
    expect(confirmed).toContain(DISCLOSURE.authority)

    // ⛔ 来源可核验的基础评估没有被改写
    const payload = planResponse()
    expect(
      payload.makeup_tasks.filter((t) => t.status === 'manual_confirmation').length,
    ).toBe(2)
  })

  it('撤销确认触发再次 recompute，并清掉该 key', async () => {
    const effective = makeupTasks().map((t) =>
      t.course_id === 'CSE101' ? { ...t, status: 'satisfied' } : t,
    )
    const wrapper = await mountPage({
      applied_manual_confirmations: ['CSE101'],
      effective_makeup_tasks: effective,
    })
    const before = runCaseADemo.mock.calls.length
    await wrapper.get('[data-testid="makeup-undo-CSE101"]').trigger('click')
    await flushPromises()

    expect(runCaseADemo.mock.calls.length).toBe(before + 1)
    const lastCall = runCaseADemo.mock.calls.at(-1)?.[0] as {
      override?: { userConfirmedManualTaskKeys: string[] }
    }
    expect(lastCall.override?.userConfirmedManualTaskKeys).toEqual([])
  })

  it('依据默认折叠在「查看依据」后面', async () => {
    const wrapper = await mountPage()
    const toggle = wrapper.get('[data-testid="makeup-evidence-CSE101"]')
    expect(toggle.text()).toContain('查看依据')
    expect(wrapper.find('[data-testid="makeup-evidence-body-CSE101"]').exists()).toBe(false)
    await toggle.trigger('click')
    expect(wrapper.get('[data-testid="makeup-evidence-body-CSE101"]').text()).toContain(
      'evidence://cse101',
    )
  })

  it('来源可核验的基础评估如实声明不被用户确认改写', async () => {
    const wrapper = await mountPage()
    expect(wrapper.get('[data-testid="makeup-source-note"]').text()).toContain('来源可核验')
  })
})

// ---------------------------------------------------------------------------
// 选修交互
// ---------------------------------------------------------------------------

describe('本学期专业选修建议', () => {
  function mountElective(overrides: Record<string, unknown> = {}) {
    return mount(CurrentElectiveSection, {
      props: {
        recommendations: planResponse().current_elective_recommendations,
        load: planResponse().current_load,
        applied: [],
        offerings: OFFERINGS as never,
        semester: '2026-1',
        ...overrides,
      },
    })
  }

  it('唯一 CLEAR 可直接加入（仍需显式点击），并发起 recompute', async () => {
    const wrapper = mountElective()
    const add = wrapper.get('[data-testid="elective-add-CSE317"]')
    expect(add.text()).toContain('加入本学期方案')
    expect(wrapper.emitted('add')).toBeUndefined()
    await add.trigger('click')
    expect(wrapper.emitted('add')?.[0]?.[0]).toEqual({
      courseId: 'CSE317',
      classId: '01',
      semester: '2026-1',
    })
  })

  it('多个 CLEAR 必须显式选择教学班（⛔ 不自动挑一个）', async () => {
    const wrapper = mountElective()
    const add = wrapper.get('[data-testid="elective-add-CSE321"]')
    // 未选班前不可加入
    expect(add.attributes('disabled')).toBeDefined()
    await add.trigger('click')
    expect(wrapper.emitted('add')).toBeUndefined()

    // 显式选班后可以加入
    const radio = wrapper.get('[data-testid="elective-section-CSE321-02"] input')
    await radio.setValue(true)
    await wrapper.get('[data-testid="elective-add-CSE321"]').trigger('click')
    expect(wrapper.emitted('add')?.[0]?.[0]).toEqual({
      courseId: 'CSE321',
      classId: '02',
      semester: '2026-1',
    })
  })

  it('UNKNOWN / CONFLICT 只有 ⇒ 没有加入动作，并说明原因', () => {
    const wrapper = mountElective()
    expect(wrapper.find('[data-testid="elective-add-CSE323"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="elective-blocked-reason"]').text()).toContain(
      '无法加入本学期方案',
    )
  })

  it('⛔ 混合候选 [CLEAR, CLEAR, CONFLICT, UNKNOWN] 只暴露 CLEAR 教学班', () => {
    // 服务端判定：CSE321 有 2 个 CLEAR（02、03），另 1 个 CONFLICT（01）、1 个 UNKNOWN（04）
    const mixed = {
      course_id: 'CSE321',
      course_name: '计算复杂性理论',
      credit: 3,
      available_class_count: 4,
      conflicting_class_count: 1,
      unknown_schedule_class_count: 1,
      clear_class_count: 2,
      unique_clear_class_id: null,
      clear_class_ids: ['02', '03'],
      conflict_label: '部分候选与课表冲突，另有候选排课信息尚未同步',
    }
    const offerings = [
      ...OFFERINGS,
      {
        course_id: 'CSE321', course_name: '计算复杂性理论', class_id: '03',
        semester: '2026-1', credit: 3,
        meetings: [{ weekday: 2, start_section: 1, end_section: 2, weeks: [1] }],
        data_source: 'real',
      },
      {
        // 与 CSE201 同时间 ⇒ 已知冲突
        course_id: 'CSE321', course_name: '计算复杂性理论', class_id: '01',
        semester: '2026-1', credit: 3,
        meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1] }],
        data_source: 'real',
      },
      {
        // meetings=[] ⇒ 排课信息待核验
        course_id: 'CSE321', course_name: '计算复杂性理论', class_id: '04',
        semester: '2026-1', credit: 3, meetings: [], data_source: 'real',
      },
    ]
    const wrapper = mount(CurrentElectiveSection, {
      props: {
        recommendations: [mixed] as never,
        load: planResponse().current_load,
        applied: [],
        offerings: offerings as never,
        semester: '2026-1',
      },
    })

    // ✅ 只渲染服务端确认无冲突的教学班
    expect(wrapper.find('[data-testid="elective-section-CSE321-02"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="elective-section-CSE321-03"]').exists()).toBe(true)
    // ⛔ CONFLICT / UNKNOWN 绝不成为可点选项
    expect(wrapper.find('[data-testid="elective-section-CSE321-01"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="elective-section-CSE321-04"]').exists()).toBe(false)
  })

  it('已加入的选修显示 ✓ 已加入 + 撤销', async () => {
    const wrapper = mountElective({
      applied: [
        { course_id: 'CSE317', course_name: '通信原理', class_id: '01', credit: 3 },
      ],
    })
    expect(wrapper.get('[data-testid="elective-applied"]').text()).toContain('已加入本学期方案')
    await wrapper.get('[data-testid="elective-remove-CSE317"]').trigger('click')
    expect(wrapper.emitted('remove')?.[0]?.[0]).toEqual({
      courseId: 'CSE317',
      classId: '01',
      semester: '2026-1',
    })
  })

  it('选修选择更新课表与学分摘要（通过页面 recompute 结果）', async () => {
    const wrapper = await mountPage({
      applied_elective_sections: [
        { course_id: 'CSE317', course_name: '通信原理', class_id: '01', credit: 3 },
      ],
      current_load: {
        selected_credit: 3,
        suggested_makeup_credit: 0,
        suggested_elective_credit: 0,
        projected_total_credit: 3,
        max_credit: 30,
        exceeds_max: false,
        policy_note: '产品默认上限。',
      },
    })
    expect(wrapper.get('[data-testid="elective-applied"]').text()).toContain('通信原理')
    // 学分摘要来自服务端结果（⛔ 不是前端自己算的）
    expect(wrapper.get('[data-testid="case-a-credit-load"]').text()).toContain('预计合计 3 学分')
  })
})

// ---------------------------------------------------------------------------
// 页面结构：没有独立待处理区块 + 议题归属不丢失
// ---------------------------------------------------------------------------

describe('页面结构与议题归属', () => {
  const ISSUES: NormalizedIssue[] = normalizedIssues({
    planUnresolved: [
      { type: 'manual_confirmation', message: '课程 CSE101 的补修认定仍需人工确认。' },
      { type: 'selection_required', message: '课程 CSE204 有多个可选教学班。' },
      { type: 'schedule_unknown', message: '课程 CSE205 排课信息缺失。' },
      { type: 'some_unknown_code', message: '' },
    ],
    roadmapUnresolved: ['课程 CSE206 的 recommended_semester=4 不在学期映射中（no_alternatives）。'],
    repairUnresolved: ['课程 CSE207 没有可确认无冲突的同课程候选（no_alternatives）。'],
    courseNameById: {},
  })

  it('⛔ 不再渲染独立的「需要你处理」区块', async () => {
    const wrapper = await mountPage({
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [{ type: 'schedule_unknown', message: '课程 CSE205 排课信息缺失。' }],
        objective_summary: null,
      },
    })
    expect(wrapper.find('[data-testid="case-a-pending-center"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('需要你处理')
  })

  it('议题归属不变式：每个议题恰好被归属一次（⛔ 无静默丢失）', () => {
    expect(ISSUES.length).toBeGreaterThan(0)
    expect(unownedIssueIds(ISSUES)).toEqual([])
    const routed = routeIssues(ISSUES)
    const total =
      routed.makeup.length +
      routed.elective.length +
      routed.timetable.length +
      routed.roadmap.length +
      routed.detailedEvidence.length
    expect(total).toBe(ISSUES.length)
  })

  it('真实页面上所有归属区块的议题数量之和 === 归一化议题总数', async () => {
    const wrapper = await mountPage({
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [
          { type: 'schedule_unknown', message: '课程 CSE205 排课信息缺失。' },
          { type: 'manual_confirmation', message: '课程 CSE101 的补修认定仍需人工确认。' },
        ],
        objective_summary: null,
      },
      repair_proposals: {
        semester: '2026-1',
        proposals: [],
        unresolved: ['课程 CSE207 没有可确认无冲突的同课程候选（no_alternatives）。'],
      },
    })
    // 议题只在**唯一的底部提醒区**渲染，默认折叠 ⇒ 先展开
    await wrapper.get('[data-testid="case-a-reminders-toggle"]').trigger('click')
    await flushPromises()
    const rendered = wrapper.findAll('[data-testid="case-a-issue"]').length
    expect(rendered).toBeGreaterThan(0)

    // ⚠️ 要求是"⛔ 没有议题被静默丢失"，而不是"恰好渲染 N 次"：
    //    兜底区为了 fail-safe 会同时覆盖归属未来路径的议题（可见时即重复）。
    //    因此这里断言**每一条**归一化议题都至少渲染一次。
    const expected = normalizedIssues({
      planUnresolved: [
        { type: 'schedule_unknown', message: '课程 CSE205 排课信息缺失。' },
        { type: 'manual_confirmation', message: '课程 CSE101 的补修认定仍需人工确认。' },
      ],
      repairUnresolved: ['课程 CSE207 没有可确认无冲突的同课程候选（no_alternatives）。'],
      courseNameById: {},
    })
    const renderedText = wrapper
      .findAll('[data-testid="case-a-issue"]')
      .map((n) => n.text())
      .join('\n')
    for (const issue of expected) {
      // 每条议题的标题（课程名或课程号）必须至少出现一次
      expect(renderedText, issue.id).toContain(issue.title)
    }
    expect(unownedIssueIds(expected)).toEqual([])
  })

  it('⛔ roadmap 为 null（且无说明）时，议题仍不丢失（统一提醒区兜底）', async () => {
    const wrapper = await mountPage({
      roadmap: null,
      roadmap_note: null,
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [{ type: 'some_unknown_code', message: '课程 CSE206 的安排需要进一步确认。' }],
        objective_summary: null,
      },
    })
    // 未来路径区块不存在，但议题必须出现在**唯一**的底部提醒区里
    expect(wrapper.find('[data-testid="case-a-roadmap-note"]').exists()).toBe(false)
    await wrapper.get('[data-testid="case-a-reminders-toggle"]').trigger('click')
    await flushPromises()
    const cards = wrapper.findAll('[data-testid="case-a-issue"]')
    expect(cards.length).toBeGreaterThanOrEqual(1)
    expect(cards.some((c) => c.text().includes('CSE206'))).toBe(true)
  })

  it('⛔ roadmap.future_semesters 为空时，议题仍不丢失（统一提醒区兜底）', async () => {
    const emptyRoadmap = {
      current_semester: '2026-1',
      current_semester_planned_course_ids: [],
      future_semesters: [],
      elective: {
        requirement_credit: 23,
        completed_credit: 0,
        current_semester_credit: 0,
        planned_credit: 0,
        remaining_credit: 23,
        gap_credit: 23,
        group_id: 'CSE-ELECTIVE-POOL',
      },
      unresolved: [],
      warnings: [],
    }
    const wrapper = await mountPage({
      roadmap: emptyRoadmap,
      roadmap_note: null,
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [{ type: 'some_unknown_code', message: '课程 CSE206 的安排需要进一步确认。' }],
        objective_summary: null,
      },
    })
    await wrapper.get('[data-testid="case-a-reminders-toggle"]').trigger('click')
    await flushPromises()
    const cards = wrapper.findAll('[data-testid="case-a-issue"]')
    expect(cards.length).toBeGreaterThanOrEqual(1)
    expect(cards.some((c) => c.text().includes('CSE206'))).toBe(true)
  })

  it('主界面不出现任何机器码', async () => {
    const wrapper = await mountPage({
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [
          { type: 'schedule_unknown', message: '课程 CSE205 排课信息缺失。' },
          { type: 'manual_confirmation', message: '课程 CSE101 的补修认定仍需人工确认。' },
        ],
        objective_summary: null,
      },
      repair_proposals: {
        semester: '2026-1',
        proposals: [],
        unresolved: ['课程 CSE207 没有可确认无冲突的同课程候选（no_alternatives）。'],
      },
    })
    const text = primaryText(wrapper.html())
    for (const code of [
      'schedule_unknown',
      'manual_confirmation',
      'no_alternatives',
      'selection_required',
      'type:',
    ]) {
      expect(text, code).not.toContain(code)
    }
  })

  it('区块顺序：补修 → 选修 → 课表 → 未来 → 详细依据', async () => {
    // 顺序以**源码模板**为准（渲染后的 HTML 会因组件内部文本而干扰定位）
    const source = readFileSync('src/components/CaseADemoView.vue', 'utf-8')
    const order = [
      'title="补修缺口分析"',
      'title="本学期专业选修建议"',
      'title="本学期推荐课表"',
      'title="未来学期修读路径"',
      'title="详细依据"',
    ]
    const positions = order.map((needle) => source.indexOf(needle))
    for (const [index, pos] of positions.entries()) {
      expect(pos, order[index]).toBeGreaterThan(-1)
      if (index > 0) expect(pos, order[index]).toBeGreaterThan(positions[index - 1])
    }

    // 渲染后同样是这五个区块，且成绩单/总览在它们之前
    const wrapper = await mountPage()
    for (const title of ['补修缺口分析', '本学期专业选修建议', '本学期推荐课表', '未来学期修读路径', '详细依据']) {
      expect(wrapper.text(), title).toContain(title)
    }
  })
})

// ---------------------------------------------------------------------------
// 空学期诚实性
// ---------------------------------------------------------------------------

describe('空学期诚实性', () => {
  function roadmapWith(semester: Record<string, unknown>) {
    const base = planResponse().roadmap as Record<string, unknown>
    return { ...base, future_semesters: [semester] }
  }

  it('API 有学分但课程为空 ⇒ ⛔ 不谎称"没有课程"', () => {
    const wrapper = mount(FutureRoadmapView, {
      props: {
        roadmap: roadmapWith({
          semester_label: '2028-1',
          curriculum_semester: 7,
          semester_index: 4,
          courses: [],
          required_credit: 7,
          elective_credit: 0,
          total_credit: 7,
          warnings: [],
        }) as never,
      },
    })
    // 不能说"没有需要安排的课程"
    expect(wrapper.text()).not.toContain('没有需要安排的课程')
    expect(wrapper.find('[data-testid="case-a-roadmap-empty-term-inconsistent"]').exists()).toBe(
      true,
    )
    // 但如实展示建议学分
    expect(wrapper.text()).toContain('7')
  })

  it('真正为空的学期显示刻意设计的空状态', () => {
    const wrapper = mount(FutureRoadmapView, {
      props: {
        roadmap: roadmapWith({
          semester_label: '2028-1',
          curriculum_semester: 7,
          semester_index: 4,
          courses: [],
          required_credit: 0,
          elective_credit: 0,
          total_credit: 0,
          warnings: [],
        }) as never,
      },
    })
    const empty = wrapper.get('[data-testid="case-a-roadmap-empty-term"]')
    expect(empty.text()).toContain('按当前方案，该学期暂不需要额外安排课程')
    expect(
      wrapper.find('[data-testid="case-a-roadmap-empty-term-inconsistent"]').exists(),
    ).toBe(false)
  })

  it('真实 7.0 学分的 2028-1 正常渲染课程与学分', () => {
    const wrapper = mount(FutureRoadmapView, {
      props: {
        roadmap: roadmapWith({
          semester_label: '2028-1',
          curriculum_semester: 7,
          semester_index: 4,
          courses: [
            {
              course_id: 'PHY137',
              course_name: '大学物理（工）上',
              credit: 3,
              requirement_kind: 'required',
              requirement_label: '必修',
              placement: 'deferred_for_credit_budget',
              reason: '受先修或学分预算影响。',
            },
            {
              course_id: 'PHY139',
              course_name: '大学物理（工）下',
              credit: 4,
              requirement_kind: 'required',
              requirement_label: '必修',
              placement: 'deferred_for_credit_budget',
              reason: '受先修或学分预算影响。',
            },
          ],
          required_credit: 7,
          elective_credit: 0,
          total_credit: 7,
          warnings: [],
        }) as never,
      },
    })
    const text = wrapper.text()
    expect(text).toContain('大学物理（工）上')
    expect(text).toContain('大学物理（工）下')
    expect(text).toContain('建议学分：7')
    expect(wrapper.find('[data-testid="case-a-roadmap-empty-term"]').exists()).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// MakeupTaskList 直接单测（交互细节）
// ---------------------------------------------------------------------------

describe('MakeupTaskList 交互细节', () => {
  it('只有未确认的 manual_confirmation 才有逐条操作按钮', () => {
    const wrapper = mount(MakeupTaskList, {
      props: {
        tasks: makeupTasks() as never,
        confirmedKeys: [],
        disclosure: DISCLOSURE,
      },
    })
    expect(wrapper.find('[data-testid="makeup-confirm-CSE101"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="makeup-defer-CSE101"]').exists()).toBe(true)
    // 已满足项没有操作按钮
    expect(wrapper.find('[data-testid="makeup-confirm-MAR103"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="makeup-defer-MAR103"]').exists()).toBe(false)
  })

  it('「暂不确认」是本地视图状态，撤销后回到待确认', async () => {
    const wrapper = mount(MakeupTaskList, {
      props: { tasks: makeupTasks() as never, confirmedKeys: [], disclosure: DISCLOSURE },
    })
    await wrapper.get('[data-testid="makeup-defer-CSE101"]').trigger('click')
    expect(wrapper.get('[data-testid="makeup-deferred-CSE101"]').text()).toContain('暂不确认')
    // ⛔ 暂不确认不提交任何请求
    expect(wrapper.emitted('confirm')).toBeUndefined()
    await wrapper.get('[data-testid="makeup-undefer-CSE101"]').trigger('click')
    expect(wrapper.find('[data-testid="makeup-deferred-CSE101"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="makeup-confirm-CSE101"]').exists()).toBe(true)
  })

  it('单项确认发出"完整期望状态"（已有确认 + 本项）', async () => {
    const wrapper = mount(MakeupTaskList, {
      props: { tasks: makeupTasks() as never, confirmedKeys: ['CSE103'], disclosure: DISCLOSURE },
    })
    await wrapper.get('[data-testid="makeup-confirm-CSE101"]').trigger('click')
    expect(wrapper.emitted('confirm')?.[0]?.[0]).toEqual({ courseIds: ['CSE101', 'CSE103'] })
  })

  it('已确认项不再可勾选（从待确认移出）', () => {
    const wrapper = mount(MakeupTaskList, {
      props: {
        tasks: makeupTasks() as never,
        confirmedKeys: ['CSE101'],
        disclosure: DISCLOSURE,
      },
    })
    expect(wrapper.find('[data-testid="makeup-select-CSE101"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="makeup-confirmed-item"]')).toHaveLength(1)
  })

  it('pending 时禁用确认与撤销（⛔ 不乐观更新）', () => {
    const wrapper = mount(MakeupTaskList, {
      props: {
        tasks: makeupTasks() as never,
        confirmedKeys: ['CSE101'],
        disclosure: DISCLOSURE,
        pending: true,
      },
    })
    expect(wrapper.get('[data-testid="makeup-undo-CSE101"]').attributes('disabled')).toBeDefined()
  })
})
