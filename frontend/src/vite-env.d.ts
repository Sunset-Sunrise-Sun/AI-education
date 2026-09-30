/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 可选：后端基地址。留空表示走同源代理（默认）。 */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
