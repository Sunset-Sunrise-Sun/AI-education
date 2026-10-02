<script setup lang="ts">
import type { PlanResult } from '../types/contracts'
import {
  PLAN_STATUS_DESCRIPTION,
  PLAN_STATUS_LABEL,
  RISK_LEVEL_LABEL,
  displayOrDash,
  unresolvedTypeLabel,
  unresolvedTypeTagClass,
} from '../utils/labels'

/**
 * 展示 Planner 模块输出的最终方案 PlanResult。
 *
 * 核心设计边界：
 * - status / selected_classes / changes / risks / unresolved / objective_summary 全部原样展示；
 * - 满足 unresolved 规范：支持 manual_confirmation、missing_data、schedule_unknown 等多种类型，
 *   并提供通用 fallback，严禁所有 unresolved 一律归为“人工确认”；
 * - 强化 changes 调班前后对比与原因阐释；
 * - 明确划分风险等级（高/中/低）。
 */
const props = defineProps<{
  planResult: PlanResult
  courseNameById: Record<string, string>
}>()

function courseLabel(courseId: string): string {
  const name = props.courseNameById[courseId]
  return name ? `${courseId} · ${name}` : courseId
}
</script>

<template>
  <div class="plan-container">
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

        <div class="plan-hero__kpis">
          <div class="kpi-item">
            <span class="kpi-label">已选教学班</span>
            <span class="kpi-val num">{{ planResult.selected_classes.length }}</span>
          </div>
          <div class="kpi-item">
            <span class="kpi-label">方案调整</span>
            <span class="kpi-val num">{{ planResult.changes.length }}</span>
          </div>
          <div class="kpi-item">
            <span class="kpi-label">风险提示</span>
            <span class="kpi-val num">{{ planResult.risks.length }}</span>
          </div>
          <div class="kpi-item" :class="{ 'kpi-item--alert': planResult.unresolved.length > 0 }">
            <span class="kpi-label">未决事项</span>
            <span class="kpi-val num">{{ planResult.unresolved.length }}</span>
          </div>
        </div>
      </div>

      <div v-if="planResult.objective_summary" class="plan-hero__summary">
        <span class="summary-label">求解目标与策略说明：</span>
        <span class="summary-text">{{ planResult.objective_summary }}</span>
      </div>
    </div>

    <!-- 1. 已选教学班 selected_classes -->
    <section class="plan-section">
      <div class="plan-section__header">
        <h3 class="plan-section__title">
          <span class="section-icon">✅</span>
          已选教学班组合 (selected_classes)
        </h3>
        <span class="plan-section__badge">{{ planResult.selected_classes.length }} 个班级</span>
      </div>

      <div v-if="planResult.selected_classes.length > 0" class="selected-grid">
        <div
          v-for="item in planResult.selected_classes"
          :key="`${item.course_id}-${item.class_id}`"
          class="selected-card"
        >
          <div class="selected-card__meta">
            <span class="selected-card__course">{{ courseLabel(item.course_id) }}</span>
            <span class="mono selected-card__class">班号：{{ item.class_id }}</span>
          </div>
          <span class="tag tag--selected">已排入</span>
        </div>
      </div>
      <p v-else class="empty-state">方案中无已排定教学班。</p>
    </section>

    <!-- 2. 方案调整变更 changes -->
    <section class="plan-section">
      <div class="plan-section__header">
        <h3 class="plan-section__title">
          <span class="section-icon">🔄</span>
          教学班调整对比与成因 (changes)
        </h3>
        <span class="plan-section__badge">{{ planResult.changes.length }} 项调整</span>
      </div>

      <p class="section-desc">
        求解器依据冲突消除算法或用户偏好进行的教学班换班记录，直观说明“由哪个班换到哪个班、为什么调整”。
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
            <span class="reason-text">{{ change.reason }}</span>
          </div>
        </article>
      </div>
      <p v-else class="empty-state">方案未发生教学班调整（无需换班）。</p>
    </section>

    <!-- 3. 风险预警 risks -->
    <section class="plan-section">
      <div class="plan-section__header">
        <h3 class="plan-section__title">
          <span class="section-icon">⚡</span>
          方案风险提示 (risks)
        </h3>
        <span class="plan-section__badge">{{ planResult.risks.length }} 项提示</span>
      </div>

      <p class="section-desc">
        由求解器及上游规则直接标记的容量紧俏、选课竞争或学分安排风险，前端不改写风险级别。
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
          <p class="risk-card__reason">{{ risk.reason }}</p>
        </div>
      </div>
      <p v-else class="empty-state">未检测到显著方案风险。</p>
    </section>

    <!-- 4. 未解决事项 unresolved（重点展示） -->
    <section class="plan-section plan-section--unresolved">
      <div class="plan-section__header">
        <h3 class="plan-section__title text-warning">
          <span class="section-icon">⚠️</span>
          待解决与待确认事项 (unresolved)
        </h3>
        <span class="plan-section__badge badge-warning">
          {{ planResult.unresolved.length }} 项需关注
        </span>
      </div>

      <div class="unresolved-alert-box">
        <strong>重要提示：</strong>
        以下事项系统<strong>不会自行做假定或强行下结论</strong>。包含需教务老师人工复核的规则等价判定、缺失排课数据等。任何未解决项都会影响方案的实际落地执行。
      </div>

      <div v-if="planResult.unresolved.length > 0" class="unresolved-list">
        <article
          v-for="(item, index) in planResult.unresolved"
          :key="`${item.type}-${index}`"
          class="unresolved-card"
        >
          <div class="unresolved-card__meta">
            <span class="tag" :class="unresolvedTypeTagClass(item.type)">
              {{ unresolvedTypeLabel(item.type) }}
            </span>
            <span class="mono tag tag--type-raw" title="后端原始类型字段">
              type: {{ item.type }}
            </span>
          </div>
          <p class="unresolved-card__message">{{ item.message }}</p>
        </article>
      </div>
      <p v-else class="empty-state text-success">所有待决事项均已解决，无遗留问题。</p>
    </section>
  </div>
</template>
