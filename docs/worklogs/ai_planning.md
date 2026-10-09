# AI Planning（DeepSeek Controller）工作日志

> 仅追加历史记录。新的 Agent 优先阅读 docs/status/ai_planning.md。

## 模板
### YYYY-MM-DD - 功能
- 本次目标：
- 已完成：
- 修改文件：
- 测试：
- 使用数据：Mock / Real
- 已知问题：
- 需要人工确认：
- 对其他模块影响：
- 下一步：

### 2026-10-08 - 新建 DeepSeek AI Planning Controller（分支 `feature/deepseek-planning-controller`）
- 本次目标：实现真实的 DeepSeek 意图解析 + 用户确认后的 Planner 调用 + 候选与二次确认采用；
  无密钥时用注入式假模型完成端到端测试，但**不得声称完成真实在线调用**。
- 已完成：
  - 新增隔离模块 `backend/app/ai_planning/`（config / errors / context / intent / minimize /
    deepseek_client / fake_model / service）与 4 条私有路由
    `backend/app/api/ai_planning.py`（status / interpret / solve / adopt）。
  - 新增 `backend/app/services/ai_planning_runtime.py`：进程内装配；
    **无密钥不构造真实客户端**，⛔ 也不内置假模型作为回退。
  - `backend/app/main.py` 只加 **2 行**（import 组 + `include_router`）。
  - DeepSeek 走 OpenAI 兼容 `/chat/completions`，`response_format=json_object`，
    仅用标准库 `urllib`（⛔ 未引入第三方依赖 / Agent 框架 / 数据库）。
  - 安全不变量：白名单外课程 / 教学班 ⇒ 拒绝整份草稿；"太累"不换算成学分数；
    硬约束必须带依据；未确认不求解；未二次确认不改方案；指纹变化即失效；
    模型调用次数有上限；会话进程内有界；命中 PII 直接 400 且不外发。
  - 候选只由冻结的四参数 `PlannerProvider.plan(...)` 产生，服务端再做确定性复核；
    差异与风险完全由后端计算。
- 修改文件：见 `docs/final_upgrade/reports/DEEPSEEK_CONTROLLER_REPORT.md` §2。
- 测试：新增 96 项（`test_ai_planning_service.py` 47 / `test_ai_planning_api.py` 22 /
  `test_ai_planning_client.py` 27）；后端全量 **3174 passed / 2 failed / 2 skipped**，
  2 项失败为既有 Windows 路径语义差异（基线同命令 3078 / 2 / 2）。
- 使用数据：**Mock**（合成教学班与补修任务）。
- 已知问题：真实在线调用 **NOT VERIFIED**（环境无密钥）；
  会话仅进程内；`exclude_course` 与跨学期调整明确 `blocked`；
  没有教学班输入时候选可能为空课表（已在 `diff.removed` / `risks` 中如实暴露）。
- 需要人工确认：是否引入会话持久化（属数据库结构变化）；
  是否扩展 Planner 以支持 exclude / 跨学期；是否接受新私有路由路径。
- 对其他模块影响：`main.py` 2 行（与 B 分支的共享冲突面）；
  `test_integration_orchestrator.py` 路由白名单新增 4 条。
  ⛔ 未改 `/schemas`、`/docs/interfaces`、`app/planner/**`、`app/curriculum/**`、
  `app/personal/**`、`app/explanation/**`、`app/integration/**`。
- 下一步：Reviewer 评审；运行方用新密钥做在线验证；B 按
  `docs/final_upgrade/AI_PLANNING_API_HANDOFF.md` 实现前端三块 UI。
