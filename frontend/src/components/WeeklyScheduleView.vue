<script setup lang="ts">
import { computed } from 'vue'
import { COURSE_TAG_LABEL, courseTags, type CourseTag } from '../utils/courseTags'
import { formatWeekday } from '../utils/labels'
import {
  buildWeeklySchedule,
  weeklyScheduleIsEmpty,
  type ScheduleBlock,
} from '../utils/weeklySchedule'
import type { CourseOffering, MakeupTask, PlanResult } from '../types/contracts'

/**
 * 本学期推荐课表（周视图）。
 *
 * - 数据**全部**来自 `PlanResult.selected_classes` + 后端返回的 `course_offerings`；
 * - ⛔ 不修改 PlanResult、⛔ 不推断、⛔ 不补数据；
 * - `selected_classes` 是 Planner 的**建议**，不是"已经选上"；
 * - 教师为空显示"教师信息暂未同步"（当前没有真实教师数据）；
 * - `meetings = []` 显示"当前数据中无排课信息"（⛔ 不等于没有课、⛔ 不等于无冲突）。
 */
const props = defineProps<{
  planResult: PlanResult | null
  offerings: readonly CourseOffering[]
  /**
   * **本学期的显式规划学期**（来自 Case A 表单 / 请求上下文）。
   *
   * 公共 `SelectedClass` 没有 `semester` 字段，而教学班身份是
   * `semester + course_id + class_id`，因此这里必须显式传入，⛔ 不从系统日期推断。
   */
  semester: string
  currentSchedule: readonly CourseOffering[]
  makeupTasks: readonly MakeupTask[]
  preferredCourses: readonly string[]
}>()

const view = computed(() => buildWeeklySchedule(props.planResult, props.offerings, props.semester))
const isEmpty = computed(() => weeklyScheduleIsEmpty(view.value))

function tagsFor(block: ScheduleBlock): CourseTag[] {
  return courseTags({
    semester: props.semester,
    courseId: block.courseId,
    classId: block.classId,
    currentSchedule: props.currentSchedule,
    makeupTasks: props.makeupTasks,
    preferredCourses: props.preferredCourses,
  })
}

function teacherText(teacher: string | null): string {
  const value = teacher?.trim()
  if (!value) return '教师信息暂未同步'
  if (value.toLocaleLowerCase() === 'redacted') return '任课教师：信息已脱敏'
  return `任课教师：${value}`
}

function placeText(block: ScheduleBlock): string {
  const parts = [block.campus, block.classroom].filter(
    (value): value is string => !!value && value.trim() !== '',
  )
  return parts.length > 0 ? parts.join(' / ') : '地点信息待核验'
}

/** 该格的课块 —— 只在**起始节**返回，避免同一门课在每一节都重复渲染。 */
function blockAt(weekday: number, section: number): ScheduleBlock | null {
  const slot = view.value.slots.find((item) => item.weekday === weekday && item.section === section)
  const block = slot?.block ?? null
  return block && block.startSection === section ? block : null
}
</script>

<template>
  <div class="weekly" data-testid="case-a-weekly-schedule">
    <p class="weekly__note">
      本周课表来自 Planner 的 <strong>建议教学班</strong>（`selected_classes`）与已返回的真实教学班数据；
      ⛔ 不代表已经完成选课或注册。
    </p>

    <p v-if="isEmpty" class="weekly__empty" data-testid="case-a-weekly-empty">
      本次建议方案中没有可绘制的教学班（或建议教学班在已返回的教学班数据中不存在）。
    </p>

    <div v-else class="weekly__scroll">
      <table class="weekly__table">
        <thead>
          <tr>
            <th class="weekly__corner">节次</th>
            <th v-for="day in view.days" :key="day.weekday" data-testid="case-a-weekly-day">
              {{ formatWeekday(day.weekday) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="section in view.sectionNumbers" :key="section">
            <th class="weekly__section" scope="row">第 {{ section }} 节</th>
            <td
              v-for="day in view.days"
              :key="`${day.weekday}-${section}`"
              class="weekly__cell"
              :class="{ 'weekly__cell--filled': !!blockAt(day.weekday, section) }"
            >
              <article
                v-if="blockAt(day.weekday, section)"
                class="weekly__block"
                data-testid="case-a-weekly-block"
              >
                <div class="weekly__block-head">
                  <strong>{{ blockAt(day.weekday, section)!.courseName }}</strong>
                  <span
                    v-for="tag in tagsFor(blockAt(day.weekday, section)!)"
                    :key="tag"
                    class="weekly__tag"
                    :class="`weekly__tag--${tag}`"
                    data-testid="case-a-weekly-tag"
                  >
                    {{ COURSE_TAG_LABEL[tag] }}
                  </span>
                </div>
                <p class="weekly__meta">
                  {{ blockAt(day.weekday, section)!.courseId }} · 教学班
                  {{ blockAt(day.weekday, section)!.classId }}
                </p>
                <p class="weekly__meta">{{ teacherText(blockAt(day.weekday, section)!.teacher) }}</p>
                <p class="weekly__meta">{{ placeText(blockAt(day.weekday, section)!) }}</p>
                <p class="weekly__meta">
                  第 {{ blockAt(day.weekday, section)!.startSection }}-{{
                    blockAt(day.weekday, section)!.endSection
                  }}
                  节
                </p>
                <p v-if="blockAt(day.weekday, section)!.departureWarning" class="weekly__warning">
                  该日存在不同校区的安排，请预留通勤时间。
                </p>
              </article>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="view.unmatched.length > 0" class="weekly__warning" data-testid="case-a-weekly-unmatched">
      有 {{ view.unmatched.length }} 个建议教学班未能在已返回的教学班数据中匹配到，因此**未绘制**到课表中
      （⛔ 系统不会为它们编造上课时间）。
    </p>
  </div>
</template>

<style scoped>
.weekly {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.weekly__note,
.weekly__empty,
.weekly__meta,
.weekly__warning {
  margin: 0;
}

.weekly__note {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.weekly__empty {
  padding: 14px 16px;
  color: var(--text-muted);
  background: #f8fafc;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
}

.weekly__scroll {
  overflow-x: auto;
}

.weekly__table {
  width: 100%;
  min-width: 940px;
  border-collapse: collapse;
  background: #fff;
}

.weekly__table th {
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  background: #f6f9fd;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
  text-align: left;
}

.weekly__corner {
  width: 76px;
}

.weekly__section {
  width: 76px;
  color: #64748b !important;
  font-weight: 600 !important;
}

.weekly__cell {
  height: 56px;
  padding: 4px;
  border: 1px solid #eef1f6;
  vertical-align: top;
}

.weekly__cell--filled {
  background: #fbfdff;
}

.weekly__block {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 7px 8px;
  border-left: 3px solid #3276df;
  border-radius: 6px;
  background: #eef5ff;
}

.weekly__block-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.weekly__block-head strong {
  color: #1e293b;
  font-size: 13px;
}

.weekly__tag {
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
}

.weekly__tag--current {
  background: #dcfce7;
  color: #15803d;
}

.weekly__tag--makeup {
  background: #fee2e2;
  color: #b91c1c;
}

.weekly__tag--preferred {
  background: #ede9fe;
  color: #6d28d9;
}

.weekly__meta {
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

.weekly__warning {
  color: #b45309;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.6;
}
</style>
