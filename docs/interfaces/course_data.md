# Course Data 模块接口

> Data Gate-2（**DG-01**）已把公共契约从"一个 `CourseOffering` = 一个时间段"
> 改为 **`CourseOffering` 1 — N `Meeting`**。本文件已同步该 breaking migration。

## 职责

回答：**现实中当前学期有哪些可用教学班？**

本模块负责：
- 读取用户已授权查看的教务课程数据；
- 课程/教学班数据清洗；
- 时间、周次、校区标准化；
- 数据去重与同步；
- 为 Planner 提供统一的 CourseOffering。

## 对外输出

所有教学班必须符合：
- `schemas/course_offering.schema.json`

**公共结构**：

```text
CourseOffering            = 一个教学班
CourseOffering.meetings[] = 该教学班**全部**上课时间 / 地点段
```

建议接口：

```text
sync_courses(source) -> CourseOffering[]
search_course(query) -> CourseOffering[]
get_course_offerings(course_id) -> CourseOffering[]
normalize_offering(raw) -> CourseOffering
```

> ⚠️ **`normalize_offering(raw)` 必须聚合同一教学班的全部 meeting**，
> **不能只解析第一个 segment**。
> 已确认的真实教务样本表明，一个教学班**可能**同时包含多个上课段
> （例如"1-17 周 星期一 第 3-4 节"＋"1-17 单周 星期三 第 5-6 节"），
> 只取第一段会**丢失真实排课信息**，让下游的冲突检测产生**假阴性**，
> 最终输出**不可执行的方案**。

## 关键标准

- **一个 `CourseOffering` 表示一个教学班，不表示一个时间段**；
- `meetings` 必须至少包含 **1 个 `Meeting`**；
- **每个真实教学班的所有 schedule segment 都必须进入 `meetings[]`**；
- ⛔ **不得只保留第一段**；
- ⛔ **不得把同一个教学班的多个 segment 拆成多个可独立选择的 `CourseOffering`**
  （那会凭空造出学校并不存在的可选教学班）；
- `meetings[].weekday`：1=周一 ... 7=周日；
- `meetings[].start_section` / `end_section`：使用整数节次；
- `meetings[].weeks`：展开为实际周次数组；
- `meetings[].campus` / `classroom`：该时间段对应的地点；
- `data_source`：必须明确是 mock 还是 real。

### 已知但暂缓的表达限制（deferred gap）

**meeting 级教师关联**：真实教务数据中 **segment 与教师确实存在关联**
（`teachingTimePlaceStr` 的 segment 项本身包含教师信息），
**但当前公共 `Meeting` 不表达它** ——
`teacher` 暂为 `CourseOffering` **顶层的汇总 / 展示字段**。

- 这是 Data Gate 已确认的 **known deferred representation gap**，**不是"该语义不存在"**；
- ⛔ 本模块**不得**为此自行在 `Meeting` 上增加字段（公共契约不得私改）；
- 后续如确需 meeting 级教师，须走 `【接口变更请求】` → 人工确认。

## 安全边界

只能读取用户正常登录后本人已经有权限查看的数据（**已授权范围内**）。

不得：
- 保存教务密码；
- 绕过认证；
- 破解验证码（CAPTCHA）；
- 越权调用接口；
- 提交 Cookie/Session/Token。

> ⚠️ 批量导入实现时必须先确认合理的 `pageSize` / 请求规模；
> 若只能取得部分范围，**必须显式记录完整性（completeness）**，
> **不得把 partial snapshot 宣称为 complete**。

## 与 Planner 的关系

Course Data 负责“真实供给”和标准化，不负责判断课程该不该选。
