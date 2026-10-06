import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import type { CourseOffering } from '@/types/contracts'

const loadCaseAOfferings = vi.fn()
const runCaseADemo = vi.fn()

vi.mock('@/api/caseADemo', () => ({
  loadCaseAOfferings: (...args: unknown[]) => loadCaseAOfferings(...args),
  runCaseADemo: (...args: unknown[]) => runCaseADemo(...args),
}))

function offering(index: number): CourseOffering {
  return {
    course_id: `CS${String(index).padStart(4, '0')}`,
    course_name: index < 22 ? `数据结构 ${index}` : `离散数学 ${index}`,
    class_id: `CLASS-${index}`,
    semester: '2026-1',
    teacher: `教师${index}`,
    meetings: [],
    source: 'capture://case-a',
    data_source: 'real',
  }
}

describe('Case A 学生端页面', () => {
  beforeEach(() => {
    loadCaseAOfferings.mockReset()
    runCaseADemo.mockReset()
    loadCaseAOfferings.mockResolvedValue(Array.from({ length: 4069 }, (_, i) => offering(i)))
  })

  it('中文为主，初始不渲染 4069 条教学班，手工表单默认收起', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    expect(wrapper.text()).toContain('学航·转衔')
    expect(wrapper.text()).toContain('第一步：上传成绩单')
    expect(wrapper.text()).toContain('第二步：填写当前课表')
    expect(wrapper.text()).toContain('第三步：设置排课偏好')
    expect(wrapper.findAll('[data-testid="case-a-search-result"]')).toHaveLength(0)
    expect(wrapper.find('[data-testid="case-a-manual-form"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已加载真实教学班数据：4069 条')
  })

  it('搜索结果最多 20 条，可加入并从当前课表移除', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    const search = wrapper.get('[data-testid="case-a-offering-search"]')
    await search.setValue('数据结构')
    expect(wrapper.findAll('[data-testid="case-a-search-result"]')).toHaveLength(20)

    const firstResult = wrapper.findAll('[data-testid="case-a-search-result"]')[0]
    await firstResult.get('button').trigger('click')
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('我的当前课表（1）')

    await wrapper.get('[data-testid="case-a-current-schedule-item"] button').trigger('click')
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(0)
  })

  it('手工添加区域只在用户主动展开后显示', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    expect(wrapper.find('[data-testid="case-a-manual-form"]').exists()).toBe(false)
    await wrapper.get('[data-testid="case-a-manual-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="case-a-manual-form"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('本人填写，未经学校系统核验')
  })
})
