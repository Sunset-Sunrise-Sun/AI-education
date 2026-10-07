/**
 * Gate E —— Frontend Real-path readiness（**纯显示 / 接线**审计的回归锁定）。
 *
 * 目标：把"前端在真实 `/api/v1/plan` 路径上**只做展示与接线**"变成可执行的断言：
 *
 * ```text
 * real /api/v1/plan  ·  503  ·  loading  ·  error  ·  success
 * Real / Mock 分离   ·  meetings=[] 中性文案  ·  remaining_capacity=None → —
 * ⛔ 不出现"已选课" / "可直接执行"
 * ⛔ 不在前端重算冲突 / 可行性
 * ⛔ 失败时不回退 Mock，也不重复请求 Mock 通道
 * ```
 *
 * ⚠️ 本文件不实现任何业务规则，只断言"展示与接线"。
 * 全部网络调用都是 mocked fetch，不依赖真实后端。
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'
import CourseOfferingList from '@/components/CourseOfferingList.vue'
import PlanResultPanel from '@/components/PlanResultPanel.vue'
import PreferencePanel from '@/components/PreferencePanel.vue'
import SubmissionActions from '@/components/SubmissionActions.vue'
import { EMPTY_MEETINGS_DATA_TEXT, formatMeetingLine } from '@/utils/labels'

const REPO_FRONTEND = join(__dirname, '..')

/** 真实链路返回的 PlanResult（含 DG-07C 的 schedule_unknown 与 manual_confirmation）。 */
const REAL_PLAN_RESULT = {
  status: 'partially_feasible',
  selected_classes: [
    { course_id: 'SYN-REAL-1', class_id: 'REAL-01' },
    { course_id: 'SYN-UNKNOWN', class_id: 'UNKNOWN-01' },
  ],
  changes: [
    {
      course_id: 'SYN-REAL-1',
      from_class: null,
      to_class: 'REAL-01',
      reason: 'REAL_CHANGE_REASON_MARKER',
    },
  ],
  risks: [],
  unresolved: [
    {
      type: 'schedule_unknown',
      message: '当前班 SYN-UNKNOWN/UNKNOWN-01 在当前来源快照中没有可用排课信息，需要人工核验。',
    },
    {
      type: 'manual_confirmation',
      message: '课程 SYN-REAL-1 的补修认定仍需人工确认，不自动新增。',
    },
    {
      type: 'missing_data',
      message: '课程 SYN-MISSING 在本次输入中没有候选教学班。',
    },
  ],
  objective_summary: 'REAL_OBJECTIVE_MARKER',
}

const MOCK_PLAN_RESULT = {
  status: 'infeasible',
  selected_classes: [],
  changes: [],
  risks: [],
  unresolved: [],
  objective_summary: 'MOCK_OBJECTIVE_MARKER',
}

const DEMO_PAYLOAD = {
  makeup_tasks: [
    { course_id: 'MAR103', course_name: 'MOCK_TASK_NAME', credit: 3, status: 'satisfied' },
  ],
  course_offerings: [
    {
      course_id: 'SYN-UNKNOWN',
      course_name: 'MOCK_OFFERING_NAME',
      class_id: 'UNKNOWN-01',
      semester: '2026-1',
      credit: 3,
      // DG-07B：来源快照没有可用排课信息 ⇒ meetings = []
      meetings: [],
      capacity: 90,
      remaining_capacity: null,
      data_source: 'mock',
    },
  ],
  preference: { max_credit: 20, avoid_cross_campus: false, preferred_courses: [], avoid_times: [] },
  plan_result: MOCK_PLAN_RESULT,
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

function errorResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 按 URL 路由：`/api/v1/plan` → 给定 plan response；其余 → Mock Demo。 */
function routedFetch(planResponse: () => Promise<Response> | Response) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/v1/plan')) {
      return Promise.resolve(planResponse())
    }
    return Promise.resolve(jsonResponse(DEMO_PAYLOAD))
  })
}

function planCallCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter((call) => String(call[0]).includes('/api/v1/plan')).length
}

function demoCallCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter((call) => String(call[0]).includes('/api/v1/mock/demo')).length
}

async function mountApp() {
  const wrapper = mount(App, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

const FORBIDDEN_USER_TEXT = ['已选课', '可直接执行', '无冲突', '无需上课', '异步课程', '尚未排课']

describe('Gate E：Real 成功路径（success + provenance + 中性文案）', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('200 → 展示 Real 结果、provenance=Real，且基础数据仍标 Mock', async () => {
    const fetchMock = routedFetch(() => jsonResponse(REAL_PLAN_RESULT))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountApp()
    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('REAL_OBJECTIVE_MARKER')
    expect(wrapper.text()).not.toContain('MOCK_OBJECTIVE_MARKER')
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Real')
    // 局部 provenance：基础演示数据仍然明确标 Mock。
    expect(wrapper.find('[data-testid="plan-provenance"]').text()).toContain('Mock')
  })

  it('Real 结果里的 schedule_unknown / manual_confirmation / missing_data 都被原样展示', async () => {
    vi.stubGlobal('fetch', routedFetch(() => jsonResponse(REAL_PLAN_RESULT)))
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const text = wrapper.text()
    // ⚠️ 本轮产品化修整：待确认事项统一由「需要你处理」以**归一化中文**展示，
    //    ⛔ 主界面不再直接输出 `type: schedule_unknown` 这类机器码。
    //    旧断言要求原样显示 raw type，与人工验收要求相反，故在此改为：
    //    中文文案必须出现，且机器码不得出现在主界面。
    expect(text).toContain('排课信息')
    expect(text).toContain('人工确认')
    expect(text).not.toContain('schedule_unknown')
    expect(text).not.toContain('missing_data')
    expect(text).not.toContain('type:')
  })

  it('⛔ 渲染结果里不出现"已选课" / "可直接执行" / 无冲突类推断词', async () => {
    vi.stubGlobal('fetch', routedFetch(() => jsonResponse(REAL_PLAN_RESULT)))
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const text = wrapper.text()
    for (const forbidden of FORBIDDEN_USER_TEXT) {
      expect(text).not.toContain(forbidden)
    }
  })

  it('⛔ Real 失败后不重试 Mock 通道：请求计数与结果都保持不变', async () => {
    const fetchMock = routedFetch(() =>
      errorResponse(503, {
        detail: { error: 'real_pipeline_not_configured', message: '真实规划链路尚未配置。' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountApp()
    const demoCallsBefore = demoCallCount(fetchMock)
    expect(demoCallsBefore).toBe(1) // 初始加载只取一次 Mock Demo

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    expect(planCallCount(fetchMock)).toBe(1)
    expect(demoCallCount(fetchMock)).toBe(demoCallsBefore)
    expect(wrapper.text()).toContain('MOCK_OBJECTIVE_MARKER')
    expect(wrapper.find('[data-testid="plan-result-provenance"]').text()).toBe('Mock')
  })
})

describe('Gate E：503 / 错误 / loading 状态', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('503 real_pipeline_not_configured → "尚未完成装配"且显示 HTTP 503 与错误码', async () => {
    vi.stubGlobal(
      'fetch',
      routedFetch(() =>
        errorResponse(503, {
          detail: {
            error: 'real_pipeline_not_configured',
            message: '真实规划链路尚未配置。',
          },
        }),
      ),
    )
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const errorBox = wrapper.find('[data-testid="real-plan-error"]')
    expect(errorBox.exists()).toBe(true)
    expect(wrapper.find('[data-testid="real-plan-error-title"]').text()).toContain('尚未完成装配')
    expect(wrapper.find('[data-testid="real-plan-error-meta"]').text()).toContain('503')
    expect(wrapper.find('[data-testid="real-plan-error-code"]').text()).toContain(
      'real_pipeline_not_configured',
    )
    // ⛔ 不展示任何替代方案
    expect(wrapper.text()).not.toContain('REAL_OBJECTIVE_MARKER')
  })

  it('loading：请求进行中按钮禁用并显示"正在请求 Real Planning…"', async () => {
    let resolvePlan: ((response: Response) => void) | undefined
    const pending = new Promise<Response>((resolve) => {
      resolvePlan = resolve
    })
    const fetchMock = routedFetch(() => pending)
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountApp()
    const button = wrapper.find('[data-testid="real-plan-submit"]')

    await button.trigger('click')
    await flushPromises()

    // 请求仍在飞行中：按钮禁用 + 明确的进行中文案（不是"请求失败"）。
    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="real-plan-submit"]').text()).toContain('正在请求 Real Planning')
    expect(wrapper.find('[data-testid="real-plan-error"]').exists()).toBe(false)

    resolvePlan?.(jsonResponse(REAL_PLAN_RESULT))
    await flushPromises()

    expect(wrapper.find('[data-testid="real-plan-submit"]').text()).toContain('生成规划')
    expect(wrapper.text()).toContain('REAL_OBJECTIVE_MARKER')
  })

  it('failed 状态：错误类型互斥且都导向"未装配 / 输入 / 服务端 / 网络"之一', async () => {
    vi.stubGlobal(
      'fetch',
      routedFetch(() =>
        errorResponse(500, { detail: { error: 'internal_error', message: 'boom' } }),
      ),
    )
    const wrapper = await mountApp()

    await wrapper.find('[data-testid="real-plan-submit"]').trigger('click')
    await flushPromises()

    const meta = wrapper.find('[data-testid="real-plan-error-meta"]').text()
    expect(meta).toContain('500')
    expect(meta).toContain('server')
    // ⛔ 500 不得被写成"未装配"
    expect(wrapper.find('[data-testid="real-plan-error-title"]').text()).not.toContain('尚未完成装配')
  })

  it('loading 状态在组件层：submitting=true 时按钮文案与禁用同时成立', () => {
    const wrapper = mount(SubmissionActions, {
      props: { mode: 'mock' as const, planApiEnabled: true, inputValid: true, submitting: true },
    })

    expect(wrapper.find('[data-testid="real-plan-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="real-plan-submit"]').text()).toBe('正在请求 Real Planning…')
  })
})

describe('Gate E：纯展示细节（meetings=[] / remaining_capacity=None）', () => {
  it('meetings=[] → 中性数据文案，⛔ 不推断无冲突 / 无课', () => {
    const wrapper = mount(CourseOfferingList, {
      props: {
        offerings: [
          {
            course_id: 'SYN-UNKNOWN',
            course_name: '示例课程',
            class_id: 'UNKNOWN-01',
            semester: '2026-1',
            meetings: [],
            capacity: 90,
            remaining_capacity: null,
            data_source: 'real',
          },
        ],
      },
    })

    const text = wrapper.text()
    expect(text).toContain('当前数据中无排课信息')
    for (const forbidden of FORBIDDEN_USER_TEXT) {
      expect(text).not.toContain(forbidden)
    }
  })

  it('remaining_capacity=None → 破折号（不显示 0 / null）', () => {
    const wrapper = mount(CourseOfferingList, {
      props: {
        offerings: [
          {
            course_id: 'SYN-A',
            course_name: '示例课程',
            class_id: 'A-01',
            semester: '2026-1',
            meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1] }],
            capacity: 90,
            remaining_capacity: null,
            data_source: 'real',
          },
        ],
      },
    })

    const capacity = wrapper.find('.capacity-box').text()
    expect(capacity).toContain('—')
    expect(capacity).toContain('/ 90')
    expect(capacity).not.toContain('null')
    expect(capacity).not.toContain('0 /')
  })

  it('PlanResultPanel：不再渲染 unresolved 明细，也不宣称可执行性', () => {
    const wrapper = mount(PlanResultPanel, {
      props: {
        planResult: {
          status: 'feasible',
          selected_classes: [],
          changes: [],
          risks: [],
          unresolved: [],
          objective_summary: null,
        },
        courseNameById: {},
      },
    })

    const text = wrapper.text()
    // ⚠️ 本轮：`unresolved` 明细统一由「需要你处理」渲染，本组件不再输出该区块
    expect(text).not.toContain('type:')
    expect(text).not.toContain('unresolved')
    expect(text).not.toContain('可直接执行')
  })
})

describe('Gate E：静态保证（前端不做业务规则 / 不依赖响应头）', () => {
  function sourceFiles(dir: string): string[] {
    const entries: string[] = []
    for (const name of readdirSync(dir)) {
      const full = join(dir, name)
      if (statSync(full).isDirectory()) {
        entries.push(...sourceFiles(full))
      } else if (name.endsWith('.ts') || name.endsWith('.vue')) {
        entries.push(full)
      }
    }
    return entries
  }

  /**
   * 去掉注释后的"代码文本"。
   *
   * ⚠️ 这些静态守卫只针对**代码**：注释里出现"X-Data-Source"或
   * "已选课"（例如"不要把演示数据当成学生真实已选课程"这类禁止性说明）
   * 是**文档**，不是违规。
   */
  function codeOnly(text: string): string {
    return text
      .replace(/<!--[\s\S]*?-->/g, ' ')
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|\s)\/\/[^\n]*/g, ' ')
  }

  const sources = sourceFiles(join(REPO_FRONTEND, 'src')).map((path) => ({
    path,
    code: codeOnly(readFileSync(path, 'utf-8')),
  }))

  it('⛔ 前端源码里没有冲突检测 / 可行性求解 / Path Repair 实现', () => {
    const forbiddenIdentifiers = [
      'hasConflict',
      'detectConflict',
      'computeConflict',
      'conflictCount',
      'resolveConflict',
      'scheduleOverlap',
      'timeOverlap',
      'isFeasible',
      'computeFeasible',
      'solveSchedule',
      'repairPlan',
      'pathRepair',
    ]

    for (const { path, code } of sources) {
      for (const identifier of forbiddenIdentifiers) {
        expect(code, `${path} 不应包含 ${identifier}`).not.toContain(identifier)
      }
    }
  })

  it('⛔ Real 链路不读取 X-Data-Source（只有 Mock 客户端读取该标记）', () => {
    const planClient = sources.find((entry) => entry.path.endsWith(join('api', 'plan.ts')))
    const app = sources.find((entry) => entry.path.endsWith('App.vue'))
    expect(planClient).toBeDefined()
    expect(app).toBeDefined()

    expect(planClient?.code).not.toContain('X-Data-Source')
    expect(app?.code).not.toContain('X-Data-Source')

    // Mock 客户端是唯一读取该标记的地方（用于如实显示"当前是 Mock"）。
    const readers = sources
      .filter((entry) => entry.code.includes('X-Data-Source'))
      .map((entry) => entry.path.replace(/\\/g, '/'))
    expect(readers).toHaveLength(1)
    expect(readers[0]).toContain('api/demo.ts')
  })

  it('⛔ 前端源码里不出现"已选课" / "可直接执行" 这类误导文案', () => {
    for (const { path, code } of sources) {
      expect(code, `${path} 不应出现"已选课"`).not.toContain('已选课')
      expect(code, `${path} 不应出现"可直接执行"`).not.toContain('可直接执行')
    }
  })

  it('真实链路只调用 POST /api/v1/plan，且不 import Mock 通道', () => {
    const planClient = readFileSync(join(REPO_FRONTEND, 'src', 'api', 'plan.ts'), 'utf-8')
    const code = codeOnly(planClient)

    expect(code).toContain('PLAN_ENDPOINT')
    expect(code).not.toContain('DEMO_ENDPOINT')
    expect(code).not.toContain("from './demo'")
    expect(code).not.toContain('fetchDemo')
  })
})

/**
 * Gate E 补充（本轮 mandate 的 6 / 9 / 10 / 12 项）：
 * 缺地点中性文案 · 空数组只表示"无记录" · 偏好措辞 · 容量阈值。
 */
describe('Gate E：地点 / 空数组语义 / 偏好措辞 / 容量阈值', () => {
  it('缺地点 → "当前数据中无地点信息"（⛔ 不猜教室、⛔ 不省略该段）', () => {
    const withoutPlace = formatMeetingLine({
      weekday: 1,
      start_section: 3,
      end_section: 4,
      weeks: [1, 2],
      campus: null,
      classroom: null,
    })
    expect(withoutPlace).toContain('当前数据中无地点信息')
    expect(withoutPlace).toContain('周一')
    expect(withoutPlace).not.toContain('null')
    expect(withoutPlace).not.toContain('undefined')

    const withPlace = formatMeetingLine({
      weekday: 2,
      start_section: 5,
      end_section: 6,
      weeks: [1],
      campus: '东校园',
      classroom: '东B305',
    })
    expect(withPlace).toContain('东校园 / 东B305')
    expect(withPlace).not.toContain('无地点信息')
  })

  it('meetings=[] 使用**同一个**中性常量（⛔ 不出现推断性词汇）', () => {
    const wrapper = mount(CourseOfferingList, {
      props: {
        offerings: [
          {
            course_id: 'SYN-UNKNOWN',
            course_name: '示例课程',
            class_id: 'UNKNOWN-02',
            semester: '2026-1',
            meetings: [],
            capacity: 90,
            remaining_capacity: null,
            data_source: 'real',
          },
        ],
      },
    })

    expect(EMPTY_MEETINGS_DATA_TEXT).toBe('当前数据中无排课信息')
    expect(wrapper.text()).toContain(EMPTY_MEETINGS_DATA_TEXT)
    for (const forbidden of FORBIDDEN_USER_TEXT) {
      expect(wrapper.text()).not.toContain(forbidden)
    }
  })

  it('changes / risks / unresolved 空数组只表示"无记录"，⛔ 不写成"无风险 / 无需调整"', () => {
    const wrapper = mount(PlanResultPanel, {
      props: {
        planResult: {
          status: 'infeasible',
          selected_classes: [],
          changes: [],
          risks: [],
          unresolved: [],
          objective_summary: null,
        },
        courseNameById: {},
      },
    })

    const text = wrapper.text()
    expect(text).toContain('未返回方案变更记录')
    expect(text).toContain('未返回风险项')
    // ⚠️ 本轮：unresolved 明细已移出本组件（统一在「需要你处理」），
    //    因此这里不再断言"未决事项为空"文案，改为断言不出现 raw 机器码。
    expect(text).not.toContain('type:')
    expect(text).not.toContain('unresolved')

    const forbiddenClaims = [
      '无风险',
      '没有风险',
      '未发现风险',
      '无需调整',
      '无变更',
      '可直接执行',
      '已选课',
      '已成功选中',
    ]
    for (const claim of forbiddenClaims) {
      expect(text).not.toContain(claim)
    }
  })

  it('Preference 展示 ⛔ 不声称偏好已被求解器执行', () => {
    const wrapper = mount(PreferencePanel, {
      props: {
        preference: {
          max_credit: 20,
          avoid_cross_campus: true,
          preferred_courses: ['CSE201'],
          avoid_times: [],
          notes: '希望尽量集中在上午',
        },
        courseNameById: { CSE201: '示例课程' },
      },
    })

    const text = wrapper.text()
    expect(text).toContain('以 PlanResult 输出为准')

    const forbiddenClaims = [
      '已按偏好求解',
      '偏好已全部满足',
      '已作为硬约束执行',
      '偏好已生效',
      '已全部满足',
      '求解器已执行',
    ]
    for (const claim of forbiddenClaims) {
      expect(text).not.toContain(claim)
    }
  })

  it('容量只展示原始比例，⛔ 不发明阈值 / 紧张度判断', () => {
    const wrapper = mount(CourseOfferingList, {
      props: {
        offerings: [
          {
            course_id: 'SYN-FULL',
            course_name: '示例课程',
            class_id: 'FULL-01',
            semester: '2026-1',
            meetings: [{ weekday: 3, start_section: 1, end_section: 2, weeks: [1] }],
            capacity: 90,
            // 余量极低也必须**原样**展示，⛔ 不得推断"即将满员 / 紧张"。
            remaining_capacity: 4,
            data_source: 'real',
          },
        ],
      },
    })

    const capacity = wrapper.find('.capacity-box').text()
    expect(capacity).toContain('4')
    expect(capacity).toContain('/ 90')

    const text = wrapper.text()
    for (const invented of [
      '余量紧张',
      '即将满员',
      '名额充足',
      '阈值',
      '紧张',
      '建议尽快',
      '大概率',
    ]) {
      expect(text).not.toContain(invented)
    }
  })

  it('静态：⛔ 前端源码不含容量阈值 / 偏好求解 / 冲突推断实现', () => {
    const forbiddenIdentifiers = [
      'capacityThreshold',
      'remainingRatio',
      'seatPressure',
      'isAlmostFull',
      'preferenceSatisfied',
      'preferencesEnforced',
      'wasPreferenceApplied',
    ]
    const forbiddenTexts = ['余量紧张', '即将满员', '已按偏好求解', '偏好已全部满足']

    const files: string[] = []
    const walk = (dir: string): void => {
      for (const name of readdirSync(dir)) {
        const full = join(dir, name)
        if (statSync(full).isDirectory()) walk(full)
        else if (name.endsWith('.ts') || name.endsWith('.vue')) files.push(full)
      }
    }
    walk(join(REPO_FRONTEND, 'src'))

    for (const file of files) {
      const raw = readFileSync(file, 'utf-8')
      const code = raw
        .replace(/<!--[\s\S]*?-->/g, ' ')
        .replace(/\/\*[\s\S]*?\*\//g, ' ')
        .replace(/(^|\s)\/\/[^\n]*/g, ' ')
      for (const identifier of forbiddenIdentifiers) {
        expect(code, `${file} 不应包含 ${identifier}`).not.toContain(identifier)
      }
      for (const phrase of forbiddenTexts) {
        expect(code, `${file} 不应出现 ${phrase}`).not.toContain(phrase)
      }
    }
  })
})
