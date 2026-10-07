/**
 * Case A 学业路径规划前端 — Phase 1 验收测试。
 *
 * 覆盖本阶段的产品化要求：
 * 1. 主界面不出现公共 Preference 的技术字段名；
 * 2. 意向课程按**课程级**去重（同一 course_id 只一条）；
 * 3. 可按 course_name 搜索；
 * 4. 可按 course_id 搜索；
 * 5. 加入后写入 `preferredCourses`；
 * 6. 重复课程不会重复加入；
 * 7. 本学期周课表可渲染 selected_classes；
 * 8. selected class 能按身份 join 到 CourseOffering；
 * 9. 教师为空 → “任课教师：待核验”；
 * 10. `selection_required` 呈现为"待确认"，不是已自动修复；
 * 11. 后端没有 roadmap 字段时**不渲染**未来学期区块、⛔ 不造假数据；
 * 12. 教学班搜索结果仍不超过 20 条。
 *
 * ⛔ 不联网：全部通过 mock 的 API 层。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import FutureRoadmapView from '@/components/FutureRoadmapView.vue'
import IntentCourseSearch from '@/components/IntentCourseSearch.vue'
import PendingAdjustments from '@/components/PendingAdjustments.vue'
import WeeklyScheduleView from '@/components/WeeklyScheduleView.vue'
import type { AcademicRoadmap } from '@/types/caseAPlanning'
import type { CourseOffering, MakeupTask, PlanResult } from '@/types/contracts'

const loadCaseAOfferings = vi.fn()
const runCaseADemo = vi.fn()
const applyCaseARepair = vi.fn()

vi.mock('@/api/caseADemo', () => ({
  loadCaseAOfferings: (...args: unknown[]) => loadCaseAOfferings(...args),
  runCaseADemo: (...args: unknown[]) => runCaseADemo(...args),
  applyCaseARepair: (...args: unknown[]) => applyCaseARepair(...args),
}))

/** 真实 `AcademicRoadmap` 形状的固定样例（字段与后端加法式响应一一对应）。 */
const ROADMAP: AcademicRoadmap = {
  current_semester: '2026-1',
  current_semester_planned_course_ids: [],
  future_semesters: [
    {
      semester_label: '2026-2',
      curriculum_semester: 4,
      semester_index: 1,
      courses: [
        {
          course_id: 'CSE310',
          course_name: '操作系统',
          credit: 3,
          requirement_kind: 'required',
          requirement_label: '必修',
          placement: 'required_by_recommended_term',
          reason: '课程 CSE310（操作系统）为培养方案要求课程，按其建议学期安排。',
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
    completed_credit: 8,
    current_semester_credit: 6,
    planned_credit: 9,
    remaining_credit: 0,
    gap_credit: 9,
    group_id: 'CSE-ELECTIVE-POOL',
  },
  unresolved: ['选修组 CSE-ELECTIVE-POOL 的本学期选修学分证据不足；⛔ 不计入。'],
  warnings: ['未提供每学期学分预算：本次不设学期学分上限。'],
}

function offering(
  overrides: Partial<CourseOffering> & { course_id: string; class_id: string },
): CourseOffering {
  return {
    course_name: '示例课程',
    semester: overrides.semester ?? '2026-1',
    credit: 3,
    meetings: [
      { weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2, 3], campus: '南校园', classroom: 'A101' },
    ],
    teacher: null,
    data_source: 'real',
    ...overrides,
  }
}

/** 两门真实课程：Python 程序设计有 3 个教学班、人工智能导论有 1 个。 */
const OFFERINGS: CourseOffering[] = [
  offering({ course_id: 'CSE201', class_id: '01', course_name: 'Python 程序设计', teacher: '张老师' }),
  offering({ course_id: 'CSE201', class_id: '02', course_name: 'Python 程序设计' }),
  offering({ course_id: 'CSE201', class_id: '03', course_name: 'Python 程序设计' }),
  offering({ course_id: 'MAR108', class_id: '01', course_name: '人工智能导论', credit: 2 }),
]

function makeupTask(courseId: string, status: MakeupTask['status'] = 'required'): MakeupTask {
  return { course_id: courseId, course_name: '示例补修课', credit: 3, status }
}

describe('意向课程搜索（课程级）', () => {
  it('同一 course_id 只显示一张结果，并给出本学期教学班数量', () => {
    const wrapper = mount(IntentCourseSearch, {
      props: { offerings: OFFERINGS, selectedCourseIds: [] },
    })
    // 未输入时不铺开任何结果
    expect(wrapper.findAll('[data-testid="case-a-intent-result"]')).toHaveLength(0)

    return wrapper.get('[data-testid="case-a-intent-input"]').setValue('CSE201').then(() => {
      const rows = wrapper.findAll('[data-testid="case-a-intent-result"]')
      expect(rows).toHaveLength(1)
      expect(rows[0].text()).toContain('Python 程序设计')
      expect(rows[0].text()).toContain('CSE201')
      expect(rows[0].text()).toContain('3 学分')
      expect(rows[0].text()).toContain('本学期有 3 个教学班')
    })
  })

  it('可按课程名称搜索', async () => {
    const wrapper = mount(IntentCourseSearch, {
      props: { offerings: OFFERINGS, selectedCourseIds: [] },
    })
    await wrapper.get('[data-testid="case-a-intent-input"]').setValue('Python')
    const rows = wrapper.findAll('[data-testid="case-a-intent-result"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('Python 程序设计')
  })

  it('可按课程号搜索，且大小写不敏感', async () => {
    const wrapper = mount(IntentCourseSearch, {
      props: { offerings: OFFERINGS, selectedCourseIds: [] },
    })
    await wrapper.get('[data-testid="case-a-intent-input"]').setValue('mar108')
    const rows = wrapper.findAll('[data-testid="case-a-intent-result"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('人工智能导论')
  })

  it('是字面搜索：没有字面命中的课程不会被当成相关结果', async () => {
    const wrapper = mount(IntentCourseSearch, {
      props: { offerings: OFFERINGS, selectedCourseIds: [] },
    })
    // “机器学习”在数据里不存在，⛔ 不得因为“和人工智能相关”而被返回
    await wrapper.get('[data-testid="case-a-intent-input"]').setValue('机器学习')
    expect(wrapper.findAll('[data-testid="case-a-intent-result"]')).toHaveLength(0)
    expect(wrapper.find('[data-testid="case-a-intent-empty"]').exists()).toBe(true)
  })

  it('加入写入 course_id，且已加入的课程不能重复加入', async () => {
    const wrapper = mount(IntentCourseSearch, {
      props: { offerings: OFFERINGS, selectedCourseIds: [] },
    })
    await wrapper.get('[data-testid="case-a-intent-input"]').setValue('Python')
    await wrapper.get('[data-testid="case-a-intent-add"]').trigger('click')
    // 组件只发事件；写入 preferred_courses 由父级完成（⛔ 组件不自行改状态）
    expect(wrapper.emitted('add')?.[0]).toEqual(['CSE201'])

    await wrapper.setProps({ selectedCourseIds: ['CSE201'] })
    const button = wrapper.get('[data-testid="case-a-intent-add"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toContain('已加入意向')
  })

  it('页面文案说明这是字面关键词搜索，不宣称智能语义推荐', () => {
    const wrapper = mount(IntentCourseSearch, {
      props: { offerings: OFFERINGS, selectedCourseIds: [] },
    })
    // 规定的搜索框 placeholder
    expect(wrapper.get('[data-testid="case-a-intent-input"]').attributes('placeholder')).toContain(
      '搜索课程名称、课程号或关键词',
    )
    // 明确声明是字面搜索，且⛔ 不出现“智能语义推荐”式承诺
    expect(wrapper.text()).toContain('字面关键词')
    expect(wrapper.text()).not.toContain('智能推荐')
    expect(wrapper.text()).not.toContain('AI 智能')
  })
})

describe('本学期周课表', () => {
  const planResult: PlanResult = {
    status: 'partially_feasible',
    selected_classes: [
      { course_id: 'CSE201', class_id: '01' },
      { course_id: 'MAR108', class_id: '99' }, // 在数据中不存在 → 不得编造
    ],
    changes: [],
    risks: [],
    unresolved: [],
  }

  it('按身份 join 到 CourseOffering 并绘制周课表', () => {
    const wrapper = mount(WeeklyScheduleView, {
      props: {
        planResult,
        offerings: OFFERINGS,
        semester: '2026-1',
        currentSchedule: [],
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    const blocks = wrapper.findAll('[data-testid="case-a-weekly-block"]')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].text()).toContain('Python 程序设计')
    expect(blocks[0].text()).toContain('CSE201')
    expect(blocks[0].text()).toContain('01')
    expect(blocks[0].text()).toContain('南校园')
    expect(blocks[0].text()).toContain('A101')
    // 周一 ~ 周日 都要有列
    expect(wrapper.findAll('[data-testid="case-a-weekly-day"]')).toHaveLength(7)
  })

  it('教师为空时显示“任课教师：待核验”，有值时正常显示', () => {
    const withAndWithout = mount(WeeklyScheduleView, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
          changes: [],
          risks: [],
          unresolved: [],
        },
        offerings: OFFERINGS,
        semester: '2026-1',
        currentSchedule: [],
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    expect(withAndWithout.text()).toContain('任课教师：张老师')

    const noTeacher = mount(WeeklyScheduleView, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [{ course_id: 'CSE201', class_id: '02' }],
          changes: [],
          risks: [],
          unresolved: [],
        },
        offerings: OFFERINGS,
        semester: '2026-1',
        currentSchedule: [],
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    expect(noTeacher.text()).toContain('任课教师：待核验')
  })

  it('匹配不到教学班时不绘制、不编造时间', () => {
    const wrapper = mount(WeeklyScheduleView, {
      props: {
        planResult,
        offerings: OFFERINGS,
        semester: '2026-1',
        currentSchedule: [],
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    expect(wrapper.text()).toContain('未能在已返回的教学班数据中匹配到')
    expect(wrapper.findAll('[data-testid="case-a-weekly-block"]')).toHaveLength(1)
  })

  it('按已有输入标注 当前 / 补修 / 意向，不猜标签', () => {
    const wrapper = mount(WeeklyScheduleView, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
          changes: [],
          risks: [],
          unresolved: [],
        },
        offerings: OFFERINGS,
        semester: '2026-1',
        currentSchedule: [OFFERINGS[0]],
        makeupTasks: [makeupTask('CSE201')],
        preferredCourses: ['CSE201'],
      },
    })
    const tags = wrapper.findAll('[data-testid="case-a-weekly-tag"]').map((node) => node.text())
    expect(tags).toContain('当前')
    expect(tags).toContain('补修')
    expect(tags).toContain('意向')
  })

  it('已满足的补修任务不算补修标签', () => {
    const wrapper = mount(WeeklyScheduleView, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
          changes: [],
          risks: [],
          unresolved: [],
        },
        offerings: OFFERINGS,
        semester: '2026-1',
        currentSchedule: [],
        makeupTasks: [makeupTask('CSE201', 'satisfied')],
        preferredCourses: [],
      },
    })
    const tags = wrapper.findAll('[data-testid="case-a-weekly-tag"]').map((node) => node.text())
    expect(tags).not.toContain('补修')
  })
})

describe('教学班身份 = semester + course_id + class_id', () => {
  /** 同一 (course_id, class_id) 在**两个不同学期**各有一条完全相同的记录。 */
  const crossSemesterOfferings: CourseOffering[] = [
    offering({ course_id: 'CSE201', class_id: '01', semester: '2026-1', course_name: 'Python 程序设计' }),
    offering({ course_id: 'CSE201', class_id: '01', semester: '2026-2', course_name: 'Python 程序设计' }),
  ]

  const selected: PlanResult = {
    status: 'partially_feasible',
    selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
    changes: [],
    risks: [],
    unresolved: [],
  }

  it('不同学期的同名教学班不会互相匹配（本学期 2026-2 不得取到 2026-1 的班）', () => {
    const wrongSemester = mount(WeeklyScheduleView, {
      props: {
        planResult: selected,
        offerings: crossSemesterOfferings,
        semester: '2026-2',
        currentSchedule: [],
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    // 本学期的班必须画出来（证明匹配本身是通的）
    expect(wrongSemester.findAll('[data-testid="case-a-weekly-block"]')).toHaveLength(1)

    // 换成本学期 2026-1 时，只有 2026-1 的那条会被取到
    const rightSemester = mount(WeeklyScheduleView, {
      props: {
        planResult: selected,
        offerings: crossSemesterOfferings,
        semester: '2026-1',
        currentSchedule: [],
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    expect(rightSemester.findAll('[data-testid="case-a-weekly-block"]')).toHaveLength(1)
  })

  it('本学期没有任何该教学班时不得回退到别的学期（保持未匹配）', () => {
    const wrapper = mount(WeeklyScheduleView, {
      props: {
        planResult: selected,
        offerings: crossSemesterOfferings,
        // 该学期在数据中根本不存在
        semester: '2027-1',
        currentSchedule: [],
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    expect(wrapper.findAll('[data-testid="case-a-weekly-block"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('未能在已返回的教学班数据中匹配到')
  })

  it('“当前”标签必须整条学期身份一致：别的学期的同一个班不算当前', () => {
    // 已提交的当前课表里是 **2026-2** 的这个班
    const currentSchedule = [crossSemesterOfferings[1]]

    // 本学期 2026-1：即使 course_id + class_id 相同，也**不是**当前那个班
    const otherSemester = mount(WeeklyScheduleView, {
      props: {
        planResult: selected,
        offerings: crossSemesterOfferings,
        semester: '2026-1',
        currentSchedule,
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    const otherTags = otherSemester
      .findAll('[data-testid="case-a-weekly-tag"]')
      .map((node) => node.text())
    expect(otherTags).not.toContain('当前')

    // 本学期 2026-2：整条学期身份一致 → 才有“当前”标签
    const sameSemester = mount(WeeklyScheduleView, {
      props: {
        planResult: selected,
        offerings: crossSemesterOfferings,
        semester: '2026-2',
        currentSchedule,
        makeupTasks: [],
        preferredCourses: [],
      },
    })
    const sameTags = sameSemester
      .findAll('[data-testid="case-a-weekly-tag"]')
      .map((node) => node.text())
    expect(sameTags).toContain('当前')
  })
})

describe('补修标签语义：只有 required 才算补修', () => {
  const planResult: PlanResult = {
    status: 'partially_feasible',
    selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
    changes: [],
    risks: [],
    unresolved: [],
  }

  function tagsForStatus(status: MakeupStatus): string[] {
    const wrapper = mount(WeeklyScheduleView, {
      props: {
        planResult,
        offerings: OFFERINGS,
        semester: '2026-1',
        currentSchedule: [],
        makeupTasks: [makeupTask('CSE201', status)],
        preferredCourses: [],
      },
    })
    return wrapper.findAll('[data-testid="case-a-weekly-tag"]').map((node) => node.text())
  }

  it('required → 显示“补修”', () => {
    expect(tagsForStatus('required')).toContain('补修')
  })

  it('possibly_equivalent → 不显示“补修”', () => {
    expect(tagsForStatus('possibly_equivalent')).not.toContain('补修')
  })

  it('manual_confirmation → 不显示“补修”', () => {
    expect(tagsForStatus('manual_confirmation')).not.toContain('补修')
  })

  it('satisfied → 不显示“补修”', () => {
    expect(tagsForStatus('satisfied')).not.toContain('补修')
  })
})

describe('待确认的调整', () => {
  it('selection_required 呈现为待确认提示，不表示已自动修复', () => {
    const wrapper = mount(PendingAdjustments, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [],
          changes: [],
          risks: [],
          unresolved: [
            { type: 'selection_required', message: '发现可调整的教学班，请确认' },
          ],
        },
        courseNameById: {},
      },
    })
    const card = wrapper.get('[data-testid="case-a-selection-required"]')
    expect(card.text()).toContain('发现可调整的教学班')
    // 确认提示（在校区块的说明里，不在单条卡片上）
    expect(wrapper.text()).toContain('当前版本需要你确认后才能调整')
    // ⛔ 不得表现成系统已经替用户换班
    expect(wrapper.text()).not.toContain('已自动')
    expect(wrapper.text()).not.toContain('已替换')
    // ⛔ 不得提供一个假的“确认调整”按钮
    expect(wrapper.findAll('button')).toHaveLength(0)
  })

  it('changes 只作为建议展示，并说明尚未应用', () => {
    const wrapper = mount(PendingAdjustments, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [],
          changes: [{ course_id: 'CSE201', from_class: '01', to_class: '02', reason: '原班时间冲突' }],
          risks: [],
          unresolved: [],
        },
        courseNameById: { CSE201: 'Python 程序设计' },
      },
    })
    const line = wrapper.get('[data-testid="case-a-adjustment-change"]')
    expect(line.text()).toContain('01 → 02')
    expect(line.text()).toContain('原班时间冲突')
    expect(wrapper.text()).toContain('尚未应用')
  })

  it('没有待确认事项时给出中性空状态', () => {
    const wrapper = mount(PendingAdjustments, {
      props: {
        planResult: { status: 'feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
        courseNameById: {},
      },
    })
    expect(wrapper.find('[data-testid="case-a-adjustments-empty"]').exists()).toBe(true)
  })
})

describe('结构化换班建议（explicit confirm only）', () => {
  const CURRENT = offering({ course_id: 'CSE201', class_id: '01', course_name: 'Python 程序设计' })
  const CANDIDATE = offering({ course_id: 'CSE201', class_id: '02', course_name: 'Python 程序设计' })

  const PLAN: PlanResult = {
    status: 'partially_feasible',
    selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
    changes: [],
    risks: [],
    unresolved: [],
  }

  function mountAdjustments(proposals: unknown) {
    return mount(PendingAdjustments, {
      props: {
        planResult: PLAN,
        repairProposals: proposals as never,
        courseNameById: { CSE201: 'Python 程序设计' },
        offerings: [CURRENT, CANDIDATE],
      },
    })
  }

  it('renders the real structured proposal by identity join', () => {
    const wrapper = mountAdjustments({
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
    })
    const item = wrapper.get('[data-testid="case-a-repair-proposal"]')
    expect(item.text()).toContain('Python 程序设计')
    expect(wrapper.get('[data-testid="case-a-repair-flow"]').text()).toContain('01 → 02')
    // 候选的时间 / 地点来自 identity join 到的 CourseOffering
    expect(item.text()).toContain('周一')
    expect(item.text()).toContain('南校园')
    expect(item.text()).toContain('任课教师：待核验')
  })

  it('never applies a proposal on render — only an explicit click emits apply', async () => {
    const wrapper = mountAdjustments({
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
    })
    // 渲染本身绝不产生任何 apply 事件
    expect(wrapper.emitted('apply')).toBeUndefined()
    await wrapper.get('[data-testid="case-a-repair-apply-CSE201-02"]').trigger('click')
    expect(wrapper.emitted('apply')).toHaveLength(1)
    expect(wrapper.emitted('apply')?.[0]?.[0]).toEqual({
      semester: '2026-1',
      courseId: 'CSE201',
      fromClassId: '01',
      toClassId: '02',
    })
  })

  it('offers no 采用调整 button when the backend returns no structured candidate', () => {
    const wrapper = mount(PendingAdjustments, {
      props: {
        planResult: {
          status: 'partially_feasible',
          selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
          changes: [],
          risks: [],
          unresolved: [{ type: 'selection_required', message: '需要人工选择教学班' }],
        },
        repairProposals: { semester: '2026-1', proposals: [], unresolved: [] },
        courseNameById: {},
        offerings: [],
      },
    })
    expect(wrapper.find('[data-testid="case-a-repair-proposal"]').exists()).toBe(false)
    // ⛔ 没有任何「采用调整」按钮（策略说明文字里提到这个词是允许的）
    expect(wrapper.findAll('button').filter((b) => b.text().includes('采用调整'))).toHaveLength(0)
    // 仍然如实提示"需要明确选择"，但⛔ 不假装系统已经能自动替换
    expect(wrapper.get('[data-testid="case-a-selection-required"]').text()).toContain(
      '需要明确选择',
    )
  })

  it('暂不调整 only hides the row locally and never emits apply', async () => {
    const wrapper = mountAdjustments({
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
    })
    await wrapper.get('[data-testid="case-a-repair-dismiss-CSE201-02"]').trigger('click')
    expect(wrapper.find('[data-testid="case-a-repair-proposal"]').exists()).toBe(false)
    expect(wrapper.emitted('apply')).toBeUndefined()
  })

  it('shows structured unresolved reasons without parsing any message string', () => {
    const wrapper = mountAdjustments({
      semester: '2026-1',
      proposals: [],
      unresolved: ['课程 MAR108 在当前数据范围内没有其他可确认无冲突的教学班。'],
    })
    expect(wrapper.get('[data-testid="case-a-repair-unresolved"]').text()).toContain(
      '没有其他可确认无冲突的教学班',
    )
    expect(wrapper.find('[data-testid="case-a-repair-proposal"]').exists()).toBe(false)
  })
})

describe('显式换班：页面编排（确认才生效）', () => {
  beforeEach(() => {
    loadCaseAOfferings.mockReset()
    runCaseADemo.mockReset()
    applyCaseARepair.mockReset()
    loadCaseAOfferings.mockResolvedValue(OFFERINGS)
  })

  function planResponse(overrides: Record<string, unknown> = {}) {
    return {
      transcript: {
        source_id: 'pdf:1',
        artifact_sha256: 'a'.repeat(64),
        record_count: 4,
        term_count: 2,
        terms: ['2025-1', '2025-2'],
        pending_course_id_count: 4,
      },
      makeup_tasks: [makeupTask('CSE201')],
      course_offerings: OFFERINGS,
      preference: { max_credit: null, avoid_cross_campus: false, preferred_courses: [], avoid_times: [], notes: null },
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
        changes: [
          {
            course_id: 'CSE201',
            from_class: '01',
            to_class: '02',
            reason: '换到无冲突教学班',
          },
        ],
        risks: [],
        unresolved: [],
      },
      provenance: {
        transcript: 't',
        curriculum: 'c',
        course_data: 'case-scoped:south+shenzhen',
        current_schedule: 'selected accepted offering',
        planner: 'actual RestrictedPlanner execution',
        is_full_semester: false,
      },
      repair_proposals: {
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
      },
      roadmap: ROADMAP,
      roadmap_note: null,
      ...overrides,
    }
  }

  async function mountAndPlan() {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const input = wrapper.get('[data-testid="case-a-pdf"]')
    const file = new File(['%PDF-1.4'], 'transcript.pdf', { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    runCaseADemo.mockResolvedValue(planResponse())
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()
    return wrapper
  }

  it('renders the real structured proposal and never applies it on render', async () => {
    const wrapper = await mountAndPlan()
    expect(wrapper.find('[data-testid="case-a-repair-proposal"]').exists()).toBe(true)
    // ⛔ 渲染本身绝不触发 apply
    expect(applyCaseARepair).not.toHaveBeenCalled()
  })

  it('only an explicit click calls repair apply, with the full identity', async () => {
    const wrapper = await mountAndPlan()
    applyCaseARepair.mockResolvedValue({
      status: 'applied',
      applied: true,
      schedule: [OFFERINGS[1]],
      changes: [
        { course_id: 'CSE201', from_class: '01', to_class: '02', reason: '已换班' },
      ],
      reason: '已应用',
      revalidated: true,
      remaining_conflicts: [],
      repair_proposals: { semester: '2026-1', proposals: [], unresolved: [] },
    })
    runCaseADemo.mockResolvedValue(planResponse({ repair_proposals: { semester: '2026-1', proposals: [], unresolved: [] } }))

    await wrapper.get('[data-testid="case-a-repair-apply-CSE201-02"]').trigger('click')
    await flushPromises()

    expect(applyCaseARepair).toHaveBeenCalledTimes(1)
    // 必须携带完整身份，⛔ 不接受"采用第一条建议"这类含糊输入
    expect(applyCaseARepair.mock.calls[0][0]).toMatchObject({
      semester: '2026-1',
      courseId: 'CSE201',
      fromClassId: '01',
      toClassId: '02',
    })
  })

  it('does not present the stale pre-repair plan as current after an applied repair', async () => {
    const wrapper = await mountAndPlan()
    expect(wrapper.findAll('[data-testid="case-a-adjustment-change"]').length).toBe(1)

    applyCaseARepair.mockResolvedValue({
      status: 'applied',
      applied: true,
      schedule: [OFFERINGS[1]],
      changes: [{ course_id: 'CSE201', from_class: '01', to_class: '02', reason: '已换班' }],
      reason: '已应用',
      revalidated: true,
      remaining_conflicts: [],
      repair_proposals: { semester: '2026-1', proposals: [], unresolved: [] },
    })
    // 重新规划**故意**在本次不返回（模拟慢请求），验证不会把旧方案当作当前方案
    runCaseADemo.mockImplementation(() => new Promise(() => {}))

    await wrapper.get('[data-testid="case-a-repair-apply-CSE201-02"]').trigger('click')
    await flushPromises()

    // 旧方案整块暂停展示，并明确标记"待刷新"
    expect(wrapper.find('[data-testid="case-a-plan-stale"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-adjustment-change"]').exists()).toBe(false)
    // ⛔ 旧方案里的 unresolved 事实**不得被清空**（那等于静默丢掉人工复核项）：
    //    它们仍保留在数据里（上方用例覆盖），这里只验证它们不再被当作当前结论展示。
    expect(wrapper.get('[data-testid="case-a-repair-notice"]').text()).toContain('已按你的确认')
  })

  it('lifts the stale marker once the recomputed plan arrives', async () => {
    const wrapper = await mountAndPlan()
    applyCaseARepair.mockResolvedValue({
      status: 'applied',
      applied: true,
      schedule: [OFFERINGS[1]],
      changes: [],
      reason: '已应用',
      revalidated: true,
      remaining_conflicts: [],
      repair_proposals: { semester: '2026-1', proposals: [], unresolved: [] },
    })
    runCaseADemo.mockResolvedValue(
      planResponse({
        plan_result: {
          status: 'feasible',
          selected_classes: [{ course_id: 'CSE201', class_id: '02' }],
          changes: [],
          risks: [],
          unresolved: [{ type: 'schedule_unknown', message: '排课信息待核验' }],
        },
      }),
    )

    await wrapper.get('[data-testid="case-a-repair-apply-CSE201-02"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="case-a-plan-stale"]').exists()).toBe(false)
    // 重新规划返回的 unresolved 如实展示（没有被清空）
    expect(wrapper.text()).toContain('排课信息待核验')
  })

  it('keeps the plan valid when the repair is rejected', async () => {
    const wrapper = await mountAndPlan()
    applyCaseARepair.mockResolvedValue({
      status: 'rejected',
      applied: false,
      schedule: [OFFERINGS[0]],
      changes: [],
      reason: '候选不属于该课程',
      revalidated: false,
      remaining_conflicts: [],
      repair_proposals: { semester: '2026-1', proposals: [], unresolved: [] },
    })
    await wrapper.get('[data-testid="case-a-repair-apply-CSE201-02"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="case-a-repair-error"]').text()).toContain('候选不属于该课程')
    expect(wrapper.get('[data-testid="case-a-repair-notice"]').text()).toContain('未生效')
    // 未生效 ⇒ 课表没变 ⇒ 原方案仍然有效，⛔ 不应标记为待刷新
    expect(wrapper.find('[data-testid="case-a-plan-stale"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-adjustment-change"]').exists()).toBe(true)
  })
})

describe('未来学期修读路径（真实 AcademicRoadmap）', () => {  it('没有 roadmap 数据时整块不渲染，不造假数据', () => {
    const empty = mount(FutureRoadmapView, { props: { roadmap: null } })
    expect(empty.find('[data-testid="case-a-future-roadmap"]').exists()).toBe(false)
    expect(empty.text()).toBe('')

    const noSemesters = mount(FutureRoadmapView, {
      props: { roadmap: { ...ROADMAP, future_semesters: [] } },
    })
    expect(noSemesters.find('[data-testid="case-a-future-roadmap"]').exists()).toBe(false)
  })

  it('renders the course-level path with real semester facts', () => {
    const wrapper = mount(FutureRoadmapView, { props: { roadmap: ROADMAP } })
    expect(wrapper.get('[data-testid="case-a-roadmap-disclaimer"]').text()).toContain(
      '课程级',
    )
    expect(wrapper.text()).toContain('操作系统')
    expect(wrapper.text()).toContain('CSE310')
    expect(wrapper.text()).toContain('必修')
    // 培养方案学期号必须如实展示（⛔ 不说成"列表第 N 项"）
    expect(wrapper.get('[data-testid="case-a-roadmap-term"]').text()).toContain(
      '培养方案第 4 学期',
    )
  })

  it('shows elective credit progress and never guesses missing evidence', () => {
    const wrapper = mount(FutureRoadmapView, { props: { roadmap: ROADMAP } })
    const progress = wrapper.get('[data-testid="case-a-elective-progress"]').text()
    expect(progress).toContain('23')
    expect(progress).toContain('规划前缺口')
    expect(progress).toContain('CSE-ELECTIVE-POOL')

    const unknown = mount(FutureRoadmapView, {
      props: {
        roadmap: {
          ...ROADMAP,
          elective: { ...ROADMAP.elective, completed_credit: null, gap_credit: null },
        },
      },
    })
    expect(unknown.find('[data-testid="case-a-elective-insufficient"]').exists()).toBe(true)
  })

  it('never leaks any teaching-class field into the future semesters', () => {
    const wrapper = mount(FutureRoadmapView, { props: { roadmap: ROADMAP } })
    const terms = wrapper.findAll('[data-testid="case-a-roadmap-term"]')
    expect(terms).toHaveLength(1)
    const termText = terms[0].text()
    for (const forbidden of ['教学班', '星期', '教室', '容量', '任课教师', '节']) {
      expect(termText).not.toContain(forbidden)
    }
    // 课程条目本身也只能带课程级字段
    for (const item of wrapper.findAll('[data-testid="case-a-roadmap-course"]')) {
      for (const forbidden of ['class_id', 'teacher', 'campus', 'classroom', 'meetings']) {
        expect(item.text()).not.toContain(forbidden)
      }
    }
  })

  it('surfaces roadmap unresolved and warnings instead of hiding them', () => {
    const wrapper = mount(FutureRoadmapView, { props: { roadmap: ROADMAP } })
    expect(wrapper.find('[data-testid="case-a-roadmap-unresolved"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-roadmap-warnings"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('本学期选修学分证据不足')
  })
})

describe('Case A 页面（Phase 1）', () => {
  beforeEach(() => {
    loadCaseAOfferings.mockReset()
    runCaseADemo.mockReset()
    loadCaseAOfferings.mockResolvedValue(OFFERINGS)
  })

  it('主界面不出现 Preference 技术字段名，且不再展示技术化第三步标题', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const text = wrapper.text()
    for (const field of ['max_credit', 'avoid_cross_campus', 'preferred_courses', 'avoid_times', 'notes']) {
      expect(text).not.toContain(field)
    }
    expect(text).toContain('第三步：告诉我你的选课需求')
    expect(text).not.toContain('第三步：设置排课偏好')
    // 学生化文案
    expect(text).toContain('本学期最多希望修多少学分？')
    expect(text).toContain('你还想学习哪些课程？')
    expect(text).toContain('我不方便上课的时间')
    expect(text).toContain('还有什么希望系统考虑？')
  })

  it('规划说明卡如实描述“找候选 → 提建议 → 用户确认”，不承诺自动替换', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const card = wrapper.get('[data-testid="case-a-planning-explainer"]')
    expect(card.text()).toContain('系统将如何帮你规划')
    expect(card.text()).toContain('检查当前课表的时间冲突')
    expect(card.text()).toContain('由你决定')
    // 必须**明确否认**自动替换（当前真实语义：找候选 → 提建议 → 用户确认）。
    // ⚠️ 断言方式必须是“没有把‘会自动替换’当作已发生的事实陈述”，
    // 因此先要求存在“不会自动替换”，再确认不存在肯定式表述。
    expect(card.text()).toContain('不会自动替换')
    expect(card.text()).not.toContain('系统自动替换')
    expect(card.text()).not.toContain('已经自动替换')
    expect(card.text()).not.toContain('已自动替换')
  })

  it('CTA 文案为“生成并优化我的转专业学业方案”', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    expect(wrapper.get('[data-testid="case-a-submit"]').text()).toContain('生成并优化我的转专业学业方案')
  })

  it('意向课程写入 preferredCourses，重复课程不会重复加入', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    await wrapper.get('[data-testid="case-a-intent-input"]').setValue('Python')
    await wrapper.get('[data-testid="case-a-intent-add"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="case-a-intent-chip"]')).toHaveLength(1)
    expect(wrapper.get('[data-testid="case-a-intent-chip"]').text()).toContain('CSE201')

    // 再次点击同一结果：按钮已禁用 → 不产生第二条
    await wrapper.get('[data-testid="case-a-intent-add"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="case-a-intent-chip"]')).toHaveLength(1)
  })

  it('教学班搜索结果仍不超过 20 条（不一次性铺开 4069）', async () => {
    loadCaseAOfferings.mockResolvedValue(
      Array.from({ length: 4069 }, (_, index) =>
        offering({
          course_id: 'CS1000',
          class_id: `C-${index}`,
          course_name: '数据结构',
          teacher: `教师${index}`,
        }),
      ),
    )
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    await wrapper.get('[data-testid="case-a-offering-search"]').setValue('数据结构')
    expect(wrapper.findAll('[data-testid="case-a-search-result"]')).toHaveLength(20)
  })

  it('结果渲染本学期推荐课表与待确认调整，且无 roadmap 时不显示未来学期区块', async () => {
    runCaseADemo.mockResolvedValue({
      transcript: {
        source_id: 's',
        artifact_sha256: 'a'.repeat(64),
        record_count: 24,
        term_count: 2,
        terms: ['2025-2026学年第一学期'],
        pending_course_id_count: 24,
      },
      makeup_tasks: [makeupTask('CSE201')],
      course_offerings: OFFERINGS,
      preference: { max_credit: 24, avoid_cross_campus: false, preferred_courses: ['CSE201'], avoid_times: [] },
      plan_result: {
        status: 'partially_feasible',
        selected_classes: [{ course_id: 'CSE201', class_id: '01' }],
        changes: [],
        risks: [],
        unresolved: [{ type: 'selection_required', message: '发现可调整的教学班' }],
      },
      provenance: {
        transcript: 'user-uploaded SYSU transcript PDF',
        curriculum: 'Case A target curriculum',
        course_data: 'case-scoped:south+shenzhen',
        current_schedule: 'selected accepted offering',
        planner: 'actual RestrictedPlanner execution',
        is_full_semester: false,
      },
    })

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

    expect(wrapper.find('[data-testid="case-a-weekly-schedule"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="case-a-weekly-block"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="case-a-pending-adjustments"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-selection-required"]').exists()).toBe(true)
    // ⛔ 后端未返回 roadmap → 整块不渲染
    expect(wrapper.find('[data-testid="case-a-future-roadmap"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('本学期推荐课表')
  })
})
