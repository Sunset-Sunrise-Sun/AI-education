# Agent B · 有依据的规则解释与最小 UI

你是 AI-education 的 Builder B，今晚无人值守。先完整阅读 AGENTS.md、docs/final_upgrade/README.md、docs/ARCHITECTURE.md、docs/GIT_WORKFLOW.md、docs/interfaces/integration.md、相关 status、现有 Planner 结果/来源字段和前端实现/测试。按公共协议先输出任务理解后自行继续，不等待用户回复。

**分支：** 仅 `feature/explanation-agent`，基于 `feature/final-upgrade`；禁止写 main 或集成分支，禁止合并。你与 A 并行，**不能假设 A 的新 API 已存在**。

## P0 目标
在现有稳定 Case A 规划结果上演示**解释与证据追溯**，不改计算：学生点击某项补修/未认定/学期安排原因，系统可从已有结构化结果与证据生成清晰解释，显示信息来源、未知条件及人工确认要求。AI 只负责解释，不能编造源数据、课程等价、先修边、规划原因，不能修改补修状态或计划。

## 开发路径
1. 查找现有 PlanResult / MakeupTask / reason / source_evidence / unresolved / risks 等字段及当前结果 UI。先确认哪些命题有已核实证据，不得自己推断规划器内部未给出的理由。
2. 做**有证据的 explanation payload builder**：只读接受当前结果及被选中条目，收集来源和状态，区分“确证规则 / 学生输入或假设 / 系统建议 / 未知”。避免传整份未经脱敏成绩给外部模型。
3. 解释服务采用**确定性可用基线**：模板基于证据生成说明，并清楚标记 `rule-based explanation`（不是 LLM）。若项目已有合法、可配置、经许可的 LLM 接口，可在独立可选适配层中使用，严格依据给定事实、做输出字段和事实/证据绑定校验；无服务或调用失败时降级到标注清晰的规则模板。**不得宣称离线模板就是 AI 模型**。不得自行引入新付费服务、秘钥或大型依赖。
4. 最小前端：在现有结果位置增加“查看依据/为什么这样安排”入口，展开解释、依据、尚未核实项、数据来源（Mock/Real），请求失败时安全提示；对“推定可转换”不能写成学校已批准。前端只展示，不重算。
5. 优先避免改 A 的文件及共用 API 契约；必要注册处允许最小修改但报告冲突风险。API 路径需要新建时优先新私有接口，不变更任何既有路径/公共 Schema。
6. **课表图片识别、聊天框、自然语言调课为明确延后项。** 不为赶演示做假 OCR 或虚假的模型调用。若 P0/P1 全过，仅在报告中给出图片识别后续设计，不擅自引入新的服务。

## 验收用例
- 解释必有可追溯的 `reason/source_evidence` 等真实字段支持；未知关系只能显示待确认，不可捏造学校规则或先修关系。
- 同一案例的 satisfied、required、manual_confirmation、风险/待办（按存在的状态类型）得到不同准确说明；缺证据状态不会被错误确证。
- 任意解释调用不修改规划结果，失败/模型不可用时仍安全且真实地标注规则模板。
- 前端正常显示已存在案例；无数据、请求失败、Mock、长文本及不支持解释情形有清楚反馈。
- 运行已有相关测试与新增测试，报告精确命令/结果，不能只声称“已测试”。

## 禁止
不修改 Planner、Curriculum/学生计算、/schemas、/docs/interfaces、业务规则、现有 Case A 接口；不加入普通聊天机器人，不自动替学生做认定，不因用户没有提供模型密钥就报已实现 LLM。无人值守遇到跨模块协议需求只记录 BLOCKED。

## 交付
提交 `docs/final_upgrade/reports/AGENT_B_REPORT.md`：实现点、模型是否**实际调用**（区分模板/LLM）、来源字段、入口截图或复现步骤、测试命令与结果、文件列表、已知局限、和 Agent A 后续联调边界。更新相关 STATUS/WORKLOG，push 本分支，可创建 base 为 feature/final-upgrade 的 draft PR，**不得合并**。
