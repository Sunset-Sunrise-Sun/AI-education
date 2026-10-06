# Readiness Decision Notes（R9 hardening）· North Diagnostic Plan（R10）

> ⛔ 本文件**不实现**任何架构变更；只记录判断与建议时机。
> ⛔ 本 Run 未访问真实学校网络、未采集任何真实数据、未存任何凭据。

## 1. Hardening decision notes（R9）

### 1.1 `POST /api/v1/completed-courses/import` 缺少认证

| 维度 | 评估 |
| --- | --- |
| 当前风险 | 该 endpoint 接受**任意调用方**上传的 XLSX 并解析（本地、零网络、无公式求值、有大小/条数上限、临时文件受控）。**不落库**、**不返回** `备注` 自由文本、**不写**调用方指定路径、错误信息脱敏。风险面主要是：**无鉴权 ⇒ 任何能访问该端口的进程都能消耗解析资源**；以及返回的归一化记录会**回给上传者本人**（其自有数据）。 |
| 比赛 / 本地 Demo 影响 | 无：Demo 不依赖上传；该入口仅供本地受控使用。 |
| 生产影响 | 中等：真实部署必须前置鉴权（网关 / 会话），否则它与其他未鉴权接口一样暴露在网络上。 |
| 是否阻塞 Real E2E 证据 | **否**。Real E2E 证据链走 `POST /api/v1/plan`；上传入口与真实数据采集链路**无关**（且当前前端未接线）。 |
| 建议时机 | 与"真实部署鉴权"一起做（属**部署/接口面**决策，需 Architecture Decision）；⛔ 本 Run 未擅自加鉴权（会引入会话/凭据语义，超出 readiness 范围）。 |
| 若要最小加固（未做，供决策） | 复用同一鉴权中间件覆盖 `/api/v1/*`；或把它限制在 `127.0.0.1` 绑定 + 反向代理白名单。 |

### 1.2 真实 `POST /api/v1/plan` 不返回 `X-Data-Source`

| 维度 | 评估 |
| --- | --- |
| 当前风险 | Mock 通道响应带 `X-Data-Source: mock`（**唯一**标记），真实响应**不带**该头。这不产生"Mock 冒充 Real"的风险（标记只增不减），但**无法**用一个响应头**正向**证明"这是 Real 响应"。 |
| 比赛 / 本地 Demo 影响 | 无：前端已按 provenance 行 + 错误态区分来源（Gate E 21 条断言锁定）。 |
| 生产影响 | 低–中：审计方无法仅凭响应头判定数据来源；需要额外证据（本项目采用 acceptance digest + evidence protocol）。 |
| 是否阻塞 Real E2E 证据 | **否**，只要证据协议**不**依赖该头：LEVEL 2/3 用 `manifest_sha256` + provider read-back + `selected_classes ⊆ accepted identities` + "⛔ 不带 mock 头"作为**否定式**判据。 |
| 建议时机 | 属**接口面变更**（公共响应头），需 Architecture Decision；建议与"真实部署鉴权/可观测性"一并裁定。 |
| 若裁定要做 | 只加**正向**标记（如 `X-Data-Source: real`）且**不改变** `/api/v1/plan` 请求契约与 `PlanResult` 结构；需同步更新 `docs/interfaces/*` 与前端（前端已明确不读该头）。 |

### 1.3 结论

```text
两项都不是 Real E2E 的阻塞项；都属"需要 Architecture Decision 的接口面/部署面"变更。
本 Run 的处置：记录 + 明确证据协议不依赖它们。⛔ 未擅自实现。
```

## 2. North campus 诊断计划（R10）

### 2.1 已知事实（⛔ 不推断）

```text
现象（历史观测）：过滤后的**深分页**在深 offset 返回 HTTP 600，且**新会话**也会出现。
⛔ 不得称为"限流（rate limiting）"——目前**没有**证据（没有 429、没有 Retry-After、没有响应体说明）。
状态：North **suspended**；五 shard 缺一 ⇒ 真实 full-semester acceptance 不可产出。
```

### 2.2 下一次**已授权**会话的最小诊断（人工观测，⛔ 不自动重试）

目标：用**最少**请求判定 600 是"按 offset 确定性失败"还是"随会话/时间变化"。

```text
前提：用户已登录（含 MFA）、使用已批准浏览器上下文；⛔ 不导出 cookie / token / 会话内容。
⛔ 不做并发、不做循环重试、不做自动化轮询；每次观测之间保持与采集器相同的 pacing（≥30s）。
记录时⛔ 不记录任何响应体中的行内容，只记录**元数据**。
```

最小观测序列（每次只记录 §2.3 的字段）：

```text
O1  baseline（不带 openingSchoolNumber 的第 1 页）        → 记录 code / total
O2  North 第 1 页（pageNo=1, openingSchoolNumber=5062202）→ 记录 code / total / rows 条数
O3  North 第 2 页（pageNo=2）                            → 记录 code / total / rows 条数
O4  North 最后一个**成功**页之后的第一页（见 §2.4 定位）  → 记录 code / 首个 600 的 pageNo
O5  同一 pageNo 再取一次（**同会话**，间隔 ≥30s）        → 记录 code（判断"确定性 by offset"）
O6  **新会话**（重新登录/刷新上下文）同一 pageNo          → 记录 code（判断是否与会话相关）
```

判读（写成结论时必须同时给出对应观测编号）：

```text
若 O5/O6 在同一 pageNo 稳定复现 600 ⇒ 与 offset / 服务端有关，与会话无关
若 O5 复现但 O6 不复现              ⇒ 与会话状态有关（仍⛔ 不得直接称限流）
若 O1–O3 正常、O4 首错                ⇒ 失败起点明确（记录该 pageNo 与 offset = (pageNo-1)*pageSize）
若 O1 就失败                          ⇒ 与"深分页"无关，需另行定位（⛔ 不要继续加深分页）
```

### 2.3 必须记录的元数据（⛔ 只记元数据）

| 字段 | 说明 |
| --- | --- |
| 时间戳（本地，秒级） | 便于判断是否随时间/批次变化 |
| `pageNo` / `pageSize` | 采集器使用 `pageSize = 200`，`firstPageNo = 1` |
| `openingSchoolNumber` | North = `5062202`（其余校区仅作对照时记录） |
| HTTP 状态码 | 含异常值 `600` |
| 响应 `code` 字段 | 业务码与 HTTP 码可能不一致 |
| `data.total` / 本页 `rows` 条数 | 完整性判定只作**参考**（⛔ 不用于推断 complete） |
| 响应头中**非敏感**项 | 例如 `retry-after`（若存在）、`content-type`、`server`；⛔ **不记录** `set-cookie`、`cookie`、`authorization` |
| 会话标识方式 | 只写"会话 A / 会话 B"；⛔ 不写任何会话值 |
| 是否新会话 | 布尔 |
| 失败形态 | 状态码 + 是否有响应体（⛔ 不 dump 响应体内容） |

### 2.4 停止条件（⛔ 先停，再报告）

```text
S1 任一观测出现 600 且**两次**（同会话 + 新会话）都在同一 pageNo ⇒ 停止深分页推进，报告
S2 出现 429 / 401 / 403 / 跳转登录页 ⇒ 立即停止（会话或权限问题，⛔ 不重试）
S3 连续 2 次请求超时或连接错误 ⇒ 停止（避免造成压力）
S4 同一会话内累计请求超过 **12** 次仍未定位 ⇒ 停止，改为离线分析已有观测
S5 任何时刻用户觉得"请求频率可能造成风险" ⇒ 立即停止
S6 若诊断需要读取/导出 cookie / token / 会话 ⇒ **禁止**（超出授权范围，立即停止并上报）
```

### 2.5 处置选项（供决策，⛔ 本 Run 不动架构）

```text
A. 等 North 恢复后在正常窗口重采（推荐：⛔ 不改变任何验收规则）
B. 若证据表明是服务端深分页限制 ⇒ 评估"分页窗口策略"（需 Architecture Decision；
   ⛔ 不得放宽完整性要求，⛔ 不得用四校区冒充 full_semester）
C. 若证据表明是会话相关 ⇒ 在授权范围内重新开始一次**完整**采集（baseline → 五 shard → baseline）
```

⛔ **不得**：跳过 North、合成 North、推断 North 完整性、把"四校区 complete"当成 full_semester complete、
或为绕过 North 而放宽 acceptance 规则。
