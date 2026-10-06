# OPC 提交就绪审计

> 2026-10-06 PR51/PR52交叉审计更新：[权威truth table](OPC_CROSS_PR_TRUTH_TABLE.md)。下文基于main c75b6da的原库存为历史基线；PR51已补README、演示脚本、架构图、启动和恢复指南，不再列为缺失。当前尚需修正来源/计算话术与LEVEL2说明，并完成成品视频、slides、截图、赛规核对及彩排。以truth table的Mode1回放/Mode2实际计算及Planner受限能力为最新口径。

审计日期：2026-10-06（Asia/Shanghai）。审计对象：main `c75b6da8101d9323160ee99beb51d57b1526e02d`，已合入 PR48。独立 reviewer，仅文档交付，不改生产、不 merge、不访问学校。新增材料都是审计草稿，尚不等于负责人批准的最终提交件。

## 结论与 scorecard

**SUBMISSION READY = NO。** 工程就绪与比赛提交就绪不同。没有根 README、成品 slides/视频/截图、正式规则核对记录；AI/Agent 的已实现范围须诚实说明；没有已验证的 3–5 分钟现场演示包。优先补材料、校准叙事、彩排，不增加核心功能。

评分采用证据状态，不推算获奖概率：绿=有当前明确证据，黄=部分证据/需要包装，红=缺关键材料或不能证明。

| 维度 | 状态 | 依据 / 提交前动作 |
|---|---|---|
| 用户与痛点 | 绿 | 转专业培养方案衔接明确；补一个脱敏人物场景 |
| 确定性技术与边界 | 绿 | Curriculum、约束检查、受限换班、UNKNOWN、人审；勿称全局优化 |
| 代码链路证据 | 绿 | Synthetic LEVEL1/API/Provider 验证；并非实际 Real LEVEL2/3 |
| 产品演示可操作性 | 黄 | Mock UI + fixed Case A runtime；尚无完整视频彩排证据 |
| AI/Agent 要求匹配 | 红/待确认 | 固定工具编排已实现；未见运行中的 LLM/RAG/GraphRAG；官方赛规未入库 |
| 效果量化 | 黄 | 有测试和 case 计数；无用户效果/节省时间/准确率数据 |
| 评委入口与叙事 | 红 | 根 README 缺失；旧运行说明与当前实现不一致 |
| 提交物完整度 | 红 | 无成品演示视频、slides、截图、团队实名分工及 portal 要求核对 |
| 风险透明度 | 黄 | 代码边界良好；需要一页统一 Synthetic/Mock/Real 与限制声明 |

### 最强 5 点

1. 围绕转专业“认定与历史缺口”组织任务，而非只回答课程问答。[范围](../ARCHITECTURE.md)
2. 区分历史欠修与未来培养安排，并保留规则出处、待确认认定。[Curriculum 状态](../status/curriculum.md)
3. UNKNOWN、容量、偏好、人工确认不被包装成已认证可执行结果。[Planner 状态](../status/planner.md)
4. 支持受限换班/时间约束预检查，保留当前课表，输出 changes/risks/unresolved。[Planner](../../backend/app/planner/provider.py)
5. 验收绑定、Store 复验、无静默 Mock fallback、ready/partial_ready 分离，形成可信失败路径。[工具](../../tools/prepare_real_case_a_runtime.py)

### 最大 5 个评委风险

1. 宣称 AI Agent/GraphRAG/自然语言推理已运行，评委追问时只能展示固定编排。须说明当前实现与规划；若赛规要求运行中的模型，此资格缺口无法靠话术填补。
2. 默认 Mock 页面被当成实时运算；文件选择被当成已完成 XLSX→规划。当前 UI 未串接导入，generic 导入 API 不注入 frozen Case A。
3. 只披露教学班 Synthetic，误使评委认为合成 case 的 Curriculum 是真实输入；端点名 Real 不证明来源。
4. 称“所有偏好/学分/容量/通勤/先修已满足”“全局最优/跨学期自动规划/成功选课”。代码不支持这些承诺。
5. 文档与演示入口散乱、没有备份视频；临场访问学校、等待分页或临时修环境吞掉演示时间。

## requirement-fit matrix

以下为常见产品比赛审视角度，**不是已确认的 OPC 官方评分规则**。仓库未找到官方赛规/模板/字段/时长限制。

| requirement | current evidence | strength | gap | recommended fix |
|---|---|---|---|---|
| 清晰用户 | 转专业学生；Case A | 强 | 缺 1 张人物情境卡 | 使用虚构人物，不展示真实身份 |
| 清晰场景 | 旧/新方案、已修记录、当前课表、偏好 | 强 | 入口故事被模块说明分散 | 用“已修能否认定→历史缺口→可安排性”串联 |
| AI/Agent 角色 | PlanningOrchestrator 固定调用 3 Provider | 部分 | 无运行中 LLM/检索/自然语言解析证据 | 如实称工具编排原型；核对官方 AI 必需条件 |
| 可执行产品 | FastAPI、Vue、本地 UI、runtime factory | 部分 | 未有评委可复现的录制/启动包 | 锁合成演示 snapshot，提前彩排 |
| 不仅聊天 | 结构化任务与确定性 PlanResult | 强 | 不能据此声称模型 Agent 已完成 | 展示输入输出及人审边界 |
| 可测价值 | Case 计数、状态/约束测试 | 部分 | 无节省时间/用户数据 | 演示可核验计数；效果指标注明待测 |
| 可演示性 | Mock UI、synthetic E2E 测试 | 部分 | 不是完整比赛故事/录像 | 4 分钟脚本与备份视频 |
| 技术深度 | 来源绑定、限制求解、换班检查、拒绝不完整数据 | 强 | 架构建议技术易被说成现有依赖 | 主图只放已实现；细节放附录 |
| 实际可行性 | 本地受控读取、Word/XLSX、Store | 部分 | North 未恢复；未公开部署 | 不以实时学校网络作为演示依赖 |
| 人在回路/风险控制 | manual_confirmation、UNKNOWN、明确拒绝 | 强 | 需可见画面与业务解释 | 展示 1 个待确认项及限制说明 |

## 定位与价值回答

**一句话：学航·转衔是面向转专业学生的 AI 学业路径重构 Agent 原型，用有出处的培养要求和确定性检查，把历史缺口、课表调整与待确认风险放进同一条可追溯流程。**“AI”是产品方向，当前模型能力边界必须见下文，不可省略。

- 谁需要：已经转专业、须比较旧/新培养要求与已修课程，并安排补修的学生；辅导/教务人员可复核。
- 教务系统为什么不够：本项目聚焦跨培养方案的解释、认定不确定性和排课衔接；仓库没有对所有学校教务产品的功能调查，因此不能说“教务系统都做不到”。
- 为什么不只是 chatbot：有结构化输入/输出、固定工具编排、独立确定性检查与风险记录；当前不是已证明的自主 LLM Agent。
- AI 做什么：预期辅助理解输入、证据检索、结构化偏好与解释；当前未证实这些模型能力上线。不能把规则实现重命名为“AI 推理”。
- 确定性系统做什么：来源授权下的课程匹配/范围投影、时间冲突检查、受限可行性检查与换班建议；不执行学校选课。
- 为什么组合 RAG/GraphRAG/规则/约束：潜在分工是检索提供证据、图表达关系、规则作认定、规划器检查约束；**当前 RAG/GraphRAG 未实现，NetworkX/OR-Tools 不是现有 Planner 事实**。比赛前不为名词临时加新功能。
- Path Repair 价值：在当前课表基础上解释哪些调整可缓解冲突，减少“推倒重排”的交互负担；当前受限换班，不是连锁修复/全局最优。
- 为什么留人审：未知认定、规则口径、容量和课表信息不足时，系统不能替代学校正式认定或学生选课确认。

### 差异化（基于任务设计，不是市场优越性实测）

| 对照类型 | 本项目强调 | 当前边界 |
|---|---|---|
| 通用大学 chatbot | 认定依据→结构化补修任务→规划结果 | 无已上线 LLM/检索证据 |
| 普通排课器 | 从培养方案缺口到排课的衔接 | 约束覆盖受限，非全局优化 |
| 课程推荐 | 认定不确定性与风险透明 | 不按猜测优先级/偏好打分 |
| 静态 degree audit | 缺口与教学班/当前课表换班衔接 | fixed case；generic XLSX 未端到端接入 |

## 仓库定位稀释 / stale 文案（仅报告，不修）

- 根 README 不存在：评委打开项目先遇到目录，没有产品入口。
- [frontend/README](../../frontend/README.md)：“唯一 Mock 来源”“无单元测试”，与现有 `/api/v1/plan` 与 134 测试不符。
- [backend/README](../../backend/README.md) Phase1 与“当前调用 Mock”已不足描述 merged runtime；Python 仅 3.14 验证的说法也未更新近期 Linux 3.12 证据。
- [DEMO_RUNBOOK](../e2e/DEMO_RUNBOOK.md) 把未配置→503写成 main 本质 LEVEL0；应区分默认未配置、LEVEL1 wiring 能力、真实 LEVEL2/3未达成。
- [ARCHITECTURE](../ARCHITECTURE.md) 的 OR-Tools/PostgreSQL/Chrome Extension/LLM 都是“建议技术”，不可转写为现有架构；实际 Store SQLite，Planner 无 OR-Tools。
- [integration interface](../interfaces/integration.md) 旧“只有 Protocol”是历史描述；属冻结契约文档，别未经确认修改接口，只在提交附录注明现有 concrete Provider。
- [PreferencePanel](../../frontend/src/components/PreferencePanel.vue) 注释“Agent 解析偏好”没有运行证据；对外材料必须称结构化表单输入。

## 证据账本 / 指标

| 事实 | 证据/来源 | 如何使用 / 不可外推 |
|---|---|---|
| main 已 merge PR48 | c75b6da，父提交6c1353b | 代码合并不等于真实 E2E |
| Backend2979pass/2skip；frontend134；type/build通过 | 2026-10-06独立6c1353b审计；本轮确认 main 的 backend/frontend/tools/schema 与该HEAD无diff | Linux环境回归，非准确率、非覆盖率；不得说100%覆盖 |
| Synthetic20tests通过 | 本轮在 main archive 实跑 test_synthetic_production_e2e.py | 正式代码链路，合成数据；非Real2/3 |
| preflight partial_ready/LEVEL1/eligibilityfalse | 本轮 main 实跑 --preflight --quiet | CourseData准备链，不是可直接启动完整runtime |
| Case A源文档84/94条；已修24；输出23任务，其中12satisfied/11manual | docs/status/curriculum.md的受控输入记录 | 本轮未读私有材料/独立重算；12不是命中率，23不是23门待补课 |
| Case A historical20/future71/unresolved3 | 同上；三个已satisfied区间项不阻断投影 | 与23输出不同计数口径；不可把3说成消失的风险 |
| UNKNOWN/人审/受限换班 | Planner源码/状态；synthetic测试 | 不等于正式容量/通勤/学分/偏好执行 |
| Real LEVEL2/3未证实，North暂停 | REAL_CASE_A_ACCEPTANCE / READINESS_DECISION_NOTES | 不称实时接入成功；HTTP200本身不证明真实来源 |

建议演示量化：固定case的输入条目/已修条目/历史未来范围计数、待确认项数、selected/changes/risks/unresolved计数、明确冲突或UNKNOWN的解释、请求状态和来源。每个指标绑定固定fixture与录制版本，不比较不同计数口径。请求耗时、重复跑一致性可在彩排后记录实际结果，不能现在填假数字。没有用户数、准确率、真实上线、节省时间/成本、签约和正式学校认可数据。

## artifact inventory（审计前库存，新增 reviewer 草稿不冒充成品）

HAVE=仓库可定位；PARTIAL=有技术素材/本轮草稿但不是提交件；MISSING=未发现 tracked 成品，不证明团队私下没有。

| artifact | 状态 | 证据 / 补齐动作 |
|---|---|---|
| 一句话/痛点/用户 | PARTIAL | AGENTS/架构；本轮建议稿需负责人批准 |
| 根README/200–300字介绍 | MISSING | 根ls-tree无README；本轮提供可移用草稿 |
| 功能表 | PARTIAL | 各status散落；需已实现/限制清单 |
| 架构图 | PARTIAL | ARCHITECTURE文本图；本轮Mermaid草稿；缺成品slide |
| 创新点 | PARTIAL | 信任边界/重构/repair；缺评委版与证据标注 |
| 3–5分钟脚本/1分钟pitch | MISSING | 只有操作runbook；本轮提供草稿，未彩排 |
| 技术附录/风险声明 | PARTIAL | 接口/数据门禁齐全但长且混有旧状态 |
| 问答库 | MISSING | 本轮 OPC_JUDGE_QA 草稿 |
| 团队角色/成员信息 | PARTIAL | AGENTS有模块职责，无成员姓名/资质可核验提交表 |
| screenshots/录屏/slides/pitch deck | MISSING | tracked文件未检出png/jpg/pdf/pptx/mp4成品 |
| demo URL | MISSING | 仅localhost；不可当作评委可公网访问URL |
| 本地运行说明 | HAVE（stale） | frontend/backend/DEMO_RUNBOOK；需封存准确快照与版本 |
| 视频计划/提交清单 | MISSING | 本轮提供草稿，仍待制作/核对 |
| 官方比赛规则/portal表格 | MISSING | 未查到；负责人核对正式来源 |

## P0/P1/P2交付计划

目标是在2026-10-08之前完成；这是用户给定的工作目标，不是已核实的比赛截止时间。以下按Asia/Shanghai排期，不保证团队产能。

| 优先级 | 任务 / 验收条件 | 建议负责人 | 努力 |
|---|---|---|---|
| P0，10/06 | 查官方规则、AI要求、格式/时长/资格、真实截止时间，留核对表；若硬性要求模型运行，升级负责人决策 | 提交负责人 | small |
| P0，10/06 | 批准一句话、Synthetic全范围披露、能力边界；禁止GraphRAG/最优/自动选课等过度承诺 | 产品负责人 | small |
| P0，10/07 | 做根README/项目简介、5页slides、脱敏截图；技术介绍更新为当前能力，不改契约 | 文档/演示成员 | medium |
| P0，10/07 | 锁合成fixture+SHA、按真实可运行路径彩排4分钟，录制主视频和备份；打包本地操作步骤与依赖 | 演示负责人；Builder只负责自身前端交付 | medium |
| P0，10/07 | 核对视频/slide/UI来源一致、链接可打开、无凭据/学生信息；owner填写portal实际表格与团队信息 | 提交负责人 | small |
| P1 | 评委Q&A演练、技术附录1页、计数指标卡；计时记录两次完整彩排 | 技术讲解者 | small/medium |
| P1 | 备用设备/离线素材/故障切片；录屏失败后有不冒充实时结果的备份 | 演示负责人 | small |
| P2 | 字体排版、字幕、镜头节奏、封面 | 视觉成员 | small |

提交完成前核对：官方要求/截止日期已确认；成员信息已owner核对；README与slides最新；演示来源可见；上传→规划未暗示贯通；AI边界明确；视频不泄露数据；演示版已锁定且能本地跑；备份视频可播；所有指标可追溯；公开链接能由非团队账户访问（如有）；最终表格/文件owner确认后按实际portal提交。本轮未替用户发布或提交。

### Builder现在不要花时间

不要新加LLM/RAG/GraphRAG、全局CP-SAT、跨学期优化、自动选课、学校实时深分页重试；不要把generic XLSX临时接入冻结Case A；不要掩盖Mock/UNKNOWN或自行实现认定。不要重写已PASS核心后端；不要堆新动画/路由替代视频和材料。只完成已授权前端工作，提供可录制的稳定页面与准确状态，余下靠文档/演示交付。

推荐话术、架构slide和4分钟脚本见 [OPC_PRESENTATION_PACK.md](OPC_PRESENTATION_PACK.md)。13项评委问答见 [OPC_JUDGE_QA.md](OPC_JUDGE_QA.md)。
