# 决赛提交总检查清单（FINAL SUBMISSION CHECKLIST）

> **本文件的性质**：这是**状态记录**，不是承诺书。只勾选**本轮实际读到证据**的条目；证据不足、依赖他人或尚无成品的一律保持未勾选。
> ⛔ 本文件不主张任何报名、参赛资格、合规或获奖结论；也不主张本项目已满足任何特定赛规。
> ⛔ `docs/submission/REHEARSAL_LOG.md` 中标注「⚠️ 无法判定」的项目，不得被当作已完成。
> **勾选口径**：`- [x]` = 本轮已用命令 / 文件内容核实；`- [ ]` = 未完成或**仓库内不可核实**。
> **计分口径**：各分区完成度按**复选框条目逐条计**（`official rules verified` 的 4 项细分各计 1 条）。

---

## 材料清单（READY / OWNER REQUIRED）

> ⛔ 本表不含任何"假勾选"：**READY** 仅指该材料已存在且内容在本轮被实际读到；**OWNER REQUIRED** 指必须由人完成或确认。

| 状态 | 材料 / 事项 | 位置或说明 |
|---|---|---|
| **READY** | 截图（6 张） | `docs/submission/assets/01..06_*.png`（模式 1 采集；02 / 03 已按 `51eaccb…` 重拍） |
| **READY** | 幻灯片内容稿（5 页） | `docs/submission/OPC_FINAL_SLIDES_CONTENT.md` |
| **READY** | PPTX 已生成 | `docs/submission/学航转衔_OPC_答辩稿.pptx`（6 页 = 封面 + 5 页；16:9；未目视校验） |
| **READY** | 演示脚本（4 分钟） | `docs/submission/OPC_FINAL_4MIN_DEMO.md` |
| **READY** | 录制计划 | `docs/submission/VIDEO_RECORDING_PLAN.md` |
| **READY** | Pitch 包 | `docs/submission/OPC_PITCH_PACK.md` |
| **READY** | 评委 Q&A（12+2 问） | `docs/submission/OPC_JUDGE_QA_SHORT.md` |
| **READY** | 溯源矩阵 / 一致性审计 | `docs/submission/FINAL_CLAIM_MATRIX.md`（M1 已修复，越界项 0） |
| **READY** | 版本锁定 / 截图索引 / 彩排记录 | `DEMO_VERSION_LOCK.md`、`SCREENSHOT_INDEX.md`、`REHEARSAL_LOG.md` |
| **OWNER REQUIRED** | PPTX 版式目视校验 | 本机无 PowerPoint / LibreOffice ⇒ 未渲染预览 |
| **OWNER REQUIRED** | 真人出声计时彩排（≥2 次） | 本轮仅完成自动化路线彩排 4 次；⛔ 不得当作真人彩排 |
| **OWNER REQUIRED** | 视频录制 | 全仓库无 `*.mp4` |
| **OWNER REQUIRED** | 团队 / 成员信息 | 模板中 `[OWNER TO FILL]` 22 处；**本赛道 ≤5 人** |
| **OWNER REQUIRED** | 门户上传 | 尚未登录门户；官方入口 `aiedu.caet.org.cn` |
| **OWNER REQUIRED** | 作品简介及承诺书 PDF、作品介绍文档 PDF、支撑材料 | 全仓库无 `*.pdf` |
| **OWNER REQUIRED** | 未解决的官方规则项 | PPT 格式 / 是否现场演示 / 是否要求 AI 真实运行 / 精确门户字段 / 校内·内部截止 |

---

## 0. 核查基准（本轮实测）

| 项 | 值 |
|---|---|
| 核查时间 | 2026-10-07 01:06 (+08:00) |
| 仓库 | `C:\Users\28746\Desktop\AI+教育\AI-education`（`Sunset-Sunrise-Sun/AI-education`） |
| 当前分支 | `docs/opc-final-submission-pack`（`git rev-parse --abbrev-ref HEAD`） |
| 当前 HEAD | `08f312f9cf2b8260fe0c83c52f842f08bc6c053a`（`git rev-parse HEAD`，本材料分支） |
| 演示版本（锁定） | **`51eaccb1f9b23f9226760eab323028ed85d01b0a`**；分支 `feature/competition-demo-closure`（PR #51）。本材料分支**以该 commit 为基线**，diff 仅含 `docs/submission/**`（⛔ 不重复任何前端改动） |
| 本材料分支与 `origin/main` | 相对 `origin/main` 领先（未合并）；相对 `feature/competition-demo-closure` 只多 `docs/submission/**`（`git diff --name-only feature/competition-demo-closure..HEAD` 共 21 个文件，全部在 `docs/submission/` 下） |
| 已核实存在的提交材料 | `DEMO_VERSION_LOCK.md`、`SCREENSHOT_INDEX.md`、`OPC_FINAL_SLIDES_CONTENT.md`、`OPC_FINAL_4MIN_DEMO.md`、`VIDEO_RECORDING_PLAN.md`、`REHEARSAL_LOG.md`、`OPC_PITCH_PACK.md`、`OPC_JUDGE_QA_SHORT.md`、`OPC_PORTAL_INFO_TEMPLATE.md`、`OFFICIAL_RULE_CHECK.md`、`学航转衔_OPC_答辩稿.pptx`、`assets/*.png`×6 |
| 经 `Test-Path` 判定**不存在**的文件 | `docs/submission/OFFICIAL_RULE_CHECK_TODO.md`（实际文件名是 `OFFICIAL_RULE_CHECK.md`）、`docs/submission/FINAL_SUBMISSION_CHECKLIST.md`（本文件即由本次创建） |
| 依赖但位于 `docs/demo/` 的文件 | `COMPETITION_DEMO_SCRIPT.md`、`COMPETITION_STARTUP.md`、`DEMO_RECOVERY.md`（均存在） |

**本轮只读核实命令（可复现）**：`git rev-parse HEAD`；`git rev-list --left-right --count origin/main...HEAD`；`Get-ChildItem docs/submission -File`；`Test-Path <逐文件>`；`Get-ChildItem mock_data -File -Filter *.json | Get-FileHash -Algorithm SHA256`；PNG 头部解析（`assets/*.png` 宽高）；PPTX 只读解包（`ppt/slides/slide*.xml` 计数 + `ppt/presentation.xml` 的 `sldSz`）；`Get-ChildItem -Recurse -Include *.mp4,*.pdf,*.mov,*.mkv`。

---

## 1. 口径红线（每一条都已落成下方检查项，⛔ 不得绕过）

| 红线 | 落在哪个检查项 |
|---|---|
| 课堂 / 教学班数据为 **Mock / Synthetic 并逐项披露**（页面横幅、第 2 区 Synthetic 披露条、第 4 区来源行、页脚声明） | P0「Synthetic/Mock provenance consistent」、P1「统一截图分辨率口径」 |
| ⛔ 不得出现「已接入 LLM / RAG / GraphRAG」 | P0「no LLM/RAG overclaim」 |
| ⛔ 不得出现「全局最优」 | P0「no global-optimum claim」 |
| ⛔ 不得出现「自动调班 / 自动选课 / 已连接教务 / Real E2E 完成 / LEVEL2、LEVEL3 达成」 | P0「no LLM/RAG overclaim」「no global-optimum claim」「official rules verified」 |
| `ready` ≠ LEVEL2（正式 Real E2E 证据等级 = LEVEL 0） | P0「no LLM/RAG overclaim」、P1「Q&A 真人演练」 |

---

## P0 MUST COMPLETE

- [ ] **PR #51 reviewed** ｜ 证据 / 位置：全仓库唯一提及处是 `docs/submission/DEMO_VERSION_LOCK.md` 第 14 行（仅作版本元数据）；`docs/` 下**无任何 review 记录或评审意见**；`git rev-list --left-right --count origin/main...HEAD` = `0 2`（未合并）；本机 `git ls-remote origin refs/pull/*` 返回 `[exit code: 1]`，**无法核实 PR 状态** ⇒ 属「仓库内不可核实」，不勾选。｜ 负责角色：owner（GitHub PR #51 页面）+ reviewer。
- [x] **final demo version locked** ｜ 证据 / 位置：`feature/competition-demo-closure` HEAD = **`51eaccb1f9b23f9226760eab323028ed85d01b0a`**（文案修复后），`DEMO_VERSION_LOCK.md` §1 锁定同一 commit（前序值 `248f835…` 作为截图 01/04/05/06 的采集版本一并记录）；§3.1 四个 Mock 夹具的 SHA-256 **本轮逐个复算全部一致**（`803cae90…` makeup_tasks / `55ac59fb…` course_offerings / `be8b9419…` preference / `b567ac76…` plan_result）。｜ 负责角色：版本 / 演示负责人。
- [x] **screenshots complete（6/6）** ｜ 证据 / 位置：`docs/submission/assets/` 实测 6 个 PNG——`01_background.png` 1600×1150、`02_requirement_assessment.png` 1600×1200（**已按 `51eaccb…` 重拍**）、`03_offerings_preferences.png` 1600×2000（**已按 `51eaccb…` 重拍**）、`04_plan_result.png` 1600×1400、`05_risks_confirmation.png` 1600×1250、`06_architecture.png` 1600×900；模式 1、生产构建预览 `:4173` 采集，逐张取景与「能证明 / 不能证明」见 `SCREENSHOT_INDEX.md`。✅ 先前记录的"分辨率口径不一致"已在 `DEMO_VERSION_LOCK.md` §8 澄清（截图取景窗口宽 1600 × 自适应高度 ≠ 录屏建议 1920×1080）。｜ 负责角色：截图采集人 + 演示负责人。
- [x] **slides content complete（5 页主内容）** ｜ 证据 / 位置：`OPC_FINAL_SLIDES_CONTENT.md`（274 行）含 Slide 1–5 的标题 / bullets / visual suggestion / presenter notes / evidence source / forbidden overclaim，以及「版式与视觉规范」与「截图引用清单」。｜ 负责角色：内容负责人。
- [x] **PPTX 已生成（6 页 = 封面 + 5 页主内容）** ｜ 证据 / 位置：`docs/submission/学航转衔_OPC_答辩稿.pptx`（765 136 字节）；本轮只读解包实测 `ppt/slides/slide1.xml … slide6.xml` = **6 页**；`ppt/presentation.xml` 的 `sldSz` = `cx="12191695" cy="6858000"`，比例 1.778 ≈ **16:9**（注：同一标签的 `type` 属性写作 `screen4x3`，与实际尺寸不符，属生成工具的陈旧标注，不影响实际画幅）。｜ 负责角色：幻灯片制作人。
- [ ] **PPTX 版式目视校验（P0，本轮不可做）** ｜ 证据 / 位置：本环境**无 PowerPoint / LibreOffice**，未产生任何渲染预览 ⇒ 无法确认正文是否 ≥24pt、页脚统一句「固定工具编排原型 · LLM / RAG / GraphRAG 尚未接入 · Real E2E 等级 LEVEL 0」是否每页在位、6 张截图在 16:9 版式内是否被裁掉 `Mock` / 「教学班数据：演示快照（Synthetic）」披露条（`OPC_FINAL_SLIDES_CONTENT.md`「版式与视觉规范」要求不得裁掉）。｜ 负责角色：owner（有 Office 的机器）。
- [x] **4-min script rehearsed twice —— 路线彩排（构建操作者 / 自动化）✅** ｜ 证据 / 位置：`REHEARSAL_LOG.md`（7 434 字节）§1 彩排 #1、§2 恢复测试、§3 彩排 #2；两次均：`/health` = 200、预览 `/api/v1/mock/demo` = 200 且 `X-Data-Source: mock`、8/8 区块锚点可解析、6/6 段画面非空（灰度级 230–254）、Synthetic/Mock 披露可见、第 6 段重复画面问题已消除；`POST /api/v1/plan` = **503 `real_pipeline_not_configured`**（模式 1 预期 fail-closed，无 Mock 回退）；一次**前端预览服务重启恢复**测试通过。｜ 负责角色：构建操作者（自动化）。
- [x] **页面对外文案越界项 = 0（第 2 区副标题已修复）** ｜ 证据 / 位置：PR #51 HEAD `51eaccb1f9b23f9226760eab323028ed85d01b0a` 将 `frontend/src/App.vue` 第 2 区 `subtitle` 由「Course Data 模块**从教务系统中抓取**并标准化的目标学期开课清单…」改为「Course Data 模块负责教学班数据的标准化与结构化；当前比赛演示使用明确标识的 Synthetic 教学班快照（未连接任何实时教务系统）。支持多段排课及中性无排课数据状态（DG-01 / DG-07D）。」；diff = **单个用户可见字符串**（⛔ 无业务逻辑 / API / Planner / Provider / Schema / 后端 / mock 数据 / runtime 改动）；`frontend/src/**` 检索「抓取 / 已连接教务 / 实时教务」= **0 命中**；文案红线审计 PASS；02 / 03 截图已按新 HEAD 重拍。｜ 负责角色：前端文案负责人（已完成）。
- [ ] **4-min script rehearsed twice —— 真人出声计时彩排 ❌** ｜ 证据 / 位置：`REHEARSAL_LOG.md` §1 与 §3 均记「主讲人是否超时 4 分钟：⚠️ **无法判定**（无真人出声；仅记录动作路径耗时 7 554 ms / 7 297 ms）」；§4 第 3 条把「出声计时彩排 ≥2 次」列为 P0 遗留；§3 问题 2 提示第 3 段（50 秒、内容密度最高）最易超时。｜ 负责角色：主讲人。
- [ ] **video recorded** ｜ 证据 / 位置：全仓库 `Get-ChildItem -Recurse -Include *.mp4,*.mov,*.mkv` 返回**空**；`OFFICIAL_RULE_CHECK.md`「必需文件（通用材料清单）」与「视频时长」两行均记「演示视频 MP4 = 未见」；`VIDEO_RECORDING_PLAN.md` 只到「计划」阶段。｜ 负责角色：主讲人 + 录屏操作者。
- [ ] **video privacy checked** ｜ 证据 / 位置：检查清单**已备好但无法执行**——`VIDEO_RECORDING_PLAN.md` §8.1 硬红线（教务登录页 / 凭据 / 真实学号成绩单 / 聊天窗口 / 书签与历史 / DevTools / 本地绝对路径 / 桌面通知）、§8.2 录制前 11 项、§8.3 录制后 7 项逐帧检查，**全部依赖成片**；当前无成片 ⇒ 未完成。｜ 负责角色：录屏操作者 + owner。
- [ ] **official rules verified（父项：任一细分未完成即未完成）** ｜ 证据 / 位置：`OFFICIAL_RULE_CHECK.md` §零 已由 owner 核实 **7 项**（全国赛公开截止 **2026-10-15**；材料四类＝作品简介及承诺书 PDF / 作品介绍文档 PDF / 演示视频 MP4 / 支撑材料选填；视频 ≤10min ≤500MB 且概述≤2 / 核心≤6 / 总结≤2；支撑材料 PDF/ZIP 合计 ≤100MB；**赛道团队 ≤5 人**；官方平台 `aiedu.caet.org.cn`；PPT 仍未解决）；§一 为公开网页逐字来源（S1–S5）用于交叉核对；**仍未解决 4 项**见 §零末节。｜ 负责角色：owner。
  - [ ] **↳ 是否要求 AI 模型真实运行** ｜ 证据 / 位置：`OFFICIAL_RULE_CHECK.md` §零 未解决项 3 与 §一「是否要求 AI 模型真实运行」标 🔴 **高风险不匹配**（赛道定义用「鼓励」而非「必须」；FAQ Q10 又写「作品形式不限」⇒ 二者不可等同，而本项目**无模型运行**）；同项在 §二 再次列为待核实。⛔ 无论核实结果如何，不得把未接入的模型能力写成已接入。｜ 负责角色：owner（门户细则原文）。
  - [ ] **↳ 是否必须现场演示** ｜ 证据 / 位置：`OFFICIAL_RULE_CHECK.md` §零 未解决项 2 与 §一「是否必须现场演示」——通用 FAQ Q9 仅写「现场竞赛不得超出整体时间框架」，**未指明哪些赛道含现场环节**；S4 中「低空装备技术应用赛道实战赛为线下」属**其他赛道**信息，不得套用。｜ 负责角色：owner。
  - [ ] **↳ PPT 格式（是否必需 PPT/PDF、页数上限、是否允许嵌入视频、是否要求 16:9）** ｜ 证据 / 位置：`OFFICIAL_RULE_CHECK.md` §零 **V7 = 仍未解决**（≈ §一「幻灯片格式」的"未核实"）；官方通用材料清单只列四类材料、**不含**幻灯片。当前已产出 16:9 / 6 页 PPTX，但**无法确认它是否被官方接受**。｜ 负责角色：owner。
  - [ ] **↳ 截止时间（全国赛公开 vs 校内/内部，必须分开写）** ｜ 证据 / 位置：`OFFICIAL_RULE_CHECK.md` §零 **V1 = 全国赛报名 / 材料提交截至 2026-10-15**（owner 已核实）；**校内 / 单位内部截止 = `OWNER MUST CONFIRM`**，同节明确⛔ 不得假设其等于全国赛截止，也⛔ 不得据此改写或覆盖任何既有内部时间（含项目此前记录的 **2026-10-08**——本材料**不主张、不修改**该日期，仅提示 owner 确认）。｜ 负责角色：owner（门户 + 校内通知）。
- [ ] **team info verified（本赛道 ≤5 人）** ｜ 证据 / 位置：`OPC_PORTAL_INFO_TEMPLATE.md` 中团队成员 / 负责人 / 学校 / 专业 / 联系方式等仍为 `[OWNER TO FILL]`（grep 命中 **22 处**）；`OFFICIAL_RULE_CHECK.md` §零 **V5 = 赛道页面口径 ≤5 人**（⚠️ 通 FAQ 的"≤6 人"是通用上限，**本赛道更严**，模板已按 ≤5 标注），「团队人数」行记「本项目团队构成**未记录在仓库中**」；模板附录自查项（补齐全部 `[OWNER TO FILL]`）未勾选。｜ 负责角色：owner。
- [ ] **portal fields filled** ｜ 证据 / 位置：`OFFICIAL_RULE_CHECK.md`「提交门户要求」= ⚠️ **未开始**（无门户账号 / 报名记录 / 已上传材料），「本项目实际报名组别 / 赛道」= 仓库内**无报名回执或受理记录**；可复制文本本身已就绪（模板第 1–23 节状态多为「已确定（仓库可核实）」），但**尚未填入任何门户字段**。｜ 负责角色：owner。
- [ ] **官方通用材料（除视频外的其余三类）已生成（补充项）** ｜ 证据 / 位置：`OFFICIAL_RULE_CHECK.md` §零 **V2** / §一「必需文件」记——①**作品简介及承诺书 PDF** = 未见（须门户生成模板后签字）、②**作品介绍文档 PDF** = 未见（口径素材在 `OPC_PITCH_PACK.md`，需导出）、④**支撑材料 PDF/ZIP** = 未见；全仓库 `Get-ChildItem -Recurse -Include *.pdf` 返回**空**。｜ 负责角色：owner + 材料撰写人。
- [x] **Synthetic / Mock provenance consistent** ｜ 证据 / 位置：同一条逐字披露口径在 `DEMO_VERSION_LOCK.md` §6、`SCREENSHOT_INDEX.md`（第 79–80 行，声明逐字来自 `frontend/src/utils/labels.ts`）、`OPC_FINAL_4MIN_DEMO.md` §0、`VIDEO_RECORDING_PLAN.md` §3、`OPC_PITCH_PACK.md` §8、`OPC_PORTAL_INFO_TEMPLATE.md` §23、`docs/demo/COMPETITION_STARTUP.md` §0 中一致（「教学班数据：演示快照（Synthetic）」；「模式 1 回放预置结果、**不执行** Curriculum / Planner」；「实际执行 ≠ 输入已获真实学校来源认证」）；四个 `mock_data/*.json` 的 SHA-256 与锁定文档**逐字节一致**（本轮复算）。⚠️ 两处**相邻**不一致见 P1（截图分辨率口径、`OPC_FINAL_SLIDES_CONTENT.md` 截图免责句）。｜ 负责角色：口径 / 文档负责人。
- [x] **no LLM/RAG overclaim** ｜ 证据 / 位置：本轮逐文件核对，**未发现**任何肯定式「已接入 LLM / RAG / GraphRAG」或「自然语言偏好解析已实现」的表述；且各材料**自带禁止清单**——`OPC_FINAL_4MIN_DEMO.md` §0.1 全片禁语、`OPC_PITCH_PACK.md`「表述红线」表、`OPC_JUDGE_QA_SHORT.md` 附录两类禁止表述、`OPC_FINAL_SLIDES_CONTENT.md` 每页 §x.6「forbidden overclaim」、`OPC_PORTAL_INFO_TEMPLATE.md` §23 第 1 条。⚠️ 成品（PPTX 讲稿 / 视频口播 / 门户文本）仍须按同一红线复核。｜ 负责角色：口径负责人 + 主讲人。
- [x] **no global-optimum claim** ｜ 证据 / 位置：同上批文件对「全局最优 / CP-SAT / ILP 已求解 / 自动调班 / 自动选课 / 偏好全部生效」的明文禁止——`OPC_JUDGE_QA_SHORT.md` Q6（「不是。我们没有把这个问题建模成全局优化问题」）、`OPC_FINAL_SLIDES_CONTENT.md` Slide 3 §3.6 与 Slide 5 §5.3 固定禁止表述条、`OPC_FINAL_4MIN_DEMO.md` §0.1、`OPC_PITCH_PACK.md` 红线表。｜ 负责角色：口径负责人 + 主讲人。
- [ ] **links tested** ｜ 证据 / 位置：唯一**实测可用**的链接是本机 `http://127.0.0.1:4173` 与 `http://127.0.0.1:8000/health`（`REHEARSAL_LOG.md` 彩排 #1 / #2 = 200，含一次重启后复测）；面向评委的 **Demo URL / Video URL / Slides 链接尚不存在**（`OPC_PORTAL_INFO_TEMPLATE.md` 对应字段为 `[OWNER TO FILL]`）⇒ 无链接可测。｜ 负责角色：owner。
- [ ] **final files named correctly** ｜ 证据 / 位置：现有文件命名**内部一致**（`assets/01..06_*.png`、`学航转衔_OPC_答辩稿.pptx`、`VIDEO_RECORDING_PLAN.md` §7.1 约定 `xuehang-opc-final-4min-<日期>-<主/备>.mp4` 且不含真实姓名 / 学号 / 单位）；但 `OFFICIAL_RULE_CHECK.md`「命名要求」= **未核实**（⛔ 不得自创命名规则当作官方要求），且视频 / PDF / 申报书成品均未生成 ⇒ 无法判定「正确」。｜ 负责角色：owner。
- [ ] **submission portal owner review** ｜ 证据 / 位置：门户提交动作**未开始**（见「portal fields filled」）；`OFFICIAL_RULE_CHECK.md` §四 明确「本项目当前不主张任何官方资格结论」，须由 owner 逐字复核全套材料后才可提交。｜ 负责角色：owner（最终签核）。

**本分区完成度：9/25（按当前真实状态；文案越界项修复后新增 1 项已完成，总项数 25）**

---

## P1 STRONGLY RECOMMENDED

- [ ] **截图替代方案（若某张需重拍）** ｜ 证据 / 位置：`SCREENSHOT_INDEX.md` 只给出 6 张的取景与说明，**未提供任何备选图或重拍指引**；`assets/` 实测仅 6 个 PNG（`Group-Object Extension` = 6 × `.png`）。｜ 负责角色：截图采集人 + 演示负责人。
- [ ] **幻灯片导出 PDF 备份** ｜ 证据 / 位置：全仓库 `*.pdf` 检索为**空**；PPTX 虽已生成（6 页 / 16:9），但尚无 PDF 兜底（现场机器若无 PowerPoint 或字体缺失时无法放映）。｜ 负责角色：幻灯片制作人。
- [ ] **视频字幕 / 封面** ｜ 证据 / 位置：`VIDEO_RECORDING_PLAN.md` 全文 grep「字幕 / 封面 / 片头 / 片尾」**无命中** ⇒ 字幕与封面既未计划也未制作。｜ 负责角色：录屏操作者 + 主讲人。
- [ ] **Q&A 真人演练（Q1–Q14）** ｜ 证据 / 位置：问答素材**已就绪**——`OPC_JUDGE_QA_SHORT.md`（12 + 2 问，每题 20–40 秒口播 + 「⛔ 不要这样说」）；但**无任何演练记录**（`REHEARSAL_LOG.md` 只覆盖演示路线，未含问答环节）。｜ 负责角色：主讲人 + 团队。
- [ ] **演示现场备份机（第二台设备外录 + 双存放）实测** ｜ 证据 / 位置：`VIDEO_RECORDING_PLAN.md` §7.1 已计划「备用录设备 = 第二台设备外录」「成片与素材双存放」，但**未实测**，也无设备清单落库。｜ 负责角色：录屏操作者。
- [x] **`docs/demo/DEMO_RECOVERY.md` 一页速查** ｜ 证据 / 位置：文件**存在**（1 010 行），含 §2「一分钟速查表」（第 126 行）与 §13「最小可信演示路径（2 分钟兜底）」（第 948 行），另有 §3–§12 逐类故障的四步查法；`VIDEO_RECORDING_PLAN.md` §10 与 `DEMO_VERSION_LOCK.md` §7 均指向它。⚠️ 「打印版单页卡片」尚未单独产出（属 P2）。｜ 负责角色：演示操作者。
- [ ] **把彩排记录补成真人计时证据** ｜ 证据 / 位置：`REHEARSAL_LOG.md` §1 / §3 的「主讲人是否超时 4 分钟」两处均为「⚠️ 无法判定」，§4 第 3 条把「出声计时彩排 ≥2 次」列为遗留 ⇒ 需补入**每段真人实测秒数**与是否超时结论。｜ 负责角色：主讲人。
- [ ] **视频对齐官方三段结构** ｜ 证据 / 位置：`OFFICIAL_RULE_CHECK.md` Q12 记官方口径「视频**通常**分为三段：概述 ≤2 分钟、核心场景演示 ≤6 分钟、效果总结 ≤2 分钟」；而现有脚本是**六段式 4:00**（`OPC_FINAL_4MIN_DEMO.md` §1），两者**尚未做映射**。4:00 满足 ≤10 分钟上限，但三段归属与「效果总结须如实写为未做效果验证」的落点尚未在成片结构中体现。｜ 负责角色：主讲人 + 录屏操作者。
- [ ] **统一截图分辨率口径** ｜ 证据 / 位置：本轮实测 6 张 PNG 均为 **1600px 宽**（高 900–1400，属整页长图），而 `DEMO_VERSION_LOCK.md` §4.1 记录「浏览器缩放 100%、窗口 **1920×1080**」——两者**不一致**；需确认哪一个是权威口径（是包装页视口设置不同，还是采集后缩放），并回填版本锁定文档，同时确认 1600px 宽截图上小字在 16:9 幻灯片中可读。｜ 负责角色：截图采集人 + owner。
- [ ] **更新 `OPC_FINAL_SLIDES_CONTENT.md` 截图引用清单的过时免责句** ｜ 证据 / 位置：该文件「截图引用清单」段仍写「⚠️ 以下 6 张截图**由另一位同事生成**，本文件只引用文件名；⛔ 本文件未创建、也未声称这些文件已生成」，而 6 张截图**现已存在**（见 P0「screenshots complete」）⇒ 免责句已与现状不符，须改为如实描述。｜ 负责角色：内容负责人。
- [ ] **演示现场降级路径演练（后端重启 / 端口占用 / 代理失效）** ｜ 证据 / 位置：`REHEARSAL_LOG.md` §2「未覆盖」明确列出这三类场景未实测（仅前端 preview 重启已测），处置步骤虽已在 `docs/demo/DEMO_RECOVERY.md` §3 / §4 / §7 写好，但**未演练**。｜ 负责角色：演示操作者。

**本分区完成度：1/11（按当前真实状态）**

---

## P2 OPTIONAL

- [ ] **PPTX 版式微调（间距 / 对齐 / 页脚统一句位置）** ｜ 证据 / 位置：依赖 P0「PPTX 版式目视校验」的结论；`OPC_FINAL_SLIDES_CONTENT.md`「版式与视觉规范」要求每页页脚统一一行，需目视后统一。｜ 负责角色：幻灯片制作人。
- [ ] **配色统一（最多 2 个强调色：深蓝 = 实际执行代码 / 灰或米黄 = 输入来源）** ｜ 证据 / 位置：规范已写在 `OPC_FINAL_SLIDES_CONTENT.md`「版式与视觉规范」（⛔ 不用高饱和渐变大色块），但**是否已落到 PPTX** 未校验。｜ 负责角色：幻灯片制作人。
- [ ] **片头 / 片尾（标题卡、结尾定格字幕）** ｜ 证据 / 位置：`VIDEO_RECORDING_PLAN.md` 全文无「片头 / 片尾」内容；§5 仅要求 3:55–4:00 画面静止定格（可在此基础上加结尾字幕）。｜ 负责角色：录屏操作者。
- [ ] **额外截图（数据流图 / 工具链 / 8 场景路线特写）** ｜ 证据 / 位置：`assets/` 仅 6 张（`SCREENSHOT_INDEX.md` 对应 6 张）；`06_architecture.png` 为静态 HTML/CSS 渲染的架构图，尚无数据流图与工具链截图。｜ 负责角色：截图采集人。
- [ ] **幻灯片 PDF 加书签 / 备注页（speaker notes）导出** ｜ 证据 / 位置：`OPC_FINAL_SLIDES_CONTENT.md` 每页 §x.4 已写好 presenter notes，但**未导出为 PPTX 备注页或 PDF 备注版**。｜ 负责角色：幻灯片制作人。
- [ ] **录屏素材 60fps 与分段留存（便于二次剪辑）** ｜ 证据 / 位置：`VIDEO_RECORDING_PLAN.md` §1.1 允许 60 fps、§0 要求「整段一镜到底」⇒ 分段留存属可选增强，尚未执行。｜ 负责角色：录屏操作者。

**本分区完成度：0/6（按当前真实状态）**

---

## 当前 P0 阻塞清单

> 覆盖上方所有未勾选的 P0 条目（含 `official rules verified` 的 4 项细分，父项不再重复计数）。

| 阻塞项 | 为什么阻塞 | 解除条件 | 建议责任人 |
|---|---|---|---|
| PR #51 reviewed | 仓库内**无评审记录**；`origin/main` 仍 `0 behind / 2 ahead`（未合并）；本机 `git ls-remote origin refs/pull/*` 无返回，无法核实 PR 状态 | 在 GitHub PR #51 页面确认评审 / 合并状态，并把结论（评审人、结论、日期）回填 `DEMO_VERSION_LOCK.md` §1 | owner + reviewer |
| PPTX 版式目视校验 | 本环境**无 PowerPoint / LibreOffice**，无任何渲染预览；字号是否 ≥24pt、页脚统一句是否每页在位、6 张截图是否裁掉 Mock / Synthetic 披露条 均未验证 | 在有 Office 的机器打开 `docs/submission/学航转衔_OPC_答辩稿.pptx` 逐页目视（重点：正文 ≥24pt、页脚统一句、披露条完整、无溢出 / 错位 / 缺字） | owner（有 Office 的机器） |
| 4-min script 真人出声计时彩排 | 两次彩排均为**自动化路线彩排，无真人出声**，「是否超时 4 分钟」在 `REHEARSAL_LOG.md` 中两处均为「无法判定」；第 3 段（50 秒）密度最高 | 主讲人按 `OPC_FINAL_4MIN_DEMO.md` **出声计时彩排 ≥2 次**，把每段实测秒数与是否超时补进 `REHEARSAL_LOG.md` §4 | 主讲人 |
| video recorded | 仓库内无 `*.mp4 / *.mov / *.mkv`；官方要求 MP4、≤10 分钟、≤500MB；录制计划已完成但未执行 | 按 `VIDEO_RECORDING_PLAN.md` 整段录制 ≥2 遍，产出命名不含个人信息的成片，并自检 500MB | 主讲人 + 录屏操作者 |
| video privacy checked | 无成片可检查 ⇒ §8.1 硬红线、§8.2 录制前清理、§8.3 七项逐帧检查**全部无法执行** | 成片产出后逐项完成 §8.3（披露出现 ≥2 次、无凭据 / 学号 / 成绩单 / 绝对路径 / 外部网址 / DevTools / 弹窗） | 录屏操作者 + owner |
| official rules verified（父项） | 本赛道**细则未获取**：官网赛道介绍以弹层 / 图片承载不可读、`caet.org.cn` 返回 403、PDF 附件不可解析；仓库内无官方规则文件或报名回执 | 登录门户取得本赛道细则 / 参赛指南原文，回填 `OFFICIAL_RULE_CHECK.md` 第一、二节 | owner |
| ↳ 是否要求 AI 模型真实运行 | 赛道定义用「**鼓励**」、FAQ Q10 说「作品形式不限」，而「鼓励」≠「必须」；本项目**无模型运行** ⇒ 若为硬性门槛，作品范围甚至赛道归属需重新决策（官方文件自评：🔴 高风险不匹配） | 拿到细则原文确认是否为硬性要求；⛔ 无论结果如何，**不得**把未接入的模型能力写成已接入 | owner |
| ↳ 是否必须现场演示 | 通用 FAQ Q9 只说「现场竞赛不得超出整体时间框架」，**未指明哪些赛道含现场环节**；已知的线下实战赛属其他赛道 | 细则 / 组委会通知确认是否需现场路演答辩、是否需带设备与网络，据此决定是否需要公网 Demo | owner |
| ↳ PPT 格式 | 官方通用材料清单（Q10）**未包含幻灯片**，S1–S5 均未规定页数 / 格式 / 是否允许嵌入视频 ⇒ 已产出的 16:9 / 6 页 PPTX 是否被接受**无从确认** | 门户「材料上传」页与赛道细则确认：是否必需 PPT/PDF、页数上限、是否允许嵌入视频 | owner |
| ↳ 截止时间 | 仅有「报名阶段 2026-06-29–10-15」的**官方页面转述**，且**未区分**「报名信息提交」与「作品 / 初评材料提交」；检索到的 2026 年日期无法独立核验 | 门户「我的申报」页确认确切截止日与逾期补正窗口，并回填 `OFFICIAL_RULE_CHECK.md` | owner |
| team info verified | `OPC_PORTAL_INFO_TEMPLATE.md` 中团队 / 学校 / 专业 / 联系方式等 **22 处**仍为 `[OWNER TO FILL]`；仓库内无团队构成记录 | owner 按「≤6 人、指定 1 名主持人」确认真实信息并回填模板（并核对本赛道是否更严） | owner |
| portal fields filled | 无门户账号 / 报名记录 / 已上传材料（`OFFICIAL_RULE_CHECK.md` 记「⚠️ 未开始」） | 按官方流程执行：注册 → 选组别 + 细分赛道 → 填团队信息 → 下载申报表签字盖章 → 上传全套材料 → 提交 | owner |
| 官方通用材料其余三类（补充项） | 申报书及承诺书、作品介绍文档 PDF、支撑材料 PDF/ZIP **均未见**；全仓库无 `*.pdf` ⇒ 材料清单四类中仅视频有脚本、其余三类无成品 | 由 `OPC_PITCH_PACK.md` / `OPC_PORTAL_INFO_TEMPLATE.md` 导出作品介绍 PDF；申报书从门户生成后签字（学生团队通常无需盖章）；支撑材料合计 ≤100MB | owner + 材料撰写人 |
| links tested | 面向评委的 **Demo URL / Video URL / Slides 链接尚不存在**（字段为 `[OWNER TO FILL]`）；仅本机 `127.0.0.1` 地址实测 200 | 链接产生后逐条实测可访问，并确认页面 / 文档中不含隐私信息与本地绝对路径 | owner |
| final files named correctly | 官方**命名规则未核实**（⛔ 不得自创规则），且视频 / PDF / 申报书成品未生成 ⇒ 无法判定命名是否正确 | 门户上传页确认命名示例或字数限制后统一命名，并把结论写入 `OFFICIAL_RULE_CHECK.md` | owner |
| submission portal owner review | 门户提交动作未开始；`OFFICIAL_RULE_CHECK.md` §四 明确本文件不主张任何资格结论，须 owner 签核 | owner 逐字复核全套材料（数据来源披露是否保留、红线用词是否清除）后完成门户提交 | owner（最终签核） |

---

## 唯一建议的下一步

**由 owner 登录官方唯一门户 <http://aiedu.caet.org.cn>，进入「我的申报 / 本赛道细则」，把四项未核实规则——①PPT 是否必需及格式与页数上限、②是否必须现场演示、③是否要求 AI 模型真实运行、④报名提交与作品提交的确切截止时间——逐条抄成原文并回填 `docs/submission/OFFICIAL_RULE_CHECK.md` 第一、二节。**

理由（一句话）：这是**唯一无法由团队在本地完成**、且会直接决定其余材料是否需要返工的前置项——若「必须现场演示」或「作品须真实运行 AI 模型」成立，则视频形态、PPT 是否必需、乃至作品范围与赛道归属都要重新决策；在它落定之前，继续制作视频与门户材料存在整体返工风险。
