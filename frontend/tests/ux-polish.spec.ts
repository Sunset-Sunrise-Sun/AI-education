/**
 * UX Polish 回归测试（本轮新增）。
 *
 * 覆盖本轮实际修改的组件：
 * 1. `转专业分析`：缺口摘要（待补修 / 已满足 / 可能等价 / 待人工确认）；
 * 2. `补修路径`：阅读顺序提示 + 支撑数据分区（不改业务结论）；
 * 3. `AI 调整` 视图：醒目自然语言入口、示例语句、"当前调整对象"常驻；
 * 4. AI 抽屉：示例预填、阶段指示、解析/求解进行中状态、消息前置校验；
 * 5. 意图确认：硬约束 / 软偏好**分开显示**，学分上限不猜；
 * 6. 候选对比：变化摘要（新增/移除/换班/保持/学分）+ **采用范围声明**；
 * 7. 页面外壳：示例点击 → 打开抽屉并预填输入框。
 *
 * ⚠️ 全部不依赖真实后端：AI 调整走前端预览 fixture，其它接口都不调用。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'
import AiAdjustView from '@/components/views/AiAdjustView.vue'
import AiAdjustDrawer from '@/components/ai/AiAdjustDrawer.vue'
import MakeupPathView from '@/components/views/MakeupPathView.vue'
import TransferAnalysisView from '@/components/views/TransferAnalysisView.vue'
import { setAiPreviewScenario } from '@/api/aiPlanning'
import { PREVIEW_PERSONAL_PLAN, PREVIEW_VERSION_LIST } from '@/api/personalPlanningFixtures'
import { createDefaultUserInputForm } from '@/state/userInput'

const PLAN_RESULT = {
  status: 'partially_feasible',
  selected_classes: [
    { course_id: '62001002', class_id: '6200100220260102' },
    { course_id: '62003007', class_id: '6200300720260101' },
  ],
  changes: [
    { course_id: '62001002', from_class: 'A', to_class: 'B', reason: '避开周五' },
  ],
  risks: [{ course_id: '62001002', level: 'medium', reason: '容量偏低' }],
  unresolved: [{ type: 'manual_confirmation', message: '待人工确认' }],
  objective_summary: '演示方案摘要',
}

const MAKEUP_TASKS = [
  {
    course_id: '62001002',
    course_name: '数据结构与算法',
    credit: 4,
    status: 'required',
    prerequisites: [],
  },
]

const OFFERINGS = [
  {
    course_id: '62001002',
    course_name: '数据结构与算法',
    class_id: '6200100220260102',
    semester: '2026-1',
    credit: 4,
    meetings: [{ weekday: 5, start_section: 7, end_section: 8, weeks: [1, 2] }],
    data_source: 'mock',
  },
]

function demoData() {
  return {
    makeup_tasks: MAKEUP_TASKS,
    course_offerings: OFFERINGS,
    preference: {
      max_credit: 20,
      avoid_cross_campus: false,
      preferred_courses: [],
      avoid_times: [],
      notes: null,
    },
    plan_result: PLAN_RESULT,
  }
}

beforeEach(() => {
  setAiPreviewScenario('ok')
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  setAiPreviewScenario('ok')
})

/* ------------------------------------------------------------------ *
 * 1. 转专业分析：缺口摘要
 * ------------------------------------------------------------------ */

describe('转专业分析：缺口摘要（P0）', () => {
  function mountView(props: Record<string, unknown> = {}) {
    return mount(TransferAnalysisView, {
      props: {
        phase: 'planned',
        selectableVersions: PREVIEW_VERSION_LIST.versions,
        rejectedVersions: PREVIEW_VERSION_LIST.rejected,
        catalogReason: 'preview_fixture',
        result: PREVIEW_PERSONAL_PLAN,
        errorMessage: '',
        errorKind: null,
        errorCode: null,
        previewNotice: null,
        apiEnabled: false,
        currentSemester: '2026-1',
        currentScheduleCount: 0,
        ...props,
      },
    })
  }

  it('把待补修数量作为第一眼结论，并同时给出已满足与待确认数量', async () => {
    const wrapper = mountView()
    await flushPromises()

    const summary = wrapper.find('[data-testid="gap-summary"]')
    expect(summary.exists()).toBe(true)
    expect(wrapper.find('[data-testid="gap-required-count"]').text()).toBe('2')
    expect(wrapper.find('[data-testid="gap-possibly-equivalent"]').text()).toContain('1')
    expect(wrapper.find('[data-testid="gap-manual"]').text()).toContain('1')
    expect(wrapper.find('[data-testid="gap-satisfied"]').text()).toContain('0')
  })

  it('明确说明"可能等价 / 待人工确认"不等于已认定通过', async () => {
    const wrapper = mountView()
    await flushPromises()

    const note = wrapper.find('[data-testid="gap-note"]').text()
    expect(note).toContain('人工确认')
    expect(note).toContain('不是')
    expect(note).toContain('不能')
  })

  it('没有结果时不显示缺口摘要（⛔ 不凭空给数字）', async () => {
    const wrapper = mountView({ result: null })
    await flushPromises()

    expect(wrapper.find('[data-testid="gap-summary"]').exists()).toBe(false)
    // 目录正常时仍应显示版本选择表单
    expect(wrapper.find('[data-testid="personal-old-version"]').exists()).toBe(true)
  })

  it('状态数字全部来自后端 status_counts（前端不重算）', async () => {
    const custom = {
      ...PREVIEW_PERSONAL_PLAN,
      makeup_tasks: [],
      status_counts: { required: 7, satisfied: 3 },
    }
    const wrapper = mountView({ result: custom })
    await flushPromises()

    expect(wrapper.find('[data-testid="gap-required-count"]').text()).toBe('7')
    expect(wrapper.find('[data-testid="gap-satisfied"]').text()).toContain('3')
  })
})

/* ------------------------------------------------------------------ *
 * 2. 补修路径：阅读顺序 + 支撑数据
 * ------------------------------------------------------------------ */

describe('补修路径：阅读顺序与分区（P0）', () => {
  function mountPath(props: Record<string, unknown> = {}) {
    return mount(MakeupPathView, {
      props: {
        state: 'success',
        data: demoData(),
        dataSource: 'mock',
        demoErrorMessage: '',
        userInput: createDefaultUserInputForm(),
        dataMode: 'mock',
        planApiEnabled: false,
        planSubmitting: false,
        planErrorMessage: '',
        planErrorKind: null,
        planErrorStatus: null,
        planErrorCode: null,
        planErrorDetail: null,
        debugInfo: {
          planEndpoint: '/api/v1/plan',
          semester: '2026-1',
          scheduleCount: 0,
          scheduleProvenance: 'empty',
          preferencePresent: true,
          planApiEnabled: false,
          lastHttpStatus: null,
          lastErrorKind: null,
          planResultSource: 'mock',
        },
        dev: false,
        scheduleBlockReason: null,
        explanationApiEnabled: false,
        explanationOpen: false,
        explanationFocusCourseId: null,
        explanationRequestSeq: 0,
        displayedPlanResult: PLAN_RESULT,
        planResultMode: 'mock',
        planResultCourseNameById: { '62001002': '数据结构与算法' },
        courseNameById: { '62001002': '数据结构与算法' },
        personalPlanApplied: false,
        personalPlanNotice: null,
        ...props,
      },
    })
  }

  it('给出明确的阅读顺序，且顺序与页面区块一致', async () => {
    const wrapper = mountPath()
    await flushPromises()

    const order = wrapper.find('[data-testid="path-reading-order"]').text()
    // ⚠️ 第 2 轮组长裁定：旧版（main）的输入 / 概览 / 补修工作区**优先展示**，
    //    新增的历史要求与规划分析区块后置。因此阅读顺序提示也同步更新为 7 步。
    expect(order).toContain('学生信息与当前课表')
    expect(order).toContain('我的学业概览')
    expect(order).toContain('历史培养要求评估')
    expect(order).toContain('教学班与偏好')
    expect(order).toContain('当前学期课表')
    expect(order).toContain('后续学期路径与风险')
    expect(order).toContain('规划结果与解释')
  })

  it('恢复旧版优先顺序：输入 / 概览 / 补修三块排在新增规划区块之前', async () => {
    const wrapper = mountPath()
    await flushPromises()

    const html = wrapper.html()
    // ⚠️ 用**带引号的完整属性值**做锚点：`section-offerings` 的尾部恰好包含
    //    `section-preference` 的前缀，裸子串会让 preferenceIndex 取到 offerings 的位置。
    const at = (id: string): number => html.indexOf(`"${id}"`)
    const userInputIndex = at('section-user-input')
    const makeupIndex = at('section-makeup')
    const offeringsIndex = at('section-offerings')
    const preferenceIndex = at('section-preference')
    const currentIndex = at('section-current-semester')
    const riskIndex = at('section-priority-risk')
    const planIndex = at('section-plan')
    const explainIndex = at('section-explanation')
    const supportIndex = at('path-supporting-data')
    const guideIndex = at('path-pipeline-guide')
    const laterIndex = at('section-later-semesters')

    for (const [name, value] of [
      ['user-input', userInputIndex],
      ['makeup', makeupIndex],
      ['offerings', offeringsIndex],
      ['preference', preferenceIndex],
      ['current-semester', currentIndex],
      ['later-semesters', laterIndex],
      ['priority-risk', riskIndex],
      ['plan', planIndex],
      ['explanation', explainIndex],
      ['supporting-data', supportIndex],
      ['pipeline-guide', guideIndex],
    ] as const) {
      expect(value, `${name} 未渲染`).toBeGreaterThan(-1)
    }

    // 旧版优先：输入 → 补修 → 教学班 → 偏好 → 规划工作区
    expect(makeupIndex).toBeGreaterThan(userInputIndex)
    expect(offeringsIndex).toBeGreaterThan(makeupIndex)
    expect(preferenceIndex).toBeGreaterThan(offeringsIndex)
    expect(preferenceIndex).not.toBe(offeringsIndex)
    // 四步流程条是规划工作区的入口，排在旧版支撑数据之后
    expect(guideIndex).toBeGreaterThan(preferenceIndex)
    expect(currentIndex).toBeGreaterThan(guideIndex)
    // 规划工作区内部顺序不变：当前学期 → 后续学期 → 风险 → 结果 → 解释 → 支撑数据
    expect(laterIndex).toBeGreaterThan(currentIndex)
    expect(riskIndex).toBeGreaterThan(laterIndex)
    expect(planIndex).toBeGreaterThan(riskIndex)
    expect(explainIndex).toBeGreaterThan(planIndex)
    expect(supportIndex).toBeGreaterThan(explainIndex)
  })

  it('恢复旧版四步流程引导（仅作流程说明，⛔ 不是功能导航）', async () => {
    const wrapper = mountPath()
    await flushPromises()

    const guide = wrapper.find('[data-testid="path-pipeline-guide"]')
    expect(guide.exists()).toBe(true)
    const text = guide.text()
    expect(text).toContain('培养方案对比')
    expect(text).toContain('教学班供给获取')
    expect(text).toContain('偏好约束注入')
    expect(text).toContain('课表求解与调班')
    // 四步条只引导规划流程，⛔ 不含功能导航语义
    expect(text).not.toContain('转专业分析')
    expect(text).not.toContain('培养方案导入')
  })

  it('支撑数据分区明确说明"不产生新结论"', async () => {
    const wrapper = mountPath()
    await flushPromises()

    const support = wrapper.find('[data-testid="path-supporting-data"]').text()
    expect(support).toContain('支撑数据')
    expect(support).toContain('不产生')
  })

  it('加载中 / 失败状态仍然可用且不改语义', async () => {
    const loading = mountPath({ state: 'loading' })
    await flushPromises()
    expect(loading.text()).toContain('正在加载演示数据')
    expect(loading.find('[data-testid="path-reading-order"]').exists()).toBe(true)

    const failed = mountPath({ state: 'error', demoErrorMessage: '连接被拒绝' })
    await flushPromises()
    expect(failed.text()).toContain('连接被拒绝')
    expect(failed.text()).toContain('重新尝试连接')
  })
})

/* ------------------------------------------------------------------ *
 * 3. AI 调整视图：入口与调整对象
 * ------------------------------------------------------------------ */

describe('AI 调整视图：醒目入口与调整对象（P0/P1）', () => {
  function mountAiView(props: Record<string, unknown> = {}) {
    return mount(AiAdjustView, {
      props: {
        currentPlan: PLAN_RESULT,
        currentPlanLabel: 'Mock 演示方案',
        adoptedVersion: null,
        makeupTasks: MAKEUP_TASKS,
        ready: true,
        notReadyReason: null,
        ...props,
      },
    })
  }

  it('用一句话入口 + 示例语句引导，且示例不要求专业术语', async () => {
    const wrapper = mountAiView()
    await flushPromises()

    const cta = wrapper.find('[data-testid="ai-cta"]')
    expect(cta.exists()).toBe(true)
    expect(cta.text()).toContain('用一句话说明你想怎么调整')
    expect(cta.text()).toContain('不需要专业术语')

    const examples = wrapper.find('[data-testid="ai-cta-examples"]')
    expect(examples.text()).toContain('尽量别在周五上课')
    expect(examples.text()).toContain('必须保留')
    expect(examples.text()).toContain('学分上限 22')
  })

  it('点击示例把这句话作为参数发出（由外壳填入面板）', async () => {
    const wrapper = mountAiView()
    await wrapper.find('[data-testid="ai-example-这学期太累，尽量别在周五上课"]').trigger('click')

    const emitted = wrapper.emitted('open-drawer')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]?.[0]).toBe('这学期太累，尽量别在周五上课')
  })

  it('常驻显示"当前调整对象"，用户始终知道在改哪份方案', async () => {
    const wrapper = mountAiView()
    await flushPromises()

    const target = wrapper.find('[data-testid="ai-target"]')
    expect(target.exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-view-plan-label"]').text()).toBe('Mock 演示方案')
    expect(target.text()).toContain('建议教学班')
    expect(target.text()).toContain('风险')
  })

  it('已采用时显示"进程内会话版本"并说明未持久化', async () => {
    const wrapper = mountAiView({ adoptedVersion: 2 })
    await flushPromises()

    const adopted = wrapper.find('[data-testid="ai-view-adopted-version"]')
    expect(adopted.text()).toContain('2')
    expect(adopted.text()).toContain('未持久化')
  })

  it('没有方案时明确不可调整，并给出下一步', async () => {
    const wrapper = mountAiView({ currentPlan: null, ready: false, notReadyReason: null })
    await flushPromises()

    const blocked = wrapper.find('[data-testid="ai-view-not-ready"]')
    expect(blocked.text()).toContain('还没有可调整的方案')
    expect(blocked.text()).toContain('不会')
    expect(wrapper.find('[data-testid="ai-cta"]').exists()).toBe(false)
  })

  it('三步说明保留，并写明"两次确认缺一不可"', async () => {
    const wrapper = mountAiView()
    const guide = wrapper.find('[data-testid="ai-two-step-guide"]').text()
    expect(guide).toContain('第一次确认')
    expect(guide).toContain('候选对比')
    expect(guide).toContain('第二次确认')
  })
})

/* ------------------------------------------------------------------ *
 * 4. AI 抽屉：预填 / 阶段 / 进行中
 * ------------------------------------------------------------------ */

describe('AI 抽屉：示例预填、阶段指示与进行中状态（P1）', () => {
  function mountDrawer(props: Record<string, unknown> = {}) {
    return mount(AiAdjustDrawer, {
      props: {
        open: true,
        semester: '2026-1',
        basePlan: PLAN_RESULT,
        basePlanLabel: 'Mock 演示方案',
        makeupTasks: MAKEUP_TASKS,
        courseOfferings: OFFERINGS,
        preference: null,
        focusCourseId: null,
        seedMessage: null,
        apiEnabled: false,
        previewEnabled: true,
        ...props,
      },
    })
  }

  it('示例语句会预填输入框（只是提示，不自动解析）', async () => {
    const wrapper = mountDrawer({ seedMessage: '数据结构必须保留，其它可以调整' })
    await flushPromises()

    const input = wrapper.find('[data-testid="ai-utterance-input"]')
    expect((input.element as HTMLTextAreaElement).value).toBe('数据结构必须保留，其它可以调整')
    // ⛔ 未点击"解析"之前不应出现草稿
    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(false)
  })

  it('提供快捷示例按钮，点击只填入输入框', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    const example = wrapper.find('[data-testid="ai-quick-example-这学期太累，尽量别在周五上课"]')
    expect(example.exists()).toBe(true)
    await example.trigger('click')

    const input = wrapper.find('[data-testid="ai-utterance-input"]')
    expect((input.element as HTMLTextAreaElement).value).toContain('尽量别在周五上课')
  })

  it('阶段指示随流程推进（输入 → 意图 → 候选 → 采用）', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    // 初始：第 1 阶段进行中
    expect(wrapper.find('[data-testid="ai-stage-input"]').attributes('data-stage-state')).toBe('active')

    await wrapper.find('[data-testid="ai-utterance-input"]').setValue('这学期太累')
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()

    // 解析完成：第 1 阶段完成，第 2 阶段（确认意图）进行中
    expect(wrapper.find('[data-testid="ai-stage-input"]').attributes('data-stage-state')).toBe('done')
    expect(wrapper.find('[data-testid="ai-stage-intent"]').attributes('data-stage-state')).toBe('active')

    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()

    // 求解完成、候选已生成：第 3 阶段完成，第 4 阶段（确认采用）进行中
    expect(wrapper.find('[data-testid="ai-stage-candidate"]').attributes('data-stage-state')).toBe(
      'done',
    )
    expect(wrapper.find('[data-testid="ai-stage-adopt"]').attributes('data-stage-state')).toBe(
      'active',
    )

    // 采用之后四个阶段全部完成
    setAiPreviewScenario('adopted')
    await wrapper.find('[data-testid="ai-adopt-candidate"]').trigger('click')
    await flushPromises()
    for (const key of ['input', 'intent', 'candidate', 'adopt']) {
      expect(wrapper.find(`[data-testid="ai-stage-${key}"]`).attributes('data-stage-state')).toBe(
        'done',
      )
    }
  })

  it('解析中显示真实状态说明，并明确不会生成课程', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    await wrapper.find('[data-testid="ai-utterance-input"]').setValue('这学期太累')
    // 只等同步部分：请求仍在飞行中（预览 fixture 是异步解析，因此此时阶段为"解析中"）。
    const pending = wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await Promise.resolve()

    const progress = wrapper.find('[data-testid="ai-interpreting"]')
    expect(progress.exists()).toBe(true)
    expect(progress.text()).toContain('不会')
    expect(progress.text()).toContain('生成任何课程')

    await pending
    await flushPromises()
  })

  it('求解中显示真实状态说明，并明确没有进度百分比', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    await wrapper.find('[data-testid="ai-utterance-input"]').setValue('这学期太累')
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()

    const pending = wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await Promise.resolve()

    const progress = wrapper.find('[data-testid="ai-solving"]')
    expect(progress.exists()).toBe(true)
    expect(progress.text()).toContain('没有进度百分比')
    expect(progress.text()).toContain('不会显示任何课程')

    await pending
    await flushPromises()
  })

  it('关闭时清空预填状态（下次打开不会残留上一次的示例）', async () => {
    const wrapper = mountDrawer({ seedMessage: '示例一' })
    await flushPromises()
    expect((wrapper.find('[data-testid="ai-utterance-input"]').element as HTMLTextAreaElement).value)
      .toBe('示例一')

    await wrapper.setProps({ open: false, seedMessage: null })
    await wrapper.setProps({ open: true })
    await flushPromises()

    expect((wrapper.find('[data-testid="ai-utterance-input"]').element as HTMLTextAreaElement).value)
      .toBe('')
  })
})

/* ------------------------------------------------------------------ *
 * 5. 意图确认面板：硬/软分开 + 学分不猜
 * ------------------------------------------------------------------ */

describe('意图确认面板：硬约束与软偏好分开显示（P1）', () => {
  async function reachDraft() {
    const wrapper = mount(AiAdjustDrawer, {
      props: {
        open: true,
        semester: '2026-1',
        basePlan: PLAN_RESULT,
        basePlanLabel: 'Mock 演示方案',
        makeupTasks: MAKEUP_TASKS,
        courseOfferings: OFFERINGS,
        preference: null,
        focusCourseId: null,
        seedMessage: null,
        apiEnabled: false,
        previewEnabled: true,
      },
    })
    await wrapper.find('[data-testid="ai-utterance-input"]').setValue('这学期太累，数据结构必须保留')
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()
    return wrapper
  }

  it('硬约束区块与软偏好区块分别标注"不可协商 / 可协商"', async () => {
    const wrapper = await reachDraft()

    expect(wrapper.find('[data-testid="ai-hard-constraints"]').text()).toContain('不可协商')
    expect(wrapper.find('[data-testid="ai-soft-preferences"]').text()).toContain('可协商')
    // 锁定课程与学分上限属于硬约束区
    expect(wrapper.find('[data-testid="ai-locked-courses"]').text()).toContain('必须保留')
    expect(wrapper.find('[data-testid="ai-credit-limit"]').text()).toContain('硬约束')
  })

  it('学分上限未指定时明确"不会替你猜"', async () => {
    const wrapper = await reachDraft()
    expect(wrapper.find('[data-testid="ai-credit-unspecified"]').text()).toContain('不会替你猜')
  })

  it('歧义存在时禁用确认，并显示必须先回答的问题', async () => {
    setAiPreviewScenario('ambiguous')
    const wrapper = await reachDraft()

    expect(wrapper.find('[data-testid="ai-ambiguities"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ai-confirm-intent"]').attributes('disabled')).toBeDefined()
  })
})

/* ------------------------------------------------------------------ *
 * 6. 候选对比：变化摘要 + 采用范围声明
 * ------------------------------------------------------------------ */

describe('候选对比：变化摘要与采用范围（P1）', () => {
  async function reachCandidate() {
    const wrapper = mount(AiAdjustDrawer, {
      props: {
        open: true,
        semester: '2026-1',
        basePlan: PLAN_RESULT,
        basePlanLabel: 'Mock 演示方案',
        makeupTasks: MAKEUP_TASKS,
        courseOfferings: OFFERINGS,
        preference: null,
        focusCourseId: null,
        seedMessage: null,
        apiEnabled: false,
        previewEnabled: true,
      },
    })
    await wrapper.find('[data-testid="ai-utterance-input"]').setValue('这学期太累')
    await wrapper.find('[data-testid="ai-parse-intent"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="ai-confirm-intent"]').trigger('click')
    await flushPromises()
    return wrapper
  }

  it('第一眼给出新增 / 移除 / 换班 / 保持 / 学分的数量摘要', async () => {
    const wrapper = await reachCandidate()

    const summary = wrapper.find('[data-testid="change-summary"]')
    expect(summary.exists()).toBe(true)
    expect(wrapper.find('[data-testid="change-added"]').text()).toContain('新增')
    expect(wrapper.find('[data-testid="change-removed"]').text()).toContain('移除')
    expect(wrapper.find('[data-testid="change-replaced"]').text()).toContain('换班')
    expect(wrapper.find('[data-testid="change-kept"]').text()).toContain('保持')
    expect(wrapper.find('[data-testid="change-credit"]').text()).toContain('学分')
  })

  it('采用按钮旁明确说明"临时采用、未持久化、不代表教务选课成功"', async () => {
    const wrapper = await reachCandidate()

    const scope = wrapper.find('[data-testid="ai-adopt-scope-notice"]').text()
    expect(scope).toContain('本次运行期间')
    expect(scope).toContain('不会')
    expect(scope).toContain('保存')
    expect(scope).toContain('不代表')
    expect(wrapper.find('[data-testid="ai-adopt-candidate"]').text()).toContain('临时')
  })

  it('换班仍显示旧班 → 新班', async () => {
    const wrapper = await reachCandidate()
    const replaced = wrapper.find('[data-testid="change-replaced"]')
    expect(replaced.text()).toContain('换班')
  })
})

/* ------------------------------------------------------------------ *
 * 7. 页面外壳：示例 → 抽屉预填（端到端接线）
 * ------------------------------------------------------------------ */

describe('页面外壳：AI 调整示例直达抽屉（P0 接线）', () => {
  const DEMO_PAYLOAD = {
    makeup_tasks: MAKEUP_TASKS,
    course_offerings: OFFERINGS,
    preference: {
      max_credit: 20,
      avoid_cross_campus: false,
      preferred_courses: [],
      avoid_times: [],
    },
    plan_result: PLAN_RESULT,
  }

  function routedFetch() {
    return vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/v1/mock/demo')) {
        return Promise.resolve(
          new Response(JSON.stringify(DEMO_PAYLOAD), {
            status: 200,
            headers: { 'Content-Type': 'application/json', 'X-Data-Source': 'mock' },
          }),
        )
      }
      return Promise.resolve(new Response('Not Found', { status: 404 }))
    })
  }

  beforeEach(() => {
    vi.stubGlobal('fetch', routedFetch())
  })

  it('在 AI 调整视图点击示例 → 打开抽屉并预填这句话（⛔ 不自动解析）', async () => {
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()

    await wrapper.find('[data-testid="nav-ai-adjust"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="ai-example-这学期太累，尽量别在周五上课"]').trigger('click')
    await flushPromises()

    const input = wrapper.find('[data-testid="ai-utterance-input"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLTextAreaElement).value).toBe('这学期太累，尽量别在周五上课')
    // 只是预填：不应已经出现待确认草稿
    expect(wrapper.find('[data-testid="ai-intent-draft"]').exists()).toBe(false)
  })

  it('导航上的"AI 调整"按钮仍然直接打开面板（不带预填）', async () => {
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()

    await wrapper.find('[data-testid="nav-open-ai-drawer"]').trigger('click')
    await flushPromises()

    const input = wrapper.find('[data-testid="ai-utterance-input"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLTextAreaElement).value).toBe('')
  })

  it('页面底部声明不再声称"AI 接口尚未实现"，而是按真实可用状态说明', async () => {
    const wrapper = mount(App, { attachTo: document.body })
    await flushPromises()

    const footer = wrapper.find('.footer-compliance').text()
    expect(footer).not.toContain('尚未由后端实现')
    expect(footer).toContain('/api/v1/ai-planning/status')
    expect(footer).toContain('不会')
  })
})
