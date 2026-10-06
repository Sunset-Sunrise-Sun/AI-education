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

vi.mock('@/api/caseADemo', () => ({
  loadCaseAOfferings: (...args: unknown[]) => loadCaseAOfferings(...args),
  runCaseADemo: (...args: unknown[]) => runCaseADemo(...args),
}))

function offering(overrides: Partial<CourseOffering> & { course_id: string; class_id: string }): CourseOffering {
  return {
    course_name: '示例课程',
    semester: '2026-1',
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
        // 该教学班身份出现在已提交的当前课表中
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
        currentSchedule: [],
        makeupTasks: [makeupTask('CSE201', 'satisfied')],
        preferredCourses: [],
      },
    })
    const tags = wrapper.findAll('[data-testid="case-a-weekly-tag"]').map((node) => node.text())
    expect(tags).not.toContain('补修')
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
    expect(wrapper.get('[data-testid="case-a-roadmap-disclaimer"]').text()).toContain(
      '未来学期为基于培养方案的课程级规划',
    )
    expect(wrapper.text()).toContain('操作系统 3 学分')
    expect(wrapper.text()).toContain('预计学分：11')
    // ⛔ 未来学期**课程条目**里不得出现任何教学班 / 排课信息
    // （disclaimer 里那句“具体教学班需以届时教务系统实际开课为准”是允许且要求的）
    const terms = wrapper.findAll('[data-testid="case-a-roadmap-term"]')
    expect(terms).toHaveLength(1)
    const termText = terms[0].text()
    for (const forbidden of ['教学班', '星期', '教室', '容量', '任课教师']) {
      expect(termText).not.toContain(forbidden)
    }
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
