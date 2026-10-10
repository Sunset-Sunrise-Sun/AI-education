<script setup lang="ts">
/**
 * 课程分类**审核**面板（⚠️ 本轮新增）。
 *
 * ```text
 * 候选列表（编码/名称/学分/学期/候选类别）
 *    ├ 证据展开：来源定位 + **原文**（PDF 里真实存在的文字）
 *    ├ 逐条操作：确认 / 人工修改（必填理由）/ 暂缓
 *    └ 状态提示：无证据、依据冲突、仅小节级
 * 类别最低学分原文  |  审核进度  |  未解决清单  |  导出审核草稿
 * ```
 *
 * ## ⛔ 本组件刻意不做的事
 *
 * | ⛔ 不做 | 为什么 |
 * | --- | --- |
 * | 显示"已获学校认证 / 已完成正式课程认定" | 审核决定只是内部草稿，未认证、未批准 |
 * | 一键确认无证据 / 冲突项 | 服务端会拒绝；界面也不提供该按钮 |
 * | 让"拒绝"自动改成相反类别 | ⛔ 拒绝 = 暂缓（回到未确定） |
 * | 提交证据 / 原文 / SHA-256 | 那些只由服务端保管 |
 * | 直接改 JSON | 组长只做点选 |
 */

import { computed, ref } from 'vue'

import {
  CANDIDATE_STATUS_LABEL,
  REQUIREMENT_LABEL,
  ReviewApiError,
  REVIEW_ERROR_LABEL,
  exportReviewDraft,
  fetchReviewSession,
  submitReviewDecisions,
  type ReviewAction,
  type ReviewCandidate,
  type ReviewSession,
} from '../api/curriculumReview'

const props = withDefaults(
  defineProps<{
    /** 解析 PDF 后返回的 `review_id`。 */
    reviewId: string
    /**
     * 通道开关。默认 `true`：**是否放行**由父组件（读取 `VITE_*` 档位）决定，
     * 本组件只负责"被放行后才发请求"。
     */
    enabled?: boolean
  }>(),
  { enabled: true },
)

const session = ref<ReviewSession | null>(null)
const loading = ref(false)
const errorKind = ref<keyof typeof REVIEW_ERROR_LABEL | null>(null)
/** 正在编辑的定位（人工修改需要先选类别 + 填理由）。 */
const editing = ref<string | null>(null)
const draftRequirement = ref<'required' | 'elective'>('required')
const draftReason = ref('')
const busyRecord = ref<string | null>(null)
const exported = ref<Record<string, unknown> | null>(null)

const enabled = computed(() => props.enabled)

async function load(): Promise<void> {
  if (!props.reviewId) {
    return
  }
  loading.value = true
  errorKind.value = null
  try {
    session.value = await fetchReviewSession(props.reviewId, { enabled: enabled.value })
  } catch (error) {
    session.value = null
    errorKind.value = error instanceof ReviewApiError ? error.kind : 'network'
  } finally {
    loading.value = false
  }
}

async function decide(candidate: ReviewCandidate, action: ReviewAction): Promise<void> {
  const input: {
    source_record: string
    action: ReviewAction
    requirement?: 'required' | 'elective'
    reason?: string
  } = { source_record: candidate.source_record, action }

  if (action === 'override') {
    if (!draftReason.value.trim()) {
      // ⛔ 前端也拦一道：人工修改必须留理由
      errorKind.value = 'override_requires_reason'
      return
    }
    input.requirement = draftRequirement.value
    input.reason = draftReason.value.trim()
  }

  busyRecord.value = candidate.source_record
  errorKind.value = null
  try {
    session.value = await submitReviewDecisions(props.reviewId, [input], {
      enabled: enabled.value,
    })
    editing.value = null
    draftReason.value = ''
  } catch (error) {
    errorKind.value = error instanceof ReviewApiError ? error.kind : 'network'
  } finally {
    busyRecord.value = null
  }
}

async function doExport(): Promise<void> {
  errorKind.value = null
  try {
    exported.value = await exportReviewDraft(props.reviewId, { enabled: enabled.value })
  } catch (error) {
    errorKind.value = error instanceof ReviewApiError ? error.kind : 'network'
  }
}

function startEdit(candidate: ReviewCandidate): void {
  editing.value = candidate.source_record
  draftRequirement.value =
    candidate.proposed_requirement === 'elective' ? 'elective' : 'required'
  draftReason.value = ''
}

/** 是否可以"确认"：⛔ 冲突 / 无证据 / 候选未确定都不允许。 */
function canConfirm(candidate: ReviewCandidate): boolean {
  return candidate.status === 'single_source' && candidate.proposed_requirement !== 'unknown'
}

function requirementText(value: string): string {
  return REQUIREMENT_LABEL[value] ?? value
}

/** 重复课程编码（单独列出，⛔ 不自动合并）。 */
const duplicateIds = computed(() => {
  const counts = new Map<string, number>()
  for (const item of session.value?.candidates ?? []) {
    counts.set(item.course_id, (counts.get(item.course_id) ?? 0) + 1)
  }
  return new Set([...counts.entries()].filter(([, n]) => n > 1).map(([id]) => id))
})

const noEvidence = computed(
  () => session.value?.candidates.filter((item) => item.status === 'no_evidence') ?? [],
)
const conflicting = computed(
  () => session.value?.candidates.filter((item) => item.status === 'conflicting') ?? [],
)
const sectionOnly = computed(
  () =>
    session.value?.candidates.filter(
      (item) => item.status === 'single_source' && !item.evidence_complete,
    ) ?? [],
)

defineExpose({ load })
</script>

<template>
  <section
    class="review"
    data-testid="curriculum-review"
    :data-review-id="reviewId || '(empty)'"
  >
    <header class="review__head">
      <h3>课程分类审核（草稿）</h3>
      <p class="review__boundary" data-testid="review-boundary">
        ⚠️ 这里的决定是<strong>内部审核草稿</strong>：<strong>未</strong>经过身份认证，
        <strong>未</strong>完成独立来源批准。⛔ 不代表学校已认定课程类别或学分，
        ⛔ 不作为正式个人补修规划的放行依据。
      </p>
      <p v-if="!enabled" class="review__notice" data-testid="review-disabled">
        ⛔ 审核通道未启用。
      </p>
      <p v-else-if="errorKind" class="review__error" data-testid="review-error" role="alert">
        ⛔ {{ REVIEW_ERROR_LABEL[errorKind] }}
      </p>
    </header>

    <button
      v-if="!session && !loading"
      type="button"
      data-testid="review-load"
      @click="load"
    >
      载入审核状态
    </button>
    <p v-if="loading" data-testid="review-loading">正在载入…</p>

    <template v-if="session">
      <!-- 进度 -->
      <div class="review__progress" data-testid="review-progress">
        <span>候选 {{ session.progress.total_candidates }}</span>
        <span>已确认 <strong>{{ session.progress.confirmed }}</strong></span>
        <span>人工修改 <strong>{{ session.progress.overridden }}</strong></span>
        <span>暂缓 <strong>{{ session.progress.deferred }}</strong></span>
        <span>未处理 <strong data-testid="review-undecided">{{ session.progress.undecided }}</strong></span>
        <span>无证据 <strong>{{ session.progress.no_evidence }}</strong></span>
        <span>冲突 <strong>{{ session.progress.conflicting }}</strong></span>
      </div>

      <!-- 课程组/类别最低学分原文 -->
      <div
        v-if="session.category_requirements.length"
        class="review__group"
        data-testid="review-category-requirements"
      >
        <h4>类别最低学分要求（文档原文，⛔ 非成员学分求和）</h4>
        <ul>
          <li v-for="item in session.category_requirements" :key="item.source_record">
            <strong>{{ item.category_code }}</strong>
            （{{ requirementText(item.requirement) }}）
            = {{ item.minimum_credit ?? '—' }} 学分
            · 原文 <code>{{ item.raw_text }}</code>
            · <code>{{ item.source_record }}</code>
          </li>
        </ul>
      </div>

      <!-- 候选列表 -->
      <h4>分类候选（逐条审核）</h4>
      <table class="review__table" data-testid="review-candidates">
        <thead>
          <tr>
            <th>课程编码</th><th>候选类别</th><th>状态</th><th>来源定位</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in session.candidates"
            :key="item.source_record"
            :data-testid="`review-row-${item.source_record}`"
          >
            <td>
              {{ item.course_id }}
              <span
                v-if="duplicateIds.has(item.course_id)"
                class="review__dup"
                :data-testid="`review-dup-${item.source_record}`"
              >重复编码</span>
            </td>
            <td>
              {{ requirementText(item.proposed_requirement) }}
              <span v-if="item.proposed_category_code">
                ({{ item.proposed_category_code }})
              </span>
            </td>
            <td>
              {{ CANDIDATE_STATUS_LABEL[item.status] }}
              <span v-if="item.status === 'single_source' && !item.evidence_complete">
                · 仅模块小节依据
              </span>
            </td>
            <td><code>{{ item.source_record }}</code></td>
            <td class="review__actions">
              <button
                type="button"
                :disabled="!canConfirm(item) || busyRecord === item.source_record"
                :data-testid="`review-confirm-${item.source_record}`"
                @click="decide(item, 'confirm')"
              >确认</button>
              <button
                type="button"
                :disabled="busyRecord === item.source_record"
                :data-testid="`review-override-${item.source_record}`"
                @click="startEdit(item)"
              >人工修改</button>
              <button
                type="button"
                :disabled="busyRecord === item.source_record"
                :data-testid="`review-defer-${item.source_record}`"
                @click="decide(item, 'defer')"
              >暂缓</button>

              <div
                v-if="editing === item.source_record"
                class="review__edit"
                :data-testid="`review-edit-${item.source_record}`"
              >
                <select v-model="draftRequirement" data-testid="review-edit-requirement">
                  <option value="required">必修</option>
                  <option value="elective">选修</option>
                </select>
                <input
                  v-model="draftReason"
                  data-testid="review-edit-reason"
                  placeholder="审核理由（必填）"
                  type="text"
                />
                <button
                  type="button"
                  :data-testid="`review-edit-save-${item.source_record}`"
                  @click="decide(item, 'override')"
                >保存人工结论</button>
                <p class="review__hint">
                  这条结论来自<strong>人工判断</strong>，⛔ 不是 PDF 原文证据。
                </p>
              </div>

              <p v-if="item.decision" :data-testid="`review-decision-${item.source_record}`">
                当前：{{ item.decision.action }}
                <span v-if="item.decision.requirement">
                  → {{ requirementText(item.decision.requirement) }}
                </span>
                <span v-if="item.decision.reason">（理由：{{ item.decision.reason }}）</span>
              </p>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 证据展开 -->
      <details class="review__evidence" data-testid="review-evidence">
        <summary>查看原文证据（共 {{ session.candidates.length }} 条候选）</summary>
        <div
          v-for="item in session.candidates"
          :key="`ev-${item.source_record}`"
          :data-testid="`review-evidence-${item.source_record}`"
        >
          <p><strong>{{ item.course_id }}</strong> · <code>{{ item.source_record }}</code></p>
          <ul v-if="item.evidence.length">
            <li v-for="(ev, index) in item.evidence" :key="index">
              [{{ ev.kind }}] 原文：<code>{{ ev.raw_text }}</code>
              <span v-if="ev.category_code">（代号 {{ ev.category_code }}）</span>
              · 来源 <code>{{ ev.source_record }}</code>
            </li>
          </ul>
          <p v-else class="review__hint">
            ⛔ 文档中未找到该课程的分类依据（保持「未确定」）。
          </p>
        </div>
      </details>

      <!-- 未解决清单 -->
      <div class="review__unresolved" data-testid="review-unresolved">
        <h4>未解决问题</h4>
        <p>无证据：<strong data-testid="review-no-evidence-count">{{ noEvidence.length }}</strong> 条</p>
        <p>依据冲突：<strong>{{ conflicting.length }}</strong> 条</p>
        <p>仅模块小节依据：<strong>{{ sectionOnly.length }}</strong> 条</p>
        <p v-if="session.section_rows.length">
          模块标题行（⛔ 不是课程）：
          <strong data-testid="review-section-rows">{{ session.section_rows.length }}</strong> 条
        </p>
        <p v-if="session.unmapped_category_codes.length">
          未映射类别代号（⛔ 未猜成必修/选修）：
          <code>{{ session.unmapped_category_codes.join('、') }}</code>
        </p>
      </div>

      <footer class="review__footer">
        <button type="button" data-testid="review-export" @click="doExport">
          导出审核草稿
        </button>
        <span class="review__hint">
          导出文件恒为草稿（<code>verified=false</code>），并绑定原始 PDF 摘要。
        </span>
      </footer>

      <pre
        v-if="exported"
        class="review__export"
        data-testid="review-export-preview"
      >{{ JSON.stringify({
        conclusion: exported.conclusion,
        verification: exported.verification,
        identity_authentication: exported.identity_authentication,
        source_sha256: (exported.source as Record<string, unknown> | undefined)?.source_sha256,
        unresolved_items: Array.isArray(exported.unresolved_items)
          ? (exported.unresolved_items as unknown[]).length : 0,
      }, null, 2) }}</pre>
    </template>
  </section>
</template>

<style scoped>
.review {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.review__boundary {
  background: #fff8e1;
  padding: 8px;
  border-radius: 4px;
}
.review__notice,
.review__error {
  color: #8a1c1c;
  background: #fdecec;
  padding: 8px;
  border-radius: 4px;
}
.review__progress {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 13px;
  background: #f4f6f8;
  padding: 8px;
  border-radius: 4px;
}
.review__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.review__table th,
.review__table td {
  border: 1px solid #e0e0e0;
  padding: 4px 6px;
  text-align: left;
  vertical-align: top;
}
.review__actions button {
  margin-right: 4px;
}
.review__edit {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.review__dup {
  color: #8a5a00;
  background: #fff3cd;
  border-radius: 3px;
  padding: 0 4px;
  margin-left: 4px;
  font-size: 12px;
}
.review__hint {
  color: #555;
  font-size: 12px;
}
.review__group,
.review__unresolved {
  background: #f7f7f7;
  border-radius: 4px;
  padding: 8px;
  font-size: 13px;
}
.review__footer {
  display: flex;
  align-items: center;
  gap: 10px;
}
.review__export {
  background: #0f172a;
  color: #e2e8f0;
  padding: 10px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
}
</style>
