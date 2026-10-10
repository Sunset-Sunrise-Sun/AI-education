"""**服务端审核会话**：保管解析快照与分类候选，接收组长的审核**草稿**决定。

```text
解析 PDF（服务端）
      │  ① SHA-256、课程行、分类候选、完整证据 全部留在**服务端**
      ▼
ReviewSession（review_id 随机不可预测）
      │  ② 客户端只提交 {source_record, action, requirement?, reason?}
      │     ⛔ 永远不能提交证据 / 课程原文 / SHA-256
      ▼
审核草稿（⛔ 不是批准件）
```

## ⛔ 本模块**不做**的事（逐条对应本轮指令 §二.A、§二.B）

| ⛔ 不做 | 由什么保证 |
| --- | --- |
| 让客户端改写证据 / 课程原文 / SHA-256 | 会话创建时快照一次；决策提交的**请求模型里根本没有这些字段**（`extra="forbid"`） |
| 只按课程编码索引决策 | 决策主键是 `source_record`（同一编码可有多行，各自独立） |
| 让 `confirm` 一键确认冲突 / UNKNOWN 项 | `confirm` 只接受 `status=single_source` 且候选非 `UNKNOWN`；否则 `review_confirm_not_allowed` |
| 让 `override` 无理由通过 | `override` 必须给 `requirement` **且** 非空 `reason`；否则 `review_override_requires_reason` |
| 让"拒绝建议"变成自动选相反类别 | ⛔ 本模块**没有** `reject` 动作；拒绝建议 = `defer`（回到未确认） |
| 接受会话里不存在的 `source_record` | 逐条校验；未知定位 ⇒ `review_unknown_source_record`（整批拒绝，⛔ 不部分应用） |
| 让新 PDF / 切换类型悄悄继承旧决定 | 每次解析都**新建**会话；`rebase` 语义由调用方显式新建，⛔ 不存在"自动沿用" |
| 无限创建会话 | 容量上限 + TTL 过期回收（见 §容量） |
| 把审核结果当成已核验 | 导出恒带 `verification.verified=false` / `complete=false` / `conclusion=pending_group_lead_review` |
| 声称已完成身份认证 | 会话**不绑定任何身份**；导出里明确写"未完成身份认证" |

## 决策语义

| action | 含义 | 前置条件 |
| --- | --- | --- |
| `confirm` | 确认**候选建议** | 候选 `single_source` 且非 `UNKNOWN` |
| `override` | 人工改写类别（**必须留理由**） | `requirement` ∈ {required, elective} 且 `reason` 非空 |
| `defer` | 暂缓 / 拒绝建议（**回到未确认**） | 无（⛔ 不自动选相反类别） |
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from app.curriculum.errors import CurriculumNormalizationError
from app.curriculum.pdf_evidence import (
    STATUS_CONFLICTING,
    STATUS_NO_EVIDENCE,
    STATUS_SINGLE,
    CategoryCandidate,
    CategoryRequirement,
    CourseClassificationReport,
)
from app.curriculum.requirements import RequirementKind

__all__ = [
    "ACTION_CONFIRM",
    "get_review_store",
    "reset_review_store",
    "ACTION_DEFER",
    "ACTION_OVERRIDE",
    "DEFAULT_TTL_SECONDS",
    "MAX_SESSIONS",
    "ReviewDecision",
    "ReviewSessionStore",
    "ReviewSession",
    "ReviewStoreError",
    "build_export",
]

#: 决策动作（⛔ 只有这三个；⛔ 没有 `reject`）。
ACTION_CONFIRM = "confirm"
ACTION_OVERRIDE = "override"
ACTION_DEFER = "defer"
_ACTIONS = frozenset({ACTION_CONFIRM, ACTION_OVERRIDE, ACTION_DEFER})

#: `override` 允许的人工结论（⛔ 不允许写 `unknown`：那是"没决定"）。
_OVERRIDE_TARGETS = frozenset({RequirementKind.REQUIRED, RequirementKind.ELECTIVE})

#: 会话 TTL（默认 2 小时，已获架构确认）。
DEFAULT_TTL_SECONDS = 2 * 60 * 60

#: 会话容量上限（⛔ 避免无限创建把进程内存吃满）。
MAX_SESSIONS = 64

#: 单次提交的决策条数上限（⛔ 避免一次请求携带超大 body）。
MAX_DECISIONS_PER_REQUEST = 512

#: `review_id` 的字节长度（`secrets.token_urlsafe` ⇒ 不可预测）。
_REVIEW_ID_BYTES = 32

#: 理由长度上限（⛔ 不接收无上限自由文本）。
_MAX_REASON_LENGTH = 500

#: 导出里的审核结论：⛔ 只能是"待组长最终确认"以外的任何东西都不允许。
CONCLUSION_PENDING = "pending_group_lead_review"


class ReviewStoreError(Exception):
    """会话/决策被拒绝（固定错误码 + 面向用户的固定文案）。"""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class ReviewDecision:
    """一条审核**草稿**决定（⛔ 不是批准）。"""

    source_record: str
    action: str
    #: `override` 时的人工结论；`confirm` / `defer` 为 `None`。
    requirement: RequirementKind | None = None
    #: `override` 必填的人工理由（⛔ 不得为空）。
    reason: str | None = None
    #: 提交序号：重复提交时后写覆盖前写，但**保留**覆盖计数。
    revision: int = 1

    def to_payload(self) -> dict:
        return {
            "source_record": self.source_record,
            "action": self.action,
            "requirement": self.requirement.value if self.requirement else None,
            "reason": self.reason,
            "revision": self.revision,
            # ⚠️ 明确区分"人工改写"与"原文证据"：本字段标明这条结论**来自人**。
            "decided_by": "reviewer_input_not_a_pdf_evidence",
        }


@dataclass(frozen=True, slots=True)
class ReviewSession:
    """一次审核会话的**服务端**快照。"""

    review_id: str
    document_key: str
    major: str
    cohort: str
    role: str
    file_name: str
    source_id: str
    #: 原始 PDF 摘要（⛔ 客户端无法提交或改写）。
    source_sha256: str
    created_at: float
    expires_at: float
    candidates: tuple[CategoryCandidate, ...]
    category_requirements: tuple[CategoryRequirement, ...]
    section_rows: tuple[Mapping, ...]
    unmapped_category_codes: tuple[str, ...]
    #: 决策表：主键是 `source_record`（⛔ 不是课程编码）。
    decisions: Mapping[str, ReviewDecision] = field(default_factory=dict)
    #: 每条定位被覆盖提交过几次（重复提交可观测，⛔ 不静默丢弃历史）。
    resubmissions: Mapping[str, int] = field(default_factory=dict)

    # ---------------------------------------------------------------- 查询
    @property
    def candidate_by_record(self) -> dict[str, CategoryCandidate]:
        return {item.source_record: item for item in self.candidates}

    def decision_for(self, source_record: str) -> ReviewDecision | None:
        return self.decisions.get(source_record)

    def progress(self) -> dict:
        """审核进度统计（⛔ 不把"未确认"算成"已确认"）。"""

        confirmed = overridden = deferred = 0
        for decision in self.decisions.values():
            if decision.action == ACTION_CONFIRM:
                confirmed += 1
            elif decision.action == ACTION_OVERRIDE:
                overridden += 1
            else:
                deferred += 1
        total = len(self.candidates)
        decided_records = set(self.decisions)
        by_status = {STATUS_SINGLE: 0, STATUS_CONFLICTING: 0, STATUS_NO_EVIDENCE: 0}
        for item in self.candidates:
            by_status[item.status] = by_status.get(item.status, 0) + 1
        return {
            "total_candidates": total,
            "confirmed": confirmed,
            "overridden": overridden,
            "deferred": deferred,
            "undecided": total - len(decided_records),
            "by_status": by_status,
            "conflicting": by_status.get(STATUS_CONFLICTING, 0),
            "no_evidence": by_status.get(STATUS_NO_EVIDENCE, 0),
            "section_rows": len(self.section_rows),
            "unmapped_category_codes": list(self.unmapped_category_codes),
            # ⛔ 明确写清：这条统计**不代表**来源已被核验
            "verification_verified": False,
            "conclusion": CONCLUSION_PENDING,
        }

    def to_payload(self, *, now: float | None = None) -> dict:
        """给前端的完整审核状态（含候选、证据、决策、进度）。"""

        candidates = []
        for item in self.candidates:
            payload = item.to_payload()
            decision = self.decisions.get(item.source_record)
            payload["decision"] = decision.to_payload() if decision else None
            payload["resubmissions"] = self.resubmissions.get(item.source_record, 0)
            candidates.append(payload)
        return {
            "review_id": self.review_id,
            "document": {
                "key": self.document_key,
                "major": self.major,
                "cohort": self.cohort,
                "role": self.role,
                "file_name": self.file_name,
                "source_id": self.source_id,
                "source_sha256": self.source_sha256,
            },
            "candidates": candidates,
            "category_requirements": [
                item.to_payload() for item in self.category_requirements
            ],
            "section_rows": [dict(item) for item in self.section_rows],
            "unmapped_category_codes": list(self.unmapped_category_codes),
            "progress": self.progress(),
            "expires_in_seconds": max(
                0, int(self.expires_at - (now if now is not None else time.time()))
            ),
            "notes": [
                "本页的审核决定是**内部草稿**，⛔ 不是学校认定，也⛔ 不是批准件。",
                "未完成身份认证，也未完成独立来源批准。",
                "⛔ 不得据此把 verification.verified 置为 true，也不得作为 Planner 放行依据。",
            ],
        }


# --------------------------------------------------------------------------- #
# 会话存储
# --------------------------------------------------------------------------- #

class ReviewSessionStore:
    """进程内存 + TTL 的审核会话存储（⛔ 不落盘，⛔ 服务重启即丢失）。"""

    def __init__(
        self, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, max_sessions: int = MAX_SESSIONS,
    ) -> None:
        if not isinstance(ttl_seconds, int) or ttl_seconds < 1:
            raise CurriculumNormalizationError("review: ttl_seconds must be a positive integer")
        if not isinstance(max_sessions, int) or max_sessions < 1:
            raise CurriculumNormalizationError("review: max_sessions must be a positive integer")
        self._lock = threading.RLock()
        self._sessions: dict[str, ReviewSession] = {}
        self._ttl = ttl_seconds
        self._max = max_sessions
        #: 统计（便于测试与运维观测；⛔ 不含材料内容）
        self.created_total = 0
        self.expired_total = 0
        self.rejected_capacity_total = 0

    # ---------------------------------------------------------------- 内部
    def _purge(self, now: float) -> None:
        """回收过期会话（调用方必须已持锁）。"""

        dead = [key for key, item in self._sessions.items() if item.expires_at <= now]
        for key in dead:
            self._sessions.pop(key, None)
            self.expired_total += 1

    def _require(self, review_id: object, now: float) -> ReviewSession:
        """取会话；未知 / 过期一律固定错误码（⛔ 不自动新建）。"""

        if not isinstance(review_id, str) or not review_id:
            raise ReviewStoreError("review_not_found", "审核会话不存在或已过期。", status=404)
        with self._lock:
            self._purge(now)
            session = self._sessions.get(review_id)
        if session is None:
            raise ReviewStoreError("review_not_found", "审核会话不存在或已过期。", status=404)
        return session

    # ---------------------------------------------------------------- 公开
    @property
    def session_count(self) -> int:
        with self._lock:
            self._purge(time.time())
            return len(self._sessions)

    def create(
        self,
        *,
        document_key: str,
        major: str,
        cohort: str,
        role: str,
        file_name: str,
        source_id: str,
        source_sha256: str,
        report: CourseClassificationReport,
    ) -> ReviewSession:
        """新建审核会话。

        ⚠️ **每次解析都新建**：⛔ 不存在"同一份 PDF 复用旧会话"的路径，
        因此⛔ 不可能"提交新 PDF 或切换类型后悄悄继承旧决定"。
        """

        now = time.time()
        with self._lock:
            self._purge(now)
            if len(self._sessions) >= self._max:
                self.rejected_capacity_total += 1
                raise ReviewStoreError(
                    "review_capacity_reached",
                    "审核会话数量已达上限，请稍后重试或结束已有会话。",
                    status=503,
                )
            review_id = secrets.token_urlsafe(_REVIEW_ID_BYTES)
            # 极小概率碰撞时重新取（⛔ 绝不覆盖已有会话）
            while review_id in self._sessions:
                review_id = secrets.token_urlsafe(_REVIEW_ID_BYTES)
            session = ReviewSession(
                review_id=review_id,
                document_key=document_key,
                major=major,
                cohort=cohort,
                role=role,
                file_name=file_name,
                source_id=source_id,
                source_sha256=source_sha256,
                created_at=now,
                expires_at=now + self._ttl,
                candidates=report.candidates,
                category_requirements=report.category_requirements,
                section_rows=report.section_rows,
                unmapped_category_codes=report.unmapped_category_codes,
            )
            self._sessions[review_id] = session
            self.created_total += 1
        return session

    def get(self, review_id: object) -> ReviewSession:
        return self._require(review_id, time.time())

    def submit(
        self, review_id: object, decisions: Sequence[Mapping[str, object]],
    ) -> ReviewSession:
        """提交 / 更新审核决定。

        ⛔ **整批校验后再应用**：任何一条非法都不落库（⛔ 不做"部分应用"）。
        """

        if isinstance(decisions, (str, bytes, bytearray)) or not isinstance(decisions, Sequence):
            raise ReviewStoreError("review_invalid_request", "决策必须是列表。")
        if len(decisions) > MAX_DECISIONS_PER_REQUEST:
            raise ReviewStoreError(
                "review_too_many_decisions",
                f"单次提交的决策条数不得超过 {MAX_DECISIONS_PER_REQUEST}。",
                status=413,
            )

        now = time.time()
        session = self._require(review_id, now)
        known = session.candidate_by_record

        parsed: list[tuple[str, ReviewDecision]] = []
        seen_in_request: set[str] = set()
        for raw in decisions:
            if not isinstance(raw, Mapping):
                raise ReviewStoreError("review_invalid_request", "每条决策必须是对象。")
            decision = self._parse_decision(raw, known)
            if decision.source_record in seen_in_request:
                raise ReviewStoreError(
                    "review_duplicate_in_request",
                    "同一次提交里出现重复的来源定位。",
                )
            seen_in_request.add(decision.source_record)
            parsed.append((decision.source_record, decision))

        with self._lock:
            current = self._sessions.get(session.review_id)
            if current is None:
                raise ReviewStoreError(
                    "review_not_found", "审核会话不存在或已过期。", status=404,
                )
            decisions_map = dict(current.decisions)
            resubmissions = dict(current.resubmissions)
            for record, decision in parsed:
                previous = decisions_map.get(record)
                revision = (previous.revision + 1) if previous is not None else 1
                decisions_map[record] = replace(decision, revision=revision)
                if previous is not None:
                    resubmissions[record] = resubmissions.get(record, 0) + 1
            updated = replace(
                current, decisions=decisions_map, resubmissions=resubmissions,
            )
            self._sessions[current.review_id] = updated
        return updated

    # ---------------------------------------------------------------- 决策校验
    def _parse_decision(
        self, raw: Mapping[str, object], known: Mapping[str, CategoryCandidate],
    ) -> ReviewDecision:
        allowed = {"source_record", "action", "requirement", "reason"}
        unknown = set(raw) - allowed
        if unknown:
            # ⛔ 客户端提交证据 / SHA-256 / 课程原文一律在这里被拒
            raise ReviewStoreError(
                "review_unknown_field",
                "决策包含不支持的字段（⛔ 不接受证据、课程原文或摘要）。",
            )

        record = raw.get("source_record")
        if not isinstance(record, str) or not record.strip():
            raise ReviewStoreError(
                "review_invalid_request", "决策必须给出 source_record。",
            )
        record = record.strip()
        if record not in known:
            # ⛔ 不允许提交当前会话不存在的定位
            raise ReviewStoreError(
                "review_unknown_source_record",
                "该来源定位不在当前审核会话中。",
            )

        action = raw.get("action")
        if action not in _ACTIONS:
            raise ReviewStoreError(
                "review_invalid_action",
                "action 必须是 confirm / override / defer。",
            )

        reason = raw.get("reason")
        if reason is not None:
            if not isinstance(reason, str):
                raise ReviewStoreError("review_invalid_request", "reason 必须是文本。")
            reason = reason.strip()
            if len(reason) > _MAX_REASON_LENGTH:
                raise ReviewStoreError(
                    "review_reason_too_long",
                    f"审核理由不得超过 {_MAX_REASON_LENGTH} 个字符。",
                )
            reason = reason or None

        requirement = raw.get("requirement")
        candidate = known[record]

        if action == ACTION_CONFIRM:
            # ⛔ 冲突 / 无证据 / 候选本身 UNKNOWN ⇒ 不能一键确认
            if candidate.status != STATUS_SINGLE or candidate.proposed_requirement is RequirementKind.UNKNOWN:
                raise ReviewStoreError(
                    "review_confirm_not_allowed",
                    "该课程没有明确类别（冲突或无证据），⛔ 不能一键确认；"
                    "请改用「人工修改」并说明理由，或「暂缓」。",
                )
            if requirement is not None:
                raise ReviewStoreError(
                    "review_invalid_request", "confirm 不接受 requirement 字段。",
                )
            return ReviewDecision(source_record=record, action=action)

        if action == ACTION_OVERRIDE:
            if requirement is None:
                raise ReviewStoreError(
                    "review_override_requires_requirement",
                    "人工修改必须明确选择类别。",
                )
            try:
                target = RequirementKind(requirement)
            except ValueError:
                raise ReviewStoreError(
                    "review_invalid_requirement",
                    "人工修改的类别只能是 required 或 elective。",
                ) from None
            if target not in _OVERRIDE_TARGETS:
                raise ReviewStoreError(
                    "review_invalid_requirement",
                    "人工修改的类别只能是 required 或 elective。",
                )
            if not reason:
                # ⛔ 人工判断必须留理由，且**不得**伪装成 PDF 原文证据
                raise ReviewStoreError(
                    "review_override_requires_reason",
                    "人工修改必须填写审核理由（该结论来自人工判断，⛔ 不是 PDF 原文证据）。",
                )
            return ReviewDecision(
                source_record=record, action=action, requirement=target, reason=reason,
            )

        # defer：暂缓 / 拒绝建议 ⇒ 回到未确认，⛔ 绝不自动选相反类别
        if requirement is not None:
            raise ReviewStoreError(
                "review_invalid_request", "defer 不接受 requirement 字段。",
            )
        return ReviewDecision(source_record=record, action=ACTION_DEFER, reason=reason)

    # ---------------------------------------------------------------- 测试/运维
    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


# --------------------------------------------------------------------------- #
# 导出
# --------------------------------------------------------------------------- #

def build_export(session: ReviewSession) -> dict:
    """导出审核草稿 + 未解决问题清单。

    ⛔ 恒带 `verification.verified=false` / `complete=false` / 待组长确认结论；
    ⛔ 明确区分"人工修改"与"PDF 原文证据"；⛔ 绑定原始 PDF 摘要。
    """

    unresolved: list[dict] = []
    for item in session.candidates:
        if item.status == STATUS_NO_EVIDENCE:
            unresolved.append({
                "kind": "no_evidence",
                "source_record": item.source_record,
                "course_id": item.course_id,
                "reason": "文档中未找到该课程的分类依据。",
            })
        elif item.status == STATUS_CONFLICTING:
            unresolved.append({
                "kind": "conflicting_evidence",
                "source_record": item.source_record,
                "course_id": item.course_id,
                "reason": "存在互相冲突的分类依据，已保留全部证据，需人工裁定。",
                "evidence": [e.to_payload() for e in item.evidence],
            })
        elif item.status == STATUS_SINGLE and not item.evidence_complete:
            unresolved.append({
                "kind": "section_level_only",
                "source_record": item.source_record,
                "course_id": item.course_id,
                "reason": "只有模块小节级依据，⛔ 不构成该课程的编码级证据。",
                "evidence": [e.to_payload() for e in item.evidence],
            })
    for record, decision in sorted(session.decisions.items()):
        if decision.action == ACTION_DEFER:
            unresolved.append({
                "kind": "deferred_by_reviewer",
                "source_record": record,
                "course_id": session.candidate_by_record[record].course_id,
                "reason": "组长暂缓处理（或拒绝该建议），保持未确认。",
                "reviewer_reason": decision.reason,
            })

    duplicates: dict[str, list[str]] = {}
    for item in session.candidates:
        duplicates.setdefault(item.course_id, []).append(item.source_record)
    duplicated = {
        code: records for code, records in duplicates.items() if len(records) > 1
    }

    return {
        "record_kind": "curriculum_classification_review_draft",
        # ⛔ 三条硬断言，任何情况下都不为真
        "verification": {"verified": False, "evidence": None},
        "complete": False,
        "conclusion": CONCLUSION_PENDING,
        "identity_authentication": "not_performed",
        "source": {
            "file_name": session.file_name,
            "source_id": session.source_id,
            "document_key": session.document_key,
            "source_sha256": session.source_sha256,
            "major": session.major,
            "cohort": session.cohort,
            "role": session.role,
        },
        "progress": session.progress(),
        "decisions": [item.to_payload() for item in session.decisions.values()],
        "candidates": [item.to_payload() for item in session.candidates],
        "category_requirements": [
            item.to_payload() for item in session.category_requirements
        ],
        "duplicate_course_ids": duplicated,
        "unresolved_items": unresolved,
        "notes": [
            "本导出是**内部审核草稿**：页面上的审核决定尚未经过身份认证，"
            "也未完成独立来源批准。",
            "⛔ 不得作为 verification.verified=true 的依据，"
            "也⛔ 不得作为正式 Planner（个人补修规划）的放行依据。",
            "`decided_by=reviewer_input_not_a_pdf_evidence` 的条目是**人工判断**，"
            "⛔ 不是 PDF 原文证据；原文证据见 `evidence[].raw_text`。",
            "类别最低学分只取自文档原文，⛔ 绝不用成员学分求和。",
        ],
    }

# --------------------------------------------------------------------------- #
# 进程级单例
# --------------------------------------------------------------------------- #
#
# ⚠️ 单例只是"进程内存里的一份存储"，⛔ 不是持久化：
#    服务重启即丢失全部会话（已获架构确认，⛔ 不作持久化承诺）。

_STORE: ReviewSessionStore | None = None
_STORE_LOCK = threading.Lock()


def get_review_store() -> ReviewSessionStore:
    """取进程级审核会话存储（懒加载）。"""

    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = ReviewSessionStore()
        return _STORE


def reset_review_store() -> None:
    """仅用于测试：清空并重建存储（⛔ 不在生产路径调用）。"""

    global _STORE
    with _STORE_LOCK:
        _STORE = ReviewSessionStore()
