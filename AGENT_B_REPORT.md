# AGENT_B_REPORT.md · Final Upgrade Agent B —— 有依据的规则解释与最小 UI

- **Agent**：Final Upgrade Agent B（Builder B）
- **分支**：`feature/explanation-agent`（基于 `feature/final-upgrade`）
- **日期**：2026-10-08
- **模式**：无人值守；仅提交 / 推送自己的分支，**未合并任何 PR**，**未写入 main / final-upgrade**
- **数据状态**：**Mock**（`mock_data/` 演示数据）。本轮**没有**真实数据链路端到端跑通。

---

## 1. 一句话结论

在不改动任何计算、公共 Schema、既有 API 路径与 Provider 签名的前提下，
新增了**只读的解释服务 + 新增私有解释接口 + 最小前端入口**：
学生可以追问「这条补修判定 / 这个教学班 / 这条调班 / 这条风险 / 这条未决事项为什么是这样」，
系统给出的每一条说明都能追溯到**真实存在的来源字段**，并明确区分
「确证规则 / 学生输入或假设 / 系统建议 / 未知 / 上下文不存在」与「仍需人工确认」。

**AI 是否被实际调用：没有。** 当前所有解释均由**确定性规则模板**生成，
界面与接口响应都明确标注 `rule_based_template`（**不是**模型生成）。
模型适配层只是预留的、需显式注入的接口，且即使注入也必须通过事实绑定校验。

---

## 2. 实现点

### 2.1 后端：只读解释服务（新增包，不参与任何计算）

| 文件 | 职责 |
| --- | --- |
| `backend/app/explanation/models.py` | 解释线格式：证据引用（对象 + 字段 + 原始取值）、证据性质、证据强度、待人工确认、生成方式、来源概况 |
| `backend/app/explanation/templates.py` | 确定性模板：只复述字段原文，不新增课程 / 学期 / 学分 / 时间 / 先修 / 等价关系 |
| `backend/app/explanation/adapter.py` | **可选**模型适配层 + 事实绑定校验（防幻觉门槛）；默认未配置 |
| `backend/app/explanation/service.py` | 事实平面、摘要、逐条生成、只读自检、上下文一致性警告 |
| `backend/app/api/explanation.py` | **新增私有接口** `POST /api/v1/explanation/plan` |
| `backend/app/main.py` | **仅 +1 行** router 注册（最小注册改动） |

解释覆盖的条目（每条都是**只读**消费已有字段）：

| 条目类型 | 被解释的来源字段 | 解释说什么 |
| --- | --- | --- |
| `plan_status` | `PlanResult.status` / `objective_summary` + 四个列表长度 | 整体状态含义、条目计数、不重新求解 |
| `makeup_task` | `MakeupTask.status` / `reason` / `source_evidence` / `prerequisites` / `recommended_semester` / `deadline_semester` | 该补修判定的含义与依据；四种状态给出**不同且准确**的说明 |
| `selected_class` | `MakeupTask.*` + `CourseOffering.meetings` / `remaining_capacity` | 为什么方案里排了这个教学班；**不重做冲突检测** |
| `change` | `PlanResult.changes[].reason` / `from_class` / `to_class` + 两个 `CourseOffering` | 调班原因**原文** + 两个教学班的排课事实；明确"未独立验证 Planner 原因" |
| `risk` | `PlanResult.risks[].level` / `reason` | 风险等级与原因原文；不补充风险类型 |
| `unresolved` | `PlanResult.unresolved[].type` / `message` | 未解决事项原文；不当作已确认结论 |

**必须强调的几条安全性设计**：

1. `possibly_equivalent` **绝不**被写成"学校已批准等价"：解释明确写"**尚未**获得课程等价认定"，
   并把"是否互认需要教务 / 人工确认"放进待确认事项。
2. `satisfied` **不等于**学校已完成正式认定：解释明确提示"正式认定仍以教务审批为准"。
3. `meetings = []` 只说"当前来源快照没有可用排课信息"，**绝不说成**无课 / 异步 / 时间自由，
   也不声称"不存在时间冲突"。
4. 缺少 `MakeupTask` 上下文时，解释**不会猜**补修状态：标记为「上下文不存在」（`absent`），
   与"字段值为空"严格区分。
5. 方案里引用了上下文找不到的课程 / 教学班时，**如实进 `warnings`**，不补一份排课信息。

### 2.2 只读保证（可核对，不靠口头承诺）

- 响应返回被解释方案的指纹 `plan_result_digest`（`sha256(canonical_json(PlanResult))`）；
- 服务在输出前**重算摘要**，不一致即中止（`ExplanationMutationDetected`）；
- 测试用 `copy.deepcopy` 断言输入对象（`PlanResult` / `MakeupTask` / `CourseOffering`）逐字段未被修改；
- 解释包**不导入** `app.planner` / `app.curriculum` / `app.course_data` / `app.services.mock_service` /
  `app.api.mock` / `app.integration` / 任何网络库（AST 测试锁定）。
- 用同一请求重复调用解释接口，响应**逐字节一致**（见 §5 证据脚本输出 `repeatable: True`）。

### 2.3 可选模型适配层（本轮**未接入真实模型**）

- 协议：`ExplanationModelAdapter.complete(*, question, facts_answer, fact_catalog) -> str`；
- **默认未配置**：`generation.model_configured = false`、`generator_kind = rule_based_template`；
- 即使配置：模型输出必须通过**事实绑定校验**才会被采用——
  1. 已核实的陈述必须原样出现（防改写事实）；
  2. 出现**数量型数字**必须能在事实目录中找到（防编造学分 / 周次 / 容量；来源 URI 与课程号中的数字不算数量）；
  3. 出现**课程号 / 教学班号**必须来自事实目录（防编造课程与等价关系）；
  4. 单个字符串且长度受限。
- 任一不通过 / 调用异常 ⇒ **该条降级为模板**，并写入 `fallback_reason`，
  整体 `generator_kind = model_unavailable_fell_back_to_template`。
- ⛔ 没有引入任何新的付费服务、密钥或大型依赖；⛔ 不读环境变量中的模型配置。

### 2.4 前端最小接入（只展示，不重算）

| 文件 | 变更 |
| --- | --- |
| `frontend/src/api/explanation.ts`（新增） | 解释接口客户端：失败如实报错，⛔ 不 fallback、⛔ 不补默认值 |
| `frontend/src/components/ExplanationPanel.vue`（新增） | 解释面板：条目 / 依据 / 前提 / 待确认 / 来源概况 / 警告 / 错误与空状态 |
| `frontend/src/utils/explanationLabels.ts`（新增） | 纯展示文案；`rule_based_template` 显示为「规则模板（非 AI）」 |
| `frontend/src/config.ts` | 新增 `EXPLANATION_ENDPOINT` 与 `EXPLANATION_API_ENABLED`（**默认关闭**） |
| `frontend/src/App.vue` | 新增第 5 区块「解释与依据」+ provenance（解释对象 / 通道状态） |
| `frontend/src/components/MakeupTaskList.vue` | 每行「🔍 查看依据」入口（仅可选 prop 开启时渲染） |
| `frontend/src/components/PlanResultPanel.vue` | 整体 / 选中教学班 / 调班三处入口 |
| `frontend/.env.example` | 文档化 `VITE_EXPLANATION_API_ENABLED` 与 `VITE_PLAN_API_ENABLED` |
| `frontend/README.md` | 新增第 9.5 节：如何开启、三条边界、手动验收步骤 |

前端边界：

- **只展示**：解释文本、来源、强度、待确认全部来自后端；前端不做截断、不重写、不推断；
- **未启用不发请求**：`VITE_EXPLANATION_API_ENABLED` 未开启时点击入口只显示"解释功能未启用"，
  一个解释请求都不会发出（App 级测试断言 fetch 调用数不变）；
- **请求失败安全**：显示失败类型与"不会用模板内容顶替、不显示任何未经后端返回的解释"；
- **不冒充**：只有后端返回 `model` 时才显示「AI 模型生成」；降级时显示降级原因；
- **provenance 精确**：区分「被解释的方案是 Mock 还是 Real」与「解释通道是否启用」，
  解释区与规划结果区互不改写。

---

## 3. 使用数据与来源字段

- 全部使用仓库内 `mock_data/` 的**演示数据**（`makeup_tasks.json` / `course_offerings.json` /
  `plan_result.json`），由既有 `mock_service` 读取并校验；解释**不新增任何数据源**；
- 解释引用的字段（全部来自公共契约，未新增字段）：
  `PlanResult.status` / `selected_classes[]` / `changes[].{course_id,from_class,to_class,reason}` /
  `risks[].{course_id,level,reason}` / `unresolved[].{type,message}` / `objective_summary`；
  `MakeupTask.{course_id,status,credit,reason,source_evidence,prerequisites,recommended_semester,deadline_semester}`；
  `CourseOffering.{course_id,class_name,class_id,semester,meetings[],remaining_capacity,data_source}`；
- ⛔ **不采集、不传输、不展示**成绩单 / 姓名 / 学号 / GPA：解释请求模型 `extra="forbid"`，
  接口结构上无法携带这些字段（有测试锁定请求键集合与禁用键名）。

---

## 4. 复现步骤（截图替代：命令行证据）

### 4.1 只看解释（后端，一条命令）

```powershell
cd backend
python ../tools/explanation_evidence.py
```

实际输出（节选，本机 2026-10-08，Python 3.14.7）：

```text
POST /api/v1/explanation/plan -> HTTP 200
contract_version      : explanation-v1
plan_result_digest    : 4f2b3a8760d3cfe731ef347d7e0ec2b390951a1acc89a6ba5f9d7f59c492cd85
generator_kind        : rule_based_template
model_configured      : False
makeup_task_count     : 5
course_offering_count : 9
contains_mock_marker  : True
warnings              : 0
items                 : 18
repeatable            : True
```

条目分布（18 条）：
`plan_status` × 1、`makeup_task` × 5（required ×2 / possibly_equivalent / manual_confirmation / satisfied）、
`selected_class` × 4、`change` × 2、`risk` × 3、`unresolved` × 3。

### 4.2 界面复现（前端）

```powershell
# 1) 后端
cd backend ; python -m uvicorn app.main:app --reload
# 2) 前端
cd frontend
"VITE_EXPLANATION_API_ENABLED=true" | Out-File -Encoding utf8 .env.local
npm run dev      # 打开 http://127.0.0.1:5173
```

界面操作路径（无截图环境，逐步可复现）：

1. 页面加载后，第 1 区块「历史培养要求评估」每行右侧出现「🔍 查看依据」；
2. 第 4 区块「规划结果与建议课表」出现「🔍 为什么这样安排（查看整体依据）」，
   每个建议教学班卡片与每条调班记录也各有入口；
3. 第 5 区块「解释与依据」显示「解释对象：Mock 演示结果 / 解释通道：已启用」；
4. 点击任一入口 → 出现解释面板：顶部是生成方式标签（此时为「规则模板（非 AI）」）、
   方案指纹前 12 位、条目数；下方每条解释含
   「直接依据（强证据）」「前提与上下文」「仍需人工确认」三栏；
5. 证据行显示 `对象.字段 = 原始取值`，`absent` 字段显示「（该字段在当前上下文中不存在）」；
6. 点补修任务某一行的入口 → 面板只显示该课程的条目，并提示"当前聚焦课程"；
7. **失败路径**：停掉后端再点入口 → 面板显示失败类型与"不会显示任何未经后端返回的解释"。

### 4.3 直接调用接口（可选）

```powershell
cd backend
python - <<'PY'
import json
from fastapi.testclient import TestClient
from app.main import app
from app.services import mock_service
payload = {
    "plan_result": mock_service.load_plan_result().model_dump(mode="json"),
    "makeup_tasks": [t.model_dump(mode="json") for t in mock_service.load_makeup_tasks()],
    "course_offerings": [o.model_dump(mode="json") for o in mock_service.load_course_offerings()],
}
with TestClient(app) as c:
    r = c.post("/api/v1/explanation/plan", json=payload)
print(r.status_code, r.json()["generation"]["generator_kind"], len(r.json()["items"]))
PY
```

---

## 5. 测试命令与结果（精确）

| 命令 | 结果 |
| --- | --- |
| `cd backend && python -m pytest -q tests/test_explanation_service.py` | **33 passed** |
| `cd backend && python -m pytest` | **2997 passed / 15 failed / 2 skipped**（约 92s） |
| `cd frontend && npx vitest run` | **154 passed / 154**（11 个测试文件，含本轮新增 20 用例） |
| `cd frontend && npx vue-tsc --noEmit` | **exit 0** |

### 5.1 关于后端那 15 个失败（**非本轮引入**）

15 个失败全部位于 `tests/test_curriculum_{case,cli,docx_reader,file_case,json_reader}.py`，
形态一致：`Failed: DID NOT RAISE CurriculumNormalizationError`。
原因：本机 **Python 3.14.7** 对含 NUL 字节（`\x00`）的路径不再抛 `OSError`，
于是这些**期望被规范化异常拦下**的用例拿不到异常。
本轮**没有**修改、没有跳过、没有放宽任何这类用例；本轮也未触碰 curriculum 包。

> 归因方法与结果见 §5.3（用未改动的 HEAD 建独立 worktree 重跑同一套测试）。

### 5.2 本轮新增测试覆盖

后端 `tests/test_explanation_service.py`（33 用例）覆盖：

- **正常**：完整上下文下每个 `PlanResult` 条目与每条 `MakeupTask` 都有解释；
  四种补修状态得到**不同且准确**的说明；
- **证据可核对**：`reason` / `source_evidence` 的 `raw_value` 与源字段**逐字相同**；
- **不重算**：调班解释复述 Planner 原文并声明"没有重新做冲突检测"；
- **缺证据**：没有 `MakeupTask` 上下文时不出现任何补修状态词；`absent` 与空值区分；
- **空输入 / 空列表**：整体状态解释仍然成立且不作可行结论；
- **边界**：超长文本被截断且带唯一标记、`meetings=[]` 不说成无冲突、方案引用上下文外课程时进 warnings、
  重复课程号只解释第一条并告警；
- **只读**：`deepcopy` 前后输入逐字段相同；`plan_result_digest` 与输入一致；重复调用结果一致；
- **架构边界**：解释包不导入 Planner / Curriculum / Course Data / Mock 通道 / 网络库，
  源码不含 `open(` / `os.environ` / `subprocess` / `socket`；
- **失败路径**：请求体非法（422）、额外字段（422，含 `student_id`）、上下文超 500 条（422）；
- **模型适配层**：合法适配器 → `model`；幻觉适配器与崩溃适配器 → 降级为模板且
  **幻觉内容没有进入任何解释**；**部分条目失败时整体也不宣称模型生成**；
  校验函数对数字 / 标识符 / 缺事实三种情况分别拒绝。

前端（20 用例）覆盖：

- 规则模板必须显示为「规则模板（非 AI）」，只有后端说 `model` 才显示「AI 模型生成」；
- 降级时显示降级原因；
- 证据显示 `对象.字段`、原始取值，并区分「上下文不存在」与空字符串；
- 请求体只有三个键、且不含个人身份字段；
- 未启用不发请求；500 / 网络失败 / 结构不符 / 空条目 / 聚焦无条目 / 长文本 → 均有明确反馈；
- App 级：入口存在性与 provenance；打开解释不改变规划结果与 Mock provenance；
  默认未启用时点击入口 fetch 调用数**不增加**。

### 5.3 基线归因（证明 15 个失败与本轮无关）

用**未改动的 HEAD**（`d387b9a`）建立独立 git worktree，重跑同一套后端测试：

```powershell
git worktree add --detach ../_baseline_wt HEAD
cd ../_baseline_wt/backend && python -m pytest -q
```

结果：

```text
BASELINE: 15 failed, 2964 passed, 2 skipped
AFTER   : 15 failed, 2997 passed, 2 skipped
```

**失败集合完全相同**（同样的 15 个用例），新增的 33 个用例**全部通过**。
因此这 15 个失败是**本机 Python 3.14 环境差异**导致的既有问题，
不是本轮引入，也没有被本轮掩盖。

---

## 6. 文件列表（本轮全部改动）

**新增**

```text
backend/app/explanation/__init__.py
backend/app/explanation/models.py
backend/app/explanation/templates.py
backend/app/explanation/adapter.py
backend/app/explanation/service.py
backend/app/api/explanation.py
backend/tests/test_explanation_service.py
frontend/src/api/explanation.ts
frontend/src/components/ExplanationPanel.vue
frontend/src/utils/explanationLabels.ts
frontend/tests/explanation-panel.spec.ts
frontend/tests/explanation-app-wiring.spec.ts
tools/explanation_evidence.py
AGENT_B_REPORT.md
```

**修改（最小改动，逐条说明理由）**

```text
backend/app/main.py                                  # +1 行 router 注册（新私有接口）
backend/tests/test_integration_orchestrator.py       # 路由白名单登记新入口（该文件要求逐条登记并说明理由）
frontend/src/config.ts                               # 新增解释 endpoint 与默认关闭的开关
frontend/src/App.vue                                 # 新增第 5 区块与入口接线（+provenance）
frontend/src/components/MakeupTaskList.vue           # 新增可选「查看依据」列（默认不渲染按钮）
frontend/src/components/PlanResultPanel.vue          # 新增三处只读解释入口
frontend/.env.example                                # 文档化解释开关
frontend/README.md                                   # 新增第 9.5 节：开启方式与验收步骤
docs/status/agent_frontend.md                        # 状态同步（本轮新增段落置顶）
docs/worklogs/agent_frontend.md                      # 追加本轮工作日志
```

**明确未改**：`/schemas/**`、`/docs/interfaces/**`、`backend/app/planner/**`、
`backend/app/curriculum/**`、`backend/app/course_data/**`、`backend/app/integration/**`、
`mock_data/**`、`backend/app/services/planning_runtime.py`、`backend/app/api/plan.py`、
Agent A 负责的个人输入 / 课程库 / 规划组合器相关文件。

---

## 7. 已知局限

1. **没有真实模型调用**：解释 100% 是规则模板。模型适配层只是接口预留，
   接入真实服务（选型 / 密钥 / 成本）属受控事项，本轮**未引入**。
2. **解释质量受上游字段质量限制**：若上游不提供 `reason` / `source_evidence`，
   解释只能如实说"无法追溯"，不会替上游补写理由。
3. **`PlanResult` 不携带 `MakeupTask`**：前端需要把上下文（`makeup_tasks` / `course_offerings`）
   一并 POST 给解释接口，存在**重复传输**；这是为了不改既有 `/api/v1/plan` 契约而做的取舍。
4. **解释不能证明学校规则**：所有"确证规则"只表示"该结论由哪个模块以哪个字段给出"，
   正式规则解释与人工审批仍是人的责任。
5. **未做**：课表图片 OCR、聊天框、自然语言调课（任务书明确的延后项），
   本轮**没有**用假 OCR 或假模型调用充数。
6. 仅在本机 **Python 3.14.7 / Windows / Node 24.9.0** 验证；未在 CI 运行。

---

## 8. 与 Agent A 的后续联调边界（只记录，不越界）

- **本轮不假设 A 的新 API 存在**：解释只消费当前已存在的 `PlanResult` / `MakeupTask` /
  `CourseOffering`，因此即使 A 的 `feature/personal-planning-pipeline` 未合并，本分支功能完整可用。
- **未来集成点（需要 A 或负责人确认后再做）**：
  1. 若 A 的新规划接口直接返回“结果 + 其上下文”（例如一次返回 `PlanResult` 与所用
     `MakeupTask[]`），解释客户端可以改为消费该返回值，**去掉当前的重复传输**；
  2. 若 A 的个人输入会产生新的状态语义（例如新的 `MakeupTask.status` 取值或新的
     `unresolved[].type`），解释侧需要新增对应模板分支——**这属于解释模块内部改动**，
     不修改 A 的代码，也不修改公共 Schema；
  3. 解释接口是**只读旁路**：A 的管线不需要等待解释成功，解释失败也不得影响规划结果。
- **共享文件冲突风险**：`frontend/src/App.vue` 与 `backend/app/main.py` 是两边都可能改的注册处。
  本轮改动都是**追加式最小改动**（main.py 一行注册；App.vue 新增一个区块 + 一个可选 prop）。
  若与 A 的分支冲突，**只报告、不擅自跨分支解决**。
- **⛔ 未做**：没有修改 A 的文件、没有修复 Planner、没有改任何既有规划 API。

---

## 9. 需要人工确认

1. 解释文案是否允许比当前更贴近"学校规则"的措辞
   （本轮严格沿用源字段原义，未新增任何学校规则解释）；
2. 未来是否接入真实 LLM 服务（选型 / 密钥 / 成本），以及允许向其发送哪些字段；
3. 是否需要把 `satisfied` 的"已满足"进一步区分为"系统判定"与"教务正式认定"
   （当前解释已提示两者不同，但公共契约里没有"正式认定"字段）。

---

## 10. 给非专业读者的六句话（通俗说明）

1. **现在能做什么**：学生在页面上点一下某条补修判定、某个排课班级或某条调班记录，
   就能看到"为什么是这样"，以及这句话是从哪个字段、哪份材料来的。
2. **用户会看到什么**：一个解释面板，里面有解释正文、来源字段与原始取值、
   以及"这件事还需要人工确认"的提醒；未配置模型时明确写着"规则模板（非 AI）"。
3. **主要代码在哪**：后端 `backend/app/explanation/`（解释逻辑）与
   `backend/app/api/explanation.py`（接口）；前端
   `frontend/src/components/ExplanationPanel.vue`（面板）。
4. **怎么运行**：先 `cd backend && python -m uvicorn app.main:app --reload`，
   再在 `frontend/.env.local` 写 `VITE_EXPLANATION_API_ENABLED=true`，然后 `npm run dev`。
5. **怎么测试**：`cd backend && python -m pytest -q tests/test_explanation_service.py`；
   `cd frontend && npx vitest run tests/explanation-panel.spec.ts`。
6. **出问题先检查什么**：先看页面第 5 区块的「解释通道」是不是"已启用"；
   再看面板里显示的失败类型（未启用 / 输入校验 / 服务端 / 网络）；
   然后确认后端 8000 端口是否在跑、以及解释请求是否真的发出（浏览器 Network 里看
   `/api/v1/explanation/plan`）。
