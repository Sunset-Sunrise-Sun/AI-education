"""培养方案**课程分类审核**端点（⚠️ 模块内私有 API 包络）。

```text
POST /api/v1/curriculum-import/parse-pdf              （已有，本轮响应追加 review 会话）
GET  /api/v1/curriculum-review/{review_id}            取审核状态
POST /api/v1/curriculum-review/{review_id}/decisions  提交审核草稿决定
GET  /api/v1/curriculum-review/{review_id}/export      导出审核草稿与未解决问题清单
```

## ⛔ 权限与信任边界（本轮指令 §二.B、§三）

| 约束 | 实现 |
| --- | --- |
| 决策主键是 `source_record` | 请求模型字段即 `source_record`；⛔ 无 `course_id` 入口 |
| 客户端⛔ 不能提交证据 / 课程原文 / SHA-256 | 请求模型 `extra="forbid"`；未知字段 ⇒ `review_unknown_field` |
| ⛔ 不能确认冲突 / UNKNOWN 项 | `confirm` 校验候选状态（见 `curriculum_review`） |
| ⛔ 不能无理由人工修改 | `override` 必须给 `requirement` + 非空 `reason` |
| ⛔ 拒绝建议不得自动选相反类别 | ⛔ 没有 `reject` 动作；拒绝 = `defer` |
| ⛔ 未知 / 过期会话 | 404 `review_not_found`（⛔ 不自动新建） |
| ⛔ 容量上限 | 503 `review_capacity_reached` |
| ⛔ 审核草稿不得进正式规划 | 导出恒 `verified=false` / `complete=false`；本模块⛔ 不 import planner |

⚠️ **不涉及公共契约**：请求/响应模型都是本模块私有；`/schemas/**` 与
`/docs/interfaces/**` 一字未改。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.services.curriculum_review import (
    ACTION_CONFIRM,
    ACTION_DEFER,
    ACTION_OVERRIDE,
    ReviewStoreError,
    build_export,
    get_review_store,
)

router = APIRouter(tags=["curriculum-review"])

#: `review_id` 由 `secrets.token_urlsafe(32)` 生成 ⇒ 最长约 43 字符；
#: 这里给一个**严格上限**，避免超长路径参数进入查找。
_MAX_REVIEW_ID_LENGTH = 128


class ReviewDecisionInput(BaseModel):
    """单条审核决策（⚠️ ⛔ 不含证据 / 课程原文 / 摘要 —— 那些只由服务端保管）。"""

    model_config = ConfigDict(extra="forbid")

    source_record: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description="目标行的来源定位（决策主键，⛔ 不是课程编码）",
        ),
    ]
    action: Annotated[
        str,
        Field(description="confirm（确认候选）/ override（人工修改）/ defer（暂缓）"),
    ]
    requirement: Annotated[
        str | None,
        Field(default=None, description="仅 override 使用：required 或 elective"),
    ] = None
    reason: Annotated[
        str | None,
        Field(default=None, max_length=500, description="仅 override 必填：人工理由"),
    ] = None


class ReviewDecisionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: Annotated[
        list[ReviewDecisionInput],
        Field(min_length=1, description="本次提交的决策（整批校验后一次性应用）"),
    ]


class ReviewDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_record: str
    action: str
    requirement: str | None
    reason: str | None
    revision: int
    decided_by: str


class ReviewProgress(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_candidates: int
    confirmed: int
    overridden: int
    deferred: int
    undecided: int


class ReviewSessionResponse(BaseModel):
    """审核状态（`progress` 等字段允许扩展，故 `extra="allow"`）。"""

    model_config = ConfigDict(extra="allow")

    review_id: str
    document: dict[str, Any]
    candidates: list[dict[str, Any]]
    progress: ReviewProgress
    notes: list[str]


class ReviewErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str
    message: str


def _reject(error: ReviewStoreError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"detail": {"error": error.code, "message": error.message}},
    )


def _require_review_id(review_id: str) -> str:
    """路径参数的长度上限校验（⛔ 不把超长字符串带进查找）。"""

    if len(review_id) > _MAX_REVIEW_ID_LENGTH:
        raise ReviewStoreError(
            "review_not_found", "审核会话不存在或已过期。", status=404,
        )
    return review_id


@router.get(
    "/curriculum-review/{review_id}",
    response_model=ReviewSessionResponse,
    responses={404: {"model": ReviewErrorBody, "description": "会话不存在或已过期"}},
)
async def get_curriculum_review(
    review_id: Annotated[str, Path(description="解析 PDF 时返回的 review_id")],
) -> Any:
    """取当前审核状态：候选 + 证据 + 决策 + 进度。"""

    try:
        session = get_review_store().get(_require_review_id(review_id))
    except ReviewStoreError as error:
        return _reject(error)
    return session.to_payload()


@router.post(
    "/curriculum-review/{review_id}/decisions",
    response_model=ReviewSessionResponse,
    responses={
        400: {"model": ReviewErrorBody, "description": "决策非法（见固定错误码）"},
        404: {"model": ReviewErrorBody, "description": "会话不存在或已过期"},
        413: {"model": ReviewErrorBody, "description": "单次提交条数超限"},
        503: {"model": ReviewErrorBody, "description": "会话容量已达上限"},
    },
)
async def submit_curriculum_review_decisions(
    review_id: Annotated[str, Path(description="review_id")],
    body: Annotated[ReviewDecisionsRequest, Body()],
) -> Any:
    """提交审核**草稿**决定（`confirm` / `override` / `defer`）。

    ⚠️ 这是**内部草稿**：⛔ 不写批准锚点、⛔ 不改 `verification.verified`、
    ⛔ 不进入正式个人补修规划。
    """

    payload = [item.model_dump() for item in body.decisions]
    try:
        session = get_review_store().submit(_require_review_id(review_id), payload)
    except ReviewStoreError as error:
        return _reject(error)
    return session.to_payload()


@router.get(
    "/curriculum-review/{review_id}/export",
    responses={404: {"model": ReviewErrorBody, "description": "会话不存在或已过期"}},
)
async def export_curriculum_review(
    review_id: Annotated[str, Path(description="review_id")],
) -> Any:
    """导出审核草稿 + 未解决问题清单（绑定原始 PDF 摘要）。

    ⛔ 导出恒为草稿：`verification.verified=false`、`complete=false`、
    `conclusion=pending_group_lead_review`、`identity_authentication=not_performed`。
    """

    try:
        session = get_review_store().get(_require_review_id(review_id))
    except ReviewStoreError as error:
        return _reject(error)
    record = build_export(session)
    return JSONResponse(
        status_code=200,
        content=record,
        headers={
            # ⛔ 明确标注这是草稿，且**不可**用作批准依据
            "X-Review-Status": "draft_not_approved",
            "Content-Disposition": (
                f'attachment; filename="curriculum-review-draft-{session.review_id[:8]}.json"'
            ),
        },
    )


#: 允许的动作（测试据此断言"只有三个动作、⛔ 没有 reject"）。
ACTIONS = (ACTION_CONFIRM, ACTION_OVERRIDE, ACTION_DEFER)

__all__ = ["ACTIONS", "router"]
