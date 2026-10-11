<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { summarizeCredits, matchesSearchTokens } from '../utils/courseSearch'
import { applyBatchAdd, describeConflicts, evaluateBatchAdd } from '../utils/scheduleBulkAdd'
import { compactMeetingSummary } from '../utils/weeklySchedule'
import type { CourseOffering } from '../types/contracts'

/**
 * 当前课表录入区（Phase 1：批量录入体验）。
 *
 * 边界：
 * - 搜索只匹配**真实字段**（课程名 / 课程号 / 教学班号 / 任课教师），支持空格分词；
 *   ⛔ 无拼音、无 embedding、无 LLM、⛔ 不做语义扩展；
 * - 结果上限固定 20 条，⛔ 不一次性铺开；
 * - 批量加入复用既有 `toggleCurrentScheduleOffering`（经 `applyBatchAdd`），
 *   ⛔ 不绕过重复检查；同一门课出现多个教学班时 **fail closed** 并提示用户先保留一个；
 * - `meetings = []` 使用中性文案（⛔ 不等于没有课 / 无冲突）；
 * - 教师为空显示"任课教师：待核验"（⛔ 不造教师数据）；
 * - ⛔ 本轮**不做**截图识别：入口只弹说明，不上传、不 OCR、不调用模型。
 */
/** 允许的截图类型（只做**本地预览**，⛔ 不上传、⛔ 不解析）。 */
const SHOT_ACCEPT = 'image/png,image/jpeg,image/webp'

/** 截图大小上限：8 MiB（仅本地校验，⛔ 不代表后端限制）。 */
const SHOT_MAX_BYTES = 8 * 1024 * 1024

/**
 * 课表截图识别的**通道状态**。
 *
 * ⚠️ 本项目**尚未接入任何图片识别服务**，因此这里恒为 `false`，
 * 页面只可能显示「待识别」，⛔ 不存在"识别成功"这种状态，
 * ⇒ ⛔ 永远不会出现任何据称来自截图解析的课程，也⛔ 不会自动勾选任何教学班。
 */
const SHOT_RECOGNITION_AVAILABLE = false

const props = defineProps<{
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
}>()

/**
 * 教学班身份（架构口径）：**semester + course_id + class_id**。
 *
 * ⚠️ `(course_id, class_id)` 两元组**不是**身份：
 * 同名课程号在不同学期是不同条目，⛔ 不得跨学期合并。
 * 学期取值优先用户填写的条目学期，其次退回显式传入的规划学期。
 */
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
const screenshotOpen = ref(false)

/* --------------------------------------------------------------------- *
 * 课表截图：上传 / 预览 / 移除 / 待识别（本轮补齐）
 *
 * ⚠️ 这些状态**完全不参与** `current_schedule` 的产出：
 *    勾选与手工添加仍是写入课表的**唯一**途径。
 * --------------------------------------------------------------------- */

/** 已选择的截图文件（⛔ 不读取其内容）。 */
const shotFile = ref<File | null>(null)
/** 本地预览 URL（`URL.createObjectURL`，换图或卸载时释放）。 */
const shotPreviewUrl = ref('')
/** 校验错误（只针对类型与大小）。 */
const shotError = ref('')

const shotFileName = (): string => shotFile.value?.name ?? ''

function releaseShotPreview(): void {
  if (shotPreviewUrl.value) {
    URL.revokeObjectURL(shotPreviewUrl.value)
    shotPreviewUrl.value = ''
  }
}

/**
 * 选择 / 更换截图。
 *
 * `event.target.value` 会被清空：否则连续选择**同一张图**不会触发 `change`。
 */
function onShotChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  shotError.value = ''

  if (!file) {
    return
  }
  if (!SHOT_ACCEPT.split(',').includes(file.type)) {
    // 只接受明确列出的图片类型；⛔ 不做扩展名猜测
    shotFile.value = null
    releaseShotPreview()
    shotError.value = '仅支持 PNG / JPEG / WebP 图片；未选择任何文件，也未读取其内容。'
    return
  }
  if (file.size > SHOT_MAX_BYTES) {
    shotFile.value = null
    releaseShotPreview()
    shotError.value = '截图不得超过 8 MiB；未读取其内容。'
    return
  }

  releaseShotPreview()
  shotFile.value = file
  // ⚠️ 预览只用浏览器本地对象 URL：⛔ 不发送到任何后端。
  shotPreviewUrl.value = URL.createObjectURL(file)
}

function clearShot(): void {
  releaseShotPreview()
  shotFile.value = null
  shotError.value = ''
}

function closeScreenshotDialog(): void {
  screenshotOpen.value = false
  // 关闭时清掉上一次的校验错误，否则重新打开会继续显示过期报错。
  // 已选中的截图保留（用户可能只是先关掉看看课表）。
  shotError.value = ''
}

function formatShotSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KiB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

onBeforeUnmount(releaseShotPreview)

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
          <button
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

    <!-- 当前课表 -->
    <section class="cse__current">
      <header class="cse__current-head">
        <h3>我的当前课表（{{ summary.count }}）</h3>
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
            <span v-if="item.source === 'manual-entry://current-schedule'" class="cse__warn">
              该课程信息由你本人填写，未经学校系统核验。
            </span>
          </div>
          <button
            class="button button--small cse__remove"
            type="button"
            data-testid="case-a-current-schedule-remove"
            @click="removeOffering(item)"
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

    <!-- 截图识别入口（本轮只放信息架构，⛔ 不上传 / 不 OCR / 不调用模型） -->
    <div class="cse__screenshot">
      <button
        class="cse__link"
        type="button"
        data-testid="case-a-screenshot-entry"
        @click="screenshotOpen = true"
      >
        上传课表截图，辅助识别
      </button>
    </div>

    <div v-if="screenshotOpen" class="cse__dialog" role="dialog" data-testid="case-a-screenshot-dialog">
      <p>
        上传课表截图，用于识别课程名称、星期和节次，并与教学班数据匹配；
        识别结果需由你确认后才能加入当前课表。
      </p>

      <!-- 图片选择：⛔ 只做本地校验与预览，不上传 -->
      <div class="cse__shot-field">
        <span class="cse__shot-label">课表截图（PNG / JPEG / WebP）</span>
        <input
          class="cse__shot-input"
          data-testid="case-a-screenshot-input"
          type="file"
          :accept="SHOT_ACCEPT"
          @change="onShotChange"
        />
        <span v-if="shotError" class="cse__error" data-testid="case-a-screenshot-error">
          {{ shotError }}
        </span>
        <span
          v-else-if="shotFile"
          class="cse__hint"
          data-testid="case-a-screenshot-name"
        >
          已选择：<code class="mono">{{ shotFileName() }}</code>
          （{{ formatShotSize(shotFile.size) }}；仅本地预览，未上传、未解析）
        </span>
        <span v-else class="cse__hint" data-testid="case-a-screenshot-empty">尚未选择截图。</span>

        <button
          v-if="shotFile"
          class="cse__link cse__link--danger"
          type="button"
          data-testid="case-a-screenshot-remove"
          @click="clearShot"
        >
          移除截图
        </button>
      </div>

      <!-- 预览：只用本地对象 URL，⛔ 不经过后端 -->
      <div
        v-if="shotPreviewUrl"
        class="cse__shot-preview"
        data-testid="case-a-screenshot-preview"
      >
        <img :src="shotPreviewUrl" :alt="`课表截图预览：${shotFileName()}`" />
      </div>

      <!--
        ⚠️ 待识别反馈：本项目**尚未接入图片识别服务** ⇒ 只有「待识别」。
        ⛔ 不显示任何识别结论，⛔ 不自动勾选任何教学班。
      -->
      <p
        v-if="shotFile"
        class="cse__warn"
        data-testid="case-a-screenshot-status"
        role="note"
      >
        <template v-if="!SHOT_RECOGNITION_AVAILABLE">
          <strong>状态：待识别。</strong>
          当前<strong>尚未接入图片识别服务</strong>，因此不会从截图中读出任何课程。
          请继续使用上方<strong>搜索加入</strong>或<strong>手工添加课程</strong>录入当前课表；
          ⛔ 本页不会用任何写死数据冒充识别结果。
        </template>
        <template v-else>
          <strong>状态：识别通道已启用。</strong>
        </template>
      </p>

      <div class="cse__dialog-actions">
        <button class="button button--small" type="button" data-testid="case-a-screenshot-close" @click="closeScreenshotDialog">
          关闭
        </button>
      </div>
    </div>
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
.cse__shot-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* 「移除截图」跟在文件名行下方，避免与预览错位 */
.cse__shot-field .cse__link--danger {
  align-self: flex-start;
  margin-top: 2px;
}

.cse__shot-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.cse__shot-input {
  font-size: 13px;
}

.cse__shot-preview {
  border: 1px solid #d9e6f7;
  border-radius: var(--radius);
  padding: 8px;
  background: #f8fbff;
  max-width: 520px;
}

.cse__shot-preview img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 4px;
}

.cse__screenshot {
  padding-top: 8px;
}
</style>
