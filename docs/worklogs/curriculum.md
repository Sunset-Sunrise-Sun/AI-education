# Curriculum 工作日志

> 仅追加历史记录。新的 Agent 优先阅读 docs/status/curriculum.md。

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

### 2026-10-01 - D4 已修课程规范化
- 新增内部模型、XLSX 只读入口和合成数据测试。
- 保留待确认课程号、实际修读学期及每次修读记录，不做课程认定。
- 未修改公共契约；未保存或提交真实样本及逐行输出。
- 验证结果：后端 595 passed、2 skipped；真实 D4 本地读取与独立逐字段核对通过。
- 后续：D2/D3 方案解析。

### 2026-10-01 - 培养方案与课程匹配框架
- 新增内部方案和课程组模型、候选匹配、Diff、Course/MakeupTask 适配及 Provider。
- 认定和缺课确认按目标版本及已修来源核对；未知字段不补造，选修池不逐课列为必补。
- 按公开证据保留方案元信息；匹配使用合成数据测试，未接入真实逐课程数据，未修改公共契约。
- 测试结果：后端 1001 passed、2 skipped；D4 本地读取仍通过。
- 后续：真实课程列表接入和规则核验。

### 2026-10-02 - 结构化 case 与 Mock MVP
- 基于交接包基线 f807d89，复用已有 D4 和内部模型。
- 新增一次绑定的匹配规则、结构化输入加载、Provider 和可运行人工 Demo。未知先修保留为待确认任务。
- 内部学业分析保留有来源的依赖和问题；显式策略下才生成顺序，不新增公共 priority。
- 来源误标和重复 JSON 键会拒绝，私有输入命令只输出统计。未提交真实材料。
- 测试：后端 1194 passed、2 skipped，无新增 skip；D4 私有读取仍通过。真实 D2/D3 与学校规则尚未验收。
- 交付：推送后等待 Architecture Review，不合并 main。

### 2026-10-02 - 文件导入与选修计划补充
- 新增明确表格/列/行范围映射的 Word 导入草稿及源位置，case 可组合仓库外的 Word 和 D4 文件。问题行阻断转换，不补课程号或先修。
- 隐藏文字、使用中的隐藏样式、未审修订、兼容分支、异常布局及 ZIP/XML 问题会保留待审或固定错误。读取有限制，不新增依赖，不实现完整 Word 渲染。
- 新增有依据的平面选修组选择，保留实际缺修学分；无选择、选择不足、额度未知继续阻断。被明确先修引用的池课程保留待确认任务。
- 补齐缺修依据，修复来源顺序被未知期限阻断、重复课程号覆盖已知先修边的问题。新增汇总学分、课程组容量和期限链的内部风险提示。
- 增加只输出统计的 Word 检查和待确认 case 检查，JSON 使用有界读取。增加可复现人工选修案例及输入说明。
- 验证：后端 1426 passed、2 skipped，无新增 skip；独立交叉检查通过。真实 D4 重新读取和待确认 ID 保留检查通过。
- 使用数据：自动测试和 Office 到 Provider 链路使用人工 Mock；真实 D4 只在本地读取统计，未提交原文件或逐行记录。
- 未修改公共 Schema、Interface、Provider 签名、Planner、Course Data、Frontend 或现有 HTTP API。
- 未完成：真实 D2/D3 和真实规则接入、官方 Word 格式核验、真实端到端验收、跨组抵扣和复杂选修约束。内部顺序不能代替学期排课结果。
- 交付：继续使用 feature/curriculum-mvp-provider，由 shadowRoxy 更新 PR #25，等待 Architecture Review，不合并 main。

### 2026-10-02 - 独立技术审查与私有接入准备
- 新的技术审查核对公共契约、真实数据边界及 Integration 消费，修复 Word 连字符被丢弃导致课程号/学分错误的问题。
- 纯必修及混合平面组现在可由已有必修要求和明确选修选择表达；实际学分缺口、课程认定状态及未知先修仍保留。
- 对应问题有修前失败用例，修后经交叉复核。后端 1445 passed、2 skipped，无新增 skip。
- 新增 Curriculum 技术审查记录，正式 Architecture Review 尚未批准。未修改公共契约、其他成员代码或新增运行依赖。
- 仓库外准备真实 D4 路径引用和待交接培养方案配置，未复制或提交真实数据及私有配置。D2/D3 课程列表仍为空、完整性为 false，自动匹配规则未启用。
- 当前没有 Planner 实际求解实现，消费核对仅证明契约传递，不声称排课或真实端到端验收通过。

### 2026-10-05 - 补修判定时点（historical makeup scope）
- 本次目标：区分“目标专业未来正常要修的课程”与“转专业时点以前真正需要补修的历史缺口”。此前 MVP 会把目标培养方案中尚未修读的后续学年课程（如操作系统、计算机网络、密码学）一并当作当前补修任务。
- 分支与基线：从最新 main `647e4908a302e3bec87823ccdb2d4a6033dccc15` 新建 `fix/curriculum-makeup-scope`（PR #25 已合入 main）。
- 设计：新增 Curriculum 内部 `MakeupScope(target_version_id, as_of_term, evidence)`，随 case 输入显式给出；Diff 记录每个目标条目的分类 `historical / future / unresolved`。只在显式提供 scope 时生效；未提供时保持原有 generic curriculum-diff 行为，不读取系统日期。
- 学期比较：新增内部严格 term parser/comparator，只接受 `YYYY-1` / `YYYY-2`（不裁剪空白）。区间 `2025-1~2025-2`、`未知`、`空`、异常格式一律返回 unresolved，绝不静默按任一方向分类。边界规则：`as_of_term` 当期算 historical（包含）。
- 行为：`historical` 且未满足 → 仍按原逻辑，可为 `required`；`historical` 且已满足 → 保持 `satisfied`；`future` → 不进入当前 `MakeupTask[]`（必修与选修同样处理）；`unresolved` → **阻断投影**（fail closed），要求人工明确范围。`as_of_term` 本身不可解释时同样阻断。
- 可追溯性：scope 的 `evidence` 会写入相关任务的 `source_evidence`；`MakeupScope` 属 Curriculum 内部对象，不进入 Provider 签名、`MakeupTask`、Integration 或 Planner。公共 Schema 与 Provider 签名未改。
- 修改文件：新增 `backend/app/curriculum/terms.py`；修改 `backend/app/curriculum/matching.py`、`backend/app/curriculum/case.py`、`backend/app/curriculum/__init__.py`；新增 `backend/tests/test_curriculum_makeup_scope.py`；新增 `mock_data/curriculum_demo/scoped_case.json` 与 `scoped_makeup_tasks.json`（全部 `mock://` 人工数据）；同步本文件与 `docs/status/curriculum.md`。
- 测试：新增 60 项测试，覆盖历史必修未满足/已满足、未来必修、未来选修、边界当期、未知学期、区间学期、异常格式、未提供 scope 的兼容行为、as_of 不可解释、scope 与目标版本不匹配、额外字段拒绝、Mock/Real 边界与证据可追溯。全量后端（`PYTHONUTF8=1`）：**1845 passed、2 failed、2 skipped**；GBK 环境默认命令：1832 passed、15 failed、2 skipped。
- 失败说明：15 项（GBK）/2 项（UTF-8）失败均为**既有环境性差异**，在本次改动前的 main 基线上同样存在；未使用 skip/xfail/删除测试掩盖，也未为通过测试修改源码或放宽断言。
- 使用数据：Mock（人工合成 `mock://` 数据）。真实 D4 只在本地读取，未提交真实文件、逐行记录或私有配置。**当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**
- 未完成/需要人工确认：Case A 的真实 `as_of_term` 仍缺正式证据或负责人确认（当前 Mock 依据已显式标注“不是学校转专业执行时点”）；真实课程等价认定仍须人工/学校依据；prerequisite 仍不能猜；真实 D2/D3/D4 端到端验收未完成；G11 与 complete 2026-1 snapshot 状态未变。
- 对其他模块影响：公共 Schema、Interface、Integration、Planner、Course Data、Frontend 均未修改。真实学生隐私材料未进入仓库。
- 下一步：等待项目 Architecture Review；**不自行 merge main**。

### 2026-10-05 - MakeupScope 修复：逐条人工确认、satisfied 语义、课程组 scope
- 本次目标：按 Architecture Review 的 `CHANGES REQUIRED` 修正三项明确问题，不推翻上一版设计，不顺手重构。继续使用 `fix/curriculum-makeup-scope`；基线仍为 main `647e4908a302e3bec87823ccdb2d4a6033dccc15`。
- 修复 A（逐条 evidence-backed 范围确认）：新增内部 `ConfirmedScopeDecision`，以 **`target_source_record`**（具体 requirement entry，非 `course_id`）为主键，`decision` 仅 `historical` / `future`，`evidence` 必填。它**只解除 parser 无法确认的 unresolved**（range / null / 空串 / 非法格式 / unknown）；对可自动解析的单学期条目下发 decision 会被判为**与来源事实冲突并报错**，不静默覆盖。校验覆盖版本匹配、条目存在、课程号一致、重复 decision、额外字段、空 evidence、Real case 混入 `mock://`。case 新增可选内部字段 `confirmed_scope_decisions`。
- 修复 B（satisfied 语义）：future 过滤**只作用于未满足/待确认项**。`satisfied` 无论 historical / future / unresolved 都保持原有输出语义（仍输出）；未满足项 future 时不输出；unresolved 未满足项继续 fail closed，但**已确认 satisfied 的条目不会因 scope unresolved 而阻断整批投影**。
- 修复 C（课程组 scope-aware）：组内成员全在未来范围 → 该组不构成历史要求，**不阻断**历史投影；全在历史范围 → 保持原有严格组规则与阻断语义；历史与未来**混合** → 明确**不按课程数量、学期比例或已得学分推导切分**，默认阻断（`historical_ambiguous`），需人工提供 `confirmed_group_scope_decisions.historical_minimum_credit`（只表示历史部分额度，须不超过组最低学分、能被历史成员学分总量满足、且只适用于 mixed 组）。`GroupGap` 新增内部 `scope` / `historical_minimum_credit` 字段（默认值保持未 scoped 行为不变）；`group_plan_covers_requirement` 在 scoped 情况下按历史额度判定；未来组的 `group_gap` 不再触发“组已满足”改写，因此未来选修选择不会被计入历史组额度。
- 可追溯性：`ConfirmedScopeDecision.evidence` 写入相关任务 `source_evidence`（仅可追溯 source reference，不含本地路径、姓名、学号、成绩或 GPA）。三类人工结构（`MakeupScope` / `ConfirmedScopeDecision` / `ConfirmedGroupScopeDecision`）均为 Curriculum 内部对象，不进入公共 Schema、`MakeupTask`、Provider 签名、Integration 或 Planner。
- 修改文件：修改 `backend/app/curriculum/terms.py`、`matching.py`、`case.py`、`__init__.py`；新增 `backend/tests/test_curriculum_scope_decisions.py`；更新 `docs/curriculum/INPUTS.md`、`docs/status/curriculum.md`、本文件。
- 测试：新增 **64** 项（上一轮 60 项保持通过），覆盖 12 项 decision 校验、明确 term 与人工 decision 冲突拒绝、satisfied 语义 6 项、future 未满足三态不输出、课程组 12 项（future-only / historical-only / mixed 阻断与显式切分 / 不得比例切分 / 未来选择不计入历史组 / 未 scoped 行为不变）。全量后端（`PYTHONUTF8=1`）：**1909 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），在本次改动前的基线上同样失败，与 scope 功能无关；未使用 skip/xfail/删除测试掩盖，也未为通过测试放宽断言。
- 使用数据：Mock（人工合成 `mock://` 数据）。真实 D4 只在本地读取，未提交真实文件、逐行记录或私有配置。**当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**
- 未完成/需要人工确认：Case A 真实 `as_of_term` 仍未确认；混合课程组的历史额度切分需要来源依据；课程等价认定与 prerequisite 仍未确认；真实 D2/D3/D4 端到端验收未完成；G11 与 complete 2026-1 snapshot 状态未变。
- 对其他模块影响：公共 Schema、公共模型、Interface、Integration、Planner、Course Data、Frontend 均未修改。
- 下一步：等待项目 Architecture Review 复验；**不自行 merge main**。
