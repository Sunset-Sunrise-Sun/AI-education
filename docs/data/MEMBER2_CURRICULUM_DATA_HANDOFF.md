# 成员2（Curriculum / 学业路径）数据交接说明

> 适用角色：成员2（Curriculum / 学业路径模块）
>
> 目的：说明当前开发所需数据**在哪里、能否直接使用、如何交接、哪些内容禁止进入 public GitHub**。
>
> 当前案例：**2025级 遥感科学与技术 → 2025级 网络空间安全**。
>
> ⚠️ 本文件只记录“位置与交接规则”，**不包含任何真实逐行成绩、姓名、学号、Cookie、Session、Token 或教务 Raw 数据**。

---

## 1. 你当前真正需要的数据

成员2当前主线是：

```text
原专业培养方案
      +
新专业培养方案
      +
已修课程
      ↓
Curriculum Diff / 课程匹配
      ↓
MakeupTask[]
```

因此你当前需要的是 **D1 + D2 + D3 + D4**。

**D5 教学班数据不是你当前实现 Curriculum 的前置条件**，不要等待 Course Data 模块完成再开始。

---

## 2. 数据定位总表

| 编号 | 数据 | 当前是否已有 | 你在哪里看 | 是否能直接从 GitHub 用 | 交接方式 / 注意事项 |
|---|---|---:|---|---:|---|
| **D1** | 学籍 / 转专业 / 学分认定政策证据 | ✅ | `docs/data/SYSU_CASE_A_PUBLIC_EVIDENCE.md`、`docs/data/DATA_SOURCE_REGISTRY.md` | ✅ | 只把明确来源支持的内容当正式规则；“待确认”不能自行补成学校规定 |
| **D2** | 2025级遥感科学与技术培养方案 | ✅ | GitHub 汇总：`docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md`；来源登记：`CURR-OLD-003` | ⚠️ GitHub只有汇总事实 | **原始 `遥感方案.docx` 在负责人受控侧仍可访问**，需要完整课程表时由负责人通过非公开方式交付；不得提交 public Git |
| **D3** | 2025级网络空间安全培养方案 | ✅ | GitHub 汇总：`docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md`；来源登记：`CURR-NEW-004` | ⚠️ GitHub只有汇总事实 | **原始 `网安方案.docx` 在负责人受控侧仍可访问**，需要完整课程表时由负责人通过非公开方式交付；不得提交 public Git |
| **D4** | 已修课程 | ✅ 有真实来源 | GitHub证据：`docs/data/SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md`；来源登记：`TRANSCRIPT-001` | ❌ GitHub不含逐行记录 | 原始成绩单在负责人受控侧仍可访问，**Raw 不得交成员**；负责人需重新生成一份脱敏逐行样本后私下交付 |
| **D5** | 真实教学班 / CourseOffering | ✅ 小规模侦察 | `docs/data/SYSU_COURSE_OFFERING_RECON.md` | ✅ 只能读字段/结论 | 主要由 Course Data / Planner 使用；不是 Curriculum 当前前置输入 |
| **Mock** | 人工演示数据 | ✅ | `/mock_data/` | ✅ | 可用于接口联调，但**不能当真实业务结论** |
| **公共输出契约** | `MakeupTask[]` | ✅ | `schemas/makeup_task.schema.json`、`docs/interfaces/curriculum.md` | ✅ | 这是成员2最终跨模块输出，不能私自加字段 |
| **Integration 边界** | Curriculum Provider | ✅ | `docs/interfaces/integration.md`、`backend/app/integration/ports.py` | ✅ | 当前固定接口：`get_makeup_tasks() -> list[MakeupTask]`，修改需走 `【接口变更请求】` |

---

## 3. D2 / D3：培养方案怎么拿

### GitHub 中已有

先读：

```text
docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md
docs/data/REAL_TO_SCHEMA_GAP_REPORT.md
docs/data/DATA_GATE_DECISIONS.md
```

这些文件已经记录：

- 两份培养方案的来源性质；
- 培养版本；
- 总学分 / 实践学分等已确认事实；
- 哪些字段可直接映射、哪些会丢失；
- `CurriculumVersion / CurriculumCourse` 当前只作为 **Curriculum 内部模型**，不新增公共 Schema。

### 完整原始培养方案

负责人受控侧仍有：

```text
遥感方案.docx
网安方案.docx
```

这两份是成员2做**实际课程表解析、课程差分、课程号匹配**时最有价值的输入。

**它们不在 public GitHub。**

需要时：

```text
成员2提出需要
→ 负责人确认
→ 通过非公开位置单独交付
→ 成员2只在本地使用
→ 禁止 commit / push 到当前 public 仓库
```

---

## 4. D4：已修课程目前到底有什么

### 已确认的事实

GitHub：

```text
docs/data/SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md
```

来源：

```text
TRANSCRIPT-001
```

之前已用真实记录验证过 D4 字段与 Curriculum 需要的数据边界。

### 现在没有的东西

当前**没有一份已经持久保存、可以直接发给你的“24条八字段脱敏文件”**。

不要在仓库里找，也不要认为它已经存在。

### 负责人现在能重新生成什么

原始成绩单仍在负责人受控侧，可以重新整理出脱敏版已修课程。

从成绩单本身可以可靠恢复：

```text
course_name
credit
semester
course_type
passed
```

`course_id`：

- **只有培养方案或其它正式来源能明确对应时才填写**；
- 不能因为课程名称相似就猜；
- 无法确认时保留 `null / 待确认`。

当前仅靠成绩单不能可靠恢复的字段：

```text
offering_unit
cultivation_type
```

这两个字段如果后续确实影响 Curriculum 逻辑，需要再从受控教务来源确认，**不能自行补值**。

### D4 正式交接形态

负责人后续私下给成员2的版本应是 **Sanitized Sample**，建议只保留 Curriculum 真正需要的最小字段：

```text
course_id           # 可确认才填
course_name
credit
semester
passed
course_type
```

禁止包含：

```text
具体成绩
GPA
排名
姓名
学号
联系方式
其它直接身份信息
```

并且：

> **脱敏样本仍不得提交到当前 public GitHub。**

---

## 5. 成员2开发时必须以哪些文件为准

开始开发前至少阅读：

```text
AGENTS.md
docs/ARCHITECTURE.md

docs/interfaces/curriculum.md
docs/interfaces/integration.md
schemas/course.schema.json
schemas/makeup_task.schema.json

docs/data/SYSU_CASE_A_AUTHENTICATED_CURRICULUM_EVIDENCE.md
docs/data/SYSU_CASE_A_COMPLETED_COURSES_EVIDENCE.md
docs/data/REAL_TO_SCHEMA_GAP_REPORT.md
docs/data/DATA_GATE_DECISIONS.md
docs/data/MEMBER_DATA_HANDOFF.md
```

其中优先级：

```text
AGENTS.md
  ↓
/schemas + /docs/interfaces
  ↓
Data Gate 已确认决策
  ↓
Evidence / Gap 文档
  ↓
成员自己的内部实现
```

如果实现想法与上面发生冲突，**停止并上报，不自行改公共接口**。

---

## 6. 成员2当前可以开始做什么

在拿到 D4 脱敏逐行样本之前，可以先做：

```text
D2/D3 培养方案解析
→ Curriculum 内部 Course / CurriculumCourse 表示
→ 新旧培养方案差分框架
→ 课程匹配框架
→ MakeupTask 输出适配
```

拿到 D4 Sanitized Sample 后再接：

```text
已修课程
→ completed-course normalization（Curriculum 内部）
→ 已满足课程识别
→ 缺课 / 补修需求识别
→ MakeupTask[]
```

### 不能自行做

```text
❌ 自己猜 prerequisite
❌ 自己造 priority 公共字段
❌ 新建 CompletedCourse 公共 Schema
❌ 新建 CurriculumVersion / CurriculumCourse 公共 Schema
❌ 把内部模型私自变成跨模块 DTO
❌ 把真实培养方案 / 成绩单 / 脱敏逐行数据 push 到 public Git
```

---

## 7. 最终交给 Planner / Integration 的只有什么

成员2对外的稳定输出仍然是：

```text
MakeupTask[]
```

依赖信息：

```text
MakeupTask.prerequisites[]
```

如果真实来源不能证明先修关系：

```text
未知 / 待人工确认
```

**不得自动补边。**

当前没有公共：

```text
priority
DependencyGraph
PriorityResult
```

成员2可以在 Curriculum 内部计算风险 / 优先级 / 跨学期建议，但**不能假装这些已经有公共跨模块字段**。

---

## 8. 成员2缺数据时怎么提

不要只说“缺样本”。

按下面格式发给负责人：

```text
【成员2数据请求】

需要的数据：
用途：
需要哪些字段：
是否必须真实数据：
当前 GitHub 文档为什么不够：
希望交付形态：
是否涉及新的跨模块字段：
```

如果只是为了开发算法结构，优先用人工 Mock。

只有在“真实数据形态会改变实现”时才申请 Sanitized Sample。

---

## 9. 当前交接状态

```text
D1：GitHub 可直接读取 ✅

D2：GitHub 有汇总证据 ✅
    原始遥感培养方案：负责人受控侧存在 ✅
    尚未通过仓库交付

D3：GitHub 有汇总证据 ✅
    原始网安培养方案：负责人受控侧存在 ✅
    尚未通过仓库交付

D4：GitHub 有字段 / 汇总结论 ✅
    原始成绩单：负责人受控侧存在 ✅
    24条正式 Sanitized Sample：需要重新生成 ⏳
    当前逐行真实数据交接次数仍为 0

D5：已有侦察证据 ✅
    不是成员2当前前置条件
```

**成员2当前最需要负责人补的一项：**

> 重新生成一份 **D4 已修课程 Sanitized Sample**，通过非公开位置私下交付。
