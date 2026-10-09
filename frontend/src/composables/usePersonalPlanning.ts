/**
 * 个人规划（`转专业分析` 视图）的界面状态机。
 *
 * 硬边界：
 * - **尊重真实 readiness**：目录未配置（503）时明确显示"没有已核验版本目录"，
 *   ⛔ **不退回固定 Case A 冒充个人结果**；
 * - `planning = null` 是**合法结果**（没有排课能力），界面必须显示跳过原因，
 *   ⛔ 不得显示"已排好课"；
 * - 预览 fixture 只在 `preview=true` 时使用，并醒目标注；真实失败**不 fallback**。
 */

import { computed, ref } from 'vue'
import {
  PersonalPlanningApiError,
  fetchCurriculumVersions,
  submitPersonalPlan,
  type CurriculumVersionList,
  type PersonalPlanRequest,
  type PersonalPlanResult,
} from '../api/personalPlanning'
import { PERSONAL_PREVIEW_NOTICE, PREVIEW_PERSONAL_PLAN, PREVIEW_VERSION_LIST } from '../api/personalPlanningFixtures'

export type PersonalPhase =
  | 'disabled'
  | 'loading'
  | 'ready'
  | 'not_configured'
  | 'empty'
  | 'error'
  | 'submitting'
  | 'planned'

export interface PersonalPlanningOptions {
  /** 真实通道是否启用。 */
  enabled: boolean
  /** 前端预览模式（只读 fixture）。 */
  preview: boolean
}

export function usePersonalPlanning(options: PersonalPlanningOptions) {
  const phase = ref<PersonalPhase>(options.enabled || options.preview ? 'loading' : 'disabled')
  const catalog = ref<CurriculumVersionList | null>(null)
  const result = ref<PersonalPlanResult | null>(null)
  const errorMessage = ref('')
  const errorKind = ref<string | null>(null)
  const errorCode = ref<string | null>(null)
  const previewActive = computed(() => options.preview)
  const previewNotice = computed(() => (options.preview ? PERSONAL_PREVIEW_NOTICE : null))

  const selectableVersions = computed(() => catalog.value?.versions ?? [])
  const rejectedVersions = computed(() => catalog.value?.rejected ?? [])

  /** 后端明确说明"本次没有排课"时，界面据此显示原因（⛔ 不显示"已排好课"）。 */
  const planningSkipped = computed(
    () => result.value !== null && result.value.planning === null,
  )

  async function loadCatalog(): Promise<void> {
    if (options.preview) {
      catalog.value = PREVIEW_VERSION_LIST
      phase.value = PREVIEW_VERSION_LIST.versions.length > 0 ? 'ready' : 'empty'
      return
    }
    if (!options.enabled) {
      phase.value = 'disabled'
      return
    }

    phase.value = 'loading'
    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null

    try {
      const payload = await fetchCurriculumVersions()
      catalog.value = payload
      phase.value = payload.versions.length > 0 ? 'ready' : 'empty'
    } catch (error) {
      if (error instanceof PersonalPlanningApiError) {
        errorKind.value = error.kind
        errorCode.value = error.code
        errorMessage.value = error.message
        phase.value = error.kind === 'not_configured' ? 'not_configured' : 'error'
      } else {
        errorKind.value = 'unexpected'
        errorMessage.value = '加载版本目录时发生未知错误。'
        phase.value = 'error'
      }
    }
  }

  async function submit(request: PersonalPlanRequest): Promise<void> {
    if (options.preview) {
      result.value = PREVIEW_PERSONAL_PLAN
      phase.value = 'planned'
      return
    }
    if (!options.enabled) {
      phase.value = 'disabled'
      return
    }

    phase.value = 'submitting'
    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null

    try {
      result.value = await submitPersonalPlan(request)
      phase.value = 'planned'
    } catch (error) {
      // 失败时**不保留半截结果**，也绝不用预览数据顶替。
      result.value = null
      if (error instanceof PersonalPlanningApiError) {
        errorKind.value = error.kind
        errorCode.value = error.code
        errorMessage.value = error.message
        phase.value = error.kind === 'not_configured' ? 'not_configured' : 'error'
      } else {
        errorKind.value = 'unexpected'
        errorMessage.value = '提交个人规划时发生未知错误。'
        phase.value = 'error'
      }
    }
  }

  function reset(): void {
    result.value = null
    errorMessage.value = ''
    errorKind.value = null
    errorCode.value = null
    phase.value = catalog.value === null ? 'loading' : catalog.value.versions.length > 0 ? 'ready' : 'empty'
  }

  return {
    phase,
    catalog,
    result,
    errorMessage,
    errorKind,
    errorCode,
    previewActive,
    previewNotice,
    selectableVersions,
    rejectedVersions,
    planningSkipped,
    loadCatalog,
    submit,
    reset,
  }
}
