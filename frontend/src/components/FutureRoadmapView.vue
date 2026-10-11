<script setup lang="ts">
import { computed } from 'vue'
import type { FutureRoadmap, FutureRoadmapSemester } from '../types/caseAPlanning'

/**
 * 未来学期修读路径（**可接入式展示壳**）。
 *
 * 边界：
 * - ⛔ 本组件**不生成** roadmap：只有后端真的返回了 roadmap 字段才渲染；
 * - 没有数据时**整块不渲染**（⛔ 不显示占位假数据、⛔ 不显示空壳）；
 * - 未来学期只做**课程级**规划：⛔ 不显示 `class_id` / 教师 / 星期 / 节次 / 教室 / 容量；
 * - ⛔ 不推断学期、不推断学分、不排序，按后端给定顺序原样展示。
 */
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
  return groupTotal([...(semester.required ?? []), ...(semester.makeup ?? []), ...(semester.elective ?? [])])
}
</script>

<template>
  <div v-if="hasData" class="roadmap" data-testid="case-a-future-roadmap">
    <p class="roadmap__disclaimer" data-testid="case-a-roadmap-disclaimer">
      未来学期为基于培养方案的课程级规划；具体教学班需以届时教务系统实际开课为准。
    </p>

    <article
      v-for="semester in semesters"
      :key="semester.semester"
      class="roadmap__term"
      data-testid="case-a-roadmap-term"
    >
      <h3 class="roadmap__term-title">{{ semester.semester }}</h3>

      <div v-if="semester.required?.length" class="roadmap__group">
        <span class="roadmap__group-label">必修</span>
        <ul class="roadmap__list">
          <li v-for="entry in semester.required" :key="entry.course_id">
            {{ courseLine(entry.course_name, entry.credit) }}
          </li>
        </ul>
      </div>

      <div v-if="semester.makeup?.length" class="roadmap__group">
        <span class="roadmap__group-label">补修</span>
        <ul class="roadmap__list">
          <li v-for="entry in semester.makeup" :key="entry.course_id">
            {{ courseLine(entry.course_name, entry.credit) }}
          </li>
        </ul>
      </div>

      <div v-if="semester.elective?.length" class="roadmap__group">
        <span class="roadmap__group-label">选修建议</span>
        <ul class="roadmap__list">
          <li v-for="entry in semester.elective" :key="entry.course_id">
            {{ courseLine(entry.course_name, entry.credit) }}
          </li>
        </ul>
      </div>

      <p v-if="expectedCredit(semester)" class="roadmap__total">
        预计学分：{{ expectedCredit(semester) }}
      </p>
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
  margin: 0;
  color: #3276df;
  font-size: 16px;
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
