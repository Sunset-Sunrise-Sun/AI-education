/**
 * AI 规划的**前端预览 fixture**（离线演示 / 组件测试专用）。
 *
 * ⛔ 三条红线：
 * 1. 全部内容都是**人工构造的前端预览数据**，不是后端返回、不是模型输出、
 *    也不是 Planner 求解结果；
 * 2. 只在 `VITE_AI_PLANNING_PREVIEW=true` 时被使用，界面必须显示
 *    `AI_PREVIEW_NOTICE`；
 * 3. **生产请求失败时绝不 fallback 到本文件**（适配层不含任何 fixture 回退路径）。
 *
 * ⚠️ 形状严格对齐后端契约（`AI_PLANNING_API_HANDOFF.md`）：
 * - `plan_digest` 在真实环境是 64 位十六进制 SHA-256（由**后端**计算）；
 *   这里用固定占位串并明确标注为预览值，避免被误读为真实摘要；
 * - `solve` 的成功状态是 `candidate_ready`；
 * - `adopt` **不返回方案体**，只返回 `accepted / state / adopted_version / ...`。
 */

import type {
  AiAdoptResponse,
  AiInterpretResponse,
  AiPlanningStatusResponse,
  AiSolveResponse,
} from './aiPlanningContract'

/** 预览模式的统一醒目标注（界面必须原样显示）。 */
export const AI_PREVIEW_NOTICE = '仅前端预览 / 非真实模型 / 未调用 Planner'

/** 预览用占位指纹（⛔ 不是真实 sha256；真实指纹由后端计算）。 */
export const PREVIEW_PLAN_DIGEST =
  'preview0preview0preview0preview0preview0preview0preview0preview0'
/** 预览用候选 id（后端是不透明字符串，前端只回传不解析）。 */
export const PREVIEW_CANDIDATE_ID = 'candidate_preview_0001'

/** 正常解析：软偏好 + 锁定课程 + 无阻塞性歧义 ⇒ `can_confirm = true`。 */
export const PREVIEW_INTERPRET_OK: AiInterpretResponse = {
  intent_id: 'intent_preview_0001',
  plan_digest: PREVIEW_PLAN_DIGEST,
  parsed_intent: {
    summary: '（前端预览）学生想降低本学期负荷，同时保留数据结构与算法。',
    scope: 'current_semester',
    target_semester: '2026-1',
    hard_constraints: [],
    soft_preferences: [
      {
        kind: 'prefer_fewer_credits',
        value: null,
        note: '（前端预览）表达了降低负荷的意愿，但未给出学分数字',
      },
      { kind: 'avoid_weekday', value: 5, note: '（前端预览）尽量避开周五' },
    ],
    locked_courses: [
      {
        course_id: '62001002',
        class_id: '6200100220260102',
        reason: '（前端预览）学生明确要求保留该教学班',
      },
    ],
    confidence: 0.6,
    notes: ['（前端预览）以上内容不是真实模型输出。'],
    ambiguities: [],
  },
  ambiguities: [],
  data_source: 'mock',
  generator_kind: 'test_double',
  generator_note: '（前端预览）注入的测试替身模型（不是线上模型）',
  model_id: 'preview-rule-fixture',
  can_confirm: true,
  state: 'intent_draft',
  token_usage_estimate: { prompt: 412, completion: 96, total: 508 },
  message: '（前端预览）已生成意图草稿，请确认后再求解。',
}

/** 有歧义：`can_confirm = false`，必须由用户回答后才能求解。 */
export const PREVIEW_INTERPRET_WITH_AMBIGUITIES: AiInterpretResponse = {
  ...PREVIEW_INTERPRET_OK,
  intent_id: 'intent_preview_0002',
  parsed_intent: {
    ...PREVIEW_INTERPRET_OK.parsed_intent,
    summary: '（前端预览）学生说“太累了”，但没有给出可验证的学分上限。',
    locked_courses: [],
    soft_preferences: [
      { kind: 'prefer_fewer_credits', value: null, note: '（前端预览）未给出数字' },
    ],
    ambiguities: [
      {
        code: 'credit_limit_missing_evidence',
        question:
          '（前端预览）你说的“少上一点 / 太累”没有给出明确学分上限。请填写本学期的学分上限（例如 22），系统不会替你猜。',
        detail: '（前端预览）模型未给出可验证的学分上限依据',
      },
    ],
  },
  ambiguities: [
    {
      code: 'credit_limit_missing_evidence',
      question:
        '（前端预览）你说的“少上一点 / 太累”没有给出明确学分上限。请填写本学期的学分上限（例如 22），系统不会替你猜。',
      detail: '（前端预览）模型未给出可验证的学分上限依据',
    },
  ],
  can_confirm: false,
  message: '（前端预览）意图草稿中仍有必须由你回答的歧义，请先补充信息。',
}

/** 成功候选：`status = candidate_ready`。 */
export const PREVIEW_SOLVE_CANDIDATE: AiSolveResponse = {
  candidate_id: PREVIEW_CANDIDATE_ID,
  status: 'candidate_ready',
  plan_kind: 'PlanResult',
  candidate_plan: {
    status: 'partially_feasible',
    selected_classes: [
      { course_id: '62001001', class_id: '6200100120260101' },
      { course_id: '62001002', class_id: '6200100220260102' },
    ],
    changes: [
      {
        course_id: '62001001',
        from_class: null,
        to_class: '6200100120260101',
        reason: '（前端预览）新增 required 任务仅有一个教学班。',
      },
    ],
    risks: [],
    unresolved: [
      {
        type: 'manual_confirmation',
        message: '（前端预览）复变函数与积分变换的学分差额仍需人工判定。',
      },
    ],
    objective_summary: '（前端预览）受限 Planner 本学期建议课表（未调用真实 Planner）。',
  },
  diff: {
    added: [
      { course_id: '62001001', class_id: '6200100120260101' },
      { course_id: '62001002', class_id: '6200100220260102' },
    ],
    removed: [{ course_id: '62003007', class_id: '6200300720260101' }],
    replaced: [],
    kept: [],
    base_credit: 5,
    candidate_credit: 7,
    credit_delta: 2,
    credit_unknown_course_ids: [],
    empty: false,
  },
  risks: ['（前端预览）本次上下文的教学班数据来源为 mock，不代表真实教务开课。'],
  unresolved: ['（前端预览）课程 62003007 的补修认定仍需人工确认，不自动新增。'],
  message: '（前端预览）已按确认意图调用受控 Planner 生成候选；请对照差异后决定是否采用。',
  blocked_reason: null,
  data_source: 'mock',
  generator_kind: 'test_double',
  plan_digest: PREVIEW_PLAN_DIGEST,
}

/** 无可行候选（Planner 可运行但没有产生变化）。 */
export const PREVIEW_SOLVE_NO_FEASIBLE: AiSolveResponse = {
  candidate_id: null,
  status: 'no_feasible_candidate',
  plan_kind: 'none',
  candidate_plan: null,
  diff: null,
  risks: [],
  unresolved: ['（前端预览）在当前约束下没有产生任何变化。'],
  message: '（前端预览）当前约束下没有可行变化；原方案保持不变。',
  blocked_reason: null,
  data_source: 'mock',
  generator_kind: 'test_double',
  plan_digest: PREVIEW_PLAN_DIGEST,
}

/** 被阻塞（例如候选破坏了锁定课程）。 */
export const PREVIEW_SOLVE_BLOCKED: AiSolveResponse = {
  candidate_id: null,
  status: 'blocked',
  plan_kind: 'none',
  candidate_plan: null,
  diff: null,
  risks: [],
  unresolved: ['（前端预览）锁定的课程 62001002（班次 6200100220260102）在候选里发生了变化。'],
  message: '（前端预览）候选破坏了用户锁定的课程，已拒绝该候选并保留原方案。',
  blocked_reason: 'locked_course_would_change',
  data_source: 'mock',
  generator_kind: 'test_double',
  plan_digest: PREVIEW_PLAN_DIGEST,
}

/**
 * 采用成功（进程内会话版本）。
 *
 * ⚠️ **不包含方案体**：被采用的方案来自 `/solve` 已返回的候选。
 */
export const PREVIEW_ADOPT_ACCEPTED: AiAdoptResponse = {
  candidate_id: PREVIEW_CANDIDATE_ID,
  accepted: true,
  state: 'adopted',
  adopted_version: 1,
  adopted_version_scope: 'process_local_session',
  original_plan_unchanged: false,
  plan_digest: PREVIEW_PLAN_DIGEST,
  message: '（前端预览）已采用候选方案（仅在本进程会话内有效，未持久化）。',
}

/** 明确保留原方案（`accept=false`）。 */
export const PREVIEW_ADOPT_KEPT: AiAdoptResponse = {
  candidate_id: PREVIEW_CANDIDATE_ID,
  accepted: false,
  state: 'rejected',
  adopted_version: 0,
  adopted_version_scope: 'process_local_session',
  original_plan_unchanged: true,
  plan_digest: PREVIEW_PLAN_DIGEST,
  message: '（前端预览）已拒绝候选方案；原方案完全不变。',
}

/** 冲突（重复采用 / 已拒绝候选）。 */
export const PREVIEW_ADOPT_REJECTED: AiAdoptResponse = {
  candidate_id: PREVIEW_CANDIDATE_ID,
  accepted: false,
  state: 'rejected',
  adopted_version: 0,
  adopted_version_scope: 'process_local_session',
  original_plan_unchanged: true,
  plan_digest: PREVIEW_PLAN_DIGEST,
  message: '（前端预览）该候选已被处理过；原方案完全不变。',
}

/** 测试替身模型可用（⛔ 不是线上模型）。 */
export const PREVIEW_STATUS_TEST_DOUBLE: AiPlanningStatusResponse = {
  enabled: true,
  live_model_available: false,
  api_key_configured: false,
  max_calls_per_request: 3,
  request_timeout_seconds: 20,
  adopt_ttl_seconds: 900,
  model: 'deepseek-flash',
  base_url: 'https://api.deepseek.com',
  generator_kind_when_live: 'deepseek_live',
  data_source_note:
    '（前端预览）上下文 data_source 由教学班自身的 data_source 判定（mock / real / mixed / unknown）。',
}

/** 真实在线模型可用（仅用于展示"已接入"分支的文案）。 */
export const PREVIEW_STATUS_LIVE: AiPlanningStatusResponse = {
  ...PREVIEW_STATUS_TEST_DOUBLE,
  live_model_available: true,
  api_key_configured: true,
}

/** 后端已实现但未启用。 */
export const PREVIEW_STATUS_DISABLED: AiPlanningStatusResponse = {
  ...PREVIEW_STATUS_TEST_DOUBLE,
  enabled: false,
  live_model_available: false,
}

/** 该私有前缀尚未部署时的说明。 */
export const PREVIEW_NOT_CONFIGURED_MESSAGE =
  'AI 调整接口当前不可用（未启用或该私有前缀尚未部署）。页面不会伪造解析或候选方案。'
