<script setup lang="ts">
import { computed, ref } from 'vue'
import CurrentScheduleInput from './CurrentScheduleInput.vue'
import E2EDebugPanel from './E2EDebugPanel.vue'
import type { E2EDebugInfo } from './E2EDebugPanel.vue'
import PreferenceForm from './PreferenceForm.vue'
import StudentContextForm from './StudentContextForm.vue'
import SubmissionActions from './SubmissionActions.vue'
import { MAJOR_OPTIONS, MANUAL_SCHEDULE_ENTRY_LABEL } from '../config'
import type { PlanResultSource } from '../config'
import type { CourseOffering } from '../types/contracts'
import type { ManualScheduleEntry, StudentContext, UserInputForm } from '../state/userInput'
import {
  GRADE_FILE_PENDING_NOTICE,
  XLSX_EXTENSION,
  addManualScheduleEntry,
  applyManualAttestation,
  invalidateManualAttestation,
  isSupportedGradeFile,
  isFormValid,
  manualScheduleOfferingCount,
  removeCurrentScheduleOffering,
  toggleCurrentScheduleOffering,
} from '../state/userInput'

/**
 * 用户输入区（Frontend User Input Gate, Phase 1）。
 *
 * 产品页面顺序中的前 4 项都在这里：
 * ① 学生信息 ② 已修课程上传 ③ 当前课表 ④ 个性化偏好 —— 之后才是"生成规划"。
 *
 * 边界（本轮的硬要求）：
 * - 只收集用户输入并如实展示"当前还不能做什么"；
 * - ⛔ XLSX 只保存 `File` 对象与文件名：**不上传、不解析、不推断**，
 *   页面明确标注"成绩文件上传分析将在真实 Curriculum User Input API 接入后启用"；
 * - ⛔ 前端**绝不**自己解析成绩并生成任何 `MakeupTask`；
 * - ⛔ 不计算冲突 / feasible / Path Repair。
 */
const props = defineProps<{
  /** 表单真源（由页面持有）。 */
  form: UserInputForm
  /** 已加载的教学班，用于组织"当前课表"输入。 */
  offerings: CourseOffering[]
  /** Real Planning 接口是否已启用。 */
  planApiEnabled: boolean
  /** 是否正在提交。 */
  submitting: boolean
  /** 数据模式。 */
  mode: PlanResultSource
  /** 当前数据来源标签（如实显示 Mock / Real）。 */
  dataSourceLabel?: string | null
  /** Real Planning 失败时的错误信息。 */
  planErrorMessage?: string
  /** Real Planning 失败的类型（`PlanErrorKind`）。 */
  planErrorKind?: string | null
  /** Real Planning 失败时的 HTTP 状态码。 */
  planErrorStatus?: number | null
  /** Real Planning 失败时后端返回的错误码。 */
  planErrorCode?: string | null
  /** Real Planning 失败时后端返回的原始 detail 文本。 */
  planErrorDetail?: string | null
  /** 联调调试信息（仅开发环境渲染）。 */
  debugInfo?: E2EDebugInfo
  /** 是否处于开发环境。 */
  dev?: boolean
  /**
   * 课表 provenance 门禁的阻止原因（fail closed）。
   *
   * `null` = 通过（空课表，或每一项都明确为 real）。
   */
  scheduleBlockReason?: string | null
}>()

const emit = defineEmits<{
  (event: 'update:form', value: UserInputForm): void
  (event: 'submit-real'): void
}>()

/**
 * 已选择的成绩文件。
 *
 * ⚠️ 这里**只保存** `File` 对象与文件名，供后续接真实
 * Curriculum User Input API 时使用；本轮不读取内容、不上传。
 */
const gradeFile = ref<File | null>(null)
const gradeFileError = ref('')

/**
 * 手工课表确认是否**已因课表改动而作废**（用于提示"需要重新确认"）。
 *
 * ⚠️ 真源是 `form.manualAttestation.invalidated`（**持续**状态）；
 * 这里只做只读转发，⛔ 不参与任何业务判断 ——
 * 门禁本身只看 `form.currentSchedule` 里条目的 `data_source`。
 */
const attestationInvalidated = computed(() => props.form.manualAttestation.invalidated)

const gradeFileName = computed(() => gradeFile.value?.name ?? '')

/** 表单是否可提交：只判断输入完整性，不判断学业/排课可行性。 */
const inputValid = computed(() => isFormValid(props.form))

/**
 * 是否可以提交到 Real Planning。
 *
 * 两道独立条件：输入完整性（`isFormValid`）+ **课表数据来源门禁**（fail closed）。
 */
const realSubmitEnabled = computed(
  () => inputValid.value && !(props.scheduleBlockReason ?? null),
)

function onSemesterUpdate(value: string): void {
  emit('update:form', { ...props.form, semester: value })
}

function onContextUpdate(value: StudentContext): void {
  emit('update:form', { ...props.form, studentContext: value })
}

function onToggleOffering(offering: CourseOffering): void {
  // 勾选 / 取消勾选也会改动课表 ⇒ 既有手工确认作废（⛔ 旧确认不得覆盖被改动过的课表）。
  const nextSchedule = toggleCurrentScheduleOffering(
    props.form.currentSchedule,
    offering,
    props.offerings,
  )
  const { form } = invalidateManualAttestation(props.form, nextSchedule)
  emit('update:form', form)
}

function onUpdateManualEntries(entries: ManualScheduleEntry[]): void {
  // 编辑录入行（可能改写将要加入课表的取值）⇒ 作废既有确认。
  const { form } = invalidateManualAttestation(props.form, undefined, entries)
  emit('update:form', form)
}

function onAddManualRow(semester: string): void {
  emit('update:form', {
    ...props.form,
    manualScheduleEntries: addManualScheduleEntry(props.form.manualScheduleEntries, semester),
  })
}

/**
 * 手工录入行校验通过后，由子组件回传"已构造好的 `CourseOffering` + 清空后的录入行"。
 *
 * ⚠️ 两者必须在**同一个** `update:form` 里一起应用：分开两次 emit 会让第二次
 * 更新基于**旧**的 form 快照重建表单，从而把刚加入的课表条目丢掉。
 *
 * ⚠️ 新加入的手工条目 `data_source` 恒为 `mock` ⇒ 同时**作废**既有确认：
 * 旧确认不得自动覆盖新加入的数据。
 */
function onManualOfferingAdded(payload: {
  offering: CourseOffering
  entries: ManualScheduleEntry[]
}): void {
  const { form } = invalidateManualAttestation(
    props.form,
    [...props.form.currentSchedule, payload.offering],
    payload.entries,
  )
  emit('update:form', form)
}

function onRemoveOffering(offering: CourseOffering): void {
  // 移除条目 ⇒ 课表已变 ⇒ 作废既有确认。
  const { form } = invalidateManualAttestation(
    props.form,
    removeCurrentScheduleOffering(props.form.currentSchedule, offering),
  )
  emit('update:form', form)
}

/**
 * **用户级确认**：是否允许手工录入的当前课表进入 Real Planning。
 *
 * ⛔ 唯一入口就是这个勾选框；⛔ 没有任何构建期环境变量能绕过它。
 * - 勾选 ⇒ 手工条目切到 `real`（学生自述输入）⇒ 门禁放行；
 * - 取消 ⇒ 切回 `mock` ⇒ 门禁立即重新阻断。
 */
function onUpdateAttested(attested: boolean): void {
  emit('update:form', applyManualAttestation(props.form, attested))
}

function onGradeFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files && input.files.length > 0 ? input.files[0] : null

  // 只接受 .xlsx；其它扩展名一律拒绝，且不做任何解析。
  if (file && !isSupportedGradeFile(file.name)) {
    gradeFile.value = null
    gradeFileError.value = `仅支持 ${XLSX_EXTENSION} 文件；未选择任何文件，也未读取其内容。`
    input.value = ''
    return
  }

  gradeFileError.value = ''
  gradeFile.value = file
}

function clearGradeFile(): void {
  gradeFile.value = null
  gradeFileError.value = ''
}
</script>

<template>
  <div class="uig">
    <!-- ① 学生信息 -->
    <section class="uig-section" data-testid="uig-section-student">
      <h3 class="uig-section__title">① 学生信息（目标学期与转专业上下文）</h3>
      <StudentContextForm
        :semester="form.semester"
        :context="form.studentContext"
        :majors="MAJOR_OPTIONS"
        @update:semester="onSemesterUpdate"
        @update:context="onContextUpdate"
      />
    </section>

    <!-- ② 已修课程文件 -->
    <section class="uig-section" data-testid="uig-section-grades">
      <h3 class="uig-section__title">② 已修课程文件（成绩单）</h3>
      <p class="uig-form__note">
        本轮仅支持<strong>选择</strong>成绩文件并保存文件对象与文件名。
      </p>

      <div class="uig-field">
        <span class="uig-field__label">成绩文件（仅 .xlsx）</span>
        <input
          class="input-text"
          data-testid="grade-file-input"
          type="file"
          accept=".xlsx"
          @change="onGradeFileChange"
        />
        <span v-if="gradeFileError" class="uig-field__error" data-testid="grade-file-error">
          {{ gradeFileError }}
        </span>
        <span v-else-if="gradeFileName" class="uig-field__hint" data-testid="grade-file-name">
          已选择：<code class="mono">{{ gradeFileName }}</code>（仅保存文件名与文件对象，未上传、未解析）
        </span>
        <span v-else class="uig-field__hint">尚未选择文件。</span>

        <button
          v-if="gradeFileName"
          class="button button--small"
          type="button"
          data-testid="grade-file-clear"
          @click="clearGradeFile"
        >
          清除选择
        </button>
      </div>

      <!-- 必须在页面上明确显示的说明 -->
      <p class="uig-pending" data-testid="grade-file-pending-notice" role="note">
        {{ GRADE_FILE_PENDING_NOTICE }}
      </p>
      <p class="uig-field__hint" data-testid="grade-file-no-makeup-notice">
        本页<strong>不会</strong>解析成绩单，也<strong>不会</strong>在前端生成任何补修任务（MakeupTask）——
        补修识别属于 Curriculum 模块，必须由后端完成。
      </p>
    </section>

    <!-- ③ 当前课表 -->
    <section class="uig-section" data-testid="uig-section-schedule">
      <h3 class="uig-section__title">③ 当前课表（current_schedule）</h3>
      <CurrentScheduleInput
        :offerings="offerings"
        :selected="form.currentSchedule"
        :manual-entries="form.manualScheduleEntries"
        :semester="form.semester"
        :manual-provenance-label="MANUAL_SCHEDULE_ENTRY_LABEL"
        :manual-attested="form.manualAttestation.attested"
        :manual-count="manualScheduleOfferingCount(form)"
        :attestation-invalidated="attestationInvalidated"
        :data-source-label="dataSourceLabel"
        @toggle="onToggleOffering"
        @update:manual-entries="onUpdateManualEntries"
        @add-manual-row="onAddManualRow"
        @manual-add-confirmed="onManualOfferingAdded"
        @remove="onRemoveOffering"
        @update:attested="onUpdateAttested"
      />
    </section>

    <!-- ④ 个性化偏好 -->
    <section class="uig-section" data-testid="uig-section-preference">
      <h3 class="uig-section__title">④ 个性化偏好（Preference）</h3>
      <PreferenceForm :form="form" @update:form="emit('update:form', $event)" />
    </section>

    <!-- ⑤ 生成规划（Mock / Real 明确隔离） -->
    <SubmissionActions
      :mode="mode"
      :plan-api-enabled="planApiEnabled"
      :input-valid="realSubmitEnabled"
      :submitting="submitting"
      :error-message="planErrorMessage"
      :error-kind="planErrorKind ?? null"
      :error-status="planErrorStatus ?? null"
      :error-code="planErrorCode ?? null"
      :error-detail="planErrorDetail ?? null"
      :schedule-block-reason="scheduleBlockReason ?? null"
      @submit-real="emit('submit-real')"
    />

    <!-- 联调调试信息：仅开发环境（生产构建不渲染） -->
    <E2EDebugPanel v-if="debugInfo" :dev="dev ?? false" :info="debugInfo" />
  </div>
</template>
