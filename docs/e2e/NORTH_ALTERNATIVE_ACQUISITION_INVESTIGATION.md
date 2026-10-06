# North 替代采集路径 — 离线架构调查（docs-only）

> 基线：`main` @ `c75b6da`（PR #48 合并后）。诊断证据：**PR #49**
> `docs/e2e/evidence/NORTH_DIAGNOSTIC_2026-10-06.md`（分支 `docs/north-diagnostic-20261006`）。
> ⛔ 本轮**未访问任何真实学校网络、未发任何请求、未使用任何凭据**。
> ⛔ **无生产代码改动**；本文只是调查记录与**待裁定**的设计提案。

## 0. 已知事实（只引用证据，⛔ 不推断）

```text
F1  North 过滤分页（openingSchoolNumber=5062202, pageSize=200, pageNo=2）
    在**同一已授权会话内两次**返回 HTTP 600 / 业务码 50015000    ← PR #49 O2 + O3
F2  ⛔ 这不是限流证据：没有 429、没有 Retry-After、没有服务端说明   ← PR #49 明示
F3  North **第 1 页从未被请求过**：诊断脚本把 baseline 第 1 页当成等价物，
    而两者**不等价**（baseline 不带 openingSchoolNumber）        ← PR #49「Important diagnostic note」
F4  历史（**未过滤**）深分页：offset ≥ 6500 稳定 600，且与 pageSize 无关
    （pageSize=100/pageNo=66 与 pageSize=50/pageNo=131 同为 offset 6500 → 600） ← course_data.md:1032-1043
F5  人工实测的 pacing 包络：pageSize=50 + 30 s 间隔，**连续 7 次成功后第 8 次**出现 600
    （⛔ 文档明确：不声称是学校公开阈值，不据此推断服务端限流实现）   ← course_data.md:1249-1252
F6  single-approved-campus 路径的批次上限 = **7**（依据 F5 的包络；ordinary/五校区仍为 5）
    ⇒ 第 8 个请求必须落在冷却之后                              ← collector.js:1591 注释
F7  已批准传输的**请求参数只有** `yearTerm` + 可选 `openingSchoolNumber`；
    `pageSize` 固定 200 且不可由调用方传入                        ← collector.js:795-801, 1110+
F8  仓库内**唯一**的 SYSU 端点 = `POST /jwxt/schedule/agg/schoolOpeningCoursesSchedule/querySchoolOpeningCourses`
    （全仓库 grep 只此一条 `/jwxt/...` 路径）                     ← collector.js:87 等
F9  recon 记录的请求字段集合 = `pageNo` / `pageSize` / `total` / `param.yearTerm` / `param.courseNumber`
    （`param.courseNumber = CSE202` 曾真实使用，返回 total=2）      ← SYSU_COURSE_OFFERING_RECON.md §2
F10 校区 shard 维度 = `param.openingSchoolNumber`（UI 取证）；五校区号码与 `north operational:false`
    都在源码常量里                                                ← course_data.md:1047, collector.js 校区表
F11 `openingSchoolName`（响应**行字段**）与 `campus` 的关系**语义待人工确认**；
    代码明确**不做** `openingSchoolName → campus` 映射             ← RECON §4, course_data/__init__.py:84-85
F12 「**选课**」与「**全校开设课程**」是**两个独立模块**；本采集器只用后者   ← DATA_SOURCE_REGISTRY.md:366, :50x
F13 验收规则（⛔ 不得放宽）：exact five-shard；Σ shard reported_total == baseline 且
    baseline_before == baseline_after；每 shard 必须 complete；每 shard 与已批准 inventory
    raw_bundle_sha256、campus acceptance 记录逐项一致              ← full_semester_acceptance.py:41-90
```

### 0.1 由 F1–F6 得到的一个**关键推论**

North 的失败发生在**该会话第 2 个请求**上（O1 baseline → O2 North p2），
**远早于** F5/F6 的 7-请求包络 ⇒ **不能用"请求批次/节奏"解释这次 North 失败**。
⚠️ 唯一未知：PR #49 未记录该会话在 O1 之前是否已有其它请求（缺口，见 §5 R1）。

## 1. 现有采集面清单（只列有证据的）

| # | surface / endpoint | known parameters | pagination behavior | expected coverage | 能否覆盖 North | evidence source | risk / unknown |
|---|---|---|---|---|---|---|---|
| S1 | `POST /jwxt/schedule/agg/schoolOpeningCoursesSchedule/querySchoolOpeningCourses`（「全校开设课程」模块） | `pageNo` / `pageSize`(固定200) / `total` / `param.yearTerm` / `param.openingSchoolNumber` | 单页 200；`pageNo` 从 1 递增；**过滤**深分页在 North 于 offset 200 即 600（F1）；**未过滤**深分页 offset ≥6500 稳定 600（F4） | 全学期全部开课教学班（教学班粒度） | ⚠️ 需五 shard 全成功；North 目前**不能** | collector.js:83-93,795-801；course_data.md:1032-1047 | North 600 成因未知；失败是"页内"还是"校区级"未判定（F3 缺口） |
| S2 | 同 S1 + `param.courseNumber=<单课程号>`（recon 曾真实使用） | 追加 `param.courseNumber` | 记录显示单课程结果集很小（total=2）⇒ 单页可返回；**但**该参数**未在已批准传输中实现** | 单门课程的（过滤后）全部教学班 | ⚠️ 单课程可用性**未复测**；**穷尽性无法证明**（见 §2.2） | RECON §2（`courseNumber=CSE202` → total=2） | 需要新增传输代码（⛔ 未实现）；且需要"完整 North 课程号清单"才能穷尽 |
| S3 | 五校区编排 `collectSharded()` / 单校区 `collectApprovedShard()` | `semester` / `maxPages` / `delayMs`（⛔ 不能传 `openingSchoolNumber` / `pageSize`） | 逐页串行 + 全局 pacing（30 s、batch 5/7 + 5 min 冷却） | 各校区完整 shard | ⛔ North 被 `operational:false` 拒绝 | collector.js 校区表, 1591 | 若 North 恢复，这是**唯一**已批准路径 |
| S4 | `diagnoseSchedulePresence()` / `diagnoseMissingScheduleCorrelation()` | `semester`（固定 pageNo=1, pageSize=200） | **只请求第 1 页一次**，不传 campus | 仅第 1 页结构/相关性聚合 | ⛔ 不产出数据；⛔ 不能覆盖 North | collector.js:1401-1404 | 仅诊断 |
| S5 | 「**选课**」模块（UI 内另一个独立模块） | **仓库内无任何端点/参数证据** | 未知 | 未知（语义上很可能是"选课范围"子集，而非全部开课） | ⛔ 不支持（需要新的授权 recon） | registry:366（只说明"是两个独立模块"） | 需新 recon；即便有端点也**不能**假定等价于"全校开设课程"全集 |
| S6 | 导出 / 批量 / 报表 / 打印 / 非分页后端端点 | — | — | — | ⛔ **不存在**：全仓库只有 S1 一个 `/jwxt/...` 端点；`导出/csv/excel` 的命中全部来自 Gate F 的**已修课程 XLSX 上传**与 Curriculum 的 DOCX/XLSX **读取器**（与教务采集无关） | 全仓库 grep（见 §4） | — |
| S7 | 响应行字段 `openingSchoolName` 作为"校区归属" | — | — | 若语义被批准，可从**未过滤**流里按校区切分 | ⛔ 当前**不可用**：语义待人工确认，代码明确不做该映射（F11） | RECON §4；`course_data/__init__.py:84-85` | 若将来由**书面证据**确认，可成为独立（但仍是"另一条需要 review 的路径"） |

## 2. Partition 策略评估

### 2.1 维度清单（只评估有证据的维度）

| 维度 | 服务器是否支持 | 穷尽性（A） | 互斥/可去重（B） | 结论 |
|---|---|---|---|---|
| `openingSchoolNumber`（校区） | ✅ 已批准（F10） | ✅ 五校区为 exact 集合（已批准常量） | ✅ 各 shard 由服务器过滤；合并按 canonical identity `(semester, course_id, class_id)` 去重并检测冲突 | **维度本身合格**，但 **North 这个 partition 内部无法取满**（page 2 → 600） |
| `param.courseNumber`（单课程号） | ⚠️ 有 recon 证据（F9），但**未在已批准传输实现** | ❌ **无法证明**：需要一个"完整 North 课程号清单"，而所有可枚举该清单的路径本身都受同一个 600 影响（见 §2.2） | ✅ 按课程号天然互斥；跨分区重复行仍可用 canonical identity 检测 | **B 类候选**（需新 acceptance 类型 + 新传输），当前**不可产出** |
| 开课单位 / 课程类别 / 年级 / 课程号区间 / 教学单位 / 课程类型 / 关键词 | ❌ **无任何证据**（F9 的字段清单里没有这些） | ❌ | ❌ | **D 拒绝**（⛔ 不推断未支持的端点/参数） |
| 响应行 `openingSchoolName` | 不是请求参数；且语义待确认（F11） | ❌ | ❌ | **D 拒绝**（属推断） |
| 更小 `pageSize`（100/50/…） | ✅ 参数存在，但 `pageSize` 被已批准传输**锁定为 200**（F7） | ❌ **不构成完整性证明**：F4 已证明失败是 **offset 驱动**、与 pageSize 无关；换 pageSize 只是把同一个 offset 边界换一个页码 | — | **C 诊断/传输 workaround**（⛔ 不是完整性方案），且需独立的有界分页完整性证明 |

### 2.2 为什么 `param.courseNumber` 分区**目前**不能证明穷尽

要让"按课程号分区"成为**完整性**方案，需要 `P = {p1..pk}` 满足：∪P == North 全集。候选来源：

```text
(a) North 过滤查询自己分页枚举课程号  → ⛔ 正是失败的那条路径（page 2 → 600）
(b) 未过滤流（所有校区）分页枚举课程号 → ⚠️ 也**不完整**：未过滤深分页 offset ≥ 6500 稳定 600
    （F4），而当前 total ≈ 6875 ⇒ 最后约 375 行不可达 ⇒ 无法保证枚举到全部 North 课程号
(c) 独立的人工/官方 North 课程清单      → ❌ 仓库内**不存在**这样的已批准清单
```

⇒ 三个来源都不成立 ⇒ **A（穷尽）无法独立证明** ⇒ 该分区**当前不可接受**用于 production
full-semester acceptance（符合本任务 §2/§6 的"不能证明即拒绝"）。

此外：即便清单存在，逐课程请求的**请求数**会达到数百/上千次，与"⛔ 不做高频探测"和
既有 pacing（30 s + batch 冷却）直接冲突 ⇒ 运营上也不可接受。

### 2.3 `pageSize` 变小为什么仍然不行（正式说明）

```text
F4 的证据表明：(未过滤) 失败边界是 **offset ≥ 6500**，与 pageSize 无关。
North 的失败在 offset 200（F1），比 6500 低得多 ⇒ 机制不同、成因未知。
无论哪种机制，"换更小 pageSize 能取到 page 2 之后的行"都只是一个**假设**；
假设成立也只能说明"某些 offset 可取"，**不能证明**覆盖了 North 全集的每一行
（尤其无法排除"某些行在服务端任何分页组合下都不可达"）。
⇒ 只能作为 **transport workaround 假设**记录，⛔ 不能当作完整性方案。
```

## 3. Export / bulk 路径（§4 专用检查）

```text
grep 结果：仓库内 `/jwxt/...` 端点只有 1 条（S1）。
`export|bulk|download|csv|xlsx|excel|report|print` 的全部命中：
  - Gate F `POST /api/v1/completed-courses/import`（**上传** .xlsx 的本地摄取，与教务无关）
  - 本地 Curriculum 读取器（DOCX / XLSX）与 CLI（读取仓库外的私有文件）
  - `matching.py` 的 "Export unambiguous ... entries"（内部对象转换，不是网络端点）
⇒ 结论：**不存在**任何"导出 / 批量 / 报表 / 非分页"的教务采集端点（⛔ 未调用任何端点）。
```

## 4. 备选过滤路径（§5 专用检查）

```text
- 多个 openingSchoolNumber：⛔ 无证据支持数组/多值（recon 与 collector 都是**单值**）
- 父子机构过滤 / department 维度：⛔ 无证据（F9 字段清单里没有）
- 「选课」模块（独立 UI 模块）：⛔ 仓库内无端点/参数证据；且**不能假定**它等价于
  「全校开设课程」全集（F12）⇒ 需要新的授权 recon 才能评估
- campus vs openingSchool：⚠️ **不是同一个概念**：`openingSchoolNumber` 是请求侧的
  "开课校区号"（已批准）；响应侧 `openingSchoolName` 的语义**待人工确认**（F11）
  ⇒ ⛔ 不得用响应字段做校区归属推断
```

## 5. 完整性模型（对每个候选的正式要求）

对任何候选分区方案，生产 full-semester acceptance 需要**同时**满足：

```text
C1  stable baseline：baseline_before == baseline_after（当次窗口内）
C2  每个 partition loaded_count == reported_total（各自 complete）
C3  所有 partition scope 都已批准、号码来自常量（⛔ 不接受调用方自报 scope）
C4  每个 raw artifact digest 绑进 inventory，并与 campus acceptance 记录逐项一致
C5  重复行用 canonical offering identity (semester, course_id, class_id) 对账，
    冲突即 fail closed（⛔ 不静默取第一条）
C6  合并后的唯一行数等于一个**独立论证**的 North total，
    **或** 分区构造本身在形式上穷尽（不需要外部 total）
```

当前评估：

```text
校区维度（S1/S3）        C1 ✅ · C2 ⚠️（North 无法取满）· C3 ✅ · C4 ✅ · C5 ✅ · C6 ❌（North 端不可证）
课程号维度（S2）         C1 ✅ · C2 ⚠️（未复测）· C3 ❌（新 scope 未批准）· C4 ⚠️（需新 transport 产出 artifact）
                         · C5 ✅ · C6 ❌（无法证明穷尽，§2.2）
pageSize workaround 变体  C6 ❌（§2.3）
其它维度                  ❌ 无证据（D）
⇒ **当前没有任何候选能同时满足 C1–C6** ⇒ 不能产出真实 full-semester acceptance。
```

## 6. 分类（A/B/C/D）

| 候选 | 分类 | 理由 |
|---|---|---|
| North 校区过滤分页（现状路径） | **D（当前不可用）** | partition 内部取不满（F1）；North 保持 suspended |
| `param.courseNumber` 逐课程分区 + 新 acceptance 类型 | **B（需新显式 acceptance 类型 + Architecture Decision）** | 不削弱信任模型（仍要求 inventory / digest / identity 去重），但**需要**：① 已批准传输支持 `param.courseNumber`；② 一份**独立批准**的完整 North 课程号清单（目前不存在）；③ 新的 North-partition acceptance manifest 类型 |
| 更小 pageSize（100/50/…） | **C（诊断/传输 workaround）** | 可能绕开某个 offset 边界，但**不可能**单独证明完整性 |
| 响应字段 `openingSchoolName` 做校区归属 | **D（拒绝）** | 语义待确认（F11）；用它会变成推断 |
| 其它过滤维度（部门/类别/年级/区间/关键词） | **D（拒绝）** | 无任何证据支持 |
| 「选课」模块 | **D（当前）** | 无端点/参数证据；需新 recon；且不能假定等价于全集 |
| 导出/批量/报表端点 | **D（不存在）** | §3 已核实 |

## 7. 推荐路径（§8，按优先级）

```text
P0（先做，最小、且**已在已批准计划内**）：
   在新的已授权会话里，**首先**只请求 **North 第 1 页一次**
   （`openingSchoolNumber=5062202`, `pageNo=1`, `pageSize=200`），
   记录 §2 的安全元数据；然后按已批准计划的 O3/O4 预算继续（≤6 次、间隔 ≥30 s）。
   目的：补上 PR #49 明示的缺口（North page 1 从未被请求），判定 600 是
   "North 过滤查询整体不可用" 还是 "从 offset 200 起不可用"。
   ⛔ 这不是"反复盲探"：它是一次**有明确判据**的、计划内的一次观测。

P1（若 P0 显示 North page 1 可用、page 2 仍 600）：
   把 North 判定为**外部系统阻塞**（preference #4）：
   ⛔ 不跳过 North、⛔ 不合成、⛔ 不推断完整性、⛔ 不放宽验收规则；
   在 North 恢复（或学校给出可复用端点）之前，**不产出**真实 full-semester acceptance。

P2（架构层面的唯一备选，需要 Architecture Decision，⛔ 不得先实现）：
   评估 **B 类**方案：新增"North 分区 acceptance 类型" + 已批准传输支持
   `param.courseNumber`（单课程、单页即可 complete）+ **独立批准**的 North 课程清单。
   前置条件：a) 学校侧该参数行为被复测并可稳定取满单课程；
             b) 存在独立、可审计的 North 课程清单（人工/官方导出，需授权）；
             c) 新的 acceptance manifest 设计通过 review（仍强制 inventory / digest / identity 去重）。
   ⚠️ 在上述 a/b/c 任一不成立前，该方案**不可用**。

⛔ 不推荐：更小 pageSize 作为完整性方案；⛔ 不推荐：任何形式的重复盲探。
```

## 8. 风险与未知

```text
R1  PR #49 未记录"O1 之前该会话是否已有请求" ⇒ 无法完全排除"会话已被预热"这一解释
    （但即便如此，F5/F6 的 7-请求包络与"第 2 个请求即失败"仍不一致）
R2  North 第 1 页从未被请求（F3 缺口）⇒ "North 过滤查询整体 vs 仅 page≥2 失败"未判定
R3  North 历史 total（405）**只作参考**（⛔ 不写进 production 逻辑）⇒ 失败边界(offset 200)
    与 405 的关系只能作为**线索**，不能作为判定依据
R4  四个其它校区标为"可采集"是**运营状态**陈述（REAL_CAPTURE_OPERATION_PACK §B），
    ⛔ 不等于"过滤分页已在真实运行中端到端取满过"
R5  HTTP 600 / code 50015000 的成因**未知**；⛔ 不得称"限流"（F2）
R6  任何"用未过滤流 + 响应字段切校区"的做法都会引入未批准的语义（F11）
```

## 9. 边界声明

```text
⛔ 本文不含任何生产代码改动；⛔ 未改 public schema / Provider contract / Store trust 语义；
⛔ 未新增采集路径；B 类方案只是**待裁定的设计提案**，实现前必须 Architecture Review。
⛔ 本轮未访问真实学校网络、未发请求、未使用/记录任何凭据。
```
