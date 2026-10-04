# Planner 当前状态

更新日期：2026-10-04。阶段：三态时间冲突检测已实现，待 Review。

## 已完成
- 公共输入输出 Schema、Provider 签名已经定义，本轮未修改。
- `backend/app/planner/conflicts.py`：内部 `ConflictState`，以及纯函数
  `check_conflict()` / `check_schedule_conflict()`。
- 比较全部 Meeting 两两组合：同星期、实际周次有交集、闭区间节次重叠才冲突。
- `meetings=[]` 为 UNKNOWN，适用于候选与当前课表；聚合优先级
  `CONFLICT > UNKNOWN > CLEAR`，未知不能掩盖后续明确冲突。
- 接受已校验的同学期 CourseOffering；不筛选班级、不修改输入。
  倒置节次沿用 Course Data 的拒绝规则，明确报错。
- 48 项 Planner 测试通过；后端全量回归 644 passed / 2 skipped，
  1 条测试依赖弃用提示（Python 3.12.14）；详见本轮 WORKLOG。

## 尚未实现
- 替代教学班搜索、Path Repair、约束优化、OR-Tools。
- `PlannerProvider.plan()` 真正实现、PlanResult 生成与状态判定。
- `schedule_unknown` 未解决事项生成和候选选入控制。
- 因此 **DG-07C 仅完成冲突检测基础，未整体完成**；DG-07 整体未完成，
  **Data Gate 仍保持 Reopened**，不得解除真实端到端 rollout gate。

## 本轮边界与数据
- 不涉及跨校区通勤、学分上限、Preference 权重或学业优先级。
- 当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。
  测试内使用合成对象；现有 `mock_data/` 未修改。
- 空课表：已知教学班返回 CLEAR；未知教学班仍为 UNKNOWN。
  CLEAR 只表示本轮输入范围内的时间判断，不表示整体方案可行。

## 下一步
- Review 本阶段实现和测试。
- 后续按确认任务实现候选搜索及方案安全处理；通勤与硬/软约束仍需人工确认。
- 只消费 Curriculum 提供的先修边，不生成学业优先级。
