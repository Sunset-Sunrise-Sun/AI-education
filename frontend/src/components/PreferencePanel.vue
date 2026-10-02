<script setup lang="ts">
import type { Preference } from '../types/contracts'
import { displayOrDash, formatSections, formatWeekday } from '../utils/labels'

/**
 * 展示用户自然语言偏好经由 Agent 解析后生成的结构化 Preference。
 *
 * 核心设计边界：
 * - 原样呈现学分上限、跨校区偏好、优先课程、回避时段与备注；
 * - 前端不重新解析偏好，也不做优化调整。
 */
defineProps<{
  preference: Preference
  courseNameById?: Record<string, string>
}>()
</script>

<template>
  <div class="pref-grid">
    <!-- 学分上限 -->
    <div class="pref-card">
      <div class="pref-card__header">
        <span class="pref-card__icon">🎯</span>
        <h4 class="pref-card__title">学期学分上限 (max_credit)</h4>
      </div>
      <div class="pref-card__body">
        <span class="pref-stat num">
          {{ preference.max_credit !== null && preference.max_credit !== undefined ? `${preference.max_credit} 学分` : '未设定' }}
        </span>
        <p class="pref-card__hint">推荐单学期总修读学分负荷控制范围</p>
      </div>
    </div>

    <!-- 跨校区限制 -->
    <div class="pref-card">
      <div class="pref-card__header">
        <span class="pref-card__icon">🏫</span>
        <h4 class="pref-card__title">跨校区偏好 (avoid_cross_campus)</h4>
      </div>
      <div class="pref-card__body">
        <span
          class="tag tag--large"
          :class="preference.avoid_cross_campus ? 'tag--cross-avoid' : 'tag--cross-allow'"
        >
          {{ preference.avoid_cross_campus ? '避免跨校区' : '允许跨校区选课' }}
        </span>
        <p class="pref-card__hint">
          {{ preference.avoid_cross_campus ? '求解器将优先过滤产生跨校区通勤的教学班' : '允许调度不同校区的可用教学班' }}
        </p>
      </div>
    </div>

    <!-- 优先修读课程 -->
    <div class="pref-card">
      <div class="pref-card__header">
        <span class="pref-card__icon">⭐</span>
        <h4 class="pref-card__title">优先选修意向 (preferred_courses)</h4>
      </div>
      <div class="pref-card__body">
        <div
          v-if="preference.preferred_courses && preference.preferred_courses.length > 0"
          class="chip-group"
        >
          <span
            v-for="courseId in preference.preferred_courses"
            :key="courseId"
            class="chip chip--pref mono"
          >
            {{ courseNameById?.[courseId] ? `${courseId} · ${courseNameById[courseId]}` : courseId }}
          </span>
        </div>
        <span v-else class="text-muted">未指定优先课程</span>
      </div>
    </div>

    <!-- 回避时段 -->
    <div class="pref-card">
      <div class="pref-card__header">
        <span class="pref-card__icon">⏰</span>
        <h4 class="pref-card__title">回避时段 (avoid_times)</h4>
      </div>
      <div class="pref-card__body">
        <div
          v-if="preference.avoid_times && preference.avoid_times.length > 0"
          class="chip-group"
        >
          <span
            v-for="(block, idx) in preference.avoid_times"
            :key="`${block.weekday}-${block.start_section}-${idx}`"
            class="chip chip--avoid"
          >
            {{ formatWeekday(block.weekday) }} {{ formatSections(block.start_section, block.end_section) }}
          </span>
        </div>
        <span v-else class="text-muted">未设置回避时段</span>
      </div>
    </div>

    <!-- 补充备注 -->
    <div v-if="preference.notes" class="pref-card pref-card--full">
      <div class="pref-card__header">
        <span class="pref-card__icon">📝</span>
        <h4 class="pref-card__title">学生偏好备注 (notes)</h4>
      </div>
      <div class="pref-card__body">
        <blockquote class="pref-notes">
          {{ displayOrDash(preference.notes) }}
        </blockquote>
      </div>
    </div>
  </div>
</template>
