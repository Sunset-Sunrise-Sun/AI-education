<script setup lang="ts">
/**
 * 培养方案 PDF 导入（⚠️ 本轮新增）。
 *
 * ```text
 * ① 上传原专业 PDF      ② 上传目标专业 PDF
 *         ↓ 解析成结构化课程表 + 待确认问题清单
 * ③ 用户确认「解析结果正确」（≠ 来源已被批准）
 * ④ 草稿交给**组长**审核来源 → 组长批准后才可能进入真实规划
 * ```
 *
 * ## ⛔ 本组件刻意不做的事
 *
 * | ⛔ 不做 | 为什么 |
 * | --- | --- |
 * | 把解析结果显示成"已核验培养方案" | 核验由组长签发的批准锚点决定，⛔ 与上传无关 |
 * | 提供"批准来源"按钮 | ⛔ Agent / 前端都不能写批准记录 |
 * | 直接写入 `APP_PERSONAL_CATALOG_DIR` | 目录只能由人放置 |
 * | 解析失败时显示演示数据 | ⛔ 不允许伪造解析成功 |
 * | 在前端重新解析 PDF | 前端只做**本地快速失败**（大小 / 类型），权威校验在后端 |
 */

import { computed, onMounted, ref } from 'vue'

import { CURRICULUM_IMPORT_API_ENABLED } from '../config'
import {
  CURRICULUM_IMPORT_ERROR_LABEL,
  CurriculumImportError,
  MAX_PDF_UPLOAD_BYTES,
  fetchCurriculumDocumentTypes,
  parseCurriculumPdf,
  validatePdfFile,
  type CurriculumDocumentType,
  type CurriculumParseResult,
  type CurriculumRole,
} from '../api/curriculumImport'

const props = withDefaults(
  defineProps<{
    /** 原专业（默认取 Case A 的默认专业名，仅作**输入初值**）。 */
    defaultOriginMajor?: string
    /** 目标专业。 */
    defaultTargetMajor?: string
    /** 年级（培养方案版本）。 */
    defaultCohort?: string
  }>(),
  {
    defaultOriginMajor: '遥感科学与技术',
    defaultTargetMajor: '网络空间安全',
    defaultCohort: '2025',
  },
)

interface SlotState {
  file: File | null
  status: 'idle' | 'uploading' | 'parsed' | 'failed'
  result: CurriculumParseResult | null
  errorKind: keyof typeof CURRICULUM_IMPORT_ERROR_LABEL | null
  /** ⚠️ 「用户确认解析正确」——⛔ 不代表来源被批准。 */
  parseConfirmed: boolean
}

function emptySlot(): SlotState {
  return { file: null, status: 'idle', result: null, errorKind: null, parseConfirmed: false }
}

const origin = ref<SlotState>(emptySlot())
const target = ref<SlotState>(emptySlot())
const originMajor = ref(props.defaultOriginMajor)
const targetMajor = ref(props.defaultTargetMajor)
const cohort = ref(props.defaultCohort)
const originSource = ref('教务系统保存网页重排生成的 PDF')
const targetSource = ref('教务系统保存网页重排生成的 PDF')

const enabled = CURRICULUM_IMPORT_API_ENABLED
const maxMiB = Math.round(MAX_PDF_UPLOAD_BYTES / 1024 / 1024)

/**
 * **已验收**的文档类型清单（来自后端注册表）。
 *
 * ⛔ 前端⛔ 不硬编码任何列位映射，也⛔ 不允许用户自定义：
 * 用户只能"选择用哪份已验收声明解析"，⛔ 无法影响"哪一列是课程编码"。
 */
const documentTypes = ref<CurriculumDocumentType[]>([])
const documentTypeKey = ref('')
const documentTypesError = ref<string | null>(null)

async function loadDocumentTypes(): Promise<void> {
  if (!enabled) {
    return
  }
  try {
    documentTypes.value = await fetchCurriculumDocumentTypes({ enabled })
    documentTypesError.value = null
    if (!documentTypeKey.value && documentTypes.value.length > 0) {
      documentTypeKey.value = documentTypes.value[0]!.key
    }
  } catch (error) {
    documentTypes.value = []
    documentTypesError.value = CURRICULUM_IMPORT_ERROR_LABEL[
      error instanceof CurriculumImportError ? error.kind : 'network'
    ]
  }
}

onMounted(loadDocumentTypes)

function slotOf(role: CurriculumRole): SlotState {
  return role === 'origin' ? origin.value : target.value
}

function majorOf(role: CurriculumRole): string {
  return role === 'origin' ? originMajor.value : targetMajor.value
}

function sourceOf(role: CurriculumRole): string {
  return role === 'origin' ? originSource.value : targetSource.value
}

function onFileChange(role: CurriculumRole, event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  const slot = slotOf(role)
  slot.file = file
  slot.result = null
  slot.parseConfirmed = false
  slot.errorKind = null
  slot.status = 'idle'
  if (file !== null) {
    const local = validatePdfFile(file)
    if (local !== null) {
      slot.status = 'failed'
      slot.errorKind = local
    }
  }
}

async function upload(role: CurriculumRole): Promise<void> {
  const slot = slotOf(role)
  if (slot.file === null) {
    return
  }
  slot.status = 'uploading'
  slot.errorKind = null
  try {
    slot.result = await parseCurriculumPdf(slot.file, {
      role,
      major: majorOf(role),
      cohort: cohort.value,
      source: sourceOf(role),
      enabled,
      // ⚠️ 只是**断言**：后端会与按内容结构判定的结果核对，不一致即 422。
      documentType: documentTypeKey.value || undefined,
    })
    slot.status = 'parsed'
  } catch (error) {
    slot.status = 'failed'
    slot.errorKind = error instanceof CurriculumImportError ? error.kind : 'network'
  }
}

function errorLabel(slot: SlotState): string | null {
  return slot.errorKind === null ? null : CURRICULUM_IMPORT_ERROR_LABEL[slot.errorKind]
}

function resetAll(): void {
  origin.value = emptySlot()
  target.value = emptySlot()
}

const anyParsed = computed(
  () => origin.value.status === 'parsed' || target.value.status === 'parsed',
)

const allConfirmed = computed(
  () =>
    (origin.value.status !== 'parsed' || origin.value.parseConfirmed)
    && (target.value.status !== 'parsed' || target.value.parseConfirmed),
)
</script>

<template>
  <section class="pdf-import" data-testid="curriculum-pdf-import">
    <header class="pdf-import__head">
      <h2>培养方案 PDF 导入</h2>
      <p class="pdf-import__lead">
        上传原专业与目标专业的培养方案 PDF，系统解析出结构化课程表、
        解析证据与<strong>需要人工确认</strong>的条目。
      </p>
      <p v-if="!enabled" class="pdf-import__notice" data-testid="pdf-import-disabled">
        ⛔ 培养方案导入通道未启用（<code>VITE_CURRICULUM_IMPORT_API_ENABLED=false</code>）。
        本页不会伪造解析结果。
      </p>
      <p v-else class="pdf-import__boundary" data-testid="pdf-import-boundary">
        ⚠️ 上传成功、解析成功、点击确认，<strong>都不代表</strong>来源已被核验。
        本 PDF 是<strong>由教务网页重排生成的转换件</strong>，
        ⛔ 不是学校正式签发的原始 PDF。来源核验只能由<strong>项目组长</strong>批准。
      </p>
      <p v-if="!enabled" class="pdf-import__boundary" data-testid="pdf-import-role-boundary">
        ⚠️ 无论通道是否启用：本页<strong>不能</strong>批准来源。用户只能确认"解析结果与源 PDF 一致"；
        来源是否可信由<strong>项目组长</strong>依据来源材料决定。
      </p>
    </header>

    <fieldset class="pdf-import__meta">
      <legend>本次导入的上下文（⛔ 不由 PDF 推断）</legend>
      <label>
        原专业名称
        <input v-model="originMajor" data-testid="pdf-origin-major" type="text" />
      </label>
      <label>
        目标专业名称
        <input v-model="targetMajor" data-testid="pdf-target-major" type="text" />
      </label>
      <label>
        年级
        <input v-model="cohort" data-testid="pdf-cohort" type="text" size="6" />
      </label>
    </fieldset>

    <fieldset class="pdf-import__doc-types">
      <legend>培养方案版本（只能选**已验收**的文档类型）</legend>
      <label>
        文档类型
        <select v-model="documentTypeKey" data-testid="pdf-document-type">
          <option v-if="documentTypes.length === 0" value="">（尚未取得清单）</option>
          <option v-for="item in documentTypes" :key="item.key" :value="item.key">
            {{ item.label }}
          </option>
        </select>
      </label>
      <p class="pdf-import__filemeta" data-testid="pdf-document-type-note">
        ⛔ 这里只选择"用哪份**已验收声明**解析"，⛔ 不能提交任何课程列位映射。
        后端会按<strong>内容结构</strong>核对上传的文件是否真的是该文档类型，
        不一致即拒绝；专业名、文件名、角色<strong>都不参与</strong>真实性判定。
      </p>
      <p v-if="documentTypes.length === 0 && !documentTypesError" class="pdf-import__filemeta">
        正在获取已验收文档类型清单…
      </p>
    </fieldset>

    <div class="pdf-import__slots">
      <article
        v-for="slot in [
          { role: 'origin' as CurriculumRole, state: origin, title: '原专业培养方案' },
          { role: 'target' as CurriculumRole, state: target, title: '目标专业培养方案' },
        ]"
        :key="slot.role"
        class="pdf-import__slot"
        :data-testid="`pdf-slot-${slot.role}`"
      >
        <h3>{{ slot.title }}</h3>

        <label class="pdf-import__source">
          来源说明（由提交者提供，组长核对）
          <input
            v-if="slot.role === 'origin'"
            v-model="originSource"
            :data-testid="`pdf-source-${slot.role}`"
            type="text"
          />
          <input
            v-else
            v-model="targetSource"
            :data-testid="`pdf-source-${slot.role}`"
            type="text"
          />
        </label>

        <p
          v-if="documentTypesError"
          class="pdf-import__error"
          data-testid="pdf-document-types-error"
          role="alert"
        >
          ⛔ 无法取得已验收文档类型清单：{{ documentTypesError }}
        </p>

        <input
          type="file"
          accept=".pdf,application/pdf"
          :disabled="!enabled"
          :data-testid="`pdf-file-${slot.role}`"
          @change="onFileChange(slot.role, $event)"
        />
        <p class="pdf-import__filemeta">
          文件名：<strong>{{ slot.state.file?.name ?? '未选择' }}</strong>
          <span v-if="slot.state.file">
            （{{ (slot.state.file.size / 1024).toFixed(0) }} KiB，上限 {{ maxMiB }} MiB）
          </span>
        </p>
        <p class="pdf-import__filemeta">
          状态：<strong :data-testid="`pdf-status-${slot.role}`">{{ slot.state.status }}</strong>
        </p>

        <button
          type="button"
          :disabled="
            !enabled
            || slot.state.file === null
            || slot.state.status === 'uploading'
            || documentTypeKey === ''
          "
          :data-testid="`pdf-upload-${slot.role}`"
          @click="upload(slot.role)"
        >
          上传并解析
        </button>

        <p
          v-if="errorLabel(slot.state)"
          class="pdf-import__error"
          :data-testid="`pdf-error-${slot.role}`"
          role="alert"
        >
          ⛔ {{ errorLabel(slot.state) }}
        </p>

        <template v-if="slot.state.result">
          <p class="pdf-import__ok" :data-testid="`pdf-summary-${slot.role}`">
            已解析：课程 <strong>{{ slot.state.result.draft.course_records.length }}</strong> 条，
            待确认 <strong>{{ slot.state.result.draft.unresolved_rows.length }}</strong> 条，
            文件摘要 <code>{{ slot.state.result.source.sha256.slice(0, 16) }}…</code>
          </p>

          <div class="pdf-import__review" :data-testid="`pdf-review-${slot.role}`">
            <p>
              审核状态：<strong>{{ slot.state.result.source.review_conclusion }}</strong>
              · 来源核验 <strong>{{ slot.state.result.source.verification_verified ? '已核验' : '未核验' }}</strong>
              · 完整 <strong>{{ slot.state.result.source.complete ? '是' : '否' }}</strong>
            </p>
            <p>
              是否学校正式签发 PDF：
              <strong>{{ slot.state.result.source.is_official_school_pdf ? '是' : '否（转换件）' }}</strong>
            </p>
            <ul>
              <li v-for="note in slot.state.result.source.notes" :key="note">{{ note }}</li>
            </ul>
          </div>

          <table
            v-if="slot.state.result.draft.course_records.length > 0"
            class="pdf-import__table"
            :data-testid="`pdf-courses-${slot.role}`"
          >
            <thead>
              <tr>
                <th>课程号</th><th>课程名称</th><th>学分</th><th>类别</th>
                <th>建议学期</th><th>来源定位</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="record in slot.state.result.draft.course_records"
                :key="record.source_record"
              >
                <td>{{ record.course_id ?? '—' }}</td>
                <td>{{ record.course_name ?? '—' }}</td>
                <td>{{ record.credit ?? '—' }}</td>
                <td>{{ record.requirement }}</td>
                <td>{{ record.recommended_term_text ?? '—' }}</td>
                <td><code>{{ record.source_record }}</code></td>
              </tr>
            </tbody>
          </table>
          <p v-else class="pdf-import__empty" :data-testid="`pdf-no-courses-${slot.role}`">
            ⛔ 没有识别出任何课程行。请查看下面的待确认问题清单与解析问题；
            本页<strong>不会</strong>用演示数据替代。
          </p>

          <div
            v-if="slot.state.result.draft.unresolved_rows.length > 0"
            class="pdf-import__unresolved"
            :data-testid="`pdf-unresolved-${slot.role}`"
          >
            <h4>需要人工确认的条目（{{ slot.state.result.draft.unresolved_rows.length }}）</h4>
            <ul>
              <li
                v-for="row in slot.state.result.draft.unresolved_rows"
                :key="row.source_record"
              >
                <code>{{ row.source_record }}</code>
                — {{ row.course_name ?? '（无课程名）' }}
                <span v-if="row.issues?.length">
                  · 问题：{{ row.issues.map((issue) => issue.code).join('、') }}
                </span>
              </li>
            </ul>
          </div>

          <div
            v-if="slot.state.result.draft.document_issues.length > 0"
            class="pdf-import__issues"
            :data-testid="`pdf-issues-${slot.role}`"
          >
            <h4>解析问题</h4>
            <ul>
              <li
                v-for="issue in slot.state.result.draft.document_issues"
                :key="`${issue.code}-${issue.table_index}-${issue.row_index}`"
              >
                {{ issue.code }}（表 {{ issue.table_index }} / 行 {{ issue.row_index }}）
              </li>
            </ul>
          </div>

          <div class="pdf-import__human" :data-testid="`pdf-human-${slot.role}`">
            <h4>必须由人确认的字段</h4>
            <ul>
              <li v-for="item in slot.state.result.draft.human_required" :key="item.field">
                <strong>{{ item.field }}</strong>（{{ item.applies_to }}）：{{ item.reason }}
              </li>
            </ul>
          </div>

          <label class="pdf-import__confirm">
            <input
              v-model="slot.state.parseConfirmed"
              type="checkbox"
              :data-testid="`pdf-confirm-${slot.role}`"
            />
            我确认<strong>解析结果与源 PDF 一致</strong>
            （这只表示"读对了"，⛔ <strong>不代表</strong>来源已被核验或批准）
          </label>
        </template>
      </article>
    </div>

    <footer class="pdf-import__footer">
      <p data-testid="pdf-import-next">
        <template v-if="anyParsed && allConfirmed">
          解析结果已确认。<strong>下一步由项目组长</strong>依据来源材料决定是否批准；
          在组长批准前，这些草稿的 <code>verified=false</code> / <code>complete=false</code>，
          ⛔ 不会被真实规划使用。
        </template>
        <template v-else-if="anyParsed">
          请先核对课程表与待确认清单，并勾选"解析结果与源 PDF 一致"。
        </template>
        <template v-else>
          请选择两份 PDF 并分别上传解析。
        </template>
      </p>
      <button type="button" data-testid="pdf-reset" @click="resetAll">清空</button>
    </footer>
  </section>
</template>

<style scoped>
.pdf-import {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pdf-import__lead,
.pdf-import__notice,
.pdf-import__boundary,
.pdf-import__filemeta,
.pdf-import__ok,
.pdf-import__empty {
  margin: 4px 0;
}
.pdf-import__notice,
.pdf-import__error {
  color: #8a1c1c;
  background: #fdecec;
  padding: 8px;
  border-radius: 4px;
}
.pdf-import__boundary {
  background: #fff8e1;
  padding: 8px;
  border-radius: 4px;
}
.pdf-import__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.pdf-import__doc-types {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pdf-import__meta label,
.pdf-import__source {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.pdf-import__slots {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 16px;
}
.pdf-import__slot {
  border: 1px solid #d8d8d8;
  border-radius: 6px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pdf-import__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.pdf-import__table th,
.pdf-import__table td {
  border: 1px solid #e0e0e0;
  padding: 4px 6px;
  text-align: left;
}
.pdf-import__review,
.pdf-import__unresolved,
.pdf-import__issues,
.pdf-import__human {
  background: #f7f7f7;
  border-radius: 4px;
  padding: 8px;
  font-size: 13px;
}
.pdf-import__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
</style>
