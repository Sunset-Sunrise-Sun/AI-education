<script setup lang="ts">
import { computed } from 'vue'
import type { AiParsedIntent } from '../../api/aiPlanningTypes'
import type { MakeupTask } from '../../types/contracts'

/**
 * **第一次确认**面板：展示 AI 解析出的待确认意图草稿。
 *
 * 硬边界：
 * - 确认前**不可进入有状态的 solve**（按钮由父组件按 `can-confirm` 控制）；
 * - 学分上限「不猜」：后端给 `null` 时显示"未指定"，并要求用户确认或填写；
 * - 锁定课程只能从**已存在于当前方案**的课程里勾选（⛔ 不让学生凭空锁一门课）。
 */
const props = defineProps<{
  draft: AiParsedIntent
  /** 当前方案可锁定的课程（来自 MakeupTask 上下文；⛔ 前端不新造课程）。 */
  lockableCourses: Pick<MakeupTask, 'course_id' | 'course_name'>[]
  /** 后端是否允许确认（`can_confirm=false` 时必须说明原因）。 */
  canConfirm: boolean
  /** 后端给出的解析说明。 */
  message: string
  /** 后端给出的生成方式（`rule_based_template` 时界面不得说成 AI 生成）。 */
  generatorKind: string | null
  /** 是否来自前端预览 fixture。 */
  previewNotice: string | null
  disabled: boolean
  busy: boolean
}>()

const emit = defineEmits<{
  (event: 'update-credit-limit', value: number | null): void
  (event: 'toggle-lock', courseId: string): void
  (event: 'confirm'): void
  (event: 'edit-again'): void
}>()

const creditLimitValue = computed(() =>
  props.draft.credit_limit === null ? '' : String(props.draft.credit_limit),
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

const generatorLabel = computed(() => {
  switch (props.generatorKind) {
    case 'model':
      return 'AI 模型生成'
    case 'rule_based_template':
      return '规则模板（非 AI）'
    case 'model_unavailable_fell_back_to_template':
      return '规则模板（模型未采用）'
    default:
      return props.generatorKind ? `未知生成方式（${props.generatorKind}）` : '未提供'
  }
})

const unlockedCourses = computed(() =>
  props.lockableCourses.filter(
    (course) => !props.draft.locked_course_ids.includes(course.course_id),
  ),
)
</script>

<template>
  <section class="ai-confirm" data-testid="ai-intent-draft">
    <header class="ai-confirm__head">
      <h4>第一次确认 · 待确认意图草稿</h4>
      <span class="tag tag--ai-generator" data-testid="ai-generator-kind">{{ generatorLabel }}</span>
    </header>

    <p v-if="message" class="ai-confirm__message" data-testid="ai-intent-message">{{ message }}</p>

    <p v-if="previewNotice" class="ai-preview" data-testid="ai-preview-notice">
      ⚠️ {{ previewNotice }}
    </p>

    <div class="ai-confirm__grid">
      <div class="ai-block" data-testid="ai-hard-constraints">
        <h5>硬约束（不可协商）</h5>
        <ul v-if="draft.hard_constraints.length > 0">
          <li v-for="item in draft.hard_constraints" :key="`${item.code}-${item.course_id ?? ''}`">
            <span class="tag tag--ai-hard">{{ item.code }}</span>
            {{ item.raw_text }}
            <span v-if="item.course_name" class="ai-block__hint">
              （{{ item.course_name }} / {{ item.course_id }}）
            </span>
            <span class="ai-block__hint">置信度 {{ item.confidence.toFixed(2) }} · 证据 {{ item.evidence }}</span>
          </li>
        </ul>
        <p v-else class="empty-state" data-testid="ai-no-hard-constraints">
          这次解析没有识别出硬约束。求解时不会有"必须保留"的课程。
        </p>
      </div>

      <div class="ai-block" data-testid="ai-soft-preferences">
        <h5>软偏好（可协商）</h5>
        <ul v-if="draft.soft_preferences.length > 0">
          <li v-for="item in draft.soft_preferences" :key="item.code">
            <span class="tag tag--ai-soft">{{ item.code }}</span>
            {{ item.raw_text }}
            <span class="ai-block__hint">置信度 {{ item.confidence.toFixed(2) }}</span>
          </li>
        </ul>
        <p v-else class="empty-state">这次解析没有识别出软偏好。</p>
      </div>

      <div class="ai-block" data-testid="ai-credit-limit">
        <h5>单学期学分上限</h5>
        <p v-if="draft.credit_limit === null" class="ai-block__unknown" data-testid="ai-credit-unspecified">
          <strong>未指定</strong>：AI 没有从这句话里得到学分上限，
          <strong>页面不会替你猜一个默认值</strong>。请确认保持"未指定"，或填写一个数字。
        </p>
        <p v-else class="ai-block__value">
          解析结果：<strong class="num">{{ draft.credit_limit }}</strong> 学分（可在求解前修改）
        </p>
        <label class="ai-field">
          <span>学分上限（留空表示未指定）</span>
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

      <div class="ai-block" data-testid="ai-locked-courses">
        <h5>锁定课程（必须保留）</h5>
        <ul v-if="draft.locked_course_ids.length > 0">
          <li v-for="courseId in draft.locked_course_ids" :key="courseId">
            <span class="mono">{{ courseId }}</span>
            <button
              type="button"
              class="button button--ghost button--small"
              :data-testid="`ai-unlock-${courseId}`"
              :disabled="disabled"
              @click="emit('toggle-lock', courseId)"
            >
              取消锁定
            </button>
          </li>
        </ul>
        <p v-else class="empty-state" data-testid="ai-no-locked-courses">当前没有锁定课程。</p>

        <div v-if="unlockedCourses.length > 0" class="ai-lock-candidates">
          <span class="ai-block__hint">可锁定（仅限当前方案已有课程）：</span>
          <button
            v-for="course in unlockedCourses"
            :key="course.course_id"
            type="button"
            class="button button--ghost button--small"
            :data-testid="`ai-lock-${course.course_id}`"
            :disabled="disabled"
            @click="emit('toggle-lock', course.course_id)"
          >
            + {{ course.course_name }}（{{ course.course_id }}）
          </button>
        </div>
      </div>

      <div class="ai-block" data-testid="ai-scope">
        <h5>范围</h5>
        <ul>
          <li>学期：<span class="mono">{{ draft.scope.semester || '未指定' }}</span></li>
          <li>目标边界：<span class="mono">{{ draft.scope.horizon }}</span></li>
          <li v-if="draft.scope.raw_text">原话：{{ draft.scope.raw_text }}</li>
        </ul>
      </div>

      <div class="ai-block ai-block--unknown" data-testid="ai-unknowns">
        <h5>未知项（解析不出来的部分）</h5>
        <ul v-if="draft.unknowns.length > 0">
          <li v-for="item in draft.unknowns" :key="item.topic">
            <strong>{{ item.topic }}</strong>：{{ item.detail }}
            <span v-if="item.needs_user_input" class="tag tag--ai-unknown">需要你补充</span>
          </li>
        </ul>
        <p v-else class="empty-state">本次解析没有列出未知项。</p>
      </div>
    </div>

    <p v-if="!canConfirm" class="ai-confirm__blocked" data-testid="ai-cannot-confirm">
      后端标记这次解析<strong>不足以求解</strong>（`can_confirm = false`）：
      请补充说明后重新解析。页面不会在未确认的情况下调用规划器。
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
        确认前<strong>不会</strong>调用规划器；这一步只确认"我理解得对不对"。
      </span>
    </div>
  </section>
</template>
