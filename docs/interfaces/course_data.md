# Course Data 模块接口

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

建议接口：

```text
sync_courses(source) -> CourseOffering[]
search_course(query) -> CourseOffering[]
get_course_offerings(course_id) -> CourseOffering[]
normalize_offering(raw) -> CourseOffering
```

## 关键标准

- weekday: 1=周一 ... 7=周日；
- start_section/end_section: 使用整数节次；
- weeks: 展开为实际周次数组；
- data_source: 必须明确是 mock 还是 real。

## 安全边界

只能读取用户正常登录后本人已经有权限查看的数据。

不得：
- 保存教务密码；
- 绕过认证；
- 破解验证码；
- 越权调用接口；
- 提交 Cookie/Session/Token。

## 与 Planner 的关系

Course Data 负责“真实供给”和标准化，不负责判断课程该不该选。
