/**
 * ⚠️ 兼容转发层（保留旧 import 路径）。
 *
 * 真实契约类型与解析器已经迁移到 `aiPlanningContract.ts`（与后端 HANDOFF 一一对应）。
 * 本文件只做 re-export，避免旧 import 失效；**新增代码请直接 import 契约文件**。
 */

export * from './aiPlanningContract'
