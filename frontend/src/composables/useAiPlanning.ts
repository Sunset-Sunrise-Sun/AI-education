/**
 * AI 调整交互状态机（UI 层唯一的状态真源）。
 *
 * 契约来源：后端 `AI_PLANNING_API_HANDOFF.md`（`feature/deepseek-planning-controller`）。
 *
 * ```text
 * checking ──(GET /status)──> idle / unavailable
 *    │
 *    ├─ interpret ─> draft（待确认意图，can_confirm=false ⇒ 禁止求解）
 *    │                 │ 第一次确认（用户编辑 + 明确确认）
 *    │                 v
 *    │              solving ──> candidate_ready ⇒ review（候选对比）
 *    │                 │              │ 第二次确认
 *    │                 │              ├─ adopt(accept=true)  → applied（进程内会话版本）
 *    │                 │              └─ adopt(accept=false) → kept（原方案不变）
 *    │                 └─> unsolved（no_feasible_candidate / blocked；原方案不变）
 *    │
 *    └─ 任何失败 ⇒ 原方案一个字都不改
 * ```
 *
 * 四条硬边界（PR #65 Review）：
 * 1. **只有 `status = candidate_ready` 才是有效候选**；
 * 2. **`/adopt` 不返回方案体**：采用时使用内存中 `/solve` 已返回的候选，
 *    ⛔ 不伪造 `adopted_plan`、⛔ 不用原方案冒充候选；
 * 3. **"已采用"仅代表进程内会话状态**（`process_local_session`），
 *    不是持久保存、更不是教务系统选课成功；
 * 4. **两次确认都保留**：执行前确认意图、采用前确认方案。
 */

import { computed, reactive, ref } from 'vue'
import {
  AiPlanningApiError,
  adoptCandidate,
  fetchAiPlanningStatus,
  interpretIntent,
  solvePlan,
  type AiPlanningErrorKind,
  type AiPreviewScenario,
} from '../api/aiPlanning'
import {
  ADJUSTMENT_SCOPE_CURRENT_SEMESTER,
  parseConfirmedIntent,
  type AiAdoptResponse,
  type AiAmbiguity,
  type AiConfirmedIntent,
  type AiDataSource,
  type AiGeneratorKind,
  type AiInterpretResponse,
  type AiLockedCourse,
  type AiParsedIntentDraft,
  type AiPlanContext,
  type AiPlanningStatusResponse,
  type AiSolveResponse,
  type AiSolveStatus,
} from '../api/aiPlanningContract'
import type { CourseOffering, MakeupTask, PlanResult, Preference } from '../types/contracts'

/** 交互阶段。 */
export type AiPhase =
  | 'idle'
  | 'checking'
  | 'unavailable'
  | 'interpreting'
  | 'draft'
  | 'solving'
  | 'review'
  | 'unsolved'
  | 'adopting'
  | 'applied'
  | 'kept'

/** 一次 AI 调整会话的输入上下文（全部来自页面已有对象）。 */
export interface AiPlanningContextInput {
  semester: string
  basePlan: PlanResult | null
  makeupTasks: MakeupTask[]
  courseOfferings: CourseOffering[]
  preference: Preference | null
  /** 抽屉聚焦某门课时携带（当前后端不消费该字段，仅用于界面提示）。 */
  focusCourseId: string | null
}

/** 后端"不可用"的具体原因（三种未启用态文案不同）。 */
export type AiUnavailableReason = 'route_absent' | 'disabled' | 'no_api_key'

const MAX_MESSAGE_CHARS = 1000

/** 与后端 `sanitize_user_message` 同构的个人信息模式（本地前置提醒）。 */
const PII_PATTERNS: { code: string; pattern: RegExp }[] = [
  { code: 'email', pattern: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/ },
  { code: 'cn_mobile', pattern: /(?<!\d)1[3-9]\d{9}(?!\d)/ },
  { code: 'id_card', pattern: /(?<!\d)\d{17}[\dXx](?!\d)/ },
  { code: 'student_no', pattern: /(?<!\d)(?:20\d{2})?\d{6,}(?!\d)/ },
  { code: 'credential', pattern: /(?:cookie|token|session|密码|password|passwd)\s*[:：=]/i },
  { code: 'api_key', pattern: /sk-[A-Za-z0-9]{8,}/ },
]

/**
 * 本地检查用户消息（⛔ 不作为唯一防线：服务器仍会校验）。
 *
 * 返回 `null` 表示本地没发现问题。
 */
export function checkUserMessage(message: string): string | null {
  const text = message.trim()
  if (text === '') {
    return '请先输入一句你想怎么调整补修方案。'
  }
  if (text.length > MAX_MESSAGE_CHARS) {
    return `这句话太长（上限 ${MAX_MESSAGE_CHARS} 字），请精简后再试。`
  }
  for (const { code, pattern } of PII_PATTERNS) {
    if (pattern.test(text)) {
      return (
        '这句话里疑似包含个人信息（' +
        code +
        '）。请改为只描述选课需求，不要填写姓名、学号、联系方式或任何凭据。'
      )
    }
  }
  return null
}

export function useAiPlanning() {
  const phase = ref<AiPhase>('idle')
  const userMessage = ref('')
  const errorMessage = ref('')
  const errorKind = ref<AiPlanningErrorKind | null>(null)
  const errorCode = ref<string | null>(null)

  /** 能力状态（来自 `GET /status`，或预览 fixture）。 */
  const status = ref<AiPlanningStatusResponse | null>(null)
  const unavailableReason = ref<AiUnavailableReason | null>(null)
  const statusChecked = ref(false)

  /** 数据来源标记：`preview_fixture` 表示"仅前端预览"。 */
  const dataSourceBadge = ref<'backend' | 'preview_fixture'>('backend')
  const previewNotice = ref<string | null>(null)

  const interpretation = ref<AiInterpretResponse | null>(null)
  /** 后端返回的意图草稿（只读原文，便于"事实对照"）。 */
  const draft = ref<AiParsedIntentDraft | null>(null)
  /** 后端计算、前端**只保存只回传**的方案指纹。 */
  const planDigest = ref<string | null>(null)
  const intentId = ref<string | null>(null)

  /** 本地编辑量（第一次确认面板）。 */
  const editedCreditLimit = ref<number | null>(null)
  const editedAvoidWeekdays = ref<number[]>([])
  const editedLockedCourses = ref<AiLockedCourse[]>([])
  const confirmedIntentSent = ref(false)

  const solveResult = ref<AiSolveResponse | null>(null)
  /** `/solve` 返回、**由后端产生**的候选方案（采用时唯一允许使用的方案体）。 */
  const candidatePlan = ref<PlanResult | null>(null)

  const adoptResult = ref<AiAdoptResponse | null>(null)
  /** 只有 `accepted === true && state === 'adopted'` 时才有值。 */
  const appliedPlan = ref<PlanResult | null>(null)
  const appliedVersion = ref<number | null>(null)
  const appliedScope = ref<string | null>(null)

  const busy = computed(
    () => phase.value === 'interpreting' || phase.value === 'solving' || phase.value === 'adopting',
  )

  const generatorKind = computed<AiGeneratorKind | null>(
    () => interpretation.value?.generator_kind ?? solveResult.value?.generator_kind ?? null,
  )
  const generatorNote = computed(() => interpretation.value?.generator_note ?? null)
  const modelId = computed(() => interpretation.value?.model_id ?? null)
  const dataSource = computed<AiDataSource | null>(
    () => interpretation.value?.data_source ?? solveResult.value?.data_source ?? null,
  )

  const ambiguities = computed<AiAmbiguity[]>(() => interpretation.value?.ambiguities ?? [])

  /** 第一次确认是否可用（后端说 `can_confirm=false` ⇒ 禁止求解）。 */
  const canConfirmIntent = computed(
    () => interpretation.value?.can_confirm === true && draft.value !== null,
  )

  /** 第二次确认是否可用：必须是 `candidate_ready` 且候选体存在。 */
  const canDecideCandidate = computed(
    () =>
      phase.value === 'review' &&
      solveResult.value?.status === 'candidate_ready' &&
      candidatePlan.value !== null,
  )

  const solveStatusLabel = computed(() => {
    const solveStatus = solveResult.value?.status
    return solveStatus === undefined ? null : SOLVE_STATUS_TEXT[solveStatus]
  })

  function resetLocalEdits(): void {
    editedCreditLimit.value = null
    editedAvoidWeekdays.value = []
    editedLockedCourses.value = []
    confirmedIntentSent.value = false
  }

  function clearDownstream(): void {
    solveResult.value = null
    candidatePlan.value = null
    adoptResult.value = null
    appliedPlan.value = null
    appliedVersion.value = null
    appliedScope.value = null
  }

  function handleError(error: unknown): void {
    if (error instanceof AiPlanningApiError) {
      errorKind.value = error.kind
      errorCode.value = error.code
      errorMessage.value = error.message
      if (error.kind === 'absent') {
        unavailableReason.value = 'route_absent'
        phase.value = 'unavailable'
        return
      }
      if (error.kind === 'disabled') {
        unavailableReason.value = 'disabled'
        phase.value = 'unavailable'
        return
      }
      if (error.kind === 'model_unavailable' && status.value?.api_key_configured === false) {
        unavailableReason.value = 'no_api_key'
      }
      // 其它失败：回到可重试阶段；⛔ 不保留半截结果。
      if (candidatePlan.value !== null && solveResult.value?.status === 'candidate_ready') {
        phase.value = 'review'
      } else if (draft.value !== null) {
        phase.value = 'draft'
      } else {
        phase.value = statusChecked.value && status.value?.enabled ? 'idle' : 'unavailable'
      }
      return
    }
    errorKind.value = 'unexpected'
    errorCode.value = null
    errorMessage.value = '发生了未知错误，请查看浏览器控制台。'
    phase.value = draft.value === null ? 'idle' : 'draft'
  }

  /** 初始化：读取后端可用状态（预览模式直接读 fixture）。 */
  async function loadStatus(): Promise<void> {
    phase.value = 'checking'
    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null

    try {
      const envelope = await fetchAiPlanningStatus()
      status.value = envelope.data
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice
      statusChecked.value = true
      if (!envelope.data.enabled) {
        unavailableReason.value = 'disabled'
        phase.value = 'unavailable'
        return
      }
      unavailableReason.value = null
      phase.value = 'idle'
    } catch (error) {
      if (error instanceof AiPlanningApiError) {
        errorKind.value = error.kind
        errorCode.value = error.code
        errorMessage.value = error.message
        if (error.kind === 'absent') {
          unavailableReason.value = 'route_absent'
          phase.value = 'unavailable'
          statusChecked.value = true
          return
        }
        if (error.kind === 'disabled') {
          unavailableReason.value = 'disabled'
          phase.value = 'unavailable'
          statusChecked.value = true
          return
        }
      }
      handleError(error)
    }
  }

  /** 从页面已有对象构造后端要求的 `context`。 */
  function buildPlanContext(input: AiPlanningContextInput): AiPlanContext | null {
    if (input.basePlan === null) {
      return null
    }
    return {
      semester: input.semester,
      base_plan: input.basePlan,
      makeup_tasks: input.makeupTasks,
      course_offerings: input.courseOfferings,
      preference:
        input.preference ?? {
          max_credit: null,
          avoid_cross_campus: false,
          preferred_courses: [],
          avoid_times: [],
          notes: null,
        },
    }
  }

  /**
   * 解析自然语言 → 待确认意图草稿。
   *
   * ⚠️ 请求体只有 `context` + `user_message`（⛔ 不带 `plan_digest`）。
   */
  async function parseMessage(input: AiPlanningContextInput): Promise<void> {
    const localError = checkUserMessage(userMessage.value)
    if (localError !== null) {
      errorKind.value = 'message_rejected'
      errorCode.value = null
      errorMessage.value = localError
      return
    }

    const context = buildPlanContext(input)
    if (context === null) {
      errorKind.value = 'plan_context_invalid'
      errorMessage.value = '当前还没有可调整的方案，无法解析意图。'
      return
    }

    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    interpretation.value = null
    draft.value = null
    planDigest.value = null
    intentId.value = null
    resetLocalEdits()
    clearDownstream()
    phase.value = 'interpreting'

    try {
      const envelope = await interpretIntent({
        context,
        user_message: userMessage.value.trim(),
      })
      const data = envelope.data
      interpretation.value = data
      draft.value = data.parsed_intent
      // ⚠️ 指纹与 intent_id 全部来自后端，前端只保存。
      planDigest.value = data.plan_digest
      intentId.value = data.intent_id
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice
      editedCreditLimit.value = null
      editedAvoidWeekdays.value = data.parsed_intent.soft_preferences
        .filter((item) => item.kind === 'avoid_weekday' && typeof item.value === 'number')
        .map((item) => item.value as number)
      editedLockedCourses.value = data.parsed_intent.locked_courses.map((item) => ({ ...item }))
      phase.value = 'draft'
    } catch (error) {
      handleError(error)
    }
  }

  /** 用户编辑：学分上限（必须由用户给出数字，⛔ 不从文本猜）。 */
  function setCreditLimit(value: number | null): void {
    editedCreditLimit.value = value
  }

  /** 用户编辑：避开星期（软偏好）。 */
  function toggleAvoidWeekday(weekday: number): void {
    const has = editedAvoidWeekdays.value.includes(weekday)
    editedAvoidWeekdays.value = has
      ? editedAvoidWeekdays.value.filter((item) => item !== weekday)
      : [...editedAvoidWeekdays.value, weekday].sort((a, b) => a - b)
  }

  /** 用户编辑：锁定 / 取消锁定课程的某个教学班。 */
  function toggleLockedCourse(course: AiLockedCourse): void {
    const exists = editedLockedCourses.value.some(
      (item) => item.course_id === course.course_id && item.class_id === course.class_id,
    )
    editedLockedCourses.value = exists
      ? editedLockedCourses.value.filter(
          (item) => !(item.course_id === course.course_id && item.class_id === course.class_id),
        )
      : [...editedLockedCourses.value, { ...course }]
  }

  /** 构造回传后端的 `confirmed_intent`（结构与后端 `ConfirmedIntent` 一致）。 */
  function buildConfirmedIntent(semester: string): AiConfirmedIntent | null {
    const source = draft.value
    const digest = planDigest.value
    if (source === null || digest === null) {
      return null
    }

    // 软偏好：用本地编辑后的 avoid_weekday 替换，其余原样保留。
    const soft = source.soft_preferences
      .filter((item) => item.kind !== 'avoid_weekday')
      .map((item) => ({ ...item }))
    for (const weekday of editedAvoidWeekdays.value) {
      soft.push({ kind: 'avoid_weekday', value: weekday, note: '用户在确认面板选择' })
    }

    return parseConfirmedIntent(
      {
        ...source,
        soft_preferences: soft,
        locked_courses: editedLockedCourses.value,
      },
      { planDigest: digest, semester, creditLimit: editedCreditLimit.value },
    )
  }

  /** 第一次确认：确认前**不允许**求解。 */
  function confirmIntent(): boolean {
    if (!canConfirmIntent.value) {
      errorKind.value = 'intent_not_confirmable'
      errorMessage.value =
        interpretation.value?.can_confirm === false
          ? '后端标记这次解析仍有歧义（can_confirm=false），请先回答上面的问题并重新解析。'
          : '请先解析意图，再确认。'
      return false
    }
    return true
  }

  /** 求解：必须先经过第一次确认。 */
  async function solve(semester: string): Promise<void> {
    if (!confirmIntent()) {
      return
    }
    const confirmedIntent = buildConfirmedIntent(semester)
    if (confirmedIntent === null || intentId.value === null) {
      errorKind.value = 'intent_invalid'
      errorMessage.value = '意图草稿或方案指纹缺失，请重新解析。'
      return
    }

    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    clearDownstream()
    phase.value = 'solving'

    try {
      const envelope = await solvePlan({
        intent_id: intentId.value,
        plan_digest: confirmedIntent.plan_digest,
        confirmed_intent: confirmedIntent,
      })
      solveResult.value = envelope.data
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice
      confirmedIntentSent.value = true

      // ⚠️ **只有 candidate_ready 才是有效候选**。
      if (envelope.data.status === 'candidate_ready' && envelope.data.candidate_plan !== null) {
        candidatePlan.value = envelope.data.candidate_plan
        phase.value = 'review'
      } else {
        candidatePlan.value = null
        phase.value = 'unsolved'
      }
    } catch (error) {
      handleError(error)
    }
  }

  /** 第二次确认是否可用（供按钮 disabled 使用）。 */
  function canAdopt(): boolean {
    return canDecideCandidate.value && solveResult.value?.candidate_id != null
  }

  /**
   * 第二次确认：采用候选（`accept = true`）。
   *
   * ⚠️ `/adopt` **不返回方案体**：采用成功时使用 `candidatePlan`（来自 `/solve`）。
   */
  async function adopt(): Promise<void> {
    const snapshot = solveResult.value
    const digest = planDigest.value
    const plan = candidatePlan.value
    if (
      snapshot?.status !== 'candidate_ready' ||
      snapshot.candidate_id === null ||
      digest === null ||
      plan === null
    ) {
      errorKind.value = 'adoption_conflict'
      errorMessage.value = '当前没有可采用的候选（必须是后端返回的 candidate_ready）。'
      return
    }

    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    phase.value = 'adopting'

    try {
      const envelope = await adoptCandidate({
        candidate_id: snapshot.candidate_id,
        plan_digest: digest,
        accept: true,
      })
      adoptResult.value = envelope.data
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice

      if (envelope.data.accepted && envelope.data.state === 'adopted') {
        // 唯一的刷新路径：方案体来自 /solve 的候选，**不是** adopt 返回值。
        appliedPlan.value = plan
        appliedVersion.value = envelope.data.adopted_version
        appliedScope.value = envelope.data.adopted_version_scope
        phase.value = 'applied'
      } else {
        appliedPlan.value = null
        appliedVersion.value = null
        appliedScope.value = null
        errorKind.value = 'adoption_conflict'
        errorMessage.value = envelope.data.message
        phase.value = 'review'
      }
    } catch (error) {
      handleError(error)
    }
  }

  /** 第二次确认的另一种结果：明确保留原方案（`accept = false`）。 */
  async function keepOriginal(): Promise<void> {
    const snapshot = solveResult.value
    const digest = planDigest.value
    if (snapshot?.candidate_id == null || digest === null) {
      errorKind.value = 'adoption_conflict'
      errorMessage.value = '当前没有可处理的候选。'
      return
    }

    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    phase.value = 'adopting'

    try {
      const envelope = await adoptCandidate({
        candidate_id: snapshot.candidate_id,
        plan_digest: digest,
        accept: false,
      })
      adoptResult.value = envelope.data
      dataSourceBadge.value = envelope.source
      previewNotice.value = envelope.previewNotice
      appliedPlan.value = null
      appliedVersion.value = envelope.data.adopted_version
      appliedScope.value = envelope.data.adopted_version_scope
      phase.value = 'kept'
    } catch (error) {
      handleError(error)
    }
  }

  /** 回到意图草稿（重新求解 / 修改意图）。 */
  function backToDraft(): void {
    clearDownstream()
    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    phase.value = draft.value === null ? 'idle' : 'draft'
  }

  /** 彻底重置（清空本次会话；⛔ 不影响当前方案）。 */
  function reset(): void {
    interpretation.value = null
    draft.value = null
    planDigest.value = null
    intentId.value = null
    resetLocalEdits()
    clearDownstream()
    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    phase.value = statusChecked.value && status.value?.enabled === false ? 'unavailable' : 'idle'
  }

  function notePreviewScenario(_scenario: AiPreviewScenario): void {
    // 场景由 `setAiPreviewScenario()` 设置；此处保留调用点便于界面扩展。
  }

  return reactive({
    phase,
    userMessage,
    errorMessage,
    errorKind,
    errorCode,
    status,
    statusChecked,
    unavailableReason,
    dataSourceBadge,
    previewNotice,
    interpretation,
    draft,
    planDigest,
    intentId,
    editedCreditLimit,
    editedAvoidWeekdays,
    editedLockedCourses,
    confirmedIntentSent,
    solveResult,
    candidatePlan,
    adoptResult,
    appliedPlan,
    appliedVersion,
    appliedScope,
    busy,
    generatorKind,
    generatorNote,
    modelId,
    dataSource,
    ambiguities,
    canConfirmIntent,
    canDecideCandidate,
    solveStatusLabel,
    parseMessage,
    setCreditLimit,
    toggleAvoidWeekday,
    toggleLockedCourse,
    confirmIntent,
    solve,
    canAdopt,
    adopt,
    keepOriginal,
    backToDraft,
    loadStatus,
    reset,
    notePreviewScenario,
  })
}

/** 求解状态 → 界面文案（⛔ 三种状态说的话不同）。 */
export const SOLVE_STATUS_TEXT: Record<AiSolveStatus, string> = {
  candidate_ready: '已生成候选方案（后端 candidate_ready）',
  no_feasible_candidate: '未生成候选：当前约束下没有可行变化',
  blocked: '未生成候选：本次调整被拒绝',
}

/**
 * `generator_kind` → 界面文案。
 *
 * ⛔ 只有 `deepseek_live` 才允许说"真实 DeepSeek 在线调用"；
 * `test_double` 必须显示为"测试替身模型（不是线上模型）"。
 */
export function generatorKindLabel(kind: AiGeneratorKind | null): string {
  switch (kind) {
    case 'deepseek_live':
      return '真实 DeepSeek 在线调用'
    case 'test_double':
      return '测试替身模型（不是线上模型）'
    case 'unavailable':
      return '模型不可用（未生成）'
    default:
      return '未提供'
  }
}

/** `data_source` → 界面文案（⛔ `unknown` 不等于 `real`）。 */
export function dataSourceLabel(source: AiDataSource | null): string {
  switch (source) {
    case 'real':
      return '上下文全部为 real 教学班'
    case 'mock':
      return '上下文全部为 mock 教学班'
    case 'mixed':
      return 'real 与 mock 混合'
    case 'unknown':
      return '本次没有教学班输入（unknown，⛔ 不代表 real）'
    default:
      return '未提供'
  }
}

/** 不可用原因 → 界面文案（三种未启用态必须区分）。 */
export function unavailableReasonLabel(reason: AiUnavailableReason | null): string {
  switch (reason) {
    case 'route_absent':
      return 'AI 调整接口尚未部署到当前后端（该私有前缀返回 404/405）。页面不会伪造解析或候选方案。'
    case 'disabled':
      return 'AI 调整未启用（服务器未开启 AI_PLANNING_ENABLED）。'
    case 'no_api_key':
      return 'AI 调整已开启，但服务器未注入模型密钥，无法解析意图。'
    default:
      return 'AI 调整当前不可用。'
  }
}
