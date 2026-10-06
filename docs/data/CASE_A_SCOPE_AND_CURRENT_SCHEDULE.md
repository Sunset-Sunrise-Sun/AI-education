# Case A 课程数据 + 当前课表操作手册（今晚闭环）

> 适用：**Case A scoped South + Shenzhen 教学班数据 + 学生当前课表 → RestrictedPlanner**。
> 边界（⛔ 不得改写）：本手册描述的是 **Case A scoped（南校园 + 深圳校区）demo 数据集**，
> **不是** `full_semester`、**不是**全校 / 五校区完整供给、**不是** LEVEL2 real dataset。
> 现有五校区 `full_semester` acceptance 语义**未被改动**。

相关代码：

| 位置 | 作用 |
| --- | --- |
| `backend/app/course_data/case_a_scope.py` | Case A scoped 数据集（派生、只读、demo scope） |
| `tools/case_a_course_data.py` | `verify` / `export` / `smoke` 三个子命令 |
| `frontend/src/state/manualSchedule.ts` | 手工录入 → 公共 `CourseOffering` 的纯逻辑 |
| `frontend/src/components/ManualScheduleForm.vue` | 手工录入界面（⛔ 不需要写 JSON） |

---

## 0. 一句话说明

```text
本地库里**已经正式验收**的两个 campus acceptance
  （南校园 5062201 / 深圳校区 333291143）
        ↓  build_case_a_dataset()   ← 复用既有 campus acceptance 信任链
Case A scoped 教学班数据集（demo scope，⛔ 不是 full_semester）
        ↓  CaseAScopedCourseDataProvider
CourseOffering[]
        ↓  + 手工录入的 current_schedule + Preference
RestrictedPlanner → PlanResult
```

⛔ 这条路径**不写库**：Case A 数据集不落进 production trust store，
因此不可能被 `StoreBackedCourseDataProvider`（只认 `full_semester` acceptance）误读。
⛔ 也**不提供**任何 `--allow-case-scope`/`--skip-north` 之类的降级逃生参数。

---

## 1. 前提：两个校区必须先有**已验收的 campus acceptance**

Case A 数据集**只从**本地库里既有的 campus acceptance 派生。因此先决条件是：

```text
本地 Course Data SQLite 中存在
  scope_kind = campus 且 scope_id = 5062201     的 acceptance 记录（south-campus）
  scope_kind = campus 且 scope_id = 333291143   的 acceptance 记录（shenzhen-campus）
```

缺任一条、出现多条、或内容绑定校验不通过 ⇒ 工具**直接失败**，
并且**不会**退化成"只用一个校区"或"本学期任意行"。
失败类别是机器可读的：`campus_acceptance_missing` / `campus_acceptance_ambiguous` /
`campus_acceptance_mismatch` / `store_error` / `semester_mismatch`。

自检（只打印统计，不含任何教学班取值）：

```bash
cd backend
python - <<'PY'
import sys; sys.path.insert(0, ".")
from app.course_data import SCOPE_KIND_CAMPUS, load_course_data_acceptances
for record in load_course_data_acceptances("<你的SQLITE路径>", semester="2026-1"):
    if record.scope_kind == SCOPE_KIND_CAMPUS:
        print(record.scope_kind, record.scope_id, record.artifact_sha256[:12], record.offering_count)
PY
```

---

## 2. 负责人采集：南校园 + 深圳校区（⛔ Builder 不访问学校）

**只允许**在本人已登录、已有权限的「全校开设课程」页面内，用**既有已批准采集器**手工触发。
⛔ 不需要 Cookie / Token / 密码，⛔ 不绕过登录，⛔ 不高频请求。

打开 SYSU 教务「全校开设课程」页面 → DevTools Console 载入
`tools/sysu_course_offering_collector.js` 的内容（与既有做法一致），然后：

### 2.1 南校园（shard `south-campus`，`openingSchoolNumber = 5062201`）

```js
const south = await window.XuehangSysuCollector.collectApprovedShard({
  semester: "2026-1",
  shardId: "south-campus",
  maxPages: 50
});
copy(window.XuehangSysuCollector.toJson(south));
```

### 2.2 深圳校区（shard `shenzhen-campus`，`openingSchoolNumber = 333291143`）

```js
const shenzhen = await window.XuehangSysuCollector.collectApprovedShard({
  semester: "2026-1",
  shardId: "shenzhen-campus",
  maxPages: 50
});
copy(window.XuehangSysuCollector.toJson(shenzhen));
```

### 2.3 期望产物与**安全元数据**（由采集器如实给出，⛔ 不要手工编造）

把 `copy(...)` 的结果**分别**贴进两个本地文件（⛔ 不要放进仓库）：

```text
/path/outside/repo/south-campus-2026-1.json      ← 裸 Capture Bundle
/path/outside/repo/shenzhen-campus-2026-1.json   ← 裸 Capture Bundle
```

每个 bundle 的**顶层**应当是：

```text
format / semester / first_page_no / page_size / pages
```

返回值里可以照抄进交接记录的**安全元数据**（⛔ 不含任何 row 取值）：

| 字段 | 含义 |
| --- | --- |
| `shard.capture_shard_id` | `south-campus` / `shenzhen-campus` |
| `shard.shard_id` | `南校园` / `深圳校区` |
| `shard.openingSchoolNumber` | `5062201` / `333291143` |
| `requests` | 本次实际请求数 |
| `expectedTotal` | 接口报告的总量 |
| `accumulatedRows` | 实际累计行数 |
| `stoppedReason` | 必须是 `reached_total` |

### 2.4 停止条件（遇到任一，**停止并报告**，⛔ 不要重试刷页）

- `stoppedReason !== "reached_total"` ⇒ 该校区**未取满**，采集器**不会**产出 bundle；
- HTTP 401 / 403 / 疑似登录页 ⇒ 认证失效，**重新人工登录后再说**；
- HTTP 600 / 其它服务端错误 ⇒ 如实记录，⛔ 不重试、⛔ 不跳页、⛔ 不换参数继续刷；
- `total` 在两页之间漂移 ⇒ 采集窗口不稳定，如实记录；
- 出现空页但未取满 ⇒ 分页提前停滞，如实记录；
- 触发 `window.confirm()` 的批次上限提示时，若不确定就**取消**（取消 = 0 个请求）。

---

## 3. 校验 + 落库（每个校区各一次）

```bash
cd backend

# 南校园
python ../tools/validate_course_data_artifact.py \
  --bundle /path/outside/repo/south-campus-2026-1.json \
  --expected-semester 2026-1 \
  --scope-id 5062201 \
  --source "capture://sysu/2026-1/campus/5062201" \
  --sqlite /path/outside/repo/case_a_campus.sqlite3

# 深圳校区
python ../tools/validate_course_data_artifact.py \
  --bundle /path/outside/repo/shenzhen-campus-2026-1.json \
  --expected-semester 2026-1 \
  --scope-id 333291143 \
  --source "capture://sysu/2026-1/campus/333291143" \
  --sqlite /path/outside/repo/case_a_campus.sqlite3
```

说明：

- `scope_kind` 固定是 `campus`，`scope_id` 就是该校区 `openingSchoolNumber`；
- 只有在**完整校验通过**（`complete` + 计数自洽 + 内容 digest）之后才会写库；
- `--expected-sha256` 可选：给了就必须与 artifact 字节摘要**完全一致**（人工对账门）；
- `--source` 是**审计标签**，⛔ **不是** acquisition provenance proof。

⛔ **不要**用 `tools/accept_full_semester_course_data.py` 来接受这两个校区：
那个入口代表**五校区 full_semester acceptance**，Case A 今晚**不需要**、也**不得**声称它。

---

## 4. 构造 / 验证 Case A scoped 数据集

```bash
cd backend

# 只验证：打印 scope 标签 + 计数 + digest（⛔ 不含任何教学班取值，可以贴进交接记录）
python ../tools/case_a_course_data.py verify \
  --store /path/outside/repo/case_a_campus.sqlite3 --semester 2026-1
```

期望输出里**必须**出现：

```text
"scope_kind": "case_scoped"
"scope_label": "case-a-scoped:south+shenzhen"
"is_full_semester": false
"is_whole_school": false
"openingSchoolNumbers": ["5062201", "333291143"]
"duplicate_identity_deduped": <两校区同 identity 且内容相同的去重条数>
```

可选：把两个校区的 acceptance digest 写成人工门（防止"换了一份 artifact 却没说"）：

```bash
python ../tools/case_a_course_data.py verify \
  --store /path/outside/repo/case_a_campus.sqlite3 --semester 2026-1 \
  --expected-campus-sha256 '{"south-campus":"<64hex>","shenzhen-campus":"<64hex>"}'
```

导出（可选，**含真实取值 ⇒ ⛔ 不得提交 Git / 不得放进 `mock_data/`**）：

```bash
python ../tools/case_a_course_data.py export \
  --store /path/outside/repo/case_a_campus.sqlite3 --semester 2026-1 \
  --out /path/outside/repo/case_a_course_data.json
```

导出的 JSON **同时**带正向标签与反向断言（`is_full_semester: false` 等），
因此下游无法只截取一半就把它当成 `full_semester`。

---

## 5. 学生当前课表（`current_schedule`）

### 5.1 官方路径：前端**手工结构化录入**（⛔ 不需要写 JSON）

在页面「③ 当前课表」区块：

1. 列表里能找到你要选的班 → 直接勾选（原有路径）；
2. 找不到（例如该教学班不在当前加载的范围内）→「**+ 新增一行手工录入**」，填：
   课程号 / 课程名称 / 教学班号 / 学期 / 星期 / 开始节次 / 结束节次 / 周次（校区、教室可留空）
   → 点「**加入当前课表**」；
3. 页面上方会显示「已加入：…」，已选列表可逐个「移除」；
4. 若要用它做**实际规划**（`POST /api/v1/plan`），必须再勾选
   「**我确认以上当前课表由本人根据本学期已经选好的课程填写**」——
   ⛔ 未勾选时手工课表**不会**被提交（fail closed）。

校验规则（⛔ 全有或全无，失败**不会**修改已有课表）：

- 任一必填字段缺失 / 非法 ⇒ 明确报错（例如"结束节次不能小于开始节次"）；
- 周次写法：`1-16`、`1-16,18`、`1,3,5-7`（也接受"周"字与中文标点）；
  ⛔ 不解释单双周等未确认写法；
- 同一 `(学期, 课程号, 教学班号)` 重复 ⇒ 明确拒绝，**不静默去重**；
- 同一课程再加一个不同教学班 ⇒ 明确拒绝（Planner 要求同一课程只有一个已选班）。

### 5.2 `data_source` 与**用户级确认**（attestation，很重要）

⛔ 手工录入**不是**学校系统的授权查询结果，因此它**不能**天然具有 `data_source = "real"`。
规则是**纯用户级**的（⛔ 没有任何构建期环境变量旁路）：

```text
录入 / 加入课表          → data_source = "mock"（⛔ 不声称学校来源）
用户在界面勾选确认        → 手工条目切到 "real"（= 学生自述），允许进入 plan 请求
用户取消勾选             → 立即切回 "mock"，门禁重新阻断
课表在上次确认后被改动    → 确认自动作废，必须重新勾选确认
```

界面上的确认控件（默认**未勾选**）：

```text
[ ] 我确认以上当前课表由本人根据本学期已经选好的课程填写，系统将基于此进行规划。
    该课表由本人提供，未经学校系统核验；它不是 Course Data 来源证明，
    也不代表学校已完成选课或审批。未勾选时，手工录入的课表不会提交到 Real Planning。
```

⚠️ 口径边界（⛔ 不得简化）：

- 确认 = **学生自述**，⛔ **不是**"学校已核验 / 教务系统已确认"；
- 确认后 Planner 的执行仍然是**真实代码执行**（不是 Mock 回放），
  但⛔ **不**代表输入数据已获得真实学校来源认证；
- 确认状态**不进入**请求体：`POST /api/v1/plan` 的 body 仍然**只有**
  `semester` / `current_schedule` / `preference` 三个公共字段；
- 手工录入**不会**进入 Course Data 的 acceptance / store（前端没有这条通路）。

> ⚠️ **架构决定（已冻结）**：手工 `current_schedule` 默认 fail-closed，
> 只有**用户显式确认**后才可作为学生自述输入进入实际规划。
> 本分支即按此实现；⛔ 不得改回"默认放行"或"负责人环境变量放行"。

### 5.3 把课表交给 Planner（离线 smoke，不走 HTTP）

把当前课表写成一个 `CourseOffering[]` JSON（字段与公共 Schema 一致；
页面手工录入产出的条目就是同一形状）：

```json
[
  {
    "course_id": "SEC1001",
    "course_name": "信息安全导论",
    "class_id": "01",
    "semester": "2026-1",
    "meetings": [
      {"weekday": 2, "start_section": 3, "end_section": 4, "weeks": [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16], "campus": "深圳校区", "classroom": "教学楼A305"}
    ],
    "source": "manual-entry://current-schedule",
    "data_source": "mock"
  }
]
```

```bash
cd backend

python ../tools/case_a_course_data.py smoke \
  --store /path/outside/repo/case_a_campus.sqlite3 --semester 2026-1 \
  --current-schedule /path/outside/repo/current_schedule.json \
  --preference /path/outside/repo/preference.json \
  --makeup-tasks /path/outside/repo/makeup_tasks.json
```

- `--makeup-tasks` 由 **Curriculum** 侧交接（public `MakeupTask[]`）；
  ⛔ 本工具**不生成**、**不推断**补修任务；
- 缺 `--makeup-tasks` 时，会改用 `APP_CASE_A_CURRICULUM_CASE_PATH` 指向的
  runtime Curriculum 装配；两条路都不通 ⇒ **直接失败**（⛔ 没有 Mock fallback）；
- 输出只含结构性信息：scope 标签、计数、`plan_status`、`changes`、`unresolved[]`。

### 5.4 已实测的真实 CLI 输出（synthetic 数据集，仅供参考形状）

Builder 用**纯 synthetic** 的两校区库实跑过 `verify` / `smoke` / `export`，
确认三个子命令均可端到端执行（exit 0）。关键形状：

```text
verify
  "scope_kind": "case_scoped"
  "scope_label": "case-a-scoped:south+shenzhen"
  "is_full_semester": false
  "openingSchoolNumbers": ["5062201", "333291143"]
  "duplicate_identity_deduped": 0
  "provider_is_full_semester": false

smoke
  "current_schedule_count": 1
  "plan_status": "partially_feasible"
  "selected_classes": [ {当前已选班}, {本次可加入的 CLEAR 班} ]
  "changes": [ {新增 required 任务：唯一 CLEAR 班} ]
  "unresolved": [ {manual_confirmation: 该任务缺推荐/截止学期},
                 {manual_confirmation: Preference 字段 max_credit / avoid_cross_campus
                  的硬软分类或执行口径尚未完整确认} ]
```

⚠️ 读 `smoke` 输出时必须守住既有口径（⛔ 不得简化）：

- `selected_classes` 是 **建议**课表（含学生当前已选班与本次可加入的 CLEAR 班），
  ⛔ **不是**已完成选课 / 已注册；
- Planner 是**受限确定性规划**，⛔ 不是全局最优、⛔ 不是 CP-SAT/ILP、⛔ 不自动注册；
- **Preference 未被完全执行时会如实出现在 `unresolved`**（上例中的 `max_credit` /
  `avoid_cross_campus`），⛔ 不得声称每一项偏好都已被执行。

---

## 6. 可选：授权页面的「已选课程 / 我的课表」侦察清单（负责人本人执行）

⛔ 目标只有一个：判断**是否存在**可用的 same-origin JSON 接口。
⛔ 找不到就**直接用手工录入**，不要为自动化花时间。

在本人已登录的「已选课程 / 我的课表 / 选课结果」页面：

1. 打开 DevTools → Network → 勾选 `Fetch/XHR`；
2. 刷新页面（或触发一次查询）；
3. 找**同源**请求（host 仍为 `jwxt.sysu.edu.cn`），且响应是 JSON；
4. **只记录以下四项**：

   ```text
   method                （GET / POST）
   path                  （例如 /jwxt/xxx/yyy）
   请求 payload 的**键名**（⛔ 不要值）
   响应 JSON 的**字段名**（⛔ 不要值）
   ```

5. ⛔ **绝对不要**复制或导出：Cookie、`Authorization`、token、`Set-Cookie`、
   完整响应体、学号 / 姓名 / 任何个人标识。

把上面四项交给 Builder 即可；Builder 会在**零网络**前提下评估是否可以安全支持。
⚠️ 若 5 分钟内没有明确结论 ⇒ **手工录入就是官方兜底方案**，Case A 不因自动化受阻。

---

## 7. 出问题先检查什么

| 现象 | 先检查 |
| --- | --- |
| `campus_acceptance_missing` | 该校区是否真的做过 `validate_course_data_artifact.py --sqlite`；`--scope-id` 是否用了正确的 `openingSchoolNumber` |
| `campus_acceptance_ambiguous` | 同一校区是否被接受过**多次**（不同 artifact）⇒ 需要人工决定哪一批算数 |
| `campus_acceptance_mismatch` | 库里那批行是否被改写 / 是否传了错的 `--expected-campus-sha256` |
| `store_error` | SQLite 路径是否指向**Course Data 本地库**（不是任意 sqlite 文件） |
| `semester_mismatch` | `--semester` 与 acceptance 记录里的学期是否一致 |
| 手工录入"加入"没反应 | 看该行下方的红色错误提示（字段级），课表**不会**被部分修改 |
| Real Planning 按钮禁用并提示"未确认" | **预期**行为：请勾选确认控件；见 §5.2 |
| 勾选确认后又点了一下课表 | 确认会**自动作废**并提示"需要重新确认"（⛔ 旧确认不覆盖被改动过的数据） |
