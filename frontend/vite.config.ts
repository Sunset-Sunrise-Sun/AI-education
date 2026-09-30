import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 后端默认地址。
 *
 * 这里刻意**不是**让浏览器直连后端，而是作为 Vite 开发/预览服务器的代理目标：
 * 前端始终请求同源路径 `/api/v1/mock/demo`，由 Vite 转发到后端。
 * 好处是本地联调**完全不需要给后端加 CORS**，因此不用改动 Phase 1 的后端代码。
 *
 * 如果确实想让浏览器直连后端，设置 `VITE_API_BASE_URL`（见 .env.example），
 * 但那样后端需要自行开启 CORS。
 */
const DEFAULT_BACKEND_TARGET = 'http://127.0.0.1:8000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')

  const backendTarget = env.VITE_PROXY_TARGET || DEFAULT_BACKEND_TARGET

  // 只有本地开发/预览才需要代理；构建产物本身不含任何后端地址。
  const proxy = {
    '/api': {
      target: backendTarget,
      changeOrigin: true,
    },
  }

  return {
    plugins: [vue()],
    server: {
      // 显式绑定 IPv4。
      // 不写 host 时 Vite 绑定的是 localhost，而 Node 在 Windows 上会优先解析到 IPv6
      // `::1`，于是浏览器/命令行访问 http://127.0.0.1:5173 会连接失败——
      // 而 127.0.0.1 正是后端代理目标使用的地址，两边必须一致才不会踩坑。
      host: '127.0.0.1',
      port: 5173,
      proxy,
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
      proxy,
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  }
})
