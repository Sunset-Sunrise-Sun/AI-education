# Planner 工作日志

> 仅追加历史记录。新的 Agent 优先阅读 docs/status/planner.md。

## 模板
### YYYY-MM-DD - 功能
- 本次目标：
- 已完成：
- 修改文件：
- 测试：
- 使用数据：Mock / Real
- 已知问题：
- 需要人工确认：
- 对其他模块影响：
- 下一步：

### 2026-10-01 - DG-07A 契约变更的 Planner 侧同步（**仅文档，未实现**）
- 本次目标：同步 DG-07A 已生效的**公共契约语义**，**不实现任何 Planner 行为**。
- 已完成（**仅 status 文档**）：
  - `docs/status/planner.md` 记录：`CourseOffering.meetings` 允许 **0..N**
    （`minItems: 0`，`required` 不变）；
    `meetings = []` = **schedule unknown**，⛔ **≠ conflict-free**；
    **同一条规则覆盖 `offerings` 与 `current_schedule`**；
    ⛔ `current_schedule` 含 `meetings = []` 时**不得**声明
    "已验证与当前课表无时间冲突"（最多只能判断"与**已知**时间段未发现冲突"）。
- 修改文件：`docs/status/planner.md`、本文件（**仅追加**）。
- 测试：**未修改任何 Planner 代码 / 测试**；后端全量 `pytest` **550 passed / 2 skipped**。
- 使用数据：Mock（未变）。
- 已知问题：**Planner safety implementation 尚未开始**（属 **DG-07C**）；
  当前代码没有任何 unknown-schedule 处理，因此**不得**把 `meetings = []`
  当成可安全选入的候选。
- 需要人工确认：`PlanResult.status` 如何取值、`unresolved[].type` 最终命名、
  `missing_schedule` 是否正式采用 —— **仍留待 Planner Implementation Review**；
  当前 **`missing_schedule` = `candidate convention only`**（⛔ 非正式公共约定）。
- 对其他模块影响：契约语义已变（消费方假设"`meetings[0]` 必然存在"**不再成立**）；
  ⚠️ **rollout gate**：DG-07B/C/D 完成前，生产链路不得产生或接入
  empty-meeting `CourseOffering`。
- 下一步：等待 **DG-07C** 任务书。⛔ **本轮不开始实现**。

### 2026-09-xx - 计划中的下一步（未开始）
- 建立统一 Mock 案例；实现时间 / 周次冲突检测（**契约要求逐段遍历**）；
  实现 NetworkX 依赖图；再接 OR-Tools。

### 2026-10-04 - Planner 第一阶段：三态时间冲突检测
- 本次目标：仅实现内部时间冲突检测及测试，不实现候选选择或方案求解。
- 分支：`feature/planner-dg07c-unknown-schedule`。
  Base SHA：`f807d89cb9af1821a0c7d5854563041b6271e628`。
  按用户要求未 commit / push / merge。
- 已完成：
  - `ConflictState` 为内部枚举 CONFLICT / CLEAR / UNKNOWN。
  - `check_conflict()` 比较两教学班全部 Meeting 两两组合；同星期、实际周次
    有交集、闭区间节次重叠时返回 CONFLICT。
  - `check_schedule_conflict()` 比较候选与当前课表，聚合
    CONFLICT > UNKNOWN > CLEAR；遇到未知仍继续检查后续已知冲突。
  - 双方/单方 `meetings=[]` 均为 UNKNOWN；空课表与已知候选为 CLEAR，
    与未知候选为 UNKNOWN。输入由调用方按同学期提供；不按 ID 排除教学班。
  - 使用现有 CourseOffering / Meeting 模型，无新字段或依赖；函数不修改输入。
    公共模型未约束 start/end 的相对大小，内部沿用现有 Course Data 规则拒绝
    倒置节次；错误对象明确报错，不伪装成 CLEAR / UNKNOWN。
- 修改文件：`backend/app/planner/__init__.py`、
  `backend/app/planner/conflicts.py`、`backend/tests/test_planner_conflicts.py`、
  `docs/status/planner.md`、本文件。
- 测试：
  - 环境：Python 3.12.14；仓库内 `backend/.venv/` 隔离环境（Git 已忽略），
    安装的只是原 `backend/requirements.txt` 依赖，无修改依赖声明。
  - 从 backend 运行 `.venv/Scripts/python.exe -m pytest tests/test_planner_conflicts.py -q -p no:cacheprovider`：
    **48 passed**。
  - `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`：
    经授权在沙箱外完成，**644 passed / 2 skipped / 1 warning**，无新增 skip。
  - 覆盖十类要求，以及共享节次端点、包含区间、单节课、周次顺序与部分交集、
    单双周不交叠、周日、Schema 未设上限的节次与周次、空课表、输入不变、
    非法对象/区间和模型非法字段。
  - `git diff --check` 通过；禁止修改的目录/文件没有 diff。
- 使用数据：Mock（测试内人工合成对象），未修改现有 `mock_data/`。
  **当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**
- 已知问题：沙箱内全量回归出现文件夹具错误并停滞，已停止该进程；
  同套测试在沙箱外通过。1 warning 是 Starlette 对现有 httpx TestClient 用法的
  弃用提示，本轮不更换依赖或修改其他模块。
- 需要人工确认：本轮无新增业务规则确认项；后续硬/软约束及跨校区通勤规则
  仍需按公共流程确认。
- 对其他模块影响：公共 Schema / Interface、Integration、Course Data、
  Curriculum、前端、Mock 文件均未修改。Provider 尚未实现、未接入真实 API。
- 尚未完成：替代教学班、Path Repair、OR-Tools、PlanResult status /
  `schedule_unknown` 生成和候选选入控制。**DG-07C 仅完成基础部分**，
  **DG-07 整体未完成，Data Gate 保持 Reopened**，不解除真实链路 gate。
- 下一步：Review 本阶段代码与测试，再按负责人确认的任务进入后续阶段。

### 2026-10-04 - Planner 第二阶段：替代教学班搜索与单目标课程 Path Repair
- 本次目标：复用三态检测，返回同课程同学期的替代班；调用方明确指定 CLEAR
  候选后只替换目标课程，不实现完整规划或连锁换班。
- 分支：`feature/planner-dg07c-unknown-schedule`。
  Base / checkpoint SHA：`b7b0ced23addf6d6a02e3feb81b2d668713864b8`。
  开工时工作区干净；本轮按用户要求不 commit / push / merge。
- 已完成：
  - `find_alternative_sections()` 以 `(semester, course_id, class_id)` 定位原班，
    排除原班、其他课程和其他学期；移除原班后复用 `check_schedule_conflict()`。
  - 返回原班三态和全部候选的三态、原因；CLEAR 全部返回并保留来源顺序，
    不按教师、容量或学业优先级排名。UNKNOWN 不冒充 CLEAR，也不猜测学校排课状态。
  - `repair_target_section()` 每次重新评估当前输入，指定 CLEAR 才替换目标位置，
    复用公共 Change 模型记录原班、新班和理由，其他课程内容及顺序不变。
  - 原班 CLEAR 不替换；即使只有一个 CLEAR 也不自动选择。
    按已确认行为，原班 UNKNOWN 可以明确指定 CLEAR 替换，原因不声称已确认冲突。
  - 指定 UNKNOWN / CONFLICT 时拒绝替换，不偷偷选择其他 CLEAR；指定不存在或
    不属于同课程同学期的替代班时明确报错。原班 CLEAR 时不使用换班选择。
  - 无候选、无 CLEAR 但有 UNKNOWN、全部 CONFLICT 使用不同内部原因；
    未使用的 UNKNOWN 不否定指定 CLEAR 的换班。不使用 PlanResult.status。
  - 重复身份、原班缺失、混入其他学期的当前课表、非法模型和倒置节次明确报错；
    数据通过既有 CourseOffering 模型重新校验并深拷贝，所有返回数据与输入隔离。
  - SearchOutcome / RepairOutcome 及结果 dataclass 均为 Planner 内部类型，
    从 Planner 包入口导出供后续复用，无新增第三方依赖。
- 修改文件：
  - 新增 `backend/app/planner/section_repair.py`：搜索和单目标修复纯函数及内部结果。
  - 修改 `backend/app/planner/__init__.py`：导出上述函数和内部类型。
  - 新增 `backend/tests/test_planner_section_repair.py`：正式 Mock 单元测试。
  - 更新 `docs/status/planner.md`，本 WORKLOG 仅追加本阶段记录。
- 测试：
  - 环境：沿用仓库 `backend/.venv/`，Python 3.12.14，无修改依赖声明。
  - 从 backend 运行 `.venv/Scripts/python.exe -m pytest tests/test_planner_section_repair.py tests/test_planner_conflicts.py -p no:cacheprovider`：
    **132 passed / 1 warning**（本阶段 84 项 + 第一阶段 48 项）。
  - `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`：
    经授权在沙箱外运行，**728 passed / 2 skipped / 1 warning**，无新增 skip。
  - 覆盖原班 CLEAR / CONFLICT / UNKNOWN、多个 CLEAR、不自动选择、未知和冲突
    混合、空输入、错误身份/学期/模型、移除原班后比较、多 Meeting 后续冲突、
    原班数据以当前课表为准、只替换目标位置、深拷贝及旧搜索结果不被直接信任。
  - `git diff --check` 通过；实际修改仅为上述五个文件，第一阶段检测实现与测试未修改。
- 使用数据：Mock（测试内人工合成对象）；未修改现有 `mock_data/`。
  **当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。**
- 已知问题：1 warning 为既有 Starlette/httpx TestClient 弃用提示；
  本轮不更换依赖或修改其他模块。
- 需要人工确认：本阶段无新增待确认项；后续硬/软约束、通勤等仍按公共流程确认。
- 对其他模块影响：公共 Schema / Interface、模型、Integration、Course Data、
  Curriculum、frontend 和 Mock 文件未修改；未接入 Provider 或真实 API。
- 能力限制：本阶段仅完成单目标课程换班；成功只确认替代班与其余输入课表
  无时间冲突，不确认其他课程彼此无冲突，也不保证整体方案或学校选课可行。
  不判断容量、教师偏好、学分、先修等其他约束。
- 尚未完成：完整 PlannerProvider.plan()、PlanResult / 最终状态判定、
  `unresolved[].type=schedule_unknown`、连锁 Path Repair、全局优化与 OR-Tools。
  **DG-07C 尚未整体完成；DG-07 整体未完成，Data Gate 保持 Reopened**，
  不解除真实端到端 rollout gate。
- 下一步：验收本阶段实现与测试，由负责人确认后再推进后续完整规划阶段。
