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

import re
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
    """⛔ 同一 endpoint 的相邻请求下限 = **30000ms**（conservative operational minimum）。

    来源是**人工实测**（短间隔连续请求稳定 `HTTP 600 / 系统异常`）；
    ⛔ 不声称是学校官方阈值。
    """

    assert "MIN_DELAY_MS = 30000" in collector_source
    assert "DEFAULT_DELAY_MS = 30000" in collector_source
    assert "delayMs < MIN_DELAY_MS" in collector_source
    # ⛔ 旧的更小取值不得残留
    assert "MIN_DELAY_MS = 1000;" not in collector_source
    assert "DEFAULT_DELAY_MS = 1500;" not in collector_source
    assert "MIN_DELAY_MS = 10000;" not in collector_source
    assert "DEFAULT_DELAY_MS = 10000;" not in collector_source


def test_collector_enforces_global_batch_pacing_constants(collector_source: str) -> None:
    """⛔ 全局 batch pacing：每 5 个成功请求冷却 5 分钟（保守运营策略）。

    ⚠️ 人工 sustained pacing 实测：`pageSize=50` + 30 秒间隔连续 7 次成功后
    第 8 次即 `HTTP 600`；⇒ "5-request batch + 5-minute cooldown"
    **不是学校公开阈值**。
    """

    assert "MAX_REQUESTS_PER_BATCH = 5" in collector_source
    assert "BATCH_COOLDOWN_MS = 300000" in collector_source
    # ⛔ 不接受调用方覆盖 batch 大小 / 冷却时长（白名单里没有这两个键）
    assert "MAX_REQUESTS_PER_BATCH = 5;" in collector_source and (
        "opts.maxRequestsPerBatch" not in collector_source
    )
    assert "opts.batchCooldownMs" not in collector_source
    assert '"maxRequestsPerBatch"' not in collector_source
    assert '"batchCooldownMs"' not in collector_source


def test_collector_has_exactly_one_global_pacing_controller(collector_source: str) -> None:
    """⛔ 等待与批次计数只允许存在于**一个**全局 pacing controller 里。

    ```text
    第 1 个请求            → 立即发送
    其它请求（前一批未满）  → sleep(delayMs)
    前一批已满 5 个成功请求 → sleep(max(BATCH_COOLDOWN_MS, delayMs))
    ```
    """

    assert collector_source.count("function createRequestPacer(") == 1
    # 定义 1 处 + 四个入口各创建 1 个（每次 run 恰好一个 controller）；
    #   `collect()` / `collectSharded()` 是生产入口，
    #   `diagnoseLayoutBCandidates()` 是**一次性零留存诊断**（多页请求 ⇒ 同样必须受同一 pacing 约束），
    #   `diagnoseLayoutBFieldSourcePart()` 是**分段式诊断**（每段一个 controller，同样不自己 sleep）。
    # 只看代码，不看注释。
    assert _collector_code_only(collector_source).count("createRequestPacer(") == 5

    pacer = _js_function_slice(
        collector_source, "function createRequestPacer(", "function requireAllowedHost("
    )

    # 全文件只有两处等待，且都在 controller 内
    assert collector_source.count("await sleep(") == 2
    assert pacer.count("await sleep(") == 2

    assert "if (isFirstRequest) {" in pacer, "第 1 个请求必须立即发送"
    assert "successfulInBatch >= MAX_REQUESTS_PER_BATCH" in pacer
    assert "Math.max(BATCH_COOLDOWN_MS, delayMs)" in pacer, (
        "批次边界只等冷却（若 delayMs 更大则取较大者），⛔ 不叠加"
    )

    # ⛔ 等待时长不得写成字面量
    assert re.search(r"await sleep\(\s*[0-9]", collector_source) is None


def test_collector_does_not_duplicate_pacing_outside_the_controller(
    collector_source: str,
) -> None:
    """⛔ baseline / 分页核心 / shard 循环里**不得**再各自等待或各自计数。"""

    blocks = {
        "collectPages": _js_function_slice(
            collector_source, "async function collectPages(", "async function requestReportedTotal("
        ),
        "requestReportedTotal": _js_function_slice(
            collector_source, "async function requestReportedTotal(", "async function collect("
        ),
        "collectSharded": _collect_sharded_slice(collector_source),
    }

    for name, block in blocks.items():
        assert "await sleep(" not in block, f"{name} 不得自己等待（必须交给全局 pacer）"
        assert "successfulInBatch" not in block, f"{name} 不得自己维护批次计数"


def test_collector_every_paced_request_goes_through_the_controller(
    collector_source: str,
) -> None:
    """⛔ 每个受 pacing 的请求都必须在 `requestPage()` 里经过同一个 controller。"""

    # 发请求之前统一等一次；响应校验成功之后统一记一次成功
    assert collector_source.count("pacer.beforeRequest()") == 1
    assert collector_source.count("pacer.noteSuccess()") == 1

    # 分页核心与 baseline 探针都把 pacer 传下去
    assert (
        "requestPage(semester, currentPageNo, pageSize, openingSchoolNumber, pacer)"
        in collector_source
    )
    assert "requestPage(semester, FIRST_PAGE_NO, SHARD_PAGE_SIZE, undefined, pacer)" in (
        collector_source
    )

    # baseline_before 与 baseline_after 走同一个 controller（同一个 run 的全局计数）
    assert collector_source.count("requestReportedTotal(resolved.semester, pacer)") == 2

    # 两个分页调用点（collect / 每个 shard）都传入 pacer
    for marker in ("var core = await collectPages(", "core = await collectPages("):
        index = collector_source.index(marker)
        window = collector_source[index : index + 260]
        assert "pacer" in window, f"{marker} 必须把 pacer 传下去"

    # ⛔ 2C1B / 2C1C 一次性诊断仍然不传 pacer（它们各自只发 1 次请求、不受批次影响）；
    # ⚠️ Layout B 诊断是**多页**的，因此必须传 pacer（否则会绕过全局批次冷却）。
    assert "requestPage(semester, DIAGNOSTIC_PAGE_NO, DIAGNOSTIC_PAGE_SIZE)" in collector_source
    assert "requestPage(semester, CORRELATION_PAGE_NO, CORRELATION_PAGE_SIZE)" in collector_source


def test_collector_does_not_add_retry_backoff_skip_or_resume(collector_source: str) -> None:
    """⛔ `HTTP 600` 仍然只是 fail closed：⛔ 不重试、⛔ 不 backoff 重试、
    ⛔ 不跳页、⛔ 不续采、⛔ 不做任何认证绕行。

    ⚠️ 说明性文字里会出现"backoff"（"不做 backoff 重试"），
    因此本断言只看**非注释代码行**。
    """

    code = _collector_code_only(collector_source)

    for token in ("retry", "backoff", "resume", "skip", "attempt", "setInterval"):
        assert token not in code, f"⛔ 不得出现重试 / 跳页 / 续采 / 定时轮询写法：{token}"


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
    """⛔ 空 teacher 不得被 REDACTED **静默修复**（那会掩盖原始数据问题）。

    2026-1 真实证据后 teacher 可能出现在两类结构里（5 字段 B / 6 字段），
    因此**两个分支都必须**先校验非空、再写占位符。
    """

    assert 'typeof teacher5 !== "string"' in collector_source
    assert 'typeof teacher6 !== "string"' in collector_source

    # 每个分支的校验都必须早于该分支的占位符写入
    pairs = (
        ('teacher5.trim() === ""', "fields[3] = REDACTED_TEACHER;"),
        ('teacher6.trim() === ""', "fields[4] = REDACTED_TEACHER;"),
    )
    for check, assign in pairs:
        assert check in collector_source, f"缺少校验：{check}"
        assert assign in collector_source, f"缺少赋值：{assign}"
        assert collector_source.index(check) < collector_source.index(assign), (
            f"必须先校验 teacher 非空，再替换为 REDACTED：{check}"
        )


def test_collector_teacher_error_message_does_not_echo_value(collector_source: str) -> None:
    """teacher 相关错误信息不得回显 teacher 取值。"""

    for check in ('teacher5.trim() === ""', 'teacher6.trim() === ""'):
        check_index = collector_source.index(check)
        # 该分支内只允许出现结构性文字，不得拼进 teacher 变量
        window = collector_source[check_index : check_index + 400]

        assert "+ teacher5" not in window
        assert "teacher5 +" not in window
        assert "+ teacher6" not in window
        assert "teacher6 +" not in window


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


def _bundle_literal_slices(collector_source: str) -> list[str]:
    """所有 `bundle: { ... }` 字面量的文本切片（用于检查**bundle 顶层键**）。

    ⚠️ 作用域说明：本轮起有两个 bundle 构造点（`collect()` 与五校区编排里
    每个 shard 各一份），因此"bundle 顶层必须是 snake_case"这条断言必须
    按**字面量**检查，而不是对全文做子串检查 —— 全文里合法地存在
    camelCase 的 JS 局部对象（例如 `resolvePagingOptions()` 的返回值）。
    """

    slices: list[str] = []
    cursor = 0

    while True:
        start = collector_source.find("bundle: {", cursor)
        if start == -1:
            break
        end = collector_source.find("}", start)
        assert end != -1, "bundle 字面量没有闭合"
        slices.append(collector_source[start:end])
        cursor = end + 1

    return slices


def test_collector_bundle_keys_match_python_bridge_expectation(collector_source: str) -> None:
    """bundle 顶层键必须与 Python Capture Bridge 的校验键一致（`first_page_no` 等 snake_case）。"""

    for key in ("format", "semester", "first_page_no", "page_size", "pages"):
        assert key + ":" in collector_source, f"bundle 缺少键：{key}"

    # ⛔ 每一个 bundle 字面量的顶层键都必须是 snake_case
    literals = _bundle_literal_slices(collector_source)
    assert len(literals) == 2, "预期恰好两个 bundle 构造点（collect / 五校区 shard）"

    for literal in literals:
        for key in ("format:", "semester:", "first_page_no:", "page_size:", "pages:"):
            assert key in literal, f"bundle 字面量缺少键：{key}"

        for camel in ("firstPageNo:", "pageSize:", "pageNo:"):
            assert camel not in literal, f"bundle 顶层不得使用 camelCase 请求参数名：{camel}"

    # 请求 body 仍用 camelCase（只出现在请求里）
    assert "pageSize: pageSize," in collector_source


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
    # 4 / 5 / 6 字段判定（未知字段数仍 fail closed）
    assert "fieldCount !== 4" in collector_source
    assert "fieldCount !== 5" in collector_source
    assert "fieldCount !== 6" in collector_source
    # 5 字段必须**严格三态判别**，⛔ 不得无条件把 fields[3] 当 teacher
    assert "classifyFiveFieldToken(fields[3])" in collector_source
    # teacher 只在明确的两个分支被替换
    assert "fields[3] = REDACTED_TEACHER;" in collector_source
    assert "fields[4] = REDACTED_TEACHER;" in collector_source
    # 最多一个 trailing comma
    assert "trailingEmpty > 1" in collector_source


def test_collector_location_grammar_matches_python_parser(collector_source: str) -> None:
    """Collector 的 5 字段判别必须与 Python `_classify_five_field_token()` **同规则**。

    收紧后的三态规则：
    `无 "-"` → teacher；`>= 3 个非空 "-" 分段` → location；其余 → ambiguous（fail closed）。
    """

    assert "function classifyFiveFieldToken(token)" in collector_source
    assert "function countNonEmptyDashSegments(token)" in collector_source
    # 门槛常量与 Python `_MIN_LOCATION_SEGMENTS` 一致
    assert "MIN_LOCATION_SEGMENTS = 3" in collector_source
    # 三态返回值
    assert 'return "teacher";' in collector_source
    assert 'return "location";' in collector_source
    assert 'return "ambiguous";' in collector_source
    # 二义必须 fail closed（⛔ 不得静默当 teacher / location）
    assert "classification === \"ambiguous\"" in collector_source


def test_collector_does_not_reuse_generic_location_grammar_for_five_fields(
    collector_source: str,
) -> None:
    """⛔ 5 字段**不得**复用宽松的通用 grammar 判定。

    旧实现用 `isLocationToken(fields[3])`（"非空园区 + `-` + 非空教室"）判别 5 字段，
    会把 `A-B` 这种两段 token 判成 location。收紧后必须走 `classifyFiveFieldToken`。
    """

    assert "isLocationToken(fields[3])" not in collector_source
    assert "classifyFiveFieldToken(fields[3])" in collector_source


def test_collector_non_concrete_two_field_grammar_matches_python_parser(
    collector_source: str,
) -> None:
    """Collector 的 non-concrete 2 字段 grammar 必须与 Python **同规则**。

    即 `<weeks token><已确认 qualifier>`：整段匹配、白名单而非通配，
    ⛔ 不得放开为"任意 2 字段"。
    """

    assert "NON_CONCRETE_FIRST_FIELD" in collector_source
    # 整段匹配（`^...$`），且周次部分要求 `N-M周`
    assert r"/^([0-9]+-[0-9]+周)(校外|校内\(户外\))$/" in collector_source
    assert "SCHEDULE_QUALIFIER_OFF_CAMPUS" in collector_source
    assert "SCHEDULE_QUALIFIER_ON_CAMPUS_OUTDOOR" in collector_source
    # ⛔ 不得无条件接受任意 2 字段
    assert "fieldCount === 2" in collector_source
    assert "NON_CONCRETE_FIRST_FIELD.test(fields[0].trim())" in collector_source


def test_collector_three_field_supports_confirmed_qualifier_whitelist(
    collector_source: str,
) -> None:
    """3 字段须支持 `<weeks><已确认 qualifier>` / teacher / activity。

    ⛔ qualifier 是**白名单**（当前 `校外` 与 `校内(户外)`），不得泛化为任意 suffix；
    ⛔ 不得因为第一个字段带 qualifier 就跳过 teacher 脱敏。
    """

    # 先把 weeks 与 qualifier 拆开
    assert "WEEKS_WITH_OPTIONAL_QUALIFIER" in collector_source
    assert r"/^([0-9]+-[0-9]+周)(.+)?$/" in collector_source
    assert "KNOWN_QUALIFIER_EXACT" in collector_source
    assert r"/^(校外|校内\(户外\))$/" in collector_source
    # 白名单校验先于脱敏
    assert "KNOWN_QUALIFIER_EXACT.test(qualifier3)" in collector_source
    # teacher 仍在 fields[1] 被替换
    assert "fields[1] = REDACTED_TEACHER;" in collector_source


def test_collector_rejects_unknown_qualifier_without_echo(
    collector_source: str,
) -> None:
    """⛔ 未确认 qualifier 必须 fail closed，且不回显取值。"""

    # 拒绝分支存在
    assert "qualifier 尚未被真实证据确认" in collector_source
    # 错误信息里不得拼进 qualifier 变量本身
    index = collector_source.index("qualifier 尚未被真实证据确认")
    window = collector_source[max(0, index - 400) : index + 200]
    assert "qualifier3" not in window or "+ qualifier3" not in window


def test_collector_non_concrete_three_field_redacts_teacher_field(
    collector_source: str,
) -> None:
    """3 字段 non-concrete（`weeks` / `teacher` / `activity`）必须脱敏 `fields[1]`。

    ⛔ 不得把 teacher 当成 location；⛔ 不得跳过脱敏；
    weeks 与 activity 必须原样保留。
    """

    assert "fieldCount === 3" in collector_source
    # 周次 token 用普通 `N-M周` 形状（与 Python `is_plain_week_range()` 同规则）
    assert "PLAIN_WEEK_RANGE" in collector_source
    assert r"/^([0-9]+)-([0-9]+)周$/" in collector_source
    # teacher 在 fields[1] 被替换
    assert "fields[1] = REDACTED_TEACHER;" in collector_source
    # 空 teacher 必须 fail closed（不得写占位符掩盖）
    assert "中 teacher 字段为空或不是字符串" in collector_source


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

    # 1 处定义 + 每个取页入口各 1 处调用：
    #   `collectPages()` 分页循环（`collect()` 与每个 shard 都走它）、
    #   `requestReportedTotal()` baseline 探针、
    #   2C1B / 2C1C 诊断各只调一次、
    #   Layout B 一次性诊断（**分页**，因此复用同一取页函数 + 同一 pacer）、
    #   分段式 f3 字段来源诊断（同样分页 + 同一 pacer）。
    # ⚠️ 只看**代码**（注释里也提到 `requestPage()`）。
    code = _collector_code_only(collector_source)
    assert code.count("requestPage(") == code.count("await requestPage(") + 1
    assert code.count("await requestPage(") == 6

    # 唯一的 `fetch(` 仍在 `requestPage` 内部（⛔ 新增入口不得自己发请求）
    assert collector_source.count("fetch(") == 1

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


def _minimize_row_code(collector_source: str) -> str:
    """`minimizeRow` 的**纯代码**（去掉 JSDoc 与行注释）。

    ⚠️ 行注释里会出现"不放行 `null` / 空串"这类**说明性**文字，
    因此"不得出现占位写法"类断言必须只看代码，不能看注释。
    """

    body = _js_function_slice(
        collector_source, "function minimizeRow(", "function validatePagePayload("
    )

    return "\n".join(line.split("//")[0] for line in body.splitlines())


def test_collect_allows_only_missing_schedule_field(collector_source: str) -> None:
    """⛔ DG-07B：`collect()` **只**允许 `teachingTimePlaceStr` **属性不存在**。

    这是原 `test_collect_still_fails_closed_on_missing_schedule_field` 的**翻转替代**：
    该用例锁定的"8 个字段全必需"不变量已被 DG-07B 取代，但**不是**放宽为"缺任何字段都行"。

    锁定：

    - A. 基础必需字段集合**恰好是 7 个**（不含排课字段）；
    - B. 最小化循环遍历的是 `REQUIRED_ROW_FIELDS`（缺任一 → FAIL）；
    - C. 排课字段用 `hasOwnProperty` 判定：**不存在就直接返回**（key 保持不存在）；
    - D. 属性**存在**时仍调用原 `redactTeachingTimePlace(`；
    - E. 不得出现占位值（`null` / `""` / `UNKNOWN` / `N/A`）；
    - F. `minimizeRow` 内没有 catch / fallback / skip row。
    """

    minimize = _minimize_row_code(collector_source)

    # A. 基础必需字段恰好 7 个，且**不含** teachingTimePlaceStr
    required_start = collector_source.index("var REQUIRED_ROW_FIELDS = [")
    required_end = collector_source.index("];", required_start)
    required_block = collector_source[required_start:required_end]

    for field in (
        "courseNum",
        "courseName",
        "classNumber",
        "yearTerm",
        "score",
        "limitNumber",
        "selectedNumber",
    ):
        assert f'"{field}"' in required_block, f"REQUIRED_ROW_FIELDS 缺少：{field}"

    assert '"teachingTimePlaceStr"' not in required_block, (
        "teachingTimePlaceStr 不得进入 REQUIRED_ROW_FIELDS（DG-07B 起它允许属性不存在）"
    )

    # B. 循环必须遍历 REQUIRED_ROW_FIELDS（不是 KEPT_ROW_FIELDS）
    assert "REQUIRED_ROW_FIELDS.length" in minimize
    assert "KEPT_ROW_FIELDS.length" not in minimize

    # C. 只有**属性不存在**才提前返回，且不写入任何占位值
    assert "if (!Object.prototype.hasOwnProperty.call(row, SCHEDULE_FIELD)) {" in minimize
    assert "return minimized;" in minimize

    # D. 属性存在 → 仍必须脱敏
    assert "minimized[SCHEDULE_FIELD] = redactTeachingTimePlace(" in minimize

    # E. 不得出现任何占位 / 伪造写法（只看代码）
    for placeholder in (
        "null",
        '""',
        "UNKNOWN",
        "N/A",
        "teachingTimePlaceStr:",
        "meetings:",
    ):
        assert placeholder not in minimize, f"minimizeRow 不得出现占位写法：{placeholder}"

    # F. 不得吞异常 / 跳过 row
    for workaround in ("continue;", "catch", "try", "return null"):
        assert workaround not in minimize, f"minimizeRow 不得出现 workaround：{workaround}"


def test_collect_still_fails_closed_on_other_missing_base_fields(collector_source: str) -> None:
    """⛔ 除排课字段外的 **7 个基础字段**缺任意一个仍必须整体失败。"""

    assert "条记录缺少字段：" in collector_source
    assert "Object.prototype.hasOwnProperty.call(row, field)" in collector_source

    minimize = _minimize_row_code(collector_source)

    # 基础字段校验必须发生在"排课字段特例"之前
    base_check = minimize.index("条记录缺少字段：")
    schedule_exception = minimize.index(
        "Object.prototype.hasOwnProperty.call(row, SCHEDULE_FIELD)"
    )
    assert base_check < schedule_exception, (
        "基础字段校验必须早于排课字段特例，避免排课字段特例把基础字段也放行"
    )


def test_collect_does_not_duplicate_sensitive_field_sets(collector_source: str) -> None:
    """⛔ DG-07B 未扩大采集字段集合：仍只保留 8 个字段，未新增任何字段。"""

    start = collector_source.index("var KEPT_ROW_FIELDS = [")
    end = collector_source.index("];", start)
    kept_block = collector_source[start:end]

    for field in (
        "courseNum",
        "courseName",
        "classNumber",
        "yearTerm",
        "score",
        "limitNumber",
        "selectedNumber",
        "teachingTimePlaceStr",
    ):
        assert f'"{field}"' in kept_block, f"KEPT_ROW_FIELDS 缺少：{field}"

    for forbidden in (
        "timePlaceId",
        "weekDay",
        "openingUnitName",
        "readObj",
        "openClass",
        "teachProgressSubmitState",
        "courseCategoryName",
        "examMode",
        "teachingName",
    ):
        assert f'"{forbidden}"' not in kept_block, f"不得采集字段：{forbidden}"

    assert "sysu-opening-courses-capture-v1" in collector_source, "Capture 格式标识不得升级"


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


def _collector_code_only(collector_source: str) -> str:
    """去掉**整行注释**后的源码（用于"某写法是否真的出现在代码里"的计数）。

    ⚠️ 说明性文字里会提到 `createRequestPacer()` / `requestPage()` / `backoff` 等，
    因此这类断言必须只看**非注释代码行**，否则计数会被文档带偏。
    """

    return "\n".join(
        line
        for line in collector_source.splitlines()
        if not line.lstrip().startswith(("*", "//", "/*"))
    )


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
    end = collector_source.index(_SHARDED_SECTION_START)
    collect_body = collector_source[start:end]

    for forbidden in (
        "diagnoseMissingScheduleCorrelation",
        "classifySchedulePresence",
        "summarizeCategoricalValues",
        "summarizeFieldShape",
    ):
        assert forbidden not in collect_body, f"collect() 不得引入 C1C：{forbidden}"


# ---------------------------------------------------------------------------
# 五校区 shard 编排（Architecture Review 已批准）
#
#   baseline_before → 五校区串行 collect → baseline_after → 外层 diagnostics
#
# ⛔ 本段仍是**源码级**检查；运行时行为由
# `node --test tools/sysu_course_offering_collector.test.mjs` 覆盖。
# ---------------------------------------------------------------------------

_SHARDED_SECTION_START = "// 五校区 shard 编排（Architecture Review 已批准）"
_SHARDED_DIAGNOSTIC_START = "async function collectSharded("
_COLLECT_CORE_START = "async function collectPages("
_SHARDED_BUNDLE_START = "function shardBundle("

_SHARDED_CAMPUS_CONSTANTS = (
    ("东校园", "5063559"),
    ("北校园", "5062202"),
    ("南校园", "5062201"),
    ("深圳校区", "333291143"),
    ("珠海校区", "5062203"),
)


def _approved_shards_slice(collector_source: str) -> str:
    """`APPROVED_SHARDS` 常量块（**唯一**的 shard 清单定义处）。"""

    start = collector_source.index("var APPROVED_SHARDS = [")
    end = collector_source.index("];", start)

    return collector_source[start:end]


def _sharded_section_slice(collector_source: str) -> str:
    """整个五校区编排段（常量除外，常量在文件顶部的常量区）。"""

    start = collector_source.index(_SHARDED_SECTION_START)
    end = collector_source.index("// 结构诊断（Phase 2B-2C1B）")

    return collector_source[start:end]


def _collect_sharded_slice(collector_source: str) -> str:
    """`collectSharded()` 的函数体（含嵌套的 `makeDiagnostics()`）。"""

    start = collector_source.index(_SHARDED_DIAGNOSTIC_START)
    end = collector_source.index(_SHARDED_BUNDLE_START)

    return collector_source[start:end]


def test_sharded_constants_are_the_five_approved_campuses(collector_source: str) -> None:
    """⛔ shard 清单**只能**是已人工取证的五个校区（不猜、不自动发现）。"""

    block = _approved_shards_slice(collector_source)

    assert block.count("shard_id:") == 5

    for shard_id, opening_school_number in _SHARDED_CAMPUS_CONSTANTS:
        assert f'shard_id: "{shard_id}"' in block
        assert f'openingSchoolNumber: "{opening_school_number}"' in block

    # 每个已批准校区号在**整个源码**里只出现一次（不散落在多处）
    for _, opening_school_number in _SHARDED_CAMPUS_CONSTANTS:
        assert collector_source.count(f'"{opening_school_number}"') == 1


def test_sharded_entry_is_exposed_and_not_auto_called(collector_source: str) -> None:
    """五校区入口必须显式暴露，且**加载脚本不得自动调用**。"""

    assert "collectSharded: collectSharded" in collector_source

    expose_index = collector_source.rindex("window.XuehangSysuCollector")
    remainder = collector_source[expose_index + len("window.XuehangSysuCollector") :]

    assert "collectSharded(" not in remainder, "挂载之后不得自动调用五校区采集"
    assert "shardBundle(" not in remainder
    assert "toShardJson(" not in remainder
    assert "toDiagnosticsJson(" not in remainder


def test_sharded_rejects_any_option_outside_the_whitelist(collector_source: str) -> None:
    """⛔ 严格白名单：只接受 `semester` / `maxPages` / `delayMs`，其它键发请求前拒绝。

    ⛔ `pageSize` / `firstPageNo` / 自定义 shard 列表**都不接受覆盖**
    （五校区固定 `pageSize=200`、`pageNo` 从 1 起、shard 清单是源码常量）。
    """

    assert 'var SHARDED_ALLOWED_OPTIONS = ["semester", "maxPages", "delayMs"];' in collector_source

    body = _collect_sharded_slice(collector_source)

    assert "SHARDED_ALLOWED_OPTIONS.indexOf(name) === -1" in body
    assert "if (unexpected.length > 0) {" in body

    # 白名单校验必须早于任何取页调用
    assert body.index("var optionNames = Object.keys(opts);") < body.index(
        "await requestReportedTotal("
    )

    # ⛔ 不得把调用方提供的键名回显到错误信息
    assert "unexpected.join(" not in body
    assert "optionNames.join(" not in body

    # ⛔ 不得从 options 读取 pageSize / firstPageNo / shard 列表
    for forbidden in ("opts.pageSize", "opts.firstPageNo", "opts.shards", "opts.shardIds"):
        assert forbidden not in body, f"五校区采集不得读取：{forbidden}"

    for forbidden in ("opts.firstPageNo === undefined ?",):
        assert forbidden not in collector_source


def test_sharded_baseline_probe_has_no_campus_dimension(collector_source: str) -> None:
    """baseline 请求只有 `yearTerm`：⛔ 不带 `openingSchoolNumber`。"""

    builder = _js_function_slice(
        collector_source, "function buildRequestParam(", "async function requestPage("
    )

    # 不传校区号 → 只有 yearTerm；传了 → 追加已批准维度
    assert "if (openingSchoolNumber === undefined) {" in builder
    assert "return { yearTerm: semester };" in builder
    assert "param[SHARD_PARAM_NAME] = openingSchoolNumber;" in builder

    probe = _js_function_slice(
        collector_source, "async function requestReportedTotal(", "async function collect("
    )

    # 探针只取一页一次、只读 total，⛔ 不最小化 / 不脱敏 / 不产出 bundle
    assert probe.count("await requestPage(") == 1
    assert "return data.total;" in probe

    for forbidden in ("minimizeRow", "redact", "bundle", "CAPTURE_FORMAT", "toJson", "for ("):
        assert forbidden not in probe, f"baseline 探针不得出现：{forbidden}"


def test_sharded_campus_requests_use_the_approved_constant(collector_source: str) -> None:
    """每个 shard 的请求维度来自**源码常量**，⛔ 不来自调用方输入。"""

    body = _collect_sharded_slice(collector_source)

    assert "var shard = APPROVED_SHARDS[shardIndex];" in body
    assert "shard.openingSchoolNumber" in body
    assert "SHARD_PAGE_SIZE" in body
    # ⛔ 不接受调用方传入 shard 列表 / 校区号
    assert "opts.openingSchoolNumber" not in body
    assert "options.shards" not in collector_source


def test_sharded_keeps_the_baseline_sandwich(collector_source: str) -> None:
    """`baseline_before` → 五个 shard → `baseline_after`，且不等价即整体失败。"""

    body = _collect_sharded_slice(collector_source)

    before_index = body.index("baselineBefore = await requestReportedTotal(")
    shard_index = body.index("for (var shardIndex = 0;")
    after_index = body.index("baselineAfter = await requestReportedTotal(")
    compare_index = body.index("if (baselineBefore !== baselineAfter) {")

    assert before_index < shard_index < after_index < compare_index, (
        "顺序必须是 baseline_before → 五个 shard → baseline_after → 对拍"
    )

    # 对拍失败必须整体失败（带 diagnostics 抛出，⛔ 不返回任何 bundle）
    assert "failWithDiagnostics(" in body[compare_index:]


def test_sharded_fails_closed_on_an_incomplete_shard(collector_source: str) -> None:
    """任一 shard 未取满（`stoppedReason !== "reached_total"`）→ 立即整体停止。"""

    body = _collect_sharded_slice(collector_source)

    assert 'core.stoppedReason !== "reached_total"' in body
    assert "core.accumulatedRows !== core.expectedTotal" in body
    assert "已整体停止，不产出任何 bundle" in body

    # 检查必须发生在取 baseline_after **之前**（fail fast，不再继续打学校接口）
    check_index = body.index('core.stoppedReason !== "reached_total"')
    assert check_index < body.index("baselineAfter = await requestReportedTotal(")


def test_sharded_requests_baseline_after_before_any_coverage_judgement(
    collector_source: str,
) -> None:
    """⛔ **判定顺序硬要求**（Review Blocker）：

    五个 shard 全部完整成功后，必须**无条件**先取 `baseline_after` 并判
    **baseline 稳定性**（`snapshot window unstable`）；**只有**稳定之后
    才允许判 **shard 覆盖性**（`shard coverage mismatch`）。

    ⛔ 覆盖性不得抢在 baseline_after 之前判定。
    """

    body = _collect_sharded_slice(collector_source)

    after_index = body.index("baselineAfter = await requestReportedTotal(")
    stability_index = body.index("if (baselineBefore !== baselineAfter) {")
    coverage_index = body.index("if (coveredTotal !== baselineBefore) {")

    assert after_index < stability_index < coverage_index, (
        "顺序必须是 baseline_after → baseline 稳定性 → shard 覆盖性"
    )

    stability_block = body[stability_index:coverage_index]

    assert "snapshot window unstable" in stability_block
    assert "shard coverage mismatch" in body[coverage_index:]

    # ⛔ 两个判定必须可区分：不得互相夹带对方的文案
    assert "shard coverage mismatch" not in stability_block
    assert "snapshot window unstable" not in body[coverage_index:]

    # 覆盖性判定只消费 baseline_before（不是 baseline_after）
    assert "coveredTotal !== baselineBefore" in body[coverage_index:]


def test_sharded_fails_closed_on_coverage_mismatch(collector_source: str) -> None:
    """Σ shard total != baseline_before → 整体失败（稳定之后才判，口径与 Python 侧一致）。"""

    body = _collect_sharded_slice(collector_source)

    assert "if (coveredTotal !== baselineBefore) {" in body
    assert "shard coverage mismatch" in body
    assert "已整体停止，不产出任何 bundle" in body[body.index("shard coverage mismatch") :]


def test_sharded_reuses_the_single_paging_core(collector_source: str) -> None:
    """⛔ 只有一个分页循环：五个 shard 全部走 `collectPages()`。

    这样 `pageNo` 从 1 起、`pageSize`、`expectedTotal` 取本 shard 第一页、
    `reached_total` 停止、以及 **pacing** 全部是**同一份**实现，
    不存在第二套分页 / 等待逻辑。
    """

    assert collector_source.count("async function collectPages(") == 1
    assert collector_source.count('stoppedReason = "reached_total";') == 1
    assert collector_source.count("for (var index = 0; index < maxPages; index += 1)") == 1

    body = _collect_sharded_slice(collector_source)

    assert body.count("await collectPages(") == 1, "五个 shard 必须复用同一个分页核心"
    # ⛔ 编排层**不自己等待**：相邻请求的间隔（含跨 shard / 跨批次）由全局 pacer 保证
    assert "await sleep(" not in body, "五校区编排层不得自己 sleep"
    assert "pacer" in body[body.index("await collectPages(") : body.index("await collectPages(") + 260]

    # ⛔ 不得并发 / 定时轮询 / 重试
    for forbidden in ("Promise.all", "Promise.allSettled", "Promise.race", "setInterval", "retry"):
        assert forbidden not in body, f"五校区编排不得出现：{forbidden}"


def test_sharded_expected_pages_is_diagnostics_only(collector_source: str) -> None:
    """⛔ `expected_pages = ceil(total / page_size)` **只允许作 diagnostics**。

    它**不得**参与 complete / 完整性判定：判据只有 `accumulatedRows == expectedTotal`。
    """

    body = _collect_sharded_slice(collector_source)

    assert "expected_pages: Math.ceil(core.expectedTotal / pageSize)" in body

    # ⛔ `Math.ceil` 只允许出现在"写 diagnostics 记录"这一处
    assert body.count("Math.ceil(") == 1, "expected_pages 的计算只允许有一处（diagnostics）"

    record_start = body.index("shardDiagnostics.push({")
    record_end = body.index("});", record_start)
    assert "Math.ceil(" in body[record_start:record_end]

    # ⛔ 判定分支里不得出现页数计算
    check_index = body.index('core.stoppedReason !== "reached_total"')
    decision = body[check_index : body.index("}", check_index)]
    assert "Math.ceil(" not in decision, "complete 判定不得使用 expected_pages"

    # ⛔ 不得把 expected_pages 与任何东西比较（那就是让它参与判定）
    for forbidden in (
        "=== expected_pages",
        "!== expected_pages",
        "== expected_pages",
        "!= expected_pages",
        "< expected_pages",
        "> expected_pages",
        "expected_pages ===",
        "expected_pages !==",
        "expected_pages +",
        "expected_pages -",
    ):
        assert forbidden not in collector_source, f"expected_pages 不得参与判定：{forbidden}"


def test_sharded_diagnostics_carries_no_row_content(collector_source: str) -> None:
    """外层 diagnostics 只有结构化计数：⛔ 无 row、无课程 / 教师 / 原文。"""

    body = _collect_sharded_slice(collector_source)

    diagnostic_start = body.index("function makeDiagnostics()")
    diagnostic_end = body.index("// ---- baseline_before")
    diagnostics = body[diagnostic_start:diagnostic_end]

    for key in (
        "baseline_before: baselineBefore",
        "baseline_after: baselineAfter",
        "shard_total_sum: totalSum",
        "expected_pages_total: pageSum",
        "shards: shardDiagnostics.slice()",
    ):
        assert key in diagnostics, f"diagnostics 缺少：{key}"

    for forbidden in (
        "pages:",
        "rows",
        "courseNum",
        "courseName",
        "classNumber",
        "teachingTimePlaceStr",
        "teacher",
        "readObj",
        "timePlaceId",
    ):
        assert forbidden not in diagnostics, f"diagnostics 不得包含：{forbidden}"

    # 每个 shard 的诊断记录：照 Review 清单，且不含任何 row 内容
    record_start = body.index("shardDiagnostics.push({")
    record_end = body.index("});", record_start)
    record = body[record_start:record_end]

    for key in (
        "shard_id: shard.shard_id",
        "openingSchoolNumber: shard.openingSchoolNumber",
        "expectedTotal: core.expectedTotal",
        "accumulatedRows: core.accumulatedRows",
        "stoppedReason: core.stoppedReason",
        "page_count: core.pages.length",
    ):
        assert key in record, f"shard 诊断记录缺少：{key}"

    for forbidden in ("rows", "courseNum", "teachingTimePlaceStr", "teacher", "readObj"):
        assert forbidden not in record, f"shard 诊断记录不得包含：{forbidden}"


def test_sharded_bundles_exclude_diagnostics(collector_source: str) -> None:
    """⛔ diagnostics **不进入**裸 bundle：bundle 顶层只有 5 个键。"""

    body = _collect_sharded_slice(collector_source)

    bundle_start = body.index("bundle: {")
    bundle_end = body.index("}", bundle_start)
    bundle = body[bundle_start:bundle_end]

    keys = {
        line.strip().split(":")[0]
        for line in bundle.splitlines()
        if ":" in line and not line.strip().startswith("//")
    }
    keys.discard("bundle")

    assert keys == {"format", "semester", "first_page_no", "page_size", "pages"}, (
        f"shard 裸 bundle 顶层键必须恰好是 5 个，实际：{sorted(keys)}"
    )
    assert "diagnostics" not in bundle
    assert "expected_pages" not in bundle


def test_sharded_serializers_refuse_incomplete_results(collector_source: str) -> None:
    """⛔ 取消 / 未完成时不得序列化任何 bundle 或 diagnostics。"""

    shard_bundle = _js_function_slice(
        collector_source, _SHARDED_BUNDLE_START, "function toShardJson("
    )
    assert "result.cancelled === true" in shard_bundle
    assert "!Array.isArray(result.shards)" in shard_bundle
    assert "本采集器不会生成伪 bundle" in shard_bundle
    # ⛔ 找不到 shard 时不回显调用方给出的名字
    assert "+ shardId" not in shard_bundle
    assert "shardId +" not in shard_bundle

    to_shard = _js_function_slice(
        collector_source, "function toShardJson(", "function toDiagnosticsJson("
    )
    assert "JSON.stringify(shardBundle(result, shardId), null, 2)" in to_shard
    # ⛔ 不得把 wrapper（含 diagnostics）序列化成 bundle
    assert "JSON.stringify(result, null, 2)" not in to_shard

    to_diagnostics = _js_function_slice(
        collector_source, "function toDiagnosticsJson(", "// 结构诊断（Phase 2B-2C1B）"
    )
    assert "JSON.stringify(result.diagnostics, null, 2)" in to_diagnostics


# ---------------------------------------------------------------------------
# 一次性 Layout B 诊断（**零留存**；Architecture Review 裁定）
#
# 目的：在 collector 对 raw response 做 minimize **之前**，用**内存比较**回答
# "Layout B 的 f3 / f4 各自是什么角色"，且**只**输出七个聚合计数。
#
# 已确认 activity 集合**只**来自已确认 layout 的 activity 固定槽位
# （`confirmedActivitySlotIndex()`）；⛔ 不用"非空字符串 = activity"当角色证据。
# ---------------------------------------------------------------------------

_LAYOUT_B_SECTION_START = "var LAYOUT_B_FIELD_COUNT"
_LAYOUT_B_SECTION_END = "// 分段式 f3 字段来源诊断"

_FIELD_SOURCE_SECTION_START = "var LAYOUT_B_FIELD_SOURCE_STATE_VERSION"
_FIELD_SOURCE_SECTION_END = "// 相关性诊断（Phase 2B-2C1C）"

_LAYOUT_B_RETURN_KEYS = (
    "candidate_count",
    "comparable_teaching_name_count",
    "f3_equals_teaching_name_count",
    "f4_equals_teaching_name_count",
    "f4_activity_count",
    "f3_in_confirmed_activity_set_count",
    "f4_in_confirmed_activity_set_count",
    "f3_matching_raw_fields",
)


def _layout_b_section_slice(collector_source: str) -> str:
    """截取 Layout B 诊断整段（常量 + 纯函数 + 异步入口）。"""

    start = collector_source.index(_LAYOUT_B_SECTION_START)
    end = collector_source.index(_LAYOUT_B_SECTION_END)
    assert start < end, "Layout B 诊断应位于 C1C 段落之前"

    return collector_source[start:end]


def _layout_b_diagnostic_slice(collector_source: str) -> str:
    """只截取 `diagnoseLayoutBCandidates()` 的代码（不含上方 JSDoc）。"""

    return _js_function_slice(
        collector_source,
        "async function diagnoseLayoutBCandidates(",
        _LAYOUT_B_SECTION_END,
    )


def test_layout_b_diagnostic_is_exposed_and_not_auto_called(collector_source: str) -> None:
    """诊断入口必须显式暴露，且**加载脚本不得自动调用**。"""

    assert "diagnoseLayoutBCandidates: diagnoseLayoutBCandidates" in collector_source

    expose_index = collector_source.rindex("window.XuehangSysuCollector")
    remainder = collector_source[expose_index + len("window.XuehangSysuCollector") :]
    assert "diagnoseLayoutBCandidates(" not in remainder, "挂载之后不得自动调用诊断"


def test_layout_b_diagnostic_is_not_in_any_production_path(collector_source: str) -> None:
    """⛔ 生产链路（`collect()` / `collectSharded()` / 分页核心）不得引用 Layout B 诊断。"""

    blocks = {
        "collectPages": _js_function_slice(
            collector_source, "async function collectPages(", "async function requestReportedTotal("
        ),
        "requestReportedTotal": _js_function_slice(
            collector_source, "async function requestReportedTotal(", "async function collect("
        ),
        "collect": _js_function_slice(
            collector_source, "async function collect(", "// 五校区 shard 编排"
        ),
        "collectSharded": _collect_sharded_slice(collector_source),
    }

    for name, block in blocks.items():
        for forbidden in ("diagnoseLayoutBCandidates", "LAYOUT_B_"):
            assert forbidden not in block, f"{name} 不得引用 Layout B 诊断：{forbidden}"


def test_layout_b_diagnostic_returns_only_the_seven_aggregate_counts(
    collector_source: str,
) -> None:
    """返回值**只有**七个聚合计数 + 一个字段名映射：⛔ 无 rows / 无取值 / 无 f3 / f4 原文。"""

    slice_ = _layout_b_diagnostic_slice(collector_source)

    return_start = slice_.index("return {")
    return_end = slice_.index("};", return_start)
    returned = slice_[return_start:return_end]

    keys = {
        line.strip().split(":")[0]
        for line in returned.splitlines()
        if ":" in line and line.strip().startswith(tuple(k for k in _LAYOUT_B_RETURN_KEYS))
    }

    assert keys == set(_LAYOUT_B_RETURN_KEYS), (
        f"Layout B 诊断只允许返回七个计数 + 一个字段名映射，实际：{sorted(keys)}"
    )

    # ⛔ 返回值里不得出现任何原始内容 / 标识 / 分页元数据 / 集合与多重集本身
    for forbidden in (
        "rows:",
        "teachingName:",
        "segment",
        "data.rows",
        "token",
        "new Set(",
        "new Map(",
        "confirmedActivityTokens",
        "candidateThirdTokens",
        "candidateFourthTokens",
        "f3FieldMatchCounts",
        "courseNum",
        "classNumber",
        "courseName",
        "timePlaceId",
        "page_no",
        "page_size",
        "semester",
        "reported_total",
    ):
        assert forbidden not in returned, f"Layout B 诊断返回值不得包含：{forbidden}"


def test_layout_b_diagnostic_never_emits_values_anywhere(collector_source: str) -> None:
    """⛔ 整段诊断（含错误路径）不得打印 / 落盘 / 序列化任何取值。"""

    slice_ = _layout_b_section_slice(collector_source)

    for forbidden in (
        "console.",
        "localStorage",
        "sessionStorage",
        "JSON.stringify",
        "Blob",
        "createObjectURL",
        "download",
        "document.cookie",
        "fetch(",
        "credentials",
    ):
        assert forbidden not in slice_, f"Layout B 诊断不得出现：{forbidden}"

    # ⛔ 错误信息不回显调用方参数名 / 任何取值
    assert "参数名不予回显" in slice_
    assert "不回显任何取值" in slice_


def test_layout_b_diagnostic_produces_no_capture_artifacts(collector_source: str) -> None:
    """⛔ 不产出 bundle、不做最小化 / 脱敏 / 序列化（零留存）。"""

    slice_ = _layout_b_section_slice(collector_source)
    # ⚠️ JSDoc 里会**说明**"不产出 bundle / 不做最小化"，因此只看非注释代码行。
    code = _collector_code_only(slice_)

    for forbidden in (
        "bundle",
        "minimizeRow",
        "redactSegmentTeacher",
        "toJson(",
        "CAPTURE_FORMAT",
        "KEPT_ROW_FIELDS",
        "REQUIRED_ROW_FIELDS",
    ):
        assert forbidden not in code, f"Layout B 诊断不得出现：{forbidden}"


def test_layout_b_diagnostic_compares_before_minimize(collector_source: str) -> None:
    """比较必须发生在 **minimize 之前**：直接读 raw row 的属性。"""

    slice_ = _layout_b_diagnostic_slice(collector_source)

    assert "row[SCHEDULE_FIELD]" in slice_, "诊断必须直接读取 raw row 的排课字段"
    assert "minimizeRow" not in slice_
    assert slice_.count("await requestPage(") == 1
    # ⛔ 连续两次请求之间不得自己等待：全部交给全局 pacer
    assert "await sleep(" not in slice_


def test_layout_b_diagnostic_pacing_and_page_bounds(collector_source: str) -> None:
    """多页请求必须复用同一 pacer，并受已验证页码 / 页大小约束。"""

    slice_ = _layout_b_diagnostic_slice(collector_source)

    assert "createRequestPacer(resolved.delayMs)" in slice_
    assert "var currentPageNo = FIRST_PAGE_NO + index;" in slice_
    assert "resolved.pageSize" in slice_
    # ⛔ 起始页恒为已验证的 1（不接受调用方传入其它起点）
    assert "resolvePagingOptions(opts)" in slice_
    # data.total 中途变化 → 整体 fail closed
    assert "data.total !== expectedTotal" in slice_
    assert "accumulatedRows >= expectedTotal" in slice_


def test_layout_b_diagnostic_option_whitelist_is_strict_and_precedes_requests(
    collector_source: str,
) -> None:
    """只接受三个已批准参数；校验必须发生在**任何取页调用之前**。"""

    assert 'LAYOUT_B_ALLOWED_OPTIONS = ["semester", "openingSchoolNumber", "maxPages"]' in (
        collector_source
    )

    slice_ = _layout_b_diagnostic_slice(collector_source)

    assert slice_.index("unexpected.length > 0") < slice_.index("await requestPage(")

    # ⛔ 不得放开页大小 / 起始页 / 间隔（恒用已验证默认口径）
    for forbidden in ("opts.pageSize", "opts.firstPageNo", "opts.delayMs"):
        assert forbidden not in slice_, f"Layout B 诊断不得读取：{forbidden}"


def test_layout_b_candidate_grammar_is_anchored_and_whitelisted(
    collector_source: str,
) -> None:
    """候选判别完全复用已批准 grammar：整段锚定 + 白名单，**无通配 / 无前辍匹配**。"""

    slice_ = _layout_b_section_slice(collector_source)
    # ⚠️ 说明性文字本身就在讲"无通配"，因此这组断言只看**非注释代码行**。
    code = _collector_code_only(slice_)

    assert "var LAYOUT_B_FIELD_COUNT = 4;" in code

    for pattern in (
        r"/^[0-9]+-[0-9]+周$/",
        r"/^[0-9]+-[0-9]+(单周|双周)$/",
        r"/^[0-9]+-[0-9]+周(校外|校内\(户外\))$/",
        r"/^第[0-9]+-[0-9]+节(校内\(户外\)|校外|线上)?$/",
    ):
        assert pattern in code, f"缺少已批准 pattern：{pattern}"

    # ⛔ 无通配、无前缀匹配、无字段数量通配
    assert ".*" not in code
    assert "startswith" not in code
    assert "startsWith" not in code
    assert "includes(" not in code
    # ⛔ **取值 / 候选 grammar** 一律不做大小写折叠：
    #    `toLowerCase` 只允许出现在**字段名**的内部 ID 规则里（`fieldName.toLowerCase() === "id"`）。
    assert code.count("toLowerCase") == 1
    assert 'fieldName.toLowerCase() === "id"' in code
    assert "row[fieldName].toLowerCase" not in code
    assert "thirdField.toLowerCase" not in code
    assert "fourthField.toLowerCase" not in code
    # location 判别必须复用既有判别器（>= 3 个非空 '-' 分段）
    assert "countNonEmptyDashSegments(fields[1].trim()) < MIN_LOCATION_SEGMENTS" in code


def test_layout_b_missing_teaching_name_is_not_guessed(collector_source: str) -> None:
    """raw row 没有 `teachingName` → 不计入 comparable，**不用其它字段顶替**。"""

    slice_ = _layout_b_diagnostic_slice(collector_source)
    code = _collector_code_only(slice_)

    assert 'Object.prototype.hasOwnProperty.call(row, "teachingName")' in code
    assert "if (hasTeachingName) {" in code
    assert "thirdField === row.teachingName" in code
    assert "fourthField === row.teachingName" in code

    # ⛔ 不得给 teachingName 做任何兜底 / 等价替换
    for forbidden in (
        "row.teachingName ||",
        "row.teachingName ??",
        "row.teachingName ?",
        "row.courseName",
        "row.teacher",
        "row.teacherName",
    ):
        assert forbidden not in code, f"不得用其它字段顶替 teachingName：{forbidden}"

    # comparable 只在属性存在时推进（顺序：先判定，再计数）
    assert code.index("if (hasTeachingName) {") < code.index("comparableTeachingNameCount += 1;")


def test_layout_b_f4_uses_the_existing_activity_rule(collector_source: str) -> None:
    """f4 只按**现有** activity 规则判定：非空字符串（⛔ 仅语法检查，非角色证据）。"""

    slice_ = _layout_b_section_slice(collector_source)

    assert (
        'return typeof token === "string" && token.trim() !== "";' in slice_
    ), "activity 规则必须与 Python `_require_non_empty_token` 同规则"
    assert "isNonEmptyActivityToken(fields[3])" in collector_source
    # ⛔ 不得把 activity 规则写成通配 / 白名单之外的模式
    assert "activityCount" in slice_


def test_layout_b_activity_set_comes_only_from_confirmed_layout_slots(
    collector_source: str,
) -> None:
    """activity 集合的来源**只能**是已确认 layout 的 activity 固定槽位。"""

    slice_ = _layout_b_section_slice(collector_source)
    code = _collector_code_only(slice_)

    # 判别器只定义一次，且诊断内只调用一次
    assert code.count("function confirmedActivitySlotIndex(") == 1
    assert code.count("= confirmedActivitySlotIndex(") == 1
    assert "var activitySlot = confirmedActivitySlotIndex(segment);" in code

    # weekday 白名单恰好七个（⛔ 无 `星期天` 等未确认写法、⛔ 无通配）
    assert code.count('"星期') == 7
    assert "CONFIRMED_WEEKDAY_TOKENS.indexOf(token) !== -1" in code

    # non-concrete（2 / 3 字段）的 f1 **不含** parity
    start = code.index("CONFIRMED_NON_CONCRETE_WEEKS_PATTERNS = [")
    end = code.index("];", start)
    non_concrete_patterns = code[start:end]
    assert "单周" not in non_concrete_patterns
    assert "双周" not in non_concrete_patterns
    assert r"/^[0-9]+-[0-9]+周$/" in non_concrete_patterns
    assert r"/^[0-9]+-[0-9]+周(校外|校内\(户外\))$/" in non_concrete_patterns

    # weeks 的数值规则（与 `expand_weeks()` 同规则：N >= 1、M >= N、parity 非空）
    assert "if (start < 1 || end < start) {" in code
    assert "for (var week = start; week <= end; week += 1) {" in code
    assert 'parity === "单周" ? week % 2 === 1 : week % 2 === 0' in code

    # sections 的数值规则
    assert "return start >= 1 && end >= start;" in code

    # layout A 的 REDACTED 必须**精确**相等（⛔ 无前缀 / 包含 / 折叠）
    assert "fields[3] === REDACTED_TEACHER" in code
    assert "REDACTED_TEACHER.indexOf" not in code
    assert "REDACTED_TEACHER.toLowerCase" not in code

    # 5 字段二义 → 不算已确认
    assert 'if (classification === "ambiguous") {' in code

    # 6 字段用**通用** location grammar（与 Python `_is_location_token` 同规则）
    assert "isGeneralLocationToken(fields[3])" in code

    # 七个固定槽位下标都在（1 / 2 / 3 / 4 / 5）且存在"未确认"分支
    for slot in ("return 1;", "return 2;", "return 3;", "return 4;", "return 5;"):
        assert slot in code, f"缺少 activity 槽位：{slot}"
    assert "return -1;" in code


def test_layout_b_activity_set_is_memory_only(collector_source: str) -> None:
    """集合与多重集**只在内存**：⛔ 不返回、⛔ 不落盘、⛔ 不进 bundle、⛔ 不写日志。"""

    slice_ = _layout_b_diagnostic_slice(collector_source)
    code = _collector_code_only(slice_)

    assert "var confirmedActivityTokens = new Set();" in code
    assert "var candidateThirdTokens = new Map();" in code
    assert "var candidateFourthTokens = new Map();" in code

    # 只声明一次，之后只做 add / has（⛔ 不重新赋值、⛔ 不挂到全局）
    assert code.count("confirmedActivityTokens =") == 1
    assert code.count("candidateThirdTokens =") == 1
    assert code.count("candidateFourthTokens =") == 1
    assert "window.XuehangSysuCollector" not in code
    assert "globalThis" not in code

    # ⛔ 集合本身不得出现在返回值里（返回值只有计数）
    return_start = code.index("return {")
    returned = code[return_start:]
    for forbidden in ("confirmedActivityTokens", "candidateThirdTokens", "candidateFourthTokens"):
        assert forbidden not in returned, f"返回值不得包含：{forbidden}"


def test_layout_b_membership_is_order_independent(collector_source: str) -> None:
    """候选 f3 / f4 先入内存多重集，**扫完所有页之后**才与集合求交。"""

    slice_ = _layout_b_diagnostic_slice(collector_source)
    code = _collector_code_only(slice_)

    assert "addTokenOccurrence(candidateThirdTokens, thirdField);" in code
    assert "addTokenOccurrence(candidateFourthTokens, fourthField);" in code

    # 成员判定只有一处实现（在纯函数里），⛔ 不得在分页循环内"就地"判定
    section_code = _collector_code_only(_layout_b_section_slice(collector_source))
    assert "function countMultisetTokensInSet(" in section_code
    assert section_code.count("tokenSet.has(token)") == 1
    assert code.count("countMultisetTokensInSet(") == 2
    assert code.count("confirmedActivityTokens\n    );") == 2

    page_loop = code.index("for (var index = 0; index < resolved.maxPages; index += 1) {")
    intersection = code.index("var thirdInSetCount = countMultisetTokensInSet(")
    assert page_loop < intersection, "求交必须发生在全部页扫完之后"
    assert code.index("addTokenOccurrence(candidateThirdTokens, thirdField);") < intersection


def test_layout_b_empty_activity_set_fails_closed(collector_source: str) -> None:
    """集合为空 → **fail closed**（⛔ 不返回会被误读为"不是 activity"的 0）。"""

    code = _collector_code_only(_layout_b_diagnostic_slice(collector_source))

    assert "if (confirmedActivityTokens.size === 0) {" in code
    assert code.index("confirmedActivityTokens.size === 0") < code.index("return {")
    assert "成员判定会退化为恒假" in collector_source
    assert "不回显任何取值" in collector_source


def test_layout_b_has_no_name_heuristics_or_cjk_length_guessing(
    collector_source: str,
) -> None:
    """⛔ 无姓名启发式、⛔ 无 CJK 长度猜测、⛔ 不读课程名 / 教师名。"""

    code = _collector_code_only(_layout_b_section_slice(collector_source))

    # teachingName 只允许出现在三处：存在性判定 + f3 / f4 两次精确相等比较
    assert code.count("teachingName") == 3

    for forbidden in (
        "charCodeAt",
        "codePointAt",
        "normalize(",
        "\\u4e00",
        "\\u9fff",
        "courseName",
        "teacherName",
        "surname",
        "百家姓",
    ):
        assert forbidden not in code, f"⛔ 诊断不得使用启发式 / 猜测：{forbidden}"

    # ⛔ 不得按 token 长度判断角色（数组 / rows 的 length 不受影响）
    assert not re.search(r"token\.length", code)
    assert not re.search(r"\.trim\(\)\.length", code)
    assert not re.search(r"(thirdField|fourthField|segment)\.length", code)


# ---------------------------------------------------------------------------
# Layout B 候选 f3 的**原始字段名命中**统计（Architecture Review 裁定 2026-10-05）
#
# ⛔ 只输出字段名 + 命中计数；⛔ 严格相等；⛔ 排除 courseNum / classNumber /
# teachingTimePlaceStr / 内部 ID 字段；⛔ 无 substring / 分词 / 模糊匹配。
# ---------------------------------------------------------------------------


def _layout_b_f3_match_loop(collector_source: str) -> str:
    """截取 f3 命中统计的循环体（从 `Object.keys(row)` 到分页累加之前）。"""

    code = _collector_code_only(_layout_b_diagnostic_slice(collector_source))

    start = code.index("var rowFieldNames = Object.keys(row);")
    end = code.index("accumulatedRows += data.rows.length;", start)
    assert start < end

    return code[start:end]


def test_layout_b_f3_match_histogram_is_strict_and_names_only(
    collector_source: str,
) -> None:
    """只遍历**字符串字段**、只做**严格相等**，且映射里只放**字段名**与计数。"""

    loop = _layout_b_f3_match_loop(collector_source)

    assert "var rowFieldNames = Object.keys(row);" in loop
    assert 'typeof row[fieldName] !== "string"' in loop
    assert "if (thirdField === row[fieldName]) {" in loop

    # ⛔ raw 取值只允许出现在"类型判定"与"严格相等"两处（⛔ 不得写进映射）
    assert loop.count("row[fieldName]") == 2

    # ⛔ 映射的键只能是**字段名**，计数只能是 +1 / 1（⛔ 不得写入任何取值）
    assert loop.count("f3FieldMatchCounts.set(") == 1
    assert "matchedSoFar === undefined ? 1 : matchedSoFar + 1" in loop

    # ⛔ 无模糊匹配 / substring / 分词 / 大小写折叠
    for forbidden in ("indexOf(", "includes(", "startsWith", "toLowerCase", "split(", "substring"):
        assert forbidden not in loop, f"⛔ f3 命中统计不得使用：{forbidden}"

    # 输出稳定：字段名排序 + 普通对象映射
    section_code = _collector_code_only(_layout_b_section_slice(collector_source))
    assert "Object.fromEntries(" in section_code
    assert "Array.from(f3FieldMatchCounts.keys())" in section_code
    assert ".sort()" in section_code


def test_layout_b_f3_match_histogram_excludes_ids_and_never_echoes_values(
    collector_source: str,
) -> None:
    """排除 courseNum / classNumber / teachingTimePlaceStr / 内部 ID 字段名。"""

    code = _collector_code_only(_layout_b_section_slice(collector_source))

    start = code.index("LAYOUT_B_F3_MATCH_EXCLUDED_FIELDS = [")
    end = code.index("];", start)
    excluded = code[start:end]
    for name in (
        "courseNum",
        "classNumber",
        "teachingTimePlaceStr",
        # Architecture Review 清单里的内部 ID 字段
        "courseId",
        "class_ID",
        "sumClassesID",
        "outLineId",
        "timePlaceId",
    ):
        assert f'"{name}"' in excluded, f"排除清单缺少：{name}"

    # 内部 ID **词法边界**规则（机械名称规则，⛔ 不是对取值的模糊匹配）
    assert 'var LAYOUT_B_F3_MATCH_ID_SUFFIXES = ["Id", "ID"];' in code
    assert "var LAYOUT_B_F3_MATCH_ID_UNDERSCORE_PATTERN = /_id$/i;" in code
    assert 'fieldName.toLowerCase() === "id"' in code
    assert "fieldName.endsWith(LAYOUT_B_F3_MATCH_ID_SUFFIXES[index])" in code
    assert "LAYOUT_B_F3_MATCH_ID_UNDERSCORE_PATTERN.test(fieldName)" in code
    assert "function hasInternalIdShape(" in code
    assert "return hasInternalIdShape(fieldName);" in code

    # ⛔ **不得**再出现"任意以 id 两个字符结尾"的过宽规则
    #    （它会错误排除 `valid` / `invalid` / `hybrid` 这类普通单词）
    assert "[Ii][Dd]$" not in code
    assert "LAYOUT_B_F3_MATCH_EXCLUDED_FIELD_PATTERN" not in code

    assert "function isExcludedMatchFieldName(" in code
    # ⚠️ 断言必须包含 `if (`：只断言函数名会被"函数定义处"满足（曾造成 P11 假绿灯）
    assert "if (isExcludedMatchFieldName(fieldName)) {" in code
    assert "LAYOUT_B_F3_MATCH_EXCLUDED_FIELDS.indexOf(fieldName) !== -1" in code

    # teachingTimePlaceStr 只能作为**排除清单字面量**出现一次
    # （读排课字段走 `row[SCHEDULE_FIELD]`，⛔ 不用字面量）
    assert code.count("teachingTimePlaceStr") == 1

    # ⛔ 映射的构建只使用 f3FieldMatchCounts（⛔ 不引用任何 row 字段值）
    build_start = code.index("var f3MatchingRawFields = Object.fromEntries(")
    build_end = code.index("return {", build_start)
    build = code[build_start:build_end]
    assert "row[" not in build
    assert "f3FieldMatchCounts.get(fieldName)" in build


# ---------------------------------------------------------------------------
# 分段式 f3 字段来源诊断（Architecture Review 方案 D）
#
# ⛔ 契约**恰好六个**字段（不含 activity-membership 计数，也不用 0 / null 占位）；
# ⛔ checkpoint 零敏感（数值计数 + 字段名 → 计数 + 安全分页元数据）；
# ⛔ 生产链路完全不引用本接口；⛔ 请求 / pacing / fail-closed 行为完全复用既有路径。
# ---------------------------------------------------------------------------

_FIELD_SOURCE_STATE_KEYS = (
    "version",
    "semester",
    "openingSchoolNumber",
    "page_size",
    "expected_total",
    "processed_pages",
    "candidate_count",
    "comparable_teaching_name_count",
    "f3_equals_teaching_name_count",
    "f4_equals_teaching_name_count",
    "f4_activity_count",
    "f3_matching_raw_fields",
)

_FIELD_SOURCE_RESULT_KEYS = (
    "candidate_count",
    "comparable_teaching_name_count",
    "f3_equals_teaching_name_count",
    "f4_equals_teaching_name_count",
    "f4_activity_count",
    "f3_matching_raw_fields",
)

_FIELD_SOURCE_MEMBERSHIP_KEYS = (
    "f3_in_confirmed_activity_set_count",
    "f4_in_confirmed_activity_set_count",
)


def _field_source_section_slice(collector_source: str) -> str:
    """截取分段式诊断整段（常量 + 纯函数 + 两个入口）。"""

    start = collector_source.index(_FIELD_SOURCE_SECTION_START)
    end = collector_source.index(_FIELD_SOURCE_SECTION_END)
    assert start < end, "分段式诊断应位于 C1C 段落之前"

    return collector_source[start:end]


def _field_source_part_slice(collector_source: str) -> str:
    """只截取 `diagnoseLayoutBFieldSourcePart()` 的代码。"""

    return _js_function_slice(
        collector_source,
        "async function diagnoseLayoutBFieldSourcePart(",
        "function finalizeLayoutBFieldSource(",
    )


def _field_source_finalize_slice(collector_source: str) -> str:
    """只截取 `finalizeLayoutBFieldSource()` 的代码。"""

    return _js_function_slice(
        collector_source,
        "function finalizeLayoutBFieldSource(",
        _FIELD_SOURCE_SECTION_END,
    )


def test_field_source_api_is_exposed_and_not_used_by_production(
    collector_source: str,
) -> None:
    """⛔ 生产链路 / 完整诊断都不得引用分段式接口；两个入口必须显式暴露。"""

    assert "diagnoseLayoutBFieldSourcePart: diagnoseLayoutBFieldSourcePart" in (
        collector_source
    )
    assert "finalizeLayoutBFieldSource: finalizeLayoutBFieldSource" in collector_source

    expose_index = collector_source.rindex("window.XuehangSysuCollector")
    remainder = collector_source[expose_index + len("window.XuehangSysuCollector") :]
    for name in ("diagnoseLayoutBFieldSourcePart(", "finalizeLayoutBFieldSource("):
        assert name not in remainder, f"挂载之后不得自动调用：{name}"

    blocks = {
        "collectPages": _js_function_slice(
            collector_source, "async function collectPages(", "async function requestReportedTotal("
        ),
        "requestReportedTotal": _js_function_slice(
            collector_source, "async function requestReportedTotal(", "async function collect("
        ),
        "collect": _js_function_slice(
            collector_source, "async function collect(", "// 五校区 shard 编排"
        ),
        "collectSharded": _collect_sharded_slice(collector_source),
        "fullDiagnostic": _layout_b_diagnostic_slice(collector_source),
        "minimizeRow": _minimize_row_code(collector_source),
    }

    for name, block in blocks.items():
        for forbidden in (
            "FieldSource",
            "LAYOUT_B_FIELD_SOURCE",
            "diagnoseLayoutBFieldSourcePart",
            "finalizeLayoutBFieldSource",
        ):
            assert forbidden not in block, f"{name} 不得引用分段式诊断：{forbidden}"


def test_field_source_contract_has_exactly_six_keys(collector_source: str) -> None:
    """最终结果**恰好六个**键：⛔ 不含 activity-membership 计数、⛔ 不用 0 / null 占位。"""

    assert "var LAYOUT_B_FIELD_SOURCE_RESULT_KEYS = [" in collector_source

    finalize = _collector_code_only(_field_source_finalize_slice(collector_source))
    return_start = finalize.index("return {")
    returned = finalize[return_start:]

    keys = {
        line.strip().split(":")[0]
        for line in returned.splitlines()
        if ":" in line and line.strip().startswith(tuple(_FIELD_SOURCE_RESULT_KEYS))
    }
    assert keys == set(_FIELD_SOURCE_RESULT_KEYS), (
        f"分段式诊断只允许六个输出字段，实际：{sorted(keys)}"
    )

    for forbidden in (
        "rows",
        "teachingName",
        "segment",
        "data.rows",
        "new Set(",
        "new Map(",
        "courseNum",
        "classNumber",
        "timePlaceId",
    ):
        assert forbidden not in returned, f"分段式诊断返回值不得包含：{forbidden}"

    # ⛔ 两个 activity-membership 计数**不得存在**于本接口（既不算也不用占位）
    section = _collector_code_only(_field_source_section_slice(collector_source))
    for membership_key in _FIELD_SOURCE_MEMBERSHIP_KEYS:
        assert membership_key not in section, f"⛔ 分段式诊断不得出现：{membership_key}"
    assert "activity_set" not in section
    assert "confirmedActivityTokens" not in section


def test_field_source_checkpoint_schema_is_closed_and_value_free(
    collector_source: str,
) -> None:
    """checkpoint 的键集合封闭；只写数值计数 + 字段名 → 计数 + 安全分页元数据。"""

    section = _collector_code_only(_field_source_section_slice(collector_source))

    start = section.index("LAYOUT_B_FIELD_SOURCE_STATE_KEYS = [")
    end = section.index("];", start)
    keys_block = section[start:end]
    for key in _FIELD_SOURCE_STATE_KEYS:
        assert f'"{key}"' in keys_block, f"state 键清单缺少：{key}"
    assert keys_block.count('"') == len(_FIELD_SOURCE_STATE_KEYS) * 2, (
        "state 键清单必须**恰好**是已批准键（⛔ 不得多写）"
    )

    assert 'LAYOUT_B_FIELD_SOURCE_PAGE_KEYS = ["page_no", "row_count"]' in section

    # 组装 state 的函数只能写这些键；⛔ 不得引用 row / 取值
    builder = _js_function_slice(
        collector_source,
        "function buildLayoutBFieldSourceState(",
        "function accumulateLayoutBFieldSourceRows(",
    )
    for key in _FIELD_SOURCE_STATE_KEYS:
        assert f"{key}:" in builder, f"state 组装缺少：{key}"

    builder_code = _collector_code_only(builder)
    builder_return_start = builder_code.index("return {")
    builder_return = builder_code[builder_return_start : builder_code.index("};", builder_return_start)]
    builder_keys = {
        line.strip().split(":")[0]
        for line in builder_return.splitlines()
        if ":" in line and line.strip()
    }
    assert builder_keys == set(_FIELD_SOURCE_STATE_KEYS), (
        f"state 组装只允许写已批准键，实际：{sorted(builder_keys)}"
    )

    for forbidden in ("row[", "rows[", "teachingName", "segment", "Object.fromEntries(fieldMatches)"):
        assert forbidden not in builder, f"state 组装不得引用：{forbidden}"
    assert "writeFieldMatchCounts(fieldMatches)" in builder

    # 逐行累计只允许把**字段名**写进映射
    accumulator = _js_function_slice(
        collector_source,
        "function accumulateLayoutBFieldSourceRows(",
        "async function diagnoseLayoutBFieldSourcePart(",
    )
    assert 'typeof row[fieldName] !== "string"' in accumulator
    assert "if (thirdField === row[fieldName]) {" in accumulator
    assert accumulator.count("row[fieldName]") == 2
    assert accumulator.count("fieldMatches.set(") == 1
    assert "matchedSoFar === undefined ? 1 : matchedSoFar + 1" in accumulator


def test_field_source_reuses_the_shared_request_path_and_pacing(
    collector_source: str,
) -> None:
    """⛔ 不复制认证 / 请求逻辑；⛔ 不放开 pageSize / delayMs；校验先于请求。"""

    part = _collector_code_only(_field_source_part_slice(collector_source))

    assert "requireAllowedHost();" in part
    assert part.count("await requestPage(") == 1
    assert "requestPage(semester, pageNo, pageSize, campus, pacer)" in part
    assert "createRequestPacer(DEFAULT_DELAY_MS)" in part
    assert "var pageSize = DEFAULT_PAGE_SIZE;" in part
    assert "opts.pageSize" not in part
    assert "opts.delayMs" not in part

    # ⛔ 不自己等待 / 不发 raw fetch / 不碰认证
    for forbidden in ("await sleep(", "fetch(", "credentials", "XMLHttpRequest"):
        assert forbidden not in part, f"⛔ 分段式诊断不得使用：{forbidden}"

    assert part.index("unexpected.length > 0") < part.index("await requestPage(")
    assert part.index("startPage < FIRST_PAGE_NO") < part.index("await requestPage(")
    assert part.index("endPage > ABSOLUTE_MAX_PAGES") < part.index("await requestPage(")


def test_field_source_fails_closed_on_incomplete_or_inconsistent_state(
    collector_source: str,
) -> None:
    """重复 / 重叠 / 缺页 / 未取满 / total 漂移 / 绑定不一致 → 全部 fail closed。"""

    part = _collector_code_only(_field_source_part_slice(collector_source))
    finalize = _collector_code_only(_field_source_finalize_slice(collector_source))

    # 重复 / 重叠页：在**发请求之前**拒绝，且不静默覆盖
    assert "if (seenPages[pageNo] === true) {" in part
    assert part.index("if (seenPages[pageNo] === true) {") < part.index(
        "var data = await requestPage("
    )
    assert "不静默覆盖" in collector_source

    # total 漂移
    assert "data.total !== expectedTotal" in part

    # semester / shard 绑定
    assert "previous.semester !== semester" in part
    assert "previous.openingSchoolNumber !== campus" in part

    # 版本 / 键集合 / 计数 / 页码元素校验
    assert "state.version !== LAYOUT_B_FIELD_SOURCE_STATE_VERSION" in collector_source
    assert "分段 state 的键集合与契约不一致" in collector_source
    assert "requireFieldSourceCount(" in collector_source
    assert "出现重复页" in collector_source
    assert "processed_pages 的元素只允许 page_no / row_count" in collector_source

    # 覆盖完整性（无洞 + 取满 + 页数与 total 自洽）
    assert "缺少第 " in finalize and "页（覆盖不连续）" in collector_source
    assert "totalRows < parsed.expectedTotal" in finalize
    assert "Math.ceil(parsed.expectedTotal / DEFAULT_PAGE_SIZE)" in finalize
    assert "maxPage !== requiredPages" in finalize

    # ⛔ 全部走 fail closed（⛔ 不得吞掉错误继续合并）
    assert "catch (" not in part
    assert "catch (" not in finalize


def test_field_source_does_not_touch_auth_storage_or_output_channels(
    collector_source: str,
) -> None:
    """⛔ 不读认证材料 / 不落盘 / 不 console / 不进 bundle。"""

    section = _field_source_section_slice(collector_source)

    for forbidden in (
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "indexedDB",
        "JSON.stringify",
        "console.",
        "Blob",
        "download",
        "createObjectURL",
        "KEPT_ROW_FIELDS",
        "REQUIRED_ROW_FIELDS",
        "bundle",
        "minimizeRow",
        "redact",
    ):
        assert forbidden not in section, f"⛔ 分段式诊断不得出现：{forbidden}"

    # 唯一允许的 window 用法是确认框
    assert section.count("window.") == 1
    assert "window.confirm(" in section


def test_field_source_reuses_the_same_predicates_as_the_full_diagnostic(
    collector_source: str,
) -> None:
    """⛔ 不复制候选 / 排除 / activity 判别逻辑：一律复用既有私有函数。"""

    section = _collector_code_only(_field_source_section_slice(collector_source))

    for helper in (
        "isLayoutBCandidate(",
        "isExcludedMatchFieldName(",
        "isNonEmptyActivityToken(",
    ):
        assert helper in section, f"分段式诊断必须复用：{helper}"

    # 这些函数在文件中**只能有一处定义**（⛔ 不得为分段诊断复制一份）
    for definition in (
        "function isLayoutBCandidate(",
        "function isExcludedMatchFieldName(",
        "function isNonEmptyActivityToken(",
        "function hasInternalIdShape(",
        "function confirmedActivitySlotIndex(",
        "function countNonEmptyDashSegments(",
    ):
        assert collector_source.count(definition) == 1, f"⛔ 不得复制定义：{definition}"

    # 读排课字段走 `row[SCHEDULE_FIELD]`：⛔ 段内不出现字面量
    assert "teachingTimePlaceStr" not in section


# ---------------------------------------------------------------------------
# Layout B（4 字段 opaque）：collector ⇄ parser 一致性
#
# 已批准：`weeks | location | REDACTED_OPAQUE | activity`（f3 = opaque / unmodeled）
# ⛔ 不解释 f3；⛔ 只对精确 Layout B 脱敏；⛔ Layout A / concrete 不变。
# ---------------------------------------------------------------------------

PARSER_PATH = _REPO_ROOT / "backend" / "app" / "course_data" / "schedule_parser.py"


def parser_source() -> str:
    return PARSER_PATH.read_text(encoding="utf-8")


def test_layout_b_placeholder_matches_between_collector_and_parser() -> None:
    """⛔ 两侧占位符必须**逐字符**一致（单一真源在 collector）。"""

    assert 'var REDACTED_OPAQUE = "REDACTED_OPAQUE";' in (
        COLLECTOR_PATH.read_text(encoding="utf-8")
    )
    assert '_REDACTED_OPAQUE_PLACEHOLDER = "REDACTED_OPAQUE"' in parser_source()

    # 既有 teacher 占位符同样保持两侧一致
    assert 'var REDACTED_TEACHER = "REDACTED";' in (
        COLLECTOR_PATH.read_text(encoding="utf-8")
    )
    assert '_REDACTED_TEACHER_PLACEHOLDER = "REDACTED"' in parser_source()

    # ⛔ 两个占位符必须互相独立（不得复用 / 不得前缀包含）
    assert "REDACTED_OPAQUE" not in 'var REDACTED_TEACHER = "REDACTED";'


def test_collector_redacts_opaque_only_for_exact_layout_b(collector_source: str) -> None:
    """collector：4 字段分支**只**在 f2 是严格 location 时脱敏 f3。"""

    branch_start = collector_source.index("    if (fieldCount === 4) {")
    branch_end = collector_source.index("    if (fieldCount === 5) {", branch_start)
    branch = _collector_code_only(collector_source[branch_start:branch_end])

    # 条件：复用既有严格 location 门槛（>= 3 个非空 '-' 分段）
    assert "countNonEmptyDashSegments(fields[1].trim()) >= MIN_LOCATION_SEGMENTS" in branch
    # 先校验非空，再写占位符（⛔ 不用占位符掩盖空值）
    assert "opaque 槽位为空" in collector_source
    assert branch.index("opaque 槽位为空") < branch.index("fields[2] = REDACTED_OPAQUE;")
    assert "fields[2] = REDACTED_OPAQUE;" in branch
    # ⛔ 不注入 row 级教师名、⛔ 不做启发式
    for forbidden in ("teachingName", "charCodeAt", "codePointAt", "\\u4e00", ".length ==="):
        assert forbidden not in branch, f"⛔ 4 字段分支不得出现：{forbidden}"

    # ⛔ 不得泛化成"所有 4 字段都脱敏"：无条件 return 前必须有 location 判定
    assert "return segment;" in branch


def test_parser_layout_b_is_exact_and_does_not_interpret_opaque() -> None:
    """parser：Layout B 的**四条精确准入** + ⛔ 不解释 opaque 槽位。"""

    source = parser_source()

    start = source.index("def _try_parse_four_field_non_concrete_layout_b(")
    end = source.index("def parse_teaching_time_place(", start)
    function = source[start:end]

    # 四条准入
    assert "_LAYOUT_B_NON_CONCRETE_FIELD_COUNT" in function
    assert "expand_weeks(fields[0].strip())" in function
    assert "_classify_five_field_token(fields[1].strip()) != _FIVE_FIELD_LOCATION" in function
    assert "if fields[2] != _REDACTED_OPAQUE_PLACEHOLDER:" in function
    assert 'if not isinstance(activity, str) or activity.strip() == "":' in function

    # meeting=None 且 **teacher=None**（⛔ 不塞占位符冒充 teacher）
    assert "meeting=None," in function
    assert "teacher=None," in function
    assert "schedule_qualifier=None," in function
    assert "schedule_weeks=weeks," in function

    # ⛔ 不解释 opaque：**代码体**不得出现 teacher 注入 / 姓名启发式 / 转义启发式
    #    （docstring 里会以"⛔ 不得…"的形式提到这些词，因此只看 docstring 之后的代码）
    docstring_end = function.index('"""', function.index('"""') + 3) + 3
    body = function[docstring_end:]
    for forbidden in ("teachingName", "charCodeAt", "codePointAt", "\\u4e00"):
        assert forbidden not in body, f"⛔ Layout B 代码不得出现：{forbidden}"


def test_parser_checks_layout_b_before_the_concrete_four_field_path() -> None:
    """⛔ 判定必须发生在 `parse_weekday(fields[1])` **之前**（否则永远到不了）。"""

    source = parser_source()

    layout_b = source.index("_try_parse_four_field_non_concrete_layout_b(fields, offset)")
    weekday = source.index("weekday = parse_weekday(fields[1])")
    sections = source.index("start_section, end_section = parse_sections(fields[2])")

    assert layout_b < weekday, "Layout B 判定必须早于 concrete 路径的 weekday 解析"
    assert layout_b < sections

    # Layout A 冻结：其判定与调用点仍在（5 字段）
    assert "_try_parse_five_field_non_concrete_layout_a(fields, offset)" in source
    assert source.index("_try_parse_five_field_non_concrete_layout_a(fields, offset)") < sections


def test_layout_a_and_concrete_paths_are_unchanged_by_layout_b(
    collector_source: str,
) -> None:
    """⛔ Layout A / concrete 均未因 Layout B 改动。"""

    source = parser_source()

    # Layout A 的五条准入仍在
    layout_a_start = source.index("def _try_parse_five_field_non_concrete_layout_a(")
    layout_a_end = source.index("def _try_parse_four_field_non_concrete_layout_b(", layout_a_start)
    layout_a = source[layout_a_start:layout_a_end]
    for required in (
        "_LAYOUT_A_NON_CONCRETE_FIELD_COUNT",
        "_classify_five_field_token(fields[2].strip()) != _FIVE_FIELD_LOCATION",
        "if fields[3] != _REDACTED_TEACHER_PLACEHOLDER:",
    ):
        assert required in layout_a, f"Layout A 准入丢失：{required}"

    # concrete 4 字段（weeks / weekday / sections / activity）仍走原路径
    assert "if field_count == FIELDS_WITHOUT_LOCATION_WITHOUT_TEACHER:" in source
    assert "campus, classroom, teacher = None, None, None" in source

