<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import CandidateComparePanel from './CandidateComparePanel.vue'
import IntentConfirmPanel from './IntentConfirmPanel.vue'
import type { AiLockedCourse, AiSolveResponse } from '../../api/aiPlanningContract'
import {
  SOLVE_STATUS_TEXT,
  unavailableReasonLabel,
  useAiPlanning,
  type AiPlanningContextInput,
} from '../../composables/useAiPlanning'
import type { CourseOffering, MakeupTask, PlanResult, Preference } from '../../types/contracts'

/**
 * AI 调整抽屉（桌面右侧 / 移动端全屏）。
 *
 * 硬边界（PR #65 Review 之后）：
 * - 面板围绕**当前选中的补修方案**，不是独立聊天机器人；
 * - 两次确认都保留：**执行前确认意图**、**采用前确认方案**；
 * - 只有后端 `status = candidate_ready` 才是有效候选；
 * - `/adopt` **不返回方案体**：采用时使用 `/solve` 已返回的候选；
 * - "已采用"只是**进程内会话状态**（`process_local_session`），⛔ 不是持久保存、
 *   ⛔ 更不是教务系统选课成功；
 * - 预览 fixture 必须醒目标注"仅前端预览 / 非真实模型 / 未调用 Planner"。
 */
const props = defineProps<{
  open: boolean
  semester: string
  basePlan: PlanResult | null
  basePlanLabel: string
  makeupTasks: MakeupTask[]
  courseOfferings: CourseOffering[]
  preference: Preference | null
  focusCourseId: string | null
  /** 真实通道是否启用（关闭时不发请求）。 */
  apiEnabled: boolean
  /** 预览模式（只读 fixture）。 */
  previewEnabled: boolean
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'applied', plan: PlanResult, version: number): void
}>()

const ai = useAiPlanning()
const messageDraft = ref('')

const contextInput = computed<AiPlanningContextInput>(() => ({
  semester: props.semester,
  basePlan: props.basePlan,
  makeupTasks: props.makeupTasks,
  courseOfferings: props.courseOfferings,
  preference: props.preference,
  focusCourseId: props.focusCourseId,
}))

/** 可锁定候选：当前方案里**已选中**的教学班（对应后端"只能锁已选中班次"的规则）。 */
const lockCandidates = computed<AiLockedCourse[]>(() => {
  const nameById = new Map<string, string>()
  for (const task of props.makeupTasks) {
    nameById.set(task.course_id, task.course_name)
  }
  return (props.basePlan?.selected_classes ?? []).map((item) => ({
    course_id: item.course_id,
    class_id: item.class_id,
    reason: `当前方案已选中：${nameById.get(item.course_id) ?? item.course_id}`,
  }))
})

/** 通道完全不可用（既没开真实接口，也没开预览）。 */
const channelDisabled = computed(() => !props.apiEnabled && !props.previewEnabled)

const capabilityLabel = computed(() => {
  if (props.previewEnabled) {
    return '前端预览（只读 fixture）'
  }
  if (!props.apiEnabled) {
    return '未启用'
  }
  return '真实接口'
})

const statusLine = computed(() => {
  const status = ai.status
  if (status === null) {
    return '状态未知'
  }
  return `enabled=${String(status.enabled)} · api_key_configured=${String(
    status.api_key_configured,
  )} · live_model_available=${String(status.live_model_available)} · model=${status.model}`
})

/** 后端给的 `blocked_reason` → 面向用户的说明（⛔ 不夸大能力）。 */
const blockedReasonLabel = computed(() => {
  const reason = ai.solveResult?.blocked_reason
  if (!reason) {
    return null
  }
  if (reason.startsWith('planner_not_configured')) {
    return '受控 Planner 尚未装配，因此没有生成候选。'
  }
  if (reason.startsWith('planner_rejected_input')) {
    return '受控 Planner 拒绝了这次输入，因此没有生成候选。'
  }
  if (reason === 'locked_course_would_change') {
    return '候选会破坏你锁定的课程，后端已拒绝该候选。'
  }
  if (reason === 'candidate_references_unavailable_class') {
    return '候选引用了不可用的教学班，后端已拒绝该候选。'
  }
  if (reason.startsWith('exclude_course_hard_constraint')) {
    return '当前冻结的 Planner 不支持"排除某门课"这种硬约束。'
  }
  if (reason === 'cross_semester_adjustment_not_supported') {
    return '当前只支持当前学期调整，跨学期调整暂不支持。'
  }
  return '后端给出了未识别的阻塞原因（已原样显示，⛔ 不猜测含义）。'
})

const adopting = computed(() => ai.phase === 'adopting')
const reviewSolve = computed<AiSolveResponse | null>(() =>
  ai.phase === 'review' ? ai.solveResult : null,
)

onMounted(() => {
  if (!channelDisabled.value) {
    void ai.loadStatus()
  }
})

watch(
  () => props.open,
  (open) => {
    if (open && !ai.statusChecked && !channelDisabled.value) {
      void ai.loadStatus()
    }
  },
)

async function submitMessage(): Promise<void> {
  ai.userMessage = messageDraft.value
  await ai.parseMessage(contextInput.value)
}

async function confirmAndSolve(): Promise<void> {
  await ai.solve(props.semester)
}

function editAgain(): void {
  ai.reset()
  ai.userMessage = messageDraft.value
}

async function adopt(): Promise<void> {
  await ai.adopt()
  if (ai.phase === 'applied' && ai.appliedPlan !== null) {
    emit('applied', ai.appliedPlan, ai.appliedVersion ?? 0)
  }
}

async function keep(): Promise<void> {
  await ai.keepOriginal()
}

/** "撤销"入口：清空本次会话，以后端给的旧方案为 base 重新解析（⛔ 不改后端状态）。 */
function startUndo(): void {
  ai.reset()
  messageDraft.value = ''
}
</script>

<template>
  <aside
    class="ai-drawer"
    :class="{ 'ai-drawer--open': open, 'ai-drawer--fullscreen': open }"
    data-testid="ai-drawer"
    :aria-hidden="!open"
  >
    <header class="ai-drawer__head">
      <div>
        <h3>AI 调整 · 围绕当前补修方案</h3>
        <p class="ai-drawer__context" data-testid="ai-drawer-context">
          调整对象：<strong>{{ basePlanLabel }}</strong>
          <span class="ai-drawer__sep" aria-hidden="true">·</span>
          学期：<code class="mono">{{ semester }}</code>
        </p>
        <p class="ai-drawer__context">
          通道：<strong data-testid="ai-drawer-channel">{{ capabilityLabel }}</strong>
          <span class="ai-drawer__sep" aria-hidden="true">·</span>
          <span data-testid="ai-drawer-status">{{ statusLine }}</span>
        </p>
      </div>
      <button
        type="button"
        class="button button--ghost"
        data-testid="ai-drawer-close"
        @click="emit('close')"
      >
        ✕ 关闭
      </button>
    </header>

    <div v-if="focusCourseId" class="ai-drawer__focus" data-testid="ai-drawer-focus">
      聚焦课程上下文：<code class="mono">{{ focusCourseId }}</code>
      （只作为界面上下文，⛔ 不会自动改这门课）
    </div>

    <div v-if="channelDisabled" class="ai-drawer__disabled" data-testid="ai-not-configured">
      <p class="state state--error">AI 调整不可用</p>
      <p class="state__detail">
        未启用真实 AI 调整接口（<code class="mono">VITE_AI_PLANNING_API_ENABLED</code> 未开启），
        也未开启前端预览。
      </p>
      <p class="state__hint">
        因此这里<strong>不会</strong>调用求解、<strong>不会</strong>生成候选方案，
        也<strong>不会</strong>显示任何"AI 已调整成功"。
      </p>
    </div>

    <template v-else>
      <div
        v-if="ai.phase === 'checking'"
        class="state state--loading"
        data-testid="ai-status-checking"
      >
        正在读取后端 AI 调整可用状态（GET /api/v1/ai-planning/status）…
      </div>

      <div
        v-else-if="ai.phase === 'unavailable'"
        class="ai-drawer__disabled"
        data-testid="ai-unavailable"
      >
        <p class="state state--error">AI 调整当前不可用</p>
        <p class="state__detail" data-testid="ai-unavailable-reason">
          {{ unavailableReasonLabel(ai.unavailableReason) }}
        </p>
        <p v-if="ai.errorMessage" class="state__hint" data-testid="ai-unavailable-detail">
          {{ ai.errorMessage }}
        </p>
        <p class="state__hint">
          页面<strong>不会</strong>回退到任何演示模型，也不会伪造候选方案。
        </p>
        <button
          type="button"
          class="button button--ghost"
          data-testid="ai-status-retry"
          @click="ai.loadStatus"
        >
          🔄 重新检查
        </button>
      </div>

      <template v-else>
        <section class="ai-drawer__input">
          <label class="ai-field">
            <span>
              用一句自然语言说明你想怎么调整（例如：这学期太累，数据结构必须保留，尽量别在周五上课）
            </span>
            <textarea
              v-model="messageDraft"
              rows="3"
              data-testid="ai-utterance-input"
              :disabled="ai.busy"
              placeholder="这学期太累，数据结构必须保留，尽量别在周五上课"
            ></textarea>
          </label>
          <div class="ai-drawer__input-actions">
            <button
              type="button"
              class="button"
              data-testid="ai-parse-intent"
              :disabled="ai.busy || messageDraft.trim() === ''"
              @click="submitMessage"
            >
              {{ ai.phase === 'interpreting' ? '正在解析…' : '🧠 让 AI 解析这句话' }}
            </button>
            <span class="ai-drawer__hint">
              解析只产生"待确认草稿"；确认前不会求解，也不会改动当前方案。
              请勿填写姓名、学号、联系方式或任何凭据（服务器会拒收）。
            </span>
          </div>
        </section>

        <p v-if="ai.errorMessage" class="error-box" data-testid="ai-error">
          <strong data-testid="ai-error-kind">{{ ai.errorKind ?? 'error' }}</strong>
          <span data-testid="ai-error-message">{{ ai.errorMessage }}</span>
        </p>

        <IntentConfirmPanel
          v-if="ai.draft && (ai.phase === 'draft' || ai.phase === 'solving')"
          :draft="ai.draft"
          :plan-digest="ai.planDigest"
          :ambiguities="ai.ambiguities"
          :can-confirm="ai.canConfirmIntent"
          :message="ai.interpretation?.message ?? ''"
          :generator-kind="ai.generatorKind"
          :generator-note="ai.generatorNote"
          :data-source="ai.dataSource"
          :preview-notice="ai.previewNotice"
          :credit-limit="ai.editedCreditLimit"
          :avoid-weekdays="ai.editedAvoidWeekdays"
          :locked-courses="ai.editedLockedCourses"
          :lock-candidates="lockCandidates"
          :disabled="ai.busy"
          :busy="ai.phase === 'solving'"
          @update-credit-limit="ai.setCreditLimit"
          @toggle-avoid-weekday="ai.toggleAvoidWeekday"
          @toggle-lock="ai.toggleLockedCourse"
          @confirm="confirmAndSolve"
          @edit-again="editAgain"
        />

        <section
          v-if="ai.phase === 'unsolved' && ai.solveResult"
          class="ai-unsolved"
          data-testid="ai-unsolved"
        >
          <h4 data-testid="ai-unsolved-title">
            {{ SOLVE_STATUS_TEXT[ai.solveResult.status] }}
          </h4>
          <p data-testid="ai-unsolved-message">{{ ai.solveResult.message }}</p>
          <p class="ai-block__hint">
            这次<strong>没有生成候选方案</strong>：当前方案保持不变。
          </p>
          <ul v-if="ai.solveResult.unresolved.length > 0">
            <li v-for="(item, index) in ai.solveResult.unresolved" :key="index">{{ item }}</li>
          </ul>
          <button
            type="button"
            class="button button--ghost"
            data-testid="ai-unsolved-retry"
            :disabled="ai.busy"
            @click="ai.backToDraft"
          >
            ↺ 回到意图草稿
          </button>
        </section>

        <CandidateComparePanel
          v-if="reviewSolve"
          :solve="reviewSolve"
          :original-plan="basePlan"
          :original-label="basePlanLabel"
          :generator-kind="ai.generatorKind"
          :data-source="ai.dataSource"
          :blocked-reason-label="blockedReasonLabel"
          :preview-notice="ai.previewNotice"
          :disabled="ai.busy"
          :busy="adopting"
          @adopt="adopt"
          @keep="keep"
          @resolve-again="ai.backToDraft"
          @back-to-draft="ai.backToDraft"
        />

        <section v-if="ai.phase === 'applied'" class="ai-adopted" data-testid="ai-adopted">
          <h4>✅ 后端已确认采用该候选</h4>
          <p data-testid="ai-adopted-message">{{ ai.adoptResult?.message }}</p>
          <p class="ai-block__unknown" data-testid="ai-adopted-scope">
            ⚠️ 这是<strong>进程内会话状态</strong>（<code class="mono">{{ ai.appliedScope }}</code>）：
            <strong>未持久化保存</strong>，服务重启即失效，也<strong>不代表</strong>教务系统已完成选课。
          </p>
          <p class="ai-block__hint">
            会话版本：<strong class="num" data-testid="ai-adopted-version">{{ ai.appliedVersion }}</strong>
          </p>
          <p class="ai-block__hint">
            当前方案已刷新为后端候选；第 2 步的解释入口会基于<strong>刷新后的方案</strong>重新取依据。
          </p>
          <button
            type="button"
            class="button button--ghost"
            data-testid="ai-undo-adoption"
            :disabled="ai.busy"
            @click="startUndo"
          >
            ↩️ 以原方案为基准重新调整（撤销入口）
          </button>
        </section>

        <section v-if="ai.phase === 'kept'" class="ai-adopted" data-testid="ai-kept">
          <h4>🛡️ 已确认保留原方案</h4>
          <p data-testid="ai-kept-message">{{ ai.adoptResult?.message }}</p>
          <p class="ai-block__hint">
            后端确认原方案未被改动（original_plan_unchanged =
            {{ String(ai.adoptResult?.original_plan_unchanged) }}）。
          </p>
          <button
            type="button"
            class="button button--ghost"
            data-testid="ai-kept-restart"
            :disabled="ai.busy"
            @click="ai.reset"
          >
            🔄 重新开始调整
          </button>
        </section>
      </template>
    </template>
  </aside>
</template>
