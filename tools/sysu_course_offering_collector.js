/**
 * 学航·转衔 —— SYSU 开课数据「显式触发」浏览器端采集器（Phase 2B-2C1A）
 * ================================================================
 *
 * 定位
 * ----
 * 本文件是 **SYSU-specific Transport 的浏览器侧实现**。
 * 它只做三件事：串行取页 → 最小化字段 + 脱敏 → 产出本地 Capture Bundle。
 *
 * ⛔ 本文件**不实现**任何后端直连学校的认证 HTTP 客户端。
 * 认证完全交给浏览器既有的登录状态（`credentials: "same-origin"`），
 * 本采集器**不读取、不保存、不打印、不导出**任何浏览器端认证状态。
 *
 * ⛔ 加载脚本 ≠ 开始采集
 * ---------------------
 * 加载本文件**不会**发送任何请求：没有顶层调用、没有定时轮询、没有页面加载钩子。
 * 用户必须在控制台**显式调用**：
 *
 *     await window.XuehangSysuCollector.collect({ semester: "2026-1" })
 *
 * 默认只跑 2 页 smoke test；要跑更多页必须显式提高 `maxPages`，并会弹出确认框。
 *
 * 取出结果：
 *
 *     const result = await window.XuehangSysuCollector.collect({ semester: "2026-1" });
 *     const text = window.XuehangSysuCollector.toJson(result);   // 裸 Capture Bundle
 *
 * `toJson()` 输出的**顶层就是** `format` / `semester` / `first_page_no` / `page_size` / `pages`，
 * 可直接交给 Python 的 `load_capture_bundle(...)`。
 *
 * ⛔ 参数归属
 * ----------
 * `pageSize = 200` 与 `firstPageNo = 1` 是 **SYSU 已验证的专有取值**，只属于本 Transport，
 * **不会**反向写进通用 `backend/app/course_data/pagination.py`。
 * `firstPageNo` 被**锁定为 1**：传入其它起始页会在发请求之前直接失败
 * （通用多起始页能力留在 backend 分页核心，不在这里放开）。
 *
 * ⛔ 完整性归属
 * ------------
 * 本采集器**不判断** completeness。它只负责安全地取回并脱敏，
 * 最终 `complete` / `partial` 由 Python Pagination Core 依据证据链判定。
 *
 * ⛔ 产物归属
 * ----------
 * 采集结果仍是 **Real Sanitized Capture**：不得提交 Git、不得放入 `mock_data/`、
 * 不得作为测试 fixture、不得复制进 docs / worklog。
 */

(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // 常量
  // ---------------------------------------------------------------------

  /** 只允许在本人已登录的教务页面上运行。 */
  var ALLOWED_HOSTNAME = "jwxt.sysu.edu.cn";

  /** 已确认的请求路径（same-origin relative URL）。 */
  var ENDPOINT_PATH =
    "/jwxt/schedule/agg/schoolOpeningCoursesSchedule/querySchoolOpeningCourses";

  /** SYSU 已验证：起始页码为 1。 */
  var FIRST_PAGE_NO = 1;

  /** SYSU 已验证：单页最大支持 200（负责人人工确认）。 */
  var MAX_PAGE_SIZE = 200;

  /** SYSU 已验证：pageSize=200 请求成功。 */
  var DEFAULT_PAGE_SIZE = 200;

  /** 串行请求间隔：默认 1500ms，下限 1000ms。 */
  var DEFAULT_DELAY_MS = 1500;
  var MIN_DELAY_MS = 1000;

  /** 默认只做 2 页 smoke test；50 是**客户端安全上限**，不是学校系统限制。 */
  var DEFAULT_MAX_PAGES = 2;
  var ABSOLUTE_MAX_PAGES = 50;

  /** Capture Bundle 格式标识（Course Data **内部**交换格式，不是公共 Schema）。 */
  var CAPTURE_FORMAT = "sysu-opening-courses-capture-v1";

  /** 输出前**只保留** Python importer 真正需要的字段。 */
  var KEPT_ROW_FIELDS = [
    "courseNum",
    "courseName",
    "classNumber",
    "yearTerm",
    "score",
    "limitNumber",
    "selectedNumber",
    "teachingTimePlaceStr"
  ];

  /** 已确认的 segment / field 分隔符。 */
  var SEGMENT_SEPARATOR = ",";
  var FIELD_SEPARATOR = "/";

  /** segment 内 teacher 的脱敏占位符。 */
  var REDACTED_TEACHER = "REDACTED";

  // ---------------------------------------------------------------------
  // 基础工具
  // ---------------------------------------------------------------------

  function fail(message) {
    throw new Error("[学航采集器] " + message);
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function requireAllowedHost() {
    if (
      typeof window === "undefined" ||
      !window.location ||
      window.location.hostname !== ALLOWED_HOSTNAME
    ) {
      fail(
        "当前页面不是 " + ALLOWED_HOSTNAME + "，拒绝执行。" +
          "本采集器只允许在本人已登录、已有权限的教务页面内运行。"
      );
    }
  }

  // ---------------------------------------------------------------------
  // 脱敏：teachingTimePlaceStr 内 segment 的 teacher
  // ---------------------------------------------------------------------

  /**
   * 对一个 segment 脱敏：只把 teacher 字段替换为 REDACTED。
   *
   * 已确认结构：
   *   5 fields: weeks / weekday / sections / teacher / activity
   *   6 fields: weeks / weekday / sections / location / teacher / activity
   *
   * 其余字段（weeks / weekday / sections / location / activity）**原样保留**。
   */
  function redactSegmentTeacher(segment, pageNo, rowIndex) {
    var fields = segment.split(FIELD_SEPARATOR);

    if (fields.length !== 5 && fields.length !== 6) {
      fail(
        "第 " + pageNo + " 页第 " + rowIndex + " 条记录的 teachingTimePlaceStr " +
          "出现不支持的字段数（" + fields.length + "）。本采集器不猜格式，已整体停止。"
      );
    }

    var teacherIndex = fields.length === 6 ? 4 : 3;
    var teacher = fields[teacherIndex];

    // ⛔ 替换前必须确认原 teacher 确实存在：
    // 空 teacher 若也被写成 REDACTED，等于**静默修复**了原始数据问题，
    // 会让下游 Python parser 误以为这条记录合法。
    // 错误信息不回显 teacher 取值。
    if (typeof teacher !== "string" || teacher.trim() === "") {
      fail(
        "第 " + pageNo + " 页第 " + rowIndex + " 条记录的 teachingTimePlaceStr " +
          "中 teacher 字段为空或不是字符串。本采集器不写入脱敏占位符来掩盖该问题，已整体停止。"
      );
    }

    fields[teacherIndex] = REDACTED_TEACHER;

    return fields.join(FIELD_SEPARATOR);
  }

  /**
   * 对整条 teachingTimePlaceStr 脱敏，并保持全部已确认结构：
   * segment 顺序、`/`、`,`、**最多一个** trailing comma、
   * location 原文、weeks / weekday / sections / activity 原文。
   */
  function redactTeachingTimePlace(text, pageNo, rowIndex) {
    if (typeof text !== "string" || text === "") {
      fail("第 " + pageNo + " 页第 " + rowIndex + " 条记录缺少可用的 teachingTimePlaceStr。");
    }

    var segments = text.split(SEGMENT_SEPARATOR);

    // 只允许**最多一个**末尾逗号：单个末尾空段可忽略，多个整体失败。
    var trailingEmpty = 0;
    for (var i = segments.length - 1; i >= 0; i -= 1) {
      if (segments[i].trim() !== "") {
        break;
      }
      trailingEmpty += 1;
    }

    if (trailingEmpty > 1) {
      fail(
        "第 " + pageNo + " 页第 " + rowIndex + " 条记录的 teachingTimePlaceStr " +
          "出现多个末尾逗号。已整体停止。"
      );
    }

    var hadTrailingComma = trailingEmpty === 1;
    if (hadTrailingComma) {
      segments.pop();
    }

    if (segments.length === 0) {
      fail("第 " + pageNo + " 页第 " + rowIndex + " 条记录的 teachingTimePlaceStr 没有有效 segment。");
    }

    var redacted = segments.map(function (segment) {
      if (segment.trim() === "") {
        fail(
          "第 " + pageNo + " 页第 " + rowIndex + " 条记录的 teachingTimePlaceStr " +
            "出现中间空 segment。已整体停止。"
        );
      }
      return redactSegmentTeacher(segment, pageNo, rowIndex);
    });

    return redacted.join(SEGMENT_SEPARATOR) + (hadTrailingComma ? SEGMENT_SEPARATOR : "");
  }

  // ---------------------------------------------------------------------
  // 数据最小化
  // ---------------------------------------------------------------------

  function minimizeRow(row, pageNo, rowIndex) {
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      fail("第 " + pageNo + " 页第 " + rowIndex + " 条记录不是对象。");
    }

    var minimized = {};
    for (var i = 0; i < KEPT_ROW_FIELDS.length; i += 1) {
      var field = KEPT_ROW_FIELDS[i];
      if (!Object.prototype.hasOwnProperty.call(row, field)) {
        fail("第 " + pageNo + " 页第 " + rowIndex + " 条记录缺少字段：" + field);
      }
      minimized[field] = row[field];
    }

    // 覆盖为脱敏后的文本（教师姓名不写入 Capture Bundle）。
    minimized.teachingTimePlaceStr = redactTeachingTimePlace(
      row.teachingTimePlaceStr,
      pageNo,
      rowIndex
    );

    return minimized;
  }

  // ---------------------------------------------------------------------
  // 单页请求
  // ---------------------------------------------------------------------

  function validatePagePayload(payload, pageNo) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      fail("第 " + pageNo + " 页响应不是对象。");
    }
    if (payload.code !== 200) {
      fail("第 " + pageNo + " 页 code 不是 200（实际 " + payload.code + "）。已整体停止。");
    }

    var data = payload.data;
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      fail("第 " + pageNo + " 页 data 不是对象。已整体停止。");
    }
    if (!Number.isInteger(data.total) || data.total < 0) {
      fail("第 " + pageNo + " 页 data.total 不是非负整数。已整体停止。");
    }
    if (!Array.isArray(data.rows)) {
      fail("第 " + pageNo + " 页 data.rows 不是数组。已整体停止。");
    }

    return data;
  }

  /**
   * 取一页：same-origin POST，认证状态由浏览器自己带上。
   *
   * `?_t=` 只是**复现已观察到的请求形态**（已观察请求带时间戳参数），
   * 不代表任何业务语义。
   */
  async function requestPage(semester, pageNo, pageSize) {
    var url = ENDPOINT_PATH + "?_t=" + Date.now();

    var response;
    try {
      response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pageNo: pageNo,
          pageSize: pageSize,
          total: true,
          param: { yearTerm: semester }
        })
      });
    } catch (error) {
      fail("第 " + pageNo + " 页请求失败：" + error.message + "。已整体停止。");
    }

    if (response.status === 401 || response.status === 403) {
      fail(
        "第 " + pageNo + " 页返回 " + response.status + "（认证或权限不足）。" +
          "已整体停止；本采集器不会尝试寻找或提取任何认证信息。【BLOCKED】"
      );
    }
    if (!response.ok) {
      fail("第 " + pageNo + " 页 HTTP 状态异常：" + response.status + "。已整体停止。");
    }

    var contentType = response.headers.get("content-type") || "";
    if (contentType.indexOf("application/json") === -1) {
      fail(
        "第 " + pageNo + " 页返回的不是 JSON（可能被重定向到登录页）。已整体停止。"
      );
    }

    var payload;
    try {
      payload = await response.json();
    } catch (error) {
      fail("第 " + pageNo + " 页 JSON 解析失败。已整体停止。");
    }

    return validatePagePayload(payload, pageNo);
  }

  // ---------------------------------------------------------------------
  // 主流程：必须由用户显式调用
  // ---------------------------------------------------------------------

  async function collect(options) {
    requireAllowedHost();

    var opts = options || {};

    var semester = opts.semester;
    if (typeof semester !== "string" || semester.trim() === "") {
      fail('必须显式提供非空 semester（例如 "2026-1"）。');
    }
    semester = semester.trim();

    var pageSize = opts.pageSize === undefined ? DEFAULT_PAGE_SIZE : opts.pageSize;
    if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
      fail(
        "pageSize 必须是 1.." + MAX_PAGE_SIZE + " 之间的整数" +
          "（SYSU 单页上限已人工验证为 " + MAX_PAGE_SIZE + "）。"
      );
    }

    // ⛔ SYSU 只验证过 firstPageNo=1：
    // 不允许调用方传入其它起始页（那会对学校发起**未经验证**的页码请求）。
    // 通用多起始页能力属于 backend 分页核心，不在这里放开。
    if (opts.firstPageNo !== undefined && opts.firstPageNo !== FIRST_PAGE_NO) {
      fail(
        "SYSU 只验证过 firstPageNo=" + FIRST_PAGE_NO + "，不接受其它起始页。已整体停止。"
      );
    }
    var firstPageNo = FIRST_PAGE_NO;

    var maxPages = opts.maxPages === undefined ? DEFAULT_MAX_PAGES : opts.maxPages;
    if (!Number.isInteger(maxPages) || maxPages < 1 || maxPages > ABSOLUTE_MAX_PAGES) {
      fail("maxPages 必须是 1.." + ABSOLUTE_MAX_PAGES + " 之间的整数。");
    }

    var delayMs = opts.delayMs === undefined ? DEFAULT_DELAY_MS : opts.delayMs;
    if (!Number.isInteger(delayMs) || delayMs < MIN_DELAY_MS) {
      fail("delayMs 不得小于 " + MIN_DELAY_MS + " 毫秒（串行、低频）。");
    }

    // 超过默认 smoke 页数时，必须由用户明确确认。
    if (maxPages > DEFAULT_MAX_PAGES) {
      var confirmed = window.confirm(
        "即将对本人已授权可见的 " + semester + " 开课数据执行串行采集。\n" +
          "pageSize=" + pageSize + "\n" +
          "最多请求 " + maxPages + " 页\n" +
          "请求间隔至少 " + delayMs / 1000 + " 秒\n" +
          "是否继续？"
      );
      if (!confirmed) {
        return { cancelled: true, requests: 0, bundle: null };
      }
    }

    var pages = [];
    var expectedTotal = null;
    var accumulatedRows = 0;
    var requests = 0;
    var stoppedReason = "max_pages";

    // 严格串行：一页一页取，中间 sleep；不并发、不预取。
    for (var index = 0; index < maxPages; index += 1) {
      var currentPageNo = firstPageNo + index;

      if (index > 0) {
        await sleep(delayMs);
      }

      var data = await requestPage(semester, currentPageNo, pageSize);
      requests += 1;

      if (expectedTotal === null) {
        expectedTotal = data.total;
      } else if (data.total !== expectedTotal) {
        fail(
          "第 " + currentPageNo + " 页的 data.total(" + data.total + ")与首页(" +
            expectedTotal + ")不一致；采集期间数据集合发生变化，已整体停止。"
        );
      }

      if (data.rows.length === 0 && accumulatedRows < expectedTotal) {
        fail(
          "第 " + currentPageNo + " 页为空，但累计(" + accumulatedRows +
            ")仍未达到 total(" + expectedTotal + ")。已整体停止。"
        );
      }

      accumulatedRows += data.rows.length;
      if (accumulatedRows > expectedTotal) {
        fail(
          "累计行数(" + accumulatedRows + ")超过 total(" + expectedTotal + ")。已整体停止。"
        );
      }

      var minimizedRows = data.rows.map(function (row, rowIndex) {
        return minimizeRow(row, currentPageNo, rowIndex);
      });

      pages.push({
        page_no: currentPageNo,
        response: {
          code: 200,
          data: { total: data.total, rows: minimizedRows }
        }
      });

      if (accumulatedRows === expectedTotal) {
        stoppedReason = "reached_total";
        break;
      }
    }

    return {
      cancelled: false,
      requests: requests,
      stoppedReason: stoppedReason,
      accumulatedRows: accumulatedRows,
      expectedTotal: expectedTotal,
      // 明确：本采集器**不判断**完整性，complete / partial 交给 Python Pagination Core。
      claimedComplete: false,
      bundle: {
        format: CAPTURE_FORMAT,
        semester: semester,
        first_page_no: firstPageNo,
        page_size: pageSize,
        pages: pages
      }
    };
  }

  /**
   * 把采集结果序列化成**裸 Capture Bundle**（可直接交给 Python `load_capture_bundle`）。
   *
   * 顶层就是 `format` / `semester` / `first_page_no` / `page_size` / `pages`，
   * 不含 wrapper 字段 —— 这样自然用法是：
   *
   *     const result = await window.XuehangSysuCollector.collect({ semester: "2026-1" });
   *     const text = window.XuehangSysuCollector.toJson(result);
   *
   * ⛔ 采集被取消或没有 bundle 时**直接失败**，不生成伪 bundle。
   * ⛔ 写文件由用户自行决定，本文件不落盘。
   */
  function toJson(result) {
    if (!result || result.cancelled === true || !result.bundle) {
      fail(
        "没有可序列化的 Capture Bundle（采集被取消或未产生 bundle）。" +
          "本采集器不会生成伪 bundle。"
      );
    }
    return JSON.stringify(result.bundle, null, 2);
  }

  // ---------------------------------------------------------------------
  // 显式暴露（加载本文件不触发任何请求）
  // ---------------------------------------------------------------------

  window.XuehangSysuCollector = {
    collect: collect,
    toJson: toJson,
    CAPTURE_FORMAT: CAPTURE_FORMAT,
    ALLOWED_HOSTNAME: ALLOWED_HOSTNAME,
    ENDPOINT_PATH: ENDPOINT_PATH,
    FIRST_PAGE_NO: FIRST_PAGE_NO,
    MAX_PAGE_SIZE: MAX_PAGE_SIZE,
    DEFAULT_PAGE_SIZE: DEFAULT_PAGE_SIZE,
    DEFAULT_MAX_PAGES: DEFAULT_MAX_PAGES,
    ABSOLUTE_MAX_PAGES: ABSOLUTE_MAX_PAGES,
    DEFAULT_DELAY_MS: DEFAULT_DELAY_MS,
    MIN_DELAY_MS: MIN_DELAY_MS,
    REDACTED_TEACHER: REDACTED_TEACHER
  };
})();
