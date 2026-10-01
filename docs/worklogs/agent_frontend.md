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
