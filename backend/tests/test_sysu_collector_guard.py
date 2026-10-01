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
# Reviewer 修复：firstPageNo 锁死 / teacher 非空 / toJson 裸 bundle
# ---------------------------------------------------------------------------


def test_collector_locks_first_page_no_to_verified_value(collector_source: str) -> None:
    """⛔ SYSU 只验证过 firstPageNo=1：不允许调用方传入其它起始页。

    - 常量保持 1；
    - 传入非 1 时**在发请求之前**失败；
    - 实际使用的一律是常量 `FIRST_PAGE_NO`（不再有"取调用方值"的回退写法）。
    """

    assert "FIRST_PAGE_NO = 1" in collector_source

    # 显式拒绝非 1 的起始页
    assert "opts.firstPageNo !== undefined" in collector_source
    assert "opts.firstPageNo !== FIRST_PAGE_NO" in collector_source

    # 实际值恒为常量：不得再出现"取 opts.firstPageNo / 默认值"的三元回退
    assert "var firstPageNo = FIRST_PAGE_NO;" in collector_source
    assert "opts.firstPageNo === undefined ?" not in collector_source

    # 校验必须发生在**任何取页调用之前**（requestPage 是唯一会 fetch 的函数）
    assert collector_source.index(
        "opts.firstPageNo !== FIRST_PAGE_NO"
    ) < collector_source.index("await requestPage(")


def test_collector_rejects_empty_teacher_before_redaction(collector_source: str) -> None:
    """⛔ 空 teacher 不得被 REDACTED **静默修复**（那会掩盖原始数据问题）。"""

    assert 'typeof teacher !== "string"' in collector_source
    assert 'teacher.trim() === ""' in collector_source

    # 校验必须早于写入占位符
    check_index = collector_source.index('teacher.trim() === ""')
    assign_index = collector_source.index("fields[teacherIndex] = REDACTED_TEACHER;")
    assert check_index < assign_index, "必须先校验 teacher 非空，再替换为 REDACTED"


def test_collector_teacher_error_message_does_not_echo_value(collector_source: str) -> None:
    """teacher 相关错误信息不得回显 teacher 取值。"""

    check_index = collector_source.index('teacher.trim() === ""')
    # 该分支内只允许出现结构性文字，不得拼进 teacher 变量
    window = collector_source[check_index : check_index + 400]

    assert "+ teacher" not in window
    assert "teacher +" not in window


def test_collector_to_json_emits_bare_bundle(collector_source: str) -> None:
    """`toJson()` 必须输出**裸** Capture Bundle（顶层即 bundle 键）。

    这样 `load_capture_bundle(...)` 可以直接吃下 `toJson` 的输出。
    """

    assert "JSON.stringify(result.bundle, null, 2)" in collector_source
    # 不得再序列化整个 wrapper
    assert "JSON.stringify(result, null, 2)" not in collector_source


def test_collector_to_json_refuses_cancelled_or_empty_result(collector_source: str) -> None:
    """⛔ 取消或没有 bundle 时 `toJson()` 必须失败，不生成伪 bundle。"""

    assert "result.cancelled === true" in collector_source
    assert "!result.bundle" in collector_source

    # 拒绝分支必须早于真正序列化
    reject_index = collector_source.index("result.cancelled === true")
    serialize_index = collector_source.index("JSON.stringify(result.bundle, null, 2)")
    assert reject_index < serialize_index


def test_collector_bundle_keys_match_python_bridge_expectation(collector_source: str) -> None:
    """bundle 顶层键必须与 Python Capture Bridge 的校验键一致（`first_page_no` 等 snake_case）。"""

    for key in ("format", "semester", "first_page_no", "page_size", "pages"):
        assert key + ":" in collector_source, f"bundle 缺少键：{key}"

    # 不得把 SYSU 的 camelCase 请求参数名写进 bundle 元数据
    assert "firstPageNo: firstPageNo" not in collector_source
    assert "pageSize: pageSize," in collector_source  # 仅出现在请求 body 中


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
