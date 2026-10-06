<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { ManualScheduleEntry } from '../state/userInput'
import {
  MANUAL_SCHEDULE_FIELD_LABEL,
  addManualScheduleEntryToSchedule,
  removeManualScheduleEntry,
  updateManualScheduleEntry,
} from '../state/userInput'
import type { CourseOffering } from '../types/contracts'

/**
 * 当前课表**手工结构化录入**（`current_schedule: CourseOffering[]`）。
 *
 * 边界（⛔ 不得越界）：
 * - 只做"结构化字段 → 公共 `CourseOffering`"，⛔ **不要求用户写裸 JSON**；
 * - ⛔ **不做**冲突检测、⛔ 不判断 feasible、⛔ 不做 Path Repair、⛔ 不计算学分；
 * - ⛔ 不猜测缺失取值：字段缺失 / 非法 ⇒ 明确报错且**不修改**课表（全有或全无）；
 * - 手工条目加入时 `data_source` **恒为 `mock`**；只有在用户**显式勾选确认**
 *   （`attested`）后才切换成 `real`（学生自述输入），⛔ 不存在构建期旁路。
 */
const props = defineProps<{
  /** 手工录入行（表单真源由页面持有）。 */
  entries: ManualScheduleEntry[]
  /** 当前课表（含手工录入条目），用于查重与"同一课程只能有一个已选班"。 */
  selected: CourseOffering[]
  /** 学期默认值（新增行时带入）。 */
  semester: string
  /** 页面当前学期（用于 detect 学期是否与表单一致）。 */
  currentSemester: string
  /** 未确认时的来源说明（⛔ 逐字可见，不得隐藏）。 */
  provenanceLabel: string
  /** 用户是否已**显式确认**手工课表由本人填写（用户级 attestation）。 */
  attested: boolean
  /** 课表里手工条目的数量（用于提示确认控件何时出现）。 */
  manualCount: number
  /** 确认是否因课表被改动而刚刚作废（界面提示"需要重新确认"）。 */
  attestationInvalidated: boolean
}>()

const emit = defineEmits<{
  (event: 'update:entries', value: ManualScheduleEntry[]): void
  (event: 'add-row', semester: string): void
  (event: 'add-confirmed', payload: { offering: CourseOffering; entries: ManualScheduleEntry[] }): void
  (event: 'remove', offering: CourseOffering): void
  (event: 'update:attested', value: boolean): void
}>()

/** 每条录入行自己的错误提示（只在用户点过"加入"之后显示）。 */
const entryErrors = reactive<Record<number, string>>({})
const lastAdded = ref('')

const WEEKDAYS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' },
]

const scheduledCount = computed(() => props.selected.length)

function patch(entry: ManualScheduleEntry, field: keyof Omit<ManualScheduleEntry, 'key'>, value: unknown): void {
  emit('update:entries', updateManualScheduleEntry(props.entries, entry.key, { [field]: value } as never))
}

function numberOrNull(raw: string): number | null {
  const text = raw.trim()
  if (!/^\d+$/.test(text)) {
    return null
  }
  const value = Number(text)
  return Number.isSafeInteger(value) ? value : null
}

function onAdd(entry: ManualScheduleEntry): void {
  const result = addManualScheduleEntryToSchedule(props.selected, entry)
  if (!result.added) {
    entryErrors[entry.key] = result.error
    lastAdded.value = ''
    return
  }

  entryErrors[entry.key] = ''
  const added = result.currentSchedule[result.currentSchedule.length - 1]
  lastAdded.value = `${added.course_name}（${added.course_id} · ${added.class_id}）`

  // ⚠️ 两个状态（课表 + 录入行清空）必须由**父组件在同一个更新里**一起应用：
  //    若先 emit 'add-confirmed' 再 emit 'update:entries'，第二次更新会基于
  //    **旧**的 form 快照重建表单，从而把刚加入的课表条目（以及"确认作废"的提示）丢掉。
  //    因此这里**只发一个**事件，录入行的清空随事件一起带给父组件。
  emit('add-confirmed', {
    offering: added,
    entries: updateManualScheduleEntry(props.entries, entry.key, {
      courseId: '',
      courseName: '',
      classId: '',
      weekday: null,
      startSection: null,
      endSection: null,
      weeksText: '',
      campus: '',
      classroom: '',
    }),
  })
}

function onRemove(entry: ManualScheduleEntry): void {
  delete entryErrors[entry.key]
  emit('update:entries', removeManualScheduleEntry(props.entries, entry.key))
}
</script>

<template>
  <div class="uig-manual-schedule">
    <p class="uig-form__note">
      若你已经在选课系统里选好了班，但上面列表里找不到（例如该教学班不在当前加载的教学班范围内），
      可以在这里<strong>结构化录入</strong>：填好课程、星期、节次、周次后点「加入当前课表」。
      <strong>不需要你写 JSON</strong>。
    </p>
    <p class="uig-field__hint" data-testid="manual-schedule-provenance">
      来源：{{ provenanceLabel }}
    </p>

    <div v-if="entries.length === 0" class="uig-field__hint">尚未添加手工录入行。</div>

    <div
      v-for="(entry, index) in entries"
      :key="entry.key"
      class="uig-manual-row"
      data-testid="manual-schedule-row"
    >
      <div class="uig-manual-row__head">
        <strong>手工录入 {{ index + 1 }}</strong>
        <button
          class="button button--small"
          type="button"
          :data-testid="`manual-schedule-remove-${entry.key}`"
          @click="onRemove(entry)"
        >
          移除该行
        </button>
      </div>

      <div class="uig-manual-grid">
        <label class="uig-field">
          <span class="uig-field__label">课程号</span>
          <input
            class="input-text"
            :data-testid="`manual-course-id-${entry.key}`"
            :value="entry.courseId"
            placeholder="例如 SEC1001"
            @input="patch(entry, 'courseId', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <label class="uig-field">
          <span class="uig-field__label">课程名称</span>
          <input
            class="input-text"
            :data-testid="`manual-course-name-${entry.key}`"
            :value="entry.courseName"
            placeholder="例如 信息安全导论"
            @input="patch(entry, 'courseName', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <label class="uig-field">
          <span class="uig-field__label">教学班号</span>
          <input
            class="input-text"
            :data-testid="`manual-class-id-${entry.key}`"
            :value="entry.classId"
            placeholder="例如 01"
            @input="patch(entry, 'classId', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <label class="uig-field">
          <span class="uig-field__label">学期</span>
          <input
            class="input-text"
            :data-testid="`manual-semester-${entry.key}`"
            :value="entry.semester"
            placeholder="例如 2026-1"
            @input="patch(entry, 'semester', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <label class="uig-field">
          <span class="uig-field__label">星期</span>
          <select
            class="input-text"
            :data-testid="`manual-weekday-${entry.key}`"
            :value="entry.weekday === null ? '' : String(entry.weekday)"
            @change="patch(entry, 'weekday', numberOrNull(($event.target as HTMLSelectElement).value))"
          >
            <option value="">请选择</option>
            <option v-for="day in WEEKDAYS" :key="day.value" :value="String(day.value)">
              {{ day.label }}
            </option>
          </select>
        </label>

        <label class="uig-field">
          <span class="uig-field__label">开始节次</span>
          <input
            class="input-text"
            inputmode="numeric"
            :data-testid="`manual-start-section-${entry.key}`"
            :value="entry.startSection === null ? '' : String(entry.startSection)"
            placeholder="例如 3"
            @input="patch(entry, 'startSection', numberOrNull(($event.target as HTMLInputElement).value))"
          />
        </label>

        <label class="uig-field">
          <span class="uig-field__label">结束节次</span>
          <input
            class="input-text"
            inputmode="numeric"
            :data-testid="`manual-end-section-${entry.key}`"
            :value="entry.endSection === null ? '' : String(entry.endSection)"
            placeholder="例如 4"
            @input="patch(entry, 'endSection', numberOrNull(($event.target as HTMLInputElement).value))"
          />
        </label>

        <label class="uig-field">
          <span class="uig-field__label">周次</span>
          <input
            class="input-text"
            :data-testid="`manual-weeks-${entry.key}`"
            :value="entry.weeksText"
            placeholder="例如 1-16 或 1-16,18"
            @input="patch(entry, 'weeksText', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <label class="uig-field">
          <span class="uig-field__label">校区（可留空）</span>
          <input
            class="input-text"
            :data-testid="`manual-campus-${entry.key}`"
            :value="entry.campus"
            placeholder="例如 深圳校区"
            @input="patch(entry, 'campus', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <label class="uig-field">
          <span class="uig-field__label">教室（可留空）</span>
          <input
            class="input-text"
            :data-testid="`manual-classroom-${entry.key}`"
            :value="entry.classroom"
            placeholder="例如 教学楼A305"
            @input="patch(entry, 'classroom', ($event.target as HTMLInputElement).value)"
          />
        </label>
      </div>

      <p
        v-if="entryErrors[entry.key]"
        class="uig-field__error"
        :data-testid="`manual-error-${entry.key}`"
        role="alert"
      >
        {{ entryErrors[entry.key] }}
      </p>

      <div class="uig-manual-row__actions">
        <button
          class="button button--small"
          type="button"
          :data-testid="`manual-add-${entry.key}`"
          @click="onAdd(entry)"
        >
          加入当前课表
        </button>
        <span class="uig-field__hint">
          只做录入与格式校验，<strong>不进行冲突检测、不判断可行性</strong>。
        </span>
      </div>
    </div>

    <div class="uig-manual-row__actions">
      <button
        class="button button--small"
        type="button"
        data-testid="manual-schedule-add-row"
        @click="emit('add-row', currentSemester)"
      >
        + 新增一行手工录入
      </button>
    </div>

    <p v-if="lastAdded" class="uig-field__hint" data-testid="manual-schedule-added">
      已加入：{{ lastAdded }}
    </p>

    <div class="uig-manual-selected" data-testid="manual-schedule-selected">
      <p class="uig-field__hint">
        当前课表共 {{ scheduledCount }} 个教学班（其中手工录入 {{ manualCount }} 个）。可逐个移除：
      </p>
      <ul v-if="scheduledCount > 0" class="uig-manual-selected__list">
        <li v-for="item in selected" :key="`${item.semester}::${item.course_id}::${item.class_id}`">
          <span>
            <strong>{{ item.course_name }}</strong>
            <span class="mono"> · {{ item.course_id }} · {{ item.class_id }}</span>
          </span>
          <button
            class="button button--small"
            type="button"
            :data-testid="`manual-schedule-remove-selected-${item.course_id}-${item.class_id}`"
            @click="emit('remove', item)"
          >
            移除
          </button>
        </li>
      </ul>
    </div>

    <!--
      用户级确认（attestation）——本轮唯一的解锁入口。

      ⛔ 默认不勾选：手工条目保持 data_source = mock，provenance 门禁阻断提交。
      ⛔ 文案不得出现"学校已核验 / 教务系统已确认"等含义。
    -->
    <div class="uig-manual-attestation" data-testid="manual-attestation">
      <label class="uig-manual-attestation__row">
        <input
          type="checkbox"
          data-testid="manual-attestation-checkbox"
          :checked="attested"
          @change="emit('update:attested', ($event.target as HTMLInputElement).checked)"
        />
        <span>
          我确认以上当前课表由<strong>本人</strong>根据本学期已经选好的课程填写，系统将基于此进行规划。
        </span>
      </label>

      <p class="uig-field__hint" data-testid="manual-attestation-note">
        该课表<strong>由本人提供，未经学校系统核验</strong>；它不是 Course Data 来源证明，
        也不代表学校已完成选课或审批。未勾选时，手工录入的课表<strong>不会</strong>提交到 Real Planning。
      </p>

      <p
        v-if="attestationInvalidated"
        class="uig-field__error"
        data-testid="manual-attestation-invalidated"
        role="alert"
      >
        当前课表在上次确认之后被改动，之前的确认已作废；请重新确认后再提交 Real Planning。
      </p>

      <p
        v-if="manualCount > 0"
        class="uig-field__hint"
        :data-testid="attested ? 'manual-attestation-state-on' : 'manual-attestation-state-off'"
      >
        <template v-if="attested">
          状态：<strong>已确认</strong>（手工录入 {{ manualCount }} 个教学班可作为本人自述输入进入规划）。
        </template>
        <template v-else>
          状态：<strong>未确认</strong>（手工录入 {{ manualCount }} 个教学班会被 provenance 门禁阻止提交）。
        </template>
      </p>
    </div>
  </div>
</template>
