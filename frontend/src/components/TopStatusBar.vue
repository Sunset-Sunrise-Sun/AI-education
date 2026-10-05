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
            <span class="badge-env">Demo Prototype</span>
          </div>
          <p class="topbar__subtitle">{{ APP_SUBTITLE }}</p>
        </div>
      </div>

      <dl class="topbar__meta">
        <div class="topbar__meta-item">
          <dt>系统模式</dt>
          <dd>Phase 2A/2B 联调演示</dd>
        </div>
        <div class="topbar__meta-item">
          <dt>后端数据源标头</dt>
          <dd class="mono source-val">
            <span class="status-dot"></span>
            {{ dataSource ?? '等待连接' }}
          </dd>
        </div>
        <div class="topbar__meta-item">
          <dt>数据安全级别</dt>
          <dd>脱敏验证环境</dd>
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
        4. 重构方案与求解
      </button>
    </nav>
  </header>

  <!-- 模拟数据醒目标识 -->
  <div class="mock-banner" role="alert">
    <span class="mock-banner__icon">⚠️</span>
    <div class="mock-banner__text">
      <strong>当前展示的是 Mock 演示通道数据（人工虚构），不是真实教务在线数据。</strong>
      <span>
        页面中的课程、教学班、教师与方案仅用于完整业务链条的交互原型验证，<strong>不能直接作为真实选课、退课或毕业学分认定的正式依据</strong>。
      </span>
    </div>
  </div>
</template>
