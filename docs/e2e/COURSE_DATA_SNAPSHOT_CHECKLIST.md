# Course Data 完整快照验收清单（2026-1 Snapshot Checklist）

> **用途**：一个 2026-1 教学班快照在**被允许进入 Real pipeline 之前**，
> 必须由人工逐项确认。⛔ 任何一项未确认 → **不得**装配进 Real runtime。
>
> 状态：**验收标准已准备**。⛔ 本文件不声明任何快照已通过验收。

---

## 0. 使用方式

- 每一行都必须能勾选为 ✅ **并附证据**；⛔ 不接受"应该没问题"。
- 任一项为 ❌ 或无法确认 → 该快照**不得**进入 Real pipeline，
  runtime 应 **fail closed**（`course_data_not_ready`）。
- ⛔ **不得为了跑通 E2E 而放行**。

**结论栏**：

```text
[ ] 通过 —— 该快照可作为 Real Case A Course Data 使用
[ ] 不通过 —— 原因：__________________
```

---

## 1. 语义正确性

| # | 检查项 | 通过判据 | 证据 |
|---|---|---|---|
| 1.1 | `semester == "2026-1"` | 快照 semester 精确等于 `2026-1` | 快照属性值 |
| 1.2 | `reported_total` **存在** | 非 `None` | 快照属性值 |
| 1.3 | `loaded_count` **存在** | 等于 `len(offerings)` | 快照属性值 |
| 1.4 | `loaded_count == reported_total` | 两者**精确相等** | 两个数字比对 |
| 1.5 | `is_complete == true` | 快照自报 `complete` | 快照属性值 |
| 1.6 | 所有 `CourseOffering.semester` 一致 | 每一条都等于 `2026-1` | 遍历断言 |

## 2. 采集完整性（分页证据链）

| # | 检查项 | 通过判据 | 证据 |
|---|---|---|---|
| 2.1 | **页码连续** | 从 `first_page_no` 起逐页连续，无缺页 | 页码列表 |
| 2.2 | **每页 `reported_total` 一致** | 与第一页完全相同，无变化 | 逐页 total |
| 2.3 | **没有中途空页** | 在达到 total 之前未出现空页 | 采集日志 |
| 2.4 | **无重复教学班** | `(semester, course_id, class_id)` 唯一 | 查重结果 |
| 2.5 | **无重复 section identity** | 同一教学班的上课段（section identity）不重复 | 逐 meeting 检查 |
| 2.6 | **Capture Bundle 不是 partial 两页样本** | ⛔ 明确**不是** 2 页 smoke/侦察样本 | bundle 页数 ≥ 实际所需页数 |
| 2.7 | 采集过程**无请求错误** | 无异常、无重试掩盖 | 采集日志 |

## 3. 契约合法性

| # | 检查项 | 通过判据 | 证据 |
|---|---|---|---|
| 3.1 | **所有 `CourseOffering` 通过 schema 校验** | 符合 `schemas/course_offering.schema.json` | 校验命令输出 |
| 3.2 | **所有 `CourseOffering` 通过 model 校验** | 符合 `backend/app/models/contracts.py`（Pydantic） | 校验命令输出 |
| 3.3 | `meetings` 语义正确 | 非空 → 逐段可用；`[]` → **仅**表示当前来源无可用排课信息（⛔ 不表示无课/无冲突） | 抽查 |
| 3.4 | **不含 `mock://` source** | 任何 `CourseOffering.source` 都不以 `mock://` 开头 | 全量扫描 |

## 4. 安全与隐私（红线）

| # | 检查项 | 通过判据 | 证据 |
|---|---|---|---|
| 4.1 | **没有 auth / captcha bypass** | 采集完全在用户本人正常权限内，无绕过登录、无破解验证码、无越权 | 采集方式说明 |
| 4.2 | **没有凭据入库** | 仓库中无密码 / Cookie / Session / Token / API Key | `git grep` + 人工检查 |
| 4.3 | **没有学生隐私** | 无姓名 / 学号 / 成绩 / GPA / 个人标识 | 全量字段检查 |
| 4.4 | **无内部长 ID** | 未登记 `courseId` / `class_ID` / `outLineId` / `timePlaceId` 等取值 | 字段检查 |
| 4.5 | **公开教学信息最小化保留，禁止内部 / 非公开人员信息** | 只保留公开教学信息所需的**最小字段**；⛔ 禁止记录内部 / 非公开人员信息（教师及其他人员的非公开信息）；⛔ 真实材料不入 public Git | 逐字段抽查 |
| 4.6 | **真实材料不入库** | capture bundle / 培训方案 docx / 成绩单均在受控本地 | `git status` 干净 |
| 4.7 | **请求规模已确认** | 未在高频批量调用；`pageSize` 在已确认上限内 | 采集参数记录 |

---

## 5. ⚠️ OPEN ARCHITECTURE ITEM：snapshot provenance

> 本节记录一个**已存在、尚未解决**的架构问题。
> ⛔ 本文档**不提出最终实现方案**。

**问题**：这份快照**是否真的来自受信 capture pipeline**，
**无法仅凭数据本身证明**。

**已知限制（事实，非推测）**：

1. **Capture Bundle 自身不携带经过认证的来源证明** ——
   其结构只有 `format` / `semester` / `first_page_no` / `page_size` / `pages`；
2. **`source` 是调用方提供的记录字段**，
   **不应单独被视为真实性证明** —— 一个 `real://...` 形式的字符串**没有证明力**；
3. `data_source` 由 Course Data 代码**无条件**置为 `real`，
   因此**受信 capture 产出的 bundle** 与**任意 synthetic bundle**
   走的是**完全相同**的代码路径。

**因此**：

- 上表 §1–§4 能证明的是「**数据看起来完整、合法、合规**」；
- 它们**不能**证明「**这份数据来自受信采集**」；
- 在架构裁决之前，来源可信只能通过**流程证据**认定
  （即"由谁、在什么权限下、用什么方式采到的"这一人工链条），
  而**不能**通过配置（env / 常量）"赋"给它。
- ⛔ **禁止**：`arbitrary bundle + 配置说它是 real → trusted Real snapshot`。

**处置**：该问题登记为 **OPEN ARCHITECTURE ITEM**，
由 Architecture Review 决定最终方案（是否需要 capture-side provenance 证明、
以及 runtime 应如何校验）。在此之前：

```text
无法证明来源 → fail closed（course_data_not_ready）
⛔ 不得为了 E2E 让它通过
```

---

## 6. 与验收等级的关系

| 本清单完成度 | 最高可达等级 |
|---|---|
| 未通过 | **LEVEL 0**（不得装配） |
| §1–§4 通过，但用的是 synthetic / test 产物 | **LEVEL 1**（wiring verified，**不是** Real E2E） |
| §1–§4 通过 + 真实受控 Curriculum 输入 | **LEVEL 2**（Real data path verified） |
| 上述 + 前端实际联调 + `REAL_CASE_A_ACCEPTANCE.md` §1 全部 10 条 | **LEVEL 3**（Real Case A E2E passed） |

等级定义见 `REAL_CASE_A_ACCEPTANCE.md` §2。
