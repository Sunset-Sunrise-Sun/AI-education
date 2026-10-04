# Planner 当前状态

更新日期：2026-10-04。阶段：三态检测、替代教学班搜索与单目标课程换班已实现，待验收。

## 已完成
- 公共输入输出 Schema、Provider 签名已经定义，本轮未修改。
- `backend/app/planner/conflicts.py`：内部 `ConflictState`，以及纯函数
  `check_conflict()` / `check_schedule_conflict()`。
- 比较全部 Meeting 两两组合：同星期、实际周次有交集、闭区间节次重叠才冲突。
- `meetings=[]` 为 UNKNOWN，适用于候选与当前课表；聚合优先级
  `CONFLICT > UNKNOWN > CLEAR`，未知不能掩盖后续明确冲突。
- 三态检测接受已校验的同学期 CourseOffering；不筛选班级、不修改输入。
  倒置节次沿用 Course Data 的拒绝规则，明确报错。
- `section_repair.py`：`find_alternative_sections()` 搜索同课程、同学期的其他
  class_id；先移除原班，再判断候选与剩余课表的关系。全部 CLEAR 候选按输入
  顺序返回，UNKNOWN 保留核验原因，CONFLICT 保留淘汰原因，不排名、不自动选班。
- `repair_target_section()` 只接受调用方明确指定的 CLEAR 候选，只替换目标位置，
  复用 Change 记录原班、新班和原因。原班 CLEAR 不替换；原班 UNKNOWN 时允许
  指定 CLEAR，但不声称原班存在已确认冲突。未使用的 UNKNOWN 不否定这次时间修复。
- 输入以 `(semester, course_id, class_id)` 识别；原班必须在当前课表恰好出现一次，
  当前课表必须属于指定学期。重复身份、非法输入明确报错；返回数据与输入深拷贝隔离。
- 无候选、存在 UNKNOWN 但无 CLEAR、全部 CONFLICT 分别给出内部原因；不生成
  PlanResult 或完整规划可行性状态，不把 UNKNOWN 当成无解。
- 第一阶段 48 项、本阶段新增 84 项，合计 132 项 Planner 测试通过；
  后端全量回归 728 passed / 2 skipped / 1 warning（既有依赖弃用提示）；详见 WORKLOG。

## 尚未实现
- 连锁换班、完整 Path Repair、硬/软约束优化、OR-Tools。
- `PlannerProvider.plan()` 真正实现、PlanResult 生成与状态判定。
- PlanResult 中 `unresolved[].type=schedule_unknown` 生成及完整方案选班安全处理。
- 因此 **DG-07C 仅完成三态检测与单目标换班，未整体完成**；DG-07 整体未完成，
  **Data Gate 仍保持 Reopened**，不得解除真实端到端 rollout gate。

## 本轮边界与数据
- 不涉及跨校区通勤、学分上限、Preference 权重或学业优先级。
- 当前功能仅使用 Mock 数据验证，尚未完成真实数据验证。
  测试内使用合成对象；现有 `mock_data/` 未修改。
- 空课表：已知教学班返回 CLEAR；未知教学班仍为 UNKNOWN。
  CLEAR 只表示本轮输入范围内的时间判断，不表示整体方案可行。
- 换班函数要求原班存在；空当前课表报错。成功仅确认替代班与剩余课表无时间冲突，
  不确认其他课程彼此无冲突，也不判断容量、教师偏好、学分或先修可行性。

## 下一步
- Review 本阶段实现和测试。
- 后续按确认任务实现完整 Provider、PlanResult 与方案安全处理；
  通勤与硬/软约束仍需人工确认。
- 只消费 Curriculum 提供的先修边，不生成学业优先级。
