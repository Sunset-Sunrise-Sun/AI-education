<script setup lang="ts">
/**
 * **联调用**调试信息面板（仅开发环境渲染）。
 *
 * ⛔ 严格边界：
 * - 只在 `dev` 为真时渲染（生产构建不出现）；
 * - 只显示**计数 / 枚举 / 状态**这类结构性信息；
 * - ⛔ 不显示成绩单内容、姓名、学号、GPA；
 * - ⛔ 不 dump 整个 request / response；
 * - ⛔ 不显示任何 token / cookie / header。
 */
export interface E2EDebugInfo {
  /** 真实规划接口地址。 */
  planEndpoint: string
  /** 请求中的学期（用户输入的结构性字段）。 */
  semester: string
  /** `current_schedule` 条目数（**只报数量，不列课程**）。 */
  scheduleCount: number
  /** `current_schedule` 的来源构成：空 / 全部 real / 含 mock / 来源未经确认。 */
  scheduleProvenance: string
  /**
   * 手工课表的**用户级确认**状态：none / unattested / attested。
   *
   * ⛔ 只报枚举，不含任何课程信息。
   */
  manualAttestation: string
  /** `preference` 是否已填写（**只报布尔**）。 */
  preferencePresent: boolean
  /** Real 提交开关是否开放。 */
  planApiEnabled: boolean
  /** 最近一次 Real 请求的 HTTP 状态码。 */
  lastHttpStatus: number | null
  /** 最近一次 Real 请求的失败类型。 */
  lastErrorKind: string | null
  /** 当前规划结果的来源。 */
  planResultSource: string
}

defineProps<{
  /** 是否处于开发环境；为假时整个面板不渲染。 */
  dev: boolean
  info: E2EDebugInfo
}>()
</script>

<template>
  <details v-if="dev" class="uig-debug" data-testid="e2e-debug">
    <summary class="uig-debug__summary">联调调试信息（仅开发环境）</summary>
    <dl class="uig-debug__grid">
      <div class="uig-debug__item">
        <dt>plan endpoint</dt>
        <dd class="mono" data-testid="debug-endpoint">{{ info.planEndpoint }}</dd>
      </div>
      <div class="uig-debug__item">
        <dt>request semester</dt>
        <dd class="mono" data-testid="debug-semester">{{ info.semester || '—' }}</dd>
      </div>
      <div class="uig-debug__item">
        <dt>current_schedule count</dt>
        <dd class="mono" data-testid="debug-schedule-count">{{ info.scheduleCount }}</dd>
      </div>
      <div class="uig-debug__item">
        <dt>current_schedule provenance</dt>
        <dd class="mono" data-testid="debug-schedule-provenance">{{ info.scheduleProvenance }}</dd>
      </div>
      <div class="uig-debug__item">
        <dt>manual attestation</dt>
        <dd class="mono" data-testid="debug-manual-attestation">{{ info.manualAttestation }}</dd>
      </div>
      <div class="uig-debug__item">
        <dt>preference present</dt>
        <dd class="mono" data-testid="debug-preference">{{ info.preferencePresent ? 'yes' : 'no' }}</dd>
      </div>
      <div class="uig-debug__item">
        <dt>plan api enabled</dt>
        <dd class="mono" data-testid="debug-enabled">{{ info.planApiEnabled ? 'true' : 'false' }}</dd>
      </div>
      <div class="uig-debug__item">
        <dt>last HTTP status</dt>
        <dd class="mono" data-testid="debug-status">
          {{ info.lastHttpStatus === null ? '—' : info.lastHttpStatus }}
        </dd>
      </div>
      <div class="uig-debug__item">
        <dt>last error kind</dt>
        <dd class="mono" data-testid="debug-error-kind">{{ info.lastErrorKind ?? '—' }}</dd>
      </div>
      <div class="uig-debug__item">
        <dt>plan result source</dt>
        <dd class="mono" data-testid="debug-result-source">{{ info.planResultSource }}</dd>
      </div>
    </dl>
    <p class="uig-debug__note">
      仅显示结构与状态信息：不含成绩内容、姓名、学号、GPA，不 dump 请求 / 响应，不显示任何凭据。
    </p>
  </details>
</template>
