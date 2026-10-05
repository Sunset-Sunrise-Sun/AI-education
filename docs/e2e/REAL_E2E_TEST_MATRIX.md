# Real E2E 验收矩阵（Acceptance Test Matrix）

> 本文件把 Real E2E 的**每个场景**固定成可复算的条目：
> **Precondition → Request → Expected backend behavior → Expected frontend behavior → Evidence required**。
>
> 状态：**验收标准已准备**。⛔ 本文件不声明任何场景"已通过 Real E2E"。
> 等级定义见 `REAL_CASE_A_ACCEPTANCE.md` §2。
>
> 说明：A–I 为**后端 / 契约**场景；J–K 为**前端**场景。编号沿用任务给定顺序。

---

## 通用约定

- **接口**：`POST /api/v1/plan`
- **请求体**（严格三个字段）：
  ```json
  { "semester": "2026-1", "current_schedule": [], "preference": {} }
  ```
- ⛔ **全程禁止 Mock fallback**：任何失败都不得改用 `GET /api/v1/mock/demo` 的数据顶替。
- ⛔ **`X-Data-Source: mock` 只加在 Mock 通道响应上**；
  Real 响应上出现该头 = **串了 Mock 通道 = 验收失败**。

---

## A. runtime disabled

| 项 | 内容 |
|---|---|
| **Precondition** | production runtime factory 未装配（`get_planning_orchestrator()` 返回 `None`）；**当前 main 即此状态** |
| **Request** | `POST /api/v1/plan`，合法 body（如 `semester="2026-1"`, `current_schedule=[]`） |
| **Expected backend** | **503**，body `{"detail": {"error": "real_pipeline_not_configured", "message": ...}}`；⛔ 不返回任何 `PlanResult`；⛔ 不 fallback |
| **Expected frontend** | 错误标题显示"**真实规划运行时尚未完成装配**"；展示 `HTTP 503` 与 `real_pipeline_not_configured`；页面**继续显示 Mock Demo**，且 provenance 仍为 **Mock** |
| **Evidence** | `curl -i` 响应（状态行 + body + 头）；前端截图或测试断言 |

## B. Curriculum missing

| 项 | 内容 |
|---|---|
| **Precondition** | runtime 已装配，但 Curriculum 输入缺失 / 不可用（无真实受控 Case A 输入） |
| **Request** | 同上 `POST /api/v1/plan` |
| **Expected backend** | **503**（链路未就绪）；⛔ **不**构造替代 MakeupTask；⛔ 不 fallback |
| **Expected frontend** | 同 A：显示"尚未完成装配"；⛔ 不展示任何 pretending Real 的结果 |
| **Evidence** | 响应状态 + body；日志中确认**没有**使用 mock/fake Curriculum；前端 provenance 仍 Mock |

## C. Course Data partial

| 项 | 内容 |
|---|---|
| **Precondition** | runtime 已装配，但 Course Data 快照为 **`partial`**（`loaded_count != reported_total`，如两页 smoke 样本） |
| **Request** | 同上 `POST /api/v1/plan` |
| **Expected backend** | **503**（`course_data_not_ready` 语义）；⛔ **partial 不得进入产品链路**；⛔ 不 fallback |
| **Expected frontend** | 显示"尚未完成装配"（或等价的未就绪文案）；provenance 仍 **Mock** |
| **Evidence** | 快照 `completeness == "partial"` 的证据 + 响应状态；确认**未**用 partial 装配 |

## D. complete snapshot + valid runtime

| 项 | 内容 |
|---|---|
| **Precondition** | runtime 已装配 **production** factory；三个 Provider 均为真实实现类；Course Data **complete** 2026-1 snapshot（见 checklist）；Curriculum 为**真实受控** Case A 输入 |
| **Request** | 同上 `POST /api/v1/plan` |
| **Expected backend** | **200** + 合法 `PlanResult`（符合 `schemas/plan_result.schema.json`）；⛔ 无 mock/fake/stub |
| **Expected frontend** | 结果区渲染 **real PlanResult**；`规划结果来源：Real`；基础演示数据（培养要求评估 / 教学班 / 偏好）**仍标 Mock** |
| **Evidence** | 完整响应 JSON；Provider 实例类型证明；checklist 勾选记录；前端 provenance 断言 |

## E. current_schedule contains mock

| 项 | 内容 |
|---|---|
| **Precondition** | 请求的 `current_schedule` 中**存在** `data_source == "mock"` 的教学班（或 real+mock 混合 / 来源未经确认） |
| **Request** | `POST /api/v1/plan`，body 的 `current_schedule` 含 mock 项 |
| **Expected backend** | **422**（`PlanRequest.current_schedule_must_be_real` 校验失败）；⛔ 不接受该请求；⛔ 不 fallback |
| **Expected frontend** | 通用标题"**Real Planning 输入未通过校验**"（⛔ 不写成"系统错误"）；展示后端 `code` / `detail`；⛔ 不把 Mock 说成 Real |
| **Evidence** | 422 body（含 `loc` / `msg` / `type`）；前端错误区文本 |

## F. current_schedule = []

| 项 | 内容 |
|---|---|
| **Precondition** | runtime 可用；`current_schedule` 为空数组 |
| **Request** | `POST /api/v1/plan`，`current_schedule: []` |
| **Expected backend** | **允许**（空课表合法，provenance 校验通过）；是否可行由 Planner 决定 |
| **Expected frontend** | 前端 provenance gate **不阻断**（空课表放行）；按钮可用（若 `VITE_PLAN_API_ENABLED=true`） |
| **Evidence** | 响应非 422；前端 gate 判定记录 |

## G. Provider raises exception

| 项 | 内容 |
|---|---|
| **Precondition** | runtime 可装配，但某个 Provider 在调用中抛异常 |
| **Request** | 同上 `POST /api/v1/plan` |
| **Expected backend** | 异常**原样向上传播** → 显式服务端错误（5xx）；⛔ **不吞异常**、⛔ **不 fallback 到 Mock**、⛔ 不返回伪造 `PlanResult` |
| **Expected frontend** | 显示"**Real Planning 服务端错误**"；⛔ 不回退 Mock、⛔ 不展示替代结果 |
| **Evidence** | 异常日志/堆栈 + 响应状态；确认无 mock 调用 |

## H. Real success

| 项 | 内容 |
|---|---|
| **Precondition** | 同 D（真实链路 + complete snapshot + 真实受控 Curriculum 输入） |
| **Request** | 同上 `POST /api/v1/plan` |
| **Expected backend** | **200** + 合法 `PlanResult`；响应**不带** `X-Data-Source: mock` |
| **Expected frontend** | 显示 real 结果；provenance `Real` |
| **Evidence** | `curl -i` **完整响应头**（证明无该头）；响应 JSON |

## I. frontend Real disabled

| 项 | 内容 |
|---|---|
| **Precondition** | `VITE_PLAN_API_ENABLED` **未设为 `true`**（默认关闭） |
| **Request** | 页面加载 + 用户点击"生成规划（Real Planning）" |
| **Expected backend** | ⛔ **收不到任何 `/api/v1/plan` 请求**（0 次调用） |
| **Expected frontend** | Real 提交按钮 **disabled**，并提示接口未开放；页面仍正常显示 Mock 数据；⛔ **不自动发请求** |
| **Evidence** | 网络面板 / 测试断言：`/api/v1/plan` 调用数 = 0；按钮 `disabled` |

## J. frontend Real enabled + runtime unavailable

| 项 | 内容 |
|---|---|
| **Precondition** | `VITE_PLAN_API_ENABLED=true` 且 runtime 未装配（= 当前 main 的真实情形） |
| **Request** | 用户点击"生成规划（Real Planning）" |
| **Expected backend** | **503** `real_pipeline_not_configured` |
| **Expected frontend** | UI 显示"**真实规划运行时尚未完成装配**"；明确说明可继续使用 Mock Demo；⛔ **不自动回退 Mock**；provenance 保持 **Mock** |
| **Evidence** | 响应 + 前端错误区文本 + provenance 仍为 Mock 的断言 |

## K. frontend Real success

| 项 | 内容 |
|---|---|
| **Precondition** | `VITE_PLAN_API_ENABLED=true`；runtime 已装配且数据真实完整（LEVEL 3 前提） |
| **Request** | 用户提交合法输入 |
| **Expected backend** | **200** + `PlanResult`；无 `X-Data-Source: mock` |
| **Expected frontend** | 结果区显示 **Real PlanResult**；`规划结果来源：Real`；**同时**培养要求评估 / 教学班 / 偏好**仍显示 Mock** 并保持 `Mock` 标记；⛔ 不出现"当前数据模式：Real"这类**全局**说法 |
| **Evidence** | 前端 provenance 断言（局部文案）+ 基础数据仍带 Mock 标记的断言 + 响应头 |

---

## 汇总表

分类口径：

- **✅ 当前 main 可直接验证** —— 该场景**在当前 main 上就能完整复算**，
  不需要任何 runtime wiring（其期望行为本来就不依赖已装配的真实 Provider）；
- **⛔ 需 runtime wiring 后做 production-path 验证** —— 该场景要求
  **已装配的 production 链路**才能真正成立；在 runtime 装配之前，
  观测到的结果（例如同为一个 503）**不能**算作该场景已验证。

| # | 场景 | 期望后端 | 期望前端 | 分类 |
|---|---|---|---|---|
| A | runtime disabled | 503 `real_pipeline_not_configured` | 显示"尚未完成装配" | ✅ **当前 main 可直接验证**（当前即此状态） |
| E | schedule contains mock | 422 | 输入未通过校验 | ✅ **当前 main 可直接验证** |
| F | schedule = [] | 允许 | gate 放行 | ✅ **当前 main 可直接验证** |
| I | frontend Real disabled | 0 请求 | 按钮 disabled | ✅ **当前 main 可直接验证**（默认状态） |
| J | enabled + runtime unavailable | 503 | "尚未完成装配" | ✅ **当前 main 可直接验证** |
| B | Curriculum missing | 503 | 同上 | ⛔ **需 runtime wiring 后做 production-path 验证** |
| C | Course Data partial | 503 | 同上 | ⛔ **需 runtime wiring 后做 production-path 验证** |
| D | complete + valid runtime | 200 `PlanResult` | Real 结果 + Real provenance | ⛔ **需 runtime wiring 后做 production-path 验证** |
| G | provider exception | 显式 5xx | 服务端错误 | ⛔ **需 runtime wiring 后做 production-path 验证** |
| H | Real success | 200，无 mock 头 | Real 结果 | ⛔ **需 runtime wiring 后做 production-path 验证** |
| K | frontend Real success | 200 | Real provenance + Mock 基础数据 | ⛔ **需 runtime wiring 后做 production-path 验证** |

> ⚠️ **为什么 B / C 归入"必须等 runtime"**：
> 它们期望的 503 与 A 的 503 **表面相同但含义不同**。
> 在 runtime 未装配时，503 恒来自"**链路尚未装配**"，
> ⛔ 因此**无法**区分"因为 Curriculum 缺失而 503"或"因为 snapshot 是 partial 而 503"。
> 要真正验证 B / C，必须先把 production 链路装上，
> 再让它在**真实**的缺失 / partial 条件下 fail closed。

> ⚠️ **"当前 main 可直接验证"≠"已通过 Real E2E"**：
> A/E/F/I/J 证明的是**失败路径与隔离正确**，
> 它们**不构成** LEVEL 3 的任何部分。
> LEVEL 3 要求 D/H/K 在**真实数据 + 完整 runtime** 上成立。
