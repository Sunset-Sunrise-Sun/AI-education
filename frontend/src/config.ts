/**
 * 集中配置。
 *
 * 后端地址**只在这里出现一次**，不散落到各个组件里。
 *
 * 默认留空 = 请求同源路径，由 Vite 开发/预览服务器代理到后端
 * （代理目标见 `vite.config.ts`，可用 `VITE_PROXY_TARGET` 覆盖）。
 * 这样本地联调不需要后端开启 CORS，也就不必改动 Phase 1 的后端代码。
 */

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL ?? ''

/** 后端基地址；空字符串表示"同源，由 Vite 代理转发"。 */
export const API_BASE_URL: string = rawBaseUrl.replace(/\/+$/, '')

/** 本阶段唯一允许调用的后端接口。 */
export const DEMO_ENDPOINT = `${API_BASE_URL}/api/v1/mock/demo`

export const APP_TITLE = '学航·转衔'
export const APP_SUBTITLE = '面向转专业学生的 AI 学业路径重构 Agent'
