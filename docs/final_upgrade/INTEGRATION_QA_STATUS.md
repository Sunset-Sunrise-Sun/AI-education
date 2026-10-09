# Final Upgrade 联合集成候选｜待验收

**状态：仅为 QA 候选，不代表通过回归或同意合并。** 
候选分支：`feature/final-upgrade-integration-qa`，从 Agent A 分支 `feature/personal-planning-pipeline` 派生，叠加 Agent B 分支 `feature/explanation-agent` 的 25 项变更（含两个共同修改文件的手工合成）。

## 合并处理
- Agent A 个人规划、学分安全检查与全部相应测试保留；
- Agent B 的解释服务、解释面板和相关测试全部保留；
- `backend/app/main.py` 同时导入并注册 `personal_plan`、`explanation`；
- `backend/tests/test_integration_orchestrator.py` 的显式路由白名单同时包含：
  - `GET /api/v1/personal-planning/curriculum-versions`
  - `POST /api/v1/personal-planning/plan`
  - `POST /api/v1/explanation/plan`
- 以路径对比核对，Agent B 原分支 25 个变更文件全部出现在候选与 A 的差异中。**未执行合并后的 Python/Vitest 回归**，该覆盖检查不能替代内容或运行测试。

## Reviewer 必查
1. Backend 全量 `python -m pytest -q`，并与相同 Python/OS 下未改基线比较既有失败集合；
2. Frontend `npm ci && npm run build && npx vitest run && npx vue-tsc --noEmit`；
3. 共同路由测试：两个个人规划入口与解释入口在 OpenAPI 中同时出现，原 `/api/v1/plan` 与 Mock 路径不变；
4. 个人两学生独立输入、未核验培养版本的 fail-closed、课表冲突与 `max_credit` 行为；
5. 解释服务不改变 PlanResult、缺证据不编造规则、Mock/Real 与“规则模板非 AI”标识正确；
6. 个人规划 `planning = null` 时解释 UI 禁止伪造“已完成排课”；
7. 未有真实目录/教学班快照、真实第二位同学数据、DeepSeek 在线调用，必须保持 BLOCKED，不得将 Mock 说成真实上线。

## 业务裁决
本轮保留 A 的 **`max_credit` 硬上限不得违反** 作为安全约束，但“累计新增超限时拒绝全部新增”的结果只允许按“保守拒绝”解释，**不是满意的最优补修路径**；下一轮由受控 Planner 搜索可行子集并按已确认目标排序，不允许模型绕过学分校验。

## 门槛
- 不自动合并 `feature/final-upgrade` 或 `main`；
- 未独立确认测试结果前，PR 保持 Draft；
- 本候选不代表 Agent B 的 LLM 已接入，实际解释仍为模板；
- 下一轮 AI Planning Controller 开发必须等候选联调验收通过。
