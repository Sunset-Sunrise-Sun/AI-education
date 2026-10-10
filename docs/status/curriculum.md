# Curriculum 当前状态

更新日期：2026-10-08（Final Upgrade · Agent A 补充）。状态：文件导入与结构化输入的 Mock MVP 已合入 main；**补修判定时点（historical makeup scope）**内部机制待 Architecture Review；本轮在分支 `feature/personal-planning-pipeline` 上新增**受核验培养方案目录读取器**（`backend/app/curriculum/catalog.py`），同样待 Architecture Review。

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
- **已消耗的确定性匹配不再进入名称候选池**：一个 completed record 一旦被确定性的 exact/identity match 消耗，就从**后续的模糊名称候选池**中移除（`_candidate_records(..., consumed)`，按 `(source_id, source_record)` 稳定标识）。**未解析身份的 record 永不被消耗**，仍可作名称候选；`ConfirmedRecognition` 走自己的路径、不触发消耗；identity 匹配本身不受影响。该规则**不是**「一条记录永远只能匹配一个目标」的通用约束，只处理「确定性确认匹配 → 退出后续模糊池」。真实 Case A：`PE201/PE202/PE305/PE302` 不再由 D4 `PE102` 产生误报。
- 判定时点必须由输入显式给出并带来源依据，**不使用系统当前日期**，也不从 deadline、先修或其他字段推断；`evidence` 会进入任务 `source_evidence`，保持可追溯。
- 公共输出仍为 `MakeupTask[]`，公共契约未修改；`MakeupScope`、`ConfirmedScopeDecision`、`ConfirmedGroupScopeDecision` 均属 Curriculum 内部对象，Provider 签名、Integration 与 Planner 均不感知。
- 自动测试使用合成数据；真实 D4 本地读取及独立逐字段核对已通过。真实文件和逐行输出不入库。
- **DOCX 导入支持两种显式模式**：原有 `header` 模式（要求 `header_row` + 逐字匹配的 `expected_headers`）行为**完全未变**；新增 `positional` 模式用于**没有列标题行**的真实培养方案（`data_start_row` + 位置式 `columns`）。两种模式字段互不混用，未知文档 / 无 profile / header 模式读无表头文档一律 reject，**没有自动回退**。
- **Gate F：通用已修课程 XLSX 摄取入口（✅ 已实现，backend only）**：
  `POST /api/v1/completed-courses/import` 接受**原始 .xlsx 字节**（⛔ 不用 multipart、⛔ 不读文件名），
  在媒体类型 / `Content-Length` / 大小上限 / 空文件校验之后交给**既有的**
  `load_completed_courses_xlsx`（worksheet 抽取 + 字段映射 + 结构校验）与
  `normalize_completed_courses`；返回归一化统计与**可直接回灌 case `completed` 的 `records` 片段**。
  ⛔ 本 Gate **未新增**任何 Curriculum Diff / 等价性 / 认定 / 优先级 / 先修判断
  （`matching.py` 未改）；⛔ 未改 public Schema（新响应模型定义在 API 模块内）；
  ⛔ **未接入**已冻结的 Case A fixed-case runtime（有回归测试锁定 runtime 源码不含上传适配器）；
  ⛔ 不回传 `备注` 自由文本；⛔ 不执行公式 / 宏；临时文件在请求结束无条件删除。
  详见 `docs/data/XLSX_COMPLETED_COURSES_IMPORT.md`。
- **positional 模式的结构守卫**：行宽必须覆盖全部映射列；数据行物理列不得超过声明的 `column_count`（学校改版整体移列时失败而非错列读取）；`identity` 锚点必须在指定（已映射）列命中；横向合并覆盖映射列时失败。`course_name_lines` 显式声明双语名称单元格保留前 N 行。
- **行选择 fail closed（不得成为绕过结构校验的旁路）**：先由 `row_kind` 判别器（仅支持 numeric）判定是否为课程行，再判结构 —— 判别器不命中 → 明确非课程行 skip；判别器命中但 selector 列物理缺失 → 结构损坏，fail closed；判别器命中且全部 selector 命中 → 进入完整结构校验；判别器不命中但**其余 identifying selectors 全部命中**（course_id 有值且 credit 为数字）→ 视为**判别器本身损坏**，**fail closed**（不得 skip）；只有判别器不命中且其余 selectors 未全部命中才是真实分区行可 skip。单元格"存在但为空"与"物理缺失"在 positional 下语义相同。selector 只能读标识性列（`course_id` / `credit` / `recommended_term_text` / `sequence`），映射到可选列的 selector 直接拒绝。真实 Case A selector = `sequence` numeric + `course_id` nonempty + `credit` numeric。
- **真实 Case A 两份培养方案现已可导入**：`遥感方案.docx` 84 条课程条目、`网安方案.docx` 94 条，均 0 issue，可转成 `CurriculumVersion`。声明式 profile 见 `backend/app/curriculum/plan_profiles.py`（不含真实文件、路径或隐私字段）。真实文档仍在受控本地，未入库。
- **真实目标方案（网络空间安全）选修组已按原文确认为单一池**：table 6 `（专业选修课）` 37 门 / 课程学分 86，方案给出主修应修专选 **23**（table 7 合计行，table 1 / table 10 独立重复）→ 建模为 `group_id = CSE-ELECTIVE-POOL`、`minimum_credit = 23`，37 门课全部 `requirement=elective` 且带该 `group_id`；六个 banner 分区仅为展示，不生成独立组、不拆 23。声明见 `plan_profiles.plan_group_records("target")`，`source_record = table:7!row:2`。
- **荣誉课程（table 8）不再作为普通主修 requirement 导入**：原文 `（荣誉课程）`、table 9 合计应修 **0** 学分；其 8 门课在 table 4 已是专业课，`CS5701/CS5702` 只从选修池导入一次 → 目标版本无重复 course_id，也**未**创建 `minimum_credit=0` 的假组。
- **真实 Case A 投影现状**：target courses 94（elective 37）、groups 1（`CSE-ELECTIVE-POOL`，23，37 名成员）、`unrepresented_requirements = ()`（**选修组阻断已消除**）。原先的 **7 条区间学期 scope unresolved 阻断现已全部解除**（4 条由 case owner 明确 decision，3 条本就 satisfied 不阻断，见下条）。satisfied 12 / possibly_equivalent 0 / manual_confirmation 82。
- **真实 Case A 区间学期 decision 已全部落为 case 数据**：7 条 range-term entry 中，**3 条**（MAR117 `2026-1~2026-2`、MAR118 `2027-1~2027-2`、MAR119 `2028-1~2028-2`）区间整体在 `as_of_term=2025-2` **之后** → 记为 `future`；**1 条横跨时点**（PUB178 劳动教育 `2025-1~2028-2`）**亦由 case owner 裁定为 `future`**（见下条）；**3 条已 satisfied**（MAR116 / PSY199 / PUB1991，区间 `2025-1~2025-2`）按冻结语义**不阻断、无需 decision**。即：**4 条 decision + 3 条 satisfied 不阻断 = 无遗留待业务确认项**。decision 定义见 `backend/app/curriculum/case_a_decisions.py`（纯 case 数据，不含姓名/学号/成绩/GPA/私有文档；evidence 为 `case-owner-confirmed://…`，非学校官方政策）。
- **PUB178 横跨区间已由 case owner 裁定为 `future`**：理由为该方案安排窗口横跨 `as_of_term=2025-2` 且持续至 2028-2，无证据表明必须在转专业时点前完成、也无阶段性拆分规则；为避免把仍有后续履行窗口的要求误判为历史欠修，本 Case 按 future 处理。该裁决**仅是 case-owner-confirmed 的 Case A 输入**，未升级为通用 scope 算法或学校官方政策（见 `case_a_decisions.CASE_OWNER_FUTURE_RATIONALE`）。
- **真实 Case A 已首次打通**：target_records 94、completed 24、historical 20、future 71、unresolved 3（均为已 satisfied 的 range 条目，按冻结语义不阻断）、`unrepresented_requirements = ()`、`group_gaps = ()`、**projection_ready = True**、`get_makeup_tasks()` 成功返回 **makeup_task_count = 23**（satisfied 12 / manual_confirmation 11 / required 0 / possibly_equivalent 0；总学分 58，其中 satisfied 32、manual_confirmation 26）。23 条全部为 historical 条目，future unmet 条目不出现在 `MakeupTask[]` 中。
- 最新后端回归：**2032 passed、2 failed、2 skipped**（UTF-8 模式）。两类失败均为既有环境性差异，与本次改动无关，详见下方说明。
- 人工 Office 文件到 Provider 的计算链路已验证。真实 D2/D3、真实规则和真实端到端结果尚未验收，官方 Word 格式仍须按实物核对映射。

## Final Upgrade · Agent A（2026-10-08，分支 `feature/personal-planning-pipeline`）

- **新增受核验培养方案目录读取器** `backend/app/curriculum/catalog.py`：从调用方**显式给出**的本地
  artifact 读取"可选版本"元信息（年级 / 校区 / 方向 / 来源 / 核验依据 / 课程数 / 学分等），
  并复用既有 `normalize_curriculum_version` 构造 `CurriculumVersion`。
  - ⛔ **不扫描文件系统找默认目录**、⛔ 不联网、⛔ 不读数据库、⛔ 不读 `mock_data`；
  - ⛔ **不解析 docx**：artifact 只能给出**既有 reader 已支持**的结构化 course records；
    Word 培养方案的读取仍走既有 `app.curriculum` 入口，本模块不为个人入口另造解析路径；
  - `verification.verified != true` → `not_verified`；`supported=false` → `unsupported_by_source`；
    同一 `version_id` 出现多次 → `version_identity_conflict`；形状 / 记录非法 → `entry_invalid`；
    artifact 缺失 → **空目录（不是异常）**；`catalog_version` 未知 → `artifact_format_unsupported`
    且⛔ 不做向前兼容解析；
  - 目录只暴露**可选**版本；`resolve()` 对不可选版本抛错，⛔ **不回退到 Case A / 第一个版本 / 任何默认值**；
  - 目录 artifact 格式（`catalog_version` / `versions[]` / `verification`）是**本模块内部声明**，
    ⛔ 不是公共 Schema。
- **新增个人规划入口**（模块 `backend/app/personal/`，非公共契约）：
  - `normalize_student_input(...)`：把"这一位学生"的输入归一化成显式对象；
    `completed_source_id` 由**调用方**给出，⛔ 不取学生行里的来源字段；
    全部认定 / 缺课记录必须属于本人来源，否则拒绝；
  - `build_personal_plan(...)`：组装**本学生**的 `CurriculumCase` 并复用既有
    `CurriculumCaseProvider.get_makeup_tasks()`；可选接入**已冻结的** `PlannerProvider.plan(...)`
    四参数签名（⛔ 不新增参数、⛔ 不复制 Planner 逻辑）；
  - `planning_assumptions` 是**明确标注的规划假设**（`planning_assumption_not_a_recognition`）：
    ⛔ 绝不改变任何 `MakeupTask.status`，只作为待人工核验依据出现在结果说明里。
- **公共输出 / 契约**：仍只有既有 `MakeupTask[]`（`CourseMatch.status` 语义
  `required / possibly_equivalent / manual_confirmation / satisfied` 一字未改）；
  `/schemas/` 与 `/docs/interfaces/` **未修改**；`CurriculumProvider` 签名未改。

## 判定时点与已知环境差异

- 本轮新增 `as_of_term` 是**输入事实**，不是学校政策结论：Case A 的真实转专业执行时点（例如是否 `2025-2`）**仍需正式证据或负责人确认**。当前 Mock 只使用人工假定的 `mock://` 依据，明确标注“不是学校转专业执行时点”。
- **推荐安排学期（`recommended_term_text`）语义未扩展**：它仍只是“培养方案建议安排在哪个学期”，不是先修关系、不是 deadline、不是学校认定规则、也不是转专业补修政策。本轮只把它用于与显式 `as_of_term` 比较。
- 课程组的 `historical_minimum_credit` 同样是**输入事实**（人工切分），不是学校政策；没有来源依据时不得自行推导。
- 环境差异（非本次改动引入）：宿主为 Windows + GBK（`cp936`）时，依赖 UTF-8 的既有用例会因解码失败报错；以 `PYTHONUTF8=1` 运行即可消除其中的解码类失败。剩余 2 项为 Windows 路径语义差异（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），既存在于本次改动之前，也与本次功能无关。

下一步：项目 Reviewer 正式审核本轮补修判定时点机制，再由负责人提供 Case A 的正式 `as_of_term` 依据；接入私下交接的完整课程列表和规则依据。仓库外的待交接 case 已接入 D4，D2/D3 课程列表仍为空并保持不完整。当前没有 Planner 实际求解实现，联调仅验证契约传递。

## 下一步（Final Upgrade · Agent A）

- 负责人确认 `APP_PERSONAL_CATALOG_DIR` 指向的**真实**已核验目录内容：目录 artifact 必须由
  负责人（或已批准工具）产出并逐条声明 `verification.evidence`；⛔ Builder 不自行批准任何版本。
- 目录 artifact 的字段设计（`campus` / `track` / `verification` 等）需要项目 Reviewer 确认
  是否作为**长期内部格式**保留；本轮它只被 `app/curriculum/catalog.py` 读取，
  ⛔ 未进入 `/schemas/` 或 `/docs/interfaces/`。
- 本轮全部验证使用**人工构造 Mock**（`backend/tests/personal_fixtures.py`）：
  **当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**

## 真实能力接入第一阶段：DOCX → 目录草稿（2026-10-09）

- 新增 `backend/app/curriculum/catalog_draft.py`（**纯序列化**，⛔ 不重写 DOCX 解析、⛔ 不判定核验）
  与薄 CLI `backend/tools/build_catalog_draft.py`：把培养方案 DOCX 转成
  ① 审核中间格式（来源文件 / 原始条目 / 证据 / 待确认清单），② `verification.verified=false` 的目录草稿。
- **硬边界**：`verified` 与 `complete` 在序列化层**硬编码为 false**（函数签名里没有开关）；
  解析器不推断的字段（`recommended_semester` / `deadline_semester` / `prerequisites`）
  一律进 `human_required` 清单；未确定的行进 `unresolved_rows`，⛔ 不丢弃、⛔ 不猜值。
- **安全性**：草稿即使被放进 `APP_PERSONAL_CATALOG_DIR` 也会被 `catalog.py` 判为
  `not_verified` 而**不可选**（fail closed，不是"半可用"）——已有可执行断言。
- 新增 `backend/tests/test_catalog_draft.py`（8 项，全部使用**合成** DOCX，⛔ 真实培养方案不进仓库）。
- ⛔ 未修改 `docx_reader.py` / `plan_profiles.py` / `catalog.py` / `requirements.py` / `__main__.py`。
- 仍未验证：真实培养方案 DOCX 不在仓库内，本工具**从未**在真实文档上运行过。
- 详见 `docs/final_upgrade/DOCX_CATALOG_DRAFT.md`。

## 来源可信性门：catalog 的 verified 不再自述生效（2026-10-10）

- `verification.verified=true` 从此**只是自述**：`load_curriculum_catalog(..., approved_versions=...)`
  要求 `version_id` 出现在**带外批准锚点**（`APP_TRUST_ANCHOR_PATH`）里，
  否则以**新拒绝码 `provenance_not_verified`** 拒绝（与 `not_verified` 区分：
  后者是"文件自己说没核验"，前者是"自称核验却拿不出独立依据"）。
- production 路径 `services/personal_runtime.py::load_personal_catalog` **必须**读锚点；
  缺锚点 ⇒ `provenance_not_verified`；锚点无 `curriculum_catalog` 记录 ⇒ `catalog_provenance_empty`。
  API 侧新增独立错误码 `personal_catalog_provenance_not_verified`（503），
  与"没配置目录"区分开。
- `approved_versions=None` 仍保留旧的"只按自述"行为，**仅供单元测试**；
  ⛔ production 调用点已全部传集合。
- ⛔ 未修改 `/schemas/**`、`docs/interfaces/**`、`requirements.py` 的公共形状。
- 详见 `docs/final_upgrade/TRUST_ANCHOR_DESIGN.md`、`PROVENANCE_GATE_CLOSURE.md`。

## 培养方案 PDF 导入（2026-10-10，`feature/pdf-curriculum-import`）

**先交付复用面报告**：`docs/final_upgrade/PDF_IMPORT_REUSE_REPORT.md`（§1 可复用、§2 必须新写、§3 新接口、§5 未验证项）。
**验收报告**：`docs/final_upgrade/PDF_IMPORT_ACCEPTANCE_REPORT.md`。

一句话结论：**DOCX 链的下游 100% 复用；只有"PDF 字节 → 表格单元格"必须新写**。

### 交付

| 层 | 文件 |
| --- | --- |
| 解析 | `app/curriculum/pdf_reader.py`（PDF → **既有** `DocxImportResult`） |
| 传输与安全 | `app/services/curriculum_pdf_ingest.py` |
| HTTP | `app/api/curriculum_import.py`（`POST /api/v1/curriculum-import/parse-pdf`，模块内私有包络） |
| CLI 取证 | `tools/parse_curriculum_pdf.py`（产出解析准确性报告 + 未识别课程清单） |
| 前端 | `components/CurriculumPdfImport.vue` + `api/curriculumImport.ts` + `config.ts` 开关 |
| 依赖 | `requirements.txt` 新增 `pymupdf>=1.24`（已获架构负责人许可） |

### 硬边界如何被结构性保证

- **⛔ 不从课程名猜课程号**：只读声明列位/表头；缺失即 `unresolved_course_id`；源码里无任何别名/推断（测试断言）。
- **⛔ 不用成员学分求和猜组学分**：PDF **完全不产出** `group_records`，且进 `human_required`；`project_makeup_tasks` 在 `minimum_credit is None` 时 raise。
- **⛔ 不自动判定跨专业等价**：不产出任何等价关系。
- **默认 `verified=false` / `complete=false` / `approval=pending`**：`draft_to_catalog_payload` 硬编码 + 响应 `is_official_school_pdf: false` 硬编码。
- **⛔ 上传不写 `APP_PERSONAL_CATALOG_DIR` / 不写批准锚点**：端点只返回内存 payload；测试断言运行后目录为空、锚点不存在。
- **扫描件**：`scanned_pdf_text_layer_missing` 式 fail closed，明确"不支持 + 转人工"，⛔ 不 OCR。

### 测试

- 后端新增 `tests/test_curriculum_pdf_reader.py`、`tests/test_curriculum_pdf_upload_api.py`（含自建**最小 PDF 生成器** `tests/pdf_fixtures.py`，⛔ 未引入第二个库）。
- 前端新增 `tests/curriculum-pdf-import.spec.ts`（契约 + 边界文案 + "⛔ 不降级"）。
- E2E 新增 `L11-curriculum-pdf-import-entry`；live 档打开 `VITE_CURRICULUM_IMPORT_API_ENABLED`。
- 路由白名单测试登记新端点（`test_integration_orchestrator.py`）。

### ⚠️ 实测发现（写进夹具注释，供后续参考）

`find_tables()` 对合成 PDF 有三个静默丢数据的行为：① 无表格线 ⇒ 识别不出表；
② 列间距太小 ⇒ 相邻列并成一格；③ 表线超出页面 / 贴太近 ⇒ **最后一列或最后一行被丢掉**。
夹具已按这些约束构造，且**测试断言"画出多少行就必须读出多少行"**，因此这些行为一旦变化会立刻暴露。

### 【BLOCKED】真实材料验收

两份 PDF（遥感 2025级 8页、网络空间安全 2025级 9页）**在本机不存在**（已整机搜索）。
真实材料相关的 5 项验收保持 BLOCKED；放置目录与执行步骤已备好
（见验收报告 §5）。⛔ 未用合成数据冒充真实验收结果。

### 第 2 轮（2026-10-10）真实文件验收
- **BLOCKED**：两份真实 PDF（遥感 8 页 / 网络空间安全 9 页）仍不在本机
  （`real-curriculum-pdf\` 为空；C:/D: 全盘按精确文件名搜索未找到）。⛔ 未用合成数据冒充。
- 真实验收的全部程序性前提已就绪：逐页结构检查（`--inspect`）、双行表头/合并单元格/
  分页/不同列数的声明式 profile、许可证评估、执行手册。
- **已修复真实缺陷**：`extract()` 行序与页面阅读顺序相反 ⇒ `page:{n}!row:{i}` 曾指错行。
  改为按 `table.rows[i].bbox` + `table.header.cells` 重建网格，几何不可用时 fail closed。
- 材料到位后：`python tools/parse_curriculum_pdf.py --pdf <路径> ... --inspect`
  再按输出写 `--profile`，步骤见 `docs/final_upgrade/PDF_IMPORT_REAL_ACCEPTANCE.md`。