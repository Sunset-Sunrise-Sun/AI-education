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
const offering: CourseOffering = {
  course_id: 'CSE211', course_name: '网络空间安全导论', class_id: 'CLASS-TEST', semester: '2026-1', credit: 4,
  meetings: [{ weekday: 2, start_section: 7, end_section: 8, weeks: [1, 2], campus: '深圳校区', classroom: '测试教室' }],
  data_source: 'real', source: 'capture://synthetic-test',
}
const response: CaseADemoResponse = {
  transcript: { source_id: 'upload:synthetic', artifact_sha256: 'a'.repeat(64), record_count: 1, term_count: 1, terms: ['2025-1'], pending_course_id_count: 1 },
  makeup_tasks: [{ course_id: 'FL101', course_name: '大学外语', credit: 2, status: 'manual_confirmation', source_evidence: 'case-owner-confirmed://synthetic' }],
  course_offerings: [offering], preference: { preferred_courses: [], avoid_times: [], avoid_cross_campus: false },
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
    await chooseFile(wrapper, 'case-a-image-input', new File(['image'], 'schedule.png', { type: 'image/png' }))
    await vi.advanceTimersByTimeAsync(350)
    await wrapper.findAll('[data-testid="case-a-image-confirm"]')[0].trigger('click')
    expect(wrapper.find('[data-testid="case-a-pending-match"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="case-a-image-import"]').text()).toContain('✓ 已确认识别结果 · 待匹配教学班')
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(0)
    expect(run).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="case-a-image-match"]').trigger('click')
    await wrapper.get('[data-testid="case-a-search-result"]').get('button').trigger('click')
    expect(wrapper.get('[data-testid="case-a-current-schedule"]').text()).toContain('CLASS-TEST')
    await chooseFile(wrapper, 'case-a-pdf', new File(['%PDF'], 'transcript.pdf', { type: 'application/pdf' }))
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()
    expect(run).toHaveBeenCalledTimes(1)
    expect(run.mock.calls[0][0].currentSchedule).toEqual([offering])
    expect(run.mock.calls[0][0].currentSchedule.some((item: CourseOffering) => item.class_id.startsWith('IMAGE-'))).toBe(false)
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(1)
    // ⚠️ 信息架构调整：原「补修缺口分析」大表格已删除，其能力并入卡片式「课程建议与确认」。
    //    现在每门课程只出现一次，确认也只有一个入口。
    for (const text of ['课程建议与确认', '调整建议', '未来学期修读路径', '方案风险提示']) expect(wrapper.text()).toContain(text)
    expect(wrapper.text()).not.toContain('补修缺口分析')
    expect(wrapper.findAll('[data-testid="case-a-confirmations"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="case-a-unresolved-row"]')).toHaveLength(1)
    const originalRequest = JSON.stringify(run.mock.calls[0][0])
    await wrapper.get('[data-testid="case-a-confirmation-checkbox"]').setValue(true)
    await wrapper.get('[data-testid="case-a-confirm-selection"]').trigger('click')
    expect(wrapper.get('[data-testid="case-a-unresolved-status"]').text()).toBe('已确认')
    expect(run).toHaveBeenCalledTimes(1)
    expect(JSON.stringify(run.mock.calls[0][0])).toBe(originalRequest)
    await wrapper.get('[data-testid="case-a-unresolved-details-toggle"]').trigger('click')
    expect(wrapper.text()).not.toMatch(/manual_confirmation|unresolved|sha256|case-owner-confirmed:\/\/|upload:|table:\d|RestrictedPlanner|source_evidence/)
    await wrapper.get('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="case-a-confirmation-count"]').text()).toBe('已选择 0 项 · 已确认 1 项')
    expect(wrapper.get('[data-testid="case-a-confirmation-feedback"]').text()).toContain('重新生成方案后仍会继续显示')
    expect(JSON.stringify(run.mock.calls[1][0])).toBe(originalRequest)
    expect(run.mock.calls[1][0].currentSchedule).toEqual([offering])
    await wrapper.get('[data-testid="case-a-offering-search"]').setValue('网络空间安全导论')
    await wrapper.get('[data-testid="case-a-current-schedule-remove"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="case-a-confirmations"]').exists()).toBe(false)
  })
})
