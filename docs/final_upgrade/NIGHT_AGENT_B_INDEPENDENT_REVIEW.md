# Night QA — Agent B：独立 Architecture Reviewer（无人值守）

**审核对象：** PR #64 https://github.com/Sunset-Sunrise-Sun/AI-education/pull/64 （`feature/final-upgrade-integration-qa`）
**角色：** Reviewer，默认只读。**不要在任何分支提交或改写代码，不合并，不批准未验证的 PR**。
**注意：** Builder A 夜间会在 **`fix/final-upgrade-integration-qa`** 独立开发。你只审 PR #64 的固定提交，不要在同一个工作目录并行修改；如果能捕获 HEAD SHA，在报告注明。

## 启动
先读 AGENTS.md、docs/ARCHITECTURE.md、docs/GIT_WORKFLOW.md、docs/interfaces/integration.md、docs/final_upgrade/INTEGRATION_QA_STATUS.md 和两个 Builder 的完成报告，按公共协议输出任务理解，随后无人值守地完成审查。

## 审核清单
1. 模块/接口：`Curriculum → MakeupTask[] → Planner → PlanResult` 是否只做允许的编排，是否改动冻结四参数签名或公共 Schema；新私有接口的输入校验、异常分型、默认 503 行为。
2. 学生独立性：是否用本学生已修事实与版本，其他人的认定/假设/缓存是否会穿透；缺失成绩不必然意味着已确证缺口；`satisfied` 不冒充学校正式认定。
3. Planner：累计新增、时段+周次冲突、重复班级、无声明学分、原课表已超限及 `max_credit` 的保守安全行为；指出它和“找最佳可行子集”之间的功能差距，不自行变更优化目标。
4. 解释服务：只读、来源原始字段、无 context 不杜撰、来源/Mock/Real 标记、规则模板非 LLM、前端不重新计算、缺失/失败态不显示假结果。
5. 集成：`main.py` 同时注册三条新路由；路由白名单与实际 app 同步；Frontend App.vue 解释入口是否带正确当前方案/任务/offerings，是否在个人规划 `planning=null` 时出现误导。
6. 安全：前端不出现密钥、用户身份数据不能被不必要地发往解释 API；不触碰真实教务授权边界。
7. 运行：可独立执行测试则运行和记录命令；做不到则如实说明，不要推测“CI 全绿”。

## 严重性
- BLOCKER：学生串数据、修改官方认定或 Schema、编造真实数据/LLM、错误展示已执行方案、核心硬约束破坏、合并导致 API 运行失败。
- MAJOR：关键异常路径缺测试、错误态误导、不能正确还原解释上下文、用户输入不明确但被确定执行。
- MINOR：非核心文案与样式问题；不要要求重构以追求美观。

## 交付
- 在本轮会话直接提交详细审查报告（**不要求 Git 提交**），建议按 BLOCKER/MAJOR/MINOR 分级，并逐条写文件路径、复现条件、影响、建议最小修复、能否独立复现。
- 可向 PR #64 留 **COMMENT** 类型评审，勿提交 APPROVE 或 REQUEST_CHANGES 以外的无授权动作；如果证据未充分，不要发正式结论。
- 结论只能为 `PASS / PASS WITH CONDITIONS / BLOCKED` 之一，明确这只是静态或独立测试视角，不替代 Builder 修复后的复验。
- 不要合并 PR #62/#63/#64 或任何分支，不要编辑 main。
