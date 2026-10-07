# Case A 学业路径规划 · Demo Runbook

面向**演示者**的最短可复现路径。目标：在本地把「学航·转衔」的完整闭环跑起来，
并知道每一步应该看到什么、出问题先查什么。

> ⚠️ **口径纪律**：本 Runbook 只描述**已经实现**的功能。
> 不允许写成"AI 自动推理已上线""CP-SAT 已上线""自动替学生换班""预测未来教学班"。

---

## 0. 这套系统实际做什么

```text
真实成绩单 PDF
→ Curriculum 识别（补修任务 MakeupTask）
→ 本学期真实教学班（CourseOffering）
→ 你的当前课表 current_schedule
→ 你的偏好 Preference
→ RestrictedPlanner（受限确定性规划）
→ 换班建议（结构化，**只是建议**）
→ 你**显式确认**某一条
→ 本学期可执行课表（周课表）
→ 未来学期**课程级**学业路径（AcademicRoadmap）
```

两条必须记住的边界：

| | 当前学期 | 未来学期 |
|---|---|---|
| 粒度 | **教学班级**（section-level） | **课程级**（course-level） |
| 数据 | 真实 `CourseOffering` | **培养方案事实**；⛔ 不需要任何 Course Data |
| 会不会出现教师 / 教室 / 时间 | 会（有真实数据才显示） | ⛔ **绝不出现** |

---

## 1. 准备：私有 Case A artifacts（⛔ 不进 Git）

需要本机已存在（**不得提交到仓库**）：

```text
<private>/curriculum/case-a.json          # 目标培养方案（网络空间安全）
<private>/case-a-course-data.sqlite3      # 已验收的南校园 + 深圳校区 scoped Course Data
一份你自己的中山大学成绩单 PDF             # 或仓库内的合成 fixture（见 §5）
```

两个 campus acceptance SHA-256 由 artifact 提供方给出。

---

## 2. 启动后端

在仓库 `backend/` 目录下（PowerShell）：

```powershell
$env:APP_CASE_A_DEMO_ENABLED="1"
$env:APP_CASE_A_DEMO_CURRICULUM_CASE_PATH="<private>\curriculum\case-a.json"
$env:APP_CASE_A_DEMO_COURSE_DATA_SQLITE_PATH="<private>\case-a-course-data.sqlite3"
$env:APP_CASE_A_DEMO_SEMESTER="2026-1"
$env:APP_CASE_A_DEMO_SOUTH_ACCEPTANCE_SHA256="<south sha256>"
$env:APP_CASE_A_DEMO_SHENZHEN_ACCEPTANCE_SHA256="<shenzhen sha256>"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

可选：

```powershell
# 未来路线图的上界学期（缺省 = 培养方案链尾，Case A 为 2028-2）
$env:APP_CASE_A_DEMO_ROADMAP_LAST_SEMESTER="2028-2"
```

**任一项缺失或 SHA 不匹配 ⇒ 接口返回 503 / 422，⛔ 不会静默使用 Mock。**

验证：`http://127.0.0.1:8000/api/v1/health`

---

## 3. 启动前端

```powershell
cd frontend
$env:VITE_CASE_A_DEMO_ENABLED="true"       # 或在 .env.local 中设置
npm install                                 # 首次
npm run dev
```

打开终端提示的地址（默认 `http://127.0.0.1:5173/`）。

---

## 4. 演示流程（逐步）

| 步骤 | 操作 | 应该看到 |
|---|---|---|
| 1 | 上传成绩单 PDF | 成绩单摘要：课程条数、学期数；**待核验课程号计数**（真实 PDF 没有官方课程号） |
| 2 | 选择当前课表：搜索课程 → 加入；或手工录入后**勾选确认** | 每条身份是 `学期 + 课程号 + 教学班号`；`meetings=[]` 显示**排课信息待核验** |
| 3 | 添加意向课程 | 只写入课程级偏好，重复课程不重复加入 |
| 4 | 设置偏好 | 学分上限 / 跨校区 / 不方便时间 |
| 5 | 点「生成并优化我的转专业学业方案」 | 补修缺口、本学期推荐课表、待确认调整、未来学期路径 |
| 6 | 看**本学期推荐课表** | 按真实教学班绘制；教师缺失显示「任课教师：待核验」 |
| 7 | 看**待你确认的调整** | 结构化换班建议：当前教学班 → 候选教学班、候选时间、校区/教室、原因 |
| 8 | 点某条建议的「采用调整」 | 只有**点击后**才调用后端；返回后端计算的新课表 |
| 9 | 看周课表是否刷新 | 该课程换成候选教学班；**其余课程不变** |
| 10 | 看**未来学期修读路径** | 真实学期标签 + **培养方案第 N 学期** + 课程名/课程号/学分/必修或选修 |
| 11 | 看**选修学分进度** | 最低学分要求 / 已确认完成 / 本学期已选 / 规划前缺口 / 本次规划 / 规划后仍缺 |
| 12 | 看 unresolved / warnings | 需要人工确认的事项与规划说明（⛔ 不被隐藏） |

「暂不调整」只在本页收起该条建议，**不改后端状态**。

---

## 5. 没有真实 artifact 时怎么演示

- 后端：`backend/tests/test_case_a_demo_e2e.py` + `tests/pdf_fixtures.py`
  提供**合成**成绩单 PDF 与合成培养方案，可零网络跑通闭环；
- 前端：全部 233 个前端测试都通过 mock 的 API 层运行，⛔ 不联网；
- ⛔ 合成数据**必须**标记为合成，不得在演示中冒充真实教务数据。

---

## 6. 口径红线（演示时不要说）

⛔ 不要说：

- "AI 已经自动推理并规划"（当前是**固定工具编排**，AI 增强待接入）
- "CP-SAT / ILP 已上线"（当前是**确定性启发式**）
- "系统自动帮你换班"（必须**你本人确认**）
- "预测未来学期的教学班 / 教师 / 教室"（未来学期**只有课程级**）
- "全校完整 / 完整学期 Course Data"（当前是**南 + 深圳 case-scoped**，
  `is_full_semester = false`）
- "教师数据已完整覆盖"（真实数据里教师普遍缺失，显示为**待核验**）

✅ 可以说：

- 固定工具编排，AI 增强待接入
- 当前学期精确到教学班
- 未来学期课程级路径规划
- 用户确认后才换班
- 真实南校园 + 深圳校区 case-scoped Course Data

---

## 7. 出问题先查什么

| 现象 | 先查 |
|---|---|
| 页面提示运行时未装配 / 503 | 五个 `APP_CASE_A_DEMO_*` 环境变量是否齐全、SHA 是否匹配 artifact |
| 422 `semester_not_in_scope` | `APP_CASE_A_DEMO_SEMESTER` 是否等于 acceptance 绑定的学期 |
| 教学班列表为空 | SQLite 路径、acceptance SHA、以及该学期是否在 scoped 范围内 |
| 「采用调整」点了没变化 | 看返回的 `reason`：多半是候选不属于同一课程 / 同一学期，或候选重新校验不是 CLEAR |
| 未来学期区块不显示 | 后端是否返回了 `roadmap`；若是 `null`，页面会显示 `roadmap_note` 说明原因 |
| 总是显示「任课教师：待核验」 | 真实采集数据里教师字段普遍缺失；⛔ 系统**不编造**教师 |
| `meetings=[]` 显示「排课信息待核验」 | 这是 UNKNOWN，**不是**"没有课"，也**不是**"无冲突" |
