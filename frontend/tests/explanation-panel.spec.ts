/**
 * 「查看依据 / 为什么这样安排」解释面板测试。
 *
 * 关键要求：
 * - 解释文本只来自后端：panel **不自行生成**任何解释；
 * - 未启用 / 请求失败 / 无条目 / 大量文本都有清楚反馈；
 * - 生成方式如实标注：`rule_based_template` 必须显示为「规则模板（非 AI）」；
 * - 证据必须显示来源对象.字段，且「上下文不存在」与「空字符串」区分开；
 * - 请求体只含 `plan_result` / `makeup_tasks` / `course_offerings` 三个键。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ExplanationPanel from '@/components/ExplanationPanel.vue'

const PLAN_RESULT = {
  status: 'partially_feasible',
  selected_classes: [{ course_id: 'C1', class_id: 'C1-01' }],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: '演示摘要',
}

const MAKEUP_TASKS = [
  {
    course_id: 'C1',
    course_name: '课程 C1',
    credit: 3,
    status: 'required',
    reason: '新培养方案必修',
    source_evidence: 'mock://curriculum/C1（演示数据）',
  },
]

const COURSE_OFFERINGS = [
  {
    course_id: 'C1',
    course_name: '课程 C1',
    class_id: 'C1-01',
    semester: '2026-1',
    meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2] }],
    data_source: 'mock',
  },
]

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

function payload(overrides: Record<string, unknown> = {}) {
  return {
    contract_version: 'explanation-v1',
    plan_result_digest: 'a'.repeat(64),
    context_digest: 'b'.repeat(64),
    generation: {
      generator_kind: 'rule_based_template',
      model_configured: false,
      model_id: null,
      fallback_reason: null,
      disclaimer: '本解释由**确定性规则模板**生成：没有调用任何 AI 模型。',
    },
    source_summary: {
      plan_result_digest: 'a'.repeat(64),
      context_digest: 'b'.repeat(64),
      makeup_task_count: 1,
      course_offering_count: 1,
      contains_mock_marker: true,
      contains_real_offering: false,
      notes: ['本次解释引用的补修任务包含演示数据标记（Mock）。'],
    },
    warnings: [],
    items: [
      {
        item_id: 'makeup_task:C1',
        kind: 'makeup_task',
        code: 'makeup_status_required',
        target_course_id: 'C1',
        target_class_id: null,
        title: '课程 C1（C1）为什么是这个补修判定',
        answer: '按目标培养方案要求，这门课被判定为需要补修。',
        strong_evidence: [
          {
            kind: 'confirmed_rule',
            strength: 'confirmed',
            source_object: 'MakeupTask',
            source_field: 'status',
            raw_value: 'required',
            note: 'Curriculum 模块输出的判定状态；本解释不改写该判定。',
          },
          {
            kind: 'absent',
            strength: 'absent',
            source_object: 'MakeupTask',
            source_field: 'prerequisites',
            raw_value: '',
            note: '该补修任务没有声明先修课程；这不等于确认「没有先修要求」。',
          },
        ],
        premise_evidence: [],
        requires_human_confirmation: [
          { reason: '没有先修课程声明时，不能据此确认「不存在先修要求」。', evidence: null },
        ],
        generation: {
          generator_kind: 'rule_based_template',
          model_configured: false,
          model_id: null,
          fallback_reason: null,
          disclaimer: '规则模板生成。',
        },
      },
    ],
    ...overrides,
  }
}

function mountPanel(props: Record<string, unknown> = {}, body: unknown = payload()) {
  const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(body)))
  vi.stubGlobal('fetch', fetchMock)

  const wrapper = mount(ExplanationPanel, {
    props: {
      planResult: PLAN_RESULT,
      makeupTasks: MAKEUP_TASKS,
      courseOfferings: COURSE_OFFERINGS,
      enabled: true,
      ...props,
    },
  })

  return { wrapper, fetchMock }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('解释面板：正常展示', () => {
  it('展示解释文本、生成方式（规则模板，非 AI）与被解释方案指纹', async () => {
    const { wrapper } = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('按目标培养方案要求，这门课被判定为需要补修。')
    expect(wrapper.find('[data-testid="explanation-generator"]').text()).toBe('规则模板（非 AI）')
    expect(wrapper.find('[data-testid="explanation-plan-digest"]').text()).toContain('aaaaaaaaaaaa')
    expect(wrapper.text()).not.toContain('AI 模型生成')
  })

  it('展示来源字段与原始取值，并区分「上下文不存在」与空字符串', async () => {
    const { wrapper } = mountPanel()
    await flushPromises()

    const evidence = wrapper.find('[data-testid="explanation-strong-evidence"]')
    expect(evidence.text()).toContain('MakeupTask.status')
    expect(evidence.text()).toContain('required')
    expect(evidence.text()).toContain('确证规则')
    // absent 字段
    expect(evidence.text()).toContain('MakeupTask.prerequisites')
    expect(evidence.text()).toContain('上下文不存在')
    expect(evidence.text()).toContain('该字段在当前上下文中不存在')
  })

  it('展示待人工确认事项与来源概况（Mock 标记）', async () => {
    const { wrapper } = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-confirmations"]').text()).toContain(
      '不存在先修要求',
    )
    expect(wrapper.find('[data-testid="explanation-contains-mock"]').text()).toBe('是')
    expect(wrapper.find('[data-testid="explanation-sources"]').text()).toContain('补修任务上下文：1')
    expect(wrapper.find('[data-testid="explanation-source-notes"]').text()).toContain('Mock')
  })

  it('展示后端给出的一致性提示（数据不一致时不会被静默忽略）', async () => {
    const body = payload({
      warnings: ['方案中的教学班 C9/C9-99 不在解释上下文的教学班列表中。'],
    })
    const { wrapper } = mountPanel({}, body)
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-warnings"]').text()).toContain(
      'C9/C9-99 不在解释上下文的教学班列表中',
    )
  })

  it('请求体只发送三个字段，且不包含任何个人身份信息', async () => {
    const { fetchMock } = mountPanel()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/api/v1/explanation/plan')
    expect(init.method).toBe('POST')

    const body = JSON.parse(init.body as string)
    expect(Object.keys(body).sort()).toEqual([
      'course_offerings',
      'makeup_tasks',
      'plan_result',
    ])

    // ⛔ 不得出现任何个人身份 / 成绩字段（只用**精确键名**判断，
    //    避免把合法的 `course_name` 误伤成个人信息）。
    const bannedKeys = ['student_id', 'student_name', 'name', 'score', 'grade', 'gpa', 'id_card']
    const keys = new Set<string>()
    const collect = (value: unknown): void => {
      if (Array.isArray(value)) {
        value.forEach(collect)
        return
      }
      if (value !== null && typeof value === 'object') {
        for (const [key, child] of Object.entries(value)) {
          keys.add(key)
          collect(child)
        }
      }
    }
    collect(body)

    for (const banned of bannedKeys) {
      expect([...keys]).not.toContain(banned)
    }
  })
})

describe('解释面板：降级与生成方式标注', () => {
  it('模型未采用时如实显示降级原因，不把模板说成 AI', async () => {
    const body = payload({
      generation: {
        generator_kind: 'model_unavailable_fell_back_to_template',
        model_configured: true,
        model_id: 'test-model',
        fallback_reason: '模型输出未通过事实绑定校验（模型输出引入了事实目录之外的数量信息）',
        disclaimer: '已配置的 AI 模型本次**未被采用**，本条解释已降级为**确定性规则模板**。',
      },
    })
    const { wrapper } = mountPanel({}, body)
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-generator"]').text()).toBe(
      '规则模板（模型未采用）',
    )
    expect(wrapper.find('[data-testid="explanation-fallback-reason"]').text()).toContain(
      '未通过事实绑定校验',
    )
  })

  it('后端声明模型生成时才显示 AI 模型生成', async () => {
    const body = payload({
      generation: {
        generator_kind: 'model',
        model_configured: true,
        model_id: 'test-model',
        fallback_reason: null,
        disclaimer: '本解释的文本部分由已配置的 AI 模型润色生成。',
      },
    })
    const { wrapper } = mountPanel({}, body)
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-generator"]').text()).toBe('AI 模型生成')
  })
})

describe('解释面板：失败与边界', () => {
  it('未启用时不发出任何请求，并明确说明不会自行生成解释', async () => {
    const { wrapper, fetchMock } = mountPanel({ enabled: false })
    await flushPromises()

    expect(fetchMock).not.toHaveBeenCalled()
    const error = wrapper.find('[data-testid="explanation-error"]')
    expect(error.exists()).toBe(true)
    expect(wrapper.find('[data-testid="explanation-error-kind"]').text()).toBe('disabled')
    expect(error.text()).toContain('不会自行生成解释文本')
  })

  it('请求失败（500）时显示安全提示，不显示任何伪造解释', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('boom', { status: 500 }))),
    )

    const wrapper = mount(ExplanationPanel, {
      props: {
        planResult: PLAN_RESULT,
        makeupTasks: MAKEUP_TASKS,
        courseOfferings: COURSE_OFFERINGS,
        enabled: true,
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-error-kind"]').text()).toBe('server')
    expect(wrapper.text()).not.toContain('按目标培养方案要求')
    expect(wrapper.find('[data-testid="explanation-answer"]').exists()).toBe(false)
  })

  it('网络失败时显示网络错误类型', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('failed to fetch'))))

    const wrapper = mount(ExplanationPanel, {
      props: {
        planResult: PLAN_RESULT,
        makeupTasks: MAKEUP_TASKS,
        courseOfferings: COURSE_OFFERINGS,
        enabled: true,
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-error-kind"]').text()).toBe('network')
  })

  it('返回结构不符合契约时停止渲染（不猜测缺失字段）', async () => {
    const { wrapper } = mountPanel({}, { contract_version: 'explanation-v1' })
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-error-kind"]').text()).toBe('unexpected')
    expect(wrapper.find('[data-testid="explanation-empty"]').exists()).toBe(false)
  })

  it('返回条目为空时明确说明"没有条目"不等于任何排课结论', async () => {
    const { wrapper } = mountPanel({}, payload({ items: [] }))
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-empty"]').text()).toContain('不构成任何排课结论')
  })

  it('聚焦某个课程时只显示该课程的条目', async () => {
    const body = payload({
      items: [
        ...payload().items,
        {
          ...payload().items[0],
          item_id: 'makeup_task:C2',
          target_course_id: 'C2',
          title: 'C2 的判定',
          answer: 'C2 的答案文本',
        },
      ],
    })
    const { wrapper } = mountPanel({ focusCourseId: 'C2' }, body)
    await flushPromises()

    expect(wrapper.text()).toContain('C2 的答案文本')
    expect(wrapper.text()).not.toContain('按目标培养方案要求')
    expect(wrapper.find('[data-testid="explanation-focus"]').text()).toContain('C2')
  })

  it('聚焦的课程没有条目时给出中性说明，不暗示"不需要补修"', async () => {
    const { wrapper } = mountPanel({ focusCourseId: 'C404' })
    await flushPromises()

    const empty = wrapper.find('[data-testid="explanation-empty"]')
    expect(empty.text()).toContain('不代表')
    expect(empty.text()).toContain('该课程不需要补修')
  })

  it('长文本原样展示（不做前端截断或重写）', async () => {
    const longAnswer = '这是一段很长的解释文本。'.repeat(40)
    const body = payload({
      items: [{ ...payload().items[0], answer: longAnswer }],
    })
    const { wrapper } = mountPanel({}, body)
    await flushPromises()

    expect(wrapper.find('[data-testid="explanation-answer"]').text()).toBe(longAnswer)
  })

  it('点击关闭按钮发出 close 事件', async () => {
    const { wrapper } = mountPanel()
    await flushPromises()

    await wrapper.find('[data-testid="explanation-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })
})
