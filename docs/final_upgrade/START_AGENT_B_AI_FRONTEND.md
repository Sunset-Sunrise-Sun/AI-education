# Agent B｜转专业 AI 补修协作网页（无人值守开发）

## 立即任务
你是 Builder B，负责新网页的**AI 补修规划交互**，不再只做原 NIGHT_AGENT_B_INDEPENDENT_REVIEW.md 的审查工作。唯一写入分支：`feature/ai-planning-frontend`（已创建），起点为 `feature/final-upgrade-integration-qa`。这是尚未全量回归的候选基线，开发必须独立测试。**不修改** main、feature/final-upgrade、集成候选、旧 PR #62/#63/#64 或 A 分支，不自动合并。务必使用自己的 worktree/clone，不与 A 共用工作目录。

先读 AGENTS.md、docs/ARCHITECTURE.md、docs/GIT_WORKFLOW.md、docs/final_upgrade/AI_PLANNING_NEXT_PHASE.md、docs/final_upgrade/DEEPSEEK_PLANNING_AGENT_V1.md、现有前端 Vue 组件、后端现存个人规划与解释 API，按公共协议先输出任务理解然后直接执行。

## 产品信息架构
产品是**转专业后的学业衔接和补修路径规划**，不是通用选课推荐、也不是独立聊天机器人。复用旧 Vue3+TS+Vite，不改技术栈，不引入大型 UI 依赖。整理为三个导航入口：
1. `转专业分析`：原/目标培养版本、当前成绩及认定状态、required/satisfied/manual_confirmation/possibly_equivalent 缺口；无真实核验时显式“待配置/Mock”；
2. `补修路径`：当前学期精确课表 + 后续学期课程级条件路径，补修优先级说明、风险、人工确认；
3. `AI 调整`：围绕**当前选中的补修方案**的对话式面板，不独立于计划泛聊。

## 最重要的交互 P0
- 学生输入自然语言（如“尽量在大三前补完，这学期尽量轻松，但数据结构必须保留”）→ 显示 AI 解析的**待确认意图草稿**。
- **第一次确认**：展示硬约束、软偏好、学分上限（不猜）、锁定课程、范围与未知项；让用户编辑、确认，确认前不可进入有状态的 solve。
- 已确认才进入 `solving`，前端调用真正的规划工具 API，不能前端计算冲突、填充假方案或让文本直接覆盖当前课表。
- 显示真实候选与原方案变化（补修课程、班次、学分、冲突、风险、未解决）；如果后端无法求解、缺课表或模型不可用，清楚显示“未生成候选”。
- **第二次确认**：`采用候选` 或 `保留原方案`，只有后端确认采用成功才能刷新当前方案；失败、拒绝、超时原案不变，候选过期可再试。
- 桌面右侧 AI 抽屉，移动端全屏，聚焦课程时携带 current course context；解释功能作为“查看依据”复用已有 ExplainPanel，仍明确规则模板非 AI。
- 不要求本轮做真实课表图片 OCR、通用聊天、多学期未验证的自动重排。

## 与 A 的并行接口策略
A 正在独立实现后端，**你不能假定 API 已存在**。参考本文给定的协调建议，仅设计可替换的前端 typed adapter：
`POST /api/v1/ai-planning/interpret` → `intent_id`, `plan_digest`, `parsed_intent`, `ambiguities[]`, `data_source`, `generator_kind`, `can_confirm`;
`POST /api/v1/ai-planning/solve` → `candidate_id`, `status`, `candidate_plan`(nullable), `diff`, `risks[]`, `unresolved[]`, `message`;
`POST /api/v1/ai-planning/adopt` → `candidate_id`, `plan_digest`, `accept:true` → adopted state/result version.
请在 `docs/final_upgrade/FRONTEND_AI_API_EXPECTATIONS.md` 明确所有字段假设及 mock fixtures，并把 client 封装为单独 adapter。不修改 /schemas/ 或 /docs/interfaces/。如果真实 A API 不匹配，报告集成差异，不在前端“自动适配”虚构字段。

## 现有接口接入
- 已有个人规划 `GET /api/v1/personal-planning/curriculum-versions` 和 `POST /api/v1/personal-planning/plan` 必须尊重真实 readiness；若 catalog 未配置 503，页面给出明确配置/数据不可用态，**不能退回固定 Case A 冒充个人结果**。
- 解释 `POST /api/v1/explanation/plan` 可以继续消费现有 PlanResult/MakeupTask/Offerings；只有 `planning != null` 且上下文可用时显示适当的结果解释入口。
- 新 AI 控制器默认关闭时提供明确“AI 调整尚未配置”的不可用态；不要用硬编码“AI 已调整成功”。
- Mock fixture 可以用于离线**界面测试与演示预览**，必须醒目标注“仅前端预览/非真实模型/未调用 Planner”；生产数据失败不 fallback。

## 测试与交付
用已有 Vitest、Vue TypeCheck、Vite Build；新增端到端状态流组件/适配器测试（草稿→确认→求解→候选→采用、拒绝、不支持、模型失败、过期、双确认、Mock 标识）。尽量保持已有四区块组件可用，不破坏旧 Case A。至少浏览器/组件层手工检查窄屏和长文本、loading/errors。
完成后 push 分支，提交 `docs/final_upgrade/reports/AI_FRONTEND_REPORT.md`；创建目标为 `feature/final-upgrade-integration-qa` 的 Draft PR（可行时），**不合并**。明确哪些交互是真 API、哪些仅 Mock/未接入；不要复制用户真实 Key、学号或成绩明细。
