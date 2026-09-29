# Planner 当前状态

## 已完成
- 公共输入输出 Schema 已定义

## 当前接口
- 输入：MakeupTask[]、CourseOffering[]、Preference
- 输出：PlanResult

## 当前阻塞
- 优先级权重尚未人工确认
- 跨校区通勤规则尚未确认

## 当前使用数据
- 建议先使用 Mock

## 下一步
- 建立统一 Mock 案例
- 实现时间/周次冲突检测
- 实现 NetworkX 依赖图
- 再接 OR-Tools
