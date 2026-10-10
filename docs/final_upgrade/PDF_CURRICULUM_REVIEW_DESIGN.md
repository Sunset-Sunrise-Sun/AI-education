# Phase B 设计：课程分类候选、组长人工审核与审核导出

> 分支：`feature/pdf-curriculum-review`（基线 `feature/final-upgrade` = `3a56422`）
> 本文件是**先交付的设计**（任务书 §七"先交付数据模型、证据提取方案和界面设计，再编写代码"）。
> ⛔ 本文件不含任何真实材料内容；引用的行号/文字均为**结构示例**，真实数据留在仓库外。

---

## 0. 读前必读：两处事实纠正

| 任务书陈述 | 仓库事实 |
| --- | --- |
| `PROJECT_CONTEXT.md` | ⛔ **仓库内不存在该文件**（全库搜索无果）。最接近的是 `AGENTS.md` + `docs/status/*.md` |
| `DEVELOPMENT_RULES.md` | ✅ 存在，但在 **`docs/DEVELOPMENT_RULES.md`**，⛔ 不在仓库根目录 |
| 最新 `feature/final-upgrade` = `3a56422` | ✅ 已核对：`3a56422` "Merge PR #75: real-PDF curriculum import Phase A" |
| PR #75 已合并 | ✅ 已核对（远端 `feature/final-upgrade` 头部即该合并提交） |

---

## 1. 数据模型

⛔ **不新增公共 Schema**：以下全部是 **Curriculum 模块内部 + API 模块私有包络**的对象。
`/schemas/**` 与 `/docs/interfaces/**` **一字未改**。

### 1.1 证据对象 `CategoryEvidence`（模块内部，冻结 dataclass）

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `kind` | `str` | 证据种类：`credit_requirement`（类别学分要求表）/ `practice_appendix`（实践教学附表）/ `section_header`（明细表小节标题行） |
| `category_code` | `str \| None` | 文档里**原文**的类别代号（`公必` / `专必` / `专选` / `公选` / `荣誉课程`） |
| `requirement` | `RequirementKind` | 由**声明式映射**翻译出的归一化类别（⛔ 不在代码里写死中文→枚举的分支） |
| `minimum_credit` | `float \| None` | 该类别在文档中给出的**最低学分要求原文数字**（仅类别级证据有） |
| `source_record` | `str` | 可追溯定位，与既有解析一致：`page:{n}!table:{t}!row:{i}` |
| `raw_text` | `str` | **原文证据**（该行/该格的原始文字，⛔ 不改写、⛔ 不翻译） |
| `table_purpose` | `str` | 该表在 profile 里的用途声明（见 §2） |

**硬约束**：`raw_text` 必须是**文档里真实存在的文字**。⛔ 不允许拼接、⛔ 不允许生成描述性文字。

### 1.2 候选分类 `CategoryCandidate`

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `course_id` | `str` | 课程编码 |
| `source_record` | `str` | 该课程行在 PDF 里的定位 |
| `proposed_requirement` | `RequirementKind` | 候选类别（`required` / `elective` / `unknown`） |
| `proposed_category_code` | `str \| None` | 候选的**原文**类别代号（如 `专必`） |
| `evidence` | `tuple[CategoryEvidence, ...]` | 支撑证据（可多条） |
| `status` | `str` | `single_source`（单一来源命中）/ `conflicting`（来源冲突）/ `no_evidence`（无证据） |
| `evidence_complete` | `bool` | 是否已有**决定性命中**的证据 |

### 1.3 审核状态 `ReviewDecision`（草稿，⛔ 不是批准）

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `course_id` | `str` | 课程编码 |
| `source_record` | `str` | 目标行定位（**主键**，不是 `course_id`——同一编码可能多行） |
| `action` | `str` | `confirm`（确认候选）/ `override`（人工改为其它类别）/ `defer`（暂不确认） |
| `requirement` | `RequirementKind \| None` | `override` 时必填的人工结论 |
| `note` | `str \| None` | 可选备注（⛔ 不写自由文本到日志） |

### 1.4 审核会话 `ReviewSession`（服务端内存，见 §5.3）

`review_id`（随机、不可猜测）+ `source_sha256` + 原始解析快照 + 决策表 + 未解决问题清单。

---

## 2. 证据提取方案

### 2.1 为什么需要新的 profile 声明

现有 `pdf_profiles.py` 只声明了**课程明细表**（用于取课程编码/名称/学分/学期）。
类别证据在**另外两类表**里，因此需要为它们新增声明，但⛔ **不能**让它们被当成课程导入。

⇒ 在 profile 里新增一个**表用途**字段 `table_purpose`：

| `table_purpose` | 用途 | 是否产出课程行 |
| --- | --- | --- |
| `course_detail` | 课程明细（现有行为） | ✅ 产出 |
| `category_evidence` | 类别学分要求表 / 实践教学附表 / 类别列 | ⛔ **不产出课程行**，只产出证据 |

⚠️ **键名待架构确认**：这是本轮新增的模块内部字段（⛔ 不进 `/schemas/**`）。
若架构审核认为应改名或换机制，改动点只在 `pdf_profiles.py` + `curriculum_pdf_evidence.py`。

### 2.2 三类证据来源（均已用真实文件核实存在）

| 来源 | 真实形态（结构示例） | 能给出什么 |
| --- | --- | --- |
| **类别学分要求表** | 6 列表：`课程类别/课程细类` \| `细类学分要求` \| `类别学分要求` \| … ；行如 `公必` / `专必` / `专选` / `公选` | 每个类别的**最低学分原文** + 类别代号 |
| **实践教学附表** | 8 列表：`序号` \| `课程编码` \| `实践教学课程名称` \| **`课程类别`** \| `开课学期` \| `课程类型` \| … | **课程编码 → 类别代号**（课程级证据） |
| **明细表小节标题行** | 明细表首列的合并单元格，仅在小节首行有值（如 `专业选修课模块` / `本研提升课`） | 该行**之后**的课程属于该小节 ⇒ 可推出必修/选修 |

### 2.3 归一化：声明式映射，⛔ 不在代码里写中文分支

```json
"category_values": {
  "公必": "required",
  "专必": "required",
  "专选": "elective",
  "公选": "elective"
}
```

- ⛔ 代码里**不存在** `if code == "公必"` 这类分支；未在映射里出现的代号 ⇒ `UNKNOWN` + 标记待确认；
- ⛔ **章节标题**（如 `专业选修课模块`）也走**同一张**声明表，
  而不是靠 `"选修" in title` 这种子串匹配（后者属于猜测，且会被 `选修课模块` 之类措辞骗过）。

### 2.4 判定规则（**这是本轮的算法核心**）

```text
证据 = 课程级证据（附表精确匹配课程编码） ∪ 小节级证据（该行所属小节标题的声明映射）

① 课程级命中且唯一（同一编码只有一种代号，且与小节证据不冲突）
      ⇒ 候选 = 该代号对应类别，status = single_source，evidence_complete = true
② 课程级出现 ≥2 种不同代号            ⇒ 候选 = UNKNOWN，status = conflicting
③ 课程级与小节级给出**不同**类别      ⇒ 候选 = UNKNOWN，status = conflicting
④ 只有小节级证据                      ⇒ 候选 = 小节推导类别，status = single_source
   ⚠️ 但 evidence_complete = false（小节是**范围**证据，不是该课程的编码级证据）
⑤ 两类证据都没有                      ⇒ 候选 = UNKNOWN，status = no_evidence
```

**硬约束**：

- ⛔ 任何一对多 / 冲突**一律不自动取舍**，交人工（对应任务书 §三.3）；
- ⛔ 候选**永不**写成 `verification.verified=true`，⛔ 永不进 `group_records`；
- ⛔ 跨表关联**只**用于生成审核建议，不代表学校已认定课程等价或学分（任务书 §三注）；
- ⛔ 组最低学分**只**从"类别学分要求表"原文取，⛔ 绝不用成员学分求和（沿用既有护栏）。

### 2.5 无证据的情形必须如实统计

真实文件的实测覆盖率（本轮已核）：
遥感明细 77 个编码中 44 个有附表类别证据；网络空间安全 89 个中 34 个。
⇒ **必然存在大量 `no_evidence` 课程**。任务书 §八明确：
> 如果存在没有来源证据的课程，不得宣称人工审核已完成。

因此未解决问题清单**必须逐条列出** `no_evidence` 课程，且导出记录里带上该计数。

---

## 3. 界面设计（在现有"培养方案导入"页之后）

### 3.1 信息架构

```text
① 上传与解析（已有，PR #75）
      ↓ 解析完成
② 分类候选（本轮新增，只读展示）
      每门课一行：课程编码 | 课程名称 | 学分 | 学期 | 候选类别 | 证据 | 状态
      证据展开：来源定位 + 原文文字 + 证据种类
      ↓
③ 组长逐条审核（本轮新增）
      每条：确认 / 改为必修 / 改为选修 / 暂不确认（+ 可选备注）
      顶部：审核进度（已确认 x / 待确认 y / 冲突 z / 无证据 w）
      ↓
④ 导出
      审核结果 JSON + 未解决问题清单（文本）—— **草稿**，⛔ 不是批准件
```

### 3.2 分区（⛔ 全部只读或草稿操作，无"批准"按钮）

| 分区 | 内容 | 硬边界 |
| --- | --- | --- |
| **课程列表** | 编码 / 名称 / 学分 / 学期 / 候选类别 / 状态 | 名称保留原文（中英双行） |
| **证据详情** | 每条证据的 `来源定位 + 原文` | ⛔ 不出现"课程等价""学分认定"字样 |
| **待确认：冲突证据** | `conflicting` 逐条列出（含全部冲突来源） | ⛔ 不预选任何一个 |
| **待确认：无证据** | `no_evidence` 逐条列出 | 显示"文档中未找到该课程的分类依据" |
| **重复课程编码** | 单独列出，**每条各自一行** | ⛔ 不合并、⛔ 不自动去重（沿用 PR #75 结论） |
| **模块标题行** | 单独列出，标注"这不是课程" | ⛔ 不可被确认为课程 |
| **课程组学分要求** | 类别 + 最低学分 + **原文依据**（定位 + 原文） | ⛔ 解析器不产出 `group_records`；此处只展示原文 |
| **审核进度** | 已确认 / 改为必修 / 改为选修 / 暂不确认 / 未处理 | — |
| **导出** | 审核结果 JSON、未解决问题清单 | 绑定 `source_sha256` |

### 3.3 非技术可用性（任务书 §四末句）

- 组长**只做点选**，⛔ 不需要看/改 JSON；
- 每条候选旁直接显示"这句是从 PDF 第几页第几张表第几行来的、原文是什么"；
- 所有类别代号**同时显示原文与归一化结果**（如 `专必 → 必修`），避免术语误解；
- 冲突项显式写出"两处依据不一致，已保留双方，请人工裁定"。

---

## 4. 安全与权限设计（任务书 §五逐条对应）

| 要求 | 设计 |
| --- | --- |
| 1 前端"确认"只形成**草稿** | 决策写入服务端会话草稿；⛔ 不触碰 `APP_TRUST_ANCHOR_PATH` |
| 2 未批准不得标已核验 | 导出记录恒带 `verification.verified=false`、`complete=false`、`conclusion=pending_group_lead_review` |
| 3 绑定原始 PDF SHA-256 | `ReviewSession.source_sha256` 由**服务端**在解析时记录；导出必带 |
| 4 文件变化旧结果不适用 | 提交决策时服务端**比对 SHA-256**；不一致 ⇒ `review_source_mismatch` 拒绝；另提供 `POST .../rebase` 显式作废并重开 |
| 5 保留 `verified=false` / `complete=false` | 硬编码，⛔ 函数签名里没有开关（沿用既有做法） |
| 6 ⛔ Agent 不得代替组长确认 | 代码里**不存在**任何自动填 `decision` 的路径；测试断言初始决策表为空 |
| 7 ⛔ 候选不得交给 Planner | 审核模块**不 import** `app.planner` / `matching.py`；候选只存在于审核会话；测试断言 |
| 8 ⛔ 真实材料/审核记录/锚点不进 Git | 审核记录由用户**下载**，服务端默认**不落盘**；`.gitignore` 兜底 |

### 4.1 为什么服务端持有会话（而不是前端回传 JSON）

若由前端回传"课程 + 证据 + 决策"的整包，客户端就能**伪造证据**或**篡改 SHA-256**。
因此：解析时服务端留存快照，客户端只提交 **`review_id` + 逐条 `decision`**，
证据与 SHA-256 **永远来自服务端**。⛔ 这也杜绝了"仅凭用户输入决定数据真实性"。

---

## 5. 接口设计（模块内私有包络，⛔ 不动公共契约）

> ⚠️ **这是本轮唯一需要架构审核的接口面**。若架构审核认为应与其他审核流程合并，
> 本模块的 4 条路由可整体替换，改动点集中在 `app/api/curriculum_review.py`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/api/v1/curriculum-import/parse-pdf` | **已存在**，本轮在其响应上**追加** `review` 段（`review_id` + 候选 + 统计）。⛔ 不改已有字段语义 |
| `GET` | `/api/v1/curriculum-review/{review_id}` | 取当前审核状态（候选 + 决策 + 进度） |
| `POST` | `/api/v1/curriculum-review/{review_id}/decisions` | 提交/更新决策（带 `source_sha256`） |
| `GET` | `/api/v1/curriculum-review/{review_id}/export` | 导出审核记录 + 未解决问题清单 |

### 5.1 兼容性

- `parse-pdf` **只增不改**：既有字段（`source_id` / `draft` / `report` / `source`）语义一字未改；
- 前端在未启用审核功能时行为不变；
- ⛔ `/schemas/**`、`/docs/interfaces/**`、`matching.py`、`planner` 均未改。

### 5.2 路由白名单

新路由必须登记到既有白名单测试
（`tests/test_integration_orchestrator.py::test_real_plan_endpoint_is_the_only_new_integration_api`）。

### 5.3 会话存储与生命周期

- 进程内存 + TTL（默认 2 小时，可配置）；⛔ **默认不落盘**；
- 超过 TTL / 不存在 ⇒ `review_not_found`（⛔ 不静默新建）；
- 显式 `rebase` 才会作废旧决策。

---

## 6. 验收映射（任务书 §七）

| 验收项 | 落点 |
| --- | --- |
| 两份真实 PDF 的候选分类 | `test_curriculum_pdf_evidence.py`（真实文件存在时全跑，CI 上 skip） |
| 候选与原文证据一致性 | 断言 `raw_text` 能在 PDF 该定位处**逐字找到** |
| 无证据保持 UNKNOWN | `no_evidence` 分支 + 计数断言 |
| 冲突证据不自动取舍 | 构造冲突夹具，断言 `UNKNOWN` + `conflicting` + 双方证据都在 |
| 组长确认/修改/拒绝/暂缓 | 决策 API 测试四种 action + 非法 action 拒绝 |
| 重复课程编码处理 | 断言各自独立决策、⛔ 不存在合并路径 |
| 课程组最低学分原文证据 | 断言 `minimum_credit` 与该定位原文一致 |
| 审核结果绑定 SHA-256 | 导出断言 + 篡改后提交被拒 |
| 篡改与重复审核 | 改字节 ⇒ `review_source_mismatch`；重复提交 ⇒ 覆盖而不是追加冲突 |
| 未审核数据无法进入正式 Planner | 结构断言：审核模块不 import planner；草稿 `verified=false` |
| Mock / DOCX 无回归 | 既有全量回归 |

---

## 7. 待架构确认事项

1. **`table_purpose` 字段名与语义**（§2.1）是否可接受为模块内部声明？
2. **`/api/v1/curriculum-review/**` 三条新路由**是否符合项目接口规划（§5）？
3. **审核会话保存在内存 + TTL**（不落盘）是否满足"审核记录"的留存预期（§5.3）？
   - 若需要跨重启留存，则需引入 `APP_CURRICULUM_REVIEW_DIR`（仓库外路径）——
     ⛔ 本轮默认不启用，避免误写敏感数据。
4. **`category_values` 映射**是否应改为"由人填写的外部映射文件"，
   以避免在模块内出现学校类别代号（§2.3）？

⛔ 在以上确认前，本模块**不接入**任何正式规划路径，也不写批准锚点。
