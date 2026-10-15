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
import { compactMeetingLines } from '../utils/weeklySchedule'

const props = defineProps<{
  currentSchedule: readonly CourseOffering[]
  attestationNotice?: string
  /**
   * 原始课表中**未能定位到真实教学班**的课程名（Phase 6）。
   *
   * ⚠️ 如实列出，⛔ 不猜、⛔ 不隐藏：这些课来自课表截图的识别结果，
   *   但本学期教学班库中找不到对应（或缺课程号而多义），需用户自行搜索选择。
   */
  unresolvedCourseNames?: readonly string[]
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
      <h3>当前课表（{{ summary.count }}）</h3>
      <!--
        ⚠️ 来源如实标注：课表里的课来自「上传我的课表截图」的识别结果，
           已按 课程名 + 星期 匹配到本学期真实教学班。
           ⛔ 不写"已通过用户确认加入"（识别结果并非用户逐条确认），
           ⛔ 也不冒充真实 OCR（识别用的是演示固定数据）。
      -->
      <p
        v-if="currentSchedule.length > 0"
        class="cse__summary-lead"
        data-testid="case-a-original-schedule-note"
      >
        以下课程来自<strong>你的原始课表</strong>（课表截图识别 + 匹配到本学期真实教学班）。
        ⚠️ 识别使用演示固定数据，⛔ 非真实 OCR；课号 / 时间 / 地点均取自真实教学班数据。
      </p>
      <p class="cse__summary-safe">
        请核对课程的教学班、时间和地点。
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

    <!--
      ⚠️ 该提示与下方课程列表**互不影响**（⛔ 不能与列表用 v-if/v-else 绑定，
         否则只要有任何未定位课程，整个课表列表就不渲染 —— 这是已修复的真 bug）。
    -->
    <p
      v-if="(unresolvedCourseNames ?? []).length > 0"
      class="cse__hint"
      data-testid="case-a-original-schedule-unresolved"
    >
      ⛔ 原始课表中
      <strong>{{ (unresolvedCourseNames ?? []).length }}</strong> 门课程未能定位到本学期教学班
      （{{ (unresolvedCourseNames ?? []).join('、') }}）；
      请用上方搜索自行选择，系统不会替你猜测。
    </p>

    <ul class="cse__list">
      <li
        v-for="item in visibleSchedule"
        :key="identity(item)"
        class="cse__item"
        data-testid="case-a-current-schedule-item"
      >
        <div class="cse__item-main">
          <strong>{{ item.course_name }}</strong>
          <span class="cse__item-id">{{ item.course_id }} · 教学班 {{ item.class_id }}</span>
          <span class="cse__item-label">上课时间</span>
          <span v-for="line in compactMeetingLines(item.meetings)" :key="line" class="cse__item-meta">{{ line }}</span>
          <span class="cse__item-label">上课地点</span>
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

<style scoped>
.cse__current { margin-top: 20px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius); background: #f8fafc; }
.cse__current-head h3 { margin: 0 0 10px; }
.cse__summary-lead, .cse__summary-safe, .cse__summary, .cse__hint { font-size: 13px; line-height: 1.7; color: var(--text-muted); }
.cse__list { display: grid; gap: 10px; list-style: none; padding: 0; }
.cse__item { display: flex; flex-wrap: wrap; gap: 12px; align-items: start; justify-content: space-between; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: #fff; }
.cse__item-main { display: flex; flex: 1; min-width: 0; flex-direction: column; gap: 6px; overflow-wrap: anywhere; }
.cse__item-id, .cse__item-meta { display: block; color: var(--text-muted); font-size: 13px; line-height: 1.7; }
.cse__item-label { margin-top: 2px; color: var(--text); font-size: 12px; font-weight: 700; }
.cse__actions, .cse__dialog-actions { display: flex; flex-wrap: wrap; gap: 14px; }
.cse__link { background: none; border: 0; padding: 6px 0; color: #2563eb; cursor: pointer; }
.cse__link--danger, .cse__warn { color: #92400e; }
.cse__dialog { margin-top: 12px; padding: 14px; background: #fff; border: 1px solid var(--border); border-radius: var(--radius-sm); }
</style>
