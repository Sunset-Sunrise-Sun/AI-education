<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { MakeupTask, PlanResult } from '../types/contracts'
import {
  PLAN_STATUS_DESCRIPTION,
  PLAN_STATUS_LABEL,
  RISK_LEVEL_LABEL,
  displayOrDash,
} from '../utils/labels'
import { studentText, unresolvedTypeHint } from '../utils/displayLanguage'

// 只展示规划事实；核对状态由父页面保存为前端输入状态，不写入响应或 API 请求。
const props = defineProps<{
  planResult: PlanResult
  courseNameById: Record<string, string>
  makeupTasks?: readonly MakeupTask[]
  confirmedKeys?: readonly string[]
}>()

const emit = defineEmits<{
  'update:confirmedKeys': [keys: string[]]
}>()

const names = computed(() => ({
  ...Object.fromEntries((props.makeupTasks ?? []).map(task => [task.course_id, task.course_name])),
  ...props.courseNameById,
}))

function courseLabel(courseId: string): string {
  const name = names.value[courseId]
  return name ? `${name}（${courseId}）` : courseId
}

function courseName(courseId: string | undefined): string {
  return courseId ? (names.value[courseId] ?? courseId) : '课程信息待核对'
}

function confirmationReason(type: string): string {
  if (type === 'manual_confirmation') {
    return '你的目标专业培养方案中包含该课程，系统需要确认该课程是否已经完成。'
  }
  if (type === 'selection_required') {
    return '请选择对应课程或教学班后重新生成方案。'
  }
  if (type === 'missing_data') {
    return '课程信息不完整，请补充后再生成方案。'
  }
  return unresolvedTypeHint(type)
}

function courseIdIn(message: string): string | undefined {
  return Object.keys(names.value).sort((a, b) => b.length - a.length).find(id =>
    message.split(/[^a-zA-Z0-9_-]+/).includes(id) || (Boolean(names.value[id]) && message.includes(names.value[id])),
  )
}

const unresolvedItems = computed(() => {
  const manualTasks = (props.makeupTasks ?? []).filter(task => task.status === 'manual_confirmation')
  const items = (props.planResult?.unresolved ?? []).map(item => {
    const courseId = courseIdIn(item.message ?? '')
    const evidence = (item as { evidence?: unknown }).evidence
    const message = studentText(item.message)
    return {
      key: courseId ? `course:${courseId}` : `${item.type}:${message || item.message}`,
      type: item.type,
      title: courseId ? courseLabel(courseId) : '课程信息待核对',
      courseName: courseName(courseId),
      courseId,
      message,
      evidence: Array.isArray(evidence) ? evidence.filter((v): v is string => typeof v === 'string').map(v => studentText(v)).filter(Boolean) : [],
    }
  }).filter(item => !(
    item.type === 'manual_confirmation'
    && !item.courseId
    && manualTasks.length > 0
  ))
  // 培养任务可能未在未决列表中重复返回；统一放在同一个用户入口。
  for (const task of manualTasks) {
    if (!items.some(item => item.courseId === task.course_id)) {
      items.push({ key: `course:${task.course_id}`, type: task.status, title: courseLabel(task.course_id), courseName: courseName(task.course_id), courseId: task.course_id,
        message: studentText(task.reason), evidence: [studentText(task.source_evidence)].filter(Boolean) })
    }
  }
  return items.filter((item, index) => items.findIndex(other =>
    other.type === item.type && other.title === item.title && other.message === item.message,
  ) === index)
})

const selected = ref<string[]>([])
const localConfirmedKeys = ref<string[]>([])
watch(() => props.planResult, () => {
  selected.value = []
  if (props.confirmedKeys === undefined) localConfirmedKeys.value = []
})
const effectiveConfirmedKeys = computed(() => props.confirmedKeys ?? localConfirmedKeys.value)
const confirmedSet = computed(() => new Set(effectiveConfirmedKeys.value))
const confirmedCount = computed(() => unresolvedItems.value.filter(item => confirmedSet.value.has(item.key)).length)
const remainingCount = computed(() => unresolvedItems.value.length - confirmedCount.value)
function confirmSelection(): void {
  const next = [...new Set([...effectiveConfirmedKeys.value, ...selected.value])]
  if (props.confirmedKeys === undefined) localConfirmedKeys.value = next
  emit('update:confirmedKeys', next)
  selected.value = []
}

</script>

<template>
  <div class="plan-container">
    <div class="plan-story" data-testid="case-a-plan-story">
      <p class="plan-story__lead">这份转专业学习建议综合参考：</p>
      <ul class="plan-story__basis">
        <li>✓ 你的已修课程信息</li>
        <li>✓ 目标专业培养方案</li>
        <li>✓ 你已确认的当前课表</li>
      </ul>
    </div>

    <!-- 方案总体状态与目标概括 Banner -->
    <div
      class="plan-hero"
      :class="`plan-hero--${planResult.status}`"
    >
      <div class="plan-hero__header">
        <div class="plan-hero__status-badge">
          <span class="tag tag--plan" :class="`tag--plan-${planResult.status}`">
            {{ PLAN_STATUS_LABEL[planResult.status] }}
          </span>
          <span class="plan-hero__status-desc">
            {{ PLAN_STATUS_DESCRIPTION[planResult.status] }}
          </span>
        </div>

        <div class="plan-hero__kpis" aria-label="当前规划状态">
          <div class="kpi-item">
            <span class="kpi-label">✓ 推荐课程</span>
            <span class="kpi-val num">{{ planResult.selected_classes.length }} 门</span>
          </div>
          <div class="kpi-item" :class="{ 'kpi-item--alert': remainingCount > 0 }">
            <span class="kpi-label">仍需确认</span>
            <span class="kpi-val num">{{ remainingCount }} 项课程信息</span>
          </div>
        </div>
      </div>

      <div v-if="studentText(planResult.objective_summary)" class="plan-hero__summary">
        <span class="summary-label">方案说明：</span>
        <span class="summary-text">{{ studentText(planResult.objective_summary) }}</span>
      </div>
    </div>

    <!-- 推荐课程与待确认课程共用一个学生任务区。 -->
    <section class="plan-section" data-testid="case-a-confirmations">
      <div class="plan-section__header">
        <h3 class="plan-section__title">
          <span class="section-icon">✅</span>
          课程建议与确认
        </h3>
        <span class="plan-section__badge">{{ planResult.selected_classes.length }} 门推荐 · {{ remainingCount }} 项待确认</span>
      </div>
      <p class="section-desc">推荐课程和需要你确认的课程统一列在这里。确认不会自动认定课程，也不会自动安排补修。</p>

      <div v-if="planResult.selected_classes.length || unresolvedItems.length" class="course-advice-grid" data-testid="case-a-course-advice">
        <article
          v-for="item in planResult.selected_classes"
          :key="`${item.course_id}-${item.class_id}`"
          class="selected-card course-advice-card"
        >
          <div class="selected-card__meta">
            <span class="selected-card__course">{{ courseLabel(item.course_id) }}</span>
            <span class="mono selected-card__class">班号：{{ item.class_id }}</span>
            <span class="selected-card__reason"><strong>推荐说明：</strong>该课程已进入本次推荐方案，请结合培养要求和当前课表核对教学班安排。</span>
          </div>
          <span class="tag tag--selected">推荐课程</span>
        </article>

        <article
          v-for="item in unresolvedItems"
          :key="item.key"
          class="unresolved-row course-advice-card course-advice-card--confirmation"
          data-testid="case-a-unresolved-row"
        >
          <div class="unresolved-row__main">
            <strong class="unresolved-row__name" data-testid="case-a-unresolved-name">{{ item.courseName }}</strong>
            <span v-if="item.courseId" class="unresolved-row__course-id">课程编号：{{ item.courseId }}</span>
            <span v-if="confirmedSet.has(item.key)" class="unresolved-row__status" data-testid="case-a-unresolved-status">已确认</span>
          </div>
          <div class="unresolved-row__reason">
            <strong>为什么需要确认：</strong>
            <p>{{ confirmationReason(item.type) }}</p>
          </div>
          <label class="confirmation-label">
            <input v-model="selected" type="checkbox" :value="item.key" :disabled="confirmedSet.has(item.key)" :aria-label="`核对${item.title}`" data-testid="case-a-confirmation-checkbox">
            <span>{{ confirmedSet.has(item.key) ? '已纳入本次核对记录' : '纳入后续规划' }}</span>
          </label>
          <details class="unresolved-row__details">
            <summary data-testid="case-a-unresolved-details-toggle">查看详情</summary>
            <p class="unresolved-row__detail">{{ item.message || unresolvedTypeHint(item.type) }}</p>
            <template v-if="item.evidence.length">
              <p>系统判断依据</p>
              <ul><li v-for="(text, i) in item.evidence" :key="i">{{ text }}</li></ul>
            </template>
          </details>
        </article>
      </div>
      <p v-else class="empty-state">本次没有待确认事项，也没有推荐课程。</p>

      <div v-if="unresolvedItems.length" class="confirmation-footer">
        <span role="status" aria-live="polite" data-testid="case-a-confirmation-count">已选择 {{ selected.length }} 项 · 已确认 {{ confirmedCount }} 项</span>
        <button class="button" type="button" :disabled="!selected.length" data-testid="case-a-confirm-selection" @click="confirmSelection">确认选择</button>
      </div>
      <div v-if="confirmedCount" class="confirmation-feedback" data-testid="case-a-confirmation-feedback">
        <strong>已确认 {{ confirmedCount }} 项</strong>
        <span>你的核对结果已保留，重新生成方案后仍会继续显示；最终课程认定仍以学校规定为准。</span>
      </div>
    </section>

    <!-- 2. 方案调整变更 changes -->
    <section class="plan-section">
      <div class="plan-section__header">
        <h3 class="plan-section__title">
          <span class="section-icon">🔄</span>
          教学班调整对比与成因
        </h3>
        <span class="plan-section__badge">{{ planResult.changes.length }} 项调整</span>
      </div>

      <p class="section-desc">
        以下是建议的教学班调整及原因，请结合自己的安排核对。
      </p>

      <div v-if="planResult.changes.length > 0" class="change-list">
        <article
          v-for="change in planResult.changes"
          :key="`${change.course_id}-${change.to_class}`"
          class="change-card"
        >
          <div class="change-card__head">
            <span class="change-card__course-title">
              {{ courseLabel(change.course_id) }}
            </span>
          </div>

          <div class="change-card__flow">
            <div class="flow-node flow-node--from">
              <span class="flow-node__label">原班级</span>
              <span class="mono flow-node__val">{{ displayOrDash(change.from_class) }}</span>
            </div>

            <div class="flow-arrow" aria-hidden="true">
              <span class="arrow-line"></span>
              <span class="arrow-head">➜</span>
            </div>

            <div class="flow-node flow-node--to">
              <span class="flow-node__label">调整为</span>
              <span class="mono flow-node__val">{{ displayOrDash(change.to_class) }}</span>
            </div>
          </div>

          <div class="change-card__reason">
            <span class="reason-badge">调整原因</span>
            <span class="reason-text">{{ studentText(change.reason, '请核对调整前后的教学班安排。') }}</span>
          </div>
        </article>
      </div>
      <p v-else class="empty-state">本次未返回调整建议。</p>
    </section>

    <!-- 3. 风险预警 risks -->
    <section class="plan-section">
      <div class="plan-section__header">
        <h3 class="plan-section__title">
          <span class="section-icon">⚡</span>
          方案风险提示
        </h3>
        <span class="plan-section__badge">{{ planResult.risks.length }} 项提示</span>
      </div>

      <p class="section-desc">
        以下事项可能影响课程安排，请在选课前核实。
      </p>

      <div v-if="planResult.risks.length > 0" class="risk-grid">
        <div
          v-for="(risk, index) in planResult.risks"
          :key="`${risk.course_id ?? 'global'}-${index}`"
          class="risk-card"
          :class="`risk-card--${risk.level}`"
        >
          <div class="risk-card__header">
            <span class="tag" :class="`tag--risk-${risk.level}`">
              {{ RISK_LEVEL_LABEL[risk.level] }}
            </span>
            <span class="risk-card__target">
              {{ risk.course_id ? courseLabel(risk.course_id) : '全局/整体性风险' }}
            </span>
          </div>
          <p class="risk-card__reason">{{ studentText(risk.reason, '相关课程安排需要进一步核实。') }}</p>
        </div>
      </div>
      <p v-else class="empty-state">本次未返回风险提示。</p>
    </section>

  </div>
</template>

<style scoped>
.confirmation-label { display: inline-flex; align-items: center; gap: 10px; cursor: pointer; color: #1e40af; font-weight: 700; }
.confirmation-label input { width: 18px; height: 18px; accent-color: #3276df; }
.confirmation-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-top: 16px; }
.confirmation-footer button:disabled { opacity: .5; cursor: default; }
.confirmation-feedback { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border-radius: 10px; background: #ecfdf5; color: #166534; }
.confirmation-feedback span { font-size: 13px; }
@media (max-width: 760px) {
  .course-advice-grid { grid-template-columns: 1fr; }
}
</style>
