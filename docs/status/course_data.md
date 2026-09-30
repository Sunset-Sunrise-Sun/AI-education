# Course Data 当前状态

## 已完成
- CourseOffering Schema 已定义
- 集成底座已提供 Mock CourseOffering 回放接口（`GET /api/v1/mock/course-offerings`），可供前端与 Planner 提前联调

## 当前接口
- 输出：CourseOffering[]

## 当前阻塞
- 尚未完成真实教务页面技术侦察

## 当前使用数据
- **仅 Mock**：`/mock_data/course_offerings.json`（人工虚构的演示教学班，全部 `data_source = "mock"`）
- 真实教学班数据**尚未开始获取**；「Mock 回放已就绪」不等于「真实 Course Data 已完成」

## 下一步
- 用户正常登录教务系统
- 人工检查 Elements / Network / Fetch-XHR
- 获取少量已授权真实课程样本
- 确定 DOM 读取还是页面正常接口数据解析
- 产出真实 CourseOffering 后，将以**新增独立 adapter / provider** 的方式接入真实通道；`/mock_data/` 与 `/api/v1/mock/*` 保持 **Mock-only**，不会被改写为真实数据源（见 `backend/README.md` 第 9 节）
