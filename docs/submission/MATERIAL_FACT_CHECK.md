# 学航·转衔 · 材料事实核对表（真实性守门文件）

> **这是整套提交材料里最重要的一份。**
> 任何对外材料、PPT、宣传页、演示话术，写完之后都要拿这份表逐条对照。
> 本表只回答一个问题：**这句话有没有实现证据。**
>
> 本版已按**最终产品 / RC HEAD `56013e5`** 更新：补修确认为**逐条操作**，页面底部只有**一个统一提醒区**，
> 专业选修候选不再截断，课表业务类别标签改为**仅有依据时出现**。

## 核对基线

| 项 | 值 |
|---|---|
| 材料分支 | `docs/opc-submission-package` |
| **产品事实基线 HEAD** | **`56013e5108b53ee7d663a8577dd687946c366c36`** |
| **最终 RC HEAD** | **`56013e5108b53ee7d663a8577dd687946c366c36`**（`release/case-a-path-planning-rc`） |
| 产品评审状态 | **独立评审 = PASS；最终 RC 验证 = PASS** |
| 历史基线（已被取代） | `7a7bb9d` → `0cd91dc` → `95976ae` → `db7d172` → 本版 `56013e5` |
| 核对时间 | 2026-10-07 |
| 核对方式 | 逐条对照产品基线的代码、状态文档、演示手册与最终 RC 验证记录 |

> ✅ **产品与 RC 已定稿**：RC 分支 `release/case-a-path-planning-rc` 指向 `56013e5`。
> 本轮交付的截图全部基于 `56013e5` 重拍；基于 `db7d172` 的上一版截图已作废并替换。

## 三档标记的含义

| 标记 | 含义 | 材料里怎么用 |
|---|---|---|
| **VERIFIED** | 在产品事实基线上有代码或实测证据，可以直接写真话 | 可以自由润色语气，但事实不能改 |
| **CONDITIONAL** | 尚未最终确认（评审 / 数值 / 素材） | 可以说，但必须加限定语，或等确认后再定稿 |
| **DO NOT CLAIM** | 没有证据，或与实现方向相反 | ⛔ 任何材料、任何场合都不要说 |

---

# 一、VERIFIED

## 1. 定位与用户

| 主张 | 证据 |
|---|---|
| 项目定位为"学航·转衔：面向转专业学生的 AI 学业路径重构 Agent" | `AGENTS.md` 第 1 节项目目标；`docs/ARCHITECTURE.md` §1 |
| 主要用户是转专业学生，次要用户是辅导员 / 教务人员 / 学院负责人 | `docs/ARCHITECTURE.md` §1；`AGENTS.md` §1 |
| 产品不定位为通用选课助手、课程问答机器人、教务系统替代品 | `docs/ARCHITECTURE.md` §1（不把通用四年选课、延毕预测纳入 MVP） |
| 用户痛点：培养方案差异难自查、补修判定涉及正式规则、供给与课表约束叠加、结论不易解释 | `docs/ARCHITECTURE.md` §1–2；`AGENTS.md` §1 核心流程 |

## 2. 数据范围与来源

| 主张 | 证据 |
|---|---|
| 使用**真实**教学班数据（`CourseOffering`） | 产品基线 `docs/status/integration.md`（真实 artifact smoke：4069 条真实教学班） |
| 数据条数为 **4069 条 `CourseOffering`** | `docs/status/integration.md`：south-campus 2898 rows + shenzhen-campus 1171 rows = **4069** |
| 数据范围是**南校园 + 深圳校区** | `backend/app/course_data/case_a_scope.py` `CASE_A_SCOPE_LABEL = "case-a-scoped:south+shenzhen"` |
| 该数据集是 case-scoped，**不是**完整学期数据，**不是**全校数据 | 同上，`is_full_semester = false`、`is_whole_school = false` |
| 学期为 `2026-1` | 演示手册 `APP_CASE_A_DEMO_SEMESTER="2026-1"`；`docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` |
| 系统不联网抓取教务系统，使用本地已验收数据 | `docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` E3 |
| 成绩单中的姓名、学号、绩点不读取、不返回 | `docs/curriculum/PDF_TRANSCRIPT_INPUT.md` 隐私边界表；验收清单 A1、E1 |
| 页面与请求中不出现 Cookie / Token / 学号 | 验收清单 E1；评审记录（diff 扫描无凭据、无私有材料） |

## 3. 培养要求评估（最关键的数字口径）

| 主张 | 证据 |
|---|---|
| 真实投影产出 **23 项历史培养要求评估** | `docs/status/curriculum.md`（`makeup_task_count = 23`） |
| 其中 **12 项已确认满足** | 同上（`satisfied 12`） |
| 其中 **11 项需要人工确认** | 同上（`manual_confirmation 11`） |
| 另有 0 项"已确认需补修"、0 项"可能等价" | 同上（`required 0 / possibly_equivalent 0`） |
| 这 23 项全部是历史范围条目，未来未满足条目不出现在评估结果里 | 同上 |
| 培养要求状态互不等同，`待人工确认` ≠ `需要补修` | `docs/interfaces/curriculum.md`；验收清单 A2 |
| 课程等价、学分差额、学院政策、条款歧义一律待人工确认，系统不下正式结论 | `docs/interfaces/curriculum.md`；`docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §4.0.1 |
| 目标专业**选修组最低学分要求为 23 学分** | `docs/status/curriculum.md`（`CSE-ELECTIVE-POOL`，`minimum_credit = 23`，37 门成员） |
| 12 项已满足事实来自已确认的培养方案事实，**不依赖**上传成绩单的课程号 | `docs/status/integration.md`（成绩单 PDF 无官方课程号，已满足事实不依赖 `CompletedCourse.course_id`） |

## 3.1 规划层确认（本轮新增能力）

| 主张 | 证据 |
|---|---|
| 用户可以对**待人工确认**项做**规划层确认**，系统据此重新计算学业方案 | `frontend/src/components/MakeupTaskList.vue`（`makeup-confirm-panel`、`makeup-select-*`、`makeup-confirm-submit`） |
| 界面逐字披露：**基于你的确认**、**仅用于本次规划**、**不是学校官方认定结果** | 同上，`DEFAULT_DISCLOSURE` 与确认标题、确认面板首句 |
| 确认后该项在**本次规划**里按已满足处理，并有明确标记 | `makeup-confirmed-title`「本次规划已确认满足（N 项）」；`makeup-user-confirmed-*` 标记 |
| 确认可**撤销**，且由**同一个按钮**承担：确认成功后按钮文案变为「✓ 已确认」 | `makeup-undo-*`；`confirmationLabel()` 返回 `row.confirmedByUser ? '✓ 已确认' : '确认可转换'` |
| 用户确认**不会**改写 source-backed 基线（23 / 12 / 11 不变） | Issue #61 最终验证：`SOURCE ASSESSMENT = 12 satisfied / 11 manual_confirmation (12/11: True)` |
| 逐条确认按钮需显式点击，且只在待确认行出现；确认后同一按钮转为撤销入口 | `确认可转换` → `✓ 已确认`；`makeup-confirm-<course>` / `makeup-undo-<course>` |
| 被服务端**拒绝**的确认会如实显示，且不会变成不可撤销的隐形意图 | Issue #61 最终 blocker 修复（`reconcilePlanningIntent`）；`case-a-rejected-confirmations` |

> ⛔ **不得写**：AI 自动认定课程等价 / 系统自动批准补修认定 / 学校已经确认。
> 规划确认是**用户的规划假设**，只作用于本次规划，可撤销。

## 3.2 本学期专业选修交互（本轮新增能力）

| 主张 | 证据 |
|---|---|
| 系统从当前学期**真实教学班**中筛出可行候选，用户明确选择后加入本学期规划 | `frontend/src/components/CurrentElectiveSection.vue`（`case-a-current-electives`、`elective-add-*`） |
| 只有服务端确认无冲突（**CLEAR**）的教学班可以加入 | 同上，`clearSections()` 只接受服务端给出的 `clear_class_ids`；Issue #61「exact server-issued CLEAR class ids only」 |
| **唯一 CLEAR** 可直接作为建议教学班加入（仍需显式点击） | `item.unique_clear_class_id` 分支；按钮文案「加入本学期方案」 |
| **多个 CLEAR** 必须由用户显式选择教学班，系统不自动挑 | `elective-multi-clear-hint`；`elective-section-<course>-<class>` 选择项 |
| **只有 UNKNOWN / CONFLICT** 时不提供加入按钮，并说明原因 | `elective-blocked-reason` |
| 已加入显示「已加入本学期方案」，且加入按钮文案变为「✓ 已加入，可撤销」，点它就是撤销 | `elective-applied`、`elective-applied-state`；`actionLabel()` 返回 `applied ? '✓ 已加入，可撤销' : '加入本学期方案'` |
| 已加入标注为**规划草稿**，不代表已完成教务选课 | 逐字：「已加入本学期方案（规划草稿，⛔ 不代表已完成教务选课）」 |
| 被服务端拒绝的选修选择如实展示，不静默丢弃 | `elective-rejections` |
| 真实 Case A 候选共 10 门（加入一门后候选列表变为 9 门，因为已加入的课程退出候选池）；首批为 CSE317 / CSE321 / CSE323 | 本次实测：intro 计数 10、展开后 10 项；加入一门后计数 9。Issue #61 最终验证 `ELECTIVES = CSE317, CSE321, CSE323` |

> ⛔ **不得写**：系统自动替学生选课 / 自动教务选课 / 自动决定教学班。

## 3.3 页面主流程与课表来源（本轮结构变化）

| 主张 | 证据 |
|---|---|
| 最终主流程为五段：补修缺口分析 → 本学期专业选修建议 → 本学期推荐课表 → 未来学期修读路径 → 详细依据 | `frontend/src/components/CaseADemoView.vue` 的 `SectionCard` 顺序 |
| **页面底部只有一个统一提醒区**，只做汇总，可操作的确认在各自模块内完成 | `frontend/src/components/PendingReminders.vue`（`case-a-reminders`）；标题逐字「待确认与提醒（N 项）」 |
| ⛔ **没有**独立的大块"待处理事项／待你确认的调整"模块 | 同上；`PendingIssuesCenter` 不再是顶层区块 |
| 补修确认改为**逐条操作**且收敛为**单一主操作**：未确认显示「确认可转换」，确认成功后同一按钮变为「✓ 已确认」，再点即撤销 | `MakeupTaskList.vue`（`makeup-confirm-<course>`、`makeup-deferred-<course>`、`makeup-undo-<key>`） |
| 确认入口上方的逐字披露包含「也不会修改学校教务系统记录」 | `makeup-confirm-disclosure` 逐字 |
| 专业选修候选**不再被截断**：本次真实数据 **10 门**，默认显示前 6 门，可展开其余或按课程名/课程号筛选（加入一门后候选列表变为 9 门） | `CurrentElectiveSection.vue`（`INITIAL_VISIBLE = 6`、`elective-expand`、`elective-collapse`、`elective-search`）；后端显示上限 50 |
| 课表用**来源图例**区分三种课程 | `case-a-schedule-legend`：`当前已选` / `规划新增·建议` / `你加入方案的选修` |
| 课表**业务类别标签仅有依据时出现**：必修需显式 `required` 证据；专业选修需确知属于选修组或用户已加入方案；其余不显示 | `WeeklyScheduleView.vue`（`categoryOf()`、`case-a-weekly-category`）；提交主题 "label course categories only on explicit evidence" |
| ⛔ 界面**没有**公选 / 跨专业 / 实验类别标签 | 同上（代码只定义 `required` 与 `elective` 两类） |
| 课表明确声明是**规划建议**，不代表已完成教务选课 | `case-a-timetable-disclaimer` 逐字 |
| 学分上限为**产品默认值**，页面注明不是学校政策声明 | `case-a-credit-policy` 逐字 |
| 详细依据**默认折叠** | `case-a-detailed-evidence` 为 `<details>`，默认不展开 |
| 确认与选修加入后，课表与未来规划会随用户选择重新计算 | Issue #61「ELECTIVE_SELECTION_UPDATES_TIMETABLE = PASS」「ELECTIVE_SELECTION_UPDATES_FUTURE = PASS」 |

> ⛔ 不得写成"界面提供必修 / 专业选修 / 公共选修 / 跨专业 / 实验五类标签"——界面只定义了两类，且都需证据。

## 3.4 数据库相关选修可达性

| 主张 | 证据 |
|---|---|
| **数据库系统原理 CSE335** 与**数据库系统实验 CSE337** 属于目标专业专业选修池，且存在真实 `2026-1` 教学班 | 本次实测：专业选修筛选「数据库」返回两门课，CSE335 教学班 `202616238`、CSE337 教学班 `202616239` |
| 曾因**选修候选显示上限**把它们藏在视野之外，不是数据缺失 | Issue #61 `DATABASE_AUDIT`；最终界面默认显示前 6 门并可展开至全部 10 门，另支持筛选 |
| 它们可以在界面上被查询到并加入当前课表 | 截图 `07_数据库相关选修可达.png`；两门课均有「加入当前课表」按钮 |
| 本次审计的当前课表输入是**空的**，这两门课**当时并未被学生选中** | Issue #61 `DATABASE_AUDIT`：`database present: NO / lab present: NO / counted in load: NO` |
| 只有用户明确加入后才计入当前负荷 | 同上；`current_semester_load` 的 `selected_credit` 只统计用户课表 |

> ⛔ **不得写**：系统已经识别学生本学期选了数据库和数据库实验。
> 正确表达：**它们作为选修候选可以被查询并纳入规划；只有用户明确加入后才计入当前负荷。**

> ⚠️ **两个 23 必须分开讲，这是本套材料最容易出错的地方**：
> - **23 项** = 历史培养要求评估条数（12 已满足 + 11 待人工确认）；
> - **23 学分** = 目标专业选修组的最低毕业学分要求。
> 一个是**条数**，一个是**学分**，含义完全不同。

## 4. 本轮已实现的产品能力（已从"未来计划"升为事实）

| 主张 | 证据 |
|---|---|
| **成绩单 PDF 导入**：可上传成绩单并识别已修课程 | `docs/curriculum/PDF_TRANSCRIPT_INPUT.md`；`backend/app/curriculum/pdf_reader.py`；前端 `CaseADemoView.vue` 上传区 |
| 成绩单不提供官方课程号，系统**不构造、不推断**课程号 | `docs/curriculum/PDF_TRANSCRIPT_INPUT.md`（全部记录 `course_id = None` + pending） |
| 成绩单**不参与**"已修完 / 已满足"判定，页面有常驻披露 | Issue #57 评审已核（`not_bound` 披露渲染在结果**之前**，且无取值可抑制） |
| **Case A 演示闭环**：成绩单 → 培养要求评估 → 本学期教学班 → 当前课表 → 偏好 → 受限规划 → 确认 → 课表 → 未来路径 | `docs/e2e/CASE_A_PLANNING_DEMO_RUNBOOK.md` §0、§4 |
| **培养要求结果展示** | 验收清单 A2；`MakeupTaskList.vue` |
| **本学期真实教学班规划**（精确到教学班） | 演示手册 §4 步骤 6；验收清单 C4 |
| **冲突检测**：三态，`已确认冲突 > 信息未知 > 在已知信息范围内未发现冲突` | `backend/app/planner/conflicts.py`；`meetings=[]` ⇒ UNKNOWN |
| **换班候选**：结构化建议（当前班 → 候选班 + 时间 / 校区 / 教室 + 原因） | `backend/app/path_planner/repair_proposals.py`；`PendingAdjustments.vue` |
| **用户明确确认 repair**：只有点击"采用调整"才调用后端并生效 | 验收清单 C1、C3；评审已核（apply 需完整身份，无自动挑选） |
| **未来学期 course-level roadmap** | `backend/app/path_planner/future_roadmap.py`；`FutureRoadmapView.vue`；验收清单 D1–D3 |
| 未来学期**结构上不出现**教学班号 / 教师 / 星期 / 节次 / 教室 / 校区 / 容量 | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §4.1；API 层断言 + 前端测试断言 |
| **专业选修学分规划**：按选修组最低学分补足即止，不超额规划 | 同上 §4.0.2、§4.3；验收清单 D4 |
| **本学期专业选修建议**：本学期可加入方案的专选候选，最多 3 门，含可用教学班数与冲突状态 | `frontend/src/components/CurrentElectiveSection.vue`；`recommend_current_electives()` |
| 选修建议**绝不自动选课**：只有用户显式点击「加入本学期方案」才进入规划草稿，加入后仍可撤销 | 同上（界面明确"系统不会替你选课"；`elective-applied-state` 标注为规划草稿） |
| **学分负荷控制** | `backend/app/services/case_a_roadmap.py` 常量与 `current_semester_load()`；演示手册 §4 步骤 12 |
| 当前学期默认学分上限 = **30**（用户设置的更严上限优先） | `CASE_A_CURRENT_HARD_MAX_CREDIT = 30.0`；`current_semester_load()` |
| 未来学期**软目标 = 26 学分** | `CASE_A_FUTURE_SOFT_TARGET_CREDIT = 26.0` |
| 未来学期硬上限 = **35 学分** | `CASE_A_FUTURE_HARD_MAX_CREDIT = 35.0`（`backend/app/services/case_a_roadmap.py`） |
| 当前学期上限与未来学期上限是**两个不同的值**（30 / 35），不得混用 | 同一文件常量注释明确写出该区别 |
| 负荷标签口径：≤26 正常 / 26–30 较满 / 30–35 很满，⛔ 不得超过 35 | 同一文件常量注释；演示手册步骤 12 |
| 真实 Case A 未来学期最大建议学分 = **34.0** | 最终 RC 验证实测（产品侧记录） |
| 用户显式学分上限优先；用户值超过对应硬上限时按硬上限收口 | `case_a_roadmap.py` 常量注释与 `effective_hard` / `effective_soft` 实现 |
| **统一确认与去重**：有身份时按 `kind + courseId + classId` 去重，无身份时按语义判别式去重，语义不同的问题不会被静默合并 | `frontend/src/utils/studentIssues.ts`（`issueKey`，`95976ae` 提交主题："correct dedup so distinct issues are never silently merged"） |
| **按归属分区的待确认事项**：待确认事项按归属路由到各区块内的 `IssueList`，**不再有独立待处理区块** | `frontend/src/components/CaseADemoView.vue`（`routedIssues`；`owner-label` = 认定与补修 / 专业选修 / 本学期排课 / 未来学期 / 其它） |
| **多候选课程聚合展示**：换班按课程分组，一门课一张卡片，默认 3 个候选，其余折叠 | `PendingAdjustments.vue`（`查看其余 N 个候选`）；`frontend/src/utils/repairView.ts`；演示手册 §4 步骤 8 |
| 待确认事项按中文展示，原始机器码折叠在"查看技术详情" | 演示手册 §4 步骤 14 |

## 5. 教师信息口径（措辞已统一）

| 主张 | 证据 |
|---|---|
| **当前 accepted Course Data 快照未保留教师字段，因此教师信息暂未同步** | `docs/status/integration.md` §教师信息：两文件合计 4069 rows 中携带 `teachingName` 的行 = 0；`teachingTimePlaceStr` 解析出 12011 个 segment 中教师段为 REDACTED 的 = 0 |
| 页面用中性文案「教师信息暂未同步」，**不伪造、不推断**教师 | `frontend/src/components/WeeklyScheduleView.vue`、`CurrentScheduleEditor.vue`、`PendingAdjustments.vue` |
| 「待核验」保留给真正影响决策的状态（例如排课信息缺失），不与教师信息混用 | `docs/status/integration.md` §教师信息结论 |
| 采集器的字段最小化白名单不含 `teachingName`，教师段在保存前就已剥离 | 同上（是"直接不存在"，不是脱敏标记） |

> ⛔ **不允许**写成"原始教务接口没有教师信息"。原始接口**存在** `teachingName`，
> 是**本次 accepted 快照的字段白名单没有保留它**。两句话含义完全不同。

## 7. 用户需求问卷（真实统计）

| 主张 | 证据 |
|---|---|
| 问卷为面向在校本科生的在线问卷，通过微信渠道发放与回收 | 问卷原始答卷文件（24 份有效样本）+ 调研总结说明文档 |
| 原始回收 **32 份**，有效样本 **24 份**，有效率 **75.0%** | 原始答卷逐条计数复核一致 |
| 回收时间 **2026 年 9 月 27 日** | 原始答卷的提交时间字段 |
| 有效样本中有转专业经历 **22 人（91.7%）**、正在转专业流程中 **2 人（8.3%）** | 原始答卷 Q1 逐条计数复核一致 |
| 无效样本剔除 **8 份**：7 份无转专业经历 + 1 份开放题乱填 | 调研总结说明文档；剔除依据为"无转专业经历"与"开放题乱填" |
| 问题发生率前三：课程时间冲突 **75.0%**、想补课程未开设 **62.5%**、跨学期规划困难 **58.3%** | 原始答卷 Q3 逐题计数，与调研总结说明一致 |
| 影响最大前三：课程时间冲突 **70.8%**、跨学期规划困难 **33.3%**、课程认定与课程不开设各 **20.8%** | 原始答卷 Q4 逐题计数一致 |
| 知晓率最低：课表冲突处理 **29.2%**、先修关系与本学期实际开课各 **37.5%** | 原始答卷 Q2 逐题计数一致 |
| 现有方式：自己查培养方案 **75.0%**、问老师 **70.8%**、教务系统反复查 **58.3%**、使用 AI 工具 **16.7%** | 原始答卷 Q5 逐题计数一致 |
| 功能需求前三：规划补修路径 **79.2%**、自动识别补修课程 **66.7%**、查询本学期开课 **62.5%** | 原始答卷 Q6 逐题计数一致 |
| 使用意愿：愿意 **70.8%**、中立 **29.2%**、不愿意 **0%** | 原始答卷 Q7 逐题计数一致 |
| 开放题 24 份有效样本均有作答，反馈集中在补修与学分认定环节 | 原始答卷 Q8；分类统计见 `support/01_用户需求调研与问卷分析.pdf` |

> ⚠️ 问卷为**小样本**（有效 24 份，原始 32 份）。结论用于确认需求方向与功能优先级，
> **不等同于**市场验证完成，也不构成对大范围需求的推断。
>
> ⛔ **不得**把上述比例写成市场规模、占有率或需求覆盖率；
> ⛔ **不得**在材料中出现任何未在原始答卷中出现的统计数字；
> ⛔ 原始答卷含 IP 等字段，**不得**原样放入对外材料，只做匿名汇总。

## 8. 安全与确认机制

| 主张 | 证据 |
|---|---|
| 手工录入的当前课表默认不被采信，用户勾选确认后才进入规划 | `docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` §5.2；验收清单 A5 |
| 确认之后课表又被改动，确认自动作废 | 同上；验收清单 A6 |
| 生成建议**不会**改动课表 | 验收清单 C1；评审已核（proposal 生成是纯函数） |
| 换班后只改被确认的那一门，其余课程不变 | 验收清单 C3、C4 |
| "暂不调整"只在本页收起，不改后端状态 | 验收清单 C5；演示手册 §4 附注 |
| 非同一课程 / 非同一学期的候选会被拒绝且课表不变 | 验收清单 C6；评审已核 |
| 应用换班后重新校验整份课表，残留冲突如实列出 | `docs/status/integration.md` §关键设计 |
| 前置条件不满足时明确拒绝，不回退演示数据 | 演示手册 §2；`503 real_pipeline_not_configured` |
| 不自动执行选课与注册，输出是建议方案 | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §3；验收清单 C1 |
| 不自动认定课程等价 | `docs/interfaces/curriculum.md`；`docs/curriculum/PDF_TRANSCRIPT_INPUT.md`（同名课停在待确认，不自动抵认） |
| 跨模块只通过公共契约交互，冻结契约未被改动 | 评审已核：`schemas/`、`docs/interfaces/`、Provider Protocol、`RestrictedPlanner`、`backend/app/planner/**` 均未改 |

## 9. 技术性质

| 主张 | 证据 |
|---|---|
| 当前是**固定工具编排** | Issue #57 评审：无 LLM / GraphRAG / CP-SAT 生产主张，编排不调用模型 |
| 规则驱动 + 结构化数据 + 确定性规划 | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §4.2（确定性启发式，非全局最优） |
| 偏好来自**结构化表单**，不是自然语言 | 验收清单 B2 |
| 不保证所有偏好都被执行，未执行部分如实列出 | 验收清单 D6；`docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` §5.4 |

---

# 二、CONDITIONAL

> 产品与 RC 已定稿，本档只剩**素材类**等待项。
> 能力与数字类的"待确认"已全部结清。

| 主张 | 现状 | 证据 / 说明 | 怎么用 |
|---|---|---|---|
| **最终界面文案与区块名称** | 产品基线界面已定稿 | `CaseADemoView.vue`、`PendingAdjustments.vue`、`CurrentElectiveSection.vue` | 按钮名、区块名以实际界面为准 |
| **最终截图** | ✅ 已采集（12 张，最终 RC 界面真实渲染） | `docs/submission/screenshots/` + `screenshots/SCREENSHOT_INDEX.md` | 可直接用于 PPT 与宣传页；配文须遵守索引里的"不能证明" |
| **教师信息补齐** | `BLOCKED_BY_MISSING_LOCAL_RAW_SOURCE`。本机原始数据里没有教师姓名，不重新采集就无法恢复 | `docs/status/integration.md` | 统一说"教师信息暂未同步"；⛔ 不说"已完整覆盖" |
| **团队名称与联系方式** | 仓库内无已确认信息 | — | 占位 `[待负责人确认]` |

---

# 三、DO NOT CLAIM

## 3A 能力不实类

| ⛔ 不得主张 | 原因 / 对照证据 |
|---|---|
| 生产级大模型推理 / LLM 已接入 | Issue #57 评审：无 LLM 生产主张；编排不调用模型 |
| 检索增强（RAG）已实现 | 同上 |
| GraphRAG 推理已实现 | 同上（仓库内 GraphRAG 命中全部是否定式） |
| 自然语言偏好解析 | 偏好来自结构化表单（验收清单 B2） |
| 全局优化 / CP-SAT / ILP 求解 | `MULTI_SEMESTER_PATH_PLANNER.md` §4.2「不是 CP-SAT / ILP 全局最优求解」 |
| "最优方案" / "全局最优" | 输出是受限候选与未决事项 |
| 自动教务选课 / 自动注册 | `MULTI_SEMESTER_PATH_PLANNER.md` §3；验收清单 C1 |
| 自动认定课程等价 | `docs/interfaces/curriculum.md`；`PDF_TRANSCRIPT_INPUT.md` |
| **自动官方课程认定 / 系统自动批准补修认定** | 规划层确认是**用户的规划假设**，界面逐字写「基于你的确认 / 仅用于本次规划 / 不是学校官方认定结果」 |
| **学校已经确认（课程等价或补修认定）** | 同上；source-backed 基线不因用户确认而改写 |
| 自动替换课程 / 自动换班 | 生成 ≠ 应用；必须用户点击"采用调整" |
| 系统按偏好或连堂密度自动调班 | 建议只来自结构化候选，无评分权重 |
| **自动决定教学班 / 自动替学生选课** | 选修只能由用户显式点击「加入本学期方案」；多 CLEAR 必须用户选班 |

## 3B 数据范围类

| ⛔ 不得主张 | 原因 / 对照证据 |
|---|---|
| 全校完整课程数据 | `is_whole_school = false` |
| 完整学期数据 | `is_full_semester = false` |
| 五校区完整供给 | 仅南校园 + 深圳校区（4069 条） |
| 已连接学校教务系统 / 实时对接 | 不联网抓取，使用本地已验收 artifact（验收清单 E3） |
| 未来学期生成详细教学班课表 | 未来字段集在结构上不含教学班信息 |
| 预测未来教师 / 上课时间 / 教室 / 容量 | `MULTI_SEMESTER_PATH_PLANNER.md` §1 |
| 已验证全部教师覆盖 | 快照 0/4069 行保留教师字段 |
| **原始教务接口没有教师信息** | ⛔ 错误。原始接口**存在** `teachingName`，是本次快照白名单未保留 |
| 数据都是真的 | 教学班为真实 scoped 数据，但成绩单行不参与满足判定，须分别表述 |
| **用户当前课表已包含数据库课程** | ⛔ 错误。本次审计的 current_schedule 输入是空的；CSE335 / CSE337 未被选中 |
| 界面提供必修 / 专业选修 / 公共选修 / 跨专业 / 实验五类标签 | 界面只定义「必修」与「专业选修」两类，且都需明确依据；其余课程不显示业务类别标签 |

## 3C 数字与效果类

| ⛔ 不得主张 | 原因 |
|---|---|
| 准确率 / 成功率 / 提升倍数 | 仓库内无此类实测数据 |
| 用户数量 / 合作学校数量 / 意向院校 | 仓库内无记录 |
| 用户访谈结果 | 仓库内无已确认的访谈记录（**问卷统计已有真实数据，见上方「用户需求问卷」小节**） |
| 比赛反馈 / 往届成绩 | 不允许虚构 |
| 市场规模 / 预计收益 | 不允许虚构 |
| "23 门课需要补修" | 正确口径：**23 项历史培养要求评估，12 项已确认满足，11 项待人工确认** |
| 把选修组 23 学分说成 23 门课 | 一个是学分，一个是课程条数 |

## 3D 关系与排名类

| ⛔ 不得主张 | 原因 |
|---|---|
| 国内首个 / 领先 / 唯一 | 无依据 |
| 其他工具或方案都做不到 | 不贬低、不虚构其他方案 |
| 开箱即用适配任何学校 | 只有 Case A 一个专业方向的部署证据 |

---

# 四、最容易讲错的十条（速查版）

| # | ⛔ 错误说法 | ✅ 正确说法 |
|---|---|---|
| 1 | 需要补修 23 门课 | 23 项历史培养要求评估，12 项已确认满足，11 项待人工确认 |
| 2 | 专业选修要修 23 门课 | 专业选修最低要求是 23 **学分** |
| 3 | 系统自动选课 / 自动换班 | 生成建议不改课表，用户明确确认后才应用 |
| 4 | 全校完整本学期课程数据 | 真实教学班数据，范围是南校园 + 深圳校区，共 4069 条 |
| 5 | 未来学期给你排好课表和老师 | 未来学期只做课程级规划，只有课程名 / 课程号 / 学分 / 必修选修 |
| 6 | 未来学期学分上限是 30 | 当前学期上限是 30，**未来学期硬上限是 35**，两者不同 |
| 7 | 未来学期可以随便排满 | 未来学期软目标 26、硬上限 35；排不下的课顺延，不硬塞 |
| 8 | 用 AI 推理出缺哪些课 | 规则驱动 + 结构化数据 + 确定性规划，AI 增强待接入 |
| 9 | 原始教务接口没有教师信息 | 当前 accepted 快照未保留教师字段，因此教师信息暂未同步 |
| 10 | 这个班没有冲突 | 在已知信息范围内未发现冲突；排课信息缺失时整体仍是未知 |
| 11 | 已经连上学校教务系统 | 不联网抓取，使用本地已验收数据 |
| 12 | 用户确认后学校就认定这门课等价了 | 用户确认是**规划假设**，仅用于本次规划、可撤销，不是学校官方认定 |
| 13 | 系统自动帮学生加了选修 | 必须用户显式点击「加入本学期方案」；多 CLEAR 时还要用户自己选教学班 |
| 14 | 系统识别到学生这学期选了数据库课 | 本次 current_schedule 输入为空；数据库课是**可查询的候选**，只有用户明确加入才计入负荷 |
| 15 | 界面用颜色区分必修 / 专选 / 公选等属性 | 界面只定义「必修」与「专业选修」两类标签，且都需明确依据；其余课程不显示业务类别标签 |
| 16 | 底部提醒里的项数就是缺陷数 | 那是"待确认与提醒"的汇总条数，包含尚未处理的确认项与提醒，不是缺陷清单 |
| 17 | 学分上限是学校政策 | 该上限是**产品默认值**，页面注明不是学校政策声明 |

---

# 五、写法要求

1. **用肯定句讲已实现的，用限定句讲未实现的。** ⛔ 不用"基本上""差不多""即将上线"。
2. **每个对外数字都要能指回上表的某一行。** 指不回去的数字，删掉。
3. **"待确认"不是丢人的词。** 它是本产品的设计选择，主动讲出来是加分项。
4. **同一份材料里前后口径必须一致。** 定稿前全文检索：`23`、`12`、`11`、`4069`、`南校园`、`深圳`、`30`、`26`、`35`、`34.0`、`教师`、`确认`、`加入本学期方案`、`撤销`。
5. **发现本表与代码不一致时，以代码为准，并更新本表。**
6. **⛔ 不要写"35 尚未落地"** —— 已在 `95976ae` 落地，并纳入最终 RC `56013e5`。
7. **⛔ 不要写"待你确认的调整""需要你处理"这类独立大区块** —— 本轮已取消独立模块，待确认事项按归属收口在各区块内部。
8. **按钮名必须与最终界面一致**：`确认可转换`（确认后同一按钮变 `✓ 已确认`）、`加入本学期方案`（加入后同一按钮变 `✓ 已加入，可撤销`）、`查看其余 N 门`、`采用调整`、`保留当前班`。

---

# 六、等待项（材料定稿前必须回填）

| 等待项 | 影响哪些文件 | 占位写法 |
|---|---|---|
| 教师信息补齐状态 | 本表、宣传页、PPT 大纲 | `[待 teacher enrichment 确认]`（本轮为 `BLOCKED_BY_MISSING_LOCAL_RAW_SOURCE`） |
| 团队名称与联系方式 | 宣传页 | `[待负责人确认]` |

> ✅ 最终截图**已就绪**（`docs/submission/screenshots/`，18 张，基于 `56013e5` 重拍）。
> ✅ 评委支撑材料**已就绪**（`docs/submission/support/`，8 份 PDF）。
> 产品 HEAD、RC HEAD、学分口径（30 / 26 / 35）与能力边界均已定稿，**不再属于等待项**。
> 以上两项是素材类工作，不影响事实正确性。
