"""SYSU 浏览器端采集器的**静态安全守卫**（Phase 2B-2C1A / 2B-2C1B）。

本文件不执行 JS，只对 `tools/sysu_course_offering_collector.js` 做**源码级**检查，
确保它满足两轮的安全边界：

- 加载脚本**不自动发请求**（无顶层调用、无定时轮询、无并发分页）；
- 有 hostname guard；
- 有 `pageSize` 上限校验与最小延迟；
- 源码中**不出现**读取浏览器端认证状态、导出认证头、后端 HTTP 客户端等字样；
- `firstPageNo` 锁死为 1；空 teacher 不得被 `REDACTED` 静默修复；`toJson` 输出裸 bundle；
- **结构诊断**（2B-2C1B）只取第 1 页一次、只输出聚合统计、不产出 Capture Bundle、
  不改动 `collect()` 的 fail-closed 行为。

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
    """Capture Bundle 只保留 8 个必要字段；内部 ID / 暂缓字段不得进入最小化路径。

    ⚠️ **Phase 2B-2C1C 起本断言的作用域收窄**为「bundle 的保留字段清单 + 最小化函数」：
    C1C 的相关性诊断**允许**在**诊断配置**中引用这些字段名（只做存在性统计 /
    有限分类值计数，见本文件 C1C 段落），但**仍不得**把它们写进 `KEPT_ROW_FIELDS`，
    也不得放进最小化结果。**旧断言的本意（bundle 不夹带内部字段）一字未改。**
    """

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

    # bundle 的保留字段清单本身：只允许上面这 8 个
    start = collector_source.index("var KEPT_ROW_FIELDS = [")
    end = collector_source.index("];", start)
    kept_block = collector_source[start:end]

    for field in kept:
        assert f'"{field}"' in kept_block, f"KEPT_ROW_FIELDS 缺少必要字段：{field}"

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
        assert f'"{forbidden}"' not in kept_block, f"不得保留字段：{forbidden}"


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


# ---------------------------------------------------------------------------
# Phase 2B-2C1B：结构诊断（Schedule Presence Diagnostic）
# ---------------------------------------------------------------------------


def _diagnose_slice(collector_source: str) -> str:
    """截取 `diagnoseSchedulePresence` 的**代码**（不含前后 JSDoc）。

    依赖文件内的函数顺序：`summarizeSchedulePresence` → `diagnoseSchedulePresence` → `toJson`。
    """

    start = collector_source.index("async function diagnoseSchedulePresence")
    end = collector_source.index("function toJson(")
    assert start < end, "诊断函数应位于 toJson 之前"

    slice_ = collector_source[start:end]

    # 尾部会带上下一个函数的 JSDoc（注释里会提到 bundle / toJson 等），截断掉
    tail_comment = slice_.rfind("/**")
    if tail_comment != -1:
        slice_ = slice_[:tail_comment]

    return slice_


def test_diagnostic_is_exposed_and_not_auto_called(collector_source: str) -> None:
    """诊断入口必须显式暴露，且**加载脚本不得自动调用**。"""

    assert "diagnoseSchedulePresence: diagnoseSchedulePresence" in collector_source

    expose_index = collector_source.rindex("window.XuehangSysuCollector")
    remainder = collector_source[expose_index + len("window.XuehangSysuCollector") :]
    assert "diagnoseSchedulePresence(" not in remainder, "挂载之后不得自动调用诊断"


def test_diagnostic_uses_the_shared_request_path(collector_source: str) -> None:
    """诊断复用既有取页函数（不复制认证 / 请求逻辑）。"""

    # 1 处定义 + 每个"只取一页一次"的入口各 1 处调用
    # （`collect()` 是唯一的多页入口；2C1B / 2C1C 诊断各只调一次）
    assert collector_source.count("requestPage(") == collector_source.count("await requestPage(") + 1
    assert collector_source.count("await requestPage(") == 3

    slice_ = _diagnose_slice(collector_source)
    assert "await requestPage(" in slice_
    # ⛔ 不出现 raw fetch / 认证相关写法
    assert "fetch(" not in slice_
    assert "credentials" not in slice_


def test_diagnostic_is_pinned_to_page_one_once(collector_source: str) -> None:
    """固定 `pageNo=1` / `pageSize=200`，且不接受任何分页选项。"""

    assert "DIAGNOSTIC_PAGE_NO = 1" in collector_source
    assert "DIAGNOSTIC_PAGE_SIZE = 200" in collector_source

    slice_ = _diagnose_slice(collector_source)

    assert "requestPage(semester, DIAGNOSTIC_PAGE_NO, DIAGNOSTIC_PAGE_SIZE)" in slice_
    assert slice_.count("await requestPage(") == 1

    for forbidden in ("maxPages", "firstPageNo", "pageNo:", "pageSize:", "while (", "for ("):
        assert forbidden not in slice_, f"诊断不得出现分页 / 循环写法：{forbidden}"


def test_diagnostic_does_not_produce_capture_artifacts(collector_source: str) -> None:
    """诊断只统计：不产出 bundle、不做最小化 / 脱敏 / 序列化。"""

    slice_ = _diagnose_slice(collector_source)

    for forbidden in ("bundle", "minimizeRow", "redact", "toJson(", "CAPTURE_FORMAT"):
        assert forbidden not in slice_, f"诊断不得出现：{forbidden}"


def test_diagnostic_returns_only_aggregate_counts(collector_source: str) -> None:
    """返回值只有聚合统计，**不含** rows / 下标 / 课程号 / 教师 / 原文。"""

    slice_ = _diagnose_slice(collector_source)

    for key in (
        "semester: semester",
        "page_no: DIAGNOSTIC_PAGE_NO",
        "page_size: DIAGNOSTIC_PAGE_SIZE",
        "reported_total: data.total",
        "total_rows: summary.total_rows",
        "teachingTimePlaceStr: summary.teachingTimePlaceStr",
    ):
        assert key in slice_, f"诊断返回值缺少：{key}"

    for forbidden in (
        "rows: data.rows",
        "rows: rows",
        "row_index",
        "courseNum",
        "courseName",
        "classNumber",
        "teacher",
    ):
        assert forbidden not in slice_, f"诊断不得输出：{forbidden}"


def test_diagnostic_summary_buckets_are_exhaustive(collector_source: str) -> None:
    """纯函数 `summarizeSchedulePresence` 必须给出互斥且穷尽的五类统计。"""

    assert "function summarizeSchedulePresence(rows)" in collector_source

    start = collector_source.index("function summarizeSchedulePresence(rows)")
    end = collector_source.index("async function diagnoseSchedulePresence")
    slice_ = collector_source[start:end]

    for bucket in ("missing", "null", "empty_string", "non_empty_string", "other_type"):
        assert f"{bucket}: 0" in slice_, f"缺少统计桶：{bucket}"

    assert "total_rows: rows.length" in slice_
    # 统计只看字段是否存在 / 值种类，不读取任何业务字段
    for forbidden in ("courseNum", "classNumber", "teacher", "readObj"):
        assert forbidden not in slice_


def test_collect_still_fails_closed_on_missing_schedule_field(collector_source: str) -> None:
    """⛔ 诊断不得改动 `collect()` 的 fail-closed 行为。

    `minimizeRow` 仍要求 8 个必要字段齐备，缺任何一个都整体失败。
    """

    assert "条记录缺少字段：" in collector_source
    assert "Object.prototype.hasOwnProperty.call(row, field)" in collector_source

    # 只检查 minimizeRow 内部：不得出现"缺字段 → 跳过 / 补空 / 占位"的写法
    start = collector_source.index("function minimizeRow(")
    end = collector_source.index("function validatePagePayload(")
    minimize = collector_source[start:end]

    for workaround in ("continue;", "meetings: []", "meetings:[]", "return null", "catch"):
        assert workaround not in minimize, f"minimizeRow 不得出现 workaround：{workaround}"


# ---------------------------------------------------------------------------
# Reviewer 修复：错误信息里的行号必须是 1-based 人类行号
# ---------------------------------------------------------------------------


def test_collector_reports_one_based_human_row_numbers(collector_source: str) -> None:
    """⛔ 错误信息里的行号必须是**人类可读的 1-based 行号**。

    `Array.prototype.map` 的回调下标是 **0-based**；若直接透传，
    第 1 条记录会被报成"第 0 条"，和浏览器里看到的行号对不上。
    因此调用点必须显式 `+ 1`，并且参数名 / 文档必须说明它是 1-based 行号。
    """

    # ① 调用点：0-based 下标显式 + 1
    assert "minimizeRow(row, currentPageNo, rowIndex + 1)" in collector_source

    # ② 不得再出现"裸下标直接透传"的写法
    assert "minimizeRow(row, currentPageNo, rowIndex)" not in collector_source

    # ③ 参数名与文档必须写明"从 1 开始"
    assert "humanRowNo" in collector_source
    assert "从 1 开始" in collector_source


def test_collector_row_number_is_only_for_messages(collector_source: str) -> None:
    """行号只用于错误信息：**不得**进入最小化结果 / 数据字段 / 诊断统计。"""

    start = collector_source.index("function minimizeRow(")
    end = collector_source.index("function validatePagePayload(")
    minimize = collector_source[start:end]

    # 断言值只被拼进错误信息，不写进 minimized 对象
    assert "minimized[humanRowNo]" not in minimize
    assert "row_no" not in minimize
    assert "row_no" not in collector_source


# ---------------------------------------------------------------------------
# Phase 2B-2C1C：Missing Schedule Correlation Diagnostic
# ---------------------------------------------------------------------------

_CORRELATION_PURE_START = "var CORRELATION_PAGE_NO"
_CORRELATION_DIAGNOSTIC_START = "async function diagnoseMissingScheduleCorrelation("
_COLLECTOR_EXPOSE_START = "window.XuehangSysuCollector = {"


def _correlation_pure_slice(collector_source: str) -> str:
    """截取 C1C 的**常量 + 纯函数**（到诊断函数之前，不含诊断函数的 JSDoc）。"""

    start = collector_source.index(_CORRELATION_PURE_START)
    end = collector_source.index(_CORRELATION_DIAGNOSTIC_START)
    assert start < end, "C1C 的常量 / 纯函数应位于诊断函数之前"

    slice_ = collector_source[start:end]

    # 尾部会带上下一个函数（诊断）的 JSDoc，截断掉
    tail_comment = slice_.rfind("/**")
    if tail_comment != -1:
        slice_ = slice_[:tail_comment]

    return slice_


def _correlation_diagnostic_slice(collector_source: str) -> str:
    """截取 `diagnoseMissingScheduleCorrelation` 的**代码**（不含其上方的 JSDoc）。"""

    start = collector_source.index(_CORRELATION_DIAGNOSTIC_START)
    end = collector_source.index(_COLLECTOR_EXPOSE_START)
    assert start < end, "诊断函数应位于显式暴露段之前"

    return collector_source[start:end]


def _exposure_slice(collector_source: str) -> str:
    """截取 `window.XuehangSysuCollector = { ... }` 的**全局暴露面**。"""

    return collector_source[collector_source.index(_COLLECTOR_EXPOSE_START) :]


def _js_function_slice(collector_source: str, start_marker: str, end_marker: str) -> str:
    """截取单个函数的代码（不含其上方 JSDoc，也不含下一个函数的 JSDoc）。"""

    start = collector_source.index(start_marker)
    end = collector_source.index(end_marker)
    assert start < end, f"函数顺序异常：{start_marker}"

    slice_ = collector_source[start:end]

    tail_comment = slice_.rfind("/**")
    if tail_comment != -1:
        slice_ = slice_[:tail_comment]

    return slice_


def test_correlation_diagnostic_is_exposed_and_not_auto_called(collector_source: str) -> None:
    """诊断入口必须显式暴露，且**加载脚本不得自动调用**。"""

    assert (
        "diagnoseMissingScheduleCorrelation: diagnoseMissingScheduleCorrelation" in collector_source
    )

    expose_index = collector_source.rindex("window.XuehangSysuCollector")
    remainder = collector_source[expose_index + len("window.XuehangSysuCollector") :]
    assert "diagnoseMissingScheduleCorrelation(" not in remainder, "挂载之后不得自动调用相关性诊断"


def test_correlation_diagnostic_requests_page_one_once(collector_source: str) -> None:
    """⛔ C1C 只允许一次 `await requestPage(...)`：无 fetch / 无并发 / 无重试 / 无第二次请求。"""

    slice_ = _correlation_diagnostic_slice(collector_source)

    assert slice_.count("await requestPage(") == 1
    assert "requestPage(semester, CORRELATION_PAGE_NO, CORRELATION_PAGE_SIZE)" in slice_

    for forbidden in (
        "fetch(",
        "Promise.all",
        "Promise.allSettled",
        "Promise.race",
        "setInterval",
        "setTimeout",
        "sleep(",
        "while (",
        "for (",
        "CORRELATION_PAGE_NO +",
        "pageNo:",
    ):
        assert forbidden not in slice_, f"相关性诊断不得出现：{forbidden}"


def test_correlation_diagnostic_page_and_size_are_locked(collector_source: str) -> None:
    """固定 `pageNo = 1` / `pageSize = 200`，且**不**从 options 读取任何分页选项。"""

    # SYSU 已人工验证的取值（2C1B 引入）
    assert "DIAGNOSTIC_PAGE_NO = 1" in collector_source
    assert "DIAGNOSTIC_PAGE_SIZE = 200" in collector_source
    # C1C 直接复用同一口径，避免两处取值漂移
    assert "var CORRELATION_PAGE_NO = DIAGNOSTIC_PAGE_NO;" in collector_source
    assert "var CORRELATION_PAGE_SIZE = DIAGNOSTIC_PAGE_SIZE;" in collector_source

    slice_ = _correlation_diagnostic_slice(collector_source)

    for option in (
        "opts.pageNo",
        "opts.pageSize",
        "opts.firstPageNo",
        "opts.maxPages",
        "opts.delayMs",
        "opts.retry",
    ):
        assert option not in slice_, f"C1C 不得接收分页 / 限速 / 重试参数：{option}"

    # 唯一被读取的 options 字段就是 semester
    assert "opts.semester" in slice_
    assert slice_.count("opts.") == 1, "C1C 只允许读取 opts.semester"


def test_correlation_diagnostic_rejects_any_option_other_than_semester(
    collector_source: str,
) -> None:
    """⛔ 严格白名单：只接受 `semester`，其它任何 own key 都在**发请求之前**失败。

    覆盖：`{semester}` 放行；`{semester, pageSize}` / `{semester, foo}` /
    `{semester, fields}` 等一律拒绝（不是"已知参数黑名单"，而是白名单）。

    说明：本测试文件按既有约定**只做源码级检查**，不执行 JS；
    这里验证白名单逻辑与"早于请求"的时序确实写在代码里。
    """

    slice_ = _correlation_diagnostic_slice(collector_source)

    assert "var optionNames = Object.keys(opts);" in slice_
    assert 'return name !== "semester";' in slice_
    assert "if (unexpected.length > 0) {" in slice_

    # 时序：白名单校验必须早于唯一一次取页调用
    assert slice_.index("var optionNames = Object.keys(opts);") < slice_.index("await requestPage(")

    # ⛔ 不得再使用"已知参数黑名单"（可绕过）
    assert "CORRELATION_FORBIDDEN_OPTIONS" not in collector_source
    assert "hasOwnProperty.call(opts," not in collector_source

    # ⛔ 失败信息不回显调用方提供的键名
    assert "unexpected.join(" not in slice_
    assert "optionNames.join(" not in slice_


def test_correlation_helpers_are_internal_only(collector_source: str) -> None:
    """⛔ C1C 的字段级 summarizer 不得暴露到 `window.XuehangSysuCollector`。

    `summarizeCategoricalValues` 是**任意字段**的 generic summarizer：
    一旦公开，调用方就能绕过 C1C 的字段 allowlist，
    对 `timePlaceId` / 课程名等字段直接产生具体 value counts。
    三者都保持为 IIFE 内部实现。
    """

    exposure = _exposure_slice(collector_source)

    for forbidden in (
        "classifySchedulePresence",
        "summarizeFieldShape",
        "summarizeCategoricalValues",
    ):
        assert forbidden not in exposure, f"全局 exposure 不得包含：{forbidden}"

    # 也不得以"函数名: 函数名"的暴露写法出现在任何位置
    for forbidden in (
        "classifySchedulePresence:",
        "summarizeFieldShape:",
        "summarizeCategoricalValues:",
    ):
        assert forbidden not in collector_source, f"不得暴露：{forbidden}"

    # 通用分类值 summarizer 的暴露面必须为空（只允许 2C1B 的 schedule presence summarizer）
    assert "summarizeSchedulePresence: summarizeSchedulePresence" in exposure


def test_correlation_diagnostic_produces_no_capture_artifacts(collector_source: str) -> None:
    """⛔ C1C 不产出任何数据：不最小化、不脱敏、不序列化、不构造 bundle / pages。"""

    slice_ = _correlation_diagnostic_slice(collector_source)

    for forbidden in (
        "minimizeRow",
        "redactTeachingTimePlace",
        "redactSegmentTeacher",
        "toJson",
        "collect(",
        "bundle",
        "pages",
        "CAPTURE_FORMAT",
        "JSON.stringify",
        "localStorage",
        "sessionStorage",
        "indexedDB",
    ):
        assert forbidden not in slice_, f"相关性诊断不得出现：{forbidden}"


def test_correlation_diagnostic_return_path_has_no_raw_or_private_fields(
    collector_source: str,
) -> None:
    """⛔ 返回路径不得包含 Raw row / 课程标识 / 教师 / 内部 ID / 原文。"""

    slice_ = _correlation_diagnostic_slice(collector_source)

    for forbidden in (
        "courseNum",
        "courseName",
        "classNumber",
        "teachingName",
        "readObj",
        "class_ID",
        "courseId",
        "outLineId",
        "sumClassesID",
        "raw_rows",
        "rows: rows",
        "rows: data.rows",
        "teachingTimePlaceStr",
    ):
        assert forbidden not in slice_, f"相关性诊断返回路径不得包含：{forbidden}"

    for key in (
        "semester: semester",
        "page_no: CORRELATION_PAGE_NO",
        "page_size: CORRELATION_PAGE_SIZE",
        "reported_total: data.total",
        "total_rows: presence.total_rows",
        "schedule_presence: presence.buckets",
        "compared_rows: groups.missing.total + groups.non_empty_string.total",
        "ungrouped_rows: split.other_rows",
        "groups: groups",
    ):
        assert key in slice_, f"相关性诊断返回值缺少：{key}"


def test_correlation_pure_functions_keep_the_five_buckets(collector_source: str) -> None:
    """纯函数必须给出与 2C1B **同口径**的五桶分类（互斥且穷尽）。"""

    slice_ = _correlation_pure_slice(collector_source)

    assert "function classifySchedulePresence(row)" in slice_
    assert "function summarizePresenceBuckets(rows)" in slice_

    for bucket in ("missing", "null", "empty_string", "non_empty_string", "other_type"):
        assert f"{bucket}: 0" in slice_, f"缺少统计桶：{bucket}"

    # 与 2C1B 完全相同的判定写法
    assert "Object.prototype.hasOwnProperty.call(row, SCHEDULE_FIELD)" in slice_
    assert "value === null" in slice_
    assert 'value.trim() === "" ? "empty_string" : "non_empty_string"' in slice_
    assert "total_rows: rows.length" in slice_

    # 非对象 row 直接失败，不静默跳过
    assert "相关性诊断遇到非对象 row" in slice_


def test_correlation_splits_only_two_groups_and_keeps_ungrouped(collector_source: str) -> None:
    """只比较 missing / non_empty_string；其余形态只计数，**不**被塞进任何一组。"""

    slice_ = _correlation_pure_slice(collector_source)

    assert 'var CORRELATION_GROUP_MISSING = "missing";' in slice_
    assert 'var CORRELATION_GROUP_PRESENT = "non_empty_string";' in slice_
    assert "function splitRowsForCorrelation(rows)" in slice_
    assert "otherRows += 1" in slice_
    assert "other_rows: otherRows" in slice_

    # 只有两个分组分支，各 push 一次
    assert slice_.count("missingRows.push(") == 1
    assert slice_.count("presentRows.push(") == 1


def test_correlation_structural_fields_are_value_free(collector_source: str) -> None:
    """A 类字段只做存在性 / 类型统计：⛔ 无 value 列表、无具体取值。"""

    slice_ = _correlation_pure_slice(collector_source)

    assert (
        'var STRUCTURAL_ONLY_FIELDS = ["timePlaceId", "limitNumber", "selectedNumber"];' in slice_
    )

    shape = _js_function_slice(
        collector_source, "function summarizeFieldShape(", "function accumulateScalarEntry("
    )

    for bucket in (
        "missing: 0",
        "null: 0",
        "empty_string: 0",
        "non_empty_string: 0",
        "number: 0",
        "boolean: 0",
        "other_type: 0",
    ):
        assert bucket in shape, f"字段形态统计缺少桶：{bucket}"

    # ⛔ 结构字段统计里不得出现"取值列表 / 去重计数"这类会泄露具体值的输出
    for forbidden in ("values", "distinct_count", "values_suppressed", "String(value)"):
        assert forbidden not in shape, f"结构字段统计不得包含：{forbidden}"


def test_correlation_categorical_fields_are_the_agreed_six(collector_source: str) -> None:
    """B 类字段只允许约定的 6 个（禁止顺手扩大统计范围）。"""

    slice_ = _correlation_pure_slice(collector_source)

    for field in (
        "weekDay",
        "openClass",
        "teachProgressSubmitState",
        "courseCategoryName",
        "examMode",
        "openingUnitName",
    ):
        assert f'"{field}"' in slice_, f"缺少分类字段：{field}"


def test_correlation_categorical_values_use_safe_serialized_format(collector_source: str) -> None:
    """分类值必须序列化成字符串 + 保留原始类型，且**不用真实取值当 key**。"""

    slice_ = _correlation_pure_slice(collector_source)

    assert 'var SCALAR_TYPE_ORDER = ["boolean", "number", "string"];' in slice_
    assert "var serialized = String(value);" in slice_
    assert "entries.push({ type: type, value: serialized, count: 1 });" in slice_

    accumulate = _js_function_slice(
        collector_source, "function accumulateScalarEntry(", "function compareScalarEntries("
    )
    assert "entries[index].value === serialized" in accumulate
    assert "entries[index].count += 1;" in accumulate

    # ⛔ 真实取值不得成为 object / Map / Set 的键
    for forbidden in ("entries[serialized]", "counts[", "new Map(", "new Set(", "Object.create(null)"):
        assert forbidden not in accumulate, f"累加实现不得出现：{forbidden}"


def test_correlation_suppresses_high_cardinality_values(collector_source: str) -> None:
    """⛔ distinct > MAX_DISTINCT_VALUES → 整体 suppression（不返回前 N / 最常见 N 个）。"""

    slice_ = _correlation_pure_slice(collector_source)
    categorical = _js_function_slice(
        collector_source, "function summarizeCategoricalValues(", "function summarizeCorrelationGroup("
    )

    assert "var MAX_DISTINCT_VALUES = 20;" in slice_
    assert "if (entries.length > MAX_DISTINCT_VALUES) {" in categorical
    assert "summary.values_suppressed = true;" in categorical
    assert "summary.values = [];" in categorical
    assert "summary.distinct_count = entries.length;" in categorical

    # ⛔ 不得有任何"取前 N / 最常见 N"的选择逻辑
    for forbidden in ("slice(0", "splice(", "left.count - right.count", "right.count - left.count"):
        assert forbidden not in categorical, f"分类值统计不得出现：{forbidden}"

    # 顺序必须与出现次数无关（只按类型 + 序列化文本）
    comparator = _js_function_slice(
        collector_source, "function compareScalarEntries(", "function summarizeCategoricalValues("
    )
    assert "left.value < right.value" in comparator
    assert "count" not in comparator, "排序不得依赖出现次数"


def test_correlation_invariants_are_checked_in_code(collector_source: str) -> None:
    """⛔ 计数不变量必须在代码里显式校验（不允许静默丢 row）。

    说明：本测试文件按既有约定**只做源码级检查**，不执行 JS；
    这里验证的是"不变量确实被写成断言，且在 return 之前调用"。
    """

    slice_ = _correlation_pure_slice(collector_source)

    assert "function assertFieldTotals(groupName, group)" in slice_
    assert "function assertCorrelationInvariants(presence, split, groups)" in slice_

    for check in (
        "bucketTotal !== presence.total_rows",
        "groups.missing.total !== buckets.missing",
        "groups.non_empty_string.total !== buckets.non_empty_string",
        "split.other_rows !== buckets.null + buckets.empty_string + buckets.other_type",
        "summary.other_type + summary.scalar_count !== summary.total",
        "sumListedCounts(summary.values) !== summary.scalar_count",
    ):
        assert check in slice_, f"缺少不变量检查：{check}"

    diagnostic = _correlation_diagnostic_slice(collector_source)

    assert "assertCorrelationInvariants(presence, split, groups);" in diagnostic
    assert diagnostic.index("assertCorrelationInvariants(presence, split, groups);") < diagnostic.index(
        "return {"
    ), "不变量校验必须发生在 return 之前"


def test_correlation_diagnostic_does_not_touch_collect_or_2c1b(collector_source: str) -> None:
    """2C1B 入口与 `collect()` 保持原样：C1C 只是**并列**的第三个入口。"""

    # 2C1B 入口仍在，且仍只取第 1 页一次
    diagnose = _js_function_slice(
        collector_source, "async function diagnoseSchedulePresence(", "function toJson("
    )
    assert diagnose.count("await requestPage(") == 1
    assert "requestPage(semester, DIAGNOSTIC_PAGE_NO, DIAGNOSTIC_PAGE_SIZE)" in diagnose
    assert "summarizeSchedulePresence(data.rows)" in diagnose

    # C1C 不得被 collect() 调用（它只是并列入口，不参与生产链路）
    start = collector_source.index("async function collect(")
    end = collector_source.index("// 结构诊断（Phase 2B-2C1B）")
    collect_body = collector_source[start:end]

    for forbidden in (
        "diagnoseMissingScheduleCorrelation",
        "classifySchedulePresence",
        "summarizeCategoricalValues",
        "summarizeFieldShape",
    ):
        assert forbidden not in collect_body, f"collect() 不得引入 C1C：{forbidden}"
