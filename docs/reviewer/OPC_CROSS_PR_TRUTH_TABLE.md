# PR51 / PR52 competition truth table

日期2026-10-06（Asia/Shanghai）。独立judging-facing审计，范围为文字/来源一致性，不是Codex1工程回归结论。

## 审计快照与裁决

已fetch all/prune/all-heads；GitHub metadata与pull refs independently一致：

- PR51 base main；feature/competition-demo-closure；28d2c1f312529161e308398d6f6884dfdccf2e8f。
- PR52 base main；review/opc-submission-readiness；90abb5ca431b83a11ce83b8fb3331933ca58e228。
- PR51 archive /tmp/opc-pr51；比较PR52上述原始HEAD材料。本补充报告会推进PR52 reviewer分支，不变更被审PR51。

**DEMO READY（judge-facing truth）= NO。SUBMISSION READY = NO。PR51 wording/provenance merge = BLOCK。**
原因是确定可定位的误导话术与来源/等级矛盾，不是要求实现新的AI功能或重开已关闭安全问题。实际工程回归留给Codex1，本轮仅少量离线HTTP/CLI probes验证争议说法。不改生产、不merge、不访问学校。

## 1. 术语：实现与来源是两个轴

- **Actual/production implementation logic**：实际执行仓库中的Curriculum/Provider/Planner代码；这不证明输入来自学校。
- **Real school data**：具体artifact有受控来源、授权及批准证据，并绑定当前消费的字节/版本；不是端点名、HTTP200、data_source=real、DEMO课程号派生或case名称能自证。
- **Synthetic**：人工/程序生成的输入，可能走实际生产代码，也可能借用real枚举形状；实际运行不会将其变成真实采集。
- **Mock/replay**：永久Mock接口回放提交的样例对象；HTTP/前端确实运行，但该请求不执行上游业务计算。
- **Planned**：尚无运行实现证据，不放入当前执行架构实线图。

禁止裸用“REAL=Curriculum/Planner”表示数据事实。推荐写“已实现并实际执行的代码”与“经证明的输入来源”两列。Mode2所谓“Real结果”仅表示来源端点/实际运算，不是整页或所有输入真实。

## 2. 权威provenance矩阵

Mode1=默认GET mock聚合回放；Mode2=POST plan实际计算。以下real data列指**是否有本轮可核验真实来源**，不是字段值。私有CaseA未提供本轮来源核验，不推定真实或虚假。

| component / executable path | Mode1 source | Mode2 source | real data? | real implementation? | synthetic? | mock? | planned only? | allowed wording | forbidden wording |
|---|---|---|---|---|---|---|---|---|---|
| StudentContext；frontend/config、state/userInput | CaseA默认情境+用户表单 | 同一表单；专业/年级不作为plan请求的Curriculum输入 | 未验证真人身份 | UI收集已实现；非个性化case装载 | 演示上下文可为虚构 | 初始情境演示 | 否 | “演示背景/表单” | “填写专业后自动重建该学生培养方案” |
| Curriculum input；load_curriculum_case | Mock对象展示；不读取真实方案执行 | 显式本地case；Builder拟用受控CaseA；复现synthetic fixture也可加载 | 必须独立审批digest/来源；本轮未查私有文件 | Mode2装载实际执行 | test fixture可synthetic | Mode1背景/结果mock | 否 | “运行显式本地case，来源另证” | “标记real就证明真实培养方案” |
| Curriculum Diff；curriculum模块 | 不计算，UI主要呈现预置任务，并非完整Diff | CurriculumCaseProvider内部匹配/投影实际执行；基础UI任务仍mock | 取决于case证据 | Mode1未执行 / Mode2执行 | 若case合成则合成派生 | Mode1 | 否 | “代码支持Diff；该请求按case计算” | “默认页面是刚算的真实差异” |
| MakeupTask；Provider.get_makeup_tasks | mock_data/makeup_tasks.json | API内部来自case；页面基础区仍mock聚合对象 | 源case条件性；不是所有任务都是待补课 | Mode2实际计算 | 合成case派生 | Mode1/UI基础区 | 否 | “状态含satisfied/required/manual，逐项来源” | “页面任务等于本次runtime任务” |
| CourseOffering；generator→acceptance→StoreProvider | mock_data/course_offerings.json | 本演示生成器合成五shard→既有Store验收→实际Provider | Mode1/演示Mode2均非真实学校供给 | 序列化/验收/Provider已实现 | Mode2明确synthetic；Mode1也是人工数据 | Mode1回放 | 否 | “合成供给、验收只证明完整性/一致性” | “full_semester/real枚举证明来源真实” |
| Preference；表单/buildRealPlanRequest | Mock偏好展示+用户编辑 | 请求中结构化表单输入，原样传Planner | 真实用户输入需具体录制证据；不是学校事实 | 收集/传递已实现，执行口径受限 | 测试/默认值人工 | Mode1默认 | 否 | “结构化输入，未保证全部约束执行” | “自然语言AI解析、偏好全部生效” |
| Planner；RestrictedPlannerProvider.plan | 不调用；JSON已有结果 | 实际时间检查/受限搜索/新增建议 | 运算真实性与输入来源分开 | Mode2执行 | 可用于合成输入 | Mode1结果回放 | 否 | “受限确定性Planner” | “全局最优/CP-SAT/ILP求解器” |
| Path Repair；find_alternative_sections | Mock changes预置，非现场求解 | 评估替代班，保留已有班并要求选择；唯一CLEAR required可新增 | 取决于输入，非执行选课 | 辅助检查实现；无自动已有班替换 | 输入可合成 | Mode1变化例子 | 非完整通用repair | “替代候选检查、人审选择、受限变更记录” | “自动按偏好/连堂密度调班” |
| PlanResult；MockAPI / orchestrator | plan_result.json回放 | actual Planner返回；risks当前返回[]，限制主要unresolved；changes可为新增 | Mode2实际计算结果，不是real来源证明 | 传输/显示皆真实代码；Mode1非现场计算 | Mode2结果可合成输入派生 | Mode1 | 否 | “回放结果/本次受限计算结果”分开 | “显示的Mock风险等级是Planner本次算出” |
| frontend；App.vue | 实际Vue，基础/结果Mock | 实际Vue；基础MakeupTask/CourseOffering/Preference仍Mock，只有结果换为POST输出 | 不能整页称Real | 已实现 | 后端输入可synthetic，基础区人工 | 两模式基础区均mock | 否 | “页面呈现；规划结果来源局部区分” | “切Mode2后整页真实” |
| API/runtime；mock.py/planning_runtime | Mock服务运行；未执行Provider/Planner | factory→真实类Provider→orchestrator，显式本地输入，逐请求校验 | 非实时学校联网证据 | 已实现 | 可跑synthetic | Mode1永久Mock | 否 | “实际API计算/本地runtime” | “200或无Mock头=学校真实E2E” |
| LLM | 无调用 | 无调用 | 不适用 | 未实现 | 不适用 | 不应伪造模型输出 | 模型能力未接入 | “模型理解/解释为后续方向” | “LLM自动分析此case” |
| RAG | 无检索管线 | 无检索管线 | 不适用 | 未实现 | 不适用 | 不适用 | 设计方向，非当前能力 | “可探索检索证据” | “已RAG增强/检索校规回答” |
| GraphRAG | 无图检索 | 无图检索 | 不适用 | 未实现 | 不适用 | 不适用 | 未来可能性，非实现 | “未接入GraphRAG” | “沿知识图谱推理并生成方案” |

关于“only CourseOffering synthetic”：只有具体Mode2确有已核验真实Curriculum provenance且与录制输入一致，才可有限表述“该段Curriculum经证明真实，供给合成”。不能用于默认Mode1或全合成E2E。Generator记录case_data_source/digest，是线索，不是完整真实来源证据。

## 3. AI claims分类（两PR逐类定位）

| 文案位置 / claim family | 分类 | 可用slide / 口述 | 禁用/最小改法 |
|---|---|---|---|
| PR51 README:3、DEMO_SCRIPT:3、STARTUP:91；“AI学业路径重构Agent系统”标题 | PARTIALLY IMPLEMENTED（产品方向+编排；非模型Agent） | “学业路径重构原型：固定工具编排已实现，模型能力待接入” | 不单独标题造成已实现AI推理印象；旁注当前模型未接入 |
| PR51 README:18、DEMO_SCRIPT:17/162；“AI负责理解/解析/协调/解释”“AI解释” | ARCHITECTURAL PLAN；当前LLM部分NOT IMPLEMENTED | “未来AI辅助理解与解释；当前规则/编排和结果文案已实现” | 改未来时态；不可当作本次运行分工 |
| PR51 README:76/ARCH:117；PlanningOrchestrator固定3Provider调用 | IMPLEMENTED NOW（fixed orchestration） | “固定工具编排，不生成业务结论” | “自主决策/多Agent协商/模型Tool Calling” |
| PR51 ARCH:165；Agent把结果解释成人话 | PARTIAL：有确定性提示/前端展示，没有生成式解释 | “前端呈现已有结果说明” | 删除暗示LLM生成解释 |
| PR51所有4份对外docs中LLM/RAG/GraphRAG | NOT IMPLEMENTED；没有找到声明其已上线的明确技术实现段，但标题未交代缺席 | 可加“LLM/RAG/GraphRAG当前未集成” | 不新增已实现AI功能承诺 |
| PR52三个OPC文档中模型理解/检索/自然语言偏好 | ARCHITECTURAL PLAN / NOT IMPLEMENTED，已有明确限制 | 保留限制；不要求赛前实现 | 不把未来段落变成当前slide实线 |
| PR52one-liner“AI…Agent原型” | PARTIAL，后文有边界但摘引时易丢 | 统一为下面canonical标题及一句当前边界 | 不能只摘AI标题去掉未接入说明 |
| PR52规则/固定编排/风险呈现事实 | IMPLEMENTED NOW，但Mode1为展示非计算 | 区分已实现能力与本次演示执行路径 | 别让演示脚本暗示默认Mock计算 |

Repo search无模型调用/检索实现证据。这里不是官方OPC资格裁决；官方是否强制运行中AI模型仍需负责人核对。不得靠更名满足规则，不要求临时补新模型功能。

## 4. Planner truth statement

**已实现确定性时间检查、受限组合可行性检查及替代教学班候选评估；当前Planner保留已有班，仅对required任务的唯一CLEAR候选提出新增建议，并保留未解决/人审事项。不自动按偏好换班、不执行学校选课，不是全局优化器或CP-SAT/ILP最优求解器。**

证据：provider.py:97-104为已有班返回selection_required而不是替换；185-193中changes为from_class=None的新增，risks=[]；_pending_non_time将激活Preference、容量、跨校区及先修口径留作manual_confirmation。section_repair辅助检查不等于当前API自动完成换班。

Allowed：restricted deterministic planner；constraint-aware planning（注明当前受限）；“确定性时间检查与受限修复候选”。Forbidden：自动平衡偏好、连堂密度优化、全约束已执行、全局最优、自动选课。空changes/risks仅表示无记录，不能说“偏好已经处理好/无风险”。

## 5. 两种模式的准确讲法

**Mode1**：本地FastAPI/Vue确实运行，GET mock读取提交JSON；不运行Curriculum/Planner，changes/risks为人工演示例子。StudentContext和结构化Preference可填写，不会把回放变成计算；专业信息和成绩文件选择不是fixed runtime参数。干净checkout可按指南准备依赖后启动，无学校凭据/私有case。

**Mode2**：POST plan实际运行CurriculumCaseProvider、StoreBackedCourseDataProvider、RestrictedPlannerProvider。需要显式本地可加载CaseA、绑定semester/SHA的accepted Store及前端开关；本演示供给由合成生成器生成。Builder真实CaseA路径需受控输入和来源证据，故不能由clean checkout复现那份私人材料；但全合成fixture可验证同代码链路，不能说代码本身不可复现。页面基础对象仍Mock，仅PlanResult来自本次计算。case data_source=real与端点Real名称不足以证明真实学校数据。

Partial-ready禁令不应靠手动补case路径绕过。已有已批准Curriculum可最终双复验而ready，但教学班仍synthetic/无真实handoff则level2_eligible=false。不要把Synthetic handoff改成non-synthetic，禁止把演示数据送入真实来源资格声明。示例或文档中的“启动计算”必须明确是合成/混合demo，非Real学校E2E。

## 6. 批准披露用语（按模式条件使用）

UI一句话：**当前为演示数据；Mock模式回放预置结果，计算模式执行实际代码，输入来源需逐项核验。**

Presenter两句：**默认页面回放Mock样例，未现场运行Planner；可选计算模式执行固定Provider和受限Planner，但页面基础数据仍Mock、教学班输入为合成快照，Curriculum来源以该次批准证据为准。我们区分实际代码与真实学校数据，未声称LLM/RAG/GraphRAG上线或Real LEVEL2/3完成。**

README paragraph：**本项目已实现文件读取/规则分析、固定Provider编排、受限时间检查、建议变化与未解决事项呈现。模式1从永久Mock接口回放提交的样例，不执行上游业务计算；模式2通过/api/v1/plan实际计算，使用显式本地CaseA与验收绑定Store，比赛教学班供给为Synthetic，页面基础区块仍来自Mock通道。真实Curriculum只在具体artifact来源批准且与消费字节一致时声明；可复现Synthetic E2E的Curriculum也为合成输入。ready证明Store与Curriculum输入复验，不证明真实学校来源；LEVEL2/3还须完整真实provenance及验收证据。当前未集成LLM、RAG或GraphRAG，不保证全局最优、全部偏好执行或选课成功。**

North背景可另写“历史记录显示North深分页异常，完整真实供给仍未完成”；不要在Mode1披露details里无条件写“本次其余链路正式执行”。DEMO标记只提供可见提示，不认证其他输入真实。

## 7. Cross-PR矛盾与PR51最小替换表

B1/B2/B3为merge前文字/provenance blocker；其余同次统一，不需改核心功能。

| 文件 / section / line（PR51） | 当前矛盾 | exact minimal replacement / action |
|---|---|---|
| DEMO_SCRIPT §3场景6:136-140，B1 | Mock预置变化被说成Planner此次按回避/连堂密度调班；声称“偏好真的进入求解” | 主讲人：“Mode1这里是人工构造的变更展示例子，不是本次Planner求解。当前Mode2会检查替代候选、保留已有班并要求选择；changes可能是唯一CLEAR required的新增记录，不保证自动调班。”评委看点改“展示变化字段及限制” |
| DEMO_SCRIPT 场景6:141，B1 | “空调整不代表偏好被忽略”暗示当前执行 | 替换：“空changes只表示没有变更记录；当前Preference已传入但执行口径未完整确认，须看unresolved，不保证满足。” |
| STARTUP §2.1.1:195-196，B2 | 已批准Curriculum⇒ready且LEVEL2，不检查synthetic CourseData | “已批准且最终复验通过的Curriculum可使双输入ready；教学班Synthetic时仍不具备真实LEVEL2资格。LEVEL2还须真实CourseData handoff/来源证据，禁止伪造。” |
| STARTUP §2.1.1:191-194，B2 | 手动补partial_ready env的case变量后直接Real启动 | “partial_ready仅CourseData准备，不得启动Real runtime。提供匹配的批准Curriculum provenance并重跑最终双复验；合成供给仅用于明确披露的本地计算demo，非真实来源晋级。” |
| README §5.3，B3 | Mode2基础数据写受控case+Store，实际UI基础区仍Mock | 分成“UI基础区：两模式皆Mock；Mode2后端运算输入：显式CaseA+accepted synthetic Store；只有结果为POST实时计算”。结果标签改“Actual API computation（代码执行，非学校数据认证）”说明 |
| README §5.1及§5.2/labels.ts:176-177，B3 | 无条件称培养分析/PathRepair正式执行，Mode1只是回放；“唯一披露面”忽略case来源 | “Mode1回放；Mode2执行实际代码。教学班合成；Curriculum须逐项证据。当前结果与基础区来源分别标注。”details也按模式分支或改通用条件文字，不称唯一披露面 |
| README:3/18、SCRIPT:3/17/162、ARCH:165 | AI原理分工被读作现有模型能力 | 加：“当前为固定工具编排原型，LLM/RAG/GraphRAG尚未集成；模型理解/生成解释为未来方向。”既有“AI负责…”改设计目标 |
| ARCH图例:84-93 | Case挂载位同时叫受控真实和Synthetic；蓝real混合执行与来源 | 蓝=实际执行代码；灰=外部本地输入（Case来源需证据）与合成供给分别节点；紫=Mock回放。两轴注明 |
| README §3风险解释；SCRIPT场景5 | 可能让Mock风险等级代表实际restrictedProvider计算 | “页面显示risks/unresolved；当前Provider主要输出unresolved，risks可为空；Mode1风险等级人工示例。”不称基于余量自动风险打分 |
| README §5.5/§10“没有真实artifact” | 私人CaseA真实前提与“从未处理真实材料”冲突；PR52另有文档记录真实Curriculum统计 | “本次可复现演示未处理真实全量CourseData；真实CaseA来自受控材料记录但本轮未独立核验。未证实Real LEVEL2/3。”保留LEVEL0实际达成/LEVEL1能力分别口径 |
| README §10 data_source=real | 将枚举“真实来源等级”与来源证明混同 | “该字段是来源声明/契约标记，不是认证；Synthetic输入可经形状正确的adapter返回real标签，须保留外部披露和完整provenance。”不改变Schema |
| OPC_PRESENTATION_PACK 一句话/30秒/示例脚本（PR52） | 正式AI标题摘引有歧义；只写未做脚本已过时 | 使用下方canonical；历史素材缺口仅main c75b6da，PR51已提供脚本/入口但话术待修 |
| OPC_JUDGE_QA PathRepair等（PR52） | “受限换班建议”可误读为自动执行 | 明确已有班替代是候选/人选；当前变化可能仅新增；RAG未上线限制保留 |
| OPC_SUBMISSION_READINESS_AUDIT库存/P0（PR52） | README、脚本、图、启动/恢复材料现在PR51已有 | 不再作为缺失P0；标记“PR51已具备待文字修正/待merge”；剩余库存见下表 |

不要为了通过文字审计实现偏好求解/LLM/新的API，也不要删除真实限制。让讲稿追随代码，而非代码追随夸大的讲稿。

## 8. Canonical定位：所有材料一致使用

Title：**学航·转衔：面向转专业学生的学业路径重构原型（固定工具编排，AI增强待接入）。**

30秒：**转专业后的难题，是把旧专业已修、新专业要求和当前课表对上。学航·转衔用有出处的输入规则区分历史缺口与待确认认定，再用受限确定性检查给出候选和建议变化。默认演示回放Mock，计算模式运行实际代码并逐项披露输入来源；模型理解和检索尚未上线，正式认定与选课仍由人和学校完成。**

Technical paragraph：**系统以CurriculumCaseProvider、StoreBackedCourseDataProvider和RestrictedPlannerProvider组成固定编排，按显式输入进行课程匹配/历史范围投影、时间约束检查、替代候选评估与受限新增建议，返回PlanResult及未解决事项。Mode1永久Mock回放与Mode2实际API计算分离，后者的合成供给不能因验收或real枚举变为真实学校数据。学校来源由绑定具体artifact的批准证据另行证明；LLM/RAG/GraphRAG为未来增强。未确认认定、偏好、容量、通勤及先修口径保留人审，不认证全局最优或自动选课。**

## 9. 更新artifact与提交计划

以下按PR51 proposed tree判断，**已有文字材料不再算缺失**；仍非已提交/已批准/已录像。

| artifact | current inventory | remaining |
|---|---|---|
| root README | HAVE PR51 README312行 | B1/B2/B3与AI边界统一 |
| demo script | HAVE PR51八场景 | 改现场计算/偏好与自动换班承诺，做计时彩排 |
| architecture figure | HAVE Mermaid/技术图 | 来源两轴修正；不是slides成品 |
| startup | HAVE指南 | partial/LEVEL2改法，不绕过gate |
| recovery | HAVE DEMO_RECOVERY | 仅标来源诚实的回退/回放；与修正模式说明交叉核对 |
| screenshots | MISSING tracked成品 | 脱敏、准确标来源，不把代码截图当UI成品 |
| slides | MISSING成品 | reviewer已有提纲不等于已制作 |
| demo video | MISSING | 录制+备份+来源/指标核对 |
| official rules check | MISSING核对证据 | 主办方AI要求、资格、时长、格式、真实deadline |
| team information | PARTIAL模块职责 | 成员/角色/资质/授权由owner填写 |
| submission form content | PARTIAL reviewer草稿 | 逐portal字段核对/owner批准，不假设必填项 |
| user rehearsal | MISSING录制/计时证据 | 两模式选实际可跑模式，至少完整计时彩排 |

P0 before submission（10/08之前为用户工作目标，不推定官方deadline）：

1. small：B1/B2/B3文字及页面披露修正，canonical逐文档一致；不加算法。
2. small：owner核对官方规则，特别是已运行模型是否硬条件；缺条件则如实评估资格。
3. medium：固定Mode1或已受控可运行Mode2，完整彩排/截图/slides/视频与备份；不可把Mock画面剪成实时求解。
4. small：团队信息、portal内容、隐私、链接/时长/格式最终核对。

P1：精简999行恢复文档为1页现场速查；Q&A演练；Case统计口径与输入digest证据卡。P2：字幕/版式/封面，不新增核心能力。

## 10. 独立证据（非全量回归）

PR51 actual TestClient，无dependency overrides。factory wrapper只计数并调用原函数：

- GET /api/v1/mock/demo→200，X-Data-Source mock；3 factory调用次数0；返回plan_result精确等于committed mock_data/plan_result.json。
- 配置test_synthetic_production_e2e的全合成fixture；POST /api/v1/plan→200 partially_feasible；3 factory都调用；验证实际代码执行并不能证明输入真实。
- Actual readiness CLI、合成capture +匹配已批准测试Curriculum证据、不提供真实CourseData handoff→exit0/statusready，level2_eligible=false，blocker real_source_handoff_missing。证明STARTUP:195-196的LEVEL2暗示不成立。metadata仅测试gate，不声称真正人工批准合成材料为真实。
- 只读provider.py确认未执行Preference/自动已有班换班，risks=[]；MockJSON中避免时段/连堂变化是预置例子。

没有重复Codex1 full backend/frontend regression，没有学校访问/真实私有case获取/生产修改/merge。PR51需上述最小修正后再次作文字闭环；PR52库存已随本报告更新，历史main审计仍保留。
