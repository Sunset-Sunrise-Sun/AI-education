# Integration 工作日志

### 2026-10-05 - Real Integration API 骨架

- 从 `main@0eaa6c0b6348e43533255484b496a7bcbcd67d79` 创建 `feature/real-plan-api`；
- 新增 API 私有 `PlanRequest`：仅包含 `semester`、`current_schedule`、`preference`，其中后两者复用公共模型；
- 新增 `POST /api/v1/plan`，成功时直接返回 `PlanningOrchestrator.build_plan(...)`；
- 新增 `get_planning_orchestrator()` production wiring seam；当前未注册真实 Provider，API 返回明确的 503，错误码为 `real_pipeline_not_configured`；
- Provider 的其它异常继续上抛，不转成 200，不回放 Mock `PlanResult`；
- 修正全局 Mock header：只对 `/api/v1/mock/*` 添加 `X-Data-Source: mock`，真实入口和健康检查不再被错误标记；
- 新增真实 API 测试，覆盖路由存在、503、422、Mock/Real 隔离、Fake Provider 调用顺序与次数、参数透明传递、结果内容不改写、Provider 异常无 fallback；
- 保持 `/api/v1/mock/demo` 行为不变；
- 未修改 `backend/app/curriculum/**`、`backend/app/planner/**`、`backend/app/course_data/**`、`schemas/**`、公共契约模型或前端。

测试记录：

- 最终相关回归：50 passed；`python -m compileall -q app` 通过；
- 首次全量回归：2016 passed / 2 skipped / 15 failed；失败均位于 Curriculum 既有测试，原因是 Windows 默认 GBK、Windows ZIP 路径行为及当前仓库绝对路径包含 `-1`，与本轮修改无关；后续以 UTF-8 模式再次复核。
- UTF-8 全量复核：2030 passed / 2 skipped / 2 failed；剩余两项均为 Curriculum 既有 Windows 环境问题：ZIP 成员反斜杠安全断言未触发，以及仓库目录日期 `2026-10-05` 令“异常文本不得含 `-1`”断言误命中。按任务边界未修改 `backend/app/curriculum/**`。
