# Agent / Frontend 当前状态

> 最后更新：2026-09-30（Phase 2A：前端最小 Demo 壳层）
> 数据状态：**全部为 Mock**，尚未接入真实教务数据

## 已完成
- 模块边界和依赖接口已定义
- **前端技术栈已由负责人确认：Vue 3 + TypeScript + Vite**（`/docs/ARCHITECTURE.md` 已同步）
- 后端集成底座可启动：`backend/app/main.py`
- 与 `/schemas/` 一致的 Pydantic 校验层：`backend/app/models/contracts.py`（含 `uniqueItems` 的运行时强制）
- Mock 回放接口：`GET /api/v1/mock/{makeup-tasks, course-offerings, preference, plan-result, demo}`
- 健康检查：`GET /health`（另挂 `/api/v1/health`）
- 启动数据自检：**先按公共 JSON Schema 校验原始 JSON**（不依赖 Pydantic 的类型转换），不合契约时进程直接启动失败
- 后端自动测试：125 passed / 1 skipped（`cd backend && python -m pytest`）
- **前端最小 Demo 壳层已建立**：`frontend/`（Vue 3 + TypeScript + Vite，单页面，原生 CSS）
  - 唯一数据来源：`GET /api/v1/mock/demo`；同源请求，由 Vite 开发/预览服务器代理转发到后端（**未修改 backend，因此不需要 CORS**）
  - 顶部醒目 Mock / 演示环境标识，四个区块各有 `Mock` 标记，并显示后端 `X-Data-Source` 的实际取值
  - 四个展示区块：补修任务 / 教学班（按课程分组）/ 用户偏好 / 最终方案
    （含 `status`、`selected_classes`、`changes`、`risks`、`unresolved`、`objective_summary`）
  - loading / success / error 三态；请求失败时只报错，**绝不生成替代数据**
  - 已验证：`npm run build` 通过（`vue-tsc --noEmit` + `vite build`）；
    `npm run dev` 与 `npm run preview` 均可启动并成功穿透到后端
- 运行与验收说明：`backend/README.md`、`frontend/README.md`

## 当前接口
- 读取：`MakeupTask[]`、`CourseOffering[]`、`Preference`、`PlanResult`（当前来自 Mock）
- 前端唯一数据来源：`GET /api/v1/mock/demo`
- 业务接口统一前缀 `/api/v1`；全部响应带 `X-Data-Source: mock`
- 公共契约真源仍是 `/schemas/*.schema.json`，本轮**未修改**

## 当前使用数据
- **仅 Mock**：仓库根目录 `/mock_data/`（人工虚构的演示数据）
- 真实数据链路尚未验证
- 「当前功能仅使用 Mock 数据验证，尚未完成真实数据验证」

## 当前阻塞
- 上游 Curriculum / Course Data / Planner 均未产出真实结果，前端只能展示 Mock
- 真实教务数据接入需等用户完成教务页面技术侦察并确认授权范围
- Demo 的信息结构（比赛讲述顺序）尚未设计，属于 Phase 2B

## 下一步
- **Phase 2B**：与负责人一起设计 Demo 信息结构，把
  「转专业前 → 缺什么 → 有什么班 → 怎么调整 → 最终方案」串成一条用户看得懂的故事线
- 真实模块接入将以**新增独立 adapter / provider** 的方式进入；`/api/v1/mock/*` 与 `mock_service` 保持 **Mock-only**
- 在真实 Curriculum / Planner / Course Data 稳定之前，不接 Agent / LLM
