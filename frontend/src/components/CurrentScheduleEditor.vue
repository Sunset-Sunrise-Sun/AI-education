<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { summarizeCredits, matchesSearchTokens } from '../utils/courseSearch'
import { applyBatchAdd, describeConflicts, evaluateBatchAdd } from '../utils/scheduleBulkAdd'
import { compactMeetingSummary } from '../utils/weeklySchedule'
import type { CourseOffering } from '../types/contracts'
import CurrentScheduleList from './CurrentScheduleList.vue'

const props = withDefaults(defineProps<{
  offerings: readonly CourseOffering[]
  currentSchedule: readonly CourseOffering[]
  /**
   * 显式规划学期（`form.semester`）。
   *
   * `SelectedClass` 没有 `semester` 字段，教学班身份只能是
   * **semester + course_id + class_id**，所以学期必须由父级显式传入，
   * ⛔ 不得从系统日期推断。
   */
  semester: string
  /** 手工确认被作废时的提示文案（由父级提供）。 */
  attestationNotice?: string
  /**
   * 是否在本组件内渲染「已确认加入的当前课表」区块。
   *
   * ⚠️ 默认 true（向后兼容：既有测试与既有用法一字不改）。
   *    父级传 false 时本区块隐藏，由父级在「上传课表截图 + 识别结果」之后渲染，
   *    ⛔ 不改任何数据流，⛔ 不删任何 DOM。
   */
  showCurrentSchedule?: boolean
}>(), { showCurrentSchedule: true })

/**
 * 教学班身份（架构口径）：**semester + course_id + class_id**。
 *
 * ⚠️ `(course_id, class_id)` 两元组**不是**身份：
 * 同名课程号在不同学期是不同条目，⛔ 不得跨学期合并。
 * 学期取值优先用户填写的条目学期，其次退回显式传入的规划学期。
 */
/**
 * 已经加入当前课表的教学班身份集合。
 *
 * ⚠️ 用途仅限**展示状态**：搜索列表里把已加入的班显示为「✓ 已确认」，避免重复加入。
 *   ⛔ 不改动搜索/过滤/排序逻辑，⛔ 不改 `current_schedule` 的数据结构，
 *   ⛔ 不新增任何身份认定语义 —— 这里的"确认"只表示"我已把它放进当前课表"。
 */
const confirmedScheduleIds = computed(
  () => new Set(props.currentSchedule.map((item) => identity(item))),
)

function isConfirmedInSchedule(offering: CourseOffering): boolean {
  return confirmedScheduleIds.value.has(identity(offering))
}

/**
 * 撤回：把该教学班从当前课表移除。
 * ⚠️ 复用父级既有的移除路径（`removeCurrentScheduleOffering` + 作废手工确认），
 *   ⛔ 不新增任何身份或来源语义。
 */
function undoSingle(offering: CourseOffering): void {
  emit('remove', offering)
}

/**
 * 把**已有**的教学班搜索定位到给定关键词。
 * ⚠️ 供父组件在「图片识别 → 未识别课程 → 搜索教学班」时调用；
 *   ⛔ 不新增第二套搜索逻辑，只是给既有搜索框设值并聚焦。
 */
const searchInputRef = ref<HTMLInputElement | null>(null)

/**
 * 子组件 CurrentScheduleList 的移除/清空回调。
 *
 * ⚠️ 布局调整后当前课表由子组件渲染，但**既有契约不变**：
 *   本组件仍然是「课表变更 → 发出 update:currentSchedule(+remove)」的唯一出口，
 *   并照旧设置提示文案、作废手工确认由父级统一处理。
 *   ⛔ 数据流与提示文案一字未改。
 */
function onListRemove(offering: CourseOffering): void {
  const next = props.currentSchedule.filter(
    (item) => identity(item) !== identity(offering),
  )
  commitSchedule(next, '已从当前课表移除。')
  emit('remove', offering)
}

function onListClear(): void {
  commitSchedule([], '当前课表已清空。')
  emit('clear')
}

function focusSearch(keyword: string): void {
  searchQuery.value = keyword
  batchNotice.value = ''
  void nextTick(() => searchInputRef.value?.focus())
}

defineExpose({ focusSearch })

function identity(offering: CourseOffering): string {
  return `${offering.semester || props.semester}::${offering.course_id}::${offering.class_id}`
}

/**
 * ⚠️ 只发一个事件：新课表。
 *   作废手工确认（attestation）由父级调用 `invalidateManualAttestation` 统一处理，
 *   ⛔ 本组件不自己改表单、⛔ 不发第二个事件（避免父子状态双写）。
 */
const emit = defineEmits<{
  (event: 'update:currentSchedule', value: CourseOffering[]): void
  (event: 'remove', offering: CourseOffering): void
  (event: 'clear'): void
}>()

/** 搜索结果上限（⛔ 保持既有约束：不一次性铺开真实数据）。 */
const SEARCH_LIMIT = 20

const searchQuery = ref('')
const campusFilter = ref('')
const weekdayFilter = ref('')
const selectedIdentities = ref<string[]>([])
const conflictMessage = ref('')
const batchNotice = ref('')
const clearOpen = ref(false)
const showAll = ref(false)

/* --------------------------------------------------------------------- *
 * 课表截图：上传 / 预览 / 移除 / 待识别（本轮补齐）
 *
 * ⚠️ 这些状态**完全不参与** `current_schedule` 的产出：
 *    勾选与手工添加仍是写入课表的**唯一**途径。
 * --------------------------------------------------------------------- */

const campusOptions = computed(() => {
  const campuses = new Set<string>()
  for (const item of props.offerings) {
    for (const meeting of item.meetings) {
      if (meeting.campus?.trim()) campuses.add(meeting.campus.trim())
    }
  }
  return [...campuses].sort((a, b) => a.localeCompare(b, 'zh-CN'))
})

const normalizedQuery = computed(() => searchQuery.value.trim())

const filteredOfferings = computed(() => {
  if (!normalizedQuery.value) return []
  return props.offerings
    .filter((item) => {
      // 空格分词：每个词都必须字面命中真实字段
      if (!matchesSearchTokens(item, normalizedQuery.value)) return false
      if (
        campusFilter.value &&
        !item.meetings.some((meeting) => meeting.campus === campusFilter.value)
      ) {
        return false
      }
      if (
        weekdayFilter.value &&
        !item.meetings.some((meeting) => String(meeting.weekday) === weekdayFilter.value)
      ) {
        return false
      }
      return true
    })
    .slice(0, SEARCH_LIMIT)
})

const groupedOfferings = computed(() => {
  const groups = new Map<
    string,
    { key: string; courseId: string; courseName: string; credit: number | null; items: CourseOffering[] }
  >()
  for (const item of filteredOfferings.value) {
    const key = `${item.course_id}::${item.course_name}`
    const existing = groups.get(key)
    if (existing) {
      existing.items.push(item)
      continue
    }
    groups.set(key, {
      key,
      courseId: item.course_id,
      courseName: item.course_name,
      credit: item.credit ?? null,
      items: [item],
    })
  }
  return [...groups.values()]
})

/* ---------------------------------------------------------------- 当前课表 */

const summary = computed(() => summarizeCredits(props.currentSchedule))

/** 默认折叠为紧凑摘要；"查看全部"展开完整行。 */
const visibleSchedule = computed(() =>
  showAll.value ? props.currentSchedule : props.currentSchedule.slice(0, 3),
)

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

/* ------------------------------------------------------------ 批量选择状态 */

const selectedSet = computed(() => new Set(selectedIdentities.value))

function isSelectedForBatch(offering: CourseOffering): boolean {
  return selectedSet.value.has(identity(offering))
}

function toggleBatchSelection(offering: CourseOffering): void {
  conflictMessage.value = ''
  batchNotice.value = ''
  const key = identity(offering)
  selectedIdentities.value = selectedSet.value.has(key)
    ? selectedIdentities.value.filter((item) => item !== key)
    : [...selectedIdentities.value, key]
}

const selectedOfferings = computed(() =>
  props.offerings.filter((offering) => selectedSet.value.has(identity(offering))),
)

/* ------------------------------------------------------------------ 加入 */

function commitSchedule(next: CourseOffering[], notice: string): void {
  emit('update:currentSchedule', next)
  batchNotice.value = notice
}

function addSingle(offering: CourseOffering): void {
  conflictMessage.value = ''
  if (props.currentSchedule.some((item) => identity(item) === identity(offering))) return
  const evaluation = evaluateBatchAdd(props.currentSchedule, [offering])
  if (evaluation.conflicts.length > 0) {
    // 同一门课已有另一个教学班 → fail closed，不自动替换
    conflictMessage.value = describeConflicts(evaluation.conflicts)
    return
  }
  const next = applyBatchAdd(props.currentSchedule, evaluation.acceptable, props.offerings)
  commitSchedule(next, '已加入当前课表。')
}

function addBatch(): void {
  conflictMessage.value = ''
  const evaluation = evaluateBatchAdd(props.currentSchedule, selectedOfferings.value)
  if (evaluation.conflicts.length > 0) {
    // fail closed：⛔ 不替用户挑选保留哪一个教学班
    conflictMessage.value = describeConflicts(evaluation.conflicts)
    return
  }
  const next = applyBatchAdd(props.currentSchedule, evaluation.acceptable, props.offerings)
  const added = next.length - props.currentSchedule.length
  selectedIdentities.value = []
  commitSchedule(
    next,
    added > 0 ? `已批量加入 ${added} 个教学班。` : '所选教学班都已在当前课表中。',
  )
}

function removeOffering(offering: CourseOffering): void {
  const next = props.currentSchedule.filter((item) => identity(item) !== identity(offering))
  conflictMessage.value = ''
  selectedIdentities.value = selectedIdentities.value.filter((key) => key !== identity(offering))
  commitSchedule(next, '已从当前课表移除。')
}

/* ------------------------------------------------------------ 清空（二次确认） */

function confirmClear(): void {
  clearOpen.value = false
  selectedIdentities.value = []
  showAll.value = false
  conflictMessage.value = ''
  commitSchedule([], '当前课表已清空。')
}
</script>

<template>
  <div class="cse" data-testid="case-a-schedule-editor">
    <!-- 搜索 -->
    <div class="cse__search-panel">
      <label class="cse__search">
        <span>搜索你已经选中的课程</span>
        <input
          ref="searchInputRef"
            v-model="searchQuery"
          data-testid="case-a-offering-search"
          class="input-text"
          type="search"
          placeholder="搜索课程名称、课程号、教学班号或任课教师，可用空格分词"
        />
      </label>
      <div class="cse__filters">
        <label>
          <span>校区</span>
          <select v-model="campusFilter" data-testid="case-a-campus-filter" class="input-text">
            <option value="">全部校区</option>
            <option v-for="campus in campusOptions" :key="campus" :value="campus">{{ campus }}</option>
          </select>
        </label>
        <label>
          <span>上课日</span>
          <select v-model="weekdayFilter" data-testid="case-a-weekday-filter" class="input-text">
            <option value="">全部上课日</option>
            <option value="1">周一</option>
            <option value="2">周二</option>
            <option value="3">周三</option>
            <option value="4">周四</option>
            <option value="5">周五</option>
            <option value="6">周六</option>
            <option value="7">周日</option>
          </select>
        </label>
      </div>
    </div>

    <p v-if="!normalizedQuery" class="cse__empty">
      输入课程名称、课程号、教学班号或任课教师开始搜索；支持空格分词（例如「数据 结构」）。
    </p>
    <p v-else-if="filteredOfferings.length === 0" class="cse__empty">
      没有找到匹配的教学班，可调整筛选条件或手工添加。
    </p>

    <div v-if="groupedOfferings.length > 0" class="cse__groups">
      <section
        v-for="group in groupedOfferings"
        :key="group.key"
        class="cse__group"
        data-testid="case-a-course-group"
      >
        <header class="cse__group-head">
          <h3>{{ group.courseName }}</h3>
          <div class="cse__group-meta">
            <span>{{ group.courseId }}</span>
            <span v-if="group.credit !== null">{{ group.credit }} 学分</span>
            <span>{{ group.items.length }} 个匹配教学班</span>
          </div>
        </header>

        <article
          v-for="item in group.items"
          :key="identity(item)"
          class="cse__row"
          data-testid="case-a-search-result"
        >
          <label class="cse__check">
            <input
              type="checkbox"
              data-testid="case-a-result-checkbox"
              :checked="isSelectedForBatch(item)"
              @change="toggleBatchSelection(item)"
            />
          </label>
          <div class="cse__row-main">
            <div class="cse__row-title">
              <strong>教学班 {{ item.class_id }}</strong>
              <span class="cse__teacher">{{ teacherText(item) }}</span>
            </div>
            <p class="cse__row-meta">{{ compactMeetingSummary(item.meetings) }}</p>
          </div>
          <span
            v-if="isConfirmedInSchedule(item)"
            class="cse__confirmed"
            data-testid="case-a-result-confirmed"
          >
            ✓ 已确认 已加入当前课表
          </span>
          <button
            v-if="isConfirmedInSchedule(item)"
            class="button button--small button--ghost"
            type="button"
            data-testid="case-a-result-undo"
            @click="undoSingle(item)"
          >
            撤回
          </button>
          <button
            v-else
            class="button button--small"
            type="button"
            data-testid="case-a-result-add"
            @click="addSingle(item)"
          >
            加入当前课表
          </button>
        </article>
      </section>
      <p class="cse__hint">最多显示 {{ SEARCH_LIMIT }} 个匹配教学班，请继续输入关键词缩小范围。</p>
    </div>

    <!-- 批量加入 -->
    <div v-if="selectedOfferings.length > 0" class="cse__batch" data-testid="case-a-batch-bar">
      <span>已选择 {{ selectedOfferings.length }} 个教学班</span>
      <button class="button button--small" type="button" data-testid="case-a-batch-add" @click="addBatch">
        批量加入当前课表
      </button>
    </div>

    <p v-if="conflictMessage" class="cse__error" role="alert" data-testid="case-a-batch-conflict">
      {{ conflictMessage }}
    </p>
    <p v-if="batchNotice" class="cse__success" data-testid="case-a-batch-notice">{{ batchNotice }}</p>

    <!--
      当前课表（已确认加入）。
      ⚠️ 布局调整（最终展示优化）：父级可传 `show-current-schedule=false`，
         由父级在「上传课表截图 + 识别结果」之后渲染本区块，
         让「识别 → 确认 → 课表实时更新」形成可感知闭环。
         ⛔ DOM 一字未删，只是交由父级决定显隐；默认 true 保持向后兼容。
    -->
    <!--
      当前课表（已确认加入）。
      ⚠️ 布局调整（最终展示优化）：父级可传 `show-current-schedule=false`，
         改由父级在「上传课表截图 + 识别结果」之后渲染，
         让「识别 → 确认 → 课表实时更新」形成可感知闭环。
         ⛔ 区块本身与数据流未变，只是换了渲染位置。
    -->
    <CurrentScheduleList
      v-if="showCurrentSchedule"
      :current-schedule="currentSchedule"
      :attestation-notice="attestationNotice"
      @remove="onListRemove($event)"
      @clear="onListClear()"
    />


  </div>
</template>

<style scoped>
.cse {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cse__search-panel {
  display: flex;
  align-items: end;
  gap: 14px;
  flex-wrap: wrap;
  padding: 14px;
  background: #f8fbff;
  border: 1px solid #d9e6f7;
  border-radius: var(--radius);
}

.cse__search {
  display: flex;
  flex: 1 1 520px;
  flex-direction: column;
  gap: 8px;
  font-weight: 600;
}

.cse__search .input-text {
  width: 100%;
  padding: 11px 14px;
  font-size: 14px;
}

.cse__filters {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.cse__filters label {
  display: flex;
  min-width: 130px;
  flex-direction: column;
  gap: 6px;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.cse__filters .input-text {
  padding: 9px 30px 9px 10px;
}

.cse__empty,
.cse__hint,
.cse__row-meta,
.cse__summary,
.cse__item-meta,
.cse__warn {
  margin: 0;
}

.cse__empty {
  padding: 14px 16px;
  color: var(--text-muted);
  background: #f8fafc;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
}

.cse__hint {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.cse__groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cse__group {
  overflow: hidden;
  border: 1px solid #d8e3f0;
  border-radius: var(--radius);
  background: #fff;
}

.cse__group-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: #f6f9fd;
  border-bottom: 1px solid #e2e8f0;
}

.cse__group-head h3 {
  margin: 0;
  color: #3276df;
  font-size: 16px;
}

.cse__group-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 5px;
}

.cse__group-meta span {
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef4fd;
  color: #64748b;
  font-size: 11px;
}

.cse__row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  border-bottom: 1px solid #edf1f6;
}

.cse__row:last-child {
  border-bottom: 0;
}

.cse__check {
  display: flex;
  align-items: center;
}

.cse__check input {
  width: 16px;
  height: 16px;
}

.cse__row-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 4px;
}

.cse__row-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.cse__teacher,
.cse__confirmed {
  flex: none;
  padding: 4px 10px;
  border: 1px solid #2e7d32;
  border-radius: 6px;
  background: #e8f5e9;
  color: #1b5e20;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.cse__row-meta {
  color: #64748b;
  font-size: 12px;
}

.cse__batch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 16px;
  border: 1px solid #bfdbfe;
  border-radius: var(--radius);
  background: #eff6ff;
  font-weight: 700;
  color: #1e40af;
}

.cse__error {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
  line-height: 1.7;
}

.cse__success {
  margin: 0;
  color: #15803d;
  font-size: 13px;
  font-weight: 600;
}

.cse__current {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.cse__current-head h3 {
  margin: 0 0 4px;
  font-size: 16px;
}

.cse__summary-lead {
  margin: 0 0 4px;
  color: #33404f;
  font-size: 13px;
}

.cse__summary-safe {
  margin: 0 0 6px;
  color: #8a5a00;
  font-size: 12px;
}

.cse__summary {
  color: var(--text);
  font-weight: 600;
}

.cse__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.cse__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
}

.cse__item-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.cse__item-id,
.cse__item-meta {
  color: var(--text-muted);
  font-size: 12px;
}

.cse__warn {
  color: #b45309;
  font-size: 12px;
  font-weight: 600;
}

.cse__remove {
  background: #64748b;
}

.cse__actions {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.cse__link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-weight: 600;
  cursor: pointer;
}

.cse__link--danger {
  color: #b91c1c;
}

.cse__dialog {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid #f3d9a4;
  border-radius: var(--radius);
  background: #fffdf5;
}

.cse__dialog p {
  margin: 0;
  line-height: 1.7;
}

.cse__dialog-actions {
  display: flex;
  gap: 10px;
}

/* ---- 课表截图上传（本轮补齐；⛔ 仅追加，不改上方既有规则） ---- */
/* 「移除截图」跟在文件名行下方，避免与预览错位 */
</style>
