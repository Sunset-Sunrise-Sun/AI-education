import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CaseADemoView from '@/components/CaseADemoView.vue'
import type { CaseADemoResponse } from '@/api/caseADemo'
import type { CourseOffering } from '@/types/contracts'

const load = vi.fn()
const run = vi.fn()
vi.mock('@/api/caseADemo', async () => ({
  ...await vi.importActual<typeof import('@/api/caseADemo')>('@/api/caseADemo'),
  loadCaseAOfferings: (...args: unknown[]) => load(...args),
  runCaseADemo: (...args: unknown[]) => run(...args),
}))

// 合成接口 fixture，只验证前端流程；真实数据链路由浏览器另行验证。
// ⚠️ 课程名必须与「课表截图识别演示数据」的某个格位一致：
//    父级会把识别结果按 **课程名** 匹配到这里下发的教学班并载入原始课表，
//    同时该课名也是 `case-a-image-match` 触发的搜索关键词。
const offering: CourseOffering = {
  course_id: 'CSE202', course_name: '数据结构与算法', class_id: 'CLASS-TEST', semester: '2026-1', credit: 3,
  meetings: [{ weekday: 1, start_section: 3, end_section: 4, weeks: [1, 2], campus: '深圳校区', classroom: '测试教室' }],
  data_source: 'real', source: 'capture://synthetic-test',
}
const response: CaseADemoResponse = {
  transcript: { source_id: 'upload:synthetic', artifact_sha256: 'a'.repeat(64), record_count: 1, term_count: 1, terms: ['2025-1'], pending_course_id_count: 1 },
  makeup_tasks: [{ course_id: 'FL101', course_name: '大学外语', credit: 2, status: 'manual_confirmation', source_evidence: 'case-owner-confirmed://synthetic' }],
  // ⚠️ 教学班需覆盖培养方案里「成绩单有记录」的必修课，才能产生 need_confirmation 卡片
  course_offerings: [
    offering,
    { ...offering, course_id: 'FL101', course_name: '大学外语（I）', class_id: 'FL-01' },
    {
      ...offering,
      course_id: 'MA179',
      course_name: '线性代数',
      class_id: 'MA-01',
      meetings: [{ weekday: 1, start_section: 3, end_section: 4, weeks: [1, 2], campus: '南校园', classroom: 'A201' }],
    },
    {
      ...offering,
      course_id: 'CSE301',
      course_name: '数据库系统原理',
      class_id: 'DB-01',
      meetings: [{ weekday: 3, start_section: 5, end_section: 6, weeks: [1, 2], campus: '南校园', classroom: 'A301' }],
    },
  ],
  preference: { preferred_courses: [], avoid_times: [], avoid_cross_campus: false },
  plan_result: { status: 'partially_feasible', selected_classes: [{ course_id: 'CSE211', class_id: 'CLASS-TEST' }], changes: [], risks: [{ level: 'medium', reason: '请核对修读期限', course_id: 'FL101' }], unresolved: [{ type: 'manual_confirmation', message: 'FL101 需要核对' }] },
  provenance: { transcript: 'upload:synthetic', curriculum: 'synthetic', course_data: 'capture://synthetic', current_schedule: 'user-selected', planner: 'RestrictedPlanner', is_full_semester: false },
  roadmap: { semesters: [{ semester: '2026-2', required: [], makeup: [{ course_id: 'FL101', course_name: '大学外语', credit: 2 }], elective: [] }] },
}

async function chooseFile(wrapper: ReturnType<typeof mount>, id: string, file: File): Promise<void> {
  const input = wrapper.get(`[data-testid="${id}"]`)
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

describe('Case A 产品流程回归', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() })
    load.mockReset().mockResolvedValue([offering])
    run.mockReset().mockImplementation(async () => structuredClone(response))
  })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it('候选确认不写入课表；选班后生成；本地确认不发请求，旧模块和当前课表保留', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    // ⚠️ 本轮行为：课表开页即载入**用户的原始课表**（课表截图识别结果按课程名
    //    匹配到真实教学班）。本 fixture 的 `数据结构与算法` 正是识别数据的第一个格位，
    //    因此它已被自动载入 —— 这本身就是"未经图片确认、课表不写入"之外的**既有课表**。
    const preloaded = wrapper.findAll('[data-testid="case-a-current-schedule-item"]')
    expect(preloaded.length).toBe(1)
    expect(preloaded[0].text()).toContain('数据结构与算法')

    await chooseFile(wrapper, 'case-a-image-input', new File(['image'], 'schedule.png', { type: 'image/png' }))
    await vi.advanceTimersByTimeAsync(350)
    await wrapper.findAll('[data-testid="case-a-image-confirm"]')[0].trigger('click')
    expect(wrapper.find('[data-testid="case-a-pending-match"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="case-a-image-import"]').text()).toContain('✓ 已确认识别结果 · 待匹配教学班')
    // ⛔ 确认识别候选**不写入课表**：条数不变
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(1)
    expect(run).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="case-a-image-match"]').trigger('click')
    // ⚠️ 该教学班已由「原始课表」自动载入，因此搜索结果里它显示为**已确认 + 撤回**，
    //    而不是「加入当前课表」——这正是既有组件按"是否已在课表"分叉的正确行为。
    expect(wrapper.get('[data-testid="case-a-search-result"]').text()).toContain('CLASS-TEST')
    expect(wrapper.find('[data-testid="case-a-result-confirmed"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="case-a-current-schedule"]').text()).toContain('CLASS-TEST')
    await chooseFile(wrapper, 'case-a-pdf', new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' }))
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()
    expect(run).toHaveBeenCalledTimes(1)
    // ⛔ 同一教学班身份只保留一条（不会因自动载入 + 手动选择而重复）
    expect(run.mock.calls[0][0].currentSchedule).toEqual([offering])
    expect(run.mock.calls[0][0].currentSchedule.some((item: CourseOffering) => item.class_id.startsWith('IMAGE-'))).toBe(false)
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(1)
    // ⚠️ 信息架构调整（本次任务）：拆成三个独立阶段，全部位于课表之前。
    //    旧的结果面板（含「方案风险提示」分区）已不再挂载到本页。
    for (const text of ['补修缺口分析', '推荐选课']) {
      expect(wrapper.text()).toContain(text)
    }
    // ⛔ Phase 7 任务 1：「调整建议」展示已删除（当前未实现教学班调整能力）
    expect(wrapper.text()).not.toContain('调整建议')
    expect(wrapper.find('[data-testid="case-a-makeup-gap"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-recommend"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-weekly-schedule"]').exists()).toBe(true)

    // ① 补修缺口分析：勾选 + 「确认可转换」→ 只改前端状态，⛔ 不发请求
    const originalRequest = JSON.stringify(run.mock.calls[0][0])
    expect(run).toHaveBeenCalledTimes(1)
    const convert = wrapper.findAll('[data-testid="case-a-makeup-convert"]')
    expect(convert.length).toBeGreaterThan(0)
    await convert[0].trigger('click')
    await flushPromises()
    // ⛔ 确认补修不触发新的后端请求
    expect(run).toHaveBeenCalledTimes(1)
    // ⛔ 结果页不消失（这是本次修复的关键）
    expect(wrapper.find('[data-testid="case-a-makeup-gap"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-recommend"]').exists()).toBe(true)

    // ② 推荐选课：加入本学期方案 → 课表实时更新，且 ⛔ 不改请求体
    const addButtons = wrapper.findAll('[data-testid="case-a-recommend-add"]')
    if (addButtons.length > 0) {
      await addButtons[0].trigger('click')
      await flushPromises()
      expect(wrapper.find('[data-testid="case-a-recommend-added"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="case-a-plan-linkage"]').exists()).toBe(true)
    }
    expect(JSON.stringify(run.mock.calls[0][0])).toBe(originalRequest)

    // ⛔ 技术字段不外泄
    expect(wrapper.text()).not.toMatch(
      /manual_confirmation|unresolved|sha256|case-owner-confirmed:\/\/|upload:|table:\d|RestrictedPlanner|source_evidence/,
    )
  })
})
