# Planner 当前状态

更新日期：2026-10-05。阶段：阶段3受限 Provider / PlanResult / DG-07C 安全处理及四项验收修复已 commit / push；阶段4成员4既有 Mock 回归已通过。成员4内部独立技术复核结论为 **PASS WITH NOTES**，该结果仅作为 Builder 自检证据，不等同于项目 Architecture Review。项目 Architecture Reviewer 已完成 DG-07C 代码正式审查：代码主体通过，当前仅剩文档 / governance 一致性修复待复验。

- 当前分支：`feature/planner-dg07c-unknown-schedule`；阶段3代码 checkpoint：`2fe77bdf912c2ef51f4ca832a2bbd279ed34d36a`；本次文档修复前远端 HEAD：`2478dd15e567e00e2d90af4cc782431a197a9fc2`。
- 阶段3代码与阶段4成员4内部技术复核已 push；项目 Architecture Review 以远端分支实际 HEAD 与 diff 为准。

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
- 阶段4在上述 HEAD 实际运行既有测试，Python 3.12.14，沿用 backend/.venv，未修改依赖或测试口径；命令与运行历史见WORKLOG“阶段4成员4独立回归与文档收尾”记录。
- Provider共210项正式Mock测试；Planner合计 **342 passed / 0 skipped / 1 warning**，默认沙箱通过，退出码0。
- 相关契约/Mock Schema/Integration：**127 passed / 2 skipped / 1 warning**，同一命令经授权在沙箱外通过，退出码0。
- 后端全量：**938 passed / 2 skipped / 1 warning**，同一命令经授权仅在沙箱外运行一次并通过，退出码0；git diff --check通过。
- 契约组及全量的先前沙箱运行出现ERROR后中止，无最终汇总或完整traceback；同命令沙箱外通过支持环境差异判断，具体临时目录权限原因未确认。未修改源码、测试、fixture、配置或环境文件来绕过错误。
- 1 warning为既有Starlette/httpx弃用提示，无新增skip。
- 当前功能仅使用Mock数据验证，尚未完成真实数据验证。测试为合成对象，现有mock_data未修改。

## 成员4内部独立技术复核（≠ 项目 Architecture Review）
- 成员4内部独立技术复核已完成，结论为 **PASS WITH NOTES**；该结果只能作为 Builder 自检证据，不得称为项目级 Architecture Review，也不构成项目级批准。
- 内部复核记录：Planner **342 passed / 0 skipped / 1 warning**；独立穷举校验 **3,645组通过**。Contracts **127 passed / 2 skipped / 1 warning**与全量 **938 passed / 2 skipped / 1 warning**沿用阶段4成员4本地重新验证记录。
- NOTES：真实数据验证仍未完成；Data Gate / rollout仍未解除；DG-07整体未关闭；完整 Planner MVP 未最终验收；API 接线、人工选择产品闭环、Frontend DG-07D 和非时间规则仍属于外部依赖。

## 项目 Architecture Reviewer（正式审查）
- 项目 Architecture Reviewer 已对 DG-07C 分支做正式代码审查；三态冲突、empty-meeting safety、current_schedule unknown safety、多 Meeting 检测、受限 Provider、PlanResult 安全状态与跨模块边界未发现代码 blocker。
- 正式审查当前结论：**代码主体通过；文档 / governance 修复后复验**。本结论不等于 DG-07 整体完成，不解除 Data Gate / rollout gate。

## 未完成与边界
- 受限Provider不是完整Planner MVP；候选展示→人工选择→回传→正式repair产品链本阶段不实现。
- 非时间正式执行规则（容量、学分统计口径、通勤、先修证据、学期映射、硬/软分类）仍需人工确认。
- 无连锁换班、全局目标优化、OR-Tools、自动优先级或跨学期规划。
- 搜索已缓存并剪枝，不构造完整笛卡尔积；一般约束组合的最坏复杂度仍为指数级，不能承诺任意规模实时完成。未加入超时/节点限制，搜索未完成绝不生成infeasible。
- 真实联调BLOCKED：成员4当前未持有完整批准联调包，仓库内也未发现满足当前联调条件的完整输入交接；成员4当前可用的完整学期CourseOffering快照、稳定真实MakeupTask、学生当前课表与Preference未齐备，真实证据汇总不等于可联调逐行数据。
- 产品API接线、人工选择调用闭环、Frontend DG-07D与非时间未定义规则保持BLOCKED，不由成员4补造或跨模块实现；partial snapshot不得进入产品链路。
- 成员4内部独立技术复核已完成并给出 PASS WITH NOTES；项目 Architecture Reviewer 已完成正式代码审查，代码主体通过，当前等待本次 docs/governance 修复复验。DG-07 / 完整 Planner MVP 仍未通过最终整体验收。
- Schema/Interface/公共模型/Integration/其他成员模块/依赖未修改。
- **DG-07整体未完成，Data Gate保持Reopened**，DG-07D 与 DG-07 整体验收 gate 未解除，真实端到端 rollout 不开放；成员4内部技术复核的 PASS WITH NOTES 不等于项目 Architecture Review，也不等于 DG-07 关闭。

## 运行与排查
- Python导入 `from app.planner import RestrictedPlannerProvider` 并用冻结四参数调用plan；网页仍是Mock回放，无新增API。
- 从backend运行 `.venv/Scripts/python.exe -B -m pytest tests/test_planner_provider.py tests/test_planner_conflicts.py tests/test_planner_section_repair.py -o addopts= -q -p no:cacheprovider`。
- 先查输入学期、重复身份、空meetings、unresolved和明确选择证据；partial中保留的课表不是已认证课表。
