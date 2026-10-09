# Agent A｜DeepSeek 转专业补修 Planning Controller（无人值守开发）

## 立即任务
你是 Builder A，专注**真正的 DeepSeek AI 补修规划后端**。唯一写入分支：`feature/deepseek-planning-controller`（已创建）。起点是 `feature/final-upgrade-integration-qa`，它是**未完成联合回归的候选**，不是正式稳定基线。**不再执行旧的 NIGHT_AGENT_A_INTEGRATION_BUILDER.md 专职 QA 任务**；只在你的新功能所需范围内补回归。禁止改 main、feature/final-upgrade、旧 PR #62/#63/#64 以及 B 的分支；禁止任何自动合并。

开工先读 AGENTS.md、docs/ARCHITECTURE.md、docs/GIT_WORKFLOW.md、docs/final_upgrade/AI_PLANNING_NEXT_PHASE.md、docs/final_upgrade/DEEPSEEK_PLANNING_AGENT_V1.md、docs/final_upgrade/INTEGRATION_QA_STATUS.md 和现有 backend 模块及测试。按 AGENTS.md 先输出任务理解，随后自动继续，不等待夜间人工回复。使用独立 worktree/clone，不能与 B 共用工作目录。

## 产品限定
这是**已转专业本科生**的补修缺口与学业路径规划，不是通用选课聊天机器人。先围绕**当前学期补修课程的班次/负荷调整**形成真实闭环，未来学期只分析已证实的课程依赖和风险；没有可靠多学期重规划器时不得声称完成跨学期自动调整。

## 核心开发（P0）
1. 盘点已有个人规划与 Planner 能力。先运行相关基线测试并分类失败。不修改冻结四参数签名、/schemas/、/docs/interfaces/、培养方案认定及学分硬约束。架构不支持的扩展写接口变更提案，不能偷改契约。
2. 新增隔离的 `app/ai_planning/`（如现有项目另有适配位置，以实际代码为准）和**明确命名的新私有 FastAPI 路由**，不能覆盖旧路由；尽量不编辑现有复杂核心文件。输入只允许现有已验证的 MakeupTask、PlanResult、Preference、CourseOffering 和选中方案上下文。区分请求前端数据来源 Mock/Real。
3. DeepSeek 用 OpenAI 兼容 API：`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-flash`、`DEEPSEEK_API_KEY` 只从服务器运行环境取，`AI_PLANNING_ENABLED=false` 默认关闭；所有配置放 `.env.example` 占位符，不存真实值，前端不得接触密钥。**过去对话里暴露过的 sk- 开头旧密钥已应作废，禁止使用或引用**。
4. 实现 `interpret`：模型把“这学期太累，但数据结构必须保留、尽量不在周五上课”转成有限、可验证的结构化**意图草稿**：范围、硬约束、软偏好、锁定课程、歧义、来源和当前方案指纹。LLM 输出不可信，强制 Pydantic/严格枚举和 course/class 白名单验证。"少上一点课"不得猜固定学分数。提供注入型假模型以在无 Key 情况下测试；**没有 Key 不得假装真实模型成功**。
5. `confirm + solve`：**仅当用户明确确认意图并匹配原方案与上下文指纹**时，才进行影响方案的求解；调用受控工具/现有 Planner（不能让 LLM 自行输出合法 PlanResult），校验学分、时间和周次、课程锁定、数据快照，并生成候选差异及风险。若既有 Planner 不支持重新求解请求，安全返回明确 `unsupported` 和阻塞原因，绝不硬造候选。确认前只读模型解析可以运行。
6. 只读 compare、候选 adopt/reject 的**最小独立会话/状态机制**：同一个版本的有效候选才能被用户第二次确认采用；若无可靠持久化机制，明确仅在进程/会话演示可用且失效时 fail-closed，不能宣称已有持久账户。未经用户确认绝不能覆盖当前方案。避免将 student raw PII 留在日志或发送给 DeepSeek。
7. 错误路径与成本：401/402/429/5xx、网络超时、空 JSON、幻觉课程号、重复确认、过期方案、无教务快照、Token 预算超过限制：均返回有边界的错误并保留原方案；模型输出次数、工具调用次数、超时均有限额。模型选择优先非思考模式，暂不依赖 beta strict tool_calls。

## 前后端临时协作契约（非公共 schema，建议直接采用并在后端文档中固定）
私有前缀建议：`/api/v1/ai-planning`
- `POST /interpret`：请求携带当前 plan/context 与 user_message；响应 `intent_id`, `plan_digest`, `parsed_intent`, `ambiguities[]`, `data_source`, `generator_kind`, `can_confirm`。**仅意图草稿，不求解**。
- `POST /solve`：请求含 `intent_id`, `plan_digest`, `confirmed_intent`；响应 `candidate_id`, `status`, `candidate_plan`（可为空）, `diff`, `risks[]`, `unresolved[]`, `message`。仅对已确认意图生成候选。
- `POST /adopt`：请求 `candidate_id`, `plan_digest`, `accept:true`；返回是否采用及结果版本。若安全采用无法实现，必须报告 blocked、不可返回假成功。
这些是**新内部路由建议**，不是预先授权修改 /docs/interfaces/。你可根据实际实现进一步缩小，但需要在 `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md` 明确实际 JSON examples 与 error codes。若不能遵照这些结构，请在分支中说明差异，B 不得凭空调用。

## 边界与验收
必须真实调用现有合法 Planner 得到候选或诚实返回不可用；可用假模型测试结构化意图，但不能将其对外显示为 DeepSeek 已接入。二次用户确认不得省略。最少覆盖：正常意图→确认→求解、未确认不求解、锁定课程、模糊学分、未知课程、数据快照过期、LLM 不可用、无教学班、结果无法满足/未采用、意图数据隔离。Case A 和解释服务不能回归；报告完整测试命令/环境/结果及遗留基线失败。

## 交付
push 自己分支，新增 `docs/final_upgrade/reports/DEEPSEEK_CONTROLLER_REPORT.md` 与内部 API handoff 文档（都只在你的分支）；允许创建指向 `feature/final-upgrade-integration-qa` 的 **Draft PR**，禁止自动 merge。报告明确：真实 DeepSeek 是否用**新安全密钥由运行方在线验证**；若无密钥必须写 NOT VERIFIED，不能要求用户明文回发。
