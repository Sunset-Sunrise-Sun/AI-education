# Planner 当前状态

更新日期：2026-10-05。阶段：受限 Provider / PlanResult / DG-07C 安全处理及四项验收修复已实现，待负责人验收及 Architecture Reviewer；未 commit / push / merge。

## 已实现
- 阶段1/2三态时间检测、全部Meeting比较、同课同学期替代搜索及显式单目标repair保持不变。
- `provider.py` 的 `RestrictedPlannerProvider.plan()` 兼容冻结四参数 Protocol；重校验、深拷贝、无网络、无排名或自动替换。
- selected_classes 按本次负责人裁决为完整本学期建议课表：保留当前班。保留UNKNOWN/冲突班是当前选择事实，不代表已认证，unresolved/status明确反映限制。
- 当前未选required仅唯一CLEAR可建议新增，且联合检查其他新增班；多个CLEAR待选择，UNKNOWN不新增。冲突组全部暂不加入，不按任务顺序牺牲任何任务，独立班可以形成部分建议。
- changes相对本次current_schedule：新增记录from_class=null/to_class=新班；保留不记录；未执行替换不记录。外部repair历史不在下一次Provider调用中伪造。
- `feasibility.py` 固定课表预检查、Section成对缓存、显式栈前缀搜索，已知冲突立即剪枝；先找CLEAR完整组合，再找UNKNOWN可能组合，不返回选班。没有搜索截断；异常/中断不能返回无解证明。
- 证明范围：所有当前课程均保留原班和同课同学期输入候选，不区分required身份。无替代班的课程才固定；证明用保守放宽域覆盖仍可能的显式repair，放宽域也无解才认证实际目标无解。找到放宽域组合不代表允许执行，plan不替换、不授权连锁换班。
- UNKNOWN按证明关联范围保留：能留下可能解的相关UNKNOWN阻止无解认证；不能解开独立已知冲突的无关UNKNOWN不抹除证明，无全局uncertain_current否决。
- 缺失推荐/截止学期明确表示学期要求未知；有相对学期编号时也缺少映射。本接口目前没有新增任务本学期必达证据，新增建议及其联合冲突均不能据此证明整体无解。唯一CLEAR仍可建议加入，但学期要求待确认使结果为partial。
- 空候选进入missing_data，不假定学校未开课或供给完整；无解证明仅针对本次输入和保留当前课程目标，不宣称学校全部供给无解。

## 本次批准输出规则
- feasible：完整建议形成，阶段要求认证且语义明确的硬条件通过，无影响可执行性的unresolved。
- partially_feasible：未知/必要决策未完成，尚未证明完整目标无解。
- infeasible：本次目标和允许操作范围内有完整无解证据，不按内部三态优先级映射。
- selection_required 是2026-10-05负责人新确认的约定，不是此前公共枚举；有CLEAR但未选择时使用。
- schedule_unknown仅描述来源快照缺排课；未用UNKNOWN不自动降级，已知完整无解证据不被无关UNKNOWN抹除。
- 未定非时间语义使用已有manual_confirmation：先修通过/并修证据、相对学期、激活的Preference、方案容量信息、多校区通勤。未定规则不筛班、不评分、不证明无解，也不认证feasible。
- 不生成未批准风险等级，risks=[]；摘要说明受限认证范围和输入数据标签，不保证学校选课成功。

## 验证
- 本阶段共210项正式Mock测试（初稿102项，本次增加108项并修正旧夹具）；Planner合计 **342 passed / 1 warning**。
- 相关契约/Mock Schema/Integration：**127 passed / 2 skipped / 1 warning**。
- 后端全量：**938 passed / 2 skipped / 1 warning**，最终运行记录见WORKLOG；git diff --check通过。
- 1 warning为既有Starlette/httpx弃用提示，无新增skip。
- 当前功能仅使用Mock数据验证，尚未完成真实数据验证。测试为合成对象，现有mock_data未修改。

## 未完成与边界
- 受限Provider不是完整Planner MVP；候选展示→人工选择→回传→正式repair产品链本阶段不实现。
- 非时间正式执行规则（容量、学分统计口径、通勤、先修证据、学期映射、硬/软分类）仍需人工确认。
- 无连锁换班、全局目标优化、OR-Tools、自动优先级或跨学期规划。
- 搜索已缓存并剪枝，不构造完整笛卡尔积；一般约束组合的最坏复杂度仍为指数级，不能承诺任意规模实时完成。未加入超时/节点限制，搜索未完成绝不生成infeasible。
- 真实联调、产品API接线和Architecture Reviewer未完成。
- Schema/Interface/公共模型/Integration/其他成员模块/依赖未修改。
- **DG-07整体未完成，Data Gate保持Reopened**，DG-07D与评审gate未解除，真实端到端rollout不开放。

## 运行与排查
- Python导入 `from app.planner import RestrictedPlannerProvider` 并用冻结四参数调用plan；网页仍是Mock回放，无新增API。
- 从backend运行 `.venv/Scripts/python.exe -B -m pytest tests/test_planner_provider.py tests/test_planner_conflicts.py tests/test_planner_section_repair.py -o addopts= -q -p no:cacheprovider`。
- 先查输入学期、重复身份、空meetings、unresolved和明确选择证据；partial中保留的课表不是已认证课表。
