# 来源信任模型（Verified Provenance）设计

> 分支：`feature/verified-provenance-gate`（基线 `feature/final-upgrade` = `45392d5`）
> 依据：架构负责人已批准的原则（见任务书 §一）+ `REAL_DATA_ISOLATION_AUDIT.md` 的 F-01/F-02/F-03/F-05/F-08
> 代码：`backend/app/provenance/__init__.py`

---

## 0. 一句话设计

> **把"已核验"从数据里的自述字段，改成"运行时必须在带外批准锚点里找到匹配记录"的硬条件。**

`data_source=real` 与 `verification.verified=true` 从此**只是声明**；
只有"**批准记录存在 + 摘要一致 + 身份一致 + 非自签 + 未过期**"才算通过。
任一条不满足 ⇒ **fail closed**。

---

## 1. 来源数据生命周期与信任锚点的位置

```text
① 原始文档 / 采集数据（学校培养方案 DOCX、教务开课数据）
        │  ⛔ 不进 Git、不进仓库
        ▼
② Parser / Importer（docx_reader / sysu collector / 五校区验收 CLI）
        │  产出「标准化 artifact」：
        │    Case A case JSON ／ catalog.json ／ 全学期验收 manifest
        ▼
③ 人工审核（**带外**：人读 artifact + 原始文档，形成批准意见）
        │  ⛔ 这一步在仓库与工具之外，本 Agent 不能代替
        ▼
④ 签发 provenance → **Trust Anchor 文件**（`APP_TRUST_ANCHOR_PATH`）
        │  记录：kind + 身份 + artifact SHA-256 + approver + authorization + 时间
        ▼
⑤ 运行时装载 Store / Provider（**新增门**：逐项校验锚点）
        ▼
⑥ Planner / AI 上下文（来源标记只作**信息**，不再作**证明**）
        ▼
⑦ 前端标识（区分"HTTP 成功"与"已核验真实教务数据"）
```

**关键不对称**（这是整个设计的支点）：

| 角色 | 能做什么 | ⛔ 不能做什么 |
| --- | --- | --- |
| Parser / Importer / 生成工具 | 产出 artifact；计算并**打印**自己的摘要供人核对 | 写锚点、签发批准、决定"已验证" |
| 运行时（后端） | 读锚点、重算摘要、逐项比对、fail closed | 自创批准、跳过缺失的批准 |
| 人 / 授权流程 | 写锚点（带 approver 与 authorization） | —— |

---

## 2. 批准记录字段

锚点文件（`trust_anchor_version: 1`，⛔ 不向前兼容）：

```json
{
  "trust_anchor_version": 1,
  "approvals": [
    {
      "kind": "curriculum_catalog",
      "identity": { "version_id": "net-2025" },
      "artifact_sha256": "<64 位小写十六进制>",
      "approver": "教务数据负责人（姓名/工号）",
      "authorization": "授权依据（邮件/会议纪要编号/签字文件标识）",
      "approved_at": "2026-10-01T00:00:00Z",
      "expires_at": null,
      "note": null
    }
  ]
}
```

| 字段 | 含义 | 校验规则 |
| --- | --- | --- |
| `kind` | 批准的 artifact 类别 | 必须属于受支持集合，否则锚点整体非法 |
| `identity` | **身份绑定**：把批准钉到具体版本/学期 | 字段集合必须与该 kind **完全相等**（⛔ 多写一个字段就拒绝，避免"加字段绕过"） |
| `artifact_sha256` | 被批准内容的摘要 | 64 位小写十六进制；必须与运行时从**当前内容**重算的摘要一致 |
| `approver` | **核验人身份** | 非空；且⛔ 不能是生成该 artifact 的工具（自签检测） |
| `authorization` | **授权依据** | 非空；⛔ 工具不解析、不推断其真伪（见 §6） |
| `approved_at` | 批准时间 | 非空 |
| `expires_at` | 失效时间（可选） | 若存在且已过期 ⇒ 拒绝 |
| `note` | 备注（可选） | —— |

### 2.1 角色分离与撤销字段（`feature/approval-workflow` 新增，全部可选）

> 完整流程见 `APPROVAL_WORKFLOW_DESIGN.md`；组长操作手册见 `APPROVAL_OPERATING_PROCEDURE.md`。
> ⛔ 这些字段**不破坏既有锚点**：缺失即 `null`，且除 `revoked` 外都不参与放行判定。

| 字段 | 含义 | 校验规则 |
| --- | --- | --- |
| `submitter` | 数据提交者（材料从哪来） | 非空字符串或 `null`；⛔ 不参与放行判定 |
| `generator` | 产出该 artifact 的工具 | 非空字符串或 `null`；✅ **允许**是工具名（如实记录），但⛔ **不得等于 `approver`** |
| `review_evidence_sha256` | 组长**实际审核过的那份待审核清单**的 SHA-256 | 64 位小写十六进制或 `null`；⚠️ **审计字段**，⛔ 不参与放行判定（见 `APPROVAL_WORKFLOW_DESIGN.md` §3.3） |
| `revoked` | 是否已撤销 | **必须是真布尔**；缺省视为 `false` |
| `revoked_at` / `revoked_by` / `revocation_reason` | 撤销时间 / 撤销人 / 撤销理由 | `revoked=true` 时**三者都必须非空**；`revoked=false` 时**必须都为 `null`**（⛔ 拒绝"撤了一半"的模糊记录） |

**新增拒绝原因码**：`approval_revoked`（与 `approval_missing` 区分：
前者"曾批准、现已撤销"，后者"从未批准"）。撤销**优先于**过期被报告。

### 2.2 ⚠️ 批准对象的唯一性（`approval_conflict`）

**批准对象** = `(kind, identity, artifact_sha256)`。**同一对象只允许一条记录**；
出现第二条 ⇒ **拒绝整个锚点**（错误码 `approval_conflict`）。

| 同一对象的记录情况 | 结果 | 错误码 |
| --- | --- | --- |
| 恰好 1 条、未撤销、未过期 | ✅ 放行 | `approved` |
| 恰好 1 条、已撤销 | ⛔ 拒绝 | `approval_revoked` |
| 恰好 1 条、未撤销、已过期 | ⛔ 拒绝（可续期） | `approval_expired` |
| **≥2 条**（撤销+有效 / 重复有效 / 过期+有效 / 重复撤销） | ⛔ 拒绝整个锚点 | **`approval_conflict`** |

⛔ 修复前的实现会"挑出未撤销的那条放行"，因此撤销可被遗留记录绕过；
修复后不留任何"挑一条"的空间。**撤销与重新审核都改同一条记录**，
所以审计链天然完整，⛔ 不需要、也⛔ 不允许审批版本系统。
详见 `APPROVAL_WORKFLOW_DESIGN.md` §2.2–§2.3 与 `APPROVAL_OPERATING_PROCEDURE.md` §4.2。

**受支持的 kind 与身份字段**

| kind | 绑定的 artifact | identity 字段 |
| --- | --- | --- |
| `course_data_semester_manifest` | 全学期验收 manifest | `semester`、`acceptance_sha256` |
| `curriculum_case` | Case A case JSON | `target_version_id`、`as_of_term` |
| `curriculum_catalog` | `catalog.json`（按版本逐条批准） | `version_id` |

---

## 3. 摘要计算对象（**对什么求 SHA-256**）

原则：**对"将要被消费的那份字节"求摘要**，⛔ 不做任何规范化、⛔ 不解析后重排。

| kind | 计算对象 | 理由 |
| --- | --- | --- |
| `course_data_semester_manifest` | 全学期验收 manifest 文件字节 | 与既有 `acceptance_sha256` 语义一致；五校区/成员身份/快照校验**原样保留** |
| `curriculum_case` | case JSON 文件字节 | 改一个字符即摘要变化 |
| `curriculum_catalog` | `catalog.json` 文件字节 | 任一版本内容变化即摘要变化 |

> ⚠️ 对**记录数组**的规范化摘要（`digest_of_records()`）只作为兜底工具存在；
> 默认走文件字节，避免"同一份数据两个摘要"。

---

## 4. 失效规则（fail closed 的全部情形）

| 固定原因码 | 触发条件 |
| --- | --- |
| `trust_anchor_not_configured` | ⛔ `APP_TRUST_ANCHOR_PATH` 未设置 |
| `trust_anchor_unreadable` | 文件不可读 |
| `trust_anchor_format_unsupported` | 版本号不是 `1`（⛔ 不向前兼容） |
| `trust_anchor_invalid` | 顶层/记录结构非法、字段多余或缺失、摘要格式错、**自签**、身份字段集合不符 |
| `approval_missing` | 锚点里没有与该 **identity** 匹配的记录 |
| `approval_digest_mismatch` | 身份匹配、但摘要与当前内容不符（**内容被改过**） |
| `approval_identity_mismatch` | 校验请求自身的身份字段不完整/与 kind 不符 |
| `approval_expired` | 匹配记录全部过期 |
| `approval_invalid` | 不支持的 kind、待校验摘要格式非法 |

**其他必须 fail closed 的场景**（由各调用点的既有校验负责，本轮**不放松**）：

- 五校区 shard 不精确匹配、inventory 摘要不绑定、基线不相等、Σ shard ≠ baseline、跨 shard 重复；
- membership 行数/集合漂移、逐行 payload 指纹不符、set digest 不符、行级 provenance 漂移；
- `partial` 快照进入生产；
- Case A 的 `version_id` / `as_of_term` / `confirmed_scope_decisions` 与已批准集合不符。

---

## 5. 存储位置与运行时校验时机

**存储位置**

- 锚点文件路径：环境变量 `APP_TRUST_ANCHOR_PATH`（与既有 `APP_*` 命名一致）。
- ⛔ **锚点文件不得进 Git、不得放在生成工具的可写目录内**；
  建议放在与教务数据同级的受权限保护目录，由负责人独占写权限。
- 锚点**只存元数据**，⛔ 不存 artifact 内容、⛔ 不存学生个人信息。

**运行时校验时机**（全部在**装配期**，⛔ 不推迟到请求期）

| 时机 | 校验 | 落点 |
| --- | --- | --- |
| 后端启动 / 每次请求重新装配 | ① 读锚点（不可用即拒绝） | `services/planning_runtime.py` |
| 装配 Curriculum provider | ② `curriculum_case` 批准 + case 文件摘要 + 身份 | `build_curriculum_provider` |
| 装配 Course Data provider | ③ `course_data_semester_manifest` 批准 + manifest 摘要 + 学期身份 | `build_course_data_provider` |
| 装载个人规划目录 | ④ `curriculum_catalog` 逐版本批准 + `catalog.json` 摘要 | `curriculum/catalog.py` |
| AI 接口每次请求 | ⑤ 来源一律标"未核验"（教学班来自请求体） | `api/ai_planning.py` + `ai_planning/context.py` |

⛔ 锚点内容**不缓存**：每次装配重新读，避免"启动时通过、之后被换掉"。

---

## 6. 信任锚的真实强度（⛔ 必须如实声明）

**本设计没有、也不打算自创密码学签名。** 因此：

1. **SHA-256 只证明"输入与摘要一致"**，⛔ 不能单独证明来源真实。
   它防的是"内容被悄悄改过"，防不了"人批准了错的东西"。
2. **锚点文件本身无防篡改**：能写该文件的人就能批准。
   真正的信任边界是**文件权限** + "锚点不在仓库内、不在生成工具可写路径内"。
   ⛔ 不要把它宣传成签名方案或密码学保证。
3. **`authorization` 字段不被机器验证**：工具只要求它非空，
   ⛔ 不解析其真伪。它的作用是"留下可追责的依据标识"，供人审计。
4. **自签检测是启发式**（`approver` 里出现 `generator`/`importer`/`mock`/`test` 等子串即拒绝）：
   能挡住"工具名直接写进 approver"，但**挡不住**有意伪装的字符串。
   它是"降低误用"的措施，⛔ 不是安全边界。
5. 因此**没有任何 Agent 可以自己完成签发**：仓库里没有可信身份与信任锚，
   签发环节必须由人配置（见 §8）。

---

## 7. 与"学业结论"的边界（⛔ 不可推定）

通过来源核验**只**说明"这份数据的来源与内容与批准记录一致"。
它⛔ **不**说明、也⛔ **不得**被用来推定：

- 某门课与另一门课**等价**（需人工认定 + 证据）；
- **毕业要求**已满足（需按学校规则判定）；
- **选课资格**已获得（学校教务系统才有此权限）；
- 学分认定、期限、先修或跨校区规则已获学校正式解释。

这些在系统里仍然是 `possibly_equivalent` / `manual_confirmation` / 未决事项，
由既有规则与人工确认决定，⛔ 不因"来源已核验"而自动升级。

---

## 8. 待人工配置的签发环节（本 Agent ⛔ 不代替）

| # | 需要人工决定 / 提供 | 为什么 Agent 不能做 |
| --- | --- | --- |
| 1 | 锚点文件的实际路径与**文件权限**（谁能写） | 属权限边界，必须由负责人设定 |
| 2 | `approver` 的**真实身份口径**（姓名/工号/角色） | 涉及真实人员身份 |
| 3 | `authorization` 的**依据形式**（邮件编号 / 纪要 / 签字件） | 涉及学校正式流程 |
| 4 | 是否允许 `expires_at`，以及有效期多长 | 属业务规则 |
| 5 | 真实 artifact 的产出（培养方案 DOCX / 教务开课数据） | 数据未提供 |
| 6 | 是否要引入真正的签名机制（如离线私钥签名） | 属架构与密钥管理决策 |

**在 1–6 确认之前**：系统只能提供**安全的拒绝路径**与**证据记录接口**，
⛔ 不会、也不能让任何真实链路"看起来已就绪"。

---

## 9. 与公共 Schema 的关系（⛔ 不改）

- 本设计**不修改** `/schemas/**`、`/docs/interfaces/**`；
- 锚点是**后端私有**的配置 artifact（与 catalog 一样属于内部声明，不是公共契约）；
- `InterpretResponse` 新增的 `context_source_verified` 是**本模块私有包络**字段
  （`api/ai_planning.py` 已声明"本文件里的请求/响应模型都是这个模块自己的私有包络"），
  ⛔ 不是公共 Schema；
- 若后续确需把 provenance 暴露成跨模块公共契约，必须先提交接口变更请求并标记 BLOCKED。
