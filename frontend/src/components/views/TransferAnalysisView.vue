<script setup lang="ts">
import { computed, ref } from 'vue'
import MakeupTaskList from '../MakeupTaskList.vue'
import type { MakeupTask } from '../../types/contracts'
import type { CurriculumVersionMetadata, PersonalPlanResult } from '../../api/personalPlanning'
import type { PersonalPhase } from '../../composables/usePersonalPlanning'

/**
 * `转专业分析` 视图：原 / 目标培养方案版本、认定状态与缺口。
 *
 * 硬边界：
 * - 目录未配置时明确说明"没有已核验版本目录"，⛔ 不退回固定 Case A；
 * - `planning = null` 时明确显示"本次没有排课"及原因，⛔ 不显示"已排好课"；
 * - 前端**不生成** MakeupTask：缺口一律来自后端返回。
 */
const props = defineProps<{
  phase: PersonalPhase
  selectableVersions: CurriculumVersionMetadata[]
  rejectedVersions: { version_id: string; code: string; detail: string }[]
  catalogReason: string
  result: PersonalPlanResult | null
  errorMessage: string
  errorKind: string | null
  errorCode: string | null
  previewNotice: string | null
  apiEnabled: boolean
  /** 已修 / 当前课表上下文（只读展示，来自用户输入区）。 */
  currentSemester: string
  currentScheduleCount: number
}>()

const emit = defineEmits<{
  (event: 'submit', payload: { oldVersionId: string; targetVersionId: string }): void
  (event: 'reload'): void
  (event: 'use-results', makeupTasks: MakeupTask[], planning: PersonalPlanResult['planning']): void
}>()

const oldVersionId = ref('')
const targetVersionId = ref('')

const busy = computed(() => props.phase === 'submitting')

const canSubmit = computed(
  () =>
    !busy.value &&
    oldVersionId.value !== '' &&
    targetVersionId.value !== '' &&
    oldVersionId.value !== targetVersionId.value,
)

const statusCounts = computed<Record<string, number>>(() => props.result?.status_counts ?? {})

const skippedCodeLabels: Record<string, string> = {
  no_course_data: '当前没有已装配的真实教学班供给，因此没有调用 Planner',
  no_semester: '本次没有指定要排进哪个学期，因此没有调用 Planner',
  semester_not_bound: '目标学期与已装配的教学班供给不一致，因此没有调用 Planner',
}

const skippedLabel = computed(() => {
  const code = props.result?.planning_skipped_code
  if (!code) {
    return '后端未返回跳过原因码'
  }
  return skippedCodeLabels[code] ?? `未识别的跳过原因码：${code}`
})

function submit(): void {
  if (!canSubmit.value) {
    return
  }
  emit('submit', { oldVersionId: oldVersionId.value, targetVersionId: targetVersionId.value })
}

function versionLabel(version: CurriculumVersionMetadata): string {
  const parts = [version.major, version.cohort ? `${version.cohort} 级` : '']
  if (version.campus) {
    parts.push(version.campus)
  }
  return `${parts.filter(Boolean).join(' · ')}（${version.version_id}）`
}
</script>

<template>
  <section class="view view--transfer" data-testid="view-transfer-analysis">
    <header class="view__head">
      <h2>转专业分析</h2>
      <p>
        选择<strong>原专业</strong>与<strong>目标专业</strong>的已核验培养方案版本，
        系统按你本人录入的已修记录独立计算缺口。
        这里<strong>不会</strong>沿用固定 Case A 或他人的认定结论。
      </p>
    </header>

    <p v-if="previewNotice" class="ai-preview" data-testid="personal-preview-notice">
      ⚠️ {{ previewNotice }}
    </p>

    <!-- 目录状态：未配置 / 加载中 / 空 / 错误 -->
    <div v-if="phase === 'not_configured'" class="error-box" data-testid="personal-not-configured">
      <p class="state state--error">没有已核验的培养方案版本目录</p>
      <p class="state__detail" data-testid="personal-error-detail">{{ errorMessage }}</p>
      <p class="state__hint">
        因此个人规划入口<strong>没有可选版本</strong>；页面<strong>不会</strong>退回固定 Case A
        或其他学生的结论来冒充个人结果。
      </p>
      <button type="button" class="button button--ghost" data-testid="personal-reload" @click="emit('reload')">
        🔄 重新检查目录
      </button>
    </div>

    <div v-else-if="phase === 'disabled'" class="ai-view__blocked" data-testid="personal-disabled">
      <p class="state state--error">个人规划通道未启用</p>
      <p class="state__detail">
        设置 <code class="mono">VITE_PERSONAL_PLANNING_API_ENABLED=true</code> 后，
        本页会调用已存在的个人规划接口；未配置已核验目录时后端会明确回答"无可用版本"。
      </p>
    </div>

    <div v-else-if="phase === 'loading'" class="state state--loading" data-testid="personal-loading">
      正在读取已核验版本目录…
    </div>

    <div v-else-if="phase === 'empty'" class="ai-view__blocked" data-testid="personal-empty">
      <p class="state state--error">目录里没有可选版本</p>
      <p class="state__detail">
        后端回答了空目录（{{ catalogReason }}）：所有条目都未通过核验或来源声明不支持。
        页面不会猜测任何版本。
      </p>
      <ul v-if="rejectedVersions.length > 0" class="view__rejected" data-testid="personal-rejected">
        <li v-for="item in rejectedVersions" :key="item.version_id">
          <span class="mono">{{ item.version_id }}</span>
          <span class="tag tag--ai-unknown">{{ item.code }}</span>
          {{ item.detail }}
        </li>
      </ul>
    </div>

    <div v-else-if="phase === 'error'" class="error-box" data-testid="personal-error">
      <p class="state state--error">读取版本目录失败</p>
      <p class="state__detail">{{ errorMessage }}</p>
      <p class="state__hint">
        失败类型：<code class="mono" data-testid="personal-error-kind">{{ errorKind ?? 'unknown' }}</code>
        <span v-if="errorCode"> · 错误码：<code class="mono">{{ errorCode }}</code></span>
        —— 页面不会用演示数据顶替。
      </p>
      <button type="button" class="button button--ghost" @click="emit('reload')">🔄 重试</button>
    </div>

    <template v-else>
      <div class="transfer-form">
        <label class="ai-field">
          <span>原专业培养方案版本</span>
          <select v-model="oldVersionId" data-testid="personal-old-version" :disabled="busy">
            <option value="">请选择…</option>
            <option v-for="version in selectableVersions" :key="version.version_id" :value="version.version_id">
              {{ versionLabel(version) }}
            </option>
          </select>
        </label>

        <label class="ai-field">
          <span>目标专业培养方案版本</span>
          <select v-model="targetVersionId" data-testid="personal-target-version" :disabled="busy">
            <option value="">请选择…</option>
            <option v-for="version in selectableVersions" :key="version.version_id" :value="version.version_id">
              {{ versionLabel(version) }}
            </option>
          </select>
        </label>

        <div class="transfer-form__meta">
          <p>
            本次学期：<code class="mono">{{ currentSemester || '未指定' }}</code> ·
            当前课表教学班：<strong class="num">{{ currentScheduleCount }}</strong> 个
          </p>
          <p class="ai-block__hint">
            提交内容仅包含版本选择、脱敏后的已修课程记录与偏好；
            ⛔ 不包含姓名、学号、成绩单原文或任何凭据。
          </p>
        </div>

        <button
          type="button"
          class="button"
          data-testid="personal-submit"
          :disabled="!canSubmit"
          @click="submit"
        >
          {{ busy ? '正在计算…' : '📐 用我的记录计算缺口' }}
        </button>
        <p v-if="oldVersionId !== '' && oldVersionId === targetVersionId" class="ai-block__hint">
          原专业与目标专业不能选择同一个版本。
        </p>
      </div>

      <ul v-if="rejectedVersions.length > 0" class="view__rejected" data-testid="personal-rejected">
        <li v-for="item in rejectedVersions" :key="item.version_id">
          <span class="mono">{{ item.version_id }}</span>
          <span class="tag tag--ai-unknown">{{ item.code }}</span>
          {{ item.detail }}
        </li>
      </ul>

      <div v-if="result" class="transfer-result" data-testid="personal-result">
        <div class="view__cards">
          <article class="ai-view__card">
            <h3>版本</h3>
            <p>原专业：{{ result.old_version.major }}（{{ result.old_version.cohort }} 级）</p>
            <p>目标专业：{{ result.target_version.major }}（{{ result.target_version.cohort }} 级）</p>
            <p class="ai-block__hint">
              数据来源：<span class="mono" data-testid="personal-data-source">{{ result.data_source }}</span>
            </p>
          </article>

          <article class="ai-view__card">
            <h3>认定状态分布</h3>
            <ul class="ai-view__stats" data-testid="personal-status-counts">
              <li>需要补修：<strong class="num">{{ statusCounts['required'] ?? 0 }}</strong></li>
              <li>可能等价（待确认）：<strong class="num">{{ statusCounts['possibly_equivalent'] ?? 0 }}</strong></li>
              <li>待人工确认：<strong class="num">{{ statusCounts['manual_confirmation'] ?? 0 }}</strong></li>
              <li>已满足：<strong class="num">{{ statusCounts['satisfied'] ?? 0 }}</strong></li>
            </ul>
            <p class="ai-block__hint">
              已修记录条数：<strong class="num">{{ result.completed_record_count }}</strong>
            </p>
          </article>
        </div>

        <div class="transfer-result__planning" data-testid="personal-planning-status">
          <template v-if="result.planning">
            <p class="transfer-result__ok">
              本次已生成可展示的规划结果（Planner 状态：<span class="mono">{{ result.planning.status }}</span>）。
            </p>
            <button
              type="button"
              class="button"
              data-testid="personal-use-results"
              @click="emit('use-results', result.makeup_tasks, result.planning)"
            >
              ➡️ 用作当前补修方案（进入补修路径 / AI 调整）
            </button>
          </template>
          <template v-else>
            <p class="transfer-result__skip" data-testid="personal-planning-skipped">
              <strong>本次没有生成排课结果</strong>：{{ skippedLabel }}。
            </p>
            <p class="state__detail" data-testid="personal-skipped-reason">
              {{ result.planning_skipped_reason }}
            </p>
            <p class="ai-block__hint">
              补修任务（"缺什么课"）仍然有效；但本方案<strong>不代表</strong>任何可执行课表，
              也不代表学校已完成认定。
            </p>
          </template>
        </div>

        <ul v-if="result.notes.length > 0" class="view__notes" data-testid="personal-notes">
          <li v-for="(note, index) in result.notes" :key="index">{{ note }}</li>
        </ul>

        <h3 class="transfer-result__title">培养要求缺口（后端逐条判定）</h3>
        <MakeupTaskList :tasks="result.makeup_tasks" />
      </div>
    </template>
  </section>
</template>
