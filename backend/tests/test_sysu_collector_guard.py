"""SYSU 浏览器端采集器的**静态安全守卫**（Phase 2B-2C1A）。

本文件不执行 JS，只对 `tools/sysu_course_offering_collector.js` 做**源码级**检查，
确保它满足本轮的安全边界：

- 加载脚本**不自动发请求**（无顶层调用、无定时轮询、无并发分页）；
- 有 hostname guard；
- 有 `pageSize` 上限校验与最小延迟；
- 源码中**不出现**读取浏览器端认证状态、导出认证头、后端 HTTP 客户端等字样。

⚠️ 这些是**静态**检查，只证明源码里没有相应写法，不等于运行时行为的形式化证明。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# backend/tests/test_sysu_collector_guard.py -> 仓库根目录
_REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_PATH = _REPO_ROOT / "tools" / "sysu_course_offering_collector.js"


@pytest.fixture(scope="module")
def collector_source() -> str:
    assert COLLECTOR_PATH.is_file(), f"缺少采集器源码：{COLLECTOR_PATH}"
    return COLLECTOR_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 认证边界：源码中不得出现读取 / 导出认证状态的写法
# ---------------------------------------------------------------------------

#: 禁止出现的写法（读取浏览器认证状态、导出认证头、后端 HTTP 客户端）。
_FORBIDDEN_TOKENS = (
    "document.cookie",
    "localStorage",
    "sessionStorage",
    "Authorization",
    "Cookie:",
    "indexedDB",
    "XMLHttpRequest",
    "requests.",
    "httpx",
)


@pytest.mark.parametrize("token", _FORBIDDEN_TOKENS)
def test_collector_source_has_no_forbidden_token(collector_source: str, token: str) -> None:
    """源码中不得出现读取认证状态 / 导出认证头 / 后端 HTTP 客户端的写法。"""

    assert token not in collector_source, f"采集器源码出现禁止的写法：{token}"


# ---------------------------------------------------------------------------
# 显式执行：加载脚本不得自动发请求
# ---------------------------------------------------------------------------


def test_collector_is_wrapped_in_an_iife(collector_source: str) -> None:
    """整份代码包在 IIFE 内，加载时只挂载对象，不执行采集。"""

    assert "(function () {" in collector_source
    assert collector_source.rstrip().endswith("})();")


def test_collector_has_no_top_level_fetch_call(collector_source: str) -> None:
    """`fetch(` 只出现一次，且必须在 `await` 之后（位于函数内部）。"""

    assert collector_source.count("fetch(") == 1
    assert "await fetch(" in collector_source


def test_collector_has_no_timer_driven_requests(collector_source: str) -> None:
    """不得使用定时轮询（只允许一次性 sleep）。"""

    assert "setInterval" not in collector_source


def test_collector_has_no_concurrent_pagination(collector_source: str) -> None:
    """分页必须串行：不得出现并发聚合。"""

    assert "Promise.all" not in collector_source
    assert "Promise.allSettled" not in collector_source
    assert "Promise.race" not in collector_source


def test_collector_requires_explicit_user_call(collector_source: str) -> None:
    """唯一入口是显式暴露的 `collect`，加载脚本不会调用它。"""

    assert "window.XuehangSysuCollector" in collector_source

    # 取**最后一次**出现（即真正的挂载点；文档里的用法示例在前面）
    expose_index = collector_source.rindex("window.XuehangSysuCollector")
    remainder = collector_source[expose_index + len("window.XuehangSysuCollector") :]

    assert "collect(" not in remainder, "挂载之后不得自动调用 collect()"


# ---------------------------------------------------------------------------
# 必要的护栏必须存在
# ---------------------------------------------------------------------------


def test_collector_has_hostname_guard(collector_source: str) -> None:
    assert 'window.location.hostname !== ALLOWED_HOSTNAME' in collector_source
    assert '"jwxt.sysu.edu.cn"' in collector_source


def test_collector_enforces_page_size_upper_bound(collector_source: str) -> None:
    assert "MAX_PAGE_SIZE = 200" in collector_source
    assert "pageSize > MAX_PAGE_SIZE" in collector_source


def test_collector_enforces_minimum_delay(collector_source: str) -> None:
    assert "MIN_DELAY_MS = 1000" in collector_source
    assert "DEFAULT_DELAY_MS = 1500" in collector_source
    assert "delayMs < MIN_DELAY_MS" in collector_source


def test_collector_limits_default_and_absolute_pages(collector_source: str) -> None:
    assert "DEFAULT_MAX_PAGES = 2" in collector_source
    assert "ABSOLUTE_MAX_PAGES = 50" in collector_source
    assert "maxPages > ABSOLUTE_MAX_PAGES" in collector_source


def test_collector_confirms_before_exceeding_smoke_pages(collector_source: str) -> None:
    assert "maxPages > DEFAULT_MAX_PAGES" in collector_source
    assert "window.confirm(" in collector_source


def test_collector_uses_same_origin_credentials(collector_source: str) -> None:
    assert 'credentials: "same-origin"' in collector_source


def test_collector_carries_expected_request_shape(collector_source: str) -> None:
    assert "querySchoolOpeningCourses" in collector_source
    assert "pageNo: pageNo" in collector_source
    assert "pageSize: pageSize" in collector_source
    assert "yearTerm: semester" in collector_source
    assert '"?_t=" + Date.now()' in collector_source


# ---------------------------------------------------------------------------
# 停止规则 / 数据最小化 / 脱敏
# ---------------------------------------------------------------------------


def test_collector_validates_each_page(collector_source: str) -> None:
    assert "payload.code !== 200" in collector_source
    assert "Number.isInteger(data.total)" in collector_source
    assert "Array.isArray(data.rows)" in collector_source


def test_collector_stops_on_total_change_and_empty_page(collector_source: str) -> None:
    assert "data.total !== expectedTotal" in collector_source
    assert "accumulatedRows > expectedTotal" in collector_source
    assert "data.rows.length === 0" in collector_source


def test_collector_does_not_claim_completeness(collector_source: str) -> None:
    """采集器只报告事实，不自行判定 complete / partial。"""

    assert "claimedComplete: false" in collector_source
    assert '"complete"' not in collector_source
    assert '"partial"' not in collector_source


def test_collector_keeps_only_minimal_row_fields(collector_source: str) -> None:
    """只保留 8 个必要字段；内部 ID / 暂缓字段不得出现。"""

    kept = (
        "courseNum",
        "courseName",
        "classNumber",
        "yearTerm",
        "score",
        "limitNumber",
        "selectedNumber",
        "teachingTimePlaceStr",
    )
    for field in kept:
        assert f'"{field}"' in collector_source, f"缺少必要字段：{field}"

    for forbidden in (
        "class_ID",
        "sumClassesID",
        "sumClassesNum",
        "courseId",
        "outLineId",
        "outlineTypeNum",
        "openingUnitName",
        "courseCategoryName",
        "teachingName",
        "examMode",
        "openingSchoolName",
        "readObj",
        "teachProgressSubmitState",
        "weekDay",
        "timePlaceId",
        "openClass",
    ):
        assert f'"{forbidden}"' not in collector_source, f"不得保留字段：{forbidden}"


def test_collector_redacts_teacher_in_segments(collector_source: str) -> None:
    assert 'REDACTED_TEACHER = "REDACTED"' in collector_source
    assert "redactSegmentTeacher" in collector_source
    assert "redactTeachingTimePlace" in collector_source
    # 5 / 6 字段判定与 teacher 下标
    assert "fields.length !== 5 && fields.length !== 6" in collector_source
    assert "fields.length === 6 ? 4 : 3" in collector_source
    # 最多一个 trailing comma
    assert "trailingEmpty > 1" in collector_source


def test_collector_source_is_plain_utf8_without_bom() -> None:
    """源码必须是 UTF-8 且不含 BOM（本地打开 / 复制粘贴都不应出乱码）。"""

    raw = COLLECTOR_PATH.read_bytes()

    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")
