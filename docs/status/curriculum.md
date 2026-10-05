# Curriculum 当前状态

更新日期：2026-10-05。状态：文件导入与结构化输入的 Mock MVP 已合入 main；本轮新增**补修判定时点（historical makeup scope）**内部机制，待 Architecture Review。

- Case A 已选定。D4 脱敏表已私下交接，D2/D3 完整方案待私下交接。
- 已实现内部 `CompletedCourse`、规范化和 XLSX 只读入口。待确认 ID 保留为空。
- 已实现结构化培养方案、课程组、汇总学分、候选匹配、Diff 和公共结果适配。
- Word 表格按明确的列映射和行范围读取，保留来源定位及问题草稿，未知课程号不补造。case 可组合本地 Word 和 D4 文件。
- case 规则有明确来源时，完全匹配和明确缺修可自动判断；模糊等价、学分差异及未知身份保留待确认。
- Provider 绑定输入 context，未知先修以待确认任务返回，不整批停止。签名未改。
- 已有人工输入、可复现任务输出和内部学业问题/依赖分析；优先顺序仅在显式策略和充分依据下生成，不传给 Planner。
- 平面组由已有必修任务和有依据的选修选择表达，实际学分缺口仍保留。必修容量不足且剩余选修未选择、计划不足或未知组额度时阻断投影；跨组抵扣和复杂组合未支持。
- 缺修输出保留完整性依据。重复课程号的明确先修边不会被覆盖；来源顺序策略不依赖未知期限。内部报告保留学分汇总、组容量及期限链问题。
- 私有检查命令只输出统计，待确认或无法投影的 case 也可检查内部问题。
- **新增补修判定时点（makeup scope）**：case 可显式给出 `makeup_scope`（`target_version_id` / `as_of_term` / `evidence`），只用于回答“历史缺口判定到哪个学期为止”。目标培养方案中安排在该时点**之后**的课程属未来正常培养计划，默认不进入 `MakeupTask[]`；**时点之前或当期**的未满足要求仍按原有匹配逻辑判定。该机制只在显式提供时生效，未提供时保持原有 generic curriculum-diff 行为。
- 学期比较只接受已确认的 `YYYY-1` / `YYYY-2` 形式（严格解析，不裁剪空白）。区间（如 `2025-1~2025-2`）、未知、空值、异常格式一律**不猜**：对应课程标为 unresolved 并**阻断投影**，要求人工给出明确范围决定。边界包含当期（`as_of_term` 本身算 historical）。
- **逐条人工范围确认**：`confirmed_scope_decisions` 以 `target_source_record`（具体 requirement entry，不是 `course_id`）为主键，`decision` 只允许 `historical` / `future`，`evidence` 必填并写入任务 `source_evidence`。它**只能解除 parser 无法确认的 unresolved**；针对可自动解析的单学期条目会被判为冲突并报错，**不静默覆盖来源事实**。重复 decision、未知条目、版本不匹配、课程号不一致、额外字段、Real case 混入 `mock://` 均拒绝。
- **scope 判定全程按 requirement entry**：`scope_bucket_for_entry` / `scope_evidence_for_entry` / `unresolved_scope_entries` 以及投影、组计算、evidence 传播全部以 `source_record` 为键，**不存在按 `course_id` 的 scope 查询入口**。同一 course_id 的多条 entry 可分别为 historical / future，分类与依据都不会串线；解除其中一条不会连带解除另一条。
- **future 过滤只作用于未满足/待确认项**：`satisfied` 条目无论 historical / future / unresolved 都**保持原有输出语义**（仍输出 satisfied），不再因 scope 被隐藏；`required` / `possibly_equivalent` / `manual_confirmation` 等未满足项在 future 时不输出，unresolved 时继续 fail closed。
- **课程组已 scope-aware**：组内成员全在未来范围 → 不构成历史要求，**不阻断**历史投影；全在历史范围 → 保持原有严格组规则；历史与未来混合 → **不做任何比例/学分推导切分**，默认阻断并要求人工明确 `confirmed_group_scope_decisions.historical_minimum_credit`（只表示历史部分额度，须能被历史成员学分总量满足且只适用于 mixed 组）。
- **组历史额度只由历史事实覆盖**：mixed 组的 `historical_minimum_credit` **只能**由 bucket 为 `historical` 的组成员覆盖；**future 成员一律不参与**，无论 satisfied / required / selected / manual_confirmation / possibly_equivalent。判定入口为 `group_plan_covers_requirement(diff, group_id)`，不只体现在 `GroupGap.remaining_credit`。
- **组决策依据精确传播**：`confirmed_group_scope_decisions[].evidence` 只附加到该组内**本身属于历史范围**的已输出任务（按 `target.group_id` + entry bucket）；同一组的 future 任务、其他组、其他课程或无组课程都不会带上该依据。
- **组缺口 reason 区分是否已有 split**：mixed 组无 split → "历史学分要求无法从来源分割，需人工确认"；已有 split 但历史学分仍不足 → "历史额度已经确认，但仍存在未满足学分"。
- 判定时点必须由输入显式给出并带来源依据，**不使用系统当前日期**，也不从 deadline、先修或其他字段推断；`evidence` 会进入任务 `source_evidence`，保持可追溯。
- 公共输出仍为 `MakeupTask[]`，公共契约未修改；`MakeupScope`、`ConfirmedScopeDecision`、`ConfirmedGroupScopeDecision` 均属 Curriculum 内部对象，Provider 签名、Integration 与 Planner 均不感知。
- 自动测试使用合成数据；真实 D4 本地读取及独立逐字段核对已通过。真实文件和逐行输出不入库。
- **DOCX 导入支持两种显式模式**：原有 `header` 模式（要求 `header_row` + 逐字匹配的 `expected_headers`）行为**完全未变**；新增 `positional` 模式用于**没有列标题行**的真实培养方案（`data_start_row` + 位置式 `columns`）。两种模式字段互不混用，未知文档 / 无 profile / header 模式读无表头文档一律 reject，**没有自动回退**。
- **positional 模式的结构守卫**：行宽必须覆盖全部映射列；数据行物理列不得超过声明的 `column_count`（学校改版整体移列时失败而非错列读取）；`identity` 锚点必须在指定（已映射）列命中；横向合并覆盖映射列时失败。`course_name_lines` 显式声明双语名称单元格保留前 N 行。
- **行选择 fail closed（不得成为绕过结构校验的旁路）**：先由 `row_kind` 判别器（仅支持 numeric）判定是否为课程行，再判结构 —— 判别器不命中 → 明确非课程行 skip；判别器命中但 selector 列物理缺失 → 结构损坏，fail closed；判别器命中且全部 selector 命中 → 进入完整结构校验；判别器命中但 selector 部分命中 → **fail closed，不得 continue**。selector 只能读标识性列（`course_id` / `credit` / `recommended_term_text` / `sequence`），映射到可选列的 selector 直接拒绝。真实 Case A selector = `sequence` numeric + `course_id` nonempty + `credit` numeric。
- **真实 Case A 两份培养方案现已可导入**：`遥感方案.docx` 84 条课程条目、`网安方案.docx` 104 条，均 0 issue，可转成 `CurriculumVersion`。声明式 profile 见 `backend/app/curriculum/plan_profiles.py`（不含真实文件、路径或隐私字段）。真实文档仍在受控本地，未入库。
- 最新后端回归：**1991 passed、2 failed、2 skipped**（UTF-8 模式）。两类失败均为既有环境性差异，与本次改动无关，详见下方说明。
- 人工 Office 文件到 Provider 的计算链路已验证。真实 D2/D3、真实规则和真实端到端结果尚未验收，官方 Word 格式仍须按实物核对映射。

## 判定时点与已知环境差异

- 本轮新增 `as_of_term` 是**输入事实**，不是学校政策结论：Case A 的真实转专业执行时点（例如是否 `2025-2`）**仍需正式证据或负责人确认**。当前 Mock 只使用人工假定的 `mock://` 依据，明确标注“不是学校转专业执行时点”。
- **推荐安排学期（`recommended_term_text`）语义未扩展**：它仍只是“培养方案建议安排在哪个学期”，不是先修关系、不是 deadline、不是学校认定规则、也不是转专业补修政策。本轮只把它用于与显式 `as_of_term` 比较。
- 课程组的 `historical_minimum_credit` 同样是**输入事实**（人工切分），不是学校政策；没有来源依据时不得自行推导。
- 环境差异（非本次改动引入）：宿主为 Windows + GBK（`cp936`）时，依赖 UTF-8 的既有用例会因解码失败报错；以 `PYTHONUTF8=1` 运行即可消除其中的解码类失败。剩余 2 项为 Windows 路径语义差异（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），既存在于本次改动之前，也与本次功能无关。

下一步：项目 Reviewer 正式审核本轮补修判定时点机制，再由负责人提供 Case A 的正式 `as_of_term` 依据；接入私下交接的完整课程列表和规则依据。仓库外的待交接 case 已接入 D4，D2/D3 课程列表仍为空并保持不完整。当前没有 Planner 实际求解实现，联调仅验证契约传递。
