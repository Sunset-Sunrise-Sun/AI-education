<script setup lang="ts">
import { DATA_MODE_LABEL } from '../state/userInput'
import type { DataMode } from '../config'

/**
 * 数据模式（Mock / Real）与提交区。
 *
 * 边界（本轮最重要的一条之一）：
 * - 页面必须能明确显示**当前数据模式**；
 * - Real Planning 接口（`POST /api/v1/plan`）尚未合并进 main 时，
 *   提交按钮**保持 disabled**，并且**绝不**把 Real 提交偷偷改调 Mock 接口；
 * - ⛔ 本组件不发任何请求，只表达"当前是否可用"与把点击事件交给父级。
 */
defineProps<{
  /** 当前数据模式。 */
  mode: DataMode
  /** Real Planning 接口是否已可用（由 `VITE_PLAN_API_ENABLED` 决定）。 */
  planApiEnabled: boolean
  /** 是否可提交（输入完整性 + provenance 门禁，均不是可行性判断）。 */
  inputValid: boolean
  /** 是否正在提交。 */
  submitting: boolean
  /** Real Planning 失败时的错误信息；没有失败时为空字符串。 */
  errorMessage?: string
  /** provenance 门禁：当前课表含 Mock 教学班 → 禁止提交到 Real Planning。 */
  scheduleProvenanceBlocked?: boolean
}>()

const emit = defineEmits<{
  (event: 'submit-real'): void
}>()
</script>

<template>
  <div class="uig-submit">
    <div class="uig-mode">
      <span
        class="tag"
        :class="mode === 'real' ? 'tag--source-real' : 'tag--source-mock'"
        data-testid="data-mode-tag"
      >
        {{ DATA_MODE_LABEL[mode] }}
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

      <!-- provenance 门禁优先提示：这是"课表来源不对"，与表单填错是两件事 -->
      <p
        v-if="scheduleProvenanceBlocked"
        class="uig-error"
        data-testid="schedule-provenance-blocked-hint"
        role="alert"
      >
        当前课表来源为 Mock 教学班，不能提交到 Real Planning。
        <br />
        真实教学班（<code class="mono">data_source = "real"</code>）接入前，请先取消勾选当前课表中的 Mock 教学班，
        或保持当前课表为空。
      </p>
      <p v-if="!planApiEnabled" class="uig-field__hint" data-testid="real-plan-disabled-hint">
        真实规划接口 <code class="mono">POST /api/v1/plan</code> 尚在并行开发中（<code class="mono">feature/real-plan-api</code>），
        因此该按钮暂不可用。Mock 演示通道保持原样，<strong>不会</strong>在 Real 提交失败时回退到 Mock。
      </p>
      <p
        v-else-if="scheduleProvenanceBlocked"
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

      <!-- Real Planning 失败：如实报错，不回退 Mock、不展示替代结果 -->
      <p v-if="errorMessage" class="uig-error" data-testid="real-plan-error" role="alert">
        Real Planning 调用失败：{{ errorMessage }}
        <br />
        本页<strong>不会</strong>在失败时回退到 Mock 通道，也不会自行生成替代方案。
      </p>
    </div>
  </div>
</template>
