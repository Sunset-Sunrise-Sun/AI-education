/**
 * AI 规划的**前端预览 fixture**（离线演示 / 组件测试专用）。
 *
 * ⛔ 三条红线：
 * 1. 全部内容都是**人工构造的前端预览数据**，不是后端返回、不是模型输出、
 *    也不是 Planner 求解结果；
 * 2. 只在 `VITE_AI_PLANNING_PREVIEW=true` 时被使用，界面必须显示
 *    `AI_PREVIEW_NOTICE`；
 * 3. **生产请求失败时绝不 fallback 到本文件**（适配层不含任何 fixture 回退路径）。
 */

import type {
  AiAdoptResponse,
  AiInterpretResponse,
  AiSolveResponse,
} from './aiPlanningTypes'

/** 预览模式的统一醒目标注（界面必须原样显示）。 */
export const AI_PREVIEW_NOTICE = '仅前端预览 / 非真实模型 / 未调用 Planner'

/** 预览数据固定使用的来源指纹（不是真实 sha256，避免被误读为真实摘要）。 */
export const PREVIEW_PLAN_DIGEST = 'preview-plan-digest'

/** 正常解析：硬约束 + 软偏好 + 锁定课程 + 未知项 + 歧义。 */
export const PREVIEW_INTERPRET_OK: AiInterpretResponse = {
  intent_id: 'preview-intent-1',
  plan_digest: PREVIEW_PLAN_DIGEST,
  data_source: 'mock',
  generator_kind: 'rule_based_template',
  can_confirm: true,
  parsed_intent: {
    hard_constraints: [
      {
        code: 'keep_course',
        course_id: '62001002',
        course_name: '数据结构与算法',
        raw_text: '数据结构必须保留',
        evidence: 'utterance',
        confidence: 0.9,
      },
    ],
    soft_preferences: [
      {
        code: 'lighter_semester',
        raw_text: '这学期尽量轻松',
        evidence: 'utterance',
        confidence: 0.8,
      },
      {
        code: 'complete_before_year_3',
        raw_text: '尽量在大三前补完',
        evidence: 'utterance',
        confidence: 0.7,
      },
    ],
    credit_limit: null,
    locked_course_ids: ['62001002'],
    scope: {
      semester: '2026-1',
      horizon: 'before_year_3',
      raw_text: '大三前补完',
    },
    unknowns: [
      {
        topic: '学分上限',
        detail: '学生没有说明本学期最多能承受多少学分',
        needs_user_input: true,
      },
    ],
  },
  ambiguities: [
    {
      code: 'possible_conflict',
      detail: '「这学期尽量轻松」与「数据结构必须保留」可能冲突：保留该课会占用课时。',
      options: ['保留课程并接受更重的学期', '放弃该课程'],
    },
  ],
  message: '（前端预览）已解析为待确认草稿；不是真实模型输出。',
}

/** 解析不足：`can_confirm=false`，前端必须禁止进入求解。 */
export const PREVIEW_INTERPRET_LOW_CONFIDENCE: AiInterpretResponse = {
  intent_id: 'preview-intent-2',
  plan_digest: PREVIEW_PLAN_DIGEST,
  data_source: 'mock',
  generator_kind: 'rule_based_template',
  can_confirm: false,
  parsed_intent: {
    hard_constraints: [],
    soft_preferences: [],
    credit_limit: null,
    locked_course_ids: [],
    scope: { semester: '2026-1', horizon: 'unknown', raw_text: '' },
    unknowns: [
      {
        topic: '整体意图',
        detail: '这句话里没有识别出可执行的约束或偏好',
        needs_user_input: true,
      },
    ],
  },
  ambiguities: [],
  message: '（前端预览）解析不足，需要学生补充说明后才能求解。',
}

/** 成功候选：含新增 / 移班 / 学分变化 / 硬约束检查 / 风险。 */
export const PREVIEW_SOLVE_CANDIDATE: AiSolveResponse = {
  candidate_id: 'preview-candidate-1',
  status: 'candidate',
  candidate_plan: {
    status: 'partially_feasible',
    selected_classes: [
      { course_id: '62001001', class_id: '6200100120260101' },
      { course_id: '62001002', class_id: '6200100220260101' },
      { course_id: '62002031', class_id: '6200203120260101' },
    ],
    changes: [
      {
        course_id: '62001002',
        from_class: '6200100220260102',
        to_class: '6200100220260101',
        reason: '（前端预览）为保留该课程并减轻周内连堂，改到周三 3-4 节教学班。',
      },
    ],
    risks: [
      {
        course_id: '62001002',
        level: 'medium',
        reason: '（前端预览）该教学班剩余容量偏低。',
      },
    ],
    unresolved: [
      {
        type: 'manual_confirmation',
        message: '（前端预览）复变函数与积分变换的学分差额仍需人工判定。',
      },
    ],
    objective_summary: '（前端预览）在保留数据结构的前提下减少本学期课时密度。',
  },
  plan_digest: PREVIEW_PLAN_DIGEST,
  candidate_digest: 'preview-candidate-digest-1',
  diff: {
    added: [
      {
        course_id: '62001001',
        course_name: '离散数学',
        class_id: '6200100120260101',
        credit: 3,
      },
    ],
    removed: [
      {
        course_id: '62003007',
        course_name: '复变函数与积分变换',
        class_id: '6200300720260101',
        credit: 2,
      },
    ],
    moved: [
      {
        course_id: '62001002',
        from_class: '6200100220260102',
        to_class: '6200100220260101',
        reason: '（前端预览）改到周三 3-4 节教学班。',
      },
    ],
    credit_delta: 1,
    hard_constraint_checks: [
      {
        code: 'keep_course',
        course_id: '62001002',
        satisfied: true,
        detail: '（前端预览）数据结构与算法仍在本学期方案内。',
      },
    ],
  },
  risks: [
    { course_id: '62001002', level: 'medium', reason: '（前端预览）剩余容量偏低。' },
  ],
  unresolved: [
    {
      type: 'manual_confirmation',
      message: '（前端预览）复变函数与积分变换的学分差额仍需人工判定。',
    },
  ],
  message: '（前端预览）已生成 1 个候选方案；未调用真实 Planner。',
  expires_at: null,
}

/** 无解：当前约束下不存在可行组合。 */
export const PREVIEW_SOLVE_INFEASIBLE: AiSolveResponse = {
  candidate_id: null,
  status: 'infeasible',
  candidate_plan: null,
  plan_digest: PREVIEW_PLAN_DIGEST,
  candidate_digest: null,
  diff: null,
  risks: [],
  unresolved: [],
  message: '（前端预览）当前约束下无可行组合：保留课程与学分上限同时满足不了。',
  expires_at: null,
}

/** 缺少必要条件：课表 / Planner / 模型不可用。 */
export const PREVIEW_SOLVE_UNAVAILABLE: AiSolveResponse = {
  candidate_id: null,
  status: 'unavailable',
  candidate_plan: null,
  plan_digest: PREVIEW_PLAN_DIGEST,
  candidate_digest: null,
  diff: null,
  risks: [],
  unresolved: [],
  message: '（前端预览）缺少已装配的教学班供给，本次没有调用 Planner。',
  expires_at: null,
}

/** 采用成功。 */
export const PREVIEW_ADOPT_ADOPTED: AiAdoptResponse = {
  status: 'adopted',
  adopted_plan: PREVIEW_SOLVE_CANDIDATE.candidate_plan,
  adopted_digest: 'preview-candidate-digest-1',
  result_version: 'v2',
  message: '（前端预览）已采用候选方案；真实环境需要后端确认。',
}

/** 候选 / 原方案过期。 */
export const PREVIEW_ADOPT_STALE: AiAdoptResponse = {
  status: 'stale_candidate',
  adopted_plan: null,
  adopted_digest: null,
  result_version: null,
  message: '（前端预览）候选已过期：原方案或候选在确认前发生变化，请重新求解。',
}

/** 后端拒绝采用。 */
export const PREVIEW_ADOPT_REJECTED: AiAdoptResponse = {
  status: 'rejected',
  adopted_plan: null,
  adopted_digest: null,
  result_version: null,
  message: '（前端预览）后端拒绝采用该候选（例如违反硬约束），原方案保持不变。',
}

/** 明确保留原方案（accept=false）。 */
export const PREVIEW_ADOPT_KEPT: AiAdoptResponse = {
  status: 'adopted',
  adopted_plan: null,
  adopted_digest: null,
  result_version: null,
  message: '（前端预览）已确认保留原方案。',
}

/** 后端尚未实现该能力。 */
export const PREVIEW_NOT_CONFIGURED_MESSAGE =
  'AI 调整接口尚未配置（后端未实现或未启用）。当前不会调用规划器，也不会生成候选方案。'
