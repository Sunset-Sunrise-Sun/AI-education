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
