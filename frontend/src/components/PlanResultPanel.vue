<script setup lang="ts">
import type { PlanResult } from '../types/contracts'
import {
  PLAN_STATUS_DESCRIPTION,
  PLAN_STATUS_LABEL,
  RISK_LEVEL_LABEL,
  displayOrDash,
} from '../utils/labels'

/**
 * 展示 Planner 模块输出的最终方案 PlanResult。
 *
 * 核心设计边界：
 * - status / selected_classes / changes / risks / objective_summary 原样展示；
 * - ⛔ `unresolved` **不再**在本组件渲染明细：待确认事项统一由「需要你处理」
 *   （`PendingIssuesCenter`）以归一化中文展示，避免重复与机器码外泄；
 *   本组件只给出「还有 N 项，见需要你处理」的指引；
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
            <span class="kpi-label">建议课表教学班</span>
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
          建议课表教学班 (selected_classes)
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
          <span class="tag tag--selected">建议纳入</span>
        </div>
      </div>
      <p v-else class="empty-state">当前建议课表中暂无教学班。</p>
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
        Planner 返回的方案变更记录。具体调整原因以每条 change.reason 为准。
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
      <p v-else class="empty-state">本次 PlanResult 未返回方案变更记录。</p>
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
        前端仅展示 Planner 返回的 risk.level、risk.reason 与关联课程，不补充或推断风险类型。
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
      <p v-else class="empty-state">本次 PlanResult 未返回风险项。</p>
    </section>

    <!-- 4. 未解决事项：⛔ 本组件不再直接渲染 plan_result.unresolved。
         待确认事项统一由「需要你处理」（PendingIssuesCenter）以归一化中文展示，
         本组件只保留方案摘要，避免同一事项在两处重复且泄露机器码。 -->
    <section v-if="planResult.unresolved.length > 0" class="plan-section plan-section--unresolved">
      <div class="plan-section__header">
        <h3 class="plan-section__title text-warning">
          <span class="section-icon">⚠️</span>
          待确认事项
        </h3>
        <span class="plan-section__badge badge-warning">
          {{ planResult.unresolved.length }} 项
        </span>
      </div>

      <p class="empty-state" data-testid="plan-result-unresolved-delegated">
        本方案仍有 {{ planResult.unresolved.length }} 项需要你确认。为便于阅读，
        这些事项已统一放在页面「<strong>需要你处理</strong>」区域，并已翻译为中文说明；
        ⛔ 这里不再重复列出，避免同一事项出现两次。
      </p>
    </section>
  </div>
</template>
