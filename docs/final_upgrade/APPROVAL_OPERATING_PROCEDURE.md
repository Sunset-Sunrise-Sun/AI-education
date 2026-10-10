# 真实数据批准操作流程（组长逐条执行）

> 设计原理见 `APPROVAL_WORKFLOW_DESIGN.md`。本文件是**照着做**的操作手册。
> ⚠️ 本流程产出的所有文件（材料、artifact、清单、锚点）都在**仓库外**。
> ⛔ 任何一步都不要把带真实内容的文件放进仓库、贴进公开 issue 或聊天记录。

---

## 0. 五个阶段一览

```text
① 材料交接      提交者 → 受控目录            产出：原始材料
② 解析与取证    工具   → artifact + 待审核清单 产出：artifact、清单
③ 组长审核      组长   → 逐项核对，写结论      产出：批准 / 拒绝 + 书面理由
④ 写入批准记录  保管者 → 锚点文件（仓库外）     产出：trust-anchor.json
⑤ 生效与撤销    后端读取；需要时撤销并重审      产出：放行 / 503；撤销记录
```

⛔ **Agent 在任何阶段都不能代替③的结论，也不能执行④的写入。**

---

## 1. 阶段①：材料交接（提交者）

1. 提交者把**学校/学院正式材料**放到组长指定的受控目录，例如：

   ```text
   %USERPROFILE%\real-data-materials\<学期>\<材料名>.docx
   ```

2. 提交者**书面说明**（记进项目 issue / 会议纪要）：
   - 材料名称与获取渠道（学院网站 / 教务系统 / 老师提供）；
   - 对应的专业、年级、学期；
   - 是否已脱敏（⛔ 不得含学生姓名、学号、成绩明细等个人信息）。
3. 组长确认目录权限：⛔ 只有组长可写，其他人只读或无权限。

**验收**：材料文件存在、渠道可追、不含个人信息。

---

## 2. 阶段②：解析与取证（工具生成者）

### 2.1 产出标准化 artifact

按材料类型用既有工具（⛔ 工具不改变原始材料）：

| 材料 | 产出 | 工具 |
| --- | --- | --- |
| 培养方案 DOCX | `catalog.json` / case JSON | `python tools/build_catalog_draft.py`（草稿）+ 人工补齐 |
| 教务开课数据 | 全学期验收 manifest + SQLite | `tools/prepare_real_case_a_runtime.py` 等既有链路 |

### 2.2 产出**待审核清单**

```powershell
cd backend
$env:PYTHONUTF8 = '1'

python tools/review_real_data.py evidence `
    --artifact "<仓库外的 artifact 路径>" `
    --kind curriculum_case `
    --source "学校培养方案交接批次 2026-10（学院网站）" `
    --out "<仓库外的证据目录>\2026-10-plan.evidence.json"
```

- `--kind` 三选一：`curriculum_case` / `curriculum_catalog` / `course_data_semester_manifest`；
- `--source` 由**提交者**提供，组长核对；
- `--out` ⛔ **不得**指向 `APP_TRUST_ANCHOR_PATH`（工具会拒绝并退出码 3）。

⛔ **工具不会**：下结论、改 artifact、写锚点、把 `verification.verified` 改成 true。

---

## 3. 阶段③：组长审核（组长）

打开清单文件，**逐项核对**下面这张表（清单里的 `reviewer_questions` 是同一批问题的机器版）：

### 3.1 逐条核对表

| # | 列 | 清单里的字段 | 组长要回答的问题 | 结论填写 |
| --- | --- | --- | --- | --- |
| 1 | **文件名称** | `file_name` | 这个文件名与交接渠道描述一致吗？ | 一致 / 不一致 |
| 2 | **来源** | `source` | 这是学校/学院**正式**提供的，还是自造/推测的？ | 正式 / 存疑 / 不合规 |
| 3 | **版本** | `version` | 版本号与本次要判断的专业年级一致吗？ | 一致 / 不一致 |
| 4 | **学期** | `semester` | 学期 / `as_of_term` 与本次判断一致吗？ | 一致 / 不一致 |
| 5 | **SHA-256** | `artifact_sha256` | 记录下这个值（写入批准记录时要用**同一个**） | （抄录） |
| 6 | **解析异常** | `parse_issues` | 每一条是"材料本来如此"还是"工具解析缺陷"？ | 逐条判断 |
| 7 | **完整性情况** | `completeness` | 未满足完整性时，是否仍足以支撑本次用途？ | 可接受 / 不可接受 |
| 8 | **审核结论** | `review_conclusion` | **批准 / 拒绝**（拒绝也要写理由） | 批准 / 拒绝 |

### 3.2 组长必须亲自回答的七个问题

1. 这份材料**是不是**学校/学院正式提供的？
2. 文件名称与**交接渠道**是否与提交者所述一致？
3. `parse_issues` 里的每一条，是"材料本来如此"还是"工具解析缺陷"？
4. 完整性未满足时，是否仍足以支撑本次使用目的？
5. 学期 / 版本标识是否与本次要做的判断一致？
6. 是否设置失效期（`expires_at`）？多长？
7. 结论：**批准 / 拒绝**（附书面理由）。

### 3.3 审核结论记录模板（记进项目 issue / 会议纪要）

```text
【真实数据审核结论】
审核人：<组长姓名>
审核时间：<ISO-8601>
清单文件：<证据文件名>
清单 SHA-256：<对清单文件字节算的 sha256>
artifact 文件名：<file_name>
artifact SHA-256：<artifact_sha256>
来源：<source>
版本 / 学期：<version> / <semester>
解析异常结论：<逐条判断>
完整性结论：<可接受 / 不可接受，理由>
失效期：<无 / expires_at 值>
结论：批准 / 拒绝
理由（拒绝时必填）：
```

> ⚠️ 这份记录里的"批准"仅代表**项目内部**确认来源可靠，
> ⛔ 不代表学校正式认证，也⛔ 不代表课程等价或学分认定。

---

## 4. 阶段④：写入批准记录（保管者，需组长明确授权）

⛔ **本阶段不由 Agent 执行。** 请组长本人（或被书面授权的一人）手工编辑锚点文件。

### 4.1 把已有记录"改回未撤销"或**新增**一条

打开锚点文件（默认路径由组长决定，⛔ 不放在仓库内），在 `approvals` 数组里新增：

```json
{
  "kind": "curriculum_case",
  "identity": { "target_version_id": "net-2025", "as_of_term": "2025-2" },
  "artifact_sha256": "<从清单第 5 行原样抄录，64 位小写十六进制>",
  "approver": "<组长姓名（唯一审核人）>",
  "authorization": "<审核结论记录的编号 / 邮件 / 纪要标识>",
  "approved_at": "<ISO-8601，如 2026-10-10T09:00:00Z>",
  "expires_at": null,
  "submitter": "<提交者，如 教务数据交接人 李四>",
  "generator": "<产出 artifact 的工具，如 tools/build_catalog_draft.py>",
  "review_evidence_sha256": "<清单文件的 SHA-256>",
  "revoked": false,
  "note": null
}
```

### 4.2 ⛔ 四条硬性要求

| # | 要求 | 违反后果 |
| --- | --- | --- |
| 1 | `approver` **不得**含工具名（`generator`/`importer`/`parser`/`mock`/`test`/`tool`/`collector` 等子串） | 锚点**整体**非法（`trust_anchor_invalid`） |
| 2 | `approver` 与 `generator` **不得**相同 | 锚点**整体**非法 |
| 3 | `review_evidence_sha256` 必须是**这次审核那份清单**的摘要（64 位小写十六进制） | 锚点非法 |
| 4 | ⚠️ **同一批准对象只能有一条记录** | 锚点**整体**拒绝（**`approval_conflict`**） |

> 第 1、2 条由 `backend/app/provenance/__init__.py` 强制；第 3 条只做格式校验
> （⚠️ 它是**审计字段**，⛔ 不参与放行判定，见设计 §3.3）。

#### 批准对象是什么

```text
批准对象 = (kind, identity, artifact_sha256)
```

**同一对象只能有一条记录。** ⛔ 出现第二条（不管是重复有效、撤销+有效、
还是过期+有效）⇒ 后端拒绝**整个锚点**，错误码 **`approval_conflict`**。

为什么这么严：如果允许同一对象有多条记录，就必须"挑一条算数"；
而"挑一条"正是**可以用遗留记录绕过撤销**的根源。

| 你想要的 | ✅ 正确做法 | ⛔ 错误做法 |
| --- | --- | --- |
| 撤销 | 把**那条**记录改成 `revoked: true` + 三个撤销字段 | 再写一条撤销记录 |
| 撤销后重新批准（内容没变） | 改**同一条**：`revoked` 改回 `false`、清空撤销字段、更新 `approved_at` / `authorization`、把撤销历史写进 `note` | 新增一条有效记录 |
| 重新审核（内容变了） | 摘要不同 = **不同对象** ⇒ 正常新增记录；旧记录保持 `revoked` | 改旧记录的摘要 |

### 4.3 写完自检（只读，不批准）

```powershell
cd backend
python tools/review_real_data.py check-anchor --anchor "<锚点路径>"
```

期望：`"status": "loaded"`，且目标记录的 `revoked` 为 `false`。

---

## 5. 阶段⑤：生效、撤销与重新审核

### 5.1 生效

把锚点路径注入**后端进程**环境：

```powershell
$env:APP_TRUST_ANCHOR_PATH = "<仓库外的锚点路径>"
```

后端**每次装配都重新读锚点** ⇒ ⛔ 不需要重启即可看到变化。

### 5.2 撤销（组长指示 → 保管者执行）

把**对应那一条**记录改为：

```json
{
  "revoked": true,
  "revoked_at": "<ISO-8601>",
  "revoked_by": "<组长或被授权保管者>",
  "revocation_reason": "<必填：为什么不再有效>"
}
```

- ⛔ **不要删除记录**：删除会让"曾经批准过"的事实消失，审计链断裂；
- ⛔ **不要新增一条撤销记录**：同一批准对象出现第二条记录 ⇒ **整个锚点被拒**
  （`approval_conflict`）。撤销是**原地标记**；
- ⛔ 三个撤销字段**缺一不可**（缺任一 ⇒ 锚点整体非法）；
- ✅ 撤销**优先于**过期被报告（主动决定比被动过期更需要人看到理由）。

### 5.3 重新审核

| 情况 | 做法 |
| --- | --- |
| 内容**没变**，只是要恢复 | 改**同一条**记录：`revoked` 改回 `false`、**清空** `revoked_at` / `revoked_by` / `revocation_reason`、更新 `approved_at` 与 `authorization`（写明这是新的审核决定）、把撤销历史写进 `note` |
| 内容**已变** | 摘要不同 = **不同对象** ⇒ 正常**新增**一条记录；旧对象的那条记录**保持** `revoked: true` |
| 仍然拒绝 | ⛔ 不写记录；把拒绝理由写进 worklog |

⛔ **撤销后不会自动恢复**：不允许靠遗留记录、不允许靠时间过去、不允许靠"再补一条"。
恢复有效**必须**是一次明确的、可追溯的新审核决定。

---

## 6. 常见失败排查

| 现象 | 诊断码 | 处置 |
| --- | --- | --- |
| 503，`real_pipeline_not_configured` + 日志 `provenance_not_verified` | `trust_anchor_not_configured` | `APP_TRUST_ANCHOR_PATH` 没注入到**后端进程** |
| 同上 | `trust_anchor_unreadable` / `trust_anchor_invalid` | 锚点路径错 / JSON 格式错 / 自签被拦 / `approver==generator` / 撤销字段不全 |
| 同上 | **`approval_conflict`** | ⚠️ **同一批准对象出现了多条记录**（重复有效 / 撤销+有效 / 过期+有效）。请只保留**一条**：撤销与重新审核都改这同一条 |
| 同上 | `approval_missing` | 锚点里没有与该身份匹配的记录（版本 / 学期写错？） |
| 同上 | `approval_digest_mismatch` | **内容被改过**：重跑证据并重新审核 |
| 同上 | `approval_expired` | 续期：重新审核并更新 `expires_at` |
| 同上 | `approval_revoked` | 记录已被撤销：查 `revocation_reason`，需要则走"重新审核"（改同一条记录） |
| `check-anchor` 报 `approval_conflict` | —— | 同一对象有多条记录，见上 |

---

## 7. 当前状态：**真实数据验收 BLOCKED**

```text
【BLOCKED — 真实数据验收】
阻塞原因：尚未取得任何真实材料（培养方案 DOCX / 教务开课数据），
          且锚点文件的存放位置与访问控制尚未由组长确认。
已经确认：流程、工具、校验与撤销机制均已实现并用**合成数据**验证通过。
无法确认：真实材料是否存在、由谁提交；锚点目录是否具备需要的访问控制；
          组长的身份口径（approver 写法）与 authorization 依据形式。
需要人工提供：① 真实材料；② 锚点目录位置与权限；③ approver 口径；
          ④ authorization 依据形式；⑤ 是否设置 expires_at 及有效期；
          ⑥ 保管者是否另有其人（需书面授权）。
在确认前不会：把任何真实材料或批准记录提交进仓库；
          ⛔ 不会为了让链路跑通而把 Agent 写进 approver。
```
