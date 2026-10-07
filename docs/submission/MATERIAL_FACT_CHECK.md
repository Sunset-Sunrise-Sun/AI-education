# 学航·转衔 · 材料事实核对表（真实性守门文件）

> **这是整套提交材料里最重要的一份。**
> 任何对外材料、PPT、宣传页、演示话术，写完之后都要拿这份表逐条对照。
> 本表只回答一个问题：**这句话有没有实现证据。**

## 核对基线

| 项 | 值 |
|---|---|
| 材料分支 | `docs/opc-submission-package` |
| 事实基线 commit | `7a7bb9d67cc1d5858cb9a63cc960f8b492eb86a5`（分支 `feature/case-a-course-data-current-schedule`） |
| 产品仍在收尾的分支 | `fix/manual-acceptance-productization`（HEAD `40803a2`，已与事实基线分叉，未合并） |
| 核对时间 | 2026-10-07 |
| 核对方式 | 逐条对照仓库内代码、状态文档、接口文档与工作记录 |

## 三档标记的含义

| 标记 | 含义 | 材料里怎么用 |
|---|---|---|
| **VERIFIED** | 在事实基线分支上有实现或实测证据，可以直接写真话 | 可以自由润色语气，但事实不能改 |
| **CONDITIONAL** | 只在尚未合并的分支上实现，或状态仍待确认 | 可以说，但必须加限定语，或先确认状态再定稿 |
| **DO NOT CLAIM** | 没有证据，或与实现方向相反 | ⛔ 任何材料、任何场合都不要说 |

---

# 一、VERIFIED

## 1. 定位与用户

| 主张 | 证据 |
|---|---|
| 项目定位为"学航·转衔：面向转专业学生的 AI 学业路径重构 Agent" | `AGENTS.md` 第 1 节项目目标；`README.md` 标题与 §1 |
| 主要用户是转专业学生，次要用户是辅导员 / 教务人员 / 学院负责人 | `README.md` §2 目标用户表 |
| 产品不定位为通用选课助手、课程问答机器人、教务系统替代品 | `README.md` §2「明确不做」；`docs/ARCHITECTURE.md` §1（不把通用四年选课、延毕预测纳入 MVP） |
| 痛点表述为：培养方案差异难以自查、补修判定涉及正式规则、供给与课表约束叠加、结论不易解释 | `README.md` §2 痛点四条（原文"痛点（不夸大）"） |

## 2. 数据范围与来源

| 主张 | 证据 |
|---|---|
| 本学期教学班使用**真实**教学班数据 | `docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` §0、§4（从已验收 campus acceptance 派生真实数据集） |
| 数据范围是**南校园 + 深圳校区** | 同上，`openingSchoolNumbers = ["5062201", "333291143"]`；`scope_label = "case-a-scoped:south+shenzhen"` |
| 该数据集是 case-scoped，**不是**完整学期数据，**不是**全校数据 | 同上，`is_full_semester: false`、`is_whole_school: false`、`scope_kind: "case_scoped"` |
| 系统不联网抓取教务系统，使用本地已验收数据 | `README.md` §9 零网络默认；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` E3 |
| 成绩单中的姓名、学号、绩点不读取、不返回 | `docs/curriculum/PDF_TRANSCRIPT_INPUT.md` 隐私边界表；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` A1、E1 |

## 3. 培养要求评估（最关键的数字口径）

| 主张 | 证据 |
|---|---|
| Case A 真实投影产出 **23 项历史培养要求评估** | `docs/status/curriculum.md`（"`get_makeup_tasks()` 成功返回 **makeup_task_count = 23**"） |
| 其中 **12 项已确认满足** | 同上（"satisfied 12 / manual_confirmation 11 / required 0 / possibly_equivalent 0"） |
| 其中 **11 项需要人工确认** | 同上 |
| 这 23 项**全部是历史范围**条目，未来未满足条目不出现在评估结果里 | 同上（"23 条全部为 historical 条目，future unmet 条目不出现在 `MakeupTask[]` 中"） |
| 培养要求状态分四种且**互不等同**：已满足 / 待人工确认 | `README.md` §3；`docs/interfaces/curriculum.md`；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` A2 |
| 课程等价、学分差额、学院政策、条款歧义一律标记为待人工确认，系统不下正式结论 | `README.md` §3 人工确认模型；`docs/interfaces/curriculum.md` |
| 目标专业选修组最低学分要求为 23 学分 | `docs/status/curriculum.md`（`CSE-ELECTIVE-POOL`，`minimum_credit = 23`，37 门成员） |

> ⚠️ **同一页可能同时出现两个 23，含义完全不同**，讲的时候必须区分：
> - **23 项** = 历史培养要求评估条数（12 已满足 + 11 待人工确认）；
> - **23 学分** = 目标专业选修组的最低毕业学分要求。
> 把这两个混为一谈是本次材料最需要防的错误。

## 4. 本学期规划与确认机制

| 主张 | 证据 |
|---|---|
| 本学期做**真实教学班级别**规划 | `docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` §0、§5；`docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §0 |
| 有冲突检测，且冲突是三态：已确认冲突 > 信息未知 > 在已知信息范围内未发现冲突 | `README.md` §3「冲突状态三态」 |
| 排课信息为空表示**未知**，不等于没有冲突 | `README.md` §3；`docs/e2e/CASE_A_PLANNING_DEMO_RUNBOOK.md` §7；`docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §3 |
| 有教学班替代建议，写成"当前班 → 候选班 + 原因" | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §3；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` C2 |
| 生成建议**不会**改动课表 | 同上（"生成 ≠ 应用"，`generate_*` 只读） |
| 换班必须用户**明确确认**后才应用 | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §3；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` C1、C3 |
| 手工录入的当前课表默认不被采信，用户勾选确认后才进入规划 | `docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` §5.2（用户级确认四条规则） |
| 确认之后课表又被改动，确认自动作废 | 同上；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` A6 |
| 页面显示的是**建议方案**，不代表已完成选课或注册 | `README.md` §3；`docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` §5.4 |
| 教师信息缺失时页面显示"待核验"，系统不编造教师 | `docs/e2e/CASE_A_PLANNING_DEMO_RUNBOOK.md` §6、§7；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` A8 |

## 5. 未来学期

| 主张 | 证据 |
|---|---|
| 未来学期只做**培养方案课程级**路径规划 | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §0、§4 |
| 未来学期结构上**不出现**教学班号、教师、星期、节次、教室、校区、容量 | 同上 §4.1（字段集刻意最小，有专门测试锁定）；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` D2 |
| 不预测未来教师、时间、教学班、容量 | 同上 §1（"把它们编出来就是伪造数据"） |
| 未来学期排序依据培养方案学期号与先修关系，不按列表位置 | 同上 §4.0、§4.2 |

## 6. 技术性质

| 主张 | 证据 |
|---|---|
| 当前是**固定工具编排** | `README.md` §4（编排层只编排，不调用模型）；`docs/ARCHITECTURE.md` §3 |
| 规则驱动 + 结构化数据 + 确定性规划 | `README.md` §3、§5；`docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §4.2 |
| 偏好来自**结构化表单**，不是自然语言 | `README.md` §3、§10.6；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` B2 |
| 不保证所有偏好都被执行，未执行部分如实列出 | `README.md` §3；`docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md` §5.4 |
| 前置条件不满足时明确拒绝，不回退演示数据 | `README.md` §5.4（fail-closed）；`docs/e2e/CASE_A_PLANNING_DEMO_RUNBOOK.md` §2 |
| 跨模块只通过公共契约交互 | `docs/ARCHITECTURE.md` §4；`schemas/*.schema.json` |
| 当前评估结果**不是**由上传的课程记录自动抵认出来的 | `docs/curriculum/PDF_TRANSCRIPT_INPUT.md`（成绩单不提供官方课程号，不做等价判定）；`docs/status/curriculum.md`（12 项 satisfied 来自已确认的课程号身份匹配） |

---

# 二、CONDITIONAL

> 这一档的每一条，**在写进对外材料之前必须先确认状态**。
> 目前它们都对应尚未合并的分支 `fix/manual-acceptance-productization`（HEAD `40803a2`）。

| 主张 | 现状 | 证据 | 怎么用 |
|---|---|---|---|
| **上传成绩单 PDF 并识别已修课程** | 前端与后端均已实现，但**只在收尾分支上** | 前端 `frontend/src/components/CaseADemoView.vue`（上传区、成绩单识别结果区块）；后端 `backend/app/curriculum/pdf_reader.py`、`POST /api/v1/completed-courses/import-pdf`（`docs/curriculum/PDF_TRANSCRIPT_INPUT.md`） | 演示时可以说"上传成绩单"，但要知道**这段代码还没进事实基线分支**；材料定稿前必须确认合并状态 |
| **换班建议的生成与应用** | 生成建议与应用接口**只在收尾分支上**；事实基线分支只有规划器内部的候选评估 | `backend/app/path_planner/repair_proposals.py`、`POST /api/v1/case-a-demo/repair/apply`（`docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §3） | 可以说"用户确认后才换班"（机制已验证），但完整交互以收尾分支为准 |
| **未来学期路径页面** | 后端路线图与前端 `FutureRoadmapView.vue` **只在收尾分支上** | `backend/app/path_planner/future_roadmap.py`、`backend/tests/test_case_a_roadmap.py` | 可以说"未来学期课程级规划"，但界面呈现待定稿 |
| **选修学分进度区块** | 计算逻辑已实现（含账目恒等式），页面**只在收尾分支上** | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §4.0.2、§4.1；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` D4 | 可以说"把选修学分的账算清楚"；数字口径以实际页面为准 |
| **本轮评估结果与上传成绩单的关系** | 收尾分支的界面**明确声明**：上传的成绩单**没有参与**"已修完 / 已满足"的判定 | `frontend/src/components/CaseADemoView.vue`（提示始终展示，无分支可抑制）；`backend/app/services/case_a_demo.py::_completed_binding` | ⛔ 不要说"上传成绩单之后系统就算出了这 12 项已满足"；正确说法是"这 12 项依据已确认的培养方案事实" |
| **教师信息补齐状态** | **待确认**。真实数据里教师字段普遍缺失，缺失时显示"待核验" | `docs/e2e/CASE_A_PLANNING_DEMO_RUNBOOK.md` §6、§7；`docs/status/course_data.md`（教师字段的来源与二义性仍在处理） | 在确认之前，一律说"教师缺失时显示待核验，系统不编造"，**不说**"教师数据已完整" |
| **最终候选版本号（RC SHA）** | 尚未确定 | 收尾分支 HEAD 为 `40803a2`，未打标签 | 材料里的版本号写成 `[待 RC SHA]` |
| **最终界面文案与区块名称** | 仍在最后产品化 | 收尾分支改动集中在界面 | 材料里的按钮名、区块名写成 `[待 UI 定稿]` |

---

# 三、DO NOT CLAIM

## 3.1 能力不实类

| ⛔ 不得主张 | 原因 / 对照证据 |
|---|---|
| 已实现大模型推理 / LLM 已接入 | `README.md` §10.6「未集成 LLM / RAG / GraphRAG：当前无模型调用」；`docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md`（编排不调用模型） |
| 已实现检索增强 | 同上，无检索管线 |
| 已实现知识图谱推理 | 同上 |
| 已实现自然语言偏好解析 | `README.md` §10.6；偏好来自结构化表单 |
| 已使用全局优化求解 | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §4.2「这里不是 CP-SAT / ILP 全局最优求解」 |
| 已求出最优方案 | 同上；输出是受限候选与未决事项 |
| 自动教务选课 / 自动注册 | `README.md` §2「不代替学生执行选课 / 注册」；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` C1 |
| 自动认定课程等价 | `README.md` §3 人工确认模型；`docs/interfaces/curriculum.md` |
| 自动替换课程 / 自动换班 | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §3「生成 ≠ 应用」 |
| 上报的具体数字就是现场算出来的 | 事实基线分支页面基础区仍有演示数据；现场以实际页面为准 |

## 3.2 数据范围类

| ⛔ 不得主张 | 原因 / 对照证据 |
|---|---|
| 全校完整课程数据 | `docs/data/CASE_A_SCOPE_AND_CURRENT_SCHEDULE.md`：`is_whole_school: false` |
| 完整学期数据 | 同上：`is_full_semester: false` |
| 五校区完整供给 | 同上，仅南校园 + 深圳校区 |
| 已连接学校教务系统 / 实时对接 | `README.md` §5.4、§9；`docs/e2e/CASE_A_HUMAN_ACCEPTANCE_CHECKLIST.md` E3 |
| 未来学期生成详细教学班课表 | `docs/architecture/MULTI_SEMESTER_PATH_PLANNER.md` §4.1（字段集在结构上就不含教学班信息） |
| 预测未来教师 / 上课时间 / 教室 / 容量 | 同上 §1 |
| 已验证全部教师覆盖 | `docs/e2e/CASE_A_PLANNING_DEMO_RUNBOOK.md` §6「教师数据已完整覆盖」列为口径红线 |
| 数据都是真的 | `README.md` §5（实际执行代码与经证明的输入来源是两条独立轴） |

## 3.3 数字与效果类

| ⛔ 不得主张 | 原因 |
|---|---|
| 准确率 / 成功率 / 提升倍数 | 仓库内没有任何此类实测数据 |
| 用户数量 / 合作学校数量 / 意向院校 | 仓库内没有记录 |
| 用户访谈结果 / 需求调研结论 | 仓库内没有已确认的访谈记录 |
| 比赛反馈 / 往届成绩 | 不允许虚构 |
| 市场规模 / 预计收益 | 不允许虚构 |
| "23 门课需要补修" | 正确口径是 **23 项历史培养要求评估，12 项已确认满足，11 项待人工确认** |

## 3.4 关系与排名类

| ⛔ 不得主张 | 原因 |
|---|---|
| 国内首个 / 领先 / 唯一 | 没有依据，且不需要这样讲 |
| 其他工具或方案都做不到 | 不贬低、不虚构其他方案 |
| 开箱即用适配任何学校 | `README.md` §10；只有 Case A 一个专业方向的部署证据 |

---

# 四、最容易讲错的十条（速查版）

| # | ⛔ 错误说法 | ✅ 正确说法 |
|---|---|---|
| 1 | 需要补修 23 门课 | 23 项历史培养要求评估，12 项已确认满足，11 项待人工确认 |
| 2 | 系统自动选课 / 自动换班 | 生成建议不改课表，用户明确确认后才应用 |
| 3 | 覆盖全校本学期所有课程 | 真实教学班数据，范围是南校园 + 深圳校区 |
| 4 | 未来学期给你排好课表和老师 | 未来学期只做课程级规划，不出现教师 / 时间 / 教室 |
| 5 | 用 AI 推理出缺哪些课 | 规则驱动 + 结构化数据 + 确定性规划，AI 增强待接入 |
| 6 | 用了 GraphRAG / 知识图谱推理 | 当前未接入 |
| 7 | 用 CP-SAT 求出了最优解 | 受限的确定性检查与候选评估，不是全局最优 |
| 8 | 教师数据已经完整覆盖 | 教师缺失时显示"待核验"，系统不编造 |
| 9 | 这个班没有冲突 | 在已知信息范围内未发现冲突；排课信息缺失时整体仍是未知 |
| 10 | 已经连上学校教务系统 | 不联网抓取，使用本地已验收数据 |

---

# 五、写法要求

1. **用肯定句讲已实现的，用限定句讲未实现的。** ⛔ 不用"基本上""差不多""即将上线"。
2. **每个对外数字都要能指回上表的某一行。** 指不回去的数字，删掉。
3. **"待确认"不是丢人的词。** 它是本产品的设计选择，主动讲出来是加分项。
4. **同一份材料里前后口径必须一致。** 定稿前用本表全文检索一次关键数字：`23`、`12`、`11`、`南校园`、`深圳`、`教学班`。
5. **发现本表与仓库实现不一致时，以仓库实现为准，并更新本表。**

---

# 六、等待项（材料定稿前必须回填）

| 等待项 | 影响哪些文件 | 占位写法 |
|---|---|---|
| 最终产品化界面（UI 定稿） | 演示脚本、截图计划、宣传页 | `[待 UI 定稿]` |
| 最终截图 | 演示脚本、PPT 大纲、截图计划 | `[待最终截图]` |
| 教师信息补齐状态 | 事实核对表、宣传页、PPT 大纲 | `[待 teacher enrichment 确认]` |
| 最终候选版本号 | 本表核对基线 | `[待 RC SHA]` |
| 团队名称与联系方式 | 宣传页 | `[待负责人确认]` |
