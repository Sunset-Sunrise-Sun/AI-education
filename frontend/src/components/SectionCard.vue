<script setup lang="ts">
/**
 * 所有展示区块共用的外壳容器：标题 + 副标题 + 内容插槽。
 * 保持设计统一与信息层级分明，无业务判断。
 *
 * ⚠️ 比赛展示优化：**不再渲染「Mock 数据」徽章**——它对评委与学生都是噪音。
 *   `mock` prop 与内部逻辑**完全保留**（调用方仍可传入，只是不再显示）。
 */
withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    /** 保留 prop（历史调用方会传），⛔ 当前不再影响渲染。 */
    mock?: boolean
    /** 需要强调时使用。 */
    tone?: 'default' | 'attention' | 'primary'
    /** 用于锚点定位与快捷跳转。 */
    sectionId?: string
    /** 数量徽章。 */
    badgeCount?: number
  }>(),
  {
    subtitle: '',
    mock: true,
    tone: 'default',
    sectionId: '',
    badgeCount: undefined,
  },
)
</script>

<template>
  <section
    :id="sectionId"
    class="card"
    :class="`card--${tone}`"
  >
    <header class="card__head">
      <div class="card__title-wrap">
        <h2 class="card__title">{{ title }}</h2>
        <span v-if="badgeCount !== undefined" class="card__count-badge">
          {{ badgeCount }}
        </span>
      </div>
      <!-- ⚠️ 比赛展示优化：原先此处的「Mock 数据」徽章（含 tooltip）已删除。 -->
    </header>

    <p v-if="subtitle" class="card__subtitle">{{ subtitle }}</p>

    <div class="card__body">
      <slot />
    </div>
  </section>
</template>
