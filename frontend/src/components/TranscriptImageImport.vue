<script setup lang="ts">
/**
 * 成绩单**图片**导入 + OCR 结果**确认页**（Phase 5）。
 *
 * ```text
 * 选择图片（本机预览，⛔ 不上传第三方）
 *   ↓ POST /api/v1/transcript-images/recognize
 * OCR 候选列表
 *   ↓ 用户逐条：确认 / 修改课程名 / 修改学分 / 丢弃
 * 已确认课程记录（confirmed_completed_courses）
 *   ↓ 交给父级随生成请求提交
 * matching engine（⛔ 一行不改）
 * ```
 *
 * ## 硬约束
 *
 * - ⛔ 组件内不做任何课程认定（不判断等价、不推断课程号）；
 * - ⛔ **未确认的行绝不进入 `confirmed`**，因此 OCR 原始结果无法影响匹配；
 * - `course_id` 恒为 `null`（图片没有官方课程号）；
 * - 置信度⛔ 不参与判定，只用于提示"建议核对"；
 * - ⛔ 失败如实报错，⛔ 不用演示数据顶替。
 */

import { computed, onBeforeUnmount, ref } from 'vue'

import {
  ACCEPTED_IMAGE_TYPES,
  CANDIDATE_STATUS_REASON,
  MAX_IMAGE_BYTES,
  TranscriptImageApiError,
  candidateRecognitionStatus,
  candidateUnrecognizedReasons,
  recognizeTranscriptImage,
  toCandidateRow,
  toConfirmedRecords,
  type ConfirmedCourseRow,
  type RecognizedCourseCandidate,
  type TranscriptImageRecognition,
} from '../api/transcriptImages'

const props = defineProps<{
  /** 当前已在方案里的成绩单来源说明（用于避免两种输入混用）。 */
  disabled?: boolean
}>()

const emit = defineEmits<{
  /** 用户确认后的课程记录变化（父级据此决定提交内容）。 */
  (event: 'update:confirmed', records: ReturnType<typeof toConfirmedRecords>): void
}>()

const fileName = ref('')
const previewUrl = ref('')
const error = ref('')
const scanning = ref(false)
const recognition = ref<TranscriptImageRecognition | null>(null)

/**
 * 把父级统一入口选择的图片文件送入本组件。
 *
 * ⚠️ 统一入口（Phase 6）：组件内⛔ 不再有自己的 file input，
 *   全链路只有 `handleImage()` 这一条识别路径。
 *   传 `null` 表示"切换到 PDF 路径"，用于清空图片侧状态。
 */
async function acceptFile(file: File | null): Promise<void> {
  await handleImage(file)
}

defineExpose({ acceptFile })

/** 每行的编辑态（用户改动后的值）。 */
const rows = ref<ConfirmedCourseRow[]>([])
/** 用户已**明确确认**的行 rowId。⛔ 未在此集合中的行不进入提交。 */
const confirmedIds = ref<string[]>([])
/** 被丢弃的候选 rowId（如实展示，⛔ 不静默删除）。 */
const discardedIds = ref<string[]>([])

function releasePreview(): void {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

onBeforeUnmount(releasePreview)

const hasResult = computed(() => recognition.value !== null)
const candidates = computed<readonly RecognizedCourseCandidate[]>(
  () => recognition.value?.candidates ?? [],
)

/** 行查找（按 rowId）。 */
function rowOf(rowId: string): ConfirmedCourseRow | undefined {
  return rows.value.find((row) => row.rowId === rowId)
}

function isConfirmed(rowId: string): boolean {
  return confirmedIds.value.includes(rowId)
}

function isDiscarded(rowId: string): boolean {
  return discardedIds.value.includes(rowId)
}

/* -------------------------------------------------------------------------- *
 * OCR 候选识别状态（⛔ 可确认性由它控制，**不是**按课程名过滤）
 * -------------------------------------------------------------------------- */

/** 某候选是否**可被用户确认**（= 识别状态为 `recognized`）。 */
function isConfirmable(candidate: RecognizedCourseCandidate): boolean {
  return candidateRecognitionStatus(candidate) === 'recognized'
}

/** 该候选为何不可确认（页面如实展示原因）。 */
function unrecognizedReasons(candidate: RecognizedCourseCandidate): string[] {
  return candidateUnrecognizedReasons(candidate).map((code) => CANDIDATE_STATUS_REASON[code])
}

/** 可确认的候选（批量确认与提交都只认这一份）。 */
const confirmableCandidates = computed(() =>
  candidates.value.filter((candidate) => isConfirmable(candidate)),
)

/** 可确认候选的 rowId 集合（用于计数与提交时 fail closed）。 */
const confirmableIds = computed(
  () => new Set(confirmableCandidates.value.map((candidate) => candidate.row_id)),
)

/** 不可确认的候选（只展示）。 */
const unrecognizedCandidates = computed(() =>
  candidates.value.filter((candidate) => !isConfirmable(candidate)),
)

/**
 * 低置信度提示（⛔ 不参与判定，只是提示用户核对）。
 */
function isLowConfidence(candidate: RecognizedCourseCandidate): boolean {
  return candidate.confidence < 0.7
}

/**
 * 发布**仅来自用户确认**的记录。
 *
 * ⛔ 双保险（两层都必须成立）：
 *   1. 该行已被用户确认（`confirmedIds`）；
 *   2. 该行的 OCR 识别状态为 `recognized`（`isConfirmable`）。
 *
 * ⇒ 未识别的候选**即使被误塞进 `confirmedIds` 也不会泄漏到提交内容**。
 */
function publish(): void {
  const confirmed = rows.value.filter((row) => {
    if (!isConfirmed(row.rowId) || isDiscarded(row.rowId)) return false
    const candidate = candidates.value.find((item) => item.row_id === row.rowId)
    // ⛔ 找不到候选（异常）也一律不提交 —— fail closed。
    return candidate !== undefined && isConfirmable(candidate)
  })
  emit('update:confirmed', toConfirmedRecords(confirmed))
}

function reset(): void {
  fileName.value = ''
  error.value = ''
  recognition.value = null
  rows.value = []
  confirmedIds.value = []
  discardedIds.value = []
  releasePreview()
  publish()
}

/**
 * 图片处理的**唯一路径**（校验 → 本机预览 → 识别 → 候选）。
 *
 * ⚠️ 由父级统一入口调用（`acceptFile`）；⛔ 组件内没有第二个入口。
 */
async function handleImage(file: File | null): Promise<void> {
  error.value = ''
  recognition.value = null
  rows.value = []
  confirmedIds.value = []
  discardedIds.value = []
  releasePreview()
  publish()

  if (!file) {
    fileName.value = ''
    return
  }
  if (!ACCEPTED_IMAGE_TYPES.split(',').includes(file.type)) {
    fileName.value = ''
    error.value = '仅支持 PNG / JPEG / WebP 图片；未选择任何文件，也未读取其内容。'
    return
  }
  if (file.size > MAX_IMAGE_BYTES) {
    fileName.value = ''
    error.value = '图片不得超过 8 MiB；未读取其内容。'
    return
  }

  fileName.value = file.name
  previewUrl.value = URL.createObjectURL(file)
  scanning.value = true
  try {
    const result = await recognizeTranscriptImage(file)
    recognition.value = result
    rows.value = result.candidates.map(toCandidateRow)
  } catch (cause) {
    recognition.value = null
    if (cause instanceof TranscriptImageApiError) {
      if (cause.isOcrUnavailable) {
        error.value = '本地识别服务不可用，无法识别该图片。'
      } else if (cause.isUnreadable) {
        error.value = cause.message || '未能在图片中识别出课程行，请上传更清晰的成绩单图片。'
      } else if (cause.isNetworkFailure) {
        error.value = '暂时无法连接后端，未能识别该图片。'
      } else {
        error.value = cause.message || '识别失败。'
      }
    } else {
      error.value = '识别失败。'
    }
  } finally {
    scanning.value = false
  }
}

function confirm(rowId: string): void {
  // ⛔ 未识别的候选不可确认（只能展示）
  const candidate = candidates.value.find((item) => item.row_id === rowId)
  if (candidate === undefined || !isConfirmable(candidate)) return
  if (!confirmedIds.value.includes(rowId)) {
    confirmedIds.value = [...confirmedIds.value, rowId]
  }
  // 同一条不会同时处于"已丢弃"
  discardedIds.value = discardedIds.value.filter((id) => id !== rowId)
  publish()
}

/**
 * 批量确认**只覆盖可确认的候选**（识别状态为 `recognized`）。
 *
 * ⛔ 未识别的候选不会被批量确认带入 —— 这是"未识别只能展示"的硬保证。
 */
function confirmAll(): void {
  const allowed = new Set(confirmableCandidates.value.map((candidate) => candidate.row_id))
  confirmedIds.value = rows.value
    .filter((row) => !isDiscarded(row.rowId) && allowed.has(row.rowId))
    .map((row) => row.rowId)
  publish()
}

function undo(rowId: string): void {
  confirmedIds.value = confirmedIds.value.filter((id) => id !== rowId)
  publish()
}

function discard(rowId: string): void {
  if (!discardedIds.value.includes(rowId)) {
    discardedIds.value = [...discardedIds.value, rowId]
  }
  confirmedIds.value = confirmedIds.value.filter((id) => id !== rowId)
  publish()
}

/** 修改课程名（用户确认页可编辑）。 */
function rename(rowId: string, event: Event): void {
  const value = (event.target as HTMLInputElement).value
  rows.value = rows.value.map((row) =>
    row.rowId === rowId ? { ...row, courseName: value } : row,
  )
  publish()
}

/** 修改学分（OCR 常读不出，允许用户补填）。 */
function setCredit(rowId: string, event: Event): void {
  const raw = (event.target as HTMLInputElement).value.trim()
  const parsed = raw === '' ? null : Number(raw)
  const value = parsed !== null && Number.isFinite(parsed) && parsed >= 0 ? parsed : null
  rows.value = rows.value.map((row) =>
    row.rowId === rowId ? { ...row, credit: value } : row,
  )
  publish()
}

/** 修改通过状态。 */
function setPassed(rowId: string, event: Event): void {
  const value = (event.target as HTMLSelectElement).value === 'passed'
  rows.value = rows.value.map((row) => (row.rowId === rowId ? { ...row, passed: value } : row))
  publish()
}

/** 已确认门数：⚠️ 只统计**可确认**的行（未识别的行永远不在此列）。 */
const confirmedCount = computed(
  () => confirmedIds.value.filter((rowId) => confirmableIds.value.has(rowId)).length,
)
/** 待确认门数：可确认但用户还没确认的行。 */
const pendingCount = computed(
  () =>
    rows.value.filter(
      (row) =>
        confirmableIds.value.has(row.rowId) &&
        !isConfirmed(row.rowId) &&
        !isDiscarded(row.rowId),
    ).length,
)
</script>

<template>
  <section class="tii" data-testid="case-a-transcript-image-import">
    <!--
      ⚠️ 统一入口（Phase 6）：成绩单文件由**父级的单一「选择成绩单文件」控件**选择。
         因此本组件⛔ 不再渲染自己的标题、说明与选择控件 ——
         否则页面上会出现两个看起来重复的上传入口（实测被反馈过）。
         本组件只负责：识别中状态、识别失败提示、以及**确认页**。
    -->
    <!-- 识别中：只在已选择图片时出现 -->
    <p v-if="scanning" class="tii__scanning" data-testid="case-a-transcript-image-scanning">
      正在本地识别成绩单…
    </p>

    <p v-if="error" class="tii__error" role="alert" data-testid="case-a-transcript-image-error">
      {{ error }}
    </p>

    <!-- 已选图片的本机预览（⛔ 不上传第三方） -->
    <div
      v-if="previewUrl"
      class="tii__preview"
      data-testid="case-a-transcript-image-preview"
    >
      <img :src="previewUrl" alt="成绩单图片预览" />
    </div>

    <div v-if="hasResult && recognition" class="tii__result" data-testid="case-a-transcript-image-result">
      <p class="tii__result-head" data-testid="case-a-transcript-image-summary">
        识别出 <strong>{{ candidates.length }}</strong> 门课程的候选；
        其中 <strong>{{ confirmableCandidates.length }}</strong> 条已识别（可确认）·
        <strong>{{ unrecognizedCandidates.length }}</strong> 条未识别（⛔ 只能展示，不可确认）；
        已确认 <strong>{{ confirmedCount }}</strong> 门 ·
        待确认 <strong>{{ pendingCount }}</strong> 门。
      </p>
      <p
        v-if="unrecognizedCandidates.length > 0"
        class="tii__privacy"
        data-testid="case-a-transcript-image-unrecognized-note"
      >
        ⛔ 未识别的候选<strong>只会展示</strong>，不会被提交进匹配；
        它们不计入「已确认」，也不受批量确认影响。
      </p>
      <p class="tii__privacy" data-testid="case-a-transcript-image-privacy">
        已在识别阶段过滤 {{ recognition.redacted_block_count }} 处个人身份信息（姓名 / 学号等），
        ⛔ 不会出现在结果中。
      </p>

      <article
        v-for="candidate in candidates"
        :key="candidate.row_id"
        class="tii__row"
        :class="{ 'tii__row--discarded': isDiscarded(candidate.row_id) }"
        data-testid="case-a-transcript-image-candidate"
      >
        <div class="tii__row-main">
          <label class="tii__field">
            <span>课程名</span>
            <input
              type="text"
              :value="rowOf(candidate.row_id)?.courseName ?? candidate.course_name"
              data-testid="case-a-transcript-image-name"
              @input="rename(candidate.row_id, $event)"
            />
          </label>
          <label class="tii__field tii__field--narrow">
            <span>学分</span>
            <input
              type="text"
              inputmode="decimal"
              :value="rowOf(candidate.row_id)?.credit ?? ''"
              placeholder="待填"
              data-testid="case-a-transcript-image-credit"
              @input="setCredit(candidate.row_id, $event)"
            />
          </label>
          <label class="tii__field tii__field--narrow">
            <span>成绩</span>
            <input
              type="text"
              :value="candidate.score_text ?? ''"
              readonly
              data-testid="case-a-transcript-image-score"
            />
          </label>
          <dl class="tii__meta">
            <div>
              <dt>学期</dt>
              <dd>{{ candidate.semester_text ?? '未识别' }}</dd>
            </div>
            <div>
              <dt>属性</dt>
              <dd>{{ candidate.course_attribute ?? '未识别' }}</dd>
            </div>
            <div>
              <dt>置信度</dt>
              <dd :class="{ 'tii__low': isLowConfidence(candidate) }">
                {{ candidate.confidence.toFixed(2) }}
                <template v-if="isLowConfidence(candidate)">（建议核对）</template>
              </dd>
            </div>
          </dl>
          <ul class="tii__unconfirmed" data-testid="case-a-transcript-image-unconfirmed">
            <li v-for="reason in candidate.unconfirmed" :key="reason">{{ reason }}</li>
          </ul>
          <label v-if="isConfirmable(candidate)" class="tii__field tii__field--narrow">
            <span>是否通过</span>
            <select
              :value="rowOf(candidate.row_id)?.passed ? 'passed' : 'failed'"
              data-testid="case-a-transcript-image-passed"
              @change="setPassed(candidate.row_id, $event)"
            >
              <option value="passed">已通过</option>
              <option value="failed">未通过 / 待确认</option>
            </select>
          </label>
        </div>

        <div class="tii__row-actions">
          <!--
            ⛔ 未识别的候选（缺课程名 / 缺成绩）**只能展示**：
               不渲染任何确认入口，也不提供"是否通过"下拉 —— 用户不能凭空断言。
          -->
          <template v-if="!isConfirmable(candidate)">
            <span
              class="tii__unrecognized"
              data-testid="case-a-transcript-image-row-unrecognized"
            >
              ⛔ 未识别：{{ unrecognizedReasons(candidate).join('；') }}（不可确认）
            </span>
          </template>
          <template v-else-if="isConfirmed(candidate.row_id)">
            <span class="tii__confirmed" data-testid="case-a-transcript-image-confirmed">
              ✓ 已确认为成绩单课程
            </span>
            <button
              class="button button--small button--ghost"
              type="button"
              data-testid="case-a-transcript-image-undo"
              @click="undo(candidate.row_id)"
            >
              撤回
            </button>
          </template>
          <template v-else>
            <button
              class="button button--small"
              type="button"
              data-testid="case-a-transcript-image-confirm"
              @click="confirm(candidate.row_id)"
            >
              确认为成绩单课程
            </button>
            <span class="tii__pending">待确认</span>
          </template>
          <button
            class="button button--small button--ghost"
            type="button"
            data-testid="case-a-transcript-image-discard"
            @click="discard(candidate.row_id)"
          >
            {{ isDiscarded(candidate.row_id) ? '已丢弃' : '丢弃' }}
          </button>
        </div>
      </article>

      <div v-if="recognition.unrecognized.length > 0" class="tii__unresolved">
        <p class="tii__unresolved-head" data-testid="case-a-transcript-image-unrecognized">
          未能归入课程行的内容（{{ recognition.unrecognized.length }} 条，⛔ 不猜测）
        </p>
        <ul>
          <li v-for="text in recognition.unrecognized" :key="text">{{ text }}</li>
        </ul>
      </div>

      <p class="tii__hint">
        ⛔ 未确认的候选不会进入补修分析；识别结果也<strong>不会</strong>直接决定任何课程状态。
        <button
          class="case-a-link-button"
          type="button"
          data-testid="case-a-transcript-image-confirm-all"
          :disabled="confirmableCandidates.length === 0"
          @click="confirmAll"
        >
          确认全部已识别（{{ confirmableCandidates.length }} 条）
        </button>
        <button
          class="case-a-link-button"
          type="button"
          data-testid="case-a-transcript-image-reset"
          @click="reset"
        >
          重新选择图片
        </button>
      </p>
    </div>
  </section>
</template>

<style scoped>
.tii {
  margin-top: 14px;
  padding: 14px;
  border: 1px dashed #c7d2e0;
  border-radius: 10px;
  background: #fbfcfe;
}

.tii__title {
  margin: 0 0 6px;
  font-size: 15px;
}

.tii__hint {
  margin: 0 0 10px;
  color: #55606e;
  font-size: 13px;
  line-height: 1.6;
}

.tii__file {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.tii__ok {
  margin: 10px 0 0;
  color: #1b5e20;
  font-size: 13px;
}

.tii__error {
  margin: 10px 0 0;
  color: #b3261e;
  font-size: 13px;
}

.tii__scanning {
  margin: 10px 0 0;
  color: #55606e;
  font-size: 13px;
}

.tii__preview {
  margin-top: 10px;
  max-width: 420px;
}

.tii__preview img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid #dde3ea;
  border-radius: 8px;
}

.tii__result {
  margin-top: 12px;
}

.tii__result-head {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
}

.tii__privacy {
  margin: 0 0 10px;
  color: #1b5e20;
  font-size: 12px;
  line-height: 1.6;
}

.tii__row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
  padding: 12px;
  border: 1px solid #dde3ea;
  border-radius: 8px;
  background: #fff;
}

.tii__row--discarded {
  opacity: 0.55;
  background: #fafafa;
}

.tii__row-main {
  display: flex;
  flex: 1 1 520px;
  flex-wrap: wrap;
  gap: 8px 14px;
}

.tii__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #6b7683;
}

.tii__field input,
.tii__field select {
  padding: 6px 8px;
  border: 1px solid #d5dde7;
  border-radius: 6px;
  font-size: 13px;
  color: #1e293b;
  min-width: 160px;
}

.tii__field--narrow input,
.tii__field--narrow select {
  min-width: 90px;
  width: 90px;
}

.tii__meta {
  display: flex;
  flex: 1 1 100%;
  flex-wrap: wrap;
  gap: 4px 18px;
  margin: 0;
}

.tii__meta dt {
  color: #6b7683;
  font-size: 11px;
}

.tii__meta dd {
  margin: 2px 0 0;
  font-size: 12px;
}

.tii__low {
  color: #8a5a00;
  font-weight: 600;
}

.tii__unconfirmed {
  flex: 1 1 100%;
  margin: 0;
  padding-left: 18px;
  color: #8a5a00;
  font-size: 12px;
  line-height: 1.6;
}

.tii__row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tii__pending {
  color: #8a5a00;
  font-size: 13px;
}

.tii__confirmed {
  padding: 4px 10px;
  border: 1px solid #2e7d32;
  border-radius: 6px;
  background: #e8f5e9;
  color: #1b5e20;
  font-size: 13px;
  font-weight: 600;
}

.tii__unresolved {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid #f0c36d;
  border-radius: 8px;
  background: #fffaf0;
  font-size: 12px;
}

.tii__unresolved-head {
  margin: 0 0 6px;
  font-weight: 600;
}

.tii__unresolved ul {
  margin: 0;
  padding-left: 18px;
  color: #8a5a00;
  line-height: 1.6;
}
</style>
