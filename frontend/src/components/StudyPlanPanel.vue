<script setup lang="ts">
/**
 * 培养方案面板 —— 展示 `GET /api/v1/study-plans/{major_id}` 的**真实**内容。
 *
 * 语义：回答「目标专业**要求**我完成什么？」
 *   ⚠️ 与「补修缺口分析」严格区分：本面板回答"要求是什么"，
 *      缺口分析回答"我还缺什么"。⛔ 本组件不判定谁该补修。
 *
 * ⛔ 组件内不含任何课程号/课程名判断；⛔ 不读前端演示配置。
 */

import { computed } from 'vue'

import { electivePoolOf, prerequisitesNote, requiredOf } from '../api/studyPlan'
import type { ElectiveProgress, StudyPlan } from '../types/studyPlan'

const props = defineProps<{
  /** 已加载的培养方案；未加载时为 `null`。 */
  plan: StudyPlan | null
  /** 加载状态（由父级驱动）。 */
  loading: boolean
  /** 加载失败原因（已翻译为学生可读文案）；空串表示无错误。 */
  error: string
  /** 当前选中的专业名（用于空状态说明）。 */
  majorName: string
  /**
   * 课程组学分进度（Phase 4）。
   *
   * ⚠️ 只有**规划结果**里才有（它依赖学生成绩单）；
   *   ⛔ 前端不计算，只展示后端下发的数字。
   */
  electiveProgress?: readonly ElectiveProgress[]
}>()

const required = computed(() => (props.plan ? requiredOf(props.plan) : []))
const electives = computed(() => (props.plan ? electivePoolOf(props.plan) : []))
const groups = computed(() => props.plan?.elective_pool.groups ?? [])
const note = computed(() => (props.plan ? prerequisitesNote(props.plan) : ''))
const progress = computed(() => props.electiveProgress ?? [])

/** 课程组名称（来自进度项自身，后端已下发中文名）。 */
function groupLabel(item: ElectiveProgress): string {
  return item.group_name || item.group_id
}

/**
 * 学分进度的展示文案。
 *
 * ⚠️ `undecided` 必须如实说明"无法确定"，⛔ 不得把 null 显示成 0。
 */
function progressText(item: ElectiveProgress): string {
  if (item.undecided) {
    return '该选修组的历史学分额度无法从培养方案来源中确定，需要人工确认后才能计算进度。'
  }
  return (
    `要求 ${item.required_credit ?? 0} 学分 · ` +
    `已认定 ${item.earned_credit ?? 0} 学分 · ` +
    `还差 ${item.remaining_credit ?? 0} 学分`
  )
}

/** 该组是否已经满足（还差 0 学分）。 */
function isSatisfied(item: ElectiveProgress): boolean {
  return !item.undecided && (item.remaining_credit ?? 0) <= 0
}
</script>

<template>
  <section class="plan" data-testid="case-a-study-plan">
    <p v-if="loading" class="plan__state" data-testid="case-a-study-plan-loading">
      正在加载培养方案…
    </p>

    <p
      v-else-if="error"
      class="plan__state plan__state--error"
      role="alert"
      data-testid="case-a-study-plan-error"
    >
      {{ error }}
    </p>

    <p v-else-if="!plan" class="plan__state" data-testid="case-a-study-plan-empty">
      请先选择目标专业，系统会加载该专业的培养方案。
    </p>

    <template v-else>
      <dl class="plan__meta" data-testid="case-a-study-plan-meta">
        <div>
          <dt>目标专业</dt>
          <dd data-testid="case-a-study-plan-major">{{ plan.name }}</dd>
        </div>
        <div>
          <dt>年级</dt>
          <dd>{{ plan.cohort }}</dd>
        </div>
        <div>
          <dt>培养要求总数</dt>
          <dd data-testid="case-a-study-plan-total">{{ plan.counts.total }}</dd>
        </div>
        <div>
          <dt>必修</dt>
          <dd data-testid="case-a-study-plan-required-count">{{ plan.counts.required }}</dd>
        </div>
        <div>
          <dt>专业选修</dt>
          <dd data-testid="case-a-study-plan-elective-count">{{ plan.counts.elective }}</dd>
        </div>
      </dl>

      <!--
        ⚠️ Phase 6 收尾：**删除**「与你的成绩单匹配结果」整块。
           理由：这几个数字在下方「补修缺口分析」里已经有完整呈现（含判定理由与依据），
           放在培养方案面板里既重复、又让用户以为要看两处。
           培养方案面板只回答「要求是什么」，⛔ 不再回答「我匹配到什么程度」。
      -->

      <!--
        ⚠️ 学分进度：数字**全部来自后端** matching 层（`elective_progress`），
           ⛔ 前端不计算剩余学分。后端用与判定相同的口径计算，
              因此这里的数字与「谁该补修」的结论必然一致。
      -->
      <div v-if="progress.length > 0" class="plan__progress" data-testid="case-a-elective-progress">
        <p class="plan__progress-title">选修学分进度（由培养方案匹配引擎计算）</p>
        <ul class="plan__progress-list">
          <li
            v-for="item in progress"
            :key="item.group_id"
            data-testid="case-a-elective-progress-item"
          >
            <span class="plan__progress-group">{{ groupLabel(item) }}</span>
            <span
              class="plan__progress-value"
              :class="isSatisfied(item) ? 'plan__progress-value--ok' : ''"
              data-testid="case-a-elective-progress-value"
            >
              {{ progressText(item) }}
            </span>
            <span class="plan__progress-state">
              {{ item.undecided ? '待人工确认' : isSatisfied(item) ? '✅ 已满足' : '仍需选修' }}
            </span>
            <!--
              ⚠️ 额度口径差异由**后端**解释，⛔ 不在前端硬编码理由。
            -->
            <span
              v-if="item.scope_note"
              class="plan__progress-scope"
              data-testid="case-a-elective-progress-scope"
            >
              {{ item.scope_note }}
            </span>
          </li>
        </ul>
      </div>

      <p
        v-if="groups.length > 0"
        class="plan__note"
        data-testid="case-a-study-plan-elective-group"
      >
        选修组：{{ groups.map((g) => g.name).join('、') }}；
        培养方案写明的学分下限为
        {{ groups.reduce((sum, g) => sum + (g.minimum_credit ?? 0), 0) }} 学分。
        这是培养方案的<strong>整份</strong>要求，不等于本学期待完成的额度
        （实际进度见上方由匹配引擎计算的结果）。
      </p>

      <!--
        先修关系如实说明：真实培养方案没有先修列，
        这直接解释了匹配结果为什么全部需要人工确认。⛔ 不隐藏、⛔ 不美化。
      -->
      <p class="plan__source" data-testid="case-a-study-plan-source">
        来源：{{ plan.source_id }}（{{ plan.complete ? '来源声明完整' : '来源声明不完整' }}）
      </p>
      <p
        v-if="note"
        class="plan__note"
        data-testid="case-a-study-plan-prerequisites-note"
      >
        {{ note }}
      </p>

      <p class="plan__note" data-testid="case-a-study-plan-scope">
        本面板只列出培养要求的<strong>统计</strong>；「哪些还没完成」由下方
        「补修缺口分析」结合实际成绩单给出，两者不混用。
      </p>
    </template>
  </section>
</template>

<style scoped>
.plan {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plan__state {
  margin: 0;
  color: #55606e;
  font-size: 13px;
  line-height: 1.6;
}

.plan__state--error {
  color: #b3261e;
}

.plan__meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px 16px;
  margin: 0;
}

.plan__meta dt {
  color: #6b7683;
  font-size: 12px;
}

.plan__meta dd {
  margin: 2px 0 0;
  font-size: 14px;
  font-weight: 600;
}

.plan__source,
.plan__note {
  margin: 0;
  color: #6b7683;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}

.plan__section {
  margin: 12px 0 4px;
  font-size: 14px;
}

/* 学分进度（后端计算） */
.plan__progress {
  margin: 0 0 8px;
  padding: 10px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #f2f7ff;
}

.plan__progress-title {
  margin: 0 0 6px;
  color: #1e293b;
  font-size: 13px;
  font-weight: 700;
}

.plan__progress-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.plan__progress-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  align-items: baseline;
  padding: 3px 0;
  font-size: 13px;
}

.plan__progress-group {
  font-weight: 600;
}

.plan__progress-value {
  color: #33404f;
}

.plan__progress-value--ok {
  color: #15803d;
  font-weight: 600;
}

.plan__progress-state {
  color: #6b7683;
  font-size: 12px;
}

/* 额度口径说明（后端给出）：占整行，避免被误读成矛盾数字 */
.plan__progress-scope {
  flex: 1 1 100%;
  color: #8a5a00;
  font-size: 12px;
  line-height: 1.6;
}

.plan__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid #eef2f6;
  max-height: 320px;
  overflow-y: auto;
}

.plan__list li {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  gap: 12px;
  align-items: center;
  padding: 6px 2px;
  border-bottom: 1px solid #eef2f6;
  font-size: 13px;
}

.plan__name {
  font-weight: 600;
}

.plan__id,
.plan__meta-cell {
  color: #6b7683;
  font-size: 12px;
  white-space: nowrap;
}
</style>
