/**
 * Case A 两处最小增量改动的测试：
 *   §1 第一步之前新增「原专业 / 目标专业」下拉框（仅两个样本专业，⛔ 不可相同）
 *   §2 第二步「上传课表截图，辅助识别」补齐为真实的上传 / 预览 / 移除 / 待识别
 *
 * ⚠️ 边界：⛔ 不产生任何识别结果；⛔ 不发任何请求；⛔ 不改变 current_schedule 的写入途径。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import CurrentScheduleEditor from '@/components/CurrentScheduleEditor.vue'
import { SAMPLE_MAJOR_OPTIONS } from '@/config'
import {
  DEFAULT_PLAN_YEAR,
  FUTURE_PLAN_YEARS,
  SUPPORTED_PLAN_YEARS,
  deriveTransferType,
  describePlanYearPair,
  bothPlanYearsSupported,
} from '@/utils/planYear'

/** 造一个合法的 PNG 文件（jsdom 不校验内容，只校验我们自己的类型/大小逻辑）。 */
function makePng(name = 'schedule.png', bytes = 2048): File {
  const file = new File([new Uint8Array(8)], name, { type: 'image/png' })
  Object.defineProperty(file, 'size', { value: bytes, configurable: true })
  return file
}

function makeFile(name: string, type: string, size: number): File {
  const file = new File([new Uint8Array(8)], name, { type })
  Object.defineProperty(file, 'size', { value: size, configurable: true })
  return file
}

function ensureObjectUrl(): void {
  if (!('createObjectURL' in URL)) {
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:mock', configurable: true })
  }
  if (!('revokeObjectURL' in URL)) {
    Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true })
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

/* ------------------------------------------------------------------ *
 * §2 课表截图上传
 * ------------------------------------------------------------------ */

function mountEditor() {
  return mount(CurrentScheduleEditor, {
    props: { offerings: [], currentSchedule: [], semester: '2026-1' },
  })
}

async function openDialog(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('[data-testid="case-a-screenshot-entry"]').trigger('click')
  await flushPromises()
  return wrapper.find('[data-testid="case-a-screenshot-dialog"]')
}

async function chooseShot(wrapper: ReturnType<typeof mount>, file: File) {
  const input = wrapper.find('[data-testid="case-a-screenshot-input"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  Object.defineProperty(input.element, 'value', { value: '', writable: true, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

describe('§2 课表截图：上传 / 预览 / 移除 / 待识别', () => {
  it('入口文案与弹窗保持原样（复用既有入口，⛔ 未改文案）', async () => {
    const wrapper = mountEditor()
    const entry = wrapper.find('[data-testid="case-a-screenshot-entry"]')
    expect(entry.exists()).toBe(true)
    expect(entry.text()).toBe('上传课表截图，辅助识别')

    const dialog = await openDialog(wrapper)
    expect(dialog.exists()).toBe(true)
  })

  it('选择合法 PNG：显示文件名、大小、预览与「待识别」', async () => {
    ensureObjectUrl()
    const wrapper = mountEditor()
    await openDialog(wrapper)
    await chooseShot(wrapper, makePng('my-timetable.png', 4096))

    const name = wrapper.find('[data-testid="case-a-screenshot-name"]')
    expect(name.exists()).toBe(true)
    expect(name.text()).toContain('my-timetable.png')
    expect(name.text()).toContain('仅本地预览，未上传、未解析')

    expect(wrapper.find('[data-testid="case-a-screenshot-preview"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-screenshot-preview"] img').exists()).toBe(true)

    const status = wrapper.find('[data-testid="case-a-screenshot-status"]')
    expect(status.exists()).toBe(true)
    expect(status.text()).toContain('待识别')
    expect(status.text()).toContain('尚未接入图片识别服务')
  })

  it('⛔ 全程不发任何请求（截图只在本地处理）', async () => {
    ensureObjectUrl()
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const wrapper = mountEditor()
    await openDialog(wrapper)
    await chooseShot(wrapper, makePng())
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('⛔ 不出现任何识别结论，也⛔ 不自动加入当前课表', async () => {
    ensureObjectUrl()
    const wrapper = mountEditor()
    await openDialog(wrapper)
    await chooseShot(wrapper, makePng())

    const text = wrapper.text()
    for (const forbidden of ['识别成功', '已识别出', '解析完成', '识别结果：']) {
      expect(text, `出现不应有的识别结论：${forbidden}`).not.toContain(forbidden)
    }
    // ⛔ 选截图不会改动 current_schedule
    expect(wrapper.emitted('update:currentSchedule')).toBeFalsy()
  })

  it('错误输入：非图片类型被拒，且不产生预览与状态', async () => {
    const wrapper = mountEditor()
    await openDialog(wrapper)
    await chooseShot(wrapper, makeFile('grades.pdf', 'application/pdf', 1000))

    const error = wrapper.find('[data-testid="case-a-screenshot-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('仅支持 PNG / JPEG / WebP')
    expect(wrapper.find('[data-testid="case-a-screenshot-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-screenshot-status"]').exists()).toBe(false)
  })

  it('边界：超过 8 MiB 的图片被拒', async () => {
    const wrapper = mountEditor()
    await openDialog(wrapper)
    await chooseShot(wrapper, makeFile('huge.png', 'image/png', 9 * 1024 * 1024))
    const error = wrapper.find('[data-testid="case-a-screenshot-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('8 MiB')
  })

  it('移除截图后回到空态', async () => {
    ensureObjectUrl()
    const wrapper = mountEditor()
    await openDialog(wrapper)
    await chooseShot(wrapper, makePng())
    expect(wrapper.find('[data-testid="case-a-screenshot-status"]').exists()).toBe(true)

    await wrapper.find('[data-testid="case-a-screenshot-remove"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="case-a-screenshot-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-screenshot-status"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-screenshot-empty"]').exists()).toBe(true)
  })

  it('空输入：未选文件时只有空态提示', async () => {
    const wrapper = mountEditor()
    await openDialog(wrapper)
    expect(wrapper.find('[data-testid="case-a-screenshot-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-screenshot-name"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="case-a-screenshot-remove"]').exists()).toBe(false)
  })

  it('关闭弹窗后重新打开，状态仍可用（不残留错误）', async () => {
    const wrapper = mountEditor()
    await openDialog(wrapper)
    await chooseShot(wrapper, makeFile('bad.gif', 'image/gif', 10))
    expect(wrapper.find('[data-testid="case-a-screenshot-error"]').exists()).toBe(true)

    await wrapper.find('[data-testid="case-a-screenshot-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="case-a-screenshot-dialog"]').exists()).toBe(false)

    await openDialog(wrapper)
    expect(wrapper.find('[data-testid="case-a-screenshot-error"]').exists()).toBe(false)
  })

  it('⛔ 手动搜索加入与手工添加入口未受影响', async () => {
    const wrapper = mountEditor()
    // 搜索面板与手工添加入口由父组件承载；这里确认本组件仍渲染搜索区
    expect(wrapper.find('.cse__search-panel').exists()).toBe(true)
  })
})

/* ------------------------------------------------------------------ *
 * §1 原专业 / 目标专业下拉框
 * ------------------------------------------------------------------ */

describe('§1 原专业 / 目标专业下拉框', () => {
  /**
   * 直接挂载 Case A 视图。
   *
   * loadCaseAOfferings 的响应形状是**顶层数组** CourseOffering[]
   * （见 api/caseADemo.ts 的 checkedJson<CourseOffering[]>），
   * 不是 { offerings: [...] } —— 一开始我 mock 错了形状，
   * 导致 offerings prop 收到对象、组件渲染报错。
   */
  function mountView() {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })),
    )
    return mount(CaseADemoView)
  }

  it('两个专业都是 <select>，且仅两个样本专业', async () => {
    const wrapper = mountView()
    await flushPromises()

    for (const testid of ['case-a-origin-major', 'case-a-target-major']) {
      const el = wrapper.find(`[data-testid="${testid}"]`)
      expect(el.exists(), `${testid} 不存在`).toBe(true)
      expect(el.element.tagName).toBe('SELECT')
      const values = el.findAll('option').map((o) => o.attributes('value'))
      expect(values).toEqual(['网络空间安全', '遥感科学与技术'])
      expect(el.findAll('option')).toHaveLength(2)
    }
    expect(SAMPLE_MAJOR_OPTIONS.map((m) => m.value)).toEqual([
      '网络空间安全',
      '遥感科学与技术',
    ])
  })

  it('默认值沿用 Case A 上下文', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(
      (wrapper.find('[data-testid="case-a-origin-major"]').element as HTMLSelectElement).value,
    ).toBe('遥感科学与技术')
    expect(
      (wrapper.find('[data-testid="case-a-target-major"]').element as HTMLSelectElement).value,
    ).toBe('网络空间安全')
  })

  it('⛔ 不允许选成相同专业：被对方占用的选项为 disabled', async () => {
    const wrapper = mountView()
    await flushPromises()

    // 目标专业已选「网络空间安全」⇒ 原专业的该选项必须 disabled
    const originOptions = wrapper.find('[data-testid="case-a-origin-major"]').findAll('option')
    const originNetwork = originOptions.find((o) => o.attributes('value') === '网络空间安全')!
    const originRemote = originOptions.find(
      (o) => o.attributes('value') === '遥感科学与技术',
    )!
    expect(originNetwork.attributes('disabled')).toBeDefined()
    expect(originRemote.attributes('disabled')).toBeUndefined()

    // 原专业已选「遥感科学与技术」⇒ 目标专业的该选项必须 disabled
    const targetOptions = wrapper.find('[data-testid="case-a-target-major"]').findAll('option')
    const targetRemote = targetOptions.find(
      (o) => o.attributes('value') === '遥感科学与技术',
    )!
    const targetNetwork = targetOptions.find((o) => o.attributes('value') === '网络空间安全')!
    expect(targetRemote.attributes('disabled')).toBeDefined()
    expect(targetNetwork.attributes('disabled')).toBeUndefined()
  })

  it('切换原专业后，目标专业的禁用项随之联动', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-testid="case-a-origin-major"]').setValue('网络空间安全')
    await flushPromises()

    // 现在原专业 = 网络空间安全 ⇒ 目标专业的「网络空间安全」应 disabled
    const targetOptions = wrapper.find('[data-testid="case-a-target-major"]').findAll('option')
    const targetNetwork = targetOptions.find((o) => o.attributes('value') === '网络空间安全')!
    expect(targetNetwork.attributes('disabled')).toBeDefined()
    // 而原专业的「网络空间安全」也应 disabled（目标专业当前就是它）
    const originOptions = wrapper.find('[data-testid="case-a-origin-major"]').findAll('option')
    const originNetworkNow = originOptions.find(
      (o) => o.attributes('value') === '网络空间安全',
    )!
    expect(originNetworkNow.attributes('disabled')).toBeDefined()
  })

  it('位置在「第一步：上传成绩单」之前', async () => {
    const wrapper = mountView()
    await flushPromises()
    const html = wrapper.html()
    const majorsIndex = html.indexOf('case-a-majors')
    const step1Index = html.indexOf('第一步：上传成绩单')
    expect(majorsIndex).toBeGreaterThan(-1)
    expect(step1Index).toBeGreaterThan(-1)
    expect(step1Index).toBeGreaterThan(majorsIndex)
  })

  it('如实说明范围与"不能相同"', async () => {
    const wrapper = mountView()
    await flushPromises()
    const note = wrapper.find('[data-testid="case-a-majors-scope"]')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('两个样本专业')
    expect(note.text()).toContain('不能相同')
  })

  it('⛔ 未破坏三步向导与手工添加入口', async () => {
    const wrapper = mountView()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('第一步：上传成绩单')
    expect(text).toContain('第二步：填写当前课表')
    expect(text).toContain('第三步：告诉我你的选课需求')
    expect(text).toContain('上传课表截图，辅助识别')
    expect(wrapper.find('[data-testid="case-a-manual-toggle"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-pdf"]').exists()).toBe(true)
  })
})

/* ------------------------------------------------------------------ *
 * §3 培养方案年级（原专业 / 目标专业各一个，独立保存）
 * ------------------------------------------------------------------ */

describe('§3 培养方案年级', () => {
  function mountView() {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })),
    )
    return mount(CaseADemoView)
  }

  it('两个年级字段都存在、都是 <select>、默认均为 2025 级', async () => {
    const wrapper = mountView()
    await flushPromises()

    for (const testid of ['case-a-origin-plan-year', 'case-a-target-plan-year']) {
      const el = wrapper.find(`[data-testid="${testid}"]`)
      expect(el.exists(), `${testid} 不存在`).toBe(true)
      expect(el.element.tagName).toBe('SELECT')
      expect((el.element as HTMLSelectElement).value).toBe(DEFAULT_PLAN_YEAR)
    }
  })

  it('两个年级字段是**各自独立**的节点，⛔ 不共用同一个字段', async () => {
    const wrapper = mountView()
    await flushPromises()

    const a = wrapper.find('[data-testid="case-a-origin-plan-year"]').element
    const b = wrapper.find('[data-testid="case-a-target-plan-year"]').element
    expect(a).not.toBe(b)

    // 切换原专业年级⛔ 不得连带改动目标专业年级
    await wrapper.find('[data-testid="case-a-origin-plan-year"]').setValue('2025级')
    await flushPromises()
    expect(
      (wrapper.find('[data-testid="case-a-target-plan-year"]').element as HTMLSelectElement).value,
    ).toBe(DEFAULT_PLAN_YEAR)
  })

  it('本轮**只启用 2025 级**：⛔ 不把 2026 级渲染成可选项', async () => {
    const wrapper = mountView()
    await flushPromises()

    for (const testid of ['case-a-origin-plan-year', 'case-a-target-plan-year']) {
      const values = wrapper
        .find(`[data-testid="${testid}"]`)
        .findAll('option')
        .map((o) => o.attributes('value'))
      expect(values).toEqual(['2025级'])
      // ⛔ 2026 级不在可选项里（不假装该年级培养方案已存在）
      expect(values).not.toContain('2026级')
    }
  })

  it('SUPPORTED_PLAN_YEARS 只含 2025 级；2026 级仅作未来占位', () => {
    expect([...SUPPORTED_PLAN_YEARS]).toEqual(['2025级'])
    expect([...FUTURE_PLAN_YEARS]).toContain('2026级')
    expect(bothPlanYearsSupported('2025级', '2025级')).toBe(true)
    expect(bothPlanYearsSupported('2025级', '2026级')).toBe(false)
    expect(bothPlanYearsSupported('2026级', '2026级')).toBe(false)
  })

  it('纯函数：平转 / 降转 / 升级 的归类与摘要正确', () => {
    expect(deriveTransferType('2025级', '2025级')).toBe('同级转专业')
    expect(deriveTransferType('2025级', '2026级')).toBe('降级转专业')
    expect(deriveTransferType('2026级', '2025级')).toBe('升级转专业')

    expect(describePlanYearPair('2025级', '2025级')).toBe('2025级 平转 2025级')
    expect(describePlanYearPair('2025级', '2026级')).toBe('2025级 降转 2026级')
  })

  it('卡片底部显示转专业类型、路径摘要与如实的数据范围说明', async () => {
    const wrapper = mountView()
    await flushPromises()

    const type = wrapper.find('[data-testid="case-a-transfer-type-label"]')
    expect(type.exists()).toBe(true)
    expect(type.text()).toBe('同级转专业')

    const scope = wrapper.find('[data-testid="case-a-plan-year-scope"]')
    expect(scope.text()).toContain('2025 → 2025')
    expect(scope.text()).toContain('遥感科学与技术')
    expect(scope.text()).toContain('网络空间安全')

    expect(wrapper.find('[data-testid="case-a-plan-year-pair"]').text()).toBe('2025级 平转 2025级')

    const note = wrapper.find('[data-testid="case-a-plan-year-note"]')
    expect(note.text()).toContain('仅支持')
    expect(note.text()).toContain('2025 级')
    expect(note.text()).toContain('需要补充相应数据')

    // ⚠️ 所选年级都有数据 ⇒ ⛔ 不显示"缺数据"警告
    expect(wrapper.find('[data-testid="case-a-plan-year-unsupported"]').exists()).toBe(false)
  })

  it('⛔ 不把培养方案年级和转入学期混为一谈', async () => {
    const wrapper = mountView()
    await flushPromises()
    // 卡片内⛔ 不出现"转入学期"字样（它是另一个概念，本轮不展示也不改动）
    const card = wrapper.find('[data-testid="case-a-majors"]')
    expect(card.text()).not.toContain('转入学期')
    // 两个年级字段的 testid 与 transferTerm 不同
    expect(wrapper.find('[data-testid="case-a-origin-plan-year"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-a-transfer-term"]').exists()).toBe(false)
  })

  it('⛔ 年级字段不进入真实规划请求（后端不支持）', async () => {
    // buildRealPlanRequest 只发 semester / current_schedule / preference
    const stateModule = await import('@/state/userInput')
    const form = stateModule.createDefaultUserInputForm()
    const request = stateModule.buildRealPlanRequest(form)
    const serialized = JSON.stringify(request)
    expect(serialized).not.toContain('PlanYear')
    expect(serialized).not.toContain('2025级')
    expect(Object.keys(request).sort()).toEqual(['current_schedule', 'preference', 'semester'])
  })

  it('⛔ 未破坏专业下拉与不能相同规则', async () => {
    const wrapper = mountView()
    await flushPromises()
    const originOptions = wrapper.find('[data-testid="case-a-origin-major"]').findAll('option')
    const network = originOptions.find((o) => o.attributes('value') === '网络空间安全')!
    expect(network.attributes('disabled')).toBeDefined()
  })
})
