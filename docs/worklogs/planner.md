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

### 2026-10-05 - 阶段3：受限 Provider、PlanResult 与 DG-07C 状态处理
- 本节为初稿实现历史，后续只读验收发现四项缺陷；最终证明范围、学期判断、搜索及回归结果以末尾“四项验收修复”记录为准，初稿测试通过不代表验收通过。
- 目标：按负责人批准计划实现代码、测试、文档；本轮不commit/push/merge。
- 分支：feature/planner-dg07c-unknown-schedule；Base/HEAD checkpoint：10cfe219de5ff1195cdeec3fb9f3379885b73249。开工工作区干净，本地upstream一致，未访问远端。
- 本次负责人裁决（来自本轮授权，不声称此前仓库已定义）：
  - selected_classes为完整本学期建议课表，保留当前班；唯一CLEAR新增required允许建议加入，多个CLEAR不选，UNKNOWN不新增。
  - 已有班替换须显式指定；selection_required为新确认开放字符串约定；UNKNOWN与无解证据按证明范围聚合status。
  - 多任务联合判断：确定目标全部允许组合已被已知约束排除才可判无解，不按任务顺序牺牲required。
  - changes相对本次current_schedule：实际新增记录，保留/未执行替换不记录。
- 实现文件：
  - backend/app/planner/provider.py：RestrictedPlannerProvider，冻结四参数，深拷贝与重校验，正式PlanResult。
  - backend/app/planner/feasibility.py：课表三态认证、组合存在性枚举；无选班、无评分。
  - backend/app/planner/__init__.py：导出Provider，阶段1/2实现不变。
  - backend/tests/test_planner_provider.py：102项合成Mock正式测试。
  - docs/status/planner.md更新当前状态，本WORKLOG追加历史。
- 算法边界：
  - 当前班事实优先于供给同身份快照；非法类型、重复、混合学期、倒置节次明确报错。
  - 唯一CLEAR新增先收集再联合检查，冲突组全暂不加入，独立新增可形成部分建议。
  - 无解证明与实际选班分离：required原班/供给候选构成可能域，其余当前班固定；存在性见证不授权自动选择/替换。
  - UNKNOWN组合是可能解，空供给不是无解证据；相对学期映射未知的目标不参与新增任务无解证明。确定子目标无解可阻塞完整目标，但局部候选失败不可冒充整体无解。
  - 只消费先修边，不推断通过/并修；激活Preference、方案容量、多校区通勤、学期映射显式manual_confirmation。不新增硬软分类、阈值、评分、权重或风险等级。
- 测试环境：Python3.12.14，沿用backend/.venv，未修改依赖。
  - Planner：.venv/Scripts/python.exe -B -m pytest tests/test_planner_provider.py tests/test_planner_conflicts.py tests/test_planner_section_repair.py -o addopts= -q -p no:cacheprovider：**234 passed / 1 warning**（新增102+原132）。
  - 同命令指定tests/test_contracts.py tests/test_mock_data_schema.py tests/test_integration_orchestrator.py：**127 passed / 2 skipped / 1 warning**。
  - 全量：.venv/Scripts/python.exe -B -m pytest -o addopts= -q -p no:cacheprovider：**830 passed / 2 skipped / 1 warning**。
  - git diff --check通过；没有修改公共契约和其他成员模块。
  - 沙箱内相关/全量回归在tmp_path setup出现临时目录创建OSError并停滞，已停止；按工具审批在沙箱外重跑同套检查。未改其他模块来绕过失败。
  - 仅既有Starlette/httpx弃用提示，无新增skip。
- 覆盖：任务书A–L、当前UNKNOWN保留、未用UNKNOWN不降级、多个CLEAR待选、已有班不自动替换；三任务两两可行但联合无解、UNKNOWN逃逸组合、16个独立时段oracle案例及顺序不影响结果；新增changes/部分建议/外部repair历史不伪造；非时间待确认；空/错误/重复/混合学期/篡改对象、多Meeting、输入隔离、JSON Schema和实际Provider注入test-only上游Orchestrator。
- 使用数据：Mock合成对象，未处理真实学校材料，现有mock_data未修改。
  **当前功能仅使用Mock数据验证，尚未完成真实数据验证。**
- 未完成/待确认：人工选择产品调用链、非时间正式执行语义、真实联调、Architecture Reviewer；本阶段不是完整Planner MVP。
- 对其他模块影响：Schema/Interface/公共模型/Integration/Curriculum/Course Data/Frontend/依赖/Mock文件均0修改。
- 风险：候选枚举无截断，最坏运行时间随组合数增长；当前适用于MVP小规模输入。
- **DG-07整体未完成，Data Gate保持Reopened，DG-07D及Review未完成，真实rollout gate不解除。**
- 下一步：停在未提交可验收状态，负责人验收后再决定commit/push，后续进入Architecture Reviewer。

### 2026-10-05 - 阶段3四项验收修复
- 授权：负责人接受NEEDS_FIX并将四项全部纳入阶段3；不暂存、不commit、不push、不merge，冻结四参数及Schema不变。
- 修复1，显式修复证明范围：所有当前课程均纳入原班及同课同学期输入候选，不按required身份限制；原班时间以current_schedule为准。证明用保守放宽域覆盖显式repair尚未排除的可能，连尚未满足本次repair条件的候选也不提前排除；放宽域无解才足以证明实际允许域无解。见证不作为执行方案、不授权连锁换班。stage2仅明确选择CLEAR后单目标替换的行为不变，Provider只报告实际CLEAR待选择、保留当前班，changes不造替换。
- 修复2，学期证据：None不再视为本学期必达；新增required缺失学期字段显式manual_confirmation。有相对编号也缺少与本次学校学期的映射，冻结输入目前不能确认新增任务本学期必达。因此新增任务安排失败不产生整体无解证据，唯一CLEAR仍可形成带待确认项的新增建议。本次可靠无解证明仅消费当前课程的保留目标，不能将建议反向当作必达目标。
- 修复3，UNKNOWN关联：删除全局uncertain_current否决，相关UNKNOWN若仍允许可能组合则partial；无关UNKNOWN不能抹除独立证明。已知冲突与UNKNOWN同时出现时按证明范围处理，不能按三态优先级机械映射PlanResult。
- 修复4，搜索：固定课表预检查；同次调用按对象身份缓存Section两两检测；显式栈增量构造前缀、已知CONFLICT立即剪枝；先搜索认证组合，再搜索含UNKNOWN可能组合。没有笛卡尔积生成、没有递归深度依赖、没有人工截止；异常/中断不转换为无解。最坏仍为指数级，未承诺大规模实时求解。
- 文件范围：修复provider.py、feasibility.py、test_planner_provider.py及STATUS/WORKLOG；__init__.py保留初稿导出，本次未改变。阶段1/2实现、公共契约、Integration及其他成员模块0修改。
- 本次增加108个测试实例：12个当前课程不同身份/学期字段的实际显式repair对照；4个缺失学期边界；4个相关/无关UNKNOWN成对回归；81个独立已知/未知时段穷尽oracle；7个固定预检查、缓存、2**36冲突后缀剪枝、全UNKNOWN可能组合和搜索失败回归。修正原有错误的缺省学期必达夹具，无解用已选保留目标验证；Schema测试增加状态取值断言。
- 首轮新测试夹具中A与保留C同一天，导致修复后新增断言失败；改为独立时段后仍保留实际stage2修复及Provider不自动替换断言，未放宽规则。
- 最终测试（Python3.12.14，backend/.venv，无依赖变更）：
  - `.venv/Scripts/python.exe -B -m pytest tests/test_planner_provider.py tests/test_planner_conflicts.py tests/test_planner_section_repair.py -o addopts= -q -p no:cacheprovider`：**342 passed / 1 warning**（Provider210 + 阶段1/2原132）。
  - 同命令指定tests/test_contracts.py tests/test_mock_data_schema.py tests/test_integration_orchestrator.py：**127 passed / 2 skipped / 1 warning**。
  - `.venv/Scripts/python.exe -B -m pytest -o addopts= -q -p no:cacheprovider`：**938 passed / 2 skipped / 1 warning**。
  - 契约/Integration沙箱内tmp_path setup报错并停止；按工具审批在沙箱外重跑相关及全量，无修改测试环境/其他模块来绕过错误。warning为既有Starlette/httpx弃用提示，skip未增加。
- 仅合成Mock验证；**当前功能仅使用Mock数据验证，尚未完成真实数据验证。**
- 保留未完成：本学期必达证据/学期映射、非时间规则和证据、人工选择产品调用链、真实联调、API接线、Architecture Reviewer。本阶段仍是受限Provider，非完整Planner MVP；DG-07整体未完成，Data Gate保持Reopened，真实rollout gate不解除。
