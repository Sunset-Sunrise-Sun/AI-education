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

### 2026-10-05 - MakeupScope 第三轮修复：entry-level scope、mixed 组历史额度、组依据传播
- 本次目标：按 Architecture Re-Review 的 `CHANGES REQUIRED` 只修三个实现级 blocker，不重新设计、不扩范围。继续使用 `fix/curriculum-makeup-scope`；基线仍为 main `647e4908a302e3bec87823ccdb2d4a6033dccc15`。
- Blocker A（scope lookup 真正按 requirement entry）：`CurriculumDiff` 的 scope 查询改为以 `source_record` 为键 —— 新增 `scope_bucket_for_entry` / `scope_evidence_for_entry` / `scope_buckets_by_entry` / `unresolved_scope_entries`，**删除按 `course_id` 的 `scope_bucket()` 入口**。投影层（future / unresolved 判定、emit 集合）、组计算、任务依据查找全部改用 entry 键；`emit_records` / `passthrough_records` 亦按 entry 组织。同一 course_id 的多条 entry 不再串线，解除其中一条不会连带解除另一条。
- Blocker B（mixed 组历史额度不得由 future 覆盖）：mixed 组的历史额度只由**历史范围内**的已满足学分或历史必修/明确选修计划覆盖；**future 课程一律不参与历史额度计算**（satisfied / required / selected 均不计）。future-only 组仍不阻断；历史组仍保持原严格规则；mixed 无切分仍 fail closed。同时保持 `group_gaps[].remaining_credit` 的既有"已得学分缺口"语义不变（不改为计划容量），避免影响既有 group 报告与测试口径。
- Blocker C（组决策依据精确传播）：`confirmed_group_scope_decisions[].evidence` 现按 `target.group_id` 精确附加到受该组历史投影影响而输出的任务 `source_evidence`；不进入其他组、其他课程或没有 `group_id` 的课程，也不为没有 decision 的组凭空附加。
- 顺带（非 blocker）：把投影层 `historical_unmet()` 重命名为语义准确的 `is_future_unmet()`。
- 修改文件：修改 `backend/app/curriculum/matching.py`；修改/新增测试 `backend/tests/test_curriculum_scope_decisions.py`；更新 `docs/curriculum/INPUTS.md`、`docs/status/curriculum.md`、本文件。未改其他模块。
- 测试：本轮新增 **20** 项（scope 测试合计 84 + 60 = 144 项全部通过），覆盖 entry-level 分类与依据不串线、同一 course_id 两条 unresolved 仅解除其一、mixed 组 future satisfied/required/selection 不计入历史额度、历史额度只由历史事实覆盖、组依据只进入本组任务（含双组互不串、非组课程不带）、组依据映射按组。全量后端（`PYTHONUTF8=1`）：**1929 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），在本次改动前的基线上同样失败，与本轮无关；未使用 skip/xfail/删除测试掩盖，也未为通过测试放宽断言。过程中曾误改 group 覆盖语义与重复 course_id 守卫，均已在既有测试约束下恢复原语义。
- 使用数据：Mock（人工合成 `mock://` 数据）。真实 D4 只在本地读取，未提交真实文件、逐行记录或私有配置。**当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**
- 未完成/需要人工确认：Case A 真实 `as_of_term` 仍未确认；mixed 组历史额度切分需来源依据；课程等价认定与 prerequisite 仍未确认；真实 D2/D3/D4 端到端验收未完成；G11 与 complete 2026-1 snapshot 状态未变。
- 对其他模块影响：公共 Schema、公共模型、Interface、Integration、Planner、Course Data、Frontend 均未修改。
- 下一步：等待项目 Architecture Review 复验；**不自行 merge main**。

### 2026-10-05 - MakeupScope 第四轮修复：历史覆盖池、组依据范围、mixed 组 reason
- 本次目标：按复验意见只修 3 点，不扩范围。继续使用 `fix/curriculum-makeup-scope`；基线仍为 main `647e4908a302e3bec87823ccdb2d4a6033dccc15`。
- 修复 A（历史覆盖池）：`_group_historical_bar()` 的历史覆盖池收紧为**只接受 bucket == historical 的组成员**（原条件会放行 `future + satisfied`）。future 成员无论 satisfied / required / selected / manual_confirmation / possibly_equivalent 一律不参与 `historical_minimum_credit` 覆盖。同一规则同步到 group gap 的 covered 计算。未 scoped 用例不带 bucket，保持原行为。新增直接断言 `group_plan_covers_requirement(diff, "GROUP-A") is False`（historical satisfied = 0、future satisfied = 6、bar = 6），不只检查 `GroupGap.remaining_credit`。
- 修复 A 附带发现：当 mixed 组已被覆盖时不会产生 `GroupGap`，原逻辑会回退成“整个组最低学分”作为历史 bar，导致已确认的 split 被忽略。现改为在无 gap 时直接读取 `confirmed_group_scope_decisions` 的 `historical_minimum_credit`。
- 修复 B（组依据过度传播）：`ConfirmedGroupScopeDecision.evidence` 现在只附加到该组内**本身属于历史范围**的已输出任务（`target.group_id` + entry bucket 双重条件）。同一组的 future satisfied 任务保持原输出语义但**不带** split evidence；不同组仍互不串。
- 修复 C（mixed 组 reason）：`GroupGap.reason` 区分两种情形 —— 有 `ConfirmedGroupScopeDecision` 且已获得 `historical_minimum_credit`、但历史学分仍有缺口时，写“历史额度已经确认，但仍存在未满足学分”；只有 mixed 且无 split decision 时才写“无法从来源分割，需人工确认”。
- 修改文件：修改 `backend/app/curriculum/matching.py`、`backend/tests/test_curriculum_scope_decisions.py`；更新 `docs/curriculum/INPUTS.md`、`docs/status/curriculum.md`、本文件。
- 测试：本轮新增 **10** 项（scope 测试合计 94 + 60 = 154 项全部通过）。全量后端（`PYTHONUTF8=1`）：**1939 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），基线上同样失败，与本轮无关；未使用 skip/xfail/删除测试掩盖，也未放宽断言。
- 使用数据：Mock（人工合成 `mock://` 数据）。**当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**
- 未完成/需要人工确认：Case A 真实 `as_of_term` 未确认；mixed 组历史额度切分需来源依据；课程等价与 prerequisite 未确认；真实 D2/D3/D4 端到端验收未完成；G11 与 complete 2026-1 snapshot 状态未变。
- 对其他模块影响：Schema、Models、Interface、Integration、Planner、Course Data、Frontend 均未修改。
- 下一步：等待项目 Architecture Review 复验；**不自行 merge main**。

### 2026-10-05 - positional DOCX profile：真实培养方案可导入
- 背景：真实 Case A validation 暴露 IMPLEMENTATION BLOCKER —— `遥感方案.docx` / `网安方案.docx` 是学校真实版式，课程表**没有列标题行**（第 1、2 行为空，数据自第 3 行起），而 `docx_reader` 强制要求 `expected_headers` 非空且逐字匹配，两份文档都无法导入。Architecture 决策：新增**显式 positional table profile**，不放宽旧 parser、不让 `expected_headers` 全局 optional、不自动猜列。
- 设计：`mode` 显式声明 `header`（缺省，行为完全不变）或 `positional`。两种模式的 profile 字段集合互斥：header 模式禁止 `data_start_row` / `row_filter` / `exclude` / `column_count` / `identity` / `course_name_lines`；positional 模式禁止 `header_row` / `expected_headers`（因此空 `expected_headers` 无法被当作旁路）。未知 mode、额外字段、无 profile 均 reject；**没有 try header / except positional 式回退**。
- positional 结构守卫：① 数据行物理列必须覆盖全部映射列，缺列即失败（不静默返回空）；② 数据行物理列不得超过声明的 `column_count`，学校改版整体移列时**失败而非错列读取**；③ `identity` 结构锚点（`{column, values}`，列必须已声明）必须在首个数据行起命中，锚点失配即失败；④ 横向 `gridSpan` 合并覆盖映射列时该行位置语义不唯一，失败（纵向合并仅下延分区标签，允许）；⑤ 行选择只用声明式 `row_filter`（全部满足）与 `exclude`（任一命中即丢弃），条件限 `nonempty` / `numeric` / `equals` + 显式取值，**无任何内容猜测或 NLP**；⑥ `course_name_lines` 显式声明双语名称单元格（"中文\nEnglish"）保留前 N 行。
- 真实 Case A：新增 `backend/app/curriculum/plan_profiles.py`，为两份真实方案各声明 4 张课程表的 positional profile（其余为学分统计 / 学年学期统计等附表，不解析）。**只提交结构 profile**：表序号、列位置、锚点课程号、结构守卫，不含真实文件、本地绝对路径、姓名、学号或成绩；真实 `.docx` 仍在受控本地目录，未入库。
- 真实导入结果：`遥感方案.docx` **84 条**课程条目（77 单学期 + 7 区间学期），0 issue；`网安方案.docx` **104 条**（97 + 7），0 issue；两者均可 `to_version()` 转成 `CurriculumVersion`。
- 真实 Case A 层验证（`as_of_term = 2025-2`，evidence 类型 = case-owner confirmation，**非学校官方政策**）：scope 分类 historical 20 / future 77 / unresolved 7；matching 得 satisfied 12（与 D4 已确认且与目标同 ID 的 12 条一致：MA179/MA189/MA190/MAR103/MAR112/MAR115/MAR116/PE101/PE102/PSY199/PUB121/PUB1991）、possibly_equivalent 4、manual_confirmation 78。投影仍被阻断，原因见下。
- 分层 blocker（预期内，未强行消除）：① 目标方案存在未声明课程组的选修条目 → `unrepresented_requirements`；② 7 个区间学期条目（MAR116/MAR117/MAR118/MAR119/PSY199/PUB178 等）为 unresolved，需逐条 `ConfirmedScopeDecision`。两者都**没有**擅自填写 decision、group 额度、course_id 或课程等价。
- 新发现（记为 IMPLEMENTATION BUG，未自行修改）：D4 的 `PE102 体育` 记录被同时用于 identity 匹配 `PE102`（satisfied）与**名称候选**匹配 `PE201/PE202/PE305/PE302`（possibly_equivalent），即同一已修记录在 identity 命中后仍可作名称候选，产生 4 条误报的 name-candidate 任务。已按流程报告，等待 Architecture 决定，本轮不改匹配语义。
- 修改文件：修改 `backend/app/curriculum/docx_reader.py`；新增 `backend/app/curriculum/plan_profiles.py`；新增 `backend/tests/test_curriculum_positional_docx.py`；更新 `docs/curriculum/INPUTS.md`、`docs/status/curriculum.md`、本文件。
- 测试：新增 **42** 项 positional 测试（header 回归 4、positional happy path 5、fail-closed 与模式隔离 24、结构漂移 3 等），全量后端（`PYTHONUTF8=1`）：**1981 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），基线上同样失败；未 skip / xfail / 删除测试，未放宽断言。
- 使用数据：真实 D4 与两份真实培养方案**仅在本地受控目录只读使用**，未提交、未复制进仓库。**本轮结论仍是 Mock + 本地真实材料的 validation，不是真实端到端验收。**
- 未完成/需要人工确认：7 条区间学期 decision；选修组额度定义；PHY137↔大学物理（工）上、大学英语↔大学外语、程序设计系列、MAR110↔MAR108 的课程认定；真实 as_of_term 的正式依据；G11 与 complete 2026-1 snapshot 未变。
- 下一步：等待 Architecture Review 决定 positional 设计是否接受，以及上述 IMPLEMENTATION BUG 的处理方式；**不自行 merge main**。

### 2026-10-05 - positional row selection fail-closed 修复
- 问题：positional 的 `row_filter` 原先在 mapped-column structural guard **之前**执行，因此一个本应属于课程的数据行如果恰好缺失 `course_id` / `credit` 等 selector 列，会因 filter 不满足而 `continue`，**绕过**"row is narrower than the mapped columns" 的 fail-closed 校验（fail-open）。
- 修复：引入显式**行身份判别器** `row_kind`（`{column, condition}`，仅支持 `numeric`，声明 `row_filter` 时必填，且该列必须同时是 selector）。判定顺序改为"先定行身份，再判结构"：
  - 判别器不命中 → 明确是分区/模块/小计行 → skip；
  - 判别器命中，但任一 selector 列物理缺失 → 疑似课程行但结构损坏 → **fail closed**；
  - 判别器命中且全部 selector 命中 → 课程行 → 进入完整 structural guard（行宽、`column_count`、横向合并、锚点）；
  - 判别器命中但某个 selector 不命中 → 部分命中 → **fail closed（不得 continue）**。
- 真实版式为何需要判别器：Case A 的 section 行（"本研贯通课"/"专业提升课"/"人工智能与内容安全"等）在 `course_id` 列**有非空文本**但在序号与学分列非数字，因此 `[False, True, False]` 属"部分命中"。若一律按"部分命中即 fail"会把真实 section 行变成错误；`row_kind`（numeric 序号）才能区分"确定非课程行"与"疑似课程行但损坏"。
- 附加守卫：selector 只能读取**标识性列**（`course_id` / `credit` / `recommended_term_text` / `sequence`）；映射到 `requirement` 这类可选列的 selector 直接拒绝（否则可能整表无行命中而静默 skip）。`exclude` 仍在行身份判定之前生效。
- 真实 Case A profile 的 selector 更新为 **`sequence` numeric + `course_id` nonempty + `credit` numeric**，`row_kind = sequence numeric`。真实导入结果不变：`遥感方案.docx` 84 条、`网安方案.docx` 104 条，均 0 issue。
- 明确未做：本轮**不修** PE102 matching bug（D4 `PE102 体育` 在 identity 命中后仍作名称候选，导致 `PE201/PE202/PE305/PE302` 误报 `possibly_equivalent`），继续作为独立 **IMPLEMENTATION BUG** 记录，等待 Architecture 决定。header mode 行为完全未变。
- 修改文件：修改 `backend/app/curriculum/docx_reader.py`、`backend/app/curriculum/plan_profiles.py`、`backend/tests/test_curriculum_positional_docx.py`；更新 `docs/curriculum/INPUTS.md`、`docs/status/curriculum.md`、本文件。
- 测试：positional 测试由 42 增至 **52** 项（新增：判别器缺失时 section 行仍安全跳过、判别器命中但 course_id 物理缺失 → reject、判别器命中但 credit 物理缺失 → reject、selector 不命中 → reject、完整课程行正常读取、`row_kind` 必填 / 仅 numeric / 须为已声明列 / 须同时是 selector、selector 须读标识性列）。全量后端（`PYTHONUTF8=1`）：**1991 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），基线上同样失败；未 skip / xfail / 删除测试，未放宽断言。
- 使用数据：真实材料仅在本地受控目录只读使用，未提交。**结论仍是本地 validation，不是真实端到端验收。**
- 下一步：等待 Architecture Review 复验；**不 merge、不 push main**。

### 2026-10-05 - positional discriminator 损坏边界修复
- 遗留 fail-open：`if not row_kind.matches(kind_value): continue` 会把"判别器（序号）本身损坏、但 course_id + credit 仍明显像课程"的记录**静默跳过**。
- 修复：区分「确定是非课程行」与「疑似课程行但判别器损坏」——
  - 判别器命中 + 全部 selector 命中 → 课程行，进入完整 structural guard（不变）；
  - 判别器命中 + 任一 selector 无值或 selector 不命中 → 结构损坏，fail closed（不变）；
  - **判别器不命中，但其余 identifying selectors 全部命中**（course_id 有值且 credit 为数字）→ 判别器本身损坏，**fail closed**（新增，报 `row discriminator is damaged`）；
  - 判别器不命中且其余 selectors 未全部命中 → 真实分区/模块/小计行 → 安全 skip（不变）。
- 配套修正：positional 模式下**单元格"存在但为空"与"物理缺失"语义相同**（空单元格读出 `None`），否则空序号单元格会伪装成"判别器不命中 + 其余命中"以外的情形而漏检。该归一化**仅作用于 positional 模式**，header 模式保持原有原始文本行为不变（首轮实现曾误扩大到 header 模式，导致 3 项既有 header 测试回归，已当场修正并复跑全绿）。
- 真实 Case A 导入结果不变：`遥感方案.docx` 84 条、`网安方案.docx` 104 条，均 0 issue；真实 section 行（判别器 False / course_id True / credit False）继续安全跳过。
- 本轮**未修** PE102 matching bug，继续作为独立 IMPLEMENTATION BUG 记录。
- 修改文件：`backend/app/curriculum/docx_reader.py`、`backend/tests/test_curriculum_positional_docx.py`；更新 `docs/curriculum/INPUTS.md`、`docs/status/curriculum.md`、本文件。
- 测试：positional 测试 52 → **56** 项（新增：sequence 单元格无值但 course_id/credit 完好 → reject；sequence 非 numeric 但 course_id/credit 完好 → reject（`row discriminator is damaged`）；判别器不命中且其余 selectors 未全命中 → 仍安全 skip；真实 section 形 `False/True/False` → 安全 skip）。全量后端（`PYTHONUTF8=1`）：**1995 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），基线上同样失败；未 skip / xfail / 删除测试。
- 下一步：等待 Architecture Review 终审；**不 merge、不 push main**。

### 2026-10-05 - consumed match candidates：已消耗的确定性匹配退出名称候选池
- 根因：`_candidate_records()` 只按「course_id 相同」区分 identity 与 named，named 池**不看该记录是否已被确定性的 exact/identity match 用过**。因此 D4 `PE102 体育` 在 identity 匹配目标 `PE102` 之后，仍因名称「体育」被再次投入 `PE201/PE202/PE305/PE302` 的候选，产生 4 条错误 `possibly_equivalent`。真实数据流：`build_curriculum_diff` 先跑一个 `automatic` pass（`allow_exact_match` 下计算 exact），随后主循环再对每个 target 调 `_candidate_records()` 组装 `candidates = identity + named`——两趟之间没有"已消耗"信息传递。
- 修复设计：新增内部 `consumed_refs: set[tuple[str, str]]`，在 `automatic` pass 中**当某个 exact 结果确实被采用为自动认证**时（`allow_exact_match` 且目标 course_id 唯一、requirement 非 UNKNOWN、无 explicit recognition、无 missing requirement——与既有 `ref_uses` 登记条件完全一致）加入该记录的 `(source_id, source_record)`。`_candidate_records(target, completed, consumed)` 在构造 **named** 池时排除 `consumed` 中的记录。**identity 池不参与过滤**，因此 identity 匹配语义不变。
- 标识选择：用 `(source_id, source_record)` 这一稳定内部引用，而非 `course_id`。原因：unresolved record 可能没有 course_id；同一 course_id 理论上可能对应不同 completed entry；按引用可避免误伤其它独立记录。
- 刻意**没有**扩成「一条 completed record 永远只能匹配一个 target」的通用规则：只有确定性确认匹配才产生消耗；`ConfirmedRecognition` 目标不进入该消耗分支（走独立路径），未解析身份的记录永不消耗，纯名称候选也不消耗。
- 真实 Case A re-validation（`as_of_term = 2025-2`，evidence 类型 = case-owner confirmation，**非学校官方政策**）：**`possibly_equivalent` 由 4 → 0**；`satisfied` 保持 **12**；`manual_confirmation` 92。`PE101/PE102` 仍为 `satisfied`（各自 identity 消耗自己的记录），`PE201/PE202/PE305/PE302` 候选列表**均为空**、状态 `manual_confirmation`，不再由 D4 `PE102` 产生误报。目标课程条目 104、旧方案 84、D4 24 条不变；投影仍被 **7 条 unresolved 区间学期 + 未声明选修组** 阻断（属业务 unresolved，本轮未触碰）。
- 修改文件：`backend/app/curriculum/matching.py`；新增 `backend/tests/test_curriculum_consumed_candidates.py`；更新 `docs/status/curriculum.md`、本文件。未触碰 Provider / Schema / Planner / Course Data / Frontend / group / prerequisite / priority / scope。
- 测试：新增 **13** 项，并已实测**去掉修复后其中 4 项会失败**（证明测试确实覆盖该缺陷）。全量后端（`PYTHONUTF8=1`）：**2008 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），基线上同样失败；未 skip / xfail / 删除测试。
- 使用数据：真实 D4 与两份培养方案仅在本地受控目录只读使用，未提交、未复制进仓库。
- 下一步：等待 Architecture Review；**不 merge main**。

### 2026-10-05 - 真实选修组建模：CSE-ELECTIVE-POOL + 荣誉课程移出普通 requirement
- 背景（Architecture 已确认的真实原文事实）：目标方案 table 6 `（专业选修课）` 共 37 门 / 课程学分合计 86，方案给出**主修应修专选 23**（table 7 合计行 `23 | 37 | 86 | 1314 | 324.0+4周`；table 1 `专选 23`；table 10 r12 专选 应修 `23.0`，与开设学分总和 `86.0` 并排）。table 6 的六个 banner 分区（人工智能与内容安全 / 本研贯通课 / 网络与通信安全 / 软硬件系统及安全 / 安全基础模块 / 密码与攻防对抗）**不带任何独立学分数字**，全文档亦无"至少修 X 学分"或"任选 X 门"说明。
- 建模决策：整个 table 6 是**一个池** —— `group_id = CSE-ELECTIVE-POOL`、`minimum_credit = 23`、`source_record = table:7!row:2`；六个分区仅作展示（保留在 `course_type`），**不**生成六个 `CurriculumGroup`，23 **不**拆分。
- 实现：`plan_profiles._course_table()` 新增可选 `group_id`，目标 profile 的 table 6 传入 `CSE-ELECTIVE-POOL`（`group_id` 本就是 positional profile 的合法字段，parser 无需改动）；新增 `plan_group_records(role)` 暴露声明式 group 记录，调用方传给 `DocxImportResult.to_version(group_records=...)` 即可构造 `CurriculumGroup`。
- 荣誉课程处理：table 8 `（荣誉课程）`（table 9 合计应修 **0** 学分）**从目标 profile 移除**，不再作为普通主修 requirement 导入；**未**创建 `minimum_credit = 0` 的假组。副作用（正向）：其 10 门课中 8 门在 table 4 已是专业课（CSE211/CSE210/CSE212/CSE309/CSE349/CSE360/CSE310/CSE362），`CS5701/CS5702` 现只从选修池导入一次 → 目标版本**无重复 course_id**（此前 104 行含 10 行荣誉课且 `CS5701/CS5702` 重复计入）。
- 修改文件：`backend/app/curriculum/plan_profiles.py`；新增 `backend/tests/test_curriculum_elective_group.py`；更新 `docs/curriculum/INPUTS.md`、`docs/status/curriculum.md`、本文件。未改 docx_reader（`group_id` 已支持）、未改 `matching.py` 的 `unrepresented_requirements` 逻辑、未改公共 Schema / Provider / Planner / Course Data / Frontend。
- 内部分层：本仓库内合成 fixture 覆盖 group 装配（同一 group_id、minimum_credit=23、banner 不生成组、池成员学分合计 ≠ 23、声明完整性）；真实文件侧只读验证，不提交。
- 测试：新增 **11** 项。全量后端（`PYTHONUTF8=1`）：**2019 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），基线上同样失败；未 skip / xfail / 删除测试。
- 使用数据：真实 D4 与两份培养方案仅在本地受控目录只读使用，未提交、未复制进仓库。
- 下一步：等待 Architecture Review；**不 merge main**。

### 2026-10-05 - 真实 Case A 区间学期 scope decision（case 数据，非算法规则）
- 只读实测：目标方案 range-term entry 共 **7 条**（以实际导入结果为准，非凭记忆）：MAR116/PSY199/PUB1991（`2025-1~2025-2`，均已 **satisfied**）、PUB178（`2025-1~2028-2`，manual_confirmation）、MAR117（`2026-1~2026-2`）、MAR118（`2027-1~2027-2`）、MAR119（`2028-1~2028-2`）。
- 决策（严格按区间自身文字，不猜）：区间整体 **> 2025-2** 的 3 条 → `future`（转专业后的正常培养计划）；区间**横跨** 2025-2/2026-1 的 PUB178 → **BUSINESS CONFIRMATION NEEDED，不记录 decision**；3 条 **satisfied** 的 range entry 按冻结语义（unresolved+satisfied 不阻断）**不加无必要 decision**。
- 实现方式（最小）：**未改任何算法或 parser**（`terms.py` / `matching.py` / `docx_reader.py` / `requirements.py` / 公共 Schema / Provider / Planner / Course Data / Frontend 全未触碰）。新增 `backend/app/curriculum/case_a_decisions.py`，把真实 Case A 的 `as_of_term`、evidence、3 条 `future` decision、以及"横跨未决"与"已满足无需 decision"清单表达为**纯 case 数据**；`confirmed_scope_decisions()` 返回可直接传给 `CurriculumCase` 的内部对象。evidence 一律 `case-owner-confirmed://case-a/range-term-scope`，**不使用** `official-policy://`，也不以当前日期推断。
- 反硬编码：通用代码中**没有**任何 `course_id == "MAR116"` / `term` 字符串匹配 / `major == "网络空间安全"` 式分支；换另一个转专业学生只需替换 case 输入（decision 集合），scope 算法不变。
- 真实 Case A 复跑：target 94 / completed 24 / historical 20 / future 70 / **unresolved 4**（原 7）/ `unrepresented_requirements=()` / `group_gaps=()`；satisfied 12 / possibly_equivalent 0 / manual_confirmation 82。**projection_ready = False**，唯一 blocker：`table:2!row:11`（PUB178 劳动教育 `2025-1~2028-2`）横跨时点，需负责人确认（历史缺口 / 按转专业时点拆分 / 整体归属转专业后计划）。
- 解除该 blocker 后的预期投影（**探针验证**，该 PUB178 decision 仅临时用于测量，未入库）：23 tasks —— satisfied 12 / manual_confirmation 11 / required 0 / possibly_equivalent 0；future unmet 条目不出现在 `MakeupTask[]` 中。
- 修改文件：新增 `backend/app/curriculum/case_a_decisions.py`、`backend/tests/test_curriculum_case_a_scope_decisions.py`；更新 `docs/status/curriculum.md`、本文件。
- 测试：新增 **12** 项（decision 集合的声明式属性：cutoff、仅"整体在时点后"才记 future、横跨条目必须无 decision、已满足条目无 decision、evidence 类型与绑定、内部对象构造；以及集成属性：不改 elective group、按 `target_source_record` 绑定而非 course_id、不改 exact matching、future unmet 不出现在投影、决定一条不豁免另一条、satisfied range 单独不阻断）。已被 `test_curriculum_scope_decisions.py` 覆盖的同义场景未重复。全量后端（`PYTHONUTF8=1`）：**2031 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），基线上同样失败；未 skip / xfail / 删除测试。
- 使用数据：真实 D4 与两份培养方案仅在本地受控目录只读使用，未提交、未复制进仓库；新增文件不含姓名/学号/成绩/GPA/排名，也不含私有 DOCX。
- 下一步：等待 Architecture Review 与负责人对 PUB178 的业务确认；**不 push、不开 PR、不 merge main**。

### 2026-10-05 - PUB178 case-owner 裁定 future：Real Case A 首次打通
- case owner 裁定：PUB178 劳动教育 `2025-1~2028-2` 在 Real Case A 记为 `future`。理由：该培养方案安排窗口横跨 `as_of_term=2025-2` 且持续至 2028-2，没有证据表明必须在转专业时点前完成，也没有阶段性拆分规则；为避免把仍有后续履行窗口的要求误判成历史欠修，本 Case 按 future 处理。该裁决**仅是 case-owner-confirmed 的 Case A 输入**，未升级为通用 scope 算法或学校官方政策。
- 实现：`case_a_decisions.py` 新增 `_CASE_OWNER_CONFIRMED_CROSSING`（PUB178）并入 `CONFIRMED_SCOPE_DECISIONS`（现 4 条，全 `future`），并以 `CASE_OWNER_FUTURE_RATIONALE` 记录裁定理由；原 `UNDECIDED_CROSSING_CUTOFF` 移除（该条目已被裁定，不再处于"未决"状态）。**未改任何算法或 parser**。
- 文档修复：`docs/status/curriculum.md` 中 `MakeupTask[]` 段落与 `- 最新后端回归：` 之间**缺失换行**（两条 bullet 被并成一行）已修复并复核。
- **Real Case A 首次打通（实测）**：target_records 94 / completed_records 24 / historical 20 / future 71 / unresolved 3（均为已 satisfied 的 range 条目，按冻结语义不阻断）；`unrepresented_requirements = ()`、`group_gaps = ()`；**projection_ready = True**，`CurriculumProvider.get_makeup_tasks()` 成功返回 **makeup_task_count = 23** —— satisfied 12 / manual_confirmation 11 / required 0 / possibly_equivalent 0；总学分 58（satisfied 32 + manual_confirmation 26）。23 条**全部为 historical** 条目（推荐学期均 ≤ 2025-2），future unmet 条目不出现在 `MakeupTask[]` 中。
- 修改文件：`backend/app/curriculum/case_a_decisions.py`、`backend/tests/test_curriculum_case_a_scope_decisions.py`、`docs/status/curriculum.md`、本文件。
- 测试：Case A decision 测试 12 → **13** 项（新增"横跨区间由 case-owner 裁定为 future"与"4 条 decision 全为 future 且逐条绑定 requirement entry"；原先的"横跨必须未决"断言随裁定更新，不再是同义测试）。全量后端（`PYTHONUTF8=1`）：**2032 passed、2 failed、2 skipped**。
- 失败说明：2 项失败为**既有 Windows 环境性差异**（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），基线上同样失败；未 skip / xfail / 删除测试。
- 使用数据：真实 D4 与两份培养方案仅在本地受控目录只读使用，未提交、未复制进仓库；仓库内文件不含姓名/学号/成绩/GPA/排名，也不含私有 DOCX。
- 下一步：等待 Architecture Review 对该 Case A 输入与首次打通结果的复核；**不 push、不开 PR、不 merge main**。

### 2026-10-06 - Gate F：已修课程 XLSX 导入入口（通用摄取能力，backend only）

- 触发：Core MVP Autonomous Run 的 Gate F —— 把"前端选择 XLSX"推进成
  `XLSX → backend validate → completed-course normalization → 既有 Curriculum pipeline`。
- 分支：`feature/xlsx-completed-courses-import`，base = `feature/frontend-real-path-readiness-final @ 19970db`。
- **新增接口**：`POST /api/v1/completed-courses/import`（原始 `.xlsx` 字节；
  ⛔ 不用 multipart ⇒ ⛔ 不新增运行期依赖，⛔ 请求里没有"文件名"参与判定）。
  成功返回归一化统计 + `completed_input`（**恰好**是 case `completed.records` 的输入形状）；
  `source_id` 由**内容摘要**派生（`upload:sha256:<16 hex>`）。
- **文件安全（F2）**：媒体类型白名单（官方 XLSX MIME / `application/octet-stream`）；
  `Content-Length` 必填（缺失 ⇒ 411，声明超限 ⇒ 413）；流式读取全程限长
  （`MAX_UPLOAD_BYTES = 8 MiB`，⛔ 不信任声明的长度）；空文件 ⇒ 400；
  malformed zip / 结构不符 ⇒ 400；记录条数上限 2000；
  ⛔ 公式单元格直接拒绝（⛔ 无 openpyxl、⛔ 不评估公式）；宏部件被忽略且⛔ 永不执行；
  只接受唯一批准的 worksheet `已修课程_脱敏`；
  临时文件只用进程自己的临时目录并在 `finally` 无条件删除（成功/失败两条路径都有测试）；
  ⛔ 不信任文件名（`Content-Disposition` / `X-File-Name` 被忽略，有测试）。
- **复用（F3）**：worksheet 抽取 / 字段映射 / 结构校验继续由既有
  `app/curriculum/xlsx_reader.py`，归一化继续由既有 `completed_courses.py`；
  ⛔ **未**新增 Curriculum Diff / equivalence / recognition / makeup priority / prerequisite
  逻辑（`matching.py` 零改动）。
- **synthetic fixtures（F4）**：新增 `backend/tests/xlsx_fixtures.py`（自建最小 OOXML）——
  valid / empty（仅表头）/ wrong headers / duplicate rows / malformed / missing course id /
  numeric-string 混合单元格 / 公式单元格 / 未批准 worksheet / 超大 XML 部件 /
  超大上传 / Unicode 课程名 / 宏部件；
  ⛔ 未提交任何真实成绩单（真实 D4 仍只在本地受控目录）。
- **隐私（F5）**：错误响应只含通用文案 + 行列位置；有测试断言
  单元格取值 / 原始 XML / `Traceback` / 本地路径 / `.xlsx` 文件名 / 临时文件名
  **一律不出现**；成功响应**不回传 `备注` 自由文本**（只回传 `notes_present_count`）；
  本模块不打印任何 worksheet / cell 内容。
- **集成证明（F6）**：把 demo case 的已修课程事实写成 XLSX 上传，再走**同一条**既有管线
  （`normalize_curriculum_case` → `CurriculumCaseProvider.get_makeup_tasks()`），
  结果与直接用 `records` 的原生 case **逐条一致**；并断言
  `planning_runtime.py`（Case A fixed case）源码里**不存在**任何上传适配器引用
  ⇒ fixed-case 路径与通用摄取能力**明确分离**。
- 测试：`tests/test_completed_courses_import_api.py` **32 passed**；
  既有 `test_curriculum_xlsx_reader.py` 等 Curriculum 套件未受影响。
- 文档：新增 `docs/data/XLSX_COMPLETED_COURSES_IMPORT.md`（两条路径的区别 + 安全/隐私表），
  并在 `docs/status/curriculum.md` 记录。
- 是否修改 public Schema：**否**（⛔ `/schemas/` 零改动；新响应模型定义在 API 模块内）。
  是否修改 frozen Provider contract：**否**。是否改 `/api/v1/plan` 请求契约：**否**（有 OpenAPI 断言）。
- 仍未做：前端接线（前端成绩文件仍只"选择"、不上传）、鉴权（与现有 `/api/v1/plan` 一致）、
  真实成绩单（⛔ 不接真实学生数据）。

### 2026-10-06 - PR #47 BLOCK 修复：`Content-Length` 严格校验（⛔ 不得 500）

- 触发：reviewer 独立探针指出 `POST /api/v1/completed-courses/import` 的
  `Content-Length` 解析在 ASGI app 路径上会 **500**：超长十进制数字、非 ASCII 数字字符。
- **复现（修复前实测，`probe_content_length_500.py`）**：
  - 5000 位纯 ASCII 数字 ⇒ endpoint 返回 `500 Internal Server Error`，
    且 `ValueError: Exceeds the limit (4300 digits) for integer string conversion`
    直接从 ASGI app 抛出（裸 ASGI 调用可复现）；
  - 全角 `８３８８６０９` / 阿拉伯-印度 `١٢٣٤٥` 在裸 ASGI 上落到 411，
    但那是**偶然**（latin-1 解码把字节变成非数字），⛔ 不是显式 ASCII 校验；
  - `" 32"` 反而被 `strip()` 容忍 ⇒ 落到 400 mismatch，与"非法格式"语义不符。
- **修复**：新增纯函数 `completed_courses_ingest.parse_declared_content_length()`
  （API 边界全部委托给它）：
  缺失 / 非字符串 / 空串 / 非 ASCII / 非纯数字 ⇒ **411**；
  纯 ASCII 数字但**位数 > `len(str(MAX_UPLOAD_BYTES))`** 或数值 > 8 MiB ⇒ **413**（位数先于 `int()`，
  ⛔ 不构造任意大整数）；合法 ⇒ 返回整数。⛔ 不再 `strip()`。
- **状态映射（与接口文档一致）**：缺失/非法 411 · 数值或位数超限 413 ·
  实际 streamed 字节超限 413 · 声明 ≠ 实际 400 · 空文件 400。
- **测试**：`tests/test_completed_courses_import_api.py` 32 → **66 passed**，
  覆盖 mandate 的 12 个 probe（含"恰好等于 8 MiB 边界不判 413"、"5000 位 ⇒ 413 不 500"、
  Unicode 数字 fail closed、空白/符号/小数/指数/十六进制/逗号 ⇒ 411、
  声明撒谎但实际超限 ⇒ 413），并对关键用例同时走**真实 endpoint** 与**裸 ASGI**。
- 边界：⛔ 未扩 API（同一 endpoint、同一错误模型，只是把解析变严格）；
  ⛔ 未改 public Schema / frozen Provider contract；⛔ 未触碰 Gate E 与已合并 runtime/store stack。

### 2026-10-07 - 成绩单 PDF → CompletedCourse → 既有 Case A Curriculum 分析
- 本次目标：让**真实中山大学本科成绩单 PDF**成为 Case A 的已完成课程输入，
  并且证明解析结果**真的**喂进既有匹配 / 投影逻辑（⛔ 不是"只解析成功"）。
- 已完成：
  - 新增 `backend/app/curriculum/pdf_reader.py`：解析**当前已核验**的成绩单版面
    （四列一组横向平铺、两行表头、`2025-2026学年 第X学期` 学期行、换行课程名、
    整数/一位小数学分、0–100 与 `P`/`NP` 成绩、多学期、重复表头），
    输出 `term` / `course_name` / `credits` / `grade` / `course_attribute`。
  - **fail closed**：非 PDF、空文件、损坏 PDF、缺标题、缺表格、版面不符、
    超页数/超条数上限一律抛错；学期行、每学期末 `学分 …`/`绩点 …` 汇总行、
    页脚毕业学分/实得学分/平均绩点/评分体系/审核人行⛔ 绝不进入结果。
  - **⛔ 不发明课程号**：成绩单没有官方课程号，因此全部记录为
    `CourseIdStatus.PENDING` + `course_id=None` + `id_match_source=None`。
  - **隐私**：表头以上的姓名/学号/学院/专业区块整体丢弃；错误文案只含固定通用描述
    （⛔ 不含课程名、成绩、学号、姓名、路径、堆栈）；解析器告警被抑制；⛔ 不落盘。
  - **最小化接入改动**：`case.py` 的 `completed` 增加第三个互斥键 `pdf`
    （与 `records` / `xlsx` 三选一），解析结果走**同一个**
    `build_curriculum_diff` / `project_makeup_tasks`。
  - 新增窄接口 `POST /api/v1/completed-courses/import-pdf`（原始字节 + 显式
    `Content-Length`，`source_id` = 内容摘要），错误码与 XLSX 入口分离；
    XLSX 入口保持原样（兼容的次要路径）。
  - 新增文档 `docs/curriculum/PDF_TRANSCRIPT_INPUT.md`（支持范围 + 明确不支持的边界）。
- 修改文件：
  `backend/app/curriculum/pdf_reader.py`（新）、
  `backend/app/services/completed_courses_pdf_ingest.py`（新）、
  `backend/app/api/completed_courses_pdf.py`（新）、
  `backend/app/curriculum/case.py`、`backend/app/curriculum/__init__.py`、
  `backend/app/main.py`、`backend/requirements.txt`（新增 `pymupdf>=1.24`）、
  `backend/tests/pdf_fixtures.py`（新）、`backend/tests/test_curriculum_pdf_reader.py`（新）、
  `backend/tests/test_curriculum_pdf_case_a_integration.py`（新）、
  `backend/tests/test_completed_courses_pdf_import_api.py`（新）、
  `backend/tests/test_integration_orchestrator.py`（白名单登记新路由）、
  `docs/status/curriculum.md`、`docs/worklogs/curriculum.md`。
- 测试：`tests/test_curriculum_pdf_reader.py` **18 passed**；
  `tests/test_curriculum_pdf_case_a_integration.py` **9 passed**；
  `tests/test_completed_courses_pdf_import_api.py` **25 passed**；全量回归见 status。
  ⚠️ 既有套件中 2 项 Windows 环境性失败（ZIP 成员名字面反斜杠、含 `\x00` 的路径）
  在本次改动**之前**就存在，与 PDF 路径无关。
- 使用数据：解析器测试与集成测试全部使用**自建虚构 fixture**（`pdf_fixtures.py`）；
  真实成绩单 PDF 仅在本机做**一次性**口径校核，**不入库**、不写逐行记录。
- 已知问题：
  - PDF 只支持**已核验版面**：⛔ 不支持扫描件 / 图片型 PDF（无 OCR）、
    ⛔ 不支持其它学校、⛔ 不支持其它版本或其它语言的中大成绩单；
  - 成绩单没有课程号 ⇒ 同名课程仍是 `possibly_equivalent` / `manual_confirmation`，
    要变成"已抵认"仍需人工在官方来源侧（如"成绩转换"页面）补全课程号；
  - `pymupdf` 是新增运行期依赖（本地纯解析，不联网）。
- 需要人工确认：PDF 解析口径（哪些表头/页脚行必须丢弃）是否符合负责人手上的成绩单实物；
  `course_id` 的补全流程（官方来源侧 + 人工认定）尚未定义。
- 对其他模块影响：⛔ 公共 Schema 零改动；⛔ Provider 签名未改；⛔ `matching.py` 未改；
  Plane/Integration/Frontend 既不需要感知，也不应把本接口当作已冻结 Case A runtime 的入口。
- 下一步：Architecture 决定 PDF 版面的**版本化**策略；负责人提供课程号补全依据后，
  再把 `pending` 记录升级为已确认身份；前端接入成绩单上传（本轮只做后端 + 接口）。

### 2026-10-07 - 复审修复：修复过的 PDF 必须 fail closed
- 本次目标：只修 Reviewer 复审指出的**唯一阻塞项**——截断 / 损坏的 PDF 可能被静默接受。
- 问题（复审实测）：页面解析库会**成功修复**截断 / 损坏的 PDF 并返回（可能不完整的）
  内容而**不**抛异常。把**真实**成绩单截断到 **97% / 95%** 时，解析器仍"成功"返回
  24 条记录，但 `terms` 从 **2 变成 1**——第二个学期整段消失。原测试只覆盖
  "打不开的输入"，因此 CI 全绿也未发现。
- 修复：打开文档后**立即**读取 `document.is_repaired`；为真则**先关闭文档**再按既有
  通用文案 `transcript: malformed PDF` 拒绝。无法判定修复状态时同样拒绝（fail closed）。
  ⛔ 未改匹配语义 / Curriculum 语义 / API 形状 / 公共 Schema / Provider 契约 /
  frontend / Course Data / Planner。
- 修改文件：`backend/app/curriculum/pdf_reader.py`（仅新增修复判定）、
  `backend/tests/test_curriculum_pdf_reader.py`（新增 3 个回归用例）、
  `docs/status/curriculum.md`、`docs/worklogs/curriculum.md`、
  `docs/curriculum/PDF_TRANSCRIPT_INPUT.md`（补充"不支持需要修复的 PDF"）。
- 测试：新增回归用例——
  ① 正常成绩单 `is_repaired is False` 且仍被接受；
  ② 截断到需要修复的文件被拒绝，且错误文案**恰为**通用文案（并断言不含姓名 / 学号 /
  路径 / `.pdf` / `Traceback`）；
  ③ 多页成绩单截断同样被拒绝。
  ⚠️ **刻意不依赖 MuPDF 的告警文案**（实现细节、可能随版本变化），只依据 `is_repaired`。
  `tests/test_curriculum_pdf_reader.py` 18 → **21 passed**。
- 数据：无。⛔ 未接触、未提交任何真实成绩单；真实文件仅在本机做一次性验证
  （完整文件仍解析出 24 条 / 2 个学期；99%–90% 截断现全部被拒绝）。
- 回归：全量 **3036 tests · 3032 passed · 2 failed · 2 skipped**；
  2 failed 与 base `c75b6da` **完全相同**（已用独立 base worktree 复现并比对失败集合）。
- 尚未处理（非阻塞）：MuPDF 的 C 层诊断会绕过 Python 的告警抑制直接写到 stderr；
  已用 fd 级捕获确认其中**不含** PDF 内容 / 个人信息，本轮按指示不做抑制。

### 2026-10-07 - Case A 历史范围裁决：3 条 `2025-1~2025-2` 条目显式记为 historical
- 本次目标：修复集成评审发现的阻塞——`POST /api/v1/case-a-demo/plan` 在**批准 scoped case +
  真实成绩单 PDF** 下 500（`makeup scope: target entries have no confirmable arrangement term`）。
- 根因（已隔离证明）：`makeup_scope.as_of_term=2025-2` 使 3 条 range 条目
  （MAR116 `table:2!row:8` / PSY199 `row:9` / PUB1991 `row:10`）落入 `SCOPE_UNRESOLVED`。
  在批准基线（D4）下它们靠 **confirmed `course_id`** 走 identity 匹配才 `satisfied`；
  换用**无课程号**的成绩单 PDF 后退化为 `possibly_equivalent`，scope guard 只对
  `SATISFIED` 放行 → 抛错。三种 rules 变体（`None` / 重定向 / 单开任一 allow 标志）**均失败**，
  证明问题不在 rules，而在 **scope 依赖了 recognition**。
- 架构裁决：这 3 条区间**整体落在 `as_of_term=2025-2` 当日或之前**，故以**自身区间措辞**
  显式裁定为 `historical`（见 `CASE_OWNER_HISTORICAL_RATIONALE`）。
  ⛔ 该 decision **只回答 historical / future**：不表示课程等价、不确认课程身份、
  不构成已修认定、不使任何要求自动满足、不提供课程号。
- 实现（仅 case 数据 + 判定门，⛔ 未改算法）：
  - `case_a_decisions.py`：新增 `_CONFIRMED_HISTORICAL`（3 条）并入 `CONFIRMED_SCOPE_DECISIONS`
    （现 **7 条 = 3 historical + 4 future**，4 条 future 保持不变）；移除语义已过时的
    `SATISFIED_UNRESOLVED_NO_DECISION`（不再宣称这 3 条"无需 decision"）；
    新增 `CONFIRMED_SCOPE_DECISION_KEYS` / `LEGACY_SCOPE_DECISION_KEYS` /
    `is_supported_scope_decision_set()`。
  - 兼容窗口：已批准的私有 case artifact 是**修复前**的 4 条 decision 集合。
    `case_a_demo` 与 `planning_runtime` 改为接受"批准的 7 条集合"或"其 4 条 future 前身"，
    并在 demo runtime 内**补齐缺失的已批准 decision**（⛔ 不修改 artifact）。
    ⛔ 该窗口**不是放松**：实测"新增未批准条目"与"翻转某条方向"与"替换 evidence"仍一律拒绝。
  - 第二处缺陷：`GET /api/v1/case-a-demo/offerings?semester=<错学期>` 原为 **500**，
    现于 API 边界捕获 `CaseAScopeError` → **422** `case_a_demo_semester_not_in_scope`
    （⛔ 未削弱 provider 自身校验）。
- 修改文件：`backend/app/curriculum/case_a_decisions.py`、`backend/app/services/case_a_demo.py`、
  `backend/app/services/planning_runtime.py`（仅判定门）、`backend/app/api/case_a_demo.py`、
  `backend/tests/test_curriculum_case_a_scope_decisions.py`、`backend/tests/test_planning_runtime.py`、
  `backend/tests/test_case_a_scoped_scope_regression.py`（新）、本文件、`docs/status/curriculum.md`。
- 回归 A（批准的 D4 artifact，**case 文件未改**）：target_records **94**、completed **24**、
  group_gap_count **0**、makeup_task_count **23**、satisfied **12**、manual_confirmation **11** —
  **完全不变**。
- 回归 B（真实 PDF + 真实 South+Shenzhen SQLite）：`POST /api/v1/case-a-demo/plan` 由 500 → **200**，
  transcript_records **24**（全部 pending）、offerings **4069**（全 real）、
  makeup_tasks 23 全 `manual_confirmation`、`plan_result.status=partially_feasible`、
  `planner='actual RestrictedPlanner execution'`、`is_full_semester=false`、响应不含 `mock`。
  MAR116/PSY199/PUB1991 均 `manual_confirmation` — ⛔ **未被静默提升为 satisfied**。
- 回归 C（测试盲区）：新增 `tests/test_case_a_scoped_scope_regression.py`（**6 项**），
  fixture 携带真实 `makeup_scope` + 真实 7 条 decision + **无课程号**（`pending`）completed 记录；
  并断言该 fixture **确实需要**这些 historical decision（去掉后 3 条重新变 unresolved 且投影 fail closed），
  防止再次退化成"没有 makeup_scope"的假绿。
- 测试：全量后端 **3079 tests · 3075 passed · 2 failed · 2 skipped**；
  2 failed 仍为既有 Windows 环境差异（本分支 base 上同样失败），⛔ 非本次引入。
- 未改动（已验证 0 diff）：`schemas/`、`docs/interfaces/`、`matching.py`、`terms.py`、
  `requirements.py`、`case.py`、`planner/`、`integration/ports.py`、`models/contracts.py`、
  `course_data/store.py`、`snapshot.py`、`case_a_scope.py`、`api/plan.py`。
- 使用数据：测试全部使用自建合成 fixture；真实 PDF / DOCX / XLSX / SQLite **均未入库**。
- 需要人工确认：本次裁决是**架构授权**下的修正；`historical` 是否正确反映学校对该三条的
  真实安排窗口，仍建议负责人复核一次。
