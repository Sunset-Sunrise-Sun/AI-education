<script setup lang="ts">
import { computed } from 'vue'
import type {
  AiAmbiguity,
  AiDataSource,
  AiGeneratorKind,
  AiHardConstraint,
  AiLockedCourse,
  AiParsedIntentDraft,
  AiSoftPreference,
} from '../../api/aiPlanningContract'
import { dataSourceLabel, generatorKindLabel } from '../../composables/useAiPlanning'

/**
 * **第一次确认**面板：展示并编辑后端返回的意图草稿。
 *
 * 硬边界（与后端 HANDOFF 一致）：
 * - 确认前**不可进入有状态的 solve**（按钮由父组件按 `can-confirm` 控制）；
 * - **学分上限不猜**：后端不给数字时显示"未指定"，必须由用户填写，
 *   回传时会带上 `evidence`（后端要求 `max_credit_limit` 必须有依据）；
 * - 锁定课程只能从**后端给出的候选**里选择（⛔ 不让学生凭空锁一门课）；
 * - `can_confirm=false` 时必须先回答 `ambiguities[]` 里的问题；
 * - `generator_kind=test_double` 必须显示为"测试替身模型（不是线上模型）"。
 */
const props = defineProps<{
  draft: AiParsedIntentDraft
  /** 后端计算的方案指纹（只读展示，⛔ 前端不改写）。 */
  planDigest: string | null
  ambiguities: AiAmbiguity[]
  canConfirm: boolean
  message: string
  generatorKind: AiGeneratorKind | null
  generatorNote: string | null
  dataSource: AiDataSource | null
  previewNotice: string | null
  /** 本地编辑态。 */
  creditLimit: number | null
  avoidWeekdays: number[]
  lockedCourses: AiLockedCourse[]
  /** 可锁定候选（当前方案里已选中的教学班）。 */
  lockCandidates: AiLockedCourse[]
  disabled: boolean
  busy: boolean
}>()

const emit = defineEmits<{
  (event: 'update-credit-limit', value: number | null): void
  (event: 'toggle-avoid-weekday', weekday: number): void
  (event: 'toggle-lock', course: AiLockedCourse): void
  (event: 'confirm'): void
  (event: 'edit-again'): void
}>()

const WEEKDAYS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' },
]

const creditLimitValue = computed(() =>
  props.creditLimit === null ? '' : String(props.creditLimit),
)

/** 后端草稿里已有的学分上限（用于对照，⛔ 不自动沿用）。 */
const draftCreditLimit = computed<AiHardConstraint | null>(
  () => props.draft.hard_constraints.find((item) => item.kind === 'max_credit_limit') ?? null,
)

const executableSoftPreferences = computed<AiSoftPreference[]>(() =>
  props.draft.soft_preferences.filter((item) => item.kind !== 'avoid_weekday'),
)

const otherHardConstraints = computed<AiHardConstraint[]>(() =>
  props.draft.hard_constraints.filter((item) => item.kind !== 'max_credit_limit'),
)

const unlockedCandidates = computed(() =>
  props.lockCandidates.filter(
    (candidate) =>
      !props.lockedCourses.some(
        (item) =>
          item.course_id === candidate.course_id && item.class_id === candidate.class_id,
      ),
  ),
)

function onCreditInput(event: Event): void {
  const raw = (event.target as HTMLInputElement).value.trim()
  if (raw === '') {
    emit('update-credit-limit', null)
    return
  }
  const parsed = Number(raw)
  emit('update-credit-limit', Number.isFinite(parsed) && parsed >= 0 ? parsed : null)
}

function isAvoiding(weekday: number): boolean {
  return props.avoidWeekdays.includes(weekday)
}
</script>

<template>
  <section class="ai-confirm" data-testid="ai-intent-draft">
    <header class="ai-confirm__head">
      <h4>第一次确认 · 待确认意图草稿</h4>
      <span class="tag tag--ai-generator" data-testid="ai-generator-kind">
        {{ generatorKindLabel(generatorKind) }}
      </span>
    </header>

    <p class="ai-confirm__message" data-testid="ai-intent-message">{{ message }}</p>
    <p v-if="generatorNote" class="ai-block__hint" data-testid="ai-generator-note">
      {{ generatorNote }}
    </p>
    <p class="ai-block__hint" data-testid="ai-data-source">
      上下文数据来源：{{ dataSourceLabel(dataSource) }}
    </p>
    <p v-if="planDigest" class="ai-block__hint" data-testid="ai-plan-digest">
      方案指纹（由后端计算，前端只回传）：<code class="mono">{{ planDigest }}</code>
    </p>

    <p v-if="previewNotice" class="ai-preview" data-testid="ai-preview-notice">
      ⚠️ {{ previewNotice }}
    </p>

    <p class="ai-block__hint" data-testid="ai-intent-summary">
      AI 的理解：{{ draft.summary }}（置信度 {{ draft.confidence.toFixed(2) }}）
    </p>

    <div
      v-if="ambiguities.length > 0"
      class="ai-block ai-block--unknown"
      data-testid="ai-ambiguities"
    >
      <h5>必须先回答的问题（歧义未消解前不能求解）</h5>
      <ul>
        <li v-for="item in ambiguities" :key="item.code">
          <span class="mono">{{ item.code }}</span>
          <p>{{ item.question }}</p>
          <p v-if="item.detail" class="ai-block__hint">{{ item.detail }}</p>
        </li>
      </ul>
    </div>

    <div class="ai-confirm__grid">
      <!-- 硬约束：视觉上单独一块，明确"不可协商" -->
      <div class="ai-block ai-block--hard" data-testid="ai-hard-constraints">
        <h5>硬约束 · 不可协商</h5>
        <p class="ai-block__hint">
          这些条件在求解时<strong>必须满足</strong>；候选如果违反，后端会直接拒绝该候选。
        </p>
        <ul v-if="otherHardConstraints.length > 0">
          <li v-for="item in otherHardConstraints" :key="`${item.kind}-${String(item.value)}`">
            <span class="tag tag--ai-hard">{{ item.kind }}</span>
            {{ item.value }}
            <span v-if="item.evidence" class="ai-block__hint">依据：{{ item.evidence }}</span>
          </li>
        </ul>
        <p v-else class="empty-state" data-testid="ai-no-hard-constraints">
          这次解析没有识别出其它硬约束。你可以在下面"锁定课程"里自己加一条。
        </p>
      </div>

      <!-- 软偏好：明确"可协商" -->
      <div class="ai-block ai-block--soft" data-testid="ai-soft-preferences">
        <h5>软偏好 · 可协商</h5>
        <p class="ai-block__hint">
          这些只是<strong>倾向</strong>：求解会尽量照顾，但为了让硬约束成立，可能无法全部满足。
        </p>
        <ul v-if="executableSoftPreferences.length > 0">
          <li v-for="item in executableSoftPreferences" :key="`${item.kind}-${String(item.value)}`">
            <span class="tag tag--ai-soft">{{ item.kind }}</span>
            {{ item.value ?? '—' }}
            <span v-if="item.note" class="ai-block__hint">{{ item.note }}</span>
          </li>
        </ul>
        <p v-else class="empty-state">没有其它软偏好。</p>
        <div class="ai-weekday-grid" data-testid="ai-avoid-weekdays">
          <span class="ai-block__hint">尽量避开（软偏好）：</span>
          <button
            v-for="day in WEEKDAYS"
            :key="day.value"
            type="button"
            class="button button--ghost button--small"
            :class="{ 'button--selected': isAvoiding(day.value) }"
            :data-testid="`ai-avoid-weekday-${day.value}`"
            :disabled="disabled"
            @click="emit('toggle-avoid-weekday', day.value)"
          >
            {{ day.label }}
          </button>
        </div>
      </div>

      <div class="ai-block ai-block--hard" data-testid="ai-credit-limit">
        <h5>本学期学分上限 · 硬约束</h5>
        <p v-if="creditLimit === null" class="ai-block__unknown" data-testid="ai-credit-unspecified">
          <strong>未指定</strong>：AI 没有给出可验证的学分上限，
          <strong>页面不会替你猜一个默认值</strong>。请填写数字，或保持"未指定"。
        </p>
        <p v-else class="ai-block__value">
          将回传：<strong class="num">{{ creditLimit }}</strong> 学分
          （依据：用户在确认面板填写）
        </p>
        <p v-if="draftCreditLimit" class="ai-block__hint" data-testid="ai-credit-from-backend">
          后端草稿里的学分上限：{{ draftCreditLimit.value }}
          （依据 {{ draftCreditLimit.evidence ?? '缺失' }}）
        </p>
        <label class="ai-field">
          <span>学分上限（留空表示不提交该硬约束）</span>
          <input
            :value="creditLimitValue"
            type="number"
            min="0"
            step="0.5"
            data-testid="ai-credit-input"
            :disabled="disabled"
            @input="onCreditInput"
          />
        </label>
      </div>

      <div class="ai-block ai-block--hard" data-testid="ai-locked-courses">
        <h5>锁定课程 · 必须保留</h5>
        <p class="ai-block__hint">
          只能锁定<strong>当前方案里已经选中</strong>的教学班；后端会核对，锁不住的会被拒绝。
        </p>
        <ul v-if="lockedCourses.length > 0">
          <li
            v-for="course in lockedCourses"
            :key="`${course.course_id}-${course.class_id}`"
            :data-testid="`ai-locked-${course.course_id}`"
          >
            <span class="mono">{{ course.course_id }}</span>
            <span class="mono">班号 {{ course.class_id }}</span>
            <span class="ai-block__hint">{{ course.reason }}</span>
            <button
              type="button"
              class="button button--ghost button--small"
              :data-testid="`ai-unlock-${course.course_id}`"
              :disabled="disabled"
              @click="emit('toggle-lock', course)"
            >
              取消锁定
            </button>
          </li>
        </ul>
        <p v-else class="empty-state" data-testid="ai-no-locked-courses">当前没有锁定课程。</p>

        <div v-if="unlockedCandidates.length > 0" class="ai-lock-candidates">
          <span class="ai-block__hint">可锁定（只能锁当前方案里已选中的教学班）：</span>
          <button
            v-for="candidate in unlockedCandidates"
            :key="`${candidate.course_id}-${candidate.class_id}`"
            type="button"
            class="button button--ghost button--small"
            :data-testid="`ai-lock-${candidate.course_id}`"
            :disabled="disabled"
            @click="emit('toggle-lock', candidate)"
          >
            + {{ candidate.course_id }}（班号 {{ candidate.class_id }}）
          </button>
        </div>
      </div>

      <div class="ai-block" data-testid="ai-scope">
        <h5>范围</h5>
        <ul>
          <li>调整范围：<span class="mono">{{ draft.scope }}</span>（当前后端只支持当前学期）</li>
          <li>目标学期：<span class="mono">{{ draft.target_semester ?? '未指定' }}</span></li>
        </ul>
      </div>

      <div class="ai-block" data-testid="ai-unknowns">
        <h5>解析备注</h5>
        <ul v-if="draft.notes.length > 0">
          <li v-for="(note, index) in draft.notes" :key="index">{{ note }}</li>
        </ul>
        <p v-else class="empty-state">后端没有给出额外备注。</p>
      </div>
    </div>

    <p v-if="!canConfirm" class="ai-confirm__blocked" data-testid="ai-cannot-confirm">
      后端标记这次解析<strong>仍有歧义</strong>（`can_confirm = false`）：
      请先回答上面的问题并重新解析。页面不会在未确认的情况下调用求解。
    </p>

    <div class="ai-confirm__actions">
      <button
        type="button"
        class="button"
        data-testid="ai-confirm-intent"
        :disabled="disabled || busy || !canConfirm"
        @click="emit('confirm')"
      >
        {{ busy ? '正在求解…' : '✅ 确认意图并生成候选方案' }}
      </button>
      <button
        type="button"
        class="button button--ghost"
        data-testid="ai-edit-again"
        :disabled="disabled || busy"
        @click="emit('edit-again')"
      >
        ✏️ 改一句重说
      </button>
      <span class="ai-confirm__hint">
        确认前<strong>不会</strong>调用求解接口；这一步只确认"AI 理解得对不对"。
      </span>
    </div>
  </section>
</template>
