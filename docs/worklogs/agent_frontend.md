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

---

### 2026-09-30 - Phase 2B-0A：真实数据获取规划（docs-only）
- 本次目标：在真实对接开发之前，先完成"需要什么数据、从哪来、能不能拿、拿到后怎么存"的规划，
  并建立数据源登记、Schema 承载能力分析与成员交接的框架。**不获取任何真实数据。**
- 已完成：
  1. 新增 `docs/data/DATA_ACQUISITION_PLAN.md`：五类数据（D1 政策 / D2 原专业培养方案 /
     D3 新专业培养方案 / D4 已修课程 / D5 教学班）逐类规划，含用途、来源、授权、最小字段、
     允许与禁止的采集方式、脱敏要求、当前状态与下一步行动；并确立
     Raw → Sanitized Sample → Mock 三层数据模型与红线。
  2. 新增 `docs/data/DATA_SOURCE_REGISTRY.md`：13 字段正式登记模板与 `source_id` 命名约定
     （POLICY / CURR-OLD / CURR-NEW / TRANSCRIPT / OFFERING），未写任何未确认 URL。
  3. 新增 `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`：五个公共 Schema 的承载能力分析框架，
     含 8 条待验证初步观察；明确"只记录缺口，不修改公共 Schema，不自行设计正式字段"。
  4. 新增 `docs/data/MEMBER_DATA_HANDOFF.md`：Curriculum / Planner 的数据需求、交接规则与清单模板；
     明确 Raw 不得直接交给其他成员。
  5. 第一轮 Review 修订（本轮一并提交）：
     - 明确 GitHub 仓库为 **public**；
     - **D4 收紧**：Raw 绝不进 Git，**脱敏样本也不得进入 public 仓库**，只能经负责人控制的
       非公开位置交付；第一版脱敏默认只保留 课程号 / 课程名 / 学分 / 修读学期 / 是否通过 /
       必要课程性质，不保留具体成绩 / GPA / 排名；
     - **D5 隐私表述修正**：不再写"不含个人信息"，改为"Raw 按潜在含个人信息处理，实际检查后再判断"；
       D5 的 Raw 与真实 Sanitized 样本都先不进 public Git；
     - 契约原则改写为"未经批准不得私自绕过或扩展契约；语义无法表达时登记缺口并提交接口变更请求"；
     - D2 / D3 案例描述改为"同一转专业案例的适用专业、年级 / 培养版本"，不要求同一自然人；
     - 补齐 **Curriculum → Planner 边界缺口**：`MakeupTask[]` 是当前已存在的稳定公共对象，
       但"课程依赖结果"与"已确认优先级"目前没有正式公共 Schema，
       不得自行设计私有跨模块格式；
     - G1 / G2 / G4 措辞由"没有承载对象"改为"当前没有明确的跨模块公共 Schema / 正式表示"，
       不预设最终一定新增 Schema（也可能是模块内部输入）；
     - 记录 **G6 裁决**：`StudentProfile` 当前不是已实现、可使用的公共契约，
       视为受公共契约规则保护的保留 / 候选概念，任何模块不得依赖，后续需走【接口变更请求】；
     - 记录**数据阶段顺序**：2B-0A 规划 → 2B-0B 公开政策 / 培养方案 → 2B-0C 已修课程脱敏
       → 2B-0D 教学班技术侦察 → 数据 Gate → 恢复 Phase 2B Integration。
- 修改文件：
  - 新增 `docs/data/DATA_ACQUISITION_PLAN.md`、`docs/data/DATA_SOURCE_REGISTRY.md`、
    `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`、`docs/data/MEMBER_DATA_HANDOFF.md`
  - 更新 `docs/status/agent_frontend.md`（当前阶段改为 Phase 2B-0）、本文件
- 测试：本次为 docs-only，未改动任何代码，因此未复跑前后端；
  最近一次确认仍为：前端 `npm run build` 通过、后端 `python -m pytest` → 125 passed, 1 skipped
- 使用数据：Mock（**未获取任何真实数据**）
- 公共接口是否变化：否（未修改 `/schemas/` 与 `/docs/interfaces/`）
- 是否修改 backend / frontend / mock_data：否
- 是否获取真实数据：**否**（未抓取、未写爬虫、未登录教务系统、未采集任何样本）
- 需要人工确认：Demo 转专业案例、可引用政策文件清单、D4 脱敏字段最终范围、非公开存放位置、
  D5 技术侦察范围与频率（详见 `docs/data/DATA_ACQUISITION_PLAN.md` 第 7 节）
- 下一步：等待 Reviewer 验收 2B-0A；通过后进入 **2B-0B 公开官方材料获取**。
  本轮**不进入 2B-0B**；Phase 2B（Integration / Orchestrator）保持暂停编码。

---

### 2026-09-30 - Phase 2B-0B：中山大学公开官方材料获取（docs-only）
- 本次目标：只获取 Case A（2025级 遥感科学与技术 → 网络空间安全）可用的中山大学**公开官方**政策与培养方案来源，
  确认 D1 / D2 / D3 的证据状态。**不登录教务系统、不采集任何个人数据。**
- 已完成：
  1. 新增 `docs/data/SYSU_CASE_A_PUBLIC_EVIDENCE.md`：Case A 证据清单，
     逐项记录"能证明什么 / 不能证明什么 / 当前有效性判断依据"。
  2. `docs/data/DATA_SOURCE_REGISTRY.md`：新增「证据等级」字段
     （Confirmed / Partial / Not Found / Historical / 不适用），登记 12 条中山大学公开官方来源并补齐 14 个字段。
  3. `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`：依据真实材料把 **G1 更新为「已由真实材料部分验证」**（见 4.2）；
     G2 / G3 / G4 / G5 / G7 / G8 因缺乏真实证据**维持「待验证」**；**未修改任何公共 Schema**。
  4. 更新 `docs/status/agent_frontend.md`、本文件。
- 调查结果（证据状态）：
  - **D1 政策：Partial** —— Confirmed 2（`POLICY-001` 学籍管理规定〔2026〕62号；
    `POLICY-003` 网络空间安全学院 2026 年转院系专业考核通知）；
    Partial 4（`POLICY-002` 转专业实施办法现行性未确认、`POLICY-004`、`POLICY-005`、
    `POLICY-006` 学院发布的学分成绩转换操作指南）；
    Historical 1（`POLICY-007` 学籍管理规定〔2022〕52号，已被取代）；
    另：`POLICY-003` 所引用的上级通知原文、校级课程认定专门制度 **Not Found**。
  - **D2 2025级 遥感科学与技术 正式培养方案：Not Found** ——
    只有 `CURR-OLD-001`（2019 级正式培养方案）与 `CURR-OLD-002`（2021 年专业白皮书），
    **均不能替代 2025 级**。
  - **D3 2025级 网络空间安全 本科正式培养方案：Not Found** ——
    学院「本科生培养 → 培养方案」栏目下**只有课程表**（`CURR-NEW-003`）；
    检索到的"2025 年方案"实为**硕士**培养方案（`CURR-NEW-002`，标记**不适用**并明确排除）。
- 关键判断（防误用）：
  - **专业白皮书 ≠ 正式培养方案**：`CURR-OLD-002` 虽含总学分 170 与课程模块学分构成，
    但它**不是培养方案**，且未声明适用 2025 级；
  - **2019 级正式方案 ≠ 2025 级方案**：不得用旧版顶替；
  - **研究生方案 ≠ 本科方案**：`CURR-NEW-002` 标题含"2025 年"但属硕士层次，不得作为 D3 依据；
  - **政策存在版本冲突**：学籍管理规定〔2026〕62号与〔2022〕52号并存，
    适用版本**标记【待人工确认】**，Agent 未自行裁决。
- 修改文件：
  - 新增 `docs/data/SYSU_CASE_A_PUBLIC_EVIDENCE.md`
  - 更新 `docs/data/DATA_SOURCE_REGISTRY.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - 更新 `docs/status/agent_frontend.md`、本文件
- 测试：本次为 docs-only，未改动任何代码，因此未复跑前后端；
  最近一次确认仍为：前端 `npm run build` 通过、后端 `python -m pytest` → 125 passed, 1 skipped
- 使用数据：Mock（**未获取任何真实数据文件**；仅查阅公开官方页面，**未下载任何原件进仓库**）
- 公共接口是否变化：否（未修改 `/schemas/` 与 `/docs/interfaces/`）
- 是否修改 backend / frontend / mock_data：否
- 是否登录教务系统 / 获取个人数据：**否**（未登录、未用 NetID、未取成绩单或课表、
  未保存 Cookie/Session/Token、未 HAR 抓包、未写爬虫、未批量请求）
- 需要人工确认：
  1. D2 / D3 的 2025 级正式培养方案缺失，走哪条补充路径（用户本人导出 / 咨询学院教务 / 暂缓）；
  2. 学籍管理规定适用版本（〔2026〕62号 vs 〔2022〕52号）；
  3. `POLICY-002` 转专业实施办法的现行性；
  4. `POLICY-006` 的校级权威原件出处。
- 下一步：等待 Reviewer 验收 2B-0B。**不进入 2B-0C / 2B-0D**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Phase 2B-0B Reviewer 修复：学籍管理规定版本链（docs-only）
- 本次目标：**只修政策版本链**，不进入 2B-0B+ / 2B-0C / 2B-0D，不登录教务系统。
- Reviewer 指出的问题：原文档把「2022〔52号〕→ 2026〔62号〕」直接写成"旧版被取代"，
  版本链不完整，且缺少正文证据。
- 已完成：
  1. **新增 `POLICY-008`**：中山大学本科生学籍管理规定（**中大教务〔2025〕1号**），
     官方 URL <https://marine.sysu.edu.cn/article/10375>，发布 **2025-04-05**，
     适用"我校全日制本科生"（正文第二条），证据等级 **Confirmed**。**未复用任何已有 source_id。**
     本轮**直接读到正文**：第五章（课程考核与成绩记载）、**第六章第三十一条（转专业后的学分认定与成绩转换）**、
     **第八章（转院系专业，第三十九–四十三条）**。
  2. **修正 `POLICY-007`**：删除"已被 `POLICY-001`〔2026〕62号取代"的表述，改为
     "较早历史版本；其后至少还存在 2024〔159号〕/ 2025〔1号〕/ 2026〔62号〕；
     逐版废止关系尚未全部取得官方正文证据，**不得**描述为被 2026〔62号〕直接取代"。
  3. **新增 `SYSU_CASE_A_PUBLIC_EVIDENCE.md` 第 2.5 节「学籍管理规定版本链」**，
     严格区分"已有正文直接证据"与"仅已确认版本存在、尚未确认废止关系"：
     - ✅ **2024〔159号〕 → 2025〔1号〕**：**已有正文直接证据**（据 **Reviewer 独立确认**，
       〔2025〕1号正文写明"原《中山大学本科生学籍管理规定》（中大教务〔2024〕159号）同时废止"）。
       ⚠️ 本轮**未能直接读到该附则条文**（页面在第七十七条处截断，且本轮工具不支持抓取 PDF 正文），
       故此项**以 Reviewer 的独立确认为依据**登记。
     - ⚠️ **2025〔1号〕 → 2026〔62号〕**：**后续版本存在，但正式替代关系待确认** ——
       本轮未找到、也无法读取 2026〔62号〕正文中的明确废止 / 替代条款，**不作任何推断**。
     - ⚠️ **2022〔52号〕 → 2024〔159号〕**：替代关系未确认。
     - 另说明其他已确认存在的版本（2021〔72号〕、更早的 2018 年转载），**仅说明"存在"**。
  4. 修正 `docs/status/agent_frontend.md` 中的确定性表述：Confirmed 由 2 项改为 3 项；
     Historical 说明改写；"政策版本冲突"阻塞项改写为"版本链待人工确认"。
  5. 顺带修正证据清单 2.4 中一处已不准确的判断：原写"校级课程认定专门制度 Not Found"，
     实际该规则**存在于 `POLICY-008` 第三十一条**（本轮已直接读到）。
- 修改文件：
  - `docs/data/DATA_SOURCE_REGISTRY.md`（新增 `POLICY-008`、修正 `POLICY-007`、更新状态与变更记录）
  - `docs/data/SYSU_CASE_A_PUBLIC_EVIDENCE.md`（新增 2.5、修正 2.3、补充 2.1、修正 2.4、更新 §5、新增 §9）
  - `docs/status/agent_frontend.md`
  - 本文件（**仅追加，未改动历史条目**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 使用数据：Mock（未获取任何真实数据文件；仅查阅公开官方页面）
- 公共接口是否变化：否（未修改 `/schemas/` 与 `/docs/interfaces/`）
- 是否修改 backend / frontend / mock_data：否
- 是否登录教务系统 / 获取个人数据：**否**
- 需要人工确认：
  1. **2025〔1号〕与 2026〔62号〕的替代关系**（需取得 2026 正文，或由负责人判定）；
  2. Case A 转专业时点适用哪一版学籍管理规定；
  3. D2 / D3 的 2025 级正式培养方案补充路径（沿用上一轮结论）。
- 下一步：等待 Reviewer 验收。**不进入 2B-0B+ / 2B-0C / 2B-0D**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Phase 2B-0B+：中大教务系统培养方案证据登记（docs-only）
- 本次目标：只做四件事 —— ① 验证两份附件确为 Case A 的 2025 级本科培养方案；
  ② 新增两个"认证系统来源"；③ 把 D2 / D3 从 Not Found 更新为 Confirmed via authenticated source；
  ④ 用这两份 2025 级真实样本继续验证 Schema 承载能力。
  **不开始课程差分、不生成 MakeupTask。**
- 附件与安全扫描（**先做**）：
  - 附件 `遥感方案.docx`、`网安方案.docx` 已由 Builder **实际解包读取正文**（非依据负责人摘要）；
  - **个人身份信息扫描结果：未发现任何个人信息** —— 无「姓名 / 学号 / 考生号 / 身份证 / NetID」，
    无 10 位以上连续数字串。**故未触发"发现身份信息即停止"的条件，任务继续。**
- 已核实的真实事实（**以附件原文为准，未照抄负责人结论**）：
  - `CURR-OLD-003`（遥感）：标题写明"**25级**遥感科学与技术专业培养方案"；"**本科培养方案**"；
    **修业年限 4 年**；**毕业总学分 147.0**；实践教学学分要求 **37.1**；
    培养类别 公必 39 / 专必 78 / 专选 22 / 公选 8（合计 147 ✓）；
    附表一含 **128 个课程号单元格**（课程号 / 课程名 / 学分 / 学时 / 学期）；
    附表二 学分学时分布情况表；附表三 实践教学环节(含实验)一览表。
  - `CURR-NEW-004`（网安）：标题写明"**25级**网络空间安全…专业培养方案"；"**本科培养方案**"；
    **修业年限 4 年**；**毕业总学分 153.0**；实践教学学分要求 **38.5**；
    公必 39 / 专必 83 / 专选 23 / 公选 8（合计 153 ✓）；附表一含 **138 个课程号单元格**。
  - **与负责人核对目标逐项比对：8 项全部一致**（年级 / 层次 / 修业年限 / 毕业总学分 × 两专业）。
  - 两份材料**均不含**：先修关系（全文检索"先修"无命中）、教师、考核方式、开课单位。
- 已完成：
  1. 新增 `docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md`
     （与公开来源证据文档**分开保存**），记录 Case A、来源性质与访问边界、两份方案的
     "能证明什么 / 不能证明什么"、与负责人核对目标的比对结果。
  2. `docs/data/DATA_SOURCE_REGISTRY.md`：
     - 新增 **`CURR-OLD-003`**（25级 遥感）与 **`CURR-NEW-004`**（25级 网安），**未复用任何已有 source_id**；
     - 新增字段「**访问类型**」：`Public Official` / `Authenticated Official`，
       并明确"**公开性**与**证据真实性**分开记录"；
     - `CURR-NEW-001`（公开搜索未找到）**保留为历史记录，未删除、未改造成新来源**，
       备注补充 *Public search remained Not Found; authenticated-source gap later resolved by `CURR-NEW-004`*；
     - 登记数 13 → **15**；Confirmed 3 → **5**。
  3. `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`：
     - **§3.1 按两份真实 25 级样本逐项判定 `Course` 映射 A/B/C**：
       A = 课程号 / 课程名 / 学分；B = 课程类别·模块、推荐修读学期（学年-学期含区间，Schema 只收整数）；
       C = 学时、实验实践学时、培养方案总学分、实践教学学分、适用年级、专业、课程分组、英文课程名；
     - **G1 升级**为「已由 Case A 两份 2025 级真实培养方案确认存在」（新增 4.3 节）；
       **仍未自行判断"是否必须新增公共 Schema"**。
  4. 更新 `docs/status/agent_frontend.md`（D2 / D3 → Confirmed via authenticated official source；
     下一步 = 2B-0C 已修课程最小脱敏样本）、本文件。
- 明确未做（红线）：
  - **未做任何课程等价判断**（未写"某课=某课"、未写"可以抵认"）；
  - **未开始** Curriculum Diff、**未生成** MakeupTask；
  - **未登录**教务系统、未要求任何人提供账号密码、**未读取**成绩、**未处理** D4；
  - **未观察** Network / Fetch / XHR、**未获取**教学班、**未处理** D5、未写抓取代码；
  - **未修改** `/schemas/`、`/docs/interfaces/`、`backend`、`frontend`、`mock_data`；
  - **未恢复** Integration。
- 原始附件处理：两份 docx **不提交 public Git**，**不复制完整课程表进仓库**，**不放进 `mock_data`**；
  仓库内只保存 `source_id`、来源性质、必要结构化事实与 Schema gap 结论。
  本轮解包产生的中间文本文件**已从工作区删除**。
- 修改文件：
  - 新增 `docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md`
  - 更新 `docs/data/DATA_SOURCE_REGISTRY.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - 更新 `docs/status/agent_frontend.md`、本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 使用数据：Mock（业务数据）+ **认证来源的真实培养方案结构化事实**（原始文件不入库）
- 公共接口是否变化：否 ｜ 是否修改 backend / frontend / mock_data：否
- 需要人工确认：
  1. `SYSU_CASE_A_PUBLIC_EVIDENCE.md` 2.5 的**版本链**（2025〔1号〕→2026〔62号〕）仍待确认；
  2. 附表一的**列语义**（第三个数值列是否为"实践/实验学时"）需人工确认；
  3. Case A 转专业时点适用哪一版学籍管理规定。
- 下一步：等待 Reviewer 验收 **2B-0B+**。通过后进入 **Phase 2B-0C：已修课程最小脱敏样本**。
  **不 merge，不进入 2B-0C / 2B-0D**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Phase 2B-0B+ Reviewer 修复：文档表述与 recommended_semester 映射（docs-only）
- 本次目标：只修 Reviewer 指出的 3 个文档 blocker + 1 处措辞收严。
  **不进入 2B-0C，不碰 D4 / D5，不改任何代码 / Schema / Interface / 附件。**
- 已完成：
  1. **`DATA_SOURCE_REGISTRY.md` 顶部状态修正**：删除"只登记公开来源"的表述；
     改为**已同时登记 `Public Official` 与 `Authenticated Official` 两类来源**；
     并明确**已取得两份认证来源培养方案副本，但原始 docx 仅由负责人受控保存、不进入 public Git**。
  2. **`docs/status/agent_frontend.md` 修正**：删除"D2 / D3 的公开来源缺口已解决"的说法，改为
     "**D2 / D3 的总体证据缺口已由认证来源补齐；公开官网仍未找到对应的 2025 级正式培养方案，
     Public Not Found 历史继续保留**"；同步改写本节顶部的 ⚠️ 提示。
  3. **`REAL_TO_SCHEMA_GAP_REPORT.md` 的 `recommended_semester` 映射修正**（拆成两行，分别判定）：
     - **单一学期值**（如 `2025-1`）：**B 可转换后映射**，前提是按 **2025 级培养进程**转换为
       **整数序号**，**具体规则仍待确认**；
     - **跨学期区间**（如 `2025-1~2025-2`、`2025-1~2028-2`）：**C 当前无法无损表示** ——
       `recommended_semester` 只能存**单个 integer**，装不下"跨若干学期"的语义；
     - **不设计新字段、不修改 Schema。**
  4. **先修关系措辞收严**（`REAL_TO_SCHEMA_GAP_REPORT.md`、`SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md`
     及 `DATA_SOURCE_REGISTRY.md` 的相应备注）：把"两份材料均无先修信息"改为
     "**本次可检索文本中未发现明确的先修 / 前置课程字段或条款**"，
     并显式写明"**这只是对本次材料的观察，不构成对学校制度的结论**"。
     同时把小节标题由"附件中没有的信息"改为"**本次材料中未检索到的信息**"。
- **对本文件历史条目的勘误说明**（因本文件只追加、不改写历史）：
  上一条 2B-0B+ 记录中"两份材料**均不含**：先修关系…"的表述**过宽**，
  应理解为"**本次可检索文本中未发现明确的先修 / 前置课程字段或条款**"，
  **不构成对中山大学先修制度的有无判断**。以本条为准。
- 修改文件：
  - `docs/data/DATA_SOURCE_REGISTRY.md`
  - `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - `docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md`
  - `docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 使用数据：Mock（业务数据）+ 认证来源的结构化事实（原始文件不入库）
- 公共接口是否变化：否 ｜ 是否修改 backend / frontend / mock_data：否
- 未做：未改 Schema / Interface / 附件；未进入 2B-0C / 2B-0D；未 merge
- 下一步：等待 Reviewer 复验。**不 merge，不进入 2B-0C**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Phase 2B-0C：已修课程真实样本验证（D4，docs-only）
- 本次目标：只回答五个问题 —— ① 中大真实已修课程记录是什么形态？② 当前 `Course` Schema 能承载其中哪些信息？
  ③ 哪些属于"课程本身"？④ 哪些属于"学生的修读事实"？⑤ G2 是否被真实数据正式验证？
  **不回答**：学生缺什么课、哪两门等价、什么课可转换、什么课需补修。
- 输入与安全边界：
  - 本轮输入为负责人**已在私密侧完成合并与脱敏**的 D4 样本（**24 条**记录）；
  - 已删除：姓名、学号、**具体成绩**、GPA、排名、班级、NetID、Cookie、Session、Token；
  - `passed` 已由负责人依据**官方成绩结果**转换；**Builder 不接触原始成绩、不推断 GPA**；
  - 原始成绩单 PDF **未提供给 Builder**；逐行样本**仅存在于本地临时文件**，
    统计完成后**已删除**，**从未进入 Git**。
- 真实来源（两个，均为 **Authenticated Official**）：
  - **A. 申请成绩转换 → 实修课程成绩**：提供 课程号 / 课程名称 / 课程类别 / 学分 / 开课单位 / 成绩 / 培养类别；
  - **B. 本科生成绩单**：提供 课程名称 / 学分 / 成绩 / 课程属性 / 所属学期。
  - **重要变化**：此前认为"成绩单不提供 `course_id`"；经 A 确认**该页面能提供 `course_id`**。
- 字段覆盖统计（**唯一允许的统计口径**）：
  - 总记录数 **24**；`course_id` / `course_name` / `credit` / `semester` / `passed` /
    `course_type` / `offering_unit` / `cultivation_type` 八个字段**覆盖率均为 100%**；
  - `semester` 2 个取值（2025-1：11 条；2025-2：13 条）；`passed` 样本内全部为 true；
  - `course_type` 4 个取值（公必 12 / 专必 8 / 公选 3 / 专选 1）；
  - `offering_unit` **11 个不同开课单位**；`cultivation_type` 样本内**单一取值**（主修）；
  - `credit` 取值 1–5，无 0 / 负值；`course_id` 24 个唯一值（无重复行）。
  - ⚠️ **未写入任何逐行课程清单、具体成绩或 GPA。**
- Schema 判定（`REAL_TO_SCHEMA_GAP_REPORT.md` 新增 **§3.6**）：
  - **A 可直接映射**：`course_id`、`course_name`、`credit`；
  - **B 可转换后映射**：`course_type`（现有字段为自由字符串、无枚举，取值体系待确认）；
  - **C 当前无正式表示**：`semester`、`passed`、`offering_unit`、`cultivation_type`；
  - **特别强调**：`semester` 是**学生实际修读学期**，**不得**映射到 `recommended_semester`
    （后者是**培养方案建议学期**，语义完全不同）；`passed` 是**某个学生的一次修读结果**，
    **不是课程固有属性**，**不得塞入 `Course`**；`cultivation_type`（样本为"主修"）与
    `course_type`（公必/专必/专选/公选）**不是同一语义**，**不得强行当成 `course_type`**。
- G2 验证（新增 **§4.4**）：**G2 更新为「已由 Case A 真实 D4 样本验证」** ——
  学生的修读事实（`semester` / `passed`）与开课侧 / 培养语境信息（`offering_unit` / `cultivation_type`）
  **无法由 `Course` 完整表达**。**未自行决定新增 `CompletedCourse` 或任何 Schema**，只记录问题；
  最终形态（Curriculum 内部模型 / Integration DTO / 正式公共契约）**由架构负责人决定**。
- 登记（`DATA_SOURCE_REGISTRY.md`）：**登记既有 `TRANSCRIPT-001`**（**未创建新的 D4 `source_id`**）：
  D4 / 中山大学本科教务系统 / **Authenticated Official** / 官方 / 不公开 / 需登录（仅本人正常权限）/
  来源 = A + B / **Evidence Grade：Confirmed**；并注明 **Raw 成绩单与逐行脱敏记录均不入库**，
  **Git 仅登记汇总事实与字段覆盖**。
- 关于"申请成绩转换"页面右侧状态：**只记录一条汇总结论** ——
  教务系统内**存在官方的成绩转换 / 培养方案对照状态**，可作为后续 Curriculum 结果的**外部验收参考**。
  **未**把红色课程当作 Curriculum Diff 输出、**未**复制进 `mock_data`、**未**据此做任何等价或补修判定。
- 课程等价：**本轮完全未做**（即使样本与培养方案中出现名称相近课程，也未写任何等价或抵认结论）。
- 修改文件：
  - 新增 `docs/data/SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md`
  - 更新 `docs/data/DATA_SOURCE_REGISTRY.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - 更新 `docs/status/agent_frontend.md`、本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 使用数据：Mock（业务数据）+ **D4 真实脱敏样本的汇总事实**（逐行样本不入库，已删除）
- 公共接口是否变化：否 ｜ 是否修改 backend / frontend / mock_data：否
- 未做：未登录教务系统、未保存 Cookie/Session/Token、未获取教学班、未做 Network/XHR 侦察、
  未进入 2B-0D、未改 Schema / Interface、未做 Curriculum Diff、未生成 MakeupTask、未恢复 Integration
- 下一步：等待 Reviewer 验收 **2B-0C**。通过后进入 **Phase 2B-0D：教学班技术侦察**（**本轮不得自行开始**）。
  **不 merge**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Phase 2B-0C Reviewer 修复：`course_type` 语义归属 + 隐私口径（docs-only）
- 本次目标：只修 2 个 Reviewer blocker —— ① `course_type` 的语义归属过强；② 公开 Git 中记录了
  真实个人的 `passed` 结果分布。**不进入 2B-0D，不改代码 / Schema / Interface / Mock。**
- Blocker 1：**修正 `course_type` 的语义归属**
  - 原先把 `course_id` / `course_name` / `credit` / `course_type` **统一定义为"课程本身的固有属性"**，
    该结论过强（同一门课在专业 A 可能是专必、在专业 B 可能是专选、在某培养方案可能是公选）；
  - 改为四类归属：**课程核心标识 / 基础属性**（`course_id` / `course_name` / `credit`）、
    **学生修读事实**（`semester` / `passed`）、**培养方案 / 上下文属性**（`course_type`）、
    **归属待确认**（`offering_unit` / `cultivation_type`）；
  - §3.6 中 `course_type` 仍记 **B 可转换后映射 → `Course.course_type`**，但**补充明确说明**：
    这只表示**现有契约能够承载该字符串值**，**不证明**"公必 / 专必 / 专选 / 公选"是课程的
    **全局固有属性**；它可能依赖**具体培养方案 / 专业 / 年级上下文**，**最终数据归属本轮不作架构裁决**；
  - §3.1 的 `course_type` 行同步补注；§4.4 的表述同步改写；
  - **已确认全仓不再出现**"课程的固有属性"、"与谁修读无关"、"属于'课程本身'"等旧断言。
- Blocker 2：**删除真实个人 `passed` 结果分布**
  - 公开 Git **不再记录**"24 条全部 `passed=true`"；
  - 只保留：**覆盖率 24/24** + **类型 / 语义 = boolean，表示某学生一次修读是否通过**；
  - 同时按建议进一步最小化个人学业画像：`semester` 改为"**覆盖两个学期**"（删除 11/13 分布）；
    `course_type` 只列**取值种类**（公必 / 专必 / 专选 / 公选），**删除 12/8/3/1 数量**；
    `offering_unit` 改为"观察到**多个不同开课单位**"（删除具体计数与分布细节）；
  - **24 条总记录数保留**（此前批准的样本规模元数据）。
- **勘误（对本文件历史条目的说明）**：本文件 2B-0C 原有条目中出现的
  "`passed` 样本内全部为 true"、"`course_type` 4 个取值（公必 12 / 专必 8 / 公选 3 / 专选 1）"、
  "`semester` 2 个取值（2025-1：11 条；2025-2：13 条）"、"`offering_unit` 11 个不同开课单位"
  等**分布性表述已不再作为公开口径**；因本文件**只追加、不改写历史**，此处一并勘误：
  **上述分布信息一律以本轮修复后的公开文档为准，且不再在 public Git 中记录**。
  同理，历史条目中若把 `course_type` 视作"课程固有属性"，**以本轮修复为准**。
- G7 处理：**本轮明确不升级 G7**。`offering_unit` 只能证明"**已修记录**里有这个字段"，
  **不能证明教学班页面也提供同样字段**；须等 **2B-0D** 用真实教学班验证。
- 修改文件：
  - `docs/data/SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md`
  - `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - `docs/data/DATA_SOURCE_REGISTRY.md`（本轮未改；确认其中无分布性表述）
  - `docs/status/agent_frontend.md`（本轮未改；确认其中无分布性表述）
  - 本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 公共接口是否变化：否 ｜ 是否修改 backend / frontend / mock_data：否
- 未做：未进入 2B-0D、未获取教学班、未登录教务系统、未改 Schema / Interface、未 merge
- 下一步：等待 Reviewer 复验。**不 merge，不进入 2B-0D**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Phase 2B-0D：教学班（CourseOffering）技术侦察（docs-only）
- 本次目标：用**已取得**的真实教学班侦察样本，验证 `CourseOffering` 的字段承载能力与真实结构。
  人工技术侦察**到此结束**，不再查询更多课程。**只做结构分析**：不写 parser、不建数据库、
  不写 Course Data Adapter、不进入 Integration。
- 侦察来源（**Authenticated Official**，小规模）：
  - 方法 / 路径：`POST /jwxt/schedule/agg/schoolOpeningCoursesSchedule/querySchoolOpeningCourses`；
  - 查询参数：`pageNo` / `pageSize` / `total` / `param.yearTerm` / `param.courseNumber`；
  - 本轮取值：`yearTerm = 2026-1`、`courseNumber = CSE202`；返回 `code = 200`、`data.total = 2`。
  - **只记录路径与查询参数**；**未记录** Cookie / Session / Token、完整 Request Headers、HAR。
- 汇总事实：**`CSE202` 在 2026-1 返回 2 个真实教学班**；每个教学班含**多个上课时间 / 地点 segment**。
- 字段映射结论（详见 `SYSU_COURSE_OFFERING_RECON.md` 与缺口报告 §3.2）：
  - **A**：`courseNum → course_id`、`courseName → course_name`、`classNumber → class_id`、
    `yearTerm → semester`、`limitNumber → capacity`；
  - **B**：`score → credit`（**字符串数字**需转 number）；
    `remaining_capacity` = `limitNumber - selectedNumber`（**派生值**）；
  - **C**：`selectedNumber`、`openingUnitName`、`courseCategoryName`、`examMode`、`readObj`、
    `teachProgressSubmitState`、`openClass`；
  - `teachingName → teacher` 为 **A/B**（**教师姓名不入库**）。
- **本轮最重要的发现 —— 新增 G9**：
  - `CSE202` 的**每个教学班都存在多个 schedule segment**（例如"1-17周 星期一 第3-4节 某教室"
    ＋ "1-17单周 星期三 第5-6节 某教室"）；
  - 而当前 `CourseOffering` **只能表达一组** `weekday` / `start_section` / `end_section` /
    `weeks[]` / `campus` / `classroom`；
  - 因此登记为**真实结构缺口**：**一个教学班可以拥有多个独立的上课时间 / 地点 segment，
    当前 `CourseOffering` 无法在一个对象中无损表达**；
  - **明确未做**：未改 Schema、未新增 `meetings[]`、未只保留第一段、未丢弃其他时间段、
    **未把同一教学班拆成多个可独立选择的 `CourseOffering`**；**最终表示方式留给 Data Gate**。
- **新增 G10**：D5 另有多个真实字段在现有 `CourseOffering` 中**没有任何表示**
  （`selectedNumber` / `openingUnitName` / `courseCategoryName` / `examMode` / `readObj` /
  `teachProgressSubmitState` / `openClass`）；**只登记、不设计字段**。
- **G7 升级为「已由真实 D5 样本验证」**：真实 JSON 中确实出现 `openingUnitName` 与 `courseCategoryName`
  （2B-0C 预留的"须等 2B-0D"条件已满足）。
- 重要口径（已写入文档）：
  - ⚠️ **不得声称学校接口直接提供 `remaining_capacity`** —— 它是**派生值**；
  - ⚠️ `courseCategoryName`（样本为"专必"）**带培养方案 / 上下文语义**，
    **不得**认定为课程的**全局固有属性**（与 D4 的 `course_type` 同源问题）；
  - ⚠️ `teachProgressSubmitState` / `openClass` / `outlineTypeNum`：**字段存在，业务语义待确认**，
    **不根据 0/1 值自行解释**；
  - ⚠️ `courseId` / `class_ID` 等**后台长 ID 不等于**公共 `course_id` / `class_id`；
    **只记录其存在**，**不记录其值**，本轮**不设计对应字段**。
- 周次格式（**仅结构记录，未实现 parser**）：已确认真实格式至少含 `1-17周`（→ `[1..17]` 的潜在转换）
  与 `1-17单周`（→ `[1,3,5,…,17]` 的潜在转换）；正式转换规则留待 Data Gate / Course Data 定义。
- 登记（`DATA_SOURCE_REGISTRY.md`）：**登记 `OFFERING-001`**（D5，**Authenticated Official**，
  证据等级 **Confirmed**，范围 **2026-1** 小规模侦察）；
  **Raw response / Cookie / Session / Token / 完整 Request Headers / HAR 均不入库**；
  **不记录**教师姓名、修读对象完整文本、内部长 ID 取值、完整教学班逐行记录。
- 修改文件：
  - 新增 `docs/data/SYSU_COURSE_OFFERING_RECON.md`
  - 更新 `docs/data/DATA_SOURCE_REGISTRY.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - 更新 `docs/status/agent_frontend.md`、本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 公共接口是否变化：否 ｜ 是否修改 backend / frontend / mock_data：否
- 未做：未登录教务系统、未保存 Cookie/Session/Token、未采集 HAR、**未写 crawler**、
  **未建数据库**、**未写 Course Data Adapter**、未改 Schema / Interface、**未进入 Integration**
- 下一步：等待 Reviewer 验收 **2B-0D**。通过后进入 **Data Gate**
  （处理 G9 多 segment 建模与 `Course` / `CurriculumCourse` / `CompletedCourse` 的架构边界）。
  ⚠️ **不得自行开始**。**不 merge**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Phase 2B-0D Reviewer 修复：§3.2 字段来源 + 登记表状态措辞（docs-only）
- 本次目标：只修 2 个 Reviewer blocker。**不再查询教务系统、不进入 Data Gate、
  不写 parser、不建数据库、不写 Adapter、不改 Schema / Interface / 代码 / Mock。**
- Blocker 1：**修正 `REAL_TO_SCHEMA_GAP_REPORT.md` §3.2 的真实字段来源**
  - 问题：原表在「真实 D5 字段」列里误列了
    `weekday` / `start_section` / `end_section` / `weeks[]` / `campus` / `classroom` ——
    **这些是公共 `CourseOffering` 的目标字段，不是 SYSU Response 的真实字段**，
    且被错误判为"C 当前无正式表示"（它们其实**在现有 Schema 中已经存在**）；
  - 处理：**删除该行**，改为以**实际 Response 字段**为源：
    `teachingTimePlaceStr`、`openingSchoolName`、`weekDay`；
  - **`teachingTimePlaceStr` 明确区分两层**（已写入表格与表下说明）：
    ① **单个 schedule segment** → 可解析为 `weeks` / `weekday` / `start_section` / `end_section` /
    `campus` / `classroom` → 属**数据转换层能力（B）**；
    ② **整个教学班** → 该字段**可包含多个 segment**，而当前一个 `CourseOffering` **只能表达一组**
    → **无法无损映射（C）→ G9**；
  - `openingSchoolName` / `weekDay` 标为 **B 待确认**：**字段真实存在**，
    分别与 `campus` / `weekday` **有关联**，但**具体转换 / 对应关系待确认**（多 segment 时如何取值不明）；
    **不猜**；
  - 表下新增「**真实 D5 字段」列的填写纪律**说明：该列**只列 Response 中实际出现的字段**，
    目标字段不得混入。
  - **保持**：不修改 Schema、不设计 `meetings[]`、不实现 parser。
- Blocker 2：**修正 `DATA_SOURCE_REGISTRY.md` 状态措辞**
  - 问题：原文"已登记来源数：17（**全部已确认，无"待填写"**）"会与
    **Evidence Grade = Confirmed** 混淆；
  - 改为："已登记来源数：17（**均已完成来源登记 / 状态判定，无"待填写"项**）"；
  - 并**保留并强化**真实证据等级分布，加注"注意：并非全部来源都是 `Confirmed`"：
    **Confirmed 7 ｜ Partial 7 ｜ Not Found 1 ｜ Historical 1 ｜ 不适用 1**；
  - 明确：**不得**把这 17 个来源全部描述成 Evidence Grade = Confirmed。
- 未改动的文件：`docs/status/agent_frontend.md` 与各 Evidence 文档**本轮未改**
  （复查后确认其中不含上述两类问题，**不为凑修改范围而改**）。
- 修改文件：
  - `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - `docs/data/DATA_SOURCE_REGISTRY.md`
  - 本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 公共接口是否变化：否 ｜ 是否修改 backend / frontend / mock_data：否
- 未做：**未再查询教务系统**、未保存 Cookie/Session/Token、未采集 HAR、未写 crawler、
  未实现 parser、未建数据库、未写 Adapter、未改 Schema / Interface、**未进入 Data Gate**、
  未进入 Integration
- 下一步：等待 Reviewer 复验。**不 merge，不进入 Data Gate**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Data Gate-1：架构裁决整理（docs-only）
- 本次目标：把 D1–D5 真实数据已暴露的架构问题，整理成**正式 Data Gate 决策草案 +
  公共接口变更请求草案（DG-01 – DG-06）**，交 Reviewer / 负责人裁决。
  **不编码、不改契约、不调 SYSU 接口、不进入 Data Gate-2。**
- 起点：`main` = `ad95d35fd802f692b223902509f2d94bfb33bb26`（= 上一轮 2B-0D 合并后）；
  新建分支 `docs/data-gate-architecture`。
- **新增 `docs/data/DATA_GATE_DECISIONS.md`**，含 15 节：
  - **§1 Data Gate 目的**：Phase 1 的 Schema 是在没有真实数据时设计的；D2–D5 已足够暴露结构性问题，
    **暂停继续采集，先做架构裁决**；明确"做 / 不做"清单。
  - **§2 D1–D5 已确认事实**：D1（3 Confirmed / 4 Partial / 1 Historical / 上级通知原文 Not Found；
    版本链仅 2024〔159号〕→2025〔1号〕有正文证据）、D2 `CURR-OLD-003`（147.0 / 37.1 / 128 单元格）、
    D3 `CURR-NEW-004`（153.0 / 38.5 / 138）、D4 `TRANSCRIPT-001`（24 条 / 8 字段 100%）、
    D5 `OFFERING-001`（2026-1，`CSE202` → 2 个教学班）；并**继承 6 条既有限制**
    （`remaining_capacity` 是派生值、`courseCategoryName` 带方案上下文、
    `teachProgressSubmitState` / `openClass` / `outlineTypeNum` 语义待确认、
    后台长 ID ≠ 公共标识、公开搜索仍 Not Found、本轮不做课程等价判断）；
    **§2.2 特别指出**：真实培养方案样本中**未发现先修字段** → `prerequisites[]` 的
    "可被真实数据填充"**尚无证据**（不构成"学校无先修制度"的结论）。
  - **§3 核心实体边界（7 个概念）**：`Course`（基础身份，**不承担**修读结果与专必/专选上下文）、
    `CurriculumVersion`、`CurriculumCourse`（方案上下文：`course_type` / 推荐学期 / 分组 / 先修）、
    `CompletedCourse`（**`semester` / `passed` 绝不能塞回 `Course`**）、
    `CurrentEnrollment`（必须与 `CompletedCourse` / `CourseOffering` / `Preference` 分开，
    Planner 冲突检测需要它）、`CourseOffering`（供给）、`ScheduleSegment` / `Meeting`；
    明确"核心原则 `Course ≠ CurriculumCourse ≠ CompletedCourse`"与"四类信息互不替代"。
  - **§4 实体所有者**：13 行表（实体 → 所有者模块 → 消费方 → 当前是否公共契约 → 建议）+
    沿用 `/AGENTS.md` 第 5 节的边界红线。
  - **§5 Shared / Private / Derived**：学校共享（`Course` / `CurriculumVersion` / `CurriculumCourse` /
    `CourseOffering` / semester offering snapshot）；用户私有（`CompletedCourse` / `CurrentEnrollment` /
    `Preference` / **用户适用的 `CurriculumVersion` reference**）；派生（`MakeupTask` / risk / priority /
    `PlanResult`）。**本轮不设计 PostgreSQL 表 / ORM / migration。**
  - **§6 G9 多 segment 裁决（本轮最重要）**：概念关系 `CourseOffering 1 — N ScheduleSegment`；
    每个 segment 至少 6 项（`weekday` / `start_section` / `end_section` / `weeks[]` / `campus` / `classroom`）；
    **`teacher` 层级结论**：真实 D5 中 `teachingName` 出现在**教学班层级**，
    **无证据**表明是 meeting 级 → MVP **建议 `teacher` 保持在教学班级、不下放到 segment**；
    **4 个候选方案（A 段数组 / B 保留单段+可选数组 / C 同 `class_id` 多行 / D 内部保留、对外合并）**
    及各自代价；**明确禁止**：❌ 只保存第一个 segment、❌ 拆成多个可独立选择的 `CourseOffering`；
    再次声明**不设计 `meetings[]`**、字段名 / 类型一律待裁决。
  - **§7 Curriculum → Planner 契约分析**：以 `/AGENTS.md` 第 5 节为权威边界；
    **登记 `docs/interfaces/planner.md` 接口文档债务**（把"课程依赖图 / 补修优先级与风险"
    写成 Planner 职责，并列出 `build_dependency_graph` / `calculate_priority`，与 AGENTS 冲突）；
    **`MakeupTask.prerequisites[]` 是否足够** → "很可能足够、**优先不新增 `DependencyGraph`**"，
    并区分"Planner 自算拓扑序"（属 Planner）≠"Planner 自行认定先修"（属 Curriculum）；
    **优先级**：列出 5 条候选（新增 `priority` 字段 / 数组顺序 / 时间字段 / `reason` 文本 /
    留在 Curriculum 内部），逐一给出代价，**字段名 / 类型 / 取值域 / 枚举一律待裁决**。
  - **§8 当前 Schema / Interface 缺口**：G1–G10 状态表 + **5 条新缺口**
    （新-1 `planner.md` 冲突、新-2 优先级无承载、新-3 依赖结果无公共对象、
    新-4 `Course.course_type` / `recommended_semester` 位置不当、新-5 跨学期区间无法表达）；
    强调"**缺口 ≠ 必须新增 Schema**"。
  - **§9 最小接口变更集合**：P0 = DG-01 / DG-03；P1 = DG-02 / DG-04 / DG-05；P2 = DG-06；
    并列出本轮**不进入**变更集合的项（G3 / G5 / 暂缓字段 / `StudentProfile`）。
  - **§10 暂缓字段**：按 A/B/C/D 分类逐项处置
    （`selectedNumber` → **B**，`remaining_capacity` 用派生值；`openingUnitName` → **B**；
    `courseCategoryName` → **归属转移至 DG-04**，**不进 `CourseOffering`**；
    `examMode` → **C**；`readObj` → **C + 待确认**（未来可能影响可选资格，当前规则不足）；
    `teachProgressSubmitState` / `openClass` / `outlineTypeNum` → **D**；
    内部 ID → **C**；`teachingTimePlaceStr` → **B 转换层**；
    `openingSchoolName` / `weekDay` → **D 转换关系待确认**；
    D4 的 `offering_unit` → **B**、`cultivation_type` → **D**）+ 三条纪律。
  - **§11 Course Data 获取边界**：完整链路
    `SYSU authenticated source → Adapter/Importer → Normalizer → Semester Offering Snapshot →
     CourseDataProvider → Integration → Planner`；边界红线（**Planner 不接触学校接口**、
     **Integration 不知道 Cookie / endpoint / 分页规则**）；**本轮零请求**；
    完整 2026-1 开课数据获取**属 Data Gate 之后的 Course Data MVP**。
  - **§12 Data Gate 通过条件 C1–C11**（含契约变更须走完 AGENTS 第 4 节流程、
    多 segment 表示方式确定且**未采用两个被禁方案**、暂缓字段确认、数据交接方式确认等）。
  - **§13 接口变更请求草案 DG-01 – DG-06**：每项严格按
    `【接口变更请求】当前设计 / 建议修改 / 原因 / 影响模块 / 是否为破坏性修改 /
     是否存在不修改接口的替代方案` 六段书写；**DG-01（多 segment）、DG-02（`CompletedCourse`）、
    DG-03（`CurrentEnrollment`）、DG-04（`CurriculumVersion` / `CurriculumCourse`）、
    DG-05（priority / dependency）、DG-06（`planner.md` 职责冲突修正）**。
    ⚠️ 每项都**如实列出"不改接口"的替代方案**（DG-02 / DG-04 的"留在 Curriculum 模块内部"
    是相当有力的方案；DG-03 的 `Preference.avoid_times[]` 是 MVP 降级方案；
    DG-05 的"优先级留在 Curriculum 内部"是最保守方案）。
  - **§14 本文件不做什么** / **§15 变更记录**。
- **更新 `docs/data/MEMBER_DATA_HANDOFF.md`**：删除过时的"目前没有任何真实数据可交接"；
  新增 **§2 当前数据清单**，明确三层：
  - **GitHub public 可直接共享**：D1–D5 Evidence 汇总（`SYSU_CASE_A_*` 与 `SYSU_COURSE_OFFERING_RECON`）、
    `DATA_SOURCE_REGISTRY.md`、`REAL_TO_SCHEMA_GAP_REPORT.md`、`DATA_GATE_DECISIONS.md`、`/mock_data/`；
    并加注"认证来源**外部访问者无法通过公开 URL 独立复核**"；
  - **负责人非公开按需交接**：D4 Sanitized Sample、后续 D5 normalized / sanitized sample
    （**需先完成 DG-01 裁决**）、培养方案结构化输出（若裁决不进公共契约）；
  - **禁止交接**：Raw transcript、Raw D5 response、password、Cookie、Session、Token、HAR、
    教师姓名、内部长 ID 取值、`readObj` 完整文本、他人数据。
  并**澄清「已有真实证据」≠「已向组员交付真实逐行数据」**；
  **§11 当前状态**如实写明：**已发生的真实数据交接 = 0**，**已交付 Curriculum / Planner 的真实数据 = 无**，
  **D4 Sanitized Sample 与 D5 normalized sample 交接次数均为 0**；
  后续章节顺延编号（原 §2–§10 → 新 §3–§11），正文内容未删改。
- **更新 `docs/status/agent_frontend.md`**：阶段图加入 `Data Gate-1 ← 本轮`；
  新增「Data Gate-1 本轮结果」小节（7 实体边界表 + DG-01–DG-06 表 + 暂缓字段 A/B/C/D）；
  「已完成」新增本轮条目；「当前阻塞」把 G9 改为"**已进入 Data Gate-1，但尚未裁决**"，
  新增"DG-01 – DG-06 全部待裁决""接口文档债务 DG-06""`prerequisites[]` 尚无真实证据"；
  「下一步」改为等待 Reviewer 验收 + 负责人逐项裁决（含建议裁决顺序，并注明**仅供参考、不构成本轮结论**）；
  标注本轮**零 SYSU 请求**。
- **小幅修改 `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`**（仅 2 处）：
  ① §4.5 末尾增加 **Data Gate-1 引用**（指向 `DATA_GATE_DECISIONS.md`，并明确
  "该文件同样没有修改任何 Schema / Interface，其结论需负责人逐项裁决；
  **本报告的缺口状态不因该文件而改变**"）；② §7 变更记录新增一行。
  **G1–G10 的状态与 A/B/C 映射结论一律不变。**
- 修改文件：
  - 新增 `docs/data/DATA_GATE_DECISIONS.md`
  - 更新 `docs/data/MEMBER_DATA_HANDOFF.md`
  - 更新 `docs/status/agent_frontend.md`
  - 小幅更新 `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`（仅 Data Gate 引用 + 变更记录）
  - 本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 公共接口是否变化：**否**（仅提交**草案**）｜ 是否修改 backend / frontend / mock_data：**否**
- **未做**：未修改 `/schemas/`、`/docs/interfaces/`、`AGENTS.md`、`backend/`、`frontend/`、`mock_data/`；
  未写 parser / crawler / Adapter / Normalizer / `CourseDataProvider` / Integration；
  未建数据库、未写 ORM / migration；**未调用 SYSU 接口（本轮零请求）**；
  **未裁决任何一项**；**未自行进入 Data Gate-2**
- 下一步：等待 Reviewer 验收 **Data Gate-1**，随后由**负责人逐项裁决 DG-01 – DG-06**，
  并按 `DATA_GATE_DECISIONS.md` §12 的 **C1 – C11** 判定是否通过 Data Gate。
  ⚠️ **裁决前不得实施任何变更**；**不 merge**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Data Gate-1 Reviewer 修复 + 架构裁决落档（docs-only）
- 本次目标：把 **Architecture Lead 的六项架构裁决**写回 Data Gate 文档，
  并修正 Reviewer 指出的 **3 处问题**。**不新建任务分支、不进入 Data Gate-2、
  不修改 Schema / Interface / 代码。**
- 起点：同一分支 `docs/data-gate-architecture`，head `c7556c81cded8ccc05b0b7182ba0629f031f66b9`。
- **一、六项裁决全部落档**（新增「架构裁决总表」+ 每项 DG 后附「裁决」块）：
  - **DG-01 = APPROVED WITH MODIFICATION**：采用 **`CourseOffering` 1 — N `Meeting`**
    （嵌套 segment 数组方案 A）；**Data Gate-2 正式修改 `course_offering.schema.json`**；
    **方案 B / C / D 不再作为待选方案**，改为**"已评估但驳回"**记录；
    meeting 的 MVP 排课字段 = `weekday` / `start_section` / `end_section` / `weeks[]` /
    `campus` / `classroom`；**教学班级 `teacher` MVP 暂保留**；
    明确这是**有意的 breaking contract migration**（"现在还没有真实联调，正是该修的时候；
    不能为了旧 Mock 保留一个错误的数据模型"）。新增 **§6.8 目标结构**（结构已锁定）。
  - **DG-02 = DEFER PUBLIC CONTRACT**：概念成立，**MVP 不新增** `completed_course.schema.json`；
    先作为 **Curriculum 内部规范化对象**；真实 D4 Sanitized Sample **可由负责人经非公开位置
    交给 Curriculum 成员**；Curriculum 对外**仍只输出 `MakeupTask[]`**。
  - **DG-03 = APPROVE CONCEPT, REUSE EXISTING CONTRACT**：**不新增** `CurrentEnrollment` Schema；
    Planner 的 **`current_schedule` 直接使用现有公共类型 `CourseOffering[]`**，
    语义 = **学生已选中的教学班子集**；必须在接口文档中与"学校全部供给"区分；
    ⛔ **不允许用 `Preference.avoid_times[]` 冒充当前课表**（原"降级替代方案"**被驳回**）。
  - **DG-04 = DEFER PUBLIC CONTRACT**：概念边界成立，**MVP 暂作为 Curriculum 内部模型**，
    **不新增两个公共 Schema**；同时明确 `Course.course_type` / `Course.recommended_semester`
    是**现有兼容字段**，**不能被解释为课程全局固有属性**；**跨学期区间**仍由
    **Curriculum 内部结构**保留，现有 `recommended_semester` 不能无损表示。
  - **DG-05 = NO NEW PUBLIC CONTRACT FOR MVP**：**不新增** `DependencyGraph`、
    **不新增** `priority` 字段、**不新增** `PriorityResult`。
  - **DG-06 = APPROVED**：下一阶段允许修正 `docs/interfaces/planner.md`，
    并根据需要同步 `docs/interfaces/curriculum.md`；**本轮仍然不改 interfaces**。
- **二、Reviewer 指出的 3 处问题已修正**：
  1. **教师证据判断错误已更正**：删除原 §6.4 的结论
     "**未观察到 segment 级教师字段，因此没有证据表明教师有 meeting-level 语义**" ——
     该说法**不成立**。真实 D5 的 `teachingTimePlaceStr` **本身就是按 segment 组织的、
     segment 项中包含教师信息**，且**已有样本表明 segment 与教师存在关联**。
     改为：**meeting-level teacher association = 已知的真实语义**；
     但**架构裁决为 Planner MVP 不依赖它**，因此**meeting 最小公共字段不纳入教师**，
     顶层 `teacher` 暂作教学班汇总保留，并登记为
     **known deferred representation gap（已知但暂缓的表达损失）**，
     **而不是"无证据"**。
  2. **DG-05 越界表述已改精确**（新增 **§7.3.1 权威边界**）：
     原文"依赖图的构建（闭包 / 拓扑序）属 Planner 内部实现"改为三段式 ——
     ```text
     Curriculum：负责认定 / 产出 authoritative dependency edges
     Planner：可以把已经收到的 prerequisites[] 转换成本地 adjacency / topological
              representation 供确定性求解使用
     Planner：不得新增、猜测、重写任何 prerequisite edge
     ```
     并补充：真实来源无法提供 prerequisite 时**标记未知 / 待人工确认，不得自动补齐**；
     无正式 priority 时 **Planner 不得自行生成 priority**。
  3. **通过条件计数已统一为 11 条**：`DATA_GATE_DECISIONS.md` 变更记录与
     `docs/status/agent_frontend.md` 中误写的"**12 条 Data Gate 通过条件**"
     更正为 **11 条（C1–C11）**。
     （注：`docs/worklogs/agent_frontend.md` 第 232 行的"登记 12 条中山大学公开官方来源"
     是**另一件事**（公开来源条数），**未改动**。）
- **三、文档结构同步更新**：
  - `DATA_GATE_DECISIONS.md`：文件状态由"草案（DRAFT）"改为
    "**Architecture Lead 已完成 DG-01 – DG-06 架构裁决；等待 Reviewer 最终复验；公共契约尚未实施**"；
    三条红线改为"契约实施统一在 Data Gate-2 / 不自行增删字段 / 未经授权不得提前实施"；
    **§9 最小接口变更集合重写** —— **进入 Data Gate-2 实施的只有 DG-01 与 DG-06 两项**，
    DG-02 / DG-03 / DG-04 / DG-05 列入"**不产生公共契约变更**"表；
    §3 / §4 / §8 各实体的"当前是否公共契约 / 处置"列补上裁决后形态；
    §5.2 私有数据表补"裁决后的公共表达"列；§7.2 / §7.4 补裁决结论；
    §10 新增 **10.2 裁决确认**；§11.4 更新（DG-01 已裁决）；**§12 增加逐条"当前状态"列**；
    §13 标题改为「接口变更请求**与裁决**」并保留原始请求文本以便追溯；§14、§15 同步。
  - `docs/status/agent_frontend.md`：阶段图加入 **Data Gate-1 ✅ 架构裁决落档** 与
    **Data Gate-2** 一环；实体边界表增"裁决后落地形态"列；DG 表重写为**裁决结果**；
    新增 3 处修复说明；「已完成」新增本轮条目；「当前阻塞」改写 G9 与 DG 状态，
    新增 **known deferred representation gap**；「下一步」改为等待 Reviewer 复验 →
    **Data Gate-2 实施 DG-01 / DG-06**。
  - `docs/data/MEMBER_DATA_HANDOFF.md`（**因 DG-02 / DG-03 / DG-04 / DG-05 直接影响而最小同步**）：
    §2.2 三行数据补裁决后的交付口径；§6.2 / §6.3 改为 **DG-05 已裁决**的准确边界
    （Planner 只能做本地 adjacency / topology，不得新增 / 猜测 / 重写 edge）；
    §11 当前状态更新。**明确新增一句**：
    **「裁决允许按需交付」≠「已经交付」** —— **逐行真实数据交接次数仍为 0**。
- 修改文件：
  - `docs/data/DATA_GATE_DECISIONS.md`
  - `docs/status/agent_frontend.md`
  - `docs/data/MEMBER_DATA_HANDOFF.md`（受裁决直接影响，最小修改）
  - 本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 公共接口是否变化：**否**（只是落档裁决，契约实施在 Data Gate-2）
- **未做**：未修改 `/schemas/`、`/docs/interfaces/`、`AGENTS.md`、`backend/`、`frontend/`、`mock_data/`；
  未写 parser / crawler / Adapter / Normalizer / `CourseDataProvider` / Integration；
  未建数据库；**未调用 SYSU 接口（本轮零请求）**；**未提前实施已裁决的变更**；
  **未自行进入 Data Gate-2**
- 备注：`REAL_TO_SCHEMA_GAP_REPORT.md` 中我**上一轮**加入的 Data Gate 引用仍写着
  "（**草案，未经批准**）"，现随裁决**已不准确**；但该文件**不在本轮允许修改范围内**，
  故**本次未改**，作为**待同步的文档一致性问题**上报，不自行扩大修改范围。
- 下一步：等待 Reviewer 最终复验。复验通过后由负责人决定是否发出 **Data Gate-2 任务书**
  （实施 DG-01 契约变更与 DG-06 接口文档修正，并同步 Mock / 后端自检 / 前端类型等连带范围）。
  ⚠️ **不 merge，不进入 Data Gate-2**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Data Gate-1 最终同步修复（docs-only）
- 本次目标：**只做最终文档同步**。架构内容已通过 Reviewer ——
  **不重新讨论 DG-01 – DG-06、不进入 Data Gate-2、不改代码与契约。**
- 起点：同一分支 `docs/data-gate-architecture`，head `7f4f9f43460715d50eaab36b7bde754fe823baf4`。
- **修复 1：School-shared 隐私措辞（`DATA_GATE_DECISIONS.md` §5.1）**
  - 问题：原文"来源为学校侧，**不含个人身份信息**，原则上可跨成员共享"**表述过强**；
  - 改为：**School-shared = "可在同一学校用户场景中复用的学校侧数据"**，
    **不代表天然不含人员信息，也不代表可以公开发布**；
  - 明确：`CourseOffering` 等数据**可能包含教师等人员信息**（真实 D5 的 `teachingName` 即为一例）；
    Real / Raw 数据仍须遵守**数据最小化、来源授权和非公开处理规则**；
    **"是否 School-shared" 与 "是否可以公开" 是两个独立问题**；
  - ⚠️ 特别写明：**不得把教师信息归成 Student-private** ——
    教师信息属**学校侧**数据，但**同样不得进入 public 仓库**。
- **修复 2：`REAL_TO_SCHEMA_GAP_REPORT.md` 的 Data Gate 状态（允许最小修改）**
  - §4.5 引用块与 §7 变更记录中上一轮加入的
    `DATA_GATE_DECISIONS.md`（**草案，未经批准**）
    → 改为语义「**Data Gate-1 架构裁决已完成；公共契约尚未实施，实施进入 Data Gate-2**」；
  - **只同步状态**：**G1–G10 的历史分析与 A/B/C 映射结论一字未改**；
    新增变更记录行说明"仅状态同步"。
- **同步 C2 / C3 / C9 / C10 / C11（Architecture Lead 已确认）**
  - **C2** ✅ 实体边界与所有者确认；
  - **C3** ✅ Shared / Private / Derived 分类确认（并指向 §5.1 的新措辞）；
  - **C9** ✅ Course Data 获取边界与合规方向确认 —— **新增 §11.3 完整记录**：
    - 目标：**2026-1 semester offering snapshot**；
    - 获取边界：用户本人正常登录 / 已有权限 / **用户明确触发授权导入** /
      ⛔ 不保存密码 · Cookie · Session · Token / ⛔ 不绕过认证 · CAPTCHA / ⛔ 不越权 /
      ⛔ **不在未确认请求规模前进行高频批量调用**；
    - 分工：Course Data = **获取·导入 → 解析 → 标准化 → 去重 → `source` / `data_source` → snapshot**；
      Integration = **只通过 `CourseDataProvider` 使用标准化结果**，
      **不知道 SYSU endpoint / Cookie / pagination**；
      Planner = **只消费标准化 `CourseOffering[]`**；
    - ⚠️ **"目标是一学期完整 Snapshot" ≠ "当前已取得完整数据"** ——
      当前实际只有 D5 小规模人工侦察（`CSE202` / `2026-1` → **2 个教学班**）；
    - ⚠️ 批量导入实现时**必须确认合理 `pageSize` / 请求规模**；
      若只能取得部分范围，**必须显式记录 completeness**，
      **不得把 partial snapshot 宣称为 complete**；
    - 原 §11.3 / §11.4 顺延为 §11.4 / §11.5。
  - **C10** ✅ 数据交接方式确认；**真实逐行数据交接次数 = 0（继续保留）**；
  - **C11** ✅ 已知未覆盖字段风险确认，逐项写明：
    ① `prerequisites[]` **暂无真实来源证据**；② `weekDay` 对应关系**待确认**；
    ③ `openingSchoolName → campus` **待确认**；④ **meeting-level teacher = known deferred
    representation gap**；⛔ **不允许实现层自行补齐**；
  - §12 进度更新为：**C1–C11 中 10 项已确认，仅 C5 待 Data Gate-2 执行**。
- 修改文件：
  - `docs/data/DATA_GATE_DECISIONS.md`（§5.1 措辞、新增 §11.3、§11.4/§11.5 顺延、§12 状态、§15 变更记录）
  - `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`（**仅** §4.5 引用块 + §7 变更记录的状态同步）
  - `docs/status/agent_frontend.md`（表头裁决状态、新增「Data Gate-1 最终同步」小节、
    「已完成」「下一步」同步）
  - `docs/data/MEMBER_DATA_HANDOFF.md`（**仅**因 C10 状态同步而最小修改：§11 标记 C10 已确认、
    重申交接次数 0）
  - 本文件（**仅追加**）
- 测试：docs-only，未改动任何代码，未复跑前后端
- 公共接口是否变化：**否**
- **未做**：未修改 `/schemas/`、`/docs/interfaces/`、`AGENTS.md`、`backend/`、`frontend/`、`mock_data/`；
  未写 parser / crawler / Adapter / Normalizer / `CourseDataProvider` / Integration；
  未建数据库；**未调用 SYSU 接口（本轮零请求）**；**未重新讨论任何 DG 裁决**；
  **未进入 Data Gate-2**
- 遗留已清零：上一轮上报的 `REAL_TO_SCHEMA_GAP_REPORT.md` 中"（草案，未经批准）"
  **已在本轮按授权同步修正**。
- 下一步：等待 Reviewer 收尾确认。之后由负责人决定是否发出 **Data Gate-2 任务书**
  （实施 DG-01 契约变更与 DG-06 接口文档修正，即完成 **C5**）。
  ⚠️ **不 merge，不进入 Data Gate-2**，Phase 2B Integration 保持暂停编码。

---

### 2026-09-30 - Data Gate-2：公共契约实施（DG-01 breaking migration + DG-06 接口文档）
- 本次目标：实施两项**已裁决**的契约变更 —— **DG-01**（`CourseOffering` → `meetings[]`）
  与 **DG-06**（Curriculum / Planner 接口职责修正）；**不重新讨论架构选型**。
  这是本项目**第一次真正修改公共契约**。
- 起点：`main` = `70c81050209808e534fe47114340d5328ce0fbf4`（Data Gate-1 已由 PR #10 合入）；
  **未继续使用旧分支 `docs/data-gate-architecture`**；新建
  `refactor/data-gate-2-course-offering-meetings`。
- **DG-01 实施（`CourseOffering` 1 — N `Meeting`）**
  - `schemas/course_offering.schema.json`：
    - 顶层**删除** `weekday` / `start_section` / `end_section` / `weeks` / `campus` / `classroom`
      （**彻底移除，不留兼容字段**）；
    - 顶层 `required` 改为 `course_id` / `course_name` / `class_id` / `semester` / **`meetings`**；
    - 新增 `meetings`：`type: array`，`minItems: 1`；
    - `Meeting`：`additionalProperties: false`，必填
      `weekday`(integer 1–7) / `start_section`(integer ≥1) / `end_section`(integer ≥1) /
      `weeks`(integer[]，item ≥1，`minItems: 1`，`uniqueItems: true`)，
      可选 `campus`(string|null) / `classroom`(string|null)；
    - **未新增任何暂缓字段**：`selectedNumber` / `openingUnitName` / `courseCategoryName` /
      `examMode` / `readObj` / `teachProgressSubmitState` / `openClass` 一律未加入；
      **`Meeting` 不含 `teacher`**。
  - `backend/app/models/contracts.py`：
    - 新增 `Meeting` 模型（与 Schema 等价）；`CourseOffering.meetings: list[Meeting]`（至少 1 项）；
      删除顶层六个排课字段；`__all__` 加入 `"Meeting"`；
    - `PositiveIntList` 的注释由 `CourseOffering.weeks` 改为 `Meeting.weeks`；
    - `weeks` 的 `uniqueItems` 仍由 `_reject_duplicates` 在**运行时真实拒绝**重复项
      （Pydantic 不生成该关键字，这一点未因迁移而放松）。
  - `mock_data/course_offerings.json`：**9 个教学班全部迁移**到 `meetings[]`；
    `6200100220260101`（数据结构与算法，**被方案选中的教学班**）拥有 **2 段 meeting**
    （周三 3-4 节 1-16 周 + **人工构造**的周一 5-6 节单周实验段，避开 prefered `avoid_times` 的周五 5-8 节）；
    **未复制任何真实 SYSU Response 或真实教师信息**（Mock 仍为人工虚构）。
  - 后端测试迁移并**加严**：
    - `test_contracts.py`：`VALID_MEETING` + `_meeting()` 工厂；所有 weekday / weeks /
      section 校验迁到 `Meeting`，**并同时验证嵌套位置**（放进 `meetings[]` 里也必须被拒）；
      新增 **多 meetings 通过**、**`meetings: []` 拒绝**、**缺少 `meetings` 拒绝**、
      **`Meeting` 额外字段（含 `teacher`）拒绝**、**旧格式顶层排课字段拒绝**
      （含"旧字段与 meetings 同时出现"）；
      新增 `test_nested_meeting_weeks_unique_items_are_enforced_at_runtime`：
      按公共 Schema 路径 `properties.meetings.items.properties.weeks` 确认 `uniqueItems: true`
      并断言模型真实拒绝 —— 因为顶层 uniqueItems 扫描**会漏掉这个嵌套数组**。
    - `test_mock_data_schema.py`：新增 `_meetings_of()` 辅助；**所有**时间 / 地点 / 周次 / 节次检查
      改为**逐 meeting 遍历**（`test_plan_result_avoids_preferred_avoid_times`
      现在检查选中教学班的**每一个** meeting，不再只看第一段）；
      新增 **至少 1 个教学班含 ≥2 个 meeting**、**Mock 无旧顶层排课字段残留**、
      **旧格式在数据层被拒**；两个 raw-schema 回归测试改到 `meetings[0].weekday` /
      `meetings[0].weeks`，**"先 JSON Schema 后 Pydantic"的顺序未被破坏**。
  - 前端：
    - `types/contracts.ts` 新增 `Meeting`，`CourseOffering` 改为 `meetings: Meeting[]`，
      删除旧顶层六个字段；**未新增 Schema 不存在的类型字段**；
    - `CourseOfferingList.vue`：原"上课时间 / 节次 / 周次 / 校区教室"四列**收敛为"上课安排"一列**，
      **逐段**渲染（`v-for="meeting in offering.meetings"`）；**不做**冲突判断、优劣排序、
      自动选择、合并 / 删除任何一段；
    - `utils/labels.ts` 新增**纯展示**函数 `formatMeetingLine(meeting)`；
    - `styles/base.css` 新增 `.meeting-list` / `.meeting`（多段之间虚线分隔）。
  - `backend/README.md` 手动验收第 7 步由"改某个 `weekday`"改为"改某个 `meetings[0].weekday`"
    （否则该步骤在新结构下失效）。
- **DG-06 实施（接口职责修正）**
  - `docs/interfaces/planner.md`：职责改为冲突检测 / 当前课表冲突分析 / 替代教学班搜索 /
    硬软约束建模 / 确定性约束求解 / Path Repair / 无解与部分可行 / `PlanResult`；
    **不负责**依赖认定 / 风险 / 优先级 / Curriculum Diff；
    **删除** `build_dependency_graph(courses)` 与 `calculate_priority(...)`；
    明确 `current_schedule: CourseOffering[]` 的语义并写明
    **"学校全部 CourseOffering[] ≠ current_schedule"**、**禁止用 `Preference.avoid_times[]` 冒充当前课表**；
    写明依赖权威边界（Curriculum 认定 edges；Planner 只做本地 adjacency / topology；
    不得新增 / 猜测 / 重写 edge；无法提供时标记未知，不自动补齐）；
    写明 **MVP 无公共 `priority` 字段，Planner 不得自行生成优先级**；
    实现约束补上**冲突检测必须遍历 `meetings[]` 的每一段**。
  - `docs/interfaces/curriculum.md`：补上**课程依赖认定**、**补修风险 / 学业优先级的所有权**、
    **跨学期补修路径建议**；明确**优先级当前没有公共契约**、
    **不得假装当前已可跨模块传 priority**；交付说明写明先修边的权威来源与"不得自动补齐"；
    并保留"真实样本中未发现先修字段"的证据限制。
- **Data Gate 收口**
  - `docs/data/DATA_GATE_DECISIONS.md`：文件状态改为 **Data Gate PASSED / CLOSED**；
    裁决总表加"实施状态"列；§1.3 流程图补 Data Gate-2；§6.7 / §6.8 / §9.1 标注已实施；
    §12 中 **C4 / C5 / C6 / C7 / C8 更新为已完成**，新增 §12.2 结论（C1–C11 全 ✅）；
    §12.1 改为"Gate 关闭后仍然适用的约束"；新增 **§16 Data Gate 关闭记录**
    （实施内容 / 同步范围 / 验证结果 / 本轮未做）。
  - `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`：**G9 更新为"已通过 DG-01 / Data Gate-2 完成公共契约修复"**，
    **原缺口描述原样保留**；新增 **§4.6** 记录修复形态、同步范围、表达损失与"未新增的字段"；
    §3.2 区分"Data Gate-1 当时的字段"与"Data Gate-2 之后的字段"，历史分析表**未删改**；
    §3.2 表下的 `teachingTimePlaceStr` 两层说明补注"该限制已解除"；变更记录追加一行。
  - `docs/status/agent_frontend.md`：阶段图改为"Data Gate 已关闭 → 下一步 Course Data MVP"；
    新增「Data Gate-2 实施结果」小节；「已完成」/「当前接口」/「当前阻塞」/「下一步」全面同步
    （G9 与 DG 状态改写为已完成，`CourseOffering[]` 注明含 `meetings[]`）。
- 修改文件：
  - `schemas/course_offering.schema.json`
  - `backend/app/models/contracts.py`、`backend/tests/test_contracts.py`、
    `backend/tests/test_mock_data_schema.py`、`backend/README.md`
  - `mock_data/course_offerings.json`
  - `frontend/src/types/contracts.ts`、`frontend/src/components/CourseOfferingList.vue`、
    `frontend/src/utils/labels.ts`、`frontend/src/styles/base.css`
  - `docs/interfaces/planner.md`、`docs/interfaces/curriculum.md`
  - `docs/data/DATA_GATE_DECISIONS.md`、`docs/data/REAL_TO_SCHEMA_GAP_REPORT.md`
  - `docs/status/agent_frontend.md`、本文件（仅追加）
- 测试：
  - `cd backend && python -m pytest` → **133 passed / 2 skipped**（全部通过；迁移前为 125 passed / 1 skipped）
  - `cd frontend && npm run build`（含 `vue-tsc --noEmit`）→ **成功**
  - **未删除任何测试、未新增 skip、未放宽任何校验**；两处 skip 仍是
    "该 Schema 顶层没有 uniqueItems 数组"的原语义，且原先被跳过的 CourseOffering
    改由 `test_nested_meeting_weeks_unique_items_are_enforced_at_runtime` **专项覆盖**。
- 公共接口是否变化：**是（本轮首次真实变更公共契约）**
  - `course_offering.schema.json`：**breaking migration**（顶层删 6 字段 + 新增 `meetings[]`）；
  - `docs/interfaces/planner.md` / `curriculum.md`：**文档修正**（无字段变更）；
  - 其余四个 Schema **未变**。
- 未执行：**未调用 SYSU API（零请求）**、**未抓取 6892 条课程**、未写 crawler、
  未写 Course Data Adapter / Normalizer / `CourseDataProvider`、**未进入 Integration / Orchestrator**、
  **未建数据库 / ORM / migration**、未写 Curriculum 算法或 Planner 求解器、
  未新增 `CompletedCourse` / `CurrentEnrollment` / `CurriculumVersion` / `CurriculumCourse` /
  `DependencyGraph` / `priority`。
- 备注（留给后续，不在本轮授权范围内）：`docs/interfaces/course_data.md` 的"关键标准"一节
  仍按旧结构罗列 `weekday` / `start_section` / `end_section` / `weeks`（语义仍成立，
  但未说明它们现在位于 `meetings[]` 内）；该文件**本轮未获授权修改**，故**未改**，
  作为**待同步的接口文档一致性问题**上报，不自行扩大修改范围。
- 下一步：等待 Reviewer 验收 **Data Gate-2**（本轮是真实契约变更，请重点复核
  breaking migration 完整性与"未偷偷新增暂缓字段"）。
  Data Gate 已关闭；下一步 **Course Data MVP**（真实 2026-1 snapshot）**须等新一轮任务书**。
  ⚠️ **不 merge，不自行开始 Course Data MVP**。

---

### 2026-09-30 - Data Gate-2 Reviewer 最终一致性修复（`course_data.md` 同步，docs-only）
- 本次目标：修掉 Reviewer 指出的**唯一 blocker** ——
  `docs/interfaces/course_data.md` **没有同步** `CourseOffering → meetings[]` 的 breaking migration。
  **不重新修改 DG-01 实现**（Schema / Backend / Mock / Frontend / Planner / Curriculum 均已通过 Reviewer），
  **不开始 Course Data MVP**。
- 起点：同一分支 `refactor/data-gate-2-course-offering-meetings`，
  head `f945004f65f08c46ff0bad536f2ed4379bb0efaa`。
- **修改 `docs/interfaces/course_data.md`**：
  - **保留原职责链**：授权读取 → 清洗 → 时间 / 周次 / 校区标准化 → 去重 / 同步 → 输出 `CourseOffering[]`；
  - 文件开头加注：Data Gate-2（DG-01）已把契约从"一个 `CourseOffering` = 一个时间段"
    改为 **`CourseOffering` 1 — N `Meeting`**；
  - **新增"公共结构"说明**：
    `CourseOffering` = 一个教学班；`CourseOffering.meetings[]` = 该教学班**全部**上课时间 / 地点段；
  - 在 `normalize_offering(raw) -> CourseOffering` **附近**明确：
    **Normalizer 必须聚合同一教学班的所有 meeting，不能只解析第一个 segment**，
    并说明理由（只取第一段会让下游冲突检测产生**假阴性**，输出**不可执行方案**）；
  - **"关键标准"重写**为至少包含：
    ① 一个 `CourseOffering` 表示一个教学班、不表示一个时间段；
    ② `meetings` 必须至少包含 1 个 `Meeting`；
    ③ 每个真实教学班的**所有** schedule segment 都必须进入 `meetings[]`；
    ④ ⛔ 不得只保留第一段；
    ⑤ ⛔ 不得把同一教学班的多个 segment 拆成多个可独立选择的 `CourseOffering`；
    ⑥ `meetings[].weekday`：1=周一 … 7=周日；
    ⑦ `meetings[].start_section` / `end_section`：整数节次；
    ⑧ `meetings[].weeks`：展开为实际周次数组；
    ⑨ `meetings[].campus` / `classroom`：该时间段对应地点；
    ⑩ `data_source`：必须明确 mock / real；
  - **保留 Data Gate 已确认的 deferred gap**：meeting 级教师关联**已知存在**
    （`teachingTimePlaceStr` 的 segment 项本身含教师信息），
    但**当前公共 `Meeting` 不表达**；`teacher` 暂为 `CourseOffering` **顶层汇总 / 展示字段**；
    并写明这**不是"该语义不存在"**，本模块**不得**自行加字段，后续须走 `【接口变更请求】`；
  - **安全边界原样保留**：正常登录 / 已授权范围 / 不保存密码 / 不绕过认证与 CAPTCHA /
    不越权 / 不提交 Cookie·Session·Token；并补一句"批量导入须先确认 `pageSize` 与请求规模，
    只能取得部分范围时必须显式记录 completeness，不得宣称 complete"（与 C9 一致）；
  - **未新增任何 Schema 字段**，**未添加任何真实 SYSU 请求代码**。
- **最小同步 `docs/status/agent_frontend.md`**（仅两处）：
  ① Data Gate-2 结果的 DG-06 条目补上"并同步 `docs/interfaces/course_data.md`"；
  ② "接口文档债务"一行补记 `course_data.md` 已同步。
- 修改文件：
  - `docs/interfaces/course_data.md`
  - `docs/status/agent_frontend.md`（**最小**，仅上述两处状态句）
  - 本文件（**仅追加**）
- 测试（按要求确认未误改代码）：
  - `cd backend && python -m pytest` → **133 passed / 2 skipped**（全部通过）
  - `cd frontend && npm run build`（含 `vue-tsc --noEmit`）→ **成功**
  - 本轮**未改动任何代码**，以上仅为回归确认。
- 公共接口是否变化：**否**（本轮只同步**接口文档描述**，未改任何 Schema 字段 / API 路径）
- 未执行：**未调用 SYSU API（零请求）**、未写 crawler、未写 Course Data Adapter / Normalizer /
  `CourseDataProvider`、未进入 Integration、未建数据库；
  **未重新修改 DG-01 实现**（`schemas/` / `backend/` / `frontend/` / `mock_data/` /
  `planner.md` / `curriculum.md` 一律未再动）；**未开始 Course Data MVP**。
- 上一轮上报的遗留已清零：`docs/interfaces/course_data.md` 的旧结构描述**已按本轮授权同步**，
  当前**无已知的接口文档一致性问题**。
- 下一步：等待 Reviewer 复验。Data Gate 已关闭；下一步 **Course Data MVP**
  （真实 2026-1 semester offering snapshot）**须等新一轮任务书**。
  ⚠️ **不 merge，不自行开始 Course Data MVP**。

---

### 2026-09-30 - Phase 2B-1：Integration / Provider Skeleton
- 本次目标：建立 Curriculum / Course Data / Planner 与 Integration 之间
  **最小、稳定、可测试的 Python Provider 边界** —— "只做插座"：
  **不接真实 SYSU 数据、不实现业务算法、不新增用户可见功能、不新增 API**。
- 起点：`main` = `6e5d330cba31be545ebf67decb01dfebd3c5d788`（Data Gate-2 已合入）；
  新建 `feature/integration-provider-skeleton`。
  （注：首次 `git pull` 直连失败 —— `Failed to connect to github.com:443`；
  按既有约定用 `git -c http.proxy=http://127.0.0.1:7890 pull` 成功，未改全局 git 配置。）
- **新增 `backend/app/integration/`**（不塞进 `mock_service.py` / `main.py`）
  - `__init__.py`：包说明 + 只导出三个 Protocol 与 `PlanningOrchestrator`；
    明确写着"本包**不会**在真实 Provider 缺失时回退到 Mock 通道"。
  - `ports.py`：三个 `typing.Protocol`（`@runtime_checkable`，便于测试断言结构满足）——
    - `CurriculumProvider.get_makeup_tasks() -> list[MakeupTask]`
      （Integration **不知道**培养方案文件 / `CompletedCourse` 内部结构 /
      `CurriculumVersion` / `CurriculumCourse` / 课程匹配实现）；
    - `CourseDataProvider.get_course_offerings(semester: str) -> list[CourseOffering]`
      （Integration **绝不能**知道 `jwxt.sysu.edu.cn` / POST endpoint / `pageNo` / `pageSize` /
      Cookie / Session / `teachingTimePlaceStr` / `class_ID` / `courseNumber`）；
    - `PlannerProvider.plan(*, makeup_tasks, offerings, current_schedule, preference) -> PlanResult`
      （**不接收** `priority` / `dependency_graph` / `risk_scores`）。
  - `orchestrator.py`：`@dataclass(frozen=True) PlanningOrchestrator`，
    **只持有**三个 Provider；`build_plan(*, semester, current_schedule, preference)` 内部严格是
    `get_makeup_tasks()` → `get_course_offerings(semester)` → `plan(...)` → **原样 `return`**。
    **没有任何业务判断**：无 `if`、无 `sort`、无筛选、无派生计算、无 fallback。
- **新增 `backend/tests/test_integration_orchestrator.py`**（14 个测试，**全部用 test-only Fake / Spy Provider**）：
  ① 正常流程 + **返回对象就是 Planner 给出的那一个**（`is` 同一性）；
  ② 调用顺序固定 `curriculum → course_data → planner`；
  ③ `semester` 原样传递（含"故意带空格/不规整"的输入，确认 Integration 不做规整）；
  ④ **四个入参按对象身份透明传递**（`makeup_tasks` / `offerings` / `current_schedule` /
  `preference` 均为 `is` 断言 + 顺序断言）；
  ⑤ 空 `current_schedule` 合法下传（不自行报错）；
  ⑥ 空 `offerings` 原样交给 Planner，**`infeasible` 由 Planner 决定**；
  ⑦ Course Data / Planner 抛异常时**原样向上抛**，且 Course Data 失败时 **Planner 不被调用**
  （证明没有 fallback 路径）；
  ⑧ Protocol 结构满足（`isinstance` + `runtime_checkable`）；
  ⑨ `PlannerProvider.plan` 的**参数集合被锁定**为四个（防私加 `priority` 等）；
  ⑩ Orchestrator 的 dataclass 字段**只有三个 Provider**；
  ⑪ **Integration 层不得引用 Mock 通道**：用 **AST** 检查 import 与函数调用
  （而不是查源码文本 —— 文档里说明"不会回退到 mock_service"是允许的，被禁的是真的导入 / 调用它）；
  ⑫ **未新增 API**：断言 OpenAPI `paths` 与 Phase 1 完全一致，且不含 `/plan` / `/integration`。
- **新增 `docs/interfaces/integration.md`**（8 节：职责 / 三个 Provider / 调用顺序 /
  `current_schedule` 语义 / dependency-priority 边界 / 错误处理原则 / Mock 与 Real 不自动 fallback /
  当前尚未开放真实 API）。明确声明这是**既有公共对象之间的编排说明，不是新增 Schema**。
- **最小修正 `docs/ARCHITECTURE.md`**（DG-05 旧口径）：
  - 删除"Planner 实际消费的是补修任务**加上**课程依赖结果与已确认优先级"的表述；
  - 改为：**MVP 当前跨模块只传 `MakeupTask[]`**，prerequisite 由
    `MakeupTask.prerequisites[]` 承载（Planner 只做本地 adjacency / topology 转换，
    不得新增 / 猜测 / 重写先修边）；
  - 明确 **`priority` 当前没有公共契约**，在正式接口变更前
    **不得声称 Integration / Planner 已经消费跨模块 priority**；
  - 补一句指向 `docs/interfaces/integration.md`。未重写整个 ARCHITECTURE。
- **本轮明确未做**：
  - ❌ **未创建任何生产 Mock Provider**（`MockCurriculumProvider` / `MockCourseDataProvider` /
    `MockPlannerProvider` 均不存在）—— 避免造成"完整 Integration 已跑通"的错觉；
  - ❌ **未新增 API**：`backend/app/main.py` **未修改**，`POST /plan` / `POST /integration` /
    `GET /real/...` 均未添加；
  - ❌ **未新增跨模块 DTO**：没有 `StudentProfile` / `IntegrationRequest` / `PlanningContext` /
    `DependencyGraph` / `CourseDataSnapshot` —— 现有稳定对象已足够；
  - ❌ 未改 `schemas/`、未改现有公共字段、未改 `mock_data/`、
    未改 `mock_service.py`（仍 **permanent Mock-only**）、未改 `/api/v1/mock/*`；
  - ❌ 未接 SYSU、未写 crawler / browser extension / Adapter / Normalizer、未做真实 semester snapshot、
    未建数据库 / ORM / migration；
  - ❌ 未写 Curriculum 算法 / Planner 冲突算法 / OR-Tools / Path Repair；
    未接 LLM / Tool Calling / Preference 自然语言解析。
- 修改文件：
  - 新增 `backend/app/integration/__init__.py`、`backend/app/integration/ports.py`、
    `backend/app/integration/orchestrator.py`
  - 新增 `backend/tests/test_integration_orchestrator.py`
  - 新增 `docs/interfaces/integration.md`
  - 修改 `docs/ARCHITECTURE.md`（仅 DG-05 两处口径）
  - 修改 `docs/status/agent_frontend.md`、本文件（仅追加）
  - **前端本轮无代码改动**，按要求未跑 `npm run build`。
- 测试：`cd backend && python -m pytest` → **147 passed / 2 skipped**
  （迁移前 133 passed / 2 skipped，**新增 14 个 Integration 测试全部通过**；
  原测试**全部继续通过**，**未删除任何旧测试、未新增 skip、未放宽 Schema**）。
- 公共接口是否变化：**否**（未改 Schema / 未新增 endpoint；`docs/interfaces/integration.md` 只是编排说明）
- 当前能做什么：三块上游只要各自给出符合 Protocol 的实现（**测试内已用 Fake 验证**），
  `PlanningOrchestrator.build_plan()` 就能把 `MakeupTask[]` + `CourseOffering[]` +
  `current_schedule` + `Preference` 串给 Planner 并原样返回 `PlanResult`。
- 当前不能做什么：**没有任何真实链路** —— production Curriculum / Course Data / Planner provider
  三件都未接入；**没有对外 API**；前端仍只能读 Mock 通道。
- 下一步：等待 Reviewer 验收 **Phase 2B-1**。之后是 **Phase 2B-2 Course Data MVP**
  （真实 2026-1 semester offering snapshot，实现 `CourseDataProvider`），
  **须等新一轮任务书**。⚠️ **不 merge，不自行开始 Phase 2B-2**。

---

### 2026-09-30 - Phase 2B-1 Reviewer 治理口径修复（Integration 接口的契约地位，docs-only）
- 本次目标：修掉 Reviewer 指出的**唯一 blocker** ——
  Integration Provider 接口被**错误描述为"不是公共契约"**。
- **治理口径的准确区分**（`/AGENTS.md` 第 4 节把 `/schemas/` 与 `/docs/interfaces/` **一并**列为公共契约）：
  - ✅ **没有新增公共业务 Schema**（未改 `/schemas/`、未改现有公共数据结构）；
  - ✅ **但新增了受保护的 Integration 公共接口边界** ——
    `docs/interfaces/integration.md` 位于 `/docs/interfaces/`，
    与 `ports.py` / `orchestrator.py` 的四个调用签名**同属公共跨模块接口**。
  - 后续模块**不得自行修改** Provider 方法名、参数语义或返回类型；
    变更仍须按 `/AGENTS.md` 第 4 节提交 `【接口变更请求】` 并经负责人确认。
- **具体修改**：
  1. `docs/interfaces/integration.md`
     - 文件开头：删除"**不是一个新 Schema**"这一会误导为"非公共契约"的表述，
       改为"本文件**不新增业务对象 Schema**，也不修改 `/schemas/` 中的公共数据结构；
       但本文件位于 `/docs/interfaces/`，因此其中定义的 **Provider 调用边界属于项目的公共跨模块接口**"，
       并写明"后续模块不得自行修改 Provider 方法名 / 参数语义 / 返回类型；变更须走 `【接口变更请求】`"；
     - §1 注释：把"这些**不是**新的公共契约，只是……的声明"改为
       "这些不是**新的业务对象 Schema**，但它们是**已确认的 Integration 公共接口边界**"；
     - **新增 §3.1「接口冻结（Phase 2B-1 已确认）」**：逐一列出
       `CurriculumProvider.get_makeup_tasks()`、`CourseDataProvider.get_course_offerings(semester)`、
       `PlannerProvider.plan(*, ...)`、`PlanningOrchestrator.build_plan(*, ...)` 四个**已确认签名**，
       明确它们是代码侧的事实接口、**不得私自修改**，并重申
       `PlannerProvider.plan()` 参数集合**恰为四个**（不得私加 `priority` / `dependency_graph` / `risk_scores`）。
  2. `backend/app/integration/ports.py`（**仅 docstring**）
     - 删除"这里的 Protocol **不是新的公共契约**"；
     - 改为"这些 Protocol 是 `docs/interfaces/integration.md` 的**代码侧映射**：
       不新增业务字段或 Schema，但其**跨模块调用签名属于已确认的 Integration 公共接口边界**，
       **不得由实现模块私自修改**"。
  3. `backend/app/integration/__init__.py`
     - **已逐句检查，不存在同类"非公共接口"的错误表述，因此未修改**（按任务要求"没有则不改"）。
  4. `docs/status/agent_frontend.md`
     - 把"**未新增任何跨模块 Schema / DTO**"改为
       "**未新增公共业务 Schema / 跨模块 DTO**……但**新增了 Integration Provider 公共接口边界**"
       （Phase 2B-1 结果与「已完成」两处）；
     - 「当前接口」的 Integration 条目补注：这四个调用签名是**已确认的 Integration 公共接口边界**，
       不得由实现模块私自修改。
- **更正上一轮记录中的口径**：上一轮本文件写的
  "公共接口是否变化：**否**（……`docs/interfaces/integration.md` 只是编排说明）"
  **应记为「是」** —— 该轮**未新增业务 Schema，但新增了受保护的 Integration 公共接口边界**。
  （按 worklog 仅追加的约定，旧行保留，以本条更正为准。）
- **未修改（严格守住 Reviewer 的禁止项）**：
  - ❌ Provider 方法签名（`get_makeup_tasks` / `get_course_offerings` / `plan` 一字未动）；
  - ❌ `orchestrator.py` 的行为（本轮**未打开该文件的逻辑**）；
  - ❌ 测试逻辑（未新增测试、未改断言）；
  - ❌ `schemas/`、`mock_data/`、`main.py`、现有 API。
- 修改文件：
  - `docs/interfaces/integration.md`
  - `backend/app/integration/ports.py`（**仅 docstring**）
  - `docs/status/agent_frontend.md`
  - 本文件（**仅追加**）
- 测试：本轮为文档 / 注释治理修复，**不需要新增测试**；按要求快速复跑
  `cd backend && python -m pytest` → **147 passed / 2 skipped**（全部通过）。
- 公共接口是否变化：**否**（未改任何方法签名 / 未改 Schema / 未新增 API）；
  本轮只**修正对既有接口契约地位的描述**。
- 下一步：等待 Reviewer 复验。⚠️ **不 merge，不自行开始 Phase 2B-2 Course Data MVP**。

---

### 2026-09-30 - Phase 2B-2A：Course Data Normalization Core（阶段同步）
- 本次目标：进入 **Course Data** 侧的 **Normalization Core**（已在 `docs/worklogs/course_data.md`
  留下本轮主记录）。对 Agent / Frontend 来说本轮是**阶段同步**，无行为改动。
- 起点：`main` = `aff6438c400731dd94e66a3d884ee45c774c4051`；
  分支 `feature/course-data-normalization-core`。
- 新增（Course Data 内部包，**不是跨模块公共契约**）：
  `backend/app/course_data/{__init__,errors,normalization,snapshot}.py`；
  新增测试 `backend/tests/test_course_data_{normalization,snapshot}.py`（90 个）。
- 关键边界（对 Integration 侧的意义）：
  - `SnapshotCourseDataProvider` **结构上满足** Phase 2B-1 冻结的 `CourseDataProvider`
    （`get_course_offerings(semester) -> list[CourseOffering]`），**不继承、不修改** Protocol；
  - 学期匹配返回该学期教学班，否则返回 `[]`；**零网络、无 Mock fallback**；
  - **Integration / Orchestrator / `ports.py` / `orchestrator.py` 一律未修改**；
  - **前端未改动**（本轮无前端相关接口变化），未跑 `npm run build`。
- 阶段影响：阶段图由"Phase 2B-1 完成"推进为"**Phase 2B-2A 完成**"，
  下一步为 **Phase 2B-2B**（真实 `teachingTimePlaceStr` parser / 授权 import adapter /
  完整 2026-1 snapshot），**须等新任务书**。
- 修改文件（本模块视角）：
  - `docs/status/agent_frontend.md`（最小阶段同步：表头、阶段图、新增 Phase 2B-2A 结果小节、
    「当前阻塞」「下一步」）
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **237 passed / 2 skipped**
  （本轮前 147 passed / 2 skipped；原测试全部继续通过，未删除旧测试、未新增 skip）。
- 公共接口是否变化：**否**（未改 `schemas/` / `docs/interfaces/` / Integration 签名 / API）
- 下一步：等待 Reviewer 验收 **Phase 2B-2A**。⚠️ **不 merge，不自行进入 2B-2B**。

---

### 2026-09-30 - Phase 2B-2B：Schedule Parser + Local Import Adapter（阶段同步）
- 本次目标：进入 **Course Data** 的 **Schedule Parser + 本地 import adapter**
  （主记录见 `docs/worklogs/course_data.md`）。对 Agent / Frontend 来说本轮是**阶段同步**，无行为改动。
- 起点：`main` = `266b11908ae47131e686a395f709dd4c46a60c5c`；
  分支 `feature/course-data-schedule-import-core`。
- 新增（Course Data 内部包，**不是跨模块公共契约**）：
  `backend/app/course_data/{schedule_parser,importer}.py`；
  修改 `normalization.py`（周次按新证据扩到 `N-M周`）与 `__init__.py`；
  新增测试 `backend/tests/test_course_data_{schedule_parser,importer}.py`。
- 关键边界（对 Integration / 前端侧的意义）：
  - **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/ports.py`、`orchestrator.py`、
    `main.py`、`api/` **一律未修改**；`CourseDataProvider` 签名保持冻结；
  - **零网络**：未发起任何 SYSU 请求；未写 fetch client / Cookie / Session / Token / 分页逻辑；
    `test_course_data_snapshot.py` 的**包边界检查会自动覆盖新增模块**；
  - **前端未改动**（本轮无前端相关接口变化），未跑 `npm run build`。
- 隐私：私密脱敏样本只在**本地**阅读，**未进入 Git**；测试全部使用人工虚构样本。
- 阶段影响：阶段图由"Phase 2B-2A 完成"推进为"**Phase 2B-2B 完成**"，
  下一步为 **Phase 2B-2C 真实受控获取**（登录 / 分页 / 请求规模确认），**须等新任务书**。
- 修改文件（本模块视角）：
  - `docs/status/agent_frontend.md`（最小阶段同步：表头、阶段图、新增 Phase 2B-2B 结果小节、
    「当前阻塞」「下一步」）
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **355 passed / 2 skipped**
  （本轮前 246 passed / 2 skipped；旧测试全部继续通过，未删除旧测试、未新增 skip）。
- 公共接口是否变化：**否**（未改 Schema / Interface / Integration 签名 / API）
- 下一步：等待 Reviewer 验收 **Phase 2B-2B**。⚠️ **不 merge，不自行进入 2B-2C**。

---

### 2026-09-30 - Phase 2B-2C0：Course Data Pagination Core（阶段同步）
- 本次目标：进入 **Course Data** 的**零网络分页采集核心**
  （主记录见 `docs/worklogs/course_data.md`）。对 Agent / Frontend 来说本轮是**阶段同步**，无行为改动。
- 起点：`main` = `6485dd15491a1f971927f853ffb032f3f8e71c4b`；
  分支 `feature/course-data-pagination-core`。
- 新增（Course Data 内部实现 / 内部接口，**不是跨模块公共契约**）：
  `backend/app/course_data/pagination.py`（`OpeningCoursesPageFetcher` +
  `collect_opening_courses_snapshot`）；修改 `__init__.py` 最小导出；
  新增 `backend/tests/test_course_data_pagination.py`（54 个测试）。
- 关键边界（对 Integration / 前端侧的意义）：
  - **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/ports.py`、`orchestrator.py`、
    `main.py`、`api/` **一律未修改**；`CourseDataProvider` 签名保持冻结；
  - **零网络**：`fetch_page` 由调用方提供（本轮只由测试 Fake 提供）；
    未发起任何 SYSU 请求；未写 fetch client / Cookie / Session / Token；
  - **`SnapshotCourseDataProvider` 未修改**；`partial` snapshot **未接入** Integration / Planner
    （有测试锁定分页核心不导入 / 不构造 Provider）；
  - **前端未改动**（本轮无前端相关接口变化），未跑 `npm run build`。
- 阶段影响：阶段图由"Phase 2B-2B 完成"推进为"**Phase 2B-2C0 完成**"，
  下一步为 **Phase 2B-2C1 真实网络 Transport**（登录 / 分页参数人工验证 / 请求规模确认），**须等新任务书**。
- 修改文件（本模块视角）：
  - `docs/status/agent_frontend.md`（最小阶段同步：表头、阶段图、新增 Phase 2B-2C0 结果小节、
    「当前阻塞」「下一步」）
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **420 passed / 2 skipped**
  （本轮前 366 passed / 2 skipped；旧测试全部继续通过，未删除旧测试、未新增 skip）。
- 公共接口是否变化：**否**（未改 Schema / Interface / Integration 签名 / API）
- 下一步：等待 Reviewer 验收 **Phase 2B-2C0**。⚠️ **不 merge，不自行进入 2B-2C1**。

---

### 2026-10-01 - Phase 2B-2C1A：SYSU Authorized Browser Transport + Capture Bridge（阶段同步）
- 本次目标：进入 **Course Data** 的**浏览器端显式触发授权采集 + 本地 Capture Bridge**
  （主记录见 `docs/worklogs/course_data.md`）。对 Agent / Frontend 来说本轮是**阶段同步**，无行为改动。
- 起点：`main` = `3ba7cc4a7c2db3bcd255e8ad8c7f6bc8b8fecc2d`；
  分支 `feature/course-data-sysu-authorized-transport`。
- 新增：
  - `tools/sysu_course_offering_collector.js`（浏览器端采集器，**必须用户显式调用**；
    认证交给浏览器 `same-origin`，代码不读取 / 不保存 / 不导出任何认证状态）；
  - `backend/app/course_data/captured_pages.py`（`CapturedPagesFetcher` +
    `collect_captured_pages_snapshot()` + `load_capture_bundle()`，零网络，
    **复用**分页核心判定 `partial` / `complete`）；
  - `backend/tests/test_course_data_captured_pages.py`、`backend/tests/test_sysu_collector_guard.py`。
- 关键边界：
  - **公共契约未改**：`schemas/`、`docs/interfaces/`、`integration/`、`main.py`、`api/`、
    `frontend/`、`mock_data/` **一律未修改**；`SnapshotCourseDataProvider` 未修改；
  - **未接产品链路**：采集器与 Bridge **不接** Integration / Planner / API / 前端产品 UI；
  - **前端未改动**（真实 Capture Bundle 的导入 UI 属后续步骤），未跑 `npm run build`；
  - **实际 SYSU 请求数：0**（未登录、未运行采集器、未生成真实数据）。
- 隐私：Capture Bundle 属 **Real Sanitized Capture**，**不进 Git**（含 `mock_data/` 与测试 fixture）；
  本轮**未生成任何真实 Capture Bundle**。
- 阶段影响：阶段图新增 `Phase 2B-2C1A ✅ 浏览器端授权采集器代码 + Capture Bridge`，
  下一步为**负责人手动 smoke run（2 页，预期 partial）**与真实 Capture 导入 UI，**须等新任务书**。
- 修改文件（本模块视角）：
  - `docs/status/agent_frontend.md`（最小阶段同步：表头、阶段图、新增 Phase 2B-2C1A 结果小节、「下一步」）
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **509 passed / 2 skipped**
  （本轮前 420 passed / 2 skipped；旧测试全部继续通过，未删除旧测试、未新增 skip）。
- 公共接口是否变化：**否**（未改 Schema / Interface / Integration 签名 / API）
- 下一步：等待 Reviewer 验收 **Phase 2B-2C1A**。⚠️ **不 merge，不自行开始手动 smoke run**。

---

### 2026-10-01 - Phase 2B-2C1A Reviewer 修复（阶段同步）
- 本次目标：同步 Reviewer 指出的 3 项 Collector 修复（主记录见 `docs/worklogs/course_data.md`）。
- 修复内容：① SYSU `firstPageNo` **锁定为 1**（传其它值在发请求前失败；通用分页核心不变）；
  ② **空 teacher 不得被 `REDACTED` 静默修复** → 整体失败（错误信息不回显取值）；
  ③ `toJson(result)` 输出**裸 Capture Bundle**，可直接交给 `load_capture_bundle`；
  取消 / 无 bundle 时 `toJson()` 失败，不生成伪 bundle。
- 修改文件（本模块视角）：
  - `docs/status/agent_frontend.md`（Phase 2B-2C1A 小节同步上述 3 条 + 测试数字）
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **515 passed / 2 skipped**
  （修复前 509 passed / 2 skipped；旧测试全部继续通过，未删除旧测试、未新增 skip）。
- **实际 SYSU 请求数：0**；公共接口是否变化：**否**
- 下一步：等待 Reviewer 复验。⚠️ **不 merge**。

---

### 2026-10-01 - Phase 2B-2C1B：Schedule Presence Diagnostic（阶段同步）
- 本次目标：同步新增的**结构诊断入口**（主记录见 `docs/worklogs/course_data.md`）。
- **新事实（负责人已确认）**：真实 smoke run 在真正的「**全校开设课程**」独立模块内
  **same-origin 请求成功**、**认证不再是 blocker**；
  但**第 1 页第 16 条 row 缺少 `teachingTimePlaceStr`**，当前 `collect()` **按设计 fail closed**；
  **尚未生成真实 Capture Bundle**、**尚未取得 complete semester snapshot**。
- **导航纠错**：「**选课**」与「**全校开设课程**」是**两个独立模块**（旧层级描述作废）。
- 新增：`tools/sysu_course_offering_collector.js` 的 `diagnoseSchedulePresence({ semester })`
  与纯函数 `summarizeSchedulePresence(rows)`；`backend/tests/test_sysu_collector_guard.py` 新增守卫；
  `docs/data/REAL_TO_SCHEMA_GAP_REPORT.md` 新增 **G11**（只登记事实、不裁决 Schema）。
- 边界：诊断**只请求第 1 页一次**、**只输出聚合统计**、**不产出 bundle**；
  ⛔ 未改 `collect()` 的 fail-closed 行为；⛔ 未改任何 Schema / Interface / Python 数据链路；
  ⛔ 未接 Integration / Planner / API / 前端产品 UI；**实际 SYSU 请求数：0**。
- 修改文件（本模块视角）：
  - `docs/status/agent_frontend.md`（表头、阶段图、新增 Phase 2B-2C1B 结果小节、「下一步」）
  - 本文件（**仅追加**）
- 测试：`cd backend && python -m pytest` → **522 passed / 2 skipped**
  （本轮前 515 passed / 2 skipped；旧测试全部继续通过，未删除旧测试、未新增 skip）。
- 公共接口是否变化：**否**
- 下一步：等待 Reviewer 验收 **Phase 2B-2C1B**。⚠️ **不 merge，不自行开始诊断或完整采集**。
