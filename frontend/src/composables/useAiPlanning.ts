/**
 * AI 调整交互状态机（UI 层唯一的状态真源）。
 *
 * 流程与硬边界：
 *
 * ```text
 * idle ──parse──> interpreting ──> draft(待确认意图)
 *                                    │ 第一次确认（可编辑）
 *                                    v
 *                                 solving ──> candidate(候选)
 *                                    │            │ 第二次确认
 *                                    │            ├─ adopt  → adopted（只有后端确认才刷新方案）
 *                                    │            └─ keep   → kept（原方案不变）
 *                                    └─> unsolved / blocked（未生成候选，原案不变）
 * ```
 *
 * - ⛔ 前端**不计算**规划：不做冲突检测、不选教学班、不生成候选；
 * - ⛔ `draft` 阶段**不允许**求解（必须先第一次确认）；
 * - ⛔ 只有 `adopt` 返回 `adopted` 才允许把候选变成当前方案；
 * - ⛔ 失败 / 拒绝 / 过期 ⇒ 当前方案**一个字都不改**。
 */

import { computed, reactive, ref } from 'vue'
import {
  AiPlanningApiError,
  adoptCandidate,
  interpretIntent,
  solvePlan,
  type AiPreviewScenario,
} from '../api/aiPlanning'
import type {
  AiAdoptResponse,
  AiAdoptStatus,
  AiInterpretResponse,
  AiParsedIntent,
  AiPlanDiff,
  AiSolveResponse,
  AiSolveStatus,
} from '../api/aiPlanningTypes'
import type { PlanResult } from '../types/contracts'

/** 交互阶段；UI 只按它渲染，避免用多个布尔量拼状态。 */
export type AiPhase =
  | 'idle'
  | 'interpreting'
  | 'draft'
  | 'solving'
  | 'candidate'
  | 'unsolved'
  | 'adopting'
  | 'adopted'
  | 'not_configured'

/** 一次 AI 调整会话的上下文（由界面提供，⛔ 不含个人身份信息）。 */
export interface AiPlanningContext {
  /** 当前被调整方案的指纹（真实模式下由后端返回；Mock 模式下用显式前缀）。 */
  planDigest: string
  semester: string
  currentScheduleCount: number
  /** 抽屉聚焦某门课时携带；缺省为全案调整。 */
  focusCourseId: string | null
}

function cloneIntent(intent: AiParsedIntent): AiParsedIntent {
  return {
    hard_constraints: intent.hard_constraints.map((item) => ({ ...item })),
    soft_preferences: intent.soft_preferences.map((item) => ({ ...item })),
    credit_limit: intent.credit_limit,
    locked_course_ids: [...intent.locked_course_ids],
    scope: { ...intent.scope },
    unknowns: intent.unknowns.map((item) => ({ ...item })),
  }
}

export function useAiPlanning() {
  const phase = ref<AiPhase>('idle')
  const utterance = ref('')
  const errorMessage = ref('')
  const errorKind = ref<string | null>(null)
  const errorCode = ref<string | null>(null)

  /** 后端是否已实现该能力（默认未知；一次真实调用后才有结论）。 */
  const capabilityKnown = ref(false)
  const notConfigured = ref(false)

  /** 预览模式标记（`preview_fixture` = 仅前端预览）。 */
  const dataSourceBadge = ref<'backend' | 'preview_fixture'>('backend')
  const previewNotice = ref<string | null>(null)

  /** 后端给出的生成方式（⛔ 规则模板不得显示成 AI 生成）。 */
  const generatorKind = ref<string | null>(null)

  const interpretation = ref<AiInterpretResponse | null>(null)
  const draft = ref<AiParsedIntent | null>(null)
  const draftDirty = ref(false)

  const solveResult = ref<AiSolveResponse | null>(null)
  const candidatePlan = ref<PlanResult | null>(null)
  const candidateDiff = ref<AiPlanDiff | null>(null)

  const adoptResult = ref<AiAdoptResponse | null>(null)
  /** 只有后端确认 `adopted` 且 `accept=true` 时才有值。 */
  const adoptedPlan = ref<PlanResult | null>(null)
  const adoptedVersion = ref<string | null>(null)
  /** 已确认保留原方案（第二次确认的另一种结果）。 */
  const keptOriginal = ref(false)

  const busy = computed(
    () => phase.value === 'interpreting' || phase.value === 'solving' || phase.value === 'adopting',
  )

  /** 第一次确认是否可用：`can_confirm` 为真且草稿存在。 */
  const canConfirmIntent = computed(
    () => phase.value === 'draft' && interpretation.value?.can_confirm === true && draft.value !== null,
  )

  /** 第二次确认是否可用：候选存在且标识完整。 */
  const canDecideCandidate = computed(
    () =>
      phase.value === 'candidate' &&
      solveResult.value?.candidate_id != null &&
      solveResult.value?.candidate_digest != null,
  )

  const solveStatusLabel = computed(() => {
    const status = solveResult.value?.status
    return status === undefined ? null : SOLVE_STATUS_TEXT[status]
  })

  function resetOutputs(): void {
    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    interpretation.value = null
    draft.value = null
    draftDirty.value = false
    solveResult.value = null
    candidatePlan.value = null
    candidateDiff.value = null
    adoptResult.value = null
    keptOriginal.value = false
  }

  function handleError(error: unknown): void {
    if (error instanceof AiPlanningApiError) {
      errorKind.value = error.kind
      errorCode.value = error.code
      errorMessage.value = error.message
      if (error.kind === 'not_configured') {
        notConfigured.value = true
        capabilityKnown.value = true
        phase.value = 'not_configured'
      } else if (error.kind === 'disabled') {
        capabilityKnown.value = true
        phase.value = 'not_configured'
      } else {
        // 失败后回到可重试的阶段：绝不保留半截结果。
        phase.value = draft.value === null ? 'idle' : 'draft'
      }
      return
    }
    errorKind.value = 'unexpected'
    errorCode.value = null
    errorMessage.value = '发生了未知错误，请查看浏览器控制台。'
    phase.value = draft.value === null ? 'idle' : 'draft'
  }

  /** 解析自然语言 → 待确认意图草稿。 */
  async function parseUtterance(context: AiPlanningContext): Promise<void> {
    const text = utterance.value.trim()
    if (text === '') {
      errorKind.value = 'input'
      errorMessage.value = '请先输入一句你想怎么调整补修方案。'
      return
    }

    resetOutputs()
    phase.value = 'interpreting'

    try {
      const envelope = await interpretIntent({
        utterance: text,
        plan_digest: context.planDigest,
        target_semester: context.semester,
        focus_course_id: context.focusCourseId,
        current_schedule_count: context.currentScheduleCount,
      })
      interpretation.value = envelope.data
      draft.value = cloneIntent(envelope.data.parsed_intent)
      draftDirty.value = false
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice
      generatorKind.value = envelope.data.generator_kind
      capabilityKnown.value = true
      notConfigured.value = false
      phase.value = 'draft'
    } catch (error) {
      handleError(error)
    }
  }

  /** 第一次确认：确认前**不允许**求解。 */
  function confirmIntent(): boolean {
    if (!canConfirmIntent.value) {
      errorKind.value = 'blocked'
      errorMessage.value = interpretation.value?.can_confirm === false
        ? '当前解析结果不足以求解（后端标记为待补充），请先补充说明后重新解析。'
        : '请先解析意图，再确认。'
      return false
    }
    return true
  }

  /** 用户编辑草稿（学分上限 / 锁定课程 / 约束文本）。 */
  function updateDraft(patch: Partial<AiParsedIntent>): void {
    if (draft.value === null) {
      return
    }
    draft.value = { ...cloneIntent(draft.value), ...patch }
    draftDirty.value = true
  }

  function setCreditLimit(value: number | null): void {
    updateDraft({ credit_limit: value })
  }

  function toggleLockedCourse(courseId: string): void {
    if (draft.value === null) {
      return
    }
    const has = draft.value.locked_course_ids.includes(courseId)
    const next = has
      ? draft.value.locked_course_ids.filter((item) => item !== courseId)
      : [...draft.value.locked_course_ids, courseId]
    updateDraft({ locked_course_ids: next })
  }

  /** 求解：必须先经过第一次确认。 */
  async function solve(context: AiPlanningContext): Promise<void> {
    if (!confirmIntent()) {
      return
    }

    const interpretationSnapshot = interpretation.value
    const draftSnapshot = draft.value
    if (interpretationSnapshot === null || draftSnapshot === null) {
      return
    }

    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    solveResult.value = null
    candidatePlan.value = null
    candidateDiff.value = null
    adoptResult.value = null
    keptOriginal.value = false
    phase.value = 'solving'

    try {
      const envelope = await solvePlan({
        intent_id: interpretationSnapshot.intent_id,
        plan_digest: interpretationSnapshot.plan_digest,
        confirmed_intent: cloneIntent(draftSnapshot),
        semester: context.semester,
      })
      solveResult.value = envelope.data
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice

      if (envelope.data.status === 'candidate' && envelope.data.candidate_plan !== null) {
        candidatePlan.value = envelope.data.candidate_plan as PlanResult
        candidateDiff.value = envelope.data.diff
        phase.value = 'candidate'
      } else {
        // ⛔ 未生成候选：原方案保持不变，按状态分别说明。
        phase.value = 'unsolved'
      }
    } catch (error) {
      handleError(error)
    }
  }

  function handleAdoptResponse(response: AiAdoptResponse, accept: boolean): void {
    adoptResult.value = response

    if (accept && response.status === 'adopted' && response.adopted_plan !== null) {
      adoptedPlan.value = response.adopted_plan as PlanResult
      adoptedVersion.value = response.result_version
      keptOriginal.value = false
      phase.value = 'adopted'
      return
    }

    if (!accept) {
      // 明确保留原方案：不是失败，也不改变当前方案。
      keptOriginal.value = true
      adoptedPlan.value = null
      adoptedVersion.value = null
      phase.value = 'adopted'
      return
    }

    // 拒绝 / 过期 / 不可用 ⇒ 原案不变，回到候选阶段允许重试。
    adoptedPlan.value = null
    adoptedVersion.value = null
    phase.value = 'candidate'
  }

  /** 第二次确认：采用候选。 */
  async function adopt(context: AiPlanningContext): Promise<void> {
    const snapshot = solveResult.value
    if (snapshot?.candidate_id == null || snapshot.candidate_digest == null) {
      errorKind.value = 'blocked'
      errorMessage.value = '当前没有可采用的候选方案。'
      return
    }

    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    phase.value = 'adopting'

    try {
      const envelope = await adoptCandidate({
        candidate_id: snapshot.candidate_id,
        plan_digest: context.planDigest,
        candidate_digest: snapshot.candidate_digest,
        accept: true,
      })
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice
      handleAdoptResponse(envelope.data, true)
      if (envelope.data.status !== 'adopted') {
        errorKind.value = envelope.data.status
        errorMessage.value = envelope.data.message
      }
    } catch (error) {
      handleError(error)
    }
  }

  /** 第二次确认的另一种结果：明确保留原方案。 */
  async function keepOriginal(context: AiPlanningContext): Promise<void> {
    const snapshot = solveResult.value
    if (snapshot?.candidate_id == null) {
      keptOriginal.value = true
      phase.value = 'adopted'
      return
    }

    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    phase.value = 'adopting'

    try {
      const envelope = await adoptCandidate({
        candidate_id: snapshot.candidate_id,
        plan_digest: context.planDigest,
        candidate_digest: snapshot.candidate_digest ?? '',
        accept: false,
      })
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice
      handleAdoptResponse(envelope.data, false)
    } catch (error) {
      handleError(error)
    }
  }

  /** 开始一次新的调整（清空旧结果，但**不动**当前方案）。 */
  function reset(): void {
    resetOutputs()
    generatorKind.value = null
    phase.value = notConfigured.value ? 'not_configured' : 'idle'
  }

  /** 供测试 / 演示设置预览场景（只影响 fixture 模式）。 */
  function notePreviewScenario(_scenario: AiPreviewScenario): void {
    // 场景由 `setAiPreviewScenario()` 设置；此处只保留调用点，便于界面扩展。
  }
  return reactive({
    phase,
    utterance,
    errorMessage,
    errorKind,
    errorCode,
    capabilityKnown,
    notConfigured,
    dataSourceBadge,
    previewNotice,
    generatorKind,
    interpretation,
    draft,
    draftDirty,
    solveResult,
    candidatePlan,
    candidateDiff,
    adoptResult,
    adoptedPlan,
    adoptedVersion,
    keptOriginal,
    busy,
    canConfirmIntent,
    canDecideCandidate,
    solveStatusLabel,
    parseUtterance,
    confirmIntent,
    updateDraft,
    setCreditLimit,
    toggleLockedCourse,
    solve,
    adopt,
    keepOriginal,
    reset,
    notePreviewScenario,
  })
}

/** 求解状态 → 界面文案（⛔ 不同状态必须说不同的话）。 */
export const SOLVE_STATUS_TEXT: Record<AiSolveStatus, string> = {
  candidate: '已生成候选方案',
  infeasible: '未生成候选：当前约束下无解',
  unavailable: '未生成候选：缺少必要条件',
  rejected: '未生成候选：输入被拒绝',
}

/** 采用状态 → 界面文案。 */
export const ADOPT_STATUS_TEXT: Record<AiAdoptStatus, string> = {
  adopted: '已采用候选方案',
  rejected: '后端拒绝采用，原方案保持不变',
  stale_candidate: '候选已过期，原方案保持不变，可重新求解',
  unavailable: '后端不可用，原方案保持不变',
}
