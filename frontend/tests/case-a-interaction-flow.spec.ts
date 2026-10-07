/**
 * 最终交互轮 —— **有状态端到端**流程测试。
 *
 * 与其它 spec 的区别：这里 mock 的 `runCaseADemo` 会**累积**每次提交的覆盖意图，
 * 并像真实后端一样把确认项从"待人工确认"移到"已满足"、把选修计入学分。
 * 因此它可以验证**跨交互**的正确性：
 *
 * ```
 * 提交 → 确认补修 → 重算 → 再确认一门 → 加入选修 → 撤销确认 → 撤销选修
 * ```
 *
 * ⚠️ 关键点：所有下游数字都必须来自"服务端"（这里即 mock 的 recompute），
 *    ⛔ 前端不得自己算。若前端偷改状态，本测试会立刻发现不一致。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'

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
  ['CSE317', '通信原理', '01', 3, 3],
  ['CSE204', '数据结构', '01', 3, 5],
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
  meetings: [
    {
      weekday,
      start_section: 1,
      end_section: 2,
      weeks: [1],
      campus: '南校园',
      classroom: 'A101',
    },
  ],
  data_source: 'real',
})) as never as Record<string, unknown>[]

/** 参与者（manual_confirmation）与已满足项。 */
const PARTICIPANTS = [
  { course_id: 'CSE101', course_name: '程序设计I', credit: 3 },
  { course_id: 'CSE103', course_name: '程序设计I实验', credit: 1 },
]
const SATISFIED = [{ course_id: 'MAR103', course_name: '中国近现代史纲要', credit: 3 }]

/**
 * 有状态的后端替身：记录确认集合与已加入选修，并按真实语义重算。
 *
 * ⚠️ 这里**故意**让它成为唯一的事实来源：前端若自己算学分就会与它不一致。
 */
function makeServer() {
  const confirmed = new Set<string>()
  const electives = new Set<string>() // course_id
  const state = { lastRequestBody: null as Record<string, unknown> | null }

  function respond() {
    const makeup_tasks = [
      ...SATISFIED.map((c) => ({
        course_id: c.course_id,
        course_name: c.course_name,
        credit: c.credit,
        status: 'satisfied',
        recommended_semester: null,
        deadline_semester: null,
        prerequisites: [],
        reason: '已确认满足。',
        source_evidence: null,
      })),
      ...PARTICIPANTS.map((c) => ({
        course_id: c.course_id,
        course_name: c.course_name,
        credit: c.credit,
        status: 'manual_confirmation',
        recommended_semester: 3,
        deadline_semester: 5,
        prerequisites: [],
        reason: '仍有课程号待确认的已修记录。',
        source_evidence: null,
      })),
    ]

    const effective_makeup_tasks = makeup_tasks.map((t) =>
      confirmed.has(t.course_id)
        ? {
            ...t,
            status: 'satisfied',
            reason: `${t.reason}｜${DISCLOSURE.basis}，${DISCLOSURE.scope}；${DISCLOSURE.authority}`,
          }
        : t,
    )

    const applied_elective_sections = [...electives].map((course_id) => {
      const off = OFFERINGS.find((o) => o.course_id === course_id)!
      return {
        course_id,
        course_name: off.course_name,
        class_id: off.class_id,
        credit: off.credit,
      }
    })
    const electiveCredit = applied_elective_sections.reduce(
      (sum, s) => sum + Number(s.credit),
      0,
    )

    const all = [
      {
        course_id: 'CSE317',
        course_name: '通信原理',
        credit: 3,
        available_class_count: 1,
        conflicting_class_count: 0,
        unknown_schedule_class_count: 0,
        clear_class_count: 1,
        unique_clear_class_id: '01',
        conflict_label: '已找到与当前课表不冲突的教学班',
      },
      {
        course_id: 'CSE321',
        course_name: '计算复杂性理论',
        credit: 3,
        available_class_count: 1,
        conflicting_class_count: 0,
        unknown_schedule_class_count: 0,
        clear_class_count: 1,
        unique_clear_class_id: '01',
        conflict_label: '已找到与当前课表不冲突的教学班',
      },
    ]

    return {
      transcript: {
        source_id: 's',
        artifact_sha256: 'a'.repeat(64),
        record_count: 5,
        term_count: 1,
        terms: [],
        pending_course_id_count: 5,
      },
      makeup_tasks,
      course_offerings: OFFERINGS,
      preference: {
        max_credit: null,
        avoid_cross_campus: false,
        preferred_courses: [],
        avoid_times: [],
      },
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [
          { course_id: 'CSE201', class_id: '01' },
          ...applied_elective_sections.map((s) => ({
            course_id: s.course_id,
            class_id: s.class_id,
          })),
        ],
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
          current_semester_credit: electiveCredit,
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
      // 已加入的课程不再作为候选出现
      current_elective_recommendations: all.filter((c) => !electives.has(c.course_id)),
      current_load: {
        selected_credit: 0,
        suggested_makeup_credit: 0,
        suggested_elective_credit: 0,
        projected_total_credit: electiveCredit,
        max_credit: 30,
        exceeds_max: false,
        policy_note: '产品默认上限。',
      },
      applied_manual_confirmations: [...confirmed].sort(),
      rejected_manual_confirmations: [],
      applied_elective_sections,
      rejected_elective_selections: [],
      effective_makeup_tasks,
      planning_only_disclosure: DISCLOSURE,
      provenance: {
        transcript: 't',
        curriculum: 'c',
        course_data: 'case-scoped:south+shenzhen',
        current_schedule: 'selected accepted offering',
        planner: 'actual RestrictedPlanner execution',
        is_full_semester: false,
      },
    }
  }

  return {
    state,
    confirmed,
    electives,
    handler: async (input: {
      override?: { userConfirmedManualTaskKeys: string[]; electiveSelections: { course_id: string }[] }
    }) => {
      // 像真实后端一样：**整体**采用请求里的意图（不是增量打补丁）
      confirmed.clear()
      for (const key of input.override?.userConfirmedManualTaskKeys ?? []) confirmed.add(key)
      electives.clear()
      for (const item of input.override?.electiveSelections ?? []) electives.add(item.course_id)
      state.lastRequestBody = input as unknown as Record<string, unknown>
      return respond()
    },
  }
}

async function mountPage() {
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

describe('端到端交互流程（有状态后端替身）', () => {
  it('确认 → 再加入选修 → 撤销确认 → 撤销选修，全程状态自洽', async () => {
    const server = makeServer()
    runCaseADemo.mockImplementation(server.handler)

    const wrapper = await mountPage()

    // ---- 初始：3 项待确认（2 参与 + 0），已满足 1 项 ----
    expect(wrapper.get('[data-testid="makeup-filter-manual"]').text()).toContain('2')
    expect(wrapper.get('[data-testid="makeup-filter-satisfied"]').text()).toContain('1')
    expect(wrapper.get('[data-testid="case-a-credit-load"]').text()).toContain('预计合计 0 学分')

    // ---- ① 确认 CSE101 ----
    await wrapper.get('[data-testid="makeup-select-CSE101"]').setValue(true)
    await wrapper.get('[data-testid="makeup-confirm-submit"]').trigger('click')
    await flushPromises()

    expect([...server.confirmed]).toEqual(['CSE101'])
    // 用户视角：该行已满足 + 带"基于你的确认"
    expect(wrapper.get('[data-testid="makeup-row-CSE101"]').text()).toContain('已满足')
    expect(wrapper.find('[data-testid="makeup-user-confirmed-CSE101"]').exists()).toBe(true)
    // 计数随之变化（待确认 2 → 1，已满足 1 → 2）
    expect(wrapper.get('[data-testid="makeup-filter-manual"]').text()).toContain('1')
    expect(wrapper.get('[data-testid="makeup-filter-satisfied"]').text()).toContain('2')
    // ⛔ 来源评估未被改写（仍 2 项 manual_confirmation）
    expect(
      (server.state.lastRequestBody as never as { override: { userConfirmedManualTaskKeys: string[] } })
        .override.userConfirmedManualTaskKeys,
    ).toEqual(['CSE101'])

    // ---- ② 加入选修 CSE317 ----
    await wrapper.get('[data-testid="elective-add-CSE317"]').trigger('click')
    await flushPromises()
    expect([...server.electives]).toEqual(['CSE317'])
    expect(wrapper.get('[data-testid="elective-applied"]').text()).toContain('通信原理')
    expect(wrapper.get('[data-testid="case-a-credit-load"]').text()).toContain('已加入选修 3 学分')
    expect(wrapper.get('[data-testid="case-a-credit-load"]').text()).toContain('预计合计 3 学分')
    // 已加入的课程不再作为候选出现
    expect(wrapper.find('[data-testid="elective-add-CSE317"]').exists()).toBe(false)
    // 课表图例如实区分来源
    const legend = wrapper.get('[data-testid="case-a-schedule-legend"]').text()
    expect(legend).toContain('当前已选')
    expect(legend).toContain('你加入方案的选修：1 门')

    // ---- ③ 再确认一门（累积意图，不是覆盖） ----
    await wrapper.get('[data-testid="makeup-select-CSE103"]').setValue(true)
    await wrapper.get('[data-testid="makeup-confirm-submit"]').trigger('click')
    await flushPromises()
    expect([...server.confirmed].sort()).toEqual(['CSE101', 'CSE103'])
    // 计数为 0 的"待人工确认"筛选消失
    expect(wrapper.find('[data-testid="makeup-filter-manual"]').exists()).toBe(false)
    // 选修仍在
    expect(wrapper.get('[data-testid="case-a-credit-load"]').text()).toContain('预计合计 3 学分')

    // ---- ④ 撤销 CSE101 的确认 ----
    await wrapper.get('[data-testid="makeup-undo-CSE101"]').trigger('click')
    await flushPromises()
    expect([...server.confirmed]).toEqual(['CSE103'])
    expect(wrapper.find('[data-testid="makeup-user-confirmed-CSE101"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="makeup-filter-manual"]').text()).toContain('1')

    // ---- ⑤ 撤销选修 ----
    await wrapper.get('[data-testid="elective-remove-CSE317"]').trigger('click')
    await flushPromises()
    expect(server.electives.size).toBe(0)
    expect(wrapper.find('[data-testid="elective-applied"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="case-a-credit-load"]').text()).toContain('预计合计 0 学分')
    // 撤销后重新可加入
    expect(wrapper.find('[data-testid="elective-add-CSE317"]').exists()).toBe(true)

    // ---- 全程：没有任何独立待处理区块，也没有机器码泄漏 ----
    expect(wrapper.find('[data-testid="case-a-pending-center"]').exists()).toBe(false)
    const primary = (() => {
      const host = document.createElement('div')
      host.innerHTML = wrapper.html().replace(/<details[\s\S]*?<\/details>/gi, '')
      return host.textContent ?? ''
    })()
    expect(primary).not.toContain('manual_confirmation')
    expect(primary).not.toContain('no_alternatives')
    expect(primary).not.toContain('type:')
  })

  it('每次交互都只调用一次 recompute（⛔ 无重复请求）', async () => {
    const server = makeServer()
    runCaseADemo.mockImplementation(server.handler)
    const wrapper = await mountPage()
    const afterInitial = runCaseADemo.mock.calls.length

    await wrapper.get('[data-testid="makeup-select-CSE101"]').setValue(true)
    await wrapper.get('[data-testid="makeup-confirm-submit"]').trigger('click')
    await flushPromises()
    expect(runCaseADemo.mock.calls.length).toBe(afterInitial + 1)

    await wrapper.get('[data-testid="elective-add-CSE317"]').trigger('click')
    await flushPromises()
    expect(runCaseADemo.mock.calls.length).toBe(afterInitial + 2)
  })

  it('recompute 失败时如实报错，⛔ 不假装成功', async () => {
    const server = makeServer()
    runCaseADemo.mockImplementation(server.handler)
    const wrapper = await mountPage()

    runCaseADemo.mockRejectedValue(new Error('Case A demo request failed (HTTP 500).'))
    await wrapper.get('[data-testid="makeup-select-CSE101"]').setValue(true)
    await wrapper.get('[data-testid="makeup-confirm-submit"]').trigger('click')
    await flushPromises()

    // 该行**没有**被本地改写成"已满足"（⛔ 无乐观更新）
    expect(wrapper.find('[data-testid="makeup-user-confirmed-CSE101"]').exists()).toBe(false)
    // 并且给出可见错误
    expect(wrapper.text()).toContain('500')
  })
})
