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
  const dataStructure = index < 22
  return {
    course_id: dataStructure ? 'CS1000' : `CS${String(index).padStart(4, '0')}`,
    course_name: dataStructure ? '数据结构' : `离散数学 ${index}`,
    class_id: `CLASS-${index}`,
    semester: '2026-1',
    teacher: dataStructure ? `教师${index}` : null,
    credit: 3,
    meetings: [{
      weekday: (index % 5) + 1,
      start_section: 3,
      end_section: 4,
      weeks: [1, 2, 3, 4],
      campus: index % 2 === 0 ? '深圳校区' : '南校园',
      classroom: `教室${index}`,
    }],
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
    expect(wrapper.text()).toContain('第三步：告诉我你的选课需求')
    expect(wrapper.findAll('[data-testid="case-a-search-result"]')).toHaveLength(0)
    expect(wrapper.find('[data-testid="case-a-manual-form"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已加载真实教学班数据 4069 条')
  })

  it('同一课程的教学班聚合展示，任课教师可见，结果仍最多 20 条', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    await wrapper.get('[data-testid="case-a-offering-search"]').setValue('数据结构')
    expect(wrapper.findAll('[data-testid="case-a-search-result"]')).toHaveLength(20)
    expect(wrapper.findAll('[data-testid="case-a-course-group"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('任课教师：教师0')
    expect(wrapper.text()).toContain('CS1000')
    expect(wrapper.text()).toContain('3 学分')
  })

  it('支持按任课教师搜索和按校区筛选', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    await wrapper.get('[data-testid="case-a-offering-search"]').setValue('教师3')
    expect(wrapper.findAll('[data-testid="case-a-search-result"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('教学班 CLASS-3')

    await wrapper.get('[data-testid="case-a-offering-search"]').setValue('数据结构')
    await wrapper.get('[data-testid="case-a-campus-filter"]').setValue('深圳校区')
    expect(wrapper.findAll('[data-testid="case-a-search-result"]').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('深圳校区')
  })

  it('可加入并从当前课表移除，已选课表同时显示任课教师', async () => {
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    await wrapper.get('[data-testid="case-a-offering-search"]').setValue('教师0')
    const firstResult = wrapper.get('[data-testid="case-a-search-result"]')
    await firstResult.get('button').trigger('click')
    expect(wrapper.findAll('[data-testid="case-a-current-schedule-item"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('我的当前课表（1）')
    expect(wrapper.get('[data-testid="case-a-current-schedule-item"]').text()).toContain('任课教师：教师0')

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
