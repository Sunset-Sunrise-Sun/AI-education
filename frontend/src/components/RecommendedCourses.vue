<script setup lang="ts">
/**
 * 推荐选课（卡片形式）。
 *
 * 语义：AI 根据**剩余培养缺口 + 当前教学班信息 + 学期安排**，
 *      推荐学生本学期应该加入的课程。
 *
 * ⚠️ 数据来源是**真实教学班对象**（后端 `/offerings` 返回的 `CourseOffering`），
 *   ⛔ **不是** `planResult.selected_classes`（那只是 planner 回传结果，可能等于当前课表）。
 *   ⛔ 不伪造课程对象。
 *
 * ⚠️ 与「补修缺口分析」严格区分：本模块回答「本学期学什么」。
 */

import { computed, ref } from 'vue'

import type { CourseOffering } from '../types/contracts'
import { compactMeetingSummary } from '../utils/weeklySchedule'

/**
 * 推荐来源标签（Phase 6，任务 2）。
 *
 * ⚠️ 两个来源**合并为一个列表**，但**必须**用标签 + 颜色区分：
 *   `required` = A 必须补修（来源：后端 `missing`）
 *   `elective` = B 建议选修（来源：培养方案 `elective_pool`）
 * ⛔ 不得把选修显示成"补修课程"；⛔ 算法本身未改。
 */
export type RecommendationTag = 'required' | 'elective'

const props = defineProps<{
  /** 可选推荐课程（已由父级按来源合并并标注 tag）。 */
  courses: readonly CourseOffering[]
  /** 当前已加入本学期方案的教学班。 */
  selectedCourses: readonly CourseOffering[]
  /** 按课程生成推荐理由（由父级依据缺口事实与偏好算出）。 */
  reasonFor?: (offering: CourseOffering) => string
  /** 按课程取来源标签（由父级决定，⛔ 组件不猜）。 */
  tagFor?: (offering: CourseOffering) => RecommendationTag
}>()

const emit = defineEmits<{
  (event: 'confirm', courses: CourseOffering[]): void
  (event: 'remove', course: CourseOffering): void
}>()

/** 标签展示文案。 */
const TAG_LABEL: Readonly<Record<RecommendationTag, string>> = {
  required: 'A · 必须补修',
  elective: 'B · 建议选修',
}

/** 标签说明（让用户明白两类含义不同）。 */
const TAG_HINT: Readonly<Record<RecommendationTag, string>> = {
  required: '培养方案要求、成绩单未发现对应记录 —— 必须完成。',
  elective: '属于目标专业选修池 —— 用于完成选修学分方向，不是补修要求。',
}

function tagOf(offering: CourseOffering): RecommendationTag {
  return props.tagFor ? props.tagFor(offering) : 'required'
}

/** 当前勾选（尚未提交）的教学班。 */
const picked = ref<string[]>([])

function keyOf(offering: CourseOffering): string {
  return `${offering.course_id}::${offering.class_id}`
}

const selectedSet = computed(() => new Set(props.selectedCourses.map(keyOf)))

function isPicked(offering: CourseOffering): boolean {
  return picked.value.includes(keyOf(offering))
}

function toggle(offering: CourseOffering): void {
  const key = keyOf(offering)
  picked.value = isPicked(offering)
    ? picked.value.filter((item) => item !== key)
    : [...picked.value, key]
}

/** 课程级「加入本学期方案」：立即生效（课表实时更新）。 */
function addOne(offering: CourseOffering): void {
  emit('confirm', [offering])
  picked.value = picked.value.filter((item) => item !== keyOf(offering))
}

/** 底部总按钮「确认加入方案」。 */
function addPicked(): void {
  const items = props.courses.filter((offering) => picked.value.includes(keyOf(offering)))
  if (items.length === 0) {
    return
  }
  emit('confirm', items)
  picked.value = []
}

function placeText(offering: CourseOffering): string {
  const places = offering.meetings
    .map((meeting) => [meeting.campus, meeting.classroom].filter(Boolean).join(' '))
    .filter((value) => value.trim() !== '')
  return places.length > 0 ? [...new Set(places)].join('；') : '地点待确认'
}
</script>

<template>
  <section class="recommend" data-testid="case-a-recommend">
    <p class="recommend__lead">
      AI 根据你的剩余培养要求、当前教学班安排和学期计划，建议你本学期加入以下课程。
      课程按来源分为 <strong>A 必须补修</strong> 与 <strong>B 建议选修</strong> 两类，
      ⛔ 两者含义不同，不会混为一谈。
    </p>

    <div v-if="courses.length > 0" class="recommend__legend" data-testid="case-a-recommend-legend">
      <span class="recommend-card__tag recommend-card__tag--required">A · 必须补修</span>
      <span class="recommend__legend-text">{{ TAG_HINT.required }}</span>
      <span class="recommend-card__tag recommend-card__tag--elective">B · 建议选修</span>
      <span class="recommend__legend-text">{{ TAG_HINT.elective }}</span>
    </div>

    <div v-if="courses.length > 0" class="recommend__grid" data-testid="case-a-recommend-list">
      <article
        v-for="offering in courses"
        :key="keyOf(offering)"
        class="recommend-card"
        :class="`recommend-card--${tagOf(offering)}`"
        data-testid="case-a-recommend-card"
      >
        <div class="recommend-card__head">
          <span
            class="recommend-card__tag"
            :class="`recommend-card__tag--${tagOf(offering)}`"
            data-testid="case-a-recommend-tag"
          >
            {{ TAG_LABEL[tagOf(offering)] }}
          </span>
          <strong class="recommend-card__name">{{ offering.course_name }}</strong>
          <span class="recommend-card__id">{{ offering.course_id }}</span>
        </div>
        <p class="recommend-card__class">教学班 {{ offering.class_id }}</p>
        <p class="recommend-card__meta">{{ compactMeetingSummary(offering.meetings) }}</p>
        <p class="recommend-card__meta">{{ placeText(offering) }}</p>
        <p class="recommend-card__reason" data-testid="case-a-recommend-reason">
          <strong>推荐原因：</strong>{{ reasonFor ? reasonFor(offering) : '该课程属于目标专业培养要求中你尚未完成的缺口。' }}
        </p>

        <div class="recommend-card__actions">
          <template v-if="selectedSet.has(keyOf(offering))">
            <span class="recommend-card__added" data-testid="case-a-recommend-added">
              ✓ 已加入本学期方案
            </span>
            <button
              class="button button--small button--ghost"
              type="button"
              data-testid="case-a-recommend-remove"
              @click="emit('remove', offering)"
            >
              移除
            </button>
          </template>
          <template v-else>
            <label class="recommend-card__check">
              <input
                type="checkbox"
                :checked="isPicked(offering)"
                :aria-label="`选择 ${offering.course_name}`"
                data-testid="case-a-recommend-checkbox"
                @change="toggle(offering)"
              />
              <span>选择</span>
            </label>
            <button
              class="button button--small"
              type="button"
              data-testid="case-a-recommend-add"
              @click="addOne(offering)"
            >
              加入本学期方案
            </button>
          </template>
        </div>
      </article>
    </div>
    <p v-else class="recommend__empty" data-testid="case-a-recommend-empty">
      目前没有需要推荐的课程（已确认可转换或已加入本学期方案）。
    </p>

    <div v-if="courses.length > 0" class="recommend__footer">
      <span role="status" aria-live="polite" data-testid="case-a-recommend-picked-count">
        已选择 {{ picked.length }} 门
      </span>
      <button
        class="button"
        type="button"
        :disabled="picked.length === 0"
        data-testid="case-a-recommend-confirm-selection"
        @click="addPicked"
      >
        确认加入方案
      </button>
      <span class="recommend__note">
        加入只表示纳入本学期规划，⛔ 不代表已经在学校系统选课成功。
      </span>
    </div>
  </section>
</template>

<style scoped>
.recommend__lead {
  margin: 0 0 12px;
  color: #55606e;
  font-size: 13px;
  line-height: 1.6;
}

.recommend__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

/* 来源图例：让 A / B 两类在列表上方就说清楚 */
.recommend__legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  margin: 0 0 12px;
  padding: 8px 12px;
  border: 1px solid var(--border, #dde3ea);
  border-radius: 8px;
  background: #f7f9fc;
}

.recommend__legend-text {
  margin-right: 10px;
  color: #55606e;
  font-size: 12px;
}

.recommend-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  border: 1px solid var(--border, #dde3ea);
  border-radius: var(--radius, 8px);
  background: #fff;
}

/* 卡片左侧色条：A 暖色（必须）、B 蓝色（建议） */
.recommend-card--required {
  border-left: 4px solid #d97706;
}

.recommend-card--elective {
  border-left: 4px solid #3276df;
}

.recommend-card__tag {
  align-self: flex-start;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.recommend-card__tag--required {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #f3d9a4;
}

.recommend-card__tag--elective {
  background: #e8f0fb;
  color: #10407a;
  border: 1px solid #bfdbfe;
}

.recommend-card__head {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.recommend-card__name {
  font-size: 15px;
}

.recommend-card__id,
.recommend-card__class,
.recommend-card__meta {
  margin: 0;
  color: #6b7683;
  font-size: 12px;
}

.recommend-card__reason {
  margin: 4px 0 0;
  color: #33404f;
  font-size: 12px;
  line-height: 1.6;
}

.recommend-card__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
  padding-top: 6px;
}

.recommend-card__check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
}

.recommend-card__check input {
  width: 18px;
  height: 18px;
  accent-color: #3276df;
}

.recommend-card__added {
  padding: 3px 10px;
  border: 1px solid #2e7d32;
  border-radius: 6px;
  background: #e8f5e9;
  color: #1b5e20;
  font-size: 12px;
  font-weight: 600;
}

.recommend__empty {
  margin: 0;
  color: #55606e;
  font-size: 13px;
}

.recommend__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
  font-size: 13px;
}

.recommend__footer button:disabled {
  opacity: 0.5;
  cursor: default;
}

.recommend__note {
  flex: 1 1 260px;
  color: #55606e;
  font-size: 12px;
}
</style>
