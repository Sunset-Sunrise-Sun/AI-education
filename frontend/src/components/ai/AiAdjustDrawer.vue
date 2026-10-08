<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import CandidateComparePanel from './CandidateComparePanel.vue'
import IntentConfirmPanel from './IntentConfirmPanel.vue'
import type { AiCandidatePlan } from '../../api/aiPlanningTypes'
import { SOLVE_STATUS_TEXT, useAiPlanning } from '../../composables/useAiPlanning'
import type { MakeupTask, PlanResult } from '../../types/contracts'

/**
 * AI 调整抽屉（桌面右侧 / 移动端全屏）。
 *
 * 硬边界：
 * - 面板**围绕当前选中的补修方案**，不是独立聊天机器人；
 * - ⛔ 前端不计算规划、不生成候选；未配置时明确显示不可用；
 * - ⛔ 预览 fixture 必须醒目标注"仅前端预览 / 非真实模型 / 未调用 Planner"；
 * - 只有后端确认采用成功才把候选变成当前方案（由父组件接收 `adopted` 事件刷新）。
 */
const props = defineProps<{
  open: boolean
  planDigest: string
  semester: string
  currentScheduleCount: number
  focusCourseId: string | null
  /** 当前方案（用于候选对比）。 */
  currentPlan: PlanResult | null
  currentPlanLabel: string
  /** 补修任务上下文：仅用于"可锁定课程"选项。 */
  makeupTasks: MakeupTask[]
  /** 真实通道是否启用（关闭时显示"尚未配置"）。 */
  apiEnabled: boolean
  /** 预览模式（只读 fixture）。 */
  previewEnabled: boolean
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'adopted', plan: PlanResult): void
}>()

const ai = useAiPlanning()
const utteranceDraft = ref('')

watch(
  () => props.open,
  (open) => {
    if (open && ai.phase === 'not_configured') {
      ai.reset()
    }
  },
)

const context = computed(() => ({
  planDigest: props.planDigest,
  semester: props.semester,
  currentScheduleCount: props.currentScheduleCount,
  focusCourseId: props.focusCourseId,
}))

const lockableCourses = computed(() =>
  props.makeupTasks.map((task) => ({
    course_id: task.course_id,
    course_name: task.course_name,
  })),
)

const originalPlan = computed<AiCandidatePlan | null>(() =>
  props.currentPlan === null ? null : (props.currentPlan as AiCandidatePlan),
)

/** 通道不可用（关闭且非预览）时的显式说明。 */
const channelDisabled = computed(() => !props.apiEnabled && !props.previewEnabled)

/** 是否正在提交第二次确认（避免模板内做窄化比较）。 */
const adopting = computed(() => ai.phase === 'adopting')

const capabilityLabel = computed(() => {
  if (props.previewEnabled) {
    return '前端预览（只读 fixture）'
  }
  if (!props.apiEnabled) {
    return '尚未配置'
  }
  return '真实接口'
})

async function submitUtterance(): Promise<void> {
  ai.utterance = utteranceDraft.value
  await ai.parseUtterance(context.value)
}

async function confirmAndSolve(): Promise<void> {
  await ai.solve(context.value)
}

function editAgain(): void {
  ai.reset()
  void nextTick(() => {
    utteranceDraft.value = ai.utterance
  })
}

async function adopt(): Promise<void> {
  await ai.adopt(context.value)
  if (ai.phase === 'adopted' && ai.adoptedPlan !== null) {
    emit('adopted', ai.adoptedPlan)
  }
}

async function keep(): Promise<void> {
  await ai.keepOriginal(context.value)
}

function resolveAgain(): void {
  ai.solveResult = null
  ai.candidatePlan = null
  ai.candidateDiff = null
  ai.phase = 'draft'
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
          调整对象：<strong>{{ currentPlanLabel }}</strong>
          <span class="ai-drawer__sep" aria-hidden="true">·</span>
          方案指纹：<code class="mono" data-testid="ai-drawer-digest">{{ planDigest }}</code>
        </p>
        <p class="ai-drawer__context">
          通道：<strong data-testid="ai-drawer-channel">{{ capabilityLabel }}</strong>
          <span class="ai-drawer__sep" aria-hidden="true">·</span>
          学期：<code class="mono">{{ semester }}</code>
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
      （只作为解析上下文，⛔ 不会自动改这门课）
    </div>

    <div v-if="channelDisabled" class="ai-drawer__disabled" data-testid="ai-not-configured">
      <p class="state state--error">AI 调整尚未配置</p>
      <p class="state__detail">
        当前未启用真实 AI 调整接口（<code class="mono">VITE_AI_PLANNING_API_ENABLED</code> 未开启），
        也未开启前端预览。
      </p>
      <p class="state__hint">
        因此这里<strong>不会</strong>调用规划器、<strong>不会</strong>生成候选方案，
        也<strong>不会</strong>显示任何"AI 已调整成功"。
      </p>
    </div>

    <template v-else>
      <section class="ai-drawer__input">
        <label class="ai-field">
          <span>用一句自然语言说明你想怎么调整（例如：尽量在大三前补完，这学期尽量轻松，但数据结构必须保留）</span>
          <textarea
            v-model="utteranceDraft"
            rows="3"
            data-testid="ai-utterance-input"
            :disabled="ai.busy"
            placeholder="尽量在大三前补完，这学期尽量轻松，但数据结构必须保留"
          ></textarea>
        </label>
        <div class="ai-drawer__input-actions">
          <button
            type="button"
            class="button"
            data-testid="ai-parse-intent"
            :disabled="ai.busy || utteranceDraft.trim() === ''"
            @click="submitUtterance"
          >
            {{ ai.phase === 'interpreting' ? '正在解析…' : '🧠 让 AI 解析这句话' }}
          </button>
          <span class="ai-drawer__hint">
            解析只产生"待确认草稿"；确认前不会求解，也不会改动当前方案。
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
        :lockable-courses="lockableCourses"
        :can-confirm="ai.canConfirmIntent"
        :message="ai.interpretation?.message ?? ''"
        :generator-kind="ai.generatorKind"
        :preview-notice="ai.previewNotice"
        :disabled="ai.busy"
        :busy="ai.phase === 'solving'"
        @update-credit-limit="ai.setCreditLimit"
        @toggle-lock="ai.toggleLockedCourse"
        @confirm="confirmAndSolve"
        @edit-again="editAgain"
      />

      <section v-if="ai.phase === 'unsolved' && ai.solveResult" class="ai-unsolved" data-testid="ai-unsolved">
        <h4>{{ SOLVE_STATUS_TEXT[ai.solveResult.status] }}</h4>
        <p>{{ ai.solveResult.message }}</p>
        <p class="ai-block__hint">
          这次<strong>没有生成候选方案</strong>：当前方案保持不变。
        </p>
        <ul v-if="ai.solveResult.unresolved.length > 0">
          <li v-for="(item, index) in ai.solveResult.unresolved" :key="index">
            <span class="mono">{{ item.type }}</span> {{ item.message }}
          </li>
        </ul>
        <button
          type="button"
          class="button button--ghost"
          data-testid="ai-unsolved-retry"
          :disabled="ai.busy"
          @click="resolveAgain"
        >
          ↺ 回到意图草稿
        </button>
      </section>

      <CandidateComparePanel
        v-if="ai.phase === 'candidate' && ai.solveResult"
        :solve="ai.solveResult"
        :original-plan="originalPlan"
        :original-label="currentPlanLabel"
        :preview-notice="ai.previewNotice"
        :disabled="ai.busy"
        :busy="adopting"
        @adopt="adopt"
        @keep="keep"
        @resolve-again="resolveAgain"
      />

      <section v-if="ai.phase === 'adopted'" class="ai-adopted" data-testid="ai-adopted">
        <h4 v-if="ai.adoptedPlan">✅ 已采用候选方案（后端确认）</h4>
        <h4 v-else>🛡️ 已确认保留原方案</h4>
        <p data-testid="ai-adopted-message">{{ ai.adoptResult?.message }}</p>
        <p v-if="ai.adoptedVersion" class="ai-block__hint">
          结果版本：<code class="mono" data-testid="ai-adopted-version">{{ ai.adoptedVersion }}</code>
        </p>
        <p class="ai-block__hint">
          当前方案第 2 步的解释入口会基于<strong>刷新后的方案</strong>重新取依据。
        </p>
      </section>
    </template>
  </aside>
</template>
