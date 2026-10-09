<script setup lang="ts">
import { computed } from 'vue'
import type { MakeupTask } from '../../types/contracts'
import { PLAN_STATUS_LABEL } from '../../utils/labels'
import type { PlanResult } from '../../types/contracts'

/**
 * `AI 调整` 视图：说明 AI 调整能做什么，并给出**醒目**的自然语言入口。
 *
 * 硬边界：
 * - 本视图**不生成**任何方案、不调用 Planner、不调用模型；
 * - 只负责入口与"当前调整的是哪一份方案"的说明，能力与状态一律由抽屉呈现；
 * - 示例语句只是**输入提示**，⛔ 不代表系统已经解析或已经改过方案。
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

const emit = defineEmits<{
  (event: 'open-drawer', seedMessage?: string): void
}>()

/**
 * 示例语句：只用于提示"你可以怎么说"，⛔ 不是已解析的意图、也不代表能改成功。
 *
 * ⚠️ 刻意避开"帮我选最轻松的课"这类需要系统替用户做价值判断的说法：
 * 学分上限、硬约束都必须由用户自己给。
 */
const EXAMPLE_UTTERANCES = [
  { text: '这学期太累，尽量别在周五上课', hint: '表达负荷与时间偏好' },
  { text: '数据结构必须保留，其它可以调整', hint: '指定必须保留的课程' },
  { text: '本学期学分上限 22，先补必修', hint: '给出明确的学分上限' },
] as const

/** 状态分布按 `MakeupTask.status` 现场计数（⛔ 不推断，只统计后端给定状态）。 */
const statusSummary = computed(() => {
  const counts: Record<string, number> = {}
  for (const task of props.makeupTasks) {
    counts[task.status] = (counts[task.status] ?? 0) + 1
  }
  return [
    { label: '需要补修', value: counts['required'] ?? 0, tone: 'required' },
    { label: '可能等价（待确认）', value: counts['possibly_equivalent'] ?? 0, tone: 'equivalent' },
    { label: '待人工确认', value: counts['manual_confirmation'] ?? 0, tone: 'manual' },
    { label: '已满足', value: counts['satisfied'] ?? 0, tone: 'satisfied' },
  ]
})

const lockedCandidates = computed(() => props.makeupTasks.slice(0, 6))

const selectedClassCount = computed(() => props.currentPlan?.selected_classes.length ?? 0)
</script>

<template>
  <section class="view view--ai" data-testid="view-ai-adjust">
    <header class="view__head">
      <h2>AI 调整</h2>
      <p>
        对<strong>当前这份补修方案</strong>说一句你的想法，系统先解析成"待确认的约束"，
        你确认之后才会去算候选；候选要再确认一次才会替换当前方案。
        这里不是通用聊天窗口，也不会在前端重算课表。
      </p>
    </header>

    <div v-if="!ready" class="ai-view__blocked" data-testid="ai-view-not-ready">
      <p class="state state--error">当前还没有可调整的方案</p>
      <p class="state__detail">{{ notReadyReason ?? '请先在「转专业分析」生成个人规划结果。' }}</p>
      <p class="state__hint">
        没有方案时，AI 调整<strong>不会</strong>凭空产生一个方案；请先完成上一步。
      </p>
    </div>

    <template v-else>
      <!-- 醒目的自然语言入口：一句话开始 -->
      <section class="ai-cta" data-testid="ai-cta">
        <div class="ai-cta__lead">
          <h3>用一句话说明你想怎么调整</h3>
          <p class="ai-cta__sub">
            不需要专业术语。你可以只说"太累""想轻松一点""哪门课必须留"，
            也可以直接给出学分上限数字。
          </p>
        </div>

        <div class="ai-cta__examples" data-testid="ai-cta-examples">
          <span class="ai-cta__examples-label">可以这样说：</span>
          <button
            v-for="example in EXAMPLE_UTTERANCES"
            :key="example.text"
            type="button"
            class="ai-cta__chip"
            :data-testid="`ai-example-${example.text}`"
            :title="`${example.hint}（点击后打开面板并填入这句话）`"
            @click="emit('open-drawer', example.text)"
          >
            「{{ example.text }}」
          </button>
        </div>

        <div class="ai-cta__actions">
          <button
            type="button"
            class="button ai-cta__button"
            data-testid="ai-view-open-drawer"
            @click="emit('open-drawer')"
          >
            💬 打开 AI 调整面板
          </button>
          <span class="ai-cta__note">
            打开后：① 确认意图 → ② 查看候选对比 → ③ 确认采用或保留原方案。
            <strong>两次确认缺一不可。</strong>
          </span>
        </div>
      </section>

      <!-- 始终显示"当前调整的是哪一份方案" -->
      <section class="ai-target" data-testid="ai-target">
        <div class="ai-target__main">
          <span class="ai-target__label">当前调整对象</span>
          <strong class="ai-target__value" data-testid="ai-view-plan-label">{{ currentPlanLabel }}</strong>
          <span v-if="currentPlan" class="tag tag--plan" :class="`tag--plan-${currentPlan.status}`">
            {{ PLAN_STATUS_LABEL[currentPlan.status] }}
          </span>
          <span v-else class="text-muted">当前没有可展示的规划结果</span>
        </div>
        <ul class="ai-target__facts">
          <li v-if="currentPlan">
            建议教学班 <strong class="num">{{ selectedClassCount }}</strong> 个
          </li>
          <li v-if="currentPlan">
            已选调班 <strong class="num">{{ currentPlan.changes.length }}</strong> 项 ·
            风险 <strong class="num">{{ currentPlan.risks.length }}</strong> 项 ·
            未决 <strong class="num">{{ currentPlan.unresolved.length }}</strong> 项
          </li>
          <li v-if="adoptedVersion !== null && adoptedVersion !== undefined" data-testid="ai-view-adopted-version">
            <span class="tag tag--ai-unknown">进程内会话版本 {{ adoptedVersion }}</span>
            已采用但<strong>未持久化</strong>，服务重启即失效
          </li>
        </ul>
        <p class="ai-block__hint" data-testid="ai-view-digest-note">
          方案指纹由<strong>后端</strong>在解析意图时计算并返回；前端不自行计算或改写，
          也不会把调整应用到别的方案上。
        </p>
      </section>

      <div class="view__cards">
        <article class="ai-view__card">
          <h3>补修任务概览</h3>
          <ul class="ai-view__stats" data-testid="ai-view-status-summary">
            <li v-for="entry in statusSummary" :key="entry.label">
              {{ entry.label }}：<strong class="num">{{ entry.value }}</strong>
            </li>
          </ul>
          <p v-if="makeupTasks.length === 0" class="empty-state">
            当前没有补修任务上下文，AI 仍可调整课表，但无法核对"该补哪些课"。
          </p>
        </article>

        <article class="ai-view__card">
          <h3>可以在调整时说"必须保留"的课程</h3>
          <ul v-if="lockedCandidates.length > 0" data-testid="ai-view-lock-candidates">
            <li v-for="task in lockedCandidates" :key="task.course_id">
              <span class="mono">{{ task.course_id }}</span> {{ task.course_name }}
            </li>
          </ul>
          <p v-else class="empty-state">当前没有可保留的课程上下文。</p>
        </article>
      </div>

      <div class="ai-view__steps" data-testid="ai-two-step-guide">
        <div class="ai-view__step">
          <span class="ai-view__step-num">1</span>
          <div>
            <strong>第一次确认：意图</strong>
            <p>
              硬约束（不可协商）与软偏好（可协商）<strong>分开显示</strong>；
              学分上限没说到就是"未指定"，<strong>系统不会替你猜</strong>。
            </p>
          </div>
        </div>
        <div class="ai-view__step">
          <span class="ai-view__step-num">2</span>
          <div>
            <strong>候选对比</strong>
            <p>只展示后端求解出来的差异：新增 / 移除 / 换班 / 学分变化 / 风险 / 未决。</p>
          </div>
        </div>
        <div class="ai-view__step">
          <span class="ai-view__step-num">3</span>
          <div>
            <strong>第二次确认：采用或保留</strong>
            <p>
              采用只是<strong>进程内临时生效</strong>（未持久化，也不代表教务系统已完成选课）；
              拒绝 / 过期 / 失败时原方案一个字都不改。
            </p>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
