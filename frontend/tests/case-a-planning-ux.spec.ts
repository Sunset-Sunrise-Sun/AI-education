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
import type { CourseOffering, MakeupTask, PlanResult } from '@/types/contracts'

const loadCaseAOfferings = vi.fn()
const runCaseADemo = vi.fn()
const loadStudyPlanMock = vi.fn()
const loadMajorsMock = vi.fn()
const loadCompletedCoursesMock = vi.fn()

vi.mock('@/api/caseADemo', () => ({
  loadCaseAOfferings: (...args: unknown[]) => loadCaseAOfferings(...args),
  runCaseADemo: (...args: unknown[]) => runCaseADemo(...args),
}))

// ⛔ 本 spec 不联网：培养方案与成绩单明细全部走 mock
//    （否则未来学习路径会依赖真实后端，测试既慢又不稳定）。
vi.mock('@/api/studyPlan', async () => {
  const actual = await vi.importActual<typeof import('@/api/studyPlan')>('@/api/studyPlan')
  return {
    ...actual,
    loadMajors: (...args: unknown[]) => loadMajorsMock(...args),
    loadStudyPlan: (...args: unknown[]) => loadStudyPlanMock(...args),
  }
})

vi.mock('@/api/completedCourses', () => ({
  CompletedCoursesApiError: class extends Error {},
  loadCompletedCourses: (...args: unknown[]) => loadCompletedCoursesMock(...args),
}))

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

  it('页面使用学生语言说明课程搜索，不宣称智能语义推荐', () => {
    const wrapper = mount(IntentCourseSearch, {
      props: { offerings: OFFERINGS, selectedCourseIds: [] },
    })
    // 规定的搜索框 placeholder
    expect(wrapper.get('[data-testid="case-a-intent-input"]').attributes('placeholder')).toContain(
      '搜索课程名称、课程号或关键词',
    )
    expect(wrapper.text()).toContain('输入课程名称、课程号或关键词进行查找')
    expect(wrapper.text()).not.toContain('字面关键词')
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
    // 待确认事项只在推荐方案出现，调整建议不重复展示。
    expect(wrapper.find('[data-testid="case-a-selection-required"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('发现可调整的教学班')
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

describe('未来学期修读路径（可接入壳）', () => {
  it('没有 roadmap 数据时整块不渲染，不造假数据', () => {
    const empty = mount(FutureRoadmapView, { props: { roadmap: null } })
    expect(empty.find('[data-testid="case-a-future-roadmap"]').exists()).toBe(false)
    expect(empty.text()).toBe('')

    const noSemesters = mount(FutureRoadmapView, { props: { roadmap: { semesters: [] } } })
    expect(noSemesters.find('[data-testid="case-a-future-roadmap"]').exists()).toBe(false)
  })

  it('有 roadmap 时渲染课程级路径，且不出现任何教学班信息', () => {
    const wrapper = mount(FutureRoadmapView, {
      props: {
        roadmap: {
          semesters: [
            {
              semester: '2026-2',
              required: [
                { course_id: 'CSE310', course_name: '操作系统', credit: 3 },
                { course_id: 'CSE320', course_name: '计算机网络', credit: 3 },
              ],
              makeup: [{ course_id: 'MAR108', course_name: '人工智能导论', credit: 2 }],
              elective: [{ course_id: 'CSE401', course_name: '专业选修', credit: 3 }],
            },
          ],
        },
      },
    })
    // ⚠️ 免责说明（Phase 7 任务 2）：必须写明"基于培养方案要求生成、不代表实际开课安排"
    expect(wrapper.get('[data-testid="case-a-roadmap-disclaimer"]').text()).toContain(
      '以上规划基于培养方案要求生成，不代表实际开课安排',
    )
    expect(wrapper.text()).toContain('操作系统 3 学分')
    expect(wrapper.text()).toContain('预计学分：11')
    // 学期以中文标签展示（2026-2 → 2026秋），并保留原始学期码
    expect(wrapper.get('[data-testid="case-a-roadmap-term-title"]').text()).toContain('2026秋')
    // ⛔ 未来学期**课程条目**里不得出现任何教学班 / 排课信息
    // （disclaimer 里"不预测教师、时间与地点"是允许且要求的）
    const terms = wrapper.findAll('[data-testid="case-a-roadmap-term"]')
    expect(terms).toHaveLength(1)
    const termText = terms[0].text()
    for (const forbidden of ['教学班', '星期', '教室', '容量', '任课教师']) {
      expect(termText).not.toContain(forbidden)
    }
  })

  it('渲染完成目标（completion_goals），且缺数据时该段不渲染', () => {
    const wrapper = mount(FutureRoadmapView, {
      props: {
        roadmap: {
          semesters: [
            {
              semester: '2026-2',
              required: [{ course_id: 'CSE310', course_name: '操作系统', credit: 3 }],
              completion_goals: ['完成 1 门培养要求缺口课程', '修读约 3 学分'],
            },
          ],
        },
      },
    })
    expect(wrapper.get('[data-testid="case-a-roadmap-goals"]').text()).toContain(
      '完成 1 门培养要求缺口课程',
    )

    const noGoals = mount(FutureRoadmapView, {
      props: {
        roadmap: {
          semesters: [
            { semester: '2026-2', required: [{ course_id: 'CSE310', course_name: '操作系统', credit: 3 }] },
          ],
        },
      },
    })
    expect(noGoals.find('[data-testid="case-a-roadmap-goals"]').exists()).toBe(false)
  })
})

/* -------------------------------------------------------------------------- *
 * 🔴 Review 回归：已满足课程禁止进入未来规划（页面级）
 * -------------------------------------------------------------------------- */

describe('🔴 Review 回归：未来规划必须扣除成绩单已修课程', () => {
  /** 培养方案：线性代数 / 体育（都会被成绩单覆盖）+ 操作系统（真缺口）。 */
  function roadmapPlan() {
    const requirement = (
      courseId: string,
      courseName: string,
      credit: number,
      term: string,
    ) => ({
      course_id: courseId,
      course_name: courseName,
      credit,
      requirement: 'required' as const,
      course_type: '公必',
      group_id: null,
      recommended_term_text: term,
      prerequisites: null,
      prerequisites_known: false,
      source_record: `table:1!row:${courseId}`,
    })
    return {
      major_id: 'network-security',
      name: '网络空间安全',
      cohort: '2025',
      version_id: 'major-network-security',
      source_id: 'case-owner-confirmed://majors/network-security/plan',
      complete: true,
      completeness_evidence: null,
      total_credit: null,
      counts: { total: 3, required: 3, elective: 0, unknown: 0, prerequisites_unknown: 3 },
      requirements: [
        requirement('MA179', '线性代数', 3, '2026-2'),
        requirement('PE101', '体育', 1, '2026-2'),
        requirement('CSE301', '操作系统', 3, '2026-2'),
      ],
      elective_pool: { groups: [], courses: [] },
    }
  }

  beforeEach(() => {
    loadCaseAOfferings.mockReset().mockResolvedValue([])
    loadMajorsMock.mockReset().mockResolvedValue([
      {
        major_id: 'network-security',
        name: '网络空间安全',
        cohort: '2025',
        version_id: 'major-network-security',
        source_id: 'case-owner-confirmed://majors/network-security/plan',
      },
    ])
    loadStudyPlanMock.mockReset().mockResolvedValue(roadmapPlan() as never)
    loadCompletedCoursesMock.mockReset()
  })

  it('成绩单含线性代数、体育 ⇒ 未来规划**不包含**线性代数与体育', async () => {
    loadCompletedCoursesMock.mockResolvedValue([
      { course_name: '线性代数', credit: 3, passed: true },
      { course_name: '体育', credit: 1, passed: true },
    ])
    runCaseADemo.mockResolvedValue({
      transcript: {
        source_id: 's',
        artifact_sha256: 'a'.repeat(64),
        record_count: 2,
        term_count: 1,
        terms: [],
        pending_course_id_count: 2,
      },
      // ⚠️ 关键：后端把**已修**与**未修**都标成 manual_confirmation
      makeup_tasks: [
        { course_id: 'MA179', course_name: '线性代数', credit: 3, status: 'manual_confirmation', reason: 'r', source_evidence: 'e' },
        { course_id: 'PE101', course_name: '体育', credit: 1, status: 'manual_confirmation', reason: 'r', source_evidence: 'e' },
        { course_id: 'CSE301', course_name: '操作系统', credit: 3, status: 'required', reason: 'r', source_evidence: 'e' },
      ],
      course_offerings: [],
      preference: { preferred_courses: [], avoid_times: [], avoid_cross_campus: false },
      plan_result: { status: 'partially_feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
      provenance: {},
    } as never)

    const wrapper = mount(CaseADemoView)
    await flushPromises()

    // 上传 PDF（触发已修课程读取）
    const pdfInput = wrapper.get('[data-testid="case-a-pdf"]')
    Object.defineProperty(pdfInput.element, 'files', {
      value: [new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await pdfInput.trigger('change')
    await flushPromises()
    expect(loadCompletedCoursesMock).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    // 🔴 核心断言：已满足课程不得出现在任何未来学期
    const roadmap = wrapper.get('[data-testid="case-a-future-roadmap"]')
    const termsText = roadmap.findAll('[data-testid="case-a-roadmap-term"]').map((node) => node.text())
    for (const termText of termsText) {
      expect(termText).not.toContain('线性代数')
      expect(termText).not.toContain('体育')
    }
    // ✅ 真缺口仍然排期
    expect(termsText.join(' ')).toContain('操作系统')
    // 五状态如实展示：已完成 2 门（线性代数、体育）
    expect(wrapper.get('[data-testid="case-a-roadmap-states"]').text()).toContain('已完成 2 门')
  })

  it('✅ 语义收敛：状态标签为「明确缺口 / 待确认 / 培养要求待覆盖」，且带固定说明', async () => {
    loadCompletedCoursesMock.mockResolvedValue([
      { course_name: '线性代数', credit: 3, passed: true },
    ])
    runCaseADemo.mockResolvedValue({
      transcript: {
        source_id: 's',
        artifact_sha256: 'a'.repeat(64),
        record_count: 1,
        term_count: 1,
        terms: [],
        pending_course_id_count: 1,
      },
      makeup_tasks: [
        { course_id: 'CSE301', course_name: '操作系统', credit: 3, status: 'manual_confirmation', reason: 'r', source_evidence: 'e' },
      ],
      course_offerings: [],
      preference: { preferred_courses: [], avoid_times: [], avoid_cross_campus: false },
      plan_result: { status: 'partially_feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
      provenance: {},
    } as never)

    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const pdfInput = wrapper.get('[data-testid="case-a-pdf"]')
    Object.defineProperty(pdfInput.element, 'files', {
      value: [new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await pdfInput.trigger('change')
    await flushPromises()
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    const states = wrapper.get('[data-testid="case-a-roadmap-states"]').text()
    expect(states).toContain('明确缺口')
    expect(states).toContain('待确认')
    expect(states).toContain('培养要求待覆盖')
    // ⛔ 不得再出现旧的暗示性措辞
    expect(states).not.toContain('待判定')
    expect(states).not.toContain('待补修')

    // ④ 固定说明必须逐字出现
    const explain = wrapper.get('[data-testid="case-a-roadmap-coverage-explain"]').text()
    expect(explain).toContain('培养要求待覆盖')
    expect(explain).toContain('目标培养方案要求存在')
    expect(explain).toContain('不足以判断是否需要补修')
    expect(explain).toContain('不代表系统已判断你缺这些课')

    // ⑤ 当前学期语义说明
    const scope = wrapper.get('[data-testid="case-a-roadmap-term-scope"]').text()
    expect(scope).toContain('未来规划从')
    expect(scope).toContain('2026秋')
    expect(scope).toContain('进行中')

    // ③ 学分摘要：待确认与待覆盖分开列出
    const recon = wrapper.get('[data-testid="case-a-roadmap-reconciliation"]').text()
    expect(recon).toContain('待确认')
    expect(recon).toContain('培养要求待覆盖')
    expect(recon).toContain('明确缺口')

    // Review 优化 ①：预计完成**不得**表达为毕业预测
    const expected = wrapper.get('[data-testid="case-a-roadmap-expected-term"]').text()
    expect(expected).toContain('预计培养要求完成时间')
    expect(expected).toContain('不是毕业时间预测')
    // ⛔ 全页不得出现"预计毕业"
    expect(wrapper.text()).not.toContain('预计毕业')

    // Review 优化 ②：学分口径说明
    expect(wrapper.get('[data-testid="case-a-roadmap-credit-note"]').text()).toContain(
      '未做四舍五入',
    )

    // Review 优化 ③：排序说明只按课程类型，⛔ 无先修假设
    const ordering = wrapper.get('[data-testid="case-a-roadmap-ordering-note"]').text()
    expect(ordering).toContain('未提供先修关系')
    expect(ordering).toContain('仅按课程类型优化顺序')
  })

  it('✅ 页面文案：标题含「基于培养方案」，且明确不预测教师/时间/教学班', async () => {
    loadCompletedCoursesMock.mockResolvedValue([
      { course_name: '线性代数', credit: 3, passed: true },
    ])
    runCaseADemo.mockResolvedValue({
      transcript: {
        source_id: 's',
        artifact_sha256: 'a'.repeat(64),
        record_count: 1,
        term_count: 1,
        terms: [],
        pending_course_id_count: 1,
      },
      makeup_tasks: [
        { course_id: 'CSE301', course_name: '操作系统', credit: 3, status: 'required', reason: 'r', source_evidence: 'e' },
      ],
      course_offerings: [],
      preference: { preferred_courses: [], avoid_times: [], avoid_cross_campus: false },
      plan_result: { status: 'partially_feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
      provenance: {},
    } as never)

    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const pdfInput = wrapper.get('[data-testid="case-a-pdf"]')
    Object.defineProperty(pdfInput.element, 'files', {
      value: [new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await pdfInput.trigger('change')
    await flushPromises()
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('未来学习路径规划（基于培养方案）')
    expect(text).toContain('不代表未来实际开课安排，不预测教师、时间和教学班')
    // 毕业要求闭环摘要
    expect(wrapper.find('[data-testid="case-a-roadmap-summary"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-roadmap-graduation"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-roadmap-expected-term"]').exists()).toBe(true)
    // 先修信息缺失必须如实说明
    expect(wrapper.get('[data-testid="case-a-roadmap-ordering-note"]').text()).toContain(
      '未提供先修关系',
    )
    // ⛔ 未来学期区块内不得出现教学班 / 教师 / 星期 / 教室
    const termText = wrapper
      .findAll('[data-testid="case-a-roadmap-term"]')
      .map((node) => node.text())
      .join(' ')
    for (const forbidden of ['教学班', '星期', '教室', '任课教师']) {
      expect(termText).not.toContain(forbidden)
    }
  })

  it('⛔ 读不到已修课程明细时不排期（避免把已修课排进未来）', async () => {
    loadCompletedCoursesMock.mockRejectedValue(new Error('boom'))
    runCaseADemo.mockResolvedValue({
      transcript: {
        source_id: 's',
        artifact_sha256: 'a'.repeat(64),
        record_count: 0,
        term_count: 0,
        terms: [],
        pending_course_id_count: 0,
      },
      makeup_tasks: [
        { course_id: 'MA179', course_name: '线性代数', credit: 3, status: 'required', reason: 'r', source_evidence: 'e' },
      ],
      course_offerings: [],
      preference: { preferred_courses: [], avoid_times: [], avoid_cross_campus: false },
      plan_result: { status: 'partially_feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
      provenance: {},
    } as never)

    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const pdfInput = wrapper.get('[data-testid="case-a-pdf"]')
    Object.defineProperty(pdfInput.element, 'files', {
      value: [new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await pdfInput.trigger('change')
    await flushPromises()
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    expect(
      wrapper.get('[data-testid="case-a-roadmap-completed-unavailable"]').text(),
    ).toContain('已修课程明细')
    expect(wrapper.find('[data-testid="case-a-future-roadmap"]').exists()).toBe(false)
  })

  it('🔴 状态闭环：确认可转换后未来路径**立即重算**（不留旧规划）', async () => {
    loadCompletedCoursesMock.mockResolvedValue([])
    runCaseADemo.mockResolvedValue({
      transcript: {
        source_id: 's',
        artifact_sha256: 'a'.repeat(64),
        record_count: 1,
        term_count: 1,
        terms: [],
        pending_course_id_count: 1,
      },
      makeup_tasks: [
        // 待确认：成绩单有记录但无法自动确认
        { course_id: 'MA179', course_name: '线性代数', credit: 3, status: 'manual_confirmation', reason: 'r', source_evidence: 'e' },
      ],
      course_offerings: [],
      preference: { preferred_courses: [], avoid_times: [], avoid_cross_campus: false },
      plan_result: { status: 'partially_feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
      provenance: {},
    } as never)

    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const pdfInput = wrapper.get('[data-testid="case-a-pdf"]')
    Object.defineProperty(pdfInput.element, 'files', {
      value: [new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await pdfInput.trigger('change')
    await flushPromises()
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    // ① 确认前：待确认 1 门；线性代数**不在**任何未来学期
    expect(wrapper.get('[data-testid="case-a-roadmap-states"]').text()).toContain('待确认 1 门')
    const termsText = () =>
      wrapper.findAll('[data-testid="case-a-roadmap-term"]').map((n) => n.text()).join(' ')
    expect(termsText()).not.toContain('线性代数')
    // 「方案要求但无依据」的课仍会排期（见 utils/futureRoadmap.ts 文件头说明）
    expect(termsText()).toContain('操作系统')

    // ② 用户在「补修缺口分析」里确认可转换
    await wrapper.get('[data-testid="case-a-makeup-convert"]').trigger('click')
    await flushPromises()

    // ③ 未来路径**立即重算**：待确认 → 已完成，且该课**仍然不进**未来学期
    const states = wrapper.get('[data-testid="case-a-roadmap-states"]').text()
    expect(states).toContain('已完成 1 门')
    expect(states).toContain('待确认 0 门')
    expect(termsText()).not.toContain('线性代数')
  })

  it('🔴 状态闭环：待确认课程在确认后**不再**出现在未来学期（对比：未确认时也不出现）', async () => {
    // 两门课：一门待确认、一门"方案要求但无依据"（会进未来学期）
    loadCompletedCoursesMock.mockResolvedValue([])
    runCaseADemo.mockResolvedValue({
      transcript: {
        source_id: 's',
        artifact_sha256: 'a'.repeat(64),
        record_count: 1,
        term_count: 1,
        terms: [],
        pending_course_id_count: 1,
      },
      makeup_tasks: [
        { course_id: 'MA179', course_name: '线性代数', credit: 3, status: 'manual_confirmation', reason: 'r', source_evidence: 'e' },
      ],
      course_offerings: [],
      preference: { preferred_courses: [], avoid_times: [], avoid_cross_campus: false },
      plan_result: { status: 'partially_feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
      provenance: {},
    } as never)

    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const pdfInput = wrapper.get('[data-testid="case-a-pdf"]')
    Object.defineProperty(pdfInput.element, 'files', {
      value: [new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await pdfInput.trigger('change')
    await flushPromises()
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    const roadmapText = () =>
      wrapper.findAll('[data-testid="case-a-roadmap-term"]').map((n) => n.text()).join(' ')
    // 未确认：待确认 ⇒ 不排期 ⇒ 学期区块不含线性代数
    expect(roadmapText()).not.toContain('线性代数')

    await wrapper.get('[data-testid="case-a-makeup-convert"]').trigger('click')
    await flushPromises()

    // 已确认：仍然不含（状态从"待确认"变为"已完成"，两者都不排期）
    expect(roadmapText()).not.toContain('线性代数')
    expect(wrapper.get('[data-testid="case-a-roadmap-states"]').text()).toContain('已完成 1 门')
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

  it('规划说明卡面向学生说明可获得的帮助，不展示算法过程', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    const card = wrapper.get('[data-testid="case-a-planning-explainer"]')
    expect(card.text()).toContain('AI 如何帮助你规划')
    expect(card.text()).toContain('分析你的培养要求和已有课程')
    expect(card.text()).toContain('帮助你了解后续学期的学习路径')
    expect(card.text()).not.toMatch(/求解|约束|算法|Planner/i)
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

  it('结果渲染本学期推荐课表与待确认调整；无课程级路径时显示诚实说明', async () => {
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
    // ⛔ Phase 7 任务 1：「调整建议」展示模块已删除（当前无教学班调整能力）。
    //    ⚠️ 只删展示：后端 `plan_result.changes` 能力未动。
    expect(wrapper.find('[data-testid="case-a-pending-adjustments"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('调整建议')
    // ⚠️ 信息架构调整（本次任务）：拆成三个独立阶段，全部位于课表之前。
    //    `unresolved` 的课程级确认已并入「补修缺口分析」（数据源 makeup_tasks），
    //    不再由旧的结果面板渲染。
    expect(wrapper.find('[data-testid="case-a-makeup-gap"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-recommend"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('补修缺口分析')
    expect(wrapper.text()).toContain('推荐选课')
    // ⚠️ Phase 7 任务 2：未来学习路径改为**前端派生**（培养方案推荐学期 + 匹配结果），
    //    因此它是否渲染取决于培养方案数据是否可用，而不再取决于后端是否返回 roadmap。
    expect(wrapper.text()).toContain('未来学习路径规划')
    expect(wrapper.text()).toContain('本次规划依据')
    expect(wrapper.text()).not.toContain('24成绩单课程')
    expect(wrapper.text()).toContain('生成后的规划课表')
    expect(wrapper.text()).not.toMatch(/Planner|Case A|结构化约束|正式求解约束|字面关键词/i)
  })
})
