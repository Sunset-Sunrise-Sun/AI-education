<script setup lang="ts">
/**
 * 比赛演示路线（8 个场景）。
 *
 * 边界：
 * - **纯导航与展示**：只提供锚点跳转与一句话看点，⛔ 不做任何业务判断、
 *   ⛔ 不计算冲突 / 可行性、⛔ 不读取任何接口数据；
 * - 场景文案必须与页面实际区块一致：锚点指向真实存在的区块 id；
 * - 场景 5–8 都在第 4 区（PlanResult）内部，分别指向 changes / risks /
 *   selected_classes / unresolved 四个子块，避免把不同业务语义混成一个。
 */
interface DemoScene {
  /** 场景序号（1–8）。 */
  index: number
  /** 场景标题。 */
  title: string
  /** 一句话看点（画面定位用，不是业务结论）。 */
  hint: string
  /** 页面锚点（指向真实区块 id）。 */
  anchor: string
}

const scenes: readonly DemoScene[] = [
  {
    index: 1,
    title: '转专业背景',
    hint: '目标学期与转专业上下文输入',
    anchor: '#section-user-input',
  },
  {
    index: 2,
    title: '学业差异',
    hint: '目标培养方案要求 vs 已修记录',
    anchor: '#section-makeup',
  },
  {
    index: 3,
    title: '历史培养要求评估',
    hint: '逐条状态：已满足 / 待课程认定 / 已确认需补修',
    anchor: '#section-makeup',
  },
  {
    index: 4,
    title: '教学班供给 + 学生偏好',
    hint: '演示快照 + 偏好约束',
    anchor: '#section-offerings',
  },
  {
    index: 5,
    title: '风险与未决',
    hint: 'risks：排课信息未知时如实说明',
    anchor: '#section-plan-risks',
  },
  {
    index: 6,
    title: 'Path Repair',
    hint: 'changes：原班级 → 调整为 + 调整原因',
    anchor: '#section-plan-changes',
  },
  {
    index: 7,
    title: '方案与建议课表',
    hint: 'selected_classes：建议方案',
    anchor: '#section-plan-selected',
  },
  {
    index: 8,
    title: '人工确认模型',
    hint: 'unresolved：待人工确认 / 缺少数据',
    anchor: '#section-plan-unresolved',
  },
]
</script>

<template>
  <nav class="scene-guide" data-testid="demo-scene-guide" aria-label="比赛演示路线（8 个场景）">
    <span class="scene-guide__title">演示路线（8 场景）</span>
    <ol class="scene-guide__list">
      <li v-for="scene in scenes" :key="scene.index" class="scene-guide__item">
        <a class="scene-guide__link" :href="scene.anchor">
          <span class="scene-guide__num">{{ scene.index }}</span>
          <span class="scene-guide__body">
            <strong class="scene-guide__name">{{ scene.title }}</strong>
            <small class="scene-guide__hint">{{ scene.hint }}</small>
          </span>
        </a>
      </li>
    </ol>
  </nav>
</template>
