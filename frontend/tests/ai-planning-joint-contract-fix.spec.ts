/**
 * 联调修复回归测试：两处**真实存在过**的前端与后端形状错配。
 *
 * 这两处都不是"猜的"，而是用真实后端响应（`backend/tests/test_ai_planning_joint_e2e.py`
 * 的真实 HTTP 用例）核出来的：
 *
 * ① `diff.replaced[]` 的键是 `from_class` / `to_class`（换班），
 *    而前端解析器与对比面板按 `class_id` 解析 ⇒
 *    一旦后端产生换班，解析会抛 `ContractViolation`（或在面板上显示 `undefined`）。
 * ② `parsed_intent.locked_courses[].reason` 在后端是**可空**字段 ⇒
 *    后端返回 `null` 时前端会拒绝整份草稿。
 *
 * ⛔ 这两条都不是"放宽契约"：它们只是把前端**对齐到后端已发布的真实形状**。
 */

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import {
  ContractViolation,
  parseInterpretResponse,
  parsePlanDiff,
  parseSolveResponse,
} from '@/api/aiPlanningContract'
import CandidateComparePanel from '@/components/ai/CandidateComparePanel.vue'

const PLAN_DIGEST = 'a'.repeat(64)

function solvePayloadWith(overrides: Record<string, unknown>) {
  return {
    candidate_id: 'candidate_x',
    status: 'candidate_ready',
    plan_kind: 'PlanResult',
    candidate_plan: {
      status: 'partially_feasible',
      selected_classes: [
        { course_id: 'DS101', class_id: 'ds-02' },
      ],
      changes: [],
      risks: [],
      unresolved: [],
      objective_summary: 'mock',
    },
    diff: {
      added: [{ course_id: 'DS101', class_id: 'ds-02' }],
      removed: [{ course_id: 'DS101', class_id: 'ds-01' }],
      replaced: [{ course_id: 'DS101', from_class: 'ds-01', to_class: 'ds-02' }],
      kept: [],
      base_credit: 3,
      candidate_credit: 3,
      credit_delta: 0,
      credit_unknown_course_ids: [],
      empty: false,
    },
    risks: [],
    unresolved: [],
    message: 'mock',
    blocked_reason: null,
    data_source: 'mock',
    generator_kind: 'test_double',
    plan_digest: PLAN_DIGEST,
    ...overrides,
  }
}

describe('diff.replaced 的真实后端形状（from_class / to_class）', () => {
  it('解析 replaced 行并保留换班前后班号', () => {
    const diff = parsePlanDiff({
      added: [],
      removed: [],
      replaced: [{ course_id: 'DS101', from_class: 'ds-01', to_class: 'ds-02' }],
      kept: [],
      base_credit: 3,
      candidate_credit: 3,
      credit_delta: 0,
      credit_unknown_course_ids: [],
      empty: false,
    })
    expect(diff.replaced).toHaveLength(1)
    expect(diff.replaced[0]).toEqual({
      course_id: 'DS101',
      from_class: 'ds-01',
      to_class: 'ds-02',
    })
    // ⛔ 换班行没有 class_id：不得补一个假的班号
    expect(diff.replaced[0].class_id).toBeUndefined()
  })

  it('solve 响应里的换班行不再让解析器抛错', () => {
    const parsed = parseSolveResponse(solvePayloadWith({}))
    expect(parsed.diff?.replaced[0].to_class).toBe('ds-02')
    expect(parsed.diff?.added[0].class_id).toBe('ds-02')
  })

  it('⛔ replaced 行既没有 class_id 也没有 from/to ⇒ 仍然拒绝（不放宽契约）', () => {
    expect(() =>
      parsePlanDiff({
        added: [],
        removed: [],
        replaced: [{ course_id: 'DS101' }],
        kept: [],
        base_credit: null,
        candidate_credit: null,
        credit_delta: null,
        credit_unknown_course_ids: [],
        empty: false,
      }),
    ).toThrow(ContractViolation)
  })

  it('对比面板把换班显示成 "from → to"，并提示不要与新增/移除重复理解', () => {
    const solve = parseSolveResponse(solvePayloadWith({}))
    const wrapper = mount(CandidateComparePanel, {
      props: {
        solve,
        originalPlan: {
          status: 'partially_feasible',
          selected_classes: [{ course_id: 'DS101', class_id: 'ds-01' }],
          changes: [],
          risks: [],
          unresolved: [],
          objective_summary: null,
        },
        originalLabel: '原方案',
        generatorKind: 'test_double',
        dataSource: 'mock',
        blockedReasonLabel: null,
        previewNotice: null,
        disabled: false,
        busy: false,
      },
    })

    const html = wrapper.html()
    // ⛔ 不得出现 undefined（旧实现按 class_id 取不到值时就会这样）
    expect(html).not.toContain('undefined')
    expect(html).toContain('ds-01 → ds-02')
    expect(wrapper.find('[data-testid="ai-replaced-note"]').exists()).toBe(true)
  })
})

describe('locked_courses[].reason 在后端可空', () => {
  it('reason=null 时规范成空串，⛔ 不因此拒绝整份草稿', () => {
    const parsed = parseInterpretResponse({
      intent_id: 'intent_x',
      plan_digest: PLAN_DIGEST,
      parsed_intent: {
        summary: 'mock',
        scope: 'current_semester',
        target_semester: '2026-1',
        hard_constraints: [],
        soft_preferences: [],
        locked_courses: [
          { course_id: 'DS101', class_id: 'ds-01', reason: null },
          { course_id: 'ALGO201', class_id: 'algo-02' },
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
      token_usage_estimate: { prompt: 1, completion: 1, total: 2 },
      message: 'mock',
    })
    expect(parsed.parsed_intent.locked_courses).toHaveLength(2)
    expect(parsed.parsed_intent.locked_courses[0].reason).toBe('')
    expect(parsed.parsed_intent.locked_courses[1].reason).toBe('')
  })

  it('⛔ reason 是非法的数字时仍然拒绝（只接受 null / 缺省 / 字符串）', () => {
    expect(() =>
      parseInterpretResponse({
        intent_id: 'intent_x',
        plan_digest: PLAN_DIGEST,
        parsed_intent: {
          summary: 'mock',
          scope: 'current_semester',
          target_semester: null,
          hard_constraints: [],
          soft_preferences: [],
          locked_courses: [{ course_id: 'DS101', class_id: 'ds-01', reason: 42 }],
          confidence: 0.6,
          notes: [],
          ambiguities: [],
        },
        ambiguities: [],
        data_source: 'mock',
        generator_kind: 'test_double',
        generator_note: 'mock',
        model_id: 'm',
        can_confirm: true,
        state: 'intent_draft',
        token_usage_estimate: { prompt: 1, completion: 1, total: 2 },
        message: 'mock',
      }),
    ).toThrow(ContractViolation)
  })
})
