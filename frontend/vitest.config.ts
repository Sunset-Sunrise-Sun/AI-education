import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

/**
 * 前端单元测试配置。
 *
 * ⚠️ 这是一个**独立**于生产构建的测试配置（`vite.config.ts` 与 `npm run build` 不受影响）。
 * 使用 jsdom 环境以便对表单做真实的交互测试（输入、勾选、增删行）。
 */
export default defineConfig({
  plugins: [vue()],
  define: {
    /**
     * 测试环境下把 Real Planning 开关置为 true，以便测试"提交 → 实际渲染 Real 结果"这条链路。
     *
     * ⚠️ 仅影响 `vitest`；生产构建仍由 `.env` / `VITE_PLAN_API_ENABLED` 决定，
     * 默认关闭（接口未合并前 Real 按钮保持 disabled）。
     */
    'import.meta.env.VITE_PLAN_API_ENABLED': JSON.stringify('true'),
    /**
     * AI 调整：测试环境打开**前端预览 fixture**，以便对
     * "草稿 → 第一次确认 → 求解 → 候选 → 第二次确认（采用 / 保留）"整条链路做组件级测试。
     *
     * ⚠️ 打开的只是**预览**，不是真实接口：`VITE_AI_PLANNING_API_ENABLED` 保持关闭，
     * 因此"预览模式不发任何真实请求"的断言仍然成立；
     * ⚠️ 仅影响 `vitest`；生产构建仍由 `.env` / `VITE_AI_PLANNING_*` 决定（默认关闭）。
     */
    'import.meta.env.VITE_AI_PLANNING_PREVIEW': JSON.stringify('true'),
    'import.meta.env.VITE_PERSONAL_PLANNING_PREVIEW': JSON.stringify('true'),
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts', 'tests/**/*.spec.ts'],
    // 需要全局钩子：@vue/test-utils 依赖 afterEach 自动卸载组件。
    globals: true,
    // 测试不依赖真实后端：所有网络调用都必须被替换为 mocked fetch。
    restoreMocks: true,
  },
})
