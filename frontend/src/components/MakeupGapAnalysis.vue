<script setup lang="ts">
/**
 * 补修缺口分析（卡片形式）—— **消费后端真实 `makeup_tasks`**。
 *
 * 语义：回答一个问题 ——「我转专业以后还缺什么？」
 *
 * ```text
 * 已满足        培养要求已满足（成绩单可抵扣 / 学生已确认转换）
 * 待确认        成绩单存在相关记录，但等价关系需人工确认
 * 缺失          培养方案要求，成绩单未发现对应记录 → 转专业后需要补修
 * ```
 *
 * ⚠️ 关键边界：
 * - 本组件**不含任何课程号/课程名判断**，也不读任何前端配置；
 *   三状态完全由 `utils/makeupAnalysis.ts` 从后端 `status` 映射而来；
 * - `reason` / `source_evidence` 一律**原样展示后端文案**，⛔ 不在前端编造理由；
 * - 「本学期是否有教学班」是**前端由教学班数据推断**的，页面上如实标注，
 *   ⛔ 不冒充后端结论（公共 `MakeupTask` 没有开课字段）。
 */

import { computed, ref } from 'vue'

import {
  UNCERTAINTY_LABEL,
  VIEW_STATUS_HINT,
  VIEW_STATUS_LABEL,
  type MakeupAnalysisItem,
} from '../utils/makeupAnalysis'

const props = defineProps<{
  /** 全部补修分析条目（已由父级按后端 `makeup_tasks` 构造）。 */
  items: readonly MakeupAnalysisItem[]
  /** 已确认可转换的课程号（用于显示「撤销」）。 */
  confirmedCourses: readonly string[]
}>()

const emit = defineEmits<{
  (event: 'confirm', courseIds: string[]): void
  (event: 'undo', courseId: string): void
}>()

const selected = ref<string[]>([])

const confirmedSet = computed(() => new Set(props.confirmedCourses))

const satisfied = computed(() => props.items.filter((item) => item.status === 'satisfied'))
const needConfirmation = computed(() =>
  props.items.filter((item) => item.status === 'need_confirmation'),
)
const missing = computed(() => props.items.filter((item) => item.status === 'missing'))

function isSelected(courseId: string): boolean {
  return selected.value.includes(courseId)
}

function toggle(courseId: string): void {
  selected.value = isSelected(courseId)
    ? selected.value.filter((id) => id !== courseId)
    : [...selected.value, courseId]
}

function confirmOne(courseId: string): void {
  emit('confirm', [courseId])
  selected.value = selected.value.filter((id) => id !== courseId)
}

function confirmSelected(): void {
  if (selected.value.length === 0) return
  emit('confirm', [...selected.value])
  selected.value = []
}

/** 不确定性分类的展示文案；解析不到分类时返回空串。 */
function uncertaintyText(item: MakeupAnalysisItem): string {
  return item.uncertainty ? UNCERTAINTY_LABEL[item.uncertainty] : ''
}

/**
 * 「本学期有教学班」文案。
 *
 * ⚠️ 如实说明这是**按教学班数据推断**，⛔ 不写成后端结论。
 */
function availabilityText(item: MakeupAnalysisItem): string {
  return item.openedThisSemester ? '本学期有教学班' : '本学期无教学班'
}
</script>

<template>
  <section class="match" data-testid="case-a-makeup-gap">
    <p class="match__summary" data-testid="case-a-makeup-summary">
      已满足 <strong>{{ satisfied.length }}</strong> 门 ·
      待确认 <strong>{{ needConfirmation.length }}</strong> 门 ·
      缺失 <strong>{{ missing.length }}</strong> 门
    </p>
    <p class="match__lead">
      系统把你的成绩单与<strong>学校培养方案</strong>逐项匹配：
      已修的直接视为已满足；有记录但无法自动判定的需你确认；没有记录的属于未完成。
      判定与理由均由培养方案匹配引擎给出，页面不会替你推断课程等价关系。
    </p>

    <!-- ① 待确认 -->
    <h4 class="match__section" data-testid="case-a-needs-conversion-title">
      待确认（{{ needConfirmation.length }}）
    </h4>
    <p class="match__hint">{{ VIEW_STATUS_HINT.need_confirmation }}</p>

    <div v-if="needConfirmation.length > 0" class="match__grid" data-testid="case-a-makeup-cards">
      <article
        v-for="item in needConfirmation"
        :key="item.courseId"
        class="match-card"
        data-testid="case-a-makeup-card"
      >
        <div class="match-card__head">
          <strong class="match-card__name">{{ item.courseName }}</strong>
          <span class="match-card__id">{{ item.courseId }}</span>
        </div>
        <dl class="match-card__meta">
          <div>
            <dt>学分</dt>
            <dd>{{ item.credit }}</dd>
          </div>
          <div>
            <dt>当前状态</dt>
            <dd>{{ VIEW_STATUS_LABEL[item.status] }}</dd>
          </div>
          <div>
            <dt>教学安排</dt>
            <dd>{{ availabilityText(item) }}</dd>
          </div>
        </dl>

        <!-- 后端给出的「为什么需要确认」，⛔ 原样展示、⛔ 不在前端编造 -->
        <p class="match-card__reason" data-testid="case-a-makeup-reason">
          <strong>为什么需要确认：</strong>{{ item.reason }}
        </p>
        <p
          v-if="item.uncertainty"
          class="match-card__cause"
          data-testid="case-a-makeup-cause"
        >
          原因分类：{{ uncertaintyText(item) }}
        </p>

        <details v-if="item.sourceEvidence" class="match-card__evidence">
          <summary data-testid="case-a-makeup-evidence-toggle">查看判定依据</summary>
          <p data-testid="case-a-makeup-evidence">{{ item.sourceEvidence }}</p>
        </details>

        <div class="match-card__actions">
          <label class="match-card__check">
            <input
              type="checkbox"
              :checked="isSelected(item.courseId)"
              :aria-label="`选择 ${item.courseName}`"
              data-testid="case-a-makeup-checkbox"
              @change="toggle(item.courseId)"
            />
            <span>选择</span>
          </label>
          <button
            class="button button--small"
            type="button"
            data-testid="case-a-makeup-convert"
            @click="confirmOne(item.courseId)"
          >
            确认可转换
          </button>
        </div>
      </article>
    </div>
    <p v-else class="match__empty">需要确认的课程都已处理完毕。</p>

    <div v-if="needConfirmation.length > 0" class="match__footer">
      <span role="status" aria-live="polite" data-testid="case-a-makeup-selected-count">
        已选择 {{ selected.length }} 门
      </span>
      <button
        class="button"
        type="button"
        :disabled="selected.length === 0"
        data-testid="case-a-makeup-confirm-selection"
        @click="confirmSelected"
      >
        确认选择
      </button>
    </div>

    <!-- ② 缺失（补修来源） -->
    <h4 class="match__section">缺失（{{ missing.length }}）</h4>
    <p class="match__hint">{{ VIEW_STATUS_HINT.missing }}</p>
    <ul v-if="missing.length > 0" class="match__list" data-testid="case-a-makeup-missing-list">
      <li
        v-for="item in missing"
        :key="item.courseId"
        data-testid="case-a-makeup-gap-item"
      >
        <span class="match__name">{{ item.courseName }}</span>
        <span class="match__id">{{ item.courseId }}</span>
        <span class="match__kind">{{ item.credit }} 学分</span>
        <span class="match__avail" data-testid="case-a-makeup-availability">
          {{ availabilityText(item) }}
        </span>
      </li>
    </ul>
    <p v-else class="match__empty">没有缺失的培养要求。</p>

    <!-- ③ 已满足 -->
    <h4 class="match__section">已满足（{{ satisfied.length }}）</h4>
    <p class="match__hint">{{ VIEW_STATUS_HINT.satisfied }}</p>
    <ul v-if="satisfied.length > 0" class="match__list" data-testid="case-a-makeup-satisfied-list">
      <li
        v-for="item in satisfied"
        :key="item.courseId"
        data-testid="case-a-makeup-satisfied-item"
      >
        <span class="match__name">{{ item.courseName }}</span>
        <span class="match__id">{{ item.courseId }}</span>
        <span class="match__kind">{{ item.credit }} 学分</span>
        <span class="match__state">
          {{ item.studentConfirmed ? '✅ 你已确认可转换' : '✅ 已满足' }}
        </span>
        <button
          v-if="confirmedSet.has(item.courseId)"
          class="match__undo"
          type="button"
          aria-label="撤销该课程的可转换确认"
          data-testid="case-a-makeup-undo"
          @click="emit('undo', item.courseId)"
        >
          撤销
        </button>
        <span v-else />
      </li>
    </ul>
    <p v-else class="match__empty">暂无已满足记录。</p>
  </section>
</template>

<style scoped>
.match__summary {
  margin: 0 0 4px;
  font-size: 14px;
}

.match__lead {
  margin: 0 0 14px;
  color: #55606e;
  font-size: 13px;
  line-height: 1.6;
}

.match__section {
  margin: 16px 0 4px;
  font-size: 14px;
}

.match__hint {
  margin: 0 0 10px;
  color: #6b7683;
  font-size: 12px;
  line-height: 1.6;
}

.match__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.match-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--border, #dde3ea);
  border-radius: var(--radius, 8px);
  background: #fff;
}

.match-card__head {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.match-card__name {
  font-size: 15px;
}

.match-card__id {
  color: #6b7683;
  font-size: 12px;
}

.match-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  margin: 0;
}

.match-card__meta dt {
  color: #6b7683;
  font-size: 12px;
}

.match-card__meta dd {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
}

.match-card__reason {
  margin: 0;
  color: #33404f;
  font-size: 12px;
  line-height: 1.6;
}

.match-card__cause {
  margin: 0;
  color: #8a5a00;
  font-size: 12px;
  font-weight: 600;
}

.match-card__evidence {
  font-size: 12px;
}

.match-card__evidence summary {
  color: #1a5fb4;
  cursor: pointer;
}

.match-card__evidence p {
  margin: 6px 0 0;
  color: #6b7683;
  font-size: 11px;
  line-height: 1.6;
  word-break: break-all;
}

.match-card__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
}

.match-card__check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
}

.match-card__check input {
  width: 18px;
  height: 18px;
  accent-color: #3276df;
}

.match__empty {
  margin: 0;
  color: #55606e;
  font-size: 13px;
}

.match__footer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
  font-size: 13px;
}

.match__footer button:disabled {
  opacity: 0.5;
  cursor: default;
}

.match__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid #eef2f6;
}

.match__list li {
  display: grid;
  grid-template-columns: 1fr auto auto auto auto;
  gap: 12px;
  align-items: center;
  padding: 7px 2px;
  border-bottom: 1px solid #eef2f6;
  font-size: 13px;
}

.match__name {
  font-weight: 600;
}

.match__id,
.match__kind {
  color: #6b7683;
  font-size: 12px;
}

.match__avail {
  color: #1a5fb4;
  font-size: 12px;
  white-space: nowrap;
}

.match__state {
  color: #8a5a00;
  font-size: 12px;
  white-space: nowrap;
}

.match__undo {
  padding: 0;
  border: none;
  background: none;
  color: #1a5fb4;
  cursor: pointer;
  font-size: 12px;
  text-decoration: underline;
}
</style>
