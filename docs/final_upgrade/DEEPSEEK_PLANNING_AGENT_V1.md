# DeepSeek AI 补修规划 Agent｜接入与开发任务书 v1
日期：2026-10-08
状态：**架构方案/待集成基线通过后执行**。不可据本文件自动合并代码或修改公共契约。

## 1. 产品任务
学生已转专业，从“培养方案+本人已修成绩→补修缺口→当前及未来学期路径”的场景，使用自然语言要求改变补修安排。AI 提取目标、提出可行的工具策略、调用现有规则与 Planner、解释候选差异；认定、硬约束、教学班事实均由受控模块负责。

## 2. DeepSeek 官方接入配置
- OpenAI 兼容 base_url：`https://api.deepseek.com`；Chat Completions API。
- 首选 model：`deepseek-flash`（DeepSeek-V4.1-Flash）；模型 ID 从服务端配置，不在前端硬编码。
- Python 服务端使用已有或轻量 OpenAI 兼容 SDK；不添加新 Agent 框架。
- 环境变量样例（只在 .env.example 给占位符）：
  - `DEEPSEEK_API_KEY`：仅服务器注入，绝不提交。
  - `DEEPSEEK_BASE_URL=https://api.deepseek.com`
  - `DEEPSEEK_MODEL=deepseek-flash`
  - `AI_PLANNING_ENABLED=false`（默认关闭，配置和权限验证后开启）
  - `AI_PLANNING_MAX_TURNS=3`（一次规划最多 3 次 LLM 工具循环，示意可调整）
  - `AI_PLANNING_MAX_OUTPUT_TOKENS` / `AI_PLANNING_REQUEST_TIMEOUT`：服务端有界设置。
- JSON Output 用 `response_format={"type":"json_object"}`，system prompt 应明确 JSON 并包含目标 schema 示例；无论何种模式都要 Pydantic 验证，非法/空/截断响应 fail-closed。
- DeepSeek strict function calling 为 Beta，使用 `https://api.deepseek.com/beta` 且 tool function 需要 `strict:true`，第一版不依赖此特性。自建白名单、参数校验与工具调用限次。
- 思考模式工具调用需按 DeepSeek 当前文档保留必要 assistant reasoning_content；第一版优先固定非思考模式、规避不必要的多轮协议复杂性，升级前增加契约测试。
- 公开文档：https://api-docs.deepseek.com/zh-cn/ 、https://api-docs.deepseek.com/zh-cn/guides/tool_calls/ 、https://api-docs.deepseek.com/guides/json_mode/ 、https://api-docs.deepseek.com/zh-cn/quick_start/pricing/

## 3. AI Planning Controller 生命周期
状态建议（**内部 proposal，不等于已批准公共 Schema**）：
- `PLAN_CURRENT`：已被用户采用的稳定方案及输入/来源指纹；
- `INTENT_DRAFT`：AI 输出自然语言目标的结构化草稿，尚未被确认；
- `INTENT_CONFIRMED`：用户确认硬约束/软偏好、锁定课程、目标范围；由后端绑定当前方案 hash；
- `SOLVING`：受控调用既有服务，验证工具参数、教学班快照、数据依赖；
- `CANDIDATE_READY | NO_FEASIBLE_CANDIDATE | BLOCKED`：不覆盖原方案；
- `ADOPTED | REJECTED`：必须第二次确认后才修改当前方案，支持可追溯版本/撤销。
任何阶段输入的培养版本、已修记录、教学班快照变化即让未采用候选失效。

## 4. 最小可行工具白名单
- `inspect_transfer_gap`：只读 MakeupTask[] 和源证据，区分 required/satisfied/manual_confirmation 等；
- `inspect_current_plan`：当前方案、已锁定正常课、补修课、用户偏好和数据完整性；
- `list_available_sections`：按已验收当前学期 snapshot 查询真实可用教学班（未知/Mock 明确显示）；
- `solve_current_semester`：使用既有 Planner 的四参数签名计算候选，不允许 LLM 直接填写 PlanResult；
- `compare_candidates`：确定性统计课程、学分、校区、时间与风险；对数据未知字段返回不可比较。
**暂不开放跨学期变更工具**，除非现有确定性课程级跨学期规划确实支持可信重求解且通过专门验收。第一版可以只读说明未来影响，缺数据须说明“不确定”。

## 5. 用户确认与数据权限
- 第一确认：展示模型提取的用户意图、硬约束、软偏好、课程锁定、要调整的学期、推迟风险；模糊项需用户填写。禁止把“尽量轻松”自动变成固定 20 学分上限。
- 第二确认：展示当前方案与候选差异，用户同意后才采用；拒绝/超时则原方案不变。
- LLM 接收脱敏且最小化的学业上下文：课程标识、学分、学期、已确认约束、摘要化依赖与方案差异；不发送姓名、学号、成绩单原文件、Cookie/token、完整成绩或教务密码。
- 模型输出是不可信建议：后端检查每个课程号和班级号是否属于本次有效数据；任何 LLM 不能更改学校认定、毕业要求、先修关系、容量、学分事实、证据等级。
- 模型请求由后端完成。前端不包含 Key、不直接与 DeepSeek 通信。出现 401/402/429/5xx、超时、空 JSON 时提供明确错误、有限重试、保持原方案。
- 记录费用（输入/输出 token 与估算金额、失败原因，默认不留学生原始对话和 PII）；限制每会话调用次数和总 token。

## 6. 与第一阶段开发分支的集成条件
现有：
- A 个人规划 API：`GET /api/v1/personal-planning/curriculum-versions`，`POST /api/v1/personal-planning/plan`。有 Mock 两学生测试，但真实目录/教学班依然需要装配；某些状态会返回 `planning=null`。
- B 解释 API：`POST /api/v1/explanation/plan`；当前使用可追溯规则模板，**真实 LLM 适配未配置**。
- 两边均改 `backend/app/main.py`，需合并后做全链路校验。未验收的接口不得宣称已稳定。
- 本任务只在两个分支通过审查并合并到 `feature/final-upgrade` 后启动。main 不动。

## 7. 下一轮 Agent 分工
### Agent A — 后端 AI Planning Controller
1. 先写受控工具与请求/响应 proposal，不得未经批准改 `/schemas` 或 `/docs/interfaces`；
2. 新建最小模型 client（依赖注入，Mock transport 用于测试，无密钥可跑）；
3. 解析结构化意图并生成确认草稿，输入用户确认后才执行；
4. Planner 返回合法候选，服务端再次确定性验证；不能求解时返回 unavailable；
5. 模型调用失败、越权工具、课程/教学班伪造、状态过期、重复确认、并发采用、成本超限等测试；
6. 报告真实模型是否完成端到端在线调用，未连接密钥不得声称成功。

### Agent B — 前端产品交互
1. 复用旧 Vue 组件，信息架构重组为“转专业分析/补修路径/AI 调整”；
2. 右侧聊天抽屉(移动端全屏)，可以携带当前补修任务和计划上下文；勿重复实现课程判定；
3. 第一确认面板：硬/软约束、学分值、锁定课程、调整范围可编辑；
4. 加载/无解/过期/错误与模型未启用态；原方案不因模型回复而变化；
5. 第二确认：对照新增/删除/换班/学分/风险、明确“采用候选/保留原案”与撤销入口；
6. 用显式 Mock 请求/响应适配器测试，不猜 A 的 API 字段；
7. 报告截图和可复现步骤。

## 8. 共同验收
1. 初始方案有至少一门补修课；输入“这学期太累，尽量降低学分，但数据结构必须保留”，模型给出草稿，**用户可以纠正再确认**；
2. 用户点击确认才启动 Planner，完成后出现由 Planner 实际产生的候选；两个确认各自有测试；
3. 原计划与候选严格隔离；不采用/无解/错误不改变原计划；
4. 输入超出当前源版本/错误学分、虚构课程号、不能核验的未来开课，系统 fail closed；
5. Mock/Real、规则模板/真实 DeepSeek 调用、个人成绩可信度均清楚标记；
6. 所有已有 Case A、A/B 个人计算与解释测试回归。
