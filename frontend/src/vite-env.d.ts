/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 可选：后端基地址。留空表示走同源代理（默认）。 */
  readonly VITE_API_BASE_URL?: string
  /** 可选：Real Planning 通道开关（`'true'` 才启用）。 */
  readonly VITE_PLAN_API_ENABLED?: string
  /**
   * 可选：手工录入「当前课表」时写入的 `data_source`。
   *
   * - 不设置（默认）⇒ 记 `mock`：provenance 门禁**阻止**提交 Real Planning（正确行为）；
   * - `'student_attested_real'` ⇒ 记 `real`：负责人**显式**声明这些条目由学生本人提供、
   *   代表其真实已选课程。⛔ 这不是静默 fallback，页面上会逐字标注来源。
   */
  readonly VITE_MANUAL_SCHEDULE_PROVENANCE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
