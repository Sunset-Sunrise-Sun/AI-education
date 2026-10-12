<script setup lang="ts">
/**
 * 「已确认加入的当前课表」区块（从 `CurrentScheduleEditor` 原样抽出）。
 *
 * ⚠️ 抽出目的：**只改布局顺序** —— 让当前课表显示在「上传课表截图 + 识别结果」之后，
 *   形成「识别 → 用户确认 → 课表实时更新 → 剩余未识别」的可感知闭环。
 *
 * ⛔ 行为与数据流完全不变：数据仍由父级传入 `currentSchedule`（唯一数据源），
 *   移除 / 清空仍向父级 emit，`data-testid` 全部沿用。
 *
 * ⚠️ 这里的"确认"只表示**用户把该教学班放进了当前课表**：
 *   ⛔ 不是 OCR 自动加入，⛔ 不是系统自动认定，⛔ 不产生任何课程身份或学分认定。
 */

import { computed, ref } from 'vue'

import type { CourseOffering } from '../types/contracts'
import { summarizeCredits } from '../utils/courseSearch'
import { compactMeetingSummary } from '../utils/weeklySchedule'

const props = defineProps<{
  currentSchedule: readonly CourseOffering[]
  attestationNotice?: string
}>()

const emit = defineEmits<{
  (event: 'remove', offering: CourseOffering): void
  (event: 'clear'): void
}>()

const showAll = ref(false)
const clearOpen = ref(false)

const summary = computed(() => summarizeCredits(props.currentSchedule))
const visibleSchedule = computed(() =>
  showAll.value ? props.currentSchedule : props.currentSchedule.slice(0, 3),
)

function identity(offering: CourseOffering): string {
  return `${offering.semester}::${offering.course_id}::${offering.class_id}`
}

function teacherText(offering: CourseOffering): string {
  const value = offering.teacher?.trim()
  if (!value) return '任课教师：待核验'
  if (value.toLocaleLowerCase() === 'redacted') return '任课教师：信息已脱敏'
  return `任课教师：${value}`
}

function placeText(offering: CourseOffering): string {
  const places = offering.meetings
    .map((meeting) => [meeting.campus, meeting.classroom].filter(Boolean).join(' '))
    .filter((value) => value.trim() !== '')
  return places.length > 0 ? [...new Set(places)].join('；') : '地点信息待核验'
}

/** 本人确认来源的条目：手工录入或图片识别确认。 */
function isUserConfirmedSource(offering: CourseOffering): boolean {
  return (
    offering.source === 'manual-entry://current-schedule'
    || offering.source === 'image-recognition://timetable-screenshot'
  )
}

function confirmClear(): void {
  clearOpen.value = false
  emit('clear')
}
</script>

<template>
  <section class="cse__current" data-testid="case-a-current-schedule">
    <header class="cse__current-head">
      <h3>已确认加入的当前课表（{{ summary.count }}）</h3>
      <p class="cse__summary-lead">
        以下课程<strong>已通过用户确认</strong>加入，将用于后续方案生成。
      </p>
      <p class="cse__summary-safe">
        ⚠️ 识别候选不会自动进入课表，也不代表教学班身份已被认定；⛔ 不是系统自动认定。
      </p>
      <p class="cse__summary" data-testid="case-a-schedule-summary">
        <template v-if="summary.total !== null">
          已加入 {{ summary.count }} 门 · 预计 {{ summary.total }} 学分
        </template>
        <template v-else>
          已加入 {{ summary.count }} 门
        </template>
      </p>
      <p v-if="summary.hasUnknownCredit" class="cse__hint" data-testid="case-a-credit-unknown">
        部分课程学分待核验（{{ summary.unknownCount }} 门），因此不显示预计总学分。
      </p>
    </header>

    <p v-if="currentSchedule.length === 0" class="cse__empty">尚未添加当前课程。</p>

    <ul v-else class="cse__list">
      <li
        v-for="item in visibleSchedule"
        :key="identity(item)"
        class="cse__item"
        data-testid="case-a-current-schedule-item"
      >
        <div class="cse__item-main">
          <strong>{{ item.course_name }}</strong>
          <span class="cse__item-id">{{ item.course_id }} · 教学班 {{ item.class_id }}</span>
          <span class="cse__item-meta">{{ compactMeetingSummary(item.meetings) }}</span>
          <span class="cse__item-meta">{{ placeText(item) }}</span>
          <span class="cse__item-meta">{{ teacherText(item) }}</span>
          <span v-if="isUserConfirmedSource(item)" class="cse__warn">
            该课程信息由你本人确认，未经学校系统核验。
          </span>
        </div>
        <button
          class="button button--small cse__remove"
          type="button"
          data-testid="case-a-current-schedule-remove"
          @click="emit('remove', item)"
        >
          移除
        </button>
      </li>
    </ul>

    <div v-if="currentSchedule.length > 0" class="cse__actions">
      <button
        v-if="currentSchedule.length > 3"
        class="cse__link"
        type="button"
        data-testid="case-a-schedule-view-all"
        @click="showAll = !showAll"
      >
        {{ showAll ? '收起列表' : `查看全部（${currentSchedule.length}）` }}
      </button>
      <button
        class="cse__link cse__link--danger"
        type="button"
        data-testid="case-a-schedule-clear"
        @click="clearOpen = true"
      >
        清空当前课表
      </button>
    </div>

    <p v-if="attestationNotice" class="cse__warn" data-testid="case-a-attestation-notice">
      {{ attestationNotice }}
    </p>

    <!-- 清空二次确认 -->
    <div v-if="clearOpen" class="cse__dialog" role="dialog" data-testid="case-a-clear-confirm">
      <p>确定清空当前已加入的 {{ currentSchedule.length }} 门课程吗？</p>
      <p class="cse__hint">清空后需要重新确认手工录入信息，确认状态不会被保留。</p>
      <div class="cse__dialog-actions">
        <button class="button button--small" type="button" data-testid="case-a-clear-cancel" @click="clearOpen = false">
          取消
        </button>
        <button
          class="button button--small cse__remove"
          type="button"
          data-testid="case-a-clear-confirm-button"
          @click="confirmClear"
        >
          确认清空
        </button>
      </div>
    </div>
  </section>
</template>
