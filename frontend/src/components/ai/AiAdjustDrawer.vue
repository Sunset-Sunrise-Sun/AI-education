<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import CandidateComparePanel from './CandidateComparePanel.vue'
import IntentConfirmPanel from './IntentConfirmPanel.vue'
import { describeCapability } from './drawerCapability'
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
  /** 打开面板时预填的示例语句（入口给的输入提示；⛔ 不等于已解析）。 */
  seedMessage?: string | null
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
const seedApplied = ref(false)

/**
 * 面板打开且带示例语句时预填输入框。
 *
 * ⚠️ 只是**输入提示**：不自动解析、不自动求解；用户可改写或清空。
 */
watch(
  () => [props.open, props.seedMessage] as const,
  ([open, seed]) => {
    if (open && seed && !seedApplied.value) {
      messageDraft.value = seed
      seedApplied.value = true
    }
    if (!open) {
      // 关闭时清空预填：下次打开不会残留上一次的示例或半截输入。
      seedApplied.value = false
      messageDraft.value = ''
    }
  },
  { immediate: true },
)

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

/**
 * 面向普通用户的**一句话能力状态** + 技术详情（见 `drawerCapability.ts`）。
 *
 * ⛔ 只读 `status` 上的布尔与模型名；⛔ 不读取、不拼接、不展示任何密钥内容。
 */
const capability = computed(() =>
  describeCapability(ai.status, { previewEnabled: props.previewEnabled }),
)

const capabilitySummary = computed(() => capability.value.summary)
const technicalFacts = computed(() => capability.value.facts)

/** 技术详情默认折叠（用原生 `<details>`，键盘与读屏可直接使用）。 */
const technicalOpen = ref(false)

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

/** 四个阶段（与后端的 interpret → solve → adopt 一一对应）。 */
const STAGES = [
  { key: 'input', index: 1, label: '说出需求' },
  { key: 'intent', index: 2, label: '确认意图' },
  { key: 'candidate', index: 3, label: '查看候选' },
  { key: 'adopt', index: 4, label: '确认采用' },
] as const

/**
 * 抽屉内的快捷示例（点击只填入输入框，⛔ 不自动解析、不自动提交）。
 *
 * ⚠️ 与 `AI 调整` 视图的示例保持同一风格：只描述学生自己的偏好/硬约束，
 * ⛔ 不出现"帮我选最轻松的课"这类需要系统替学生做价值判断的说法。
 */
const QUICK_EXAMPLES = [
  '这学期太累，尽量别在周五上课',
  '数据结构必须保留，其它可以调整',
] as const

type StageKey = (typeof STAGES)[number]['key']

/** 阶段状态：`active` / `done` / `todo`（只用于展示，不影响任何请求）。 */
function stageState(key: StageKey): 'active' | 'done' | 'todo' {
  const phase = ai.phase
  const order: StageKey[] = ['input', 'intent', 'candidate', 'adopt']
  const reachedIndex = (() => {
    switch (phase) {
      case 'idle':
        return 0
      case 'interpreting':
      case 'draft':
        return 1
      case 'solving':
      case 'unsolved':
        return 2
      case 'review':
      case 'adopting':
        return 3
      case 'applied':
      case 'kept':
        return 4
      default:
        return 0
    }
  })()

  // 终态：全部标记完成（`applied` 表示已采用，`kept` 表示已决定保留）。
  if (phase === 'applied' || phase === 'kept') {
    return 'done'
  }

  const index = order.indexOf(key)
  if (index < reachedIndex) {
    return 'done'
  }
  if (index === reachedIndex) {
    return 'active'
  }
  return 'todo'
}

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
      <div class="ai-drawer__head-main">
        <h3>AI 调整 · 围绕当前补修方案</h3>
        <p class="ai-drawer__context" data-testid="ai-drawer-context">
          调整对象：<strong>{{ basePlanLabel }}</strong>
          <span class="ai-drawer__sep" aria-hidden="true">·</span>
          学期：<code class="mono">{{ semester }}</code>
        </p>
        <p class="ai-drawer__context">
          通道：<strong data-testid="ai-drawer-channel">{{ capabilityLabel }}</strong>
        </p>
        <!--
          面向普通用户的能力状态：一句话说清"现在能不能用、以及为什么"。
          ⛔ 原始配置字段不再直接铺在头部（375px 下会挤成多行），
          而是收进下面的"技术详情"，完整保留、可展开、⛔ 不删信息。
        -->
        <p class="ai-drawer__capability" data-testid="ai-drawer-status">
          {{ capabilitySummary }}
        </p>
        <details
          class="ai-drawer__tech"
          data-testid="ai-drawer-tech"
          :open="technicalOpen"
          @toggle="technicalOpen = ($event.target as HTMLDetailsElement).open"
        >
          <summary data-testid="ai-drawer-tech-toggle">技术详情（配置与限额）</summary>
          <p class="ai-drawer__tech-line" data-testid="ai-drawer-tech-raw">{{ statusLine }}</p>
          <dl class="ai-drawer__tech-list" data-testid="ai-drawer-tech-facts">
            <template v-for="fact in technicalFacts" :key="fact.label">
              <dt>{{ fact.label }}</dt>
              <dd>{{ fact.value }}</dd>
            </template>
          </dl>
          <p class="ai-drawer__tech-note" data-testid="ai-drawer-tech-note">
            ⛔ 这里只显示"是否已配置"这类事实，不显示密钥内容；
            ⛔ <code class="mono">live_model_available=true</code> 只说明开关与密钥就绪，
            <strong>不是</strong>在线鉴权或模型调用成功的证明。
          </p>
        </details>
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

    <!-- 阶段指示：让用户随时知道"现在走到哪一步、下一步是什么" -->
    <ol v-if="!channelDisabled" class="ai-stage" data-testid="ai-stage">
      <li
        v-for="stage in STAGES"
        :key="stage.key"
        class="ai-stage__item"
        :class="{
          'ai-stage__item--done': stageState(stage.key) === 'done',
          'ai-stage__item--active': stageState(stage.key) === 'active',
        }"
        :data-testid="`ai-stage-${stage.key}`"
        :data-stage-state="stageState(stage.key)"
      >
        <span class="ai-stage__dot">{{ stageState(stage.key) === 'done' ? '✓' : stage.index }}</span>
        <span class="ai-stage__text">{{ stage.label }}</span>
      </li>
    </ol>

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
              用一句自然语言说明你想怎么调整（不需要专业术语，说清"哪里不舒服 / 什么必须保留"就够）
            </span>
            <textarea
              v-model="messageDraft"
              rows="3"
              data-testid="ai-utterance-input"
              :disabled="ai.busy"
              placeholder="这学期太累，数据结构必须保留，尽量别在周五上课"
            ></textarea>
          </label>

          <!-- 示例提示：点击即填入输入框（⛔ 不等于已解析，也不会自动提交） -->
          <div class="ai-drawer__examples" data-testid="ai-drawer-examples">
            <span class="ai-drawer__examples-label">示例（点一下填入，可再改）：</span>
            <button
              v-for="example in QUICK_EXAMPLES"
              :key="example"
              type="button"
              class="ai-cta__chip ai-cta__chip--small"
              :data-testid="`ai-quick-example-${example}`"
              :disabled="ai.busy"
              @click="messageDraft = example"
            >
              {{ example }}
            </button>
          </div>

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

        <!-- 正在解析：只说明真实状态，⛔ 不显示假的进度条或假课程 -->
        <div
          v-if="ai.phase === 'interpreting'"
          class="ai-progress"
          data-testid="ai-interpreting"
          role="status"
          aria-live="polite"
        >
          <span class="spinner" aria-hidden="true"></span>
          <div>
            <strong>正在把你的话解析成"待确认的约束"…</strong>
            <p class="ai-drawer__hint">
              这一步<strong>不会</strong>生成任何课程或候选方案；解析完成后还需要你确认一次。
            </p>
          </div>
        </div>

        <!-- 正在求解：说明"正在进行确定性求解"，并明确没有假进度 -->
        <div
          v-if="ai.phase === 'solving'"
          class="ai-progress"
          data-testid="ai-solving"
          role="status"
          aria-live="polite"
        >
          <span class="spinner" aria-hidden="true"></span>
          <div>
            <strong>正在用你确认过的约束求解候选方案…</strong>
            <p class="ai-drawer__hint">
              求解由后端执行（当前学期 + 已装配的教学班供给）。
              <strong>没有进度百分比</strong>：完成前不会显示任何课程，也不会先给一个占位方案。
            </p>
          </div>
        </div>

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
