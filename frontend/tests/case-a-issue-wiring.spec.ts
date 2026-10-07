/**
 * 本轮（FOCUSED UI WIRING FIX）的**真实渲染**回归测试。
 *
 * ⚠️ 为什么必须 mount 真实组件：上一轮的缺陷正是
 * "utility 的单元测试全绿，但该模块没有任何生产 importer"。
 * 因此这里每个用例都 mount 真实组件（或真实页面），断言**用户实际看到的内容**。
 *
 * 对应独立 Review 要求的 Test A–G。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import FutureRoadmapView from '@/components/FutureRoadmapView.vue'
import PendingAdjustments from '@/components/PendingAdjustments.vue'
import PendingIssuesCenter from '@/components/PendingIssuesCenter.vue'
import PlanResultPanel from '@/components/PlanResultPanel.vue'
import type { NormalizedIssue } from '@/utils/studentIssues'
import { normalizedIssues } from '@/utils/studentIssues'

const loadCaseAOfferings = vi.fn()
const runCaseADemo = vi.fn()
const applyCaseARepair = vi.fn()

vi.mock('@/api/caseADemo', () => ({
  loadCaseAOfferings: (...args: unknown[]) => loadCaseAOfferings(...args),
  runCaseADemo: (...args: unknown[]) => runCaseADemo(...args),
  applyCaseARepair: (...args: unknown[]) => applyCaseARepair(...args),
}))

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
      { weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2, 3], campus: '南校园', classroom: 'A101' },
    ],
    data_source: 'real',
  },
]

function planResponse(overrides: Record<string, unknown> = {}) {
  return {
    transcript: {
      source_id: 's',
      artifact_sha256: 'a'.repeat(64),
      record_count: 2,
      term_count: 1,
      terms: ['2025-2026学年第一学期'],
      pending_course_id_count: 2,
    },
    makeup_tasks: [],
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
    roadmap: null,
    roadmap_note: null,
    completed_binding: 'not_bound',
    completed_binding_note: '上传的成绩单未参与认定。',
    current_elective_recommendations: [],
    current_load: {
      selected_credit: 0,
      suggested_makeup_credit: 0,
      suggested_elective_credit: 0,
      projected_total_credit: 0,
      max_credit: 30,
      exceeds_max: false,
      policy_note: '产品默认上限。',
    },
    provenance: {
      transcript: 'user-uploaded SYSU transcript PDF',
      curriculum: 'Case A target curriculum',
      course_data: 'case-scoped:south+shenzhen',
      current_schedule: 'selected accepted offering',
      planner: 'actual RestrictedPlanner execution',
      is_full_semester: false,
    },
    ...overrides,
  }
}

/** 从真实页面里取出「需要你处理」主区域的全部文本。 */
function pendingCenterText(wrapper: ReturnType<typeof mount>): string {
  const center = wrapper.find('[data-testid="case-a-pending-center"]')
  return center.exists() ? center.text() : ''
}

/**
 * 主界面文本 = 去掉所有**折叠的技术详情**之后的页面文本。
 *
 * ⚠️ 为什么要这样取：raw 机器码是**允许**保留在「查看技术详情」里的
 * （产品要求：技术详情可含 raw type / backend message）。
 * `wrapper.text()` 会连同折叠区一起抓取，因此不能直接拿它断言"不含机器码"。
 */
function primaryText(wrapper: ReturnType<typeof mount>): string {
  const html = wrapper.html()
  const body = html.replace(/<details[\s\S]*?<\/details>/gi, '')
  const host = document.createElement('div')
  host.innerHTML = body
  return host.textContent ?? ''
}

async function mountPageWith(overrides: Record<string, unknown> = {}) {
  runCaseADemo.mockResolvedValue(planResponse(overrides))
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

/**
 * ⚠️ mock 必须在**顶层**重置：`CaseADemoView` 挂载时会立刻加载教学班，
 * 若某个 describe 忘了设置 `loadCaseAOfferings`，渲染期会因
 * `offerings.length` 读到 undefined 而抛错，表现为"卡片数为 0"这种误导性失败。
 */
beforeEach(() => {
  loadCaseAOfferings.mockReset()
  runCaseADemo.mockReset()
  applyCaseARepair.mockReset()
  loadCaseAOfferings.mockResolvedValue(OFFERINGS)
})

describe('Test A/B — 机器码不得出现在真实渲染的主界面', () => {
  it('Test A: schedule_unknown 渲染为中文，主界面不含机器码', async () => {
    const wrapper = await mountPageWith({
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
        changes: [],
        risks: [],
        unresolved: [{ type: 'schedule_unknown', message: '排课信息缺失' }],
        objective_summary: null,
      },
    })

    const center = pendingCenterText(wrapper)
    const centerPrimary = primaryText(wrapper.find('[data-testid="case-a-pending-center"]'))
    expect(center).toContain('排课信息')
    // 主界面（不含折叠的技术详情）不得出现机器码
    expect(centerPrimary).not.toContain('schedule_unknown')

    // 页面整体主界面同样不得出现机器码或 `type:` 前缀
    const whole = primaryText(wrapper)
    expect(whole).not.toContain('schedule_unknown')
    expect(whole).not.toContain('type:')
  })

  it('Test B: 未知机器码渲染为中性中文，展开技术详情后才可见原始取值', async () => {
    const wrapper = await mountPageWith({
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
        changes: [],
        risks: [],
        unresolved: [{ type: 'some_new_internal_state', message: '' }],
        objective_summary: null,
      },
    })

    // 主界面：中性中文兜底，⛔ 不回显 raw code
    expect(pendingCenterText(wrapper)).toContain('该事项需要进一步确认')
    expect(primaryText(wrapper)).not.toContain('some_new_internal_state')

    // 技术详情（折叠区内）保留原始取值，供排查
    const tech = wrapper.get('[data-testid="case-a-issue-tech"]')
    expect(tech.text()).toContain('some_new_internal_state')
  })
})

describe('Test C/D — 去重：跨来源合并，但不同教学班必须保留', () => {
  it('Test C: 同一事项同时来自 plan 与 roadmap，主界面只显示一次', async () => {
    const wrapper = await mountPageWith({
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [{ type: 'schedule_unknown', message: '课程 CSE204 排课信息缺失' }],
        objective_summary: null,
      },
      roadmap: {
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
        // 与 plan.unresolved 是**同一件事**（同一课程 + 同一类问题）
        unresolved: ['课程 CSE204 的排课信息缺失（schedule_unknown）'],
        warnings: [],
      },
    })

    const cards = wrapper.findAll('[data-testid="case-a-issue"]')
    const sameCourse = cards.filter((card) => card.text().includes('CSE204'))
    expect(sameCourse).toHaveLength(1)
  })

  it('Test D: 同课程不同教学班 → 显示两条', async () => {
    const wrapper = mount(PendingIssuesCenter, {
      props: {
        issues: normalizedIssues({
          repairUnresolved: [
            '课程 PUB178 的当前教学班 202616253 状态为 CONFLICT，没有可确认无冲突的同课程候选（no_alternatives）。',
            '课程 PUB178 的当前教学班 202616999 状态为 CONFLICT，没有可确认无冲突的同课程候选（no_alternatives）。',
          ],
          courseNameById: { PUB178: '劳动教育' },
        }),
      },
    })

    const cards = wrapper.findAll('[data-testid="case-a-issue"]')
    expect(cards).toHaveLength(2)
    expect(cards[0].text()).toContain('202616253')
    expect(cards[1].text()).toContain('202616999')
  })
})

describe('Test E/F — 旧 raw 渲染路径已删除', () => {
  it('Test E: PlanResultPanel 不再输出 raw unresolved 明细', () => {
    const wrapper = mount(PlanResultPanel, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [],
          changes: [],
          risks: [],
          unresolved: [
            { type: 'schedule_unknown', message: '排课信息缺失' },
            { type: 'manual_confirmation', message: '需要人工确认' },
          ],
          objective_summary: null,
        } as never,
        courseNameById: {},
      },
    })

    const text = wrapper.text()
    expect(text).not.toContain('type:')
    expect(text).not.toContain('schedule_unknown')
    expect(text).not.toContain('manual_confirmation')
    // 但仍如实告知还有待确认事项，并指向统一区域
    expect(text).toContain('需要你处理')
    expect(text).toContain('2')
  })

  it('Test F: FutureRoadmapView 默认不出现 raw token（no_alternatives / recommended_semester）', () => {
    const wrapper = mount(FutureRoadmapView, {
      props: {
        roadmap: {
          current_semester: '2026-1',
          current_semester_planned_course_ids: [],
          future_semesters: [
            {
              semester_label: '2026-2',
              curriculum_semester: 4,
              semester_index: 1,
              courses: [],
              required_credit: 0,
              elective_credit: 0,
              total_credit: 0,
              warnings: [],
            },
          ],
          elective: {
            requirement_credit: 23,
            completed_credit: 0,
            current_semester_credit: 0,
            planned_credit: 23,
            remaining_credit: 0,
            gap_credit: 23,
            group_id: 'CSE-ELECTIVE-POOL',
          },
          unresolved: [
            '课程 MAR108 的 recommended_semester=4 不在本次提供的学期映射中（no_alternatives）',
          ],
          warnings: [],
        } as never,
      },
    })

    const visible = wrapper.get('[data-testid="case-a-roadmap-unresolved-item"]').text()
    // 主文案：中文，且不含未登记机器码
    expect(visible).toContain('培养方案建议学期')
    expect(visible).not.toContain('no_alternatives')
    expect(visible).not.toContain('recommended_semester')

    // raw 原文只保留在折叠的技术详情里
    expect(wrapper.get('[data-testid="case-a-roadmap-tech"]').text()).toContain('no_alternatives')
  })
})

describe('Test G — 只有一个待确认主区域', () => {
  it('Test G: 真实页面上待确认事项只在一个主区域呈现，且不重复', async () => {
    const wrapper = await mountPageWith({
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
        changes: [],
        risks: [],
        unresolved: [
          { type: 'schedule_unknown', message: '课程 CSE204 排课信息缺失' },
          { type: 'manual_confirmation', message: '课程 MAR108 需要人工确认' },
        ],
        objective_summary: null,
      },
      repair_proposals: {
        semester: '2026-1',
        proposals: [],
        unresolved: ['课程 CSE204 的排课信息缺失（schedule_unknown）'],
      },
    })

    // ① 只有一个「需要你处理」容器
    const centers = wrapper.findAll('[data-testid="case-a-pending-center"]')
    expect(centers).toHaveLength(1)

    // ② 同一门课的同一类问题只出现一次
    const cards = wrapper.findAll('[data-testid="case-a-issue"]')
    const cse204 = cards.filter((card) => card.text().includes('CSE204'))
    expect(cse204).toHaveLength(1)

    // ③ PlanResultPanel 不再重复渲染 unresolved 明细
    expect(wrapper.find('[data-testid="plan-result-unresolved-delegated"]').exists()).toBe(true)

    // ④ 主界面（不含折叠技术详情）不出现机器码
    const whole = primaryText(wrapper)
    expect(whole).not.toContain('schedule_unknown')
    expect(whole).not.toContain('manual_confirmation')
    expect(whole).not.toContain('type:')

    // ⑤ 可执行换班仍然可用（本页无候选 ⇒ 中性空状态，但按钮策略说明仍在）
    expect(wrapper.find('[data-testid="case-a-pending-adjustments"]').exists()).toBe(true)
  })

  it('无待确认事项时给出中性空状态，不编造内容', async () => {
    const wrapper = await mountPageWith({})
    expect(wrapper.find('[data-testid="case-a-issues-empty"]').exists()).toBe(true)
    expect(pendingCenterText(wrapper)).toContain('没有需要你处理的事项')
  })
})

describe('可执行换班仍然可点（未因去重被削弱）', () => {
  it('有 CLEAR 候选时渲染「采用调整」，且必须显式点击才 emit', async () => {
    const wrapper = mount(PendingAdjustments, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [],
          changes: [],
          risks: [],
          unresolved: [],
        } as never,
        repairProposals: {
          semester: '2026-1',
          proposals: [
            {
              proposal_id: 'p1',
              semester: '2026-1',
              course_id: 'CSE201',
              current_class_id: '01',
              candidate_class_id: '02',
              original_state: 'CONFLICT',
              candidate_state: 'CLEAR',
              reason: '候选教学班与当前课表不冲突。',
            },
          ],
          unresolved: [],
        } as never,
        courseNameById: { CSE201: 'Python 程序设计' },
        offerings: OFFERINGS as never,
      },
    })

    expect(wrapper.get('[data-testid="case-a-repair-course"]').text()).toContain('Python 程序设计')
    // 渲染本身绝不 apply
    expect(wrapper.emitted('apply')).toBeUndefined()
    await wrapper.get('[data-testid="case-a-repair-apply-CSE201-02"]').trigger('click')
    expect(wrapper.emitted('apply')).toHaveLength(1)
  })

  it('只有 UNKNOWN 候选时不渲染可点击卡片（不是可执行动作）', () => {
    const wrapper = mount(PendingAdjustments, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [],
          changes: [],
          risks: [],
          unresolved: [],
        } as never,
        repairProposals: {
          semester: '2026-1',
          proposals: [
            {
              proposal_id: 'p1',
              semester: '2026-1',
              course_id: 'CSE201',
              current_class_id: '01',
              candidate_class_id: '02',
              original_state: 'CONFLICT',
              candidate_state: 'UNKNOWN',
              reason: '排课信息待核验。',
            },
          ],
          unresolved: [],
        } as never,
        courseNameById: { CSE201: 'Python 程序设计' },
        offerings: [] as never,
      },
    })

    expect(wrapper.find('[data-testid="case-a-repair-course"]').exists()).toBe(false)
    expect(wrapper.findAll('button').filter((b) => b.text().includes('采用调整'))).toHaveLength(0)
    // ⛔ 也不在此重复渲染成清单
    expect(wrapper.find('[data-testid="case-a-repair-blockers-summary"]').exists()).toBe(false)
  })
})

describe('渐进披露与折叠', () => {
  const many: NormalizedIssue[] = Array.from({ length: 7 }, (_, i) => ({
    id: `schedule_unknown::C${i}::${i}::排课信息暂不完整，需要进一步确认`,
    kind: 'schedule_unknown' as const,
    title: `示例课程 ${i}`,
    detail: `C${i}`,
    message: '排课信息暂不完整，需要进一步确认',
    rawCode: 'schedule_unknown',
    rawMessage: `课程 C${i} 排课信息缺失`,
    sourceEvidence: [],
    actionable: false,
    courseId: `C${i}`,
    classId: null,
  }))

  it('每个分组默认最多 3 条，其余可展开', async () => {
    const wrapper = mount(PendingIssuesCenter, { props: { issues: many } })
    expect(wrapper.findAll('[data-testid="case-a-issue"]')).toHaveLength(3)
    const expand = wrapper.get('[data-testid="case-a-issues-expand-incompleteData"]')
    expect(expand.text()).toContain('查看其余 4 项')
    await expand.trigger('click')
    expect(wrapper.findAll('[data-testid="case-a-issue"]')).toHaveLength(7)
  })

  it('技术详情默认折叠（details 未 open）', () => {
    const wrapper = mount(PendingIssuesCenter, { props: { issues: many.slice(0, 1) } })
    const details = wrapper.get('[data-testid="case-a-issue-tech"]').element.closest('details')
    expect(details?.hasAttribute('open')).toBe(false)
  })
})
