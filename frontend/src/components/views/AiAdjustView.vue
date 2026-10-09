<script setup lang="ts">
import { computed } from 'vue'
import type { MakeupTask } from '../../types/contracts'
import { PLAN_STATUS_LABEL } from '../../utils/labels'
import type { PlanResult } from '../../types/contracts'

/**
 * `AI 调整` 视图：描述 AI 调整抽屉能做什么，并给出打开入口。
 *
 * 硬边界：本视图**不生成**任何方案、不调用 Planner；
 * 调整能力与状态一律由 `AiAdjustDrawer` 呈现。
 */
const props = defineProps<{
  currentPlan: PlanResult | null
  currentPlanLabel: string
  /** 已采用的**进程内会话版本**（后端 adopted_version；未采用时为 null）。 */
  adoptedVersion?: number | null
  makeupTasks: MakeupTask[]
  ready: boolean
  notReadyReason: string | null
}>()

const emit = defineEmits<{ (event: 'open-drawer'): void }>()

/** 状态分布按 `MakeupTask.status` 现场计数（⛔ 不推断，只统计后端给定状态）。 */
const statusSummary = computed(() => {
  const counts: Record<string, number> = {}
  for (const task of props.makeupTasks) {
    counts[task.status] = (counts[task.status] ?? 0) + 1
  }
  return [
    { label: '需要补修', value: counts['required'] ?? 0 },
    { label: '可能等价（待确认）', value: counts['possibly_equivalent'] ?? 0 },
    { label: '待人工确认', value: counts['manual_confirmation'] ?? 0 },
    { label: '已满足', value: counts['satisfied'] ?? 0 },
  ]
})

const lockedCandidates = computed(() => props.makeupTasks.slice(0, 5))
</script>

<template>
  <section class="view view--ai" data-testid="view-ai-adjust">
    <header class="view__head">
      <h2>AI 调整</h2>
      <p>
        围绕<strong>当前选中的补修方案</strong>做对话式调整：先让 AI 解析你的说法，
        再经过<strong>两次确认</strong>（确认意图 → 确认采用），才会改动方案。
        这里不是独立聊天机器人，也不会在前端重算课表。
      </p>
    </header>

    <div v-if="!ready" class="ai-view__blocked" data-testid="ai-view-not-ready">
      <p class="state state--error">当前还没有可调整的方案</p>
      <p class="state__detail">{{ notReadyReason ?? '请先在「转专业分析」生成个人规划结果。' }}</p>
    </div>

    <template v-else>
      <div class="view__cards">
        <article class="ai-view__card">
          <h3>当前调整对象</h3>
          <p data-testid="ai-view-plan-label">{{ currentPlanLabel }}</p>
          <p class="ai-block__hint" data-testid="ai-view-digest-note">
            方案指纹由<strong>后端</strong>在解析意图时计算并返回；前端不自行计算或改写。
          </p>
          <p v-if="adoptedVersion !== null && adoptedVersion !== undefined" class="ai-block__unknown" data-testid="ai-view-adopted-version">
            当前方案来自 AI 采用（进程内会话版本 {{ adoptedVersion }}，未持久化）。
          </p>
          <p v-if="currentPlan">
            Planner 状态：
            <span class="tag tag--plan" :class="`tag--plan-${currentPlan.status}`">
              {{ PLAN_STATUS_LABEL[currentPlan.status] }}
            </span>
          </p>
          <p v-else class="text-muted">当前没有可展示的规划结果。</p>
        </article>

        <article class="ai-view__card">
          <h3>补修任务概览</h3>
          <ul class="ai-view__stats">
            <li v-for="entry in statusSummary" :key="entry.label">
              {{ entry.label }}：<strong class="num">{{ entry.value }}</strong>
            </li>
          </ul>
        </article>

        <article class="ai-view__card">
          <h3>可锁定课程（可用于"必须保留"）</h3>
          <ul>
            <li v-for="task in lockedCandidates" :key="task.course_id">
              <span class="mono">{{ task.course_id }}</span> {{ task.course_name }}
            </li>
          </ul>
          <p v-if="makeupTasks.length === 0" class="empty-state">当前没有补修任务上下文。</p>
        </article>
      </div>

      <div class="ai-view__actions">
        <button
          type="button"
          class="button"
          data-testid="ai-view-open-drawer"
          @click="emit('open-drawer')"
        >
          💬 打开 AI 调整面板
        </button>
        <span class="ai-block__hint">
          面板打开后：输入一句自然语言 → <strong>第一次确认</strong>意图 →
          求解候选 → <strong>第二次确认</strong>采用或保留原方案。
        </span>
      </div>

      <div class="ai-view__steps" data-testid="ai-two-step-guide">
        <div class="ai-view__step">
          <span class="ai-view__step-num">1</span>
          <div>
            <strong>第一次确认：意图</strong>
            <p>展示硬约束 / 软偏好 / 学分上限（不猜）/ 锁定课程 / 范围 / 未知项，可编辑。</p>
          </div>
        </div>
        <div class="ai-view__step">
          <span class="ai-view__step-num">2</span>
          <div>
            <strong>候选对比</strong>
            <p>只展示后端求解结果与原方案的差异（新增 / 移除 / 调班 / 学分 / 风险 / 未决）。</p>
          </div>
        </div>
        <div class="ai-view__step">
          <span class="ai-view__step-num">3</span>
          <div>
            <strong>第二次确认：采用或保留</strong>
            <p>只有后端确认采用成功才刷新当前方案；拒绝 / 过期 / 失败时原案不变。</p>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
