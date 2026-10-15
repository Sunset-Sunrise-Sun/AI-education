/**
 * 专业选择链与培养方案接口测试。
 *
 * ```text
 * GET /api/v1/majors                  → 下拉选项（专业名 + major_id）
 * GET /api/v1/study-plans/{major_id}  → 培养方案（要求 + 选修池）
 *
 * 选择目标专业 → 加载对应培养方案 → （后端在 /plan 中据成绩单匹配）
 * ```
 *
 * ⛔ 全程不发真实网络请求；⛔ 不放宽 data_source 门禁。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import StudyPlanPanel from '@/components/StudyPlanPanel.vue'
import {
  StudyPlanApiError,
  type ElectiveProgress,
  type MajorSummary,
  type StudyPlan,
  type StudyPlanRequirement,
} from '@/types/studyPlan'
import {
  electivePoolOf,
  prerequisitesNote,
  requiredOf,
} from '@/api/studyPlan'

const loadOfferings = vi.fn()
const loadMajorsApi = vi.fn()
const loadStudyPlanApi = vi.fn()

vi.mock('@/api/caseADemo', async () => ({
  ...(await vi.importActual<typeof import('@/api/caseADemo')>('@/api/caseADemo')),
  loadCaseAOfferings: (...args: unknown[]) => loadOfferings(...args),
  runCaseADemo: vi.fn(),
}))

vi.mock('@/api/studyPlan', async () => {
  const actual = await vi.importActual<typeof import('@/api/studyPlan')>('@/api/studyPlan')
  return {
    ...actual,
    loadMajors: (...args: unknown[]) => loadMajorsApi(...args),
    loadStudyPlan: (...args: unknown[]) => loadStudyPlanApi(...args),
  }
})

function requirement(
  courseId: string,
  courseName: string,
  kind: 'required' | 'elective',
  credit = 3,
): StudyPlanRequirement {
  return {
    course_id: courseId,
    course_name: courseName,
    credit,
    requirement: kind,
    course_type: '专业课',
    group_id: kind === 'elective' ? 'POOL' : null,
    recommended_term_text: '2025-1',
    prerequisites: null,
    prerequisites_known: false,
    source_record: `table:2!row:${courseId}`,
  }
}

function studyPlan(majorId: string, name: string, total: number): StudyPlan {
  const requirements = [
    requirement('MA179', '线性代数', 'required', 3),
    requirement('CSE101', '程序设计I', 'required', 3),
    requirement('CSE335', '数据库系统原理', 'elective', 3),
    requirement('CSE371', '自然语言处理', 'elective', 2),
  ]
  return {
    major_id: majorId,
    name,
    cohort: '2025',
    version_id: `major-${majorId}`,
    source_id: `case-owner-confirmed://majors/${majorId}/plan`,
    complete: true,
    completeness_evidence: 'case-owner-confirmed://completeness',
    total_credit: null,
    counts: {
      total,
      required: 2,
      elective: 2,
      unknown: 0,
      // 真实培养方案 docx 无先修列 ⇒ 全部未知
      prerequisites_unknown: total,
    },
    requirements,
    elective_pool: {
      groups: [
        { group_id: 'POOL', name: '专业选修课', minimum_credit: 23, source_record: 'table:7!row:2' },
      ],
      courses: requirements.filter((item) => item.requirement === 'elective'),
    },
  }
}

const MAJORS: MajorSummary[] = [
  {
    major_id: 'network-security',
    name: '网络空间安全',
    cohort: '2025',
    version_id: 'major-network-security',
    source_id: 'case-owner-confirmed://majors/network-security/plan',
  },
  {
    major_id: 'remote-sensing',
    name: '遥感科学与技术',
    cohort: '2025',
    version_id: 'major-remote-sensing',
    source_id: 'case-owner-confirmed://majors/remote-sensing/plan',
  },
]

beforeEach(() => {
  loadOfferings.mockReset().mockResolvedValue([])
  loadMajorsApi.mockReset().mockResolvedValue(MAJORS)
  loadStudyPlanApi.mockReset().mockImplementation((majorId: string) =>
    Promise.resolve(
      majorId === 'remote-sensing'
        ? studyPlan('remote-sensing', '遥感科学与技术', 84)
        : studyPlan('network-security', '网络空间安全', 94),
    ),
  )
})

/* -------------------------------------------------------------------------- *
 * 纯派生工具
 * -------------------------------------------------------------------------- */

describe('培养方案派生工具（⛔ 不判定等价、⛔ 不算缺口）', () => {
  it('requiredOf / electivePoolOf 按 requirement 分流', () => {
    const plan = studyPlan('network-security', '网络空间安全', 94)
    expect(requiredOf(plan).map((r) => r.course_id)).toEqual(['MA179', 'CSE101'])
    expect(electivePoolOf(plan).map((r) => r.course_id)).toEqual(['CSE335', 'CSE371'])
  })

  it('先修关系全部未知时给出如实说明（解释匹配为何保守）', () => {
    const plan = studyPlan('network-security', '网络空间安全', 94)
    const note = prerequisitesNote(plan)
    expect(note).toContain('未提供先修关系')
    expect(note).toContain('94/94')
    expect(note).toContain('不会自动断定缺课')
  })

  it('先修关系完整时不声称"未知"', () => {
    const plan = studyPlan('network-security', '网络空间安全', 4)
    const patched = { ...plan, counts: { ...plan.counts, prerequisites_unknown: 0 } }
    expect(prerequisitesNote(patched)).toContain('已提供全部课程的先修关系')
  })
})

/* -------------------------------------------------------------------------- *
 * StudyPlanPanel 渲染
 * -------------------------------------------------------------------------- */

describe('StudyPlanPanel：只呈现培养方案要求', () => {
  it('加载中 / 未选择 / 失败 三种状态如实展示', () => {
    const loading = mount(StudyPlanPanel, {
      props: { plan: null, loading: true, error: '', majorName: '网络空间安全' },
    })
    expect(loading.find('[data-testid="case-a-study-plan-loading"]').exists()).toBe(true)

    const empty = mount(StudyPlanPanel, {
      props: { plan: null, loading: false, error: '', majorName: '网络空间安全' },
    })
    expect(empty.find('[data-testid="case-a-study-plan-empty"]').exists()).toBe(true)

    const failed = mount(StudyPlanPanel, {
      props: { plan: null, loading: false, error: '后端未配置专业注册表。', majorName: '网络空间安全' },
    })
    const errorNode = failed.get('[data-testid="case-a-study-plan-error"]')
    expect(errorNode.text()).toContain('未配置')
    expect(errorNode.attributes('role')).toBe('alert')
  })

  it('展示专业与培养要求统计（⛔ 不再铺开完整课程列表）', () => {
    const wrapper = mount(StudyPlanPanel, {
      props: {
        plan: studyPlan('network-security', '网络空间安全', 94),
        loading: false,
        error: '',
        majorName: '网络空间安全',
      },
    })
    expect(wrapper.get('[data-testid="case-a-study-plan-major"]').text()).toBe('网络空间安全')
    expect(wrapper.get('[data-testid="case-a-study-plan-total"]').text()).toBe('94')
    expect(wrapper.get('[data-testid="case-a-study-plan-required-count"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="case-a-study-plan-elective-count"]').text()).toBe('2')

    // ⚠️ 任务 4：必修 57 门与选修池 37 门的完整列表已移除，改为统计
    expect(wrapper.find('[data-testid="case-a-study-plan-required-item"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-study-plan-elective-item"]').exists()).toBe(false)

    // ⚠️ 收尾修改：培养方案面板**不再**重复展示匹配结果统计
    //    （那几个数字在下方「补修缺口分析」里已有完整呈现）
    expect(wrapper.find('[data-testid="case-a-study-plan-match-summary"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('与你的成绩单匹配结果')

    // 先修未知的如实说明必须出现
    expect(wrapper.get('[data-testid="case-a-study-plan-prerequisites-note"]').text()).toContain(
      '未提供先修关系',
    )
    // 与"缺口分析"的边界必须写明
    expect(wrapper.get('[data-testid="case-a-study-plan-scope"]').text()).toContain('补修缺口分析')
  })
})

/* -------------------------------------------------------------------------- *
 * 选修学分进度：数字必须来自后端，⛔ 前端不计算
 * -------------------------------------------------------------------------- */

describe('选修学分进度（Phase 4，后端计算）', () => {
  function withProgress(items: ElectiveProgress[]) {
    return mount(StudyPlanPanel, {
      props: {
        plan: studyPlan('network-security', '网络空间安全', 94),
        loading: false,
        error: '',
        majorName: '网络空间安全',
        electiveProgress: items,
      },
    })
  }

  it('直接展示后端下发的 required / earned / remaining', () => {
    const wrapper = withProgress([
      {
        group_id: 'CSE-ELECTIVE-POOL',
        group_name: '专业选修课',
        required_credit: 23,
        earned_credit: 12,
        remaining_credit: 11,
        undecided: false,
      },
    ])
    const value = wrapper.get('[data-testid="case-a-elective-progress-value"]').text()
    expect(value).toContain('要求 23 学分')
    expect(value).toContain('已认定 12 学分')
    expect(value).toContain('还差 11 学分')
    expect(wrapper.get('[data-testid="case-a-elective-progress-item"]').text()).toContain('仍需选修')
  })

  it('remaining 为 0 时标为已满足', () => {
    const wrapper = withProgress([
      {
        group_id: 'G1',
        group_name: '专业选修课',
        required_credit: 0,
        earned_credit: 0,
        remaining_credit: 0,
        undecided: false,
      },
    ])
    expect(wrapper.get('[data-testid="case-a-elective-progress-item"]').text()).toContain('已满足')
  })

  it('⛔ undecided 时如实说明无法确定，不得把 null 显示成 0', () => {
    const wrapper = withProgress([
      {
        group_id: 'G1',
        group_name: '专业选修课',
        required_credit: null,
        earned_credit: null,
        remaining_credit: null,
        undecided: true,
      },
    ])
    const text = wrapper.get('[data-testid="case-a-elective-progress-item"]').text()
    expect(text).toContain('无法从培养方案来源中确定')
    expect(text).toContain('待人工确认')
    // ⛔ 不得出现伪造的 0 学分结论
    expect(text).not.toContain('还差 0 学分')
  })

  it('没有进度数据时不渲染进度块（⛔ 不编造）', () => {
    const wrapper = withProgress([])
    expect(wrapper.find('[data-testid="case-a-elective-progress"]').exists()).toBe(false)
  })

  it('额度口径差异由后端说明（⛔ 前端不硬编码理由）', () => {
    const wrapper = withProgress([
      {
        group_id: 'G1',
        group_name: '专业选修课',
        required_credit: 0,
        earned_credit: 0,
        remaining_credit: 0,
        undecided: false,
        scope_note: '本组课程全部安排在转专业时点之后，因此在转专业时点上没有历史学分要求。',
      },
    ])
    const note = wrapper.get('[data-testid="case-a-elective-progress-scope"]')
    expect(note.text()).toContain('转专业时点之后')
  })

  it('后端没有给 scope_note 时不渲染该说明', () => {
    const wrapper = withProgress([
      {
        group_id: 'G1',
        group_name: '专业选修课',
        required_credit: 23,
        earned_credit: 0,
        remaining_credit: 23,
        undecided: false,
      },
    ])
    expect(wrapper.find('[data-testid="case-a-elective-progress-scope"]').exists()).toBe(false)
  })
})

/* -------------------------------------------------------------------------- *
 * CaseADemoView 的接线
 * -------------------------------------------------------------------------- */

describe('专业选择 → 加载培养方案', () => {
  it('挂载后按当前目标专业加载培养方案，并渲染要求列表', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    expect(loadMajorsApi).toHaveBeenCalled()
    expect(loadStudyPlanApi).toHaveBeenCalledWith('network-security')
    expect(wrapper.find('[data-testid="case-a-study-plan"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="case-a-study-plan-total"]').text()).toBe('94')
  })

  it('下拉选项来自后端专业列表（含两个 major_id）', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    const options = wrapper
      .find('[data-testid="case-a-target-major"]')
      .findAll('option')
      .map((n) => n.text())
    expect(options).toEqual(['网络空间安全', '遥感科学与技术'])
    expect(wrapper.get('[data-testid="case-a-majors-source"]').text()).toContain('后端专业注册表')
  })

  it('切换到另一个专业 → 重新加载**该专业**的培养方案', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()
    expect(wrapper.get('[data-testid="case-a-study-plan-total"]').text()).toBe('94')

    const select = wrapper.get('[data-testid="case-a-target-major"]')
    await select.setValue('遥感科学与技术')
    await flushPromises()

    expect(loadStudyPlanApi).toHaveBeenLastCalledWith('remote-sensing')
    // 培养方案确实变化（不同专业、不同课程数）
    expect(wrapper.get('[data-testid="case-a-study-plan-total"]').text()).toBe('84')
    expect(wrapper.get('[data-testid="case-a-study-plan-major"]').text()).toBe('遥感科学与技术')
  })

  it('后端未配置专业注册表（503）时如实提示，⛔ 不伪造培养方案', async () => {
    loadMajorsApi.mockRejectedValue(
      new StudyPlanApiError('未配置', 503, 'majors_not_configured'),
    )
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    // 专业下拉回退到离线演示选项，页面如实说明
    expect(wrapper.get('[data-testid="case-a-majors-source"]').text()).toContain('不可用')
    // 培养方案面板进入 error 态，并给出**正确原因**（不是"该专业没有数据"）
    const errorNode = wrapper.get('[data-testid="case-a-study-plan-error"]')
    expect(errorNode.text()).toContain('专业注册表不可用')
    // ⛔ 不得渲染任何培养方案内容（不从演示数据补齐）
    expect(wrapper.find('[data-testid="case-a-study-plan-required"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-study-plan-total"]').exists()).toBe(false)
  })

  it('培养方案接口失败时如实报错，⛔ 不用演示数据补齐', async () => {
    loadStudyPlanApi.mockRejectedValue(
      new StudyPlanApiError('该专业不在可用专业列表中。', 404, 'unknown_major'),
    )
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    const errorNode = wrapper.get('[data-testid="case-a-study-plan-error"]')
    expect(errorNode.text()).toContain('不在后端可用专业列表')
    expect(wrapper.find('[data-testid="case-a-study-plan-required"]').exists()).toBe(false)
  })
})
