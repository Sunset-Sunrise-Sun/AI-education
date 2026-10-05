# Integration 当前状态

> 最后更新：2026-10-05

## 当前能力

- `PlanningOrchestrator` 继续只按 Curriculum → Course Data → Planner 顺序编排；
- 新增真实规划入口 `POST /api/v1/plan`，请求复用公共 `CourseOffering` 与 `Preference` 模型，成功响应为 `PlanResult`；
- production Provider 尚未完成装配，因此当前真实入口明确返回 `503 real_pipeline_not_configured`；
- 真实入口不引用 `mock_service`，Provider 运行期异常不被吞掉，也不会回退到 Mock；
- 永久 Mock 通道仍为 `/api/v1/mock/*`，只有该路径携带 `X-Data-Source: mock`。

## 当前边界

- 未修改 `/schemas/`、frozen Provider contract 或 `PlanningOrchestrator`；
- 未实现 Curriculum、Course Data 或 Planner 业务算法；
- 未接入真实教务网络、XLSX 上传或学生身份信息；
- 真实 Provider 可用后，在 `backend/app/services/planning_runtime.py` 完成装配即可复用现有 API。

## 下一步

- 由 Architecture Reviewer 审查本分支；
- 待真实 Curriculum / Course Data / Planner Provider 满足各自数据门后，再完成 production wiring 与真实 E2E。
