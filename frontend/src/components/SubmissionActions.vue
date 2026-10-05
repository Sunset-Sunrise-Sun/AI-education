<script setup lang="ts">
import { computed } from 'vue'
import { PLAN_RESULT_SOURCE_LABEL, describePlanError } from '../state/userInput'
import type { PlanResultSource } from '../config'

/**
 * **规划结果来源**与提交区。
 *
 * 边界：
 * - 页面显示的是**规划结果的来源**（局部 provenance），
 *   不是"整页数据模式"：`POST /api/v1/plan` 只返回 `PlanResult`，
 *   培养要求评估 / 教学班 / 偏好仍全部是 Mock 演示数据；
 * - `VITE_PLAN_API_ENABLED` 只控制 **Real submit 是否开放**：
 *   不改变 Mock Demo 获取、不触发自动请求、不改变 provenance gate；
 * - ⛔ 本组件不发任何请求，只表达"当前是否可用"与把点击事件交给父级。
 */
const props = defineProps<{
  /** 规划结果的来源。 */
  mode: PlanResultSource
  /** Real Planning 接口是否已开放（由 `VITE_PLAN_API_ENABLED` 决定）。 */
  planApiEnabled: boolean
  /** 是否可提交（输入完整性 + 课表 provenance 门禁，均不是可行性判断）。 */
  inputValid: boolean
  /** 是否正在提交。 */
  submitting: boolean
  /** Real Planning 失败时的错误信息；没有失败时为空字符串。 */
  errorMessage?: string
  /**
   * Real Planning 失败的**类型**（`PlanErrorKind`）。
   *
   * UI 只按这个分支，因此 503"未装配"不会被笼统显示成"请求失败"。
   */
  errorKind?: string | null
  /** 失败时的 HTTP 状态码；网络错误为 `null`。 */
  errorStatus?: number | null
  /** 后端返回的机器可读错误码（如 `real_pipeline_not_configured`）。 */
  errorCode?: string | null
  /**
   * 课表 provenance 门禁的阻止原因（fail closed）；`null` 表示通过。
   *
   * 不同原因对应不同提示（含 Mock 教学班 vs 来源未经确认）。
   */
  scheduleBlockReason?: string | null
}>()

const emit = defineEmits<{
  (event: 'submit-real'): void
}>()

/** 失败文案：按 `kind` 分类，而不是统一写"请求失败"。 */
const errorDisplay = computed(() =>
  props.errorKind ? describePlanError(props.errorKind, props.errorStatus ?? null) : null,
)
</script>

<template>
  <div class="uig-submit">
    <div class="uig-mode">
      <span
        class="tag"
        :class="mode === 'real' ? 'tag--source-real' : 'tag--source-mock'"
        data-testid="data-mode-tag"
      >
        {{ PLAN_RESULT_SOURCE_LABEL[mode] }}
      </span>
      <span class="uig-mode__hint" data-testid="data-mode-hint">
        <template v-if="mode === 'mock'">
          Mock 演示通道（<code class="mono">GET /api/v1/mock/demo</code>）持续保留；本页当前展示的仍是该通道数据。
        </template>
        <template v-else>
          <strong>规划结果</strong>已来自 <code class="mono">POST /api/v1/plan</code>（Real）；
          培养要求评估 / 教学班 / 偏好仍为 Mock 演示数据。
        </template>
      </span>
    </div>

    <div class="uig-submit__action">
      <button
        class="button"
        type="button"
        data-testid="real-plan-submit"
        :disabled="!planApiEnabled || !inputValid || submitting"
        @click="emit('submit-real')"
      >
        {{ submitting ? '正在请求 Real Planning…' : '生成规划（Real Planning）' }}
      </button>

      <!-- 课表 provenance 门禁（fail closed）：这是"课表来源不对"，与表单填错是两件事 -->
      <p
        v-if="scheduleBlockReason"
        class="uig-error"
        data-testid="schedule-provenance-blocked-hint"
        role="alert"
      >
        {{ scheduleBlockReason }}
        <br />
        门禁只放行两种情况：<strong>当前课表为空</strong>，或<strong>每一项都明确为真实教学班</strong>
        （<code class="mono">data_source = "real"</code>）。含 Mock、来源混合或来源未经确认时一律阻止。
      </p>
      <p
        v-if="!planApiEnabled"
        class="uig-field__hint"
        data-testid="real-plan-disabled-hint"
      >
        真实规划接口 <code class="mono">POST /api/v1/plan</code> 尚在并行开发中（<code class="mono">feature/real-plan-api</code>），
        因此该按钮暂不可用。Mock 演示通道保持原样，<strong>不会</strong>在 Real 提交失败时回退到 Mock。
      </p>
      <p
        v-else-if="scheduleBlockReason"
        class="uig-field__hint"
        data-testid="real-plan-provenance-hint"
      >
        provenance 门禁已阻止提交；未发出任何请求。
      </p>
      <p v-else-if="!inputValid" class="uig-field__hint" data-testid="real-plan-invalid-hint">
        请先修正表单：学期需为 <code class="mono">YYYY-1</code> / <code class="mono">YYYY-2</code>，
        回避时段的结束节不得早于起始节。
      </p>
      <p v-else class="uig-field__hint">
        提交内容仅包含 <code class="mono">semester</code> / <code class="mono">current_schedule</code> /
        <code class="mono">preference</code> 三个字段。
      </p>

      <!--
        Real Planning 失败：按**类型**分类展示，不回退 Mock、不展示替代结果。

        ⚠️ 503 real_pipeline_not_configured 是"**运行时尚未装配**"这一当前正确状态，
        不是系统故障，因此单独标题、单独说明，绝不与 500 混为一谈。
      -->
      <div v-if="errorDisplay" class="uig-error" data-testid="real-plan-error" role="alert">
        <p class="uig-error__title" data-testid="real-plan-error-title">
          {{ errorDisplay.title }}
        </p>
        <p class="uig-error__hint" data-testid="real-plan-error-hint">
          {{ errorDisplay.hint }}
        </p>
        <p class="uig-error__meta" data-testid="real-plan-error-meta">
          <span v-if="errorStatus !== null && errorStatus !== undefined" class="mono">
            HTTP {{ errorStatus }}
          </span>
          <span v-if="errorCode" class="mono" data-testid="real-plan-error-code">
            {{ errorCode }}
          </span>
          <span v-if="errorKind" class="mono">{{ errorKind }}</span>
        </p>
        <p v-if="errorMessage" class="uig-error__detail" data-testid="real-plan-error-detail">
          {{ errorMessage }}
        </p>
        <p class="uig-error__hint">
          本页<strong>不会</strong>在失败时回退到 Mock 通道，也不会自行生成替代方案。
        </p>
      </div>
    </div>
  </div>
</template>
