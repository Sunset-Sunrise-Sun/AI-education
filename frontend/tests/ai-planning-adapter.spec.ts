/**
 * AI 规划适配层测试（开关、预览隔离、错误分类）。
 *
 * ⚠️ 真实后端契约形状测试在 `ai-planning-contract.spec.ts`；
 * 本文件覆盖：开关语义、预览 fixture 不伪造、预览**不发真实请求**、
 * 以及"强制真实路径"时的错误分类与不 fallback。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  aiPlanningCapability,
  aiPlanningFlags,
  interpretIntent,
  parseAiPlanningErrorBody,
  previewResolvers,
  setAiPreviewScenario,
} from '@/api/aiPlanning'
import { AI_PREVIEW_NOTICE } from '@/api/aiPlanningFixtures'
import type { AiInterpretRequest } from '@/api/aiPlanningContract'

const INTERPRET_REQUEST: AiInterpretRequest = {
  context: {
    semester: '2026-1',
    base_plan: {
      status: 'partially_feasible',
      selected_classes: [{ course_id: 'DS101', class_id: 'ds-01' }],
      changes: [],
      risks: [],
      unresolved: [],
    },
    makeup_tasks: [],
    course_offerings: [],
    preference: {
      max_credit: 20,
      avoid_cross_campus: false,
      preferred_courses: [],
      avoid_times: [],
      notes: null,
    },
  },
  user_message: '这学期太累，尽量别在周五上课',
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAiPreviewScenario('ok')
})

describe('适配层开关与能力状态', () => {
  it('测试环境打开预览：能力状态为 preview，并给出"仅前端预览"标注', () => {
    expect(aiPlanningFlags()).toEqual({ apiEnabled: false, preview: true })
    const capability = aiPlanningCapability()
    expect(capability.mode).toBe('preview')
    expect(capability.notice).toContain('仅前端预览')
    expect(capability.notice).toContain('非真实模型')
    expect(capability.notice).toContain('未调用 Planner')
  })

  it('预览模式下发请求不产生任何 HTTP 调用（fixture 只读）', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const envelope = await interpretIntent(INTERPRET_REQUEST)
    expect(envelope.source).toBe('preview_fixture')
    expect(envelope.previewNotice).toBe(AI_PREVIEW_NOTICE)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('无预览且开关关闭 ⇒ 抛 absent 且不发请求（不伪造、不 fallback）', async () => {
    vi.stubEnv('VITE_AI_PLANNING_API_ENABLED', 'false')
    vi.stubEnv('VITE_AI_PLANNING_PREVIEW', 'false')
    vi.resetModules()
    const adapter = await import('@/api/aiPlanning')

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    expect(adapter.aiPlanningCapability().mode).toBe('api_disabled')
    await expect(adapter.interpretIntent(INTERPRET_REQUEST)).rejects.toMatchObject({
      kind: 'absent',
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('错误体解析', () => {
  it('解析后端统一错误体 {detail:{error,message}}', () => {
    expect(
      parseAiPlanningErrorBody({ detail: { error: 'ai_planning_disabled', message: '未启用' } }),
    ).toEqual({ code: 'ai_planning_disabled', detail: '未启用' })
  })

  it('解析 FastAPI 422 数组形状', () => {
    expect(parseAiPlanningErrorBody({ detail: [{ type: 'value_error', msg: 'bad' }] })).toEqual({
      code: 'value_error',
      detail: 'bad',
    })
  })

  it('未知形状不抛错', () => {
    expect(parseAiPlanningErrorBody('plain')).toEqual({ code: null, detail: 'plain' })
    expect(parseAiPlanningErrorBody(null)).toEqual({ code: null, detail: null })
  })
})

describe('预览 fixture：形状与标注', () => {
  it('每个场景都是后端形状：generator_kind 三值之一、data_source 四值之一', () => {
    const scenarios = ['ok', 'ambiguous', 'no_feasible', 'blocked'] as const
    for (const scenario of scenarios) {
      const interpret = previewResolvers.interpret(scenario)
      expect(['deepseek_live', 'test_double', 'unavailable']).toContain(interpret.generator_kind)
      expect(['real', 'mock', 'mixed', 'unknown']).toContain(interpret.data_source)
      expect(interpret.message).toContain('前端预览')
      expect(typeof interpret.plan_digest).toBe('string')
      expect(interpret.parsed_intent.confidence).toBeGreaterThanOrEqual(0)
    }
  })

  it('歧义场景：can_confirm=false，且歧义码来自后端固定白名单', () => {
    const ambiguous = previewResolvers.interpret('ambiguous')
    expect(ambiguous.can_confirm).toBe(false)
    expect(ambiguous.ambiguities.length).toBeGreaterThan(0)
    expect(ambiguous.ambiguities[0]?.code).toBe('credit_limit_missing_evidence')
    expect(ambiguous.ambiguities[0]?.question).toContain('不会替你猜')
  })

  it('求解场景：成功值必须是 candidate_ready（⛔ 不是旧的 candidate）', () => {
    expect(previewResolvers.solve('ok').status).toBe('candidate_ready')
    expect(previewResolvers.solve('no_feasible').status).toBe('no_feasible_candidate')
    expect(previewResolvers.solve('blocked').status).toBe('blocked')
    expect(previewResolvers.solve('blocked').blocked_reason).toBe('locked_course_would_change')
  })

  it('非成功状态一律不带候选（避免"看起来生成了"）', () => {
    for (const status of ['no_feasible', 'blocked'] as const) {
      const solve = previewResolvers.solve(status)
      expect(solve.candidate_id).toBeNull()
      expect(solve.candidate_plan).toBeNull()
      expect(solve.diff).toBeNull()
    }
  })

  it('候选场景：diff 含 added/removed/replaced/kept 与学分口径', () => {
    const candidate = previewResolvers.solve('ok')
    expect(candidate.diff?.added.length).toBeGreaterThan(0)
    expect(candidate.diff?.removed.length).toBeGreaterThan(0)
    expect(candidate.diff?.kept).toEqual([])
    expect(candidate.diff?.credit_delta).toBe(2)
    expect(candidate.plan_kind).toBe('PlanResult')
  })

  it('adopt 场景：**没有** adopted_plan 字段；scope 是进程内会话', () => {
    const accepted = previewResolvers.adopt(true, 'ok')
    expect(Object.keys(accepted)).not.toContain('adopted_plan')
    expect(accepted.adopted_version_scope).toBe('process_local_session')

    const kept = previewResolvers.adopt(false)
    expect(kept.accepted).toBe(false)
    expect(kept.original_plan_unchanged).toBe(true)
  })

  it('status 场景：测试替身不是"线上模型可用"', () => {
    const testDouble = previewResolvers.status('ok')
    expect(testDouble.enabled).toBe(true)
    expect(testDouble.live_model_available).toBe(false)

    const live = previewResolvers.status('status_live')
    expect(live.live_model_available).toBe(true)
    expect(live.generator_kind_when_live).toBe('deepseek_live')

    const disabled = previewResolvers.status('status_disabled')
    expect(disabled.enabled).toBe(false)
  })
})
