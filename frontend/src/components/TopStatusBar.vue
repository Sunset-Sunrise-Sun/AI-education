<script setup lang="ts">
import { APP_SUBTITLE, APP_TITLE } from '../config'

defineProps<{
  /** 后端响应头 X-Data-Source 的值；请求失败时为 null。 */
  dataSource: string | null
}>()

function scrollToSection(id: string) {
  const el = document.getElementById(id)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth' })
  }
}
</script>

<template>
  <header class="topbar">
    <div class="topbar__main">
      <div class="topbar__brand">
        <div class="topbar__logo" aria-hidden="true">🎓</div>
        <div>
          <div class="topbar__title-line">
            <h1 class="topbar__title">{{ APP_TITLE }}</h1>
            <span class="badge-env">AI 学业规划助手</span>
          </div>
          <p class="topbar__subtitle">{{ APP_SUBTITLE }}</p>
        </div>
      </div>

      <!--
        ⚠️ 比赛展示优化：删除了「系统模式 Phase 2A/2B 联调演示」与「数据安全级别 脱敏验证环境」
           两项内部状态——它们对评委与学生都无意义。
      -->
      <dl class="topbar__meta">
        <div class="topbar__meta-item">
          <dt>数据来源</dt>
          <dd class="mono source-val">
            <span class="status-dot"></span>
            {{ dataSource ?? '等待连接' }}
          </dd>
        </div>
      </dl>
    </div>

    <!-- 快捷导航 -->
    <nav class="topbar__nav" aria-label="模块快速跳转">
      <span class="nav-label">快速导航：</span>
      <button type="button" class="nav-btn" @click="scrollToSection('section-user-input')">
        0. 用户输入
      </button>
      <button type="button" class="nav-btn" @click="scrollToSection('section-makeup')">
        1. 培养要求评估
      </button>
      <button type="button" class="nav-btn" @click="scrollToSection('section-offerings')">
        2. 开课教学班
      </button>
      <button type="button" class="nav-btn" @click="scrollToSection('section-preference')">
        3. 用户偏好
      </button>
      <button type="button" class="nav-btn nav-btn--accent" @click="scrollToSection('section-plan')">
        4. 学习路径规划
      </button>
    </nav>
  </header>

  <!--
    ⚠️ 比赛展示优化：横幅文案改为学生/评委可理解的说法，
       ⛔ 不再出现「Mock 演示通道」「人工虚构」等工程表达。
       安全语义（以学校教务系统为准、不能作为正式依据）完整保留。
  -->
  <div class="mock-banner" role="alert">
    <span class="mock-banner__icon">⚠️</span>
    <div class="mock-banner__text">
      <strong>当前展示为演示数据，最终结果以学校教务系统为准。</strong>
      <span>
        页面中的课程、教学班、教师与方案仅用于完整业务链条的交互原型验证，<strong>不能直接作为真实选课、退课或毕业学分认定的正式依据</strong>。
      </span>
    </div>
  </div>
</template>
