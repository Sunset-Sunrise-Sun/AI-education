<script setup lang="ts">
import type { PlanResult } from '../types/contracts'
import {
  PLAN_STATUS_LABEL,
  RISK_LEVEL_LABEL,
  displayOrDash,
  unresolvedTypeLabel,
} from '../utils/labels'

/**
 * 展示 Planner 模块本应输出的 PlanResult。
 *
 * 再次强调边界：
 * - status / selected_classes / changes / risks / unresolved / objective_summary 全部**原样显示**；
 * - 前端不重新计算风险等级、不修改方案、不判断哪些课程"更好"；
 * - `courseNameById` 只用于把 course_id 显示得更好读（changes 里只有课程号），
 *   不做任何比对或等价判定。
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
  <div class="plan">
    <!-- 方案总体状态 -->
    <div class="plan__status">
      <!-- 动态 class 必须用 :class 绑定；拼在 class 属性里的 {{ }} 不会被 Vue 解析，
           会原样输出成 class="tag tag--plan-{{ ... }}"，样式因此完全失效。 -->
      <span class="tag" :class="`tag--plan-${planResult.status}`">
        {{ PLAN_STATUS_LABEL[planResult.status] }}
      </span>
      <p class="plan__summary">{{ displayOrDash(planResult.objective_summary) }}</p>
    </div>

    <!-- selected_classes -->
    <section class="plan__block">
      <h3 class="plan__block-title">
        已选教学班（selected_classes）
        <span class="plan__count">{{ planResult.selected_classes.length }} 条</span>
      </h3>
      <ul class="plan__list">
        <li v-for="item in planResult.selected_classes" :key="`${item.course_id}-${item.class_id}`">
          <span class="mono">{{ item.class_id }}</span>
          <span class="plan__list-note">{{ courseLabel(item.course_id) }}</span>
        </li>
        <li v-if="planResult.selected_classes.length === 0" class="empty">没有已选教学班。</li>
      </ul>
    </section>

    <!-- changes：让观众看懂"原来是什么班 -> 改成了什么班 -> 为什么" -->
    <section class="plan__block">
      <h3 class="plan__block-title">
        方案调整（changes）
        <span class="plan__count">{{ planResult.changes.length }} 条</span>
      </h3>

      <article
        v-for="change in planResult.changes"
        :key="`${change.course_id}-${change.to_class}`"
        class="change"
      >
        <p class="change__course">{{ courseLabel(change.course_id) }}</p>

        <div class="change__flow">
          <div class="change__node change__node--from">
            <span class="change__label">原教学班</span>
            <span class="mono">{{ displayOrDash(change.from_class) }}</span>
          </div>

          <div class="change__arrow" aria-hidden="true">↓</div>

          <div class="change__node change__node--to">
            <span class="change__label">修改为</span>
            <span class="mono">{{ displayOrDash(change.to_class) }}</span>
          </div>
        </div>

        <p class="change__reason">
          <span class="change__label">原因</span>
          {{ change.reason }}
        </p>
      </article>

      <p v-if="planResult.changes.length === 0" class="empty">方案未发生教学班调整。</p>
    </section>

    <!-- risks：等级直接来自后端，前端不重新评定 -->
    <section class="plan__block">
      <h3 class="plan__block-title">
        风险提示（risks）
        <span class="plan__count">{{ planResult.risks.length }} 条</span>
      </h3>
      <ul class="risk-list">
        <li
          v-for="(risk, index) in planResult.risks"
          :key="`${risk.course_id ?? 'global'}-${index}`"
          class="risk"
        >
          <span class="tag" :class="`tag--risk-${risk.level}`">
            风险等级：{{ RISK_LEVEL_LABEL[risk.level] }}（{{ risk.level }}）
          </span>
          <span class="risk__course">
            {{ risk.course_id ? courseLabel(risk.course_id) : '整体性风险' }}
          </span>
          <p class="risk__reason">{{ risk.reason }}</p>
        </li>
        <li v-if="planResult.risks.length === 0" class="empty">没有风险提示。</li>
      </ul>
    </section>

    <!-- unresolved：必须显眼，不能隐藏。
         `type` 在公共 Schema 中是**开放字符串**（没有 enum 约束），当前演示数据里同时存在
         manual_confirmation 与 missing_data。因此这里只按已知取值翻译标签，
         未知取值原样显示，**不做任何业务归类**。 -->
    <section class="plan__block plan__block--unresolved">
      <h3 class="plan__block-title">
        ⚠️ 未解决事项（unresolved）
        <span class="plan__count">{{ planResult.unresolved.length }} 条</span>
      </h3>
      <p class="plan__block-note">
        以下事项系统<strong>不会自行下结论</strong>：可能是需要人工确认的规则问题，
        也可能是上游数据缺失。它们都会影响上面的方案是否成立。
      </p>
      <ul class="unresolved-list">
        <li
          v-for="(item, index) in planResult.unresolved"
          :key="`${item.type}-${index}`"
          class="unresolved"
        >
          <span class="tag tag--unresolved">{{ unresolvedTypeLabel(item.type) }}</span>
          <span class="tag tag--plain mono">{{ item.type }}</span>
          <p class="unresolved__message">{{ item.message }}</p>
        </li>
        <li v-if="planResult.unresolved.length === 0" class="empty">没有未解决事项。</li>
      </ul>
    </section>
  </div>
</template>
