<script setup lang="ts">
import { computed } from 'vue'
import { formatWeekday } from '../utils/labels'
import type { AvoidTimeRow, InvalidatableField, UserInputForm } from '../state/userInput'
import {
  addAvoidTime,
  normalizeMaxCreditInput,
  removeAvoidTime,
  updateAvoidTime,
} from '../state/userInput'

/**
 * 学生的选课需求表单（面向学生的文案，**底层字段不变**）。
 *
 * 边界：
 * - 只编辑公共 `Preference` 的 5 个字段：`max_credit` / `avoid_cross_campus` /
 *   `preferred_courses` / `avoid_times` / `notes`，**不新增字段、不改 Schema**；
 * - 主界面**不出现** `max_credit` 等内部字段名（这些名字只在代码与 Schema 里存在）；
 * - 意向课程（`preferred_courses`）由 `IntentCourseSearch.vue` 以**课程级搜索**方式编辑，
 *   本组件只展示已选结果，避免出现"输入课程号"这种技术交互；
 * - 组件自身持有草稿以便输入过程流畅，每次变更把**完整草稿**同步给父级
 *   （父级持有唯一真源并负责序列化）；
 * - ⛔ 不做冲突检测、不判断学分是否可达、不生成任何补修结论。
 *
 * 与只读的 `PreferencePanel.vue` 分工：
 * `PreferencePanel` 继续负责展示后端返回的 Preference；本组件只负责**创建用户输入**。
 */
const props = defineProps<{
  /** 父级当前的表单状态。 */
  form: UserInputForm
  /**
   * 已加入的意向课程号。
   *
   * 缺省时回退到 `form.preference.preferredCourses`（旧页面仍然只维护表单自身），
   * 这样本组件可以同时服务 Case A 页面（课程级搜索写入）与既有 Mock 页面。
   */
  preferredCourses?: readonly string[]
}>()

const emit = defineEmits<{
  (event: 'update:form', value: UserInputForm): void
  (event: 'remove-preferred', courseId: string): void
}>()

/** 展示用：优先用父级传入的列表，否则用表单自身的字段（同一个字段，**不新增字段**）。 */
const selectedPreferredCourses = computed<readonly string[]>(
  () => props.preferredCourses ?? props.form.preference.preferredCourses,
)

/** 没有父级监听 `remove-preferred` 时（旧页面），直接改表单自身。 */
function removePreferredCourseRow(courseId: string): void {
  if (props.preferredCourses === undefined) {
    patchPreference({
      preferredCourses: props.form.preference.preferredCourses.filter((item) => item !== courseId),
    })
    return
  }
  emit('remove-preferred', courseId)
}

const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const
const SECTION_NUMBERS = Array.from({ length: 13 }, (_, index) => index + 1)

function patchPreference(patch: Partial<UserInputForm['preference']>): void {
  emit('update:form', {
    ...props.form,
    preference: { ...props.form.preference, ...patch },
  })
}

/**
 * 学分上限输入的处理。
 *
 * ⚠️ 不能只把非法输入归一化成 `null`：那样它与"未触碰 / 主动留空"无法区分，
 * 表单会被误判为合法并允许提交。因此归一化的同时必须留下显式的 invalid 标记。
 */
function onMaxCreditInput(event: Event): void {
  const { value, invalid } = normalizeMaxCreditInput((event.target as HTMLInputElement).value)
  const invalidFields: InvalidatableField[] = invalid
    ? props.form.invalidFields.includes('maxCredit')
      ? props.form.invalidFields
      : [...props.form.invalidFields, 'maxCredit']
    : props.form.invalidFields.filter((item) => item !== 'maxCredit')

  // ⚠️ 必须**一次性**用同一个新状态 emit：
  // 分两次（先 patchPreference 再 setFieldInvalid）第二次会展开**过期的** props.form，
  // 把刚写入的取值覆盖掉。
  emit('update:form', {
    ...props.form,
    preference: { ...props.form.preference, maxCredit: value },
    invalidFields,
  })
}

const maxCreditInvalid = computed(() => props.form.invalidFields.includes('maxCredit'))

function onAvoidCrossCampusChange(event: Event): void {
  patchPreference({ avoidCrossCampus: (event.target as HTMLInputElement).checked })
}

function onNotesInput(event: Event): void {
  patchPreference({ notes: (event.target as HTMLTextAreaElement).value })
}

/* 意向课程：由课程级搜索组件写入，这里只负责移除。 */
function onRemovePreferredCourse(courseId: string): void {
  removePreferredCourseRow(courseId)
}

/* 回避时段 */
function onAddAvoidTime(): void {
  patchPreference({ avoidTimes: addAvoidTime(props.form.preference.avoidTimes) })
}

function onRemoveAvoidTime(key: number): void {
  patchPreference({ avoidTimes: removeAvoidTime(props.form.preference.avoidTimes, key) })
}

function onAvoidTimeField(key: number, field: keyof Omit<AvoidTimeRow, 'key'>, event: Event): void {
  const value = Number((event.target as HTMLInputElement | HTMLSelectElement).value)
  patchPreference({
    avoidTimes: updateAvoidTime(props.form.preference.avoidTimes, key, { [field]: value }),
  })
}
</script>

<template>
  <div class="uig-form">
    <div class="uig-grid">
      <!-- 学分上限（底层 max_credit） -->
      <label class="uig-field">
        <span class="uig-field__label">本学期最多希望修多少学分？</span>
        <span class="uig-inline">
          <input
            class="input-text"
            data-testid="max-credit-input"
            type="text"
            inputmode="decimal"
            :value="form.preference.maxCredit ?? ''"
            placeholder="例如 24"
            @input="onMaxCreditInput"
          />
          <span class="uig-unit">学分</span>
        </span>
        <span v-if="maxCreditInvalid" class="uig-field__error" data-testid="max-credit-error">
          请输入不小于 0 的数字；系统不会猜测或补全学分上限，表单将保持不可提交。
        </span>
        <span v-else class="uig-field__hint">用于控制本学期学习负担。留空表示暂不设定。</span>
      </label>

      <!-- 校区偏好（底层 avoid_cross_campus） -->
      <div class="uig-field">
        <span class="uig-field__label">校区安排</span>
        <label class="uig-check">
          <input
            data-testid="avoid-cross-campus-input"
            type="checkbox"
            :checked="form.preference.avoidCrossCampus"
            @change="onAvoidCrossCampusChange"
          />
          <span>尽量避免跨校区上课</span>
        </label>
        <span class="uig-field__hint">
          仅记录你的偏好；是否作为正式求解约束执行，以生成结果中的待确认事项为准。
        </span>
      </div>

      <!-- 意向课程（底层 preferred_courses）：由上方课程级搜索写入 -->
      <div class="uig-field uig-field--wide">
        <span class="uig-field__label">我的意向课程</span>
        <div v-if="selectedPreferredCourses.length > 0" class="chip-group">
          <span
            v-for="courseId in selectedPreferredCourses"
            :key="courseId"
            class="chip chip--pref mono"
            data-testid="preferred-course-chip"
          >
            {{ courseId }}
            <button
              class="uig-chip-remove"
              type="button"
              :aria-label="`移除 ${courseId}`"
              @click="onRemovePreferredCourse(courseId)"
            >
              ×
            </button>
          </span>
        </div>
        <span v-else class="uig-field__hint">
          还没有意向课程。在上方“你还想学习哪些课程？”里搜索并加入；同一门课不会重复加入。
        </span>
      </div>

      <!-- 回避时段（底层 avoid_times） -->
      <div class="uig-field uig-field--wide">
        <span class="uig-field__label">我不方便上课的时间</span>
        <div class="uig-avoid-list">
          <div
            v-for="row in form.preference.avoidTimes"
            :key="row.key"
            class="uig-avoid-row"
            data-testid="avoid-time-row"
          >
            <label class="uig-avoid-cell">
              <span>星期</span>
              <select
                class="input-text"
                data-testid="avoid-time-weekday"
                :value="row.weekday"
                @change="onAvoidTimeField(row.key, 'weekday', $event)"
              >
                <option v-for="day in WEEKDAYS" :key="day" :value="day">
                  {{ formatWeekday(day) }}
                </option>
              </select>
            </label>
            <label class="uig-avoid-cell">
              <span>起始节</span>
              <select
                class="input-text"
                data-testid="avoid-time-start"
                :value="row.start_section"
                @change="onAvoidTimeField(row.key, 'start_section', $event)"
              >
                <option v-for="n in SECTION_NUMBERS" :key="n" :value="n">{{ n }}</option>
              </select>
            </label>
            <label class="uig-avoid-cell">
              <span>结束节</span>
              <select
                class="input-text"
                data-testid="avoid-time-end"
                :value="row.end_section"
                @change="onAvoidTimeField(row.key, 'end_section', $event)"
              >
                <option v-for="n in SECTION_NUMBERS" :key="n" :value="n">{{ n }}</option>
              </select>
            </label>
            <button
              class="button button--small"
              type="button"
              data-testid="avoid-time-remove"
              @click="onRemoveAvoidTime(row.key)"
            >
              删除
            </button>
          </div>
          <span v-if="form.preference.avoidTimes.length === 0" class="uig-field__hint">
            还没有添加。例如：周三 第9-10节 不方便上课。
          </span>
        </div>
        <button
          class="button button--small"
          type="button"
          data-testid="avoid-time-add"
          @click="onAddAvoidTime"
        >
          + 添加时间
        </button>
      </div>

      <!-- 备注（底层 notes） -->
      <label class="uig-field uig-field--wide">
        <span class="uig-field__label">还有什么希望系统考虑？</span>
        <textarea
          class="input-text uig-textarea"
          data-testid="notes-input"
          rows="2"
          :value="form.preference.notes ?? ''"
          placeholder="例如：希望课程尽量集中在上午"
          @input="onNotesInput"
        ></textarea>
        <span class="uig-field__hint">
          备注会原样带给规划系统，但不会被解析成结构化约束；是否被满足以生成结果为准。
        </span>
      </label>
    </div>
  </div>
</template>
