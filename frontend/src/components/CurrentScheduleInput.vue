<script setup lang="ts">
import type { CourseOffering } from '../types/contracts'
import { EMPTY_MEETINGS_DATA_TEXT, formatMeetingLine } from '../utils/labels'

/**
 * 当前课表输入（`current_schedule: CourseOffering[]`）。
 *
 * 边界（DG-03 语义 + 本轮范围）：
 * - 只做一件事：让用户从**已加载的教学班**里勾选"我当前已选的班"；
 * - 勾选结果严格是 `CourseOffering[]`（复用公共类型，不新增 Schema）；
 * - ⛔ **不做冲突检测、不判断 feasible、不做 Path Repair、不计算学分**；
 * - ⛔ 不用 `Preference.avoid_times[]` 冒充当前课表；
 * - 允许为空：空数组是合法输入，是否需要更多信息由后端决定。
 */
const props = defineProps<{
  /** 来源教学班（学校供给），当前来自 Mock 演示通道。 */
  offerings: CourseOffering[]
  /** 用户已勾选的当前课表。 */
  selected: CourseOffering[]
  /** 数据来源标记，用于如实说明当前是 Mock 还是 Real。 */
  dataSourceLabel?: string | null
}>()

const emit = defineEmits<{
  (event: 'toggle', offering: CourseOffering): void
}>()

function keyOf(offering: CourseOffering): string {
  return `${offering.semester}::${offering.course_id}::${offering.class_id}`
}

function isSelected(offering: CourseOffering): boolean {
  return props.selected.some((item) => keyOf(item) === keyOf(offering))
}

function onToggle(offering: CourseOffering): void {
  emit('toggle', offering)
}

function firstMeetingText(offering: CourseOffering): string {
  if (offering.meetings.length === 0) {
    return EMPTY_MEETINGS_DATA_TEXT
  }
  return formatMeetingLine(offering.meetings[0])
}
</script>

<template>
  <div class="uig-form">
    <p class="uig-form__note">
      勾选你<strong>当前已选</strong>的教学班。本区块只负责组织输入，<strong>不进行冲突检测、不判断可行性</strong>；
      教学班供给当前来自{{ dataSourceLabel ? ` ${dataSourceLabel} ` : '当前数据源' }}。
    </p>

    <div v-if="offerings.length === 0" class="uig-empty" data-testid="schedule-empty">
      当前没有可勾选的教学班记录（教学班数 0）。当前课表可以留空继续。
    </div>

    <div v-else class="uig-schedule-list">
      <label
        v-for="offering in offerings"
        :key="keyOf(offering)"
        class="uig-schedule-row"
        data-testid="schedule-option"
      >
        <input
          type="checkbox"
          :data-testid="`schedule-checkbox-${offering.course_id}-${offering.class_id}`"
          :checked="isSelected(offering)"
          @change="onToggle(offering)"
        />
        <span class="uig-schedule-main">
          <strong>{{ offering.course_name }}</strong>
          <span class="mono uig-schedule-id">{{ offering.course_id }} · {{ offering.class_id }}</span>
        </span>
        <span class="uig-schedule-meta">{{ offering.semester }}</span>
        <span class="uig-schedule-meta">{{ firstMeetingText(offering) }}</span>
      </label>
    </div>

    <p class="uig-field__hint" data-testid="schedule-summary">
      已选 {{ selected.length }} 个教学班（<code class="mono">current_schedule</code> 将以
      <code class="mono">CourseOffering[]</code> 原样输出）。
    </p>
  </div>
</template>
