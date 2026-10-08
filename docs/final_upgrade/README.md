# Final Upgrade · 双 Agent 无人值守协作说明（2026-10-08）

## 本轮目标与版本保护
本轮将固定 Case A 演示逐步提升为**受支持培养方案范围内、由个人输入驱动的规划原型**，并增加有来源的规则解释。当前 main 是冻结基线，禁止写入 main；Case A 必须继续运行。

分支拓扑：
- `main`（只读基线）
- `feature/final-upgrade`（集成目标；本轮由负责人验收前不合并）
- `feature/personal-planning-pipeline`（Agent A；基于 final-upgrade）
- `feature/explanation-agent`（Agent B；基于 final-upgrade）

两个 Agent **只能提交到自己的分支**；允许推送自己的提交、创建 draft PR（base=`feature/final-upgrade`），**严禁自动合并任何 PR、移动集成分支、推送 main、强推或删除分支**。不要求夜间人工回复。

## 必读优先级
1. `AGENTS.md`（最高）
2. `docs/ARCHITECTURE.md`、`docs/GIT_WORKFLOW.md`
3. `docs/interfaces/integration.md`、当前模块状态文档及相关现有接口/测试
4. 本轮任务书 `docs/final_upgrade/AGENT_A.md` 或 `AGENT_B.md`

公共 Schema、接口路径、正式学校规则、第三方模型服务选型属于受控事项；**本轮没有预授权修改**。任务和公共协议冲突时，以公共协议为准：继续做不冲突工作，冲突项写 BLOCKED，不猜测、不绕过。阶段结束后统一交接，不能因为无人值守而放宽要求。

## 交叉依赖协议
- A 独占个人输入/课程库/当前规划组合器/选修接纳验证相关生产代码。
- B 独占解释服务及解释 UI；不得编辑 A 的文件、不得修复 Planner，也不得修改当前个人规划 API。解释服务优先消费**已经存在的已证实 plan/result 与来源字段**，未来 A 的新输入接口只是后续集成点。
- 共享 `frontend` 根入口、`backend` app/router 注册等文件可能冲突：尽量用独立模块与最小注册改动；不得为集成跨分支修改他人代码。发现冲突只报告。
- 各自独立写 `docs/final_upgrade/reports/AGENT_A_REPORT.md` / `AGENT_B_REPORT.md`；相关 STATUS/WORKLOG 更新在自己分支。
- 仅在自己分支做测试；不得伪造通过记录、不得以 Mock 冒充 Real、不得把模型模板输出称为实际 LLM 调用。

## 优先级与无人值守结束条件
P0: 基线测试/合同不破坏；真正正确的个人输入与结果差异（A）；有证据的解释输出（B）。
P1: 前端最小接入、回归、明确来源标签。
P2: 课表图片 OCR 为**延后任务**，本轮不要抢占 P0/P1，也不以假 OCR 冒充 AI。

若遇到必须人工决策、数据真实性不足、无可用模型配置或共享协议冲突，选择安全降级（明确“不可用/待确认”）并记录；不要停掉独立可完成部分。任务结束必须 commit、push 自己的分支并提交报告；如可行创建 draft PR，不 merge。

## 用户可提供的数据（本轮不等待）
- 有正式来源且可核验的培养方案版本、学分/课程组要求
- 第二名学生经授权且脱敏的成绩记录
- 本人课表截图及其周次/节次的人工核验
没有这些材料就只对现有已核验数据/显式 Mock 测试数据做开发；不得编造中山大学真实条款或用第一位学生结论填充第二人。
