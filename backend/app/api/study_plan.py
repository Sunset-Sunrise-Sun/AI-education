"""专业与培养方案只读接口（`/api/v1/majors`、`/api/v1/study-plans/{major_id}`）。

⚠️ 本路由**刻意不挂在 `/case-a-demo` 下**：
   选择专业 / 读取培养方案是通用只读资源，不属于某个固定 case 的闭环演示。
   它也不读 `case_a_decisions` 的范围裁定 —— 范围（historical/future）只影响
   "转专业时点之前需要补什么"，与"培养方案本身是什么"是两件事。

## 错误契约

```text
503 majors_not_configured      运行时未配置专业注册表（APP_MAJORS_REGISTRY_PATH）
404 unknown_major              major_id 不在注册表里
```

⛔ 两种失败都**不返回任何演示数据**。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.study_plan import (
    REGISTRY_PATH_ENV,
    StudyPlanError,
    StudyPlanRuntime,
    get_study_plan_runtime,
    to_major_summary,
    to_study_plan_payload,
)

router = APIRouter(tags=["study-plan"])

ERROR_NOT_CONFIGURED = "majors_not_configured"
ERROR_UNKNOWN_MAJOR = "unknown_major"


def _runtime_or_503(runtime: StudyPlanRuntime) -> StudyPlanRuntime:
    if not runtime.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": ERROR_NOT_CONFIGURED,
                "message": (
                    "专业培养方案数据尚未准备好。"
                    f"请配置 {REGISTRY_PATH_ENV} 指向有效的专业注册表。"
                ),
            },
        )
    return runtime


@router.get("/majors")
def list_majors(
    runtime: Annotated[StudyPlanRuntime, Depends(get_study_plan_runtime)],
) -> list[dict[str, object]]:
    """列出可用专业（供前端 `MajorSelector` 渲染）。"""

    configured = _runtime_or_503(runtime)
    return [to_major_summary(record) for record in configured.list_majors()]


@router.get("/study-plans/{major_id}")
def get_study_plan(
    major_id: str,
    runtime: Annotated[StudyPlanRuntime, Depends(get_study_plan_runtime)],
) -> dict[str, object]:
    """返回某专业的培养方案：要求列表 + 专业选修池 + 先修已知性统计。"""

    configured = _runtime_or_503(runtime)
    try:
        plan = configured.require(major_id)
    except StudyPlanError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": ERROR_UNKNOWN_MAJOR,
                "message": "该专业不在可用专业列表中。",
            },
        ) from None
    return to_study_plan_payload(plan)
