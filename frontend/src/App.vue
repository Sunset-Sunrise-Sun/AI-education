<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import E2EDebugPanel from './components/E2EDebugPanel.vue'
import type { E2EDebugInfo } from './components/E2EDebugPanel.vue'
import TopStatusBar from './components/TopStatusBar.vue'
import AiAdjustDrawer from './components/ai/AiAdjustDrawer.vue'
import AiAdjustView from './components/views/AiAdjustView.vue'
import MakeupPathView from './components/views/MakeupPathView.vue'
import TransferAnalysisView from './components/views/TransferAnalysisView.vue'
import { useDemoData } from './composables/useDemoData'
import { usePersonalPlanning } from './composables/usePersonalPlanning'
import {
  AI_PLANNING_API_ENABLED,
  AI_PLANNING_PREVIEW,
  EXPLANATION_API_ENABLED,
  PERSONAL_PLANNING_API_ENABLED,
  PLAN_API_ENABLED,
  PLAN_ENDPOINT,
  initialDataMode,
} from './config'
import {
  buildRealPlanRequest,
  createDefaultUserInputForm,
  describeScheduleProvenance,
  evaluatePlanSubmission,
  isPreferencePresent,
  scheduleProvenanceBlockReason,
} from './state/userInput'
import type { UserInputForm } from './state/userInput'
import { PlanApiError, fetchRealPlan } from './api/plan'
import type { MakeupTask, PlanResult } from './types/contracts'
import { computePlanDigest } from './utils/planDigest'

/**
 * 页面外壳：三个导航入口 + AI 调整抽屉。
 *
 * 信息架构（任务书）：
 * 1. `转专业分析`：原 / 目标培养版本、认定状态与缺口（真实 readiness，⛔ 不冒充）；
 * 2. `补修路径`：当前学期精确课表 + 后续学期课程级条件路径 + 风险 / 人工确认；
 * 3. `AI 调整`：围绕**当前选中补修方案**的对话式调整（两次确认）。
 *
 * 本轮把旧的"0–5 区块"整体搬进 `补修路径` 视图，保留原有 data-testid 与行为，
 * 因此旧 Case A 演示与既有测试继续可用。
 */
type ViewKey = 'transfer-analysis' | 'makeup-path' | 'ai-adjust'

const VIEWS: { key: ViewKey; label: string; hint: string }[] = [
  { key: 'transfer-analysis', label: '转专业分析', hint: '培养方案版本与缺口认定' },
  { key: 'makeup-path', label: '补修路径', hint: '当前学期课表与后续学期路径' },
  { key: 'ai-adjust', label: 'AI 调整', hint: '对话式调整当前方案（两次确认）' },
]

const activeView = ref<ViewKey>('makeup-path')

const { state, data, dataSource, errorMessage, load } = useDemoData()

const isDev = import.meta.env.DEV

/* ------------------------------------------------------------------ *
 * 用户输入（Frontend User Input Gate, Phase 1）
 * ------------------------------------------------------------------ */

const userInput = ref<UserInputForm>(createDefaultUserInputForm())
const dataMode = ref(initialDataMode())

/* ------------------------------------------------------------------ *
 * Real Planning（POST /api/v1/plan）与 Mock 演示结果
 * ------------------------------------------------------------------ */

const realPlanResult = ref<PlanResult | null>(null)
const planErrorMessage = ref('')
const planErrorKind = ref<string | null>(null)
const planErrorStatus = ref<number | null>(null)
const planErrorCode = ref<string | null>(null)
const planErrorDetail = ref<string | null>(null)
const planSubmitting = ref(false)
const lastHttpStatus = ref<number | null>(null)

/** 后端个人规划结果被"用作当前方案"时置位（用于 provenance）。 */
const personalPlanApplied = ref(false)
const personalPlanNotice = ref<string | null>(null)

/** AI 调整（第二次确认成功）采用的方案；只有后端确认才可能被赋值。 */
const aiAdoptedPlan = ref<PlanResult | null>(null)
const aiAdoptedDigest = ref<string | null>(null)

const planScheduleBlocked = computed(() => scheduleProvenanceBlockReason(userInput.value) !== null)

/**
 * 方案来源的**局部** provenance。
 *
 * - `real`：`POST /api/v1/plan` 成功返回；
 * - `ai_candidate`：AI 调整第二次确认被后端接受；
 * - `mock`：都还没有成功，展示的是 Mock 演示方案。
 */
const planResultMode = computed<'mock' | 'real' | 'ai_candidate'>(() => {
  if (aiAdoptedPlan.value !== null) {
    return 'ai_candidate'
  }
  if (realPlanResult.value !== null) {
    return 'real'
  }
  return 'mock'
})

/** 解释入口用的二分模式（解释面板目前只区分 Mock / Real）。 */
const explanationPlanMode = computed<'mock' | 'real'>(() =>
  planResultMode.value === 'mock' ? 'mock' : 'real',
)

const displayedPlanResult = computed<PlanResult | null>(
  () =>
    aiAdoptedPlan.value ??
    realPlanResult.value ??
    data.value?.plan_result ??
    null,
)

const planResultLabel = computed(() => {
  switch (planResultMode.value) {
    case 'ai_candidate':
      return 'AI 候选方案（后端确认采用）'
    case 'real':
      return 'Real Planning 结果'
    default:
      return 'Mock 演示方案'
  }
})

const courseNameById = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const task of data.value?.makeup_tasks ?? []) {
    map[task.course_id] = task.course_name
  }
  for (const offering of data.value?.course_offerings ?? []) {
    if (!map[offering.course_id]) {
      map[offering.course_id] = offering.course_name
    }
  }
  return map
})

const planResultCourseNameById = computed<Record<string, string>>(() =>
  planResultMode.value === 'mock' ? courseNameById.value : {},
)

/* ------------------------------------------------------------------ *
 * 解释（只读）
 * ------------------------------------------------------------------ */

const explanationOpen = ref(false)
const explanationFocusCourseId = ref<string | null>(null)
const explanationRequestSeq = ref(0)

function openExplanation(courseId: string | null): void {
  explanationFocusCourseId.value = courseId
  explanationOpen.value = true
  explanationRequestSeq.value += 1
}

function closeExplanation(): void {
  explanationOpen.value = false
}

/* ------------------------------------------------------------------ *
 * 方案指纹（AI 调整的 plan_digest）
 * ------------------------------------------------------------------ */

const planDigest = ref<string>('sha256:未计算')
const digestError = ref<string | null>(null)

async function refreshPlanDigest(): Promise<void> {
  if (aiAdoptedDigest.value !== null) {
    planDigest.value = aiAdoptedDigest.value
    return
  }
  const plan = displayedPlanResult.value
  if (plan === null) {
    planDigest.value = 'sha256:无方案'
    return
  }
  try {
    planDigest.value = await computePlanDigest(plan)
    digestError.value = null
  } catch {
    planDigest.value = 'sha256:计算失败'
    digestError.value = '无法计算方案指纹；AI 调整会把它当作"原方案可能已变化"处理。'
  }
}

watch(displayedPlanResult, () => {
  void refreshPlanDigest()
})

/* ------------------------------------------------------------------ *
 * AI 调整抽屉
 * ------------------------------------------------------------------ */

const aiDrawerOpen = ref(false)
const aiFocusCourseId = ref<string | null>(null)

function openAiDrawer(focusCourseId: string | null): void {
  aiFocusCourseId.value = focusCourseId
  aiDrawerOpen.value = true
}

function closeAiDrawer(): void {
  aiDrawerOpen.value = false
}

/**
 * 第二次确认成功后的**唯一**刷新入口。
 *
 * ⛔ 只有抽屉在收到后端 `adopted` 时才调用它；失败 / 拒绝 / 过期都不会走到这里。
 */
function onAiAdopted(plan: PlanResult): void {
  aiAdoptedPlan.value = plan
  aiAdoptedDigest.value = null
  personalPlanApplied.value = false
  personalPlanNotice.value = '当前方案已由 AI 调整的后端确认结果刷新。'
  void refreshPlanDigest()
}

/* ------------------------------------------------------------------ *
 * Real Planning 提交
 * ------------------------------------------------------------------ */

async function submitRealPlan(): Promise<void> {
  if (planSubmitting.value) {
    return
  }

  const gate = evaluatePlanSubmission(userInput.value)
  if (!gate.allowed) {
    planErrorMessage.value = gate.reason
    planErrorKind.value = 'blocked'
    planErrorStatus.value = null
    planErrorCode.value = null
    planErrorDetail.value = null
    return
  }

  planSubmitting.value = true
  planErrorMessage.value = ''
  planErrorKind.value = null
  planErrorStatus.value = null
  planErrorCode.value = null
  planErrorDetail.value = null

  try {
    realPlanResult.value = await fetchRealPlan(buildRealPlanRequest(userInput.value))
    aiAdoptedPlan.value = null
    dataMode.value = 'real'
    lastHttpStatus.value = 200
    void refreshPlanDigest()
  } catch (error) {
    realPlanResult.value = null
    dataMode.value = 'mock'

    if (error instanceof PlanApiError) {
      planErrorKind.value = error.kind
      planErrorStatus.value = error.status
      planErrorCode.value = error.code
      planErrorDetail.value = error.detail
      planErrorMessage.value = error.message
      lastHttpStatus.value = error.status
    } else {
      planErrorKind.value = 'unexpected'
      planErrorStatus.value = null
      planErrorCode.value = null
      planErrorDetail.value = null
      planErrorMessage.value =
        error instanceof Error ? error.message : '发生了未知错误，请查看浏览器控制台。'
      lastHttpStatus.value = null
    }
  } finally {
    planSubmitting.value = false
  }
}

/* ------------------------------------------------------------------ *
 * 个人规划（转专业分析）
 * ------------------------------------------------------------------ */

const personal = usePersonalPlanning({
  enabled: PERSONAL_PLANNING_API_ENABLED,
  preview: !PERSONAL_PLANNING_API_ENABLED && import.meta.env.VITE_PERSONAL_PLANNING_PREVIEW === 'true',
})

const personalMakeupTasks = ref<MakeupTask[] | null>(null)

function onPersonalSubmit(payload: { oldVersionId: string; targetVersionId: string }): void {
  void personal.submit({
    old_version_id: payload.oldVersionId,
    target_version_id: payload.targetVersionId,
    semester: userInput.value.semester,
    student: {
      completed: { records: [] },
      preference: {
        max_credit: null,
        avoid_cross_campus: false,
        preferred_courses: [],
        avoid_times: [],
      },
    },
    current_schedule: userInput.value.currentSchedule,
  })
}

/**
 * 把后端个人规划结果"用作当前方案"。
 *
 * ⚠️ 只有当后端真的给出 `planning`（排课结果）时才允许覆盖当前方案的规划结果；
 * `planning = null` 时**只**接管补修任务上下文，并明确提示"没有排课结果"。
 */
function onPersonalUseResults(makeupTasks: MakeupTask[], planning: PlanResult | null): void {
  personalMakeupTasks.value = makeupTasks
  if (planning === null) {
    personalPlanApplied.value = false
    personalPlanNotice.value =
      '后端个人规划结果没有排课内容（planning = null）：补修任务已载入，但当前展示的规划结果仍来自其它来源，不代表个人排课已完成。'
  } else {
    realPlanResult.value = planning
    aiAdoptedPlan.value = null
    personalPlanApplied.value = true
    personalPlanNotice.value = '当前规划结果已切换为后端个人规划结果（Real）。'
    void refreshPlanDigest()
  }
  activeView.value = 'makeup-path'
}

/* ------------------------------------------------------------------ *
 * 联调调试信息（仅开发环境）
 * ------------------------------------------------------------------ */

const e2eDebugInfo = computed<E2EDebugInfo>(() => ({
  planEndpoint: PLAN_ENDPOINT,
  semester: userInput.value.semester,
  scheduleCount: userInput.value.currentSchedule.length,
  scheduleProvenance: describeScheduleProvenance(userInput.value),
  preferencePresent: isPreferencePresent(userInput.value),
  planApiEnabled: PLAN_API_ENABLED,
  lastHttpStatus: lastHttpStatus.value,
  lastErrorKind: planErrorKind.value,
  planResultSource: planResultMode.value,
}))

/** 供 `转专业分析` 使用的课表计数（只传计数，不传明细）。 */
const currentScheduleCount = computed(() => userInput.value.currentSchedule.length)

onMounted(() => {
  void load()
  void refreshPlanDigest()
  void personal.loadCatalog()
})
</script>

<template>
  <div class="page page--ai-planning">
    <TopStatusBar :data-source="dataSource" />

    <nav class="app-nav" aria-label="主导航" data-testid="app-nav">
      <button
        v-for="view in VIEWS"
        :key="view.key"
        type="button"
        class="app-nav__tab"
        :class="{ 'app-nav__tab--active': activeView === view.key }"
        :data-testid="`nav-${view.key}`"
        :aria-current="activeView === view.key ? 'page' : undefined"
        @click="activeView = view.key"
      >
        <strong>{{ view.label }}</strong>
        <span class="app-nav__hint">{{ view.hint }}</span>
      </button>

      <button
        type="button"
        class="app-nav__ai-button"
        data-testid="nav-open-ai-drawer"
        :disabled="displayedPlanResult === null"
        @click="openAiDrawer(null)"
      >
        💬 AI 调整
      </button>
    </nav>

    <main class="page__main">
      <TransferAnalysisView
        v-if="activeView === 'transfer-analysis'"
        :phase="personal.phase.value"
        :selectable-versions="personal.selectableVersions.value"
        :rejected-versions="personal.rejectedVersions.value"
        :catalog-reason="personal.catalog.value?.catalog_reason ?? ''"
        :result="personal.result.value"
        :error-message="personal.errorMessage.value"
        :error-kind="personal.errorKind.value"
        :error-code="personal.errorCode.value"
        :preview-notice="personal.previewNotice.value"
        :api-enabled="PERSONAL_PLANNING_API_ENABLED"
        :current-semester="userInput.semester"
        :current-schedule-count="currentScheduleCount"
        @submit="onPersonalSubmit"
        @reload="personal.loadCatalog"
        @use-results="onPersonalUseResults"
      />

      <MakeupPathView
        v-else-if="activeView === 'makeup-path'"
        :state="state"
        :data="data"
        :data-source="dataSource"
        :demo-error-message="errorMessage"
        :user-input="userInput"
        :data-mode="dataMode"
        :plan-api-enabled="PLAN_API_ENABLED"
        :plan-submitting="planSubmitting"
        :plan-error-message="planErrorMessage"
        :plan-error-kind="planErrorKind"
        :plan-error-status="planErrorStatus"
        :plan-error-code="planErrorCode"
        :plan-error-detail="planErrorDetail"
        :debug-info="e2eDebugInfo"
        :dev="isDev"
        :schedule-block-reason="scheduleProvenanceBlockReason(userInput)"
        :explanation-api-enabled="EXPLANATION_API_ENABLED"
        :explanation-open="explanationOpen"
        :explanation-focus-course-id="explanationFocusCourseId"
        :explanation-request-seq="explanationRequestSeq"
        :displayed-plan-result="displayedPlanResult"
        :plan-result-mode="explanationPlanMode"
        :plan-result-course-name-by-id="planResultCourseNameById"
        :course-name-by-id="courseNameById"
        :personal-plan-applied="personalPlanApplied"
        :personal-plan-notice="personalPlanNotice"
        @update:form="userInput = $event"
        @submit-real-plan="submitRealPlan"
        @reload-demo="load"
        @open-explanation="openExplanation"
        @close-explanation="closeExplanation"
        @open-ai-drawer="openAiDrawer"
      />

      <AiAdjustView
        v-else
        :current-plan="displayedPlanResult"
        :current-plan-label="planResultLabel"
        :plan-digest="planDigest"
        :makeup-tasks="data?.makeup_tasks ?? []"
        :ready="displayedPlanResult !== null"
        :not-ready-reason="
          state === 'loading'
            ? '演示数据仍在加载中。'
            : state === 'error'
              ? '演示数据加载失败，因此没有可调整的方案。'
              : '当前还没有规划结果可供调整。'
        "
        @open-drawer="openAiDrawer(null)"
      />
    </main>

    <!-- AI 调整抽屉：桌面右侧 / 移动端全屏 -->
    <button
      v-if="aiDrawerOpen"
      type="button"
      class="ai-drawer__scrim"
      data-testid="ai-drawer-scrim"
      aria-label="关闭 AI 调整面板"
      @click="closeAiDrawer"
    ></button>

    <AiAdjustDrawer
      :open="aiDrawerOpen"
      :plan-digest="planDigest"
      :semester="userInput.semester"
      :current-schedule-count="currentScheduleCount"
      :focus-course-id="aiFocusCourseId"
      :current-plan="displayedPlanResult"
      :current-plan-label="planResultLabel"
      :makeup-tasks="data?.makeup_tasks ?? []"
      :api-enabled="AI_PLANNING_API_ENABLED"
      :preview-enabled="AI_PLANNING_PREVIEW"
      @close="closeAiDrawer"
      @adopted="onAiAdopted"
    />

    <E2EDebugPanel v-if="isDev" :dev="isDev" :info="e2eDebugInfo" />

    <footer class="page__footer">
      <div class="footer-content">
        <p class="footer-brand">
          <strong>学航·转衔</strong> —— 面向高校转专业学生的 AI 学业路径重构 Agent 系统
        </p>
        <p class="footer-compliance">
          数据声明：<strong>页面基础展示数据</strong>由后端
          <code class="mono">GET /api/v1/mock/demo</code> 通道提供，属<strong>演示数据</strong>。
          <br />
          <template v-if="planResultMode === 'ai_candidate'">
            <strong>当前方案</strong>来自 AI 调整的<strong>后端确认采用</strong>结果；
          </template>
          <template v-else-if="planResultMode === 'real'">
            <strong>规划结果</strong>由 <code class="mono">POST /api/v1/plan</code> 返回（Real）；
          </template>
          <template v-else>
            <strong>规划结果</strong>当前同样来自上述 Mock 演示通道；尚未提交 Real Planning。
          </template>
          AI 调整接口（<code class="mono">/api/v1/ai-planning/*</code>）尚未由后端实现，
          未配置时页面明确显示"尚未配置"，<strong>不会</strong>伪造候选方案。
          <br />
          两类内容均<strong>不代表真实教务系统正式指令</strong>。
        </p>
        <p v-if="digestError" class="footer-compliance" data-testid="digest-error">{{ digestError }}</p>
      </div>
    </footer>
  </div>
</template>
