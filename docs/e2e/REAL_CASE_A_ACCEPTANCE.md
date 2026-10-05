# Real Case A E2E 验收定义（Acceptance Definition）

> 本文件回答一个**只能有一个答案**的问题：
> **什么情况下我们才被允许说「Real Case A E2E PASSED」。**
>
> 状态：**验收标准已准备（acceptance criteria prepared）**。
> ⛔ 本文件**不声明** Real E2E 已完成；
> 当前 main（`111c41a7faa68b9076adcac6fe26081d07c43fde`）的状态是 **LEVEL 0**。

---

## 0. 为什么需要这份定义

项目里已经同时存在这些东西：

- 一个**永久 Mock 通道**（`GET /api/v1/mock/demo`，响应带 `X-Data-Source: mock`）；
- 一套**真实依赖**（`X-Data-Source: mock` 现在**只**加在 Mock 通道响应上）；
- 一套**真实 Provider 实现类**（Curve/Planner/Course Data 都有 production 形状的实现）；
- 一些**人工虚构的测试/采集产物**（synthetic bundle、test Fake）。

这些放在一起极容易产生一种**错误结论**：
> "接口返回了 200 和一个合法 PlanResult，所以 Real E2E 通过了。"

本文件的目的就是**把这条捷径堵死**：
**"跑通了链路" ≠ "跑通了真实数据"。**

---

## 1. 「Real Case A E2E PASSED」的正式定义

只有当下列 **10 条同时成立**时，才允许写成
**Real Case A E2E PASSED**（缺任一条即**不得**如此表述）：

| # | 条件 | 说明 / 可核查点 |
|---|---|---|
| **1** | `POST /api/v1/plan` **实际经过 production runtime factory** | 请求由真实装配入口（`backend/app/services/planning_runtime.py` 的装配 seam）构造出的 Orchestrator 处理；⛔ 不是测试里的 `dependency_overrides`、⛔ 不是 Fake |
| **2** | `CurriculumProvider` **= `CurriculumCaseProvider`** | 真实实现类（`backend/app/curriculum/case.py`），**不是** 任何 test Fake/Stub |
| **3** | `CourseDataProvider` **= `SnapshotCourseDataProvider`** | 真实实现类（`backend/app/course_data/snapshot.py`），且其持有的快照**是**真实完整快照 |
| **4** | `PlannerProvider` **= `RestrictedPlannerProvider`** | 真实实现类（`backend/app/planner/provider.py`） |
| **5** | Curriculum 输入 **= 真实受控 Case A 输入** | 即 Case A（2025 级 遥感科学与技术 → 网络空间安全）的**真实受控**培养方案与已修记录；⛔ 不含 synthetic / mock case 数据 |
| **6** | Course Data **= complete 2026-1 snapshot** | `semester == "2026-1"`、`is_complete == true`、`loaded_count == reported_total`（逐项见 `COURSE_DATA_SNAPSHOT_CHECKLIST.md`） |
| **7** | **不使用 Mock / Fake / Stub** | 上述三个 Provider 与 Orchestrator 链路中，**没有**任何一处是 mock/fake/stub；⛔ 包括"只在测试里替换一下"这种 |
| **8** | `current_schedule` **provenance 合法** | 空数组，或其中**每一项** `data_source == "real"`；含 mock / 混合 / 来源未经确认 → 后端 422，**不算通过** |
| **9** | API 返回**合法 `PlanResult`** | 符合 `schemas/plan_result.schema.json`（含 `status` / `selected_classes` / `changes` / `risks` / `unresolved`） |
| **10** | 响应**不带** `X-Data-Source: mock` | 该响应头**只**给永久 Mock 通道加；Real 响应上出现它即视为**串了 Mock 通道**，验收失败 |

### 1.1 必须同时记录的证据

上表每一项都必须能与一条**可复核证据**对应（命令、响应片段、或日志），
⛔ 不接受"我看过了"这种口头结论。建议证据形式见
`REAL_E2E_TEST_MATRIX.md` 的 `Evidence required` 列。

### 1.2 ⚠️ synthetic source-shaped artifact 只能证明什么

**一个"长得像真实来源"的产物**（`real://...` 形式的 `source` 字符串、
用测试夹具构造的 bundle、`data_source` 被置为 `real` 的对象）
**只能证明下面这件事**：

> **production wiring 可以被装配并跑通**（即 LEVEL 1）。

它**不能**证明 Real E2E，原因有两条**硬事实**：

1. **Capture Bundle 自身不携带经过认证的来源证明**；
   `CourseOffering.source` 只是**调用方提供的一个记录字段**，
   一个 `real://...` 形式的字符串**没有任何证明力**；
2. `data_source` 由 Course Data 代码**无条件**置为 `real`
   —— 它表达的是"这是真实来源等级"，**不是**"这份数据已被证明来自受信采集"。

> ⛔ 因此：**synthetic artifact + 配置说它是 real ≠ Real E2E**。
> 详见 `OPEN ARCHITECTURE ITEM`（本文件 §4）。

---

## 2. 验收状态分级（四档，不得混用）

为避免以后再把不同成熟度混为一谈，统一定义四档：

| 等级 | 名称 | 含义 | 判定依据 |
|---|---|---|---|
| **LEVEL 0** | **Runtime unavailable** | 真实链路**尚未装配** | `POST /api/v1/plan` → **503** `real_pipeline_not_configured` |
| **LEVEL 1** | **Runtime wiring verified** | production factory **能装配**真实实现类，但使用的是 **synthetic / test artifact** | 装配成功且返回 `PlanResult`，但数据来自 synthetic / test 产物 |
| **LEVEL 2** | **Real data path verified** | 使用**真实 Curriculum + 完整 Course Data**，但**前端尚未完成实际联调** | 后端链路用真实数据跑通；前端联调**未**通过 |
| **LEVEL 3** | **Real Case A E2E passed** | Frontend → API → Runtime → Providers → PlanResult **完整跑通** | 同时满足 §1 的 **全部 10 条** |

### 2.1 当前状态

```text
LEVEL 0 on main
```

依据（可当场复核）：

- `backend/app/services/planning_runtime.py` 的 `get_planning_orchestrator()`
  **当前恒返回 `None`**；
- 因此 `POST /api/v1/plan` 恒返回 **503 `real_pipeline_not_configured`**；
- 前端 `VITE_PLAN_API_ENABLED` 默认关闭，Real 提交按钮 disabled。

⚠️ **不得**因为"Codex 本地存在 runtime wiring 工作"就把状态写成 **LEVEL 1**：
**本地未合入的代码不是当前状态**。等级只描述**当前 main 可验证的事实**。

### 2.2 等级晋升的规则

- **LEVEL 0 → 1**：需要 production factory 真的能装配真实实现类（可合并的代码 + 证据）；
- **LEVEL 1 → 2**：需要真实 Curriculum 输入 + **complete** 2026-1 snapshot（见 checklist）；
- **LEVEL 2 → 3**：需要前端实际联调通过，且 §1 的 10 条**全部**成立；
- ⛔ **跳级不被允许**：不得在 LEVEL 1 的证据上声称 LEVEL 2/3。

---

## 3. 术语（避免误读）

| 术语 | 含义 |
|---|---|
| **Mock 通道** | `GET /api/v1/mock/*`，永久保留，响应带 `X-Data-Source: mock` |
| **synthetic artifact** | 人工构造的测试/演示产物（含 `real://` 形式 source 的假 bundle） |
| **真实受控输入** | 经负责人确认、按数据边界私下交接的真实材料（不入 public Git） |
| **complete snapshot** | `reported_total == loaded_count` 且通过全部 checklist 项的快照 |
| **production runtime factory** | 真实装配入口（唯一 production wiring seam） |

---

## 4. OPEN ARCHITECTURE ITEM：snapshot provenance

> 本节记录一个**已知且尚未解决**的架构问题。
> ⛔ 本文件**不提出最终实现**，只把问题固定下来，供架构决策。

**问题**：当前无法仅凭数据本身证明"这份 Course Data 快照来自受信 capture pipeline"。

**已知限制（事实）**：

- `Capture Bundle` **自身不携带**经过认证的来源证明
  （其结构只有 `format` / `semester` / `first_page_no` / `page_size` / `pages`）；
- `CourseOffering.source` 是**调用方提供的记录字段**，
  **不应单独被视为真实性证明**；
- `CourseOffering.data_source` 由 Course Data 代码**无条件**置为 `real`，
  因此**受信 capture 与任意 synthetic bundle 走的是同一条代码路径**。

**安全不变量（本文件据此提出验收要求，非实现方案）**：

```text
✅ 允许： captured provenance → runtime **校验** → expected source（来自配置）
⛔ 禁止： 配置（env / 常量）→ **赋值** provenance → 数据变 Real
```

即：**runtime 配置不得替数据"证明自己是真实来源"**；
环境变量至多作为**期望值**参与校验。
⛔ 不得出现 `arbitrary bundle + env says real → trusted Real snapshot`。

**当前处置**：在架构裁决之前，Real E2E 只能通过
「**受信 capture pipeline 产出 + 现有 completeness evidence**」的证据链来认定（见 checklist），
否则 **fail closed**（不得为了 E2E 放行）。

---

## 5. 相关文档

- `docs/e2e/COURSE_DATA_SNAPSHOT_CHECKLIST.md` —— 完整快照进入 Real pipeline 前的人工确认清单
- `docs/e2e/REAL_E2E_TEST_MATRIX.md` —— 验收矩阵（Precondition / Request / Expected / Evidence）
- `docs/e2e/DEMO_RUNBOOK.md` —— 比赛 Demo 运行手册（含 Real 不可用时的切换策略）
- `docs/status/course_data.md` —— snapshot provenance 语义的详细记录
- `docs/status/integration.md` —— Integration 当前状态
