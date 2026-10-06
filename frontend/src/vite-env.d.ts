/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 可选：后端基地址。留空表示走同源代理（默认）。 */
  readonly VITE_API_BASE_URL?: string
  /** 可选：Real Planning 通道开关（`'true'` 才启用）。 */
  readonly VITE_PLAN_API_ENABLED?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
