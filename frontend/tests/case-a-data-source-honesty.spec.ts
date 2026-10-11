/**
 * R1 修复：Case A 页面的**数据来源与加载状态**必须如实展示。
 *
 * 覆盖架构评审要求的 5 种情况：
 *   1. 成功加载且来源可确认
 *   2. 返回空列表
 *   3. 接口返回 503（运行时未配置）
 *   4. 网络失败
 *   5. 来源信息缺失或未验证
 *
 * 硬约束：
 *   - 任何状态下都不得无条件显示「已加载真实教学班数据」；
 *   - `:mock="false"` 不作为真实性证明；
 *   - 只有 `success` 才允许出现「已加载」字样；
 *   - 503 的提示必须保留，不得静默降级为 Mock。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseADemoView from '@/components/CaseADemoView.vue'
import type { CourseOffering } from '@/types/contracts'

const loadCaseAOfferings = vi.fn()
const runCaseADemo = vi.fn()

// 保留**真实的** CaseAApiError 类：视图用 `instanceof` 判别「未配置」，
// 不能把它一起 mock 掉，否则判别逻辑测不到。
vi.mock('@/api/caseADemo', async () => {
  const actual = await vi.importActual<typeof import('@/api/caseADemo')>('@/api/caseADemo')
  return {
    CaseAApiError: actual.CaseAApiError,
    loadCaseAOfferings: (...args: unknown[]) => loadCaseAOfferings(...args),
    runCaseADemo: (...args: unknown[]) => runCaseADemo(...args),
  }
})

type ApiModule = typeof import('@/api/caseADemo')

async function makeApiError(
  message: string, status: number | null, code: string | null,
): Promise<Error> {
  const actual = await vi.importActual<ApiModule>('@/api/caseADemo')
  return new actual.CaseAApiError(message, status, code)
}

function offering(index: number): CourseOffering {
  return {
    course_id: `CS${String(index).padStart(4, '0')}`,
    course_name: `课程 ${index}`,
    class_id: `CLASS-${index}`,
    semester: '2026-1',
    teacher: null,
    credit: 3,
    meetings: [],
    source: 'capture://case-a',
    data_source: 'real',
  }
}

/**
 * 取出**真正渲染出来的**文本（段落内容）。
 *
 * 避坑记录（我连踩两次）：
 *   1. wrapper.text() 会把模板 <!-- --> 注释算进来，而本组件注释里
 *      **引用**了被移除的旧文案用于解释；
 *   2. element.textContent 又会把 <script> 整段当文本带进来，
 *      而组件源码里也有同样的引用。
 *   ⇒ 先移除 script/style，再取文本。
 */
function visibleText(wrapper: { element: Element }): string {
  const clone = (wrapper.element as HTMLElement).cloneNode(true) as HTMLElement
  clone.querySelectorAll('script, style').forEach((node) => node.remove())
  return clone.textContent ?? ''
}

/** 页面**渲染文本**里是否出现来源认定字样。 */
function claimsAuthenticity(text: string): boolean {
  return /真实教学班|已加载真实|来源已核验|已认证/.test(text)
}

async function uploadTranscript(wrapper: ReturnType<typeof mount>): Promise<void> {
  const pdf = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], 'a.pdf', {
    type: 'application/pdf',
  })
  Object.defineProperty(pdf, 'size', { value: 8, configurable: true })
  const input = wrapper.find('[data-testid="case-a-pdf"]')
  Object.defineProperty(input.element, 'files', { value: [pdf], configurable: true })
  await input.trigger('change')
}

describe('R1：数据来源与加载状态如实展示', () => {
  beforeEach(() => {
    loadCaseAOfferings.mockReset()
    runCaseADemo.mockReset()
  })

  it('① 成功加载：显示已加载教学班数据 N 条，但不认定来源真实性', async () => {
    loadCaseAOfferings.mockResolvedValue([offering(1), offering(2)])
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    expect(wrapper.text()).toContain('已加载教学班数据 2 条')
    // 该接口是裸数组、无来源字段，不得做真实性认定
    expect(claimsAuthenticity(visibleText(wrapper))).toBe(false)

    const tag = wrapper.find('[data-testid="case-a-offerings-tag"]')
    expect(tag.text()).toBe('已加载教学班数据')
    expect(tag.classes()).toContain('tag--source-real')
  })

  it('② 空列表：仍算成功，不显示已加载真实，也不谎报条数', async () => {
    loadCaseAOfferings.mockResolvedValue([])
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    // 空不等于失败：接口确实答复了
    expect(wrapper.text()).toContain('已加载教学班数据 0 条')
    expect(claimsAuthenticity(visibleText(wrapper))).toBe(false)
    expect(wrapper.find('[data-testid="case-a-offerings-tag"]').text()).toBe(
      '已加载教学班数据',
    )
    // 空列表不得被说成不可用
    expect(wrapper.text()).not.toContain('教学班数据不可用')
  })

  it('③ 503 运行时未配置：如实提示，不显示已加载，不降级为 Mock', async () => {
    loadCaseAOfferings.mockRejectedValue(
      await makeApiError(
        'Case A demo request failed (HTTP 503).', 503, 'case_a_demo_not_configured',
      ),
    )
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    // 绝不出现「已加载」
    expect(wrapper.text()).not.toContain('已加载教学班数据')
    expect(claimsAuthenticity(visibleText(wrapper))).toBe(false)

    const tag = wrapper.find('[data-testid="case-a-offerings-tag"]')
    expect(tag.text()).toBe('教学班数据未配置')
    expect(tag.classes()).not.toContain('tag--source-real')

    // 503 提示保留
    expect(wrapper.text()).toContain('503')
    expect(wrapper.text()).toContain('尚未配置')
    expect(wrapper.text()).toContain('教学班数据运行时未配置')
    // 不得静默降级成 Mock
    expect(wrapper.text()).not.toContain('Mock 数据')
  })

  it('④ 网络失败：如实标为不可用，不显示已加载', async () => {
    loadCaseAOfferings.mockRejectedValue(
      await makeApiError('教学班数据请求失败：无法连接后端。', null, null),
    )
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    expect(wrapper.text()).not.toContain('已加载教学班数据')
    expect(claimsAuthenticity(visibleText(wrapper))).toBe(false)

    const tag = wrapper.find('[data-testid="case-a-offerings-tag"]')
    expect(tag.text()).toBe('教学班数据不可用')
    expect(tag.classes()).not.toContain('tag--source-real')
    expect(wrapper.text()).toContain('无法连接后端')
    expect(wrapper.text()).toContain('教学班数据加载失败')
  })

  it('⑤ 来源信息缺失或未验证：使用中性表述，不虚构来源认证', async () => {
    loadCaseAOfferings.mockResolvedValue([offering(1)])
    const wrapper = mount(CaseADemoView)
    await flushPromises()

    expect(claimsAuthenticity(visibleText(wrapper))).toBe(false)
    for (const banned of ['已核验', '已认证', '官方来源', '来源可信']) {
      expect(wrapper.text()).not.toContain(banned)
    }
    // 也不虚构来源：未加载规划结果时不该出现 provenance 值
    expect(wrapper.text()).not.toContain('case-scoped')
  })

  it('规划结果里有 provenance 时才展示来源（依据响应字段）', async () => {
    loadCaseAOfferings.mockResolvedValue([offering(1)])
    runCaseADemo.mockResolvedValue({
      transcript: {
        source_id: 's',
        artifact_sha256: 'a',
        record_count: 1,
        term_count: 1,
        terms: ['2025-1'],
        pending_course_id_count: 0,
      },
      makeup_tasks: [],
      course_offerings: [offering(1)],
      preference: {
        max_credit: null,
        avoid_cross_campus: false,
        preferred_courses: [],
        avoid_times: [],
        notes: null,
      },
      plan_result: {
        status: 'feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unsolved: [],
      },
      provenance: {
        transcript: 'user-uploaded SYSU transcript PDF',
        curriculum: 'case-a-curriculum',
        course_data: 'case-scoped:south+shenzhen',
        current_schedule: 'user-confirmed',
        planner: 'RestrictedPlanner',
        is_full_semester: false,
      },
    })

    const wrapper = mount(CaseADemoView)
    await flushPromises()
    await uploadTranscript(wrapper)
    await wrapper.find('[data-testid="case-a-submit"]').trigger('click')
    await flushPromises()

    const source = wrapper.find('[data-testid="case-a-plan-course-data-source"]')
    expect(source.exists()).toBe(true)
    expect(source.text()).toContain('case-scoped:south+shenzhen')

    // 即便有 provenance，也不出现前端自行加的真实性认定
    expect(visibleText(wrapper)).not.toContain('真实教学班')
    // 结果区不再写死神秘数字
    expect(wrapper.text()).not.toContain('4069 条教学班')
  })
})
