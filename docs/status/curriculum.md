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
- **成绩单 PDF 入口（Case A 主路径）已实现**：新增 `backend/app/curriculum/pdf_reader.py`，
  把**当前已核验的中山大学本科成绩单 PDF 版面**解析成 `term` / `course_name` / `credits` /
  `grade` / `course_attribute`，再经既有 `normalize_completed_courses` 变成既有内部
  `CompletedCourse`（⛔ 未新增中间模型）。支持：四列一组横向平铺、两行表头
  （`课程名称`/`学分`/`成绩`/`课程` + `属性`）、`2025-2026学年 第X学期` 学期行、
  换行课程名、整数与一位小数学分、0–100 数字成绩与 `P`/`NP`、多学期、重复表头。
  学期行 / 每学期末 `学分 …`·`绩点 …` 汇总行 / 页脚毕业学分与平均绩点 / 审核人行
  **一律不进入**结果；版面不符、损坏 PDF、非 PDF 输入一律 **fail closed**。
- **成绩单不提供课程号，因此⛔ 不构造任何课程号**：所有记录都是
  `CourseIdStatus.PENDING` + `course_id = None`，由既有 `matching.py` 的保守语义处理
  （同名课程仍为 `possibly_equivalent` / `manual_confirmation`，⛔ 不自动抵认）。
  内部模型 `CompletedCourse` **本来就允许** `course_id = None`，所以**无契约变更**：
  ⛔ 未改 `/schemas/`（零改动）、⛔ 未改 Provider 签名、⛔ 未改 `matching.py`。
- **解析层改用 PyMuPDF 取词级坐标**（新增运行期依赖 `pymupdf>=1.24`）：已核验版面的四个
  单元格共享同一基线，而字符级回调按字体给出不同基线偏移（同一行会错位约 8 个用户单位），
  无法可靠按行归并。库缺失时 PDF 入口 fail closed 并给出明确错误，⛔ 不静默降级。
- **PDF 接入既有 case 的唯一改动**是 `case.py` 的 `completed` 新增第三个互斥键
  `{"pdf": {"path": …}}`（与既有 `records` / `xlsx` 三选一）。解析结果直接喂给
  **同一个** `build_curriculum_diff` / `project_makeup_tasks`，⛔ 没有第二套匹配逻辑。
- **新增窄接口** `POST /api/v1/completed-courses/import-pdf`（原始 PDF 字节，
  ⛔ 不用 multipart、⛔ 不读文件名；`source_id` 由内容摘要派生 `upload:pdf:sha256:…`）。
  错误码与 XLSX 入口**分离**（`completed_courses_pdf_*`），XLSX 入口
  `POST /api/v1/completed-courses/import` **保持不变**、仍是兼容的次要路径。
- **隐私**：表头以上的姓名 / 学号 / 学院 / 专业区块在解析时整体丢弃；解析结果不含姓名、
  学号、学院、专业、绩点；错误信息只含固定通用文案（⛔ 不含课程名、成绩、路径、堆栈）。
- **PDF 输入确实改变 Curriculum 分析**已有端到端证明：同一份目标方案下，成绩单 PDF 与
  空已修记录给出**不同**的投影依据（补修任务带 `pdf:` 来源引用）；同名的 `示例线性代数`
  仍是 `possibly_equivalent`（待人工确认）、目标方案有而成绩单无的课是
  `manual_confirmation`（因仍有课程号待确认的已修记录），⛔ 没有任何 `satisfied` 自动抵认。
- **解析口径与真实 D4 记录数一致**：用负责人交接的**真实**成绩单 PDF 做本地校核，
  解析出 **24 条**课程（11 条 `2025-2026学年第一学期` + 13 条第二学期），
  与既有 Case A `completed = 24` 的记录数一致（⚠️ 这不能替代 Reviewer 的逐字段验收；
  真实成绩单**不入库**，校核只在本机进行）。
- **修复过的 PDF 一律 fail closed（Reviewer 复审后的唯一修复）**：页面解析库会**成功修复**
  截断 / 损坏的 PDF 并返回（可能不完整的）内容而**不**报错——实测把真实成绩单截断到 97%
  会让第二个学期整段消失，而解析器仍"成功"返回记录。现在打开文档后**立即**检查
  `document.is_repaired`，为真则关闭文档并按既有的 `transcript: malformed PDF`
  通用文案拒绝。⛔ 未改任何匹配 / Curriculum / 接口 / Schema / Provider 语义。
  新增回归测试：正常成绩单 `is_repaired is False` 且仍被接受；截断到需要修复的文件被拒绝
  且错误文案保持通用（⛔ 不依赖 MuPDF 警告文案）；多页成绩单同样适用。
- 最新后端回归（UTF-8 模式，本分支 c75b6da 工作树）：**3036 tests · 3032 passed · 2 failed · 2 skipped**。
  两类失败均为**既有环境性差异**，与本次改动无关：ZIP 成员名中的字面反斜杠、
  以及含 `\x00` 的路径（Windows 路径语义）。⛔ 本次改动**未新增任何失败**
  （已在独立 base worktree 上复现同一组失败，失败集合完全相同）。
  本分支新增用例：PDF 解析 **21** · Case A PDF 集成 **9** · PDF 接口 **25** = **55 passed**。
- 人工 Office 文件到 Provider 的计算链路已验证。真实 D2/D3、真实规则和真实端到端结果尚未验收，官方 Word 格式仍须按实物核对映射。

## 判定时点与已知环境差异

- 本轮新增 `as_of_term` 是**输入事实**，不是学校政策结论：Case A 的真实转专业执行时点（例如是否 `2025-2`）**仍需正式证据或负责人确认**。当前 Mock 只使用人工假定的 `mock://` 依据，明确标注“不是学校转专业执行时点”。
- **推荐安排学期（`recommended_term_text`）语义未扩展**：它仍只是“培养方案建议安排在哪个学期”，不是先修关系、不是 deadline、不是学校认定规则、也不是转专业补修政策。本轮只把它用于与显式 `as_of_term` 比较。
- 课程组的 `historical_minimum_credit` 同样是**输入事实**（人工切分），不是学校政策；没有来源依据时不得自行推导。
- 环境差异（非本次改动引入）：宿主为 Windows + GBK（`cp936`）时，依赖 UTF-8 的既有用例会因解码失败报错；以 `PYTHONUTF8=1` 运行即可消除其中的解码类失败。剩余 2 项为 Windows 路径语义差异（含 `\x00` 的路径、ZIP 成员名中的字面反斜杠），既存在于本次改动之前，也与本次功能无关。

下一步：项目 Reviewer 正式审核本轮补修判定时点机制，再由负责人提供 Case A 的正式 `as_of_term` 依据；接入私下交接的完整课程列表和规则依据。仓库外的待交接 case 已接入 D4，D2/D3 课程列表仍为空并保持不完整。当前没有 Planner 实际求解实现，联调仅验证契约传递。
