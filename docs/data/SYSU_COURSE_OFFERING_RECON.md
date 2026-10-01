# SYSU 教学班（CourseOffering）技术侦察记录（Phase 2B-0D）

> **本文件只记录字段名、语义、映射结论与汇总事实。**
>
> **不含**：任何 Raw JSON、Cookie / Session / Token、完整 Request Headers、HAR、
> 教师姓名、修读对象完整文本、内部长 ID 取值、完整教学班逐行记录。

---

## 1. 本轮范围与方式

| 项 | 内容 |
|---|---|
| 方式 | **人工技术侦察**（由负责人在本人正常登录、已有权限的范围内完成） |
| 查询规模 | **小规模**：单一课程、单一学期（不批量、不枚举） |
| 本轮性质 | **只做结构分析**：不写正式 parser、不建数据库、不写 Course Data Adapter、不进入 Integration |
| 侦察状态 | **到此结束**，不再继续查询更多课程 |

---

## 2. 已确认的查询入口（不含任何凭据）

| 项 | 内容 |
|---|---|
| 方法 / 路径 | `POST /jwxt/schedule/agg/schoolOpeningCoursesSchedule/querySchoolOpeningCourses` |
| 请求参数 | `pageNo` / `pageSize` / `total` / `param.yearTerm` / `param.courseNumber` |
| 本轮取值 | `yearTerm = 2026-1`；`courseNumber = CSE202` |
| 返回 | `code = 200`；`data.total = 2` |

> ⚠️ **不记录**任何认证信息（Cookie / Session / Token、完整 Request Headers、HAR）。
> 上述**请求参数本身不含个人信息**，故可记录；**响应 Raw JSON 不进入本仓库**。

---

## 3. 汇总事实

- 课程 **`CSE202`（数据结构与算法）** 在 **2026-1** 学期返回 **2 个真实教学班**；
- 每个教学班包含**多个独立的"上课时间 / 地点" segment** —— 见第 6 节（本轮最重要的结构发现）。

---

## 4. 已确认的真实字段（字段名 + 语义 + 映射结论）

> 只列**字段名与判定**，**不列任何具体取值**（除第 3 节已给出的汇总数）。
> 内部 ID 类字段**只说明"存在"，不记录其值**。

| 真实字段 | 语义 | 与公共 `CourseOffering` 的关系 |
|---|---|---|
| `courseNum` | 课程号 | → `course_id`：**A 可直接映射** |
| `courseName` | 课程名称 | → `course_name`：**A** |
| `classNumber` | 教学班号 | → `class_id`：**A** |
| `yearTerm` | 学年-学期 | → `semester`：**A** |
| `score` | 学分（**字符串数字**） | → `credit`：**B 可转换后映射** |
| `teachingName` | 授课教师 | → `teacher`：**A/B**（语义可对应；**教师姓名不入库**） |
| `limitNumber` | 容量上限 | → `capacity`：**A** |
| `selectedNumber` | 已选人数 | **C 当前无直接字段** |
| `limitNumber - selectedNumber` | 剩余容量（**派生值**） | → `remaining_capacity`：**B 派生值** |
| `openingUnitName` | 开课单位 | **C 当前无正式表示**（见 G7 / G10） |
| `courseCategoryName` | 课程类别（样本中出现"专必"） | **C 当前无正式表示**；⚠️ **带培养方案 / 上下文语义，不得认定为课程全局固有属性** |
| `examMode` | 考核方式 | **C 当前无正式表示** |
| `readObj` | 修读对象 | **C 当前无正式表示**（完整文本**不入库**） |
| `teachProgressSubmitState` | **待确认** | **C 当前无正式表示** |
| `openClass` | **待确认** | **C 当前无正式表示** |
| `teachingTimePlaceStr` | 上课时间地点**原始文本串** | 需**结构化解析**才能对应 `weekday` / `start_section` / `end_section` / `weeks` / `campus` / `classroom`；**原始串不入库** |
| `openingSchoolName` | 开课校区 / 学校 | 可能与 `campus` 相关，**语义待人工确认** |
| `weekDay` | 星期 | 与 `weekday` 相关；**它与 segment 的对应关系待确认**（见第 6 节） |
| 内部 ID / 计数类：`class_ID`、`sumClassesID`、`sumClassesNum`、`courseId`、`outLineId`、`outlineTypeNum`、`timePlaceId` | 后台内部标识 / 计数 | **只记录为"存在"**；**不等于**公共 `course_id` / `class_id`；本轮**不设计对应字段**，**不记录其值** |

### 4.1 业务语义待确认（**不根据 0/1 值自行解释**）

`teachProgressSubmitState`、`openClass`、`outlineTypeNum`：

> **字段存在，业务语义待确认。** 本轮**不解释**其取值含义。

---

## 5. 公共标识的选取口径

```text
courseNum   → CourseOffering.course_id
classNumber → CourseOffering.class_id
```

**`courseId` / `class_ID` 等后台长 ID 不等于现有公共 `course_id` / `class_id`。**
本轮**只记录它们存在**，**不设计对应字段**。

---

## 6. 【真实结构缺口】一个教学班可有多个上课时间 / 地点 segment

**本轮最重要的发现**：`CSE202` 的**每个教学班都存在多个 schedule segment**。
一个真实教学班的结构形如：

```text
segment 1：1-17周      星期一   第 3-4 节   某校区 / 教学楼 / 教室
segment 2：1-17单周    星期三   第 5-6 节   某校区 / 教学楼 / 教室
```

而当前 `CourseOffering` **只能表达一组**：

```text
weekday / start_section / end_section / weeks[] / campus / classroom
```

**因此登记为结构缺口（见缺口报告的 G9）**：

> **一个教学班可以拥有多个独立的上课时间 / 地点 segment，
> 当前 `CourseOffering` 无法在一个对象中无损表达。**

**本轮明确未做，也禁止做**：

- ❌ 修改 Schema
- ❌ 新增 `meetings[]`（或任何字段）
- ❌ 只保留第一段
- ❌ 丢弃其他时间段
- ❌ 把同一教学班擅自拆成多个可独立选择的 `CourseOffering`

**最终表示方式留给 Data Gate。**

---

## 7. 周次格式与潜在转换（仅记录，**不实现 parser**）

已确认的真实格式至少包括：

| 真实格式 | 潜在转换（**仅记录，本轮未实现**） |
|---|---|
| `1-17周` | → `[1,2,3,…,17]` |
| `1-17单周` | → `[1,3,5,…,17]` |

⚠️ 本轮**只做结构分析**，**不实现正式 parser**。
是否还存在"双周"、跨 segment 的周次交集如何处理等，**需在 Data Gate / Course Data 模块正式定义**。

---

## 8. 合规声明

- 本轮查询由负责人在**本人正常登录、已有权限**的范围内完成；
  DeepSeek **未登录**教务系统、**未使用** NetID、**未要求**任何人提供账号密码；
- **未保存** Cookie / Session / Token；**未记录**完整 Request Headers；**未采集** HAR；
- **未写**任何 crawler / 抓取脚本；**未建**数据库；**未写** Course Data Adapter；
- **未修改** `/schemas/`、`/docs/interfaces/`、`backend`、`frontend`、`mock_data`；
- **未进入** Integration；
- 本文件**不含** Raw JSON、教师姓名、修读对象完整文本、内部长 ID 取值、完整教学班逐行记录；
- 人工技术侦察**到此结束**，不再继续查询更多课程。
