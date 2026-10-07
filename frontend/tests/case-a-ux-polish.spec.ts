/**
 * 最终 UX 收尾轮 —— 真实渲染回归测试。
 *
 * 覆盖本轮 7 项产品要求的**可验证部分**（⛔ 不做纯样式断言）：
 *
 * 1. 中间重复的「待确认事项」大块已移除；页面底部**只有一处**统一提醒区；
 * 2. 补修「待人工确认」逐条只有一个 toggle 主操作（确认 / 已确认可撤销）+ 三项披露；
 * 3. 专业选修可加入/撤销，且**数据库选修可达**（不再被显示上限静默藏掉）；
 * 4. 交互后是**局部**更新体验（按模块 pending + 轻量反馈）；
 * 5. 标签色/层级由 global CSS 统一（此处只断言结构化标签存在）；
 * 6. 课表有类别标签与图例，且类别来自真实数据。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import CurrentElectiveSection from '@/components/CurrentElectiveSection.vue'
import WeeklyScheduleView from '@/components/WeeklyScheduleView.vue'

const loadCaseAOfferings = vi.fn()
const runCaseADemo = vi.fn()
const applyCaseARepair = vi.fn()

vi.mock('@/api/caseADemo', () => ({
  loadCaseAOfferings: (...a: unknown[]) => loadCaseAOfferings(...a),
  runCaseADemo: (...a: unknown[]) => runCaseADemo(...a),
  applyCaseARepair: (...a: unknown[]) => applyCaseARepair(...a),
}))

const DISCLOSURE = {
  basis: '基于你的确认',
  scope: '仅用于本次规划',
  authority: '不是学校官方认定结果',
}

const OFFERINGS = [
  ['CSE201', 'Python 程序设计', '01', 3, 1],
  ['CSE335', '数据库系统原理', '202616238', 3, 2],
  ['CSE337', '数据库系统实验', '202616239', 1, 3],
].map(([course_id, course_name, class_id, credit, weekday]) => ({
  course_id,
  course_name,
  class_id,
  semester: '2026-1',
  credit,
  teacher: null,
  capacity: 90,
  remaining_capacity: 30,
  campus: '南校园',
  classroom: 'A101',
  meetings: [{ weekday, start_section: 1, end_section: 2, weeks: [1] }],
  data_source: 'real',
})) as never as Record<string, unknown>[]

function rec(course_id: string, course_name: string, credit: number, clear: string[]) {
  return {
    course_id,
    course_name,
    credit,
    available_class_count: clear.length,
    conflicting_class_count: 0,
    unknown_schedule_class_count: 0,
    clear_class_count: clear.length,
    unique_clear_class_id: clear.length === 1 ? clear[0] : null,
    clear_class_ids: clear,
    conflict_label: '已找到与当前课表不冲突的教学班',
  }
}

/** 7 门候选：数据库课程排在第 4、7 位（正是旧上限会藏掉的位置）。 */
const ELECTIVES = [
  rec('CSE317', '通信原理', 3, ['01']),
  rec('CSE321', '计算复杂性理论', 3, ['01']),
  rec('CSE323', '数字图像处理', 3, ['01']),
  rec('CSE335', '数据库系统原理', 3, ['202616238']),
  rec('CSE357', '模式识别与计算机视觉', 3, ['01']),
  rec('CSE359', '深度学习', 3, ['01']),
  rec('CSE337', '数据库系统实验', 1, ['202616239']),
]

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
    makeup_tasks: [
      {
        course_id: 'CSE101',
        course_name: '程序设计I',
        credit: 3,
        status: 'manual_confirmation',
        recommended_semester: 3,
        deadline_semester: 5,
        prerequisites: [],
        reason: '仍有课程号待确认的已修记录。',
        source_evidence: 'evidence://cse101',
      },
      {
        course_id: 'MAR103',
        course_name: '中国近现代史纲要',
        credit: 3,
        status: 'satisfied',
        recommended_semester: null,
        deadline_semester: null,
        prerequisites: [],
        reason: '已确认满足。',
        source_evidence: null,
      },
    ],
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
    current_elective_recommendations: ELECTIVES,
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
    effective_makeup_tasks: [],
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

describe('1. 冗余提醒块已收口', () => {
  it('页面中只有一个统一提醒区，且中间不再出现"与本区块相关的待确认事项"', async () => {
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
    })
    // ✅ 有且仅有一个统一提醒区
    expect(wrapper.findAll('[data-testid="case-a-reminders"]')).toHaveLength(1)
    // ⛔ 不再有模块内部的重复大块
    expect(wrapper.findAll('[data-testid="case-a-issue-list"]')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('与本区块相关的待确认事项')
  })

  it('提醒区默认折叠，只给汇总；展开后才列出明细', async () => {
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
    expect(wrapper.get('[data-testid="case-a-reminders-summary"]').exists()).toBe(true)
    // 默认折叠：明细不可见
    expect(wrapper.findAll('[data-testid="case-a-issue"]')).toHaveLength(0)
    await wrapper.get('[data-testid="case-a-reminders-toggle"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="case-a-issue"]').length).toBeGreaterThan(0)
  })

  it('没有议题时给出中性说明，不编造', async () => {
    const wrapper = await mountPage()
    expect(wrapper.get('[data-testid="case-a-reminders-none"]').exists()).toBe(true)
  })
})

describe('2. 补修「待人工确认」逐条可操作', () => {
  it('每个待确认项都有课程身份，且左侧只有一个“确认可转换”主按钮', async () => {
    const wrapper = await mountPage()
    const row = wrapper.get('[data-testid="makeup-row-CSE101"]')
    // 课程名优先，课程号次级；⛔ 不是匿名"需要你确认"卡片
    expect(row.text()).toContain('程序设计I')
    expect(row.text()).toContain('CSE101')
    expect(row.text()).not.toContain('需要你确认')
    const action = wrapper.get('[data-testid="makeup-action-region-CSE101"]')
    expect(action.findAll('button')).toHaveLength(1)
    expect(action.get('[data-testid="makeup-confirm-CSE101"]').text()).toBe('确认可转换')
    expect(wrapper.find('[data-testid="makeup-defer-CSE101"]').exists()).toBe(false)
    expect(action.text()).not.toContain('暂不确认')
  })

  it('「确认可转换」成功后同一个主按钮变为明显的“已确认”toggle', async () => {
    const wrapper = await mountPage()
    runCaseADemo.mockResolvedValueOnce(
      planResponse({ applied_manual_confirmations: ['CSE101'] }),
    )
    await wrapper.get('[data-testid="makeup-confirm-CSE101"]').trigger('click')
    await flushPromises()
    expect(runCaseADemo).toHaveBeenCalled()
    const body = runCaseADemo.mock.calls.at(-1)?.[0] as {
      override?: { userConfirmedManualTaskKeys: string[] }
    }
    expect(body.override?.userConfirmedManualTaskKeys).toEqual(['CSE101'])
    const action = wrapper.get('[data-testid="makeup-action-region-CSE101"]')
    const confirmed = action.get('[data-testid="makeup-undo-CSE101"]')
    expect(action.findAll('button')).toHaveLength(1)
    expect(confirmed.text()).toContain('已确认')
    expect(confirmed.classes()).toContain('makeup-confirm-toggle--confirmed')
    expect(confirmed.attributes('aria-pressed')).toBe('true')
    // 模块内轻量反馈（⛔ 不是整页提示）
    expect(wrapper.get('[data-testid="case-a-makeup-notice"]').text()).toContain('已根据你的确认')
  })

  it('表格使用固定 7 列与单操作区结构，行分隔不再由 flex td 拼接', async () => {
    const wrapper = await mountPage()
    const table = wrapper.get('[data-testid="makeup-task-table"]')
    expect(table.classes()).toContain('makeup-task-table')
    expect(table.findAll('col.makeup-col')).toHaveLength(7)
    const row = wrapper.get('[data-testid="makeup-row-CSE101"]')
    expect(row.findAll(':scope > td')).toHaveLength(7)
    expect(row.get('td.makeup-actions-cell').find('.makeup-action-region').exists()).toBe(true)
    expect(row.get('td.makeup-actions-cell').classes()).not.toContain('makeup-action-region')
  })

  it('披露同时说明：仅用于本次规划 / 非官方认定 / 不改教务系统', async () => {
    const wrapper = await mountPage()
    const text = wrapper.get('[data-testid="makeup-confirm-disclosure"]').text()
    expect(text).toContain(DISCLOSURE.scope)
    expect(text).toContain(DISCLOSURE.authority)
    expect(text).toContain('不会修改学校教务系统记录')
  })

  it('已确认项显示"基于你的确认"并可撤销', async () => {
    const wrapper = await mountPage({ applied_manual_confirmations: ['CSE101'] })
    expect(wrapper.get('[data-testid="makeup-user-confirmed-CSE101"]').text()).toContain(
      DISCLOSURE.basis,
    )
    const before = runCaseADemo.mock.calls.length
    await wrapper.get('[data-testid="makeup-undo-CSE101"]').trigger('click')
    await flushPromises()
    expect(runCaseADemo.mock.calls.length).toBe(before + 1)
  })
})

describe('3. 专业选修交互 + 数据库选修可达', () => {
  it('CSE335 / CSE337 不再被显示上限静默藏掉（可展开/可筛选）', () => {
    const wrapper = mount(CurrentElectiveSection, {
      props: {
        recommendations: ELECTIVES as never,
        load: planResponse().current_load as never,
        applied: [] as never,
        offerings: OFFERINGS as never,
        semester: '2026-1',
      },
    })
    // 默认只显示前 6 门：第 7 门（CSE337）通过明确的展开入口可达
    expect(wrapper.get('[data-testid="elective-expand"]').text()).toContain('查看其余 1 门')
    // 第 4 门（CSE335）默认就可见
    expect(wrapper.find('[data-testid="elective-add-CSE335"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="elective-add-CSE337"]').exists()).toBe(false)
  })

  it('展开后 CSE337 可见可加入', async () => {
    const wrapper = mount(CurrentElectiveSection, {
      props: {
        recommendations: ELECTIVES as never,
        load: planResponse().current_load as never,
        applied: [] as never,
        offerings: OFFERINGS as never,
        semester: '2026-1',
      },
    })
    await wrapper.get('[data-testid="elective-expand"]').trigger('click')
    expect(wrapper.find('[data-testid="elective-add-CSE337"]').exists()).toBe(true)
  })

  it('搜索「数据库」可直接筛出两门数据库课程', async () => {
    const wrapper = mount(CurrentElectiveSection, {
      props: {
        recommendations: ELECTIVES as never,
        load: planResponse().current_load as never,
        applied: [] as never,
        offerings: OFFERINGS as never,
        semester: '2026-1',
      },
    })
    await wrapper.get('[data-testid="elective-search"]').setValue('数据库')
    const cards = wrapper.findAll('[data-testid="case-a-elective-item"]')
    expect(cards).toHaveLength(2)
    expect(cards.map((c) => c.text()).join(' ')).toContain('数据库系统原理')
    expect(cards.map((c) => c.text()).join(' ')).toContain('数据库系统实验')
  })

  it('加入后候选卡变为清晰的已加入 toggle，并触发局部更新', async () => {
    const wrapper = await mountPage()
    runCaseADemo.mockResolvedValueOnce(
      planResponse({
        applied_elective_sections: [
          { course_id: 'CSE317', course_name: '通信原理', class_id: '01', credit: 3 },
        ],
      }),
    )
    await wrapper.get('[data-testid="elective-add-CSE317"]').trigger('click')
    await flushPromises()
    const body = runCaseADemo.mock.calls.at(-1)?.[0] as {
      override?: { electiveSelections: { course_id: string }[] }
    }
    expect(body.override?.electiveSelections?.[0]?.course_id).toBe('CSE317')
    const card = wrapper
      .findAll('[data-testid="case-a-elective-item"]')
      .find((candidate) => candidate.text().includes('CSE317'))
    expect(card).toBeDefined()
    expect(card?.classes()).toContain('elective__item--selected')
    const toggle = wrapper.get('[data-testid="elective-add-CSE317"]')
    expect(toggle.text()).toContain('已加入，可撤销')
    expect(toggle.classes()).toContain('elective__toggle--applied')
    expect(toggle.attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="case-a-elective-notice"]').text()).toContain(
      '已根据你的选修选择',
    )
  })

  it('加入失败时恢复未加入状态并显示失败反馈', async () => {
    const wrapper = await mountPage()
    runCaseADemo.mockRejectedValueOnce(new Error('选修加入失败，请重试。'))

    await wrapper.get('[data-testid="elective-add-CSE317"]').trigger('click')
    await flushPromises()

    const button = wrapper.get('[data-testid="elective-add-CSE317"]')
    expect(button.text()).toBe('加入本学期方案')
    expect(button.classes()).not.toContain('elective__toggle--applied')
    expect(button.attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('[role="alert"]').text()).toContain('选修加入失败，请重试。')
    expect(wrapper.find('[data-testid="elective-applied"]').exists()).toBe(false)
  })
})

describe('4. 局部更新体验', () => {
  it('只显示对应模块的"更新中"，不出现整页 loading 文案', async () => {
    // 让 recompute 挂起，观察 pending 状态
    let release: (v: unknown) => void = () => {}
    runCaseADemo.mockImplementationOnce(async () => planResponse())
    const wrapper = await mountPage()
    runCaseADemo.mockImplementation(
      () => new Promise((resolve) => { release = resolve as (v: unknown) => void }),
    )

    await wrapper.get('[data-testid="makeup-confirm-CSE101"]').trigger('click')
    await flushPromises()
    // 只有补修模块显示更新中
    expect(wrapper.find('[data-testid="case-a-makeup-pending"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-elective-pending"]').exists()).toBe(false)
    // ⛔ 提交按钮被禁用（不乐观更新）
    expect(wrapper.get('[data-testid="makeup-confirm-CSE101"]').attributes('disabled')).toBeDefined()

    release(planResponse())
    await flushPromises()
    expect(wrapper.find('[data-testid="case-a-makeup-pending"]').exists()).toBe(false)
  })
})

describe('6. 课表类别标签：只在有明确证据时标注（render regression）', () => {
  /** 造一个只含指定课程的课表。 */
  function mountSchedule(options: {
    courseId: string
    courseName: string
    meetings?: { weekday: number; start_section: number; end_section: number; weeks: number[] }[]
    makeupTasks?: unknown[]
    electivePoolCourseIds?: string[]
    appliedElectiveCourseIds?: string[]
  }) {
    const offerings = [
      {
        course_id: options.courseId,
        course_name: options.courseName,
        class_id: '01',
        semester: '2026-1',
        credit: 3,
        meetings:
          options.meetings ?? [
            { weekday: 1, start_section: 1, end_section: 2, weeks: [1] },
          ],
        data_source: 'real',
      },
    ]
    return mount(WeeklyScheduleView, {
      props: {
        planResult: {
          status: 'feasible',
          selected_classes: [{ course_id: options.courseId, class_id: '01' }],
          changes: [],
          risks: [],
          unresolved: [],
          objective_summary: null,
        } as never,
        offerings: offerings as never,
        semester: '2026-1',
        currentSchedule: [] as never,
        makeupTasks: (options.makeupTasks ?? []) as never,
        preferredCourses: [] as never,
        electivePoolCourseIds: options.electivePoolCourseIds ?? [],
        appliedElectiveCourseIds: options.appliedElectiveCourseIds ?? [],
      },
    })
  }

  function categoryLabels(wrapper: ReturnType<typeof mount>): string[] {
    return wrapper.findAll('[data-testid="case-a-weekly-category"]').map((n) => n.text())
  }

  it('1) 显式 required ⇒ 必修', () => {
    const wrapper = mountSchedule({
      courseId: 'CSE204',
      courseName: '数据结构',
      makeupTasks: [
        { course_id: 'CSE204', course_name: '数据结构', credit: 3, status: 'required', prerequisites: [] },
      ],
    })
    expect(categoryLabels(wrapper)).toEqual(['必修'])
  })

  it('2) 确知属于专业选修组 ⇒ 专业选修', () => {
    const wrapper = mountSchedule({
      courseId: 'CSE335',
      courseName: '数据库系统原理',
      electivePoolCourseIds: ['CSE335'],
    })
    expect(categoryLabels(wrapper)).toEqual(['专业选修'])
  })

  it('2b) 用户已加入方案的选修（精确身份）⇒ 专业选修', () => {
    const wrapper = mountSchedule({
      courseId: 'CSE337',
      courseName: '数据库系统实验',
      appliedElectiveCourseIds: ['CSE337'],
    })
    expect(categoryLabels(wrapper)).toEqual(['专业选修'])
  })

  it('3) ⛔ manual_confirmation 的课程不得被标成专业选修', () => {
    // 这正是 Codex 指出的 blocker：status !== required 曾被反推成"专业选修"
    const wrapper = mountSchedule({
      courseId: 'CSE201',
      courseName: '程序设计II',
      makeupTasks: [
        {
          course_id: 'CSE201',
          course_name: '程序设计II',
          credit: 3,
          status: 'manual_confirmation',
          prerequisites: [],
        },
      ],
    })
    expect(categoryLabels(wrapper)).toEqual([])
    expect(wrapper.text()).not.toContain('专业选修')
  })

  it('3b) ⛔ possibly_equivalent / satisfied 同样不得被标成专业选修', () => {
    for (const status of ['possibly_equivalent', 'satisfied']) {
      const wrapper = mountSchedule({
        courseId: 'CSE202',
        courseName: '示例课程',
        makeupTasks: [
          { course_id: 'CSE202', course_name: '示例课程', credit: 3, status, prerequisites: [] },
        ],
      })
      expect(categoryLabels(wrapper), status).toEqual([])
    }
  })

  it('4) 未分类课程 ⇒ 不显示任何业务类别标签', () => {
    const wrapper = mountSchedule({
      courseId: 'UNCLASSIFIED-1',
      courseName: '未分类课程',
    })
    expect(categoryLabels(wrapper)).toEqual([])
  })

  it('5) 图例只列**实际出现**的类别（无必修时不提必修）', () => {
    const electiveOnly = mountSchedule({
      courseId: 'CSE335',
      courseName: '数据库系统原理',
      electivePoolCourseIds: ['CSE335'],
    })
    const legend = electiveOnly.get('[data-testid="case-a-weekly-legend"]').text()
    expect(legend).toContain('专业选修')
    expect(legend).not.toContain('必修')

    const requiredOnly = mountSchedule({
      courseId: 'CSE204',
      courseName: '数据结构',
      makeupTasks: [
        { course_id: 'CSE204', course_name: '数据结构', credit: 3, status: 'required', prerequisites: [] },
      ],
    })
    const legend2 = requiredOnly.get('[data-testid="case-a-weekly-legend"]').text()
    expect(legend2).toContain('必修')
    expect(legend2).not.toContain('专业选修')
  })

  it('5b) 没有任何类别的证据 ⇒ 完全不渲染图例', () => {
    const wrapper = mountSchedule({ courseId: 'UNCLASSIFIED-1', courseName: '未分类课程' })
    expect(wrapper.find('[data-testid="case-a-weekly-legend"]').exists()).toBe(false)
  })

  it('⛔ 不猜公选 / 跨专业 / 实验', () => {
    const wrapper = mountSchedule({
      courseId: 'CSE103',
      courseName: '程序设计I实验',
      makeupTasks: [
        { course_id: 'CSE103', course_name: '程序设计I实验', credit: 1, status: 'manual_confirmation', prerequisites: [] },
      ],
    })
    const text = wrapper.text()
    for (const guessed of ['公选', '公共选修', '跨专业']) {
      expect(text, guessed).not.toContain(guessed)
    }
    // 课程名里含"实验"，但⛔ 不因此产出"实验"类别标签
    expect(categoryLabels(wrapper)).toEqual([])
  })
})
