/**
 * 课表截图导入确认（frontend-only demo）的行为测试。
 *
 * 覆盖：上传成功/失败态、识别候选展示、**必须用户确认**才加入、忽略、重新选择、
 * 以及"确认后的条目是未核验来源"这一安全边界。
 */

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'

import TimetableImageImport from '@/components/TimetableImageImport.vue'

function png(name = 'timetable.png'): File {
  const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, { type: 'image/png' })
  return file
}

async function upload(wrapper: ReturnType<typeof mount>, file: File): Promise<void> {
  const input = wrapper.find('[data-testid="case-a-image-input"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  Object.defineProperty(input.element, 'value', { value: '', configurable: true })
  await input.trigger('change')
  await new Promise((resolve) => setTimeout(resolve, 420))
  await wrapper.vm.$nextTick()
}

describe('课表截图导入确认', () => {
  beforeEach(() => {
    // URL.createObjectURL 在 jsdom 中不存在，桩掉以免预览逻辑报错。
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:demo', configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true })
  })

  it('未选择文件时不显示识别结果', () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    expect(wrapper.find('[data-testid="case-a-image-result"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-image-uploaded"]').exists()).toBe(false)
  })

  it('非图片类型被拒绝，且不产生识别结果', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    const bad = new File([new Uint8Array([1])], 'a.pdf', { type: 'application/pdf' })
    await upload(wrapper, bad)

    expect(wrapper.find('[data-testid="case-a-image-error"]').text()).toContain('PNG')
    expect(wrapper.find('[data-testid="case-a-image-result"]').exists()).toBe(false)
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })

  it('超大图片被拒绝', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    const big = png('big.png')
    Object.defineProperty(big, 'size', { value: 9 * 1024 * 1024, configurable: true })
    await upload(wrapper, big)

    expect(wrapper.find('[data-testid="case-a-image-error"]').text()).toContain('8 MiB')
    expect(wrapper.find('[data-testid="case-a-image-result"]').exists()).toBe(false)
  })

  it('上传成功后展示识别候选（课程/时间/地点）', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())

    expect(wrapper.find('[data-testid="case-a-image-uploaded"]').text()).toContain('上传成功')
    expect(wrapper.find('[data-testid="case-a-image-result"]').exists()).toBe(true)
    const blocks = wrapper.findAll('[data-testid="case-a-image-block"]')
    expect(blocks.length).toBeGreaterThan(0)
    // 演示数据首个候选：网络空间安全导论 · 星期二 7-8节
    expect(wrapper.find('[data-testid="case-a-image-course"]').text()).toContain('网络空间安全导论')
    expect(wrapper.find('[data-testid="case-a-image-time"]').text()).toMatch(/星期二\s*7-8节/)
    expect(wrapper.find('[data-testid="case-a-image-place"]').text()).toContain('深圳校区')
    // 摘要：识别成功约 10 门
    expect(wrapper.find('[data-testid="case-a-image-summary"]').text()).toContain('10')
    expect(wrapper.findAll('[data-testid="case-a-image-block"]').length).toBe(10)
  })

  it('识别结果明确标注为候选、不含课程号与教学班号', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    expect(wrapper.find('[data-testid="case-a-image-result"]').text()).toContain('识别候选')
    expect(wrapper.find('[data-testid="case-a-image-result"]').text()).toContain('不含课程号与教学班号')
  })

  it('确认前不发出任何 confirm（未经确认不进入当前课表）', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })

  it('点击确认后才发出 confirm，且条目为未核验来源', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    await wrapper.find('[data-testid="case-a-image-confirm"]').trigger('click')

    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeTruthy()
    const offering = (emitted as unknown[][])[0][0] as Record<string, unknown>
    // ⛔ 不冒充学校来源、⛔ 不是 real，因此必须走人工确认才能提交。
    expect(offering.source).toBe('image-recognition://timetable-screenshot')
    expect(offering.data_source).toBe('mock')
    expect(offering.course_name).toBe('网络空间安全导论')
    // 确认后该条显示已确认态
    expect(wrapper.find('[data-testid="case-a-image-confirmed"]').text()).toContain('已确认')
  })

  it('确认后不再显示加入按钮（不会重复加入）', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    const before = wrapper.findAll('[data-testid="case-a-image-confirm"]').length
    await wrapper.findAll('[data-testid="case-a-image-confirm"]')[0].trigger('click')
    expect(wrapper.findAll('[data-testid="case-a-image-confirm"]').length).toBe(before - 1)
    expect((wrapper.emitted('confirm') as unknown[][]).length).toBe(1)
  })

  it('确认后可以撤回：已确认条目的忽略会发出 remove', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    await wrapper.findAll('[data-testid="case-a-image-confirm"]')[0].trigger('click')
    expect(wrapper.find('[data-testid="case-a-image-confirmed"]').exists()).toBe(true)

    await wrapper.find('[data-testid="case-a-image-ignore"]').trigger('click')
    expect((wrapper.emitted('remove') as unknown[][]).length).toBe(1)
    expect(wrapper.find('[data-testid="case-a-image-confirmed"]').exists()).toBe(false)
    expect((wrapper.emitted('confirm') as unknown[][]).length).toBe(1)
  })

  it('重新选择图片会撤回已确认条目并清空结果', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    await wrapper.findAll('[data-testid="case-a-image-confirm"]')[0].trigger('click')
    await wrapper.find('[data-testid="case-a-image-clear"]').trigger('click')
    expect((wrapper.emitted('remove') as unknown[][]).length).toBe(1)
    expect(wrapper.find('[data-testid="case-a-image-result"]').exists()).toBe(false)
  })

  it('重新选择图片会清空识别结果', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    expect(wrapper.find('[data-testid="case-a-image-result"]').exists()).toBe(true)
    await wrapper.find('[data-testid="case-a-image-clear"]').trigger('click')
    expect(wrapper.find('[data-testid="case-a-image-result"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-image-uploaded"]').exists()).toBe(false)
  })

  it('第二个候选在确认前保持未确认态', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    const confirms = wrapper.findAll('[data-testid="case-a-image-confirm"]')
    expect(confirms.length).toBeGreaterThan(1)
    await confirms[0].trigger('click')
    // 只剩第二个候选的确认按钮
    expect(wrapper.findAll('[data-testid="case-a-image-confirm"]').length).toBe(confirms.length - 1)
    expect((wrapper.emitted('confirm') as unknown[][]).length).toBe(1)
  })

  // ------------------------------------------------ 未识别课程 → 引导搜索

  it('展示「识别成功 约 10 门」与「未识别 2 门」摘要', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())

    expect(wrapper.find('[data-testid="case-a-image-summary"]').text()).toContain('识别成功')
    expect(wrapper.find('[data-testid="case-a-image-summary"]').text()).toContain('10')
    const summary = wrapper.find('[data-testid="case-a-image-unresolved-summary"]')
    expect(summary.text()).toContain('未识别')
    expect(summary.text()).toContain('2')
  })

  it('未识别区列出两门课程，并如实说明各自原因', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())

    const items = wrapper.findAll('[data-testid="case-a-image-unresolved-item"]')
    expect(items.length).toBe(2)
    const courses = wrapper
      .findAll('[data-testid="case-a-image-unresolved-course"]')
      .map((node) => node.text())
    expect(courses).toEqual(['数据库系统实验', '形势与政策（二）'])
    const reasons = wrapper
      .findAll('[data-testid="case-a-image-unresolved-reason"]')
      .map((node) => node.text())
    expect(reasons[0]).toContain('图片信息不足，无法唯一匹配教学班')
    expect(reasons[1]).toContain('存在多个教学安排，需要人工选择')
    expect(wrapper.find('[data-testid="case-a-image-unresolved"]').text()).toContain(
      '请通过教学班搜索完成选择',
    )
  })

  it('「搜索教学班」只发出 search 事件，⛔ 不自建搜索、⛔ 不直接加入', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())

    const buttons = wrapper.findAll('[data-testid="case-a-image-search"]')
    expect(buttons.length).toBe(2)
    await buttons[0].trigger('click')

    const emitted = wrapper.emitted('search') as unknown[][]
    expect(emitted.length).toBe(1)
    expect(emitted[0][0]).toBe('数据库系统实验')
    // ⛔ 只是把关键词交给父级**已有**搜索；⛔ 不确认、⛔ 不加入课表
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.emitted('remove')).toBeUndefined()
  })

  it('第二个未识别课程发出自己的关键词', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    await wrapper.findAll('[data-testid="case-a-image-search"]')[1].trigger('click')
    expect((wrapper.emitted('search') as unknown[][])[0][0]).toBe('形势与政策（二）')
  })

  it('未识别区与确认/撤回互不影响', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())
    await wrapper.findAll('[data-testid="case-a-image-confirm"]')[0].trigger('click')
    expect(wrapper.find('[data-testid="case-a-image-unresolved"]').exists()).toBe(true)

    await wrapper.find('[data-testid="case-a-image-ignore"]').trigger('click')
    expect((wrapper.emitted('remove') as unknown[][]).length).toBe(1)
    expect(wrapper.findAll('[data-testid="case-a-image-unresolved-item"]').length).toBe(2)
  })

  it('组件内顺序：识别候选 → 未识别区（当前课表由父级插在两者之间）', async () => {
    const wrapper = mount(TimetableImageImport, { props: { semester: '2026-1', selected: [] } })
    await upload(wrapper, png())

    const html = wrapper.html()
    const firstBlock = html.indexOf('case-a-image-block')
    const unresolved = html.indexOf('case-a-image-unresolved')
    expect(firstBlock).toBeGreaterThanOrEqual(0)
    expect(unresolved).toBeGreaterThan(firstBlock)

    // ⚠️ 本组件**不渲染**当前课表：它由父级 `CaseADemoView` 插在
    //    「识别结果」与「未识别区」之间，形成「识别 → 确认 → 课表」闭环。
    expect(wrapper.find('[data-testid="case-a-current-schedule"]').exists()).toBe(false)
  })
})
