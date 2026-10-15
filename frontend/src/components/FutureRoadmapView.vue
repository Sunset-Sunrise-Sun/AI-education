<script setup lang="ts">
import { computed } from 'vue'
import type { FutureRoadmap, FutureRoadmapSemester } from '../types/caseAPlanning'

/**
 * 未来学习路径规划（Phase 7 任务 2）。
 *
 * 边界：
 * - ⛔ 本组件**不生成** roadmap：数据由 `deriveFutureRoadmap()` 从
 *   **培养方案推荐学期 + 后端匹配结果**派生后传入；
 * - ⛔ 不是未来选课预测：不显示且不预测 `class_id` / 教师 / 星期 / 节次 / 教室；
 * - 没有数据时**整块不渲染**（⛔ 不显示占位假数据、⛔ 不显示空壳）；
 * - 按传入顺序原样展示，⛔ 本组件不再排序、不再改学分。
 */
import { termLabel } from '../utils/futureRoadmap'

const props = defineProps<{
  roadmap: FutureRoadmap | null | undefined
}>()

const semesters = computed<FutureRoadmapSemester[]>(() => props.roadmap?.semesters ?? [])

const hasData = computed(() => semesters.value.length > 0)

/** 课程级规划条目：只有课程名与学分，⛔ 不携带任何教学班信息。 */
function courseLine(name: string, credit: number | null | undefined): string {
  return credit === null || credit === undefined ? name : `${name} ${credit} 学分`
}

function groupTotal(entries: readonly { credit?: number | null }[]): string | null {
  const credits = entries
    .map((entry) => entry.credit)
    .filter((value): value is number => typeof value === 'number')
  if (credits.length !== entries.length || credits.length === 0) return null
  return String(credits.reduce((sum, value) => sum + value, 0))
}

/** 后端明确给出 expected_credit 时用它；否则只在**全部条目学分都已知**时相加。 */
function expectedCredit(semester: FutureRoadmapSemester): string | null {
  if (semester.expected_credit !== null && semester.expected_credit !== undefined) {
    return String(semester.expected_credit)
  }
  return groupTotal([
    ...(semester.required ?? []),
    ...(semester.pendingCoverage ?? []),
    ...(semester.makeup ?? []),
    ...(semester.elective ?? []),
  ])
}
</script>

<template>
  <div v-if="hasData" class="roadmap" data-testid="case-a-future-roadmap">
    <p class="roadmap__disclaimer" data-testid="case-a-roadmap-disclaimer">
      以上规划基于培养方案要求生成，不代表实际开课安排。
      ⛔ 不预测未来学期的教师、时间与地点，也不生成具体教学班。
    </p>

    <article
      v-for="semester in semesters"
      :key="semester.semester"
      class="roadmap__term"
      data-testid="case-a-roadmap-term"
    >
      <h3 class="roadmap__term-title" data-testid="case-a-roadmap-term-title">
        {{ termLabel(semester.semester) }}
        <span class="roadmap__term-code">{{ semester.semester }}</span>
      </h3>

      <div v-if="semester.required?.length" class="roadmap__group">
        <span class="roadmap__group-label">明确缺口（后端判定必修）</span>
        <ul class="roadmap__list" data-testid="case-a-roadmap-required">
          <li v-for="entry in semester.required" :key="entry.course_id">
            {{ courseLine(entry.course_name, entry.credit) }}
          </li>
        </ul>
      </div>

      <div v-if="semester.pendingCoverage?.length" class="roadmap__group">
        <span class="roadmap__group-label">培养要求待覆盖</span>
        <p class="roadmap__group-note" data-testid="case-a-roadmap-pending-coverage-note">
          目标培养方案要求存在，但当前成绩单 / 课表 / 匹配结果不足以判断是否需要补修。
        </p>
        <ul class="roadmap__list" data-testid="case-a-roadmap-term-pending-coverage">
          <li v-for="entry in semester.pendingCoverage" :key="entry.course_id">
            {{ courseLine(entry.course_name, entry.credit) }}
          </li>
        </ul>
      </div>

      <div v-if="semester.makeup?.length" class="roadmap__group">
        <span class="roadmap__group-label">待人工确认</span>
        <ul class="roadmap__list" data-testid="case-a-roadmap-unconfirmed">
          <li v-for="entry in semester.makeup" :key="entry.course_id">
            {{ courseLine(entry.course_name, entry.credit) }}
          </li>
        </ul>
      </div>

      <div v-if="semester.elective?.length" class="roadmap__group">
        <span class="roadmap__group-label">专业选修建议</span>
        <ul class="roadmap__list" data-testid="case-a-roadmap-elective">
          <li v-for="entry in semester.elective" :key="entry.course_id">
            {{ courseLine(entry.course_name, entry.credit) }}
          </li>
        </ul>
      </div>

      <p v-if="expectedCredit(semester)" class="roadmap__total" data-testid="case-a-roadmap-credit">
        预计学分：{{ expectedCredit(semester) }}
      </p>

      <div v-if="semester.completion_goals?.length" class="roadmap__goals">
        <span class="roadmap__group-label">完成目标</span>
        <ul class="roadmap__list" data-testid="case-a-roadmap-goals">
          <li v-for="goal in semester.completion_goals" :key="goal">{{ goal }}</li>
        </ul>
      </div>
    </article>
  </div>
</template>

<style scoped>
.roadmap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.roadmap__disclaimer {
  margin: 0;
  padding: 12px 14px;
  color: #1e40af;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.7;
}

.roadmap__term {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}

.roadmap__term-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  color: #3276df;
  font-size: 16px;
}

.roadmap__term-code {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 400;
}

.roadmap__goals {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
}

.roadmap__group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.roadmap__group-label {
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

/* 「培养要求待覆盖」的固定说明（语义收敛要求逐字展示） */
.roadmap__group-note {
  margin: 2px 0 4px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.6;
}

.roadmap__list {
  margin: 0;
  padding-left: 20px;
  color: #334155;
  line-height: 1.8;
}

.roadmap__total {
  margin: 0;
  color: var(--text);
  font-weight: 700;
}
</style>
