# 真实数据批准流程设计（组长为唯一项目内部审核人）

> 分支：`feature/approval-workflow`（基线 `feature/final-upgrade` = `d52160f`，已含 provenance gate）
> 复用：`backend/app/provenance/__init__.py` 与 `APP_TRUST_ANCHOR_PATH`（⛔ 不自创签名方案）
> 前序：`TRUST_ANCHOR_DESIGN.md`（信任模型）、`PROVENANCE_GATE_CLOSURE.md`（F-01…F-08 收口）

---

## 0. 一句话设计

> **组长是唯一有权批准的人；批准这个动作**只能**由组长在带外对一个受权限保护的
> 锚点文件执行。Agent 与生成工具只能"准备证据"和"读取校验"，⛔ 不能写锚点。**

系统侧的可执行保证只有两条，但它们是硬的：

1. **代码层**：生成工具的名称出现在 `approver` 里 ⇒ 锚点整体被拒绝（既有自签检测）；
   工具还会在**写入前**检查目标路径是否等于 `APP_TRUST_ANCHOR_PATH`，相等即拒写。
2. **权限层（真正边界）**：锚点文件在仓库外、由组长独占写权限；
   ⛔ 它不在任何 Agent / 工具的可写路径内。

⚠️ 这两条**不是**密码学保证。能写那个文件的人就能批准——这是设计的一部分，不是缺陷。

---

## 1. 四个角色的职责分离

| 角色 | 是谁 | 能做什么 | ⛔ 不能做什么 |
| --- | --- | --- | --- |
| **数据提交者**<br>`submitter` | 学校 / 学院提供的正式材料持有人，或项目内负责交接材料的人 | 把原始材料交到受控目录；说明来源与学期 | ⛔ 不能批准；⛔ 不能把材料提交进 Git |
| **工具生成者**<br>`generator` | 本仓库的 parser / importer / collector / 校验工具 | 解析材料、产出标准化 artifact、**计算并记录摘要** | ⛔ 不能批准；⛔ 不能写锚点；⛔ 不能改 `verification.verified` |
| **审核人**<br>`approver` | **项目组长本人**（唯一） | 读待审核清单与原始材料，判定"来源是否可靠"；签署批准或拒绝 | —— |
| **批准记录保管者**<br>custodian | 组长（或组长明确书面授权的一人） | 在带外把批准记录写入锚点文件；保管文件权限；执行撤销 | ⛔ 不能替组长判断；⛔ 不能把锚点提交进 Git |

### 角色分离如何在结构上体现

```text
提交者 ──提供材料──> 受控目录（仓库外）
                        │
生成者 ──解析──────> artifact（仓库外） + 证据清单（仓库外）
                        │
                        ▼  待审核清单（工具产出，可复制到 issue / 文档）
审核人（组长）──逐项核对──> 批准 / 拒绝（手写意见）
                        │
                        ▼  组长明确授权后
保管者 ──写入──> 锚点文件（仓库外，组长独占写权限）
                        │
                        ▼  只读
运行时 ──load_trust_anchor + verify_approval──> fail closed 或放行
```

⛔ **同一个人不得同时是"工具生成者"与"approver"**：这由自签检测强制。
⛔ **角色分离不依赖 Agent 自觉**：Agent 在物理上没有锚点的写权限。

---

## 2. 批准记录字段（在既有字段上**只增不改**）

既有字段（不变，来自 `TRUST_ANCHOR_DESIGN.md`）：
`kind`、`identity`、`artifact_sha256`、`approver`、`authorization`、`approved_at`、
`expires_at`（可选）、`note`（可选）。

**本轮新增**（全部为可选元数据；缺失即 `null`，⛔ 不猜测）：

| 字段 | 含义 | 谁能写 | 校验规则 |
| --- | --- | --- | --- |
| `submitter` | 数据提交者标识（姓名/单位），用于追责 | 保管者按组长提供的信息填写 | 非空字符串或 `null`；⛔ 不参与放行判定 |
| `generator` | 产出该 artifact 的工具（如 `tools/sysu_course_offering_collector.js`） | 保管者按证据清单填写 | 非空字符串或 `null`；⛔ 允许出现工具名（这是**如实记录**），但⛔ 不得等于 `approver` |
| `review_evidence_sha256` | 组长**实际审核过的那份待审核清单**的 SHA-256 | 保管者按组长确认的清单计算 | 64 位小写十六进制或 `null`；存在时⛔ 不参与放行判定（**只作可追溯绑定**，见 §3.3） |
| `revoked` | 是否已撤销 | 保管者按组长指示填 `true` | **必须是真布尔**；缺省视为 `false` |
| `revoked_at` | 撤销时间 | 同上 | ISO-8601 字符串或 `null` |
| `revoked_by` | 谁撤销的 | 同上 | 非空字符串或 `null` |
| `revocation_reason` | 撤销原因 | 同上 | 非空字符串或 `null` |

### 撤销的结构性要求

```text
revoked == true  ⇒  revoked_at 与 revoked_by 与 revocation_reason 都必须非空
revoked == false ⇒  revoked_at / revoked_by / revocation_reason 必须为 null
```

任一条不满足 ⇒ **锚点整体非法**（`trust_anchor_invalid`）。理由：避免"撤了一半"的
模糊记录被后续读者误判。

> ⚠️ 为什么用 `revoked` 布尔而不是**删除**那条记录？
> 因为删除会让"这份数据曾经被批准过"这一事实消失，审计链断裂。
> 保留 + 标记撤销，才能回答"它是什么时候、被谁、因为什么不再有效"。

### 2.2 ⚠️ 批准对象的唯一性（Architecture Review 修复：`approval_conflict`）

**批准对象** = `(kind, identity, artifact_sha256)` 三元组。

```text
同一批准对象**只允许一条记录**。
出现第二条 ⇒ 拒绝**整个锚点**，错误码 `approval_conflict`（fail closed）。
```

**修复的漏洞**：修复前 `verify_approval()` 先筛出所有"未撤销"记录，只要其中一条有效
就放行。于是"已撤销 + 有效"共存时，**撤销被静默忽略** —— 用一条遗留记录即可绕过撤销。

**修复后的判定表**（⛔ 任何一档都不会"挑一条放行"）：

| 同一对象的记录情况 | 结果 | 错误码 |
| --- | --- | --- |
| 恰好 1 条、未撤销、未过期 | ✅ 放行 | `approved` |
| 恰好 1 条、已撤销 | ⛔ 拒绝 | `approval_revoked` |
| 恰好 1 条、未撤销、已过期 | ⛔ 拒绝（可续期） | `approval_expired` |
| **≥2 条**（含"撤销+有效"、"两条有效"、"过期+有效"、"两条撤销"） | ⛔ 拒绝整个锚点 | **`approval_conflict`** |
| 0 条（身份匹配但摘要不符） | ⛔ 拒绝 | `approval_digest_mismatch` |

**为什么要求"唯一"而不是"未撤销的恰好一条"**：

1. 不留任何"挑一条"的空间，语义没有歧义；
2. **撤销与重新审核都改同一条记录**，所以审计链天然完整（不需要多条记录）；
3. 重新审核改了内容时，`artifact_sha256` 已经不同 ⇒ 属于**不同对象**，不会误伤；
4. ⛔ **不引入审批版本系统**——只有"同一对象唯一记录"这一条最小规则。

**两层 fail-closed**（纵深防御）：

| 层 | 位置 | 作用 |
| --- | --- | --- |
| ① 装载期 | `load_trust_anchor()` → `_require_unique_objects()` | 同一对象 ≥2 条 ⇒ **整个锚点**拒绝（运维立刻看到） |
| ② 校验期 | `verify_approval()` | 即使调用方手工构造 `TrustAnchor` 绕过①，也绝不挑一条放行 |

### 2.3 撤销后如何重新批准（⛔ 不允许自动恢复）

```text
⛔ 错误做法：为同一对象**新增**一条有效记录去"顶掉"撤销
           ⇒ 触发 approval_conflict，整个锚点被拒
✅ 正确做法：修改**同一条**记录：
             revoked 改回 false
             清空 revoked_at / revoked_by / revocation_reason
             更新 approved_at 与 authorization（写明是新的审核决定）
             把撤销历史留在 note 里
```

因此"恢复有效"必须是**明确的、可追溯的新审核决定**，
⛔ 不能靠遗留记录、⛔ 不能靠时间过去、⛔ 不能靠"再补一条"。

---

## 3. 待审核清单（可复制、可归档、可绑定）

工具产出一份 JSON（`--out`），包含任务书要求的全部列：

| 列 | 来源 | 谁提供 |
| --- | --- | --- |
| **文件名称** | 调用方传入的 artifact 路径的**基名**（⛔ 不写绝对路径，避免泄漏目录结构） | 工具 |
| **来源** | 调用方显式传入的 `--source`（学校系统 / 交接批次 / 采集会话标识） | 提交者说明，组长核对 |
| **版本** | 从 artifact 读取（`version_id` / `catalog_version` / 目标版本号） | 工具 |
| **学期** | 从 artifact 读取（`semester` / `as_of_term`） | 工具 |
| **SHA-256** | 对 artifact **文件字节**计算（⛔ 不解析后重排、⛔ 不规范化） | 工具 |
| **解析异常** | artifact 自带的 issue 码列表（如 `unresolved_credit`、`unmapped_requirement`、`docx` 导入问题码） | 工具**原样转述**，⛔ 不解释、⛔ 不修补 |
| **完整性情况** | artifact 自带的 completeness 字段（`complete` / `completeness_evidence` / 行数与计数是否自洽） | 工具原样转述 |
| **审核结论** | ⛔ **不是工具填的**：固定输出 `pending_group_lead_review` | —— |
| **复核项** | 工具**无法**判断、必须由组长回答的问题清单（见 §3.2） | 工具生成问题，组长回答 |

### 3.1 工具的输出形状

```json
{
  "evidence_format": "real_data_review_evidence",
  "evidence_version": 1,
  "generated_at": "<ISO-8601>",
  "items": [
    {
      "kind": "curriculum_case",
      "file_name": "case-a.json",
      "source": "<调用方传入>",
      "version": {"target_version_id": "net-2025", "catalog_version": null},
      "semester": {"semester": null, "as_of_term": "2025-2"},
      "artifact_sha256": "<64 hex>",
      "parse_issues": [{"code": "unresolved_credit", "row": 7, "field": "credit"}],
      "completeness": {"complete": false, "completeness_evidence": null, "self_consistent": true},
      "review_conclusion": "pending_group_lead_review",
      "reviewer_questions": ["..."]
    }
  ],
  "review_conclusion": "pending_group_lead_review"
}
```

### 3.2 组长必须亲自回答的问题（工具⛔ 不代答）

1. 这份材料**是不是**学校/学院正式提供的（还是自造/推测）？
2. 文件名称与**交接渠道**是否与提交者所述一致？
3. `parse_issues` 里的每一条，是"材料本来如此"还是"工具解析缺陷"？
4. `completeness` 未满足时，是否仍足以支撑本次使用目的？
5. 学期 / 版本标识是否与本次要做的判断一致？
6. 是否设置失效期（`expires_at`）？多长？
7. 结论：**批准 / 拒绝**。拒绝也要求留下书面理由。

### 3.3 `review_evidence_sha256` 的作用与**边界**

- **作用**：把"组长批准的那次审核"钉到**具体某一份清单**上。日后若要回答
  "组长当时看到的是什么"，用这个摘要即可验证清单未被事后替换。
- ⛔ **边界**：它**不**参与放行判定。为什么？因为"证据文件是否就是组长看的那份"
  同样只能由文件权限保证；把它做成放行条件会给人"有密码学保证"的错觉。
  因此它是一个**审计字段**，不是信任锚。

---

## 4. Agent 为什么无法自行把数据设为已批准

| 层 | 机制 | 性质 |
| --- | --- | --- |
| 1 | 自签检测：`approver` 含 `generator`/`importer`/`parser`/`mock`/`test`/`tool`/`collector` 等子串 ⇒ 锚点整体非法 | **启发式**（能挡明显自签，⛔ 挡不住有意伪装） |
| 2 | 工具的写路径守卫：目标路径 == `APP_TRUST_ANCHOR_PATH` ⇒ **拒绝写入**（退出码 3） | 硬检查（防误操作） |
| 3 | ⛔ 工具**不提供**"批准"子命令：只有 `evidence`（产出清单）与 `verify`（校验锚点） | 接口设计 |
| 4 | **锚点文件在仓库外**，⛔ 不在任何 Agent / 工具的默认可写路径内 | **真正的安全边界** |
| 5 | `.gitignore` 覆盖锚点与证据目录名；CI 不注入锚点 | 防误提交 |
| 6 | 运行时只**读**锚点，⛔ 从不写 | 代码层 |

> ⚠️ 如实声明：第 1、2、3、5、6 条是"降低误用"，第 4 条才是安全边界。
> 如果组长把锚点文件放在 Agent 可写的目录里，整套流程就退化成"Agent 自己批准自己"。
> **这是必须在部署时由组长亲自确认的事**（见 §8）。

---

## 5. 批准记录的存储权限

| 对象 | 建议位置 | 权限 | 谁能写 |
| --- | --- | --- | --- |
| 原始材料 | 仓库外受控目录（如 `%USERPROFILE%\real-data-materials\`） | 组长读写；⛔ 其他人只读或无权限 | 提交者放入，组长管理 |
| 标准化 artifact | 仓库外（如 `…\real-data-artifacts\`） | 同上 | 工具产出 |
| 待审核清单（证据） | 仓库外（如 `…\real-data-evidence\`） | 组长读写 | 工具产出 |
| **批准锚点** | 仓库外**单独目录**（如 `…\real-data-approvals\trust-anchor.json`） | **组长独占写**；服务账号只读 | ⛔ **只有保管者** |
| `APP_TRUST_ANCHOR_PATH` | 后端进程环境变量 | —— | 部署者注入 |

⛔ **不提交到 GitHub 的清单**：
`trust-anchor*.json`、`*.evidence.json`、`real-data-*` 目录、原始材料（`.docx`/`.xlsx`/bundle）、
任何 `.env`、任何密钥。

`.gitignore` 已覆盖 `*.env`；本轮补充锚点与证据的**文件名模式**（见 §7 实施）。

---

## 6. 撤销、失效与重新审核

### 6.1 失效的四种触发方式

| 触发 | 机制 | 结果 |
| --- | --- | --- |
| **内容被修改** | `artifact_sha256` 与当前文件字节不符 | `approval_digest_mismatch` |
| **到期** | `expires_at` 早于当前时间 | `approval_expired` |
| **撤销** | `revoked: true`（+ 必填的撤销三字段） | `approval_revoked` |
| **身份变化** | 版本 / 学期 / 摘要等身份字段不再匹配 | `approval_missing` 或 `approval_identity_mismatch` |

### 6.2 撤销流程（组长指示 → 保管者执行）

```text
① 组长发现问题（材料被替换 / 来源存疑 / 学期错 / 学校规则变化）
        ↓  书面指示（记录在 issue / 邮件 / 会议纪要，含理由）
② 保管者打开锚点文件，把对应记录改为：
     "revoked": true,
     "revoked_at": "<ISO-8601>",
     "revoked_by": "<组长或保管者标识>",
     "revocation_reason": "<必填理由>"
        ↓  ⛔ **不新增记录**、⛔ 不删除该记录
        ↓  ⛔ 同一对象出现第二条记录 ⇒ 整个锚点被拒（approval_conflict）
③ 后端**每次装配都重新读**锚点 ⇒ 下一个请求立即 fail closed（503）
        ↓  ⛔ 无需重启服务
④ 记录到 worklog：撤销了什么、为什么、何时
```

> ⚠️ **撤销是原地标记**：`_require_unique_objects` 要求同一批准对象只有一条记录，
> 所以撤销**不能**用"再写一条撤销记录"的方式，必须是改原记录。

### 6.3 重新审核流程

```text
① 重新跑 evidence 工具（同一 artifact 或新材料）⇒ 新清单、新摘要
② 组长重新逐项核对（§3.2 的七个问题）
③ 若批准：
     - 内容未变（同一对象）⇒ 改**同一条**记录：
         revoked 改回 false，清空三个撤销字段，
         更新 approved_at / authorization，把撤销历史写进 note
       ⛔ 不允许"新增一条有效记录"来顶掉撤销（会触发 approval_conflict）
     - 内容已变 ⇒ `artifact_sha256` 不同 = **不同对象** ⇒ 正常**新增**一条记录；
       旧对象的那条记录保持 revoked（⛔ 不会因新记录而复活）
④ 若拒绝 ⇒ 不写记录；把拒绝理由写进 worklog
```

⛔ **绝不允许**为了"让流程跑通"而：删除记录、放宽自签检测、把 Agent 名字写进 `approver`、
把锚点路径指向仓库内文件、或为同一对象堆叠多条记录。

---

## 7. 与现有校验逻辑的衔接（⛔ 不自创签名方案）

| 复用项 | 位置 | 本轮是否改动 |
| --- | --- | --- |
| `APP_TRUST_ANCHOR_PATH` | `app/provenance/__init__.py` | ⛔ 环境变量名不变 |
| `trust_anchor_version: 1` | 同上 | ⛔ 版本号不变（只增可选字段，⛔ 不破坏既有锚点） |
| `load_trust_anchor()` | 同上 | ✅ 增加新可选字段的解析与撤销一致性校验 |
| `verify_approval()` | 同上 | ✅ 增加"跳过已撤销记录、报 `approval_revoked`" |
| `sha256_file()` | 同上 | ⛔ 不变（仍是"文件字节"语义） |
| 三个运行时门 | `planning_runtime` / `store.load_accepted_offerings` / `personal_runtime` | ⛔ 不改调用方式 |
| 自签检测 `_SELF_ISSUING` | 同上 | ⛔ 不放松；仅澄清它只作用于 `approver` |

新增拒绝原因码：**`approval_revoked`**（与 `approval_missing` 区分：
前者是"曾批准、现已撤销"，后者是"从未批准"）。

---

## 8. 待组长确认事项（⛔ 不假设已具备安全保管条件）

```text
【BLOCKED — 待组长确认】
1. 锚点文件的**实际路径**与所在目录的**访问控制**（谁能写、谁能读）。
   ⛔ 在确认前不假设存在安全保管条件。
2. 组长在批准记录里的**身份口径**（姓名？工号？"项目组长"？）——需统一，
   因为 approver 是唯一的责任人字段。
3. `authorization` 的**依据形式**（会议纪要编号 / 邮件 / 签字文件标识）。
4. 是否设置 `expires_at`，以及各类 artifact 的默认有效期。
5. 保管者是组长本人，还是组长**书面授权**的另一人；授权如何留痕。
6. 证据清单与锚点是否需要**异地/离线备份**（防勒索、防误删）。
7. 是否引入真正的签名机制（离线私钥）。⛔ 本轮不做，因为它需要密钥管理决策。
8. 真实材料是否已取得；未取得则真实数据验收**保持 BLOCKED**。
```

---

## 9. 本轮明确**不做**的事

- ⛔ 不实现"Agent 自动批准"的任何路径（包括"检测到文件存在就批准"）。
- ⛔ 不自创签名 / HMAC / 密钥方案。
- ⛔ 不把锚点或证据写成默认参数（不给"忘了传就用仓库内默认值"的机会）。
- ⛔ 不修改公共 Schema、Mock 演示通道、Planner 算法。
- ⛔ 不因"流程跑通"而放宽任何既有 fail-closed 检查。
