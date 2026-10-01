# Agent / Frontend 工作日志

> 仅追加历史记录。新的 Agent 优先阅读 docs/status/agent_frontend.md。

## 模板
### YYYY-MM-DD - 功能
- 本次目标：
- 已完成：
- 修改文件：
- 测试：
- 使用数据：Mock / Real
- 已知问题：
- 需要人工确认：
- 对其他模块影响：
- 下一步：

---

### 2026-09-30 - 组长模块 Phase 1：FastAPI 集成底座 + Mock API
- 本次目标：建立后续模块都能接入的后端集成底座，使 Curriculum / Course Data / Planner 未完成时也能跑通完整数据链路。
- 已完成：
  - FastAPI 应用组装、`/api/v1` 版本前缀、启动数据自检、统一错误处理
  - 与公共 Schema 一一对应的 Pydantic 契约层（Course / CourseOffering / MakeupTask / Preference / PlanResult）
  - 4 份 Mock 数据，同时通过公共 JSON Schema 与 Pydantic 双层校验
  - 5 个 Mock 回放接口（含聚合接口 `/api/v1/mock/demo`）
  - 自动测试 118 passed / 1 skipped
  - `backend/README.md`（第 11 节要求）与根目录 `.gitignore`
- 修改文件：
  - 新增 `backend/`（`app/`、`tests/`、`pyproject.toml`、`requirements.txt`、`README.md`）
  - 新增 `mock_data/`（4 份 JSON + `README.md`）
  - 新增 `.gitignore`
  - 更新 `docs/status/agent_frontend.md`、`docs/status/course_data.md`、本文件
- 测试：`cd backend && python -m pytest` → 118 passed, 1 skipped；skip 为 PlanResult 无 `uniqueItems` 字段的设计内跳过，非失败
- 使用数据：Mock
- 公共接口是否变化：否（未改动 `/schemas/` 与 `/docs/interfaces/`）
- 已知问题：
  - Pydantic 模型与 JSON Schema 的一致性靠测试维护，不是代码生成，长期存在人工同步漂移风险
  - 仅在 Python 3.14 / Windows 上验证过
  - `/api/v1/mock/*` 是数据回放而非计算，`plan_result` 不是求解器产出
- 需要人工确认：
  - 前端技术栈（Vue / React）尚未确定
  - 真实教务数据的访问方式需等页面技术侦察结果
  - `MakeupTask` 的课程等价判定仍为演示数据，正式认定须人工完成
- 对其他模块影响：无破坏性影响。上游模块只要产出符合 `/schemas/` 的结果，即可被本层直接接入，无需本层改动接口。
- 下一步：先做静态页面原型对接 `/api/v1/mock/demo`；真实模块接入将新增独立 adapter / provider，`mock_service` 与 `/api/v1/mock/*` 保持 Mock-only。

---

### 2026-09-30 - 第一轮 Code Review 修复（仅修 blocker）
- 本次目标：只修 Reviewer 第一轮指出的 3 个 blocker，不做其他重构，不进入 Phase 2。
- 已完成：
  1. `CourseOffering.weeks` 现在真的在运行时拒绝重复元素（新增 `PositiveIntList`），
     并补上显式用例 `weeks=[1, 1]` 必须 `ValidationError`；
     同时**修正**原先只"确认字段存在"、并未真正验证运行时拒绝的 `uniqueItems` 用例，
     改为按公共 Schema 自动构造重复数据并断言被拒绝。
  2. `mock_service` 现在在进入 Pydantic 之前，**先按 `/schemas/*.schema.json` 校验原始 JSON**；
     新增回归测试覆盖"Pydantic 原本会做类型转换"的非法数据
     （`weekday: "1"`、`credit: true`、`max_credit: "15"`、`weeks: [1, 1]`），
     并单独覆盖启动自检 `all_mock_data()` 这条路径。
  3. 修正文档中"把 `mock_service` / `mock.py` 原地替换为真实数据源"的错误描述：
     `mock_service` 与 `/api/v1/mock/*` **永久 Mock-only**，
     真实接入将以**新增独立 adapter / provider** 的方式另开通道，正式形态届时确认。
- 修改文件：
  - `backend/app/models/contracts.py`、`backend/app/services/mock_service.py`、`backend/app/api/mock.py`
  - `backend/tests/test_contracts.py`、`backend/tests/test_mock_data_schema.py`
  - `backend/requirements.txt`（`jsonschema` 由测试依赖提升为**运行期**依赖）
  - `backend/README.md`、`mock_data/README.md`、`docs/status/agent_frontend.md`、
    `docs/status/course_data.md`、本文件
- 测试：`cd backend && python -m pytest` → 125 passed, 1 skipped
- 使用数据：Mock
- 公共接口是否变化：否（未修改 `/schemas/` 与 `/docs/interfaces/`）
- 已知问题：无新增
- 需要人工确认：无（本轮仅修 blocker）
- 对其他模块影响：无
- 下一步：等待 Reviewer 第二轮验收；Phase 2 未开始，`main` 未合并。

---

### 2026-09-30 - Phase 2A：前端技术选型 + 最小 Demo 壳层
- 本次目标：建立最小可运行的 Vue 前端，让用户能在浏览器里看到一条完整的 Mock 演示链路。
- 已完成：
  - 前端技术栈由负责人确认为 **Vue 3 + TypeScript + Vite**，并同步 `/docs/ARCHITECTURE.md`
  - 新建 `frontend/` 工程：单页面、原生 CSS，**未引入** Vue Router / Pinia / UI 组件库 / 图表库
  - 页面含：顶部 Mock 标识（含后端 `X-Data-Source` 实际取值）、四个展示区块、loading/success/error 三态
  - 唯一数据来源 `GET /api/v1/mock/demo`；后端地址集中在 `vite.config.ts` + `.env.example`，不散落在组件里
  - 采用 Vite 同源代理，**因此没有修改 backend**，也就不需要 CORS
  - 请求失败时不生成任何替代数据（`useDemoData.ts` 错误分支把 data 置为 null）
- 修改文件：
  - 新增 `frontend/`（package.json、package-lock.json、vite.config.ts、tsconfig.json、index.html、
    .env.example、.gitignore、README.md、src/**）
  - 更新 `docs/ARCHITECTURE.md`（`Vue 或 React（尚未最终确定）` → `Vue 3 + TypeScript + Vite`）
  - 更新 `docs/status/agent_frontend.md`、本文件
- 测试：
  - 前端构建：`npm run build` 通过（`vue-tsc --noEmit` + `vite build`，28 modules；
    dist JS 76.56 kB / CSS 6.92 kB，gzip 后 29.98 kB / 1.93 kB）
  - 后端回归：`cd backend && python -m pytest` → 125 passed, 1 skipped（后端未被修改，复跑确认）
  - 端到端实测：
    `npm run dev` → `GET http://127.0.0.1:5173/api/v1/mock/demo` 返回 200 且 `X-Data-Source: mock`；
    `npm run preview` → `GET http://127.0.0.1:4173/api/v1/mock/demo` 同样返回 200；
    关闭后端后同一请求失败（502），页面因此走 error 分支
- 使用数据：Mock
- 公共接口是否变化：否（未修改 `/schemas/` 与 `/docs/interfaces/`）
- 是否修改 backend：否
- 已知问题 / 踩坑记录：
  - `typescript` 默认装到了 v7，而 `vue-tsc@3` 尚不兼容（报 `./lib/tsc` 未导出），
    已将 `typescript` 固定为 `^5.9.0`
  - Vite 默认绑定 `localhost`，Node 在 Windows 上优先解析到 IPv6 `::1`，
    导致 `http://127.0.0.1:5173` 访问失败；已在 `vite.config.ts` 中显式 `host: '127.0.0.1'`
  - 前端类型是与 `/schemas/` **手工对齐**的，不是代码生成，契约变更时需要同步
- 需要人工确认：无（技术栈已确认）
- 对其他模块影响：无。后端未改动；`/api/v1/mock/*` 仍是永久 Mock 通道
- 下一步：Phase 2B 设计比赛 Demo 的信息结构（故事线）；在此之前不接 Agent / LLM

---

### 2026-09-30 - Phase 2A 第一轮 Review 修复（仅修 3 个 blocker）
- 本次目标：只修 Reviewer 指出的 3 个前端 blocker，不进入 Phase 2B、不做其他重构。
- 已完成：
  1. `App.vue` 成功态把四个展示组件分别放进 `SectionCard`，补上
     「补修任务 / 教学班 / 用户偏好 / 最终方案」四个顶层标题，`Mock` 标记因此真正显示；
     未改动任何组件内部逻辑。
  2. 修正 `PlanResultPanel.vue` 两处动态 class 的错误写法：
     `class="tag tag--plan-{{ ... }}"` 与 `class="tag tag--risk-{{ ... }}"` 改为 `:class` 绑定，
     现在会正确生成 `tag--plan-feasible|partially_feasible|infeasible`
     与 `tag--risk-low|medium|high`。
  3. 修正 `unresolved` 的展示语义：区块标题改为「未解决事项（unresolved）」；
     `manual_confirmation` 显示"待人工确认"、`missing_data` 显示"缺少数据"，
     未知 `type` 原样显示并保留原始 type 标签。
     `unresolved[].type` 在公共 Schema 中是开放字符串，前端**不做业务归类**。
- 修改文件：
  - `frontend/src/App.vue`
  - `frontend/src/components/PlanResultPanel.vue`
  - `frontend/src/utils/labels.ts`（新增 `UNRESOLVED_TYPE_LABEL` / `unresolvedTypeLabel`）
  - `frontend/README.md`、本文件
- 测试：`cd frontend && npm run build`（`vue-tsc --noEmit` + `vite build`）→ 通过
- 使用数据：Mock
- 公共接口是否变化：否（未修改 `/schemas/` 与 `/docs/interfaces/`）
- 是否修改 backend：否（backend 未改动，沿用已确认的 125 passed, 1 skipped）
- 是否引入新依赖：否
- 已知问题：无新增
- 需要人工确认：无
- 下一步：等待 Reviewer 第二轮验收；Phase 2B 未开始

---

### 2026-09-30 - 负责人路线校准（docs-only）
- 本次目标：按负责人校准，修正两份文档里的"下一阶段定位"与"模块职责描述"。
  **不改代码、不改 Schema、不改 Interface**；本文件只追加记录，不改写任何历史条目。
- 已完成：
  1. `docs/status/agent_frontend.md`：下一阶段由"比赛 Demo 故事线"改为
     **Integration / Orchestrator 集成骨架**；对应阻塞项同步更新
     （改为"集成骨架尚未建立：上游模块没有正式接入点"）。
  2. `docs/ARCHITECTURE.md`：Curriculum 与 Planner 的职责 / 不负责范围按 `/AGENTS.md` 第 5 节重写，
     并补充"Planner 消费 Curriculum 的补修任务、课程依赖结果与已确认优先级，
     不得自行重写课程认定或学业优先级规则"；数据流图下补了一条说明，
     指出图中 Curriculum 的输出是简写，Planner 的输入不止 `MakeupTask[]`。
  3. 本文件追加本条校准记录。
- 负责人校准要点：
  - 此前讨论过的 8 幕比赛 Demo 故事线已由负责人叫停，未进入远端仓库或 main，
    不属于当前开发主线；后续比赛展示设计须由负责人另行下发任务。
- 修改文件：
  - `docs/status/agent_frontend.md`
  - `docs/ARCHITECTURE.md`
  - 本文件
- 测试：本次为 docs-only，未改动任何代码。已复跑确认现状仍为绿：
  前端 `cd frontend && npm run build` 通过；后端 `cd backend && python -m pytest` → 125 passed, 1 skipped
- 使用数据：Mock
- 公共接口是否变化：否（未修改 `/schemas/` 与 `/docs/interfaces/`）
- 是否修改 backend：否
- 已知问题：无新增
- 需要人工确认：无
- 下一步：等待负责人下发新的 Phase 2B 技术任务书（Integration / Orchestrator 集成骨架）
