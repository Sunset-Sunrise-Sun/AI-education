<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ExplanationApiError,
  fetchPlanExplanation,
  type ExplanationItem,
  type ExplanationPayload,
  type ExplanationRequest,
} from '../api/explanation'
import type { CourseOffering, MakeupTask, PlanResult } from '../types/contracts'
import {
  EVIDENCE_KIND_HINT,
  EVIDENCE_KIND_LABEL,
  EVIDENCE_STRENGTH_LABEL,
  ITEM_KIND_LABEL,
  evidenceSourceLabel,
  evidenceValueLabel,
  generatorKindLabel,
  generatorKindTagClass,
} from '../utils/explanationLabels'

/**
 * 「查看依据 / 为什么这样安排」解释面板。
 *
 * 核心边界（与任务书一致）：
 * - 面板**只展示**后端解释：不生成解释文本、不推断规划原因、不改写任何结论；
 * - 未启用 / 请求失败 / 无数据 / 不支持解释时都有清楚反馈，⛔ 不显示任何伪造内容；
 * - 生成方式如实标注：规则模板不会被说成 AI 模型；
 * - 展示 `plan_result_digest`，让观众能核对"解释的是同一份方案"。
 */
const props = defineProps<{
  /** 被解释的方案（必需）。 */
  planResult: PlanResult
  /** 解释上下文：Curriculum 已输出的补修任务。 */
  makeupTasks?: MakeupTask[]
  /** 解释上下文：Course Data 已输出的教学班。 */
  courseOfferings?: CourseOffering[]
  /** 是否启用解释接口。 */
  enabled?: boolean
  /** 只显示某个课程的条目（点某一行时聚焦）。 */
  focusCourseId?: string | null
  /** 当前规划结果的来源（Mock / Real），用于明确解释对象。 */
  planResultSource?: 'mock' | 'real'
}>()

const emit = defineEmits<{ (event: 'close'): void }>()

const loading = ref(false)
const payload = ref<ExplanationPayload | null>(null)
const errorMessage = ref('')
const errorKind = ref<string | null>(null)

const isEnabled = computed(() => props.enabled !== false)

function buildRequest(): ExplanationRequest {
  return {
    plan_result: props.planResult,
    makeup_tasks: props.makeupTasks ?? [],
    course_offerings: props.courseOfferings ?? [],
  }
}

async function load(): Promise<void> {
  if (!isEnabled.value) {
    payload.value = null
    errorKind.value = 'disabled'
    errorMessage.value =
      '解释功能当前未启用（VITE_EXPLANATION_API_ENABLED 未开启）。页面不会自行生成解释文本。'
    return
  }

  loading.value = true
  errorMessage.value = ''
  errorKind.value = null

  try {
    payload.value = await fetchPlanExplanation(buildRequest())
  } catch (error) {
    payload.value = null
    if (error instanceof ExplanationApiError) {
      errorKind.value = error.kind
      errorMessage.value = error.message
    } else if (error instanceof Error) {
      errorKind.value = 'unexpected'
      errorMessage.value = '解释请求发生未知错误，已停止渲染（不会显示伪造解释）。'
    } else {
      errorKind.value = 'unexpected'
      errorMessage.value = '解释请求发生未知错误。'
    }
  } finally {
    loading.value = false
  }
}

/** 只按已经拿到的数据做**纯展示**筛选，不改变任何结论。 */
const visibleItems = computed<ExplanationItem[]>(() => {
  const items = payload.value?.items ?? []
  if (!props.focusCourseId) {
    return items
  }
  return items.filter((item) => item.target_course_id === props.focusCourseId)
})

const focusedCourseLabel = computed(() => props.focusCourseId ?? '')

watch(
  () => [props.planResult, props.focusCourseId, props.enabled] as const,
  () => {
    void load()
  },
  { immediate: true, deep: false },
)

function retry(): void {
  void load()
}
</script>

<template>
  <section class="explain-panel" data-testid="explanation-panel">
    <header class="explain-panel__header">
      <div class="explain-panel__title">
        <h3>查看依据 · 为什么这样安排</h3>
        <p class="explain-panel__subtitle">
          以下解释由后端**只读**生成：它只转述已存在的结构化字段与来源，
          <strong>不改变</strong>任何补修判定、教学班选择或规划结果。
        </p>
      </div>
      <div class="explain-panel__actions">
        <button type="button" class="button button--ghost" data-testid="explanation-retry" @click="retry">
          🔄 重新获取解释
        </button>
        <button type="button" class="button button--ghost" data-testid="explanation-close" @click="emit('close')">
          ✕ 收起
        </button>
      </div>
    </header>

    <p v-if="focusCourseId" class="explain-panel__focus" data-testid="explanation-focus">
      当前聚焦课程：<code class="mono">{{ focusedCourseLabel }}</code>
      （其余条目仍可通过收起后重新打开查看）
    </p>

    <p v-if="loading" class="state state--loading" data-testid="explanation-loading">
      正在向解释接口请求依据…
    </p>

    <div v-else-if="errorMessage" class="error-box" data-testid="explanation-error">
      <p class="state state--error">无法获取解释</p>
      <p class="state__detail" data-testid="explanation-error-detail">{{ errorMessage }}</p>
      <p v-if="errorKind" class="state__hint">
        失败类型：<code class="mono" data-testid="explanation-error-kind">{{ errorKind }}</code>
        —— 页面不会用模板内容顶替，也不会显示任何未经后端返回的解释。
      </p>
    </div>

    <template v-else-if="payload">
      <div class="explain-meta">
        <span class="explain-meta__item">
          生成方式：
          <span class="tag" :class="generatorKindTagClass(payload.generation.generator_kind)" data-testid="explanation-generator">
            {{ generatorKindLabel(payload.generation.generator_kind) }}
          </span>
        </span>
        <span class="explain-meta__item">
          被解释方案来源：<strong>{{ planResultSource === 'real' ? 'Real' : 'Mock' }}</strong>
        </span>
        <span class="explain-meta__item">
          方案指纹：<code class="mono" data-testid="explanation-plan-digest">{{ payload.plan_result_digest.slice(0, 12) }}…</code>
        </span>
        <span class="explain-meta__item">
          解释条目：<strong>{{ payload.items.length }}</strong>
        </span>
      </div>

      <p class="explain-disclaimer" data-testid="explanation-disclaimer">
        {{ payload.generation.disclaimer }}
      </p>
      <p
        v-if="payload.generation.fallback_reason"
        class="explain-fallback"
        data-testid="explanation-fallback-reason"
      >
        模型未被采用的原因：{{ payload.generation.fallback_reason }}
      </p>

      <div class="explain-sources" data-testid="explanation-sources">
        <span class="explain-sources__item">
          补修任务上下文：<strong>{{ payload.source_summary.makeup_task_count }}</strong> 条
        </span>
        <span class="explain-sources__item">
          教学班上下文：<strong>{{ payload.source_summary.course_offering_count }}</strong> 个
        </span>
        <span class="explain-sources__item">
          含 Mock 标记：
          <strong data-testid="explanation-contains-mock">
            {{ payload.source_summary.contains_mock_marker ? '是' : '否' }}
          </strong>
        </span>
        <span class="explain-sources__item">
          含 Real 教学班：
          <strong>{{ payload.source_summary.contains_real_offering ? '是' : '否' }}</strong>
        </span>
      </div>

      <ul v-if="payload.source_summary.notes.length > 0" class="explain-notes" data-testid="explanation-source-notes">
        <li v-for="(note, index) in payload.source_summary.notes" :key="index">{{ note }}</li>
      </ul>

      <div v-if="payload.warnings.length > 0" class="explain-warnings" data-testid="explanation-warnings">
        <strong>数据一致性提示：</strong>
        <ul>
          <li v-for="(warning, index) in payload.warnings" :key="index">{{ warning }}</li>
        </ul>
      </div>

      <p v-if="visibleItems.length === 0" class="empty-state" data-testid="explanation-empty">
        <template v-if="focusCourseId">
          该课程在当前方案中没有可解释的条目（方案里可能没有与它相关的选中教学班、调班、风险或未决事项）。
          这<strong>不代表</strong>该课程不需要补修。
        </template>
        <template v-else>
          本次解释没有返回任何条目（例如方案各列表均为空）。这只表示没有对应条目，不构成任何排课结论。
        </template>
      </p>

      <ul v-else class="explain-list">
        <li
          v-for="item in visibleItems"
          :key="item.item_id"
          class="explain-item"
          :data-testid="`explanation-item-${item.item_id}`"
        >
          <div class="explain-item__head">
            <span class="tag tag--explain-kind">{{ ITEM_KIND_LABEL[item.kind] ?? item.kind }}</span>
            <span class="explain-item__title">{{ item.title }}</span>
            <span class="tag" :class="generatorKindTagClass(item.generation.generator_kind)">
              {{ generatorKindLabel(item.generation.generator_kind) }}
            </span>
          </div>

          <p class="explain-item__answer" data-testid="explanation-answer">{{ item.answer }}</p>

          <div class="explain-item__grid">
            <div class="explain-block" data-testid="explanation-strong-evidence">
              <h4 class="explain-block__title">直接依据（强证据）</h4>
              <ul v-if="item.strong_evidence.length > 0" class="evidence-list">
                <li v-for="(evidence, index) in item.strong_evidence" :key="index" class="evidence-row">
                  <span class="tag tag--evidence" :class="`tag--evidence-${evidence.kind}`">
                    {{ EVIDENCE_KIND_LABEL[evidence.kind] ?? evidence.kind }}
                  </span>
                  <span class="evidence-row__source mono">
                    {{ evidenceSourceLabel(evidence.source_object, evidence.source_field) }}
                  </span>
                  <span class="evidence-row__value">{{ evidenceValueLabel(evidence.kind, evidence.raw_value) }}</span>
                  <span class="evidence-row__note">{{ evidence.note }}</span>
                  <span class="evidence-row__hint">{{ EVIDENCE_KIND_HINT[evidence.kind] ?? '' }}</span>
                </li>
              </ul>
              <p v-else class="empty-state">本条解释没有直接依据字段。</p>
            </div>

            <div class="explain-block" data-testid="explanation-premise-evidence">
              <h4 class="explain-block__title">前提与上下文</h4>
              <ul v-if="item.premise_evidence.length > 0" class="evidence-list">
                <li v-for="(evidence, index) in item.premise_evidence" :key="index" class="evidence-row">
                  <span class="tag tag--evidence" :class="`tag--evidence-${evidence.kind}`">
                    {{ EVIDENCE_KIND_LABEL[evidence.kind] ?? evidence.kind }}
                  </span>
                  <span class="evidence-row__source mono">
                    {{ evidenceSourceLabel(evidence.source_object, evidence.source_field) }}
                  </span>
                  <span class="evidence-row__value">{{ evidenceValueLabel(evidence.kind, evidence.raw_value) }}</span>
                  <span class="evidence-row__strength">
                    强度：{{ EVIDENCE_STRENGTH_LABEL[evidence.strength] ?? evidence.strength }}
                  </span>
                </li>
              </ul>
              <p v-else class="empty-state">本条解释没有额外前提。</p>
            </div>

            <div
              class="explain-block explain-block--confirm"
              data-testid="explanation-confirmations"
            >
              <h4 class="explain-block__title">仍需人工确认</h4>
              <ul v-if="item.requires_human_confirmation.length > 0" class="confirm-list">
                <li
                  v-for="(requirement, index) in item.requires_human_confirmation"
                  :key="index"
                  class="confirm-row"
                >
                  {{ requirement.reason }}
                </li>
              </ul>
              <p v-else class="empty-state">本条解释没有额外的待确认事项。</p>
            </div>
          </div>
        </li>
      </ul>

      <p class="explain-footnote">
        解释只负责说明，不代替学校正式规则、教务审批或人工确认。
        判定状态与方案本身请以对应模块输出与教务系统为准。
      </p>
    </template>
    <p v-else class="empty-state" data-testid="explanation-empty-before-load">
      尚未获取解释。<button type="button" class="button button--ghost" @click="retry">立即获取</button>
    </p>
  </section>
</template>
