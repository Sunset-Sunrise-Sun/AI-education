# Night QA — Agent A：集成 Builder（无人值守）

**目标 PR：** https://github.com/Sunset-Sunrise-Sun/AI-education/pull/64
**唯一允许写入分支：** `fix/final-upgrade-integration-qa`（已从 `feature/final-upgrade-integration-qa` 派生）
**禁止修改：** `main`、`feature/final-upgrade`、`feature/final-upgrade-integration-qa`、两条原始 Agent 分支。

## 启动
1. 用独立 clone/worktree。先读 AGENTS.md、docs/GIT_WORKFLOW.md、docs/ARCHITECTURE.md、docs/final_upgrade/INTEGRATION_QA_STATUS.md 与相关模块状态、接口说明。
2. 检查 git status/branch/log；基于 `fix/final-upgrade-integration-qa` 独立完成测试修复。按 AGENTS.md 输出任务理解后自行继续，不等用户回复。
3. 完成后 push 本分支，建立 **Draft PR：base = feature/final-upgrade-integration-qa, head = fix/final-upgrade-integration-qa**；不 merge；原 PR #64 不 merge。

## 任务（按顺序）
- 先运行基线：后端相关测试+全量 pytest；前端 `npm ci`（环境许可时）、`npx vitest run`、`npx vue-tsc --noEmit`、`npm run build`。记录 Python/Node/系统和全部原始失败。
- 核对 combined FastAPI 路由、OpenAPI 白名单、个人规划接口、解释 API、旧 Case A 规划路径。
- 使用已有 Mock 和单元测试验证两个独立学生、未核验版本 fail-closed、学分上限、选修冲突、解释只读及 Mock/Real、非 AI 模板标识。
- 发现**由两个分支合并造成的回归**，仅做最小修复并增加测试；发现原分支逻辑缺陷可定位和报告，但不得私自修改学分/课程认定/硬软约束/公共契约。
- `max_credit` 当前“超限拒绝整组新增”保留作为安全行为，不允许自行改成自动舍弃某些课程；这属于下一阶段 Planner 优化。
- 无真实目录/教务教学班时绝不编造或宣称真实 E2E；未配置 DeepSeek 不准假装调用成功。
- 对 Python 3.14 Windows NUL 路径类已知失败，重复运行与同环境基线对比；不能跳过、删除或放宽断言来让测试变绿。
- 如遇无法解决的公共 API 冲突或正式学校业务规则，标为 BLOCKED，但继续其余独立验证。

## 交付
- 在自己的分支新建 `docs/final_upgrade/reports/INTEGRATION_BUILDER_REPORT.md`；记录：环境、commit SHA、复现命令、通过/失败数字、失败分类（基线/新增/无法确认）、各修复文件、仍待人工决定事项、Mock/Real 状态、没有真实 DeepSeek 调用的说明。
- 运行测试后 push，创建 Draft PR 到 **feature/final-upgrade-integration-qa**；不改原 PR #64，不合并任何 PR。
- 最后输出给非开发者的“现在能做什么/尚不能做什么/如何启动演示”。
