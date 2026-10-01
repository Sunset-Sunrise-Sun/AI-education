# Planner 当前状态

## 已完成
- 公共输入输出 Schema 已定义

## 当前接口
- 输入：MakeupTask[]、CourseOffering[]、Preference
- 输出：PlanResult
- ⚠️ **`CourseOffering.meetings = []` 的语义（DG-07A 契约已生效，Planner 尚未实现）**：
  - `meetings` **非空** → 冲突检测必须**遍历全部 `Meeting`**；
  - `meetings = []` → **schedule unknown**；
    ⛔ **绝不能**解释为"没有时间占用"；⛔ **绝不能**解释为 **conflict-free**；
  - **同一条规则同时适用于 `offerings` 与 `current_schedule`**（两者都是 `CourseOffering[]`）：
    任意 `meetings = []` → 该教学班 schedule 视为 unknown；
  - ⛔ **若 `current_schedule` 中存在 `meetings = []`**：**不得**输出
    "已验证与当前课表无时间冲突"，最多只能判断"**与当前课表中已知时间段未发现冲突**"，
    且**整体时间冲突状态仍含未知部分**。
- ⚠️ **以上只是公共契约语义**（见 `docs/interfaces/planner.md`）：
  **Planner safety implementation 尚未开始**（属 **DG-07C**，待任务书）。
  当前代码**没有任何** unknown-schedule 处理，因此**不得**把 `meetings = []`
  当成可安全选入的候选。
- ⏳ **仍未决定（留待 Planner Implementation Review）**：`PlanResult.status` 如何取值、
  `unresolved[].type` 的最终命名、`missing_schedule` 是否正式采用 ——
  当前 **`missing_schedule` 只是 `candidate convention only`**，
  ⛔ 不是已定的公共约定。

## 当前阻塞
- 优先级权重尚未人工确认
- 跨校区通勤规则尚未确认
- **DG-07C（unknown-schedule safety）尚未开始**：
  在实现完成前，任何含 `meetings = []` 的教学班都不能被声明为"已验证无冲突"

## 当前使用数据
- 建议先使用 Mock
- ⚠️ **rollout gate**：`meetings = []` 虽已在契约层合法，但在
  **DG-07B / DG-07C / DG-07D 完成前**，生产真实数据链路**不得**产生或接入
  empty-meeting `CourseOffering`；`mock_data/` 保持全部教学班 ≥1 段

## 下一步
- 建立统一 Mock 案例
- 实现时间/周次冲突检测（**契约要求：逐段遍历**）
- **DG-07C — Planner unknown-schedule safety**（**待任务书**）：
  `meetings = []` ≠ conflict-free，含 `current_schedule` 一侧
- 实现 NetworkX 依赖图
- 再接 OR-Tools
