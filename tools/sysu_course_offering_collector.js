/**
 * 学航·转衔 —— SYSU 开课数据「显式触发」浏览器端采集器（Phase 2B-2C1A）
 * ================================================================
 *
 * 定位
 * ----
 * 本文件是 **SYSU-specific Transport 的浏览器侧实现**。
 * 它提供两件事：
 *   1. `collect()` —— 串行取页 → 最小化字段 + 脱敏 → 产出本地 Capture Bundle；
 *   2. `diagnoseSchedulePresence()` —— **只取第 1 页一次**的**结构诊断**（只统计，不产出数据）。
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
 *     await window.XuehangSysuCollector.diagnoseSchedulePresence({ semester: "2026-1" })
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
 * ⛔ 结构诊断的定位
 * ----------------
 * `diagnoseSchedulePresence()` 是**取证**，**不是** workaround：
 * 它只统计 `teachingTimePlaceStr` 的存在形态，**不**改造数据、
 * **不**放宽 `collect()` 的 fail-closed 行为、**不**产出 Capture Bundle。
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
   *
   * `humanRowNo` 为**从 1 开始**的人类行号，只用于错误信息（见 `minimizeRow`）。
   */
  function redactSegmentTeacher(segment, pageNo, humanRowNo) {
    var fields = segment.split(FIELD_SEPARATOR);

    if (fields.length !== 5 && fields.length !== 6) {
      fail(
        "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
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
        "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
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
   *
   * `humanRowNo` 为**从 1 开始**的人类行号，只用于错误信息（见 `minimizeRow`）。
   */
  function redactTeachingTimePlace(text, pageNo, humanRowNo) {
    if (typeof text !== "string" || text === "") {
      fail("第 " + pageNo + " 页第 " + humanRowNo + " 条记录缺少可用的 teachingTimePlaceStr。");
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
        "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
          "出现多个末尾逗号。已整体停止。"
      );
    }

    var hadTrailingComma = trailingEmpty === 1;
    if (hadTrailingComma) {
      segments.pop();
    }

    if (segments.length === 0) {
      fail("第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr 没有有效 segment。");
    }

    var redacted = segments.map(function (segment) {
      if (segment.trim() === "") {
        fail(
          "第 " + pageNo + " 页第 " + humanRowNo + " 条记录的 teachingTimePlaceStr " +
            "出现中间空 segment。已整体停止。"
        );
      }
      return redactSegmentTeacher(segment, pageNo, humanRowNo);
    });

    return redacted.join(SEGMENT_SEPARATOR) + (hadTrailingComma ? SEGMENT_SEPARATOR : "");
  }

  // ---------------------------------------------------------------------
  // 数据最小化
  // ---------------------------------------------------------------------

  /**
   * 取一条 row 的最小化副本：只保留 `KEPT_ROW_FIELDS`，
   * 并把 `teachingTimePlaceStr` 覆盖为脱敏后的文本。
   *
   * ⚠️ **`humanRowNo` 是从 1 开始的人类行号，只用于错误信息**。
   * 调用方在第 1 页对第 1 条记录报告"第 1 条"，
   * 因此 `collect()` 传入的是 `Array.prototype.map` 的 **0-based** 下标 **加 1**。
   * 这样错误信息可以直接和浏览器里看到的行号对齐；**报告的是行数，不是数组下标**。
   */
  function minimizeRow(row, pageNo, humanRowNo) {
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      fail("第 " + pageNo + " 页第 " + humanRowNo + " 条记录不是对象。");
    }

    var minimized = {};
    for (var i = 0; i < KEPT_ROW_FIELDS.length; i += 1) {
      var field = KEPT_ROW_FIELDS[i];
      if (!Object.prototype.hasOwnProperty.call(row, field)) {
        fail("第 " + pageNo + " 页第 " + humanRowNo + " 条记录缺少字段：" + field);
      }
      minimized[field] = row[field];
    }

    // 覆盖为脱敏后的文本（教师姓名不写入 Capture Bundle）。
    minimized.teachingTimePlaceStr = redactTeachingTimePlace(
      row.teachingTimePlaceStr,
      pageNo,
      humanRowNo
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

      // 报告给用户的行号从 1 开始：map 的下标是 0-based，因此显式 + 1。
      // 不改变顺序、不跳过任何 row、不做任何字段修补。
      var minimizedRows = data.rows.map(function (row, rowIndex) {
        return minimizeRow(row, currentPageNo, rowIndex + 1);
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

  // ---------------------------------------------------------------------
  // 结构诊断（Phase 2B-2C1B）：只取证，不是 workaround
  // ---------------------------------------------------------------------

  /** 诊断统计的目标字段名。 */
  var SCHEDULE_FIELD = "teachingTimePlaceStr";

  /** 诊断固定只取第 1 页（不对外开放、不循环、不重试）。 */
  var DIAGNOSTIC_PAGE_NO = 1;

  /** 诊断固定使用已验证的单页上限。 */
  var DIAGNOSTIC_PAGE_SIZE = 200;

  /**
   * 纯函数：统计 `rows` 中 `teachingTimePlaceStr` 的存在形态。
   *
   * 分类（互斥且穷尽）：
   *   missing          —— 字段不存在
   *   null             —— 字段存在且值为 null
   *   empty_string     —— 值是字符串但 trim 后为空
   *   non_empty_string —— 值是字符串且 trim 后非空
   *   other_type       —— 字段存在，但既不是 null 也不是字符串
   *
   * 保证：missing + null + empty_string + non_empty_string + other_type === rows.length
   *
   * ⛔ 只统计数量，**不返回也不打印**任何 row 内容、课程号、教师、教室或原文。
   */
  function summarizeSchedulePresence(rows) {
    if (!Array.isArray(rows)) {
      fail("诊断需要 data.rows 是数组。已停止。");
    }

    var bucket = {
      missing: 0,
      null: 0,
      empty_string: 0,
      non_empty_string: 0,
      other_type: 0
    };

    for (var index = 0; index < rows.length; index += 1) {
      var row = rows[index];

      if (!row || typeof row !== "object" || Array.isArray(row)) {
        // 只报结构性问题与下标，不回显 row 内容。
        fail("诊断遇到非对象 row（下标 " + index + "）。已停止。");
      }

      if (!Object.prototype.hasOwnProperty.call(row, SCHEDULE_FIELD)) {
        bucket.missing += 1;
        continue;
      }

      var value = row[SCHEDULE_FIELD];

      if (value === null) {
        bucket.null += 1;
      } else if (typeof value === "string") {
        if (value.trim() === "") {
          bucket.empty_string += 1;
        } else {
          bucket.non_empty_string += 1;
        }
      } else {
        bucket.other_type += 1;
      }
    }

    return {
      total_rows: rows.length,
      teachingTimePlaceStr: bucket
    };
  }

  /**
   * 结构诊断：**只请求第 1 页一次**，统计 `teachingTimePlaceStr` 的存在形态。
   *
   * - 复用现有 hostname guard / same-origin 请求 / 既有取页函数的
   *   HTTP / JSON / code / total / rows 校验（**不复制认证逻辑**）；
   * - 固定 `pageNo = DIAGNOSTIC_PAGE_NO`（1）、`pageSize = DIAGNOSTIC_PAGE_SIZE`（200）；
   * - ⛔ 不接受任何分页选项（没有 maxPages / firstPageNo / 循环 / 重试 / 并发）；
   * - ⛔ **不生成 Capture Bundle**、不做字段最小化、不做教师脱敏、不调用 `toJson`；
   * - ⛔ 不修改 `collect()` 的 fail-closed 行为 —— 本函数只是取证，不是 workaround。
   *
   * 返回值只有聚合统计，**不含**任何 Raw row / 课程号 / 教师 / 教室 / 原文。
   */
  async function diagnoseSchedulePresence(options) {
    requireAllowedHost();

    var opts = options || {};

    var semester = opts.semester;
    if (typeof semester !== "string" || semester.trim() === "") {
      fail('诊断必须显式提供非空 semester（例如 "2026-1"）。');
    }
    semester = semester.trim();

    // 只取第 1 页、只取一次。
    var data = await requestPage(semester, DIAGNOSTIC_PAGE_NO, DIAGNOSTIC_PAGE_SIZE);

    var summary = summarizeSchedulePresence(data.rows);

    return {
      semester: semester,
      page_no: DIAGNOSTIC_PAGE_NO,
      page_size: DIAGNOSTIC_PAGE_SIZE,
      reported_total: data.total,
      total_rows: summary.total_rows,
      teachingTimePlaceStr: summary.teachingTimePlaceStr
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
    diagnoseSchedulePresence: diagnoseSchedulePresence,
    summarizeSchedulePresence: summarizeSchedulePresence,
    toJson: toJson,
    DIAGNOSTIC_PAGE_NO: DIAGNOSTIC_PAGE_NO,
    DIAGNOSTIC_PAGE_SIZE: DIAGNOSTIC_PAGE_SIZE,
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
