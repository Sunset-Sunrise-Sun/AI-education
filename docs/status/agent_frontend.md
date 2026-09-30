# Agent / Frontend 当前状态

> 最后更新：2026-09-30（组长模块 Phase 1 收尾）
> 数据状态：**全部为 Mock**，尚未接入真实教务数据

## 已完成
- 模块边界和依赖接口已定义
- FastAPI 集成底座可启动：`backend/app/main.py`
- 与 `/schemas/` 一致的 Pydantic 校验层：`backend/app/models/contracts.py`
- Mock 回放接口：`GET /api/v1/mock/{makeup-tasks, course-offerings, preference, plan-result, demo}`
- 健康检查：`GET /health`（另挂 `/api/v1/health`）
- 启动数据自检：Mock 数据不合契约时进程直接启动失败
- 自动测试：118 passed / 1 skipped（`cd backend && python -m pytest`）
- 接口清单、启动/测试/验收步骤：`backend/README.md`

## 当前接口
- 读取：`MakeupTask[]`、`CourseOffering[]`、`Preference`（当前来自 Mock）
- 输出：`PlanResult`（当前来自 Mock）
- 业务接口统一前缀 `/api/v1`；全部响应带 `X-Data-Source: mock`
- 公共契约真源仍是 `/schemas/*.schema.json`，本轮**未修改**

## 当前使用数据
- **仅 Mock**：仓库根目录 `/mock_data/`（人工虚构的演示数据）
- 真实数据链路尚未验证
- 「当前功能仅使用 Mock 数据验证，尚未完成真实数据验证」

## 当前阻塞
- 前端框架尚未最终确定（Vue / React，见 `/docs/ARCHITECTURE.md`）
- 上游 Curriculum / Course Data / Planner 均未产出真实结果，底座只能回放 Mock
- 真实教务数据接入需等用户完成教务页面技术侦察并确认授权范围

## 下一步
- 基于公共 Schema 做静态页面原型，直接调 `/api/v1/mock/demo`
- 用 Mock `PlanResult` 展示冲突与 Path Repair 的前后变化，以及 `unresolved` 的人工确认项
- 上游任一模块可用后，按 `backend/README.md` 第 9 节只替换数据来源，不改 API 与模型
