<script setup lang="ts">
import { computed } from 'vue'
import type { AiCandidatePlan, AiPlanDiff, AiSolveResponse } from '../../api/aiPlanningTypes'
import { RISK_LEVEL_LABEL } from '../../utils/labels'

/**
 * **第二次确认**面板：候选方案 vs 原方案。
 *
 * 硬边界：
 * - 只有后端回答 `adopted` 才允许刷新当前方案（按钮由父组件按状态禁用）；
 * - ⛔ 前端不比较、不排序、不推断"哪个更好"：差异一律来自后端 `diff`；
 * - ⛔ 原方案上下文缺失时如实说明，不用候选回填"原方案"。
 */
const props = defineProps<{
  solve: AiSolveResponse
  /** 当前页面上的原方案（用于对比）；缺失时如实说明。 */
  originalPlan: AiCandidatePlan | null
  originalLabel: string
  previewNotice: string | null
  disabled: boolean
  busy: boolean
}>()

const emit = defineEmits<{
  (event: 'adopt'): void
  (event: 'keep'): void
  (event: 'resolve-again'): void
}>()

const diff = computed<AiPlanDiff | null>(() => props.solve.diff)
const candidate = computed<AiCandidatePlan | null>(() => props.solve.candidate_plan)

const creditDeltaLabel = computed(() => {
  const delta = diff.value?.credit_delta
  if (delta === undefined || delta === null) {
    return '—'
  }
  if (delta === 0) {
    return '总学分不变'
  }
  return delta > 0 ? `总学分 +${delta}` : `总学分 ${delta}`
})

function planCourseCount(plan: AiCandidatePlan | null): number {
  return plan === null ? 0 : plan.selected_classes.length
}
</script>

<template>
  <section class="ai-candidate" data-testid="ai-candidate-compare">
    <header class="ai-candidate__head">
      <h4>第二次确认 · 候选方案对比</h4>
      <span class="tag tag--ai-solve-status" data-testid="ai-solve-status">{{ solve.status }}</span>
    </header>

    <p class="ai-candidate__message" data-testid="ai-solve-message">{{ solve.message }}</p>

    <p v-if="previewNotice" class="ai-preview" data-testid="ai-preview-notice">
      ⚠️ {{ previewNotice }}
    </p>

    <p
      v-if="solve.expires_at"
      class="ai-candidate__expiry"
      data-testid="ai-candidate-expiry"
    >
      候选有效期至 {{ solve.expires_at }}；过期后采用会失败，原方案不变。
    </p>

    <div class="ai-candidate__columns">
      <div class="ai-plan-card" data-testid="ai-original-plan">
        <h5>{{ originalLabel }}</h5>
        <p class="ai-plan-card__count">
          建议教学班 <strong class="num">{{ planCourseCount(originalPlan) }}</strong> 个
        </p>
        <ul v-if="originalPlan && originalPlan.selected_classes.length > 0">
          <li v-for="item in originalPlan.selected_classes" :key="`${item.course_id}-${item.class_id}`">
            <span class="mono">{{ item.course_id }}</span>
            <span class="ai-block__hint">班号 {{ item.class_id }}</span>
          </li>
        </ul>
        <p v-else class="empty-state" data-testid="ai-original-plan-missing">
          当前上下文没有可对比的原方案明细（例如尚未生成个人规划）。
          页面<strong>不会</strong>用候选回填"原方案"。
        </p>
      </div>

      <div class="ai-plan-card ai-plan-card--candidate" data-testid="ai-candidate-plan">
        <h5>候选方案（后端求解结果）</h5>
        <p class="ai-plan-card__count">
          建议教学班 <strong class="num">{{ planCourseCount(candidate) }}</strong> 个 ·
          <strong>{{ creditDeltaLabel }}</strong>
        </p>
        <ul v-if="candidate && candidate.selected_classes.length > 0">
          <li v-for="item in candidate.selected_classes" :key="`${item.course_id}-${item.class_id}`">
            <span class="mono">{{ item.course_id }}</span>
            <span class="ai-block__hint">班号 {{ item.class_id }}</span>
          </li>
        </ul>
        <p v-else class="empty-state">候选方案没有教学班明细。</p>
        <p v-if="candidate?.objective_summary" class="ai-plan-card__summary">
          {{ candidate.objective_summary }}
        </p>
      </div>
    </div>

    <div v-if="diff" class="ai-diff" data-testid="ai-plan-diff">
      <div class="ai-block">
        <h5>新增课程</h5>
        <ul v-if="diff.added.length > 0">
          <li v-for="item in diff.added" :key="`add-${item.course_id}-${item.class_id}`">
            <span class="mono">{{ item.course_id }}</span> {{ item.course_name }} ·
            班号 {{ item.class_id }} · {{ item.credit }} 学分
          </li>
        </ul>
        <p v-else class="empty-state">没有新增课程。</p>
      </div>

      <div class="ai-block">
        <h5>移除课程</h5>
        <ul v-if="diff.removed.length > 0">
          <li v-for="item in diff.removed" :key="`rm-${item.course_id}-${item.class_id}`">
            <span class="mono">{{ item.course_id }}</span> {{ item.course_name }} ·
            班号 {{ item.class_id }} · {{ item.credit }} 学分
          </li>
        </ul>
        <p v-else class="empty-state">没有移除课程。</p>
      </div>

      <div class="ai-block">
        <h5>教学班调整</h5>
        <ul v-if="diff.moved.length > 0">
          <li v-for="item in diff.moved" :key="`mv-${item.course_id}-${item.from_class}-${item.to_class}`">
            <span class="mono">{{ item.course_id }}</span>
            {{ item.from_class ?? '—' }} → {{ item.to_class ?? '—' }}
            <span class="ai-block__hint">{{ item.reason }}</span>
          </li>
        </ul>
        <p v-else class="empty-state">没有教学班调整。</p>
      </div>

      <div class="ai-block" data-testid="ai-hard-constraint-checks">
        <h5>硬约束核对（后端给出的结果）</h5>
        <ul v-if="diff.hard_constraint_checks.length > 0">
          <li
            v-for="check in diff.hard_constraint_checks"
            :key="`${check.code}-${check.course_id ?? ''}`"
            :class="check.satisfied ? 'ai-check--ok' : 'ai-check--fail'"
          >
            <span class="tag" :class="check.satisfied ? 'tag--ai-ok' : 'tag--ai-fail'">
              {{ check.satisfied ? '满足' : '未满足' }}
            </span>
            <span class="mono">{{ check.code }}</span>
            <span v-if="check.course_id" class="mono">{{ check.course_id }}</span>
            <span class="ai-block__hint">{{ check.detail }}</span>
          </li>
        </ul>
        <p v-else class="empty-state">后端没有返回硬约束核对项。</p>
      </div>
    </div>

    <div class="ai-block" data-testid="ai-solve-risks">
      <h5>候选风险</h5>
      <ul v-if="solve.risks.length > 0">
        <li v-for="(risk, index) in solve.risks" :key="`risk-${index}`">
          <span class="tag" :class="`tag--risk-${risk.level}`">
            {{ RISK_LEVEL_LABEL[risk.level as keyof typeof RISK_LEVEL_LABEL] ?? risk.level }}
          </span>
          {{ risk.course_id ? `${risk.course_id}：` : '' }}{{ risk.reason }}
        </li>
      </ul>
      <p v-else class="empty-state">后端没有返回风险项。</p>
    </div>

    <div class="ai-block" data-testid="ai-solve-unresolved">
      <h5>未解决 / 待确认事项</h5>
      <ul v-if="solve.unresolved.length > 0">
        <li v-for="(item, index) in solve.unresolved" :key="`unresolved-${index}`">
          <span class="mono">{{ item.type }}</span> {{ item.message }}
        </li>
      </ul>
      <p v-else class="empty-state">后端没有返回未决事项。</p>
    </div>

    <div class="ai-candidate__actions">
      <button
        type="button"
        class="button"
        data-testid="ai-adopt-candidate"
        :disabled="disabled || busy"
        @click="emit('adopt')"
      >
        {{ busy ? '正在提交…' : '✅ 采用候选方案' }}
      </button>
      <button
        type="button"
        class="button button--ghost"
        data-testid="ai-keep-original"
        :disabled="disabled || busy"
        @click="emit('keep')"
      >
        🛡️ 保留原方案
      </button>
      <button
        type="button"
        class="button button--ghost"
        data-testid="ai-resolve-again"
        :disabled="disabled || busy"
        @click="emit('resolve-again')"
      >
        🔄 重新求解
      </button>
      <span class="ai-candidate__hint">
        只有后端确认"采用成功"才会刷新当前方案；拒绝、过期或失败时<strong>原方案一个字都不改</strong>。
      </span>
    </div>
  </section>
</template>
