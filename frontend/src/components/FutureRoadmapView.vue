<script setup lang="ts">
import { computed } from 'vue'
import type { AcademicRoadmap, RoadmapSemester } from '../types/caseAPlanning'
import { loadLabel, type LoadTone } from '../utils/creditPolicy'

/**
 * 未来学期修读路径（真实 `AcademicRoadmap`）。
 *
 * 边界：
 * - ⛔ 本组件**不生成** roadmap：只展示后端返回的事实；
 * - `roadmap` 为 `null` 时整块不渲染（⛔ 不显示占位假数据）；
 * - 未来学期只做**课程级**规划：⛔ 不显示 `class_id` / 教师 / 星期 / 节次 / 教室 / 容量；
 * - ⛔ 不推断学期、不推断学分、不重排顺序，按后端给定顺序原样展示；
 * - ⛔ 不把 `unresolved` / `warnings` 藏起来，也不把它们改写成结论。
 */
const props = defineProps<{
  roadmap: AcademicRoadmap | null | undefined
}>()

const semesters = computed<RoadmapSemester[]>(() => props.roadmap?.future_semesters ?? [])

const hasData = computed(() => semesters.value.length > 0)

const elective = computed(() => props.roadmap?.elective ?? null)

/** 数值保留一位小数以内，避免出现 23.000000000000004 这类噪声。 */
function credit(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return String(Math.round(value * 100) / 100)
}

/** 学期负荷标签：口径与阈值集中在 `utils/creditPolicy.ts`（含 26/30/35 三档）。 */
function loadTone(total: number): LoadTone {
  return loadLabel(total).tone
}

/** 培养方案学期号文案：⛔ 不把它说成"列表第 N 项"。 */
function curriculumTermText(semester: RoadmapSemester): string {
  return `培养方案第 ${semester.curriculum_semester} 学期`
}

const unresolved = computed(() => props.roadmap?.unresolved ?? [])
const warnings = computed(() => props.roadmap?.warnings ?? [])
</script>

<template>
  <div v-if="hasData" class="roadmap" data-testid="case-a-future-roadmap">
    <p class="roadmap__disclaimer" data-testid="case-a-roadmap-disclaimer">
      未来学期为基于培养方案的<strong>课程级</strong>规划；具体教学班需以届时教务系统实际开课为准。
      ⛔ 这里不预测未来的教学班、教师、教室或上课时间。
    </p>

    <!-- 选修学分进度 -->
    <section v-if="elective" class="roadmap__elective" data-testid="case-a-elective-progress">
      <h3 class="roadmap__elective-title">
        选修学分进度<template v-if="elective.group_id">（{{ elective.group_id }}）</template>
      </h3>
      <div class="roadmap__elective-grid">
        <div>
          <strong>{{ credit(elective.requirement_credit) }}</strong>
          <span>最低学分要求</span>
        </div>
        <div>
          <strong>{{ credit(elective.completed_credit) }}</strong>
          <span>已确认完成</span>
        </div>
        <div>
          <strong>{{ credit(elective.current_semester_credit) }}</strong>
          <span>本学期已选</span>
        </div>
        <div>
          <strong>{{ credit(elective.gap_credit) }}</strong>
          <span>规划前缺口</span>
        </div>
        <div>
          <strong>{{ credit(elective.planned_credit) }}</strong>
          <span>本次规划</span>
        </div>
        <div>
          <strong>{{ credit(elective.remaining_credit) }}</strong>
          <span>规划后仍缺</span>
        </div>
      </div>
      <p
        v-if="elective.completed_credit === null || elective.requirement_credit === null"
        class="roadmap__elective-note"
        data-testid="case-a-elective-insufficient"
      >
        学分证据不足时系统<strong>不猜测</strong>：缺失项显示为「—」，需人工确认。
      </p>
    </section>

    <article
      v-for="semester in semesters"
      :key="semester.semester_label"
      class="roadmap__term"
      data-testid="case-a-roadmap-term"
    >
      <header class="roadmap__term-head">
        <h3 class="roadmap__term-title">{{ semester.semester_label }}</h3>
        <span class="roadmap__term-sub">{{ curriculumTermText(semester) }}</span>
        <span class="tag tag--source-real">
          建议学分：{{ credit(semester.total_credit) }}
        </span>
        <span
          class="tag"
          :class="{
            'tag--load-normal': loadTone(semester.total_credit) === 'normal',
            'tag--unresolved-schedule': loadTone(semester.total_credit) === 'full',
            'tag--unresolved-manual':
              loadTone(semester.total_credit) === 'heavy' ||
              loadTone(semester.total_credit) === 'over',
          }"
          data-testid="case-a-roadmap-load"
        >
          负荷：{{ loadLabel(semester.total_credit).text }}
        </span>
      </header>

      <p v-if="semester.courses.length === 0" class="roadmap__term-empty">
        该学期按当前培养方案事实没有需要安排的课程。
      </p>

      <ul v-else class="roadmap__list">
        <li
          v-for="entry in semester.courses"
          :key="entry.course_id"
          class="roadmap__item"
          data-testid="case-a-roadmap-course"
        >
          <div class="roadmap__item-head">
            <strong>{{ entry.course_name }}</strong>
            <span class="mono roadmap__item-id">{{ entry.course_id }}</span>
            <span class="tag">{{ entry.requirement_label }}</span>
            <span class="roadmap__item-credit">{{ credit(entry.credit) }} 学分</span>
          </div>
          <p class="roadmap__item-reason">{{ entry.reason }}</p>
        </li>
      </ul>

      <p class="roadmap__term-credit">
        必修 {{ credit(semester.required_credit) }} 学分 ·
        选修 {{ credit(semester.elective_credit) }} 学分
      </p>

      <ul v-if="semester.warnings.length > 0" class="roadmap__notes">
        <li v-for="(item, index) in semester.warnings" :key="`w-${index}`">{{ item }}</li>
      </ul>
    </article>

    <!-- 未决事项与如实说明（⛔ 不隐藏） -->
    <section v-if="unresolved.length > 0" class="roadmap__block" data-testid="case-a-roadmap-unresolved">
      <h3 class="roadmap__block-title">路线图中需要人工确认的事项（{{ unresolved.length }} 项）</h3>
      <ul class="roadmap__notes">
        <li v-for="(item, index) in unresolved" :key="`u-${index}`">{{ item }}</li>
      </ul>
    </section>

    <section v-if="warnings.length > 0" class="roadmap__block" data-testid="case-a-roadmap-warnings">
      <h3 class="roadmap__block-title">规划说明（{{ warnings.length }} 项）</h3>
      <ul class="roadmap__notes">
        <li v-for="(item, index) in warnings" :key="`g-${index}`">{{ item }}</li>
      </ul>
    </section>
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

.roadmap__elective {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.roadmap__elective-title {
  margin: 0;
  font-size: 14px;
  color: var(--text);
}

.roadmap__elective-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
  gap: 10px;
}

.roadmap__elective-grid div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.roadmap__elective-grid strong {
  font-size: 16px;
  color: #3276df;
}

.roadmap__elective-grid span {
  color: var(--text-muted);
  font-size: 11px;
}

.roadmap__elective-note {
  margin: 0;
  color: #b45309;
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

.roadmap__term-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.roadmap__term-title {
  margin: 0;
  color: #3276df;
  font-size: 16px;
}

.roadmap__term-sub {
  color: var(--text-muted);
  font-size: 12px;
}

.roadmap__term-empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.roadmap__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.roadmap__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 12px;
  border-left: 3px solid #dbeafe;
}

.roadmap__item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  color: #334155;
}

.roadmap__item-id {
  color: var(--text-muted);
  font-size: 12px;
}

.roadmap__item-credit {
  color: #475569;
  font-size: 12px;
}

.roadmap__item-reason {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}

.roadmap__term-credit {
  margin: 0;
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
}

.roadmap__block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  background: #fffdf5;
  border: 1px solid #f3d9a4;
  border-radius: var(--radius);
}

.roadmap__block-title {
  margin: 0;
  font-size: 13px;
  color: #92400e;
}

.roadmap__notes {
  margin: 0;
  padding-left: 20px;
  color: #475569;
  font-size: 12px;
  line-height: 1.8;
}
</style>
