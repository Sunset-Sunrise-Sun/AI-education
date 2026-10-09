<script setup lang="ts">
import { computed } from 'vue'
import type {
  AiDataSource,
  AiGeneratorKind,
  AiPlanDiff,
  AiSolveResponse,
} from '../../api/aiPlanningContract'
import { dataSourceLabel, generatorKindLabel } from '../../composables/useAiPlanning'
import type { PlanResult } from '../../types/contracts'

/**
 * **第二次确认**面板：候选方案 vs 原方案。
 *
 * 硬边界（与后端 HANDOFF 一致）：
 * - 只有 `status = candidate_ready` 才渲染候选（别的状态由父组件显示"未生成候选"）；
 * - `diff` 由后端**确定性**计算；前端⛔ 不自己比较、不排序、不推断"哪个更好"；
 * - ⛔ 原方案上下文缺失时如实说明，不用候选回填"原方案"；
 * - `credit_delta = null`（或 `credit_unknown_course_ids` 非空）时必须说"学分未知"；
 * - 两个按钮：**采用候选** / **保留原案**（后者同样由后端确认）。
 */
const props = defineProps<{
  solve: AiSolveResponse
  /** 当前页面上的原方案（用于对比）；缺失时如实说明。 */
  originalPlan: PlanResult | null
  originalLabel: string
  generatorKind: AiGeneratorKind | null
  dataSource: AiDataSource | null
  blockedReasonLabel: string | null
  previewNotice: string | null
  disabled: boolean
  busy: boolean
}>()

const emit = defineEmits<{
  (event: 'adopt'): void
  (event: 'keep'): void
  (event: 'resolve-again'): void
  (event: 'back-to-draft'): void
}>()

const diff = computed<AiPlanDiff | null>(() => props.solve.diff)
const candidate = computed<PlanResult | null>(() => props.solve.candidate_plan)

const creditDeltaLabel = computed(() => {
  const delta = diff.value?.credit_delta
  if (delta === null || delta === undefined) {
    return '学分未知'
  }
  if (delta === 0) {
    return '总学分不变'
  }
  return delta > 0 ? `总学分 +${delta}` : `总学分 ${delta}`
})

const creditUnknown = computed(() => (diff.value?.credit_unknown_course_ids.length ?? 0) > 0)

function formatEntry(entry: { course_id: string; class_id?: string }): string {
  return `${entry.course_id}（班号 ${entry.class_id ?? '未知'}）`
}

/**
 * 换班行：后端 `diff.replaced[]` 的键是 `from_class` / `to_class`（⛔ 不是 `class_id`）。
 *
 * ⚠️ 同一次换班在后端的语义里**同时**出现在 `added` / `removed`（按教学班键看），
 * 因此这里必须优先展示 `replaced`，并在提示里说明它不是"又新增又移除"。
 */
function formatReplaced(entry: { course_id: string; from_class?: string; to_class?: string }): string {
  return `${entry.course_id}（班号 ${entry.from_class ?? '未知'} → ${entry.to_class ?? '未知'}）`
}

function entryKey(prefix: string, entry: { course_id: string; class_id?: string }): string {
  return `${prefix}-${entry.course_id}-${entry.class_id ?? 'unknown'}`
}

function replacedKey(entry: { course_id: string; from_class?: string; to_class?: string }): string {
  return `rp-${entry.course_id}-${entry.from_class ?? 'unknown'}-${entry.to_class ?? 'unknown'}`
}
</script>

<template>
  <section class="ai-candidate" data-testid="ai-candidate-compare">
    <header class="ai-candidate__head">
      <h4>第二次确认 · 候选方案对比</h4>
      <span class="tag tag--ai-solve-status" data-testid="ai-solve-status">
        {{ solve.status }}
      </span>
    </header>

    <p class="ai-candidate__message" data-testid="ai-solve-message">{{ solve.message }}</p>

    <p class="ai-block__hint" data-testid="ai-candidate-meta">
      候选类型：<code class="mono">{{ solve.plan_kind }}</code>
      <span class="ai-drawer__sep" aria-hidden="true">·</span>
      生成方式：{{ generatorKindLabel(generatorKind) }}
      <span class="ai-drawer__sep" aria-hidden="true">·</span>
      数据来源：{{ dataSourceLabel(dataSource) }}
    </p>

    <p v-if="previewNotice" class="ai-preview" data-testid="ai-preview-notice">
      ⚠️ {{ previewNotice }}
    </p>

    <div class="ai-candidate__columns">
      <div class="ai-plan-card" data-testid="ai-original-plan">
        <h5>{{ originalLabel }}</h5>
        <p class="ai-plan-card__count">
          建议教学班
          <strong class="num">{{ originalPlan?.selected_classes.length ?? 0 }}</strong> 个
        </p>
        <ul v-if="originalPlan && originalPlan.selected_classes.length > 0">
          <li
            v-for="item in originalPlan.selected_classes"
            :key="`${item.course_id}-${item.class_id}`"
          >
            <span class="mono">{{ item.course_id }}</span>
            <span class="ai-block__hint">班号 {{ item.class_id }}</span>
          </li>
        </ul>
        <p v-else class="empty-state" data-testid="ai-original-plan-missing">
          当前上下文没有可对比的原方案明细。页面<strong>不会</strong>用候选回填"原方案"。
        </p>
      </div>

      <div class="ai-plan-card ai-plan-card--candidate" data-testid="ai-candidate-plan">
        <h5>候选方案（后端 Planner 产生）</h5>
        <p class="ai-plan-card__count">
          建议教学班 <strong class="num">{{ candidate?.selected_classes.length ?? 0 }}</strong> 个 ·
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
        <h5>新增（added）</h5>
        <ul v-if="diff.added.length > 0">
          <li v-for="entry in diff.added" :key="entryKey('add', entry)">
            {{ formatEntry(entry) }}
          </li>
        </ul>
        <p v-else class="empty-state">没有新增。</p>
      </div>

      <div class="ai-block">
        <h5>移除（removed）</h5>
        <ul v-if="diff.removed.length > 0">
          <li v-for="entry in diff.removed" :key="entryKey('rm', entry)">
            {{ formatEntry(entry) }}
          </li>
        </ul>
        <p v-else class="empty-state">没有移除。</p>
      </div>

      <div class="ai-block">
        <h5>替换（replaced）</h5>
        <ul v-if="diff.replaced.length > 0">
          <li v-for="entry in diff.replaced" :key="replacedKey(entry)">
            {{ formatReplaced(entry) }}
          </li>
        </ul>
        <p v-else class="empty-state">没有替换。</p>
        <p v-if="diff.replaced.length > 0" class="ai-block__hint" data-testid="ai-replaced-note">
          同一次换班在后端的班次集合语义里也会出现在"新增/移除"，
          请以本段"替换"为准，⛔ 不要理解成同一门课既新增又移除。
        </p>
      </div>

      <div class="ai-block">
        <h5>保持（kept）</h5>
        <ul v-if="diff.kept.length > 0">
          <li v-for="entry in diff.kept" :key="entryKey('kp', entry)">
            {{ formatEntry(entry) }}
          </li>
        </ul>
        <p v-else class="empty-state">没有保持项。</p>
      </div>

      <div class="ai-block" data-testid="ai-credit-diff">
        <h5>学分变化</h5>
        <p>
          原方案：<strong class="num">{{ diff.base_credit ?? '未知' }}</strong> ·
          候选：<strong class="num">{{ diff.candidate_credit ?? '未知' }}</strong> ·
          <strong data-testid="ai-credit-delta">{{ creditDeltaLabel }}</strong>
        </p>
        <p v-if="creditUnknown" class="ai-block__unknown" data-testid="ai-credit-unknown">
          有课程的学分未知：{{ diff.credit_unknown_course_ids.join('、') }}，
          因此"总学分"不能作为确定结论。
        </p>
      </div>
    </div>

    <p v-if="blockedReasonLabel" class="ai-block__unknown" data-testid="ai-blocked-reason">
      阻塞原因：<code class="mono">{{ solve.blocked_reason }}</code> —— {{ blockedReasonLabel }}
    </p>

    <div class="ai-block" data-testid="ai-solve-risks">
      <h5>候选风险</h5>
      <ul v-if="solve.risks.length > 0">
        <li v-for="(risk, index) in solve.risks" :key="`risk-${index}`">{{ risk }}</li>
      </ul>
      <p v-else class="empty-state">后端没有返回风险项。</p>
    </div>

    <div class="ai-block" data-testid="ai-solve-unresolved">
      <h5>未解决 / 待确认事项</h5>
      <ul v-if="solve.unresolved.length > 0">
        <li v-for="(item, index) in solve.unresolved" :key="`unresolved-${index}`">{{ item }}</li>
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
      <button
        type="button"
        class="button button--ghost"
        data-testid="ai-back-to-draft"
        :disabled="disabled || busy"
        @click="emit('back-to-draft')"
      >
        ✏️ 回到意图草稿
      </button>
      <span class="ai-candidate__hint">
        只有后端确认<strong>采用成功</strong>才会刷新当前方案；拒绝、过期或失败时
        <strong>原方案一个字都不改</strong>。
      </span>
    </div>
  </section>
</template>
