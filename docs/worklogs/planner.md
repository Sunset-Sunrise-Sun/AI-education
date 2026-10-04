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
