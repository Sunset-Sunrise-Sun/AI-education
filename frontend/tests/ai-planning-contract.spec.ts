/**
 * 真实后端契约测试（联调契约形状）。
 *
 * 契约来源：后端 `feature/deepseek-planning-controller` 的
 * `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md`
 * （与 `backend/app/api/ai_planning.py` 同一提交）。
 *
 * 覆盖 PR #65 Architecture Review 指出的四处不一致：
 * ① `interpret` 请求是 `{context, user_message}`，**没有** `plan_digest`；
 * ② `solve` 成功状态是 **`candidate_ready`**；
 * ③ `adopt` 返回 `accepted / state / adopted_version / adopted_version_scope`，
 *    **不返回 `adopted_plan`**（前端不得伪造方案体）；
 * ④ 错误码 → 分类映射（404 是"会话不存在"，不是"接口未配置"）。
 *
 * ⚠️ 这里用**真实后端形状**的 JSON 直接喂给适配层（mocked fetch），
 * 因此这些用例就是"联调契约测试"：形状一旦漂移，测试立刻失败。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AiPlanningApiError,
  setAiPlanningForceReal,
  classifyAiPlanningError,
  interpretIntent,
  solvePlan,
  adoptCandidate,
  fetchAiPlanningStatus,
} from '@/api/aiPlanning'
import {
  ContractViolation,
  parseAdoptResponse,
  parseInterpretResponse,
  parseSolveResponse,
  parseStatusResponse,
  type AiInterpretRequest,
  type AiSolveRequest,
} from '@/api/aiPlanningContract'

/* ------------------------------------------------------------------ *
 * 真实后端形状的样本（逐字段抄自 HANDOFF）
 * ------------------------------------------------------------------ */

const PLAN_DIGEST = 'e4df931cec5e9c89'.padEnd(64, '0')

const INTERPRET_RESPONSE = {
  intent_id: 'intent_b0c38498f4423f57c',
  plan_digest: PLAN_DIGEST,
  parsed_intent: {
    summary: '学生想降低负荷并保留数据结构',
    scope: 'current_semester',
    target_semester: '2026-1',
    hard_constraints: [],
    soft_preferences: [
      { kind: 'prefer_fewer_credits', value: null, note: '未给出学分数字' },
      { kind: 'avoid_weekday', value: 5, note: '尽量避开周五' },
    ],
    locked_courses: [
      { course_id: 'DS101', class_id: 'ds-01', reason: '学生明确要求保留该课程' },
    ],
    confidence: 0.6,
    notes: [],
    ambiguities: [],
  },
  ambiguities: [],
  data_source: 'mock',
  generator_kind: 'test_double',
  generator_note: '注入的测试替身模型（不是线上模型）',
  model_id: 'test-rule-fake',
  can_confirm: true,
  state: 'intent_draft',
  token_usage_estimate: { prompt: 412, completion: 96, total: 508 },
  message: '已生成意图草稿，请确认后再求解。',
}

const SOLVE_RESPONSE_CANDIDATE = {
  candidate_id: 'candidate_1b69e89768ff7e4e',
  status: 'candidate_ready',
  plan_kind: 'PlanResult',
  candidate_plan: {
    status: 'partially_feasible',
    selected_classes: [
      { course_id: 'DS101', class_id: 'ds-01' },
      { course_id: 'ALGO201', class_id: 'algo-02' },
    ],
    changes: [
      {
        course_id: 'ALGO201',
        from_class: null,
        to_class: 'algo-02',
        reason: '新增 required 任务仅有一个 CLEAR 教学班',
      },
    ],
    risks: [],
    unresolved: [{ type: 'manual_confirmation', message: '课程 NET301 仍需人工确认' }],
    objective_summary: '受限 Planner 本学期建议课表',
  },
  diff: {
    added: [{ course_id: 'ALGO201', class_id: 'algo-02' }],
    removed: [],
    replaced: [],
    kept: [{ course_id: 'DS101', class_id: 'ds-01' }],
    base_credit: 3,
    candidate_credit: 6,
    credit_delta: 3,
    credit_unknown_course_ids: [],
    empty: false,
  },
  risks: ['本次上下文的教学班数据来源为 mock，不代表真实教务开课。'],
  unresolved: ['课程 NET301 的补修认定仍需人工确认，不自动新增。'],
  message: '已按确认意图调用受控 Planner 生成候选；请对照差异后决定是否采用。',
  blocked_reason: null,
  data_source: 'mock',
  generator_kind: 'test_double',
  plan_digest: PLAN_DIGEST,
}

const SOLVE_RESPONSE_BLOCKED = {
  candidate_id: null,
  status: 'blocked',
  plan_kind: 'none',
  candidate_plan: null,
  diff: null,
  risks: [],
  unresolved: ['锁定的课程 DS101（班次 ds-01）在候选里发生了变化。'],
  message: '候选破坏了用户锁定的课程，已拒绝该候选并保留原方案。',
  blocked_reason: 'locked_course_would_change',
  data_source: 'mock',
  generator_kind: 'test_double',
  plan_digest: PLAN_DIGEST,
}

const ADOPT_RESPONSE_ACCEPTED = {
  candidate_id: 'candidate_1b69e89768ff7e4e',
  accepted: true,
  state: 'adopted',
  adopted_version: 1,
  adopted_version_scope: 'process_local_session',
  original_plan_unchanged: false,
  plan_digest: PLAN_DIGEST,
  message: '已采用候选方案（仅在本进程会话内有效，未持久化）。',
}

const ADOPT_RESPONSE_REJECTED = {
  candidate_id: 'candidate_1b69e89768ff7e4e',
  accepted: false,
  state: 'rejected',
  adopted_version: 0,
  adopted_version_scope: 'process_local_session',
  original_plan_unchanged: true,
  plan_digest: PLAN_DIGEST,
  message: '已拒绝候选方案；原方案完全不变。',
}

const STATUS_RESPONSE = {
  enabled: true,
  live_model_available: false,
  api_key_configured: false,
  model: 'deepseek-flash',
  base_url: 'https://api.deepseek.com',
  max_calls_per_request: 3,
  request_timeout_seconds: 20.0,
  adopt_ttl_seconds: 900,
  generator_kind_when_live: 'deepseek_live',
  data_source_note: '上下文 data_source 由教学班自身的 data_source 判定。',
}

const INTERPRET_REQUEST: AiInterpretRequest = {
  context: {
    semester: '2026-1',
    base_plan: {
      status: 'partially_feasible',
      selected_classes: [{ course_id: 'DS101', class_id: 'ds-01' }],
      changes: [],
      risks: [],
      unresolved: [],
      objective_summary: '原方案',
    },
    makeup_tasks: [
      {
        course_id: 'DS101',
        course_name: '数据结构',
        credit: 3,
        status: 'required',
        prerequisites: [],
      },
    ],
    course_offerings: [
      {
        course_id: 'DS101',
        course_name: '数据结构',
        class_id: 'ds-01',
        semester: '2026-1',
        credit: 3,
        data_source: 'mock',
        meetings: [{ weekday: 1, start_section: 1, end_section: 2, weeks: [1, 3] }],
      },
    ],
    preference: {
      max_credit: 22,
      avoid_cross_campus: false,
      preferred_courses: [],
      avoid_times: [],
      notes: null,
    },
  },
  user_message: '这学期太累，数据结构必须保留，尽量别在周五上课',
}

const SOLVE_REQUEST: AiSolveRequest = {
  intent_id: 'intent_b0c38498f4423f57c',
  plan_digest: PLAN_DIGEST,
  confirmed_intent: {
    plan_digest: PLAN_DIGEST,
    semester: '2026-1',
    scope: 'current_semester',
    target_semester: '2026-1',
    hard_constraints: [{ kind: 'max_credit_limit', value: 22, evidence: '用户在确认面板填写' }],
    soft_preferences: [{ kind: 'avoid_weekday', value: 5, note: '尽量避开周五' }],
    locked_courses: [{ course_id: 'DS101', class_id: 'ds-01', reason: '用户要求保留' }],
    user_note: null,
  },
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 强制走真实路径（不使用预览 fixture），并 mock fetch。 */
function useRealFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const mock = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(handler(String(input), init)),
  )
  vi.stubGlobal('fetch', mock)
  return mock
}

beforeEach(() => {
  // 强制走真实网络路径：契约测试必须验证真实请求体与响应解析，
  // ⛔ 不能落到前端预览 fixture。
  setAiPlanningForceReal(true)
})

afterEach(() => {
  setAiPlanningForceReal(false)
  vi.unstubAllGlobals()
})

/* ------------------------------------------------------------------ *
 * ① interpret
 * ------------------------------------------------------------------ */

describe('interpret：请求形状与响应解析', () => {
  it('请求体只有 context + user_message（⛔ 不带 plan_digest）', async () => {
    const mock = useRealFetch(() => jsonResponse(INTERPRET_RESPONSE))

    const envelope = await interpretIntent(INTERPRET_REQUEST)

    expect(mock).toHaveBeenCalledTimes(1)
    const [url, init] = mock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/v1/ai-planning/interpret')
    const body = JSON.parse(init.body as string)
    expect(Object.keys(body).sort()).toEqual(['context', 'user_message'])
    expect(body).not.toHaveProperty('plan_digest')
    expect(Object.keys(body.context).sort()).toEqual([
      'base_plan',
      'course_offerings',
      'makeup_tasks',
      'preference',
      'semester',
    ])

    // 指纹由**后端**返回，前端只保存
    expect(envelope.data.plan_digest).toBe(PLAN_DIGEST)
    expect(envelope.data.intent_id).toBe('intent_b0c38498f4423f57c')
    expect(envelope.source).toBe('backend')
  })

  it('解析草稿字段（含 generator_kind=test_double 与 token_usage_estimate）', async () => {
    useRealFetch(() => jsonResponse(INTERPRET_RESPONSE))
    const envelope = await interpretIntent(INTERPRET_REQUEST)

    expect(envelope.data.generator_kind).toBe('test_double')
    expect(envelope.data.generator_note).toContain('测试替身')
    expect(envelope.data.parsed_intent.soft_preferences).toHaveLength(2)
    expect(envelope.data.parsed_intent.locked_courses[0]).toEqual({
      course_id: 'DS101',
      class_id: 'ds-01',
      reason: '学生明确要求保留该课程',
    })
    expect(envelope.data.can_confirm).toBe(true)
    expect(envelope.data.token_usage_estimate.total).toBe(508)
  })

  it('can_confirm=false + ambiguities 是合法响应（不是错误）', () => {
    const parsed = parseInterpretResponse({
      ...INTERPRET_RESPONSE,
      can_confirm: false,
      ambiguities: [
        { code: 'credit_limit_missing_evidence', question: '请填写学分上限', detail: null },
      ],
    })
    expect(parsed.can_confirm).toBe(false)
    expect(parsed.ambiguities[0]?.code).toBe('credit_limit_missing_evidence')
  })

  it('⛔ 未知 generator_kind 一律拒绝（不得把未知状态显示成"AI 已接入"）', () => {
    expect(() =>
      parseInterpretResponse({ ...INTERPRET_RESPONSE, generator_kind: 'gpt_live' }),
    ).toThrow(ContractViolation)
  })

  it('⛔ 未知 data_source 一律拒绝（unknown 之外不得乱造）', () => {
    expect(() => parseInterpretResponse({ ...INTERPRET_RESPONSE, data_source: 'demo' })).toThrow(
      ContractViolation,
    )
  })

  it('⛔ 缺字段不补默认值 ⇒ ContractViolation', () => {
    const { plan_digest: _omitted, ...withoutDigest } = INTERPRET_RESPONSE
    expect(() => parseInterpretResponse(withoutDigest)).toThrow(ContractViolation)
    expect(() => parseInterpretResponse({ ...INTERPRET_RESPONSE, can_confirm: 'yes' })).toThrow(
      ContractViolation,
    )
  })
})

/* ------------------------------------------------------------------ *
 * ② solve
 * ------------------------------------------------------------------ */

describe('solve：成功状态是 candidate_ready', () => {
  it('candidate_ready 且带候选 / diff ⇒ 解析为有效候选', async () => {
    const mock = useRealFetch(() => jsonResponse(SOLVE_RESPONSE_CANDIDATE))
    const envelope = await solvePlan(SOLVE_REQUEST)

    const [, init] = mock.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(init.body as string)
    expect(Object.keys(body).sort()).toEqual(['confirmed_intent', 'intent_id', 'plan_digest'])
    expect(body.confirmed_intent.hard_constraints[0].evidence).toBe('用户在确认面板填写')

    expect(envelope.data.status).toBe('candidate_ready')
    expect(envelope.data.plan_kind).toBe('PlanResult')
    expect(envelope.data.candidate_plan?.selected_classes).toHaveLength(2)
    expect(envelope.data.diff).toMatchObject({ credit_delta: 3, empty: false })
    expect(envelope.data.diff?.kept).toEqual([{ course_id: 'DS101', class_id: 'ds-01' }])
    // risks / unresolved 是**字符串数组**
    expect(typeof envelope.data.risks[0]).toBe('string')
  })

  it('blocked（锁定课程被破坏）⇒ 无候选 + blocked_reason', async () => {
    useRealFetch(() => jsonResponse(SOLVE_RESPONSE_BLOCKED))
    const envelope = await solvePlan(SOLVE_REQUEST)

    expect(envelope.data.status).toBe('blocked')
    expect(envelope.data.candidate_id).toBeNull()
    expect(envelope.data.candidate_plan).toBeNull()
    expect(envelope.data.diff).toBeNull()
    expect(envelope.data.blocked_reason).toBe('locked_course_would_change')
  })

  it('no_feasible_candidate 也带 plan_kind=none', () => {
    const parsed = parseSolveResponse({
      ...SOLVE_RESPONSE_BLOCKED,
      status: 'no_feasible_candidate',
      blocked_reason: null,
    })
    expect(parsed.status).toBe('no_feasible_candidate')
    expect(parsed.plan_kind).toBe('none')
    expect(parsed.candidate_plan).toBeNull()
  })

  it('⛔ status=candidate_ready 却缺候选 / diff ⇒ ContractViolation', () => {
    expect(() =>
      parseSolveResponse({ ...SOLVE_RESPONSE_CANDIDATE, candidate_plan: null, diff: null }),
    ).toThrow(ContractViolation)
  })

  it('⛔ 非 candidate_ready 却带候选 ⇒ ContractViolation（状态与内容矛盾）', () => {
    expect(() =>
      parseSolveResponse({
        ...SOLVE_RESPONSE_BLOCKED,
        candidate_plan: SOLVE_RESPONSE_CANDIDATE.candidate_plan,
        diff: SOLVE_RESPONSE_CANDIDATE.diff,
      }),
    ).toThrow(ContractViolation)
  })

  it('⛔ 旧契约的 status="candidate" 不再被接受', () => {
    expect(() =>
      parseSolveResponse({ ...SOLVE_RESPONSE_CANDIDATE, status: 'candidate' }),
    ).toThrow(ContractViolation)
  })

  it('credit_delta=null 与 credit_unknown_course_ids 被如实保留（不猜学分）', () => {
    const parsed = parseSolveResponse({
      ...SOLVE_RESPONSE_CANDIDATE,
      diff: {
        ...SOLVE_RESPONSE_CANDIDATE.diff,
        candidate_credit: null,
        credit_delta: null,
        credit_unknown_course_ids: ['ALGO201'],
      },
    })
    expect(parsed.diff?.credit_delta).toBeNull()
    expect(parsed.diff?.credit_unknown_course_ids).toEqual(['ALGO201'])
  })
})

/* ------------------------------------------------------------------ *
 * ③ adopt
 * ------------------------------------------------------------------ */

describe('adopt：不返回方案体', () => {
  it('采用成功 ⇒ accepted / state / adopted_version / process_local_session', async () => {
    const mock = useRealFetch(() => jsonResponse(ADOPT_RESPONSE_ACCEPTED))
    const envelope = await adoptCandidate({
      candidate_id: 'candidate_1b69e89768ff7e4e',
      plan_digest: PLAN_DIGEST,
      accept: true,
    })

    const [url, init] = mock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/v1/ai-planning/adopt')
    expect(Object.keys(JSON.parse(init.body as string)).sort()).toEqual([
      'accept',
      'candidate_id',
      'plan_digest',
    ])

    expect(envelope.data.accepted).toBe(true)
    expect(envelope.data.state).toBe('adopted')
    expect(envelope.data.adopted_version).toBe(1)
    expect(envelope.data.adopted_version_scope).toBe('process_local_session')
    expect(envelope.data.original_plan_unchanged).toBe(false)
    // ⛔ 后端不返回方案体：解析结果里**没有**任何 adopted_plan 字段
    expect(Object.keys(envelope.data)).not.toContain('adopted_plan')
  })

  it('拒绝候选 ⇒ accepted=false / original_plan_unchanged=true', async () => {
    useRealFetch(() => jsonResponse(ADOPT_RESPONSE_REJECTED))
    const envelope = await adoptCandidate({
      candidate_id: 'candidate_1b69e89768ff7e4e',
      plan_digest: PLAN_DIGEST,
      accept: false,
    })

    expect(envelope.data.accepted).toBe(false)
    expect(envelope.data.state).toBe('rejected')
    expect(envelope.data.original_plan_unchanged).toBe(true)
  })

  it('⛔ adopted_version_scope 只接受 process_local_session（不得伪造持久化语义）', () => {
    expect(() =>
      parseAdoptResponse({
        ...ADOPT_RESPONSE_ACCEPTED,
        adopted_version_scope: 'persistent_account',
      }),
    ).toThrow(ContractViolation)
  })

  it('⛔ state 只接受 adopted / rejected', () => {
    expect(() =>
      parseAdoptResponse({ ...ADOPT_RESPONSE_ACCEPTED, state: 'saved' }),
    ).toThrow(ContractViolation)
  })
})

/* ------------------------------------------------------------------ *
 * ④ status 与错误码映射
 * ------------------------------------------------------------------ */

describe('GET /status', () => {
  it('解析可用状态（⛔ 响应里没有密钥）', async () => {
    useRealFetch(() => jsonResponse(STATUS_RESPONSE))
    const envelope = await fetchAiPlanningStatus()

    expect(envelope.data.enabled).toBe(true)
    expect(envelope.data.api_key_configured).toBe(false)
    expect(envelope.data.adopt_ttl_seconds).toBe(900)
    expect(envelope.data.generator_kind_when_live).toBe('deepseek_live')
    expect(JSON.stringify(envelope.data)).not.toContain('sk-')
  })

  it('该私有前缀尚未部署（404 且无结构化 code）⇒ absent，而不是 session_not_found', async () => {
    useRealFetch(() => new Response('Not Found', { status: 404 }))
    await expect(fetchAiPlanningStatus()).rejects.toMatchObject({
      kind: 'absent',
    })
  })

  it('后端已实现但未启用（503 ai_planning_disabled）⇒ disabled', async () => {
    useRealFetch(() =>
      jsonResponse(
        { detail: { error: 'ai_planning_disabled', message: 'AI 规划控制器未启用。' } },
        503,
      ),
    )
    await expect(fetchAiPlanningStatus()).rejects.toMatchObject({
      kind: 'disabled',
    })
  })
})

describe('错误码 → 分类（与后端固定码表一致）', () => {
  const cases: [string, number, string][] = [
    ['ai_planning_disabled', 503, 'disabled'],
    ['ai_planning_model_unavailable', 503, 'model_unavailable'],
    ['ai_planning_message_rejected', 400, 'message_rejected'],
    ['ai_planning_model_output_invalid', 422, 'model_output_invalid'],
    ['ai_planning_intent_invalid', 422, 'intent_invalid'],
    ['ai_planning_plan_context_invalid', 422, 'plan_context_invalid'],
    ['ai_planning_intent_not_confirmable', 409, 'intent_not_confirmable'],
    ['ai_planning_adoption_conflict', 409, 'adoption_conflict'],
    ['ai_planning_session_not_found', 404, 'session_not_found'],
    ['ai_planning_session_expired', 410, 'session_expired'],
    ['ai_planning_solve_unsupported', 501, 'solve_unsupported'],
    ['ai_planning_candidate_invalid', 502, 'candidate_invalid'],
    ['ai_planning_budget_exceeded', 429, 'budget_exceeded'],
  ]

  it.each(cases)('%s ⇒ %s', (code, status, kind) => {
    expect(classifyAiPlanningError(status, code)).toBe(kind)
  })

  it('无 code 时按状态码兜底（404 ⇒ session_not_found，501 ⇒ solve_unsupported）', () => {
    expect(classifyAiPlanningError(404, null)).toBe('session_not_found')
    expect(classifyAiPlanningError(501, null)).toBe('solve_unsupported')
    expect(classifyAiPlanningError(500, null)).toBe('server')
  })

  it('会话过期 / 不存在时抛出带 code 的错误（界面据此提示"重新解析"）', async () => {
    useRealFetch(() =>
      jsonResponse(
        { detail: { error: 'ai_planning_session_expired', message: '指纹已变化。' } },
        410,
      ),
    )
    const error = await solvePlan(SOLVE_REQUEST).catch(
      (reason: unknown) => reason,
    )
    expect(error).toBeInstanceOf(AiPlanningApiError)
    expect((error as AiPlanningApiError).kind).toBe('session_expired')
    expect((error as AiPlanningApiError).status).toBe(410)
  })

  it('未知错误码按状态码兜底，⛔ 不被当成"接口未配置"', async () => {
    useRealFetch(() => jsonResponse({ detail: { error: 'something_new', message: 'x' } }, 422))
    await expect(
      interpretIntent(INTERPRET_REQUEST),
    ).rejects.toMatchObject({ kind: 'intent_invalid' })
  })
})

/* ------------------------------------------------------------------ *
 * 解析器单测（无需 fetch）
 * ------------------------------------------------------------------ */

describe('解析器边界', () => {
  it('parseStatusResponse 缺字段即失败', () => {
    expect(() => parseStatusResponse({ enabled: true })).toThrow(ContractViolation)
  })

  it('parseAdoptResponse 缺字段即失败', () => {
    expect(() => parseAdoptResponse({ accepted: true })).toThrow(ContractViolation)
  })

  it('parseSolveResponse：risks 必须是字符串数组（不是对象数组）', () => {
    expect(() =>
      parseSolveResponse({
        ...SOLVE_RESPONSE_CANDIDATE,
        risks: [{ level: 'high', reason: '旧形状' }],
      }),
    ).toThrow(ContractViolation)
  })
})
