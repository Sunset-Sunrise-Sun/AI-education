<script setup lang="ts">
import { ref, computed } from 'vue'
import { formatWeekday } from '../utils/labels'
import type { AvoidTimeRow, InvalidatableField, UserInputForm } from '../state/userInput'
import {
  addPreferredCourse,
  addAvoidTime,
  normalizeMaxCreditInput,
  removeAvoidTime,
  removePreferredCourse,
  updateAvoidTime,
} from '../state/userInput'

/**
 * 可编辑的 Preference 表单。
 *
 * 边界：
 * - 只编辑公共 `Preference` 的 5 个字段：`max_credit` / `avoid_cross_campus` /
 *   `preferred_courses` / `avoid_times` / `notes`，**不新增字段**；
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
}>()

const emit = defineEmits<{
  (event: 'update:form', value: UserInputForm): void
}>()

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

/* 意向课程 */
function onPreferredCourseInput(event: Event): void {
  preferredDraft.value = (event.target as HTMLInputElement).value
}

function commitPreferredCourse(): void {
  const next = addPreferredCourse(props.form.preference.preferredCourses, preferredDraft.value)
  patchPreference({ preferredCourses: next })
  preferredDraft.value = ''
}

function onRemovePreferredCourse(courseId: string): void {
  patchPreference({
    preferredCourses: removePreferredCourse(props.form.preference.preferredCourses, courseId),
  })
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

const preferredDraft = ref('')
</script>

<template>
  <div class="uig-form">
    <div class="uig-grid">
      <!-- max_credit -->
      <label class="uig-field">
        <span class="uig-field__label">
          学期学分上限 <code class="mono">max_credit</code>
        </span>
        <input
          class="input-text"
          data-testid="max-credit-input"
          type="text"
          inputmode="decimal"
          :value="form.preference.maxCredit ?? ''"
          placeholder="留空 = 未设定"
          @input="onMaxCreditInput"
        />
        <span v-if="maxCreditInvalid" class="uig-field__error" data-testid="max-credit-error">
          请输入不小于 0 的数字；前端不会猜测或补全学分上限，表单将保持不可提交。
        </span>
        <span v-else class="uig-field__hint">留空表示未设定，序列化为 null。</span>
      </label>

      <!-- avoid_cross_campus -->
      <div class="uig-field">
        <span class="uig-field__label">
          跨校区偏好 <code class="mono">avoid_cross_campus</code>
        </span>
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
          仅记录偏好；是否作为正式求解约束执行，以 PlanResult 输出为准。
        </span>
      </div>

      <!-- preferred_courses -->
      <div class="uig-field uig-field--wide">
        <span class="uig-field__label">
          意向课程 <code class="mono">preferred_courses</code>
        </span>
        <div class="uig-inline">
          <input
            class="input-text"
            data-testid="preferred-course-input"
            type="text"
            :value="preferredDraft"
            placeholder="输入课程号，例如 CSE201"
            autocomplete="off"
            @input="onPreferredCourseInput"
            @keyup.enter="commitPreferredCourse"
          />
          <button
            class="button button--small"
            type="button"
            data-testid="preferred-course-add"
            @click="commitPreferredCourse"
          >
            加入
          </button>
        </div>
        <div v-if="form.preference.preferredCourses.length > 0" class="chip-group">
          <span
            v-for="courseId in form.preference.preferredCourses"
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
        <span v-else class="uig-field__hint">尚未添加意向课程。重复课程号不会重复添加。</span>
      </div>

      <!-- avoid_times -->
      <div class="uig-field uig-field--wide">
        <span class="uig-field__label">
          回避时段 <code class="mono">avoid_times</code>
        </span>
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
            尚未设置回避时段。
          </span>
        </div>
        <button
          class="button button--small"
          type="button"
          data-testid="avoid-time-add"
          @click="onAddAvoidTime"
        >
          + 添加回避时段
        </button>
      </div>

      <!-- notes -->
      <label class="uig-field uig-field--wide">
        <span class="uig-field__label">补充备注 <code class="mono">notes</code></span>
        <textarea
          class="input-text uig-textarea"
          data-testid="notes-input"
          rows="2"
          :value="form.preference.notes ?? ''"
          placeholder="例如：希望尽量集中在上午；不接受晚间课程"
          @input="onNotesInput"
        ></textarea>
        <span class="uig-field__hint">留空序列化为 null；前端不会把备注解析成结构化约束。</span>
      </label>
    </div>
  </div>
</template>
