# 个人规划闭环设计（Final Upgrade · Agent A）

> 分支：`feature/personal-planning-pipeline`（base = `feature/final-upgrade`）
> 状态：**已实现，待项目 Architecture Review**
> ⚠️ 本轮全部验证使用**人工构造 Mock**；**当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**

## 1. 要解决的问题

旧 Case A 由**固定 case 文件**驱动：一位学生的已修事实、个案匹配规则与范围裁定
全部写在 case JSON 里。Case A 因此可用，但**换一个学生就不成立** ——
个人规划入口必须能让另一位学生用自己的材料，在**同一个已核验目标培养方案**上
独立算出自己的结果。

三条硬要求：

1. **不得继承** Case A / 其他学生的 `satisfied` 状态或个案认定；
2. **不得伪造**培养方案：只能用已核验、来源声明支持的版本；
3. **不得重写** Curriculum 的认定 / 匹配 / 组学分 / scope 规则，
   也不得在 Planner 内另写认定。

## 2. 数据流

```text
GET /api/v1/personal-planning/curriculum-versions
        ↑
已核验版本目录（app/curriculum/catalog.py）
        ↓  resolve（不可选版本 → 明确拒绝）
POST /api/v1/personal-planning/plan
        ↓
app/personal/planning.normalize_personal_plan_request(...)
        ↓  completed_source_id 由**请求体内容摘要**派生（服务端给出）
本学生 CurriculumCase（复用既有 CurriculumCase / build_curriculum_diff）
        ↓
既有 CurriculumCaseProvider.get_makeup_tasks()  →  MakeupTask[]
        ↓  （可选）已冻结的 PlannerProvider.plan(...) 四参数签名
PersonalPlanResult：版本元信息 + 补修任务 + 可选规划结果 + 跳过原因
```

## 3. 模块与文件

| 文件 | 职责 | 是否公共契约 |
| --- | --- | --- |
| `backend/app/curriculum/catalog.py` | 已核验版本目录读取器 + fail-closed 解析 | 否（内部格式） |
| `backend/app/personal/student_input.py` | 本学生输入的显式模型与归一化 | 否 |
| `backend/app/personal/planning.py` | 本学生 case 组装 + 结果对象 | 否 |
| `backend/app/api/personal_plan.py` | 两条 API + 请求 / 响应包络 | 否（路径需负责人确认） |
| `backend/app/services/personal_runtime.py` | 目录的显式装配边界 | 否 |
| `backend/app/planner/credit_limit.py` | 学分上限的确定性接纳校验 | 否（Planner 内部） |

`backend/app/main.py` 只增加了**一行** `include_router`；⛔ 未改动任何现有路由。

## 4. 关键设计决定

### 4.1 已修来源由服务端派生，不信任学生行

`completed_source_id` 由**请求体内容摘要**（`personal-upload://sha256:<digest>`）派生，
⛔ 不读学生行里的来源字段。因此：

- 一份材料无法靠改一个标签冒充成"另一个来源"；
- 两位不同学生（不同材料）**必然**得到不同的来源 id；
- 归一化层还会拒绝任何 `source_id` 与本学生来源不符的输入。

### 4.2 目录只暴露"可选"版本

`catalog_version` 是本模块内部声明（`1`）。一个版本只有同时满足
`verification.verified == true`（带非空 `evidence`）、`supported == true`
且课程 / 组记录能被既有 normalizer 接受，才进入可选列表。其余进入
`rejected`，带固定原因码：

```text
artifact_unreadable / artifact_format_unsupported / entry_invalid
not_verified / unsupported_by_source / version_identity_conflict
```

⛔ 目录缺失 = **没有可选版本**（空目录，不是异常）：API 明确回答"无可用版本"，
⛔ 不回退到 Case A 或任何演示方案。

### 4.3 不做 docx 解析

目录 artifact 只能给出**既有 reader 已支持**的结构化 `course_records`。
真实培养方案 Word 的解析仍走既有 `app.curriculum` 入口，
本模块⛔ 不为个人入口另造一条解析路径（那会制造"看起来支持了，其实没有"的假象）。

### 4.4 规划假设与正式认定严格分离

`planning_assumptions[]` 是学生自述（"我认为可抵"），带固定标签
`planning_assumption_not_a_recognition`：

- ⛔ 绝不改变任何 `MakeupTask.status`；
- ✅ 只出现在结果 `notes` 里，让人工能区分"有凭据的认定"与"学生假设"；
- `ConfirmedRecognition` 走既有路径，必须带 `evidence` 且指向**本人**修读记录。

### 4.5 为什么不复用 `PlanningOrchestrator`

`PlanningOrchestrator` 只能从它自己持有的 `CurriculumProvider` 取 `MakeupTask[]`，
而个人规划的 `MakeupTask[]` 必须来自**本学生** case。
把本学生 case 伪装成一个 provider 塞进 Orchestrator 只会制造假的边界。
因此个人规划显式使用**同一个已冻结的** `PlannerProvider.plan(...)` 四参数签名：

- ✅ 教学班供给仍然只来自**已装配的** production Course Data（`runtime.orchestrator.course_data`）；
- ✅ `MakeupTask[]` 来自本学生 case；
- ⛔ 不新增参数、⛔ 不改返回类型、⛔ 不复制任何 Planner 逻辑。

`PersonalPlanResult.__post_init__` 还会拒绝"Planner 返回了本学生任务之外课程"的结果。

### 4.6 学分上限（行为变更，需确认）

见 `docs/status/planner.md` 的"学分上限接纳校验"一节。
一句话：学生**本人显式声明**的 `max_credit` 从"语义未确认"升级为
"对 `原课表 + 累计新增` 的确定性接纳判断"，并且**无法证明时不放行**。

## 5. 本轮明确不做（BLOCKED / 延后）

| 项 | 原因 |
| --- | --- |
| 真实已核验目录内容 | `APP_PERSONAL_CATALOG_DIR` 必须由负责人提供；⛔ Builder 不批准版本 |
| 第二位学生的真实脱敏成绩 | 未交接；只用显式 Mock |
| 前端接入（版本 / 成绩预览） | 共享入口 `frontend/src/App.vue` 与 Agent B 冲突风险高；本轮只做后端 + 联调说明 |
| 课表图片 OCR | 任务书列为 **P2 延后**；本轮不抢占，也⛔ 不以假 OCR 冒充 AI |
| `max_credit` 语义的最终口径 | 需负责人确认（哪些课计入、是否含重修） |
| 新 API 路径的正式批准 | `/api/v1/personal-planning/*` 需负责人确认 |

## 6. 怎么运行与怎么测试

```powershell
# 1) 指向一个**已核验**目录（本轮用测试目录；真实目录由负责人提供）
$env:APP_PERSONAL_CATALOG_DIR = "<local verified catalog dir>"

# 2) 启动后端（在 backend/ 下）
python -m uvicorn app.main:app --reload

# 3) 列可选版本
curl http://127.0.0.1:8000/api/v1/personal-planning/curriculum-versions

# 4) 跑个人规划
curl -X POST http://127.0.0.1:8000/api/v1/personal-planning/plan `
     -H "Content-Type: application/json" -d @request.json
```

```powershell
# 测试（Windows 上必须开 UTF-8，否则既有用例会因 GBK 解码失败）
$env:PYTHONUTF8 = "1"
cd backend && python -m pytest -q
```

## 7. 出问题先检查什么

1. **503 `personal_catalog_not_configured`** → `APP_PERSONAL_CATALOG_DIR` 未设置 / 目录不存在；
2. **版本不在可选列表** → 看 `GET .../curriculum-versions` 的 `rejected[].code`：
   `not_verified` 说明缺核验依据，`unsupported_by_source` 说明来源明确不支持；
3. **422 `personal_plan_input_invalid`** → 学生输入字段名 / 来源一致性 / 版本 id 不合法；
4. **422 `personal_plan_not_projectable`** → 既有 Curriculum 规则判定本次不能投影
   （例如组学分计划不足、目标方案不完整）；这是**既有规则**的结论，不是新入口的 bug；
5. **`planning_skipped_code = no_course_data`** → 没有已装配的真实教学班供给；
   这是**当前正确状态**，⛔ 不代表功能故障，也⛔ 不会回退到 Mock。
