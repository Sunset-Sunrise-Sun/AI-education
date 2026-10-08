/**
 * AI 规划适配层测试。
 *
 * 重点（与任务书一致）：
 * - 契约字段缺失 / 状态与内容矛盾 ⇒ `unexpected`，⛔ 不补默认值、不猜测；
 * - 404/501 ⇒ `not_configured`（界面显示"尚未配置"），⛔ 不伪造成成功；
 * - `plan_digest` 回显不一致 ⇒ `conflict`（原方案可能已变化）；
 * - **生产失败不 fallback**：真实模式下 fixture 绝不会被返回；
 * - 预览 fixture 必须带醒目标注，且明确标注不是模型输出。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AiPlanningApiError,
  aiPlanningCapability,
  aiPlanningFlags,
  parseAiPlanningErrorBody,
  previewResolvers,
} from '@/api/aiPlanning'
import { AI_PREVIEW_NOTICE, PREVIEW_PLAN_DIGEST } from '@/api/aiPlanningFixtures'
import type { AiInterpretRequest, AiSolveRequest } from '@/api/aiPlanningTypes'

const INTERPRET_REQUEST: AiInterpretRequest = {
  utterance: '尽量在大三前补完，这学期尽量轻松，但数据结构必须保留',
  plan_digest: 'sha256:current',
  target_semester: '2026-1',
  current_schedule_count: 2,
}

const SOLVE_REQUEST: AiSolveRequest = {
  intent_id: 'intent-1',
  plan_digest: 'sha256:current',
  confirmed_intent: {
    hard_constraints: [],
    soft_preferences: [],
    credit_limit: 18,
    locked_course_ids: [],
    scope: { semester: '2026-1', horizon: 'unknown', raw_text: '' },
    unknowns: [],
  },
  semester: '2026-1',
}

const INTERPRET_OK_BODY = {
  intent_id: 'intent-1',
  plan_digest: 'sha256:current',
  data_source: 'real',
  generator_kind: 'model',
  can_confirm: true,
  parsed_intent: {
    hard_constraints: [],
    soft_preferences: [],
    credit_limit: null,
    locked_course_ids: [],
    scope: { semester: '2026-1', horizon: 'unknown', raw_text: '' },
    unknowns: [],
  },
  ambiguities: [],
  message: 'ok',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('适配层开关与能力状态', () => {
  it('测试环境打开预览：能力状态为 preview，并给出"仅前端预览"标注', () => {
    // vitest 配置把 VITE_AI_PLANNING_PREVIEW 置为 true；
    // 真实接口开关保持关闭（默认），因此这里只可能走预览。
    expect(aiPlanningFlags()).toEqual({ apiEnabled: false, preview: true })
    const capability = aiPlanningCapability()
    expect(capability.mode).toBe('preview')
    expect(capability.notice).toContain('仅前端预览')
    expect(capability.notice).toContain('非真实模型')
  })

  it('预览模式下发请求不产生任何 HTTP 调用（fixture 只读）', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { interpretIntent } = await import('@/api/aiPlanning')
    const envelope = await interpretIntent(INTERPRET_REQUEST)

    expect(envelope.source).toBe('preview_fixture')
    expect(envelope.previewNotice).toContain('未调用 Planner')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('无预览且开关关闭 ⇒ 抛 disabled 且不发请求', async () => {
    vi.stubEnv('VITE_AI_PLANNING_API_ENABLED', 'false')
    vi.stubEnv('VITE_AI_PLANNING_PREVIEW', 'false')
    vi.resetModules()
    const adapter = await import('@/api/aiPlanning')

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    expect(adapter.aiPlanningCapability().mode).toBe('disabled')
    await expect(adapter.interpretIntent(INTERPRET_REQUEST)).rejects.toMatchObject({
      kind: 'disabled',
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('错误体解析与状态分类', () => {
  it('解析已知 detail 形状', () => {
    expect(
      parseAiPlanningErrorBody({ detail: { error: 'ai_planning_not_configured', message: 'x' } }),
    ).toEqual({ code: 'ai_planning_not_configured', detail: 'x' })
  })

  it('解析 FastAPI 422 形状（数组 detail）', () => {
    expect(parseAiPlanningErrorBody({ detail: [{ type: 'value_error', msg: 'bad' }] })).toEqual({
      code: 'value_error',
      detail: 'bad',
    })
  })

  it('未知形状不抛错（由状态码分类）', () => {
    expect(parseAiPlanningErrorBody('plain text')).toEqual({ code: null, detail: 'plain text' })
    expect(parseAiPlanningErrorBody(null)).toEqual({ code: null, detail: null })
  })
})

describe('预览 fixture：标注与场景', () => {
  it('每个场景都带"仅前端预览"标注，且明确不是模型/Planner 输出', () => {
    const scenarios = [
      'ok',
      'low_confidence',
      'candidate',
      'infeasible',
      'unavailable',
      'stale',
      'rejected',
    ] as const

    for (const scenario of scenarios) {
      const interpret = previewResolvers.interpret(scenario)
      expect(interpret.generator_kind).toBe('rule_based_template')
      expect(interpret.message).toContain('前端预览')
      expect(AI_PREVIEW_NOTICE).toContain('非真实模型')
      expect(AI_PREVIEW_NOTICE).toContain('未调用 Planner')
    }
  })

  it('解析不足场景：can_confirm 为 false，且列出来未知项', () => {
    const low = previewResolvers.interpret('low_confidence')
    expect(low.can_confirm).toBe(false)
    expect(low.parsed_intent.unknowns.length).toBeGreaterThan(0)
    expect(low.parsed_intent.credit_limit).toBeNull()
  })

  it('预览方案：学分上限为 null（不猜默认值），未知项要求用户补充', () => {
    const ok = previewResolvers.interpret('ok')
    expect(ok.parsed_intent.credit_limit).toBeNull()
    expect(ok.parsed_intent.locked_course_ids).toContain('62001002')
    expect(ok.parsed_intent.unknowns.some((item) => item.needs_user_input)).toBe(true)
    expect(ok.plan_digest).toBe(PREVIEW_PLAN_DIGEST)
  })

  it('求解场景：无解 / 缺条件 都不带候选（避免"看起来生成了"）', () => {
    const infeasible = previewResolvers.solve('infeasible')
    expect(infeasible.status).toBe('infeasible')
    expect(infeasible.candidate_plan).toBeNull()
    expect(infeasible.candidate_id).toBeNull()

    const unavailable = previewResolvers.solve('unavailable')
    expect(unavailable.status).toBe('unavailable')
    expect(unavailable.candidate_plan).toBeNull()
  })

  it('候选场景：带 diff 与硬约束核对，风险/未决非空', () => {
    const candidate = previewResolvers.solve('candidate')
    expect(candidate.status).toBe('candidate')
    expect(candidate.candidate_plan).not.toBeNull()
    expect(candidate.diff?.hard_constraint_checks.length).toBeGreaterThan(0)
    expect(candidate.diff?.added.length).toBeGreaterThan(0)
    expect(candidate.diff?.moved.length).toBeGreaterThan(0)
  })

  it('采用场景：过期 / 拒绝 / 保留原方案语义各不相同', () => {
    expect(previewResolvers.adopt(true, 'stale').status).toBe('stale_candidate')
    expect(previewResolvers.adopt(true, 'stale').adopted_plan).toBeNull()
    expect(previewResolvers.adopt(true, 'rejected').status).toBe('rejected')
    expect(previewResolvers.adopt(true, 'rejected').adopted_plan).toBeNull()
    expect(previewResolvers.adopt(false).adopted_plan).toBeNull()
    expect(previewResolvers.adopt(false).message).toContain('保留原方案')
  })
})

describe('真实模式：错误分类与不 fallback', () => {
  async function loadEnabledAdapter() {
    vi.stubEnv('VITE_AI_PLANNING_API_ENABLED', 'true')
    vi.stubEnv('VITE_AI_PLANNING_PREVIEW', 'false')
    vi.resetModules()
    return import('@/api/aiPlanning')
  }

  it('404 ⇒ not_configured，且绝不返回 fixture 内容（不 fallback）', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('not found', { status: 404 }))),
    )

    await expect(adapter.interpretIntent(INTERPRET_REQUEST)).rejects.toMatchObject({
      kind: 'not_configured',
    })
    expect(adapter.aiPlanningCapability().mode).toBe('backend')
  })

  it('503 ⇒ unavailable，并保留后端错误码', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            { detail: { error: 'ai_planning_runtime_unavailable', message: 'no offerings' } },
            503,
          ),
        ),
      ),
    )

    await expect(adapter.interpretIntent(INTERPRET_REQUEST)).rejects.toMatchObject({
      kind: 'unavailable',
      code: 'ai_planning_runtime_unavailable',
    })
  })

  it('网络失败 ⇒ network', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('boom'))))

    await expect(adapter.interpretIntent(INTERPRET_REQUEST)).rejects.toMatchObject({
      kind: 'network',
    })
  })

  it('缺少必需字段 ⇒ unexpected（不补默认值）', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ plan_digest: 'sha256:current' }))),
    )

    await expect(adapter.interpretIntent(INTERPRET_REQUEST)).rejects.toMatchObject({
      kind: 'unexpected',
    })
  })

  it('plan_digest 回显不一致 ⇒ conflict（原方案可能已变化）', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse({ ...INTERPRET_OK_BODY, plan_digest: 'sha256:other' })),
      ),
    )

    await expect(adapter.interpretIntent(INTERPRET_REQUEST)).rejects.toMatchObject({
      kind: 'conflict',
      code: 'stale_plan',
    })
  })

  it('solve：status=infeasible 却带候选 ⇒ unexpected（状态与内容矛盾）', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({
            candidate_id: 'c1',
            status: 'infeasible',
            candidate_plan: { status: 'feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
            plan_digest: 'sha256:current',
            candidate_digest: 'sha256:cd',
            diff: { added: [], removed: [], moved: [], credit_delta: 0, hard_constraint_checks: [] },
            risks: [],
            unresolved: [],
            message: 'm',
            expires_at: null,
          }),
        ),
      ),
    )

    await expect(adapter.solvePlan(SOLVE_REQUEST)).rejects.toMatchObject({ kind: 'unexpected' })
  })

  it('solve：status=candidate 但缺 diff ⇒ unexpected', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({
            candidate_id: 'c1',
            status: 'candidate',
            candidate_plan: { status: 'feasible', selected_classes: [], changes: [], risks: [], unresolved: [] },
            plan_digest: 'sha256:current',
            candidate_digest: 'sha256:cd',
            diff: null,
            risks: [],
            unresolved: [],
            message: 'm',
            expires_at: null,
          }),
        ),
      ),
    )

    await expect(adapter.solvePlan(SOLVE_REQUEST)).rejects.toMatchObject({ kind: 'unexpected' })
  })

  it('adopt：声称 adopted 但没有 adopted_plan ⇒ unexpected（不刷新当前方案）', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({
            status: 'adopted',
            adopted_plan: null,
            adopted_digest: null,
            result_version: 'v2',
            message: 'adopted',
          }),
        ),
      ),
    )

    await expect(
      adapter.adoptCandidate({
        candidate_id: 'c1',
        plan_digest: 'sha256:current',
        candidate_digest: 'sha256:cd',
        accept: true,
      }),
    ).rejects.toMatchObject({ kind: 'unexpected' })
  })

  it('成功响应包裹为 backend 来源（不冒充预览）', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse(INTERPRET_OK_BODY))))

    const envelope = await adapter.interpretIntent(INTERPRET_REQUEST)
    expect(envelope.source).toBe('backend')
    expect(envelope.previewNotice).toBeNull()
    expect(envelope.data.intent_id).toBe('intent-1')
  })

  it('错误类型是公开的 class（界面只按 kind 分支）', async () => {
    const adapter = await loadEnabledAdapter()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('', { status: 500 }))))

    // ⚠️ 动态 import 拿到的是**独立模块实例**，因此与静态导入的 class 不是同一个对象；
    //    这里断言它确实是该实例自己导出的 `AiPlanningApiError`，并带正确的 kind。
    const error = await adapter.interpretIntent(INTERPRET_REQUEST).catch((reason: unknown) => reason)
    expect(error).toBeInstanceOf(adapter.AiPlanningApiError)
    expect((error as { kind: string }).kind).toBe('server')
  })
})
